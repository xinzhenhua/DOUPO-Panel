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
    headers = headers or {}
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


# ---------------------------------------------------------------------------
# 1. USDA-FAS 出口销售数据 (ESR)
# ---------------------------------------------------------------------------
def get_soybean_meal_esr_code():
    """动态查找"大豆粕/豆饼"在 ESR 商品列表里的编码，避免硬编码错误的代码。"""
    data = fetch_json(f"{USDA_BASE}/esr/commodities", headers={"X-Api-Key": USDA_API_KEY})
    if not data:
        return None
    for item in data:
        name = (item.get("commodityName") or "").lower()
        if "soybean" in name and ("meal" in name or "cake" in name):
            return item.get("commodityCode")
    return None


def get_latest_market_year():
    now = datetime.now(timezone.utc)
    # 豆粕的美国市场年一般是10月-次年9月，这里做一个简单近似
    return now.year if now.month >= 10 else now.year - 1


def fetch_esr_export_sales():
    code = get_soybean_meal_esr_code()
    if not code:
        return {"available": False, "reason": "未能找到豆粕的ESR商品编码"}

    my = get_latest_market_year()
    url = f"{USDA_BASE}/esr/exports/commodityCode/{code}/allCountries/marketYear/{my}"
    rows, debug = fetch_json_debug(url, headers={"X-Api-Key": USDA_API_KEY})
    if not rows:
        return {"available": False, "reason": "ESR接口无返回数据", "debug": debug}

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

    result = {
        "available": True,
        "weekEnding": latest_week_date,
        "latestTotalMT": latest_total,
        "prevTotalMT": prev_total,
        "wowChangePct": wow_change_pct,
        "chinaLatestMT": china_latest,
        "source": "USDA-FAS ESR API",
        "sourceUrl": "https://apps.fas.usda.gov/esrqs/",
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
    data = fetch_json(f"{USDA_BASE}/psd/commodities", headers={"X-Api-Key": USDA_API_KEY})
    if not data:
        return None
    for item in data:
        name = (item.get("commodityName") or "").lower()
        if "soybean" in name and "meal" in name:
            return item.get("commodityCode")
    return None


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


def fetch_psd_supply_demand():
    code = get_soybean_meal_psd_code()
    if not code:
        return {"available": False, "reason": "未能找到豆粕的PSD商品编码"}

    year = datetime.now(timezone.utc).year
    url = f"{USDA_BASE}/psd/commodity/{code}/country/US/year/{year}"
    rows, debug = fetch_json_debug(url, headers={"X-Api-Key": USDA_API_KEY})
    if not rows:
        # 尝试上一年（有些数据在跨年时还未更新到今年）
        year -= 1
        url = f"{USDA_BASE}/psd/commodity/{code}/country/US/year/{year}"
        rows, debug = fetch_json_debug(url, headers={"X-Api-Key": USDA_API_KEY})
    if not rows:
        return {"available": False, "reason": "PSD接口无返回数据", "debug": debug}

    # 实际部署后发现真实返回结构是数字ID (attributeId/unitId)，不是字符串名称，
    # 所以要么a)有attributeName字符串字段（旧版/其他数据源可能这样），要么b)只有attributeId数字，
    # 这里两种情况都兼容处理。
    has_string_names = any(r.get("attributeName") for r in rows)

    wanted_normalized = {
        "ending stocks": "Ending Stocks",
        "production": "Production",
        "total supply": "Total Supply",
        "domestic consumption": "Domestic Consumption",
    }
    out = {}
    seen_attrs = set()

    if has_string_names:
        # 情况A：接口真的返回了字符串字段名（用容错匹配：忽略大小写、多余空格）
        for r in rows:
            attr = r.get("attributeName") or r.get("AttributeName") or r.get("attribute_name")
            val = r.get("value") if "value" in r else r.get("Value")
            if attr is None:
                continue
            seen_attrs.add(attr)
            norm = " ".join(attr.lower().split())
            if norm in wanted_normalized:
                out[wanted_normalized[norm]] = val
    else:
        # 情况B（实测中遇到的真实情况）：只有数字 attributeId，需要额外查名称对照表
        attr_map, attr_map_source = get_psd_attribute_names()
        if attr_map:
            # 同一个 attributeId 可能有多个月份的记录，取 calendarYear+month 最新的一条
            rows_sorted = sorted(rows, key=lambda r: (r.get("calendarYear") or "", r.get("month") or ""))
            latest_by_attr = {}
            for r in rows_sorted:
                aid = r.get("attributeId")
                if aid is not None:
                    latest_by_attr[aid] = r  # 排序后一路覆盖，最后剩下的就是每个attributeId最新一条
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

    result = {
        "available": True,
        "marketYear": year,
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
            "sampleRawRow": rows[0] if rows else None,
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
        debugs[state] = debug
        if not rows:
            out[state] = {"available": False}
            continue
        # 取最新一条记录；字段名为 D0-D4 的百分比（各版本字段可能是 D0..D4 或 d0..d4，做兼容）
        rows_sorted = sorted(rows, key=lambda r: r.get("ValidStart") or r.get("validStart") or "")
        latest = rows_sorted[-1]

        def g(*keys):
            for k in keys:
                if k in latest and latest[k] is not None:
                    return latest[k]
            return None

        d2_plus = (g("D2", "d2") or 0) + (g("D3", "d3") or 0) + (g("D4", "d4") or 0)
        out[state] = {
            "available": True,
            "validDate": g("ValidStart", "validStart", "MapDate", "mapDate"),
            "d0": g("D0", "d0"),
            "d1": g("D1", "d1"),
            "d2": g("D2", "d2"),
            "d3": g("D3", "d3"),
            "d4": g("D4", "d4"),
            "severeOrWorsePct": round(d2_plus, 1),
        }

    available_states = {k: v for k, v in out.items() if v.get("available")}
    if not available_states:
        return {"available": False, "reason": "USDM接口未返回任何州的数据", "debug": debugs}

    avg_severe = sum(v["severeOrWorsePct"] for v in available_states.values()) / len(available_states)

    return {
        "available": True,
        "byState": out,
        "avgSevereOrWorsePct": round(avg_severe, 1),
        "source": "US Drought Monitor (NDMC/USDA/NOAA联合发布)",
        "sourceUrl": "https://droughtmonitor.unl.edu/",
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

    result = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "cbotPrice": fetch_cbot_price(),
        "droughtMonitor": fetch_drought_monitor(),
        "exportSales": fetch_esr_export_sales() if USDA_API_KEY else {
            "available": False,
            "reason": "缺少 USDA_API_KEY",
        },
        "supplyDemand": fetch_psd_supply_demand() if USDA_API_KEY else {
            "available": False,
            "reason": "缺少 USDA_API_KEY",
        },
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] 数据已写入 {OUTPUT_PATH}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
