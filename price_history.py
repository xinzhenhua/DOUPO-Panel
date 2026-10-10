"""价格位置补历史(v101.19)。
问题：新上市的合约(1月合约约173根、9月合约十几根)自己的历史不够算"近1年百分位"。
做法：用其他合约在"重叠交易日"上的收盘价比值(取中位数，抗个别异常日)把它们的历史按比例换算成本合约的价位，补在前面——
      就是期货连续合约常用的"比例后复权"。换算后的前史不是本合约真实成交价(含月间价差被固定比例吸收)，页面会标出"其中N日为换算"。
只借用本合约上市日之前的日期；多个候选里选前史最长的；重叠日不足min_overlap的不用。
"""
from statistics import median


def extend_closes(own, donors, target=260, min_overlap=3, ratio_days=20):
    """own: [(date, close)] 升序；donors: {名称: [(date, close)]}。返回 {closes, ownCount, extendedCount, donor}。"""
    own = [(d, c) for d, c in own if c is not None]
    if not own:
        return {"closes": [], "ownCount": 0, "extendedCount": 0, "donor": None}
    need = target - len(own)
    base = {"closes": [c for _, c in own][-target:], "ownCount": min(len(own), target), "extendedCount": 0, "donor": None}
    if need <= 0:
        return base
    own_map = dict(own)
    first = own[0][0]
    best = None
    for name, series in donors.items():
        dmap = {d: c for d, c in series if c}
        overlap = [d for d in sorted(own_map) if d in dmap]
        if len(overlap) < min_overlap:
            continue
        ratio = median(own_map[d] / dmap[d] for d in overlap[:ratio_days])
        pre = [(d, dmap[d] * ratio) for d in sorted(dmap) if d < first]
        if pre and (best is None or len(pre) > len(best[1])):
            best = (name, pre)
    if best is None:
        return base
    pre = best[1][-need:]
    closes = [round(c, 2) for _, c in pre] + [c for _, c in own]
    return {"closes": closes[-target:], "ownCount": len(own), "extendedCount": len(pre), "donor": best[0]}
