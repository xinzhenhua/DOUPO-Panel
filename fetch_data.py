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
    headers = headers or {}
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - 抓取脚本，任何异常都要能继续
            last_err = e
            time.sleep(2 * (attempt + 1))
    print(f"[WARN] 请求失败: {url} -> {last_err}", file=sys.stderr)
    return None


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
    rows = fetch_json(url, headers={"X-Api-Key": USDA_API_KEY})
    if not rows:
        return {"available": False, "reason": "ESR接口无返回数据"}

    # 关键点：每周有多个国家的记录，不能直接用 rows[-1]/rows[-2]
    # （那样可能取到"同一周的另一个国家"而不是"上一周"）。
    # 必须先拿到"去重后的周次日期"排序，再取最近两个不同的周。
    unique_weeks = sorted(set(r.get("weekEndingDate") for r in rows if r.get("weekEndingDate")))
    if len(unique_weeks) < 2:
        return {"available": False, "reason": "数据量不足以计算环比（不足两个不同周次）"}

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

    return {
        "available": True,
        "weekEnding": latest_week_date,
        "latestTotalMT": latest_total,
        "prevTotalMT": prev_total,
        "wowChangePct": wow_change_pct,
        "chinaLatestMT": china_latest,
        "source": "USDA-FAS ESR API",
        "sourceUrl": "https://apps.fas.usda.gov/esrqs/",
    }


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


def fetch_psd_supply_demand():
    code = get_soybean_meal_psd_code()
    if not code:
        return {"available": False, "reason": "未能找到豆粕的PSD商品编码"}

    year = datetime.now(timezone.utc).year
    url = f"{USDA_BASE}/psd/commodity/{code}/country/US/year/{year}"
    rows = fetch_json(url, headers={"X-Api-Key": USDA_API_KEY})
    if not rows:
        # 尝试上一年（有些数据在跨年时还未更新到今年）
        year -= 1
        url = f"{USDA_BASE}/psd/commodity/{code}/country/US/year/{year}"
        rows = fetch_json(url, headers={"X-Api-Key": USDA_API_KEY})
    if not rows:
        return {"available": False, "reason": "PSD接口无返回数据"}

    wanted = {"Ending Stocks", "Production", "Total Supply", "Domestic Consumption"}
    out = {}
    for r in rows:
        attr = r.get("attributeName")
        if attr in wanted:
            out[attr] = r.get("value")

    return {
        "available": True,
        "marketYear": year,
        "endingStocks": out.get("Ending Stocks"),
        "production": out.get("Production"),
        "totalSupply": out.get("Total Supply"),
        "domesticConsumption": out.get("Domestic Consumption"),
        "source": "USDA-FAS PSD API (WASDE同源数据)",
        "sourceUrl": "https://apps.fas.usda.gov/psdonline/",
    }


# ---------------------------------------------------------------------------
# 3. CBOT 豆粕期货价格（Yahoo Finance 非官方接口，免注册）
# ---------------------------------------------------------------------------
def fetch_cbot_price():
    # ZM=F 是 CBOT 豆粕期货代码；这个 chart 接口是非官方但被广泛使用
    url = "https://query1.finance.yahoo.com/v8/finance/chart/ZM=F?interval=1d&range=5d"
    data = fetch_json(url, headers={"User-Agent": "Mozilla/5.0"})
    if not data:
        return {"available": False, "reason": "Yahoo Finance接口无返回（可能被限流或接口变更）"}

    try:
        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        timestamps = result["timestamp"]
        # 过滤掉 None（非交易日）
        pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
        if len(pairs) < 2:
            return {"available": False, "reason": "价格数据点不足"}
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
        return {"available": False, "reason": f"数据解析失败: {e}"}


# ---------------------------------------------------------------------------
# 4. 美国干旱监测 (US Drought Monitor) —— 真正的官方干旱等级数据
#    区别于天气预报推算的"风险"，这是 NDMC/USDA/NOAA 每周四联合发布的
#    实测干旱分级 (D0-D4)，网页端(index.html)里天气板块用降雨预报算的是
#    "风险倾向"，这里补的是"官方实际认定的干旱状态"。
# ---------------------------------------------------------------------------
DROUGHT_STATES = ["IA", "IL", "MN"]  # 爱荷华/伊利诺伊/明尼苏达，豆粕主产区


def fetch_drought_monitor():
    from datetime import timedelta

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=14)  # 拉两周，确保能覆盖最近一次周四更新

    out = {}
    for state in DROUGHT_STATES:
        url = (
            "https://usdmdataservices.unl.edu/api/StateStatistics/"
            f"GetDroughtSeverityStatisticsByArea?aoi={state}"
            f"&startdate={start.strftime('%-m/%-d/%Y')}&enddate={end.strftime('%-m/%-d/%Y')}"
            "&statisticsType=1"
        )
        rows = fetch_json(url, headers={"Accept": "application/json"})
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
        return {"available": False, "reason": "USDM接口未返回任何州的数据"}

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
