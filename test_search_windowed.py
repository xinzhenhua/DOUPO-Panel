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


# ---------------- v101.5：先探一页(probe)，封顶就直接切，不再翻完750条再丢掉 ----------------
def fake_probe_search(items, calls, cap=750):
    """区分探测(max_pages=1，只给第一页20条+接口报告的总数)和整窗搜索(翻完所有页)。接口总数封顶在 cap。"""
    def _s(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        sel = sorted((i for i in items if start.date().isoformat() <= i["publishTime"][:10] <= end.date().isoformat()), key=lambda i: i["publishTime"], reverse=True)
        total = min(len(sel), cap)
        calls.append({"start": start.date(), "end": end.date(), "max_pages": max_pages, "pages": 1 if max_pages == 1 else min(-(-total // 20), max_pages)})
        return (sel[:20] if max_pages == 1 else sel[:cap]), total, None
    return _s


def test_probe_splits_a_capped_window_without_paging_through_it():
    """★2026-10-08 真实：开机率回填跑满60分钟被取消。每个被截断的父窗口先翻完约38页才发现封顶，再整个丢掉重搜。探测一页就够判断。"""
    ds = day_range(date(2026, 5, 1), date(2026, 7, 29))
    items = [mkitem(d.isoformat(), n) for d in ds for n in range(10)]      # 900条，封顶
    c_plain, c_probe = [], []
    got0, _ = bf.search_windowed(fake_probe_search(items, c_plain), "q", ds[0], ds[-1], max_pages=60)
    got1, info = bf.search_windowed(fake_probe_search(items, c_probe), "q", ds[0], ds[-1], probe=True, max_pages=60)
    assert len(got0) == len(got1) == 900 and info["unresolved"] == [], (len(got0), len(got1))
    pages_plain, pages_probe = sum(c["pages"] for c in c_plain), sum(c["pages"] for c in c_probe)
    assert pages_probe < pages_plain, f"探测应该少翻页：{pages_probe} vs {pages_plain}"
    parent = [c for c in c_probe if (c["start"], c["end"]) == (ds[0], ds[-1])]
    assert len(parent) == 1 and parent[0]["max_pages"] == 1, "封顶的父窗口只被探测了一页，没有整窗翻页"
    ok(f"★探测：900条封顶的窗口只探一页就切，结果同样900条；总翻页数 {pages_plain} → {pages_probe}；封顶的父窗口没被整窗翻页")


def test_probe_uses_the_first_page_when_it_is_everything_and_pages_fully_otherwise():
    few = [mkitem("2026-06-10", n) for n in range(5)]
    c1 = []
    got, info = bf.search_windowed(fake_probe_search(few, c1), "q", date(2026, 6, 1), date(2026, 6, 30), probe=True)
    assert len(got) == 5 and len(c1) == 1 and c1[0]["max_pages"] == 1, c1
    mid = [mkitem("2026-06-10", n) for n in range(45)]      # 45条：第一页只有20，需要整窗翻页
    c2 = []
    got, info = bf.search_windowed(fake_probe_search(mid, c2), "q", date(2026, 6, 1), date(2026, 6, 30), probe=True)
    assert len(got) == 45 and [c["max_pages"] == 1 for c in c2] == [True, False], c2
    ok("★第一页就是全部(5条<20)：只请求一次；多于一页(45条)：探测之后再整窗翻页，45条全拿到")


def test_probe_failure_does_not_split_and_a_capped_single_day_is_still_reported():
    def failing(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        return [], 0, "搜索接口无返回/返回异常"
    got, info = bf.search_windowed(failing, "q", date(2026, 6, 1), date(2026, 6, 30), probe=True)
    assert got == [] and info["splits"] == 0 and info["calls"] == 1 and "搜索接口无返回" in " ".join(info["notes"]), info
    day = [mkitem("2026-06-15", n) for n in range(800)]
    got, info = bf.search_windowed(fake_probe_search(day, []), "q", date(2026, 6, 15), date(2026, 6, 15), probe=True, max_pages=60)
    assert info["unresolved"] == ["2026-06-15~2026-06-15"] and len(got) == 750, info
    ok("探测失败：不切(切了也没用)，原因记进 notes；单日仍封顶(800条)：仍然明确标进 unresolved，拿到的750条保留")


# ---------------- v101.5：开机率回填只补历史里缺的交易日 + 时间预算 ----------------
import cn_calendar as cc


def trading_days(a, b):
    return [d for d in day_range(a, b) if cc.dce_is_trading_day(d)]


def crush_items(days):
    return [tc.mk(d.isoformat(), tc.FLASH(f"{55 + (i % 9)}.{i % 10}"), "17:30") for i, d in enumerate(days)]


def test_crush_only_searches_the_trading_days_missing_from_history():
    """★真实：399天已经在历史里，缺约60天。以前每次都把整个22个月重新下载一遍(加上自适应切窗就超过60分钟)。现在只搜缺的日子。"""
    start, today = date(2026, 6, 1), date(2026, 9, 30)
    allds = trading_days(start, today)
    have = [d for i, d in enumerate(allds) if i % 7 != 3]      # 每7个交易日缺1个
    miss = [d for d in allds if d not in have]
    d_ = tempfile.mkdtemp()
    try:
        hs.record_points("crush_rate", [{"d": x.isoformat(), "v": 50.0} for x in have], d_)
        calls = []
        rep = bf.backfill_crush_rate(base_dir=d_, start=start, today=today, search=fake_capped_search(crush_items(allds), calls))
        p = {x["d"]: x["v"] for x in hs.load_series("crush_rate", d_)["points"]}
        assert len(p) == len(allds) and all(x.isoformat() in p for x in miss), (len(p), len(allds))
        assert all(p[x.isoformat()] == 50.0 for x in have), "已有的点原样保留，不被覆盖"
        searched = sorted({(c["start"], c["end"]) for c in calls})
        covered = {d for a, b in searched for d in day_range(a, b)}
        assert all(x in covered for x in miss), "每个缺的交易日都被搜到"
        assert len(covered) < len(day_range(start, today)), f"只搜缺的附近：覆盖{len(covered)}天 < 整段{len(day_range(start, today))}天"
        assert rep["missingBefore"] == len(miss) and rep["added"] == len(miss) and rep["stillMissing"] == [], rep
    finally:
        shutil.rmtree(d_, ignore_errors=True)
    ok(f"★只补缺的交易日：每7个交易日缺1个，只搜缺口附近(覆盖天数少于整段)，缺的全补上、已有的点原样保留，报告 missingBefore={len(miss)}、stillMissing=[]")


def test_crush_nothing_missing_means_no_search_at_all_and_second_run_is_a_noop():
    start, today = date(2026, 6, 1), date(2026, 6, 30)
    allds = trading_days(start, today)
    d_ = tempfile.mkdtemp()
    try:
        hs.record_points("crush_rate", [{"d": x.isoformat(), "v": 50.0} for x in allds], d_)
        calls = []
        rep = bf.backfill_crush_rate(base_dir=d_, start=start, today=today, search=fake_capped_search([], calls))
        assert calls == [] and rep["missingBefore"] == 0 and rep["added"] == 0, (calls, rep)
    finally:
        shutil.rmtree(d_, ignore_errors=True)
    ok("★历史里该有的交易日都有了：一次搜索都不发(幂等、不浪费、不会再超时)")


def test_crush_time_budget_stops_gracefully_keeps_progress_and_reports_what_is_left():
    start, today = date(2026, 6, 1), date(2026, 9, 30)
    allds = trading_days(start, today)
    have = [d for i, d in enumerate(allds) if i % 7 != 3]
    miss = [d for d in allds if d not in have]
    d_ = tempfile.mkdtemp()
    try:
        hs.record_points("crush_rate", [{"d": x.isoformat(), "v": 50.0} for x in have], d_)
        t = {"now": 0.0}
        def clock():
            return t["now"]
        base = fake_capped_search(crush_items(allds), [])
        def slow(*a, **k):
            t["now"] += 100.0      # 每次搜索"花100秒"
            return base(*a, **k)
        rep = bf.backfill_crush_rate(base_dir=d_, start=start, today=today, search=slow, time_budget_s=250, clock=clock)
        added = len(hs.load_series("crush_rate", d_)["points"]) - len(have)
        assert rep["stoppedEarly"] is True and 0 < added < len(miss), (rep["stoppedEarly"], added, len(miss))
        assert len(rep["stillMissing"]) == len(miss) - added and rep["stillMissing"][0] <= rep["stillMissing"][-1], rep["stillMissing"]
        assert any("时间预算" in n for n in rep["notes"]), rep["notes"]
        rep2 = bf.backfill_crush_rate(base_dir=d_, start=start, today=today, search=fake_capped_search(crush_items(allds), []), time_budget_s=10 ** 9, clock=clock)
        assert rep2["stoppedEarly"] is False and rep2["stillMissing"] == [] and len(hs.load_series("crush_rate", d_)["points"]) == len(allds), rep2
    finally:
        shutil.rmtree(d_, ignore_errors=True)
    ok("★时间预算：超时就停(不被工作流强杀)，已补的天保存，报告写 stoppedEarly 和还缺哪些天；再点一次接着补完")


def test_crush_empty_history_still_covers_the_whole_range_in_contiguous_windows():
    calls = []
    d_ = tempfile.mkdtemp()
    try:
        bf.backfill_crush_rate(base_dir=d_, today=date(2026, 10, 1), search=fake_capped_search([], calls))
    finally:
        shutil.rmtree(d_, ignore_errors=True)
    assert calls[0]["start"] == date(2024, 12, 1) and calls[-1]["end"] == date(2026, 10, 1)
    for a, b in zip(calls, calls[1:]):
        assert b["start"] == a["end"] + timedelta(days=1)
    ok("历史为空(第一次)：与以前一样从2024-12-01到今天无缝分90天窗口(兼容原有行为)")


def test_crush_backfill_really_uses_the_first_page_probe():
    """★变异检查发现：没有测试验证开机率回填真的用了探测——而探测正是修好'跑满60分钟被取消'的关键。"""
    ds = day_range(date(2026, 5, 1), date(2026, 7, 29))
    items = []
    for i, d in enumerate(ds):
        items.append(tc.mk(d.isoformat(), tc.FLASH(f"{50 + (i % 20)}.{i % 10}"), "17:30"))
        for n in range(8):
            items.append(tc.mk(d.isoformat(), "砂石矿山开机率28.96%，较上周提升10.82个百分点", f"09:{n:02d}"))
    calls = []
    d_ = tempfile.mkdtemp()
    try:
        bf.backfill_crush_rate(base_dir=d_, start=ds[0], today=ds[-1], search=fake_probe_search(items, calls))
    finally:
        shutil.rmtree(d_, ignore_errors=True)
    first = calls[0]
    assert first["max_pages"] == 1 and (first["start"], first["end"]) == (ds[0], ds[-1]), first
    assert not any(c["max_pages"] != 1 and (c["end"] - c["start"]).days >= 60 for c in calls), "封顶的大窗口没有被整窗翻页"
    ok("★开机率回填的第一个请求是对整个窗口的探测(max_pages=1)，封顶的大窗口没有被整窗翻页")


def test_crush_never_overwrites_existing_points_even_inside_a_merged_gap_window():
    """★变异检查发现：缺的日子隔得远时每个窗口只含缺的那天，覆盖与否看不出区别。这里让两个缺口相隔3个交易日(合并成一个窗口)，窗口里夹着已有的日子。"""
    start, today = date(2026, 6, 1), date(2026, 6, 30)
    allds = trading_days(start, today)
    gap_a, gap_b = allds[1], allds[3]      # 同一周内相隔2个日历天(≤4，会合并)；中间 allds[2] 已有，被夹进同一个窗口。(上一版用 allds[3]/allds[6] 跨了周末，相隔5天>4，根本不合并)
    have = [d for d in allds if d not in (gap_a, gap_b)]
    d_ = tempfile.mkdtemp()
    try:
        hs.record_points("crush_rate", [{"d": x.isoformat(), "v": 50.0} for x in have], d_)
        calls = []
        bf.backfill_crush_rate(base_dir=d_, start=start, today=today, search=fake_capped_search(crush_items(allds), calls))
        assert any(c["start"] <= allds[2] <= c["end"] and c["start"] <= gap_a and gap_b <= c["end"] for c in calls), "夹具有效：同一个窗口同时覆盖两个缺口和夹在中间的已有日子"
        p = {x["d"]: x["v"] for x in hs.load_series("crush_rate", d_)["points"]}
        assert p[allds[2].isoformat()] == 50.0, "窗口里夹着的已有日子不能被覆盖"
        assert gap_a.isoformat() in p and gap_b.isoformat() in p and p[gap_a.isoformat()] != 50.0
    finally:
        shutil.rmtree(d_, ignore_errors=True)
    ok("★两个缺口(相隔2天)合并成一个窗口、中间夹着已有的日子：已有的点(50.0)原样保留，只补缺的两天")


def test_crush_time_budget_boundary_is_exactly_the_budget():
    """★预算200秒、每次搜索花100秒、每段只需一次请求：开始每段前已用时 0、100、200 秒。已用时恰好等于预算(200)时还允许搜(用 > 不是 >=)，到300才停。"""
    start, today = date(2026, 6, 1), date(2026, 9, 30)
    allds = trading_days(start, today)
    have = [d for i, d in enumerate(allds) if i % 7 != 3]
    d_ = tempfile.mkdtemp()
    try:
        hs.record_points("crush_rate", [{"d": x.isoformat(), "v": 50.0} for x in have], d_)
        t = {"now": 0.0}
        base = fake_capped_search(crush_items(allds), [])
        def slow(*a, **k):
            t["now"] += 100.0
            return base(*a, **k)
        rep = bf.backfill_crush_rate(base_dir=d_, start=start, today=today, search=slow, time_budget_s=200, clock=lambda: t["now"])
        assert rep["rangesSearched"] == 3 and rep["stoppedEarly"] is True, (rep["rangesSearched"], rep["stoppedEarly"])
    finally:
        shutil.rmtree(d_, ignore_errors=True)
    ok("★时间预算边界：已用时恰好等于预算(200秒)时还搜第3段，超过(300秒)才停——共搜3段")


def test_crush_gap_ranges_are_merged_when_close_and_chunked_to_90_days():
    r = bf.gap_ranges([date(2026, 6, 3), date(2026, 6, 4), date(2026, 6, 8), date(2026, 7, 20)])
    assert r == [(date(2026, 6, 3), date(2026, 6, 8)), (date(2026, 7, 20), date(2026, 7, 20)) ], r      # 06-04→06-08 隔4天(周末)合并；07-20 单独
    far = [date(2026, 1, 1) + timedelta(days=i) for i in range(0, 200, 2)]
    chunks = bf.gap_ranges(far)
    assert all((b - a).days <= 89 for a, b in chunks) and chunks[0][0] == far[0] and chunks[-1][1] == far[-1], chunks
    for (a0, a1), (b0, b1) in zip(chunks, chunks[1:]):
        assert b0 > a1
    assert bf.gap_ranges([]) == []
    ok("缺口分组：相隔≤4天(含周末)合并成一段，更远的单独成段；超过90天的段切成≤90天的块；空→空")


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
