# -*- coding: utf-8 -*-
"""
每天记录两个系统的方向：把 scripts/snapshot_systems.js(无头运行页面评分代码)产出的快照写进历史序列 systems_sep/may/jan。

为什么记录：基本面(仅供需票)和市场结构(基差/月差/量价)的"背离"到底有没有信息，现在只是直觉。每天把两个系统的方向连同
当天价格记下来，几个月后用自己的数据检验(analyze_systems.py)，而不是靠直觉。

每个点：d=北京日期，v=基本面(仅供需)的净倾向(-1~+1)，x=其余字段(市场结构方向/综合预警/价格/覆盖情况/评分规则版本…)。

★同一天多次运行的合并策略(每小时同步会跑很多次)：
  页面加载时联网拉天气/汇率，偶尔被限流——天气票缺席会改变基本面的投票构成，方向可能因为"网络噪声"翻转，污染要检验的数据。
  所以同一天：覆盖(基本面票数+市场结构项数)更完整的那次，方向字段胜出；覆盖相同取最新的；
  价格字段(symbol/close/priceDate)始终取最新一次(收盘价会随盘中更新)；评分规则版本变了(当天部署了新规则)，新的整体胜出。
"""
import json
import os
import sys

import history_store as hs

CONTRACT_KEYS = {"sep": "systems_sep", "may": "systems_may", "jan": "systems_jan"}
PRICE_FIELDS = ("symbol", "close", "priceDate", "dataGeneratedAt")      # 始终取最新一次；其余(含v)属于"方向"，跟着覆盖最完整的那次走


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def build_point(snap, c):
    """单个合约的快照 → 历史点。基本面(仅供需)没有方向(数据不足)时返回(None, 原因)——不拿别的东西凑。"""
    if c.get("error"):
        return None, f"页面计算出错: {c['error']}"
    f = c.get("fund") or {}
    if f.get("ratio") is None or not f.get("direction"):
        return None, "基本面(仅供需票)数据不足，没有方向"
    st = c.get("structure") or {}
    comp = c.get("composite") or {}
    x = {
        "fundDir": f.get("direction"), "fundN": f.get("n"),
        "structDir": st.get("direction"), "structRatio": _r(st.get("ratio")), "structN": st.get("n"), "structThin": bool(st.get("thin")),
        "structItems": st.get("items") or [],
        "compDir": comp.get("direction"), "compRatio": _r(comp.get("ratio")), "compN": comp.get("n"),
        "tech": c.get("tech"), "foreign": c.get("foreign"),
        "quality": _r(c.get("quality")), "confidence": c.get("confidence"), "vpStatus": c.get("vpStatus"),
        "missing": c.get("missing") or [],
        "symbol": c.get("symbol"), "close": c.get("close"), "priceDate": c.get("priceDate"), "inWindow": c.get("inWindow"),
        "scoringVersion": snap.get("scoringVersion"), "tradingDay": snap.get("tradingDay"),
        "dataGeneratedAt": snap.get("dataGeneratedAt"), "failures": len(snap.get("fetchFailures") or []),
    }
    return {"d": snap["date"], "v": _r(f["ratio"]), "x": x}, None


def coverage(pt):
    x = pt["x"]
    return (x.get("fundN") or 0) + (x.get("structN") or 0)


def merge_same_day(old, new):
    """同一天已有记录old和新记录new的合并(见模块说明)。返回(合并后的点, 说明)。"""
    if old is None:
        return new, "新增"
    ox, nx = old.get("x", {}), new["x"]
    if ox.get("scoringVersion") != nx.get("scoringVersion"):
        return new, f"评分规则版本变了({ox.get('scoringVersion')}→{nx.get('scoringVersion')})，新的整体胜出"
    if coverage(new) >= coverage(old):
        return new, "覆盖不低于已有记录，方向取最新一次"
    merged = {"d": old["d"], "v": old["v"], "x": dict(ox)}           # 方向沿用覆盖更完整的旧记录
    for k in PRICE_FIELDS:
        if nx.get(k) is not None:
            merged["x"][k] = nx[k]                                    # 价格字段始终取最新
    return merged, f"新一次覆盖更少({coverage(new)}<{coverage(old)})：保留之前的方向，只更新价格"


def ingest_snapshot(snap, base_dir=None):
    """把一份快照写进三个合约的历史序列。返回{"recorded":[...],"skipped":{合约:原因},"notes":{合约:说明}}。"""
    report = {"recorded": [], "skipped": {}, "notes": {}}
    for c in snap.get("contracts", []):
        key = CONTRACT_KEYS.get(c.get("contract"))
        if key is None:
            continue
        pt, why = build_point(snap, c)
        if pt is None:
            report["skipped"][c.get("contract")] = why
            continue
        series = hs.load_series(key, base_dir)
        old = next((p for p in series["points"] if p["d"] == pt["d"]), None)
        final, note = merge_same_day(old, pt)
        _s, changed = hs.record_points(key, [final], base_dir)
        report["notes"][c["contract"]] = note
        if changed:
            report["recorded"].append(key)
    return report


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("用法: python3 record_systems.py <snapshot.json>", file=sys.stderr)
        return 2
    if not os.path.exists(argv[0]):
        print(f"[记录失败] 找不到快照文件 {argv[0]}(快照步骤可能失败了)", file=sys.stderr)
        return 1
    with open(argv[0], encoding="utf-8") as f:
        snap = json.load(f)
    rep = ingest_snapshot(snap)
    print(f"[记录] {snap.get('date')} 评分规则{snap.get('scoringVersion')}：写入{len(rep['recorded'])}个序列"
          + (f"；跳过{len(rep['skipped'])}个({'; '.join(f'{k}:{v}' for k, v in rep['skipped'].items())})" if rep["skipped"] else ""))
    for k, v in rep["notes"].items():
        print(f"   {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
