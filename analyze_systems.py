# -*- coding: utf-8 -*-
"""
检验"基本面(仅供需) vs 市场结构"的状态组合，对之后N个交易日的价格变动有没有区别。用法：python3 analyze_systems.py [sep|may|jan] [版本号]

数据：record_systems.py 每天记录的 data/history/systems_{合约}.json(自带当天收盘价，不需要外部行情)。

⚠️这个脚本只做描述统计，**不给任何"有效/无效"的结论**，而且默认就会提醒你为什么不能轻易下结论：
  1. 有效样本远小于看起来的样本：相邻两天的"之后N日"窗口大部分重叠，有效样本约 n/N。
  2. 状态组合有9种 × 3个合约 × 多个观察期——看得越多，越容易碰巧看到"显著"的差别(多重比较)。
  3. 合约价格包含移仓/到期的影响；合约代码变了的前后不可比(已按代码过滤)。
  4. 评分规则版本不同的数据不能混在一起(阈值/权重/门槛变了，方向的含义就变了)——默认只用最新版本的数据。
  5. 样本<30期：只列出，标"样本不足"。
"""
import os
import statistics
import sys
from datetime import date

import history_store as hs

MIN_N = 30
STATES_ORDER = ["同向偏多", "同向偏空", "背离(基本面偏多/结构偏空)", "背离(基本面偏空/结构偏多)",
                "基本面中性/结构偏多", "基本面中性/结构偏空", "基本面偏多/结构中性", "基本面偏空/结构中性", "都中性"]


def classify(fund_dir, struct_dir):
    f, s = fund_dir, struct_dir
    if f == "中性" and s == "中性":
        return "都中性"
    if f == "中性":
        return f"基本面中性/结构{s}"
    if s == "中性":
        return f"基本面{f}/结构中性"
    if f == s:
        return f"同向{f}"
    return f"背离(基本面{f}/结构{s})"


def load_records(contract, base_dir=None):
    pts = hs.load_series(f"systems_{contract}", base_dir)["points"]
    return [{"d": p["d"], "fundRatio": p["v"], **p.get("x", {})} for p in pts]


def usable(r, version=None, in_window_only=True):
    """能用来检验的记录：交易日、在该合约的推荐交易窗口内、两个系统都有方向、市场结构不是只有1项(thin)、有价格。
    ★窗口外的记录价格可能已过期、合约可能已到期(比如9月合约在10月)，而且那时你并不在交易这个合约——混进来会污染结论。"""
    if r.get("tradingDay") is not True or r.get("structThin"):
        return False
    if in_window_only and r.get("inWindow") is not True:
        return False
    if not r.get("fundDir") or not r.get("structDir"):
        return False
    if r.get("close") is None or not r.get("priceDate") or not r.get("symbol"):
        return False
    return version is None or r.get("scoringVersion") == version


def price_series(records):
    """按priceDate去重(同一个价格日取最晚的一条记录)，升序。"""
    by = {}
    for r in records:
        if r.get("close") is None or not r.get("priceDate"):
            continue
        if r["priceDate"] not in by or r["d"] >= by[r["priceDate"]]["d"]:
            by[r["priceDate"]] = r
    return [by[k] for k in sorted(by)]


def forward_return(prices, i, horizon):
    """第i个价格日之后horizon个价格日的涨跌幅(%)。合约代码变了，或日历间隔异常(缺数据)时返回None。"""
    j = i + horizon
    if j >= len(prices):
        return None
    a, b = prices[i], prices[j]
    if a["symbol"] != b["symbol"]:
        return None
    gap = (date.fromisoformat(b["priceDate"]) - date.fromisoformat(a["priceDate"])).days
    if gap > horizon * 2 + 5:                     # 之间缺了很多天数据：不拿来算
        return None
    return (b["close"] / a["close"] - 1) * 100


def latest_version(records):
    vs = [r.get("scoringVersion") for r in records if r.get("scoringVersion")]
    return max(vs, key=lambda v: [int(x) if x.isdigit() else 0 for x in v.lstrip("v").split(".")]) if vs else None


def summarize(contract, horizon=10, base_dir=None, version="latest", in_window_only=True):
    recs = load_records(contract, base_dir)
    ver = latest_version(recs) if version == "latest" else version
    # ★价格序列用全部记录(市场价格跟评分规则版本无关)；只有"方向标签"才按版本过滤(规则变了，方向的含义就变了)。
    #   如果价格也按版本过滤，新版本刚上线时后续几天的价格只存在于同版本记录里，前瞻收益会被白白少算。
    prices = price_series(recs)
    idx = {p["priceDate"]: i for i, p in enumerate(prices)}
    rows = {}
    n_usable = n_ret = 0
    for r in recs:
        if not usable(r, ver, in_window_only):
            continue
        n_usable += 1
        i = idx.get(r["priceDate"])
        if i is None:
            continue
        ret = forward_return(prices, i, horizon)
        if ret is None:
            continue
        n_ret += 1
        rows.setdefault(classify(r["fundDir"], r["structDir"]), []).append(ret)
    out = []
    for label in STATES_ORDER:
        xs = rows.get(label)
        if not xs:
            continue
        out.append({"state": label, "n": len(xs), "effectiveN": round(len(xs) / horizon, 1), "mean": round(statistics.mean(xs), 3),
                    "median": round(statistics.median(xs), 3), "upShare": round(sum(1 for v in xs if v > 0) / len(xs) * 100, 1),
                    "enough": len(xs) >= MIN_N})
    return {"contract": contract, "horizon": horizon, "version": ver, "records": len(recs), "usable": n_usable, "withReturn": n_ret,
            "range": (recs[0]["d"], recs[-1]["d"]) if recs else None, "rows": out,
            "versionsPresent": sorted({r.get("scoringVersion") for r in recs if r.get("scoringVersion")})}


def render(res):
    L = [f"【{res['contract']}合约】之后{res['horizon']}个交易日的涨跌幅(%)  评分规则版本={res['version']}  "
         f"记录{res['records']}天 / 可用{res['usable']} / 有前瞻收益{res['withReturn']}"
         + (f"  ({res['range'][0]}~{res['range'][1]})" if res["range"] else "")]
    if len(res["versionsPresent"]) > 1:
        L.append(f"   ⚠️历史里有多个评分规则版本{res['versionsPresent']}：只用了{res['version']}，不同版本的方向含义不同，没有混用")
    if not res["rows"]:
        L.append("   (还没有可用的样本——需要先累积记录，并且有足够的后续交易日)")
    for r in res["rows"]:
        L.append(f"   {r['state']:<22} n={r['n']:<4} 有效样本≈{r['effectiveN']:<5} 均值{r['mean']:+.2f}%  中位{r['median']:+.2f}%  上涨占比{r['upShare']:.0f}%"
                 + ("" if r["enough"] else f"   ⚠️样本不足(<{MIN_N})，仅供参考"))
    L.append("   ⚠️只是描述统计，不是结论：相邻两天的前瞻窗口大部分重叠(有效样本≈n/观察期)；9种状态×3合约×多个观察期会有多重比较；"
             "合约价格含移仓/到期影响；不同评分规则版本不混用。")
    return "\n".join(L)


def main(argv=None):
    argv = argv or sys.argv[1:]
    contracts = [argv[0]] if argv and argv[0] in ("sep", "may", "jan") else ["sep", "may", "jan"]
    version = argv[1] if len(argv) > 1 else "latest"
    for c in contracts:
        for h in (5, 10, 20):
            print(render(summarize(c, h, version=version)))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
