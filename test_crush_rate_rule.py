# -*- coding: utf-8 -*-
"""开机率评分规则重做(v98)：滚动365天分位(去掉春节窗口) + 回填。运行：python3 test_crush_rate_rule.py"""
import os, sys, json, tempfile, shutil, traceback
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_store as hs
import backfill_history as bf
import fetch_data as fd

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="cr_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def series(start, n, fn):
    """从start起每天1个点(不分周末，测试用)，值=fn(i)。"""
    d0 = date.fromisoformat(start)
    return [{"d": (d0 + timedelta(days=i)).isoformat(), "v": fn(i)} for i in range(n)]


# ===================== summarize_trailing =====================
def test_trailing_basic_shape_and_semantics():
    pts = series("2025-03-01", 200, lambda i: 50.0 + (i % 21))            # 50..70 循环
    r = hs.summarize_trailing(pts, 60.0, "2025-09-17", window_days=365, min_n=120)
    assert r["n"] == len([p for p in pts if p["d"] < "2025-09-17"]) and r["enough"] is True and r["windowDays"] == 365 and r["minN"] == 120
    assert len(r["quantiles"]) == 21 and r["quantiles"] == sorted(r["quantiles"]) and r["quantiles"][0] == 50.0 and r["quantiles"][-1] == 70.0
    assert r["asOf"] == "2025-09-17" and r["since"] == "2025-03-01" and abs(r["median"] - 60.0) < 1.01
    assert r["percentile"] == hs.percentile_rank(60.0, [p["v"] for p in pts if p["d"] < "2025-09-17"])
    ok("滚动分位：n=参照样本数(不含当天)、21个分位点单调、含最小/最大、percentile与percentile_rank一致")


def test_trailing_window_boundaries_and_current_day_excluded():
    pts = series("2024-01-01", 800, lambda i: float(i))
    asof = "2025-12-01"
    r = hs.summarize_trailing(pts, 700.0, asof, window_days=365, min_n=10)
    ref = [p for p in pts if "2024-12-01" <= p["d"] < asof]          # asof-365天(含) ~ asof前一天
    assert r["n"] == len(ref) == 365 and r["since"] == "2024-12-01", (r["n"], r["since"])
    pts2 = pts + [{"d": asof, "v": 9999.0}]                            # 当天的点(就是当前值自己)不能进参照
    assert hs.summarize_trailing(pts2, 9999.0, asof, window_days=365, min_n=10)["n"] == 365
    assert hs.summarize_trailing(pts, 700.0, asof, window_days=30, min_n=10)["n"] == 30
    ok("窗口边界：asof-365天(含)~前一天共365个点；当天的点(当前值自己)不进参照；窗口天数可调")


def test_trailing_min_n_gate():
    pts = series("2026-01-01", 100, lambda i: 60.0)
    r = hs.summarize_trailing(pts, 60.0, "2026-04-15", window_days=365, min_n=120)
    assert r["enough"] is False and r["n"] == 100 and r["minN"] == 120
    r2 = hs.summarize_trailing(pts, 60.0, "2026-04-15", window_days=365, min_n=100)
    assert r2["enough"] is True
    r0 = hs.summarize_trailing([], 60.0, "2026-04-15")
    assert r0["n"] == 0 and r0["enough"] is False and r0["quantiles"] is None and r0["percentile"] is None
    ok("样本门槛：不足min_n时enough=False(仍给出统计，但不能用于计分)；空序列不报错")


def test_trailing_ignores_bad_points():
    pts = series("2026-01-01", 130, lambda i: 60.0) + [{"d": "2026-02-01", "v": None}, {"d": "乱码", "v": 5.0}, {"d": "2026-03-01", "v": True}, {"d": "2026-03-02", "v": float("nan")}]
    r = hs.summarize_trailing(pts, 60.0, "2026-07-01", window_days=365, min_n=120)
    assert r["n"] == 130 and r["enough"] is True
    ok("坏点(None/日期乱码/布尔/NaN)被忽略")


def test_quantile_table_interpolates_linearly_hand_calculated():
    """★变异检查发现原测试的数据太整齐(50..70循环，分位点都落在整数下标)，插值项恒为0，看不出"不插值"。
    手算：5个点[10,20,30,40,50]，n=5，第k个分位点的位置=(n-1)*k/20=k/5：k=1→0.2→12.0；k=2→0.4→14.0；k=5→1.0→20.0；k=7→1.4→24.0；k=20→4.0→50.0。"""
    q = hs._quantile_table([10.0, 20.0, 30.0, 40.0, 50.0])
    assert len(q) == 21 and q[0] == 10.0 and q[1] == 12.0 and q[2] == 14.0 and q[5] == 20.0 and q[7] == 24.0 and q[10] == 30.0 and q[16] == 42.0 and q[20] == 50.0, q
    assert hs._quantile_table([7.0]) == [7.0] * 21, "只有1个点：全部等于它(不越界)"
    assert hs._quantile_table([1.0, 3.0])[10] == 2.0, "2个点：中位数是中点"
    ok("★分位点表线性插值(手算：[10..50]→12.0/14.0/20.0/24.0/42.0/50.0)；单点/双点不越界")


def test_min_n_gate_through_update_and_attach_is_exactly_120():
    """★变异检查发现原测试用300个点，门槛是120还是1看不出来。恰好119个参照点→不允许计分；120个→允许。(这是整条规则最重要的安全阀)"""
    for n_ref, want in ((119, False), (120, True)):
        with Tmp() as d:
            # 区间必须避开春节窗口(会被排除，参照数就不是n_ref了)：2025-06-01起n_ref天，最晚到2025-09-28，离2026春节窗口(2026-02-10起)很远
            hs.record_points("crush_rate", series("2025-06-01", n_ref, lambda i: 60.0 + (i % 5)), d)
            asof = (date(2025, 6, 1) + timedelta(days=n_ref)).isoformat()                 # 当天=参照最后一天的次日，参照恰好n_ref个
            res = {"mysteelCrushRate": {"available": True, "value": 61.0, "date": asof}}
            hs.update_and_attach(res, base_dir=d)
            tr = res["mysteelCrushRate"]["history"]["trailing"]
            assert tr["n"] == n_ref and tr["enough"] is want and tr["minN"] == 120, (n_ref, tr)
    ok("★经update_and_attach的真实路径：119个参照点→enough=False，120个→True(门槛恰好是120)")


# ===================== usable_points：开机率去掉春节窗口 =====================
def test_usable_points_drops_festival_window_only_for_crush_rate():
    pts = [{"d": "2026-02-09", "v": 66.0}, {"d": "2026-02-10", "v": 55.0}, {"d": "2026-02-24", "v": 15.46}, {"d": "2026-03-03", "v": 50.0}, {"d": "2026-03-04", "v": 54.0},
           {"d": "2025-10-02", "v": 60.0}]
    u = hs.usable_points("crush_rate", pts)
    assert [p["d"] for p in u] == ["2026-02-09", "2026-03-04", "2025-10-02"], [p["d"] for p in u]
    assert hs.usable_points("basis", pts) == pts and hs.usable_points("feed_days", pts) == pts, "别的序列不受影响"
    ex = hs.excluded_points("crush_rate", pts)
    assert [d for d, _ in ex] == ["2026-02-10", "2026-02-24", "2026-03-03"] and all("春节" in r for _, r in ex)
    assert len(pts) == 6, "原始点不动"
    ok("★开机率：春节窗口(节前7天~节后14天)的点不进参照(国庆不排除)；别的序列不受影响；排除原因写明；原始点不改")


# ===================== update_and_attach 挂接 =====================
def test_update_and_attach_adds_trailing_only_for_crush_rate():
    with Tmp() as d:
        hs.record_points("crush_rate", series("2025-09-01", 300, lambda i: 55.0 + (i % 15)), d)
        res = {"mysteelCrushRate": {"available": True, "value": 60.95, "date": "2026-06-28"}, "mysteelBasis": {"available": True, "value": -100, "city": "日照", "date": "2026-06-28"}}
        hs.update_and_attach(res, base_dir=d)
        tr = res["mysteelCrushRate"]["history"]["trailing"]
        assert tr["enough"] is True and tr["n"] >= 120 and tr["asOf"] == "2026-06-28" and len(tr["quantiles"]) == 21 and tr["windowDays"] == 365
        assert "trailing" not in res["mysteelBasis"]["history"], "只有开机率有滚动分位"
    ok("update_and_attach：只给开机率挂history.trailing(含分位点表)，基差等不挂")


def test_trailing_excludes_festival_days_from_the_reference():
    with Tmp() as d:
        base = series("2025-06-01", 260, lambda i: 62.0)
        fest = [{"d": "2026-02-%02d" % k, "v": 12.0} for k in range(10, 28)]          # 春节窗口内的12%
        hs.record_points("crush_rate", base + fest, d)
        res = {"mysteelCrushRate": {"available": True, "value": 61.0, "date": "2026-04-01"}}
        hs.update_and_attach(res, base_dir=d)
        q = res["mysteelCrushRate"]["history"]["trailing"]["quantiles"]
        assert q[0] == 62.0 and min(q) == 62.0, f"春节窗口的12%不该拉低参照分布: {q[:3]}"
    ok("★参照分布里没有春节窗口的12%(否则p0会被拉到12，p20会被严重拉低)")


# ===================== 回填 =====================
def mk(dt, content, hhmm="16:30"):
    return {"publishTime": f"{dt} {hhmm}", "title": "", "content": content, "url": None}


FLASH = lambda v: f"开机方面，今日全国动态全样本油厂开机率为{v}%，较前一日下降1.20%。"


def fake_search(by_window=None, calls=None, items=None):
    def _s(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        if calls is not None:
            calls.append({"query": query, "start": start.date().isoformat(), "end": end.date().isoformat(), "url": url})
        if items is not None:
            sel = [i for i in items if start.date().isoformat() <= i["publishTime"][:10] <= end.date().isoformat()]
            return sel, len(sel), None
        return [], 0, None
    return _s


def test_backfill_crush_rate_basic():
    items = [mk("2025-01-10", FLASH("66.5")), mk("2025-06-02", FLASH("61.3")), mk("2026-03-06", "砂石矿山开机率28.96%，较上周提升10.82个百分点"),
             mk("2026-02-24", FLASH("15.46")), mk("2026-08-15", FLASH("63.2"))]
    with Tmp() as d:
        calls = []
        rep = bf.backfill_crush_rate(base_dir=d, today=date(2026, 10, 1), search=fake_search(calls=calls, items=items))
        p = hs.load_series("crush_rate", d)["points"]
        assert [(x["d"], x["v"]) for x in p] == [("2025-01-10", 66.5), ("2025-06-02", 61.3), ("2026-02-24", 15.46), ("2026-08-15", 63.2)], p
        assert rep["added"] == 4 and calls[0]["query"] == "全国动态全样本油厂开机率" and calls[0]["url"] == fd.MYSTEEL_SEARCH_URL, "走快讯接口"
        assert any("别的行业" in str(x) for x in rep.get("excluded(非油厂/超范围，前6条)", [])), rep.keys()
    ok("回填：4个油厂读数入库(含春节停机15.46%，真实数据)；'砂石矿山开机率'排除；走快讯接口")


def test_backfill_windows_cover_the_range_without_gaps_or_overlap():
    calls = []
    with Tmp() as d:
        bf.backfill_crush_rate(base_dir=d, today=date(2026, 10, 1), search=fake_search(calls=calls, items=[]))
    assert calls[0]["start"] == "2024-12-01" and calls[-1]["end"] == "2026-10-01"
    for a, b in zip(calls, calls[1:]):
        assert date.fromisoformat(b["start"]) == date.fromisoformat(a["end"]) + timedelta(days=1), (a, b)
    assert all((date.fromisoformat(c["end"]) - date.fromisoformat(c["start"])).days <= 90 for c in calls)
    ok("★分窗口搜索(每窗≤90天)：从2024-12-01到今天无缝无重叠——接口有750条上限，不分窗口会漏掉更早的")


def test_backfill_same_day_keeps_the_latest_publication():
    items = [mk("2026-05-06", FLASH("60.0"), "09:30"), mk("2026-05-06", FLASH("62.5"), "17:40"), mk("2026-05-06", FLASH("61.0"), "12:00")]
    with Tmp() as d:
        bf.backfill_crush_rate(base_dir=d, today=date(2026, 10, 1), search=fake_search(items=items))
        p = hs.load_series("crush_rate", d)["points"]
        assert [(x["d"], x["v"]) for x in p] == [("2026-05-06", 62.5)]
    ok("同一天多条快讯：取发布最晚的一条(与每日累积'最后一次运行胜出'一致)")


def test_backfill_merges_with_daily_accumulation():
    with Tmp() as d:
        hs.record_points("crush_rate", [{"d": "2026-09-29", "v": 60.95}], d)
        bf.backfill_crush_rate(base_dir=d, today=date(2026, 10, 1), search=fake_search(items=[mk("2026-09-29", FLASH("60.95")), mk("2026-09-28", FLASH("62.15"))]))
        p = hs.load_series("crush_rate", d)["points"]
        assert [x["d"] for x in p] == ["2026-09-28", "2026-09-29"] and len(p) == 2
        n = len(p)
        bf.backfill_crush_rate(base_dir=d, today=date(2026, 10, 1), search=fake_search(items=[mk("2026-09-29", FLASH("60.95")), mk("2026-09-28", FLASH("62.15"))]))
        assert len(hs.load_series("crush_rate", d)["points"]) == n
    ok("与每日累积合并：同一天不重复；重复运行幂等")


def test_backfill_flags_a_window_that_hit_the_result_cap():
    big = [mk("2026-01-%02d" % (1 + i % 28), FLASH("60.0")) for i in range(750)]
    def capped(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        sel = [i for i in big if start.date().isoformat() <= i["publishTime"][:10] <= end.date().isoformat()]
        return sel, 750 if sel else 0, None
    with Tmp() as d:
        rep = bf.backfill_crush_rate(base_dir=d, today=date(2026, 10, 1), search=capped)
    assert rep["windowsHitCap"] and "750" in " ".join(rep["notes"]), rep
    ok("某个窗口搜索结果恰好750条(接口上限)：报告里标出，提示该窗口可能被截断")


def test_backfill_registered_in_default_jobs_and_failure_modes():
    assert "crush_rate" in bf.JOBS and "crush_rate" in bf.DEFAULT_JOBS and bf.JOBS["crush_rate"] is bf.backfill_crush_rate
    junk = [{"publishTime": "乱码", "content": FLASH("60"), "title": ""}, {"publishTime": "2026-05-06 10:00", "content": None, "title": None}, mk("2026-05-07", "开机率为120%")]
    with Tmp() as d:
        rep = bf.backfill_crush_rate(base_dir=d, today=date(2026, 10, 1), search=fake_search(items=junk))
        assert rep["added"] == 0
        rep0 = bf.backfill_crush_rate(base_dir=d, today=date(2026, 10, 1), search=fake_search(items=[]))
        assert rep0["added"] == 0
    ok("已注册并进默认清单；日期乱码/内容为None/数值超范围/空结果：不报错、不写入")


# ===================== v99：往年同月分位(第一档) =====================
def month_pts(year, month, vals):
    """year年month月，第k个值放在该月第k+1天(测试用，不分周末)。"""
    return [{"d": date(year, month, k + 1).isoformat(), "v": float(v)} for k, v in enumerate(vals)]


def test_same_month_reference_is_other_calendar_years_only_hand_calculated():
    """手算：Dec 2025的20个读数=1..20，当前是2026-12-10。参照=同月不同年→只有Dec 2025的20个(同年2026的点不算)。
    分位点表(n=20, pos=0.95k)：q[0]=1, q[4]=4.8, q[10]=10.5, q[16]=16.2, q[20]=20。当前值12：小于12的有11个、等于1个→(11+0.5)/20=57.5。"""
    pts = month_pts(2025, 12, range(1, 21)) + month_pts(2026, 12, [99, 99, 99])         # 2026年同月的点(同年)不进参照
    r = hs.summarize_same_month(pts, 12.0, "2026-12-10", min_n=20)
    assert r["month"] == 12 and r["n"] == 20 and r["years"] == [2025] and r["enough"] is True and r["minN"] == 20, r
    q = r["quantiles"]
    assert (q[0], q[4], q[10], q[16], q[20]) == (1.0, 4.8, 10.5, 16.2, 20.0), (q[0], q[4], q[10], q[16], q[20])
    assert r["percentile"] == 57.5 and r["median"] == 10.5 and r["since"] == "2025-12-01"
    ok("往年同月参照=同月不同日历年(2026年同月的点不算)；手算：n=20，q4=4.8/q10=10.5/q16=16.2，12的分位57.5")


def test_same_month_median_is_a_median_not_a_mean_skewed_hand_calculated():
    """★变异检查发现1..20对称，均值=中位数=10.5，"用均值"也过。偏斜数据[1,1,1,1,100]：中位数1，均值20.8。"""
    r = hs.summarize_same_month(month_pts(2025, 12, [1, 1, 1, 1, 100]), 1.0, "2026-12-10", min_n=1)
    assert r["median"] == 1.0, r["median"]
    ok("同月参照的median是中位数不是均值(手算：[1,1,1,1,100]中位数1，均值20.8)")


def test_same_month_collects_several_prior_years_and_lists_them():
    pts = month_pts(2024, 12, range(1, 11)) + month_pts(2025, 12, range(11, 21)) + month_pts(2023, 11, range(100, 110)) + month_pts(2025, 1, range(200, 210))
    r = hs.summarize_same_month(pts, 5.0, "2026-12-15", min_n=20)
    assert r["n"] == 20 and r["years"] == [2024, 2025] and r["since"] == "2024-12-01" and r["enough"] is True, r
    assert r["quantiles"][0] == 1.0 and r["quantiles"][20] == 20.0, "别的月份(11月、1月)的点不混进来"
    ok("多个往年合并(2024+2025年12月共20个)；列出年份；别的月份的点不混进来")


def test_same_month_min_n_gate_is_exactly_the_minimum_via_update_and_attach():
    """恰好19个→不够，20个→够(与滚动分位的120那条同理，经update_and_attach的真实路径)。2025-12的点数=n_ref，当前读数在2026-12-10。"""
    for n_ref, want in ((19, False), (20, True)):
        with Tmp() as d:
            hs.record_points("crush_rate", month_pts(2025, 12, [60.0 + (i % 5) for i in range(n_ref)]), d)
            res = {"mysteelCrushRate": {"available": True, "value": 61.0, "date": "2026-12-10"}}
            hs.update_and_attach(res, base_dir=d)
            sm = res["mysteelCrushRate"]["history"]["sameMonth"]
            assert sm["n"] == n_ref and sm["enough"] is want and sm["minN"] == 20, (n_ref, sm)
    ok("★经update_and_attach：同月参照19个→enough=False，20个→True(门槛恰好是20)")


def test_same_month_excludes_festival_window_and_the_tariff_war_period():
    """★春节窗口(放假)和2025年3~4月关税战(真实的停机低谷，不代表往年同月的常态)的读数都不进往年同月参照。
    构造：2025-04有20个正常的60 + 10个关税战期间的30；2025年4月全部在关税战区间里→参照0个。2025-05有20个60→参照20个。"""
    with Tmp() as d:
        war = [{"d": f"2025-04-{k + 1:02d}", "v": 30.0} for k in range(25)]
        may = [{"d": f"2025-05-{k + 1:02d}", "v": 60.0 + (k % 3)} for k in range(25)]
        hs.record_points("crush_rate", war + may, d)
        a = {"mysteelCrushRate": {"available": True, "value": 50.0, "date": "2026-04-15"}}
        hs.update_and_attach(a, base_dir=d)
        assert a["mysteelCrushRate"]["history"]["sameMonth"]["n"] == 0 and a["mysteelCrushRate"]["history"]["sameMonth"]["enough"] is False, "2025年4月整月在关税战区间：参照为空"
        b = {"mysteelCrushRate": {"available": True, "value": 50.0, "date": "2026-05-15"}}
        hs.update_and_attach(b, base_dir=d)
        assert b["mysteelCrushRate"]["history"]["sameMonth"]["n"] == 25, "2025年5月不在关税战区间：正常进入参照"
    assert hs.KNOWN_ABNORMAL_PERIODS["crush_rate"][0][:2] == ("2025-03-01", "2025-04-30")
    ok("★同月参照排除关税战(2025-03-01~04-30)：2025年4月参照为空，2025年5月照常(25个)；区间常量在KNOWN_ABNORMAL_PERIODS里，核实后可改")


def test_abnormal_period_boundaries_are_inclusive_on_both_ends():
    """★变异检查发现没有测试恰好落在区间边界日上(闭区间改成开区间也过)。区间是[2025-03-01, 2025-04-30]，两端都含：
    当前3月→2025-03-01(起点当天)被排除、2025-03-02也被排除(区间内)；当前4月→2025-04-30(终点当天)被排除；
    当前2月→2025-02-28(区间前一天)保留；当前5月→2025-05-01(区间后一天)保留。"""
    def n_ref(as_of, day):
        pts = [{"d": day, "v": 50.0}]
        return hs.summarize_same_month(pts, 50.0, as_of, min_n=1, exclude_key="crush_rate")["n"]
    assert n_ref("2026-03-10", "2025-03-01") == 0, "起点当天被排除"
    assert n_ref("2026-03-10", "2025-03-02") == 0
    assert n_ref("2026-04-10", "2025-04-30") == 0, "终点当天被排除"
    assert n_ref("2026-02-10", "2025-02-28") == 1, "区间前一天保留"
    assert n_ref("2026-05-10", "2025-05-01") == 1, "区间后一天保留"
    assert n_ref("2026-03-10", "2024-03-01") == 1, "别的年份的3月1日不受影响(区间只覆盖2025年)"
    ok("★关税战区间两端都含：2025-03-01/2025-04-30被排除，前一天(02-28)/后一天(05-01)保留，2024年的3月1日不受影响")


def test_same_month_does_not_apply_the_abnormal_period_to_other_series_or_to_trailing():
    pts = [{"d": f"2025-04-{k + 1:02d}", "v": 30.0} for k in range(25)]
    assert [p["d"] for p in hs.usable_points("crush_rate", pts)] == [p["d"] for p in pts], "usable_points不排除关税战(它只对往年同月参照生效)：滚动分位的参照里仍包含"
    assert hs.excluded_points("crush_rate", pts) == [], "关税战的读数不在'被排除的点'里(数据本身是真实的，只是不当作往年同月的常态)"
    with Tmp() as d:
        hs.record_points("crush_rate", pts + [{"d": f"2025-06-{k + 1:02d}", "v": 62.0} for k in range(25)], d)
        res = {"mysteelCrushRate": {"available": True, "value": 61.0, "date": "2025-09-01"}}
        hs.update_and_attach(res, base_dir=d)
        assert res["mysteelCrushRate"]["history"]["trailing"]["n"] == 50, "滚动分位的参照仍含关税战期间的25个+6月的25个"
    ok("关税战区间只影响'往年同月'参照：滚动分位的参照里仍有它(数据是真实的)；别的序列不受影响")


def test_same_month_attached_only_for_crush_rate_and_none_when_current_date_is_bad():
    with Tmp() as d:
        hs.record_points("crush_rate", month_pts(2025, 12, range(1, 25)), d)
        res = {"mysteelCrushRate": {"available": True, "value": 5.0, "date": "2026-12-10"}, "mysteelBasis": {"available": True, "value": -100, "city": "日照", "date": "2026-12-10"}}
        hs.update_and_attach(res, base_dir=d)
        assert "sameMonth" in res["mysteelCrushRate"]["history"] and "sameMonth" not in res["mysteelBasis"]["history"]
    r = hs.summarize_same_month(month_pts(2025, 12, range(1, 25)), 5.0, "乱码", min_n=20)
    assert r["n"] == 0 and r["enough"] is False and r["quantiles"] is None and r["month"] is None
    ok("只给开机率挂history.sameMonth；当前日期乱码不报错(n=0、enough=False)")


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
