# -*- coding: utf-8 -*-
"""自适应搜索窗口(v101.4)。运行：python3 test_search_windowed.py
背景：Mysteel 搜索接口一次最多返回 750 条。开机率回填的 8 个 90 天窗口**全部恰好返回 750 条**(2026-10-08 的真实报告)，被截断，
只采到 399 个交易日(理论上 450 多个)，而代码只在报告里提醒、没有补救。现在：窗口返回满 750 条就对半切开重搜，直到不再封顶。"""
import os, sys, traceback, tempfile, shutil
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backfill_history as bf
import history_store as hs
import test_crush_rate_rule as tc

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def mkitem(d, n, stamp="16:30"):
    return {"publishTime": f"{d} {stamp}", "title": f"文章{d}-{n}", "content": "", "url": f"http://x/{d}/{n}"}


def day_range(a, b):
    out, d = [], a
    while d <= b:
        out.append(d)
        d += timedelta(days=1)
    return out


def fake_capped_search(items, calls, cap=750):
    """模拟真实接口：窗口内超过 cap 条时只返回前 cap 条(按发布时间从新到旧)，total 也封顶在 cap——调用方看不出真实总数。"""
    def _s(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        calls.append({"start": start.date(), "end": end.date(), "max_pages": max_pages, "url": url, "sleep_s": sleep_s, "query": query})
        sel = sorted((i for i in items if start.date().isoformat() <= i["publishTime"][:10] <= end.date().isoformat()), key=lambda i: i["publishTime"], reverse=True)
        return sel[:cap], min(len(sel), cap), None
    return _s


def test_under_the_cap_one_call_no_split():
    items = [mkitem("2026-05-01", n) for n in range(10)]
    calls = []
    got, info = bf.search_windowed(fake_capped_search(items, calls), "q", date(2026, 5, 1), date(2026, 7, 29))
    assert len(got) == 10 and len(calls) == 1 and info["splits"] == 0 and info["unresolved"] == [], (len(got), len(calls), info)
    ok("没封顶：只搜一次，不切窗口，10条全拿到")


def test_over_the_cap_is_split_until_nothing_is_lost():
    """★真实场景的缩影：90天 × 每天10条 = 900条 > 750。不切窗口会丢最老的 150 条。"""
    ds = day_range(date(2026, 5, 1), date(2026, 7, 29))
    items = [mkitem(d.isoformat(), n) for d in ds for n in range(10)]
    calls = []
    got, info = bf.search_windowed(fake_capped_search(items, calls), "q", ds[0], ds[-1])
    assert len(items) == 900 and len(got) == 900, f"应该一条不丢：{len(got)}/900"
    assert info["splits"] >= 1 and info["unresolved"] == [], info
    # 对照：不切窗口(只调用一次)只能拿到750条
    single = fake_capped_search(items, [])("q", datetime(2026, 5, 1), datetime(2026, 7, 29, 12))
    assert len(single[0]) == 750
    ok("★90天×10条=900条：不切只能拿750(丢150)；自适应切窗后拿齐900条，没有'仍未解决'的窗口")


def test_exactly_at_the_cap_counts_as_possibly_truncated():
    """恰好返回750条无法区分'刚好750条'和'被截断'，必须当作被截断处理。"""
    ds = day_range(date(2026, 5, 1), date(2026, 5, 10))
    items = [mkitem(d.isoformat(), n) for d in ds for n in range(75)]      # 10天×75=750
    calls = []
    got, info = bf.search_windowed(fake_capped_search(items, calls), "q", ds[0], ds[-1])
    assert len(got) == 750 and info["splits"] == 1 and len(calls) == 3, (len(got), info, len(calls))
    ok("★恰好750条按'可能被截断'处理：切一次(共3次调用)，两半都不封顶，结果仍是750条")


def test_leaf_windows_partition_the_range_exactly():
    """★切出来的叶子窗口必须无缝无重叠地覆盖原区间(否则会漏天或重复)。"""
    ds = day_range(date(2026, 5, 1), date(2026, 7, 29))
    items = [mkitem(d.isoformat(), n) for d in ds for n in range(20)]      # 每天20条，1800条
    calls = []
    got, info = bf.search_windowed(fake_capped_search(items, calls), "q", ds[0], ds[-1])
    leaves = sorted((c["start"], c["end"]) for c in calls if (c["end"] - c["start"]).days == 0 or True)
    # 叶子 = 没有被再切的窗口：它的区间不被其它调用的区间严格包含
    def is_parent(c):
        return any((o["start"] >= c["start"] and o["end"] <= c["end"] and (o["start"], o["end"]) != (c["start"], c["end"])) for o in calls)
    leaf = sorted((c["start"], c["end"]) for c in calls if not is_parent(c))
    assert leaf[0][0] == ds[0] and leaf[-1][1] == ds[-1], leaf[:2]
    for (a0, a1), (b0, b1) in zip(leaf, leaf[1:]):
        assert b0 == a1 + timedelta(days=1), f"叶子窗口之间有缝或重叠：{(a0, a1)} -> {(b0, b1)}"
    assert len(got) == 1800
    ok("★叶子窗口无缝无重叠地覆盖整个区间(2026-05-01~07-29)，1800条全拿到")


def test_a_single_day_that_still_hits_the_cap_is_reported_not_hidden():
    items = [mkitem("2026-06-15", n) for n in range(800)] + [mkitem("2026-06-16", n) for n in range(3)]
    calls = []
    got, info = bf.search_windowed(fake_capped_search(items, calls), "q", date(2026, 6, 14), date(2026, 6, 17))
    assert info["unresolved"] == ["2026-06-15~2026-06-15"], info
    assert len(got) == 750 + 3, len(got)
    ok("★单日仍然封顶(800条)：不再切(切不动了)，在 unresolved 里明确标出 2026-06-15，其余天正常拿到")


def test_cap_is_detected_from_returned_count_even_when_total_is_missing():
    """★变异检查发现：只看接口的 total 字段分不出问题——真实接口里 total 可能缺失(_search_articles 取不到时是0)。
    窗口实际返回了750条、total=0：必须按封顶处理(切窗)；反过来 total>=750 但返回条数<750(分页中途失败)也要切。"""
    ds = day_range(date(2026, 5, 1), date(2026, 5, 10))
    items = [mkitem(d.isoformat(), n) for d in ds for n in range(80)]      # 800条
    def no_total(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        sel = [i for i in items if start.date().isoformat() <= i["publishTime"][:10] <= end.date().isoformat()]
        return sel[:750], 0, None      # total 缺失
    got, info = bf.search_windowed(no_total, "q", ds[0], ds[-1])
    assert len(got) == 800 and info["splits"] >= 1, (len(got), info)
    def total_only(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        sel = [i for i in items if start.date().isoformat() <= i["publishTime"][:10] <= end.date().isoformat()]
        return sel[:100], 750 if len(sel) > 100 else len(sel), "第3页请求失败"      # 分页中途失败：条数少但 total 说明还有
    got2, info2 = bf.search_windowed(total_only, "q", ds[0], ds[-1])
    assert info2["splits"] >= 1, info2
    ok("★封顶判断两个信号都看：返回750条但 total 缺失→切窗；返回条数少但 total>=750(分页中途失败)→也切")


def test_dedup_across_windows_and_failure_notes_do_not_split():
    a = mkitem("2026-06-10", 1)
    dup = [dict(a), dict(a)]
    def s(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        return dup, 2, None
    got, info = bf.search_windowed(s, "q", date(2026, 6, 10), date(2026, 6, 10))
    assert len(got) == 1, "同一条(同url)重复出现只算一条"
    def failing(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        return [], 0, "搜索接口无返回/返回异常"
    got, info = bf.search_windowed(failing, "q", date(2026, 6, 1), date(2026, 6, 30))
    assert got == [] and info["splits"] == 0 and info["calls"] == 1 and "搜索接口无返回" in " ".join(info["notes"]), info
    ok("重复的条目按url去重；接口失败(没返回)：不切窗口(切了也没用)，失败原因记进 notes")


def test_kwargs_reach_the_search_function_unchanged():
    calls = []
    bf.search_windowed(fake_capped_search([], calls), "全国动态全样本油厂开机率", date(2026, 6, 1), date(2026, 6, 3), max_pages=60, url="U", sleep_s=0.25)
    assert calls[0]["max_pages"] == 60 and calls[0]["url"] == "U" and calls[0]["sleep_s"] == 0.25 and calls[0]["query"] == "全国动态全样本油厂开机率"
    ok("max_pages/url/sleep_s/query 原样传给搜索函数(开机率走快讯接口，不能丢 url)")


def test_hard_bound_on_the_number_of_calls():
    """永远封顶的接口(每个窗口都返回750)不能无限切：90天窗口最多 2*90-1=179 次调用。"""
    def always_capped(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        return [mkitem(start.date().isoformat(), 1)], 750, None
    calls = []
    def wrapped(*a, **k):
        calls.append(1)
        return always_capped(*a, **k)
    got, info = bf.search_windowed(wrapped, "q", date(2026, 5, 1), date(2026, 7, 29))
    assert len(calls) == 179 and len(info["unresolved"]) == 90, (len(calls), len(info["unresolved"]))
    ok("永远封顶的接口：90天窗口恰好 179 次调用、90个单日 unresolved，不会无限切")


def test_crush_backfill_now_recovers_the_days_that_a_capped_window_used_to_lose():
    """★端到端：每天9条(1条真读数+8条别的快讯)，90天=810条>750。旧的固定窗口会丢掉最老的约 7 天；现在一天不丢。"""
    ds = day_range(date(2026, 6, 1), date(2026, 8, 29))
    items = []
    for i, d in enumerate(ds):
        items.append(tc.mk(d.isoformat(), tc.FLASH(f"{50 + (i % 20)}.{i % 10}"), "17:30"))
        for n in range(8):
            items.append(tc.mk(d.isoformat(), "砂石矿山开机率28.96%，较上周提升10.82个百分点", f"09:{n:02d}"))
    assert len(items) == 810
    calls = []
    d_ = tempfile.mkdtemp()
    try:
        rep = bf.backfill_crush_rate(base_dir=d_, start=date(2026, 6, 1), today=date(2026, 8, 29), search=fake_capped_search(items, calls))
        pts = hs.load_series("crush_rate", d_)["points"]
        assert len(pts) == 90 and pts[0]["d"] == "2026-06-01" and pts[-1]["d"] == "2026-08-29", (len(pts), pts[0], pts[-1])
        assert rep["windowsHitCap"] == [] and any("切窗" in n for n in rep["notes"]), rep["notes"]
        single = fake_capped_search(items, [])("q", datetime(2026, 6, 1), datetime(2026, 8, 29, 12))
        assert len(single[0]) == 750, "对照：固定窗口只能拿到750条，最老的60条(约7天)丢了"
    finally:
        shutil.rmtree(d_, ignore_errors=True)
    ok("★开机率回填端到端：90天×9条=810条>750，旧的固定窗口会丢最老约7天；现在 90 个交易日一天不丢，windowsHitCap 为空，报告写明切窗次数")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    fails = []
    for t in TESTS:
        try:
            t()
        except Exception:
            fails.append(t.__name__)
            print("❌", t.__name__)
            traceback.print_exc()
    print(f"\n结果：{_pass}项通过，{len(fails)}项失败" + (f"：{fails}" if fails else ""))
    sys.exit(1 if fails else 0)
