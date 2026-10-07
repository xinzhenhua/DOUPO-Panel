# -*- coding: utf-8 -*-
"""龙虎榜按"交易日"往回找数据(v101.1)。运行：python3 test_position_rank_dates.py
背景：fetch_dce_position_rank_multi 原来 `for days_back in range(6)`，每个日历日算一次尝试，周末/假日也消耗次数。
国庆休市 10-01~10-07，10-06 往回数 6 个日历日只到 10-01，够不到最后一个有数据的交易日 09-30 → 龙虎榜整块失效
(线上 latest.json：'尝试了最近6个日期都没能获取到M2701的持仓排名数据'，marketCapital.available=false)。"""
import os, sys, traceback
from datetime import datetime, timedelta, date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd
import cn_calendar as cc

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def D(s):
    return datetime.strptime(s, "%Y-%m-%d")


def test_normal_weekday_returns_recent_trading_days_only():
    """手算：2026-09-29(周二) 起往回 6 个交易日：09-29、09-28(周一)、09-25(周五，跳过周末09-26/27)、09-24、09-23、09-22。"""
    got = [d.strftime("%Y-%m-%d") for d in fd.candidate_trading_dates(D("2026-09-29"), 6, min_calendar_days=0)]
    assert got == ["2026-09-29", "2026-09-28", "2026-09-25", "2026-09-24", "2026-09-23", "2026-09-22"], got
    ok("★不要求日历下限时：从周二往回6个交易日，周末不占名额(09-26/27被跳过)")


def test_national_day_holiday_still_reaches_the_last_trading_day():
    """★这次线上失败的场景：10-06(国庆休市，表里有)。往回要越过 10-06~10-01 全部休市日，第一个候选就是 09-30。"""
    got = [d.strftime("%Y-%m-%d") for d in fd.candidate_trading_dates(D("2026-10-06"), 6, min_calendar_days=0)]
    assert got[0] == "2026-09-30", f"国庆里应该直接从最后一个交易日09-30开始找，实际 {got}"
    assert got == ["2026-09-30", "2026-09-29", "2026-09-28", "2026-09-25", "2026-09-24", "2026-09-23"], got
    assert all(cc.dce_is_trading_day(d.date()) for d in fd.candidate_trading_dates(D("2026-10-06"), 6)), "候选里不能有休市日"
    # 对照：旧写法 range(6) 个日历日，10-06 往回只到 10-01，一个交易日都没有
    old = [(D("2026-10-06") - timedelta(days=i)) for i in range(6)]
    assert not any(cc.dce_is_trading_day(d.date()) for d in old), "确认旧写法在这个场景里一个交易日都碰不到(这就是线上失败的原因)"
    ok("★国庆(10-06)：候选从最后一个交易日09-30开始；旧写法的6个日历日(10-06~10-01)里一个交易日都没有——这就是线上龙虎榜失效的原因")


def test_holiday_day_itself_is_not_a_candidate():
    got = [d.strftime("%Y-%m-%d") for d in fd.candidate_trading_dates(D("2026-10-03"), 3, min_calendar_days=0)]
    assert "2026-10-03" not in got and got[0] == "2026-09-30", got
    ok("今天本身是休市日(10-03)：不作为候选，不白发网络请求")


def test_minimum_calendar_span_guarantees_coverage_of_a_nine_day_holiday():
    """★因此函数要保证'至少回溯 N 个日历日'(默认14天)，不管表里有没有记录：覆盖春节9天休市+前后周末。
    手算：02-12 往回 14 天到 01-29，包含 02-04(节前最后一个交易日)。"""
    # 02-12(周五)往回：02-12、11、10、09、08(周一)、05(周五)——靠"6个交易日"恰好停在02-05，够不到02-04。
    # 只有"至少覆盖14个日历日"这条下限才会让它继续往回包含 02-04。所以这条同时验证了：下限起作用，且不下限时(min_calendar_days=0)确实够不到。
    short = fd.candidate_trading_dates(D("2027-02-12"), 6, min_calendar_days=0)
    assert D("2027-02-04") not in short and min(short) == D("2027-02-05"), f"前置：只按6个交易日时停在02-05，够不到02-04：{short[-2:]}"
    got = fd.candidate_trading_dates(D("2027-02-12"), 6, min_calendar_days=14)
    assert D("2027-02-04") in got, "必须包含春节前最后一个交易日 2027-02-04"
    assert len(got) > len(short), "日历下限让候选变多了"
    ok("★日历天数下限(14天)：只按6个交易日停在02-05够不到节前最后交易日02-04；加上14天下限后包含了02-04(春节还不在休市表里时靠它兜底)")


def test_results_are_newest_first_unique_and_never_in_the_future():
    got = fd.candidate_trading_dates(D("2026-09-29"), 6, min_calendar_days=14)
    assert got == sorted(set(got), reverse=True), "按日期从新到旧，不重复"
    assert all(d <= D("2026-09-29") for d in got), "不能有未来日期"
    ok("候选日期从新到旧、不重复、没有未来日期")


def test_hard_cap_prevents_runaway_when_calendar_is_wrong():
    """日历数据有错(比如把所有日子都当休市)时不能死循环：有日历天数的硬上限。"""
    orig = cc.dce_is_trading_day
    cc.dce_is_trading_day = lambda d: False
    try:
        got = fd.candidate_trading_dates(D("2026-09-29"), 6, min_calendar_days=14, max_calendar_days=30)
    finally:
        cc.dce_is_trading_day = orig
    assert got == [], f"全是休市日时返回空，不是无限循环：{got}"
    orig2 = cc.dce_is_trading_day
    cc.dce_is_trading_day = lambda d: True
    try:
        got2 = fd.candidate_trading_dates(D("2026-09-29"), 6, min_calendar_days=14, max_calendar_days=30)
    finally:
        cc.dce_is_trading_day = orig2
    assert (D("2026-09-29") - min(got2)).days >= 13 and len(got2) >= 14, f"日历说天天都是交易日时：仍保证至少覆盖14个日历日(不能只给6天)：{len(got2)}个"
    ok("日历出错的两种极端(全休市/全交易日)：不死循环；全交易日时仍覆盖至少14个日历日")


def test_hard_cap_actually_bounds_how_many_days_are_examined():
    """★变异检查发现：只看返回值(全休市→空列表)分不出硬上限是30还是30000(只是慢)。用计数器验证：全休市时日历函数恰好被调用 max_calendar_days+1 次。"""
    calls = []
    orig = cc.dce_is_trading_day
    cc.dce_is_trading_day = lambda d: (calls.append(d), False)[1]
    try:
        fd.candidate_trading_dates(D("2026-09-29"), 6, min_calendar_days=14, max_calendar_days=30)
    finally:
        cc.dce_is_trading_day = orig
    assert len(calls) == 31, f"全休市时应恰好检查 max_calendar_days+1=31 天后停止，实际 {len(calls)} 次"
    ok("★硬上限真的限制了循环：全休市时恰好检查31个日历日后停止(不是无限、也不是30000)")


def test_calendar_floor_boundary_is_exactly_min_calendar_days():
    """★变异检查发现：下限条件 `back+1 >= min` 与 `back+1 > min` 差一个日历日，之前没有用例落在边界上。
    手算：today=2026-09-29，back=k 表示往回 k 天。n_trading_days=0(个数条件恒成立，只由日历下限决定何时停止)；
    让日历只有两个交易日：09-16(back=13)和 09-15(back=14)。循环在'处理完 back 这一天'之后判断 back+1>=min：
      min=14 → 处理完 back=13 就停 → 只含 09-16，不含 09-15；若误写成 back+1>min，要处理完 back=14 才停 → 会多含 09-15。
      min=13 → 处理完 back=12 就停 → 两个都不含。  min=15 → 处理完 back=14 才停 → 两个都含。"""
    days = {date(2026, 9, 16), date(2026, 9, 15)}
    orig = cc.dce_is_trading_day
    cc.dce_is_trading_day = lambda d: (d.date() if hasattr(d, "date") else d) in days
    try:
        f = lambda m: sorted(x.date() for x in fd.candidate_trading_dates(D("2026-09-29"), 0, min_calendar_days=m, max_calendar_days=40))
        got13, got14, got15 = f(13), f(14), f(15)
    finally:
        cc.dce_is_trading_day = orig
    assert got13 == [], f"下限13：处理完 back=12 就停，09-16(back=13)还没到：{got13}"
    assert got14 == [date(2026, 9, 16)], f"下限14：处理完 back=13 停，含 09-16 不含 09-15：{got14}"
    assert got15 == [date(2026, 9, 15), date(2026, 9, 16)], f"下限15：处理完 back=14 停，两个都含：{got15}"
    ok("★日历下限边界精确：下限13→空、下限14→只含距今13天的09-16、下限15→再含距今14天的09-15(分得出 >= 与 >)")


def test_max_attempts_parameter_changes_the_number_of_trading_days():
    """★变异检查发现：max_attempts 的默认值6与写死的6无差别，因为没有任何测试传别的值。传 3 和 10，候选交易日个数要跟着变(不要求日历下限，避免被下限盖住)。"""
    f = lambda n: len(fd.candidate_trading_dates(D("2026-09-29"), n, min_calendar_days=0))
    assert (f(3), f(6), f(10)) == (3, 6, 10), (f(3), f(6), f(10))
    # 并且 fetch 函数把 max_attempts 原样传下去(接线)
    import inspect
    assert "n_trading_days=max_attempts" in inspect.getsource(fd.fetch_dce_position_rank_multi)
    ok("★max_attempts 真的决定候选交易日个数(3→3、6→6、10→10)，且接线把它原样传给了 candidate_trading_dates")


def test_the_fetch_loop_uses_candidate_dates_instead_of_range_of_calendar_days():
    """★接线：函数对、没接上就等于没做。fetch_dce_position_rank_multi 的循环必须用 candidate_trading_dates。"""
    import inspect
    src = inspect.getsource(fd.fetch_dce_position_rank_multi)
    assert "candidate_trading_dates" in src, "循环没有使用 candidate_trading_dates"
    assert "for days_back in range(max_attempts)" not in src, "还在用旧的 range(max_attempts) 日历日循环"
    ok("★接线：循环使用 candidate_trading_dates，旧的 range(max_attempts) 已去掉")


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
