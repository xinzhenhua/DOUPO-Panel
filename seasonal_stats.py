# -*- coding: utf-8 -*-
"""季节性统计(v101.14)：只做展示用的历史规律，不参与任何计分。纯标准库，不联网。

关键口径(都是从 2026-10-09 的分析里来的，见 README v101.14)：
1. 期货"主力连续"的月涨跌幅会被换月缺口污染：每年 11-12 月主力从 01 换到 05，05 比 01 便宜 5%~15%，这个缺口被算成"下跌"，
   所以同花顺表里"12月80%下跌"大部分是换月造成的。这里用【换月修正指数】：只累计同一合约相邻交易日的涨跌，换月日不计缺口。
2. 现货没有换月问题，单独统计(样本外一致性比期货好)。
3. 月内上冲/下探：相对上月末收盘的最高/最低收盘(收盘价口径，不是日内高低)，上冲≥0、下探≤0。
4. 12个月里纯随机也有约75%概率出现某个月"10年里8年同向"，所以只做分级(较稳/一般/不稳)，不给买卖结论。"""
import argparse
import csv
import glob
import json
import math
import os
import statistics
from datetime import datetime, timezone

SPLIT_YEAR = 2021          # 前后各约5年，用来检验"两半是否同向"
WEEKS = 52


# ----------------------------------------------------------------------------- 指数
def adjusted_index(rows):
    """rows: 按日期升序的 [{"d","c","k"(合约，可无)}]。同一合约相邻日按涨跌幅累计；合约变了(换月日)那天不计缺口。基准=100。"""
    out, idx, prev = [], 100.0, None
    for r in rows:
        if prev is not None:
            same = r.get("k") == prev.get("k")
            if same and prev["c"]:
                idx *= r["c"] / prev["c"]
        o = {"d": r["d"], "i": idx}
        if r.get("k") is not None:
            o["k"] = r["k"]
        out.append(o)
        prev = r
    return out


def index_from_contracts(contracts):
    """contracts: {代码: [{"d","close","hold"}]}。每天主力=当天有价格的合约里持仓量最大者；
    指数每天沿用【前一天的主力合约】的当日涨跌(它当天没价格则持平)，所以换月不产生缺口。返回 [{"d","i","k"}]。"""
    bydate = {}
    for code, rows in contracts.items():
        for r in rows:
            if r.get("close") is None:
                continue
            bydate.setdefault(r["d"], {})[code] = (r["close"], r.get("hold") or 0)
    dates = sorted(bydate)
    out, idx, dom_prev, prices_prev = [], 100.0, None, None
    for n, d in enumerate(dates):
        cur = bydate[d]
        dom = max(cur, key=lambda c: (cur[c][1], c))
        if n > 0 and dom_prev is not None:
            p0 = bydate[dates[n - 1]].get(dom_prev)
            p1 = cur.get(dom_prev)
            if p0 and p1 and p0[0]:
                idx *= p1[0] / p0[0]
        out.append({"d": d, "i": idx, "k": dom})
        dom_prev = dom
    return out


# ----------------------------------------------------------------------------- 月度
def _ym(d):
    return int(d[:4]), int(d[5:7])


def _prev_ym(y, m):
    return (y, m - 1) if m > 1 else (y - 1, 12)


def monthly_returns(idx):
    """→ {年: {月: 涨跌幅%或None}}；涨跌幅=本月最后一个指数/上月最后一个指数−1。首月(无上月末)=None。"""
    last = {}
    for r in idx:
        last[_ym(r["d"])] = r["i"]
    out = {}
    for (y, m), v in sorted(last.items()):
        p = last.get(_prev_ym(y, m))
        out.setdefault(y, {})[m] = None if p is None else (v / p - 1) * 100
    return out


def excursions(idx):
    """→ {年: {月: {"up":%≥0, "dn":%≤0}}}：本月最高/最低指数相对上月末的幅度；没有上月末则不记。"""
    last, hi, lo = {}, {}, {}
    for r in idx:
        k = _ym(r["d"])
        last[k] = r["i"]
        hi[k] = max(hi.get(k, r["i"]), r["i"])
        lo[k] = min(lo.get(k, r["i"]), r["i"])
    out = {}
    for (y, m) in sorted(last):
        p = last.get(_prev_ym(y, m))
        if p is None:
            continue
        out.setdefault(y, {})[m] = {"up": max(0.0, (hi[(y, m)] / p - 1) * 100), "dn": min(0.0, (lo[(y, m)] / p - 1) * 100)}
    return out


def _pct(vals, q):
    v = sorted(vals)
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    pos = (len(v) - 1) * q
    lo = int(math.floor(pos)); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def month_stats(vals):
    v = [x for x in vals if x is not None]
    n = len(v)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "upPct": None, "std": None, "t": None}
    mean = sum(v) / n
    std = statistics.stdev(v) if n >= 2 else None
    t = mean / (std / math.sqrt(n)) if std else None
    return {"n": n, "mean": mean, "median": statistics.median(v), "upPct": sum(1 for x in v if x > 0) / n * 100, "std": std, "t": t}


def grade_month(vals, split_year=SPLIT_YEAR, years=None):
    """vals 与 years 一一对应(可含 None)。较稳：前后两半同向 且 上涨比例≥70%或≤30% 且 |t|≥1.5；
    不稳：前后两半方向相反；样本<6：样本不足；其余：一般。"""
    pairs = [(y, x) for y, x in zip(years or [], vals) if x is not None]
    st = month_stats([x for _, x in pairs])
    if st["n"] < 6:
        return {"label": "样本不足", "why": f"只有{st['n']}个年份"}
    a = [x for y, x in pairs if y <= split_year]; b = [x for y, x in pairs if y > split_year]
    if len(a) < 2 or len(b) < 2:
        return {"label": "一般", "why": "前后两半的样本太少，没法比"}
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    if ma * mb < 0:
        return {"label": "不稳", "why": f"前{len(a)}年均值{ma:+.1f}%，后{len(b)}年{mb:+.1f}%，方向相反"}
    strong_dir = st["upPct"] >= 70 or st["upPct"] <= 30
    if ma * mb > 0 and strong_dir and st["t"] is not None and abs(st["t"]) >= 1.5:
        return {"label": "较稳", "why": f"两半同向({ma:+.1f}%/{mb:+.1f}%)，{st['upPct']:.0f}%的年份{'上涨' if st['upPct'] >= 50 else '下跌'}，t={st['t']:.1f}"}
    return {"label": "一般", "why": f"两半{'同向' if ma * mb > 0 else '不明'}，但胜率{st['upPct']:.0f}%或t={0 if st['t'] is None else st['t']:.1f}不够强"}


# ----------------------------------------------------------------------------- 年内路径
def weekly_paths(idx, min_days=200):
    """→ {年: [52个周度累计收益%或None]}。基准=上一年最后一个指数(没有上一年数据的年份跳过)；周=(年内第几天−1)//7，最多51；中间缺的周沿用前值。
    min_days：该年至少多少个交易日才算(今年没走完也要，所以调用方对今年放宽)。"""
    by_year = {}
    for r in idx:
        by_year.setdefault(int(r["d"][:4]), []).append(r)
    out = {}
    years = sorted(by_year)
    for y in years:
        prev = by_year.get(y - 1)
        if not prev or len(by_year[y]) < min_days and y != years[-1]:
            continue
        base = prev[-1]["i"]
        arr = [None] * WEEKS
        for r in by_year[y]:
            doy = datetime.strptime(r["d"], "%Y-%m-%d").timetuple().tm_yday
            w = min(WEEKS - 1, (doy - 1) // 7)
            arr[w] = (r["i"] / base - 1) * 100
        last = None
        lastw = max((w for w in range(WEEKS) if arr[w] is not None), default=-1)
        for w in range(lastw + 1):
            if arr[w] is None:
                arr[w] = last
            last = arr[w]
        out[y] = arr
    return out


def path_bands(paths):
    keys = {"p10": .10, "p25": .25, "median": .5, "p75": .75, "p90": .90}
    bands = {k: [] for k in keys}
    for w in range(WEEKS):
        col = [p[w] for p in paths.values() if p[w] is not None]
        for k, q in keys.items():
            bands[k].append(_pct(col, q) if col else None)
    return bands


def position_in_band(value, hist):
    h = [x for x in hist if x is not None]
    if len(h) < 5:
        return {"percentile": None, "flag": "样本不足", "n": len(h)}
    pct = sum(1 for x in h if x <= value) / len(h) * 100
    flag = "高于历史带" if pct >= 90 else "低于历史带" if pct <= 10 else "带内"
    return {"percentile": pct, "flag": flag, "n": len(h)}


# ----------------------------------------------------------------------------- 汇总
def _r(x, nd=2):
    return None if x is None else round(x, nd)


def _stat_out(st):
    return {k: (v if k == "n" else _r(v)) for k, v in st.items()}


def build(fut_idx, spot_idx, meta_extra=None):
    fm, sm = monthly_returns(fut_idx), monthly_returns(spot_idx)
    ex = excursions(fut_idx)
    years_all = sorted(set(fm) | set(sm))
    months = []
    for m in range(1, 13):
        fy = [(y, fm[y].get(m)) for y in years_all if y in fm]
        sy = [(y, sm[y].get(m)) for y in years_all if y in sm]
        ups = [ex[y][m]["up"] for y in ex if m in ex[y]]
        dns = [ex[y][m]["dn"] for y in ex if m in ex[y]]
        months.append({
            "month": m,
            "futures": _stat_out(month_stats([v for _, v in fy])),
            "spot": _stat_out(month_stats([v for _, v in sy])),
            "gradeFutures": grade_month([v for _, v in fy], SPLIT_YEAR, [y for y, _ in fy]),
            "gradeSpot": grade_month([v for _, v in sy], SPLIT_YEAR, [y for y, _ in sy]),
            "excursion": {"n": len(ups), "upMean": _r(sum(ups) / len(ups)) if ups else None, "upMedian": _r(_pct(ups, .5)), "upP90": _r(_pct(ups, .9)),
                          "dnMean": _r(sum(dns) / len(dns)) if dns else None, "dnMedian": _r(_pct(dns, .5)), "dnP10": _r(_pct(dns, .1))},
        })
    table = {"futures": {str(y): {str(m): _r(v, 1) for m, v in fm[y].items() if v is not None} for y in fm},
             "spot": {str(y): {str(m): _r(v, 1) for m, v in sm[y].items() if v is not None} for y in sm}}
    paths = weekly_paths(fut_idx)
    cur_year = int(fut_idx[-1]["d"][:4])
    cur = weekly_paths([r for r in fut_idx], min_days=1).get(cur_year)
    hist = {y: p for y, p in paths.items() if y != cur_year}
    bands = path_bands(hist)
    current = None
    if cur:
        lastw = max(w for w in range(WEEKS) if cur[w] is not None)
        position = position_in_band(cur[lastw], [p[lastw] for p in hist.values()])
        current = {"year": cur_year, "path": [_r(x) for x in cur], "lastWeek": lastw, "value": _r(cur[lastw]), "asOf": fut_idx[-1]["d"], "position": {k: (_r(v) if isinstance(v, float) else v) for k, v in position.items()}}
    meta = {"builtAt": datetime.now(timezone.utc).isoformat(), "firstDate": fut_idx[0]["d"], "lastDate": fut_idx[-1]["d"], "priceBasis": "收盘价",
            "rollMethod": "换月修正指数：只累计同一合约相邻交易日的涨跌，换月日不计缺口", "splitYear": SPLIT_YEAR,
            "years": [y for y in years_all], "pathYears": sorted(hist),
            "caveats": ["每个月只有约10个年份，样本很小；12个月里纯随机也有约75%概率出现某个月'10年里8年同向'(多重比较)，所以只分级，不给买卖结论。",
                        "期货月涨跌幅已做换月修正；同花顺等'主连'表格里 11-12月偏空、部分 3-4月/8月数字含换月缺口，和这里不能直接比。",
                        "月内上冲/下探用收盘价，不是日内最高最低，实际波动比这里略大。",
                        "季节性只描述'历史上通常怎样'，不预测今年；今年若长期偏离历史带，更可能是资金或事件在主导。"]}
    if meta_extra:
        meta.update(meta_extra)
    return {"months": months, "monthlyTable": table, "path": {"weeks": WEEKS, "bands": {k: [_r(x) for x in v] for k, v in bands.items()},
            "years": {str(y): [_r(x) for x in p] for y, p in sorted(hist.items())}, "current": current}, "meta": meta}


# ----------------------------------------------------------------------------- 读文件
def load_baseline_csv(path):
    fut, spot = [], []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            d = r["date"][:10]
            fut.append({"d": d, "c": float(r["futures"]), "k": r["dominant_contract"]})
            spot.append({"d": d, "c": float(r["spot"])})
    fut.sort(key=lambda x: x["d"]); spot.sort(key=lambda x: x["d"])
    return fut, spot


def build_from_baseline_csv(path):
    fut, spot = load_baseline_csv(path)
    return build(adjusted_index(fut), adjusted_index(spot), {"source": "baseline_csv", "futuresSeries": "生意社主力合约价(换月日不计缺口)", "spotSeries": "生意社现货价"})


def load_contract_files(dirpath):
    out = {}
    for f in sorted(glob.glob(os.path.join(dirpath, "M*.csv"))):
        code = os.path.splitext(os.path.basename(f))[0].lower()
        rows = []
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    rows.append({"d": str(r["date"])[:10], "close": float(r["close"]), "hold": float(r.get("hold") or 0)})
                except (KeyError, ValueError):
                    continue
        if rows:
            out[code] = rows
    return out


def contracts_sufficient(contracts):
    if len(contracts) < 20:
        return False, f"合约文件只有{len(contracts)}个(至少需要20个才能覆盖10年)"
    ds = sorted({r["d"] for rows in contracts.values() for r in rows})
    if not ds or ds[0] > "2017-06-30":
        return False, f"合约文件最早只到{ds[0] if ds else '—'}，没覆盖到2017年"
    return True, ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成季节性统计 data/seasonal.json")
    ap.add_argument("--raw", default=os.path.join("data", "raw", "seasonal"))
    ap.add_argument("--out", default=os.path.join("data", "seasonal.json"))
    a = ap.parse_args(argv)
    base = os.path.join(a.raw, "meal_spot_futures_10y.csv")
    if not os.path.exists(base):
        raise SystemExit(f"找不到基线文件 {base}")
    fut, spot = load_baseline_csv(base)
    note = "只用基线CSV"
    source = "baseline_csv"
    res = None
    cdir = os.path.join(a.raw, "contracts")
    if os.path.isdir(cdir):
        contracts = load_contract_files(cdir)
        okc, why = contracts_sufficient(contracts)
        if okc:
            fidx = index_from_contracts(contracts)
            res = build(fidx, adjusted_index(spot), {"source": "contracts", "futuresSeries": f"{len(contracts)}个具体合约，每天沿用前一天主力(持仓最大)合约的涨跌", "spotSeries": "生意社现货价(来自基线CSV)"})
            source, note = "contracts", f"用了{len(contracts)}个合约文件"
        else:
            note = f"合约文件不够用，回退基线CSV：{why}"
    if res is None:
        res = build(adjusted_index(fut), adjusted_index(spot), {"source": "baseline_csv", "futuresSeries": "生意社主力合约价(换月日不计缺口)", "spotSeries": "生意社现货价"})
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    print(f"[季节性] {source}：{note}；{res['meta']['firstDate']}~{res['meta']['lastDate']} → {a.out}")
    return {"source": source, "note": note, "out": a.out}


if __name__ == "__main__":
    main()
