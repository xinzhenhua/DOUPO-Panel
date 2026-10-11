# -*- coding: utf-8 -*-
"""现货/期货价格每日自动累积(v101.20)。
数据来源：akshare 的 futures_spot_price(日期, vars_list=['M'])——生意社(100ppi.com)的豆粕现货价、近月合约价、主力合约价。
  用户 2026-10-09 给的基线 CSV(meal_spot_futures_10y.csv，列 spot/dominant_contract/futures/near_contract…)就是这个接口的输出，所以自动抓取和基线口径一致。
累积文件：data/raw/seasonal/spot_auto.csv(列 date,spot,dominant_contract,futures,near_contract,near_contract_price)，按日期幂等 upsert。
  - 每日：job_spot_daily 取最近 4 个交易日里文件还没有的(生意社收盘后 18:30 才有当天数据)。
  - 回补：job_spot 从新到旧补缺口，带时间预算、可重复运行接着补；连续失败多次就中止(站点限流/改版)，不死磨。
  - seasonal_stats 读它，与基线合并：重叠日一致(容差 1 元)就以自动抓取的为准；不一致就保留基线并在 meta.autoMerge 里标出。
★开发环境连不上生意社，这里的测试全部用假接口；真实接口是否稳定要看 Actions 日志。"""
import csv, os, time, datetime

AUTO_COLS = ["date", "spot", "dominant_contract", "futures", "near_contract", "near_contract_price"]
BASE_NAME = "meal_spot_futures_10y.csv"
AUTO_NAME = "spot_auto.csv"


def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def load_rows(path):
    """读累积文件或基线CSV(列名兼容)。→ {日期: {date,spot,dominant_contract,futures,near_contract,near_contract_price}}；现货或期货价不是数的行跳过。"""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            d = str(r.get("date") or "")[:10]
            spot, fut = _f(r.get("spot")), _f(r.get("futures"))
            if len(d) != 10 or d[4] != "-" or spot is None or fut is None:
                continue
            out[d] = {"date": d, "spot": spot, "dominant_contract": (r.get("dominant_contract") or "").strip(), "futures": fut,
                      "near_contract": (r.get("near_contract") or "").strip(), "near_contract_price": _f(r.get("near_contract_price"))}
    return out


def _same(a, b):
    return a["spot"] == b["spot"] and a["futures"] == b["futures"] and a["dominant_contract"] == b["dominant_contract"]


def upsert(path, rows):
    """按日期幂等写入。→ (新增行数, 更新行数)。文件按日期升序。"""
    cur = load_rows(path)
    added = updated = 0
    for r in rows:
        n = {"date": r["date"], "spot": float(r["spot"]), "dominant_contract": r.get("dominant_contract") or "", "futures": float(r["futures"]),
             "near_contract": r.get("near_contract") or "", "near_contract_price": _f(r.get("near_contract_price"))}
        old = cur.get(n["date"])
        if old is None:
            added += 1
        elif _same(old, n):
            continue
        else:
            updated += 1
        cur[n["date"]] = n
    if added or updated or not os.path.exists(path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(AUTO_COLS)
            for d in sorted(cur):
                r = cur[d]
                w.writerow([r["date"], r["spot"], r["dominant_contract"], r["futures"], r["near_contract"], "" if r["near_contract_price"] is None else r["near_contract_price"]])
        os.replace(tmp, path)
    return added, updated


def missing_dates(existing, start, end, is_trading):
    """[start,end] 内的交易日里 existing 没有的，从新到旧。is_trading(date)->bool。"""
    d0, d1 = datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
    out, d = [], d1
    while d >= d0:
        if is_trading(d) and d.isoformat() not in existing:
            out.append(d.isoformat())
        d -= datetime.timedelta(days=1)
    return out


def make_get_row(fetch, deadline_s=45):
    """把 fetch(日期iso)->DataFrame(akshare) 包成 get_row(日期iso)->(行或None, 原因)。有硬性时限；复用 fetch_data.parse_spot_basis 的解析和合理性检查。"""
    def get_row(ds):
        import fetch_data
        ok_, res = fetch_data._run_with_deadline(lambda: fetch(ds), deadline_s)
        if not ok_:
            return None, str(res)
        parsed, why = fetch_data.parse_spot_basis(res)
        if parsed is None:
            return None, why
        return {"date": ds, "spot": parsed["spot"], "dominant_contract": parsed["domSymbol"] or "", "futures": parsed["domPrice"],
                "near_contract": parsed["nearSymbol"] or "", "near_contract_price": parsed["nearPrice"]}, None
    return get_row


def backfill(path, start, end, get_row, is_trading, budget_s=2400, pause=0.8, max_consecutive_fail=8, clock=time.time, sleep=time.sleep, flush_every=20):
    """从新到旧补 path 里缺的交易日。预算到了就停(报告剩余)，连续失败 max_consecutive_fail 次就中止。每 flush_every 条落盘一次，被杀也不丢进度。"""
    todo = missing_dates(set(load_rows(path)), start, end, is_trading)
    rep = {"ok": True, "missing": len(todo), "fetched": [], "failed": {}, "stoppedByBudget": False, "abortedByFailures": False, "remaining": 0}
    buf, fails, t0 = [], 0, clock()

    def flush():
        if buf:
            upsert(path, buf)
            buf.clear()
    try:
        for i, ds in enumerate(todo):
            if clock() - t0 > budget_s:
                rep["stoppedByBudget"], rep["remaining"] = True, len(todo) - i
                break
            try:
                r, why = get_row(ds)
            except Exception as e:  # noqa: BLE001
                r, why = None, f"{type(e).__name__}: {e}"[:150]
            if r is None:
                rep["failed"][ds] = (why or "")[:150]
                fails += 1
                if fails >= max_consecutive_fail:
                    rep["abortedByFailures"], rep["remaining"] = True, len(todo) - i - 1
                    break
            else:
                fails = 0
                buf.append(r)
                rep["fetched"].append(ds)
                if len(buf) >= flush_every:
                    flush()
            sleep(pause)
    finally:
        flush()
    return rep


def merge_rows(base, auto, tol=1.0):
    """base/auto: {日期: 行}。→ ([{d,spot,futures,k}] 升序, 报告)。
    重叠日：现货和期货价最大差 ≤ tol 视为一致，用自动抓取的；不一致就保留基线(并在报告里标 consistent=False)，自动抓取的新日期照样追加。"""
    overlap = sorted(set(base) & set(auto))
    ms = max((abs(base[d]["spot"] - auto[d]["spot"]) for d in overlap), default=None)
    mf = max((abs(base[d]["futures"] - auto[d]["futures"]) for d in overlap), default=None)
    consistent = None if not overlap else (ms <= tol and mf <= tol)
    use_auto = consistent is not False
    merged = {d: base[d] for d in base}
    for d, r in auto.items():
        if d not in merged or use_auto:
            merged[d] = r
    rows = [{"d": d, "spot": merged[d]["spot"], "futures": merged[d]["futures"], "k": merged[d]["dominant_contract"] or None} for d in sorted(merged)]
    rep = {"baseRows": len(base), "autoRows": len(auto), "overlap": len(overlap), "maxAbsSpot": ms, "maxAbsFut": mf, "consistent": consistent, "tolerance": tol}
    return rows, rep


# ----------------------------------------------------------------------------- 给 fetch_seasonal_raw 用的任务
def _is_trading(d):
    import cn_calendar
    return cn_calendar.dce_is_trading_day(d)


def _akshare_fetch():
    import fetch_data
    return fetch_data._akshare_spot_price


def job_spot(out, years=10, budget_s=2400, fetch=None, today=None, **kw):
    """回补(从新到旧)。★基线 CSV 覆盖的区间[首日,末日]整段不抓(v101.22)：基线里没有的工作日就是休市日，
    而重叠日自动抓取与基线逐个一致(用户 2026-10-11 的实测：927 个重叠日差 0.0)，去抓只会撞上假日、触发'连续失败中止'，
    还让 remaining 虚高(1665)。只抓基线末日之后(和基线首日之前)缺的交易日。"""
    today = today or datetime.date.today()
    start = (today - datetime.timedelta(days=365 * years)).isoformat()
    get_row = make_get_row(fetch or _akshare_fetch())
    base = load_rows(os.path.join(out, BASE_NAME))
    lo, hi = (min(base), max(base)) if base else (None, None)
    trading = (lambda d: _is_trading(d) and not (lo <= d.isoformat() <= hi)) if base else _is_trading
    rep = backfill(os.path.join(out, AUTO_NAME), start, today.isoformat(), get_row, trading, budget_s=budget_s, **kw)
    rep["skippedBecauseBaselineCovers"] = [lo, hi] if base else None
    return rep


def job_spot_daily(out, now_bj=None, fetch=None, n=4, **kw):
    """每日累积：最近 n 个交易日(18:30 前不试当天)里文件还没有的。"""
    import fetch_data
    if now_bj is None:
        now_bj = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).replace(tzinfo=None)
    cands = [d.isoformat() for d in fetch_data._spot_candidate_dates(now_bj, n)]
    path = os.path.join(out, AUTO_NAME)
    have = set(load_rows(path))
    get_row = make_get_row(fetch or _akshare_fetch())
    rep = {"ok": True, "candidates": cands, "fetched": [], "failed": {}, "alreadyHad": [d for d in cands if d in have]}
    rows = []
    for ds in cands:
        if ds in have:
            continue
        r, why = get_row(ds)
        if r is None:
            rep["failed"][ds] = why
        else:
            rows.append(r); rep["fetched"].append(ds)
        time.sleep(kw.get("pause", 0.8))
    if rows:
        upsert(path, rows)
    rep["ok"] = bool(rep["fetched"]) or bool(rep["alreadyHad"]) or not cands
    return rep


def main(argv=None):
    import argparse, json
    ap = argparse.ArgumentParser(description="现货/期货每日累积")
    ap.add_argument("--out", default=os.path.join("data", "raw", "seasonal"))
    ap.add_argument("--mode", choices=["daily", "backfill"], default="daily")
    ap.add_argument("--budget", type=int, default=2400)
    ap.add_argument("--years", type=int, default=10)
    a = ap.parse_args(argv)
    rep = job_spot_daily(a.out) if a.mode == "daily" else job_spot(a.out, a.years, a.budget)
    print(json.dumps(rep, ensure_ascii=False)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
