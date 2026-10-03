# -*- coding: utf-8 -*-
"""
榨利/月差的窗口与阈值校准诊断(纯本地计算，不联网；只描述，不下"该怎么改"的结论)。

背景：这两个指标的规则是"当前值在往年同月(不同日历年)里的分位，≥80偏一边、≤20偏另一边，同月样本≥20才判"(榨利高=偏空，月差高=偏多)。
这些阈值当初没有数据标定。回填之后每个序列有约600多个点，可以回答几个问题——都用生产代码自己的 history_store.summarize(同一个口径，不是另写一套)：
  1. 年水平有没有漂移？(各合约年的中位数/四分位)——有漂移，"往年同月"分位会长期偏向一边
  2. 同月样本够不够？(窗口各月、各年；最新年的参照数是否≥20)
  3. 现行规则历史上到底触发多少？(逐年的高端/低端触发率；理想是各约20%)
  4. 换阈值怎么变？(90/10、85/15、80/20、75/25)
  5. 去掉各合约年的水平后，规则还触发多少、和现行的方向一致吗？
  6. 逐日数据高度相关——600多个点相当于多少个独立观测？(滞后1自相关→有效样本数)

★做不到的：信号之后N日价格涨跌的前向检验——这些序列的点只存了榨利值/月差百分比，没有价格，无法回算。(要做得靠每天记录的两个系统方向，见analyze_systems.py。)
★去掉年水平用的是整个合约年窗口的中位数，是"事后"才知道的，只用来比较两种口径是否一致，不能直接搬到线上。
"""
import statistics
from datetime import date

import history_store as hs

# 信号编码(方向无关，只描述"在哪一端")：高端(分位≥hi)=+1，低端(≤lo)=-1，中间=0，参照样本不足=None
HI, LO, MIN_N = 80, 20, 20          # 与页面里的CRUSH_SIGNAL/SPREAD_SIGNAL一致(80/20，同月样本≥20)
SENSITIVITY_PAIRS = ((90, 10), (85, 15), (80, 20), (75, 25))
CAVEATS = [
    "这些序列的点只存了榨利值/月差百分比，没有价格——信号之后N日涨跌的前向检验做不了(要靠每天记录的两个系统方向，见analyze_systems.py)",
    "'去掉年水平'用的是整个合约年窗口的中位数，是事后才知道的，只用来比较两种口径是否一致，不能直接用于线上",
    "逐日点高度相关：有效样本数(effectiveN)远小于点数，80/20的触发率估计的误差比点数暗示的大得多",
    "分位按'同日历月、不同日历年'算(与线上一致)，5月合约的12月和1~3月是不同日历年，会互为参照",
]


def contract_year(d, ctype):
    """日期d属于哪一年的合约：窗口月份大于合约月的属于下一年(5月合约的12月、1月合约的8~11月)。"""
    w = hs.CRUSH_MARGIN_WINDOWS[ctype]
    y, m = int(str(d)[:4]), int(str(d)[5:7])
    return y + (1 if m > w["contractMonth"] else 0)


def _q(vals_sorted, p):
    n = len(vals_sorted)
    pos = (n - 1) * p
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    return vals_sorted[lo] + (vals_sorted[hi] - vals_sorted[lo]) * (pos - lo)


def _by_contract_year(points, ctype):
    by = {}
    for p in points:
        by.setdefault(contract_year(p["d"], ctype), []).append(p)
    return dict(sorted(by.items()))


def level_drift(points, ctype):
    """各合约年的点数、中位数、四分位。"""
    out = []
    for y, pts in _by_contract_year(points, ctype).items():
        vs = sorted(p["v"] for p in pts)
        out.append({"year": y, "n": len(vs), "median": round(_q(vs, 0.5), 2), "q1": round(_q(vs, 0.25), 2), "q3": round(_q(vs, 0.75), 2)})
    return out


def month_sufficiency(points, ctype, min_n=MIN_N):
    """窗口各日历月：各日历年的点数；最新一年在该月的参照数(其余日历年同月点数之和)是否≥min_n。"""
    months = {}
    for p in points:
        months.setdefault(int(p["d"][5:7]), {}).setdefault(p["d"][:4], 0)
        months[int(p["d"][5:7])][p["d"][:4]] += 1
    out = {}
    for m, by_year in sorted(months.items()):
        latest = max(by_year)
        ref = sum(n for y, n in by_year.items() if y != latest)
        out[str(m)] = {"byYear": dict(sorted(by_year.items())), "latestYear": latest, "refNForLatestYear": ref, "ok": ref >= min_n}
    return out


def _adjusted(points, ctype):
    """每个点减去它所在合约年窗口的中位数(事后水平)。"""
    med = {y: statistics.median([p["v"] for p in pts]) for y, pts in _by_contract_year(points, ctype).items()}
    return [{"d": p["d"], "v": p["v"] - med[contract_year(p["d"], ctype)]} for p in points]


def rule_trigger_history(points, ctype, hi=HI, lo=LO, min_n=MIN_N, adjust_level=False):
    """把现行规则套到每个历史点上：用生产的history_store.summarize(freq='seasonal-daily')算分位——参照=同日历月、不同日历年的点。
    返回[{d, pct, n, signal}]：signal=+1(≥hi)/-1(≤lo)/0，参照数<min_n或分位不可用时None。adjust_level=True：先去掉各合约年水平。"""
    pts = _adjusted(points, ctype) if adjust_level else [{"d": p["d"], "v": p["v"]} for p in points]
    rows = []
    for p in pts:
        s = hs.summarize(pts, p["v"], p["d"], "seasonal-daily")
        sea = s.get("seasonal") or {}
        n, pct = sea.get("n", 0), sea.get("percentile")
        sig = None
        if pct is not None and n >= min_n:
            sig = 1 if pct >= hi else -1 if pct <= lo else 0
        rows.append({"d": p["d"], "pct": pct, "n": n, "signal": sig})
    return rows


def trigger_share_by_year(rows):
    """按日历年：有信号的点里高端/低端各占多少%(没有信号的不计入分母，另报skipped)。"""
    by = {}
    for r in rows:
        by.setdefault(r["d"][:4], []).append(r)
    out = {}
    for y, rs in sorted(by.items()):
        ev = [r for r in rs if r["signal"] is not None]
        out[y] = {"n": len(ev), "skipped": len(rs) - len(ev),
                  "high": round(sum(1 for r in ev if r["signal"] == 1) / len(ev) * 100, 1) if ev else None,
                  "low": round(sum(1 for r in ev if r["signal"] == -1) / len(ev) * 100, 1) if ev else None}
    return out


def agreement(raw_rows, adj_rows):
    """现行规则 vs 去掉年水平后的规则：逐点比较信号。agreeShare=两者信号相同的占比(两边都有信号的点)；opposite=一个在高端一个在低端的点数。"""
    both = [(a["signal"], b["signal"]) for a, b in zip(raw_rows, adj_rows) if a["signal"] is not None and b["signal"] is not None]
    n = len(both)
    return {"n": n, "agreeShare": round(sum(1 for a, b in both if a == b) / n * 100, 1) if n else None,
            "opposite": sum(1 for a, b in both if a * b == -1)}


def threshold_sensitivity(rows, pairs=SENSITIVITY_PAIRS):
    """同一组分位，换阈值时高端/低端的触发率(只统计分位可用且参照够的点)。"""
    pcts = [r["pct"] for r in rows if r["pct"] is not None and r["signal"] is not None]
    out = []
    for hi, lo in pairs:
        out.append({"hi": hi, "lo": lo, "n": len(pcts),
                    "highShare": round(sum(1 for p in pcts if p >= hi) / len(pcts) * 100, 1) if pcts else None,
                    "lowShare": round(sum(1 for p in pcts if p <= lo) / len(pcts) * 100, 1) if pcts else None})
    return out


def lag1_autocorr(values):
    """滞后1自相关(标准估计：Σ(d_t·d_{t+1})/Σd_t²)。常数/不足2个点返回None。"""
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    den = sum((v - mean) ** 2 for v in values)
    if den == 0:
        return None
    return sum((values[i] - mean) * (values[i + 1] - mean) for i in range(n - 1)) / den


def effective_n(n, rho):
    """AR(1)近似的有效样本数 n·(1-ρ)/(1+ρ)；ρ≤0 时不放大(封顶n)；ρ为None返回None。"""
    if rho is None:
        return None
    if rho <= 0:
        return float(n)
    return n * (1 - rho) / (1 + rho)


def series_autocorr(points, ctype):
    """按合约年分别算滞后1自相关再按点数加权——相邻合约年之间隔着窗口外很久，跨年的'相邻点'不是相邻交易日。"""
    num = tot = 0.0
    for y, pts in _by_contract_year(points, ctype).items():
        vs = [p["v"] for p in pts]
        r = lag1_autocorr(vs)
        if r is not None:
            num += r * len(vs)
            tot += len(vs)
    rho = num / tot if tot else None
    n = len(points)
    ne = effective_n(n, rho)
    return {"rho": None if rho is None else round(rho, 3), "effectiveN": None if ne is None else round(ne, 1), "n": n}


def calibrate_series(points, ctype, key):
    """一个序列的完整校准报告(紧凑：<8KB，回填报告会被日志截断)。"""
    pts = sorted([p for p in points if isinstance(p.get("v"), (int, float)) and not isinstance(p.get("v"), bool)], key=lambda p: p["d"])
    raw = rule_trigger_history(pts, ctype)
    adj = rule_trigger_history(pts, ctype, adjust_level=True)
    return {
        "key": key, "n": len(pts), "from": pts[0]["d"] if pts else None, "to": pts[-1]["d"] if pts else None,
        "contractYears": len(_by_contract_year(pts, ctype)),
        "levelDrift": level_drift(pts, ctype),
        "monthSufficiency": month_sufficiency(pts, ctype),
        "ruleToday": {"hi": HI, "lo": LO, "minN": MIN_N, "byYear": trigger_share_by_year(raw)},
        "levelAdjusted": {"byYear": trigger_share_by_year(adj)},
        "agreement": agreement(raw, adj),
        "thresholdSensitivity": {"today(含年水平漂移)": threshold_sensitivity(raw), "levelAdjusted": threshold_sensitivity(adj)},
        "autocorr": series_autocorr(pts, ctype),
        "caveats": CAVEATS,
    }


def margin_spread_calibration(base_dir=None):
    """六个序列(榨利×3、月差×3)的校准报告；某个序列出错只记它自己的error，不影响其他。没有数据的序列不出现。"""
    out = {}
    for prefix in ("crush_margin_", "term_spread_"):
        for ctype in hs.CRUSH_MARGIN_WINDOWS:
            key = prefix + ctype
            pts = hs.load_series(key, base_dir)["points"]
            if not pts:
                continue
            try:
                out[key] = calibrate_series(pts, ctype, key)
            except Exception as e:  # noqa: BLE001 - 一个序列出错不能影响其他
                out[key] = {"key": key, "error": f"{type(e).__name__}: {str(e)[:160]}"}
    return out
