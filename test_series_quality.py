# -*- coding: utf-8 -*-
"""序列质量声明：口径断点(meal_stock 2024-01-05)与已知可疑点(meal_stu 2025-04)。原始点永远保留，只是计算分位/校准时不用。
运行：python3 test_series_quality.py"""
import os, sys, tempfile, shutil, traceback, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_store as hs
import backfill_history as bf

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="sq_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


# 用户2026-10-01贴出的 meal_stu.json 里的真实20个点(月份, 值)
REAL_STU = [("2024-05", 13.77), ("2024-06", 16.57), ("2024-07", 20.83), ("2024-08", 20.27), ("2024-09", 17.22), ("2024-11", 11.32), ("2024-12", 10.66), ("2025-01", 7.4),
            ("2025-02", 9.86), ("2025-04", 1.56), ("2025-11", 15.4), ("2025-12", 16.3), ("2026-01", 12.45), ("2026-02", 20.95), ("2026-03", 15.54), ("2026-04", 10.17),
            ("2026-05", 5.94), ("2026-07", 13.19), ("2026-08", 15.12), ("2026-09", 16.04)]


def test_declarations_match_what_the_user_reported():
    assert hs.SERIES_BREAKS["meal_stock"][0] == "2024-01-05", "Mysteel特别声明：自2024年1月5日(第一周)开始网页端只发一版动态全样本数据"
    assert "2025-04" in hs.KNOWN_SUSPECT_POINTS["meal_stu"]
    ok("声明表：meal_stock口径断点=2024-01-05(Mysteel特别声明原文)；meal_stu已知可疑点=2025-04")


def test_series_break_excludes_old_basis_points_but_keeps_them_in_the_file():
    pts = [{"d": "2022-11-21", "v": 14.92}, {"d": "2023-12-29", "v": 40.0}, {"d": "2024-01-02", "v": 50.0}, {"d": "2024-01-05", "v": 60.0}, {"d": "2024-01-12", "v": 70.0}, {"d": "2026-09-28", "v": 129.64}]
    u = hs.usable_points("meal_stock", pts)
    assert [p["d"] for p in u] == ["2024-01-05", "2024-01-12", "2026-09-28"], "断点当天(2024-01-05)含在内，之前的(含2023-12-29、2024-01-02)排除"
    assert len(pts) == 6, "原始列表没被修改"
    ex = hs.excluded_points("meal_stock", pts)
    assert [d for d, _ in ex] == ["2022-11-21", "2023-12-29", "2024-01-02"] and all("口径断点" in r and "2024年1月5日" in r for _, r in ex)
    ok("口径断点：2024-01-05及之后保留，之前(含2022年旧口径的历史最低14.92万吨)排除；原始数据不改；排除原因写明出处")


def test_known_suspect_point_excluded_from_percentile_but_kept_in_file():
    with Tmp() as d:
        hs.record_points("meal_stu", [{"d": m, "v": v, "x": {"how": "stated"}} for m, v in REAL_STU], d)
        pts = hs.load_series("meal_stu", d)["points"]
        assert len(pts) == 20 and any(p["d"] == "2025-04" and p["v"] == 1.56 for p in pts), "文件里仍然有这个点"
        u = hs.usable_points("meal_stu", pts)
        assert len(u) == 19 and all(p["d"] != "2025-04" for p in u)
        # 用真实数据看影响：当前值16.04%在19个点里的分位 vs 20个点(含1.56)里的分位
        s19 = hs.summarize(u, 16.04, "2026-09", "monthly")
        s20 = hs.summarize(pts, 16.04, "2026-09", "monthly")
        # summarize的n是"剔除当前点自己之后的参照样本数"：20个点里当前值2026-09占1个→n=19(与用户latest.json里history.n=19吻合)；排除1.56后19个点→n=18
        assert s20["n"] == 19 and s19["n"] == 18, (s19["n"], s20["n"])
        assert s19["min"] == 5.94 and s20["min"] == 1.56, "排除后历史最小值是5.94(2026-05)，不再被1.56拖低"
        assert s20["percentile"] == 68.4 and s19["percentile"] == 66.7, "当前16.04%的分位：含1.56→68.4%(与用户latest.json里的真实值一致)，排除后→66.7%"
        assert s20["median"] == 13.77 and s19["median"] == 14.45, "参照样本中位数13.77→14.45"
    ok("★真实数据：meal_stu 20个点里的1.56%(2025-04)排除后，分位基于19个点、最小值5.94；文件里原点保留")


def test_summarize_integration_excludes_declared_points():
    """update_and_attach 里三个有声明的系列：真实经过完整流程，附到结果上的history已排除。"""
    with Tmp() as d:
        hs.record_points("meal_stock", [{"d": "2022-11-21", "v": 14.92}, {"d": "2023-06-05", "v": 30.0}] + [{"d": f"2024-0{m}-{day:02d}", "v": 50.0 + m} for m in (1, 2, 3) for day in (12, 19, 26)], d)
        res = {"mysteelMealStock": {"available": True, "value": 129.64, "date": "2026-09-28", "recentWeeks": [{"date": "2026-09-28", "value": 129.64, "week": "2026年第39周"}]}}
        hs.update_and_attach(res, base_dir=d)
        h = res["mysteelMealStock"]["history"]
        assert h["since"] >= "2024-01-05" and h["min"] >= 51.0, f"history里不应有口径断点之前的点: {h}"
        assert len(hs.load_series("meal_stock", d)["points"]) == 2 + 9 + 1, "文件里仍保留全部(含2个旧口径点)"
    ok("完整流程：meal_stock附到页面的history已排除2022/2023旧口径点(最小值不是14.92)，文件里仍保留全部12个点")


def test_series_without_declarations_are_unaffected():
    pts = [{"d": "2021-05-21", "v": 8.56}, {"d": "2026-09-24", "v": 8.55}]
    assert hs.usable_points("feed_days", pts) == pts and hs.usable_points("不存在的序列", pts) == pts
    assert hs.excluded_points("feed_days", pts) == []
    ok("没有声明的序列(饲料库存天数等)完全不受影响")


def test_calibration_report_shows_exclusions_instead_of_silently_dropping():
    with Tmp() as d:
        old = [{"d": "2022-11-21", "v": 14.92}, {"d": "2022-11-28", "v": 20.0}, {"d": "2023-03-06", "v": 35.0}]
        new = [{"d": f"2024-{m:02d}-08", "v": 40.0 + m * 5} for m in range(1, 9)]
        hs.record_points("meal_stock", old + new, d)
        hs.record_points("meal_stu", [{"d": m, "v": v, "x": {"how": "stated"}} for m, v in REAL_STU], d)
        c = bf.calibration_summary(d)
        ms = c["meal_stock"]
        assert ms["nTotalInFile"] == 11 and ms["n"] == 8 and ms["nExcluded"] == 3 and "2024-01-05" in ms["excludedReason"] and "3个点" in ms["excludedReason"]
        assert min(p for p in [ms["quantiles"]["p5"]]) >= 45, "分位数只基于断点之后的点(旧口径的14.92不在内)"
        assert c["meal_stu_excluded"] == [{"d": "2025-04", "reason": "已知可疑点：离群最小值(1.56%，其余5.9%~21%)，缺期末库存/消费量佐证，无法在现有数据里核实"}]
    ok("★校准报告：明确写出排除了几个点和原因(meal_stock排除3个旧口径点、meal_stu列出2025-04可疑点)，而不是悄悄少算")


def test_empty_and_edge_cases():
    assert hs.usable_points("meal_stock", []) == [] and hs.excluded_points("meal_stu", []) == []
    assert [p["d"] for p in hs.usable_points("meal_stock", [{"d": "2024-01-05", "v": 1}])] == ["2024-01-05"], "断点当天含在内(第一周)"
    assert hs.usable_points("meal_stock", [{"d": "2024-01-04", "v": 1}]) == [], "断点前一天排除"
    assert hs.usable_points("meal_stu", [{"d": "2025-04", "v": 1.56}, {"d": "2025-05", "v": 5.0}])[0]["d"] == "2025-05"
    with Tmp() as d:
        res = {"mysteelMealStock": {"available": True, "value": 50.0, "date": "2026-09-28"}}       # 没有recentWeeks、序列不存在
        hs.update_and_attach(res, base_dir=d)
        assert "history" in res["mysteelMealStock"], "序列不存在时也应附上history(空历史)，不报错"
    ok("边界：空列表、断点当天/前一天、月度日期格式(2025-04)、序列不存在时不报错")


def test_meal_stu_full_flow_excludes_the_suspect_point():
    """★走完整的update_and_attach(meal_stu有自己的春节队列cohort_fn路径)：附到页面的history必须已排除2025-04的1.56%。
    (变异检查发现原先只有meal_stock有集成测试，meal_stu的summarize不走过滤也能通过——而1.56%恰恰在这个系列里。)"""
    with Tmp() as d:
        hs.record_points("meal_stu", [{"d": m, "v": v, "x": {"how": "stated"}} for m, v in REAL_STU if m != "2026-09"], d)
        res = {"mysteelMealStu": {"available": True, "value": 16.04, "month": "2026-09", "date": "2026-08-31", "method": "stated", "stockWan": 125.0, "consumptionWan": 779.0, "productionWan": 795.0,
                                  "usedFallbackMonth": False, "festival": {"disturbed": False}}}
        hs.update_and_attach(res, base_dir=d)
        h = res["mysteelMealStu"]["history"]
        assert h["min"] == 5.94, f"页面拿到的history里最小值应该是5.94，不是被可疑点拖低的1.56: {h}"
        assert h["percentile"] == 66.7 and h["median"] == 14.45, h
        assert any(p["d"] == "2025-04" and p["v"] == 1.56 for p in hs.load_series("meal_stu", d)["points"]), "文件里仍保留这个点"
    ok("★meal_stu完整流程：页面拿到的history最小值5.94(不是1.56)、分位66.7%、中位14.45；文件里仍保留2025-04")


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
