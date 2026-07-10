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
from datetime import datetime, timezone

USDA_API_KEY = os.environ.get("USDA_API_KEY", "")
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
# 4. 美国干旱监测 (US Drought Monitor) —— 真正的官方干旱等级数据
#    区别于天气预报推算的"风险"，这是 NDMC/USDA/NOAA 每周四联合发布的
#    实测干旱分级 (D0-D4)，网页端(index.html)里天气板块用降雨预报算的是
#    "风险倾向"，这里补的是"官方实际认定的干旱状态"。
# ---------------------------------------------------------------------------
# 州名用两字母缩写做显示/内部key，但查询接口的aoi参数官方文档明确要求"两位数FIPS代码"
# （之前的bug就在这里：用了邮政缩写"IA"当aoi值，接口返回200+空数组，因为查无此州）
DROUGHT_STATES = ["IA", "IL", "MN"]  # 爱荷华/伊利诺伊/明尼苏达，豆粕主产区
DROUGHT_STATE_FIPS = {"IA": "19", "IL": "17", "MN": "27"}  # 官方文档：droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx


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

    avg_severe = sum(v["severeOrWorsePct"] for v in available_states.values()) / len(available_states)
    any_anomalous = any(v.get("anomalous") for v in available_states.values())

    return {
        "available": True,
        "anomalous": any_anomalous,
        "byState": out,
        "avgSevereOrWorsePct": round(avg_severe, 1),
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

# 跟天气监测用同一组代表性坐标，方便三层时间尺度互相对照
OUTLOOK_LOCATIONS = [
    {"name": "IA", "lat": 41.878, "lon": -93.097},
    {"name": "IL", "lat": 39.798, "lon": -89.644},
    {"name": "MN", "lat": 44.986, "lon": -93.279},
]

# 展望分类 → 对交易而言的方向（Development/Persistence=干旱在发展或持续=偏多；
# Improvement/Removal=干旱在改善或解除=偏空；No_Drought=预计维持无旱=中性偏空）
OUTLOOK_DIRECTION = {
    "Development": 1, "Persistence": 1,
    "Improvement": -1, "Removal": -1,
    "No_Drought": 0,
}
OUTLOOK_LABEL_CN = {
    "Development": "干旱发展中", "Persistence": "干旱持续",
    "Improvement": "干旱改善", "Removal": "干旱解除", "No_Drought": "预计无旱",
}


def fetch_noaa_drought_outlook():
    """查询NOAA/CPC月度干旱展望——用ArcGIS REST的Query接口，
    给一个经纬度点，返回覆盖这个点的展望区域是什么分类(Development/Persistence/Improvement/Removal/No_Drought)。
    已确认：这个服务坐标系是标准WGS84(4326)，不需要坐标转换。"""
    results = {}
    debugs = {}

    for loc in OUTLOOK_LOCATIONS:
        geometry = json.dumps({"x": loc["lon"], "y": loc["lat"], "spatialReference": {"wkid": 4326}})
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
        #   手动拼URL漏编码空格踩过2次坑了(到港预报那边)，这次直接用标准工具处理，
        #   geometry参数本身是一段JSON文本，里面有花括号/引号/冒号，更需要正确编码。
        query_string = urllib.parse.urlencode(params)
        url = f"{NOAA_OUTLOOK_QUERY_URL}?{query_string}"
        data, debug = fetch_json_debug(url)
        debugs[loc["name"]] = debug

        if not data or "features" not in data or not data["features"]:
            results[loc["name"]] = {"available": False}
            continue

        attrs = data["features"][0]["attributes"]
        outlook = attrs.get("outlook")
        results[loc["name"]] = {
            "available": True,
            "outlook": outlook,
            "outlookLabel": OUTLOOK_LABEL_CN.get(outlook, outlook),
            "targetPeriod": attrs.get("target"),
            "forecastDate": attrs.get("fcst_date"),
        }

    available = {k: v for k, v in results.items() if v.get("available")}
    if not available:
        return {"available": False, "reason": "NOAA月度干旱展望接口未返回任何州的数据", "debug": debugs}

    # 综合信号：任意一州判定"发展中"或"持续"就偏多倾向；全部"改善/解除/无旱"才偏空
    signals = [OUTLOOK_DIRECTION.get(v["outlook"], 0) for v in available.values()]
    # 简化判断逻辑：只要有任何一州展望是"发展中/持续"(drought worsening)，整体就偏多；
    # 否则(没有一个地方在恶化，不管是明确改善还是本来就没旱)，整体就偏空。
    # 之前用all(s==-1...)要求"全部州都严格是-1"才判偏空，但No_Drought信号是0不是-1，
    # 导致"两个州改善+一个州本来没旱"这种明显该偏空的组合被误判成中性，已修复。
    overall_signal = 1 if any(s == 1 for s in signals) else -1

    return {
        "available": True,
        "byLocation": results,
        "overallSignal": overall_signal,
        "source": "NOAA/CPC 月度干旱展望（专家研判，综合ENSO/季节性降雨规律等因素）",
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
