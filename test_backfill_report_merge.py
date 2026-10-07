# -*- coding: utf-8 -*-
"""回填报告：这次没跑的项保留上次的结果(v101.2)。运行：python3 test_backfill_report_merge.py
背景：_backfill_report.json 每次运行都整体覆盖。先跑回填、再跑校准(不联网，series=[])，回填的结果就被盖掉了——
用户把校准的报告发来，看不出回填到底成功没有(2026-10-07 真实发生)。"""
import os, sys, json, tempfile, shutil, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backfill_history as bf

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


T1, T2 = "2026-10-07T13:00:00+00:00", "2026-10-07T14:00:00+00:00"


def e(key, n, **kw):
    return {"key": key, "n": n, **kw}


def test_unrun_items_keep_the_previous_result_marked_with_when_they_ran():
    """手算：上次跑了 crush_rate(n=30)、arrival(n=29)；这次只跑校准(没有新条目)。→ 两项都保留，ranAt=上次时间，且标明'本次未运行'。"""
    prev = [e("crush_rate", 30, ranAt=T1), e("arrival", 29, ranAt=T1)]
    out = bf.merge_report_series(prev, [], T2)
    assert [x["key"] for x in out] == ["crush_rate", "arrival"], out
    assert all(x["ranAt"] == T1 and x["fromPreviousRun"] is True for x in out), out
    assert out[0]["n"] == 30 and out[1]["n"] == 29
    ok("★这次没跑的项保留上次结果：ranAt 仍是上次的时间，标 fromPreviousRun=True，数字不变")


def test_new_result_replaces_the_old_one_for_the_same_key():
    prev = [e("crush_rate", 30, ranAt=T1), e("arrival", 29, ranAt=T1)]
    new = [e("crush_rate", 48)]
    out = {x["key"]: x for x in bf.merge_report_series(prev, new, T2)}
    assert out["crush_rate"]["n"] == 48 and out["crush_rate"]["ranAt"] == T2 and out["crush_rate"]["fromPreviousRun"] is False
    assert out["arrival"]["n"] == 29 and out["arrival"]["ranAt"] == T1 and out["arrival"]["fromPreviousRun"] is True
    ok("★同一项新旧都有：以新的为准(n=48，ranAt=本次)；没重跑的 arrival 仍保留上次的")


def test_a_failed_new_run_does_not_erase_a_good_previous_result():
    """★这次回填 crush_rate 报错(网络失败)——不能把上次成功的 30 个点的统计抹掉：保留上次的，并把这次的错误一起带出来。"""
    prev = [e("crush_rate", 30, ranAt=T1)]
    new = [{"key": "crush_rate", "error": "URLError: timed out"}]
    out = bf.merge_report_series(prev, new, T2)
    cr = [x for x in out if x["key"] == "crush_rate"]
    assert len(cr) == 1 and cr[0]["error"] == "URLError: timed out" and cr[0]["ranAt"] == T2, cr
    assert cr[0]["previousGood"]["n"] == 30 and cr[0]["previousGood"]["ranAt"] == T1, "上次成功的结果挂在 previousGood 下，不丢"
    ok("★这次失败不抹掉上次成功的结果：错误照实写出，上次的 30 点统计挂在 previousGood 下")


def test_first_ever_run_and_corrupt_previous_report_do_not_crash():
    assert bf.merge_report_series(None, [e("arrival", 5)], T2)[0]["ranAt"] == T2
    assert bf.merge_report_series([], [], T2) == []
    for bad in ("坏的", 123, [1, "x", None, {"n": 3}], [{"key": None}], {"a": 1}):
        out = bf.merge_report_series(bad, [e("arrival", 5)], T2)
        assert [x["key"] for x in out] == ["arrival"], (bad, out)
    ok("第一次运行(没有旧报告)、旧报告损坏(字符串/数字/列表里混了垃圾/缺key)：不崩，只保留合法的项")


def test_previous_report_file_missing_or_not_valid_json_does_not_stop_the_run():
    """★变异检查发现：只测了'旧报告里的条目损坏'，没测'旧报告文件本身不存在/不是合法JSON'(例如上次运行被中断写了一半)。这两种都不能让这次运行失败。"""
    d = tempfile.mkdtemp()
    try:
        assert bf._read_previous_series(d) == [], "文件不存在 → 空列表"
        for content in ("{坏的json", "", "[1,2,3]", "null", json.dumps({"series": "不是列表"})):
            open(os.path.join(d, "_backfill_report.json"), "w", encoding="utf-8").write(content)
            got = bf._read_previous_series(d)
            assert got in ([], None, "不是列表") or isinstance(got, list), (content, got)
        # 端到端：旧文件写到一半(坏JSON)时，这次运行照常完成并写出一份好报告
        open(os.path.join(d, "_backfill_report.json"), "w", encoding="utf-8").write('{"generatedAt": "2026-10-')
        r = bf.main(["--only", "calibrate"], base_dir=d)
        assert r["series"] == [] and isinstance(json.load(open(os.path.join(d, "_backfill_report.json"), encoding="utf-8")), dict)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★旧报告文件不存在/是坏JSON(上次写到一半)：这次运行照常完成并写出好报告，不崩")


def test_order_is_stable_and_new_keys_come_after_previous_ones():
    prev = [e("us_stu", 21, ranAt=T1), e("esr", 600, ranAt=T1)]
    out = bf.merge_report_series(prev, [e("arrival", 29), e("esr", 630)], T2)
    assert [x["key"] for x in out] == ["us_stu", "esr", "arrival"], [x["key"] for x in out]
    ok("顺序稳定：旧报告里已有的项保持原位置(被更新也不换位)，新项追加在后面")


def test_main_calibrate_after_backfill_keeps_the_backfill_stats_end_to_end():
    """★端到端：先'回填'(用桩函数代替联网)写出报告，再跑 only=calibrate，报告里的 series 必须还在，且calibration 是新的。"""
    d = tempfile.mkdtemp()
    old_jobs = dict(bf.JOBS)
    try:
        bf.JOBS["arrival"] = lambda base_dir=None, **k: {"key": "arrival", "n": 29, "from": "2024-02", "to": "2026-06"}
        r1 = bf.main(["--only", "arrival"], base_dir=d)
        assert [x["key"] for x in r1["series"]] == ["arrival"] and r1["series"][0]["fromPreviousRun"] is False
        r2 = bf.main(["--only", "calibrate"], base_dir=d)
        assert [x["key"] for x in r2["series"]] == ["arrival"], f"校准后回填结果被抹掉了：{r2['series']}"
        assert r2["series"][0]["n"] == 29 and r2["series"][0]["fromPreviousRun"] is True and r2["series"][0]["ranAt"] == r1["generatedAt"]
        on_disk = json.load(open(os.path.join(d, "_backfill_report.json"), encoding="utf-8"))
        assert on_disk["series"][0]["n"] == 29 and "calibration" in on_disk
    finally:
        bf.JOBS.clear()
        bf.JOBS.update(old_jobs)
        shutil.rmtree(d, ignore_errors=True)
    ok("★端到端：先回填 arrival(29点)，再 only=calibrate——报告里的回填结果还在(标上次运行时间)，校准摘要是新的")


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
