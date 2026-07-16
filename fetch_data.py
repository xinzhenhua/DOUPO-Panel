#!/usr/bin/env python3
"""
豆粕基本面数据自动抓取脚本
============================
这个脚本设计为在 GitHub Actions 里运行（服务器端），不是在浏览器里运行。
服务器端运行不受 CORS 限制，可以自由请求任何网站的数据。

抓取的数据：
1. USDA-FAS 出口销售数据（ESR）- 豆粕(Soybean Cake and Meal)
2. USDA-FAS 供需库存数据（PSD）- 等同 WASDE 核心数据
3. CBOT 豆粕期货价格（通过 Yahoo Finance 非官方接口）
4. US Drought Monitor 官方干旱监测数据
5. UN Comtrade 中国大豆进口官方数据
6. USDA/AMS 谷物出口检验数据（用来推算"本月到港预报"）

关于开机率/商业库存/现货基差/猪粮比/能繁母猪这5项：
之前用Groq+Tavily做过AI辅助搜索自动化，实测发现数据质量不稳定
（比如把某公司PDF公告误当成全国数据、把价格表格误判成基差数据），
已放弃这个方向。现在改用"批量粘贴解析"方案：用户自己选择任意AI工具
获取数据(网页里有一键复制的提示词按钮)，把AI的回答粘贴回网页，
由前端JS纯文本解析并自动填充到对应输入框。这样数据的可信度由用户自己
选择的信息源和AI工具决定，网页本身只负责"解析+填充"这个机械环节，
不再涉及自动判断数据是否权威/相关。

运行方式：
    export USDA_API_KEY=你的api.data.gov密钥
    python3 fetch_data.py

输出：
    data/latest.json  ← 网页会读取这个文件
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta

USDA_API_KEY = os.environ.get("USDA_API_KEY", "")
NASS_API_KEY = os.environ.get("NASS_API_KEY", "")  # 单独申请：quickstats.nass.usda.gov/api（跟FAS的密钥是两套系统）
USDA_BASE = "https://api.fas.usda.gov/api"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "latest.json")

# ---------------------------------------------------------------------------
# 通用请求函数（带重试，避免单次网络抖动导致整个流程失败）
# ---------------------------------------------------------------------------
def fetch_json(url, headers=None, retries=3, timeout=20):
    data, _ = fetch_json_debug(url, headers=headers, retries=retries, timeout=timeout)
    return data


def fetch_json_debug(url, headers=None, retries=3, timeout=20):
    """
    跟 fetch_json 一样，但额外返回诊断信息 (data, debug)。
    debug 里包含：实际请求的url、HTTP状态码、响应体前500字符、异常信息。
    这样接口返回的东西跟预期不一致时，不需要去翻GitHub Actions运行日志，
    直接看 data/latest.json 里的诊断字段就知道真实情况是什么。
    """
    headers = dict(headers or {})
    # 防御性修复：很多网站/API服务(包括Groq)会挡掉Python urllib默认的User-Agent
    # (被Cloudflare等WAF当作机器人流量拦截，报错"error code: 1010")，
    # 这里统一给个正常浏览器UA垫底，调用方传入的headers仍可以覆盖它。
    headers.setdefault("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    debug = {"url": url}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                debug["httpStatus"] = resp.status
                debug["rawSnippet"] = raw[:500]
                try:
                    return json.loads(raw), debug
                except json.JSONDecodeError as je:
                    debug["error"] = f"JSON解析失败: {je}（接口可能返回了非JSON内容，比如CSV或HTML）"
                    print(f"[WARN] JSON解析失败: {url} -> {je}\n  原始内容片段: {raw[:300]}", file=sys.stderr)
                    return None, debug
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:  # noqa: BLE001
                pass
            debug["httpStatus"] = e.code
            debug["error"] = f"HTTP {e.code}: {e.reason}"
            debug["rawSnippet"] = body
            print(f"[WARN] 请求失败(HTTP {e.code}): {url} -> {e.reason}\n  响应体: {body}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # noqa: BLE001 - 抓取脚本，任何异常都要能继续
            debug["error"] = str(e)
            print(f"[WARN] 请求失败: {url} -> {e}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return None, debug


def get_soybean_meal_esr_code():
    """动态查找"大豆粕/豆饼"在 ESR 商品列表里的编码，避免硬编码错误的代码。
    返回 (code, debug)：code为None时，debug里会说明具体是"请求失败"还是"没匹配上"，
    这两种情况原因完全不同，不应该用同一句模糊的错误信息掩盖。"""
    data, debug = fetch_json_debug(f"{USDA_BASE}/esr/commodities", headers={"X-Api-Key": USDA_API_KEY})
    if not data:
        debug["failureStage"] = "请求/esr/commodities本身失败（网络问题、认证失败、或被限流）"
        return None, debug
    for item in data:
        name = (item.get("commodityName") or "").lower()
        if "soybean" in name and ("meal" in name or "cake" in name):
            return item.get("commodityCode"), None
    # 请求成功、拿到了数据，但没有一条命中"soybean"+"meal/cake"，
    # 这跟"请求失败"是完全不同的情况——很可能是接口把商品名称改了，附上实际收到的完整列表方便核对
    debug["failureStage"] = "接口请求成功，拿到了商品列表，但没有一条命中'soybean'+'meal或cake'关键词"
    debug["actualCommodityNamesSeen"] = sorted(set((item.get("commodityName") or "") for item in data))[:50]
    debug["totalCommoditiesReturned"] = len(data)
    return None, debug


def fetch_esr_export_sales():
    code, code_lookup_debug = get_soybean_meal_esr_code()
    if not code:
        return {
            "available": False,
            "reason": "未能找到豆粕的ESR商品编码",
            "debug": code_lookup_debug,
        }

    # ★ 已修复：之前用"10月做分界"猜市场年度，实测发现猜错了
    #   （查到marketYear=2025时，最新数据停在2025-10-02，说明那是个已完结、不再更新的年度）。
    #   现在不再猜，而是同时试几个候选年份，用真实返回数据里最新的日期来判断哪个年度是当前活跃的。
    now = datetime.now(timezone.utc)
    candidate_years = [now.year - 1, now.year, now.year + 1]
    best_rows, best_debug, best_year = None, None, None
    all_attempts_debug = {}

    for candidate_my in candidate_years:
        url = f"{USDA_BASE}/esr/exports/commodityCode/{code}/allCountries/marketYear/{candidate_my}"
        rows, debug = fetch_json_debug(url, headers={"X-Api-Key": USDA_API_KEY})
        all_attempts_debug[str(candidate_my)] = {
            "httpStatus": debug.get("httpStatus"),
            "rowCount": len(rows) if rows else 0,
            "latestWeekFound": max((r.get("weekEndingDate") for r in rows if r.get("weekEndingDate")), default=None) if rows else None,
        }
        if not rows:
            continue
        candidate_latest_week = max((r.get("weekEndingDate") for r in rows if r.get("weekEndingDate")), default=None)
        if candidate_latest_week is None:
            continue
        best_latest_week = max((r.get("weekEndingDate") for r in best_rows if r.get("weekEndingDate")), default=None) if best_rows else None
        if best_rows is None or candidate_latest_week > best_latest_week:
            best_rows, best_debug, best_year = rows, debug, candidate_my

    rows, debug = best_rows, best_debug
    if not rows:
        return {
            "available": False,
            "reason": "ESR接口无返回数据（已尝试" + "、".join(str(y) for y in candidate_years) + "这几个候选年份）",
            "debug": all_attempts_debug,
        }

    # 关键点：每周有多个国家的记录，不能直接用 rows[-1]/rows[-2]
    # （那样可能取到"同一周的另一个国家"而不是"上一周"）。
    # 必须先拿到"去重后的周次日期"排序，再取最近两个不同的周。
    unique_weeks = sorted(set(r.get("weekEndingDate") for r in rows if r.get("weekEndingDate")))
    if len(unique_weeks) < 2:
        return {
            "available": False,
            "reason": "数据量不足以计算环比（不足两个不同周次）",
            "debug": {"note": f"拿到{len(rows)}条记录，但去重后只有{len(unique_weeks)}个周次", "sampleRawRow": rows[0] if rows else None},
        }

    latest_week_date = unique_weeks[-1]
    prev_week_date = unique_weeks[-2]

    # 汇总所有国家在某一周的净销售量（weeklyExports字段名可能随API版本略有差异，做容错）
    def week_total(week_rows, field_candidates):
        total = 0
        for r in week_rows:
            for f in field_candidates:
                if f in r and r[f] is not None:
                    total += r[f]
                    break
        return total

    latest_week = [r for r in rows if r.get("weekEndingDate") == latest_week_date]
    prev_week = [r for r in rows if r.get("weekEndingDate") == prev_week_date]

    net_sales_field_candidates = ["weeklyExports", "grossNewSales", "netSales"]
    latest_total = week_total(latest_week, net_sales_field_candidates)
    prev_total = week_total(prev_week, net_sales_field_candidates)

    china_latest = sum(
        r.get("weeklyExports", 0) or 0
        for r in latest_week
        if "china" in (r.get("countryName") or "").lower()
    )

    wow_change_pct = None
    if prev_total:
        wow_change_pct = round((latest_total - prev_total) / abs(prev_total) * 100, 1)

    # 计算数据新鲜度：即便三个候选年份里选出了"最新的"，也可能三个都不新鲜
    # （比如接口本身更新滞后）。ESR是每周更新的报告，超过25天没更新就该提醒一下。
    try:
        latest_date_parsed = datetime.fromisoformat(latest_week_date.replace("Z", "+00:00"))
        if latest_date_parsed.tzinfo is None:
            latest_date_parsed = latest_date_parsed.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - latest_date_parsed).days
    except (ValueError, AttributeError):
        age_days = None
    is_stale = age_days is not None and age_days > 25

    result = {
        "available": True,
        "weekEnding": latest_week_date,
        "marketYearUsed": best_year,
        "dataAgeDays": age_days,
        "isStale": is_stale,
        "latestTotalMT": latest_total,
        "prevTotalMT": prev_total,
        "wowChangePct": wow_change_pct,
        "chinaLatestMT": china_latest,
        "source": "USDA-FAS ESR API",
        "sourceUrl": "https://apps.fas.usda.gov/esrqs/",
    }
    if is_stale:
        result["debug"] = {
            "warning": f"三个候选年份({candidate_years})里最新数据是{latest_week_date}，距今{age_days}天，"
                       f"已超过25天的新鲜度阈值，ESR是每周更新的报告，这可能意味着接口有延迟或候选年份范围需要调整",
            "allCandidateYearsResults": all_attempts_debug,
        }
    # 如果拿到了记录，但汇总出来的数值全是0，很可能是 weeklyExports/grossNewSales/netSales
    # 这几个候选字段名都没命中，附上实际字段名方便诊断
    if latest_total == 0 and prev_total == 0 and latest_week:
        result["debug"] = {
            "warning": "已连接上接口并拿到数据，但汇总净销售量为0，可能是字段名候选(weeklyExports/grossNewSales/netSales)都没匹配上",
            "actualFieldsSeen": sorted(latest_week[0].keys()) if latest_week else [],
            "sampleRawRow": latest_week[0] if latest_week else None,
        }
    return result


# ---------------------------------------------------------------------------
# 2. USDA-FAS 供需库存数据 (PSD) —— 等同 WASDE 里豆粕/大豆的核心数字
# ---------------------------------------------------------------------------
def get_soybean_meal_psd_code():
    """返回 (code, debug)，跟ESR那边一样区分'请求失败'和'没匹配上'两种不同情况。"""
    data, debug = fetch_json_debug(f"{USDA_BASE}/psd/commodities", headers={"X-Api-Key": USDA_API_KEY})
    if not data:
        debug["failureStage"] = "请求/psd/commodities本身失败（网络问题、认证失败、或被限流）"
        return None, debug
    for item in data:
        name = (item.get("commodityName") or "").lower()
        if "soybean" in name and "meal" in name:
            return item.get("commodityCode"), None
    debug["failureStage"] = "接口请求成功，拿到了商品列表，但没有一条命中'soybean'+'meal'关键词"
    debug["actualCommodityNamesSeen"] = sorted(set((item.get("commodityName") or "") for item in data))[:50]
    debug["totalCommoditiesReturned"] = len(data)
    return None, debug


def get_soybean_psd_code():
    """南美产区关心的是大豆本身(不是豆粕)的产量——中国从南美进口的主要是原豆，
    自己在国内压榨成豆粕。找"Soybeans"这个商品(不带meal)，排除"Soybean Meal"/"Soybean Oil"。
    ★ 已修复第二个真实bug：巴西实测产量只有13,260(千吨)，而查证过的真实数字是180,000，
      只有7.4%。排查后发现Production+BeginningStocks+Imports=TotalSupply在数学上完全自洽
      (13260+197+100=13557)，说明USDA接口本身返回的数值没问题，问题是抓错了商品——
      之前用宽松的子字符串匹配("soybean"+不含"meal"+不含"soybean oil")，PSD商品列表里
      很可能存在不止一个满足这个条件的条目(比如某个大豆的细分子类)，而列表顺序不是
      按重要性排的，宽松匹配抓到了第一个满足条件但不是主要统计口径的那条。
      现在改成：优先精确匹配"Oilseed, Soybean"这个官方标准名称(已通过第三方PSD数据站
      AgroChart交叉验证，全球总产量数量级跟WASDE报告吻合)，找不到才退回宽松匹配兜底。"""
    data, debug = fetch_json_debug(f"{USDA_BASE}/psd/commodities", headers={"X-Api-Key": USDA_API_KEY})
    if not data:
        debug["failureStage"] = "请求/psd/commodities本身失败（网络问题、认证失败、或被限流）"
        return None, debug

    # 第一优先级：精确匹配官方标准名称"Oilseed, Soybean"(不区分大小写)
    for item in data:
        name = (item.get("commodityName") or "").strip().lower()
        if name == "oilseed, soybean":
            return item.get("commodityCode"), {"matchedBy": "精确匹配'Oilseed, Soybean'", "matchedName": item.get("commodityName")}

    # 兜底：精确匹配没找到时，退回宽松匹配(排除meal/soybean oil)，并明确标注是兜底路径，
    # 提醒之后核对这条路径抓到的是不是真的对
    for item in data:
        name = (item.get("commodityName") or "").lower()
        if "soybean" in name and "meal" not in name and "soybean oil" not in name:
            return item.get("commodityCode"), {"matchedBy": "⚠️兜底宽松匹配(精确匹配'Oilseed, Soybean'失败)，请核对是否抓对了商品", "matchedName": item.get("commodityName")}

    debug["failureStage"] = "接口请求成功，但精确匹配和宽松匹配都没有命中"
    # ★ 已改进：之前是"前50个按字母排序的商品"，如果总商品数多，光是A/B/C开头的
    #   条目就可能占满50个名额，真正含"soybean"的那几条反而看不到。
    #   现在专门筛出所有包含"soybean"的条目，不管总列表有多长，都能看到真正相关的部分。
    soybean_related = sorted(set((item.get("commodityName") or "") for item in data if "soybean" in (item.get("commodityName") or "").lower()))
    debug["allSoybeanRelatedEntries"] = soybean_related
    debug["totalCommoditiesReturned"] = len(data)
    return None, debug


def get_psd_attribute_names():
    """
    获取 attributeId → 属性名称 的对照表。
    真实部署后发现：PSD接口返回的数据行里只有数字的 attributeId（比如7），
    没有人类可读的 attributeName 字符串，所以需要额外查一次"属性名称对照表"接口。
    接口的确切路径没有100%确认（USDA没有给出完整的可交互文档），
    这里按最可能的几种命名尝试，只要有一个成功就用哪个。
    """
    candidate_paths = [
        f"{USDA_BASE}/psd/commodityAttributes",
        f"{USDA_BASE}/psd/attributes",
        f"{USDA_BASE}/psd/commodityattribute",
    ]
    for path in candidate_paths:
        data, debug = fetch_json_debug(path, headers={"X-Api-Key": USDA_API_KEY})
        if data:
            mapping = {}
            for item in data:
                aid = item.get("attributeId")
                name = item.get("attributeName") or item.get("attributeDesc") or item.get("name")
                if aid is not None and name:
                    mapping[aid] = name
            if mapping:
                return mapping, path
    return None, None


def _parse_psd_rows(rows, attr_map):
    """把一批PSD原始行解析成 {Ending Stocks:.., Production:.., ...} 的字典，
    同时返回这批数据里最新的 (calendarYear, month) 组合，用来判断新鲜度。"""
    has_string_names = any(r.get("attributeName") for r in rows)
    wanted_normalized = {
        "ending stocks": "Ending Stocks",
        "production": "Production",
        "total supply": "Total Supply",
        "domestic consumption": "Domestic Consumption",
    }
    out = {}
    seen_attrs = set()
    latest_vintage = None  # (calendarYear, month) 里最新的一个，代表这批数据最新是哪个月的WASDE修订版本

    for r in rows:
        cy, mo = r.get("calendarYear"), r.get("month")
        if cy and mo:
            vintage = (cy, mo)
            if latest_vintage is None or vintage > latest_vintage:
                latest_vintage = vintage

    if has_string_names:
        for r in rows:
            attr = r.get("attributeName") or r.get("AttributeName") or r.get("attribute_name")
            val = r.get("value") if "value" in r else r.get("Value")
            if attr is None:
                continue
            seen_attrs.add(attr)
            norm = " ".join(attr.lower().split())
            if norm in wanted_normalized:
                out[wanted_normalized[norm]] = val
    elif attr_map:
        rows_sorted = sorted(rows, key=lambda r: (r.get("calendarYear") or "", r.get("month") or ""))
        latest_by_attr = {}
        for r in rows_sorted:
            aid = r.get("attributeId")
            if aid is not None:
                latest_by_attr[aid] = r
        for aid, r in latest_by_attr.items():
            name = attr_map.get(aid)
            if not name:
                continue
            seen_attrs.add(f"{aid}:{name}")
            norm = " ".join(name.lower().split())
            if norm in wanted_normalized:
                out[wanted_normalized[norm]] = r.get("value")
    else:
        seen_attrs = {f"attributeId={r.get('attributeId')}" for r in rows}

    return out, seen_attrs, has_string_names, latest_vintage


def fetch_psd_supply_demand():
    code, code_lookup_debug = get_soybean_meal_psd_code()
    if not code:
        return {
            "available": False,
            "reason": "未能找到豆粕的PSD商品编码",
            "debug": code_lookup_debug,
        }

    attr_map, attr_map_source = get_psd_attribute_names()

    # ★ 同样的教训：不再猜哪个"year"参数值对应当前活跃的市场年度，
    #   而是同时试几个候选年份，用每批数据里真实出现的"最新WASDE修订月份"来判断哪个最新。
    now_year = datetime.now(timezone.utc).year
    candidate_years = [now_year - 1, now_year, now_year + 1]
    best = None  # {"year":, "rows":, "out":, "seen_attrs":, "has_string_names":, "vintage":}
    all_attempts = {}

    for candidate_year in candidate_years:
        url = f"{USDA_BASE}/psd/commodity/{code}/country/US/year/{candidate_year}"
        rows, debug = fetch_json_debug(url, headers={"X-Api-Key": USDA_API_KEY})
        all_attempts[str(candidate_year)] = {
            "httpStatus": debug.get("httpStatus"),
            "rowCount": len(rows) if rows else 0,
        }
        if not rows:
            continue
        out, seen_attrs, has_string_names, vintage = _parse_psd_rows(rows, attr_map)
        all_attempts[str(candidate_year)]["latestVintage"] = vintage
        candidate = {
            "year": candidate_year, "rows": rows, "out": out,
            "seen_attrs": seen_attrs, "has_string_names": has_string_names, "vintage": vintage,
        }
        # 优先选"有实际匹配到数值"且"vintage最新"的候选；vintage为None时排到最后
        if best is None:
            best = candidate
        else:
            best_sort_key = (bool(best["out"]), best["vintage"] or ("", ""))
            cand_sort_key = (bool(out), vintage or ("", ""))
            if cand_sort_key > best_sort_key:
                best = candidate

    if best is None:
        return {
            "available": False,
            "reason": "PSD接口无返回数据（已尝试" + "、".join(str(y) for y in candidate_years) + "这几个候选年份）",
            "debug": all_attempts,
        }

    year = best["year"]
    out = best["out"]
    seen_attrs = best["seen_attrs"]
    has_string_names = best["has_string_names"]
    vintage = best["vintage"]

    result = {
        "available": True,
        "marketYear": year,
        "wasdeVintage": f"{vintage[0]}年{vintage[1]}月版" if vintage else "未知",
        "endingStocks": out.get("Ending Stocks"),
        "production": out.get("Production"),
        "totalSupply": out.get("Total Supply"),
        "domesticConsumption": out.get("Domestic Consumption"),
        "source": "USDA-FAS PSD API (WASDE同源数据)",
        "sourceUrl": "https://apps.fas.usda.gov/psdonline/",
    }

    # 如果四个关键字段一个都没匹配上，说明还是没能正确识别，
    # 把实际收到的信息列出来，方便直接看出真实情况是什么，不用去翻原始接口。
    if not out:
        if has_string_names:
            warning = "已连接上接口并拿到数据，但字段名一个都没匹配上，可能是接口实际用的attributeName和预期不同"
        else:
            warning = "接口返回的是数字attributeId而不是字符串名称，且未能成功获取attributeId对照表（这个对照表接口的确切路径尚未100%确认）"
        result["debug"] = {
            "warning": warning,
            "actualAttributeNamesSeen": sorted(str(a) for a in seen_attrs)[:30],
            "sampleRawRow": best["rows"][0] if best["rows"] else None,
            "allCandidateYearsAttempted": all_attempts,
        }

    return result


# ---------------------------------------------------------------------------
# 美豆优良率（USDA/NASS 每周作物生长报告，Crop Progress的"Good+Excellent"评级）
# 每年4月-11月每周一发布，是美豆生长季最重要的周度指标之一
# ---------------------------------------------------------------------------
NASS_BASE = "https://quickstats.nass.usda.gov/api/api_GET/"


def fetch_soybean_condition():
    """查询USDA/NASS Quick Stats的美豆生长状况评级(优良率=Excellent%+Good%)。
    这个数据每年只在4月-11月生长季发布，其余月份接口有数据但不会更新(正常现象)。"""
    if not NASS_API_KEY:
        return {"available": False, "reason": "缺少 NASS_API_KEY"}

    now = datetime.now(timezone.utc)
    params = {
        "key": NASS_API_KEY,
        "commodity_desc": "SOYBEANS",
        "statisticcat_desc": "CONDITION",
        "agg_level_desc": "NATIONAL",
        "year": str(now.year),
        "format": "JSON",
    }
    url = f"{NASS_BASE}?{urllib.parse.urlencode(params)}"
    data, debug = fetch_json_debug(url)
    if not data or "data" not in data or not data["data"]:
        return {"available": False, "reason": "NASS接口无返回数据(注意：每年4-11月才有生长季数据)", "debug": debug}

    rows = data["data"]
    # 找出最新的week_ending日期，只用那一周的数据（避免混进往年/其他周的记录）
    weeks = sorted(set(r.get("week_ending") for r in rows if r.get("week_ending")))
    if not weeks:
        return {"available": False, "reason": "返回数据里没有week_ending字段", "debug": {"sampleRawRow": rows[0] if rows else None}}
    latest_week = weeks[-1]
    latest_rows = [r for r in rows if r.get("week_ending") == latest_week]

    # 5个等级分别是独立的行，靠short_desc或unit_desc里的关键词区分，容错匹配大小写
    excellent_pct, good_pct = None, None
    for r in latest_rows:
        desc = (r.get("short_desc") or r.get("unit_desc") or "").upper()
        try:
            val = float(str(r.get("Value", "")).replace(",", ""))
        except (ValueError, TypeError):
            continue
        if "EXCELLENT" in desc:
            excellent_pct = val
        elif "GOOD" in desc and "VERY" not in desc:
            good_pct = val

    if excellent_pct is None or good_pct is None:
        return {
            "available": False,
            "reason": "拿到数据但没能识别出Excellent/Good这两个等级的字段",
            "debug": {"sampleRawRows": latest_rows[:5], "actualDescsSeen": [r.get("short_desc") for r in latest_rows]},
        }

    good_excellent = round(excellent_pct + good_pct, 1)

    # 尝试算环比：找上一个有数据的周
    prev_change = None
    if len(weeks) >= 2:
        prev_week = weeks[-2]
        prev_rows = [r for r in rows if r.get("week_ending") == prev_week]
        prev_excellent, prev_good = None, None
        for r in prev_rows:
            desc = (r.get("short_desc") or r.get("unit_desc") or "").upper()
            try:
                val = float(str(r.get("Value", "")).replace(",", ""))
            except (ValueError, TypeError):
                continue
            if "EXCELLENT" in desc:
                prev_excellent = val
            elif "GOOD" in desc and "VERY" not in desc:
                prev_good = val
        if prev_excellent is not None and prev_good is not None:
            prev_change = round(good_excellent - (prev_excellent + prev_good), 1)

    return {
        "available": True,
        "weekEnding": latest_week,
        "goodExcellentPct": good_excellent,
        "wowChangePts": prev_change,
        "source": "USDA/NASS 每周作物生长报告(Crop Progress)",
        "sourceUrl": "https://www.nass.usda.gov/Charts_and_Maps/Crop_Progress_&_Condition/",
    }


# ---------------------------------------------------------------------------
# 美豆播种进度 —— 服务5月合约窗口期(美豆播种意向+早期播种是这个阶段的核心关注点)
# 复用跟"美豆优良率"完全相同的NASS Quick Stats API，只是statisticcat_desc换成
# "AREA PLANTED"(播种进度)而不是"CONDITION"(生长状况)——已查证这是NASS的标准分类。
# ---------------------------------------------------------------------------
def fetch_us_planting_progress():
    """查询美豆播种进度(占预期种植面积的百分比)。
    这个数据只在每年4-6月(播种季)有意义，其余月份接口有数据但不会更新(正常现象，
    因为播种季结束后这个"进度%"就一直停在100%不变了，不像"CONDITION"那样全季都更新)。"""
    if not NASS_API_KEY:
        return {"available": False, "reason": "缺少 NASS_API_KEY"}

    now = datetime.now(timezone.utc)
    params = {
        "key": NASS_API_KEY,
        "commodity_desc": "SOYBEANS",
        # ★已修复(第三次修复，找到确切根因)：之前先后用过"AREA PLANTED"(年度英亩数调查，
        #   不是周度进度)，然后误以为要加freq_desc=WEEKLY(这个参数会导致NASS API直接
        #   报错"bad request - invalid query")。真正的问题是：周度进度百分比根本不在
        #   "AREA PLANTED"这个分类底下，而是单独的"PROGRESS"这个statisticcat_desc，
        #   还需要额外指定unit_desc="PCT PLANTED"才能从PROGRESS大类里(还包含emerged/
        #   blooming等其他生长阶段)筛出播种进度这一项。这个参数组合是从真实的第三方
        #   NASS API使用案例反推确认的，不是猜测。
        "statisticcat_desc": "PROGRESS",
        "unit_desc": "PCT PLANTED",
        "agg_level_desc": "NATIONAL",
        "year": str(now.year),
        "format": "JSON",
    }
    url = f"{NASS_BASE}?{urllib.parse.urlencode(params)}"
    data, debug = fetch_json_debug(url)
    if not data or "data" not in data or not data["data"]:
        return {"available": False, "reason": "NASS接口无返回数据(注意：每年4-6月播种季才有进度数据)", "debug": debug}

    rows = data["data"]
    # 播种进度只有"PCT PLANTED"这一个百分比字段(不像优良率要分Excellent/Good两档相加)
    pct_rows = [r for r in rows if "PCT PLANTED" in (r.get("short_desc") or "").upper()]
    if not pct_rows:
        return {
            "available": False,
            "reason": "拿到数据但没能识别出PCT PLANTED这个字段",
            "debug": {"sampleRawRows": rows[:5], "actualDescsSeen": [r.get("short_desc") for r in rows]},
        }

    weeks = sorted(set(r.get("week_ending") for r in pct_rows if r.get("week_ending")))
    if not weeks:
        return {"available": False, "reason": "返回数据里没有week_ending字段", "debug": {"sampleRawRow": pct_rows[0]}}
    latest_week = weeks[-1]
    latest_row = next((r for r in pct_rows if r.get("week_ending") == latest_week), None)
    try:
        pct_planted = float(str(latest_row.get("Value", "")).replace(",", ""))
    except (ValueError, TypeError):
        return {"available": False, "reason": "PCT PLANTED字段值无法解析为数字", "debug": {"rawValue": latest_row.get("Value")}}

    # 环比：找上一个有数据的周
    prev_change = None
    if len(weeks) >= 2:
        prev_week = weeks[-2]
        prev_row = next((r for r in pct_rows if r.get("week_ending") == prev_week), None)
        if prev_row:
            try:
                prev_pct = float(str(prev_row.get("Value", "")).replace(",", ""))
                prev_change = round(pct_planted - prev_pct, 1)
            except (ValueError, TypeError):
                pass

    return {
        "available": True,
        "weekEnding": latest_week,
        "pctPlanted": pct_planted,
        "wowChangePts": prev_change,
        "source": "USDA/NASS 每周作物播种进度报告(Crop Progress)",
        "sourceUrl": "https://www.nass.usda.gov/Charts_and_Maps/Crop_Progress_&_Condition/",
    }


# ---------------------------------------------------------------------------
# 美豆收获进度 —— 服务1月合约窗口期(收获进度反映新豆能多快流入市场)
# 复用同一个NASS Quick Stats API，statisticcat_desc用"PROGRESS"+unit_desc="PCT HARVESTED"
# (不是"AREA HARVESTED"，那是年度英亩数调查，不是周度进度百分比)。
# ---------------------------------------------------------------------------
def fetch_us_harvest_progress():
    """查询美豆收获进度(占预期收获面积的百分比)。
    这个数据只在每年9-11月(收获季)有意义，其余月份接口有数据但不会更新(正常现象)。"""
    if not NASS_API_KEY:
        return {"available": False, "reason": "缺少 NASS_API_KEY"}

    now = datetime.now(timezone.utc)
    params = {
        "key": NASS_API_KEY,
        "commodity_desc": "SOYBEANS",
        # ★已修复(第三次修复，找到确切根因，跟播种进度同样的问题)：周度收获进度
        #   百分比在"PROGRESS"这个statisticcat_desc底下，配合unit_desc="PCT HARVESTED"
        #   筛出具体阶段，不是"AREA HARVESTED"(那是年度英亩数调查)。
        "statisticcat_desc": "PROGRESS",
        "unit_desc": "PCT HARVESTED",
        "agg_level_desc": "NATIONAL",
        "year": str(now.year),
        "format": "JSON",
    }
    url = f"{NASS_BASE}?{urllib.parse.urlencode(params)}"
    data, debug = fetch_json_debug(url)
    if not data or "data" not in data or not data["data"]:
        return {"available": False, "reason": "NASS接口无返回数据(注意：每年9-11月收获季才有进度数据)", "debug": debug}

    rows = data["data"]
    pct_rows = [r for r in rows if "PCT HARVESTED" in (r.get("short_desc") or "").upper()]
    if not pct_rows:
        return {
            "available": False,
            "reason": "拿到数据但没能识别出PCT HARVESTED这个字段",
            "debug": {"sampleRawRows": rows[:5], "actualDescsSeen": [r.get("short_desc") for r in rows]},
        }

    weeks = sorted(set(r.get("week_ending") for r in pct_rows if r.get("week_ending")))
    if not weeks:
        return {"available": False, "reason": "返回数据里没有week_ending字段", "debug": {"sampleRawRow": pct_rows[0]}}
    latest_week = weeks[-1]
    latest_row = next((r for r in pct_rows if r.get("week_ending") == latest_week), None)
    try:
        pct_harvested = float(str(latest_row.get("Value", "")).replace(",", ""))
    except (ValueError, TypeError):
        return {"available": False, "reason": "PCT HARVESTED字段值无法解析为数字", "debug": {"rawValue": latest_row.get("Value")}}

    prev_change = None
    if len(weeks) >= 2:
        prev_week = weeks[-2]
        prev_row = next((r for r in pct_rows if r.get("week_ending") == prev_week), None)
        if prev_row:
            try:
                prev_pct = float(str(prev_row.get("Value", "")).replace(",", ""))
                prev_change = round(pct_harvested - prev_pct, 1)
            except (ValueError, TypeError):
                pass

    return {
        "available": True,
        "weekEnding": latest_week,
        "pctHarvested": pct_harvested,
        "wowChangePts": prev_change,
        "source": "USDA/NASS 每周作物收获进度报告(Crop Progress)",
        "sourceUrl": "https://www.nass.usda.gov/Charts_and_Maps/Crop_Progress_&_Condition/",
    }


# ---------------------------------------------------------------------------
# 3. CBOT 豆粕期货价格（Yahoo Finance 非官方接口，免注册）
# ---------------------------------------------------------------------------
def fetch_cbot_price():
    # ZM=F 是 CBOT 豆粕期货代码；这个 chart 接口是非官方但被广泛使用
    url = "https://query1.finance.yahoo.com/v8/finance/chart/ZM=F?interval=1d&range=5d"
    data, debug = fetch_json_debug(url, headers={"User-Agent": "Mozilla/5.0"})
    if not data:
        return {"available": False, "reason": "Yahoo Finance接口无返回（可能被限流或接口变更）", "debug": debug}

    try:
        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        timestamps = result["timestamp"]
        # 过滤掉 None（非交易日）
        pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
        if len(pairs) < 2:
            return {"available": False, "reason": "价格数据点不足", "debug": {"note": f"只拿到{len(pairs)}个有效数据点", "sampleRawRow": data}}
        latest_ts, latest_close = pairs[-1]
        prev_ts, prev_close = pairs[-2]
        change = round(latest_close - prev_close, 2)
        change_pct = round(change / prev_close * 100, 2)
        return {
            "available": True,
            "price": round(latest_close, 2),
            "change": change,
            "changePct": change_pct,
            "asOf": datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat(),
            "source": "Yahoo Finance (非官方接口，仅供参考)",
        }
    except (KeyError, IndexError, TypeError) as e:
        return {"available": False, "reason": f"数据解析失败: {e}", "debug": {"note": "接口返回的JSON结构和预期不一致", "sampleRawRow": data}}


# ---------------------------------------------------------------------------
# 技术面：DCE豆粕期货K线数据（日线+小时线），用akshare库(免密钥，抓新浪财经公开数据)
# ★ 第一阶段范围：先只做当前主力(9月合约M09)验证可行，跑通后再加5月/1月合约。
# ★ 诚实说明：akshare底层是抓取新浪财经公开页面，不是官方付费实时数据源，
#   实际数据大概率有几秒到几分钟延迟，不是真正的逐笔实时行情。
# ---------------------------------------------------------------------------
def get_current_contract_code(contract_month, now=None):
    """算出"现在"该关注的是哪个具体合约代码，比如7月看9月合约，应该是M2609
    （不能写死，因为合约到期后，同一个"9月合约"概念下个周期就该指向M2709了）。
    简化规则：如果当前月份<=合约月份，用今年；否则用明年。"""
    if now is None:
        now = datetime.now(timezone.utc)
    year = now.year if now.month <= contract_month else now.year + 1
    yy = str(year)[-2:]
    return f"M{yy}{contract_month:02d}"


def fetch_dce_daily_kline(symbol, max_rows=260):
    """DCE豆粕日K线，默认取最近约260个交易日(约1年，覆盖MA250等常用中长期指标)。
    ★ 用akshare的futures_zh_daily_sina接口，免密钥，但依赖新浪财经这个第三方数据源。"""
    try:
        import akshare as ak
    except ImportError:
        return {"available": False, "reason": "未安装akshare库，请检查GitHub Actions是否执行了pip install akshare"}

    try:
        df = ak.futures_zh_daily_sina(symbol=symbol)
    except Exception as e:
        return {"available": False, "reason": f"akshare日K线接口调用失败: {e}", "debug": {"symbol": symbol, "errorType": type(e).__name__}}

    if df is None or len(df) == 0:
        return {"available": False, "reason": f"接口调用成功但返回空数据(合约代码{symbol}可能已过期或尚未上市)", "debug": {"symbol": symbol}}

    df_recent = df.tail(max_rows)
    try:
        bars = []
        for _, row in df_recent.iterrows():
            bars.append({
                "date": str(row["date"]),
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row["volume"]) if row.get("volume") is not None else None,
                "hold": float(row["hold"]) if row.get("hold") is not None else None,
                "settle": float(row["settle"]) if row.get("settle") is not None else None,  # ★补上：之前查过akshare日线接口本来就有这个字段(结算价)，但一直没提取出来
            })
    except (KeyError, ValueError, TypeError) as e:
        return {
            "available": False,
            "reason": f"字段解析失败: {e}",
            "debug": _json_safe({"symbol": symbol, "actualColumns": list(df.columns), "sampleRawRow": df.tail(1).to_dict("records")}),
        }

    return {
        "available": True,
        "symbol": symbol,
        "totalBarsReturned": len(bars),
        "bars": bars,
        "source": "新浪财经(经akshare库获取)，非官方实时数据，可能有延迟",
    }


def _get_col(row, *possible_names):
    """尝试多个可能的字段名，返回第一个存在且非空的值。用于兼容akshare不同接口
    可能返回英文字段名(date/open/close)或中文字段名(日期/开盘价/收盘价)的情况——
    宁可写得啰嗦一点兼容两种可能，也不要直接猜一种、猜错了才发现。"""
    for name in possible_names:
        if name in row and row[name] is not None:
            return row[name]
    raise KeyError(f"以下候选字段名都没找到或都是空值: {possible_names}")


def _json_safe(obj):
    """把可能含有date/Timestamp等json.dumps不认识的物件，转成字符串，
    确保debug信息本身能被正常序列化——不能让\"显示诊断信息\"这一步自己先崩溃，
    那样反而看不到真正有用的诊断内容。"""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def fetch_dce_continuous_kline(symbol="M0", years=3):
    """DCE豆粕主力连续合约(M0)，用于回测——单个具体合约(如M2609)存续时间不到1年，
    没法支撑多年回测，连续合约是把历次主力合约"接续"起来的合成序列，能给足够长的历史。
    ★诚实说明：这是"简单拼接"未做平滑处理的版本——每次主力合约切换时(比如从M2601
    切到M2605)，新旧合约收盘价不一定完全相等，拼接点可能出现"价格跳空"，这不是真实
    市场波动，是数据拼接的artifact。这个函数会顺便标记出疑似换月的日期(单日涨跌幅
    异常大)，供回测时排查用，不会假装这个问题不存在。"""
    try:
        import akshare as ak
    except ImportError:
        return {"available": False, "reason": "未安装akshare库，请检查GitHub Actions是否执行了pip install akshare"}

    start_date = (datetime.now(timezone.utc) - timedelta(days=int(years*365.25)+30)).strftime("%Y%m%d")
    try:
        df = ak.futures_main_sina(symbol=symbol, start_date=start_date)
    except Exception as e:
        return {"available": False, "reason": f"akshare连续合约接口调用失败: {e}", "debug": {"symbol": symbol, "errorType": type(e).__name__}}

    if df is None or len(df) == 0:
        return {"available": False, "reason": f"接口调用成功但返回空数据(连续合约代码{symbol}可能不存在)", "debug": {"symbol": symbol}}

    try:
        bars = []
        prev_close = None
        suspected_rollovers = []
        for _, row in df.iterrows():
            # ★已修复：之前直接假设字段名是英文(date/open/close等)，实测报错发现futures_main_sina()
            #   很可能用的是不同的字段命名(比如中文"日期/开盘价/收盘价")。现在用_get_col()
            #   同时尝试英文和中文两种可能，不管这个接口实际用哪种命名都能兼容。
            date_val = _get_col(row, "date", "日期")
            close_val = float(_get_col(row, "close", "收盘价"))
            bar = {
                "date": str(date_val),
                "open": float(_get_col(row, "open", "开盘价")),
                "high": float(_get_col(row, "high", "最高价")),
                "low": float(_get_col(row, "low", "最低价")),
                "close": close_val,
            }
            try:
                bar["volume"] = float(_get_col(row, "volume", "成交量"))
            except KeyError:
                bar["volume"] = None
            try:
                bar["hold"] = float(_get_col(row, "hold", "持仓量"))
            except KeyError:
                bar["hold"] = None

            if prev_close is not None and prev_close != 0:
                pct_change = abs(close_val - prev_close) / prev_close
                if pct_change > 0.06:  # 单日涨跌幅超过6%，DCE豆粕正常涨跌停板通常在4-5%左右，超过这个很可能是换月拼接的跳空
                    suspected_rollovers.append({"date": bar["date"], "pctChange": round(pct_change*100, 2)})
            bars.append(bar)
            prev_close = close_val
    except (KeyError, ValueError, TypeError) as e:
        return {
            "available": False,
            "reason": f"字段解析失败: {e}",
            "debug": _json_safe({"symbol": symbol, "actualColumns": list(df.columns), "sampleRawRow": df.tail(1).to_dict("records")}),
        }

    return {
        "available": True,
        "symbol": symbol,
        "totalBarsReturned": len(bars),
        "bars": bars,
        "suspectedRolloverDates": suspected_rollovers,  # ⚠️疑似换月跳空日，回测时应该排查这些日期附近的信号是否可靠
        "source": "新浪财经(经akshare库获取)，主力连续合约(简单拼接未平滑)，非官方实时数据",
    }


def fetch_dce_hourly_kline(symbol, max_bars=180):
    """DCE豆粕小时K线，默认取最近约180根(按日盘+夜盘大约6根/天算，约30天)。
    ★ 用akshare的futures_zh_minute_sina接口，period=60表示60分钟(小时)线。"""
    try:
        import akshare as ak
    except ImportError:
        return {"available": False, "reason": "未安装akshare库，请检查GitHub Actions是否执行了pip install akshare"}

    try:
        df = ak.futures_zh_minute_sina(symbol=symbol, period="60")
    except Exception as e:
        return {"available": False, "reason": f"akshare小时K线接口调用失败: {e}", "debug": {"symbol": symbol, "errorType": type(e).__name__}}

    if df is None or len(df) == 0:
        return {"available": False, "reason": f"接口调用成功但返回空数据(合约代码{symbol}可能已过期或尚未上市)", "debug": {"symbol": symbol}}

    df_recent = df.tail(max_bars)
    try:
        bars = []
        for _, row in df_recent.iterrows():
            bars.append({
                "datetime": str(row["datetime"]),  # ★已修复：实测发现akshare 1.18.64版本这个字段叫datetime，不是date(旧版本文档示例是date，版本间不一致)
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row["volume"]) if row.get("volume") is not None else None,
                "hold": float(row["hold"]) if row.get("hold") is not None else None,
            })
    except (KeyError, ValueError, TypeError) as e:
        return {
            "available": False,
            "reason": f"字段解析失败: {e}",
            "debug": _json_safe({"symbol": symbol, "actualColumns": list(df.columns), "sampleRawRow": df.tail(1).to_dict("records")}),
        }

    return {
        "available": True,
        "symbol": symbol,
        "totalBarsReturned": len(bars),
        "bars": bars,
        "source": "新浪财经(经akshare库获取)，非官方实时数据，可能有几秒到几分钟延迟",
    }


# ---------------------------------------------------------------------------
# 4. 美国干旱监测 (US Drought Monitor) —— 真正的官方干旱等级数据
#    区别于天气预报推算的"风险"，这是 NDMC/USDA/NOAA 每周四联合发布的
#    实测干旱分级 (D0-D4)，网页端(index.html)里天气板块用降雨预报算的是
#    "风险倾向"，这里补的是"官方实际认定的干旱状态"。
# ---------------------------------------------------------------------------
# 州名用两字母缩写做显示/内部key，但查询接口的aoi参数官方文档明确要求"两位数FIPS代码"
# （之前的bug就在这里：用了邮政缩写"IA"当aoi值，接口返回200+空数组，因为查无此州）
# ★ 已扩展：查证美国大豆种植面积排名(SoyStats官方2024年数据)后确认：
#   核心8州(伊利诺伊/爱荷华/明尼苏达/印第安纳/内布拉斯加/俄亥俄/密苏里/南达科他)
#   = 全国种植面积64.0%；加上次要4州(北达科他/堪萨斯/密歇根/威斯康星)
#   合计12州 = 全国种植面积81.8%，覆盖绝大部分主产区。
CORE_STATES = ["IA", "IL", "MN", "IN", "NE", "OH", "MO", "SD"]
SECONDARY_STATES = ["ND", "KS", "MI", "WI"]
DROUGHT_STATES = CORE_STATES + SECONDARY_STATES
DROUGHT_STATE_FIPS = {
    "IA": "19", "IL": "17", "MN": "27", "IN": "18",
    "NE": "31", "OH": "39", "MO": "29", "SD": "46",
    "ND": "38", "KS": "20", "MI": "26", "WI": "55",
}  # 官方文档：droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx

# ★ 新增：按种植面积加权，而不是12州简单平均。
#   之前简单平均的问题：伊利诺伊(全国最大产区)天气不好 vs 南达科他(产量小得多)天气不好，
#   在简单平均里权重完全一样，明显不合理——大产区的天气影响应该占更大权重。
#   数据来源：SoyStats官方2024年种植面积统计(单位：千英亩)，与上面确认12州覆盖率时用的是同一份数据。
STATE_ACREAGE_WEIGHTS = {
    "IL": 10800, "IA": 10050, "MN": 7400, "IN": 5800,
    "NE": 5300, "OH": 5050, "MO": 5900, "SD": 5450,
    "ND": 6600, "KS": 4530, "MI": 2200, "WI": 2150,
}


def weighted_avg(state_values):
    """state_values: {"IA": 12.3, "IL": 5.0, ...} → 按STATE_ACREAGE_WEIGHTS加权平均。
    某州权重查不到时按0处理(不太可能发生，因为这个字典本来就是DROUGHT_STATES的来源)。"""
    total_weight = sum(STATE_ACREAGE_WEIGHTS.get(st, 0) for st in state_values)
    if total_weight == 0:
        return sum(state_values.values()) / len(state_values) if state_values else 0
    weighted_sum = sum(v * STATE_ACREAGE_WEIGHTS.get(st, 0) for st, v in state_values.items())
    return weighted_sum / total_weight
    return weighted_sum / total_weight


# ---------------------------------------------------------------------------
# 南美产区(巴西/阿根廷)天气监测 —— 服务5月合约窗口期(南美收获期是主要行情驱动)
# ★ 已确认：巴西现在是全球最大大豆产区(超过美国)，2025/26年度总产量约174百万吨，
#   数据来源：巴西IBGE官方统计+USDA FAS交叉验证。这6州覆盖巴西全国产量约80%。
# ---------------------------------------------------------------------------
BRAZIL_STATE_WEIGHTS = {
    "MT": 30,  # 马托格罗索州，全国最大产区
    "PR": 13,  # 巴拉那州
    "RS": 11,  # 南里奥格朗德州
    "GO": 11,  # 戈亚斯州
    "MS": 8,   # 南马托格罗索州
    "MG": 5,   # 米纳斯吉拉斯州
}
BRAZIL_LOCATIONS = {
    "MT": {"lat": -12.5, "lon": -55.7, "name_cn": "马托格罗索"},   # Sorriso地区，主产带
    "PR": {"lat": -24.95, "lon": -53.46, "name_cn": "巴拉那"},     # Cascavel地区
    "RS": {"lat": -28.26, "lon": -52.4, "name_cn": "南里奥格朗德"}, # Passo Fundo地区
    "GO": {"lat": -16.68, "lon": -49.25, "name_cn": "戈亚斯"},     # Goiânia附近
    "MS": {"lat": -20.44, "lon": -54.65, "name_cn": "南马托格罗索"}, # Campo Grande附近
    "MG": {"lat": -18.9, "lon": -48.28, "name_cn": "米纳斯吉拉斯"}, # Uberlândia地区(西部大豆带)
}

# ★ 已查证：圣菲/科尔多瓦/布宜诺斯艾利斯/恩特雷里奥斯这4省合计占阿根廷全国产量89%，
#   但没查到4省之间的精确细分占比(不像巴西那样有清晰的独立数字来源)，
#   诚实起见，这4省先按相等权重处理，不编造没有可靠依据的具体百分比。
ARGENTINA_LOCATIONS = {
    "SantaFe": {"lat": -31.63, "lon": -60.7, "name_cn": "圣菲"},
    "Cordoba": {"lat": -31.42, "lon": -64.18, "name_cn": "科尔多瓦"},
    "BuenosAires": {"lat": -34.92, "lon": -59.95, "name_cn": "布宜诺斯艾利斯"},
    "EntreRios": {"lat": -31.73, "lon": -60.53, "name_cn": "恩特雷里奥斯"},
}
ARGENTINA_STATE_WEIGHTS = {k: 1 for k in ARGENTINA_LOCATIONS}  # 权重相等，见上方说明

SOUTH_AMERICA_LOCATIONS = {**BRAZIL_LOCATIONS, **ARGENTINA_LOCATIONS}
SOUTH_AMERICA_WEIGHTS = {**BRAZIL_STATE_WEIGHTS, **ARGENTINA_STATE_WEIGHTS}


def fetch_south_america_weather():
    """南美(巴西+阿根廷)产区天气监测，用Open-Meteo(全球性API，跟美国那边用的是同一个服务)。
    南美是南半球，生长季节跟北美相反：南美播种期约9-12月，收获期约1-6月(集中在2-4月)。"""
    results = {}
    debugs = {}
    for code, loc in SOUTH_AMERICA_LOCATIONS.items():
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={loc['lat']}&longitude={loc['lon']}"
            f"&daily=precipitation_sum,temperature_2m_max&forecast_days=7&timezone=America%2FSao_Paulo"
        )
        data, debug = fetch_json_debug(url)
        debugs[code] = debug
        if not data or "daily" not in data:
            results[code] = {"available": False}
            continue
        precip_list = data["daily"].get("precipitation_sum") or []
        temp_list = data["daily"].get("temperature_2m_max") or []
        precip7d = round(sum(v for v in precip_list if v is not None), 1)
        valid_temps = [v for v in temp_list if v is not None]
        avg_temp = round(sum(valid_temps) / len(valid_temps), 1) if valid_temps else None
        results[code] = {
            "available": True,
            "nameCn": loc["name_cn"],
            "country": "BR" if code in BRAZIL_LOCATIONS else "AR",
            "precip7d": precip7d,
            "avgMaxTemp": avg_temp,
        }

    available = {k: v for k, v in results.items() if v.get("available")}
    if not available:
        return {"available": False, "reason": "南美天气接口未返回任何产区数据", "debug": debugs}

    precip_weighted = weighted_avg_custom({k: v["precip7d"] for k, v in available.items()}, SOUTH_AMERICA_WEIGHTS)
    temp_valid = {k: v["avgMaxTemp"] for k, v in available.items() if v["avgMaxTemp"] is not None}
    temp_weighted = weighted_avg_custom(temp_valid, SOUTH_AMERICA_WEIGHTS) if temp_valid else None

    return {
        "available": True,
        "byRegion": results,
        "avgPrecip7d": precip_weighted,
        "avgMaxTemp": temp_weighted,
        "source": "Open-Meteo（全球性天气API），按巴西州产量占比+阿根廷4省等权重加权",
        "note": "南半球生长季与北半球相反：播种约9-12月，收获集中在2-4月",
    }


def weighted_avg_custom(values, weights):
    """跟weighted_avg()逻辑一样，但权重表可以自定义传入(南美用的是单独的权重表，不是STATE_ACREAGE_WEIGHTS)。"""
    total_weight = sum(weights.get(k, 0) for k in values)
    if total_weight == 0:
        return round(sum(values.values()) / len(values), 1) if values else 0
    weighted_sum = sum(v * weights.get(k, 0) for k, v in values.items())
    return round(weighted_sum / total_weight, 1)


def fetch_south_america_psd():
    """巴西/阿根廷的大豆(原豆，不是豆粕)供需数据，复用已有的PSD解析逻辑，只是换个国家代码。
    ★ 国家代码(BR/AR)是根据USDA FAS一般命名习惯推断的，没有100%验证过，
      如果查询失败，debug信息会明确说明，不会静默失败误导判断。
    ★ 已修复：之前成功时完全不带debug信息，导致查证发现产量数字明显偏低(巴西只有
      真实数字的7%左右)时完全没法定位原因。现在不管成功失败都带上原始样本行，
      方便直接核对USDA接口实际返回的是哪个字段、单位是什么。"""
    code, code_debug = get_soybean_psd_code()
    if not code:
        return {"available": False, "reason": "大豆商品代码查找失败", "debug": code_debug}

    results = {}
    attr_map, _ = get_psd_attribute_names()
    for country_code, country_name in [("BR", "巴西"), ("AR", "阿根廷")]:
        now_year = datetime.now(timezone.utc).year
        candidate_years = [now_year - 1, now_year, now_year + 1]
        best = None
        best_rows = None
        all_attempts = {}
        for candidate_year in candidate_years:
            url = f"{USDA_BASE}/psd/commodity/{code}/country/{country_code}/year/{candidate_year}"
            rows, debug = fetch_json_debug(url, headers={"X-Api-Key": USDA_API_KEY})
            all_attempts[str(candidate_year)] = {"httpStatus": debug.get("httpStatus"), "rowCount": len(rows) if rows else 0}
            if not rows:
                continue
            out, seen_attrs, has_string_names, vintage = _parse_psd_rows(rows, attr_map)
            candidate = {"year": candidate_year, "out": out, "vintage": vintage}
            if best is None or (bool(out), vintage or ("", "")) > (bool(best["out"]), best["vintage"] or ("", "")):
                best = candidate
                best_rows = rows
        country_debug = {
            "matchedCommodity": code_debug,  # 显示匹配到的商品名称，方便一眼确认抓对了没有
            "attemptsPerYear": all_attempts,
            "sampleRawRows": best_rows[:10] if best_rows else None,  # 带单位就在原始行里，方便直接核对
        }
        if not best or not best["out"]:
            results[country_code] = {"available": False, "reason": f"{country_name}PSD数据查询失败或字段未匹配", "debug": country_debug}
            continue
        results[country_code] = {
            "available": True,
            "marketYear": best["year"],
            "production": best["out"].get("Production"),
            "totalSupply": best["out"].get("Total Supply"),
            "countryName": country_name,
            "debug": country_debug,  # ★ 成功也带上，方便核对数字是否合理
        }
    return {
        "available": any(v.get("available") for v in results.values()),
        "byCountry": results,
        "source": "USDA-FAS PSD API（跟美国数据同一套接口，换了国家代码）",
    }


def fetch_drought_monitor():
    from datetime import timedelta

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=14)  # 拉两周，确保能覆盖最近一次周四更新

    out = {}
    debugs = {}
    for state in DROUGHT_STATES:
        fips = DROUGHT_STATE_FIPS[state]
        url = (
            "https://usdmdataservices.unl.edu/api/StateStatistics/"
            f"GetDroughtSeverityStatisticsByArea?aoi={fips}"
            f"&startdate={start.strftime('%-m/%-d/%Y')}&enddate={end.strftime('%-m/%-d/%Y')}"
            "&statisticsType=1"
        )
        rows, debug = fetch_json_debug(url, headers={"Accept": "application/json"})
        if rows:
            debug["sampleRawRow"] = rows[0]
            debug["totalRowsReturned"] = len(rows)
        debugs[state] = debug
        if not rows:
            out[state] = {"available": False}
            continue
        # 取最新一条记录
        rows_sorted = sorted(rows, key=lambda r: r.get("ValidStart") or r.get("validStart") or "")
        latest = rows_sorted[-1]

        def g(*keys):
            for k in keys:
                if k in latest and latest[k] is not None:
                    return latest[k]
            return None

        # ★ 已确认修复（感谢实测原始数据核实）：
        # d0/d1/d2/d3/d4 不是百分比，是"平方英里"的原始面积！
        # 证据：爱荷华 none(37534.63) + d0(18776.87) = 56311.5 ≈ 爱荷华全州面积(56273平方英里)
        # 说明"none"代表无干旱区域面积，"d0"代表D0及以上(至少轻度干旱)的区域面积，
        # 两者相加 = 全州面积。真正的百分比 = 各等级面积 ÷ (none+d0) × 100
        none_area = g("none", "None", "NONE")
        d0_area, d1_area = g("D0", "d0"), g("D1", "d1")
        d2_area = g("D2", "d2") or 0
        d3_area = g("D3", "d3") or 0
        d4_area = g("D4", "d4") or 0

        if none_area is not None and d0_area is not None and (none_area + d0_area) > 0:
            total_area = none_area + d0_area
            d0 = round(d0_area / total_area * 100, 2)
            d1 = round(d1_area / total_area * 100, 2) if d1_area is not None else None
            d2 = round(d2_area / total_area * 100, 2)
            d3 = round(d3_area / total_area * 100, 2)
            d4 = round(d4_area / total_area * 100, 2)
            d2_plus = d2 + d3 + d4
            is_anomalous = False
        else:
            # 拿不到 none 字段时没法换算，保留原始数值但标记异常，不能装作换算成功了
            d0, d1, d2, d3, d4 = d0_area, d1_area, d2_area, d3_area, d4_area
            d2_plus = (d2 or 0) + (d3 or 0) + (d4 or 0)
            is_anomalous = True
            debugs[state]["anomalyWarning"] = "找不到'none'字段，无法换算成百分比（需要 none+d0=全州面积 这个关系式来计算）"

        out[state] = {
            "available": True,
            "anomalous": is_anomalous,
            "validDate": g("ValidStart", "validStart", "MapDate", "mapDate"),
            "d0": d0,
            "d1": d1,
            "d2": d2,
            "d3": d3,
            "d4": d4,
            "severeOrWorsePct": round(d2_plus, 1),
        }

    available_states = {k: v for k, v in out.items() if v.get("available")}
    if not available_states:
        return {"available": False, "reason": "USDM接口未返回任何州的数据", "debug": debugs}

    # ★ 已改进：之前是12州简单平均，现在改成按种植面积加权——
    #   伊利诺伊(全国最大产区)的干旱情况理应比南达科他(小得多的产区)占更大权重。
    severe_by_state = {st: v["severeOrWorsePct"] for st, v in available_states.items()}
    avg_severe = weighted_avg(severe_by_state)
    simple_avg_severe = sum(severe_by_state.values()) / len(severe_by_state)  # 保留做对比参考
    any_anomalous = any(v.get("anomalous") for v in available_states.values())

    return {
        "available": True,
        "anomalous": any_anomalous,
        "byState": out,
        "avgSevereOrWorsePct": round(avg_severe, 1),
        "simpleSevereOrWorsePct": round(simple_avg_severe, 1),
        "source": "US Drought Monitor (NDMC/USDA/NOAA联合发布)",
        "sourceUrl": "https://droughtmonitor.unl.edu/",
        # 不管本次是否异常，都附上原始样本方便随时核对，不用等到下次出问题才临时加诊断
        "debug": debugs,
    }


# ---------------------------------------------------------------------------
# NOAA/CPC 月度干旱展望 —— 填补"现状(干旱监测)"和"未来7天(天气预报)"之间的空白
# 这是专家综合研判(不只是降雨量公式)：还会考虑ENSO状态、季节性降雨规律、
# 热带风暴季等因素，预测未来1个月这个地区干旱会"发展/持续/改善/解除"。
# ---------------------------------------------------------------------------
NOAA_OUTLOOK_QUERY_URL = "https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/cpc_drought_outlk/MapServer/1/query"

# ★ 已升级：之前每州只查1个代表性坐标(比如明尼苏达只查双城区)，
#   实测发现跟"干旱监测"的全州统计口径对不上——旱区可能集中在采样点以外的区域，
#   导致"全州统计有旱"+"这一个点没旱"同时出现，看起来像矛盾其实是采样粒度不同。
#   现在改成每州分散取8个点(覆盖东西南北+中，都是确认过在该州境内的真实城镇坐标)，
#   统计"这8个点里有百分之多少显示干旱在发展/持续"，这样才能跟干旱监测的
#   "全州百分之多少面积处于XX等级"做有意义的对比。
OUTLOOK_LOCATIONS = {
    "IA": [  # 爱荷华：西北-中北-东北-中西-中央-中东-中南-东南，覆盖全州
        {"lat": 42.4966, "lon": -96.4058},  # Sioux City 西北
        {"lat": 43.1548, "lon": -93.2010},  # Mason City 中北
        {"lat": 42.5006, "lon": -90.6646},  # Dubuque 东北
        {"lat": 41.2619, "lon": -95.8608},  # Council Bluffs 中西
        {"lat": 41.5868, "lon": -93.6250},  # Des Moines 中央
        {"lat": 41.9779, "lon": -91.6656},  # Cedar Rapids 中东
        {"lat": 41.0161, "lon": -92.4113},  # Ottumwa 中南
        {"lat": 40.8078, "lon": -91.1129},  # Burlington 东南
    ],
    "IL": [  # 伊利诺伊：北-东北-中西-中东-中央-西-西南-东南，纵贯全州
        {"lat": 42.2711, "lon": -89.0940},  # Rockford 北
        {"lat": 41.8781, "lon": -87.6298},  # Chicago 东北
        {"lat": 40.6936, "lon": -89.5890},  # Peoria 中西
        {"lat": 40.1245, "lon": -87.6300},  # Danville 中东
        {"lat": 39.7817, "lon": -89.6501},  # Springfield 中央
        {"lat": 39.9356, "lon": -91.4098},  # Quincy 西
        {"lat": 38.5201, "lon": -89.9840},  # Belleville 西南
        {"lat": 37.7273, "lon": -88.9331},  # Marion 东南
    ],
    "MN": [  # 明尼苏达：最北-西北-东北-中北-中央-西南-东南-最南，覆盖全州(含容易被忽略的西北/南部)
        {"lat": 48.6011, "lon": -93.4111},  # International Falls 最北
        {"lat": 46.8739, "lon": -96.7678},  # Moorhead 西北
        {"lat": 46.7867, "lon": -92.1005},  # Duluth 东北
        {"lat": 46.3580, "lon": -94.2008},  # Brainerd 中北
        {"lat": 44.9778, "lon": -93.2650},  # Minneapolis 中央
        {"lat": 44.4472, "lon": -95.7889},  # Marshall 西南
        {"lat": 44.0121, "lon": -92.4802},  # Rochester 东南
        {"lat": 43.6478, "lon": -93.3683},  # Albert Lea 最南
    ],
    "IN": [  # 印第安纳：北-东北-中西-中东-中央-西南-中南-东南偏南，覆盖全州
        {"lat": 41.6764, "lon": -86.2520},  # South Bend 北
        {"lat": 41.0793, "lon": -85.1394},  # Fort Wayne 东北
        {"lat": 39.4667, "lon": -87.4139},  # Terre Haute 中西
        {"lat": 40.1934, "lon": -85.3863},  # Muncie 中东
        {"lat": 39.7684, "lon": -86.1581},  # Indianapolis 中央
        {"lat": 37.9716, "lon": -87.5711},  # Evansville 西南
        {"lat": 39.1653, "lon": -86.5264},  # Bloomington 中南
        {"lat": 39.2014, "lon": -85.9214},  # Columbus(IN) 东南偏南
    ],
    "NE": [  # 内布拉斯加：最西-西北-中北-东北-中西-东南-东-西南，覆盖全州(大豆集中在东部)
        {"lat": 41.8666, "lon": -103.6672},  # Scottsbluff 最西
        {"lat": 42.0977, "lon": -102.8710},  # Alliance 西北
        {"lat": 42.4547, "lon": -98.6467},   # O'Neill 中北
        {"lat": 41.9911, "lon": -97.4173},   # Norfolk 东北
        {"lat": 41.1239, "lon": -100.7654},  # North Platte 中西
        {"lat": 40.8136, "lon": -96.7026},   # Lincoln 东南
        {"lat": 41.2565, "lon": -95.9345},   # Omaha 东
        {"lat": 40.2013, "lon": -100.6254},  # McCook 西南
    ],
    "OH": [  # 俄亥俄：西北-东北-中西-中央-西南-东南-远西南-中东，覆盖全州
        {"lat": 41.6528, "lon": -83.5379},  # Toledo 西北
        {"lat": 41.4993, "lon": -81.6944},  # Cleveland 东北
        {"lat": 40.7426, "lon": -84.1052},  # Lima 中西
        {"lat": 39.9612, "lon": -82.9988},  # Columbus(OH) 中央
        {"lat": 39.7589, "lon": -84.1916},  # Dayton 西南
        {"lat": 39.3292, "lon": -82.1013},  # Athens 东南
        {"lat": 39.1031, "lon": -84.5120},  # Cincinnati 远西南
        {"lat": 39.9400, "lon": -82.0132},  # Zanesville 中东
    ],
    "MO": [  # 密苏里：北-东北-西北-中央-西-东-西南-东南，覆盖全州
        {"lat": 40.1948, "lon": -92.5832},  # Kirksville 北
        {"lat": 39.7084, "lon": -91.3585},  # Hannibal 东北
        {"lat": 39.7674, "lon": -94.8467},  # St. Joseph 西北
        {"lat": 38.9517, "lon": -92.3341},  # Columbia(MO) 中央
        {"lat": 39.0997, "lon": -94.5786},  # Kansas City 西
        {"lat": 38.6270, "lon": -90.1994},  # St. Louis 东
        {"lat": 37.2090, "lon": -93.2923},  # Springfield(MO) 西南
        {"lat": 37.3059, "lon": -89.5181},  # Cape Girardeau 东南
    ],
    "SD": [  # 南达科他：大豆主要集中在东部，采样点适度偏东覆盖
        {"lat": 43.5446, "lon": -96.7311},  # Sioux Falls 东南
        {"lat": 44.3114, "lon": -96.7984},  # Brookings 东
        {"lat": 45.4647, "lon": -98.4865},  # Aberdeen 东北
        {"lat": 44.8996, "lon": -97.1152},  # Watertown 东中
        {"lat": 43.7094, "lon": -98.0298},  # Mitchell 东南中
        {"lat": 44.3633, "lon": -98.2144},  # Huron 中央偏东
        {"lat": 42.8711, "lon": -97.3973},  # Yankton 最南
        {"lat": 44.3683, "lon": -100.3510}, # Pierre 中西(大豆较少，为覆盖全州)
    ],
    "ND": [  # 北达科他：大豆集中在东部，覆盖东部为主+适度西部
        {"lat": 48.2330, "lon": -101.2957},  # Minot 中北
        {"lat": 47.9253, "lon": -97.0329},   # Grand Forks 东北
        {"lat": 46.8083, "lon": -100.7837},  # Bismarck 中央
        {"lat": 46.8772, "lon": -96.7898},   # Fargo 东
        {"lat": 46.2807, "lon": -98.7031},   # Jamestown 东中
        {"lat": 48.1128, "lon": -103.6210},  # Williston 西北
        {"lat": 46.0555, "lon": -102.7813},  # Dickinson 西南
        {"lat": 47.5515, "lon": -99.2379},   # Devils Lake area 中北偏东
    ],
    "KS": [  # 堪萨斯：大豆集中在东部，覆盖全州(西部偏干旱少大豆但为完整性纳入)
        {"lat": 39.8403, "lon": -95.3639},   # Hiawatha area 东北
        {"lat": 38.9717, "lon": -95.2353},   # Lawrence 东
        {"lat": 37.6922, "lon": -97.3375},   # Wichita 中南
        {"lat": 39.1836, "lon": -96.5717},   # Manhattan 中北偏东
        {"lat": 38.0608, "lon": -97.9298},   # Hutchinson 中央
        {"lat": 37.0420, "lon": -95.6161},   # Independence 东南
        {"lat": 39.3475, "lon": -101.7104},  # Oakley 西部
        {"lat": 37.7528, "lon": -100.0171},  # Dodge City 西南
    ],
    "MI": [  # 密歇根：大豆主要在南部/中南部(下半岛)，覆盖为主
        {"lat": 43.6211, "lon": -84.2280},   # Mount Pleasant 中部
        {"lat": 42.7325, "lon": -84.5555},   # Lansing 中南
        {"lat": 42.2917, "lon": -83.7130},   # Ann Arbor 东南
        {"lat": 41.9163, "lon": -83.3554},   # Monroe 最南偏东
        {"lat": 42.0970, "lon": -86.4526},   # Benton Harbor 西南
        {"lat": 43.4195, "lon": -85.3378},   # Big Rapids area 中西
        {"lat": 43.0125, "lon": -83.6875},   # Flint 中东
        {"lat": 45.0000, "lon": -84.6800},   # Gaylord(上半岛附近，大豆少但为覆盖) 北部
    ],
    "WI": [  # 威斯康星：大豆集中在南部，覆盖南部为主+适度北部
        {"lat": 42.8666, "lon": -88.0198},   # Kenosha area 东南
        {"lat": 42.7261, "lon": -89.0187},   # Janesville 中南
        {"lat": 43.0731, "lon": -89.4012},   # Madison 中央偏南
        {"lat": 43.7844, "lon": -88.7879},   # Fond du Lac 中东
        {"lat": 43.0389, "lon": -91.1521},   # La Crosse 西南
        {"lat": 44.5192, "lon": -88.0198},   # Green Bay 东北
        {"lat": 44.9591, "lon": -91.6899},   # Eau Claire 中西北
        {"lat": 45.8666, "lon": -91.2429},   # Rice Lake area 北部
    ],
}

# 展望分类 → 对交易而言的方向（Development/Persistence=干旱在发展或持续=偏多信号；
# Improvement/Removal/No_Drought=干旱在改善/解除/本来没有=偏空方向）
OUTLOOK_WORSENING = {"Development", "Persistence"}
OUTLOOK_LABEL_CN = {
    "Development": "干旱发展中", "Persistence": "干旱持续",
    "Improvement": "干旱改善", "Removal": "干旱解除", "No_Drought": "预计无旱",
}


def _query_noaa_outlook_point(lat, lon):
    """查询单个经纬度点的NOAA月度展望分类，返回 (outlook_dict_or_None, debug)。"""
    geometry = json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}})
    params = {
        "geometry": geometry,
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "outlook,fcst_date,target",
        "returnGeometry": "false",
        "f": "json",
    }
    # ★ 用urllib.parse.urlencode()而不是手动拼字符串——这个项目已经因为
    #   手动拼URL漏编码空格踩过2次坑了(到港预报那边)，这次直接用标准工具处理。
    query_string = urllib.parse.urlencode(params)
    url = f"{NOAA_OUTLOOK_QUERY_URL}?{query_string}"
    data, debug = fetch_json_debug(url)
    if not data or "features" not in data or not data["features"]:
        return None, debug
    attrs = data["features"][0]["attributes"]
    outlook = attrs.get("outlook")
    return {
        "outlook": outlook,
        "outlookLabel": OUTLOOK_LABEL_CN.get(outlook, outlook),
        "targetPeriod": attrs.get("target"),
        "forecastDate": attrs.get("fcst_date"),
    }, debug


def fetch_noaa_drought_outlook():
    """查询NOAA/CPC月度干旱展望——每州取8个分散点分别查询，
    统计"这8个点里有多少百分比展望在发展/持续"，
    这样才能跟干旱监测的"全州XX%面积处于某等级"做有意义的对比，
    而不是单点采样容易漏掉旱区集中在采样点以外区域的情况。
    已确认：这个服务坐标系是标准WGS84(4326)，不需要坐标转换。"""
    by_state = {}
    debugs = {}

    for state, points in OUTLOOK_LOCATIONS.items():
        point_results = []
        state_debug = {}
        for i, pt in enumerate(points):
            if i > 0:
                time.sleep(0.5)  # 8点×12州=96次请求，加个小间隔对官方服务更友好
            outlook_data, debug = _query_noaa_outlook_point(pt["lat"], pt["lon"])
            state_debug[f"point{i}"] = {"lat": pt["lat"], "lon": pt["lon"], **debug}
            if outlook_data:
                point_results.append(outlook_data)
        debugs[state] = state_debug

        if not point_results:
            by_state[state] = {"available": False}
            continue

        worsening_count = sum(1 for r in point_results if r["outlook"] in OUTLOOK_WORSENING)
        total = len(point_results)
        worsening_pct = round(worsening_count / total * 100, 1)

        # 统计每种分类出现的次数，取出现最多的作为"代表性展望"方便展示
        category_counts = {}
        for r in point_results:
            category_counts[r["outlook"]] = category_counts.get(r["outlook"], 0) + 1
        dominant = max(category_counts, key=category_counts.get)

        by_state[state] = {
            "available": True,
            "pointResults": point_results,
            "totalPoints": total,
            "worseningCount": worsening_count,
            "worseningPct": worsening_pct,
            "dominantOutlook": dominant,
            "dominantOutlookLabel": OUTLOOK_LABEL_CN.get(dominant, dominant),
            "targetPeriod": point_results[0].get("targetPeriod"),
        }

    available = {k: v for k, v in by_state.items() if v.get("available")}
    if not available:
        return {"available": False, "reason": "NOAA月度干旱展望接口未返回任何州的数据", "debug": debugs}

    # ★ 已改进：跟干旱监测一样，从简单平均改成按种植面积加权
    worsening_by_state = {st: v["worseningPct"] for st, v in available.items()}
    avg_worsening_pct = round(weighted_avg(worsening_by_state), 1)
    simple_avg_worsening = round(sum(worsening_by_state.values()) / len(worsening_by_state), 1)
    # 跟干旱监测的阈值逻辑保持一致(>=20%明显，>=5%中等)，方便两者直接对比
    overall_signal = 1 if avg_worsening_pct >= 20 else (0 if avg_worsening_pct >= 5 else -1)

    return {
        "available": True,
        "byState": by_state,
        "avgWorseningPct": avg_worsening_pct,
        "simpleWorseningPct": simple_avg_worsening,
        "overallSignal": overall_signal,
        "source": "NOAA/CPC 月度干旱展望（专家研判，综合ENSO/季节性降雨规律等因素，每州8点采样，按种植面积加权）",
        "sourceUrl": "https://www.cpc.ncep.noaa.gov/products/expert_assessment/mdo_summary.php",
        "debug": debugs,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    if not USDA_API_KEY:
        print(
            "[WARN] 未设置 USDA_API_KEY 环境变量，USDA相关数据将标记为不可用。\n"
            "       请到 https://api.data.gov/signup/ 免费申请，"
            "并在 GitHub 仓库 Settings → Secrets 里添加 USDA_API_KEY。",
            file=sys.stderr,
        )
    if not NASS_API_KEY:
        print(
            "[WARN] 未设置 NASS_API_KEY 环境变量，美豆优良率将标记为不可用。\n"
            "       请到 https://quickstats.nass.usda.gov/api 免费申请"
            "（跟USDA_API_KEY是两套不同的密钥系统）。",
            file=sys.stderr,
        )
    # 注：开机率/库存/基差/到港预报/猪粮比/能繁母猪/进口量这7项已全部改为"批量粘贴解析"方案
    #     (纯前端JS完成，见index.html)，不再需要UN Comtrade/USDA出口检验/Groq/Tavily
    #     这些后端集成——实测这类数据不管走官方API还是AI搜索都不够稳定/准确，
    #     不如让用户自己去问AI、亲眼确认、再粘贴解析来得可靠。

    no_usda_key = {"available": False, "reason": "缺少 USDA_API_KEY"}

    result = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "cbotPrice": fetch_cbot_price(),
        "droughtMonitor": fetch_drought_monitor(),
        "noaaOutlook": fetch_noaa_drought_outlook(),
        "soybeanCondition": fetch_soybean_condition(),
        "usPlantingProgress": fetch_us_planting_progress(),
        "usHarvestProgress": fetch_us_harvest_progress(),
        # ★ 技术面第一阶段：先只做当前主力9月合约(M09)验证可行，跑通后再加5月/1月合约
        "dceM09Daily": fetch_dce_daily_kline(get_current_contract_code(9)),
        "dceM09Hourly": fetch_dce_hourly_kline(get_current_contract_code(9)),
        "southAmericaWeather": fetch_south_america_weather(),
        "southAmericaPsd": fetch_south_america_psd() if USDA_API_KEY else no_usda_key,
        "exportSales": fetch_esr_export_sales() if USDA_API_KEY else no_usda_key,
        "supplyDemand": fetch_psd_supply_demand() if USDA_API_KEY else no_usda_key,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] 数据已写入 {OUTPUT_PATH}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
