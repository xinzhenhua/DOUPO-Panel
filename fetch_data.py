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

import html
import json
import os
import re
import sys
import time
import socket
import threading
import base64
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from datetime import date as _date_cls

import cn_calendar
import history_store

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


def fetch_jsonp_debug(url, headers=None, retries=3, timeout=20):
    """
    跟 fetch_json_debug 一样，但专门处理JSONP格式的响应(用回调函数名包裹JSON，
    比如 callbackName({...JSON内容...}); 而不是纯JSON)。东方财富的
    datacenter-web接口就是这种格式——这是实测抓包确认的，不是文档记录的。
    先剥掉"函数名(...)"这层包装，再按JSON解析剥出来的内容。
    """
    headers = dict(headers or {})
    headers.setdefault("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    debug = {"url": url}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                debug["httpStatus"] = resp.status
                debug["rawSnippet"] = raw[:500]
                # 剥JSONP包装：形如 jQuery1123xxx({...}); ，取第一个'('和最后一个')'之间的内容。
                # 如果接口哪天不带回调直接返回纯JSON了，这个逻辑也不会出错——
                # 纯JSON整体也会被最外层的{}括号"包住"，正好落在第一个(和最后一个)之间为空的边界情况，
                # 所以额外做一次"看起来已经是纯JSON"的兜底判断。
                stripped = raw.strip()
                if stripped.startswith("{") or stripped.startswith("["):
                    json_text = stripped
                else:
                    first_paren = stripped.find("(")
                    last_paren = stripped.rfind(")")
                    if first_paren == -1 or last_paren == -1 or last_paren <= first_paren:
                        debug["error"] = "JSONP格式识别失败：响应内容里找不到成对的括号"
                        print(f"[WARN] JSONP解析失败: {url}\n  原始内容片段: {raw[:300]}", file=sys.stderr)
                        return None, debug
                    json_text = stripped[first_paren + 1:last_paren]
                try:
                    return json.loads(json_text), debug
                except json.JSONDecodeError as je:
                    debug["error"] = f"JSON解析失败: {je}（剥掉JSONP包装后的内容仍不是合法JSON）"
                    print(f"[WARN] JSON解析失败: {url} -> {je}\n  原始内容片段: {raw[:300]}", file=sys.stderr)
                    return None, debug
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:2000]
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


def fetch_json_debug(url, headers=None, retries=3, timeout=20, post_data=None):
    """
    跟 fetch_json 一样，但额外返回诊断信息 (data, debug)。
    debug 里包含：实际请求的url、HTTP状态码、响应体前500字符、异常信息。
    这样接口返回的东西跟预期不一致时，不需要去翻GitHub Actions运行日志，
    直接看 data/latest.json 里的诊断字段就知道真实情况是什么。

    ★新增post_data参数(向后兼容，默认None=GET，不影响任何既有调用方)：
    传入一个dict时，改用POST方法+JSON body发送(Mysteel快讯搜索接口这类需要
    POST的场景要用到)，dict会被json.dumps()编码成请求体，自动补上
    Content-Type: application/json;charset=UTF-8(不覆盖调用方自己传的同名头)。
    """
    headers = dict(headers or {})
    # 防御性修复：很多网站/API服务(包括Groq)会挡掉Python urllib默认的User-Agent
    # (被Cloudflare等WAF当作机器人流量拦截，报错"error code: 1010")，
    # 这里统一给个正常浏览器UA垫底，调用方传入的headers仍可以覆盖它。
    headers.setdefault("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    debug = {"url": url}
    body_bytes = None
    if post_data is not None:
        headers.setdefault("Content-Type", "application/json;charset=UTF-8")
        body_bytes = json.dumps(post_data, ensure_ascii=False).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers, data=body_bytes)
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
                # ★已放宽(原500)：agtransport那次SoQL报错("No such column")里，
                #   Socrata会把整个数据集的字段清单回显出来帮助排查，之前500字符
                #   截断把这份清单切掉了大半，只看到"date, cert_date, week, month,
                #   quarter..."就没了——看不到真正需要确认的grain/mt这些字段
                #   到底叫什么。放宽到2000字符，留足空间容纳这类"字段清单"级别
                #   的错误信息，不需要真的运行了才发现被截断、还得再等一轮。
                body = e.read().decode("utf-8", errors="replace")[:2000]
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


def get_soybean_esr_code():
    """动态查找\"Soybeans\"(大豆本身，不是豆粕/豆油)在 ESR 商品列表里的编码。
    ★为什么从豆粕改成大豆：美国豆粕出口量对DCE豆粕的影响远小于\"美豆对华销售\"，
      ESR里能拿来判断中国买家动向的是大豆(801)这一项，不是豆粕。
    返回 (code, debug)：code为None时，debug里说明是\"请求失败\"还是\"没匹配上\"。"""
    data, debug = fetch_json_debug(f"{USDA_BASE}/esr/commodities", headers={"X-Api-Key": USDA_API_KEY})
    if not data:
        debug["failureStage"] = "请求/esr/commodities本身失败（网络问题、认证失败、或被限流）"
        return None, debug
    # 第一优先级：名称精确等于"soybeans"(不区分大小写/首尾空格)
    for item in data:
        if (item.get("commodityName") or "").strip().lower() == "soybeans":
            return item.get("commodityCode"), None
    # 兜底：含soybean、且不是meal/cake/oil
    for item in data:
        name = (item.get("commodityName") or "").lower()
        if "soybean" in name and not any(x in name for x in ("meal", "cake", "oil")):
            return item.get("commodityCode"), None
    debug["failureStage"] = "接口请求成功，拿到了商品列表，但没有一条是'Soybeans'(大豆本身)"
    debug["actualCommodityNamesSeen"] = sorted(set((item.get("commodityName") or "") for item in data))[:50]
    debug["totalCommoditiesReturned"] = len(data)
    return None, debug


# ★ESR每行数据里两个容易混淆的量：
#   weeklyExports      = 当周实际装船出口量(shipments，已经发走的货)
#   currentMYNetSales / nextMYNetSales = 当周净销售(net sales，新签的合同，本年度+下一年度)
# 之前的版本按\"weeklyExports优先\"取数，却把它标成\"净销售\"，等于把装船量当成了销售量。
# 买家的采购意愿看的是净销售；装船量是滞后的执行结果，单独展示，不混用。
ESR_NET_SALES_FIELDS = ("currentMYNetSales", "nextMYNetSales")


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _esr_net_sales(row):
    return sum(_num(row.get(f)) for f in ESR_NET_SALES_FIELDS)


def _is_china(row):
    """国家名里含china(不区分大小写)算中国。这是按名称匹配的，没法在开发环境里核对ESR接口里中国
    到底怎么写——所以结果里会带上出现过的国家名列表(countryNamesSeen)，部署后可以核对。"""
    return "china" in (row.get("countryName") or "").lower()


def _is_unknown_dest(row):
    """\"未知目的地\"：买家国家还没确定的销售。ESR的做法不是回头修改历史，而是国家明确的那一周
    记一笔目的地变更(未知记负、具体国家记正)。所以单周的中国数字会忽小忽大，未知也不能直接算成中国。"""
    return "unknown" in (row.get("countryName") or "").lower()


def _adjust_rollover_weeks(weekly):
    """★市场年度切换周(周截止日在8/31~9/6)的净销售系统性偏高：12年逐年的这一周都是尖峰(比前后两周高一到三倍，
    2020年564万吨)。推断原因：新年度第一周的"本年度净销售"里带入了上年度已经报过的"下年度销售"(结转)，
    而我们把 本年度净销售+下年度净销售 加总，等于把结转的部分重复算了一次。
    处理：切换周用相邻两周的均值代替(两边都在才行)。返回(调整后的列表, 最新一周本身是不是切换周, 被调整的周)。"""
    out = [dict(w) for w in weekly]
    adjusted = []
    keys = ("netSalesMT", "chinaNetSalesMT", "unknownNetSalesMT", "otherNetSalesMT")
    for i, w in enumerate(out):
        if history_store.is_rollover_week(str(w["weekEnding"])[:10]) and 0 < i < len(out) - 1:
            for k in keys:
                w[k] = round((weekly[i - 1][k] + weekly[i + 1][k]) / 2)
            w["rolloverAdjusted"] = True
            adjusted.append(str(w["weekEnding"])[:10])
    return out, history_store.is_rollover_week(str(out[-1]["weekEnding"])[:10]), adjusted


def fetch_esr_export_sales():
    code, code_lookup_debug = get_soybean_esr_code()
    if not code:
        return {
            "available": False,
            "reason": "未能找到大豆(Soybeans)的ESR商品编码",
            "debug": code_lookup_debug,
        }

    # 同时试几个候选年份(不猜哪个是当前年度)，把每个年度的逐周数据都收下来。
    # 跨市场年度切换(9月初)时，4周均值需要用到上一个年度的最后几周，所以不能只留\"最新年度\"一份。
    now = datetime.now(timezone.utc)
    candidate_years = [now.year - 1, now.year, now.year + 1]
    rows_by_year = {}
    all_attempts_debug = {}
    for candidate_my in candidate_years:
        url = f"{USDA_BASE}/esr/exports/commodityCode/{code}/allCountries/marketYear/{candidate_my}"
        rows, debug = fetch_json_debug(url, headers={"X-Api-Key": USDA_API_KEY})
        all_attempts_debug[str(candidate_my)] = {
            "httpStatus": debug.get("httpStatus"),
            "rowCount": len(rows) if rows else 0,
            "latestWeekFound": max((r.get("weekEndingDate") for r in rows if r.get("weekEndingDate")), default=None) if rows else None,
        }
        if rows:
            rows_by_year[candidate_my] = rows

    if not rows_by_year:
        return {
            "available": False,
            "reason": "ESR接口无返回数据（已尝试" + "、".join(str(y) for y in candidate_years) + "这几个候选年份）",
            "debug": all_attempts_debug,
        }

    # 每个周次只取\"包含这一周的最大市场年度\"那一批行，避免年度交界处同一周被两个年度重复计入。
    week_rows = {}
    for my in sorted(rows_by_year):
        by_week = {}
        for r in rows_by_year[my]:
            w = r.get("weekEndingDate")
            if w:
                by_week.setdefault(w, []).append(r)
        for w, rs in by_week.items():
            week_rows[w] = (my, rs)

    unique_weeks = sorted(week_rows)
    if len(unique_weeks) < 2:
        return {
            "available": False,
            "reason": "数据量不足以计算环比（不足两个不同周次）",
            "debug": {"note": f"去重后只有{len(unique_weeks)}个周次", "attempts": all_attempts_debug},
        }

    # ★不做\"净销售字段找不到就退回weeklyExports\"的静默兜底——那正是之前把装船量当成销售量的原因。
    latest_rows = week_rows[unique_weeks[-1]][1]
    if not any(f in r for r in latest_rows for f in ESR_NET_SALES_FIELDS):
        return {
            "available": False,
            "reason": "ESR返回的数据里找不到净销售字段(currentMYNetSales/nextMYNetSales)，为避免把装船量误当成净销售，不使用",
            "debug": {"actualFieldsSeen": sorted(latest_rows[0].keys()) if latest_rows else [],
                      "sampleRawRow": latest_rows[0] if latest_rows else None},
        }

    weekly = []
    country_names_seen = set()
    for w in unique_weeks:
        my, rs = week_rows[w]
        china = [r for r in rs if _is_china(r)]
        unknown = [r for r in rs if _is_unknown_dest(r)]
        for r in rs:
            n = (r.get("countryName") or "").strip()
            if n:
                country_names_seen.add(n)
        net_total = sum(_esr_net_sales(r) for r in rs)
        china_net = sum(_esr_net_sales(r) for r in china)
        unknown_net = sum(_esr_net_sales(r) for r in unknown)
        weekly.append({
            "weekEnding": w,
            "marketYear": my,
            "netSalesMT": net_total,
            "shipmentsMT": sum(_num(r.get("weeklyExports")) for r in rs),
            "chinaNetSalesMT": china_net,
            "unknownNetSalesMT": unknown_net,
            "otherNetSalesMT": net_total - china_net - unknown_net,
            "chinaShipmentsMT": sum(_num(r.get("weeklyExports")) for r in china),
        })

    weekly, latest_is_rollover, rollover_adjusted = _adjust_rollover_weeks(weekly)
    latest, prev = weekly[-1], weekly[-2]
    trailing = weekly[-5:-1]  # 最新一周之前的4周，作为\"近期常态\"基准，比单看环比噪音小得多
    avg4 = round(sum(x["netSalesMT"] for x in trailing) / 4) if len(trailing) == 4 else None
    vs4w = round((latest["netSalesMT"] - avg4) / abs(avg4) * 100, 1) if avg4 else None
    wow = round((latest["netSalesMT"] - prev["netSalesMT"]) / abs(prev["netSalesMT"]) * 100, 1) if prev["netSalesMT"] else None
    if latest_is_rollover:
        # 最新一周本身就是切换周：没法用相邻两周代替(下一周还没出)，含结转的数字不能拿来比，一律不给
        vs4w = wow = None
    last4 = weekly[-4:]
    sum4 = (lambda key: None if latest_is_rollover else sum(x[key] for x in last4))

    try:
        latest_date_parsed = datetime.fromisoformat(latest["weekEnding"].replace("Z", "+00:00"))
        if latest_date_parsed.tzinfo is None:
            latest_date_parsed = latest_date_parsed.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - latest_date_parsed).days
    except (ValueError, AttributeError):
        age_days = None
    is_stale = age_days is not None and age_days > 25

    result = {
        "available": True,
        "commodity": "Soybeans(大豆)",
        "weekEnding": latest["weekEnding"],
        "marketYearUsed": latest["marketYear"],
        "dataAgeDays": age_days,
        "isStale": is_stale,
        "netSalesMT": latest["netSalesMT"],
        "prevNetSalesMT": prev["netSalesMT"],
        "avg4wNetSalesMT": avg4,
        "vs4wAvgPct": vs4w,
        "wowChangePct": wow,
        "shipmentsMT": latest["shipmentsMT"],
        "chinaNetSalesMT": latest["chinaNetSalesMT"],
        "unknownNetSalesMT": latest["unknownNetSalesMT"],
        "otherNetSalesMT": latest["otherNetSalesMT"],
        "chinaShipmentsMT": latest["chinaShipmentsMT"],
        # 近4周(含最新周)滚动合计：抹平\"未知→中国\"目的地变更造成的单周跳动
        "china4wSumMT": sum4("chinaNetSalesMT"),
        "unknown4wSumMT": sum4("unknownNetSalesMT"),
        "total4wSumMT": sum4("netSalesMT"),
        "chinaShare4wPct": (round(sum4("chinaNetSalesMT") / sum4("netSalesMT") * 100, 1)
                            if (not latest_is_rollover and sum4("netSalesMT") > 0) else None),
        "latestIsRollover": latest_is_rollover,               # 最新一周是市场年度切换周(净销售含结转，虚高)：不判方向
        "rolloverAdjustedWeeks": rollover_adjusted,          # 已经用相邻两周均值代替的切换周
        "chinaMatched": any(_is_china(r) for _, (_, rs) in week_rows.items() for r in rs),
        "countryNamesSeen": sorted(country_names_seen)[:60],
        "recentWeeks": [{"weekEnding": x["weekEnding"], "netSalesMT": x["netSalesMT"],
                         "chinaNetSalesMT": x["chinaNetSalesMT"], "unknownNetSalesMT": x["unknownNetSalesMT"]} for x in weekly[-8:]],
        "source": "USDA-FAS ESR API",
        "sourceUrl": "https://apps.fas.usda.gov/esrqs/",
    }
    if is_stale:
        result["debug"] = {
            "warning": f"最新数据是{latest['weekEnding']}，距今{age_days}天，已超过25天的新鲜度阈值，"
                       f"ESR是每周更新的报告，这可能意味着接口有延迟或候选年份范围需要调整",
            "allCandidateYearsResults": all_attempts_debug,
        }
    if latest["netSalesMT"] == 0 and prev["netSalesMT"] == 0:
        result["debug"] = {
            "warning": "已连接上接口并拿到数据，但连续两周净销售汇总为0，可能是净销售字段名(currentMYNetSales/nextMYNetSales)没匹配上",
            "actualFieldsSeen": sorted(latest_rows[0].keys()) if latest_rows else [],
            "sampleRawRow": latest_rows[0] if latest_rows else None,
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
        "exports": "Exports",
        "crush": "Crush",
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


def _psd_target_market_year(now):
    """美豆的PSD市场年度按起始年份标记(2026=2026/27，9月1日开始)。
    5月WASDE起首次给出新年度预估——9月合约窗口(4-7月)看的正是新作物平衡表，
    所以5月起用\"当年\"，1-4月用\"上一年\"(还在当前年度内，新年度预估要5月才发布)。"""
    return now.year if now.month >= 5 else now.year - 1


def fetch_psd_supply_demand():
    """美国大豆(Oilseed, Soybean)的供需平衡表，算库存消费比(stocks-to-use)。
    ★之前抓的是美国豆粕：豆粕是流量型商品，期末库存只占消费的1-3%，套用\"大豆\"的阈值等于永远偏多；
      大豆库存消费比的标准口径是 期末库存 ÷ (国内消费+出口)，即 期末库存/总用量。"""
    code, code_lookup_debug = get_soybean_psd_code()
    if not code:
        return {
            "available": False,
            "reason": "未能找到大豆(Oilseed, Soybean)的PSD商品编码",
            "debug": code_lookup_debug,
        }
    matched_name = (code_lookup_debug or {}).get("matchedName")

    attr_map, attr_map_source = get_psd_attribute_names()

    now = datetime.now(timezone.utc)
    target = _psd_target_market_year(now)
    candidate_years = [target - 1, target, target + 1]
    candidates = {}
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
        candidates[candidate_year] = {
            "year": candidate_year, "rows": rows, "out": out,
            "seen_attrs": seen_attrs, "has_string_names": has_string_names, "vintage": vintage,
        }

    if not candidates:
        return {
            "available": False,
            "reason": "PSD接口无返回数据（已尝试" + "、".join(str(y) for y in candidate_years) + "这几个候选年份）",
            "debug": all_attempts,
        }

    # ★按日历规则选目标年度(见_psd_target_market_year)，而不是\"哪个年度WASDE版本最新\"——
    #   之前的做法在版本月份相同时会取到已经结束的旧年度。目标年度没有解析出数据时才退回版本最新的。
    best = candidates.get(target)
    if best is None or not best["out"]:
        best = max(candidates.values(), key=lambda c: (bool(c["out"]), c["vintage"] or ("", "")))

    year = best["year"]
    out = best["out"]
    vintage = best["vintage"]

    es, dc, ex = out.get("Ending Stocks"), out.get("Domestic Consumption"), out.get("Exports")
    total_use = (dc + ex) if (dc is not None and ex is not None) else None
    stocks_to_use = round(es / total_use * 100, 1) if (es is not None and total_use) else None

    result = {
        "available": True,
        "commodity": matched_name or "Oilseed, Soybean",
        "marketYear": year,
        "marketYearLabel": f"{year}/{str(year + 1)[-2:]}",
        "wasdeVintage": f"{vintage[0]}年{vintage[1]}月版" if vintage else "未知",
        "endingStocks": es,
        "production": out.get("Production"),
        "totalSupply": out.get("Total Supply"),
        "domesticConsumption": dc,
        "exports": ex,
        "crush": out.get("Crush"),
        "totalUse": total_use,
        "stocksToUsePct": stocks_to_use,
        "unit": "千公吨(USDA PSD标准单位)",
        "source": "USDA-FAS PSD API (WASDE同源数据)",
        "sourceUrl": "https://apps.fas.usda.gov/psdonline/",
    }

    if not out:
        if best["has_string_names"]:
            warning = "已连接上接口并拿到数据，但字段名一个都没匹配上，可能是接口实际用的attributeName和预期不同"
        else:
            warning = "接口返回的是数字attributeId而不是字符串名称，且未能成功获取attributeId对照表（这个对照表接口的确切路径尚未100%确认）"
        result["debug"] = {
            "warning": warning,
            "actualAttributeNamesSeen": sorted(str(a) for a in best["seen_attrs"])[:30],
            "sampleRawRow": best["rows"][0] if best["rows"] else None,
            "allCandidateYearsAttempted": all_attempts,
        }

    return result


# ---------------------------------------------------------------------------
# 美豆优良率（USDA/NASS 每周作物生长报告，Crop Progress的"Good+Excellent"评级）
# 每年4月-11月每周一发布，是美豆生长季最重要的周度指标之一
# ---------------------------------------------------------------------------
NASS_BASE = "https://quickstats.nass.usda.gov/api/api_GET/"

# ★"进度型"指标(优良率/播种进度/收获进度)专用：同比+五年均值的共用逻辑。
# 这几个都是NASS Quick Stats接口，用year参数分年查询——这个接口是官方稳定接口，
# 不是那种容易被风控的爬虫源，所以多查几年(6次而不是1次)的可靠性风险不大。
def _fetch_nass_years(base_params, years):
    """给定NASS查询参数(不含year)和一组年份，依次查询每一年，返回{year: rows_list}。
    某一年查不到就跳过(不是每年都有对应季节的数据，比如季节还没开始)，
    不会因为某一年缺数据就让整个同比/五年均值计算失败。"""
    results = {}
    for year in years:
        params = dict(base_params)
        params["year"] = str(year)
        url = f"{NASS_BASE}?{urllib.parse.urlencode(params)}"
        data, debug = fetch_json_debug(url, retries=1)  # 历史年份查询失败不重试3次，避免拖慢整体运行时间
        if data and "data" in data and data["data"]:
            results[year] = data["data"]
    return results


def _find_closest_week_rows(rows, target_date, week_field="week_ending"):
    """在给定一年的rows里，找week_ending离target_date(date对象)最近的那一周，
    返回(那个week_ending字符串, 该周对应的所有行)。用"最接近"而不是要求精确匹配，
    是因为USDA的周次一般定在周日，不同年份"同一个月同一天"未必是周日，
    找最近的周日周次才是真正对应"去年同期"的正确对比对象。"""
    from datetime import date as date_cls
    weeks_seen = sorted(set(r.get(week_field) for r in rows if r.get(week_field)))
    if not weeks_seen:
        return None, []

    def parse_date(s):
        return date_cls(*(int(x) for x in s.split("-")))

    closest_week = min(weeks_seen, key=lambda w: abs((parse_date(w) - target_date).days))
    matched_rows = [r for r in rows if r.get(week_field) == closest_week]
    return closest_week, matched_rows


def _target_date_n_years_ago(base_date, n):
    """base_date往前推n年的"同一个月同一天"，用来在历史年份数据里找对应周次。
    处理闰年2月29日这种极端边界：往前推年份后如果那天不存在(比如推到非闰年的2月29日)，
    就退到2月28日，不让这种边缘情况直接让整个历史对比失败。"""
    try:
        return base_date.replace(year=base_date.year - n)
    except ValueError:
        return base_date.replace(year=base_date.year - n, day=28)


def _compute_yoy_and_five_year_avg(current_rows, current_week_ending, base_params, value_extractor):
    """通用的同比+五年均值计算：value_extractor是个函数，输入"某一周对应的行列表"，
    输出这一周该指标的数值(比如优良率要把EXCELLENT+GOOD两行加总，播种/收获进度
    只需要一个PCT字段)——三个指标各自的取值逻辑不一样，这里只负责"找到对应周次
    +查多年数据"这个共同部分。
    返回(yoyValue, yoyChangePts, fiveYearAvg, fiveYearAvgChangePts)，某一项算不出来就是None。"""
    from datetime import date as date_cls
    current_value = value_extractor(
        [r for r in current_rows if r.get("week_ending") == current_week_ending]
    )
    if current_value is None:
        return None, None, None, None

    latest_date = date_cls(*(int(x) for x in current_week_ending.split("-")))
    years_back = [1, 2, 3, 4, 5]
    target_dates = {n: _target_date_n_years_ago(latest_date, n) for n in years_back}
    historical_years = [latest_date.year - n for n in years_back]
    year_data = _fetch_nass_years(base_params, historical_years)

    matched_values = {}  # {往前第几年: 数值}
    for n in years_back:
        year = latest_date.year - n
        if year not in year_data:
            continue
        _, matched_rows = _find_closest_week_rows(year_data[year], target_dates[n])
        val = value_extractor(matched_rows)
        if val is not None:
            matched_values[n] = val

    yoy_value = matched_values.get(1)
    yoy_change = round(current_value - yoy_value, 1) if yoy_value is not None else None

    five_year_values = list(matched_values.values())  # 有几年算几年，不强求凑满5年
    five_year_avg = round(sum(five_year_values) / len(five_year_values), 1) if five_year_values else None
    five_year_avg_change = round(current_value - five_year_avg, 1) if five_year_avg is not None else None

    return yoy_value, yoy_change, five_year_avg, five_year_avg_change


def fetch_soybean_condition():
    """查询USDA/NASS Quick Stats的美豆生长状况评级(优良率=Excellent%+Good%)。
    这个数据每年只在4月-11月生长季发布，其余月份接口有数据但不会更新(正常现象)。
    ★属于"进度型"指标(0-100%有界、季节性强)，除了环比，也算同比+五年均值——
    单看环比容易被单周噪音误导，同比+五年均值才能看出"今年这个水平算不算异常"。"""
    if not NASS_API_KEY:
        return {"available": False, "reason": "缺少 NASS_API_KEY"}

    now = datetime.now(timezone.utc)
    base_params = {
        "key": NASS_API_KEY,
        "commodity_desc": "SOYBEANS",
        "statisticcat_desc": "CONDITION",
        "agg_level_desc": "NATIONAL",
        "format": "JSON",
    }
    params = dict(base_params, year=str(now.year))
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

    def extract_good_excellent(week_rows):
        """从某一周的行列表里，把EXCELLENT+GOOD两个等级的百分比加总。取不到就返回None。"""
        excellent, good = None, None
        for r in week_rows:
            desc = (r.get("short_desc") or r.get("unit_desc") or "").upper()
            try:
                val = float(str(r.get("Value", "")).replace(",", ""))
            except (ValueError, TypeError):
                continue
            if "EXCELLENT" in desc:
                excellent = val
            elif "GOOD" in desc and "VERY" not in desc:
                good = val
        if excellent is None or good is None:
            return None
        return round(excellent + good, 1)

    good_excellent = extract_good_excellent(latest_rows)
    if good_excellent is None:
        return {
            "available": False,
            "reason": "拿到数据但没能识别出Excellent/Good这两个等级的字段",
            "debug": {"sampleRawRows": latest_rows[:5], "actualDescsSeen": [r.get("short_desc") for r in latest_rows]},
        }

    # 环比：找上一个有数据的周
    prev_change = None
    if len(weeks) >= 2:
        prev_value = extract_good_excellent([r for r in rows if r.get("week_ending") == weeks[-2]])
        if prev_value is not None:
            prev_change = round(good_excellent - prev_value, 1)

    yoy_value, yoy_change, five_year_avg, five_year_avg_change = _compute_yoy_and_five_year_avg(
        rows, latest_week, base_params, extract_good_excellent
    )

    return {
        "available": True,
        "weekEnding": latest_week,
        "goodExcellentPct": good_excellent,
        "wowChangePts": prev_change,
        "yoyValue": yoy_value,
        "yoyChangePts": yoy_change,
        "fiveYearAvg": five_year_avg,
        "fiveYearAvgChangePts": five_year_avg_change,
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
    因为播种季结束后这个"进度%"就一直停在100%不变了，不像"CONDITION"那样全季都更新)。
    ★属于"进度型"指标，同时算同比+五年均值(逻辑跟优良率共用_compute_yoy_and_five_year_avg)。"""
    if not NASS_API_KEY:
        return {"available": False, "reason": "缺少 NASS_API_KEY"}

    now = datetime.now(timezone.utc)
    base_params = {
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
        "format": "JSON",
    }
    params = dict(base_params, year=str(now.year))
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

    def extract_pct_planted(week_rows):
        pct_only = [r for r in week_rows if "PCT PLANTED" in (r.get("short_desc") or "").upper()]
        if not pct_only:
            return None
        try:
            return float(str(pct_only[0].get("Value", "")).replace(",", ""))
        except (ValueError, TypeError):
            return None

    pct_planted = extract_pct_planted([r for r in pct_rows if r.get("week_ending") == latest_week])
    if pct_planted is None:
        return {"available": False, "reason": "PCT PLANTED字段值无法解析为数字", "debug": {"latestWeek": latest_week}}

    # 环比：找上一个有数据的周
    prev_change = None
    if len(weeks) >= 2:
        prev_pct = extract_pct_planted([r for r in pct_rows if r.get("week_ending") == weeks[-2]])
        if prev_pct is not None:
            prev_change = round(pct_planted - prev_pct, 1)

    yoy_value, yoy_change, five_year_avg, five_year_avg_change = _compute_yoy_and_five_year_avg(
        rows, latest_week, base_params, extract_pct_planted
    )

    return {
        "available": True,
        "weekEnding": latest_week,
        "pctPlanted": pct_planted,
        "wowChangePts": prev_change,
        "yoyValue": yoy_value,
        "yoyChangePts": yoy_change,
        "fiveYearAvg": five_year_avg,
        "fiveYearAvgChangePts": five_year_avg_change,
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
    这个数据只在每年9-11月(收获季)有意义，其余月份接口有数据但不会更新(正常现象)。
    ★属于"进度型"指标，同时算同比+五年均值(逻辑跟优良率共用_compute_yoy_and_five_year_avg)。"""
    if not NASS_API_KEY:
        return {"available": False, "reason": "缺少 NASS_API_KEY"}

    now = datetime.now(timezone.utc)
    base_params = {
        "key": NASS_API_KEY,
        "commodity_desc": "SOYBEANS",
        # ★已修复(第三次修复，找到确切根因，跟播种进度同样的问题)：周度收获进度
        #   百分比在"PROGRESS"这个statisticcat_desc底下，配合unit_desc="PCT HARVESTED"
        #   筛出具体阶段，不是"AREA HARVESTED"(那是年度英亩数调查)。
        "statisticcat_desc": "PROGRESS",
        "unit_desc": "PCT HARVESTED",
        "agg_level_desc": "NATIONAL",
        "format": "JSON",
    }
    params = dict(base_params, year=str(now.year))
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

    def extract_pct_harvested(week_rows):
        pct_only = [r for r in week_rows if "PCT HARVESTED" in (r.get("short_desc") or "").upper()]
        if not pct_only:
            return None
        try:
            return float(str(pct_only[0].get("Value", "")).replace(",", ""))
        except (ValueError, TypeError):
            return None

    pct_harvested = extract_pct_harvested([r for r in pct_rows if r.get("week_ending") == latest_week])
    if pct_harvested is None:
        return {"available": False, "reason": "PCT HARVESTED字段值无法解析为数字", "debug": {"latestWeek": latest_week}}

    prev_change = None
    if len(weeks) >= 2:
        prev_pct = extract_pct_harvested([r for r in pct_rows if r.get("week_ending") == weeks[-2]])
        if prev_pct is not None:
            prev_change = round(pct_harvested - prev_pct, 1)

    yoy_value, yoy_change, five_year_avg, five_year_avg_change = _compute_yoy_and_five_year_avg(
        rows, latest_week, base_params, extract_pct_harvested
    )

    return {
        "available": True,
        "weekEnding": latest_week,
        "pctHarvested": pct_harvested,
        "wowChangePts": prev_change,
        "yoyValue": yoy_value,
        "yoyChangePts": yoy_change,
        "fiveYearAvg": five_year_avg,
        "fiveYearAvgChangePts": five_year_avg_change,
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
# 油厂开机率：改自动抓取，用Mysteel(钢联)的快讯搜索接口。
#
# ★实测确认过程(不是猜的，是用户实际抓包+我逐条核对过的)：
#   ① 接口: POST https://search.mysteel.com/searchapi/search/searchFlashNews
#      查询关键词"全国动态全样本油厂开机率"，回传按日期新到旧排序的快讯列表。
#   ② 逐条核对了2026年9月9日到9月23日共12个交易日的真实content字段，
#      核心句式100%一致："...开机方面，今日全国动态全样本油厂开机率为
#      XX.XX%，较前一日[上升/下降/持平]..."——用正则提取"开机率为(数字)%"
#      这个模式应该可靠，不依赖换行符等次要格式(实测有一条记录缺了\r\n
#      换行符，但核心句式不受影响)。
#   ③ 请求头里的token字段实测值是字面量"-1"，看起来是"匿名/未登录"的
#      占位值，不是需要破解的动态签名——直接固定发送这个值。
#   ④ 没法在开发环境里实测这个接口(域名不在网络白名单里)，这次的实现要靠
#      GitHub Actions真实跑一次来验证——跟其他好几个数据源一样的路子。
MYSTEEL_SEARCH_URL = "https://search.mysteel.com/searchapi/search/searchFlashNews"


# ---------------------------------------------------------------------------
# ★数据合理性防线(用户发现豆粕库存抓到"0.7万吨"后加的)：从文章里用正则提取数字，最
#   大的风险是提取到"变动量"或"别的指标的数"而不是指标本身——例如"豆粕库存较上周增加
#   0.7万吨"被当成库存0.7万吨。这张表给每个指标一个宽松但不荒谬的合理范围：抓到
#   范围之外的数值一律丢弃(继续找下一个候选)，全部被丢弃就诚实报告失败，宁可显示
#   "抓取失败"也不显示荒谬的数字。前端index.html里有同一张表(SANITY_RANGES)兜底，
#   有测试保证两边一致。范围故意放宽(比如开机率10~100)，只挡明显荒谬的值，不是
#   要替用户判断行情好坏。
PLAUSIBLE_RANGES = {
    "chickenFeedRatio": (0.5, 6.0, ""),               # 鸡料比价(肉鸡价格÷饲料价格；实测1.79~2.41)
    "spotMealPrice": (1500.0, 6000.0, "元/吨"),     # 豆粕现货价/主力合约结算价(生意社)
    "spotBasis": (-1000.0, 1000.0, "元/吨"),         # 现货-主力合约结算价(自己算；比 Mysteel 沿海代表的 ±500 宽，全国综合现货对主力合约的基差更大)
    "crushRate": (10.0, 100.0, "%"),            # 油厂开机率
    "poultryProfit": (-20.0, 20.0, "元/只"),     # 白羽肉鸡养殖利润(可为负)
    "rmSpread": (100.0, 3000.0, "元/吨"),        # 豆菜粕现货价差(变动幅度一般只有几十，会被挡掉)
    "arrivalForecast": (200.0, 2000.0, "万吨"),  # 月度大豆到港预报
    "mealStock": (10.0, 600.0, "万吨"),          # 豆粕商业库存
    "feedDays": (1.0, 30.0, "天"),              # 饲料企业豆粕库存天数(常态约5~10天；见到的样本7.41天)
    "mealStu": (1.0, 40.0, "%"),                # 国内豆粕库消比(月末库存÷当月消费；近12个月实测5.94~16.30)
    "soyImport": (200.0, 2000.0, "万吨"),        # 中国大豆月度进口量(2026年最低401.9，最高约1400)
    "reserveAuction": (0.1, 300.0, "万吨"),      # 国储进口大豆单次计划拍卖量(实测6.8~54.3)
    "soyAuctionPrice": (2000.0, 8000.0, "元/吨"),  # 国储进口大豆拍卖价格(实测4110~4450)
    "meaBasis": (-500.0, 500.0, "元/吨"),        # 豆粕现货基差(实测-200~+170)
    "hogRatio": (1.0, 20.0, ""),                # 猪粮比
    "pigPrice": (3.0, 40.0, "元/公斤"),          # 外三元生猪价格
    "cornPricePerTon": (1000.0, 6000.0, "元/吨"),  # 玉米价格
    "sowInventory": (1000.0, 10000.0, "万头"),   # 能繁母猪存栏
}
_CHANGE_WORDS = ("较", "比", "减", "降", "增", "升", "下滑", "回落")
_LEVEL_VERB_RE = re.compile(r"(?:下降|上升|减少|增加|增长|回落|降|减|增|升)[至到]")


def _plausibility_problem(key, value):
    """数值在合理范围内返回None，否则返回一句说明(用于日志/诊断信息)。"""
    lo, hi, unit = PLAUSIBLE_RANGES[key]
    if value is None or value != value:
        return "数值无效(NaN)"
    if not (lo <= value <= hi):
        return f"{value:g}{unit}超出合理范围({lo:g}~{hi:g}{unit})"
    return None


def _looks_like_change(gap):
    """指标名和数字之间的这段文字是不是在描述"变动量"(较上周增加/同比下降…)。
    "降至/增至/升至"是到达某个水平，不算变动量。"""
    return any(w in _LEVEL_VERB_RE.sub("", gap) for w in _CHANGE_WORDS)



def fetch_mysteel_crush_rate():
    """通过Mysteel快讯搜索"全国动态全样本油厂开机率"这个关键词，从最新一条
    包含"开机率为"字样的快讯正文里，用正则提取百分比数值。"""
    now_bj = datetime.now(timezone.utc) + timedelta(hours=8)  # 转成北京时间
    start_bj = now_bj - timedelta(days=14)  # 抓最近2周，肯定能覆盖到最新一条(平常交易日基本天天发)
    payload = {
        "query": "全国动态全样本油厂开机率",
        "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
        "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"),
        "sortType": "complex",
        "platform": "pc",
        "pageNo": 1,
        "pageSize": 20,
    }
    headers = {
        "token": "-1",
        "Origin": "https://search.mysteel.com",
        "Referer": "https://search.mysteel.com/fastcomment.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    data, debug = fetch_json_debug(MYSTEEL_SEARCH_URL, headers=headers, post_data=payload)

    if data is None:
        return {"available": False, "reason": "Mysteel接口无返回数据", "debug": debug}
    if not isinstance(data, dict) or data.get("resultCode") != 0:
        return {
            "available": False,
            "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
            "debug": {"rawSnippet": debug.get("rawSnippet")},
        }

    data_list = data.get("dataList") or []
    if not data_list:
        return {"available": False, "reason": "搜索结果为空(最近14天内没有匹配的快讯)", "debug": {"total": data.get("total")}}

    # 逐条找第一条能提取出"开机率为XX.XX%"的记录(不假设一定是第0条，
    # 万一排序方式或者某条记录格式有出入，逐条尝试更稳)
    rejected = []
    for item in data_list:
        content = item.get("content") or ""
        for m in re.finditer(r"开机率为(\d+\.?\d*)%", content):
            value = float(m.group(1))
            problem = _plausibility_problem("crushRate", value)
            if problem:
                rejected.append(problem)
                continue
            day = item.get("publishTime", "")[:10]
            return {
                "available": True,
                "value": value,
                "date": day,
                # ★春节停机扰动窗口(节前7天~节后14天)：油厂放假，开机率掉到10~40%不代表供应紧；页面据此不计分(见cn_calendar.CRUSH_FESTIVAL_*)
                "festival": cn_calendar.crush_festival_window(day),
                "rawContent": content,
                "source": "Mysteel快讯(全国动态全样本油厂开机率)",
                "sourceUrl": "https://search.mysteel.com/fastcomment.html",
            }

    if rejected:
        return {"available": False, "reason": f"提取到的开机率数值都不合理，已丢弃: {'; '.join(rejected[:3])}",
                "debug": {"rejectedImplausible": rejected[:10], "firstItemContent": data_list[0].get("content")}}
    return {
        "available": False,
        "reason": "搜索结果里没有一条能提取出'开机率为XX.XX%'这个格式(可能措辞变了)",
        "debug": {"firstItemContent": data_list[0].get("content"), "totalItemsChecked": len(data_list)},
    }


# ---------------------------------------------------------------------------
# 白羽肉鸡养殖利润：改自动抓取，用Mysteel(钢联)的"文章"搜索接口
# (跟开机率用的"快讯"搜索是不同的接口——文章搜索适合这种周度、篇幅更长的
# 分析报告，快讯搜索适合开机率这种每日短讯)。
#
# ★实测确认过程：用户提供了4条真实内容样本，发现措辞比开机率那次多样得多——
#   "平均理论养殖亏损"/"养殖端理论亏损"/"全面亏损，平均理论亏损"/"平均理论
#   养殖盈利"这几种不同写法混杂出现，不是单一固定句式。正则没有照抄某一句
#   完整话术，改成更贴近核心的"盈利或亏损"紧跟"数字+元/只"这个模式——手算
#   验证过这个设计能正确跳过"全面亏损，"这种后面紧跟逗号、没有数字的
#   "假信号"，继续找到真正带数字的那一次"亏损"出现(比如"全面亏损，平均
#   理论亏损1.06元/只"这句里，"亏损"出现了两次，只有第二次后面直接跟着
#   数字，实测正则确实取到了第二次而不是被第一次干扰)。
#
# ★这个指标本身可能是负数(亏损)，跟开机率(恒为正的百分比)不同，正则设计
#   上要靠"盈利"/"亏损"这两个关键词本身来决定正负号，不能只提取数字本身。
#
# ★字段名不假设一定叫"content"——这次是"文章"搜索，字段结构未必跟"快讯"
#   搜索一样，扫描记录里所有字符串字段的值找匹配，而不是硬编一个字段名。
#
# ★真实运行中发现的第二种措辞变体(已修正)："本周毛鸡平均理论养殖盈利在
#   0.82元/只"——"盈利"和数字之间多了个"在"字，原本要求紧邻数字的正则
#   匹配不到。改成允许中间有0-2个"在/为/约"这类常见连接词字符，但不包含
#   标点符号——手算验证过这样既能覆盖新案例，又不会破坏"全面亏损，平均
#   理论亏损1.06元/只"这个陷阱案例的正确处理(逗号不在允许清单里，第一次
#   "亏损"依然会被正确跳过)。
MYSTEEL_ARTICLE_SEARCH_URL = "https://search.mysteel.com/searchapi/search/searchArticle"
MYSTEEL_POULTRY_PATTERN = re.compile(r"(盈利|亏损)[在为约]{0,2}(\d+\.?\d*)元/只")


NDRC_BASE = "https://www.jgjcndrc.org.cn"
NDRC_ENTRY_LIST = NDRC_BASE + "/list?clmId=1832298113994649601&sclmId=1836667772799598593"      # 父栏目页(已验证是服务器端渲染，导航里有'猪料、鸡料、蛋料比价信息'子栏目)
NDRC_TITLE_KEY = "猪料、鸡料、蛋料比价"


def _ndrc_num(s):
    """'2.2 5'(表格排版错误，中间有空格)、'-4.10'、'1.54' → float；读不出返回 None。"""
    try:
        return float(re.sub(r"\s+", "", str(s)))
    except (TypeError, ValueError):
        return None


def parse_ndrc_poultry(text):
    """从发改委价格监测中心×卓创资讯《猪料、鸡料、蛋料比价》周报的正文文字里取肉鸡部分。返回 (结果, 原因)。
    ★取**公布的预期盈利/亏损**，不自己重算：用 2.75×(鸡料比价-平衡点)×饲料价格 只做核对(formulaCheckOk/formulaCheckValue)——卓创转载页脚注把系数写成过2.5，官方页是2.75。
    ★只认'肉鸡养殖预期(盈利|亏损)'：同一篇里还有生猪('头均亏损')和蛋鸡('每只盈利/亏损')，不能误取。**亏损写成正数('预期亏损3.31元/只')，转成负值。**
    ★表格里偶有排版错误('本 周'、'2.2 5')，所以主要靠文字句子；表格只用来补肉鸡价/饲料价/平衡点，并且数字中间的空格会被去掉。"""
    if not text:
        return None, "没有文字可解析"
    t = str(text)
    m = re.search(r"肉鸡养殖预期\s*(盈利|亏损)\s*(?:为)?\s*(-?\d+(?:\.\d+)?)\s*元\s*/\s*只", t)
    if not m:
        return None, "没有找到'肉鸡养殖预期盈利/亏损 X元/只'这句话(只有生猪/蛋鸡的句子不算)"
    mag = float(m.group(2))
    value = round(-abs(mag) if m.group(1) == "亏损" else mag, 2)
    problem = _plausibility_problem("poultryProfit", value)
    if problem:
        return None, f"肉鸡预期盈利{value}{problem}"
    # 鸡料比价与环比：取离这句话最近的前面那一句'本周全国鸡料比价为X，环比…'
    head = t[:m.start()]
    ms = list(re.finditer(r"鸡料比价为\s*(\d+(?:\.\d+)?)\s*[，,]?\s*(?:环比\s*(上涨|下跌|持平)\s*(\d+(?:\.\d+)?)?\s*%?|与上周持平)", head))
    ratio, chg = None, None
    if ms:
        mm = ms[-1]
        ratio = float(mm.group(1))
        if mm.group(2) is None or mm.group(2) == "持平":
            chg = 0.0
        else:
            chg = round(float(mm.group(3)) * (1 if mm.group(2) == "上涨" else -1), 2)
    else:
        mr = list(re.finditer(r"鸡料比价为\s*(\d+(?:\.\d+)?)", head))
        if mr:
            ratio = float(mr[-1].group(1))
    if ratio is None:
        return None, "没有找到'鸡料比价为X'"
    problem = _plausibility_problem("chickenFeedRatio", ratio)
    if problem:
        return None, f"鸡料比价{ratio}{problem}"
    out = {"value": value, "ratio": ratio, "ratioChangePct": chg, "balance": None, "chickenPrice": None, "feedPrice": None, "weekLabel": None,
           "monitorDate": None, "publishDate": None, "formulaCheckOk": None, "formulaCheckValue": None}
    # 表格：'本周 7.04 3.12 2.26 2.08 1.54'(肉鸡价 饲料价 鸡料比价 平衡点 预期盈利)，容忍'本 周'和数字里的空格
    for tm in re.finditer(r"本\s*周\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\s*\.\s*\d+(?:\s\d+)?)?)\s+(-?\d+(?:\.\d+)?)\b", t):
        c, f, r_, b, p = (_ndrc_num(x) for x in tm.groups())
        if None in (c, f, r_, b, p):
            continue
        if abs(r_ - ratio) < 0.011 and abs(p - value) < 0.011 and 3 < c < 20 and 1 < f < 8:      # 必须与句子里的鸡料比价/预期盈利对得上，才认这一行(排除生猪/蛋鸡的表)
            out["chickenPrice"], out["feedPrice"], out["balance"] = c, f, b
            break
    if out["balance"] is not None and out["feedPrice"] is not None:
        chk = round(2.75 * (ratio - out["balance"]) * out["feedPrice"], 2)
        out["formulaCheckValue"] = chk
        out["formulaCheckOk"] = abs(chk - value) <= 0.06
    w = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*第\s*(\d)\s*周", t)
    if w:
        out["weekLabel"] = f"{w.group(1)}年{int(w.group(2))}月第{w.group(3)}周"
    pm = re.search(r"发布时间[：:]\s*(20\d{2})[/\-年](\d{1,2})[/\-月](\d{1,2})", t)
    if pm:
        try:
            out["publishDate"] = _date_cls(int(pm.group(1)), int(pm.group(2)), int(pm.group(3))).isoformat()
        except ValueError:
            pass
    # 肉鸡段自己的监测日期：'卓创资讯 2026年3月4日 全国肉鸡（活鸡）棚前收购价格…'
    dm = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(?:\*\*)?\s*全国肉鸡", t)
    if dm:
        try:
            out["monitorDate"] = _date_cls(int(dm.group(1)), int(dm.group(2)), int(dm.group(3))).isoformat()
        except ValueError:
            pass
    return out, None


def pick_ndrc_monitor_date(week_label, body_date, publish_date):
    """监测日期(周三)。正文里的日期偶有年份笔误(2023年9月第3周那篇正文写成了2024年9月18日)，所以要核对：
    年份必须与标题一致，且不晚于发布日、不早于发布日前14天；对不上就退到'发布日当天或之前最近的周三'。返回 (日期, 是否退回了)。"""
    ty = None
    mt = re.match(r"(20\d{2})", week_label or "")
    if mt:
        ty = int(mt.group(1))
    def last_wed(d):
        return d - timedelta(days=(d.weekday() - 2) % 7)
    if body_date is not None and (ty is None or body_date.year == ty):
        if publish_date is None or (body_date <= publish_date and (publish_date - body_date).days <= 14):
            return body_date, False
    if publish_date is not None:
        return last_wed(publish_date), True
    return None, True


def _ndrc_abs(base, href):
    href = html.unescape(href or "").strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http"):
        return href
    return urllib.parse.urljoin(base, href)


def find_ndrc_feed_ratio_list_url(page_html, base=NDRC_ENTRY_LIST):
    """从(父栏目)列表页的导航里找'猪料、鸡料、蛋料比价信息'子栏目的链接。找不到返回 None。"""
    for m in re.finditer(r'(?is)<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', page_html or ""):
        label = re.sub(r"(?s)<[^>]+>", "", m.group(2)).strip()
        if NDRC_TITLE_KEY in label and "比价信息" in label:
            return _ndrc_abs(base, m.group(1))
    return None


def extract_ndrc_article_links(page_html, base=NDRC_ENTRY_LIST):
    """列表页里所有标题含'猪料、鸡料、蛋料比价'的详情链接，按页面顺序。每项 {url,title,week,pageDate}。
    ★先找出所有 <a>，每个条目页面上的日期只在'这个 </a> 到下一个 <a>'之间的片段里找——不能用'</a>后面贪婪吞N个字符'的写法：
      那样第一个条目吞掉的字符会把下一个 <a> 整个吃掉，列表里就悄悄少了文章(测试发现：3篇只取到2篇)。"""
    h = page_html or ""
    anchors = list(re.finditer(r'(?is)<a\b[^>]*?href\s*=\s*["\']([^"\']*)["\'][^>]*>(.*?)</a>', h))
    out = []
    for k, m in enumerate(anchors):
        if "detail" not in m.group(1):
            continue
        title = re.sub(r"(?s)<[^>]+>", "", m.group(2)).strip()
        if NDRC_TITLE_KEY not in title:
            continue
        tail = h[m.end(): (anchors[k + 1].start() if k + 1 < len(anchors) else len(h))]
        w = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*第\s*(\d)\s*周", title)
        d = re.search(r"(20\d{2})-(\d{2})-(\d{2})", re.sub(r"(?s)<[^>]+>", " ", tail[:200]))
        out.append({"url": _ndrc_abs(base, m.group(1)), "title": title, "week": (f"{w.group(1)}年{int(w.group(2))}月第{w.group(3)}周" if w else None),
                    "pageDate": (d.group(0) if d else None)})
    return out


def find_ndrc_next_page(page_html, base):
    """列表页里文字为'下一页'的链接。没有返回 None。"""
    for m in re.finditer(r'(?is)<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', page_html or ""):
        if re.sub(r"(?s)<[^>]+>", "", m.group(2)).strip() == "下一页":
            return _ndrc_abs(base, m.group(1))
    return None


NDRC_STALE_DAYS = 21           # 周频数据：监测日距今超过这么多天标 stale(正常≤7~9天，节假日可能晚一周)
NDRC_LIVE_MAX_ARTICLES = 2     # 最新一篇解析不出时，最多退到前几篇


def _ndrc_get(fetch, url):
    """取一个页面。返回 (文本, 错误)；绝不抛异常。重试≤2次、超时≤15秒(每小时的线上抓取不能被拖慢)。"""
    try:
        raw, dbg = fetch(url, headers={"Referer": NDRC_BASE + "/"}, retries=2, timeout=15)
    except Exception as e:  # noqa: BLE001
        return None, f"请求异常: {type(e).__name__}: {e}"
    if not raw:
        return None, f"请求失败({(dbg or {}).get('error') or (dbg or {}).get('httpStatus') or '无返回'})"
    return raw, None


class NdrcHttpLister:
    """文章列表提供者(纯 HTTP 版)：父栏目页 → 子栏目链接 → 列表页 → 逐页'下一页'。
    ⚠️2026-10-08 实测：该站点服务器端渲染出来的列表永远是默认栏目(生猪出场价)，子栏目是点击后才加载的，所以这个版本在真实站点上取不到比价文章——
    保留它是因为：①页面以后若改成服务器端渲染它就能直接用；②测试里用它喂构造好的页面，验证下游(解析/选日期/回填)。线上默认用 ndrc_browser.SeleniumLister。"""

    def __init__(self, fetch=None):
        self.fetch = fetch or fetch_text_debug

    def list_articles(self, max_pages=1, resolve_limit=0, skip_weeks=()):
        out = {"links": [], "pages": 0, "noNext": False, "error": None, "debug": {"url": NDRC_ENTRY_LIST}}
        raw, err = _ndrc_get(self.fetch, NDRC_ENTRY_LIST)
        if err:
            out["error"] = f"发改委价格监测中心父栏目页取不到: {err}"
            return out
        sub = find_ndrc_feed_ratio_list_url(raw, NDRC_ENTRY_LIST)
        if not sub:
            out["error"] = "父栏目页里没有找到'猪料、鸡料、蛋料比价信息'子栏目链接(页面可能改版)"
            out["debug"]["htmlHead"] = raw[:300]
            return out
        url, seen, html_ = sub, set(), ""
        while url and out["pages"] < max_pages:
            html_, err = _ndrc_get(self.fetch, url)
            if err:
                out["error"] = out["error"] or f"子栏目列表页取不到: {err}"
                break
            out["pages"] += 1
            for ln in extract_ndrc_article_links(html_, url):
                if ln["url"] not in seen:
                    seen.add(ln["url"])
                    out["links"].append(ln)
            nxt = find_ndrc_next_page(html_, url)
            if not nxt:
                out["noNext"] = True
                break
            url = nxt if nxt != sub else None
        if not out["links"] and not out["error"]:
            out["error"] = "子栏目列表里没有文章链接(标题含'猪料、鸡料、蛋料比价')，页面可能改版或列表改成了前端渲染"
            out["debug"]["htmlHead"] = html_[:300]
        return out

    def page_html(self, url):
        return _ndrc_get(self.fetch, url)

    def close(self):
        pass


def default_ndrc_lister(total_timeout_s=90):
    """线上默认：Selenium 无头 Chrome(只用来拿文章列表；详情页仍走纯 HTTP)。线上每小时抓取 90 秒总时限；回填会给更长的。"""
    import ndrc_browser
    return ndrc_browser.SeleniumLister(total_timeout_s=total_timeout_s)


def fetch_ndrc_poultry(now_bj=None, fetch=None, max_articles=NDRC_LIVE_MAX_ARTICLES, lister=None):
    """肉鸡养殖预期盈利(元/只)：国家发改委价格监测中心×卓创资讯《猪料、鸡料、蛋料比价》周报。
    列表靠 Selenium(lister)：站点的子栏目列表是点击后才加载的，纯 HTTP 拿不到；详情页是服务器端渲染，纯 HTTP 读(失败时才退回用浏览器读)。
    流程：浏览器取列表(最新在前) → 最新一篇(解析不出就退到前一篇，最多 max_articles 篇) → 解析。每一环失败都写明是哪一环，绝不抛异常，浏览器一定关掉。
    ★与 Mysteel 的'白羽肉鸡养殖利润'不是同一个定义：这是发改委按成本模型推算的'未来肉鸡养殖预期盈利'(=2.75×(鸡料比价-平衡点)×饲料价格)，取公布的数字。"""
    if now_bj is None:
        now_bj = (datetime.now(timezone.utc) + timedelta(hours=8)).replace(tzinfo=None)
    fetch = fetch or fetch_text_debug
    try:
        lister = lister or default_ndrc_lister()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"浏览器模块加载失败: {type(e).__name__}: {str(e)[:120]}", "debug": {}}
    try:
        lst = lister.list_articles(max_pages=1)
        links = lst.get("links") or []
        if lst.get("error") and not links:
            return {"available": False, "reason": f"发改委文章列表取不到: {lst['error']}", "debug": lst.get("debug") or {}}
        if not links:
            return {"available": False, "reason": "子栏目列表里没有文章链接", "debug": lst.get("debug") or {}}
        attempted = []
        for k, ln in enumerate(links[:max_articles]):
            raw3, err = (ln["html"], None) if ln.get("html") else _ndrc_get(fetch, ln["url"])
            if err:
                raw3, err2 = lister.page_html(ln["url"])
                if err2:
                    attempted.append(f"{ln['title']}: 详情页取不到: {err}；浏览器也取不到: {err2}")
                    continue
            parsed, why = parse_ndrc_poultry(_html_to_text(raw3))
            if parsed is None:
                attempted.append(f"{ln['title']}: {why}")
                continue
            pub = None
            if parsed.get("publishDate"):
                pub = _date_cls.fromisoformat(parsed["publishDate"])
            elif ln.get("pageDate"):
                pub = _date_cls.fromisoformat(ln["pageDate"])
            body = _date_cls.fromisoformat(parsed["monitorDate"]) if parsed.get("monitorDate") else None
            d, fb = pick_ndrc_monitor_date(parsed.get("weekLabel") or ln.get("week"), body, pub)
            if d is None:
                attempted.append(f"{ln['title']}: 正文和页面都没有可用的日期")
                continue
            age = (now_bj.date() - d).days
            return {"available": True, "value": parsed["value"], "date": d.isoformat(), "ratio": parsed["ratio"], "ratioChangePct": parsed["ratioChangePct"], "balance": parsed["balance"],
                    "chickenPrice": parsed["chickenPrice"], "feedPrice": parsed["feedPrice"], "weekLabel": parsed["weekLabel"] or ln.get("week"), "publishDate": parsed.get("publishDate"),
                    "formulaCheckOk": parsed["formulaCheckOk"], "formulaCheckValue": parsed["formulaCheckValue"], "dateFallback": fb, "usedFallback": k > 0, "fallbackWeeks": k,
                    "ageDays": age, "stale": age > NDRC_STALE_DAYS, "source": "国家发改委价格监测中心×卓创资讯《猪料、鸡料、蛋料比价》(未来肉鸡养殖预期盈利)", "sourceUrl": ln["url"],
                    "definition": "发改委按成本模型推算的未来肉鸡养殖预期盈利=2.75×(鸡料比价-平衡点)×饲料价格，不是Mysteel的白羽肉鸡养殖利润"}
        last = attempted[-1].split(": ", 1)[-1] if attempted else ""
        return {"available": False, "reason": f"最新{min(len(links), max_articles)}篇周报都没取到肉鸡预期盈利(最后一篇：{last})", "debug": {"attempted": attempted}}
    except Exception as e:  # noqa: BLE001 - 任何意外都只影响这一个指标
        return {"available": False, "reason": f"发改委抓取出现意外: {type(e).__name__}: {str(e)[:150]}", "debug": {}}
    finally:
        try:
            lister.close()
        except Exception:  # noqa: BLE001
            pass


def fetch_mysteel_poultry_profit():
    """通过Mysteel文章搜索"白羽肉鸡养殖利润"这个关键词，从最新一条能匹配
    "盈利/亏损...元/只"这个模式的文章里，提取数值(盈利为正、亏损为负)。"""
    now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
    start_bj = now_bj - timedelta(days=21)  # 这是周度指标(不是每天发布)，回看窗口比开机率那次宽一些
    payload = {
        "query": "白羽肉鸡养殖利润",
        "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
        "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"),
        "sortType": "complex",
        "platform": "pc",
        "pageNo": 1,
        "pageSize": 20,
    }
    headers = {
        "token": "-1",
        "Origin": "https://search.mysteel.com",
        "Referer": "https://search.mysteel.com/fastcomment.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    data, debug = fetch_json_debug(MYSTEEL_ARTICLE_SEARCH_URL, headers=headers, post_data=payload)

    if data is None:
        return {"available": False, "reason": "Mysteel文章搜索接口无返回数据", "debug": debug}
    if not isinstance(data, dict) or data.get("resultCode") != 0:
        return {
            "available": False,
            "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
            "debug": {"rawSnippet": debug.get("rawSnippet")},
        }

    data_list = data.get("dataList") or []
    if not data_list:
        return {"available": False, "reason": "搜索结果为空(最近21天内没有匹配的文章)", "debug": {"total": data.get("total")}}

    rejected = []
    for item in data_list:
        if not isinstance(item, dict):
            continue
        for v in item.values():
            if not isinstance(v, str):
                continue
            for m in MYSTEEL_POULTRY_PATTERN.finditer(v):
                sign = 1 if m.group(1) == "盈利" else -1
                value = round(sign * float(m.group(2)), 2)
                problem = _plausibility_problem("poultryProfit", value)
                if problem:
                    rejected.append(problem)
                    continue
                return {
                    "available": True,
                    "value": value,
                    "date": item.get("publishTime", "")[:10],
                    "matchedText": v,
                    "source": "Mysteel文章(白羽肉鸡养殖利润)",
                    "sourceUrl": "https://search.mysteel.com/fastcomment.html",
                }

    if rejected:
        return {"available": False, "reason": f"提取到的养殖利润数值都不合理，已丢弃: {'; '.join(rejected[:3])}",
                "debug": {"rejectedImplausible": rejected[:10], "firstItemSample": data_list[0]}}
    return {
        "available": False,
        "reason": "搜索结果里没有一条能提取出'盈利/亏损XX元/只'这个格式(可能措辞变了)",
        "debug": {"firstItemSample": data_list[0], "totalItemsChecked": len(data_list)},
    }


# ---------------------------------------------------------------------------
# 豆菜粕价差：同样改自动抓取(Mysteel文章搜索)，但这次比开机率/养殖利润都
# 麻烦——用户提供的7条真实内容样本里，出现了两种完全不同的表述格式：
#
#   格式A(6条，多数情况)："区间"格式：豆菜粕现货价差本身是一个区间，比如
#   "价差在490-540元/吨"——取这个区间的中点(均值)当代表值。
#   ★这种格式还有个坑：同一句话里经常会**同时**出现两个"数字-数字元/吨"
#   模式——一个是价差本身的区间(我要的)，另一个是"较前一日涨/跌XX-YY元/吨"
#   这种当日变动幅度的区间(我不要的)。正则锚定在"价差"这个词后面紧跟
#   (允许少量连接字符)的第一个区间，不是全文里随便抓一个区间——手算验证过
#   6条真实样本全部正确抓到"价差"本身的区间，没有被"涨跌XX-YY元/吨"这种
#   变动幅度干扰。
#
#   格式B(1条，8月28日那条)："分城市单值"格式：不是一个统一区间，而是列出
#   多个城市各自的价差单值，比如"广东地区...价差740元/吨；广西地区...
#   价差710元/吨；南通地区...价差810元/吨"——这种情况下取全部城市数值的
#   算术平均。
#
# ★两种格式的正则设计上互斥，不会交叉误判：格式A要求价差后面是"数字-数字"
#   (带横线)，格式B要求价差后面直接是单个数字(不带横线)——手算验证过格式A
#   的正则对格式B样本完全匹配不到(因为没有横线区间)，格式B的正则对格式A
#   样本也完全匹配不到(因为"价差"后面紧跟的不是数字，是"下跌，区间为"这类
#   连接文字)。处理顺序上先试格式A(更常见)，格式A没匹配到才试格式B。
MYSTEEL_RMSPREAD_RANGE_PATTERN = re.compile(r"价差.{0,8}?(\d+)-(\d+)元/吨")
MYSTEEL_RMSPREAD_SINGLE_PATTERN = re.compile(r"价差(\d+)元/吨")


def parse_rmspread(text):
    """从一段文字(搜索摘要)里提取豆菜粕价差。返回 (结果, rejected)：结果 None 或 {value, fmt, ...}。
    取值规则(v101.4统一，线上抓取和回填共用)：
      ①文字里有≥2个城市的价差单值("广东价差800元/吨")→取这些单值的平均，fmt='cities'；
      ②否则有区间("价差在420-600元/吨之间")→取区间中点，fmt='range'；
      ③否则只有1个单值→取该单值，fmt='single'(沿用原来线上的行为)。
    为什么城市平均优先：同一篇文章常同时有"各城市单值"和一句概括"各区域价差在700-900元/吨区间"。原来区间优先，会因为概括句写"700-900"(短横线)
    还是"720至920"(至字)而取到不同的值——重叠的4篇上两种取法相差 +5/+33/-5/+37(约±5%)，是偶然因素。
    离谱的值(超出100~3000，如"较前一日跌10-20元/吨"的中点15)单独丢掉，原因记在 rejected 里，不拉偏平均。"""
    rejected, singles, rng = [], [], None
    for x in MYSTEEL_RMSPREAD_SINGLE_PATTERN.findall(text or ""):
        problem = _plausibility_problem("rmSpread", float(x))
        if problem:
            rejected.append(problem)
        else:
            singles.append(float(x))
    for m in MYSTEEL_RMSPREAD_RANGE_PATTERN.finditer(text or ""):
        low, high = float(m.group(1)), float(m.group(2))
        mid = round((low + high) / 2, 1)
        problem = f"区间{low:g}-{high:g}上下限颠倒" if low > high else _plausibility_problem("rmSpread", mid)
        if problem:
            rejected.append(problem)
            continue
        rng = {"value": mid, "fmt": "range", "low": low, "high": high}
        break
    if len(singles) >= 2:
        return {"value": round(sum(singles) / len(singles), 1), "fmt": "cities", "samples": singles}, rejected
    if rng:
        return rng, rejected
    if singles:
        return {"value": round(singles[0], 1), "fmt": "single", "samples": singles}, rejected
    return None, rejected


def fetch_mysteel_rmspread():
    """通过Mysteel文章搜索"豆菜粕价差"这个关键词，从最新一条能提取出价差
    数值的文章里提取(格式A的区间取中点，格式B的多城市单值取平均)。"""
    now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
    start_bj = now_bj - timedelta(days=7)  # 这是日度/准日度指标，回看窗口不用太宽
    payload = {
        "query": "豆菜粕价差",
        "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
        "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"),
        "sortType": "complex",
        "platform": "pc",
        "pageNo": 1,
        "pageSize": 20,
    }
    headers = {
        "token": "-1",
        "Origin": "https://search.mysteel.com",
        "Referer": "https://search.mysteel.com/fastcomment.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    data, debug = fetch_json_debug(MYSTEEL_ARTICLE_SEARCH_URL, headers=headers, post_data=payload)

    if data is None:
        return {"available": False, "reason": "Mysteel文章搜索接口无返回数据", "debug": debug}
    if not isinstance(data, dict) or data.get("resultCode") != 0:
        return {
            "available": False,
            "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
            "debug": {"rawSnippet": debug.get("rawSnippet")},
        }

    data_list = data.get("dataList") or []
    if not data_list:
        return {"available": False, "reason": "搜索结果为空(最近7天内没有匹配的文章)", "debug": {"total": data.get("total")}}

    rejected = []
    for item in data_list:
        if not isinstance(item, dict):
            continue
        for v in item.values():
            if not isinstance(v, str):
                continue
            res, rej = parse_rmspread(v)
            rejected += rej
            if res:
                out = {"available": True, "value": res["value"], "date": item.get("publishTime", "")[:10], "matchedText": v,
                       "source": "Mysteel文章(豆菜粕价差)", "sourceUrl": "https://search.mysteel.com/fastcomment.html"}
                if res["fmt"] == "range":
                    out.update({"rangeLow": res["low"], "rangeHigh": res["high"], "formatUsed": "区间中点"})
                else:
                    out.update({"citySamples": res["samples"], "formatUsed": "多城市单值平均"})
                return out

    if rejected:
        return {"available": False, "reason": f"提取到的价差数值都不合理，已丢弃: {'; '.join(rejected[:3])}",
                "debug": {"rejectedImplausible": rejected[:10], "firstItemSample": data_list[0]}}
    return {
        "available": False,
        "reason": "搜索结果里没有一条能提取出价差数值(区间格式或多城市单值格式都没匹配到，可能措辞变了)",
        "debug": {"firstItemSample": data_list[0], "totalItemsChecked": len(data_list)},
    }


# ---------------------------------------------------------------------------
# 到港预报：同样改自动抓取(Mysteel文章搜索)。
#
# ★这项在设计上跟前三项(开机率/养殖利润/价差)不一样，值得专门说明：
#   用户提出了一个重要问题——到港预报一般在月底那一周发布，预测的是"下个月"
#   (偶尔是未来3个月)，不是"当月"。实测查证了用户提供的6条真实样本，发现：
#     ① 6条里只有1条(预测7/8/9三个月的那条)是"未来3个月"格式，其余5条都
#        只预测下一个月——这个"3个月"格式并不常见，而且原文自己就说"远月
#        到港数据仍存修正可能"，连数据来源自己都不认为远月数字够可靠。
#     ② 基于此，没有做成3个固定指标(下月/下2月/下3月)——后两个大概率经常
#        是空的，而且就算有数据，可靠性也存疑，硬做成3个评分指标等于把
#        噪音引入综合评分。
#     ③ 改成一个指标，但不再简单假设"抓到的数字就是本月"——而是把"具体是
#        哪一年哪个月"和"多少万吨"一起提取出来，前端老实展示"这是X月的
#        到港预报"，不管什么时候看仪表盘都清楚这个数字对应哪个月，不会被
#        误导成"当月"。
#
# ★原始文本目前已知有三种不同的措辞风格(手算验证过全部7条真实样本，
#   含GitHub Actions真实运行后新发现的第三种)：
#   ①"YYYY年M月份...到港...共计约XXX万吨"(5条)
#   ②"YYYY年M月...到港量预计达XXX万吨"(1条，预测未来3个月那条，只取最近月)
#   ③"YYYY年M月...到港约XXX万吨"(1条，真实运行后新发现——"月"后面没有"份"字，
#     "到港"和数字之间只有一个"约"字，原本要求"共计约"或"预计达"这种具体
#     连接词的正则完全对不上这种更简短的写法)
#   一开始用两个各自死板的正则(要求具体连接词"共计约"/"预计达")去应对①②，
#   真实运行后③直接把两个正则都打穿了——教训是穷举具体连接词这种做法太脆弱，
#   连接词的变体没法预先枚举完。改成更宽松的策略：不再尝试猜"到港"和数字
#   之间具体是哪几个字，而是限定一个合理的字符数上限(15个)，中间随便是什么
#   字都行，只要在这个范围内找到"数字+万吨"就算数——手算验证过这样反而更
#   稳健，全部7条真实样本(3种措辞风格)都能正确提取，且限定了长度上限，
#   不会跳到句子里更远处的其他数字(比如分区域细分数据、或者后续月份的数字)。
MYSTEEL_ARRIVAL_PATTERN = re.compile(r"(\d{4})年(\d{1,2})月份?.{0,20}?到港(.{0,15}?)(\d+\.?\d*)万吨")


def fetch_mysteel_arrival_forecast():
    """通过Mysteel文章搜索"大豆到港预报"这个关键词，从最新一条能提取出
    "哪年哪月+多少万吨"的文章里提取(标准格式优先，级联格式兜底)。"""
    now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
    start_bj = now_bj - timedelta(days=35)  # 这是月度指标，回看窗口给足一个月以上
    payload = {
        "query": "大豆到港预报",
        "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
        "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"),
        "sortType": "complex",
        "platform": "pc",
        "pageNo": 1,
        "pageSize": 20,
    }
    headers = {
        "token": "-1",
        "Origin": "https://search.mysteel.com",
        "Referer": "https://search.mysteel.com/fastcomment.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    data, debug = fetch_json_debug(MYSTEEL_ARTICLE_SEARCH_URL, headers=headers, post_data=payload)

    if data is None:
        return {"available": False, "reason": "Mysteel文章搜索接口无返回数据", "debug": debug}
    if not isinstance(data, dict) or data.get("resultCode") != 0:
        return {
            "available": False,
            "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
            "debug": {"rawSnippet": debug.get("rawSnippet")},
        }

    data_list = data.get("dataList") or []
    if not data_list:
        return {"available": False, "reason": "搜索结果为空(最近35天内没有匹配的文章)", "debug": {"total": data.get("total")}}

    rejected = []
    for item in data_list:
        if not isinstance(item, dict):
            continue
        for v in item.values():
            if not isinstance(v, str):
                continue
            for m in MYSTEEL_ARRIVAL_PATTERN.finditer(v):
                value = float(m.group(4))
                problem = "到港后面是变动量(较上月增减)，不是到港总量" if _looks_like_change(m.group(3)) else _plausibility_problem("arrivalForecast", value)
                if problem:
                    rejected.append(problem)
                    continue
                return {
                    "available": True,
                    "forecastYear": int(m.group(1)),
                    "forecastMonth": int(m.group(2)),
                    "value": value,
                    "date": item.get("publishTime", "")[:10],
                    "matchedText": v,
                    "source": "Mysteel文章(大豆到港预报)",
                    "sourceUrl": "https://search.mysteel.com/fastcomment.html",
                }

    if rejected:
        return {"available": False, "reason": f"提取到的到港数值都不合理，已丢弃: {'; '.join(rejected[:3])}",
                "debug": {"rejectedImplausible": rejected[:10], "firstItemSample": data_list[0]}}
    return {
        "available": False,
        "reason": "搜索结果里没有一条能提取出'哪年哪月+多少万吨'这个格式(可能措辞变了)",
        "debug": {"firstItemSample": data_list[0], "totalItemsChecked": len(data_list)},
    }


# ---------------------------------------------------------------------------
# 豆粕商业库存：同样改自动抓取(Mysteel文章搜索)。
#
# ★这次直接吸取到港预报那次的教训，从一开始就不去穷举"库存"和数字之间
#   具体是"为"、"约"、"达到"哪个连接词——到港预报那次因为死板要求"共计约"
#   或"预计达"这种具体连接词，被第三种真实写法("到港约XXX万吨")直接打穿，
#   这次直接用"限定字符数上限、中间随便什么词都行"这个更宽松的策略，
#   一步到位：库存后面允许最多10个任意字符，只要在这个范围内找到数字+万吨
#   就算数。手算验证过多种常见写法("库存约XX万吨"/"库存为XX万吨"/"库存
#   达到XX万吨"/"库存XX万吨"不带任何连接词)都能正确匹配，且"库存"这个词
#   在原文里通常只出现一次(库存数值本身)，不会被"较上周增加XX万吨"这种
#   变动幅度数字干扰(那句前面没有"库存"这个词紧邻)。
#
# ★真实运行暴露的bug(已修复)：查询关键词原本用的是"豆粕商业库存"，但
#   真实运行时搜索结果是total:0(完全没有匹配的文章)——用户贴出了真实存在
#   的相关文章("Mysteel数据：全国主要区域大豆及豆粕库存统计")，内容里
#   写的是"豆粕库存117.32万吨"，从头到尾都没有出现"商业"这两个字。问题
#   出在搜索关键词本身，不是正则(正则的(?:商业)?本来就设计成可选，这部分
#   没问题，问题是连"搜索"这一步都因为关键词里多了"商业"这两个字而找不到
#   任何文章)。已经把查询关键词改成"豆粕库存"(跟Mysteel文章实际用词一致)。
MYSTEEL_MEAL_STOCK_PATTERN = re.compile(r"豆粕(?:商业)?库存(.{0,10}?)(\d+\.?\d*)万吨")


# ★第三版(用户改了搜索关键词)：查询词改成"全国主要区域大豆"——搜出来的是Mysteel每周一期的
#   "全国主要区域大豆及豆粕库存统计"(例如2026-09-21那篇："2026年第38周全国主要油厂大豆库存
#   上升，豆粕库存上升…其中大豆库存856.85万吨…豆粕库存117.32万吨，较上周增加6.33万吨")，
#   比原来用"豆粕库存"搜到各种零散文章准确。用户抓包的请求：startTime=2025-09-28、
#   endTime=2026-09-28(一年窗口)、pageNo=1、pageSize=20、platform=pc、sortType=complex。
#
# ★一年窗口会搜出几十篇每周一期的文章，而排序是按相关度(complex)不是按时间——如果还像
#   旧版那样"取第一个匹配"，很可能取到去年10月的旧一期。所以：①翻页收齐(最多5页)；②所有
#   文章里提取到的库存都收集起来，按**发布日期取最新的一篇**；③新鲜度限制：周度数据，
#   最新一期距今超过21天就拒绝(宁可显示失败也不显示旧数据)——跟能繁母猪存栏那次同样的教训。
#
# ★这篇文章里同一句话同时有"大豆库存856.85万吨""豆粕库存117.32万吨""未执行合同459.91万吨"
#   "豆粕表观消费量178.08万吨"四个数，取错一个就是错的：①"豆粕库存"和数字之间出现大豆/菜粕/
#   未执行合同等别的指标名就拒绝(防止"豆粕库存上升，大豆库存856.85万吨"取到大豆库存)；②间隔里
#   出现较/比/增/减等词是变动量，拒绝(0.7万吨那次的教训)；③"豆粕库存"前面是华东/山东/沿海等
#   地区名，是区域数据不是全国库存，拒绝；④整篇文章(标题或正文)必须出现"全国"字样；⑤数值
#   要在合理范围内(10~600万吨)。
MEAL_STOCK_MAX_AGE_DAYS = 21
_MEAL_REGION_WORDS = ("华东", "华南", "华北", "华中", "东北", "西南", "西北", "山东", "广东", "广西", "江苏", "沿海", "沿江")
_MEAL_OTHER_SUBJECTS = ("大豆", "菜粕", "未执行合同", "表观消费", "压榨", "进口")
_MEAL_WEEK_RE = re.compile(r"(\d{4})年第(\d{1,2})周")


def _extract_meal_stock_values(text):
    """从一段文本里提取"豆粕库存XX万吨"，返回(合格数值列表, 被丢弃的说明列表)。"""
    good, rejected = [], []
    for m in MYSTEEL_MEAL_STOCK_PATTERN.finditer(text):
        gap, value = m.group(1), float(m.group(2))
        before = text[max(0, m.start() - 6):m.start()]
        if any(w in before for w in _MEAL_REGION_WORDS):
            rejected.append(f"{value:g}万吨: 前面是地区名，是区域数据不是全国库存")
        elif any(w in gap for w in _MEAL_OTHER_SUBJECTS):
            rejected.append(f"{value:g}万吨: 间隔里出现别的指标名(大豆/合同等)，可能不是豆粕库存")
        elif _looks_like_change(gap):
            rejected.append(f"{value:g}万吨: 库存后面是变动量(较上周增减)，不是库存量")
        else:
            problem = _plausibility_problem("mealStock", value)
            if problem:
                rejected.append(problem)
            else:
                good.append(value)
    return good, rejected


def fetch_mysteel_meal_stock(today=None):
    """通过Mysteel文章搜索"全国主要区域大豆"(每周一期的全国大豆及豆粕库存统计)，翻页收齐后
    取发布日期最新的一篇里的豆粕库存(万吨)。today参数只给测试用。"""
    if today is None:
        now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
        today = now_bj.date()
    else:
        now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    start_bj = now_bj - timedelta(days=365)  # 跟用户抓包验证过的请求一致(一年窗口)
    headers = {
        "token": "-1",
        "Origin": "https://search.mysteel.com",
        "Referer": "https://search.mysteel.com/fastcomment.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    page_size, max_pages = 20, 5
    candidates = []  # (发布日期, 库存, item)
    rejected_all = []
    items_checked = 0
    first_item = None

    for page in range(1, max_pages + 1):
        payload = {
            "query": "全国主要区域大豆",
            "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
            "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"),
            "sortType": "complex",
            "platform": "pc",
            "pageNo": page,
            "pageSize": page_size,
        }
        data, debug = fetch_json_debug(MYSTEEL_ARTICLE_SEARCH_URL, headers=headers, post_data=payload)
        if data is None or not isinstance(data, dict) or data.get("resultCode") != 0:
            if page == 1:
                if data is None:
                    return {"available": False, "reason": "Mysteel文章搜索接口无返回数据", "debug": debug}
                return {"available": False,
                        "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
                        "debug": {"rawSnippet": debug.get("rawSnippet")}}
            break  # 后面的页失败：用已经拿到的
        data_list = data.get("dataList") or []
        if page == 1 and not data_list:
            return {"available": False, "reason": "搜索结果为空(最近一年内没有匹配的文章)", "debug": {"total": data.get("total")}}
        for item in data_list:
            if not isinstance(item, dict):
                continue
            items_checked += 1
            if first_item is None:
                first_item = item
            try:
                pub_date = datetime.strptime(str(item.get("publishTime", ""))[:10], "%Y-%m-%d").date()
            except ValueError:
                continue  # 没有发布日期就没法判断新鲜度，跳过
            title, content = str(item.get("title") or ""), str(item.get("content") or "")
            national = "全国" in title or "全国" in content
            for text in (content, title):
                good, rejected = _extract_meal_stock_values(text)
                rejected_all.extend(rejected)
                if good and not national:
                    rejected_all.append(f"{good[0]:g}万吨: 文章标题和正文都没有'全国'字样，不确认是全国口径")
                elif good:
                    candidates.append((pub_date, good[0], item))
                    break  # 一篇文章只取一个库存值
        total = data.get("total") or 0
        if len(data_list) < page_size or page * page_size >= total:
            break

    if not candidates:
        if rejected_all:
            return {"available": False, "reason": f"提取到的库存数值都不合理，已丢弃: {'; '.join(rejected_all[:3])}",
                    "debug": {"rejectedImplausible": rejected_all[:10], "itemsChecked": items_checked, "firstItemSample": first_item}}
        return {"available": False,
                "reason": "搜索结果里没有一条能提取出'豆粕库存XX万吨'这个格式(可能措辞变了)",
                "debug": {"itemsChecked": items_checked, "firstItemSample": first_item}}

    pub_date, value, item = max(candidates, key=lambda c: c[0])
    age = (today - pub_date).days
    if age > MEAL_STOCK_MAX_AGE_DAYS:
        return {"available": False,
                "reason": f"只找到了{age}天前({pub_date.isoformat()})的库存数据，超过{MEAL_STOCK_MAX_AGE_DAYS}天的新鲜度限制，为避免把旧数据当成最新值，不采用",
                "debug": {"latestArticleDate": pub_date.isoformat(), "latestValue": value, "candidates": len(candidates), "itemsChecked": items_checked}}
    wm = _MEAL_WEEK_RE.search(str(item.get("content") or "") + str(item.get("title") or ""))
    # ★搜索窗口里所有能提取出数字的周(不只是最新一周)，交给历史序列累积：回填时Mysteel周报大多补不全，
    #   靠每次抓取顺带把窗口里已有的周补齐，缺的周从此不再缺。同一发布日期只留一条，最多60周。
    seen_days, recent = set(), []
    for c_pub, c_val, c_item in sorted(candidates, key=lambda c: c[0], reverse=True):
        if c_pub in seen_days:
            continue
        seen_days.add(c_pub)
        cwm = _MEAL_WEEK_RE.search(str(c_item.get("content") or "") + str(c_item.get("title") or ""))
        recent.append({"date": c_pub.isoformat(), "value": c_val,
                       "week": f"{cwm.group(1)}年第{int(cwm.group(2))}周" if cwm else None})
        if len(recent) >= 60:
            break
    return {
        "available": True,
        "value": value,
        "date": pub_date.isoformat(),
        "recentWeeks": recent,
        "weekLabel": f"{wm.group(1)}年第{int(wm.group(2))}周" if wm else None,
        "articleTitle": item.get("title"),
        "source": "Mysteel文章(全国主要区域大豆及豆粕库存统计)",
        "sourceUrl": item.get("url") or "https://search.mysteel.com/fastcomment.html",
    }



# ---------------------------------------------------------------------------
# 国内豆粕库存消费比(库消比)：Mysteel每月一篇《全国豆粕供需平衡表》。
#
# ★为什么要做：美豆库存消费比反映中长期的顶和底，国内豆粕库消比更能反映国内期货的中短期状态。
# ★口径(用文章里的数字手算核对过，不是猜的)：库消比 = 月末库存 ÷ 当月消费量(月度，不是年度)。
#     5月 40÷673=5.94%、1月 90÷722=12.47%(文中12.45%)、12月 117÷716=16.34%(文中16.30%)。
#     这跟已有的"豆粕商业库存"是同一份数据的两种口径(库存是分子)，评分里不能并列投票，见前端合并规则。
#
# ★数据结构的三个坑(用户抓包+我抓过一篇正文核实的)：
#   ① 搜索接口的content只是摘要：12篇里约1/3的摘要没有具体数字(比如"库消比仍处高位")，
#      数字在正文里 → 要再GET文章url取正文。匿名访问时正文只到第2个月就截断(写到"10月产量大幅收缩"
#      就没了)，刚好够用(当月+下月)。但这是开发环境的访问结果，GitHub Actions那边可能被拦或页面变了，
#      所以抓取正文失败时要退回摘要，摘要也不行再退回"周度库存÷当月消费"，都不行就不可用。
#   ② 文章标题的月份不可靠(2025年10-12月的文章，标题写的是下一个月)，所以不看标题，只看正文里的月份。
#   ③ 摘要措辞五花八门："库消比从10.06%升至15.27%"(多月区间)、"库消比处于10.3%至10.5%"(区间)、
#      "库消比达15%"(整数)、"期初库存仅43万吨...库存一度降至30万吨以下"(月中低点，不是月末)。
#      → 只认单月记录里明示的单个库消比；区间/多月一律不采用；库存数字要跟库消比自洽才采用。
# ---------------------------------------------------------------------------
MEAL_BALANCE_QUERY = "全国豆粕供需平衡表"
MEAL_BALANCE_TITLE_KEY = "豆粕供需平衡表"       # 标题必须含这个，排除"Mysteel半年报"这类不是平衡表的文章
MEAL_BALANCE_MAX_ARTICLE_AGE_DAYS = 45          # 每月月底发一篇，超过45天没有新的就说明可能停更
MEAL_BALANCE_BODY_FETCH_LIMIT = 2               # 只取最新2篇的正文，避免频繁请求触发反爬
MEAL_MONTHLY_CONSUMPTION_RANGE = (300.0, 1200.0)  # 月消费量(万吨)合理范围(实测570~800)
MEAL_STU_CONSISTENCY_TOL = 0.6                  # 库存÷消费 与 文中库消比 相差超过0.6个百分点，认为库存数字不是月末值，丢弃

# 月份标记：先匹配"区间"(3月至6月 / 8-11月 / 2025年12月至2026年3月)，再匹配单月。区间整体跳过。
_MB_MONTH_TOKEN = re.compile(
    r"(?P<range>(?:\d{4}年)?\d{1,2}月?\s*[-—–至到]\s*(?:\d{4}年)?\d{1,2}月)"
    r"|(?<![较比自从至到])(?:(?P<year>\d{4})年)?(?P<month>\d{1,2})月(?![份]?[0-9])"
)
_MB_PRODUCTION_RE = re.compile(r"产量[^0-9。；;]{0,8}?(\d+\.?\d*)万吨")
_MB_CONSUMPTION_RE = re.compile(r"消费(?:量)?[^0-9。；;]{0,8}?(\d+\.?\d*)万吨")
_MB_STOCK_RE = re.compile(r"(?<!期初)库存[^0-9。；;]{0,10}?(\d+\.?\d*)万吨")
# ★库消比的叫法：近12个月的文章都写"库消比"；更早的文章(2024-05~2025-09)回填时全部给不出数，怀疑叫法不同，
#   先兼容几种常见写法(库存消费比/库存消耗比/库销比)。这是猜测，回填报告里会带上给不出数的月份的原文片段来验证。
_MB_STU_RE = re.compile(r"(?:库消比|库存消费比|库存消耗比|库销比)[^0-9。；;]{0,8}?(\d+\.?\d*)%(?!\s*[-—–至到~]\s*\d)")   # 后面紧跟"-16%"/"至10.5%"的是区间，不取
_MB_STU_ANY_RE = re.compile(r"库消比")


def _nearest_year_for_month(month, pub_date):
    """文章里只写"12月"没写年份时，取离发布日期最近的那个年份(1月4日发布的文章里的12月是上一年)。"""
    best = None
    for y in (pub_date.year - 1, pub_date.year, pub_date.year + 1):
        diff = abs((y * 12 + month) - (pub_date.year * 12 + pub_date.month))
        if best is None or diff < best[0]:
            best = (diff, y)
    return best[1]


def _parse_meal_balance_text(text, pub_date, keep_text=False):
    """从一段文字(正文或摘要)里解析出"单月"记录：{(年,月): {production, consumption, stock, stu, stuSource}}。
    只处理单月片段；"8-11月""3月至6月"这种区间片段整体跳过(区间里的数字没法对应到具体某个月)。
    keep_text=True时，每条记录额外带上seg(该月片段原文前200字)，仅用于回填诊断，正常抓取不用。"""
    text = re.sub(r"\s+", "", str(text or ""))
    tokens = list(_MB_MONTH_TOKEN.finditer(text))
    records = {}
    for i, m in enumerate(tokens):
        if m.group("range"):
            continue
        month = int(m.group("month"))
        if not 1 <= month <= 12:
            continue
        year = int(m.group("year")) if m.group("year") else _nearest_year_for_month(month, pub_date)
        # 片段=这个月份标记到下一个"不同月份"标记之前。同一个月连续出现("5月，...5月中旬...")合并成一段。
        end = len(text)
        for nxt in tokens[i + 1:]:
            if nxt.group("range") or (int(nxt.group("month")) != month):
                end = nxt.start()
                break
        seg = text[m.end():end]
        rec = records.setdefault((year, month), {"production": None, "consumption": None, "stock": None, "stu": None, "stuStated": False})
        if keep_text and "seg" not in rec:
            rec["seg"] = seg[:200]
        def first(rx):
            mm = rx.search(seg)
            return float(mm.group(1)) if mm else None
        rec["production"] = rec["production"] if rec["production"] is not None else first(_MB_PRODUCTION_RE)
        rec["consumption"] = rec["consumption"] if rec["consumption"] is not None else first(_MB_CONSUMPTION_RE)
        rec["stock"] = rec["stock"] if rec["stock"] is not None else first(_MB_STOCK_RE)
        if rec["stu"] is None:
            stu = first(_MB_STU_RE)
            if stu is not None and 1.0 <= stu <= 40.0:
                rec["stu"], rec["stuStated"] = stu, True
    # 合理性 + 自洽检查
    lo, hi = MEAL_MONTHLY_CONSUMPTION_RANGE
    for key, rec in list(records.items()):
        if rec["consumption"] is not None and not (lo <= rec["consumption"] <= hi):
            rec["consumption"] = None
        if rec["stock"] is not None and _plausibility_problem("mealStock", rec["stock"]):
            rec["stock"] = None
        if rec["stuStated"] and rec["stock"] is not None and rec["consumption"]:
            if abs(rec["stock"] / rec["consumption"] * 100 - rec["stu"]) > MEAL_STU_CONSISTENCY_TOL:
                rec["stock"] = None     # 多半是月中低点/期初值，不是月末库存：库消比以文中明示为准，库存不展示
        if all(rec[k] is None for k in ("production", "consumption", "stock", "stu")):
            if keep_text and rec.get("seg"):
                continue       # 诊断模式下保留"有月份标记但一个数都没解析出"的记录，回填报告要展示它的原文
            del records[key]
    return records


def _usable_meal_record(rec):
    """这条月度记录能不能给出库消比：文中明示，或库存和消费都有可以推算。返回(值, 方式)。"""
    if rec.get("stu") is not None:
        return rec["stu"], "stated"
    if rec.get("stock") is not None and rec.get("consumption"):
        v = round(rec["stock"] / rec["consumption"] * 100, 2)
        if 1.0 <= v <= 40.0:
            return v, "computed"
    return None, None


def _html_to_text(raw):
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw or "")
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _extract_article_region(text, title):
    """页面里有大量导航/推荐文章标题(含各种"9月29日…"月份标记，会干扰解析)。只取"文章标题→免责声明"之间那段正文。"""
    end = text.find("免责声明")
    end = end if end >= 0 else len(text)
    start = text.rfind(title, 0, end) if title else -1
    start = start if start >= 0 else max(0, end - 6000)
    return text[start:end]


# ★来源是"外部响应"的URL(比如Mysteel搜索结果里每篇文章的url)必须过域名白名单才允许请求。
#   这类URL不是我们写死的，如果搜索接口被劫持/污染/返回异常数据，没有校验的话，Actions(带着USDA_API_KEY等环境变量运行)会去访问任意地址。
#   只允许https + 精确的Mysteel域名；不接受http、带用户名密码的URL(user@host技巧)、域名后缀欺骗(如 ncp.mysteel.com.evil.com)。
TRUSTED_ARTICLE_HOSTS = ("ncp.mysteel.com", "www.mysteel.com", "m.mysteel.com", "ncp.m.mysteel.com")


def is_trusted_article_url(url, allowed_hosts=TRUSTED_ARTICLE_HOSTS):
    """url是否是https、主机名恰好在白名单里、没有用户名密码、没有奇怪端口。"""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(str(url).strip())
    except ValueError:
        return False
    if u.scheme != "https" or u.username is not None or u.password is not None:
        return False
    try:
        port = u.port
    except ValueError:
        return False
    return (u.hostname or "").lower() in allowed_hosts and port in (None, 443)


def fetch_text_debug(url, headers=None, retries=2, timeout=20):
    """GET一个网页，返回(文本, debug)。跟fetch_json_debug同一套错误处理，只是不做JSON解析。"""
    headers = dict(headers or {})
    headers.setdefault("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    headers.setdefault("Accept", "text/html,application/xhtml+xml")
    debug = {"url": url}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                debug["httpStatus"] = resp.status
                debug["rawSnippet"] = raw[:300]
                return raw, debug
        except urllib.error.HTTPError as e:
            debug["httpStatus"] = e.code
            debug["error"] = f"HTTP {e.code}: {e.reason}"
            print(f"[WARN] 请求失败(HTTP {e.code}): {url}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            debug["error"] = str(e)
            print(f"[WARN] 请求失败: {url} -> {e}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return None, debug


def fetch_mysteel_meal_balance(today=None, weekly_stock=None):
    """国内豆粕库存消费比(月度，Mysteel《全国豆粕供需平衡表》)。
    weekly_stock：可选，形如fetch_mysteel_meal_stock()的返回值，给"周度库存÷当月消费"这一级回退和交叉核对用。
    today参数只给测试用。"""
    if today is None:
        now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
        today = now_bj.date()
    else:
        now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    start_bj = now_bj - timedelta(days=365)
    headers = {"token": "-1", "Origin": "https://search.mysteel.com",
               "Referer": "https://search.mysteel.com/fastcomment.html", "X-Requested-With": "XMLHttpRequest"}

    articles = []   # (发布日期, item)
    items_checked, skipped_titles = 0, []
    for page in range(1, 3):
        payload = {"query": MEAL_BALANCE_QUERY, "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
                   "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"), "sortType": "complex",
                   "platform": "pc", "pageNo": page, "pageSize": 20}
        data, debug = fetch_json_debug(MYSTEEL_ARTICLE_SEARCH_URL, headers=headers, post_data=payload)
        if data is None or not isinstance(data, dict) or data.get("resultCode") != 0:
            if page == 1:
                if data is None:
                    return {"available": False, "reason": "Mysteel文章搜索接口无返回数据", "debug": debug}
                return {"available": False, "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
                        "debug": {"rawSnippet": debug.get("rawSnippet")}}
            break
        data_list = data.get("dataList") or []
        if page == 1 and not data_list:
            return {"available": False, "reason": "搜索结果为空(最近一年内没有匹配的文章)", "debug": {"total": data.get("total")}}
        for item in data_list:
            if not isinstance(item, dict):
                continue
            items_checked += 1
            title = str(item.get("title") or "")
            if MEAL_BALANCE_TITLE_KEY not in title:
                skipped_titles.append(title[:40])
                continue
            try:
                pub = datetime.strptime(str(item.get("publishTime", ""))[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            articles.append((pub, item))
        total = data.get("total") or 0
        if len(data_list) < 20 or page * 20 >= total:
            break

    if not articles:
        return {"available": False, "reason": "搜索结果里没有标题含'豆粕供需平衡表'的文章",
                "debug": {"itemsChecked": items_checked, "skippedTitles": skipped_titles[:10]}}
    articles.sort(key=lambda a: a[0], reverse=True)
    newest_pub, newest_item = articles[0]
    newest_age = (today - newest_pub).days
    if newest_age > MEAL_BALANCE_MAX_ARTICLE_AGE_DAYS:
        return {"available": False,
                "reason": f"最新一篇平衡表是{newest_age}天前({newest_pub.isoformat()})，超过{MEAL_BALANCE_MAX_ARTICLE_AGE_DAYS}天的新鲜度限制，可能停更；不采用",
                "debug": {"latestArticleDate": newest_pub.isoformat(), "articles": len(articles)}}

    # ---- 逐篇解析：新→旧；每篇先正文(只取最新几篇)，再摘要 ----
    candidates = {}      # (年,月) → [(优先级顺序, 记录, 来源, 文章日期, 文章)]，靠前的优先
    body_notes, bodies_fetched = [], 0
    for idx, (pub, item) in enumerate(articles[:4]):
        sources = []
        if idx < MEAL_BALANCE_BODY_FETCH_LIMIT and item.get("url") and is_trusted_article_url(item["url"]):
            raw, dbg = fetch_text_debug(item["url"], headers={"Referer": "https://ncp.mysteel.com/"})
            if raw:
                region = _extract_article_region(_html_to_text(raw), str(item.get("title") or ""))
                recs = _parse_meal_balance_text(region, pub)
                if recs:
                    bodies_fetched += 1
                    sources.append(("body", recs))
                else:
                    body_notes.append(f"{pub.isoformat()}: 正文取到了但没解析出单月记录(可能被截断/格式变了)")
            else:
                body_notes.append(f"{pub.isoformat()}: 正文请求失败({dbg.get('error')})")
        srecs = _parse_meal_balance_text(item.get("content"), pub)
        if srecs:
            sources.append(("summary", srecs))
        for src, recs in sources:
            for key, rec in recs.items():
                candidates.setdefault(key, []).append((src, rec, pub, item))

    def best_for(key):
        for src, rec, pub, item in candidates.get(key, []):
            val, how = _usable_meal_record(rec)
            if val is not None:
                return {"src": src, "how": how, "value": val, "rec": rec, "pub": pub, "item": item}
        # 没有可用的库消比，但有消费量：给"周度库存÷消费"这一级回退留着
        for src, rec, pub, item in candidates.get(key, []):
            if rec.get("consumption"):
                return {"src": src, "how": None, "value": None, "rec": rec, "pub": pub, "item": item}
        return None

    def ym_add(y, m, k):
        t = y * 12 + (m - 1) + k
        return t // 12, t % 12 + 1

    cur = (today.year, today.month)
    used_fallback_month = False
    chosen = best_for(cur)
    chosen_key = cur
    if chosen is None or (chosen["value"] is None and not (weekly_stock and weekly_stock.get("available"))):
        # 当月还没有记录(比如月初，新一期还没发)：用最近一个不晚于当月的记录，新鲜度已经由文章日期限制过
        for back in range(1, 4):
            k = ym_add(cur[0], cur[1], -back)
            b = best_for(k)
            if b is not None and b["value"] is not None:
                chosen, chosen_key, used_fallback_month = b, k, True
                break
    if chosen is None:
        return {"available": False, "reason": "最近几篇平衡表里没有解析出任何单月的库消比/库存/消费数据(措辞或格式可能变了)",
                "debug": {"articlesChecked": len(articles[:4]), "bodyNotes": body_notes,
                          "newestSummary": str(newest_item.get("content") or "")[:300]}}

    rec, method, value = chosen["rec"], chosen["how"], chosen["value"]
    weekly_ok = bool(weekly_stock and weekly_stock.get("available") and weekly_stock.get("value") is not None)
    weekly_check = None
    if rec.get("consumption") and weekly_ok:
        wv = round(weekly_stock["value"] / rec["consumption"] * 100, 2)
        weekly_check = {"stockWan": weekly_stock["value"], "stockDate": weekly_stock.get("date"),
                        "consumptionWan": rec["consumption"], "value": wv}
    if value is None:
        # 第三级回退：周度库存÷当月预计消费。周度库存不是月末值，可信度低于文中数字，明确标出
        if weekly_check and 1.0 <= weekly_check["value"] <= 40.0:
            value, method = weekly_check["value"], "weekly"
        else:
            return {"available": False, "reason": "当月记录里没有库消比，也没有足够的库存/消费数据可以推算",
                    "debug": {"record": rec, "bodyNotes": body_notes}}
    if _plausibility_problem("mealStu", value):
        return {"available": False, "reason": f"解析出的库消比不合理，已丢弃: {_plausibility_problem('mealStu', value)}",
                "debug": {"record": rec}}

    nxt = None
    nk = ym_add(chosen_key[0], chosen_key[1], 1)
    nb = best_for(nk)
    if nb is not None and nb["value"] is not None and not _plausibility_problem("mealStu", nb["value"]):
        nxt = {"month": f"{nk[0]}-{nk[1]:02d}", "monthLabel": f"{nk[0]}年{nk[1]}月", "value": nb["value"],
               "method": nb["how"], "stockWan": nb["rec"].get("stock"), "consumptionWan": nb["rec"].get("consumption")}
    trend = None
    if nxt is not None:
        d = round(nxt["value"] - value, 2)
        trend = {"delta": d, "direction": "上升(累库)" if d >= 1.0 else "下降(去库)" if d <= -1.0 else "基本持平"}

    pub, item = chosen["pub"], chosen["item"]
    method_label = {"stated": "文章明示", "computed": "由库存÷消费推算", "weekly": "周度库存÷当月预计消费(可信度较低)"}[method]
    festival = cn_calendar.holiday_month_context(chosen_key[0], chosen_key[1])
    if nxt is not None:
        nxt["festival"] = cn_calendar.holiday_month_context(nk[0], nk[1])
    result = {
        "available": True,
        "value": value,
        "month": f"{chosen_key[0]}-{chosen_key[1]:02d}",
        "monthLabel": f"{chosen_key[0]}年{chosen_key[1]}月",
        # ★长假扰动：库消比=月末库存÷当月消费量，长假前后月消费骤变，比值被机械压低/抬高，跟供应松紧无关。
        #   name=春节(level=strong)：前端不按固定阈值判方向；name=国庆(level=mild)：仍计分，但这一组票权降一档(见cn_calendar)。
        "festival": festival,
        # 记录的月份晚于文章发布的月份 = 预测值(比如8月31日发布的文章里的9月)
        "isForecast": (chosen_key[0] * 12 + chosen_key[1]) > (pub.year * 12 + pub.month),
        "usedFallbackMonth": used_fallback_month,
        "method": method, "methodLabel": method_label,
        "recordSource": chosen["src"],
        "stockWan": rec.get("stock"), "consumptionWan": rec.get("consumption"), "productionWan": rec.get("production"),
        "next": nxt, "trend": trend, "weeklyCheck": weekly_check,
        "date": pub.isoformat(), "articleAgeDays": (today - pub).days,
        "articleTitle": item.get("title"),
        "bodiesFetched": bodies_fetched,
        "source": "Mysteel文章(全国豆粕供需平衡表)",
        "sourceUrl": item.get("url") or "https://search.mysteel.com/fastcomment.html",
    }
    if body_notes:
        result["bodyNotes"] = body_notes     # 正文没取到时如实说明(用的是摘要)，部署后看一眼就知道Actions那边能不能抓到正文
    return result


# ---------------------------------------------------------------------------
# 饲料企业豆粕库存天数(Mysteel每周《全国主要地区饲料企业豆粕库存天数调查》)
#
# ★为什么要：需求端目前只有猪粮比/肉鸡利润/豆菜粕价差这类间接指标，缺一个直接的——
#   饲料厂手里的豆粕还能用几天。天数高=库存充足，近期采购需求偏弱；天数低=需要补库，采购需求偏强。
#   (之前我说它是付费数据，可能说错了：它跟豆粕库存同一个搜索接口，摘要里直接有数字。)
# ★数据形态：只见过这一篇真实样本(2026-07-03那期)——
#   "截至7月3日，全国饲料企业豆粕物理库存为7.41天，环比微增0.17天，同比下滑0.50天。"
#   注意"环比微增0.17天""同比下滑0.50天"也是"X天"，不能把它们当成库存天数——所以库存天数必须紧跟在"库存"后面，
#   中间不能夹着"环比/同比"。别的周的措辞我没见过，所以提取不出时如实说明，不猜。
# ★评分：只有历史分位可用时才投票(≥80%偏空、≤20%偏多)，样本不足时只显示——不为它编绝对阈值(见前端)。
# ---------------------------------------------------------------------------
FEED_DAYS_QUERY = "全国主要地区饲料企业豆粕库存天数调查"
FEED_DAYS_TITLE_KEY = "饲料企业豆粕库存天数"
FEED_DAYS_MAX_AGE_DAYS = 30                 # 每周一期，超过30天没有新的说明可能停更
_FEED_VALUE_RE = re.compile(r"库存(?:天数)?(?P<gap>[^0-9。；;，,]{0,6}?)(?P<v>\d+\.?\d*)\s*天")
# ★旧措辞(2021年底~2022年初，用户2026-10-01回填报告里5篇提取失败的真实原文)："国内饲料企业豆粕库存天数（物理库存天数）为10.85，较前一周增加1.33天"——
#   数值后面没有"天"字，且"（物理库存天数）为"超过6个字符。放宽成没有"天"字时有误取风险(增幅13.97%、第2周、年份、115万吨)，
#   所以只在一个很具体的结构下才允许：库存天数 + 可选括号说明 + 为 + 数字，数字后面不能紧跟 % / 万 / 吨 / 数字。
_FEED_VALUE_OLD_RE = re.compile(r"库存天数(?:[（(][^）)]{0,12}[）)])?为(?P<v>\d+\.\d+|\d+)(?![\d.]*[%％万吨])(?!\d)")
# ★措辞不止一种(用户2026-09-30贴的20期真实摘要)：多数写"环比…/同比…"，但9月24日和5~6月初那几期写"较上期增0.32天""较上一期减0.08天""较去年同期增0.63天"，
#   只认"环比/同比"会漏掉这5期。
_FEED_CHANGE_RE = {
    "mom": re.compile(r"(?:环比|较上一?期|较前一周|较上一?周)(?P<w>[^0-9。；;，,]{0,6}?)(?P<v>\d+\.?\d*)\s*天"),
    "yoy": re.compile(r"(?:同比|较去年同期)(?P<w>[^0-9。；;，,]{0,6}?)(?P<v>\d+\.?\d*)\s*天"),
}
_FEED_CHANGE_MARKERS = ("比", "较", "增", "减", "升", "降", "涨", "跌", "下", "上", "持平")
_FEED_UP = ("增", "升", "涨", "上")
_FEED_DOWN = ("降", "减", "跌", "下", "缩", "回落")
_FEED_TITLE_DATE_RE = re.compile(r"[（(](\d{8})[)）]")


def _extract_feed_days(text):
    """从一段文字里提取(库存天数, 环比天数, 同比天数)。返回(result或None, 拒绝原因列表)。
    环比/同比带方向：增/升/涨=正，降/减/跌/下滑=负，"持平"=0；方向词认不出来时不给数(None)，不猜符号。"""
    text = re.sub(r"\s+", "", str(text or ""))
    rejected = []
    value = None
    for m in _FEED_VALUE_RE.finditer(text):
        # ★变动量的标志词：比(环比/同比)、较(较上期/较前一周/较去年同期)、增/减/升/降/涨/跌/下/上/持平——gap里出现任何一个，后面的数字就是变动量不是库存天数。
        #   (原来只认"比"，写'库存天数较前一周增加1.33天'时会把1.33当成库存天数——加"较前一周"措辞时变动量防护没有同步扩展，变异检查发现)
        if any(w in m.group("gap") for w in _FEED_CHANGE_MARKERS):
            rejected.append(f"{m.group('v')}天: 紧跟在比较/变动方向词后面，是变动量不是库存天数")
            continue
        v = float(m.group("v"))
        problem = _plausibility_problem("feedDays", v)
        if problem:
            rejected.append(f"{v:g}天: {problem}")
            continue
        value = v
        break
    if value is None:
        # 新写法(数值后面有"天")没匹配上：再试旧写法(2021年底~2022年初，数值后面没有"天")
        for m in _FEED_VALUE_OLD_RE.finditer(text):
            v = float(m.group("v"))
            problem = _plausibility_problem("feedDays", v)
            if problem:
                rejected.append(f"{v:g}: {problem}")
                continue
            value = v
            break
    if value is None:
        return None, rejected
    out = {"value": value, "mom": None, "yoy": None}
    for key, rx in _FEED_CHANGE_RE.items():
        m = rx.search(text)
        if not m:
            if key == "mom" and ("环比持平" in text or "较上期持平" in text or "较上一期持平" in text or "较前一周持平" in text or "较上周持平" in text or "较上一周持平" in text):
                out["mom"] = 0.0
            if key == "yoy" and ("同比持平" in text or "较去年同期持平" in text):
                out["yoy"] = 0.0
            continue
        word, v = m.group("w"), float(m.group("v"))
        if any(w in word for w in _FEED_UP):
            out[key] = v
        elif any(w in word for w in _FEED_DOWN):
            out[key] = -v
        elif "持平" in word:
            out[key] = 0.0
    return out, rejected


def _feed_asof_date(item, pub):
    """数据日期：优先用标题里的(20260703)，否则用发布日期。"""
    m = _FEED_TITLE_DATE_RE.search(str(item.get("title") or ""))
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            pass
    return pub


def fetch_mysteel_feed_days(today=None):
    if today is None:
        now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
        today = now_bj.date()
    else:
        now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    start_bj = now_bj - timedelta(days=365)
    headers = {"token": "-1", "Origin": "https://search.mysteel.com", "Referer": "https://search.mysteel.com/fastcomment.html",
               "X-Requested-With": "XMLHttpRequest"}
    arts, rejected_all, items_checked, skipped = [], [], 0, []
    for page in range(1, 4):
        payload = {"query": FEED_DAYS_QUERY, "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
                   "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"), "sortType": "complex", "platform": "pc", "pageNo": page, "pageSize": 20}
        data, debug = fetch_json_debug(MYSTEEL_ARTICLE_SEARCH_URL, headers=headers, post_data=payload)
        if data is None or not isinstance(data, dict) or data.get("resultCode") != 0:
            if page == 1:
                if data is None:
                    return {"available": False, "reason": "Mysteel文章搜索接口无返回数据", "debug": debug}
                return {"available": False, "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
                        "debug": {"rawSnippet": debug.get("rawSnippet")}}
            break
        lst = data.get("dataList") or []
        if page == 1 and not lst:
            return {"available": False, "reason": "搜索结果为空(最近一年内没有匹配的文章)", "debug": {"total": data.get("total")}}
        for it in lst:
            if not isinstance(it, dict):
                continue
            items_checked += 1
            title = str(it.get("title") or "")
            if FEED_DAYS_TITLE_KEY not in title:
                skipped.append(title[:40])
                continue
            try:
                pub = datetime.strptime(str(it.get("publishTime", ""))[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            arts.append((pub, it))
        total = data.get("total") or 0
        if len(lst) < 20 or page * 20 >= total:
            break
    if not arts:
        return {"available": False, "reason": "搜索结果里没有标题含'饲料企业豆粕库存天数'的文章",
                "debug": {"itemsChecked": items_checked, "skippedTitles": skipped[:10]}}
    arts.sort(key=lambda a: a[0], reverse=True)

    weeks = {}      # 数据日期 → {value, mom, yoy, source, item}
    for idx, (pub, it) in enumerate(arts):
        res, rej = _extract_feed_days(it.get("content"))
        rejected_all.extend(rej)
        src = "summary"
        if res is None and idx < 2 and it.get("url") and is_trusted_article_url(it["url"]):
            # 最新两篇摘要里没有数：抓正文再试一次(只取标题→免责声明之间，避免导航/推荐文章的干扰)
            raw, dbg = fetch_text_debug(it["url"], headers={"Referer": "https://ncp.mysteel.com/"})
            if raw:
                region = _extract_article_region(_html_to_text(raw), str(it.get("title") or ""))
                res, rej2 = _extract_feed_days(region)
                rejected_all.extend(rej2)
                src = "body"
        if res is None:
            continue
        d = _feed_asof_date(it, pub)
        if d not in weeks or pub > weeks[d]["pub"]:
            weeks[d] = dict(res, pub=pub, source=src, item=it)
    if not weeks:
        return {"available": False, "reason": "最近几篇《饲料企业豆粕库存天数调查》里都没能提取出库存天数(措辞可能变了)",
                "debug": {"articlesChecked": len(arts), "rejected": rejected_all[:10],
                          "newestSample": str(arts[0][1].get("content") or "")[:300]}}
    latest_d = max(weeks)
    w = weeks[latest_d]
    age = (today - latest_d).days
    if age > FEED_DAYS_MAX_AGE_DAYS:
        return {"available": False, "reason": f"最新一期是{age}天前({latest_d.isoformat()})，超过{FEED_DAYS_MAX_AGE_DAYS}天的新鲜度限制，可能停更；不采用",
                "debug": {"latestDate": latest_d.isoformat(), "value": w["value"]}}
    recent = [{"date": d.isoformat(), "value": x["value"], "mom": x["mom"], "yoy": x["yoy"]}
              for d, x in sorted(weeks.items(), reverse=True)[:60]]
    return {
        "available": True, "value": w["value"], "date": latest_d.isoformat(),
        "momDays": w["mom"], "yoyDays": w["yoy"],
        # 去年同期的库存天数 = 本期 - 同比变动量(文章里的同比是"比去年同期高/低多少天")；同比没有数字时为None
        "lastYearValue": round(w["value"] - w["yoy"], 2) if w["yoy"] is not None else None,
        # 备货-假期窗口：长假前饲料厂提前提货，库存天数被抬高，不代表真实需求强弱(见cn_calendar.holiday_window)
        "holiday": cn_calendar.holiday_window(latest_d),
        "articleTitle": w["item"].get("title"), "publishDate": w["pub"].isoformat(), "extractedFrom": w["source"],
        "recentWeeks": recent,
        "source": "Mysteel文章(全国主要地区饲料企业豆粕库存天数调查)",
        "sourceUrl": w["item"].get("url") or "https://search.mysteel.com/fastcomment.html",
    }


# ---------------------------------------------------------------------------
# 猪粮比 + 能繁母猪存栏：改自动抓取，用akshare的futures_hog_supply接口
# (数据源：玄田数据，https://zhujia.zhuwang.com.cn)。
#
# ★实测确认过程：这次用户直接给了函数名，没有照搬——先pip install akshare，
#   确认了ak.futures_hog_supply这个函数真实存在，docstring里明确列出的
#   symbol选项("猪粮比价"/"生猪产能")跟用户说的一致。实际调用测试时，沙盒
#   连不上底层真实API域名(跟DCE K线数据一样的沙盒网络限制)，改成跟处理
#   agrobr(巴西播种进度)那次一样的方法——直接读akshare这个函数的源码。
#
# ★源码读出来两个关键发现：
#   ① 真实的底层URL是https://xt.yangzhu.vip/data/getmapdata(不是docstring
#      写的zhujia.zhuwang.com.cn，那只是这个数据服务对外的门户网站)，用
#      ptype这个参数区分具体取哪类数据(猪粮比价=11，生猪产能=7)。
#   ② "生猪产能"这个symbol的返回结构里，除了"能繁母猪存栏"这一项，还
#      同时带了"猪肉产量"/"生猪存栏"/"生猪出栏"三项——这次实现只取
#      能繁母猪存栏这一项(仪表盘目前的手动指标只对应这一项)。
#
# ★没有自己重新实现底层HTTP+JSON解析逻辑(跟处理Mysteel/agtransport不同的
#   决定)：因为akshare源码里"temp_df.columns = [...]"这一行是**事后**按位置
#   重新命名DataFrame的欄位，不是原始JSON的真实键名——原始JSON的字段结构
#   要么是没有键名的list-of-lists，要么是键名跟"date"/"value"完全不同的
#   list-of-dicts，源码本身看不出是哪一种，而沙盒又连不上真实API去实测
#   确认。与其自己猜一份可能出错的JSON解析逻辑，不如直接调用akshare这个
#   函数本身(反正已经装了这个库)，让pandas/akshare处理这部分，只需要在
#   拿到DataFrame之后处理"取最新一行"这一步。
def _fetch_akshare_hog_df(symbol, retries=2, timeout_seconds=15, retry_delay_seconds=2, func_name="futures_hog_supply"):
    """共用逻辑：调用ak.futures_hog_supply(symbol=...)，处理import/调用异常。
    返回(df, None)成功，或(None, error_dict)失败——调用方失败时直接return
    error_dict。

    ★真实运行暴露的问题(已加固)：akshare这个函数内部直接调用
    `requests.post(url, params=params)`，没有传timeout参数——真实运行时
    遇到过`ConnectTimeoutError`(连接xt.yangzhu.vip超时)，因为没有显式
    timeout，卡了很久才失败，拖累了同一批次里其他20多个数据源的抓取。
    没法直接修改akshare内部的requests.post()调用(它是第三方库，没有暴露
    timeout参数给调用方)，改用`socket.setdefaulttimeout()`这个全局设置
    间接给这次调用加上超时限制——用完之后必须在finally里恢复原值，避免
    影响同一个Python进程里其他部分的网络请求(这个文件里还有很多其他函数
    也在发网络请求)。同时加了重试(默认2次)，因为连接超时也可能只是这次
    运行偶发的网络波动，不一定是这个数据源本身长期不可达。
    ★retry_delay_seconds单独作为参数暴露出来(不是写死在函数体内)，方便
    单元测试时传0跳过真正的等待，不用为了测"重试耗尽"这种场景真的等上
    好几秒。"""
    try:
        import akshare as ak
    except ImportError:
        return None, {"available": False, "reason": "未安装akshare库，请检查GitHub Actions是否执行了pip install akshare"}

    last_error_msg = None
    last_error_type = None
    for attempt in range(retries):
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout_seconds)
        try:
            df = getattr(ak, func_name)(symbol=symbol)
        except Exception as e:
            last_error_msg = str(e)
            last_error_type = type(e).__name__
            df = None
        finally:
            socket.setdefaulttimeout(old_timeout)  # ★必须恢复，这是进程级全局设置

        if df is not None and len(df) > 0:
            return df, None
        if attempt < retries - 1:
            time.sleep(retry_delay_seconds)  # 重试前等一下，给网络一点恢复时间

    if last_error_msg is not None:
        return None, {
            "available": False,
            "reason": f"akshare猪粮比/生猪产能接口调用失败(已重试{retries}次): {last_error_msg}",
            "debug": {"symbol": symbol, "errorType": last_error_type, "retriesAttempted": retries},
        }
    return None, {"available": False, "reason": f"接口调用成功但返回空数据(已重试{retries}次，symbol={symbol})", "debug": {"symbol": symbol, "retriesAttempted": retries}}


# ---------------------------------------------------------------------------
# 上月中国大豆月度进口量：改用Mysteel文章搜索(沿用前面几个指标的思路)。用户在文档里贴了真实响应
# (查询"海关总署中国大豆进口量"，一年窗口，共24条，展开了20条完整正文)，看到的写法很杂：
#   官方快讯 "2026年7月中国大豆进口量为1147.7万吨"；"中国2026年4月大豆进口847.8万吨"；
#   "中国2026年5月进口大豆1179.1万吨"(顺序反过来)；一篇里合并发布1月+2月；
#   市场早报里没写年份的 "8月中国大豆进口1214.14万吨"。
#
# ★同一篇文章里还有一堆"长得像月度进口量、其实不是"的数，逐个防：
#   ① 累计数："今年1-7月累计进口大豆6151.1万吨"、"上半年累计进口大豆5015.4万吨"、
#      "2025年1－12月中国累计进口大豆总量为11183.3万吨"、"中国2026年1-4月大豆进口2515.1万吨"——
#      要求"X月"后面**紧跟**"大豆进口"/"进口大豆"(中间不许有"累计")，并且"X月"前面不能是"1-"/"1－"
#      这种区间横线(否则"1－2月大豆进口1254.7万吨"会被当成2月，而2月真实值是597.6)；
#   ② 年度数："2025年全年中国大豆进口量共11181.89万吨"——没有"X月"，不匹配；
#   ③ 变动量："环比12月进口减少147.3万吨"——"进口"后面是"减少"不是"大豆"，不匹配；
#   ④ 预测："7月预计1100万吨"(到港预估)——前面出现预计/预估等词就丢，且没有"大豆进口"紧邻；
#   ⑤ 没写数值的："8月大豆进口同比增1.1%"、"国内大豆进口量增加"——必须有"X万吨"。
#   年份没写时按发布日期推断(8月的数在9月发布→当年；12月的数在1月发布→上一年)。
#
# ★新鲜度：只接受"今天的上个月"和"再上一个月"两期(海关快讯一般在次月7号前后发布，所以月初上个月的
#   数据可能还没出，要允许退到上上个月；但更旧的一律不采用)。2026-09-28：接受8月，找不到才退到7月。
MYSTEEL_SOY_IMPORT_PATTERN = re.compile(
    r"(?<![-－—~至\d])(?:(\d{4})年)?(\d{1,2})月(?:份)?(?:中国|我国|全国)?"
    r"(?:大豆进口(?:量)?(?:为)?|进口大豆(?:量)?(?:为)?)\s*(\d+\.?\d*)\s*万吨")
_IMPORT_FORECAST_WORDS = ("预计", "预期", "预估", "预测", "有望", "将", "计划")


def _prev_month(year, month):
    return (year, month - 1) if month > 1 else (year - 1, 12)


def _extract_soy_import_candidates(text, pub_date, today):
    """从一段文本里提取所有(年, 月, 进口量万吨)候选。"""
    out = []
    latest_done = _prev_month(today.year, today.month)
    for m in MYSTEEL_SOY_IMPORT_PATTERN.finditer(text):
        month = int(m.group(2))
        if not (1 <= month <= 12):
            continue
        if any(w in text[max(0, m.start() - 8):m.start()] for w in _IMPORT_FORECAST_WORDS):
            continue  # 预测值
        value = float(m.group(3))
        if _plausibility_problem("soyImport", value):
            continue
        year = int(m.group(1)) if m.group(1) else (pub_date.year if month <= pub_date.month else pub_date.year - 1)
        if (year, month) > latest_done:
            continue  # 当月及以后的月份不可能已有进口数据
        out.append((year, month, value))
    return out


def fetch_mysteel_soy_import(today=None):
    """通过Mysteel文章搜索"海关总署中国大豆进口量"，翻页收齐后取最新的一个月度进口量(万吨)。
    today参数只给测试用。"""
    if today is None:
        now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
        today = now_bj.date()
    else:
        now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    start_bj = now_bj - timedelta(days=365)  # 跟用户抓包的请求一致(2025-09-28到2026-09-28)
    headers = {
        "token": "-1",
        "Origin": "https://search.mysteel.com",
        "Referer": "https://search.mysteel.com/fastcomment.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    page_size, max_pages = 20, 5  # 实测total=24(2页)，上限放到5页留余量
    candidates = []  # (年, 月, 发布日期, 进口量, item)
    items_checked = 0
    first_item = None

    for page in range(1, max_pages + 1):
        payload = {
            "query": "海关总署中国大豆进口量",
            "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
            "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"),
            "sortType": "complex",
            "platform": "pc",
            "pageNo": page,
            "pageSize": page_size,
        }
        data, debug = fetch_json_debug(MYSTEEL_ARTICLE_SEARCH_URL, headers=headers, post_data=payload)
        if data is None or not isinstance(data, dict) or data.get("resultCode") != 0:
            if page == 1:
                if data is None:
                    return {"available": False, "reason": "Mysteel文章搜索接口无返回数据", "debug": debug}
                return {"available": False,
                        "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
                        "debug": {"rawSnippet": debug.get("rawSnippet")}}
            break
        data_list = data.get("dataList") or []
        if page == 1 and not data_list:
            return {"available": False, "reason": "搜索结果为空(最近一年内没有匹配的文章)", "debug": {"total": data.get("total")}}
        for item in data_list:
            if not isinstance(item, dict):
                continue
            items_checked += 1
            if first_item is None:
                first_item = item
            try:
                pub_date = datetime.strptime(str(item.get("publishTime", ""))[:10], "%Y-%m-%d").date()
            except ValueError:
                pub_date = today
            for v in item.values():
                if not isinstance(v, str):
                    continue
                for year, month, value in _extract_soy_import_candidates(v, pub_date, today):
                    candidates.append((year, month, pub_date, value, item))
        total = data.get("total") or 0
        if len(data_list) < page_size or page * page_size >= total:
            break

    if not candidates:
        return {"available": False,
                "reason": "搜索结果里没有一条能提取出'X月中国大豆进口XXXX万吨'这个格式(可能措辞变了，或者上个月的数据还没发布)",
                "debug": {"itemsChecked": items_checked, "firstItemSample": first_item}}

    label = lambda ym: f"{ym[0]}年{ym[1]}月"
    months_seen = sorted({(c[0], c[1]) for c in candidates}, reverse=True)
    latest_done = _prev_month(today.year, today.month)
    allowed = {latest_done, _prev_month(*latest_done)}
    fresh = [c for c in candidates if (c[0], c[1]) in allowed]
    if not fresh:
        return {"available": False,
                "reason": (f"只找到了较旧的月度数据(最新一期是{label(months_seen[0])})，已超出允许的滞后范围"
                           f"(今天的上个月是{label(latest_done)}，只接受{label(latest_done)}和{label(_prev_month(*latest_done))})，"
                           f"为避免把旧数据当成最新值，不采用"),
                "debug": {"monthsSeen": [label(x) for x in months_seen], "itemsChecked": items_checked}}

    year, month, pub_date, value, item = max(fresh, key=lambda c: (c[0], c[1], c[2]))
    return {
        "available": True,
        "value": value,
        "monthLabel": label((year, month)),
        "date": pub_date.isoformat(),
        "articleTitle": item.get("title"),
        "monthsSeen": [label(x) for x in months_seen],
        "source": "Mysteel文章(海关总署中国大豆进口量)",
        "sourceUrl": item.get("url") or "https://search.mysteel.com/fastcomment.html",
    }


# ---------------------------------------------------------------------------
# 最近一次国储进口大豆拍卖：改用Mysteel文章搜索(沿用前面几个指标的思路)。用户在文档里贴了真实响应
# (查询"进口大豆竞价销售结果"，一年窗口，total=115，展开了第1页20条完整正文)。
#
# ★现有计分逻辑是"拍卖量>=40万吨→供给端主动增投，偏空"，输入框占位符"如54.3"正好是9月22日那次的
#   计划拍卖量(542992吨=54.3万吨)——所以这个指标的口径是**计划拍卖量(万吨)**，自动填这个数，计分逻辑不动。
#   成交量/成交率/成交价格作为参考信息一起抓下来展示(文档里用户问过"能不能把成交率和成交价格也加上来
#   一起判断")；要不要把成交率纳入计分，是单独的分析决策，没有擅自改。
#
# ★20条真实文章里混着三类完全不同的东西，必须分开：
#   ① 交易公告("2026年9月28日进口大豆竞价销售交易公告"，正文只有一句"中储粮油脂委托于…开展竞价销售")——
#      没有数量，天然排除(要求正文有"计划拍卖"+成交结果)；
#   ② **原油基差竞价**("【中储粮网】…油脂公司进口大豆原油基差竞价销售交易结果"，"计划销售总量19884吨")——
#      卖的是大豆**原油**不是大豆，量只有几千吨，标题也带"进口大豆…竞价销售交易结果"，最容易混进来。
#      标题或正文出现"原油"/"基差"就排除；
#   ③ 真正的"进口大豆竞价销售结果"——提取计划拍卖量、成交量、成交率、价格。
#
# ★写法有变化(5条真实结果，措辞都不一样)："计划拍卖22、23、24年产进口大豆514312.514吨"(年产夹在中间)/
#   "计划拍卖542992.291吨"/"计划拍卖进口大豆68012.56吨"；"最终成交191698.792吨"/"最终成交量为0吨"/
#   "实际成交222781.779吨"；价格有"竞拍底价4310元/吨，最高价4390元/吨"、"价格区间为4280元/吨至4450元/吨"、
#   "起拍价区间为4330-4380元/吨"、"成交价格区间为4110-4200元/吨，成交均价4162.73元/吨"四种。
#   完整性校验：成交量÷计划量必须跟文中的成交率对得上(误差1个百分点内)，对不上说明取错了数，整条丢弃。
#
# ★"最近一次"按**拍卖日期**取最大(不是文章发布日期——9月2日那次的结果文章是9月14日才发的)。国储拍卖
#   可能暂停，所以新鲜度放宽到45天(实测拍卖间隔最长13天)，超过就拒绝并提示"可能已暂停拍卖"。
#   搜索结果共115条(6页)，按相关度排序，最新一次不一定在第1页，所以翻页收齐(最多8页)。
RESERVE_MAX_AGE_DAYS = 45
_RESERVE_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_RESERVE_TITLE_MD_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")


def _parse_reserve_auction(title, content, pub_date):
    """解析一篇"进口大豆竞价销售结果"文章。成功返回(dict, None)，不是目标文章/解析不了返回(None, 原因)。"""
    title, content = str(title or ""), str(content or "")
    if any(w in title or w in content for w in ("原油", "基差")):
        return None, "原油基差竞价(卖的是大豆原油，不是大豆)"
    m = re.search(r"计划拍卖.{0,25}?(?<![\d.])(\d+\.?\d*)吨", content)
    if not m:
        return None, "没有'计划拍卖X吨'(不是拍卖结果文章，比如交易公告)"
    planned_t = float(m.group(1))
    sold = re.search(r"(?:最终|实际)成交(?:量)?(?:为)?(?<![\d.])(\d+\.?\d*)吨", content)
    rate = re.search(r"成交率(?:为)?(\d+\.?\d*)%", content)
    sold_t = float(sold.group(1)) if sold else None
    rate_v = float(rate.group(1)) if rate else None
    if sold_t is None and rate_v is None:
        if "流拍" in content or "未达成" in content:
            sold_t, rate_v = 0.0, 0.0
        else:
            return None, "没有成交量/成交率，看不出成交结果"
    if planned_t <= 0:
        return None, "计划拍卖量为0"
    if sold_t is None:
        sold_t = round(planned_t * rate_v / 100.0, 3)
    if rate_v is None:
        rate_v = round(sold_t / planned_t * 100.0, 2)
    if sold_t > planned_t * 1.001 or abs(sold_t / planned_t * 100.0 - rate_v) > 1.0:
        return None, f"成交量{sold_t:g}吨/计划{planned_t:g}吨算出的成交率跟文中的{rate_v:g}%对不上，可能取错了数"
    # 拍卖日期：优先正文里第一个"YYYY年M月D日"，没有就用标题里的"M月D日"+按发布日期推断年份
    dm = _RESERVE_DATE_RE.search(content)
    try:
        if dm:
            auction_date = _date_cls(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
        else:
            tm = _RESERVE_TITLE_MD_RE.search(title)
            if not tm:
                return None, "找不到拍卖日期"
            cand = _date_cls(pub_date.year, int(tm.group(1)), int(tm.group(2)))
            auction_date = cand if cand <= pub_date else _date_cls(pub_date.year - 1, cand.month, cand.day)
    except ValueError:
        return None, "拍卖日期无效"
    planned_wan, sold_wan = round(planned_t / 10000.0, 2), round(sold_t / 10000.0, 2)
    if _plausibility_problem("reserveAuction", planned_wan):
        return None, _plausibility_problem("reserveAuction", planned_wan)
    # 价格(参考信息)：超出合理范围的价格只丢掉价格本身，不丢整条
    avg = re.search(r"成交均价(\d+\.?\d*)元/吨", content)
    rng = re.search(r"(起拍价区间|成交价格区间|价格区间)为(\d+\.?\d*)(?:元/吨)?(?:至|-|－)(\d+\.?\d*)元/吨", content)
    base = re.search(r"竞拍底价(\d+\.?\d*)元/吨，最高价(\d+\.?\d*)元/吨", content)
    price_low = price_high = avg_price = None
    price_kind = None
    if rng:
        price_low, price_high, price_kind = float(rng.group(2)), float(rng.group(3)), rng.group(1)
    elif base:
        price_low, price_high, price_kind = float(base.group(1)), float(base.group(2)), "底价~最高价"
    if avg:
        avg_price = float(avg.group(1))
    if any(v is not None and _plausibility_problem("soyAuctionPrice", v) for v in (price_low, price_high, avg_price)):
        price_low = price_high = avg_price = price_kind = None
    return {
        "auctionDate": auction_date, "plannedWan": planned_wan, "soldWan": sold_wan, "soldRate": round(rate_v, 2),
        "avgPrice": avg_price, "priceLow": price_low, "priceHigh": price_high, "priceKind": price_kind,
    }, None


def fetch_mysteel_reserve_auction(today=None):
    """通过Mysteel文章搜索"进口大豆竞价销售结果"(中储粮国储进口大豆拍卖)，翻页收齐后取拍卖日期最新的一次。
    自动填入的是计划拍卖量(万吨)，成交量/成交率/成交价格作为参考信息。today参数只给测试用。"""
    if today is None:
        now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
        today = now_bj.date()
    else:
        now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    start_bj = now_bj - timedelta(days=365)  # 跟用户抓包的请求一致(2025-09-28到2026-09-28)
    headers = {
        "token": "-1",
        "Origin": "https://search.mysteel.com",
        "Referer": "https://search.mysteel.com/fastcomment.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    page_size, max_pages = 20, 8  # 实测total=115(6页)，上限放到8页(160条)留余量
    by_date = {}  # 拍卖日期 -> (发布日期, 解析结果, item)：同一次拍卖有多篇文章时取发布最晚的
    items_checked = 0
    skipped = []
    first_item = None

    for page in range(1, max_pages + 1):
        payload = {
            "query": "进口大豆竞价销售结果",
            "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
            "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"),
            "sortType": "complex",
            "platform": "pc",
            "pageNo": page,
            "pageSize": page_size,
        }
        data, debug = fetch_json_debug(MYSTEEL_ARTICLE_SEARCH_URL, headers=headers, post_data=payload)
        if data is None or not isinstance(data, dict) or data.get("resultCode") != 0:
            if page == 1:
                if data is None:
                    return {"available": False, "reason": "Mysteel文章搜索接口无返回数据", "debug": debug}
                return {"available": False,
                        "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
                        "debug": {"rawSnippet": debug.get("rawSnippet")}}
            break
        data_list = data.get("dataList") or []
        if page == 1 and not data_list:
            return {"available": False, "reason": "搜索结果为空(最近一年内没有匹配的文章)", "debug": {"total": data.get("total")}}
        for item in data_list:
            if not isinstance(item, dict):
                continue
            items_checked += 1
            if first_item is None:
                first_item = item
            try:
                pub_date = datetime.strptime(str(item.get("publishTime", ""))[:10], "%Y-%m-%d").date()
            except ValueError:
                pub_date = today
            parsed, why = _parse_reserve_auction(item.get("title"), item.get("content"), pub_date)
            if parsed is None:
                if "计划拍卖" not in why and len(skipped) < 8:  # 交易公告太多，不记；只记有价值的排除原因
                    skipped.append(f"{str(item.get('title'))[:30]}: {why}")
                continue
            if parsed["auctionDate"] > today:
                continue  # 拍卖日期在未来，不可能有结果
            key = parsed["auctionDate"]
            if key not in by_date or pub_date >= by_date[key][0]:
                by_date[key] = (pub_date, parsed, item)
        total = data.get("total") or 0
        if len(data_list) < page_size or page * page_size >= total:
            break

    if not by_date:
        return {"available": False,
                "reason": "搜索结果里没有一篇能解析出'计划拍卖X吨…成交率X%'的拍卖结果文章(可能措辞变了，或者最近没有拍卖)",
                "debug": {"itemsChecked": items_checked, "skipped": skipped, "firstItemSample": first_item}}

    dates = sorted(by_date, reverse=True)
    pub_date, latest, item = by_date[dates[0]]
    age = (today - latest["auctionDate"]).days
    if age > RESERVE_MAX_AGE_DAYS:
        return {"available": False,
                "reason": (f"最近一次拍卖是{age}天前({latest['auctionDate'].isoformat()})，超过{RESERVE_MAX_AGE_DAYS}天的新鲜度限制，"
                           f"可能国储已暂停拍卖；为避免把旧数据当成最近一次，不采用"),
                "debug": {"latestAuctionDate": latest["auctionDate"].isoformat(), "plannedWan": latest["plannedWan"], "itemsChecked": items_checked}}

    previous = None
    if len(dates) > 1:
        pd_, prev, _ = by_date[dates[1]]
        previous = {"auctionDate": prev["auctionDate"].isoformat(), "plannedWan": prev["plannedWan"],
                    "soldWan": prev["soldWan"], "soldRate": prev["soldRate"], "avgPrice": prev["avgPrice"]}
    return {
        "available": True,
        "value": latest["plannedWan"],          # 自动填入m_reserve的是计划拍卖量(万吨)
        "auctionDate": latest["auctionDate"].isoformat(),
        "ageDays": age,
        "plannedWan": latest["plannedWan"],
        "soldWan": latest["soldWan"],
        "soldRate": latest["soldRate"],
        "avgPrice": latest["avgPrice"],
        "priceLow": latest["priceLow"], "priceHigh": latest["priceHigh"], "priceKind": latest["priceKind"],
        "previous": previous,
        "auctionsSeen": len(dates),
        "date": pub_date.isoformat(),
        "articleTitle": item.get("title"),
        "source": "Mysteel文章(中储粮进口大豆竞价销售结果)",
        "sourceUrl": item.get("url") or "https://search.mysteel.com/fastcomment.html",
    }


# ---------------------------------------------------------------------------
# 全国主要市场豆粕现货基差：改用Mysteel文章搜索(每日一篇"全国主要市场豆粕基差价格汇总")。
#
# ★用户提出"要不要分沿海/内陆区域平均或加权"，先研究了用户文档里的20条真实正文和讨论——
#   现有UI标签本身写的是"全国平均"，计分逻辑只看正负号；用户在讨论里也承认"全国平均"这个
#   概念本身有点模糊(基差正负是"地点和强弱的标签"，不是"多空对错")。逐城市完整解析、按沿海/
#   内陆分组算平均，在这个数据源的自然语言表达方式下不现实——20条真实正文里，同一天最多
#   20多个城市，但经常只有5-8个给了确切数值，其余全是"多地基差为负值"这种模糊描述，逐城市
#   解析的可靠性会远低于之前做过的任何一个指标。
# ★最终跟用户确认的方案(方案A)：不分区，只抓**沿海代表城市**的基差当全国代理指标——理由是
#   "全国豆粕定价的核心锚在沿海"(用户讨论里的原话)，且沿海城市的确切数值出现频率相对更高。
#   按优先级依次尝试"日照(山东，最核心的沿海压榨基地)→南通→东莞→湛江→防城港→厦门→天津"，
#   取清单里第一个能在文章里找到**确切数值**(不是范围、不是只有涨跌幅度)的城市。
#
# ★同一句话里，同一个城市的基差可能是：确切值("日照-70")、范围("日照…均为-70至-80")、
#   共享值("日照、湛江、东莞均为-90")、"最低/最高"修饰("防城港最低为-80")、纯变动量没有
#   基准值("日照…上涨20")——只接受前三种能给出确切数值的写法，范围和纯变动量一律跳过、
#   尝试清单里下一个城市。这个正则设计(见MYSTEEL_BASIS_CITY_PATTERN_TMPL)拿用户提供的
#   20条真实正文全部逐条手算验证过：17/20天能提取出确切值且完全正确，另外3天(9-22/9-21/9-11)
#   原文本身没有给出任何沿海候选城市的确切数值(不是正则的问题)，属于数据源本身的局限，诚实报告。
#
# ★"最新一篇解析失败"时不直接放弃：往前找最近几篇(最多7篇)里第一个能提取出确切值的——
#   20条真实样本里有连续两天(9-22、9-21)都没有确切值，如果只看"最新一篇"，失败率会不必要地
#   偏高；往前找几天内最近一个能用的值更稳健，结果里会诚实标注"实际用的是哪天的数据"，跟
#   最新一篇的发布日期不一样时会提示滞后了几天。
BASIS_MAX_AGE_DAYS = 7  # 每日更新，实测最大发布间隔4天(周末/节假日)，留一些余量
BASIS_FALLBACK_LOOKBACK = 7  # 最新一篇解析失败时，最多往前找几篇
_BASIS_ALL_CITIES = ["长春", "大连", "昆明", "成都", "西安", "日照", "湛江", "东莞", "南通",
                     "防城港", "天津", "沧州", "周口", "厦门", "南昌", "武汉", "重庆", "岳阳"]
_BASIS_COASTAL_PRIORITY = ["日照", "南通", "东莞", "湛江", "防城港", "厦门", "天津"]
_BASIS_CHANGE_WORDS = ("涨", "跌", "升", "降", "增", "减")


def _find_city_basis(content, city):
    """在content里找city紧跟着的确切基差数值(不是范围、不是纯变动量)。城市名后面允许用
    "、/，/及"连接其他已知城市名(共享同一个值)，再接"(基差)?(最低|最高)?[，,]?(均为|为|低至|达)?"
    这几种连接词组合，最后是数字。数字后面紧跟"至/-数字"说明是范围，拒绝。"""
    others = "|".join(sorted([c for c in _BASIS_ALL_CITIES if c != city], key=len, reverse=True))
    pat = re.compile(rf"{re.escape(city)}((?:[、，及](?:{others}))*)(基差)?(最低|最高)?[，,]?(均为|为|低至|达)?(-?\d)")
    for m in pat.finditer(content):
        gap = m.group(1) or ""
        if any(w in gap for w in _BASIS_CHANGE_WORDS):
            continue
        num_start = m.start(5)
        num_str = re.match(r"-?\d+\.?\d*", content[num_start:]).group(0)
        num_end = num_start + len(num_str)
        if re.match(r"^(至|-\d|－\d|~\d)", content[num_end:num_end + 3]):
            continue  # 后面紧跟"至-80"这种，是范围不是确切值
        return float(num_str)
    return None


def _extract_basis_from_article(content):
    """按沿海优先级依次尝试，返回(城市, 数值)或(None, None)。"""
    for city in _BASIS_COASTAL_PRIORITY:
        v = _find_city_basis(content, city)
        if v is not None:
            return city, v
    return None, None


def parse_basis_table(text):
    """解析《全国主要市场豆粕基差价格汇总》正文里的数据表。真实正文长这样(2026-10-08 回填报告里的 bodyFailures，逐字)：
        ...智能摘要 内容由AI生成 2026年8月11日，...。 省份 市场 期货合约 现货基差 涨跌 云南 昆明 09 60 0 吉林 长春 09 110 20 ... 山东 日照 09 -90 20 广东 湛江 ...
    每行：省份 市场 期货合约(两位月份) 现货基差 涨跌(都是整数，可负)。返回 {市场: {value, change, contract}}。
    页面顶部那段"智能摘要 内容由AI生成"只是这张表的AI概括(线上抓取用的就是它，之前的回填也是)，表才是权威数据；表里每天都有日照，选城市不再每天切换。
    只认"市场名(已知城市) 两位合约 整数 整数"，纯文字里的数字不会被误读；缺涨跌列/基差不是数字的残缺行跳过。"""
    out = {}
    if not text:
        return out
    cities = "|".join(sorted(_BASIS_ALL_CITIES, key=len, reverse=True))
    # 不要求城市名前面不是汉字：省份和市场粘在一起写("山东日照 09 -90 20")也要能读；真正的约束是后面必须紧跟"两位合约 整数 整数"
    for m in re.finditer(rf"({cities})\s+(\d{{2}})\s+(-?\d+)\s+(-?\d+)(?!\d)", str(text)):
        city = m.group(1)
        if city not in out:
            out[city] = {"value": float(m.group(3)), "change": float(m.group(4)), "contract": m.group(2)}
    return out


def basis_from_table(text):
    """表里按沿海城市优先级(日照/南通/东莞/湛江/防城港/厦门/天津)取第一个有数值的，返回 (城市, 基差, 合约月份)；取不出返回 (None, None, None)。
    只用沿海城市(不拿内陆凑)；合理范围与线上一致(meaBasis)，超出就当没有。"""
    t = parse_basis_table(text)
    for city in _BASIS_COASTAL_PRIORITY:
        r = t.get(city)
        if r is not None and not _plausibility_problem("meaBasis", r["value"]):
            return city, r["value"], r["contract"]
    return None, None, None


SPOT_BASIS_SYMBOL = "M"
SPOT_BASIS_DEADLINE_S = 45          # 单次抓取的硬性时限(秒)
SPOT_BASIS_TOLERANCE = 1.5          # 自算基差与站点基差相差小于这个数才算一致(四舍五入级别)
SPOT_BASIS_PUBLISH_AFTER = (18, 30)  # 生意社当天的数据收盘后才有；这之前不试当天(白等会拖慢每小时的抓取)。★这个时间是我的假设，没有核实站点的实际更新时间


def _run_with_deadline(fn, seconds):
    """在守护线程里执行 fn，最多等 seconds 秒。返回 (True, 结果) 或 (False, 原因)。
    ★为什么需要：akshare 的 futures_spot_price 内部是 while True 循环——页面加载成功但日期对不上时只 sleep(3) 就继续、不累计失败次数，
    可能长时间不返回；线上每小时抓取一旦卡在这里会拖垮整批数据源。守护线程超时就放弃这次调用(不会阻塞进程退出)。"""
    box = {}

    def target():
        try:
            box["v"] = fn()
        except Exception as e:  # noqa: BLE001
            box["e"] = e

    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(seconds)
    if th.is_alive():
        return False, f"超时(>{seconds}秒)，已放弃这次调用"
    if "e" in box:
        return False, f"{type(box['e']).__name__}: {box['e']}"
    return True, box.get("v")


def _spot_num(x):
    try:
        if x is None:
            return None
        if isinstance(x, str):
            x = x.replace(",", "").strip()
        v = float(x)
        return v if v == v and abs(v) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _spot_col(df, names):
    for n in names:
        if n in df.columns:
            return n
    return None


def parse_spot_basis(df, var=SPOT_BASIS_SYMBOL):
    """解析 ak.futures_spot_price(date, vars_list=['M']) 的返回(生意社 100ppi.com/sf/)。返回 (结果, 原因)：成功 (dict, None)，失败 (None, 原因)。
    ★基差自己算：基差 = 现货价 - 主力合约结算价，现货高于期货为正(与页面'正基差偏多/负基差偏空'的符号一致)；
    站点自己给的 dom_basis 只用来核对(**符号相反，取反后**差距≥1.5 标 consistent=False)，不当数据用。
    ★真实列名(读 akshare 1.19.1 源码确认)：symbol/spot_price/dominant_contract/dominant_contract_price/near_contract/near_contract_price/dom_basis…；函数 docstring 写的
    var/sp/dom_price/dom_symbol 是过时的——两套都兼容。主力合约代码是 akshare 处理后的小写带品种前缀(m2701)。
    sp 的口径文档只写'现货价格'(生意社的商品现货价，通常是它自己的基准价，是否全国综合没有明确说明)。"""
    if df is None or len(df) == 0:
        return None, "没有返回数据(非交易日、数据还没发布或被站点限流)"
    vc = _spot_col(df, ("var", "symbol"))
    if vc is None:
        return None, "返回的表里没有品种列(var/symbol)，接口可能改了字段"
    sub = df[df[vc].astype(str).str.upper().str.strip() == var]
    if len(sub) == 0:
        return None, f"返回的表里没有{var}(豆粕)这一行"
    r = sub.iloc[0]

    def g(*names):
        c = _spot_col(df, names)
        return r[c] if c is not None else None

    sp, dp = _spot_num(g("sp", "spot_price")), _spot_num(g("dom_price", "dominant_contract_price"))
    if sp is None or sp <= 0:
        return None, f"现货价缺失或不是正数({g('sp', 'spot_price')!r})"
    if dp is None or dp <= 0:
        return None, f"主力合约结算价缺失或不是正数({g('dom_price', 'dominant_contract_price')!r})"
    for label, v in (("现货价", sp), ("主力合约结算价", dp)):
        problem = _plausibility_problem("spotMealPrice", v)
        if problem:
            return None, f"{label}{problem}"
    value = round(sp - dp, 2)
    problem = _plausibility_problem("spotBasis", value)
    if problem:
        return None, f"自算基差{problem}(现货{sp}-主力{dp})"
    # ★符号：akshare 的 dom_basis = dominant_contract_price − spot_price(期货−现货，'期现价差')，与本页面的约定(基差=现货−期货，现货升水为正)**相反**
    #   (读 akshare 1.19.1 源码 _check_information 确认)。所以取反后才能和自算的核对，并且带出去的 siteBasis 也是取反后的(页面约定的符号)——
    #   否则用真实数据时每一天都会报'站点基差与自算不一致'(自算-72，站点+72)，页面天天一条假警告。
    site_raw = _spot_num(g("dom_basis", "dominant_basis"))
    site = (-site_raw if site_raw is not None else None)
    if site is not None and site == 0:
        site = 0.0      # 避免 -0.0
    diff = round(value - site, 2) if site is not None else None
    dom_sym, near_sym = g("dom_symbol", "dominant_contract"), g("near_symbol", "near_contract")
    return {"value": value, "spot": sp, "domPrice": dp, "domSymbol": (str(dom_sym) if dom_sym is not None and dom_sym == dom_sym else None),
            "nearSymbol": (str(near_sym) if near_sym is not None and near_sym == near_sym else None), "nearPrice": _spot_num(g("near_price", "near_contract_price")),
            "siteBasis": site, "siteDiff": diff, "consistent": (None if diff is None else abs(diff) < SPOT_BASIS_TOLERANCE)}, None


def _spot_candidate_dates(now_bj, n=4):
    """要尝试的交易日(从新到旧)，休市日跳过。北京时间 18:30 之前不试当天(站点收盘后才有)。"""
    import cn_calendar
    d = now_bj.date()
    if (now_bj.hour, now_bj.minute) < SPOT_BASIS_PUBLISH_AFTER:
        d -= timedelta(days=1)
    out, steps = [], 0
    while len(out) < n and steps < 40:
        if cn_calendar.dce_is_trading_day(d):
            out.append(d)
        d -= timedelta(days=1)
        steps += 1
    return out


def _akshare_spot_price(d_iso):
    """调用 ak.futures_spot_price(日期, vars_list=['M'])。akshare 没有超时参数，用 socket 默认超时间接限制(用完恢复，这是进程级设置)。
    返回 DataFrame(可能为空)；akshare 未安装/调用抛异常会向上抛，由调用方(_run_with_deadline)接住。"""
    import akshare as ak
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(15)
    try:
        return ak.futures_spot_price(d_iso, vars_list=[SPOT_BASIS_SYMBOL])
    finally:
        socket.setdefaulttimeout(old)


def fetch_spot_basis(now_bj=None, fetch=None, deadline_s=SPOT_BASIS_DEADLINE_S, max_attempts=4):
    """现货基差(生意社现货价 - 主力合约结算价，自己算)。从最近的交易日往前最多试 max_attempts 个，第一个取到的就用；
    每次抓取有硬性时限；任何异常/空表/没有豆粕行都不崩，诊断里逐日写明原因。fetch(日期iso) -> DataFrame，默认走 akshare，测试可注入。"""
    if now_bj is None:
        now_bj = (datetime.now(timezone.utc) + timedelta(hours=8)).replace(tzinfo=None)
    fetch = fetch or _akshare_spot_price
    cands = _spot_candidate_dates(now_bj, max_attempts)
    attempted = []
    for d in cands:
        ok_, res = _run_with_deadline(lambda d=d: fetch(d.isoformat()), deadline_s)
        if not ok_:
            attempted.append(f"{d.isoformat()}: {res}")
            continue
        parsed, why = parse_spot_basis(res)
        if parsed is None:
            attempted.append(f"{d.isoformat()}: {why}")
            continue
        return {"available": True, "value": parsed["value"], "date": d.isoformat(), "spot": parsed["spot"], "domSymbol": parsed["domSymbol"], "domPrice": parsed["domPrice"],
                "nearSymbol": parsed["nearSymbol"], "nearPrice": parsed["nearPrice"], "siteBasis": parsed["siteBasis"], "siteDiff": parsed["siteDiff"], "consistent": parsed["consistent"],
                "usedFallback": d != cands[0], "fallbackDays": (cands[0] - d).days, "ageDays": (now_bj.date() - d).days,
                "source": "生意社(100ppi.com)豆粕现货价 − 主力合约结算价，自行计算(AKShare futures_spot_price)",
                "sourceUrl": f"https://www.100ppi.com/sf/day-{d.isoformat()}.html",
                "spotDefinition": "生意社现货价(口径文档未明确，疑为多地综合的基准价)；主力合约是生意社认定的，可能与页面选的合约月份不同，主力换月处基差会有断层"}
    return {"available": False, "reason": f"最近{len(cands)}个交易日都没取到豆粕现货基差(生意社)", "debug": {"attempted": attempted}}


BASIS_LIVE_MAX_BODY_FETCHES = 2      # 线上每次运行最多请求几篇正文(每小时一次，不能拖慢整批抓取)


def fetch_basis_page(url, title, fetch=None):
    """抓一篇《全国主要市场豆粕基差价格汇总》并读出数据表所在的文字。线上抓取和回填共用，两处口径不会分叉。
    返回 {ok, err, text, where, diag}：where='region'(表在正文区域里)/'page'(只有整页文字里才有)/None(没读到表)；text 是 basis_from_table 该读的那段文字。
    ★为什么要整页兜底：正文区域取"标题最后一次出现"到"第一个免责声明"之间，页面里推荐区重复了同一个标题、或表在免责声明之后，区域里就没有表了
    (2026-10-08 回填：735个日期里只有24个读到表。这是对原因的推测，没有原始网页可验证)。表行的格式很严(城市 两位合约 整数 整数)，整页文字里不会误中。
    没读到表时 diag 给出定位原因所需的信息(table标签数、图片数、有没有'现货基差'表头及其后300字、标题出现次数、免责声明位置、各段长度)。绝不抛异常。"""
    fetch = fetch or fetch_text_debug
    try:
        raw, dbg = fetch(url, headers={"Referer": "https://ncp.mysteel.com/"}, retries=2, timeout=12)
    except Exception as e:  # noqa: BLE001 - 线上抓取不能被这一步拖垮
        return {"ok": False, "err": f"正文请求异常: {type(e).__name__}: {e}", "text": "", "where": None, "diag": {}}
    if not raw:
        return {"ok": False, "err": f"正文请求失败({(dbg or {}).get('error') or (dbg or {}).get('httpStatus') or '无返回'})", "text": "", "where": None, "diag": {}}
    full = _html_to_text(raw)
    region = _extract_article_region(full, title)
    for where, text in (("region", region), ("page", full)):
        if parse_basis_table(text):
            return {"ok": True, "err": None, "text": text, "where": where, "diag": {}}
    hi = full.find("现货基差")
    diag = {"rawLen": len(raw), "fullLen": len(full), "regionLen": len(region), "tableTags": len(re.findall(r"(?i)<table", raw)), "imgTags": len(re.findall(r"(?i)<img", raw)),
            "titleCount": full.count(title) if title else 0, "disclaimerAt": full.find("免责声明"), "headerSeen": hi >= 0, "afterHeader": full[hi:hi + 300] if hi >= 0 else "",
            "regionHead": region[:400]}
    return {"ok": True, "err": None, "text": region, "where": None, "diag": diag}


def fetch_mysteel_basis(today=None, fetch_page=None):
    """通过Mysteel文章搜索"全国主要市场豆粕基差价格汇总"(每日一篇)，从最新几篇里找第一篇能
    解析出沿海代表城市确切基差的，作为全国基差的代理值。today参数只给测试用。"""
    if today is None:
        now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
        today = now_bj.date()
    else:
        now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    start_bj = now_bj - timedelta(days=365)
    headers = {
        "token": "-1",
        "Origin": "https://search.mysteel.com",
        "Referer": "https://search.mysteel.com/fastcomment.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    page_size, max_pages = 20, 5
    all_items = []
    items_checked = 0
    first_item = None

    for page in range(1, max_pages + 1):
        payload = {
            "query": "全国主要市场豆粕基差价格汇总",
            "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
            "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"),
            "sortType": "complex",
            "platform": "pc",
            "pageNo": page,
            "pageSize": page_size,
        }
        data, debug = fetch_json_debug(MYSTEEL_ARTICLE_SEARCH_URL, headers=headers, post_data=payload)
        if data is None or not isinstance(data, dict) or data.get("resultCode") != 0:
            if page == 1:
                if data is None:
                    return {"available": False, "reason": "Mysteel文章搜索接口无返回数据", "debug": debug}
                return {"available": False,
                        "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
                        "debug": {"rawSnippet": debug.get("rawSnippet")}}
            break
        data_list = data.get("dataList") or []
        if page == 1 and not data_list:
            return {"available": False, "reason": "搜索结果为空(最近一年内没有匹配的文章)", "debug": {"total": data.get("total")}}
        for item in data_list:
            if not isinstance(item, dict):
                continue
            items_checked += 1
            if first_item is None:
                first_item = item
            try:
                pub_date = datetime.strptime(str(item.get("publishTime", ""))[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if pub_date > today:
                continue
            all_items.append((pub_date, item))
        total = data.get("total") or 0
        if len(data_list) < page_size or page * page_size >= total:
            break

    if not all_items:
        return {"available": False,
                "reason": "搜索结果里没有一篇带有效发布日期的基差汇总文章",
                "debug": {"itemsChecked": items_checked, "firstItemSample": first_item}}

    all_items.sort(key=lambda x: x[0], reverse=True)
    latest_date = all_items[0][0]
    attempted = []
    fetch_page = fetch_page or fetch_basis_page
    bodies_used = 0
    for pub_date, item in all_items[:BASIS_FALLBACK_LOOKBACK]:
        content = str(item.get("content") or "")
        city, value = _extract_basis_from_article(content)
        src, contract = "summary", None
        # ★表优先：正文底下的数据表是权威数据(表里每天都有日照，城市固定)，页面顶部的AI智能摘要只是概括。
        #   读不到表(请求失败/没有表/抛异常)就退回摘要，行为与以前一致；每次运行最多请求 BASIS_LIVE_MAX_BODY_FETCHES 篇正文。
        url = str(item.get("url") or "")
        if bodies_used < BASIS_LIVE_MAX_BODY_FETCHES and url and is_trusted_article_url(url):
            bodies_used += 1
            try:
                page = fetch_page(url, str(item.get("title") or ""))
                if page and page.get("ok"):
                    t_city, t_val, t_contract = basis_from_table(page.get("text") or "")
                    if t_val is not None:
                        city, value, src, contract = t_city, t_val, "table", t_contract
            except Exception:  # noqa: BLE001 - 读表只是增强，失败就用摘要
                pass
        if value is None:
            attempted.append(pub_date.isoformat())
            continue
        if _plausibility_problem("meaBasis", value):
            attempted.append(f"{pub_date.isoformat()}({city}={value:g}超出合理范围)")
            continue
        age = (today - pub_date).days
        if age > BASIS_MAX_AGE_DAYS:
            return {"available": False,
                    "reason": f"最近能解析出基差的一篇也是{age}天前({pub_date.isoformat()})的，超过{BASIS_MAX_AGE_DAYS}天的新鲜度限制，不采用",
                    "debug": {"latestArticleDate": latest_date.isoformat(), "attempted": attempted, "itemsChecked": items_checked}}
        return {
            "available": True,
            "value": value,
            "city": city,
            "date": pub_date.isoformat(),
            "latestArticleDate": latest_date.isoformat(),
            "usedFallback": pub_date != latest_date,
            "fallbackDays": (latest_date - pub_date).days,
            "articleTitle": item.get("title"),
            "src": src,
            "contract": contract,
            "source": f"Mysteel文章(全国主要市场豆粕基差价格汇总，{city}代表沿海" + ("，读正文数据表)" if src == "table" else "，AI摘要)"),
            "sourceUrl": item.get("url") or "https://search.mysteel.com/fastcomment.html",
        }

    return {
        "available": False,
        "reason": f"最近{len(attempted)}篇文章里，沿海代表城市(日照/南通/东莞/湛江/防城港/厦门/天津)都没有给出确切数值(可能都是模糊描述或范围)",
        "debug": {"latestArticleDate": latest_date.isoformat(), "attemptedDates": attempted, "itemsChecked": items_checked},
    }


# ---------------------------------------------------------------------------
# 猪粮比：用玄田数据(中国养猪网旗下)的每日"生猪价格(外三元)"和"玉米价格"
# 两个序列自己计算——猪粮比 = 生猪价格(元/公斤) ÷ 玉米价格(元/公斤)。
#
# ★这次的方案来自用户提供的技术文档，但文档里有两处经核对后不采用/修正：
#   ① 文档给的"占位请求体 type=1&days=365"是错的(15个字符，跟文档自己说的
#      抓包content-length:28对不上)。akshare源码里的真实参数是
#      ptype=X&areano=-1&datetype=0，恰好28个字符——跟抓包互相印证。
#   ② 文档说"生猪价格和玉米价格在同一个响应里(pigprice/pricedate/maizeprice
#      三个字段)"，被akshare源码否定：getzhujiahitsdata每个ptype只返回一个
#      序列(值+日期两列)——外三元是ptype=1、玉米是ptype=4，要请求两次。
#   文档里对的部分：接口就是getzhujiahitsdata；猪粮比=生猪价÷玉米价(玉米
#   元/吨要除以1000)；用户截图里2026-09-27的10.37÷2.358=4.40跟页面一致。
#
# ★不自己重新实现HTTP/JSON解析，直接调用akshare已经封装好的
#   futures_hog_core("外三元")(ptype=1)和futures_hog_cost("玉米")(ptype=4)，
#   复用_fetch_akshare_hog_df里已有的超时+重试。两个序列的最新日期不一定
#   相同，所以取两边**共同的最新一天**来算，不假设最后一行就是同一天。
def _hog_series_to_dict(df):
    """把akshare返回的[date, value]两列DataFrame转成{'YYYY-MM-DD': float}，
    丢掉日期解析失败(NaT/None)或数值为NaN的行——akshare内部用
    errors="coerce"转换，异常行会变成NaT/NaN而不是报错。"""
    import re as _re
    out = {}
    for d, v in zip(df["date"], df["value"]):
        key = str(d)
        if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", key):
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv != fv:  # NaN
            continue
        out[key] = fv
    return out


HOG_SERIES_KEEP_DAYS = 1100      # 线上每次抓取带出的猪粮比历史最多保留最近这么多天(约3年)，防止历史文件无限变大


def hog_ratio_at(pig_price, corn_price):
    """单个日期的猪粮比 = 外三元生猪价(元/公斤) ÷ 玉米价(元/公斤)。返回 (ratio, kind, detail)：
    成功 (ratio, None, None)；失败 (None, kind, 说明)，kind ∈ corn_nonpositive / range / plausibility。
    fetch_hog_ratio(取最新一天)和 hog_ratio_points(取全部共同日期，回填用)共用这一个函数，两处口径不会分叉。"""
    # 玉米价格正常是元/吨(2358这种量级)；如果哪天接口改成元/公斤(2.358这种量级)，不再除以1000，避免算出一个小1000倍的荒谬结果。
    corn_per_kg = corn_price / 1000.0 if corn_price > 100 else corn_price
    if not (corn_per_kg > 0):
        return None, "corn_nonpositive", f"玉米价格异常({corn_price})，没法计算猪粮比"
    ratio = round(pig_price / corn_per_kg, 2)
    # 单位/字段搞错时(比如取错了序列)算出来的结果会离谱，宁可不展示也不展示错数字
    if not (1.0 <= ratio <= 20.0):
        return None, "range", f"计算出的猪粮比{ratio}超出合理范围(1~20)，可能是单位或字段对错了"
    for key, val, label in (("pigPrice", pig_price, "生猪价格"), ("cornPricePerTon", corn_per_kg * 1000.0, "玉米价格")):
        problem = _plausibility_problem(key, val)
        if problem:
            return None, "plausibility", f"{label}{problem}，可能取错了序列或单位变了"
    return ratio, None, None


def hog_ratio_points(pig, corn):
    """pig/corn: {日期: 价格}。返回 (points, dropped)：points=[{d, v}]，所有'两个序列都有'的日期各算一个，按日期升序；
    每个日期独立校验，不合格的只丢这一个并记 {d, kind, reason}，不连累其他日期。点的结构与每天累积的完全一致(只有 d、v)。"""
    pts, dropped = [], []
    for d in sorted(set(pig) & set(corn)):
        r, kind, detail = hog_ratio_at(pig[d], corn[d])
        if r is None:
            dropped.append({"d": d, "kind": kind, "reason": detail})
        else:
            pts.append({"d": d, "v": r})
    return pts, dropped


def fetch_hog_ratio():
    """猪粮比：外三元生猪价格(元/公斤) ÷ 玉米价格(元/公斤)，取两个序列共同的
    最新一天。"""
    pig_df, err = _fetch_akshare_hog_df("外三元", func_name="futures_hog_core")
    if err:
        return {**err, "reason": f"生猪价格(外三元)获取失败: {err['reason']}"}
    corn_df, err = _fetch_akshare_hog_df("玉米", func_name="futures_hog_cost")
    if err:
        return {**err, "reason": f"玉米价格获取失败: {err['reason']}"}

    try:
        pig = _hog_series_to_dict(pig_df)
        corn = _hog_series_to_dict(corn_df)
    except (KeyError, TypeError) as e:
        return {
            "available": False,
            "reason": f"字段解析失败: {e}(接口可能改了字段名)",
            "debug": {"pigColumns": list(pig_df.columns), "cornColumns": list(corn_df.columns)},
        }

    common = sorted(set(pig) & set(corn))
    if not common:
        return {
            "available": False,
            "reason": "生猪价格和玉米价格没有任何共同的日期，没法计算猪粮比",
            "debug": {
                "pigLatestDate": max(pig) if pig else None, "pigRows": len(pig),
                "cornLatestDate": max(corn) if corn else None, "cornRows": len(corn),
            },
        }

    latest = common[-1]
    pig_price = pig[latest]
    corn_price = corn[latest]
    corn_per_kg = corn_price / 1000.0 if corn_price > 100 else corn_price
    ratio, kind, detail = hog_ratio_at(pig_price, corn_price)
    if ratio is None:
        # 报错文案和重构前逐字一致(已有测试依赖)；只是计算移到了共用函数里
        dbg = {"date": latest, "pigPrice": pig_price, "cornPrice": corn_price}
        if kind == "range":
            return {"available": False, "reason": detail, "debug": dbg}
        if kind == "plausibility":
            return {"available": False, "reason": detail, "debug": {**dbg, "ratio": round(pig_price / corn_per_kg, 2)}}
        return {"available": False, "reason": detail, "debug": dbg}
    return {
        "available": True,
        "value": ratio,
        "date": latest,
        "pigPrice": pig_price,
        "cornPricePerTon": round(corn_per_kg * 1000.0, 1),
        "pigLatestDate": max(pig),
        "cornLatestDate": max(corn),
        # ★数据源每次返回的是整段历史：带出来由 history_store 记成 hog_ratio 序列(线上抓取成功一次，历史就补齐，不依赖一次手动回填)，
        #   记完从 latest.json 里去掉(和 CFTC 的156周明细一样)
        "seriesPoints": hog_ratio_points(pig, corn)[0][-HOG_SERIES_KEEP_DAYS:],
        "source": "玄田数据(中国养猪网)：外三元生猪价格÷玉米价格，自行计算",
        "sourceUrl": "https://zhujia.zhuwang.com.cn",
    }


# ---------------------------------------------------------------------------
# 能繁母猪存栏：改用Mysteel文章搜索(沿用开机率/库存等指标的同一套思路)，不再用
# akshare/玄田数据——那条线停在2025年10月，滞后近一年。
#
# ★这个指标是**季度末**数据：Mysteel文章里写的是"二季度末能繁母猪存栏3780万头"
#   这种说法(用户提供的真实响应样本，2026-09-24发布)。所以查找逻辑跟前面的
#   日度/周度指标不一样：不是"取最新一篇文章里的数"，而是把搜到的所有文章里
#   提到的(年份, 季度, 存栏量)都收集起来，取**最新的一个季度末**——同一年里
#   四季度比三季度新，四季度末数据发布之前，三季度末就是最新的(现在是2026年
#   9月底，最新就是2026年二季度末的3780万头)。同一季度被多篇文章提到时，取
#   发布时间最晚的那一篇。
#
# ★几个容易误判的陷阱(手算验证过)：
#   ① 年份：文章通常只写"二季度末"不写年份，按"季度末日期不能晚于发布日期"
#      推断——2026-09-24发布提到二季度末=2026年；2027-01发布提到四季度末=
#      2026年；2026-09-24发布提到三季度末=2025年(2026年三季度末9月30日还没到)。
#      文章里写了"2025年四季度末"这种显式年份就以显式为准。
#   ② 预测值：政策文章常见"预计四季度末能繁母猪存栏将降至XXXX万头"，不是实际
#      数据——匹配前面出现预计/预期/目标/调控/有望/将等词就丢掉；显式年份
#      的季度末如果比今天还晚(未来)也丢掉。
#   ③ 增减量："二季度末能繁母猪存栏较一季度末减少20万头"里的20万头是变动量
#      不是存栏量——数字前面的间隔里出现较/比/减/降/增/升等词就丢掉；另外存栏
#      量落在1000~10000万头之外的一律不认(能繁母猪合理范围约3000~4500)。
#
# ★第二版(用户贴了8条真实正文后重写)：第一版只用1条样本设计，要求"季度末"后面紧跟
#   "能繁母猪存栏"，拿8条真实文章一测只识别出3条——漏掉的5条写法各不相同：
#   ① 先写生猪总存栏再写"其中，能繁母猪存栏X"(隔了很远，样本2、4)；
#   ② "存栏量降至3904万头"——"降至"里的"降"字被"变动量过滤"误杀(样本5)；
#   ③ 顺序反过来："能繁母猪存栏自…，但2026年一季度末存栏量仍有3904万头"(样本7、8)。
#   现在改成以"季度末"为锚点，往后找数字，再判断数字属于谁(能繁母猪还是别的
#   指标)，并过滤变动量、基准值(3900万头的正常保有量)、预测值——8条真实样本
#   全部验证过，而且样本2里的"生猪存栏43680万头""肉牛出栏3564万头"这类
#   别的指标的数字不会被误认(3564万头在1000~10000范围内，只靠范围过滤挡不住，
#   靠的是"主语"判断)。
_SOW_QUARTER_MENTION = re.compile(r"(?:(\d{4})年)?第?([一二三四1-4])季度末")
_SOW_NUMBER = re.compile(r"(\d+\.?\d*)万头")
_SOW_OWNER_SOW = ("能繁母猪",)
_SOW_OWNER_OTHER = ("生猪存栏", "生猪出栏", "出栏", "猪肉", "牛羊", "肉牛", "牛肉", "牛奶", "仔猪", "后备母猪", "商品猪")
_SOW_BAD_PHRASE_WORDS = ("较", "比", "减", "降", "增", "升", "下滑", "回落", "高于", "低于", "超过", "不足", "设定", "正常", "合理")
_SOW_LEVEL_VERB = re.compile(r"(?:下降|上升|减少|增加|增长|回落|降|减|增|升)[至到]")
_SOW_FORECAST_WORDS = ("预计", "预期", "预测", "目标", "调控", "有望", "将", "计划", "力争", "拟")
_QUARTER_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "1": 1, "2": 2, "3": 3, "4": 4}
_QUARTER_END_MD = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
_SOW_WINDOW = 100


def _quarter_end_date(year, quarter):
    m, d = _QUARTER_END_MD[quarter]
    return _date_cls(year, m, d)


def _latest_completed_quarter(today):
    """今天为止最近一个已经结束的季度(年, 季)。2026-09-28 → (2026, 2)：三季度末9月30日还没到。"""
    for q in (4, 3, 2, 1):
        if _quarter_end_date(today.year, q) <= today:
            return (today.year, q)
    return (today.year - 1, 4)


def _previous_quarter(yq):
    y, q = yq
    return (y, q - 1) if q > 1 else (y - 1, 4)


def _infer_quarter_year(quarter, pub_date):
    """文章只写"X季度末"没写年份时，按"季度末日期不能晚于发布日期"推断年份。"""
    return pub_date.year if _quarter_end_date(pub_date.year, quarter) <= pub_date else pub_date.year - 1


def _sow_owner_at(sentence, pos):
    """pos之前最后出现的"主语"关键词属于哪一类：'sow'(能繁母猪)/'other'(生猪总存栏、
    出栏、肉牛等别的指标)/None。用来判断一个"XXXX万头"到底是不是能繁母猪的数。"""
    best_end, best = -1, None
    for kw in _SOW_OWNER_SOW:
        i = sentence.rfind(kw, 0, pos)
        if i != -1 and i + len(kw) > best_end:
            best_end, best = i + len(kw), "sow"
    for kw in _SOW_OWNER_OTHER:
        i = sentence.rfind(kw, 0, pos)
        if i != -1 and i + len(kw) > best_end:
            best_end, best = i + len(kw), "other"
    return best


def _extract_sow_candidates(text, pub_date, today):
    """从一段文本里提取所有(年份, 季度, 存栏量万头)候选。

    ★以"季度末"为锚点(不再要求"季度末"后面紧跟"能繁母猪存栏"——真实文章里有
    "三季度末，全国生猪存栏43680万头…其中，能繁母猪存栏4035万头"这种隔很远的写法，
    也有"能繁母猪存栏自…，但2026年一季度末存栏量仍有3904万头"这种顺序反过来的写法)：
    在同一个句子里，每个"季度末"提及往后(下一个提及之前，最多100字)找第一个合格的
    "XXXX万头"。合格 = ①这个数字的"主语"是能繁母猪(不是生猪总存栏/出栏/肉牛)；
    ②紧挨着它的那个短语里没有较/比/减/增/高于/设定/正常/合理这类变动量或基准值的词
    ("降至/增至/升至"这种"到达某个水平"的写法要放行)；③后面不是"…保有量"；
    ④没有预计/目标/将等预测词；⑤在1000~10000万头合理范围内；⑥季度末不在未来。"""
    out = []
    for sentence in re.split(r"[。\n；;]", text):
        mentions = list(_SOW_QUARTER_MENTION.finditer(sentence))
        for mi, m in enumerate(mentions):
            next_start = mentions[mi + 1].start() if mi + 1 < len(mentions) else len(sentence)
            seg_end = min(m.end() + _SOW_WINDOW, next_start)
            for n in _SOW_NUMBER.finditer(sentence, m.end(), seg_end):
                pos = n.start()
                if _sow_owner_at(sentence, pos) != "sow":
                    continue  # 这个数是生猪总存栏/出栏/肉牛等别的指标的
                phrase = re.split(r"[，,、%\s]", sentence[:pos])[-1][-14:]
                phrase = _SOW_LEVEL_VERB.sub("", phrase)  # "降至/增至"是到达某个水平，不是变动量
                if any(w in phrase for w in _SOW_BAD_PHRASE_WORDS):
                    continue  # 变动量(较上季度减少X)或基准值(高于X的合理保有量)
                if "保有量" in sentence[n.end():n.end() + 8]:
                    continue  # "3900万头的正常保有量"是基准值
                context = sentence[max(0, m.start() - 10):pos]
                if any(w in context for w in _SOW_FORECAST_WORDS):
                    continue  # 预测/目标值，不是实际数据
                value = float(n.group(1))
                if not (1000 <= value <= 10000):
                    continue
                quarter = _QUARTER_CN[m.group(2)]
                year = int(m.group(1)) if m.group(1) else _infer_quarter_year(quarter, pub_date)
                if _quarter_end_date(year, quarter) > today:
                    continue  # 季度末还没到，不可能是实际存栏数据
                out.append((year, quarter, value))
                break  # 一个季度末提及只取第一个合格的数字
    return out



def fetch_mysteel_sow_inventory(today=None):
    """通过Mysteel文章搜索"季度末能繁母猪存栏"，收集所有文章里提到的
    (年份, 季度, 存栏量)，取最新的一个季度末。

    ★新鲜度限制(用户指出的，之前漏掉了)：只接受"最近一个已完成季度"和它的上一个季度
    这两期。2026-09-28这天最近已完成的是2026年二季度末(三季度末9月30日还没到)，
    所以只接受二季度末，找不到才退到一季度末；2025年的数据一律不采用——宁可
    显示失败原因，也不能把陈年老数据当成最新值填进去。
    today参数只给测试用(固定"今天"让测试不随真实日期变化)，正式运行不传。"""
    if today is None:
        now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
        today = now_bj.date()
    else:
        now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    # ★回看一年：跟用户实际抓包验证过的请求保持一致(startTime=2025-09-27, endTime=2026-09-27，
    #   返回total=41)。之前写的150天没有被真实接口验证过，还会少看到去年的历史文章。
    start_bj = now_bj - timedelta(days=365)
    headers = {
        "token": "-1",
        "Origin": "https://search.mysteel.com",
        "Referer": "https://search.mysteel.com/fastcomment.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    page_size, max_pages = 20, 5  # 一年窗口实测41条(3页)，上限放到5页(100条)留余量
    candidates = []  # (year, quarter, pub_date, value, item)
    items_checked = 0
    first_item = None

    for page in range(1, max_pages + 1):
        payload = {
            "query": "季度末能繁母猪存栏",
            "startTime": start_bj.strftime("%Y-%m-%d 00:00:00"),
            "endTime": now_bj.strftime("%Y-%m-%d 23:59:59"),
            "sortType": "complex",
            "platform": "pc",
            "pageNo": page,
            "pageSize": page_size,
        }
        data, debug = fetch_json_debug(MYSTEEL_ARTICLE_SEARCH_URL, headers=headers, post_data=payload)
        if data is None or not isinstance(data, dict) or data.get("resultCode") != 0:
            if page == 1:
                if data is None:
                    return {"available": False, "reason": "Mysteel文章搜索接口无返回数据", "debug": debug}
                return {
                    "available": False,
                    "reason": f"接口返回异常(resultCode={data.get('resultCode') if isinstance(data, dict) else '未知'})",
                    "debug": {"rawSnippet": debug.get("rawSnippet")},
                }
            break  # 后面的页失败：用已经拿到的
        data_list = data.get("dataList") or []
        if page == 1 and not data_list:
            return {"available": False, "reason": "搜索结果为空(最近一年内没有匹配的文章)", "debug": {"total": data.get("total")}}
        for item in data_list:
            if not isinstance(item, dict):
                continue
            items_checked += 1
            if first_item is None:
                first_item = item
            try:
                pub_date = datetime.strptime(str(item.get("publishTime", ""))[:10], "%Y-%m-%d").date()
            except ValueError:
                pub_date = today
            for v in item.values():
                if not isinstance(v, str):
                    continue
                for year, quarter, value in _extract_sow_candidates(v, pub_date, today):
                    candidates.append((year, quarter, pub_date, value, item))
        total = data.get("total") or 0
        if len(data_list) < page_size or page * page_size >= total:
            break

    if not candidates:
        return {
            "available": False,
            "reason": "搜索结果里没有一条能提取出'X季度末能繁母猪存栏XXXX万头'这个格式(可能措辞变了，或者最新一季度的数据还没发布)",
            "debug": {"itemsChecked": items_checked, "firstItemSample": first_item},
        }

    quarters_seen = sorted({(c[0], c[1]) for c in candidates}, reverse=True)
    label = lambda yq: f"{yq[0]}年{'一二三四'[yq[1] - 1]}季度末"
    latest_done = _latest_completed_quarter(today)
    allowed = {latest_done, _previous_quarter(latest_done)}
    fresh = [c for c in candidates if (c[0], c[1]) in allowed]
    if not fresh:
        return {
            "available": False,
            "reason": (f"只找到了较旧的季度末数据(最新一期是{label(quarters_seen[0])})，已超出允许的滞后范围"
                       f"(今天最近已完成的季度是{label(latest_done)}，只接受{label(latest_done)}和"
                       f"{label(_previous_quarter(latest_done))})，为避免把旧数据当成最新值，不采用"),
            "debug": {"quartersSeen": [label(q) for q in quarters_seen], "itemsChecked": items_checked},
        }

    # 在允许的季度里取最新的季度末；同一季度被多篇文章提到时取发布最晚的那篇
    year, quarter, pub_date, value, item = max(fresh, key=lambda c: (c[0], c[1], c[2]))
    return {
        "available": True,
        "value": value,
        "quarterLabel": f"{year}年{'一二三四'[quarter - 1]}季度末",
        "quarterEnd": _quarter_end_date(year, quarter).isoformat(),
        "date": pub_date.isoformat(),
        "articleTitle": item.get("title"),
        "quartersSeen": [f"{y}年{'一二三四'[q - 1]}季度末" for y, q in quarters_seen],
        "source": "Mysteel文章(能繁母猪存栏，季度末数据)",
        "sourceUrl": item.get("url") or "https://search.mysteel.com/fastcomment.html",
    }


# ---------------------------------------------------------------------------
# CFTC持仓报告(COT)：CBOT豆粕合约里Managed Money(基金/投机资金)的净多空持仓+周变化。
# 这是美国版的"龙虎榜"——跟大商所会员持仓排名是同一个概念的海外对照，Managed Money
# 这一类是CFTC自己划分的"投机资金"分类，最接近用户想追踪的"外资/资金动向"。
#
# ★数据源确认过程(不是看文档/猜测的，是实测抓包确认的)：
# - CFTC通过Socrata开放数据平台(publicreporting.cftc.gov)发布COT数据，不需要API key——
#   CFTC官方文档原话："Currently, we are not providing tokens...As long as you are not
#   overusing the API, you should be able to use the API without a token."
# - COT报告分Legacy/Disaggregated/TFF三种口径，Legacy只分Commercial/Non-Commercial，
#   不够细；Disaggregated才有Managed Money这个细分类别，数据集ID是72hh-3qpy——这个ID
#   交叉核对过2个独立信息源都指向同一个，且实测直接抓取过真实响应验证过字段名。
# - 关键字段命名有个坑：swap dealer那类字段(swap__positions_short_all)在short/spread
#   前有双下划线，但m_money(Managed Money)这类没有这个问题，字段名是规整的
#   m_money_positions_long_all/short_all，不要混淆搞错。
# - CFTC每周五下午发布，覆盖到当周二的持仓数据(不是当周五当天)。
# ---------------------------------------------------------------------------
CFTC_DISAGGREGATED_BASE = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"


def cftc_history_points(rows):
    """CFTC明细行(按report_date DESC)→历史点[{d,v,x}]，按日期升序。d=报告日期(周二)，v=管理基金净多(多−空)，x={long,short}。
    个别行解析失败/没有日期就跳过，不让整体失效。"""
    out = []
    for row in rows or []:
        try:
            d = str(row.get("report_date_as_yyyy_mm_dd") or "")[:10]
            lo, sh = float(row["m_money_positions_long_all"]), float(row["m_money_positions_short_all"])
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        if not d:
            continue
        out.append({"d": d, "v": lo - sh, "x": {"long": lo, "short": sh}})
    out.sort(key=lambda p: p["d"])
    return out


def fetch_cftc_managed_money(market_name="SOYBEAN MEAL - CHICAGO BOARD OF TRADE", history_limit=156):
    """查询CFTC Disaggregated COT报告里，指定市场的Managed Money(基金/投机资金)
    净多空持仓+CFTC官方已经算好的周变化(change_in_m_money_long_all等字段)。

    ★用户明确要求：只看"这周涨跌"不够，净多头"持续增加"、"处于历史高位"、
    "持续下降/转净空"这三种情况，含义完全不同，值得分开展示，方便决策判断。
    这几项都需要多周历史数据才能判断，不是只看最新一周就够——所以这次把
    单次请求的$limit从1改成history_limit(默认156周≈3年)，一次请求把历史
    序列都拿回来，不需要额外发起156次请求。

    ★为什么选3年当回看窗口：COT数据本身能追溯几十年，但拿几十年前的数据当
    "正常范围"参考意义有限(当年市场结构、参与者跟现在很不一样)，3年是常见的、
    既能反映"近期正常波动区间"、又不会因窗口太短被单次极端值扭曲的折中选择。"""
    params = {
        "$where": f"market_and_exchange_names='{market_name}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": str(history_limit),
    }
    url = f"{CFTC_DISAGGREGATED_BASE}?{urllib.parse.urlencode(params)}"
    data, debug = fetch_json_debug(url)
    if data is None:
        return {"available": False, "reason": "CFTC接口无返回数据", "debug": debug}
    if len(data) == 0:
        return {"available": False, "reason": f"没有查到市场名称为\"{market_name}\"的记录(可能CFTC那边的命名有细微差异)", "debug": debug}

    latest_row = data[0]
    try:
        long_pos = float(latest_row["m_money_positions_long_all"])
        short_pos = float(latest_row["m_money_positions_short_all"])
        long_chg = float(latest_row["change_in_m_money_long_all"])
        short_chg = float(latest_row["change_in_m_money_short_all"])
    except (KeyError, ValueError, TypeError) as e:
        return {
            "available": False,
            "reason": f"字段解析失败: {e}(CFTC那边可能改了字段名)",
            "debug": {"sampleRawRow": latest_row, "actualKeysSeen": list(latest_row.keys())},
        }

    net_pos = round(long_pos - short_pos, 0)
    net_chg = round(long_chg - short_chg, 0)

    # 解析全部历史行的净持仓，构建时间序列(数据本来就是按report_date DESC排的，
    # data[0]最新、data[-1]最旧)。个别行解析失败就跳过，不让整体功能失效。
    net_series = []
    for row in data:
        try:
            net_series.append(float(row["m_money_positions_long_all"]) - float(row["m_money_positions_short_all"]))
        except (KeyError, ValueError, TypeError):
            continue

    # ★信号①③：连续上升/下降了几周——从最新一周往回看，相邻两周的差值方向
    #   连续一致就累加，遇到方向反转或打平就停。
    streak_weeks = 0
    streak_direction = None
    for i in range(len(net_series) - 1):
        diff = net_series[i] - net_series[i + 1]
        direction = "up" if diff > 0 else "down" if diff < 0 else None
        if streak_direction is None:
            if direction is None:
                break
            streak_direction = direction
            streak_weeks = 1
        elif direction == streak_direction:
            streak_weeks += 1
        else:
            break

    # ★信号②：历史百分位——当前净持仓在这段回看窗口里，比多少历史值都高(或持平)。
    #   用>=1年(52周)数据才计算，数据太短的话"历史高位"这个说法没有意义。
    history_percentile = None
    if len(net_series) >= 52:
        below_or_equal = sum(1 for v in net_series if v <= net_pos)
        history_percentile = round(below_or_equal / len(net_series) * 100, 1)

    return {
        "available": True,
        "marketName": latest_row.get("market_and_exchange_names", market_name),
        "reportDate": latest_row.get("report_date_as_yyyy_mm_dd", "")[:10],
        "longPositions": long_pos,
        "shortPositions": short_pos,
        "netPosition": net_pos,
        "longChange": long_chg,
        "shortChange": short_chg,
        "netChange": net_chg,
        "streakWeeks": streak_weeks,
        "streakDirection": streak_direction,  # 'up' | 'down' | None
        "historyPercentile": history_percentile,  # 0-100，None表示历史数据不够(<52周)
        "historyWeeksUsed": len(net_series),
        "history": cftc_history_points(data),   # ★v101：把156周明细带出来，由history_store记成cftc_mm_net序列(第一次运行就有整段历史)
        "source": "CFTC Disaggregated COT报告(Managed Money/投机资金类别)，每周五发布，覆盖到当周二数据",
        "sourceUrl": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
    }

# ============================================================================
# 资金面(龙虎榜+CFTC)：外资多头拥挤度——从已经抓到的龙虎榜和CFTC派生，不增加任何网络请求
# ============================================================================
# 为什么要固定看"主力合约"：用真实数据(2026-09-30)——M2701的净空头榜持仓合计约79.6万手(中粮48.2万、国投22.6万)，
#   而9月合约M2709只有几千手(前几名只有几百到几千手)。页面选中9月合约时，外资看起来"很平静"，其实是那个合约几乎没人持仓。
#   所以外资/产业的分析必须看主力合约，不跟着页面选中的合约走。
# 为什么只叫"拥挤度"、不直接宣布"资金市"：文档对"资金市"的定义还要求价格突破、无视基本面利空、美豆不涨豆粕涨、高盛连续单边增仓——
#   这些现有数据判断不了(没有龙虎榜历史，只有当天快照；联动需要美豆数据)。能判断的只有：高盛净多头水平 + CFTC管理基金净多的历史分位。
# 阈值全部来自文档(博主经验)：暂定，未回测。等累积够龙虎榜历史再校准(见TODO.md)。
CAPITAL_GS_HIGH = 120000            # 高盛净多头≥12万手 = 高位(文档：从16万手级别降到12万手以下→资金市可能接近尾声，所以12万以上算高位区)
CAPITAL_GS_RETREAT_CHG = -20000     # 高盛单日净多变化≤-2万手 = 撤退预警(文档：单日减仓超2万手→预警)
CAPITAL_CFTC_CROWDED_PCT = 90       # CFTC管理基金净多的历史分位≥90 = 拥挤(文档：创历史新高后回落→拥挤反转风险；分位用近156周)
CAPITAL_FOREIGN = ["高盛期货", "摩根大通", "瑞银期货"]            # 展示的外资席位(与FOREIGN_FIRM_CORE_NAMES一致；摩根士丹利在数据里没出现过)
CAPITAL_INDUSTRY = ["中粮期货", "国投期货"]                       # 产业席位(文档：产业双空头格局)


def _member_net(tables, name):
    """会员在净多头榜/净空头榜里的净持仓：在netLong表=+value，在netShort表=-value，都没有=None(未进榜，不是0)。
    netShort里的change是净空的变化，所以净持仓变化=-change。返回{net, change, side, rank, foreign}或None。"""
    for side, tbl in (("long", tables.get("netLong") or []), ("short", tables.get("netShort") or [])):
        for r in tbl:
            if name in str(r.get("name") or "") and r.get("value") is not None:
                sign = 1 if side == "long" else -1
                chg = r.get("change")
                return {"net": sign * r["value"], "change": (sign * chg) if chg is not None else None, "side": side, "rank": r.get("rank"),
                        "foreign": bool(r.get("isForeign")) or _is_foreign_futures_firm(r.get("name"))}
    return None


def _capital_state(gs, cftc):
    """外资多头拥挤度状态。gs=高盛的_member_net结果(可None)，cftc=build_market_capital里的cftc字典(可None)。
    优先级：撤退预警(当天大幅减仓，更新的信息) > 拥挤(高盛高位且CFTC拥挤) > 高位(满足其一) > 中性 > 数据不足。数据缺失绝不写中性。"""
    gs_net = gs["net"] if gs else None
    gs_chg = gs["change"] if gs else None
    pct = cftc.get("percentile") if cftc else None
    gs_high = gs_net is not None and gs_net >= CAPITAL_GS_HIGH
    crowded = pct is not None and pct >= CAPITAL_CFTC_CROWDED_PCT
    note = ("只能判断持仓拥挤度(高盛净多头水平+CFTC管理基金净多的历史分位)。文档里'资金市'还要求的价格突破、无视基本面利空、美豆不涨豆粕涨、"
            "高盛连续N日单边增仓，目前都未判断：价格/联动需要美豆数据，'连续N日'需要龙虎榜历史(v101起每天累积，但刚开始，要攒够才能判断，见TODO.md)。")
    base = {"note": note, "thresholdSource": "文档经验值，暂定，未回测"}
    if gs_chg is not None and gs_chg <= CAPITAL_GS_RETREAT_CHG:
        return dict(base, code="retreat", level="yellow", label=f"外资撤退预警：高盛当日减仓{abs(gs_chg):,}手")
    if gs_high and crowded:
        return dict(base, code="crowded", level="red", label="外资多头拥挤")
    if gs_high:
        return dict(base, code="elevated", level="yellow", label="外资多头高位(高盛净多头在高位，CFTC未到拥挤)")
    if crowded:
        return dict(base, code="elevated", level="yellow", label="外资多头高位(依据：CFTC管理基金净多到顶；高盛未进榜或不在高位)")
    if gs_net is None and pct is None:
        return dict(base, code="unknown", level="gray", label="外资状态：数据不足")
    if gs_net is None or pct is None:
        return dict(base, code="unknown", level="gray", label="外资状态：数据不足(高盛或CFTC缺一项，不下'中性'结论)")
    return dict(base, code="neutral", level="green", label="外资中性(高盛净多头不在高位，CFTC不拥挤)")


def build_market_capital(rank_by_key, cftc):
    """rank_by_key={'sep':龙虎榜结果,'may':…,'jan':…}(每个是单合约的龙虎榜结果或None)；cftc=fetch_cftc_managed_money()的结果或None。
    返回{available, mainContract:{key,symbol,gross}, date, members:{名字:{net,change,side,rank,foreign}}, industry:{net,change,changePct}, cftc:{…}, state:{…}}。"""
    best = None
    for key, rk in (rank_by_key or {}).items():
        if not isinstance(rk, dict) or not rk.get("available"):
            continue
        tbl = rk.get("tables") or {}
        gross = sum(r.get("value") or 0 for r in (tbl.get("netShort") or []))
        if best is None or gross > best[2]:
            best = (key, rk, gross)
    cf = None
    if isinstance(cftc, dict) and cftc.get("available", True) and cftc.get("netPosition") is not None:
        cf = {"net": cftc.get("netPosition"), "netChange": cftc.get("netChange"), "streakWeeks": cftc.get("streakWeeks"), "streakDirection": cftc.get("streakDirection"),
              "percentile": cftc.get("historyPercentile"), "weeksUsed": cftc.get("historyWeeksUsed"), "reportDate": cftc.get("reportDate")}
    if best is None:
        return {"available": False, "mainContract": None, "members": {}, "industry": None, "cftc": cf, "state": _capital_state(None, cf)}
    key, rk, gross = best
    tables = rk.get("tables") or {}
    members = {}
    for name in CAPITAL_FOREIGN + CAPITAL_INDUSTRY:
        members[name] = _member_net(tables, name) or {"net": None, "change": None, "side": None, "rank": None, "foreign": name in CAPITAL_FOREIGN}
    ind_nets = [members[n] for n in CAPITAL_INDUSTRY if members[n]["net"] is not None]
    industry = None
    if ind_nets:
        net = sum(m["net"] for m in ind_nets)
        chgs = [m["change"] for m in ind_nets if m["change"] is not None]
        chg = sum(chgs) if len(chgs) == len(ind_nets) else None
        industry = {"net": net, "change": chg, "changePct": round(chg / abs(net) * 100, 2) if (chg is not None and net) else None,
                    "members": [n for n in CAPITAL_INDUSTRY if members[n]["net"] is not None]}
    return {"available": True, "mainContract": {"key": key, "symbol": rk.get("symbol"), "gross": gross}, "date": rk.get("date"), "members": members, "industry": industry,
            "cftc": cf, "state": _capital_state(members.get("高盛期货"), cf),
            "source": "大商所龙虎榜(东方财富，T+1，收盘后发布)+CFTC Managed Money(每周五发布，覆盖到当周二)；主力合约=净空头榜持仓合计最大的合约"}




# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 技术面：DCE豆粕期货K线数据（日线+小时线），用akshare库(免密钥，抓新浪财经公开数据)
# ★ 第一阶段范围：先只做当前主力(9月合约M09)验证可行，跑通后再加5月/1月合约。

# ---------------------------------------------------------------------------
# 技术面：DCE豆粕期货K线数据（日线+小时线），用akshare库(免密钥，抓新浪财经公开数据)
# ★ 第一阶段范围：先只做当前主力(9月合约M09)验证可行，跑通后再加5月/1月合约。
# ★ 诚实说明：akshare底层是抓取新浪财经公开页面，不是官方付费实时数据源，
#   实际数据大概率有几秒到几分钟延迟，不是真正的逐笔实时行情。
# ---------------------------------------------------------------------------
def get_current_contract_code(contract_month, now=None, prefix="M"):
    """算出"现在"该关注的是哪个具体合约代码，比如7月看9月合约，应该是M2609
    （不能写死，因为合约到期后，同一个"9月合约"概念下个周期就该指向M2709了）。
    简化规则：如果当前月份<=合约月份，用今年；否则用明年。
    ★prefix参数：默认"M"(豆粕)，压榨利润计算需要复用这个函数算"Y"(豆油)/"B"(豆二/
    进口大豆)的合约代码——年份计算逻辑对这三个品种是通用的，不用另外写一份。"""
    if now is None:
        now = datetime.now(timezone.utc)
    year = now.year if now.month <= contract_month else now.year + 1
    yy = str(year)[-2:]
    return f"{prefix}{yy}{contract_month:02d}"


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
        # 新浪对"不存在的合约"(远月尚未上市、或太久以前的已下市合约)不返回空表，而是让akshare内部抛pandas异常(Length mismatch: Expected axis has 0 elements...)，
        # 用户看到的是一串看不懂的原始报错(2026-10-01回填报告里M2801、M1809等)。这种情况和下面"返回空数据"本质是同一件事，统一成人话。
        if "Length mismatch" in str(e) and "0 elements" in str(e):
            return {"available": False, "reason": f"新浪没有合约{symbol}的数据(远月尚未上市，或太久以前已下市)", "debug": {"symbol": symbol, "errorType": type(e).__name__, "rawError": str(e)[:120]}}
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
# 压榨利润(榨利)：按用户确认的优先级排第二项。这个不是直接抓来的数据，是算出来的——
# 复用豆粕日K线同一个akshare接口，换成豆油(Y)/豆二(B，进口大豆)的合约代码去查最新收盘价，
# 三者代入行业标准公式算出"盘面毛利"。
#
# ★标准公式+系数确认过程(多个独立信息源交叉确认，其中出粕率/出油率这组数字
#   最权威的来源是大商所豆二期货厂库交割置换的官方标准本身)：
#   压榨利润 = 豆粕价格×出粕率 + 豆油价格×出油率 - 大豆价格 - 加工费
#   进口大豆(豆二/B)：出粕率78.5%，出油率18.5%
#
# ★诚实说明这是"毛利"不是"净利"：公式里的"加工费"(油厂自己的加工/物流成本)
#   没有一个公开、权威、会随时间变化的数据源可以查，硬编一个猜测数字反而不诚实
#   (看起来精确，实际是瞎猜)。所以这里只算到"豆粕+豆油产出价值 - 大豆成本"这一步，
#   不减加工费——趋势方向(涨跌)依然有参考价值，只是绝对数值会比真实净利润更高。
# ---------------------------------------------------------------------------
CRUSH_YIELD_MEAL = 0.785  # 出粕率(进口大豆/豆二)
CRUSH_YIELD_OIL = 0.185   # 出油率(进口大豆/豆二)


def fetch_crush_margin(contract_month, now=None):
    """算指定合约月份(9/5/1)的盘面压榨毛利：分别抓豆粕(M)/豆油(Y)/豆二(B)三个
    同月份合约的最新收盘价，代入标准公式。三者只要有一个抓不到数据就整体标记不可用——
    压榨利润是三个价格联动算出来的，缺一个都算不出有意义的结果，不能用"缺了就当0"
    这种方式硬凑一个看似正常的数字出来。"""
    meal_symbol = get_current_contract_code(contract_month, now, prefix="M")
    oil_symbol = get_current_contract_code(contract_month, now, prefix="Y")
    bean_symbol = get_current_contract_code(contract_month, now, prefix="B")

    meal_data = fetch_dce_daily_kline(meal_symbol, max_rows=1)
    oil_data = fetch_dce_daily_kline(oil_symbol, max_rows=1)
    bean_data = fetch_dce_daily_kline(bean_symbol, max_rows=1)

    missing = []
    if not meal_data.get("available") or not meal_data.get("bars"):
        missing.append(f"豆粕{meal_symbol}({meal_data.get('reason','未知原因')})")
    if not oil_data.get("available") or not oil_data.get("bars"):
        missing.append(f"豆油{oil_symbol}({oil_data.get('reason','未知原因')})")
    if not bean_data.get("available") or not bean_data.get("bars"):
        missing.append(f"豆二{bean_symbol}({bean_data.get('reason','未知原因')})")
    if missing:
        return {"available": False, "reason": f"以下合约价格缺失，无法计算压榨利润: {'; '.join(missing)}"}

    meal_price = meal_data["bars"][-1]["close"]
    oil_price = oil_data["bars"][-1]["close"]
    bean_price = bean_data["bars"][-1]["close"]
    gross_margin = round(meal_price * CRUSH_YIELD_MEAL + oil_price * CRUSH_YIELD_OIL - bean_price, 1)
    # 数据日期：三个合约最新一根K线的日期，取最早的那个(三者不一致时以最旧的为准，诚实标注)；用于判断新鲜度和写入历史
    bar_dates = [d[ "bars"][-1].get("date") for d in (meal_data, oil_data, bean_data)]
    bar_dates = [str(x)[:10] for x in bar_dates if x]
    margin_date = min(bar_dates) if bar_dates else None

    return {
        "available": True,
        "contractMonth": contract_month,
        "date": margin_date,
        "datesAligned": len(set(bar_dates)) == 1 if bar_dates else None,
        "mealSymbol": meal_symbol, "mealPrice": meal_price,
        "oilSymbol": oil_symbol, "oilPrice": oil_price,
        "beanSymbol": bean_symbol, "beanPrice": bean_price,
        "grossMargin": gross_margin,
        "yieldMeal": CRUSH_YIELD_MEAL, "yieldOil": CRUSH_YIELD_OIL,
        "source": "DCE豆粕/豆油/豆二盘面价格(新浪财经，经akshare获取)算出的盘面毛利，未扣加工费",
    }


# ---------------------------------------------------------------------------
# 月差/期限结构：近月合约 - 远月合约(大商所标准月差：9-1、5-9、1-5)
#   9月合约看 9-1(M{yy}09 对 次年M{yy+1}01)；5月合约看 5-9(M{yy}05 对 M{yy}09)；1月合约看 1-5(M{yy}01 对 M{yy}05)。
#   即"这个合约对下一个活跃合约"，跟着合约切换，跟榨利同一套思路。
# ★符号：spread = 近月 - 远月。>0 近强远弱(backwardation，近端偏紧)；<0 远强近弱(contango，远月升水)。
#   ⚠️粮食可以储存，远月升水(contango)是"持有成本"造成的正常状态，所以**正负本身不是信号**——
#   只能看它跟历史同期比的位置(分位)。用"价差占近月价格的百分比"(spreadPct)而不是元/吨：不同年份价格水平不同(2500 vs 4000)，
#   绝对价差没法跨年比较。
# ---------------------------------------------------------------------------
TERM_SPREAD_FAR = {9: (1, 1), 5: (9, 0), 1: (5, 0)}      # 合约月份 → (远月月份, 远月比近月晚几年)


def term_spread_symbols(contract_month, now=None):
    """近月/远月合约代码。近月复用get_current_contract_code(比如9月合约在2026年7月是M2609)；远月按上表推。"""
    near = get_current_contract_code(contract_month, now, prefix="M")
    far_month, year_add = TERM_SPREAD_FAR[contract_month]
    yy = (int(near[1:3]) + year_add) % 100
    return near, f"M{yy:02d}{far_month:02d}"


def fetch_term_spread(contract_month, now=None):
    """指定合约月份(9/5/1)的近远月价差。两个合约都要抓到收盘价，缺一个整体不可用(不用0硬凑)。"""
    near_sym, far_sym = term_spread_symbols(contract_month, now)
    near_data = fetch_dce_daily_kline(near_sym, max_rows=1)
    far_data = fetch_dce_daily_kline(far_sym, max_rows=1)
    missing = []
    if not near_data.get("available") or not near_data.get("bars"):
        missing.append(f"近月{near_sym}({near_data.get('reason', '未知原因')})")
    if not far_data.get("available") or not far_data.get("bars"):
        missing.append(f"远月{far_sym}({far_data.get('reason', '未知原因')})")
    if missing:
        return {"available": False, "reason": f"以下合约价格缺失，无法计算月差: {'; '.join(missing)}"}
    near_bar, far_bar = near_data["bars"][-1], far_data["bars"][-1]
    near_price, far_price = near_bar["close"], far_bar["close"]
    if not near_price:
        return {"available": False, "reason": f"近月{near_sym}收盘价为0/空，无法计算价差占比"}
    dates = [str(b.get("date"))[:10] for b in (near_bar, far_bar) if b.get("date")]
    return {
        "available": True, "contractMonth": contract_month,
        "date": min(dates) if dates else None,
        "datesAligned": len(set(dates)) == 1 if dates else None,
        "nearSymbol": near_sym, "nearPrice": near_price, "farSymbol": far_sym, "farPrice": far_price,
        "spread": round(near_price - far_price, 1),
        "spreadPct": round((near_price - far_price) / near_price * 100, 2),
        "source": "DCE豆粕近远月合约盘面价格(新浪财经，经akshare获取)",
    }


def term_spread_series(near_bars, far_bars):
    """两条日K线 → 逐日{日期: 价差占近月价格的百分比}。只算两个合约都有收盘价、近月价格非0的日期。"""
    def to_map(bars):
        return {str(b.get("date"))[:10]: b.get("close") for b in bars if b.get("date") and b.get("close") is not None}
    n, f = to_map(near_bars), to_map(far_bars)
    return {d: round((n[d] - f[d]) / n[d] * 100, 2) for d in sorted(set(n) & set(f)) if n[d]}


def crush_margin_series(meal_bars, oil_bars, bean_bars):
    """三条日K线 → 逐日盘面毛利{日期: 毛利}。只算三者都有收盘价的日期(缺一个就不算，跟单日算法一致)。
    回填历史用：同一个合约月份(比如2509)的豆粕/豆油/豆二，各自的上市周期一致。"""
    def to_map(bars):
        return {str(b.get("date"))[:10]: b.get("close") for b in bars if b.get("date") and b.get("close") is not None}
    m, o, b = to_map(meal_bars), to_map(oil_bars), to_map(bean_bars)
    return {d: round(m[d] * CRUSH_YIELD_MEAL + o[d] * CRUSH_YIELD_OIL - b[d], 1) for d in sorted(set(m) & set(o) & set(b))}


# ★确认过的境内外资独资期货公司(实测查证，不是猜测)：这4家目前都是100%外资控股的
#   境内期货公司，且都是大商所会员——高盛期货是2026年才由"乾坤期货"更名而来。
#   用"in"做包含匹配(不是精确匹配)，因为会员名称在不同数据源/时间点可能带"(代客)"
#   这类后缀，或者叫"高盛期货(深圳)"这种更完整的写法。
FOREIGN_FUTURES_FIRMS = ["高盛期货", "摩根大通期货", "摩根士丹利期货", "瑞银期货"]
# ★v100：识别用的核心名。数据源(东方财富)返回的会员名可能没有"期货"后缀——2026-09-30的真实数据里写的是"摩根大通"，而名单里是"摩根大通期货"，
#   "名单项 in 名字"的包含匹配方向让它一直没被识别成外资(isForeign:false)。核心名要足够长以免误伤境内会员(不用"摩根"/"大通"这种太短的)；
#   高盛/瑞银在真实数据里带"期货"后缀，本来就能匹配，这里一并列出。用2026-09-30三个合约四张表里的54个真实会员名验证过：51个境内会员零误判。
FOREIGN_FIRM_CORE_NAMES = ["高盛期货", "摩根大通", "摩根士丹利", "瑞银期货"]


def _is_foreign_futures_firm(name):
    """判断一个会员名称是不是已确认的外资独资期货公司(包含匹配：完整名单项或核心名出现在会员名里)。"""
    name = str(name or "")
    return any(firm in name for firm in FOREIGN_FUTURES_FIRMS) or any(core in name for core in FOREIGN_FIRM_CORE_NAMES)


# 六个龙虎榜类别的配置：sortField是请求时sortColumns参数要用的值(不带下划线)，
# rankField/valueField/chgField是响应数据里实际的字段名(部分带下划线)。
# ⚠️这几个字段名都是从用户实测抓包的真实响应数据里确认的，不是看文档猜的。
POSITION_RANK_CATEGORIES = {
    "long":     {"sortField": "LPRANK",      "rankField": "LP_RANK",      "valueField": "LONG_POSITION",      "chgField": "LP_CHANGE",  "label": "多头持仓龙虎榜"},
    "short":    {"sortField": "SPRANK",      "rankField": "SP_RANK",      "valueField": "SHORT_POSITION",     "chgField": "SP_CHANGE",  "label": "空头持仓龙虎榜"},
    "netLong":  {"sortField": "NLPRANK",     "rankField": "NLP_RANK",     "valueField": "NET_LONG_POSITION",  "chgField": "NLP_CHANGE", "label": "净多头龙虎榜"},
    "netShort": {"sortField": "NSPRANK",     "rankField": "NSP_RANK",     "valueField": "NET_SHORT_POSITION", "chgField": "NSP_CHANGE", "label": "净空头龙虎榜"},
    "longUp":   {"sortField": "LPUPRANK",    "rankField": "LP_UP_RANK",   "valueField": "LONG_POSITION",      "chgField": "LP_CHANGE",  "label": "多头增仓龙虎榜"},
    "longDown": {"sortField": "LPDOWNRANK",  "rankField": "LP_DOWN_RANK", "valueField": "LONG_POSITION",      "chgField": "LP_CHANGE",  "label": "多头减仓龙虎榜"},
}


def _build_eastmoney_position_url(symbol, date_str, sort_field):
    """构造东方财富datacenter-web持仓排名接口的请求URL。
    symbol: 合约代码，如"M2701"(不需要转小写，跟东方财富这边的格式完全一致)
    date_str: 交易日，格式"YYYY-MM-DD"(不是YYYYMMDD)
    sort_field: 排序字段，取值见POSITION_RANK_CATEGORIES里各类别的sortField——
    这个接口返回的每一行是"一个会员在各项指标下的排名"，不是独立的多个排行榜，
    所以要拿"按某项指标排名前20"，必须显式按对应字段排序单独查询，不能从任意一次
    查询结果里直接截取，不然拿到的20个会员可能是按别的指标排出来的。
    ⚠️这个URL结构是实测抓包确认的(不是看文档/猜测的)：用户在浏览器F12开发者工具
    Network标签里，实际点击查询按钮后抓到的真实请求。括号不要被urlencode转义掉——
    抓包结果显示服务端要的是字面的圆括号，等号和双引号这些字符才需要转义成%3D/%22等。"""
    filter_str = f'(SECURITY_CODE="{symbol}")(TRADE_DATE=\'{date_str}\')(TYPE="0")({sort_field}<>9999)'
    params = {
        "reportName": "RPT_FUTU_DAILYPOSITION",
        "columns": "ALL",
        "filter": filter_str,
        "sortTypes": "1",
        "sortColumns": sort_field,
        "pageNumber": "1",
        "pageSize": "20",
        "source": "WEB",
        "client": "WEB",
        "_": str(int(time.time() * 1000)),
    }
    query = "&".join(f"{k}={urllib.parse.quote(str(v), safe='()')}" for k, v in params.items())
    return f"https://datacenter-web.eastmoney.com/api/data/v1/get?{query}"


def _parse_eastmoney_position_rows(raw_rows, category_key):
    """把东方财富接口返回的原始行，转换成本项目统一使用的行格式。
    category_key: POSITION_RANK_CATEGORIES里的键，决定用哪个排名字段过滤/排序，
    以及用哪个持仓量+增减字段作为这一类别的"值"。每一行统一输出
    {rank, name, value, change, isForeign}这几个字段，不管是哪个类别都是同一套结构，
    方便前端用同一套渲染逻辑处理六个不同的榜单。"""
    cfg = POSITION_RANK_CATEGORIES[category_key]
    rows = []
    for r in raw_rows:
        rank_val = r.get(cfg["rankField"])
        if rank_val is None or rank_val == 9999:
            continue  # 9999是"没有这项排名"的哨兵值，跳过
        name = r.get("ORG_NAME_ABBR_NEW") or r.get("MEMBER_NAME_ABBR") or ""
        rows.append({
            "rank": int(rank_val),
            "name": name,
            "value": r.get(cfg["valueField"]),
            "change": r.get(cfg["chgField"]),
            "isForeign": _is_foreign_futures_firm(name),
        })
    # ★明确按rank排序，不单纯依赖服务端的返回顺序——虽然请求时已经指定了sortColumns，
    #   服务端理论上会排好序，但多一道自己排序的保险，不容易因为服务端行为的细微变化出问题。
    rows.sort(key=lambda r: r["rank"])
    return rows


def candidate_trading_dates(now, n_trading_days=6, min_calendar_days=14, max_calendar_days=30):
    """龙虎榜往回找数据的候选日期：从 now 往回，只取日历判断为"大商所交易日"的日子(休市日不发网络请求、不占名额)，从新到旧。
    取到"至少 n_trading_days 个交易日，并且至少覆盖 min_calendar_days 个日历日"为止，但不超过 max_calendar_days 个日历日(日历数据有错时不死循环)。
    为什么：原来 `for days_back in range(6)` 每个日历日算一次尝试，国庆休市10-01~10-07时，10-06往回数6个日历日只到10-01，
    够不到最后一个有数据的交易日09-30，龙虎榜整块失效(线上：'尝试了最近6个日期都没能获取到M2701的持仓排名数据')。
    为什么还要日历下限：休市表(cn_calendar.DCE_CLOSURES)里现在只有2026国庆，春节(约9天)还没进表，日历会把它当交易日；
    只数交易日个数覆盖不了春节，所以另外保证至少回溯14个日历日。平时第一个候选就拿到数据，循环里"全部类别拿到就break"，不会多发请求。"""
    import cn_calendar
    out = []
    for back in range(max_calendar_days + 1):
        d = now - timedelta(days=back)
        if cn_calendar.dce_is_trading_day(d.date() if hasattr(d, "date") else d):
            out.append(d)
        if len(out) >= n_trading_days and back + 1 >= min_calendar_days:
            break
    return out


def fetch_dce_position_rank_multi(symbols, max_attempts=6, categories=None):
    """大商所持仓排名(龙虎榜)：每个合约六类榜单(多头持仓/空头持仓/净多头/净空头/
    多头增仓/多头减仓)的前20名会员，含外资独资期货公司标注。
    ★2026-09更新：彻底改用东方财富datacenter-web接口，不再走大商所官网直连——
    之前用akshare的futures_dce_position_rank会稳定报BadZipFile错误(大商所官网
    反爬拦截或格式变化，生产环境实测确认)。这次改用的接口地址、参数结构、
    返回字段，全部是通过浏览器F12开发者工具实测抓包确认的，不是看文档/猜测的。

    ★categories默认是POSITION_RANK_CATEGORIES的全部键，但按用户明确要求，
    实际调用时(main()里)只传4类：netLong/netShort/longUp/longDown——多头/空头
    持仓这两类(long/short)虽然接口支持，暂时不在默认抓取范围内，避免请求量
    进一步增加(每类都要走一遍T+1重试逻辑，类别越多，最坏情况下请求次数越多)。

    数据是T+1性质：收盘后才发布当天数据，所以从"今天"开始最多往前试max_attempts天，
    找到数据就停。每个合约每个类别都需要独立请求——这个接口的原始数据结构是
    "每个会员一行、同时列出该会员在各项指标下的排名"，不是分开的独立榜单，
    所以不能从"按某一个指标排序"的结果里直接截取别的指标数据。

    ⚠️这是会员(期货公司)持仓排名，不是最终客户排名——比如"中信期货"是会员名，
    不代表某个具体机构自己的仓位，除非该机构本身就是直接注册的会员。已确认的
    4家外资独资期货公司(高盛期货/摩根大通期货/摩根士丹利期货/瑞银期货)会标注
    isForeign:true，但要注意：就算这几家进了前20，也不保证当天真的进了榜——
    多数情况下它们可能根本不在前20名之列(需求量没那么大)，这是真实市场情况，
    不是数据缺失。

    返回：{symbol: {available, date, tables:{类别: rows}, source} 或 {available:False, reason, debug}}"""
    if categories is None:
        categories = list(POSITION_RANK_CATEGORIES.keys())

    now_beijing = datetime.now(timezone.utc) + timedelta(hours=8)
    final = {}

    for symbol in symbols:
        attempts_log = []
        tables = {cat: None for cat in categories}
        used_date = None

        for try_date in candidate_trading_dates(now_beijing, n_trading_days=max_attempts):
            if all(v is not None for v in tables.values()):
                break
            date_str = try_date.strftime("%Y-%m-%d")

            for cat in categories:
                if tables[cat] is not None:
                    continue  # 这一类已经拿到过了，不用再查
                sort_field = POSITION_RANK_CATEGORIES[cat]["sortField"]
                url = _build_eastmoney_position_url(symbol, date_str, sort_field)
                data, debug_info = fetch_jsonp_debug(url)
                if data is None:
                    attempts_log.append({"date": date_str, "category": cat, "error": debug_info.get("error", "未知错误")})
                    continue
                if not data.get("success"):
                    attempts_log.append({"date": date_str, "category": cat, "note": f"接口返回success=false: {data.get('message')}"})
                    continue
                raw_rows = (data.get("result") or {}).get("data") or []
                if not raw_rows:
                    attempts_log.append({"date": date_str, "category": cat, "note": "该日期没有返回任何数据(可能是非交易日，或数据尚未发布)"})
                    continue
                tables[cat] = _parse_eastmoney_position_rows(raw_rows, cat)
                used_date = date_str

        if any(v is not None for v in tables.values()):
            final[symbol] = {
                "available": True,
                "symbol": symbol,
                "date": used_date,
                "tables": {cat: (rows or []) for cat, rows in tables.items()},
                "source": "东方财富期货持仓排名(datacenter-web接口)，T+1数据(收盘后发布)",
            }
            missing = [cat for cat, rows in tables.items() if rows is None]
            if missing:
                final[symbol]["partialNote"] = f"这几类没拿到数据：{', '.join(POSITION_RANK_CATEGORIES[c]['label'] for c in missing)}"
        else:
            final[symbol] = {
                "available": False,
                "reason": f"尝试了最近{max_attempts}个日期都没能获取到{symbol}的持仓排名数据",
                "debug": {"attempts": attempts_log},
            }
    return final


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

# ★已移除fetch_south_america_weather()：实测发现前端loadSaWeather()是完全独立的
#   异步函式，直接在浏览器里重新打了一遍Open-Meteo API(同样10个地点、同样权重)，
#   根本没有读取这里算出来的southAmericaWeather数据——后端这份完全是重复劳动，
#   白白消耗GitHub Actions执行时间和data/latest.json的文件大小，删掉不影响任何
#   前端功能。SOUTH_AMERICA_LOCATIONS/SOUTH_AMERICA_WEIGHTS/weighted_avg_custom
#   这三个只服务于这个被移除的函数，一并删除；BRAZIL_LOCATIONS/ARGENTINA_LOCATIONS
#   这些底层常量保留，因为fetch_south_america_psd()等其他函数还在用。


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


# ---------------------------------------------------------------------------
# 巴西大豆播种进度：用开源库agrobr对接CONAB(巴西农业部旗下国家商品供应公司)。
#
# ★之前判断这项要走手动指标，原因是"需要浏览器自动化"——后来用户指出这个判断
#   有误，实测查了agrobr的源码(conab/progresso/api.py + client.py)确认：
#   核心逻辑是httpx.AsyncClient(纯HTTP客户端) + BeautifulSoup(从列表页解析出
#   最新周报的链接) + 直接下载解析XLSX二进制内容，源码里meta信息明确标注
#   source为"httpx+xlsx"，完全不涉及Playwright/浏览器渲染。之前的判断是把
#   "agrobr这个库整体的默认Docker镜像包含Playwright"错误地推广到了这一个
#   具体功能上，这次已经订正。
#
# ★诚实的限制说明：本项目的开发/测试沙盒网络白名单不包含gov.br(CONAB官网域名)，
#   没法在开发环境完整测试"实际连上CONAB、真实解析一次"这个流程——GitHub Actions
#   的runner网络是完全开放的，没有这个限制，但这意味着下面这个函数的验证程度
#   不如NASS/CFTC那两个(那两个是真的抓包/实测过真实响应)。这里改用尽量详尽的
#   防御性检查+debug信息，万一CONAB那边的数据结构跟从源码读到的预期有出入，
#   第一次在GitHub Actions真实运行时能通过debug信息定位问题，而不是静默出错
#   或编造数据。
COLUNAS_ESPERADAS_CONAB = {"cultura", "safra", "operacao", "estado",
                           "pct_ano_anterior", "pct_semana_anterior", "pct_semana_atual", "pct_media_5_anos"}


def fetch_brazil_planting_progress():
    """查询CONAB每周发布的巴西大豆播种进度(全国汇总)，包含本周/上周/去年同期/
    近五年均值——CONAB自己的报告格式本来就是这四个数字放在一起发布的，比
    美豆播种进度(NASS只给当周+需要自己另外查历史年份算同比)更直接。"""
    try:
        import asyncio
        from agrobr import conab
    except ImportError as e:
        return {"available": False, "reason": f"agrobr库未安装(需要 pip install agrobr pandas): {e}"}

    try:
        df = asyncio.run(conab.progresso_safra(cultura="Soja", operacao="Plantio"))
    except Exception as e:
        # agrobr内部可能抛出各种网络/解析异常，这里统一兜底成"不可用+具体报错"，
        # 不让这一项的失败影响main()里其他数据的抓取。
        return {"available": False, "reason": f"CONAB接口调用失败: {type(e).__name__}: {e}"}

    if df is None or len(df) == 0:
        return {"available": False, "reason": "CONAB返回空数据(可能当周报告还没发布，或播种季尚未开始)"}

    missing_cols = COLUNAS_ESPERADAS_CONAB - set(df.columns)
    if missing_cols:
        return {
            "available": False,
            "reason": f"返回数据缺少预期字段: {sorted(missing_cols)}(CONAB或agrobr可能改了格式)",
            "debug": {"actualColumns": list(df.columns)},
        }

    # ★实测查过agrobr源码(parser.py)确认：全国汇总行的estado字段值固定是"BR"
    #   (源码判断逻辑：表格里出现"Estados"或"Brasil"字样的行，归一化成"BR")。
    national_rows = df[df["estado"] == "BR"]
    if len(national_rows) == 0:
        return {
            "available": False,
            "reason": "没有找到estado='BR'的全国汇总行(数据结构跟预期不符)",
            "debug": {"actualEstadoValues": sorted(df["estado"].astype(str).unique().tolist())},
        }

    row = national_rows.iloc[-1]  # 万一有多条(理论上不该发生)，取最后一条(通常是最新)
    try:
        import pandas as pd
        pct_atual = float(row["pct_semana_atual"])
        pct_ano_anterior = float(row["pct_ano_anterior"])
        pct_semana_anterior = float(row["pct_semana_anterior"]) if pd.notna(row["pct_semana_anterior"]) else None
        pct_media_5_anos = float(row["pct_media_5_anos"]) if pd.notna(row["pct_media_5_anos"]) else None
    except (ValueError, TypeError) as e:
        return {
            "available": False,
            "reason": f"字段值无法解析为数字: {e}",
            "debug": {"sampleRow": {k: str(v) for k, v in row.to_dict().items()}},
        }

    return {
        "available": True,
        "safra": row.get("safra"),
        "weekLabel": row.get("semana_atual"),
        "pctCurrent": pct_atual,
        "pctYearAgo": pct_ano_anterior,
        "pctPrevWeek": pct_semana_anterior,
        "pctFiveYearAvg": pct_media_5_anos,
        "source": "CONAB(巴西农业部旗下国家商品供应公司)每周播种进度报告，经agrobr库解析(httpx+xlsx，非浏览器)",
        "sourceUrl": "https://www.gov.br/conab",
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

    # ★三个合约代码只算一次，日线/小时线/持仓排名都复用，不重复调用get_current_contract_code()
    sep_code = get_current_contract_code(9)
    may_code = get_current_contract_code(5)
    jan_code = get_current_contract_code(1)
    position_ranks = fetch_dce_position_rank_multi([sep_code, may_code, jan_code], categories=["netLong", "netShort", "longUp", "longDown"])
    crush_margins = {
        "sep": fetch_crush_margin(9),
        "may": fetch_crush_margin(5),
        "jan": fetch_crush_margin(1),
    }
    term_spreads = {
        "sep": fetch_term_spread(9),
        "may": fetch_term_spread(5),
        "jan": fetch_term_spread(1),
    }

    _meal_stock_result = fetch_mysteel_meal_stock()   # 周度库存：自己要展示，也给库消比的回退/交叉核对用

    result = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "cbotPrice": fetch_cbot_price(),
        "mysteelCrushRate": fetch_mysteel_crush_rate(),
        "ndrcPoultryProfit": fetch_ndrc_poultry(),      # v101.8：肉鸡养殖利润改用发改委价格监测中心×卓创资讯《猪料、鸡料、蛋料比价》周报(未来肉鸡养殖预期盈利)，不再取 Mysteel
        "mysteelRmSpread": fetch_mysteel_rmspread(),
        "mysteelArrivalForecast": fetch_mysteel_arrival_forecast(),
        "mysteelMealStock": _meal_stock_result,
        "mysteelMealStu": fetch_mysteel_meal_balance(weekly_stock=_meal_stock_result),
        "mysteelFeedDays": fetch_mysteel_feed_days(),
        "mysteelSoyImport": fetch_mysteel_soy_import(),
        "mysteelReserveAuction": fetch_mysteel_reserve_auction(),
        "spotBasis": fetch_spot_basis(),      # v101.7：现货基差改用 AKShare(生意社现货价 - 主力合约结算价，自己算)，不再取 Mysteel
        "hogRatio": fetch_hog_ratio(),
        "sowInventory": fetch_mysteel_sow_inventory(),
        "cftcManagedMoney": fetch_cftc_managed_money(),
        "crushMargins": crush_margins,
        "termSpreads": term_spreads,
        "brazilPlantingProgress": fetch_brazil_planting_progress(),
        "droughtMonitor": fetch_drought_monitor(),
        "noaaOutlook": fetch_noaa_drought_outlook(),
        "soybeanCondition": fetch_soybean_condition(),
        "usPlantingProgress": fetch_us_planting_progress(),
        "usHarvestProgress": fetch_us_harvest_progress(),
        # ★ 技术面覆盖三个合约(9月/5月/1月)。key用月份命名(不用具体年份)，
        #   这样合约年份每年滚动时key不用跟着改——具体是哪年的合约看里面的symbol字段。
        "dceM09Daily": fetch_dce_daily_kline(sep_code),
        "dceM09Hourly": fetch_dce_hourly_kline(sep_code),
        "dceM05Daily": fetch_dce_daily_kline(may_code),
        "dceM05Hourly": fetch_dce_hourly_kline(may_code),
        "dceM01Daily": fetch_dce_daily_kline(jan_code),
        "dceM01Hourly": fetch_dce_hourly_kline(jan_code),
        # ★龙虎榜(会员持仓排名)，同样按月份命名key，三个合约一次请求批量拿到
        "dceM09PositionRank": position_ranks[sep_code],
        "dceM05PositionRank": position_ranks[may_code],
        "dceM01PositionRank": position_ranks[jan_code],
        "southAmericaPsd": fetch_south_america_psd() if USDA_API_KEY else no_usda_key,
        "exportSales": fetch_esr_export_sales() if USDA_API_KEY else no_usda_key,
        "supplyDemand": fetch_psd_supply_demand() if USDA_API_KEY else no_usda_key,
    }

    # ★资金面(龙虎榜+CFTC)：从上面已经抓到的数据派生，不增加网络请求；任何错都不能影响latest.json
    try:
        result["marketCapital"] = build_market_capital({"sep": position_ranks.get(sep_code), "may": position_ranks.get(may_code), "jan": position_ranks.get(jan_code)}, result.get("cftcManagedMoney"))
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ marketCapital生成失败(不影响其他数据): {type(e).__name__}: {e}")
        result["marketCapital"] = {"available": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}

    # ★历史序列：把各指标最新值追加进data/history/*.json，并给对应结果挂上history(历史分位摘要)。
    #   出任何错都只打印警告——历史是锦上添花，绝不能让latest.json写不出来。
    try:
        import history_store
        history_store.update_and_attach(result, base_dir=os.path.join(os.path.dirname(OUTPUT_PATH), "history"))
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 历史序列更新失败(不影响其它数据): {type(e).__name__}: {e}", file=sys.stderr)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] 数据已写入 {OUTPUT_PATH}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
