# -*- coding: utf-8 -*-
"""Mysteel《全国豆粕价格日报》摘要解析(v101.16)。纯函数、不联网。
数据来源：search.mysteel.com 的文章搜索接口(searchArticle)，query=全国豆粕价格日报，每个交易日一篇，摘要(content)里写各地43%豆粕现货价、涨跌，
有时还写 Mysteel 自己公布的各地"基差"(= 当地现货价 − 主力合约收盘价，2026-10-09 实测：江苏 3340 − M2701 收盘 3402 = −62，与公布的 −62 吻合)。
★摘要措辞每天不一样：有些天只写涨跌不写价格，有些天写成"3300-3310区间"。读不出确切数字就返回缺失，**绝不猜**；
  价格必须在 2000~6000、基差必须在 ±500，否则丢弃。并列写法按位置对应，名字个数与数字个数对不上就一个都不取。"""
import re

REGIONS = ["辽宁", "天津", "山东", "江苏", "广东"]
_PY = {"辽宁": "ln", "天津": "tj", "山东": "sd", "江苏": "js", "广东": "gd"}
_NAME = "(?:" + "|".join(REGIONS) + ")"
_GROUP = re.compile(r"(?:%s(?:地区)?[、与和及]?)+" % _NAME)
_PRICE_RUN = re.compile(r"(?<![\d.])(\d{4})(?:[、,]\d{4})*(?![\d])")
_FILLER_MAX = 16
PRICE_RANGE = (2000, 6000)
BASIS_ABS_MAX = 500


def _names(g):
    return re.findall(_NAME, g)


def _price_in(text):
    """text = 一个'名字组'后面到下一个名字组之前的文字。返回 [价格...] 或 None。"""
    m = _PRICE_RUN.search(text)
    if not m or m.start() > _FILLER_MAX:
        return None
    before, after = text[:m.start()], text[m.start():]
    if "区间" in before or re.search(r"\d{4}\s*[-－—~至]\s*$", before) or re.match(r"\d{4}(?:[、,]\d{4})*\s*[-－—~至]\s*\d{4}", after):
        return None                                          # 区间/范围，不是确切价格
    return [int(x) for x in re.findall(r"\d{4}", m.group(0))]


def _assign(names, nums):
    if not nums:
        return {}
    if len(nums) == len(names):
        return dict(zip(names, nums))
    if len(nums) == 1:                                       # '山东、广东涨10元至3310元'、'江苏与广东均为3270元'：共用一个数
        return {n: nums[0] for n in names}
    return {}


def _signed_in(text):
    m = re.match(r"(?:基差)?(?:均为|为|报)?(-?\d{1,3})(?![\d元点%])", text)
    return int(m.group(1)) if m else None


def parse_meal_daily(content):
    out = {"price": {}, "basis": {}}
    t = str(content or "")
    if not t:
        return out
    # —— 43%豆粕价格：只读"高蛋白/基差/价差"之前的部分
    cut = [t.find(k) for k in ("高蛋白", "基差", "价差") if t.find(k) >= 0]
    ptxt = t[:min(cut)] if cut else t
    for clause in re.split(r"[；;]", ptxt):
        gs = list(_GROUP.finditer(clause))
        for i, g in enumerate(gs):
            rest = clause[g.end(): gs[i + 1].start() if i + 1 < len(gs) else len(clause)]
            nums = _price_in(rest)
            if nums is None:
                continue
            for n, v in _assign(_names(g.group(0)), nums).items():
                if PRICE_RANGE[0] <= v <= PRICE_RANGE[1] and n not in out["price"]:
                    out["price"][n] = v
    # —— 基差：只读含"基差"的那一句
    bi = t.find("基差")
    if bi >= 0:
        btxt = t[bi:].split("。")[0]
        gs = list(_GROUP.finditer(btxt))
        for i, g in enumerate(gs):
            rest = btxt[g.end(): gs[i + 1].start() if i + 1 < len(gs) else len(btxt)]
            v = _signed_in(rest)
            if v is None or abs(v) > BASIS_ABS_MAX:
                continue
            for n in _names(g.group(0)):
                out["basis"].setdefault(n, v)
    return out


def is_daily_report(item):
    return "全国豆粕价格日报" in str((item or {}).get("title") or "")


def article_date(item):
    it = item or {}
    m = re.search(r"[（(](\d{4})(\d{2})(\d{2})[）)]", str(it.get("title") or ""))
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(it.get("publishTime") or ""))
    return m.group(1) if m else None


def build_rows(items):
    """搜索结果 → (按日期排序去重的行, 报告)。同一天多篇：取解析出字段更多的(并列取发布更晚的)。"""
    best, skipped = {}, 0
    for it in items or []:
        if not isinstance(it, dict) or not is_daily_report(it):
            skipped += 1
            continue
        d = article_date(it)
        if not d:
            skipped += 1
            continue
        p = parse_meal_daily(it.get("content"))
        score = (len(p["price"]) + len(p["basis"]), str(it.get("publishTime") or ""))
        if d not in best or score > best[d][0]:
            best[d] = (score, it, p)
    rows = []
    for d in sorted(best):
        _, it, p = best[d]
        row = {"date": d}
        for r in REGIONS:
            row[_PY[r] + "_price"] = p["price"].get(r)
            row[_PY[r] + "_basis"] = p["basis"].get(r)
        row["publishTime"] = it.get("publishTime")
        row["url"] = it.get("url")
        rows.append(row)
    by_year = {}
    for r in rows:
        by_year[r["date"][:4]] = by_year.get(r["date"][:4], 0) + 1
    rep = {"days": len(rows), "first": rows[0]["date"] if rows else None, "last": rows[-1]["date"] if rows else None,
           "jsPriceDays": sum(1 for r in rows if r["js_price"] is not None), "jsBasisDays": sum(1 for r in rows if r["js_basis"] is not None),
           "skippedNotDaily": skipped, "daysByYear": by_year}
    return rows, rep
