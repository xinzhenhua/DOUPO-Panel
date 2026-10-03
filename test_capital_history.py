# -*- coding: utf-8 -*-
"""龙虎榜+CFTC历史累积(v101)：序列、主力合约分段的"连续N日"、CFTC 156周回填。运行：python3 test_capital_history.py
期望值全部手算；龙虎榜的点带合约代码(主力合约会换月，不同合约的净持仓不可比)。"""
import os, sys, tempfile, shutil, traceback
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_store as hs
import fetch_data as fd

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="cap_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def tdays(start, n):
    """从start起n个大商所交易日(跳过周末，测试里没有休市)。"""
    out, d = [], date.fromisoformat(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def pts(dates, vals, contract="M2701"):
    return [{"d": d, "v": v, "x": {"contract": contract}} for d, v in zip(dates, vals)]


# ===================== 序列定义 =====================
def test_series_are_declared():
    for k in ("capital_gs_net", "capital_jpm_net", "capital_ubs_net", "capital_zl_net", "capital_gt_net", "cftc_mm_net"):
        assert k in hs.SERIES_META, k
    assert hs.SERIES_META["capital_gs_net"]["freq"] == "daily" and hs.SERIES_META["cftc_mm_net"]["freq"] == "weekly"
    assert hs.SERIES_META["capital_gs_net"]["unit"] == "手" and hs.SERIES_META["cftc_mm_net"]["unit"] == "手"
    assert "主力合约" in hs.SERIES_META["capital_gs_net"]["name"] and "不可比" in hs.SERIES_META["capital_gs_net"]["name"], "名字里要写明：带合约代码、换月时不可比"
    ok("6个序列已声明：高盛/摩根大通/瑞银/中粮/国投的净持仓(日频，名字写明主力合约且换月不可比)+CFTC管理基金净多(周频)")


# ===================== 连续N日(同一合约内) =====================
def test_consecutive_run_hand_calculated():
    """手算：净持仓 100,110,105,95,90(同一合约，5个相邻交易日d0..d4)。从最新往回：90<95(降)、95<105(降)、105<110(降)、110>100(升，停)
    →连续下降3日，累计变化=90-110=-20(从d1的110到d4的90)。**since=第一个下降日=d2**(105那天，'自d2起连续下降')，不是d1(110那天是下降前的基准日，那天是上涨的)。"""
    d = tdays("2026-09-21", 5)
    r = hs.consecutive_run(pts(d, [100, 110, 105, 95, 90]))
    assert r["direction"] == "down" and r["days"] == 3 and r["total"] == -20 and r["since"] == d[2] and r["contract"] == "M2701", r
    r2 = hs.consecutive_run(pts(d, [100, 90, 95, 105, 110]))
    assert r2["direction"] == "up" and r2["days"] == 3 and r2["total"] == 20 and r2["since"] == d[2], r2
    ok("★连续N日手算：[100,110,105,95,90]→连续下降3日、累计-20(从110到90)；[100,90,95,105,110]→连续上升3日、累计+20")


def test_consecutive_run_stops_at_a_flat_day():
    d = tdays("2026-09-21", 4)
    r = hs.consecutive_run(pts(d, [100, 110, 110, 120]))
    assert r["direction"] == "up" and r["days"] == 1 and r["total"] == 10, "最新一天上升，前一天打平→停：连续1日"
    assert hs.consecutive_run(pts(d, [100, 110, 120, 120])) == {"direction": None, "days": 0, "total": 0, "since": None, "contract": "M2701"}, "最新一天打平：没有连续方向"
    ok("打平的一天打断连续；最新一天打平=没有方向(days=0)")


def test_consecutive_run_never_crosses_a_contract_change():
    """★主力合约换月：M2701最后3天净持仓150000,152000,153000，换成M2705后头两天只有8000,7500。
    若跨合约算，会得到'连续下降'或巨大的假变化。必须只在最新合约(M2705)内算：8000→7500下降1日，不把M2701的点算进来。"""
    d = tdays("2026-12-01", 5)
    p = pts(d[:3], [150000, 152000, 153000], "M2701") + pts(d[3:], [8000, 7500], "M2705")
    r = hs.consecutive_run(p)
    assert r["contract"] == "M2705" and r["direction"] == "down" and r["days"] == 1 and r["total"] == -500, r
    ok("★主力合约换月：只在最新合约(M2705)内算连续——8000→7500下降1日、累计-500；不拿M2701的15.3万去减M2705的8000(那会得到-14.5万的假变化)")


def test_consecutive_run_breaks_when_a_trading_day_is_missing():
    """相邻两点之间缺了交易日(采集失败)：不能当成'连续'。09-22(周二)后直接09-24(周四)，中间09-23是交易日却没有点。"""
    p = pts(["2026-09-21", "2026-09-22", "2026-09-24", "2026-09-25"], [100, 110, 105, 95])
    r = hs.consecutive_run(p)
    assert r["direction"] == "down" and r["days"] == 1 and r["total"] == -10, r      # 09-25(95)<09-24(105)降；09-24与09-22之间缺09-23→断
    ok("★缺了交易日就断开：09-22→09-24之间缺09-23，连续只算最后1日(105→95)，不把缺日前的点接上")


def test_consecutive_run_skips_weekends_and_holidays_but_not_trading_days():
    """周五→下周一是相邻交易日(周末不算缺)；国庆休市(10-01~10-07)后的第一个交易日10-08与休市前最后一个交易日09-30也是相邻的。"""
    p = pts(["2026-09-25", "2026-09-28"], [100, 90])
    assert hs.consecutive_run(p)["days"] == 1, "周五→周一相邻"
    p2 = pts(["2026-09-29", "2026-09-30", "2026-10-08"], [100, 110, 120])
    r = hs.consecutive_run(p2)
    assert r["direction"] == "up" and r["days"] == 2 and r["total"] == 20, r
    ok("周五→周一、国庆休市(09-30→10-08)都算相邻交易日，不误断")


def test_consecutive_run_edge_cases():
    assert hs.consecutive_run([]) == {"direction": None, "days": 0, "total": 0, "since": None, "contract": None}
    one = hs.consecutive_run(pts(tdays("2026-09-21", 1), [100]))
    assert one["days"] == 0 and one["direction"] is None and one["contract"] == "M2701", "只有1个点：没法算变化"
    bad = [{"d": "2026-09-21", "v": 100, "x": {"contract": "M2701"}}, {"d": "乱码", "v": 5}, {"d": "2026-09-22", "v": None}, {"d": "2026-09-23", "v": 90, "x": {"contract": "M2701"}}]
    r = hs.consecutive_run(bad)
    # 坏点(日期乱码/v为None)被过滤后剩09-21(100)和09-23(90)，二者之间缺了交易日09-22 → 不相邻 → 没有可算的连续变化
    assert r == {"direction": None, "days": 0, "total": 0, "since": None, "contract": "M2701"}, r
    unsorted = pts(["2026-09-23", "2026-09-21", "2026-09-22"], [90, 100, 110])
    assert hs.consecutive_run(unsorted)["direction"] == "down" and hs.consecutive_run(unsorted)["days"] == 1, "乱序输入先按日期排序：100,110,90→最新降1日"
    ok("边界：空/只有1个点/坏点(日期乱码、v为None)不崩；乱序输入先按日期排")


# ===================== 近N日变化 =====================
def test_change_over_last_n_trading_days_within_the_same_contract():
    """手算：6个相邻交易日净持仓 100,102,98,105,110,120(同一合约，d0..d5)。
    较5个交易日前：往前数第5个点=d0(100)→120-100=+20。较3个交易日前：窗口是最后4个点[98,105,110,120]，起点=d2(98)→120-98=+22
    (上一版我写成+15是数错了位置：105是d3，对应n=2；n=3的起点是d2的98)。n=2→起点d3(105)→+15。
    窗口里换了合约/缺了交易日/点数不够 → None。"""
    d = tdays("2026-09-21", 6)
    p = pts(d, [100, 102, 98, 105, 110, 120])
    assert hs.change_over(p, 5) == {"change": 20, "from": d[0], "to": d[5], "contract": "M2701", "n": 5}, hs.change_over(p, 5)
    assert hs.change_over(p, 3) == {"change": 22, "from": d[2], "to": d[5], "contract": "M2701", "n": 3}, hs.change_over(p, 3)
    assert hs.change_over(p, 2)["change"] == 15 and hs.change_over(p, 1)["change"] == 10
    assert hs.change_over(p, 6) is None, "只有6个点，往前6个交易日需要7个点"
    p2 = pts(d[:3], [100, 102, 98], "M2701") + pts(d[3:], [105, 110, 120], "M2705")
    assert hs.change_over(p2, 5) is None, "★窗口里换了合约：不可比，返回None(不给一个跨合约的假变化)"
    p3 = pts(d[:2] + d[3:], [100, 102, 105, 110, 120])
    assert hs.change_over(p3, 4) is None, "窗口里缺了一个交易日：None"
    ok("★近N个交易日变化手算(n=5:+20, n=3:+22, n=2:+15, n=1:+10)；点数不够/窗口里换合约/缺交易日→None，不给跨合约或跨缺口的假变化")


# ===================== 累积(经update_and_attach) =====================
MC = {"available": True, "mainContract": {"key": "jan", "symbol": "M2701", "gross": 867214}, "date": "2026-09-30",
      "members": {"高盛期货": {"net": 152092, "change": 2181, "side": "long", "rank": 1, "foreign": True}, "摩根大通": {"net": -9739, "change": -7014, "side": "short", "rank": 7, "foreign": True},
                  "瑞银期货": {"net": 11489, "change": 829, "side": "long", "rank": 12, "foreign": True}, "中粮期货": {"net": -482209, "change": 5234, "side": "short", "rank": 1, "foreign": False},
                  "国投期货": {"net": -226091, "change": -2906, "side": "short", "rank": 2, "foreign": False}},
      "industry": {"net": -708300, "change": 2328, "changePct": 0.33}, "cftc": {"net": 191087.0}, "state": {"code": "crowded"}}


def test_update_and_attach_records_one_point_per_member_with_the_contract_code():
    with Tmp() as d:
        res = {"marketCapital": MC}
        hs.update_and_attach(res, base_dir=d)
        want = {"capital_gs_net": 152092, "capital_jpm_net": -9739, "capital_ubs_net": 11489, "capital_zl_net": -482209, "capital_gt_net": -226091}
        for k, v in want.items():
            p = hs.load_series(k, d)["points"]
            assert len(p) == 1 and p[0]["d"] == "2026-09-30" and p[0]["v"] == v and p[0]["x"]["contract"] == "M2701", (k, p)
        assert hs.load_series("capital_gs_net", d)["points"][0]["x"]["change"] == 2181, "源数据的当日变化也存(x.change)，用来和自己算的相邻差核对"
        assert hs.load_series("capital_jpm_net", d)["points"][0]["x"]["change"] == -7014
    ok("★累积：5个席位各记1个点(日期=龙虎榜数据日期，值=净持仓，x.contract=M2701，x.change=源数据当日变化)；摩根大通净空记负数")


def test_member_not_in_the_ranking_records_nothing_not_zero():
    """未进榜(net=None)不记点——记0会让'连续N日'误以为持仓降到了0。"""
    mc = {**MC, "members": {**MC["members"], "瑞银期货": {"net": None, "change": None, "side": None, "rank": None, "foreign": True}}}
    with Tmp() as d:
        hs.update_and_attach({"marketCapital": mc}, base_dir=d)
        assert hs.load_series("capital_ubs_net", d)["points"] == [], "未进榜：不记点"
        assert len(hs.load_series("capital_gs_net", d)["points"]) == 1
    ok("席位未进榜(net=None)：不记点(记0会让连续N日误以为降到了0)；其余席位照常")


def test_unavailable_or_missing_market_capital_records_nothing():
    for mc in (None, {"available": False}, {"available": True, "date": None, "members": MC["members"], "mainContract": MC["mainContract"]}, {"available": True, "date": "2026-09-30", "members": MC["members"], "mainContract": None}):
        with Tmp() as d:
            hs.update_and_attach({"marketCapital": mc} if mc is not None else {}, base_dir=d)
            assert all(hs.load_series(k, d)["points"] == [] for k in ("capital_gs_net", "capital_zl_net")), mc
    ok("marketCapital缺失/不可用/没有日期/没有主力合约：什么都不记")


def test_same_day_rerun_is_idempotent_and_contract_change_adds_a_new_point_on_a_new_day():
    with Tmp() as d:
        hs.update_and_attach({"marketCapital": MC}, base_dir=d)
        hs.update_and_attach({"marketCapital": MC}, base_dir=d)
        assert len(hs.load_series("capital_gs_net", d)["points"]) == 1, "同一天重复运行不重复"
        mc2 = {**MC, "date": "2026-10-08", "mainContract": {"key": "may", "symbol": "M2705", "gross": 100}, "members": {**MC["members"], "高盛期货": {**MC["members"]["高盛期货"], "net": 8000, "change": 100}}}
        hs.update_and_attach({"marketCapital": mc2}, base_dir=d)
        p = hs.load_series("capital_gs_net", d)["points"]
        assert [(x["d"], x["v"], x["x"]["contract"]) for x in p] == [("2026-09-30", 152092, "M2701"), ("2026-10-08", 8000, "M2705")]
    ok("同一天重复运行不重复；换主力合约后新的一天记新点并带新合约代码")


def test_streak_is_attached_to_the_members_after_recording():
    """记录之后把'连续N日/近N日变化'挂回marketCapital.members[席位].history，页面直接展示。
    手算：高盛前4个交易日(同一合约) 100000,101000,102000,103000，今天(第5个交易日)104000 → 连续上升4日、累计+4000(从100000到104000)；
    累积点数n=5、历史起点=第1个交易日；往前5个交易日需要6个点，只有5个→change5=None。"""
    with Tmp() as d:
        days = tdays("2026-09-23", 5)
        hs.record_points("capital_gs_net", pts(days[:4], [100000, 101000, 102000, 103000]), d)
        mc = {**MC, "date": days[4], "members": {**MC["members"], "高盛期货": {**MC["members"]["高盛期货"], "net": 104000, "change": 1000}}}
        res = {"marketCapital": mc}
        hs.update_and_attach(res, base_dir=d)
        h = res["marketCapital"]["members"]["高盛期货"]["history"]
        assert h["run"]["direction"] == "up" and h["run"]["days"] == 4 and h["run"]["total"] == 4000 and h["run"]["contract"] == "M2701", h
        assert h["n"] == 5 and h["since"] == days[0], h
        assert h["change5"] is None, "只有5个点，往前5个交易日需要6个点"
    ok("★记录后把连续N日/累积点数挂回members.history：高盛连续上升4日、累计+4000；点数不够的窗口=None")


def test_history_attach_never_breaks_the_main_flow():
    mc = {**MC, "members": None}
    with Tmp() as d:
        res = {"marketCapital": mc}
        hs.update_and_attach(res, base_dir=d)      # 不抛异常
    ok("members异常(None)：不抛异常、不拖垮主流程")


# ===================== CFTC：156周回填 =====================
def cftc_rows(n, start=date(2023, 10, 3)):
    """n周的CFTC行(周二，按report_date DESC)：long=100000+1000*i，short=10000(i是从旧到新的序号)。净多=90000+1000*i。"""
    rows = []
    for i in range(n):
        d = start + timedelta(weeks=i)
        rows.append({"report_date_as_yyyy_mm_dd": d.isoformat() + "T00:00:00.000", "m_money_positions_long_all": str(100000 + 1000 * i), "m_money_positions_short_all": "10000",
                     "change_in_m_money_long_all": "1000", "change_in_m_money_short_all": "0", "market_and_exchange_names": "SOYBEAN MEAL - CHICAGO BOARD OF TRADE"})
    return list(reversed(rows))


def test_cftc_parse_history_returns_every_week():
    h = fd.cftc_history_points(cftc_rows(156))
    assert len(h) == 156 and h[0]["d"] == "2023-10-03" and h[-1]["d"] == (date(2023, 10, 3) + timedelta(weeks=155)).isoformat(), (h[0], h[-1])
    assert h[0]["v"] == 90000.0 and h[-1]["v"] == 90000.0 + 155 * 1000 and h[0]["x"] == {"long": 100000.0, "short": 10000.0}, h[0]
    assert [p["d"] for p in h] == sorted(p["d"] for p in h), "按日期升序"
    ok("★CFTC明细→历史点：156周全部带出，d=报告日期(周二)、v=净多(多−空)、x里是多/空；升序。手算首周90000、末周90000+155000")


def test_cftc_parse_skips_bad_rows_without_losing_the_rest():
    rows = cftc_rows(10)
    rows[3] = {"report_date_as_yyyy_mm_dd": "2024-01-02T00:00:00.000", "m_money_positions_long_all": "x", "m_money_positions_short_all": "1"}
    rows[5] = {"m_money_positions_long_all": "1", "m_money_positions_short_all": "1"}
    h = fd.cftc_history_points(rows)
    assert len(h) == 8, len(h)
    ok("个别行解析失败/没有日期：跳过，其余照常(10行→8个点)")


def test_cftc_history_is_recorded_in_full_by_update_and_attach():
    """每次抓取都顺带把156周补齐(同recentWeeks机制)——第一次运行就有156周历史，不用等。"""
    with Tmp() as d:
        res = {"cftcManagedMoney": {"available": True, "reportDate": "2026-09-22", "netPosition": 191087.0, "history": fd.cftc_history_points(cftc_rows(156))}}
        hs.update_and_attach(res, base_dir=d)
        s = hs.load_series("cftc_mm_net", d)["points"]
        assert len(s) == 156 and s[0]["d"] == "2023-10-03" and s[-1]["d"] == "2026-09-22", (len(s), s[0]["d"], s[-1]["d"])
        hs.update_and_attach(res, base_dir=d)
        assert len(hs.load_series("cftc_mm_net", d)["points"]) == 156, "重复运行幂等"
    ok("★CFTC：第一次抓取就记下156周(2023-10-03~2026-09-22)，重复运行幂等")


def test_cftc_without_history_field_still_works():
    with Tmp() as d:
        hs.update_and_attach({"cftcManagedMoney": {"available": True, "reportDate": "2026-09-22", "netPosition": 191087.0}}, base_dir=d)
        s = hs.load_series("cftc_mm_net", d)["points"]
        assert [(p["d"], p["v"]) for p in s] == [("2026-09-22", 191087.0)], "没有history明细(旧版结果)：至少记最新一周"
    ok("没有history明细的旧版结果：至少记最新一周，不崩")


# ===================== 变异检查补的三个盲区 =====================
def test_bad_value_point_with_the_same_contract_is_filtered_on_its_own():
    """★变异检查发现：坏点(v=None)原来没有带合约代码，会被"合约不一致"这道防线先断开——掩盖了"过滤v非数字"这道防线是否存在(冗余防护)。
    让坏点带上和它两边相同的合约代码，只剩"过滤非数字"这一道防线。
    手算：09-21(100)、09-22(v=None，同合约)、09-23(90)：坏点被过滤后只剩09-21和09-23，二者之间缺了交易日09-22→不相邻→没有连续变化。
    若不过滤：09-22的v=None参与比较(None-100会抛TypeError)，或被当成有效点。"""
    p = [{"d": "2026-09-21", "v": 100, "x": {"contract": "M2701"}}, {"d": "2026-09-22", "v": None, "x": {"contract": "M2701"}}, {"d": "2026-09-23", "v": 90, "x": {"contract": "M2701"}}]
    assert hs.consecutive_run(p) == {"direction": None, "days": 0, "total": 0, "since": None, "contract": "M2701"}
    assert hs.change_over(p, 1) is None, "过滤后只剩2个点但中间缺交易日"
    p2 = [{"d": "2026-09-21", "v": 100, "x": {"contract": "M2701"}}, {"d": "2026-09-22", "v": "abc", "x": {"contract": "M2701"}}, {"d": "2026-09-23", "v": True, "x": {"contract": "M2701"}}, {"d": "2026-09-24", "v": 90, "x": {"contract": "M2701"}}]
    assert hs.consecutive_run(p2)["days"] == 0, "字符串/布尔也不是有效数值"
    ok("★坏点(v=None/字符串/布尔，且带同样的合约代码)被过滤：不抛TypeError、不当有效点(之前被'合约不一致'那道防线掩盖了)")


def test_record_capital_itself_skips_a_member_without_net_not_relying_on_the_merge_filter():
    """★变异检查发现：把net=None交给record_points，它的merge_points也会丢掉v非数字的点，所以"未进榜不记点"被两道防线中的另一道掩盖。
    直接打桩record_points，断言_record_capital自己没有为未进榜的席位调用它。"""
    called = []
    real = hs.record_points
    def spy(key, new_points, base_dir=None):
        called.append((key, new_points))
        return real(key, new_points, base_dir)
    hs.record_points = spy
    try:
        mc = {**MC, "members": {**MC["members"], "瑞银期货": {"net": None, "change": None, "side": None, "rank": None, "foreign": True}}}
        with Tmp() as d:
            hs.update_and_attach({"marketCapital": mc}, base_dir=d)
    finally:
        hs.record_points = real
    keys = [k for k, _ in called if k.startswith("capital_")]
    assert "capital_ubs_net" not in keys and set(keys) == {"capital_gs_net", "capital_jpm_net", "capital_zl_net", "capital_gt_net"}, keys
    zero = {**MC, "members": {**MC["members"], "瑞银期货": {"net": 0, "change": 0, "side": "long", "rank": 12, "foreign": True}}}
    with Tmp() as d:
        hs.update_and_attach({"marketCapital": zero}, base_dir=d)
        assert hs.load_series("capital_ubs_net", d)["points"][0]["v"] == 0, "★真实的0(净持仓恰好为0)是有效点，要记；None才是未进榜"
    ok("★_record_capital自己跳过未进榜的席位(不依赖record_points的过滤)；净持仓恰好为0是有效点要记，None才不记")


def test_fetch_cftc_managed_money_really_returns_the_156_week_history():
    """★变异检查发现：只测了cftc_history_points函数本身，没测fetch_cftc_managed_money的返回值里确实带了history——函数对、没接上就等于没做。
    打桩fetch_json_debug返回156周行，断言返回值里history有156个点、升序、最新一周=netPosition。"""
    rows = cftc_rows(156)
    old = fd.fetch_json_debug
    fd.fetch_json_debug = lambda url, *a, **k: (rows, {})
    try:
        r = fd.fetch_cftc_managed_money()
    finally:
        fd.fetch_json_debug = old
    assert r["available"] is True and len(r["history"]) == 156, len(r.get("history", []))
    assert r["history"][-1]["d"] == r["reportDate"] and r["history"][-1]["v"] == r["netPosition"], (r["history"][-1], r["reportDate"], r["netPosition"])
    assert r["history"][0]["d"] < r["history"][-1]["d"], "升序"
    assert r["historyWeeksUsed"] == 156
    ok("★fetch_cftc_managed_money的返回值里带了156周history(最新一周=reportDate/netPosition)——接线没断")


# ===================== CFTC：用累积的156周自己重算，核对来源给的分位和连续周数 =====================
def test_cftc_stored_history_reproduces_the_source_percentile_and_streak():
    """来源(fetch_cftc_managed_money)算的historyPercentile=历史里<=当前净多的占比(含并列)，streakWeeks=从最新一周往回净多连续同向变化的周数。
    用存下的156周按同一口径重算，必须与来源给的值逐项一致——这是对CFTC数据的独立自检(不一致=解析或存储有问题)。
    构造：净多每周+1000(单调上升156周) → 当前是历史最高 → 分位=156/156=100.0；连续上升周数=155(156个点有155个相邻差，全为正)。"""
    rows = cftc_rows(156)
    old = fd.fetch_json_debug
    fd.fetch_json_debug = lambda url, *a, **k: (rows, {})
    try:
        r = fd.fetch_cftc_managed_money()
    finally:
        fd.fetch_json_debug = old
    with Tmp() as d:
        hs.update_and_attach({"cftcManagedMoney": r}, base_dir=d)
        pts = hs.load_series("cftc_mm_net", d)["points"]
    vals = [p["v"] for p in pts]
    pct = round(sum(1 for v in vals if v <= vals[-1]) / len(vals) * 100, 1)
    assert pct == r["historyPercentile"] == 100.0, (pct, r["historyPercentile"])
    streak, direction = 0, None
    for i in range(len(vals) - 1, 0, -1):
        diff = vals[i] - vals[i - 1]
        step = "up" if diff > 0 else "down" if diff < 0 else None
        if direction is None:
            if step is None:
                break
            direction, streak = step, 1
        elif step == direction:
            streak += 1
        else:
            break
    assert (streak, direction) == (r["streakWeeks"], r["streakDirection"]) == (155, "up"), (streak, direction, r["streakWeeks"], r["streakDirection"])
    ok("★自检：用存下的156周重算，分位(100.0)和连续周数(155周上升)与来源给的完全一致——CFTC的解析和存储互相印证")


def test_cftc_stored_history_percentile_mid_series():
    """非单调的情形再核对一次：净多 [10,30,20,40,25]，当前25：历史里<=25的有10,20,25 → 3/5=60.0%。(只有5个点，来源要求>=52周才给分位，这里只验证我这边按同一口径的重算公式)"""
    vals = [10, 30, 20, 40, 25]
    assert round(sum(1 for v in vals if v <= vals[-1]) / len(vals) * 100, 1) == 60.0
    ok("分位公式手算：[10,30,20,40,25]，当前25 → 历史里<=25的有3个/5=60.0%")


def test_cftc_history_detail_is_removed_from_latest_json_after_recording():
    """156周明细(约12KB)记进data/history/cftc_mm_net.json之后，不需要留在latest.json里(页面不用它，每小时都重复写一遍)——记完就从result里删掉。
    但摘要字段(netPosition/streakWeeks/historyPercentile…)必须保留。"""
    with Tmp() as d:
        res = {"cftcManagedMoney": {"available": True, "reportDate": "2026-09-22", "netPosition": 191087.0, "streakWeeks": 6, "historyPercentile": 100.0, "history": fd.cftc_history_points(cftc_rows(156))}}
        hs.update_and_attach(res, base_dir=d)
        assert "history" not in res["cftcManagedMoney"], "明细记完就删，latest.json保持精简"
        assert res["cftcManagedMoney"]["netPosition"] == 191087.0 and res["cftcManagedMoney"]["streakWeeks"] == 6 and res["cftcManagedMoney"]["historyPercentile"] == 100.0, "摘要字段保留"
        assert len(hs.load_series("cftc_mm_net", d)["points"]) == 156, "但历史已经存进序列文件"
    ok("★记完156周后明细从latest.json里删掉(省约12KB/次)，摘要字段保留，序列文件里有完整156周")


def test_marketcapital_members_history_stays_small():
    """members[名].history只放摘要(n/since/run/change5/change20)，不放全部点——累积几年也不会让latest.json变大。"""
    with Tmp() as d:
        days = tdays("2026-01-05", 300)
        hs.record_points("capital_gs_net", pts(days, [100000 + 10 * i for i in range(300)]), d)
        mc = {**MC, "date": "2026-12-31"}
        res = {"marketCapital": mc}
        hs.update_and_attach(res, base_dir=d)
        h = res["marketCapital"]["members"]["高盛期货"]["history"]
        assert set(h) == {"n", "since", "run", "change5", "change20"}, set(h)
        import json
        assert len(json.dumps(h, ensure_ascii=False)) < 600, len(json.dumps(h, ensure_ascii=False))
    ok("members.history只有5个摘要字段、不随累积点数增长(300个点也<600字节)")


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
