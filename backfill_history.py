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
  meal_stock 国内豆粕周度库存：Mysteel每周《全国主要区域大豆及豆粕库存统计》

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
    k = hs.load_series("meal_stock", base_dir)["points"]
    if k:
        vals = [p["v"] for p in k]
        out["meal_stock"] = {"n": len(vals), "quantiles": quantiles(vals), "currentThresholds": {"tight<50": share(vals, lambda v: v < 50), "loose>100": share(vals, lambda v: v > 100)},
                             "pointsPerYear": dict(Counter(p["d"][:4] for p in k)), "coverage": hs.coverage_problem(k, "weekly") or "样本连续，可用", "spotChecks(独立来源Mysteel英文站周报)": meal_stock_spot_checks(k)}
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


def _search_articles(query, start, end, max_pages=40):
    """翻页收齐搜索结果。返回(items, total, 说明)。"""
    items, total, note = [], 0, None
    for page in range(1, max_pages + 1):
        payload = {"query": query, "startTime": start.strftime("%Y-%m-%d 00:00:00"), "endTime": end.strftime("%Y-%m-%d 23:59:59"),
                   "sortType": "complex", "platform": "pc", "pageNo": page, "pageSize": 20}
        data, dbg = fd.fetch_json_debug(fd.MYSTEEL_ARTICLE_SEARCH_URL, headers=_MY_HEADERS, post_data=payload)
        if not isinstance(data, dict) or data.get("resultCode") != 0:
            note = f"第{page}页请求失败或返回异常，已用前{page - 1}页" if page > 1 else "搜索接口无返回/返回异常"
            break
        lst = data.get("dataList") or []
        total = data.get("total") or total
        items.extend(i for i in lst if isinstance(i, dict))
        if len(lst) < 20 or page * 20 >= total:
            break
        time.sleep(0.5)
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
# 4. 国内豆粕周度库存
# ---------------------------------------------------------------------------
def backfill_meal_stock(base_dir=None, start=None, today=None, max_pages=40, fetch_bodies=True, max_bodies=400, sleep_s=0.8):
    """★上一版只用搜索摘要：搜到750篇只提取出12个点(中间空了两年)。摘要里多半没有数字，数字在正文里，
    所以摘要提不出时，对"像周度库存"的文章(摘要/标题里有"第N周"，或标题有"库存"+大豆/豆粕)再抓正文提取。
    提取规则不变(沿用fetch_mysteel_meal_stock的_extract_meal_stock_values：拒绝区域数据/变动量/别的指标)。
    同一周有多篇时取发布更晚的。"""
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    start = start or datetime(2020, 1, 1).date()
    now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    items, total, note = _search_articles("全国主要区域大豆", datetime(start.year, start.month, start.day), now_bj, max_pages=max_pages)
    items = sorted((i for i in items if _pub(i)), key=lambda i: _pub(i), reverse=True)
    stats, samples = Counter(), {}
    def sample(cat, it, text=""):
        lst = samples.setdefault(cat, [])
        if len(lst) < 5:
            lst.append({"pub": _pub(it).isoformat(), "title": str(it.get("title"))[:50], "text": (text or str(it.get("content") or ""))[:150]})
    by_week, bodies = {}, 0
    for it in items:
        pub, title, content = _pub(it), str(it.get("title") or ""), str(it.get("content") or "")
        val, how = None, None
        for text in (content, title):
            good, _rej = fd._extract_meal_stock_values(text)
            if good and ("全国" in title or "全国" in content):
                val, how = good[0], "summary"
                break
        weeklike = bool(fd._MEAL_WEEK_RE.search(title + content)) or ("库存" in title and ("大豆" in title or "豆粕" in title))
        week_src = title + content
        if val is None and fetch_bodies and weeklike and bodies < max_bodies and it.get("url") and fd.is_trusted_article_url(it["url"]):
            raw, dbg = fd.fetch_text_debug(it["url"], headers={"Referer": "https://ncp.mysteel.com/"})
            bodies += 1
            time.sleep(sleep_s)
            if raw:
                region = fd._extract_article_region(fd._html_to_text(raw), title)
                week_src += region
                good, _rej = fd._extract_meal_stock_values(region)
                if good and ("全国" in region or "全国" in title):
                    val, how = good[0], "body"
                else:
                    stats["正文取到但没有可用的全国豆粕库存"] += 1
                    sample("正文取到但没有可用的全国豆粕库存", it, region[:150])
            else:
                stats["正文请求失败"] += 1
                sample("正文请求失败", it, str(dbg.get("error") or dbg.get("httpStatus")))
        if val is None:
            if not weeklike:
                stats["不像周度库存文章(标题/摘要没有第N周，标题也没有库存+大豆/豆粕)"] += 1
                sample("不像周度库存文章", it)
            elif not (fetch_bodies and bodies < max_bodies) and "正文" not in "".join(stats):
                stats["像周度库存文章，但摘要没数字且未抓正文"] += 1
            continue
        stats[f"提取成功(来自{'摘要' if how == 'summary' else '正文'})"] += 1
        wm = fd._MEAL_WEEK_RE.search(week_src)
        key = f"{wm.group(1)}-W{int(wm.group(2)):02d}" if wm else pub.isoformat()
        if key not in by_week or pub > by_week[key][0]:
            by_week[key] = (pub, val)
    pts = [{"d": pub.isoformat(), "v": v, "x": {"week": k}} for k, (pub, v) in by_week.items()]
    hs.record_points("meal_stock", pts, base_dir)
    notes = [note] if note else []
    notes.append(f"搜索到{len(items)}篇(总数{total})；抓了{bodies}篇正文；提取结果统计见extractStats")
    return _report_entry("meal_stock", base_dir, len(pts), notes=notes,
                         extra={"extractStats": dict(stats), "rejectedSamples(每类前5篇)": samples,
                                "spotChecks(独立来源Mysteel英文站周报)": meal_stock_spot_checks(hs.load_series("meal_stock", base_dir)["points"])})



# ---------------------------------------------------------------------------
# 5. 盘面压榨毛利(新浪日K线：豆粕M/豆油Y/豆二B同月份合约)
# ---------------------------------------------------------------------------
def _window_ok(d, ctype, expiry_year):
    """日期d(YYYY-MM-DD)是否落在这个合约类型(到期年expiry_year)的建议交易窗口内。"""
    w = hs.CRUSH_MARGIN_WINDOWS[ctype]
    y, m = int(d[:4]), int(d[5:7])
    if m not in w["months"]:
        return False
    return y == expiry_year - 1 if m in w["prevYearMonths"] else y == expiry_year


def backfill_crush_margin(base_dir=None, from_year=None, to_year=None, sleep_s=0.6):
    """★榨利的绝对数没有意义(毛利没扣加工费，几乎永远为正)，所以评分只能用"跟历史同期比的分位"。这里把过去几年各合约的
    建议交易窗口内的逐日毛利补齐：9月合约取4-7月、5月合约取12-3月、1月合约取8-11月(与前端合约窗口一致，不同年份才可比)。
    数据源：新浪日K线(ak.futures_zh_daily_sina)按合约取全部历史。⚠️已到期合约能不能取到没有验证——每个合约的取数结果都写进报告，
    取不到的会明确列出。"""
    now = datetime.now(timezone.utc)
    to_year = to_year or now.year + 1
    from_year = from_year or now.year - 8
    per_type, contracts = {t: [] for t in hs.CRUSH_MARGIN_WINDOWS}, []
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
    return {"key": "crush_margin", "series": reports, "contracts": contracts,
            "notes": [f"共{len(contracts)}个合约，{len(failed_all)}个有合约取不到(已到期/未上市/接口问题)，见contracts里的failed"]}


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
    return {"key": "term_spread", "series": reports, "pairs": pairs,
            "notes": [f"共{len(pairs)}对合约，{len(failed_all)}对有合约取不到(已到期/未上市/接口问题)，见pairs里的failed"]}


# ---------------------------------------------------------------------------
JOBS = {"us_stu": backfill_us_stocks_to_use, "esr": backfill_esr_weekly, "meal_stu": backfill_meal_stu, "meal_stock": backfill_meal_stock, "margin": backfill_crush_margin, "spread": backfill_term_spread, "feed_days": backfill_feed_days}
DEFAULT_JOBS = ["us_stu", "esr", "meal_stu", "margin", "spread", "feed_days"]      # Mysteel周度库存回填不进默认：第二次报告证明补不全(摘要没数字、2026年6月起正文改版)，改成靠每次抓取累积
LOCAL_ONLY = ("calibrate",)     # 不联网，只基于data/history里已有的序列重新生成校准摘要


def main(argv=None, base_dir=None):
    ap = argparse.ArgumentParser(description="豆粕仪表盘历史回填")
    ap.add_argument("--only", default="all", help="逗号分隔：us_stu,esr,meal_stu,meal_stock,margin,spread,feed_days,calibrate；默认=us_stu,esr,meal_stu,margin,spread,feed_days(meal_stock补不全，不进默认)；calibrate=不联网，只重新生成校准摘要")
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
            if n in ("meal_stu", "meal_stock", "feed_days"):
                kw["start"] = start
            if n in ("meal_stu", "meal_stock", "feed_days"):
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
    with open(os.path.join(out_dir, "_backfill_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


if __name__ == "__main__":
    main()
