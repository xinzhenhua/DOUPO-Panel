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
    ("2026-02-02", 93.04, "2026年第5周"), ("2026-04-13", 62.05, "2026年第15周"), ("2026-04-20", 61.38, "2026年第16周"),
    ("2026-05-29", 34.74, "2026年第22周"), ("2026-06-05", 50.65, "2026年第23周"), ("2026-07-03", 72.47, "2026年第27周"),
    ("2026-07-31", 100.34, "2026年第31周"), ("2026-08-28", 116.73, "2026年第35周"),
]


def meal_stock_spot_checks(points, tol_days=5, tol_wan=0.1):
    """对每个校验点找最近的回填点：日期差<=tol_days且数值差<=tol_wan万吨算通过。"""
    out = []
    for d, v, label in MEAL_STOCK_CHECKPOINTS:
        dd = date.fromisoformat(d)
        near = min(points, key=lambda p: abs((date.fromisoformat(p["d"][:10]) - dd).days), default=None)
        if near is None or abs((date.fromisoformat(near["d"][:10]) - dd).days) > tol_days:
            out.append({"week": label, "expected": v, "result": "缺失(附近没有回填点)"})
        else:
            ok = abs(near["v"] - v) <= tol_wan
            out.append({"week": label, "expected": v, "got": near["v"], "gotDate": near["d"], "result": "通过" if ok else "不一致"})
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
        out["meal_stu"] = {"n": len(vals), "quantiles": quantiles(vals), "currentThresholds": {"tight<=10": share(vals, lambda v: v <= 10), "loose>=14": share(vals, lambda v: v >= 14)},
                           "allValues": {p["d"]: p["v"] for p in m}}
    k = hs.load_series("meal_stock", base_dir)["points"]
    if k:
        vals = [p["v"] for p in k]
        out["meal_stock"] = {"n": len(vals), "quantiles": quantiles(vals), "currentThresholds": {"tight<50": share(vals, lambda v: v < 50), "loose>100": share(vals, lambda v: v > 100)},
                             "pointsPerYear": dict(Counter(p["d"][:4] for p in k)), "spotChecks(独立来源Mysteel英文站周报)": meal_stock_spot_checks(k)}
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
        if fetch_bodies and idx < max_bodies and it.get("url"):
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
                pts.append({"d": f"{k[0]}-{k[1]:02d}", "v": v, "pub": pub.isoformat(), "x": {"how": how}})
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
        if val is None and fetch_bodies and weeklike and bodies < max_bodies and it.get("url"):
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
JOBS = {"us_stu": backfill_us_stocks_to_use, "esr": backfill_esr_weekly, "meal_stu": backfill_meal_stu, "meal_stock": backfill_meal_stock}
LOCAL_ONLY = ("calibrate",)     # 不联网，只基于data/history里已有的序列重新生成校准摘要


def main(argv=None, base_dir=None):
    ap = argparse.ArgumentParser(description="豆粕仪表盘历史回填")
    ap.add_argument("--only", default="all", help="逗号分隔：us_stu,esr,meal_stu,meal_stock,calibrate；默认前四项全部；calibrate=不联网，只重新生成校准摘要")
    ap.add_argument("--start", default="2020-01-01", help="Mysteel两项的起始日期")
    ap.add_argument("--no-bodies", action="store_true", help="国内库消比不抓文章正文，只用摘要")
    args = ap.parse_args(argv)
    names = list(JOBS) if args.only == "all" else [n.strip() for n in args.only.split(",") if n.strip()]
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
            if n in ("meal_stu", "meal_stock"):
                kw["start"] = start
            if n in ("meal_stu", "meal_stock"):
                kw["fetch_bodies"] = not args.no_bodies
            entry = JOBS[n](**kw)
        except Exception as e:  # noqa: BLE001 - 一项失败不影响其他项
            entry = {"key": n, "error": f"{type(e).__name__}: {e}"}
        report["series"].append(entry)
        print(json.dumps(entry, ensure_ascii=False, indent=2), flush=True)
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
