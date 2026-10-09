# -*- coding: utf-8 -*-
"""大商所"日成交持仓排名"文本文件解析 + 席位净持仓(龙虎榜回填用，v101.13)。纯函数、不联网。
文件格式(用户从大商所下载的txt)：首行 `大连商品交易所_日成交持仓排名_YYYYMMDD`，第2行表头，之后每行12列(制表符)：
  1-4 成交量榜(名次/会员/成交量/增减)，5-8 持买榜，9-12 持卖榜；最后一行'合计'不算。数字带千分位逗号和尾随空格。
净持仓口径与线上一致(2026-09-30 对账过)：净 = 持买 − 持卖，变化 = 持买增减 − 持卖增减；
某席位只进了一边的前20：另一边用该榜第20名的数值/增减顶替(净持仓是下限估计，approx=True)；两边都没进：None(不记0)；榜单不足20行：不估计。"""
import re

TOP_N = 20
_DATE_RE = re.compile(r"日成交持仓排名[_\s]*(\d{8})")


def _num(s):
    s = (s or "").replace(",", "").replace(" ", "").replace("　", "").strip()
    if not re.fullmatch(r"[+-]?\d+", s):
        raise ValueError(f"不是整数: {s!r}")
    return int(s)


def _base(name):
    """'高盛期货（代客）' → '高盛期货'"""
    return re.split(r"[（(]", (name or "").strip(), maxsplit=1)[0].strip()


def parse_rank_text(text):
    lines = [l for l in (text or "").replace("\r", "").split("\n") if l.strip()]
    if not lines:
        raise ValueError("空文件")
    m = _DATE_RE.search(lines[0])
    if not m:
        raise ValueError("首行找不到'日成交持仓排名_YYYYMMDD'")
    ds = m.group(1)
    out = {"date": f"{ds[:4]}-{ds[4:6]}-{ds[6:]}", "buy": [], "sell": []}
    for l in lines[1:]:
        c = [x.strip() for x in l.split("\t")]
        if len(c) < 12 or not c[0].isdigit():
            continue                      # 表头、合计行
        try:
            out["buy"].append({"rank": _num(c[4]), "name": c[5], "value": _num(c[6]), "change": _num(c[7])})
            out["sell"].append({"rank": _num(c[8]), "name": c[9], "value": _num(c[10]), "change": _num(c[11])})
        except ValueError:
            raise ValueError(f"数据行解析失败: {l[:60]!r}")
    if not out["buy"] and not out["sell"]:
        raise ValueError("没有任何排名数据行")
    return out


def _find(rows, name):
    for r in rows:
        if _base(r["name"]) == name:
            return r
    return None


def member_net(parsed, name):
    b, s = _find(parsed["buy"], name), _find(parsed["sell"], name)
    if b is None and s is None:
        return None
    approx = False
    if b is None:
        if len(parsed["buy"]) < TOP_N:
            return None
        b, approx = parsed["buy"][TOP_N - 1], True
    if s is None:
        if len(parsed["sell"]) < TOP_N:
            return None
        s, approx = parsed["sell"][TOP_N - 1], True
    return {"net": b["value"] - s["value"], "change": b["change"] - s["change"], "approx": approx}
