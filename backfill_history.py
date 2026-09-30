# -*- coding: utf-8 -*-
"""
历史回填(一次性，手动运行)
==========================
用法：
  python3 backfill_history.py                      # 四项全部回填
  python3 backfill_history.py --only us_stu,meal_stu
  python3 backfill_history.py --start 2020-01-01   # Mysteel两项的起始日期
  python3 backfill_history.py --no-bodies          # 国内库消比只用搜索摘要，不逐篇抓正文(更快，但覆盖的月份更少)
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
import sys
import time
from datetime import datetime, timedelta, timezone

import fetch_data as fd
import history_store as hs


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
                                f"没有净销售字段(已跳过)的年度: {fields_missing}" if fields_missing else "所有年度都有净销售字段"])


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
    bodies_ok = bodies_fail = 0
    for idx, (pub, it) in enumerate(arts):
        if fetch_bodies and idx < max_bodies and it.get("url"):
            raw, dbg = fd.fetch_text_debug(it["url"], headers={"Referer": "https://ncp.mysteel.com/"})
            if raw:
                region = fd._extract_article_region(fd._html_to_text(raw), str(it.get("title") or ""))
                recs = fd._parse_meal_balance_text(region, pub)
                if recs:
                    bodies_ok += 1
                    for k, r in recs.items():
                        cands.setdefault(k, []).append((pub, 0, r))
                else:
                    bodies_fail += 1
            else:
                bodies_fail += 1
            time.sleep(sleep_s)
        for k, r in fd._parse_meal_balance_text(it.get("content"), pub).items():
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
            unusable.append(f"{k[0]}-{k[1]:02d}")
    hs.record_points("meal_stu", pts, base_dir)
    notes.append(f"平衡表文章{len(arts)}篇(搜索总数{total})；正文成功解析{bodies_ok}篇、失败{bodies_fail}篇" if fetch_bodies else f"平衡表文章{len(arts)}篇；未抓正文，只用摘要")
    if unusable:
        notes.append(f"出现过但没法给出库消比的月份: {unusable}")
    return _report_entry("meal_stu", base_dir, len(pts), notes=notes)


# ---------------------------------------------------------------------------
# 4. 国内豆粕周度库存
# ---------------------------------------------------------------------------
def backfill_meal_stock(base_dir=None, start=None, today=None, max_pages=40):
    if today is None:
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    start = start or datetime(2020, 1, 1).date()
    now_bj = datetime(today.year, today.month, today.day, 12, 0, 0)
    items, total, note = _search_articles("全国主要区域大豆", datetime(start.year, start.month, start.day), now_bj, max_pages=max_pages)
    pts, rejected = {}, 0
    for it in items:
        pub = _pub(it)
        if not pub:
            continue
        title, content = str(it.get("title") or ""), str(it.get("content") or "")
        national = "全国" in title or "全国" in content
        got = None
        for text in (content, title):
            good, _rej = fd._extract_meal_stock_values(text)
            if good and national:
                got = good[0]
                break
        if got is None:
            rejected += 1
            continue
        pts[pub.isoformat()] = {"d": pub.isoformat(), "v": got}
    hs.record_points("meal_stock", list(pts.values()), base_dir)
    notes = [note] if note else []
    notes.append(f"搜索到{len(items)}篇(总数{total})，其中{rejected}篇没有提取出全国豆粕库存(区域数据/变动量/别的指标等，已按现有规则拒绝)")
    return _report_entry("meal_stock", base_dir, len(pts), notes=notes)


# ---------------------------------------------------------------------------
JOBS = {"us_stu": backfill_us_stocks_to_use, "esr": backfill_esr_weekly, "meal_stu": backfill_meal_stu, "meal_stock": backfill_meal_stock}


def main(argv=None, base_dir=None):
    ap = argparse.ArgumentParser(description="豆粕仪表盘历史回填")
    ap.add_argument("--only", default="all", help="逗号分隔：us_stu,esr,meal_stu,meal_stock；默认全部")
    ap.add_argument("--start", default="2020-01-01", help="Mysteel两项的起始日期")
    ap.add_argument("--no-bodies", action="store_true", help="国内库消比不抓文章正文，只用摘要")
    args = ap.parse_args(argv)
    names = list(JOBS) if args.only == "all" else [n.strip() for n in args.only.split(",") if n.strip()]
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(), "series": []}
    for n in names:
        if n not in JOBS:
            report["series"].append({"key": n, "error": "未知的回填项"})
            continue
        print(f"[回填] {n} ...", flush=True)
        try:
            kw = {"base_dir": base_dir}
            if n in ("meal_stu", "meal_stock"):
                kw["start"] = start
            if n == "meal_stu":
                kw["fetch_bodies"] = not args.no_bodies
            entry = JOBS[n](**kw)
        except Exception as e:  # noqa: BLE001 - 一项失败不影响其他项
            entry = {"key": n, "error": f"{type(e).__name__}: {e}"}
        report["series"].append(entry)
        print(json.dumps(entry, ensure_ascii=False, indent=2), flush=True)
    out_dir = base_dir or hs.HISTORY_DIR
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "_backfill_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


if __name__ == "__main__":
    main()
