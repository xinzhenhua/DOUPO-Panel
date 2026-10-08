# -*- coding: utf-8 -*-
"""
历史回填(一次性，手动运行)
==========================
用法：
  python3 backfill_history.py                      # 四项全部回填
  python3 backfill_history.py --only us_stu,meal_stu
  python3 backfill_history.py --start 2020-01-01   # Mysteel两项的起始日期
  python3 backfill_history.py --no-bodies          # Mysteel两项只用搜索摘要，不逐篇抓正文(更快，但覆盖少很多)
  python3 backfill_history.py --only calibrate     # 不联网：只基于已有序列重新生成校准摘要
GitHub上：Actions → "回填历史数据" → Run workflow(需要USDA_API_KEY这个Secret，跟每小时同步用的是同一个)。

回填四项(数据源本身能往前拉的)：
  us_stu     美豆库存消费比：PSD按市场年度逐年查，期末库存÷(国内消费+出口)
  esr        美豆出口净销售：ESR按市场年度取整年的逐周数据，全部国家合计(另存中国/未知)
  meal_stu   国内豆粕库消比：Mysteel《全国豆粕供需平衡表》，逐篇解析(先正文后摘要)
  margin     榨利(盘面毛利)：按合约窗口回填，每日累积只记窗口内的点
  spread     月差/期限结构(近月−远月，占近月价%)：同上
  feed_days  饲料企业豆粕库存天数：Mysteel周报，逐篇解析(含2021-2022年的旧措辞)
  soy_import 海关大豆月度进口量：多篇交叉验证，排除累计/去年/对比/分国别
  arrival    大豆到港预报(2024-02~2026-06，'N船，共计约X万吨'的严格结构；双口径的月份不采用)
  crush_rate 油厂开机率(日频快讯，快讯只保留到2024-12，分90天窗口搜索)
  (周度库存回填meal_stock与采样诊断sample已在v99移除，见REMOVED_backfill_sample_and_meal_stock.md；周度库存改靠每次抓取累积)

★没法在开发环境联网验证：跑完会生成 data/history/_backfill_report.json(每个序列的点数、起止日期、最小/最大/中位、
  缺失的月份、疑似异常点)——把这个报告发我，我据此校准阈值，也能发现解析出错的地方。
★回填的是"现在能查到的数字"，不是"当时市场看到的数字"：PSD/ESR会被USDA事后修订，Mysteel月度平衡表里的
  更早月份是预测值被后续文章更新过的版本。拿来算"当前值在历史上的位置"没问题，但不能直接拿去做严格的回测。
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import fetch_data as fd
import history_store as hs
import mysteel_parsers as mp



# ---------------------------------------------------------------------------
# 统计/诊断工具(报告里用)
# ---------------------------------------------------------------------------
def quantiles(vals, qs=(5, 10, 20, 25, 50, 75, 80, 90, 95)):
    """线性插值分位数。返回{"p5":..,"p10":..}。"""
    if not vals:
        return {}
    srt = sorted(vals)
    out = {}
    for q in qs:
        pos = (len(srt) - 1) * q / 100
        lo, hi = int(pos), min(int(pos) + 1, len(srt) - 1)
        out[f"p{q}"] = round(srt[lo] + (srt[hi] - srt[lo]) * (pos - lo), 2)
    return out


def share(vals, pred):
    return round(sum(1 for v in vals if pred(v)) / len(vals) * 100, 1) if vals else None


def find_outliers(points, k=8, z_min=6.0):
    """稳健异常点：|v-中位数| / (1.4826×MAD) 最大的k个(超过z_min才算)，带前后相邻点，方便判断是真实极端值还是数据毛病。"""
    if len(points) < 20:
        return []
    vals = [p["v"] for p in points]
    med = statistics.median(vals)
    mad = statistics.median(abs(v - med) for v in vals)
    if mad == 0:
        return []
    scored = sorted(((abs(p["v"] - med) / (1.4826 * mad), i) for i, p in enumerate(points)), reverse=True)
    out = []
    for z, i in scored[:k]:
        if z < z_min:
            break
        out.append({"d": points[i]["d"], "v": points[i]["v"], "z": round(z, 1),
                    "prev": points[i - 1]["v"] if i > 0 else None, "next": points[i + 1]["v"] if i + 1 < len(points) else None})
    return out


def esr_boundary_weeks(points):
    """每年8月20日~9月20日那几周的净销售(市场年度切换前后)，用来判断9月初的极端值是不是切换造成的。"""
    out = {}
    for p in points:
        m, d = int(p["d"][5:7]), int(p["d"][8:10])
        if (m == 8 and d >= 20) or (m == 9 and d <= 20):
            out.setdefault(p["d"][:4], []).append(f'{p["d"][5:]}:{int(p["v"])}')
    return out


# 独立来源的校验点：Mysteel英文站周报(mysteel.net/analysis)里的全国豆粕库存(万吨)。d=报告发布日期(中文站发布日期可能差几天)。
# 用来核对回填的周度库存有没有取错(比如取成大豆库存)。
MEAL_STOCK_CHECKPOINTS = [
    ("2026-W05", 93.04), ("2026-W12", 67.05), ("2026-W13", 67.68), ("2026-W15", 62.05), ("2026-W16", 61.38),
    ("2026-W22", 34.74), ("2026-W23", 50.65), ("2026-W27", 72.47), ("2026-W31", 100.34), ("2026-W35", 116.73),
]


def meal_stock_spot_checks(points, tol_wan=0.1):
    """按"周次"(点的x.week，形如2026-W35)匹配校验点，数值差<=tol_wan万吨算通过。
    ★不按日期最近匹配：上一份报告里第31周校验点(8月3日)没有对应的点，被错配到第30周的点(7月27日，96.73)，误报"不一致"。
    没有x.week的点(旧版数据)匹配不上，如实报告缺失。"""
    by_week = {p["x"]["week"]: p for p in points if isinstance(p.get("x"), dict) and p["x"].get("week")}
    out = []
    for wk, v in MEAL_STOCK_CHECKPOINTS:
        p = by_week.get(wk)
        if p is None:
            out.append({"week": wk, "expected": v, "result": "缺失(没有这一周的点)"})
        else:
            out.append({"week": wk, "expected": v, "got": p["v"], "gotDate": p["d"], "result": "通过" if abs(p["v"] - v) <= tol_wan else "不一致"})
    return out


def calibration_summary(base_dir=None):
    """基于已有的历史序列，给出校准阈值需要的数字。纯本地计算，不联网。"""
    out = {}
    s = hs.load_series("us_stocks_to_use", base_dir)["points"]
    if s:
        vals = [p["v"] for p in s]
        out["us_stocks_to_use"] = {
            "n": len(vals), "quantiles": quantiles(vals),
            "latest": s[-1], "latestPercentile": hs.percentile_rank(s[-1]["v"], [p["v"] for p in s[:-1]]) if len(s) > 1 else None,
            "currentThresholds": {"tight<5": {"shareOfYears%": share(vals, lambda v: v < 5), "years": [p["d"] for p in s if p["v"] < 5]},
                                  "loose>10": {"shareOfYears%": share(vals, lambda v: v > 10), "years": [p["d"] for p in s if p["v"] > 10]}},
            "allValues": {p["d"]: p["v"] for p in s},
        }
    w = hs.load_series("esr_net_sales", base_dir)["points"]
    if len(w) > 10:
        rows = []       # (日期, 相对前4周均值的百分比 或 None, 是否基数太小)
        for i in range(4, len(w)):
            try:
                gap_ok = all((date.fromisoformat(w[j + 1]["d"][:10]) - date.fromisoformat(w[j]["d"][:10])).days <= 10 for j in range(i - 4, i))
            except ValueError:
                gap_ok = False
            if not gap_ok:
                continue
            avg = sum(p["v"] for p in w[i - 4:i]) / 4
            pct = round((w[i]["v"] - avg) / abs(avg) * 100, 1) if avg else None
            rows.append((w[i]["d"], pct, avg < 100000))
        usable = [r for r in rows if r[1] is not None and not r[2]]
        pcts = [r[1] for r in usable]
        thr = 40
        first_weeks = [r for r in usable if (r[0][5:7] == "09" and int(r[0][8:10]) <= 14)]
        out["esr_net_sales"] = {
            "weeksEvaluated": len(rows), "weeksWithBaseBelow100k(判中性)": sum(1 for r in rows if r[2]),
            "signalShare%(当前±40%)": {"bullish": share(pcts, lambda v: v > thr), "bearish": share(pcts, lambda v: v < -thr), "neutral": share(pcts, lambda v: -thr <= v <= thr)},
            "pctVs4wAvgQuantiles": quantiles(pcts, (5, 10, 20, 25, 50, 75, 80, 90, 95)),
            "septFirst2WeeksSignalShare%": {"n": len(first_weeks), "bullish": share([r[1] for r in first_weeks], lambda v: v > thr), "bearish": share([r[1] for r in first_weeks], lambda v: v < -thr)},
            "byMonthBullishShare%": {f"{m:02d}": share([r[1] for r in usable if int(r[0][5:7]) == m], lambda v: v > thr) for m in range(1, 13)},
        }
    m = hs.load_series("meal_stu", base_dir)["points"]
    if m:
        vals = [p["v"] for p in m]
        import cn_calendar
        fest = [p["v"] for p in m if cn_calendar.festival_cohort(p["d"]) == "春节扰动月"]
        norm = [p["v"] for p in m if cn_calendar.festival_cohort(p["d"]) == "平常月"]
        out["meal_stu"] = {"n": len(vals), "quantiles": quantiles(vals),
                           "currentThresholds(v84: 松阈值14→16)": {"tight<=10": share(vals, lambda v: v <= 10), "loose>=14": share(vals, lambda v: v >= 14), "loose>=16": share(vals, lambda v: v >= 16)},
                           "byFestivalCohort": {"春节扰动月": {"n": len(fest), "values": sorted(fest)},
                                                "平常月": {"n": len(norm), "quantiles": quantiles(norm), "share>=14%": share(norm, lambda v: v >= 14), "share>=16%": share(norm, lambda v: v >= 16), "share<=10%": share(norm, lambda v: v <= 10)}},
                           "allValues": {p["d"]: p["v"] for p in m}}
    for ctype in hs.CRUSH_MARGIN_WINDOWS:
        cm = hs.load_series("crush_margin_" + ctype, base_dir)["points"]
        if cm:
            vals = [p["v"] for p in cm]
            by_year = Counter(p["d"][:4] for p in cm)
            by_month = {f"{m:02d}": round(statistics.median([p["v"] for p in cm if int(p["d"][5:7]) == m]), 1) for m in range(1, 13) if any(int(p["d"][5:7]) == m for p in cm)}
            out["crush_margin_" + ctype] = {"n": len(vals), "quantiles": quantiles(vals), "pointsPerYear": dict(by_year),
                                            "medianByMonth": by_month, "share<0": share(vals, lambda v: v < 0), "share>300": share(vals, lambda v: v > 300)}
    fd_pts = hs.load_series("feed_days", base_dir)["points"]
    if fd_pts:
        vals = [p["v"] for p in fd_pts]
        out["feed_days"] = {"n": len(vals), "quantiles": quantiles(vals), "coverage": hs.coverage_problem(fd_pts, "weekly") or "样本连续，可用",
                            "medianByMonth": {f"{m:02d}": round(statistics.median([p["v"] for p in fd_pts if int(p["d"][5:7]) == m]), 2) for m in range(1, 13) if any(int(p["d"][5:7]) == m for p in fd_pts)},
                            "momIndependentCheck": feed_days_mom_check(fd_pts)}
    for ctype in hs.CRUSH_MARGIN_WINDOWS:
        ts = hs.load_series("term_spread_" + ctype, base_dir)["points"]
        if ts:
            vals = [p["v"] for p in ts]
            by_month = {f"{m:02d}": round(statistics.median([p["v"] for p in ts if int(p["d"][5:7]) == m]), 2) for m in range(1, 13) if any(int(p["d"][5:7]) == m for p in ts)}
            out["term_spread_" + ctype] = {"n": len(vals), "quantiles": quantiles(vals), "pointsPerYear": dict(Counter(p["d"][:4] for p in ts)),
                                           "medianByMonth(%)": by_month, "share<0(远月升水)": share(vals, lambda v: v < 0)}
    k_all = hs.load_series("meal_stock", base_dir)["points"]
    k = hs.usable_points("meal_stock", k_all)        # ★只用口径断点(2024-01-05)之后的点；之前的旧口径点不可比，不参与分位/阈值校准
    if k_all:
        brk = hs.SERIES_BREAKS["meal_stock"]
        vals = [p["v"] for p in k]
        out["meal_stock"] = {"n": len(vals), "nTotalInFile": len(k_all), "nExcluded": len(k_all) - len(k),
                             "excludedReason": f"{len(k_all) - len(k)}个点在{brk[0]}之前：{brk[1]}",
                             "quantiles": quantiles(vals) if vals else None,
                             "currentThresholds": {"tight<50": share(vals, lambda v: v < 50), "loose>100": share(vals, lambda v: v > 100)} if vals else None,
                             "pointsPerYear": dict(Counter(p["d"][:4] for p in k)), "coverage": (hs.coverage_problem(k, "weekly") or "样本连续，可用") if k else "没有断点之后的点",
                             "spotChecks(独立来源Mysteel英文站周报)": meal_stock_spot_checks(k)}
    sus = hs.excluded_points("meal_stu", hs.load_series("meal_stu", base_dir)["points"])
    if sus:
        out["meal_stu_excluded"] = [{"d": d, "reason": r} for d, r in sus]
    # 榨利/月差的窗口与阈值校准诊断(v98)：年水平漂移、同月样本充足度、现行80/20规则历史触发率、阈值敏感性、去掉年水平后的对比、有效样本数。
    #   纯本地计算；出错只记错误，不影响上面的校准摘要。详见calibrate_margin_spread.py。
    try:
        import calibrate_margin_spread as _cms
        ms = _cms.margin_spread_calibration(base_dir)
        if ms:
            out["marginSpreadCalibration"] = ms
    except Exception as e:  # noqa: BLE001
        out["marginSpreadCalibration_error"] = f"{type(e).__name__}: {str(e)[:160]}"
    return out


def _report_entry(key, base_dir, added, notes=None, extra=None):
    series = hs.load_series(key, base_dir)
    pts = series["points"]
    vals = [p["v"] for p in pts]
    entry = {"key": key, "name": series["name"], "unit": series["unit"], "freq": series["freq"],
             "added": added, "total": len(pts),
             "first": pts[0]["d"] if pts else None, "last": pts[-1]["d"] if pts else None}
    if vals:
        srt = sorted(vals)
        entry.update({"min": round(srt[0], 2), "max": round(srt[-1], 2), "median": round(srt[len(srt) // 2], 2)})
        entry["lowest3"] = [{"d": p["d"], "v": p["v"]} for p in sorted(pts, key=lambda p: p["v"])[:3]]
        entry["highest3"] = [{"d": p["d"], "v": p["v"]} for p in sorted(pts, key=lambda p: -p["v"])[:3]]
    if series["freq"] == "weekly" and len(pts) >= 20:
        entry["outliers(稳健z>6)"] = find_outliers(pts)
    if series["freq"] == "monthly" and len(pts) >= 2:
        entry["missingMonths"] = _missing_months([p["d"] for p in pts])
    if series["freq"] == "weekly" and len(pts) >= 2:
        entry["gapsOver10Days"] = _weekly_gaps([p["d"] for p in pts])
    if notes:
        entry["notes"] = notes
    if extra:
        entry.update(extra)
    return entry


def _missing_months(ds):
    ys = [(int(d[:4]), int(d[5:7])) for d in ds]
    lo, hi = min(ys), max(ys)
    have, out = set(ys), []
    y, m = lo
    while (y, m) <= hi:
        if (y, m) not in have:
            out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _weekly_gaps(ds):
    from datetime import date
    days = sorted(date.fromisoformat(d[:10]) for d in ds)
    return [f"{a.isoformat()}→{b.isoformat()}" for a, b in zip(days, days[1:]) if (b - a).days > 10]


# ---------------------------------------------------------------------------
# 1. 美豆库存消费比(PSD按市场年度)
# ---------------------------------------------------------------------------
def backfill_us_stocks_to_use(base_dir=None, from_year=2006, to_year=None):
    now = datetime.now(timezone.utc)
    to_year = to_year or now.year + 1
    code, dbg = fd.get_soybean_psd_code()
    if not code:
        return {"key": "us_stocks_to_use", "error": "找不到大豆的PSD商品编码", "debug": dbg}
    attr_map, _ = fd.get_psd_attribute_names()
    pts, missing, no_data = [], [], []
    for y in range(from_year, to_year + 1):
        rows, _dbg = fd.fetch_json_debug(f"{fd.USDA_BASE}/psd/commodity/{code}/country/US/year/{y}", headers={"X-Api-Key": fd.USDA_API_KEY})
        if not rows:
            missing.append(y)
            continue
        out, _seen, _named, vintage = fd._parse_psd_rows(rows, attr_map)
        es, dc, ex = out.get("Ending Stocks"), out.get("Domestic Consumption"), out.get("Exports")
        total = (dc + ex) if (dc is not None and ex is not None) else None
        if es is None or not total:
            no_data.append(y)
            continue
        stu = round(es / total * 100, 2)
        if not 0.5 <= stu <= 60:      # 大豆库消比历史上大约2.5%~25%，超出这个范围一定是取错了
            no_data.append(y)
            continue
        pts.append({"d": str(y), "v": stu, "x": {"endingStocks": es, "domestic": dc, "exports": ex,
                                                   "vintage": f"{vintage[0]}-{vintage[1]}" if vintage else None}})
    series, changed = hs.record_points("us_stocks_to_use", pts, base_dir)
    return _report_entry("us_stocks_to_use", base_dir, len(pts),
                         notes=[f"接口无返回的年份: {missing}" if missing else "所有年份都有返回",
                                f"取不到期末库存/消费/出口或数值荒谬的年份: {no_data}" if no_data else "所有年份字段齐全"])


# ---------------------------------------------------------------------------
# 2. 美豆出口净销售(ESR逐周)
# ---------------------------------------------------------------------------
def backfill_esr_weekly(base_dir=None, from_year=2015, to_year=None):
    now = datetime.now(timezone.utc)
    to_year = to_year or now.year + 1
    code, dbg = fd.get_soybean_esr_code()
    if not code:
        return {"key": "esr_net_sales", "error": "找不到大豆的ESR商品编码", "debug": dbg}
    by_week, empty_years, fields_missing = {}, [], []
    for y in range(from_year, to_year + 1):
        rows, _dbg = fd.fetch_json_debug(f"{fd.USDA_BASE}/esr/exports/commodityCode/{code}/allCountries/marketYear/{y}", headers={"X-Api-Key": fd.USDA_API_KEY})
        if not rows:
            empty_years.append(y)
            continue
        if not any(f in r for r in rows for f in fd.ESR_NET_SALES_FIELDS):
            fields_missing.append(y)      # 没有净销售字段的年份不能拿装船量冒充，跳过
            continue
        weeks = {}
        for r in rows:
            w = r.get("weekEndingDate")
            if w:
                weeks.setdefault(w, []).append(r)
        for w, rs in weeks.items():          # 后面的市场年度覆盖前面的(同一周只算一次，跟每小时同步的逻辑一致)
            china = [r for r in rs if fd._is_china(r)]
            unknown = [r for r in rs if fd._is_unknown_dest(r)]
            by_week[w[:10]] = {"v": sum(fd._esr_net_sales(r) for r in rs),
                               "x": {"chinaNetSalesMT": sum(fd._esr_net_sales(r) for r in china),
                                     "unknownNetSalesMT": sum(fd._esr_net_sales(r) for r in unknown)}}
    pts = [{"d": d, "v": v["v"], "x": v["x"]} for d, v in sorted(by_week.items())]
    hs.record_points("esr_net_sales", pts, base_dir)
    return _report_entry("esr_net_sales", base_dir, len(pts),
                         notes=[f"接口无返回的市场年度: {empty_years}" if empty_years else "所有市场年度都有返回",
                                f"没有净销售字段(已跳过)的年度: {fields_missing}" if fields_missing else "所有年度都有净销售字段"],
                         extra={"boundaryWeeks(每年8/20~9/20，看市场年度切换前后有没有异常)": esr_boundary_weeks(hs.load_series("esr_net_sales", base_dir)["points"])})


# ---------------------------------------------------------------------------
# Mysteel文章搜索(两项共用)
# ---------------------------------------------------------------------------
_MY_HEADERS = {"token": "-1", "Origin": "https://search.mysteel.com", "Referer": "https://search.mysteel.com/fastcomment.html",
               "X-Requested-With": "XMLHttpRequest"}


def _search_articles(query, start, end, max_pages=40, url=None, sleep_s=0.5):
    """翻页收齐搜索结果。返回(items, total, 说明)。url默认是文章搜索接口；快讯(开机率)用 fd.MYSTEEL_SEARCH_URL。"""
    url = url or fd.MYSTEEL_ARTICLE_SEARCH_URL
    items, total, note = [], 0, None
    for page in range(1, max_pages + 1):
        payload = {"query": query, "startTime": start.strftime("%Y-%m-%d 00:00:00"), "endTime": end.strftime("%Y-%m-%d 23:59:59"),
                   "sortType": "complex", "platform": "pc", "pageNo": page, "pageSize": 20}
        data, dbg = fd.fetch_json_debug(url, headers=_MY_HEADERS, post_data=payload)
        if not isinstance(data, dict) or data.get("resultCode") != 0:
            note = f"第{page}页请求失败或返回异常，已用前{page - 1}页" if page > 1 else "搜索接口无返回/返回异常"
            break
        lst = data.get("dataList") or []
        total = data.get("total") or total
        items.extend(i for i in lst if isinstance(i, dict))
        if len(lst) < 20 or page * 20 >= total:
            break
        time.sleep(sleep_s)
    else:
        note = f"翻到{max_pages}页上限，可能还有更早的文章没翻到"
    return items, total, note


def _pub(item):
    try:
        return datetime.strptime(str(item.get("publishTime", ""))[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 3. 国内豆粕库消比(月度平衡表)
# ---------------------------------------------------------------------------
def backfill_meal_stu(base_dir=None, start=None, today=None, fetch_bodies=True, max_bodies=90, sleep_s=0.8):
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    start = start or datetime(2020, 1, 1).date()
    now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    items, total, note = _search_articles(fd.MEAL_BALANCE_QUERY, datetime(start.year, start.month, start.day), now_bj)
    arts = []
    for it in items:
        if fd.MEAL_BALANCE_TITLE_KEY in str(it.get("title") or "") and _pub(it):
            arts.append((_pub(it), it))
    arts.sort(key=lambda a: a[0], reverse=True)
    notes = [note] if note else []
    if not arts:
        return {"key": "meal_stu", "error": "没有搜到标题含'豆粕供需平衡表'的文章", "searchTotal": total, "notes": notes}

    cands = {}          # (年,月) → [(pub, 来源, 记录)]
    bodies_ok = 0
    body_problems = []   # 正文没取到/没解析出东西的文章：原因+原文片段，回填报告里给出来，方便修解析规则
    for idx, (pub, it) in enumerate(arts):
        if fetch_bodies and idx < max_bodies and it.get("url") and fd.is_trusted_article_url(it["url"]):
            raw, dbg = fd.fetch_text_debug(it["url"], headers={"Referer": "https://ncp.mysteel.com/"})
            if raw:
                region = fd._extract_article_region(fd._html_to_text(raw), str(it.get("title") or ""))
                recs = fd._parse_meal_balance_text(region, pub, keep_text=True)
                if any(fd._usable_meal_record(r)[0] is not None for r in recs.values()):
                    bodies_ok += 1
                elif len(body_problems) < 8:
                    body_problems.append({"pub": pub.isoformat(), "title": str(it.get("title"))[:40], "reason": "正文里没有解析出可用的库消比",
                                          "regionHead": region[:220]})
                for k, r in recs.items():
                    cands.setdefault(k, []).append((pub, 0, r))
            elif len(body_problems) < 8:
                body_problems.append({"pub": pub.isoformat(), "title": str(it.get("title"))[:40], "reason": f"正文请求失败({dbg.get('error') or dbg.get('httpStatus')})"})
            time.sleep(sleep_s)
        for k, r in fd._parse_meal_balance_text(it.get("content"), pub, keep_text=True).items():
            cands.setdefault(k, []).append((pub, 1, r))

    cur = (today.year, today.month)
    pts, unusable = [], []
    for k, lst in sorted(cands.items()):
        if k > cur:
            continue                       # 未来月份的预测不进历史
        # 发布越晚越接近实际值(预测会被后续文章更新)；同一篇里正文优先于摘要
        for pub, _pri, rec in sorted(lst, key=lambda c: (-c[0].toordinal(), c[1])):
            v, how = fd._usable_meal_record(rec)
            if v is not None:
                x = {"how": how}
                for key, fld in (("stock", "stock"), ("consumption", "consumption"), ("production", "production")):
                    if rec.get(fld) is not None:
                        x[key] = rec[fld]       # 存下当月库存/消费/产量：以后做"春节调整后库消比"用得上
                pts.append({"d": f"{k[0]}-{k[1]:02d}", "v": v, "pub": pub.isoformat(), "x": x})
                break
        else:
            seg = next((r.get("seg") for _p, _pri, r in sorted(lst, key=lambda c: (-c[0].toordinal(), c[1])) if r.get("seg")), "")
            unusable.append({"month": f"{k[0]}-{k[1]:02d}", "segment": seg})
    hs.record_points("meal_stu", pts, base_dir)
    notes.append(f"平衡表文章{len(arts)}篇(搜索总数{total})；正文可用{bodies_ok}篇" if fetch_bodies else f"平衡表文章{len(arts)}篇；未抓正文，只用摘要")
    extra = {}
    if unusable:
        notes.append(f"有月份标记但给不出库消比的月份共{len(unusable)}个(原文片段见unusableMonths)")
        extra["unusableMonths(前12个，附该月片段原文)"] = unusable[:12]
    if body_problems:
        extra["bodyProblems"] = body_problems
    return _report_entry("meal_stu", base_dir, len(pts), notes=notes, extra=extra)




# ---------------------------------------------------------------------------
# 5. 盘面压榨毛利(新浪日K线：豆粕M/豆油Y/豆二B同月份合约)
# ---------------------------------------------------------------------------
def _window_ok(d, ctype, expiry_year):
    """日期d(YYYY-MM-DD)是否落在这个合约类型(到期年expiry_year)的建议交易窗口内。(逻辑在history_store.window_ok，回填和每日累积共用)"""
    return hs.window_ok(d, ctype, expiry_year)


def backfill_crush_margin(base_dir=None, from_year=None, to_year=None, sleep_s=0.6):
    """★榨利的绝对数没有意义(毛利没扣加工费，几乎永远为正)，所以评分只能用"跟历史同期比的分位"。这里把过去几年各合约的
    建议交易窗口内的逐日毛利补齐：9月合约取4-7月、5月合约取12-3月、1月合约取8-11月(与前端合约窗口一致，不同年份才可比)。
    数据源：新浪日K线(ak.futures_zh_daily_sina)按合约取全部历史。⚠️已到期合约能不能取到没有验证——每个合约的取数结果都写进报告，
    取不到的会明确列出。"""
    now = datetime.now(timezone.utc)
    to_year = to_year or now.year + 1
    from_year = from_year or now.year - 8
    per_type, contracts = {t: [] for t in hs.CRUSH_MARGIN_WINDOWS}, []
    # 一次性清理：之前每日累积没有按窗口过滤，已经混进去的窗口外点(临近到期/刚滚动合约)要删掉，否则会污染"往年同月"的比较
    pruned = {t: hs.prune_out_of_window("crush_margin_" + t, t, base_dir, "contract") for t in hs.CRUSH_MARGIN_WINDOWS}
    for ctype, w in hs.CRUSH_MARGIN_WINDOWS.items():
        for year in range(from_year, to_year + 1):
            yy, mm = f"{year % 100:02d}", f"{w['contractMonth']:02d}"
            syms = {p: f"{p}{yy}{mm}" for p in ("M", "Y", "B")}
            klines, failed = {}, []
            for p, sym in syms.items():
                kd = fd.fetch_dce_daily_kline(sym, max_rows=6000)
                time.sleep(sleep_s)
                if kd.get("available") and kd.get("bars"):
                    klines[p] = kd["bars"]
                else:
                    failed.append(f"{sym}({str(kd.get('reason', ''))[:40]})")
            entry = {"type": ctype, "contract": f"{yy}{mm}", "failed": failed}
            if failed:
                contracts.append(entry)
                continue
            series = fd.crush_margin_series(klines["M"], klines["Y"], klines["B"])
            inwin = {d: v for d, v in series.items() if _window_ok(d, ctype, year)}
            entry.update({"daysAll3": len(series), "daysInWindow": len(inwin),
                          "first": min(inwin) if inwin else None, "last": max(inwin) if inwin else None})
            contracts.append(entry)
            per_type[ctype].extend({"d": d, "v": v, "x": {"contract": f"{yy}{mm}"}} for d, v in inwin.items())
    reports = []
    for ctype, pts in per_type.items():
        key = "crush_margin_" + ctype
        hs.record_points(key, pts, base_dir)
        reports.append(_report_entry(key, base_dir, len(pts)))
    failed_all = [c for c in contracts if c.get("failed")]
    return {"key": "crush_margin", "series": reports, "contracts": contracts, "prunedOutOfWindow": pruned,
            "notes": [f"共{len(contracts)}个合约，{len(failed_all)}个有合约取不到(已到期/未上市/接口问题)，见contracts里的failed",
                      f"清理了窗口外的旧点：{pruned}"]}


# ---------------------------------------------------------------------------
# 6. 饲料企业豆粕库存天数(Mysteel每周《全国主要地区饲料企业豆粕库存天数调查》)
# ---------------------------------------------------------------------------
# 已知的真实样本(来自第一次回填报告里出现过的2026-07-03那期摘要)：库存7.41天，环比+0.17，同比-0.50。
FEED_DAYS_CHECKPOINTS = [("2026-07-03", 7.41, 0.17, -0.50)]


def feed_days_mom_check(weeks, tol=0.015):
    """★独立校验：连续两周(相隔5~9天)的库存天数之差，应该等于文章里写的"环比"。
    没有外部数据源时，这是发现"解析取错了数"的最直接办法(比如把环比当成了库存，或取到了别的指标的天数)。
    环比在文章里通常只写两位小数，所以容差取0.015。weeks: 按日期升序的[{"d","v","x":{"mom","yoy"}}]"""
    from datetime import date as _d
    comparable = matched = 0
    bad = []
    for a, b in zip(weeks, weeks[1:]):
        gap = (_d.fromisoformat(b["d"][:10]) - _d.fromisoformat(a["d"][:10])).days
        mom = (b.get("x") or {}).get("mom")
        if not (5 <= gap <= 9) or mom is None:
            continue
        comparable += 1
        diff = round(b["v"] - a["v"], 2)
        if abs(diff - mom) <= tol:
            matched += 1
        elif len(bad) < 6:
            bad.append({"d": b["d"], "value": b["v"], "prevValue": a["v"], "computedChange": diff, "statedMom": mom})
    return {"comparable": comparable, "matched": matched, "mismatched": comparable - matched, "examples": bad}


def backfill_feed_days(base_dir=None, start=None, today=None, fetch_bodies=True, max_bodies=60, sleep_s=0.8):
    """饲料企业豆粕库存天数：这是需求端最直接的真实信号(饲料厂手里的豆粕还能用几天)。
    ★现状：后端抓取函数(fetch_mysteel_feed_days)只用一条真实样本验证过，从来没对真实接口跑过；别的周的写法我没见过。
      所以先回填+诊断：搜出所有《饲料企业豆粕库存天数调查》，摘要提不出就抓正文，逐周落盘，并报告——
      提取成功/失败各多少篇、失败的原文片段、日期范围与断档、环比独立校验(见feed_days_mom_check)、已知样本核对。
    评分要等这份报告确认解析可靠、积累出足够的历史分位之后才接。"""
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    start = start or datetime(2020, 1, 1).date()
    now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    items, total, note = _search_articles(fd.FEED_DAYS_QUERY, datetime(start.year, start.month, start.day), now_bj, max_pages=20)
    arts = sorted(((_pub(i), i) for i in items if _pub(i) and fd.FEED_DAYS_TITLE_KEY in str(i.get("title") or "")), key=lambda a: a[0], reverse=True)
    notes = [note] if note else []
    if not arts:
        return {"key": "feed_days", "error": f"没有搜到标题含'{fd.FEED_DAYS_TITLE_KEY}'的文章", "searchTotal": total,
                "skippedTitles": [str(i.get("title"))[:40] for i in items[:8]], "notes": notes}
    weeks, stats, fails, bodies = {}, Counter(), [], 0
    for idx, (pub, it) in enumerate(arts):
        content, title = str(it.get("content") or ""), str(it.get("title") or "")
        res, _rej = fd._extract_feed_days(content)
        how = "summary"
        region = ""
        if res is None and fetch_bodies and bodies < max_bodies and it.get("url") and fd.is_trusted_article_url(it["url"]):
            raw, dbg = fd.fetch_text_debug(it["url"], headers={"Referer": "https://ncp.mysteel.com/"})
            bodies += 1
            time.sleep(sleep_s)
            if raw:
                region = fd._extract_article_region(fd._html_to_text(raw), title)
                res, _rej = fd._extract_feed_days(region)
                how = "body"
            else:
                stats["正文请求失败"] += 1
                if len(fails) < 8:
                    fails.append({"pub": pub.isoformat(), "title": title[:50], "reason": f"正文请求失败({dbg.get('error') or dbg.get('httpStatus')})", "summary": content[:160]})
                continue
        if res is None:
            stats["摘要和正文都没提取出库存天数"] += 1
            if len(fails) < 8:
                fails.append({"pub": pub.isoformat(), "title": title[:50], "reason": "提取不出库存天数(措辞可能不同)", "summary": content[:160], "regionHead": region[:200]})
            continue
        stats[f"提取成功(来自{'摘要' if how == 'summary' else '正文'})"] += 1
        d = fd._feed_asof_date(it, pub)
        if d not in weeks or pub > weeks[d]["pub"]:
            weeks[d] = {"pub": pub, "res": res}
    pts = []
    for d, w in sorted(weeks.items()):
        x = {k: w["res"][k] for k in ("mom", "yoy") if w["res"].get(k) is not None}
        p = {"d": d.isoformat(), "v": w["res"]["value"]}
        if x:
            p["x"] = x
        pts.append(p)
    hs.record_points("feed_days", pts, base_dir)
    checks = []
    for cd, cv, cm, cy in FEED_DAYS_CHECKPOINTS:
        got = next((p for p in pts if p["d"] == cd), None)
        if got is None:
            checks.append({"date": cd, "expected": cv, "result": "缺失(这一期没有回填到)"})
        else:
            ok_ = abs(got["v"] - cv) < 0.005 and abs((got.get("x") or {}).get("mom", 9e9) - cm) < 0.005 and abs((got.get("x") or {}).get("yoy", 9e9) - cy) < 0.005
            checks.append({"date": cd, "expected": {"value": cv, "mom": cm, "yoy": cy}, "got": {"value": got["v"], **(got.get("x") or {})}, "result": "通过" if ok_ else "不一致"})
    notes.append(f"搜到《饲料企业豆粕库存天数调查》{len(arts)}篇(搜索总数{total})，抓了{bodies}篇正文")
    return _report_entry("feed_days", base_dir, len(pts), notes=notes,
                         extra={"extractStats": dict(stats), "failedSamples(前8篇)": fails,
                                "momIndependentCheck(连续两周库存之差 vs 文章写的环比)": feed_days_mom_check(sorted(pts, key=lambda p: p["d"])),
                                "knownSampleCheck": checks})

# ---------------------------------------------------------------------------
# 6. 月差/期限结构(新浪日K线：近月/远月豆粕合约)
# ---------------------------------------------------------------------------
def backfill_term_spread(base_dir=None, from_year=None, to_year=None, sleep_s=0.6):
    """与榨利回填同一套：各合约建议交易窗口内(9月合约4-7月、5月合约12-3月、1月合约8-11月)的逐日月差(占近月价格%)。
    9月合约=M{yy}09对M{yy+1}01；5月合约=M{yy}05对M{yy}09；1月合约=M{yy}01对M{yy}05。
    ⚠️已到期合约能不能从新浪取到没有验证——每个合约对的取数结果都写进报告，取不到的明确列出。"""
    now = datetime.now(timezone.utc)
    to_year = to_year or now.year + 1
    from_year = from_year or now.year - 8
    per_type, pairs = {t: [] for t in hs.CRUSH_MARGIN_WINDOWS}, []
    pruned = {t: hs.prune_out_of_window("term_spread_" + t, t, base_dir, "near") for t in hs.CRUSH_MARGIN_WINDOWS}      # 同榨利：先清理窗口外的旧点
    for ctype, w in hs.CRUSH_MARGIN_WINDOWS.items():
        cm = w["contractMonth"]
        far_month, year_add = fd.TERM_SPREAD_FAR[cm]
        for year in range(from_year, to_year + 1):
            near_sym = f"M{year % 100:02d}{cm:02d}"
            far_sym = f"M{(year + year_add) % 100:02d}{far_month:02d}"
            klines, failed = {}, []
            for tag, sym in (("near", near_sym), ("far", far_sym)):
                kd = fd.fetch_dce_daily_kline(sym, max_rows=6000)
                time.sleep(sleep_s)
                if kd.get("available") and kd.get("bars"):
                    klines[tag] = kd["bars"]
                else:
                    failed.append(f"{sym}({str(kd.get('reason', ''))[:40]})")
            entry = {"type": ctype, "near": near_sym, "far": far_sym, "failed": failed}
            if failed:
                pairs.append(entry)
                continue
            series = fd.term_spread_series(klines["near"], klines["far"])
            inwin = {d: v for d, v in series.items() if _window_ok(d, ctype, year)}
            entry.update({"daysBoth": len(series), "daysInWindow": len(inwin), "first": min(inwin) if inwin else None, "last": max(inwin) if inwin else None})
            pairs.append(entry)
            per_type[ctype].extend({"d": d, "v": v, "x": {"near": near_sym, "far": far_sym}} for d, v in inwin.items())
    reports = []
    for ctype, pts in per_type.items():
        key = "term_spread_" + ctype
        hs.record_points(key, pts, base_dir)
        reports.append(_report_entry(key, base_dir, len(pts)))
    failed_all = [p for p in pairs if p.get("failed")]
    return {"key": "term_spread", "series": reports, "pairs": pairs, "prunedOutOfWindow": pruned,
            "notes": [f"共{len(pairs)}对合约，{len(failed_all)}对有合约取不到(已到期/未上市/接口问题)，见pairs里的failed",
                      f"清理了窗口外的旧点：{pruned}"]}


# ---------------------------------------------------------------------------
# 8. 月度进口量 / 到港预报：用采样诊断拿到的真实措辞写的回填(解析器在mysteel_parsers.py，用真实样本测试)
# ---------------------------------------------------------------------------
# 只用搜索摘要(采样已验证摘要里就有数值)，不抓正文，不跟随任何链接。
# 写入的序列key/日期格式和每日累积完全一致(soy_import的d='YYYY-MM'，arrival_forecast的d=预报月份'YYYY-MM')，所以两者能合并。
def backfill_soy_import(base_dir=None, start=None, today=None, search=None, sleep_s=0.6, include_inferred_single=False):
    """中国大豆月度进口量(海关总署数据，Mysteel文章转述)。
    ★同一个月会在多篇文章里重复出现(2023-06有5篇)，所以按月交叉验证：多篇一致才采用(见mysteel_parsers.select_import_months)。
    只有一篇且年份是靠发布日期推断的月份默认不采用(可能出错)。海关合并公布的1-2月累计没有单月数据，缺失是真实的。"""
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    start = start or date(2022, 1, 1)
    search = search or _search_articles
    items, total, note = search("海关总署中国大豆进口量", datetime(start.year, start.month, start.day), datetime(today.year, today.month, today.day, 12), max_pages=60, url=fd.MYSTEEL_ARTICLE_SEARCH_URL, sleep_s=sleep_s)
    obs, rejected = [], []
    for it in items:
        d = _pub(it)
        if d is None:
            continue
        got, rej = mp.parse_soy_import(str(it.get("title") or "") + "。" + str(it.get("content") or ""), d.isoformat())
        obs += [(g["month"], g["value"], d.isoformat(), g["yearExplicit"]) for g in got]
        rejected += rej
    acc, doubt, skipped = mp.select_import_months(obs, include_inferred_single=include_inferred_single)
    pts = []
    for mo, info in sorted(acc.items()):
        v = info["value"]
        problem = fd._plausibility_problem("soyImport", v)
        if problem:
            skipped.append((mo, v, info["pubs"][0], f"超出合理范围: {problem}"))
            continue
        pts.append({"d": mo, "v": v, "pub": max(info["pubs"]), "x": {"how": info["how"], "n": info["n"]}})
    hs.record_points("soy_import", pts, base_dir)
    notes = [note] if note else []
    notes.append(f"搜到{len(items)}篇(搜索总数{total})，提取{len(obs)}条单月观察，采用{len(pts)}个月；海关合并公布的1-2月累计没有单月数据，缺失是真实的")
    return _report_entry("soy_import", base_dir, len(pts), notes=notes,
                         extra={"how": dict(Counter(p["x"]["how"] for p in pts)),
                                "doubtful(同月数值冲突)": [{"month": d["month"], "adopted": d["adopted"], "overruled": d["overruled"]} for d in doubt][:10],
                                "notAdopted(只有一篇且年份靠推断/超范围)": [{"month": m, "value": v, "pub": p, "why": w} for m, v, p, w in skipped][:12],
                                "excludedWordings(累计/去年/对比等，前8条)": rejected[:8]})


def backfill_arrival_forecast(base_dir=None, start=None, today=None, search=None, sleep_s=0.6):
    """大豆到港预报(Mysteel每月月底发下月预估，每月1篇)。只收"2024年9月份国内全样本油厂大豆到港预估133.5船，共计约867.75万吨"这类严格结构的句子。
    ★刻意不处理2026-06之后的新写法(一篇同时给当月+后两个月的预估，后两个月是'远月数据后期可能修正'的初步预估)：那是每日累积正在抓的，回填只补历史。
    ★同一篇里同一个月出现两个口径(2023-11~2024-01同时发布111家783.25万吨/123家845万吨，相差8%)时整月不采用，写进excluded。"""
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    start = start or date(2022, 1, 1)
    search = search or _search_articles
    items, total, note = search("大豆到港预报", datetime(start.year, start.month, start.day), datetime(today.year, today.month, today.day, 12), max_pages=60, url=fd.MYSTEEL_ARTICLE_SEARCH_URL, sleep_s=sleep_s)
    by_month, rejected = {}, []
    for it in items:
        d = _pub(it)
        if d is None:
            continue
        got, rej = mp.parse_arrival_forecast(str(it.get("content") or ""), d.isoformat())
        rejected += rej
        for g in got:
            # 同月多篇(修订/转载)：取发布最晚的一篇(最终预估)
            if g["month"] not in by_month or d.isoformat() > by_month[g["month"]]["pub"]:
                by_month[g["month"]] = {"value": g["value"], "ships": g["ships"], "pub": d.isoformat()}
    pts, skipped = [], []
    for mo, info in sorted(by_month.items()):
        problem = fd._plausibility_problem("arrivalForecast", info["value"])
        if problem:
            skipped.append({"month": mo, "value": info["value"], "why": f"超出合理范围: {problem}"})
            continue
        pts.append({"d": mo, "v": info["value"], "pub": info["pub"], "x": {"ships": info["ships"]}})
    hs.record_points("arrival_forecast", pts, base_dir)
    notes = [note] if note else []
    notes.append(f"搜到{len(items)}篇(搜索总数{total})，采用{len(pts)}个月；2026-06之后的新写法(一篇三个月预估)由每日累积接上，回填不处理")
    return _report_entry("arrival_forecast", base_dir, len(pts), notes=notes,
                         extra={"excluded(同一篇多个口径/超范围)": rejected[:10] + skipped[:5]})


# ---------------------------------------------------------------------------
# 9. 油厂开机率(日频快讯)：v98重做开机率评分规则(滚动365天分位)需要历史，所以现在回填(v96.3时有意没做，等规则要改时一起做)
# ---------------------------------------------------------------------------
# 快讯接口只保留到约2024-12-13(采样时确认)，所以起点2024-12-01；该接口对一个查询最多返回750条(采样时三个指标恰好都是750)，
# 所以必须分窗口搜索(每窗90天)，不然会漏掉更早的；某个窗口恰好返回750条时在报告里标出。
# 同一天多条快讯：取发布最晚的一条(与每日累积"最后一次运行胜出"一致)。只收"油厂开机率"(同一个接口里还有"砂石矿山开机率"这类别的行业)。
CRUSH_BACKFILL_FROM = date(2024, 12, 1)
CRUSH_WINDOW_DAYS = 90


SEARCH_CAP = 750      # Mysteel 搜索接口一次最多返回 750 条(真实报告：开机率的 8 个 90 天窗口全部恰好返回 750)


def _item_key(it):
    return str(it.get("url") or "") or (str(it.get("title") or "") + "|" + str(it.get("publishTime") or ""))


PAGE_SIZE = 20       # _search_articles 每页20条


def search_windowed(search, query, w_start, w_end, cap=SEARCH_CAP, probe=False, **kw):
    """在 [w_start, w_end](日期，含两端)内搜索；某个窗口返回满 cap 条(或接口报告的 total 达到 cap)就**对半切开重搜**，直到不再封顶。
    为什么：窗口返回恰好 cap 条无法区分"刚好这么多"和"被截断"，必须当作被截断；原来只在报告里提醒、不补救，开机率因此漏了约12%的交易日。
    返回 (items, info)：items 按 url(没有 url 用 标题+发布时间)去重；info={calls, splits, unresolved:[切到单日仍封顶的'日期~日期'], notes:[接口失败说明]}。
    叶子窗口无缝无重叠地覆盖原区间；接口失败(没有返回)不切(切了也没用)；单日仍封顶就标进 unresolved，不假装拿全了。
    kw(max_pages/url/sleep_s…)原样传给 search。"""
    info = {"calls": 0, "splits": 0, "probes": 0, "unresolved": [], "notes": []}
    seen = {}

    def go(a, b):
        a_dt, b_dt = datetime(a.year, a.month, a.day), datetime(b.year, b.month, b.day, 12)
        if probe:
            # ★先只请求第1页：接口会报告这个窗口的总数。总数达到 cap 就直接对半切，不再把750条翻完再丢掉(2026-10-08 真实：开机率回填因此跑满60分钟被取消)。
            #   第一页就是全部(少于一页)：直接用，不再请求；否则才整窗翻页。
            items1, total1, note1 = search(query, a_dt, b_dt, **dict(kw, max_pages=1))
            info["calls"] += 1
            info["probes"] += 1
            if note1:
                info["notes"].append(f"{a}~{b}: {note1}")
            capped1 = len(items1) >= cap or (total1 or 0) >= cap
            if capped1 and (b - a).days >= 1:
                mid = a + timedelta(days=(b - a).days // 2)
                info["splits"] += 1
                go(a, mid)
                go(mid + timedelta(days=1), b)
                return
            if not capped1 and len(items1) < PAGE_SIZE:
                for it in items1:
                    if isinstance(it, dict):
                        seen.setdefault(_item_key(it), it)
                return
        items, total, note = search(query, a_dt, b_dt, **kw)
        info["calls"] += 1
        if note:
            info["notes"].append(f"{a}~{b}: {note}")
        capped = len(items) >= cap or (total or 0) >= cap
        if capped and (b - a).days >= 1:
            mid = a + timedelta(days=(b - a).days // 2)
            info["splits"] += 1
            go(a, mid)
            go(mid + timedelta(days=1), b)
            return      # 父窗口被截断的结果丢弃，由两个子窗口覆盖
        if capped:
            info["unresolved"].append(f"{a}~{b}")
        for it in items:
            if isinstance(it, dict):
                seen.setdefault(_item_key(it), it)

    go(w_start, w_end)
    return list(seen.values()), info


def gap_ranges(days, gap_merge=4, max_days=90):
    """缺的日期 → 要搜索的日期段 [(起, 止)]。相隔≤gap_merge天(含周末)的合并成一段(少发请求)，更远的单独成段；每段超过max_days天的切成≤max_days天的块。"""
    runs = []
    for d in sorted(set(days)):
        if runs and (d - runs[-1][1]).days <= gap_merge:
            runs[-1][1] = d
        else:
            runs.append([d, d])
    out = []
    for a, b in runs:
        s0 = a
        while s0 <= b:
            e0 = min(s0 + timedelta(days=max_days - 1), b)
            out.append((s0, e0))
            s0 = e0 + timedelta(days=1)
    return out


CRUSH_TIME_BUDGET_S = 40 * 60      # 工作流总超时是60分钟，留足余量给装依赖和提交；超过就优雅地停，不被强杀


def backfill_crush_rate(base_dir=None, start=None, today=None, search=None, sleep_s=0.6, time_budget_s=CRUSH_TIME_BUDGET_S, clock=time.monotonic):
    """油厂开机率回填。★v101.5：只补历史里缺的交易日，并有时间预算。
    为什么：v101.4 的自适应切窗让它把整个22个月重新下载一遍(每个被截断的父窗口先翻完约38页再丢掉)，在真实环境里跑满60分钟被工作流取消，一个点都没保存。
    现在：①用交易日历算出历史里缺哪些交易日，只搜缺口附近(相隔≤4天合并成一段)，已有的点不覆盖；②每个窗口先探一页(probe)，总数达到750条就直接切，不再翻完；
    ③超过 time_budget_s 就停下，已补的保存，报告写 stoppedEarly 和还缺哪些天，再点一次接着补。历史为空(第一次)时与以前一样从起点按90天窗口无缝覆盖。"""
    import cn_calendar
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    start = start or CRUSH_BACKFILL_FROM
    search = search or _search_articles
    existing = {p.get("d") for p in hs.load_series("crush_rate", base_dir).get("points", [])}
    all_td, d0 = [], start
    while d0 <= today:
        if cn_calendar.dce_is_trading_day(d0):
            all_td.append(d0)
        d0 += timedelta(days=1)
    missing = [d for d in all_td if d.isoformat() not in existing]
    if existing:
        ranges = gap_ranges(missing, max_days=CRUSH_WINDOW_DAYS)
    else:       # 第一次：与以前一样，从起点到今天按90天窗口无缝覆盖
        ranges, w0 = [], start
        while w0 <= today:
            w1 = min(w0 + timedelta(days=CRUSH_WINDOW_DAYS - 1), today)
            ranges.append((w0, w1))
            w0 = w1 + timedelta(days=1)
    by_day, excluded, caps, windows, total_items = {}, [], [], 0, 0
    splits, probes, calls_n, search_notes = 0, 0, 0, []
    t0, stopped = clock(), False
    for a, b in ranges:
        if clock() - t0 > time_budget_s:
            stopped = True
            break
        items, sinfo = search_windowed(search, "全国动态全样本油厂开机率", a, b, probe=True, max_pages=60, url=fd.MYSTEEL_SEARCH_URL, sleep_s=sleep_s)
        windows += 1
        total_items += len(items)
        splits += sinfo["splits"]
        probes += sinfo["probes"]
        calls_n += sinfo["calls"]
        caps += sinfo["unresolved"]
        search_notes += sinfo["notes"]
        for it in items:
            d = _pub(it)
            if d is None or d.isoformat() in existing:        # 已有的点不覆盖(线上每天累积的和上次回填的都保留)
                continue
            got, rej = mp.parse_crush_rate(str(it.get("content") or ""), d.isoformat())
            if rej:
                excluded += rej
            if not got:
                continue
            stamp = str(it.get("publishTime") or "")
            if d.isoformat() not in by_day or stamp >= by_day[d.isoformat()][0]:
                by_day[d.isoformat()] = (stamp, got[0]["value"])
    pts = [{"d": k, "v": v} for k, (_, v) in sorted(by_day.items())]
    if pts:
        hs.record_points("crush_rate", pts, base_dir)
    still = [d.isoformat() for d in missing if d.isoformat() not in by_day]
    notes = [f"历史里已有{len(existing)}个点，{start}~{today}共{len(all_td)}个交易日，缺{len(missing)}个；搜了{windows}段(相隔≤4天的缺口合并)共搜到{total_items}条快讯，本次补上{len(pts)}个交易日；"
             "春节停机期的低值(如2025-01-26的9.80%)是真实数据，照常入库，但评分时的参照分布会把春节窗口去掉"]
    if splits:
        notes.append(f"自适应切窗{splits}次(先探一页，总数达到750条就对半切开重搜)，共{calls_n}次请求(其中探测{probes}次)")
    if stopped:
        notes.append(f"⚠️用完了{time_budget_s // 60}分钟的时间预算，还有{len(still)}个交易日没补(已保存已补的部分)：再点一次 only=crush_rate 接着补")
    elif still:
        notes.append(f"这{len(still)}个交易日搜了但快讯里没有开机率读数(可能当天确实没发布，或春节期间)，下次运行还会再试一次，开销很小")
    if caps:
        notes.append(f"⚠️这些日期切到最小的1天窗口仍然恰好返回750条(接口上限)，这几天可能还是不全：{', '.join(caps)}")
    notes += [f"搜索说明：{n}" for n in search_notes[:5]]
    return _report_entry("crush_rate", base_dir, len(pts), notes=notes,
                         extra={"windowsHitCap": caps, "excluded(非油厂/超范围，前6条)": excluded[:6], "missingBefore": len(missing), "stillMissing": still[:60],
                                "stoppedEarly": stopped, "rangesSearched": windows, "probeRequests": probes})



def merge_report_series(prev_series, new_entries, ran_at):
    """把上一份报告里'这次没跑的项'的结果保留下来，并给每一项标明何时运行(ranAt)、是不是上次留下的(fromPreviousRun)。
    为什么：报告每次运行都整体覆盖。先跑回填、再跑校准(不联网，series 为空)，回填的统计就被盖掉了——
    用户把校准的报告发来，看不出回填成功没有(2026-10-07 真实发生)。
    规则：①同一项新旧都有→以新的为准，ranAt=本次；②这次失败(有 error)→不抹掉上次成功的结果，挂在 previousGood 下；
    ③旧报告损坏/缺key的条目一律忽略，不崩；④顺序：旧报告里已有的项保持原位置，新项追加在后面。"""
    prev = {}
    order = []
    if isinstance(prev_series, list):
        for it in prev_series:
            if isinstance(it, dict) and isinstance(it.get("key"), str) and it.get("key"):
                if it["key"] not in prev:
                    order.append(it["key"])
                prev[it["key"]] = it
    new = {}
    for it in new_entries or []:
        if isinstance(it, dict) and isinstance(it.get("key"), str) and it.get("key"):
            new[it["key"]] = it
            if it["key"] not in order:
                order.append(it["key"])
    out = []
    for k in order:
        if k in new:
            cur = dict(new[k], ranAt=ran_at, fromPreviousRun=False)
            old = prev.get(k)
            if "error" in cur and old and "error" not in old:
                cur["previousGood"] = {kk: vv for kk, vv in old.items() if kk != "previousGood"}
            out.append(cur)
        else:
            old = dict(prev[k])
            old.setdefault("ranAt", None)
            old["fromPreviousRun"] = True
            out.append(old)
    return out


def _read_previous_series(out_dir):
    """读上一份报告里的 series；文件不存在/损坏/不是预期结构都返回空列表，不影响这次运行。"""
    try:
        with open(os.path.join(out_dir, "_backfill_report.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d.get("series") if isinstance(d, dict) else []
    except Exception:  # noqa: BLE001
        return []


POULTRY_NDRC_TIME_BUDGET_S = 20 * 60


def backfill_poultry_ndrc(base_dir=None, today=None, fetch=None, sleep_s=1.0, time_budget_s=POULTRY_NDRC_TIME_BUDGET_S, clock=time.monotonic,
                          max_consecutive_misses=6, max_list_pages=60, save_every=20, lister=None):
    """肉鸡养殖预期盈利回填(发改委价格监测中心×卓创资讯周报)。文章列表靠 Selenium(lister)：先点开'猪料、鸡料、蛋料比价信息'子栏目，再逐页点'下一页'；
    每篇详情页走纯 HTTP(服务器端渲染)，失败才退回用浏览器读。不猜分页参数：找不到'下一页'就只处理已经拿到的，并在报告里写明 noNextPageLink=True。
    从最新开始；历史里已有的周(按监测日或 x.wk 周标签)不重抓详情页；时间预算；连续 max_consecutive_misses 篇失败判断站点不可达并停手；每攒 save_every 个点落盘；浏览器一定关掉。"""
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    fetch = fetch or fd.fetch_text_debug
    t_start = clock()      # ★预算从函数开头算：翻列表页的时间也要算进去
    ex = hs.load_series("poultry_ndrc", base_dir).get("points", [])
    have_dates = {p.get("d") for p in ex}
    have_weeks = {(p.get("x") or {}).get("wk") for p in ex if (p.get("x") or {}).get("wk")}
    try:
        lister = lister or fd.default_ndrc_lister(total_timeout_s=15 * 60)
    except Exception as e:  # noqa: BLE001
        return {"key": "poultry_ndrc", "error": f"浏览器模块加载失败: {type(e).__name__}: {str(e)[:120]}"}
    try:
        return _backfill_poultry_ndrc_body(lister, fetch, base_dir, today, ex, have_dates, have_weeks, t_start, sleep_s, time_budget_s, clock,
                                           max_consecutive_misses, max_list_pages, save_every)
    finally:
        try:
            lister.close()
        except Exception:  # noqa: BLE001
            pass


def _backfill_poultry_ndrc_body(lister, fetch, base_dir, today, ex, have_dates, have_weeks, t_start, sleep_s, time_budget_s, clock,
                                max_consecutive_misses, max_list_pages, save_every):
    lst = lister.list_articles(max_pages=max_list_pages, resolve_limit=None, skip_weeks=have_weeks)      # 条目没有链接时要点开才有地址：不限个数(受总时限约束)，已有的周不点
    links, pages, no_next, paging_stopped = lst.get("links") or [], lst.get("pages") or 0, bool(lst.get("noNext")), False
    if not links:
        return {"key": "poultry_ndrc", "error": lst.get("error") or "子栏目列表里没有任何文章链接", "listPages": pages, "noNextPageLink": no_next, "debug": lst.get("debug") or {},
                "notes": ["海外 IP 访问国内政府站点可能超时或被拒；GitHub Actions 的出口我无法验证。debug 里是浏览器看到的页面情况，发我据此调整"]}
    list_note = lst.get("error")
    if clock() - t_start > time_budget_s:
        paging_stopped = True
    new_pts, unsaved, misses, skipped, stopped, consecutive = {}, [], [], 0, False, 0
    for ln in links:
        if ln.get("week") and ln["week"] in have_weeks:
            skipped += 1
            continue
        # 没有 x.wk 的旧点(线上或手工记的)：用列表页上的发布日推出监测日(发布日之前最近的周三)，已在历史里就不重抓详情页
        if ln.get("pageDate"):
            pd_ = _date_from_iso(ln["pageDate"])
            if pd_ is not None and (pd_ - timedelta(days=(pd_.weekday() - 2) % 7)).isoformat() in have_dates:
                skipped += 1
                continue
        if clock() - t_start > time_budget_s:
            stopped = True
            break
        raw3, err = (ln["html"], None) if ln.get("html") else fd._ndrc_get(fetch, ln["url"])
        if err:
            raw3, err2 = lister.page_html(ln["url"])
            err = None if not err2 else f"{err}；浏览器也取不到: {err2}"
        parsed, why = (fd.parse_ndrc_poultry(fd._html_to_text(raw3)) if not err else (None, err))
        if parsed is None:
            if len(misses) < 40:
                misses.append({"title": ln["title"], "why": str(why)[:80]})
            consecutive += 1
            if consecutive >= max_consecutive_misses:
                break
            continue
        consecutive = 0
        pub = _date_from_iso(parsed.get("publishDate")) or _date_from_iso(ln.get("pageDate"))
        body = _date_from_iso(parsed.get("monitorDate"))
        d, fb = fd.pick_ndrc_monitor_date(parsed.get("weekLabel") or ln.get("week"), body, pub)
        if d is None:
            if len(misses) < 40:
                misses.append({"title": ln["title"], "why": "没有可用的日期"})
            continue
        if d.isoformat() in have_dates or d.isoformat() in new_pts:
            skipped += 1
            continue
        x = {"ratio": parsed["ratio"], "bal": parsed["balance"], "wk": parsed["weekLabel"] or ln.get("week"), "cp": parsed["chickenPrice"], "fp": parsed["feedPrice"]}
        pt = {"d": d.isoformat(), "v": parsed["value"], "x": {k: v for k, v in x.items() if v is not None}}
        new_pts[pt["d"]] = pt
        unsaved.append(pt)
        if len(unsaved) >= save_every:
            hs.record_points("poultry_ndrc", unsaved, base_dir)
            unsaved = []
        if sleep_s:
            time.sleep(sleep_s)
    if unsaved:
        hs.record_points("poultry_ndrc", unsaved, base_dir)
    stopped = stopped or paging_stopped
    if not new_pts and not ex:
        return {"key": "poultry_ndrc", "error": ("时间预算用完，还没来得及解析任何一篇周报(翻页就用掉了预算)" if stopped else "列表里的周报一篇都没解析出肉鸡预期盈利"), "misses": misses, "articlesSeen": len(links),
                "listPages": pages, "noNextPageLink": no_next, "stoppedEarly": stopped}
    ds = sorted(new_pts)
    notes = [f"列表翻了{pages}页，共{len(links)}篇周报；本次写入{len(new_pts)}个周" + (f"({ds[0]}~{ds[-1]})" if ds else "") + f"，已有的{skipped}个周跳过",
             "★与 Mysteel 的白羽肉鸡养殖利润不是同一个定义：这是发改委按成本模型推算的未来肉鸡养殖预期盈利(取公布的数字)；公式脚注的系数曾被转载页写错，不重算"]
    if list_note:
        notes.append(f"列表读取过程中的问题：{list_note}")
    if no_next:
        notes.append("⚠️列表页里没有找到'下一页'链接，只处理了已经拿到的文章(不猜分页参数)：把报告里的 listPages/articlesSeen 发我，我根据真实的分页结构改")
    if stopped:
        notes.append(f"⚠️用完了{time_budget_s // 60}分钟的时间预算，已保存已拿到的：再点一次 only=poultry_ndrc 接着补")
    if misses:
        notes.append(f"{len(misses)}篇没取到/没解析出(见 misses)")
    return _report_entry("poultry_ndrc", base_dir, len(new_pts), notes=notes,
                         extra={"articlesSeen": len(links), "listPages": pages, "noNextPageLink": no_next, "skippedWeeks": skipped, "misses": misses, "stoppedEarly": stopped})


def _date_from_iso(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


SPOT_BASIS_BACKFILL_FROM = date(2023, 9, 1)
SPOT_BASIS_TIME_BUDGET_S = 40 * 60


def backfill_spot_basis(base_dir=None, start=None, today=None, fetch=None, sleep_s=1.0, time_budget_s=SPOT_BASIS_TIME_BUDGET_S, clock=time.monotonic,
                        max_consecutive_misses=8, save_every=25, deadline_s=fd.SPOT_BASIS_DEADLINE_S):
    """现货基差回填(生意社现货价 - 主力合约结算价，自己算)。不用 Mysteel。
    数据源 ak.futures_spot_price(日期, vars_list=['M'])：**每个交易日一次网页请求**(akshare 内部请求 100ppi.com/sf/day-日期.html，页面日期对不上会 sleep(3)，被限流返回空表)；
    所以不用 futures_spot_price_daily(它只是日期循环，中途被切断就什么都拿不到)，自己按交易日逐天调用：从最新开始、休市日不请求、已有历史的日期跳过(可重复点接着补)、
    每次请求有硬性时限、40分钟时间预算、连续 max_consecutive_misses 天拿不到就判断被限流并停手、每攒够 save_every 个点就落盘(被强杀也不丢)。
    每个点 x={sp现货价, dom主力合约, dp结算价, sb站点基差}；报告标出站点基差与自算不符的日期和主力合约换月点(换月处基差会有断层，是换了对比的合约，不是行情)。"""
    import cn_calendar
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    start = start or SPOT_BASIS_BACKFILL_FROM
    fetch = fetch or fd._akshare_spot_price
    existing = {p.get("d") for p in hs.load_series("spot_basis", base_dir).get("points", [])}
    cands, d0 = [], today
    while d0 >= start:
        if cn_calendar.dce_is_trading_day(d0) and d0.isoformat() not in existing:
            cands.append(d0)
        d0 -= timedelta(days=1)
    new_pts, unsaved, misses, mismatches = {}, [], [], []
    consecutive, attempted, stopped, blocked, t0 = 0, 0, False, False, clock()
    for d in cands:
        if clock() - t0 > time_budget_s:
            stopped = True
            break
        attempted += 1
        ok_, res = fd._run_with_deadline(lambda d=d: fetch(d.isoformat()), deadline_s)
        parsed, why = fd.parse_spot_basis(res) if ok_ else (None, res)
        if parsed is None:
            if len(misses) < 60:
                misses.append(d.isoformat())
            consecutive += 1
            if consecutive >= max_consecutive_misses:
                blocked = True
                break
        else:
            consecutive = 0
            x = {"sp": parsed["spot"], "dom": parsed["domSymbol"], "dp": parsed["domPrice"], "sb": parsed["siteBasis"]}
            pt = {"d": d.isoformat(), "v": parsed["value"], "x": {k: v for k, v in x.items() if v is not None}}
            new_pts[pt["d"]] = pt
            unsaved.append(pt)
            if parsed["consistent"] is False:
                mismatches.append({"d": pt["d"], "computed": parsed["value"], "site": parsed["siteBasis"]})
            if len(unsaved) >= save_every:
                hs.record_points("spot_basis", unsaved, base_dir)
                unsaved = []
        if sleep_s:
            time.sleep(sleep_s)
    if unsaved:
        hs.record_points("spot_basis", unsaved, base_dir)
    remaining = len(cands) - attempted
    if not new_pts and not existing:
        return {"key": "spot_basis", "error": "一个交易日都没取到生意社的豆粕现货价", "misses": misses, "blocked": blocked, "attempted": attempted,
                "notes": ["连续拿不到：可能被站点限流、akshare 版本/接口变了、或网络不通——看 misses 和 Actions 日志里 akshare 打印的生意社连接失败信息"]}
    ds = sorted(new_pts)
    rolls = []
    for a, b in zip(ds, ds[1:]):
        da, db = new_pts[a]["x"].get("dom"), new_pts[b]["x"].get("dom")
        if da and db and da != db:
            rolls.append({"from": a, "to": b, "dom": f"{da}→{db}"})
    notes = [f"候选{len(cands)}个交易日(已有历史的跳过)，本次请求{attempted}个，写入{len(new_pts)}个点" + (f"({ds[0]}~{ds[-1]})" if ds else ""),
             "基差=生意社现货价-主力合约结算价(自己算，现货高于期货为正)；sp 的口径文档没写明(疑为多地综合的基准价)；主力合约换月处基差会有断层(见 contractRolls)"]
    if stopped:
        notes.append(f"⚠️用完了{time_budget_s // 60}分钟的时间预算，还有{remaining}个交易日没请求(已保存已拿到的)：再点一次 only=spot_basis 接着补")
    if blocked:
        notes.append(f"⚠️连续{max_consecutive_misses}个交易日拿不到数据，判断站点在限流，已停手(已保存已拿到的，还有{remaining}个交易日没请求)：隔一段时间再点一次 only=spot_basis")
    if mismatches:
        notes.append(f"{len(mismatches)}个交易日站点给的基差与自算(现货-主力结算价)相差≥{fd.SPOT_BASIS_TOLERANCE}元，已取自算值")
    return _report_entry("spot_basis", base_dir, len(new_pts), notes=notes,
                         extra={"attempted": attempted, "remaining": remaining, "stoppedEarly": stopped, "blocked": blocked, "misses": misses,
                                "siteMismatches": len(mismatches), "siteMismatchSamples": mismatches[:5], "contractRolls": rolls[:20]})


BASIS_QUERY = "全国主要市场豆粕基差价格汇总"
BASIS_TITLE_KEY = "豆粕基差价格汇总"
BASIS_BACKFILL_FROM = date(2023, 9, 1)      # 采样里最早一篇是 2023-09-18
BASIS_WINDOW_DAYS = 90


def _fetch_basis_body(url, title):
    """抓一篇文章并返回 (该读表的文字, 错误, 诊断)。与线上共用 fd.fetch_basis_page(区域里没有表就在整页文字里找；没读到表给出诊断)。"""
    page = fd.fetch_basis_page(url, title)
    if not page["ok"]:
        return None, page["err"], None
    return page["text"], None, page["diag"]


BASIS_PARSER_VERSION = "table-v2"      # 解析规则版本：报告里记下"正文没有表"的日期，只在版本相同时下次才跳过(解析规则改了就全部重试)。v2：整页兜底读表(v1 只在"标题~免责声明"的区域里找，735个日期只读到24个)


def _basis_known_no_table(out_dir):
    """上次报告里记下的'抓了正文但里面没有数据表'的日期(只在 parserVersion 相同时有效)。读不到/损坏/版本不同都返回空集。"""
    for it in _read_previous_series(out_dir) or []:
        if isinstance(it, dict) and it.get("key") == "basis" and it.get("parserVersion") == BASIS_PARSER_VERSION:
            return {d for d in (it.get("triedNoTable") or []) if isinstance(d, str)}
    return set()


def backfill_basis(base_dir=None, start=None, today=None, search=None, fetch_body=None, max_bodies=300, sleep_s=0.8):
    """现货基差回填。★v101.5：用正文里的数据表。
    真实情况(2026-10-08 回填报告)：每篇《全国主要市场豆粕基差价格汇总》正文底下有一张每市场一行的表(省份 市场 期货合约 现货基差 涨跌)，
    页面顶部"智能摘要 内容由AI生成"只是它的概括——线上抓取和 v101.4 的回填解析的都是那段AI概括，所以300篇正文一个都没解析出来。
    取值：①抓正文，读表，按沿海城市优先级(日照/南通/东莞/湛江/防城港/厦门/天津)取第一个有数值的(表里每天都有日照，不再每天切换城市)，点里记 x={city,src:'table',contract}；
          ②表取不出：退回搜索摘要(线上同一规则，src='summary')；③再不行用正文里的文字(src='body')。
    每次最多抓 max_bodies 篇正文、从最新的开始；配额用完的日期若摘要有值先用摘要记上(src='summary')，下次运行用表升级。
    ★已有的点：src='table'/'body' 或没有 src(线上每天累积的)永不动、不重抓；src='summary'(上一版回填)会被表升级(表取不出就保留原点)。
    ★正文请求成功但里面没有表的日期记进报告 triedNoTable(带 parserVersion)，下次不再重抓，免得顽固的日期每次占掉配额。"""
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    start = start or BASIS_BACKFILL_FROM
    search = search or _search_articles
    fetch_body = fetch_body or _fetch_basis_body
    out_dir = base_dir or hs.HISTORY_DIR
    ex_pts = {p.get("d"): p for p in hs.load_series("basis", base_dir).get("points", [])}
    known_no_table = _basis_known_no_table(out_dir)
    arts, other_titles, windows, splits, calls_n, caps, search_notes, total_items = {}, 0, 0, 0, 0, [], [], 0
    w_start = start
    while w_start <= today:
        w_end = min(w_start + timedelta(days=BASIS_WINDOW_DAYS - 1), today)
        items, sinfo = search_windowed(search, BASIS_QUERY, w_start, w_end, max_pages=40, sleep_s=sleep_s)
        windows += 1
        total_items += len(items)
        splits += sinfo["splits"]
        calls_n += sinfo["calls"]
        caps += sinfo["unresolved"]
        search_notes += sinfo["notes"]
        for it in items:
            if BASIS_TITLE_KEY not in str(it.get("title") or ""):
                other_titles += 1
                continue
            d = _pub(it)
            if d is None:
                continue
            stamp = str(it.get("publishTime") or "")
            if d.isoformat() not in arts or stamp >= arts[d.isoformat()][0]:
                arts[d.isoformat()] = (stamp, it)
        w_start = w_end + timedelta(days=1)
    new_pts, via = {}, {"table": 0, "summary": 0, "body": 0}
    city_counts, contract_counts, body_fail, no_value, tried_no_table = {}, {}, [], 0, []
    bodies, untrusted, existing_skipped, need_body, upgraded, upgrade_pending, skipped_known = 0, 0, 0, 0, 0, 0, 0

    def accept(d, city, val, src, contract=None):
        problem = fd._plausibility_problem("meaBasis", val)
        if problem:
            if len(body_fail) < 8:
                body_fail.append({"d": d, "reason": f"{city}基差{problem}，已丢弃"})
            return False
        x = {"city": city, "src": src}
        if contract:
            x["contract"] = contract
        new_pts[d] = {"d": d, "v": val, "x": x}
        city_counts[city] = city_counts.get(city, 0) + 1
        if contract:
            contract_counts[contract] = contract_counts.get(contract, 0) + 1
        via[src] += 1
        return True

    for d in sorted(arts, reverse=True):          # 最新的先处理：近期的先补上，正文配额也先用在近期
        old = ex_pts.get(d)
        upgrade = bool(old) and (old.get("x") or {}).get("src") == "summary"
        if old and not upgrade:
            existing_skipped += 1
            continue
        it = arts[d][1]
        s_city, s_val = fd._extract_basis_from_article(str(it.get("content") or ""))
        url = str(it.get("url") or "")
        can_fetch = bool(url) and fd.is_trusted_article_url(url)
        if d in known_no_table or not can_fetch or bodies >= max_bodies:
            # 不抓正文：已知这篇正文没有表 / 网址不可用 / 配额用完。有摘要值就先用摘要(新日期)；升级点保持原样
            if upgrade:
                if d not in known_no_table and can_fetch:
                    upgrade_pending += 1
                continue
            if d in known_no_table:
                skipped_known += 1
            elif not can_fetch:
                untrusted += 1
            if s_val is not None and accept(d, s_city, s_val, "summary"):
                continue
            if can_fetch and bodies >= max_bodies and d not in known_no_table:
                need_body += 1
            else:
                no_value += 1
            continue
        bodies += 1
        res = fetch_body(url, str(it.get("title") or ""))
        text, err, diag = res[0], res[1], (res[2] if len(res) > 2 else None)       # fetch_body 可以返回 (文字, 错误) 或 (文字, 错误, 诊断)
        time.sleep(sleep_s)
        if err or not text:
            if len(body_fail) < 8:
                body_fail.append({"d": d, "reason": err or "正文为空"})
            if not upgrade and s_val is not None and accept(d, s_city, s_val, "summary"):
                continue
            no_value += 1
            continue
        t_city, t_val, t_contract = fd.basis_from_table(text)
        if t_val is not None:
            if accept(d, t_city, t_val, "table", t_contract) and upgrade:
                upgraded += 1
            continue
        # 正文请求成功但表里取不出沿海城市：记下来(下次不再重抓)，退回摘要/正文文字
        tried_no_table.append(d)
        if len(body_fail) < 8:
            body_fail.append({"d": d, "reason": "正文里没有数据表，或表里没有沿海城市(日照/南通/东莞/湛江/防城港/厦门/天津)的数值", "regionHead": text[:220], **({"diag": diag} if diag else {})})
        if upgrade:
            continue
        if s_val is not None and accept(d, s_city, s_val, "summary"):
            continue
        b_city, b_val = fd._extract_basis_from_article(text)
        if b_val is not None and accept(d, b_city, b_val, "body"):
            continue
        no_value += 1
    if not new_pts and not existing_skipped:
        # ★一个点都没取到时恰恰最需要诊断：把能说明原因的计数都带上
        return {"key": "basis", "error": "没有搜到能提取出沿海城市基差的文章", "searchTotal": total_items, "articleDates": len(arts), "otherTitlesSkipped": other_titles,
                "bodiesFetched": bodies, "needBodyRemaining": need_body, "untrustedOrMissingUrl": untrusted, "noValue": no_value, "bodyFailures": body_fail,
                "parserVersion": BASIS_PARSER_VERSION, "triedNoTable": sorted(set(tried_no_table) | known_no_table)[:900],
                "notes": [f"搜索说明：{n}" for n in search_notes[:5]]}
    if new_pts:
        hs.record_points("basis", [new_pts[k] for k in sorted(new_pts)], base_dir)
    notes = [f"{windows}个窗口共搜到{total_items}条，基差文章{len(arts)}个日期；本次写入{len(new_pts)}个点(表{via['table']}、摘要{via['summary']}、正文文字{via['body']})，其中升级旧摘要点{upgraded}个；"
             f"已有历史且不动的{existing_skipped}个日期跳过，抓了{bodies}篇正文(上限{max_bodies})",
             "取值：读正文数据表，按沿海城市优先级取第一个有数值的(表里每天都有日照，城市不再每天切换)；表取不出才退回AI摘要/正文文字，点里的 x.src 标明来源，x.contract 是表里的合约月份(09→01 换月处基差会有断层)"]
    if need_body:
        notes.append(f"⚠️还有{need_body}篇没有任何可用的值、本次也没抓正文(达到每次{max_bodies}篇的上限)：再点一次 only=basis 接着补(已有的日期会跳过)")
    if upgrade_pending:
        notes.append(f"还有{upgrade_pending}个旧的摘要点等着用表升级(本次配额用完)：再点一次 only=basis")
    if tried_no_table or skipped_known:
        notes.append(f"正文里没有表的日期{len(tried_no_table)}个(本次新发现)+{skipped_known}个(上次已知，本次跳过)：已记入 triedNoTable，下次不再重抓；解析规则改了(parserVersion 变)会全部重试")
    if body_fail:
        notes.append("有正文没取到值：看 bodyFailures 里的原因和正文开头")
    if splits:
        notes.append(f"自适应切窗{splits}次(窗口返回满750条就对半切开重搜)，共{calls_n}次搜索")
    if caps:
        notes.append(f"⚠️这些日期切到1天仍恰好返回750条，可能不全：{', '.join(caps)}")
    notes += [f"搜索说明：{n}" for n in search_notes[:5]]
    return _report_entry("basis", base_dir, len(new_pts), notes=notes,
                         extra={"viaTable": via["table"], "viaSummary": via["summary"], "viaBody": via["body"], "upgraded": upgraded, "bodiesFetched": bodies,
                                "needBodyRemaining": need_body, "upgradePending": upgrade_pending, "existingSkipped": existing_skipped, "skippedKnownNoTable": skipped_known,
                                "noValue": no_value, "untrustedOrMissingUrl": untrusted, "cityCounts": city_counts, "contractCounts": contract_counts, "bodyFailures": body_fail,
                                "otherTitlesSkipped": other_titles, "windowsHitCap": caps,
                                "parserVersion": BASIS_PARSER_VERSION, "triedNoTable": sorted(set(tried_no_table) | known_no_table)[:900]})


RMSPREAD_QUERY = "豆菜粕价差"
RMSPREAD_TITLE_KEY = "价差统计分析"            # 主系列《国内主要市场豆菜粕价差统计分析》(每3~5天一篇)；月度解读等其它类文章口径不同，按标题排除
RMSPREAD_BACKFILL_FROM = date(2023, 12, 1)      # 主系列最早一篇是 2024-01-09，留一点余量
RMSPREAD_WINDOW_DAYS = 90


def backfill_rm_spread(base_dir=None, start=None, today=None, search=None, sleep_s=0.6):
    """豆菜粕价差回填。取值规则与线上共用 fd.parse_rmspread(城市单值≥2个取平均，否则区间中点)，每个点带 x.fmt。
    只收标题含"价差统计分析"的主系列文章。每个90天窗口用 search_windowed(返回满750条就对半切)。
    采样(2026-10-02)里主系列 211 篇、2024-01-09~2026-09-30、间隔中位5天；10篇摘要里只有定性描述(如"价差下跌")，没有数字，跳过。
    评分仍然关闭(新口径暂不计分)，回填只用于趋势展示。"""
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    start = start or RMSPREAD_BACKFILL_FROM
    search = search or _search_articles
    by_day, other_titles, no_value, windows, splits, calls_n, caps, search_notes, total_items = {}, 0, [], 0, 0, 0, [], [], 0
    w_start = start
    while w_start <= today:
        w_end = min(w_start + timedelta(days=RMSPREAD_WINDOW_DAYS - 1), today)
        items, sinfo = search_windowed(search, RMSPREAD_QUERY, w_start, w_end, max_pages=40, sleep_s=sleep_s)
        windows += 1
        total_items += len(items)
        splits += sinfo["splits"]
        calls_n += sinfo["calls"]
        caps += sinfo["unresolved"]
        search_notes += sinfo["notes"]
        for it in items:
            title = str(it.get("title") or "")
            if RMSPREAD_TITLE_KEY not in title:
                other_titles += 1
                continue
            d = _pub(it)
            if d is None:
                continue
            res, _rej = fd.parse_rmspread(str(it.get("content") or ""))
            if not res:
                if len(no_value) < 8:
                    no_value.append({"d": d.isoformat(), "title": title[:40], "content": str(it.get("content") or "")[:40]})
                continue
            stamp = str(it.get("publishTime") or "")
            if d.isoformat() not in by_day or stamp >= by_day[d.isoformat()][0]:
                by_day[d.isoformat()] = (stamp, res["value"], res["fmt"])
        w_start = w_end + timedelta(days=1)
    if not by_day:
        return {"key": "rm_spread", "error": "没有搜到能提取出价差数值的'价差统计分析'文章", "searchTotal": total_items, "otherTitlesSkipped": other_titles,
                "noValueSamples": no_value, "notes": [f"搜索说明：{n}" for n in search_notes[:5]]}
    ds = sorted(by_day)
    pts = [{"d": k, "v": by_day[k][1], "x": {"fmt": by_day[k][2]}} for k in ds]
    hs.record_points("rm_spread", pts, base_dir)
    counts = {}
    for k in ds:
        counts[by_day[k][2]] = counts.get(by_day[k][2], 0) + 1
    switches = [{"from": a, "to": b, "fmt": f"{by_day[a][2]}→{by_day[b][2]}"} for a, b in zip(ds, ds[1:]) if by_day[a][2] != by_day[b][2]]
    gaps = [{"from": a, "to": b, "days": (date.fromisoformat(b) - date.fromisoformat(a)).days} for a, b in zip(ds, ds[1:]) if (date.fromisoformat(b) - date.fromisoformat(a)).days > 14]
    notes = [f"{windows}个窗口共搜到{total_items}条，主系列文章提取出{len(pts)}个日期的价差({ds[0]}~{ds[-1]})；口径：城市单值≥2个取平均，否则区间中点",
             f"口径切换点{len(switches)}处：切换前后可能有约±5%的断层(重叠的4篇上两种取法相差+5/+33/-5/+37)，看趋势时留意；评分仍然关闭"]
    if splits:
        notes.append(f"自适应切窗{splits}次(窗口返回满750条就对半切开重搜)，共{calls_n}次搜索")
    if caps:
        notes.append(f"⚠️这些日期切到1天仍恰好返回750条，可能不全：{', '.join(caps)}")
    notes += [f"搜索说明：{n}" for n in search_notes[:5]]
    return _report_entry("rm_spread", base_dir, len(pts), notes=notes,
                         extra={"formatCounts": counts, "formatSwitches": switches[:12], "gapsOver14Days": gaps[:12], "noValueSamples": no_value,
                                "otherTitlesSkipped": other_titles, "windowsHitCap": caps})


def backfill_hog_ratio(base_dir=None, start=None, today=None):
    """猪粮比历史回填。数据源(akshare 的猪价网数据)每次返回的就是生猪价和玉米价的完整历史序列，fetch_hog_ratio 只取了最后一个共同日期；
    这里把所有共同日期都算出来存进历史。不搜索、不抓正文、不联网以外的东西；每个日期的计算与 fetch_hog_ratio 共用 fd.hog_ratio_at。
    日期之前的 start 不进历史；生猪价或玉米价任一获取失败：只在报告里写 error，不写任何文件。"""
    # 一次性任务：多重试、多等(2026-10-08 真实报告：默认的重试2次/超时15秒连续超时，猪粮比历史没补上)
    pig_df, err = fd._fetch_akshare_hog_df("外三元", retries=5, timeout_seconds=30, retry_delay_seconds=5, func_name="futures_hog_core")
    if err:
        return {"key": "hog_ratio", "error": f"生猪价格(外三元)获取失败: {err.get('reason')}"}
    corn_df, err = fd._fetch_akshare_hog_df("玉米", retries=5, timeout_seconds=30, retry_delay_seconds=5, func_name="futures_hog_cost")
    if err:
        return {"key": "hog_ratio", "error": f"玉米价格获取失败: {err.get('reason')}"}
    try:
        pig, corn = fd._hog_series_to_dict(pig_df), fd._hog_series_to_dict(corn_df)
    except (KeyError, TypeError) as e:
        return {"key": "hog_ratio", "error": f"字段解析失败: {e}(接口可能改了字段名)"}
    pts, dropped = fd.hog_ratio_points(pig, corn)
    if start is not None:
        s_iso = start.isoformat() if hasattr(start, "isoformat") else str(start)
        pts = [p for p in pts if p["d"] >= s_iso]
    if not pts:
        return {"key": "hog_ratio", "error": "生猪价格和玉米价格没有任何可用的共同日期", "notes": [f"生猪{len(pig)}天，玉米{len(corn)}天，丢弃{len(dropped)}天"]}
    hs.record_points("hog_ratio", pts, base_dir)
    notes = [f"生猪价格{len(pig)}天({min(pig)}~{max(pig)})，玉米价格{len(corn)}天({min(corn)}~{max(corn)})，共同日期{len(set(pig) & set(corn))}天，写入{len(pts)}天"]
    if dropped:
        notes.append(f"丢弃{len(dropped)}天(比值超出合理范围/玉米价异常等)，前5个：" + "；".join(f"{x['d']} {x['reason']}" for x in dropped[:5]))
    return _report_entry("hog_ratio", base_dir, len(pts), notes=notes, extra={"droppedDates": dropped[:20]})


# ---------------------------------------------------------------------------
JOBS = {"us_stu": backfill_us_stocks_to_use, "esr": backfill_esr_weekly, "meal_stu": backfill_meal_stu, "margin": backfill_crush_margin, "spread": backfill_term_spread, "feed_days": backfill_feed_days, "soy_import": backfill_soy_import, "arrival": backfill_arrival_forecast, "crush_rate": backfill_crush_rate, "hog_ratio": backfill_hog_ratio, "rm_spread": backfill_rm_spread, "poultry_ndrc": backfill_poultry_ndrc, "spot_basis": backfill_spot_basis}
DEFAULT_JOBS = ["us_stu", "esr", "meal_stu", "margin", "spread", "feed_days", "soy_import", "arrival", "crush_rate", "hog_ratio", "rm_spread"]      # Mysteel周度库存回填不进默认：第二次报告证明补不全(摘要没数字、2026年6月起正文改版)，改成靠每次抓取累积
LOCAL_ONLY = ("calibrate",)     # 不联网，只基于data/history里已有的序列重新生成校准摘要


def main(argv=None, base_dir=None):
    ap = argparse.ArgumentParser(description="豆粕仪表盘历史回填")
    ap.add_argument("--only", default="all", help="逗号分隔：us_stu,esr,meal_stu,margin,spread,feed_days,soy_import,arrival,crush_rate,calibrate；默认=us_stu,esr,meal_stu,margin,spread,feed_days,soy_import,arrival,crush_rate；calibrate=不联网，只重新生成校准摘要(含榨利/月差的窗口与阈值校准诊断)。(采样诊断sample与周度库存回填meal_stock已在v99移除，见REMOVED_backfill_sample_and_meal_stock.md)")
    ap.add_argument("--start", default="2020-01-01", help="Mysteel两项的起始日期")
    ap.add_argument("--no-bodies", action="store_true", help="国内库消比不抓文章正文，只用摘要")
    args = ap.parse_args(argv)
    names = list(DEFAULT_JOBS) if args.only == "all" else [n.strip() for n in args.only.split(",") if n.strip()]
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(), "series": []}
    for n in names:
        if n in LOCAL_ONLY:
            continue
        if n not in JOBS:
            report["series"].append({"key": n, "error": "未知的回填项"})
            continue
        print(f"[回填] {n} ...", flush=True)
        try:
            kw = {"base_dir": base_dir}
            if n in ("meal_stu", "feed_days"):
                kw["start"] = start
            if n in ("meal_stu", "feed_days"):
                kw["fetch_bodies"] = not args.no_bodies
            entry = JOBS[n](**kw)
        except Exception as e:  # noqa: BLE001 - 一项失败不影响其他项
            entry = {"key": n, "error": f"{type(e).__name__}: {e}"}
        report["series"].append(entry)
        print(json.dumps(entry, ensure_ascii=False, indent=2)[:3000], flush=True)
    try:
        report["calibration"] = calibration_summary(base_dir)      # 校准阈值需要的数字：分位数、当前阈值在历史里的位置、信号触发比例…
    except Exception as e:  # noqa: BLE001
        report["calibration"] = {"error": f"{type(e).__name__}: {e}"}
    out_dir = base_dir or hs.HISTORY_DIR
    os.makedirs(out_dir, exist_ok=True)
    # 这次没跑的项(比如这次只跑校准)保留上次的结果，并标明何时运行——不再每次都把回填的统计抹掉
    report["series"] = merge_report_series(_read_previous_series(out_dir), report["series"], report["generatedAt"])
    with open(os.path.join(out_dir, "_backfill_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


if __name__ == "__main__":
    main()
