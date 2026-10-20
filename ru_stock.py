# -*- coding: utf-8 -*-
"""橡胶库存自动化（v102.2）：隆众(Mysteel)《中国天然橡胶社会库存周数据分析（YYYYMMDD）》→ data/ru_ind_auto.json

两步走：①搜索接口 searchArticle 取文章列表（列表里只有「社会总库存」）；②点进正文页取「深色胶/浅色胶」。
公式：深色胶 + 浅色胶 = 社会总库存。正文缺哪一项（浅色胶最常被截断/改版），就用这条公式算出来，并记进 calc。
三个数都读到了但对不上（差 > 0.3 万吨）：以总库存为准，浅色 = 总 − 深色，记进 warn（深色是正文里写得最稳的一项）。

输出（按列，每项 [{d:"截至日",v:万吨}] 升序）：
  {"stk":[…], "dark":[…], "light":[…], "calc":["2026-10-11:light"], "warn":["…"], "src":{"2026-10-11":"url"}, "updated":"…"}
统计日 d = 正文「截至 YYYY年M月D日」（周日）。页面把它当"统计日"，和手动录入同一口径。
纯函数（parse_*）不联网，供测试；联网部分失败不抛异常、不覆盖旧文件。
用法：python3 ru_stock.py                # 增量：近 70 天
      python3 ru_stock.py --years 6      # 回填 6 年（按半年窗口翻页）
      python3 ru_stock.py --no-bodies    # 只用列表摘要（只有总库存）"""
import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

OUT = "data/ru_ind_auto.json"
SEARCH_URL = "https://search.mysteel.com/searchapi/search/searchArticle"
QUERY = "中国天然橡胶社会库存周数据分析"
TOL = 0.3          # 三个数的加总容差（万吨）。样本里 74.5+35.9=110.4 恰好等；四舍五入最多差 0.1，留余量
RANGE = {"stk": (60, 220), "dark": (25, 170), "light": (5, 90)}   # 合理范围（万吨），超出视为解析错误

_TITLE_OK = re.compile(r"社会库存周数据分析")
_TITLE_DATE = re.compile(r"[（(]\s*(20\d{2})(\d{2})(\d{2})\s*[）)]")


def _clean(t):
    """去掉所有空白（正文里换行/空格位置不稳定），全角标点统一。"""
    return re.sub(r"\s+", "", str(t or "")).replace("，", ",").replace("：", ":")


def html_to_text(h):
    """网页 → 纯文字（去 script/style/标签，实体还原）。"""
    import html as _h
    s = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", h or "")
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return _h.unescape(s)


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_stock_text(text):
    """一篇文章(正文或列表摘要)里的 截至日 / 总库存 / 深色胶 / 浅色胶。读不到的项为 None。
    ★只认「中国…社会(总)库存」这几个固定写法，不用万能正则；浅色胶段落常常被截断（样本里就有"浅色胶社会总库存为"后面没数字），读不到就是 None。"""
    t = _clean(text)
    out = {"d": None, "stk": None, "dark": None, "light": None}
    m = re.search(r"截至(20\d{2})年(\d{1,2})月(\d{1,2})日", t)
    if m:
        try:
            out["d"] = date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    m = re.search(r"中国天然橡胶社会库存(?:总量)?(?:为|达)?(\d+(?:\.\d+)?)万吨", t)
    if m:
        out["stk"] = _num(m.group(1))
    m = re.search(r"中国深色胶社会(?:总)?库存(?:为|达)?(\d+(?:\.\d+)?)万吨", t)
    if m:
        out["dark"] = _num(m.group(1))
    m = re.search(r"中国浅色胶社会(?:总)?库存(?:为|达)?(\d+(?:\.\d+)?)万吨", t)
    if m:
        out["light"] = _num(m.group(1))
    return out


def title_date(title):
    m = _TITLE_DATE.search(title or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def reconcile(p):
    """用公式 深色+浅色=总 补全/校验。返回 (stk, dark, light, calc[list of 'dark'/'light'/'stk'], warn[str])。
    规则：
      - 范围外的数当没读到；
      - 三个都有：加总差 ≤ TOL 原样保留；否则以总库存为准，浅色 = 总 − 深色（warn）；
      - 缺一个：用另外两个算出来（calc）；
      - 只剩总库存：只记总库存（深/浅没法分，不猜）。"""
    v = {}
    for k in ("stk", "dark", "light"):
        x = p.get(k)
        lo, hi = RANGE[k]
        v[k] = x if (x is not None and lo <= x <= hi) else None
    calc, warn = [], ""
    s, d, l = v["stk"], v["dark"], v["light"]
    if s is not None and d is not None and l is not None:
        if abs(d + l - s) > TOL:
            warn = "深%.2f+浅%.2f=%.2f 与总%.2f 差 %.2f，浅色胶改为 总−深色" % (d, l, d + l, s, d + l - s)
            l = round(s - d, 2); calc.append("light")
    elif s is not None and d is not None:
        l = round(s - d, 2); calc.append("light")
    elif s is not None and l is not None:
        d = round(s - l, 2); calc.append("dark")
    elif d is not None and l is not None:
        s = round(d + l, 2); calc.append("stk")
    if l is not None and not (RANGE["light"][0] <= l <= RANGE["light"][1]):
        warn = (warn + "；" if warn else "") + "算出的浅色胶 %.2f 不在合理范围，丢弃" % l
        l = None
        if "light" in calc:
            calc.remove("light")
    if d is not None and not (RANGE["dark"][0] <= d <= RANGE["dark"][1]):
        d = None
        if "dark" in calc:
            calc.remove("dark")
    return s, d, l, calc, warn


def merge_store(store, d, s, dk, lt, calc, url=None, warn=""):
    """把一周的数并入 store（同日覆盖）；返回是否有变化。"""
    store.setdefault("stk", []); store.setdefault("dark", []); store.setdefault("light", []); store.setdefault("calc", []); store.setdefault("warn", []); store.setdefault("src", {})
    changed = False
    for k, v in (("stk", s), ("dark", dk), ("light", lt)):
        ls = store[k]
        cur = next((p for p in ls if p["d"] == d), None)
        if v is None:
            continue
        if cur is None:
            ls.append({"d": d, "v": round(v, 2)}); changed = True
        elif abs(cur["v"] - v) > 1e-9:
            cur["v"] = round(v, 2); changed = True
        ls.sort(key=lambda p: p["d"])
    tags = {"%s:%s" % (d, c) for c in calc}
    store["calc"] = sorted((set(store["calc"]) - {x for x in store["calc"] if x.startswith(d + ":")}) | tags)
    store["warn"] = [w for w in store["warn"] if not w.startswith(d + " ")]
    if warn:
        store["warn"].append("%s %s" % (d, warn))
    if url:
        store["src"][d] = url
    return changed


def complete(store, d):
    return all(any(p["d"] == d for p in store.get(k, [])) for k in ("stk", "dark", "light"))


# ----------------------------------------------------------------------------- 联网部分
def _headers():
    return {"token": "-1", "Origin": "https://search.mysteel.com", "Referer": "https://search.mysteel.com/fastcomment.html", "X-Requested-With": "XMLHttpRequest"}


def search_window(start, end, fetch_json, page_size=20, max_pages=6):
    """一个时间窗口内的文章列表 [{title,url,publishTime,content}]；接口失败返回 (已拿到的, 原因)。"""
    items, why = [], None
    for page in range(1, max_pages + 1):
        payload = {"query": QUERY, "startTime": start.strftime("%Y-%m-%d 00:00:00"), "endTime": end.strftime("%Y-%m-%d 23:59:59"),
                   "sortType": "complex", "platform": "pc", "pageNo": page, "pageSize": page_size}
        data, dbg = fetch_json(SEARCH_URL, headers=_headers(), post_data=payload)
        if not isinstance(data, dict) or data.get("resultCode") != 0:
            why = "搜索接口无返回/异常：%s" % (str((dbg or {}).get("error") or (dbg or {}).get("rawSnippet") or "")[:120])
            break
        lst = data.get("dataList") or []
        for it in lst:
            if isinstance(it, dict):
                items.append(it)
        if len(lst) < page_size or page * page_size >= (data.get("total") or 0):
            break
    return items, why


def pick_articles(items):
    """只留标题是『社会库存周数据分析（日期）』的，按标题日期去重（同日多篇取发布最晚的）。返回 {标题日期: item}"""
    best = {}
    for it in items:
        title = str(it.get("title") or "")
        if not _TITLE_OK.search(title):
            continue
        td = title_date(title)
        if not td:
            continue
        cur = best.get(td)
        if cur is None or str(it.get("publishTime") or "") > str(cur.get("publishTime") or ""):
            best[td] = it
    return best


def process_article(store, td, item, fetch_text, use_body=True):
    """一篇文章 → 并入 store。返回 (状态, 说明)。"""
    url = item.get("url") or ""
    snippet = parse_stock_text(item.get("content"))
    body = None
    if use_body and url:
        raw, dbg = fetch_text(url)
        if raw:
            body = parse_stock_text(html_to_text(raw))
    p = {"d": None, "stk": None, "dark": None, "light": None}
    for src in (body, snippet):                      # 正文优先，摘要补
        if src:
            for k in p:
                if p[k] is None:
                    p[k] = src[k]
    d = p["d"] or td
    note = ""
    if p["d"] and p["d"] != td:
        note = "正文截至日 %s ≠ 标题日 %s，按正文" % (p["d"], td)
    s, dk, lt, calc, warn = reconcile(p)
    if s is None and dk is None and lt is None:
        return "fail", "没读到任何库存数（正文%s）" % ("已取到" if body else "没取到")
    if note:
        warn = (warn + "；" if warn else "") + note
    merge_store(store, d, s, dk, lt, calc, url, warn)
    got = "总%s 深%s 浅%s" % tuple("—" if x is None else ("%.2f" % x) for x in (s, dk, lt))
    return "ok", got + ("（算出：%s）" % ",".join(calc) if calc else "") + ("；⚠" + warn if warn else "") + ("" if body else "；仅摘要")


def load(path=OUT):
    try:
        with open(path, encoding="utf-8") as f:
            j = json.load(f)
            return j if isinstance(j, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def run(years=0, days=70, use_body=True, out=OUT, fetch_json=None, fetch_text=None, today=None, sleep=0.6):
    if fetch_json is None or fetch_text is None:
        import fetch_data as fd
        fetch_json = fetch_json or fd.fetch_json_debug
        fetch_text = fetch_text or (lambda u: fd.fetch_text_debug(u, headers={"Referer": "https://nenghua.mysteel.com/"}))
    today = today or (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    store = load(out)
    # 窗口：增量=一个窗口；回填=按半年切（接口一次最多翻几页，窗口太大会被截断）
    wins = []
    if years and years > 0:
        end = today
        for _ in range(int(years * 2)):
            wins.append((end - timedelta(days=182), end)); end = end - timedelta(days=183)
    else:
        wins.append((today - timedelta(days=days), today))
    stats = {"ok": 0, "fail": 0, "skip": 0, "listFail": 0}
    log = []
    for (a, b) in wins:
        items, why = search_window(a, b, fetch_json)
        if why:
            stats["listFail"] += 1; log.append("窗口 %s~%s：%s" % (a, b, why))
        arts = pick_articles(items)
        log.append("窗口 %s~%s：列表 %d 条，库存周报 %d 篇" % (a, b, len(items), len(arts)))
        for td in sorted(arts, reverse=True):
            if not years:
                old = (today - date.fromisoformat(td)).days > 28 and any(p["d"] == td for p in store.get("stk", []))
                done = complete(store, td) and td not in {x.split(":")[0] for x in store.get("calc", [])}
                if old or done:
                    stats["skip"] += 1; continue      # 增量：四周前的、或三项齐全且不是算出来的，不重抓（回填用 --years）
            st, msg = process_article(store, td, arts[td], fetch_text, use_body)
            stats[st] += 1; log.append("  %s %s %s" % (td, st, msg))
            time.sleep(sleep)
    changed = any(store.get(k) for k in ("stk", "dark", "light"))
    if changed:
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
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    store, stats, log = run(years=a.years, days=a.days, use_body=not a.no_bodies, out=a.out)
    print("\n".join("[RU库存] " + x for x in log))
    n = len(store.get("stk", []))
    print("[RU库存] 结果 %s；累计 %d 周（总库存），深色 %d，浅色 %d，其中算出 %d 项，警告 %d；最新 %s" % (
        stats, n, len(store.get("dark", [])), len(store.get("light", [])), len(store.get("calc", [])), len(store.get("warn", [])),
        store["stk"][-1]["d"] if n else "—"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print("[RU库存] 失败：%s: %s" % (type(e).__name__, str(e)[:200])); sys.exit(0)
