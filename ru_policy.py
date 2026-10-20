# -*- coding: utf-8 -*-
"""橡胶「政策突袭」预警（v102.4）：扫隆众(Mysteel)搜索接口里的天胶快讯，命中「主产国/三国 + 限制出口类动作」→ data/ru_policy.json

只做触发器，不做判断：标题+摘要同时含 ①主产国词(泰国/印尼/马来西亚/ITRC/IRCo/三国…) ②限出口/减产类动作词，
且不含 取消/解除/放宽/撤销（放宽出口对空头是利好，不是风险）。命中 → 页面亮「政策突袭预警」，暂缓新做空/提示持仓离场，你人工核实。
没有回测、关键词法必有误报漏报；官方渠道(RAOT/Kemendag/IRCo)未接入（泰语/印尼语、无稳定接口）。
输出 {"items":[{d,title,url,why}],"scanned":N,"updated":"…","errors":[…]}；只留近 120 天命中(回看模式放大)。联网失败不覆盖旧文件。
用法：python3 ru_policy.py            # 近 14 天
      python3 ru_policy.py --days 400 # 回看（用来检验关键词，如 2016-03 三国限出口能否命中）"""
import argparse
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone

import ru_stock as RS

OUT = "data/ru_policy.json"
KEEP = 120   # 文件里保留多少天的命中；回看模式 main 会放大
QUERIES = ["天胶快讯", "天然橡胶 出口 限制 泰国", "三国 橡胶 出口 削减", "ITRC 橡胶 出口", "印尼 橡胶 出口 政策", "马来西亚 橡胶 出口 政策", "橡胶管理局 RAOT"]
COUNTRY = re.compile(r"泰国|印尼|印度尼西亚|马来西亚|ITRC|IRCo|三国|三大产胶国|主产国|产胶国")
# 动作必须出现在【标题】里，且是政策动词（限制/削减/配额/禁令/联合减产…），不含"减少"（"出口量减少"是数据描述，不是政策）
ACTION = re.compile(r"(限制|削减|暂停|禁止|禁令|收紧|限产|配额|出口税|出口关税).{0,8}(出口|出货|产量|减产)|出口.{0,8}(限制|削减|配额|禁令|暂停|禁止)|联合.{0,8}(减产|限产|限制|限出口)|限出口|出口配额|出口削减|出口限制")
RELAX = re.compile(r"取消|解除|放宽|撤销|废除|放开|恢复出口")
# 非天然橡胶政策/数据类/期货公司评论：这些标题里偶尔提到三国或限出口，但不是新政策
NOISE = re.compile(r"棕榈油|轮胎|促进剂|硬脂酸|月数据|出口量|进口量|数据分析|反倾销|期货[：:]|建议|多单|空单|期权|日评|早评|周评|晨报|行情|走势|胶价|期价|沪胶|策略|何时|反弹|支撑")


def classify(title, content=""):
    """返回 (命中?, 原因)。动作词须在标题里；国家词在标题或摘要里；放宽类/噪音类不算。"""
    title = title or ""
    if not title:
        return False, ""
    a = ACTION.search(title)
    c = COUNTRY.search(title) or COUNTRY.search(content or "")
    if not (c and a):
        return False, ""
    if NOISE.search(title):
        return False, "噪音类，不算"
    if RELAX.search(title[max(0, a.start() - 12):a.end() + 12]):
        return False, "放宽类，不算"
    return True, "%s + %s" % (c.group(0), a.group(0))


def _day(it):
    s = str(it.get("publishTime") or "")[:10]
    return s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else None


def merge(store, items, today):
    """items=搜索结果列表；命中的并入 store['items']（按 url/标题去重），只留近 120 天。返回新增数。"""
    have = {(x.get("url") or x["title"]) for x in store["items"]}
    n = 0
    for it in items:
        d = _day(it); title = (it.get("title") or "").strip()
        if not d or not title:
            continue
        store["scanned"] = store.get("scanned", 0) + 1
        if d < (today - timedelta(days=KEEP)).isoformat():
            continue
        hit, why = classify(title, it.get("content") or "")
        if not hit:
            continue
        k = it.get("url") or title
        if k in have:
            continue
        have.add(k); n += 1
        store["items"].append({"d": d, "title": title, "url": it.get("url") or "", "why": why})
    cut = (today - timedelta(days=KEEP)).isoformat()
    store["items"] = sorted([x for x in store["items"] if x["d"] >= cut], key=lambda x: x["d"])
    return n


def load(path=OUT):
    try:
        j = json.load(open(path, encoding="utf-8"))
        if isinstance(j.get("items"), list):
            return j
    except Exception:
        pass
    return {"items": [], "scanned": 0, "errors": []}


def run(days=14, out=OUT, fetch_json=None, today=None, sleep=0.6, trim=True):
    if fetch_json is None:
        import fetch_data as fd
        fetch_json = fd.fetch_json_debug
    today = today or (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    store = load(out); store["scanned"] = 0; errs = []; added = 0; okq = 0
    for q in QUERIES:
        items, why = RS.search_window(today - timedelta(days=days), today, fetch_json, query=q, max_pages=3 if days <= 30 else 12)
        if why:
            errs.append("%s：%s" % (q, why))
        if items or not why:
            okq += 1
        added += merge(store, items, today)
        time.sleep(sleep)
    store["errors"] = errs; store["updated"] = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    if okq == 0:   # 全部失败：不覆盖旧文件
        return store, added, False
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(store, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return store, added, True


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=14); ap.add_argument("--out", default=OUT)
    ap.add_argument("--end", default="", help="窗口截止日 YYYY-MM-DD（默认今天）；与 --days 配合做定点回看，如 --end 2016-04-30 --days 90")
    a = ap.parse_args(argv)
    global KEEP
    KEEP = max(KEEP, a.days + 5)
    st, added, wrote = run(days=a.days, out=a.out, today=date.fromisoformat(a.end) if a.end else None, trim=not a.end)
    for x in st["items"][-30:]:
        print("[RU政策] 命中 %s %s（%s）" % (x["d"], x["title"], x["why"]))
    for e in st["errors"]:
        print("[RU政策] ⚠ " + e)
    print("[RU政策] 结果 扫描%d条 新增命中%d 累计命中%d 写文件=%s" % (st["scanned"], added, len(st["items"]), wrote))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
