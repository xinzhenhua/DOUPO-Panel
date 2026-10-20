# -*- coding: utf-8 -*-
"""橡胶指标全自动抓取（v102.3）：隆众(Mysteel)文章 → data/ru_ind_auto.json（页面橡胶视图只读这个文件，没有手动录入）

五类来源（都走 search.mysteel.com/searchapi/search/searchArticle 取列表；青岛库存和社会库存还要点进正文取细项）：
  stock  《中国天然橡胶社会库存周数据分析（日期）》  → stk 社会总库存 / dark 深色胶 / light 浅色胶（深+浅=总，缺哪项用公式算）   [ru_stock.py]
  qd     《青岛地区天然橡胶样本库存和出入库率周数据分析（日期）》→ qd 合计库存(万吨) qdb 保税区 qdg 一般贸易；
                                 qin/qout 一般贸易仓库入/出库率「周变化」(百分点)，qinb/qoutb 保税仓库同
  prod   《全球天然橡胶产量月数据统计（YYYY年M月）》  → prod 当月产量(万吨,ANRPC预测) prodM 当月同比% prodY 累计同比%（信号用）
  imp    《中国天然橡胶进口量月数据统计(YYYY年M月)》 → imp 进口量(万吨,海关终值) impM 当月同比% impY 累计同比%（信号用）
                                 ★标题或正文带「预估」的整篇丢弃，只要海关终值
  tire   《中国轮胎产能利用率周数据统计（起-止）》   → qg 全钢胎 bg 半钢胎 产能利用率%；qgY/bgY 同比(百分点)
统计日 d：周数据=正文「截至」日(周日)/周期止日(周四)；月数据=文章发布日（可用信息的日期，避免回测偷看），另存 m=统计月份。
纯函数 parse_* 不联网；联网失败不抛异常、不覆盖旧文件。
用法：python3 ru_ind.py                 # 增量：近 70 天
      python3 ru_ind.py --years 6       # 回填
      python3 ru_ind.py --no-bodies     # 不点正文（社会库存/青岛库存只有总数）"""
import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import ru_stock as RS

OUT = RS.OUT
RANGES = {"qd": (20, 150), "qdb": (0, 80), "qdg": (10, 140), "prod": (20, 250), "imp": (5, 150), "qg": (0, 100), "bg": (0, 100)}
MONTHLY = {"prod", "prodY", "prodM", "imp", "impY", "impM"}   # 带 m(统计月份)的序列：同月只留最新一篇


def _norm(t):
    """去空白；全角标点统一成半角（正文空格/换行位置不稳定）。"""
    t = re.sub(r"\s+", "", str(t or ""))
    return t.translate(str.maketrans({"，": ",", "；": ";", "：": ":", "（": "(", "）": ")", "－": "-", "—": "-", "–": "-", "﹣": "-"}))


def _sgn(word):
    w = word or ""
    if any(x in w for x in ("增", "升", "涨", "提高", "+")):
        return 1
    if any(x in w for x in ("减", "降", "跌", "下", "-")):
        return -1
    return 0


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _in(k, v):
    if v is None:
        return None
    lo, hi = RANGES.get(k, (-1e9, 1e9))
    return v if lo <= v <= hi else None


# ----------------------------------------------------------------------------- 解析（纯函数）
def parse_qd(text):
    """青岛样本库存和出入库率周报。读不到的项为 None。入/出库率给的是「较上期变化(百分点)」，不是水平值。"""
    t = _norm(text)
    out = {"d": None, "qd": None, "qdb": None, "qdg": None, "qin": None, "qout": None, "qinb": None, "qoutb": None}
    m = re.search(r"截至(20\d{2})年(\d{1,2})月(\d{1,2})日", t)
    if m:
        try:
            out["d"] = date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    m = re.search(r"合计库存量?(\d+(?:\.\d+)?)万吨", t)
    if m:
        out["qd"] = _in("qd", _f(m.group(1)))
    m = re.search(r"保税区库存(?:量)?(\d+(?:\.\d+)?)万吨", t)
    if m:
        out["qdb"] = _in("qdb", _f(m.group(1)))
    m = re.search(r"一般贸易库存(?:量)?(\d+(?:\.\d+)?)万吨", t)
    if m:
        out["qdg"] = _in("qdg", _f(m.group(1)))
    ib = re.search(r"保税(?:仓库|区)?入库率", t)
    ig = re.search(r"一般贸易(?:仓库)?入库率", t)
    segb = t[ib.start(): (ig.start() if ig and ig.start() > ib.start() else ib.start() + 90)] if ib else ""
    segg = t[ig.start(): ig.start() + 90] if ig else ""

    def chg(seg, name):
        mm = re.search(name + r"(增加|减少|上升|下降|降低|提高|增|降|持平)(?:了)?(\d+(?:\.\d+)?)?个?百分点", seg)
        if not mm:
            mm0 = re.search(name + r"持平", seg)
            return 0.0 if mm0 else None
        if mm.group(1) == "持平":
            return 0.0
        v = _f(mm.group(2))
        return None if v is None else round(_sgn(mm.group(1)) * v, 2)
    out["qinb"], out["qoutb"] = chg(segb, "入库率"), chg(segb, "出库率")
    out["qin"], out["qout"] = chg(segg, "入库率"), chg(segg, "出库率")
    return out


def complete_parts(total, a, b, tol=0.15):
    """total = a + b（青岛合计=保税+一般贸易）。返回 (total,a,b,calc[],warn)。三个都有但对不上：以合计为准，b = total − a。"""
    calc, warn = [], ""
    if total is not None and a is not None and b is not None:
        if abs(a + b - total) > tol:
            warn = "保税%.2f+一般贸易%.2f=%.2f 与合计%.2f 差 %.2f，一般贸易改为 合计−保税" % (a, b, a + b, total, a + b - total)
            b = round(total - a, 2); calc.append("b")
    elif total is not None and a is not None:
        b = round(total - a, 2); calc.append("b")
    elif total is not None and b is not None:
        a = round(total - b, 2); calc.append("a")
    elif a is not None and b is not None:
        total = round(a + b, 2); calc.append("t")
    return total, a, b, calc, warn


def parse_prod(text):
    """ANRPC 月度产量(隆众转述，是预测值)。prodY=累计同比(信号用)：有「前N个月/上半年/第一季度 累计产量料增降X%」用它；
    12月用全年同比；1月累计=当月；都没有退回当月同比。"""
    t = _norm(text)
    out = {"mon": None, "prod": None, "prodM": None, "prodY": None}
    m = re.search(r"(\d{1,2})月全球天胶产量料(增|降|增加|下降|减少)(\d+(?:\.\d+)?)%至(\d+(?:\.\d+)?)万吨", t)
    if m:
        out["mon"] = int(m.group(1))
        out["prod"] = _in("prod", _f(m.group(4)))
        out["prodM"] = round(_sgn(m.group(2)) * _f(m.group(3)), 2)
    cum = re.search(r"累计产量料(增|降|增加|下降|减少)(\d+(?:\.\d+)?)%至(\d+(?:\.\d+)?)万吨", t)
    if cum:
        out["prodY"] = round(_sgn(cum.group(1)) * _f(cum.group(2)), 2)
    else:
        ann = re.search(r"(20\d{2})年全球天胶产量料同比(增加|减少|下降|增|降)(\d+(?:\.\d+)?)%", t)
        if out["mon"] == 12 and ann:
            out["prodY"] = round(_sgn(ann.group(2)) * _f(ann.group(3)), 2)
        elif out["mon"] == 1:
            out["prodY"] = out["prodM"]
    if out["prodY"] is None:
        out["prodY"] = out["prodM"]
    return out


def parse_imp(text, title=""):
    """中国天然橡胶进口量(海关终值)。预估文章返回 (None, 原因)。impY=累计同比(信号用，没有就用当月同比)。"""
    t = _norm(text)
    if "预估" in str(title) or "预估" in t:
        return None, "预估值，丢弃"
    m = re.search(r"(20\d{2})年(\d{1,2})月中国天然橡胶(?:\([^)]*\))?进口量(\d+(?:\.\d+)?)万吨(?:,环比(增加|减少|持平)(\d+(?:\.\d+)?)?%?)?(?:,同比(增加|减少|持平)(\d+(?:\.\d+)?)?%?)?", t)
    if not m:
        return None, "没找到『X年X月中国天然橡胶…进口量X万吨』"
    v = _in("imp", _f(m.group(3)))
    if v is None:
        return None, "进口量不在合理范围"
    out = {"y": int(m.group(1)), "mon": int(m.group(2)), "imp": v, "impM": None, "impY": None}
    if m.group(6):
        out["impM"] = 0.0 if m.group(6) == "持平" or m.group(7) is None else round(_sgn(m.group(6)) * _f(m.group(7)), 2)
    c = re.search(r"累计进口数量(\d+(?:\.\d+)?)万吨,累计同比(增加|减少|持平)(\d+(?:\.\d+)?)?%", t)
    if c:
        out["impY"] = 0.0 if c.group(2) == "持平" or c.group(3) is None else round(_sgn(c.group(2)) * _f(c.group(3)), 2)
    if out["impY"] is None:
        out["impY"] = out["impM"]
    return out, ""


def parse_tire(text):
    """轮胎样本企业产能利用率(周)：半钢/全钢 水平%、环比(百分点)、同比(百分点)。"""
    t = _norm(text)
    out = {}
    for key, name in (("bg", "半钢"), ("qg", "全钢")):
        m = re.search(name + r"(?:轮胎|胎)样本企业产能利用率为(\d+(?:\.\d+)?)%,环比([+-]?\d+(?:\.\d+)?)个百分点,同比([+-]?\d+(?:\.\d+)?)%?个百分点", t)
        if m:
            out[key] = _in(key, _f(m.group(1)))
            out[key + "H"] = _f(m.group(2))
            out[key + "Y"] = _f(m.group(3))
    return out


def tire_end_date(title):
    m = re.search(r"(20\d{2})(\d{2})(\d{2})-(\d{2})(\d{2})", str(title))
    if not m:
        return None
    y, m1, d1, m2, d2 = (int(x) for x in m.groups())
    try:
        return date(y + (1 if m2 < m1 else 0), m2, d2).isoformat()
    except ValueError:
        return None


def title_ym(title):
    m = re.search(r"(20\d{2})年(\d{1,2})月", str(title))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _pub_date(item):
    s = str(item.get("publishTime") or "")[:10]
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        return None


# ----------------------------------------------------------------------------- 存储
def put(store, k, d, v, m=None):
    """写一个点。月度序列按 m(统计月份) 去重（同月只留最新发布日的）。返回是否变化。"""
    if v is None:
        return False
    ls = store.setdefault(k, [])
    if m and k in MONTHLY:
        old = [p for p in ls if p.get("m") == m]
        if old and old[0]["d"] > d:
            return False
        ls[:] = [p for p in ls if p.get("m") != m]
        ls.append({"d": d, "v": round(v, 3), "m": m})
        ls.sort(key=lambda p: p["d"])
        return True
    cur = next((p for p in ls if p["d"] == d), None)
    if cur is None:
        ls.append({"d": d, "v": round(v, 3)}); ls.sort(key=lambda p: p["d"]); return True
    if abs(cur["v"] - v) > 1e-9:
        cur["v"] = round(v, 3); return True
    return False


def _tag(store, d, names, calc):
    old = [x for x in store.get("calc", []) if not any(x == "%s:%s" % (d, n) for n in names)]
    store["calc"] = sorted(set(old) | {"%s:%s" % (d, n) for n in calc})


# ----------------------------------------------------------------------------- 各来源：一篇文章 → store
def apply_qd(store, key, item, fetch_text, use_body):
    url = item.get("url") or ""
    snip = parse_qd(item.get("content"))
    body = None
    if use_body and url:
        raw, _ = fetch_text(url)
        if raw:
            body = parse_qd(RS.html_to_text(raw))
    p = dict(snip)
    if body:
        for k, v in body.items():
            if v is not None:
                p[k] = v
    d = p["d"] or key
    t, b, g, calc, warn = complete_parts(p["qd"], p["qdb"], p["qdg"])
    if t is None:
        return "fail", "没读到青岛合计库存"
    for k, v in (("qd", t), ("qdb", b), ("qdg", g), ("qin", p["qin"]), ("qout", p["qout"]), ("qinb", p["qinb"]), ("qoutb", p["qoutb"])):
        put(store, k, d, v)
    _tag(store, d, ("qd", "qdb", "qdg"), [{"a": "qdb", "b": "qdg", "t": "qd"}[c] for c in calc])
    if warn:
        store.setdefault("warn", []).append("%s 青岛 %s" % (d, warn))
    fmt = lambda x: "—" if x is None else ("%g" % x)
    return "ok", "合计%s 保税%s 一般贸易%s | 一般贸易入库率变化%s 出库率变化%s | 保税入%s 出%s%s%s" % (
        fmt(t), fmt(b), fmt(g), fmt(p["qin"]), fmt(p["qout"]), fmt(p["qinb"]), fmt(p["qoutb"]),
        "（算出：%s）" % ",".join(calc) if calc else "", "" if body else "；仅摘要") + ("；⚠" + warn if warn else "")


def apply_prod(store, key, item, fetch_text, use_body):
    ym = title_ym(item.get("title"))
    p = parse_prod(item.get("content"))
    if not ym or p["prod"] is None:
        return "fail", "没读到当月产量"
    if p["mon"] is not None and p["mon"] != ym[1]:
        return "fail", "正文月份 %s 与标题月份 %s 不一致" % (p["mon"], ym[1])
    d, m = _pub_date(item), "%04d-%02d" % ym
    if not d:
        return "fail", "没有发布日期"
    put(store, "prod", d, p["prod"], m); put(store, "prodY", d, p["prodY"], m); put(store, "prodM", d, p["prodM"], m)
    return "ok", "%s 产量%g万吨 当月同比%s%% 累计同比%s%%" % (m, p["prod"], p["prodM"], p["prodY"])


def apply_imp(store, key, item, fetch_text, use_body):
    ym = title_ym(item.get("title"))
    p, why = parse_imp(item.get("content"), item.get("title"))
    if p is None:
        return ("skip" if "预估" in why else "fail"), why
    if ym and (p["y"], p["mon"]) != ym:
        return "fail", "正文月份 %s-%s 与标题 %s-%s 不一致" % (p["y"], p["mon"], ym[0], ym[1])
    d, m = _pub_date(item), "%04d-%02d" % (p["y"], p["mon"])
    if not d:
        return "fail", "没有发布日期"
    put(store, "imp", d, p["imp"], m); put(store, "impY", d, p["impY"], m); put(store, "impM", d, p["impM"], m)
    return "ok", "%s 进口%g万吨 当月同比%s%% 累计同比%s%%" % (m, p["imp"], p["impM"], p["impY"])


def apply_tire(store, key, item, fetch_text, use_body):
    d = tire_end_date(item.get("title"))
    p = parse_tire(item.get("content"))
    if not d or "qg" not in p or "bg" not in p or p["qg"] is None or p["bg"] is None:
        return "fail", "没读到全钢/半钢产能利用率"
    for k in ("qg", "bg"):
        put(store, k, d, p[k]); put(store, k + "Y", d, p.get(k + "Y"))
    return "ok", "全钢%g%%(环比%+g,同比%+g点) 半钢%g%%(环比%+g,同比%+g点)" % (p["qg"], p["qgH"], p["qgY"], p["bg"], p["bgH"], p["bgY"])


def _key_week(title):
    m = re.search(r"[(（]\s*(20\d{2})(\d{2})(\d{2})\s*[)）]", str(title))
    return "%s-%s-%s" % m.groups() if m else None


def _key_ym(title):
    ym = title_ym(title)
    return "%04d-%02d" % ym if ym else None


SOURCES = [
    {"id": "qd", "label": "青岛库存/出入库率", "query": "青岛地区天然橡胶样本库存和出入库率周数据分析", "title_ok": re.compile(r"青岛.*库存和出入库率周数据"), "key": _key_week, "apply": apply_qd, "body": True},
    {"id": "prod", "label": "全球产量", "query": "全球天然橡胶产量月数据统计", "title_ok": re.compile(r"全球天然橡胶产量月数据统计"), "key": _key_ym, "apply": apply_prod, "body": False},
    {"id": "imp", "label": "进口量", "query": "中国天然橡胶进口量月数据统计", "title_ok": re.compile(r"进口量月数据统计"), "key": _key_ym, "apply": apply_imp, "body": False},
    {"id": "tire", "label": "轮胎产能利用率", "query": "中国轮胎产能利用率周数据统计", "title_ok": re.compile(r"轮胎产能利用率周数据统计"), "key": lambda t: tire_end_date(t), "apply": apply_tire, "body": False},
]


def pick(items, src):
    """按 key 分组，同一期多篇取发布最晚的。返回 {key: item}"""
    best = {}
    for it in items:
        title = str(it.get("title") or "")
        if not src["title_ok"].search(title):
            continue
        k = src["key"](title)
        if not k:
            continue
        cur = best.get(k)
        if cur is None or str(it.get("publishTime") or "") > str(cur.get("publishTime") or ""):
            best[k] = it
    return best


def windows(years, days, today):
    if years and years > 0:
        w, end = [], today
        for _ in range(int(years * 2)):
            w.append((end - timedelta(days=182), end)); end = end - timedelta(days=183)
        return w
    return [(today - timedelta(days=days), today)]


def run(years=0, days=70, use_body=True, out=OUT, fetch_json=None, fetch_text=None, today=None, sleep=0.6, only=None):
    if fetch_json is None or fetch_text is None:
        import fetch_data as fd
        fetch_json = fetch_json or fd.fetch_json_debug
        fetch_text = fetch_text or (lambda u: fd.fetch_text_debug(u, headers={"Referer": "https://nenghua.mysteel.com/"}))
    today = today or (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    store = RS.load(out)
    log, stats = [], {}
    wins = windows(years, days, today)

    def bump(src, st):
        s = stats.setdefault(src, {"ok": 0, "fail": 0, "skip": 0, "listFail": 0}); s[st] = s.get(st, 0) + 1

    # ① 社会库存（ru_stock：深色/浅色走正文，公式补缺）
    if not only or "stock" in only:
        for (a, b) in wins:
            items, why = RS.search_window(a, b, fetch_json)
            if why:
                bump("stock", "listFail"); log.append("[社会库存] 窗口 %s~%s：%s" % (a, b, why))
            arts = RS.pick_articles(items)
            log.append("[社会库存] 窗口 %s~%s：列表 %d 条，周报 %d 篇" % (a, b, len(items), len(arts)))
            for td in sorted(arts, reverse=True):
                if not years:
                    old = (today - date.fromisoformat(td)).days > 28 and any(p["d"] == td for p in store.get("stk", []))
                    done = RS.complete(store, td) and td not in {x.split(":")[0] for x in store.get("calc", [])}
                    if old or done:
                        bump("stock", "skip"); continue
                st, msg = RS.process_article(store, td, arts[td], fetch_text, use_body)
                bump("stock", st); log.append("  [社会库存] %s %s %s" % (td, st, msg)); time.sleep(sleep)
    # ②~⑤ 其余四类
    for src in SOURCES:
        if only and src["id"] not in only:
            continue
        for (a, b) in wins:
            items, why = RS.search_window(a, b, fetch_json, query=src["query"])
            if why:
                bump(src["id"], "listFail"); log.append("[%s] 窗口 %s~%s：%s" % (src["label"], a, b, why))
            arts = pick(items, src)
            log.append("[%s] 窗口 %s~%s：列表 %d 条，有效文章 %d 篇" % (src["label"], a, b, len(items), len(arts)))
            for k in sorted(arts, reverse=True):
                ub = use_body and src["body"]
                if ub and not years:        # 增量：四周前的、或细项已齐的青岛周报不再点正文
                    try:
                        age = (today - date.fromisoformat(k)).days
                    except ValueError:
                        age = 0
                    have = all(any(p["d"] == k for p in store.get(x, [])) for x in ("qd", "qdb", "qdg", "qin", "qout"))
                    if age > 28 or have:
                        ub = False
                        if any(p["d"] == k for p in store.get("qd", [])):
                            bump(src["id"], "skip"); continue
                st, msg = src["apply"](store, k, arts[k], fetch_text, ub)
                bump(src["id"], st); log.append("  [%s] %s %s %s" % (src["label"], k, st, msg))
                if ub:
                    time.sleep(sleep)
    if any(isinstance(v, list) and v for v in store.values()):
        store["updated"] = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
        store["calc"] = sorted(set(store.get("calc", [])))
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, separators=(",", ":"))
    return store, stats, log


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=0)
    ap.add_argument("--days", type=int, default=70)
    ap.add_argument("--no-bodies", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    only = {x.strip() for x in a.only.split(",") if x.strip()} or None
    store, stats, log = run(years=a.years, days=a.days, use_body=not a.no_bodies, out=a.out, only=only)
    print("\n".join("[RU指标] " + x for x in log))
    n = {k: len(v) for k, v in store.items() if isinstance(v, list) and v and isinstance(v[0], dict)}
    print("[RU指标] 结果 %s" % json.dumps(stats, ensure_ascii=False))
    print("[RU指标] 各序列点数 %s；算出 %d 项，警告 %d 条" % (json.dumps(n, ensure_ascii=False), len(store.get("calc", [])), len(store.get("warn", []))))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print("[RU指标] 失败：%s: %s" % (type(e).__name__, str(e)[:200])); sys.exit(0)
