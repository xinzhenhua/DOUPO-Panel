# -*- coding: utf-8 -*-
"""猪粮比历史回填(v101.3)。运行：python3 test_hog_backfill.py
背景：fetch_hog_ratio 每次从 akshare(猪价网数据)拿到的是生猪价和玉米价的**完整历史序列**，却只取了最后一个共同日期，其余全部丢掉；
历史库里的猪粮比因此只有从部署那天起的 8 个点。现在回填：每个共同日期都算一遍，单个日期的计算与 fetch_hog_ratio 共用同一个函数。"""
import os, sys, json, tempfile, shutil, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import fetch_data as fd
import backfill_history as bf
import history_store as hs

_pass = 0
KW = []      # 每次调用数据源时传入的 重试/超时 参数


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def df(d):
    return pd.DataFrame({"date": list(d.keys()), "value": list(d.values())})


def fake_source(pig, corn, fail=None):
    """替换 _fetch_akshare_hog_df：按 symbol 返回假数据。fail='pig'/'corn' 时对应序列返回失败。"""
    def _f(symbol, retries=2, timeout_seconds=15, retry_delay_seconds=2, func_name="futures_hog_supply"):
        KW.append({"symbol": symbol, "retries": retries, "timeout_seconds": timeout_seconds, "retry_delay_seconds": retry_delay_seconds})
        if symbol == "外三元":
            return (None, {"available": False, "reason": "假的失败"}) if fail == "pig" else (df(pig), None)
        if symbol == "玉米":
            return (None, {"available": False, "reason": "假的失败"}) if fail == "corn" else (df(corn), None)
        raise AssertionError("未知 symbol " + symbol)
    return _f


class Patch:
    def __init__(self, pig, corn, fail=None):
        self.f = fake_source(pig, corn, fail)

    def __enter__(self):
        self.orig = fd._fetch_akshare_hog_df
        fd._fetch_akshare_hog_df = self.f
        return self

    def __exit__(self, *a):
        fd._fetch_akshare_hog_df = self.orig


def test_ratio_at_hand_calculated_values_and_units():
    """手算：生猪 10.50 元/公斤 ÷ 玉米 2300 元/吨(=2.3 元/公斤) = 4.5652 → 4.57；玉米直接给 2.3(元/公斤，≤100)结果相同。"""
    r, kind, _ = fd.hog_ratio_at(10.50, 2300.0)
    assert (r, kind) == (4.57, None), (r, kind)
    assert fd.hog_ratio_at(10.50, 2.3)[0] == 4.57, "玉米已经是元/公斤时不再除以1000"
    assert fd.hog_ratio_at(10.40, 2310.0)[0] == 4.5, "10.4/2.31=4.50216 → 4.5"
    ok("★单个日期：10.50÷2300元/吨=4.57；玉米给元/公斤(2.3)结果一样；10.40÷2310=4.5(手算)")


def test_ratio_at_rejects_each_kind_of_bad_input_with_a_kind():
    assert fd.hog_ratio_at(10.5, 0.0)[1] == "corn_nonpositive"
    assert fd.hog_ratio_at(10.5, -5.0)[1] == "corn_nonpositive"
    r, kind, detail = fd.hog_ratio_at(100.0, 2300.0)      # 100/2.3=43.48，超出 1~20
    assert r is None and kind == "range" and "43.48" in detail, (r, kind, detail)
    r, kind, _ = fd.hog_ratio_at(float("nan"), 2300.0)
    assert r is None and kind in ("plausibility", "range"), kind
    assert fd.hog_ratio_at(1.0, 2300.0)[1] in ("range", "plausibility"), "1.0/2.3=0.43 低于下限1"
    ok("★每类坏输入都被拒绝并说明类型：玉米≤0、比值超出1~20、NaN、比值低于1")


def test_ratio_boundaries_are_exact():
    """★变异检查发现：之前没有用例落在边界上，比值上限20改30、下限1改0都没人发现。
    手算(合理性范围：生猪3~40元/公斤，玉米1000~6000元/吨，所以边界值要挑在这个范围里，否则会先被合理性检查拦下)：
    30.0÷1.5=20.0(含上限，接受)；30.02÷1.5=20.0133→20.01(拒绝)；3.0÷3.0=1.0(含下限，接受)；2.97÷3.0=0.99(拒绝)。"""
    assert fd.hog_ratio_at(30.0, 1500.0) == (20.0, None, None)
    r, k, _ = fd.hog_ratio_at(30.02, 1500.0)
    assert r is None and k == "range", (r, k)
    assert fd.hog_ratio_at(3.0, 3000.0) == (1.0, None, None)
    r, k, _ = fd.hog_ratio_at(2.97, 3000.0)
    assert r is None and k == "range", (r, k)
    ok("★比值边界精确：恰好20.0接受、20.01拒绝、恰好1.0接受、0.99拒绝(分得出 <= 与 <)")


def test_corn_unit_threshold_is_100_not_1000():
    """★变异检查发现：阈值100改1000没人发现，因为用例只有2300和2.3。玉米500：
    阈值100 → 当成元/吨，除以1000=0.5元/公斤 → 还原500元/吨 < 合理下限1000 → plausibility；
    若阈值是1000 → 500被当成元/公斤 → 比值10/500=0.02 → range。两者种类不同。另外101、100 都在阈值附近。"""
    r, k, _ = fd.hog_ratio_at(10.0, 500.0)
    assert r is None and k == "plausibility", (r, k)
    assert fd.hog_ratio_at(10.0, 2.0)[0] == 5.0, "玉米给元/公斤(2.0，≤100)：10÷2.0=5.0"
    assert fd.hog_ratio_at(10.0, 100.0)[1] == "range", "恰好100：不再除以1000，当成元/公斤 → 比值0.1 → range"
    assert fd.hog_ratio_at(10.0, 101.0)[1] == "range", "101：>100 除以1000=0.101元/公斤 → 比值99 → range"
    ok("★玉米单位阈值是100：玉米500→plausibility(阈值若是1000会变成range)；2.0→5.0；100和101都→range")


def test_points_use_every_common_date_ascending_and_ignore_dates_in_only_one_series():
    pig = {"2026-09-29": 10.50, "2026-09-30": 10.40, "2026-10-01": 10.30}
    corn = {"2026-09-29": 2300.0, "2026-09-30": 2310.0, "2026-10-02": 2320.0}
    pts, dropped = fd.hog_ratio_points(pig, corn)
    assert pts == [{"d": "2026-09-29", "v": 4.57}, {"d": "2026-09-30", "v": 4.5}], pts
    assert dropped == [], dropped
    # 乱序输入也要升序输出
    pts2, _ = fd.hog_ratio_points(dict(reversed(list(pig.items()))), dict(reversed(list(corn.items()))))
    assert pts2 == pts
    ok("★所有共同日期各算一个点(09-29→4.57、09-30→4.5)，只在一个序列里出现的日期(10-01、10-02)不算；乱序输入也按日期升序输出")


def test_one_bad_date_is_dropped_alone_and_does_not_hurt_the_others():
    pig = {"2026-09-28": 10.0, "2026-09-29": 100.0, "2026-09-30": 10.4}      # 09-29 生猪价离谱
    corn = {"2026-09-28": 2300.0, "2026-09-29": 2300.0, "2026-09-30": 0.0}   # 09-30 玉米为0
    pts, dropped = fd.hog_ratio_points(pig, corn)
    assert [p["d"] for p in pts] == ["2026-09-28"], pts
    assert pts[0]["v"] == 4.35, "10.0/2.3=4.3478 → 4.35"
    assert {d["d"]: d["kind"] for d in dropped} == {"2026-09-29": "range", "2026-09-30": "corn_nonpositive"}, dropped
    ok("★单个日期坏了只丢这一个并记原因(09-29 比值43.48超范围、09-30 玉米为0)，09-28 照常算出 4.35")


def test_latest_point_equals_what_fetch_hog_ratio_reports():
    """★两处共用同一份计算：回填序列的最后一个点 = fetch_hog_ratio 今天给出的值(口径不会分叉)。"""
    pig = {"2026-10-05": 10.20, "2026-10-06": 10.33, "2026-10-07": 10.33}
    corn = {"2026-10-05": 2330.0, "2026-10-06": 2337.0, "2026-10-07": 2337.0}
    with Patch(pig, corn):
        live = fd.fetch_hog_ratio()
    pts, _ = fd.hog_ratio_points(pig, corn)
    assert live["available"] is True and pts[-1] == {"d": live["date"], "v": live["value"]}, (live, pts[-1])
    assert live["value"] == 4.42, "10.33/2.337=4.4203 → 4.42(与线上 latest.json 的 4.42 一致)"
    ok("★回填序列的最后一个点与 fetch_hog_ratio 完全一致(10-07 → 4.42，和你线上 latest.json 的值相同)")


def test_fetch_hog_ratio_error_messages_are_unchanged():
    """重构不能改变线上的报错文案(已有测试依赖)。"""
    with Patch({"2026-10-07": 100.0}, {"2026-10-07": 2300.0}):
        r = fd.fetch_hog_ratio()
    assert r["available"] is False and "超出合理范围(1~20)" in r["reason"] and "可能是单位或字段对错了" in r["reason"], r
    with Patch({"2026-10-07": 10.0}, {"2026-10-07": 0.0}):
        r = fd.fetch_hog_ratio()
    assert r["available"] is False and "玉米价格异常" in r["reason"], r
    with Patch({"2026-10-07": 10.0}, {}, fail="corn"):
        r = fd.fetch_hog_ratio()
    assert r["available"] is False and "玉米价格获取失败" in r["reason"], r
    ok("重构后 fetch_hog_ratio 的三种报错文案与原来一致(比值超范围/玉米异常/玉米获取失败)")


def test_backfill_job_writes_all_points_with_same_shape_as_daily_records():
    d = tempfile.mkdtemp()
    try:
        pig = {f"2026-09-{day:02d}": 10.0 + day * 0.01 for day in range(20, 31)}
        corn = {f"2026-09-{day:02d}": 2300.0 for day in range(20, 31)}
        with Patch(pig, corn):
            entry = bf.backfill_hog_ratio(base_dir=d)
        s = hs.load_series("hog_ratio", d)
        assert len(s["points"]) == 11 and entry["key"] == "hog_ratio", (len(s["points"]), entry)
        assert entry["added"] == 11 and entry["total"] == 11 and entry["first"] == "2026-09-20" and entry["last"] == "2026-09-30", entry      # _report_entry 的真实字段
        assert all(set(p.keys()) == {"d", "v"} for p in s["points"]), "点的结构必须和每天累积的一样：只有 d、v"
        assert s["points"][0]["d"] == "2026-09-20" and s["points"][-1]["d"] == "2026-09-30"
        ok("★回填写入全部 11 个共同日期，点的结构与每天累积的完全一致(只有 d、v)，报告里 added=11、total=11、起止 09-20~09-30")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_backfill_merges_with_existing_points_without_duplicates_and_is_idempotent():
    d = tempfile.mkdtemp()
    try:
        hs.record_points("hog_ratio", [{"d": "2026-09-30", "v": 4.32}, {"d": "2026-10-01", "v": 4.32}], d)      # 线上已经每天累积的点
        pig = {"2026-09-29": 10.0, "2026-09-30": 10.0, "2026-10-01": 10.0}
        corn = {"2026-09-29": 2300.0, "2026-09-30": 2300.0, "2026-10-01": 2300.0}
        with Patch(pig, corn):
            bf.backfill_hog_ratio(base_dir=d)
        s = hs.load_series("hog_ratio", d)
        assert [p["d"] for p in s["points"]] == ["2026-09-29", "2026-09-30", "2026-10-01"], "没有重复日期"
        before = open(os.path.join(d, "hog_ratio.json"), "rb").read()
        with Patch(pig, corn):
            bf.backfill_hog_ratio(base_dir=d)
        assert open(os.path.join(d, "hog_ratio.json"), "rb").read() == before, "第二次运行没有变化时不改文件(幂等)"
        ok("★和线上已累积的点合并不产生重复日期；重复运行幂等(文件字节不变)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_backfill_start_date_filters_and_failures_do_not_write_anything():
    d = tempfile.mkdtemp()
    try:
        from datetime import date
        pig = {f"2026-09-{day:02d}": 10.0 for day in range(20, 31)}
        corn = {f"2026-09-{day:02d}": 2300.0 for day in range(20, 31)}
        with Patch(pig, corn):
            bf.backfill_hog_ratio(base_dir=d, start=date(2026, 9, 28))
        assert [p["d"] for p in hs.load_series("hog_ratio", d)["points"]] == ["2026-09-28", "2026-09-29", "2026-09-30"]
        d2 = tempfile.mkdtemp()
        for fail in ("pig", "corn"):
            with Patch(pig, corn, fail=fail):
                e = bf.backfill_hog_ratio(base_dir=d2)
            assert e["key"] == "hog_ratio" and "error" in e, e
            want = "生猪价格(外三元)获取失败" if fail == "pig" else "玉米价格获取失败"
            assert want in e["error"] and "字段解析失败" not in e["error"], f"错误信息要指出是哪个序列失败(而不是被下一步的'字段解析失败'接住)：{e['error']}"
            assert not os.path.exists(os.path.join(d2, "hog_ratio.json")), "失败时不写文件"
        shutil.rmtree(d2, ignore_errors=True)
        ok("★start 之前的日期不进历史(09-28 起 3 个点)；生猪价或玉米价任一失败：报告写 error 且指明是哪个序列失败，不写任何文件")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_backfill_retries_more_and_waits_longer_than_the_hourly_fetch():
    """★2026-10-08 真实报告：回填的猪粮比请求连接超时(重试2次都超时)，历史库里仍只有8个点。一次性任务值得多重试、多等：≥5次、超时≥30秒、两个序列都一样。"""
    d = tempfile.mkdtemp()
    try:
        del KW[:]
        with Patch({"2026-09-30": 10.0}, {"2026-09-30": 2300.0}):
            bf.backfill_hog_ratio(base_dir=d)
        assert {k["symbol"] for k in KW} == {"外三元", "玉米"}, KW
        assert all(k["retries"] >= 5 and k["timeout_seconds"] >= 30 and k["retry_delay_seconds"] >= 3 for k in KW), KW
        del KW[:]
        with Patch({"2026-09-30": 10.0}, {"2026-09-30": 2300.0}):
            fd.fetch_hog_ratio()
        assert all(k["retries"] <= 2 for k in KW), "每小时的抓取保持原来的轻量重试，不拖慢整批抓取"
        ok("★回填：两个序列都重试≥5次、超时≥30秒、重试间隔≥3秒；每小时的线上抓取保持原来的轻量参数(≤2次)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_live_fetch_carries_the_whole_series_capped_to_recent_days():
    from datetime import date, timedelta
    base = date(2022, 1, 1)
    pig = {(base + timedelta(days=i)).isoformat(): 10.0 + (i % 5) * 0.1 for i in range(1500)}
    corn = {(base + timedelta(days=i)).isoformat(): 2300.0 for i in range(1500)}
    with Patch(pig, corn):
        r = fd.fetch_hog_ratio()
    sp = r["seriesPoints"]
    assert len(sp) == fd.HOG_SERIES_KEEP_DAYS == 1100 and sp[-1] == {"d": r["date"], "v": r["value"]}, (len(sp), sp[-1], r["value"])
    assert sp == sorted(sp, key=lambda p: p["d"]) and all(set(p) == {"d", "v"} for p in sp)
    ok("★线上抓取带出整段历史，最多保留最近1100天(约3年，防止文件无限变大)，最后一个点=当天的值，按日期升序，点只有 d、v")


def test_update_and_attach_records_the_series_before_summarising_and_strips_it_from_latest_json():
    d = tempfile.mkdtemp()
    try:
        sp = [{"d": f"2026-09-{day:02d}", "v": 4.0 + day * 0.01} for day in range(1, 31)]
        res = {"hogRatio": {"available": True, "value": 4.3, "date": "2026-09-30", "seriesPoints": sp}}
        touched = hs.update_and_attach(res, base_dir=d)
        s = hs.load_series("hog_ratio", d)["points"]
        assert len(s) == 30 and s[0]["d"] == "2026-09-01" and "hog_ratio" in touched, (len(s), touched)
        assert "seriesPoints" not in res["hogRatio"], "整段历史已存进序列文件，不能留在 latest.json 里每小时重复写一遍"
        h = res["hogRatio"]["history"]
        assert h["n"] == 29 and h["since"] == "2026-09-01", h      # 摘要的参照集不含当天这个点本身：30个点里参照是29个；起点09-01说明读到的是整段历史
        # 对照：如果只记当天一个点(旧行为)，参照集是空的
        d0 = tempfile.mkdtemp()
        r0 = {"hogRatio": {"available": True, "value": 4.3, "date": "2026-09-30"}}
        hs.update_and_attach(r0, base_dir=d0)
        assert r0["hogRatio"]["history"]["n"] == 0, r0["hogRatio"]["history"]
        shutil.rmtree(d0, ignore_errors=True)
        ok("★线上更新：整段历史记进 hog_ratio 序列(30点)，从 latest.json 里去掉明细，并且分位摘要基于整段历史(参照29个点、起点09-01；只记当天时参照是0个)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_update_and_attach_ignores_bad_points_and_works_without_series_points():
    d = tempfile.mkdtemp()
    try:
        res = {"hogRatio": {"available": True, "value": 4.3, "date": "2026-09-30", "seriesPoints": [{"d": "2026-09-29", "v": 4.2}, {"d": "", "v": 4}, {"d": "2026-09-28", "v": "x"}, "垃圾", None, {"v": 4.1}, {"d": "2026-09-30", "v": float("nan")}]}}
        hs.update_and_attach(res, base_dir=d)
        assert [p["d"] for p in hs.load_series("hog_ratio", d)["points"]] == ["2026-09-29", "2026-09-30"], hs.load_series("hog_ratio", d)["points"]
        assert "seriesPoints" not in res["hogRatio"]
        d2 = tempfile.mkdtemp()
        res2 = {"hogRatio": {"available": True, "value": 4.3, "date": "2026-09-30"}}
        hs.update_and_attach(res2, base_dir=d2)
        assert [p["d"] for p in hs.load_series("hog_ratio", d2)["points"]] == ["2026-09-30"], "没有 seriesPoints(旧结果/别的数据源)照常只记当天"
        d3 = tempfile.mkdtemp()
        res3 = {"hogRatio": {"available": False, "reason": "x", "seriesPoints": [{"d": "2026-09-01", "v": 4.0}]}}
        hs.update_and_attach(res3, base_dir=d3)
        assert not os.path.exists(os.path.join(d3, "hog_ratio.json")) and "seriesPoints" not in res3["hogRatio"], "不可用时不记，但明细也不能留在 latest.json 里"
        shutil.rmtree(d2, ignore_errors=True)
        shutil.rmtree(d3, ignore_errors=True)
        ok("坏点(空日期/非数字/NaN/垃圾)单独忽略；没有 seriesPoints 照常只记当天；不可用时不记且明细也不留在 latest.json")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_job_is_registered_and_runs_in_the_default_set():
    assert "hog_ratio" in bf.JOBS and "hog_ratio" in bf.DEFAULT_JOBS
    ok("hog_ratio 已登记为回填任务，且在默认(all)里")


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
