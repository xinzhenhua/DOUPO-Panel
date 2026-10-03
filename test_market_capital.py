# -*- coding: utf-8 -*-
"""资金面(龙虎榜+CFTC)：主力合约、席位净持仓、外资多头拥挤度状态(fetch_data.build_market_capital)。运行：python3 test_market_capital.py
数据是2026-09-30真实龙虎榜(东方财富)和CFTC(2026-09-22)的节选；期望值全部手算。"""
import os, sys, json, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def row(rank, name, value, change, foreign=False):
    return {"rank": rank, "name": name, "value": value, "change": change, "isForeign": foreign}


# ===== 真实数据节选(2026-09-30) =====
M2701 = {"available": True, "symbol": "M2701", "date": "2026-09-30", "tables": {
    "netLong": [row(1, "高盛期货", 152092, 2181, True), row(2, "中信期货", 136049, -16621), row(3, "国泰君安", 133425, -1533), row(12, "瑞银期货", 11489, 829, True)],
    "netShort": [row(1, "中粮期货", 482209, -5234), row(2, "国投期货", 226091, 2906), row(3, "广发期货", 77667, -1063), row(7, "摩根大通", 9739, 7014, True)],
    "longUp": [], "longDown": []}}
M2705 = {"available": True, "symbol": "M2705", "date": "2026-09-30", "tables": {"netLong": [row(1, "兴业期货", 5200, 10)], "netShort": [row(1, "中粮期货", 61000, 300)], "longUp": [], "longDown": []}}
M2709 = {"available": True, "symbol": "M2709", "date": "2026-09-30", "tables": {"netLong": [row(1, "兴业期货", 1669, 3), row(8, "国投期货", 557, 288)], "netShort": [row(1, "中粮期货", 3754, 392), row(2, "五矿期货", 2879, 180)], "longUp": [], "longDown": []}}
CFTC = {"available": True, "reportDate": "2026-09-22", "netPosition": 191087.0, "netChange": 7976.0, "streakWeeks": 6, "streakDirection": "up", "historyPercentile": 100.0, "historyWeeksUsed": 156}


def test_main_contract_is_the_one_with_the_real_positions_not_the_selected_one():
    """★9月合约的龙虎榜几乎是空的(前几名只有几百~几千手)，而M2701才有真实规模。外资/产业分析必须固定看主力合约，不能跟着页面选中的合约走。
    手算：每个合约'净空头榜'持仓合计 → M2701: 482209+226091+77667+9739=795706；M2705: 61000；M2709: 3754+2879=6633 → 主力=M2701。"""
    mc = fd.build_market_capital({"sep": M2709, "may": M2705, "jan": M2701}, CFTC)
    assert mc["mainContract"] == {"key": "jan", "symbol": "M2701", "gross": 795706}, mc["mainContract"]
    mc2 = fd.build_market_capital({"sep": M2701, "may": M2705, "jan": M2709}, CFTC)
    assert mc2["mainContract"]["key"] == "sep" and mc2["mainContract"]["symbol"] == "M2701", "主力合约由数据决定，不由合约在字典里的位置决定"
    ok("★主力合约=净空头榜持仓合计最大的(手算M2701=795706 vs M2705=61000 vs M2709=6633)，不跟页面选中的合约走")


def test_member_net_positions_use_the_right_table_and_sign():
    """净持仓：在netLong表里=+value(净多)；在netShort表里=-value(净空)；两张表都没有=未进榜(None)。
    真实数据：高盛期货netLong 152092(+2181)；摩根大通在netShort里9739(+7014，净空增加)→净持仓=-9739、日变化=-7014(净多头减少7014)；瑞银期货+11489(+829)；
    中粮期货netShort 482209(-5234，净空减少)→净持仓=-482209、日变化=+5234；国投期货-226091、日变化=-2906。"""
    mc = fd.build_market_capital({"sep": M2709, "may": M2705, "jan": M2701}, CFTC)
    m = mc["members"]
    assert (m["高盛期货"]["net"], m["高盛期货"]["change"], m["高盛期货"]["side"]) == (152092, 2181, "long")
    assert (m["摩根大通"]["net"], m["摩根大通"]["change"], m["摩根大通"]["side"]) == (-9739, -7014, "short"), m["摩根大通"]
    assert (m["瑞银期货"]["net"], m["瑞银期货"]["change"]) == (11489, 829)
    assert (m["中粮期货"]["net"], m["中粮期货"]["change"]) == (-482209, 5234), "净空减少5234=净持仓变化+5234"
    assert (m["国投期货"]["net"], m["国投期货"]["change"]) == (-226091, -2906)
    assert m["高盛期货"]["foreign"] is True and m["摩根大通"]["foreign"] is True and m["中粮期货"]["foreign"] is False
    ok("★席位净持仓符号手算：高盛+152092(+2181)、摩根大通-9739(净空增加7014→变化-7014)、中粮-482209(净空减少5234→变化+5234)")


def test_member_not_in_either_table_is_unknown_not_zero():
    mc = fd.build_market_capital({"sep": M2709, "may": M2705, "jan": {**M2701, "tables": {**M2701["tables"], "netLong": [row(2, "中信期货", 136049, -16621)]}}}, CFTC)
    assert mc["members"]["高盛期货"]["net"] is None and mc["members"]["高盛期货"]["side"] is None, "两张净持仓榜里都没有=未进榜，不是0"
    ok("席位不在任何净持仓榜里：net=None(未进榜)，不当成0")


def test_unavailable_contract_is_never_the_main_contract_even_with_stale_big_numbers():
    """★变异检查发现：没有'某个合约抓取失败(available=False)但还留着很大的数字'的用例。失败的合约不能被选成主力。
    手算：把M2705改成available=False但净空头榜持仓合计9,999,999(远大于M2701的795706)——必须仍然选M2701。"""
    huge = {"available": False, "symbol": "M2705", "date": "2026-09-30", "tables": {"netLong": [], "netShort": [row(1, "中粮期货", 9999999, 0)], "longUp": [], "longDown": []}}
    mc = fd.build_market_capital({"sep": M2709, "may": huge, "jan": M2701}, CFTC)
    assert mc["mainContract"]["symbol"] == "M2701" and mc["mainContract"]["gross"] == 795706, mc["mainContract"]
    ok("★抓取失败(available=False)的合约，即使残留着更大的数字(999万手)也不能当主力：仍选M2701(795706)")


def test_row_with_null_value_is_not_in_the_ranking():
    """★真实数据里就有value=null的行(如东证期货longUp rank19)。高盛那一行value为null：当作未进榜(net=None)，不能当0、也不能算出None*符号崩溃。
    手算：高盛netLong行value=None → 去netShort找也没有 → net=None、side=None；此时CFTC分位=100但高盛未知 → 只满足CFTC条件 → elevated，label写依据是CFTC。"""
    t = {"netLong": [row(1, "高盛期货", None, 2181, True), row(2, "中信期货", 136049, -16621)], "netShort": [row(1, "中粮期货", 482209, -5234)], "longUp": [], "longDown": []}
    mc = fd.build_market_capital({"sep": M2709, "may": M2705, "jan": {"available": True, "symbol": "M2701", "date": "2026-09-30", "tables": t}}, CFTC)
    gs = mc["members"]["高盛期货"]
    assert gs["net"] is None and gs["side"] is None and gs["change"] is None, gs
    assert mc["state"]["code"] == "elevated" and "CFTC" in mc["state"]["label"], mc["state"]
    ok("★value=null的行视为未进榜(net=None)，不崩、不当0；此时状态只靠CFTC(elevated，label写依据是CFTC)")


def test_industry_total_and_cftc_are_carried_through():
    mc = fd.build_market_capital({"sep": M2709, "may": M2705, "jan": M2701}, CFTC)
    ind = mc["industry"]
    assert ind["net"] == -482209 + -226091 == -708300 and ind["change"] == 5234 - 2906 == 2328, ind
    assert ind["changePct"] == round(2328 / 708300 * 100, 2) == 0.33, ind
    c = mc["cftc"]
    assert (c["net"], c["netChange"], c["streakWeeks"], c["streakDirection"], c["percentile"], c["weeksUsed"], c["reportDate"]) == (191087.0, 7976.0, 6, "up", 100.0, 156, "2026-09-22")
    ok("产业合计(手算：中粮-482209+国投-226091=-708300，变化+5234-2906=+2328=净空减少0.33%)；CFTC字段原样带出")


# ===== 状态(阈值是文档里的经验值，暂定，没有回测) =====
def state(gs_net, gs_chg, pct, streak_dir="up"):
    t = {"netLong": [row(1, "高盛期货", gs_net, gs_chg, True)] if gs_net is not None else [], "netShort": [row(1, "中粮期货", 400000, 0)], "longUp": [], "longDown": []}
    mc = fd.build_market_capital({"sep": M2709, "may": M2705, "jan": {"available": True, "symbol": "M2701", "date": "2026-09-30", "tables": t}},
                                 None if pct is None else {**CFTC, "historyPercentile": pct, "streakDirection": streak_dir})
    return mc["state"]


def test_state_levels_hand_calculated_with_the_document_thresholds():
    """文档阈值(暂定)：高盛净多≥12万手=高位；CFTC历史分位≥90=拥挤；高盛单日减仓≥2万手=撤退预警。
    当前真实读数：高盛152092(≥12万)、CFTC分位100(≥90) → 两个条件都满足 → 'crowded'(外资多头拥挤)。"""
    assert fd.CAPITAL_GS_HIGH == 120000 and fd.CAPITAL_CFTC_CROWDED_PCT == 90 and fd.CAPITAL_GS_RETREAT_CHG == -20000
    s = state(152092, 2181, 100.0)
    assert s["code"] == "crowded" and s["level"] == "red" and s["label"] == "外资多头拥挤", s
    assert state(152092, 2181, 60.0)["code"] == "elevated" and state(152092, 2181, 60.0)["level"] == "yellow", "只有高盛高位，CFTC不拥挤→外资多头高位"
    assert state(80000, 500, 95.0)["code"] == "elevated", "只有CFTC拥挤，高盛不高→外资多头高位"
    assert state(80000, 500, 50.0)["code"] == "neutral" and state(80000, 500, 50.0)["level"] == "green"
    ok("★状态(文档阈值，手算)：高盛15.2万+CFTC100分位=拥挤🔴；只满足一个=高位🟡；都不满足=中性🟢")


def test_state_boundaries_are_inclusive_as_documented():
    assert state(120000, 0, 50.0)["code"] == "elevated", "恰好12万手算高位(≥)"
    assert state(119999, 0, 50.0)["code"] == "neutral"
    assert state(80000, 0, 90.0)["code"] == "elevated", "CFTC恰好90分位算拥挤(≥)"
    assert state(80000, 0, 89.9)["code"] == "neutral"
    assert state(150000, -20000, 50.0)["code"] == "retreat", "单日减仓恰好2万手算撤退预警(≤-2万)"
    assert state(150000, -19999, 50.0)["code"] == "elevated"
    ok("★阈值边界：高盛恰好12万=高位、CFTC恰好90=拥挤、单日恰好减仓2万=撤退预警(都含边界)；差1就不算")


def test_retreat_takes_priority_over_crowded():
    """文档：高盛单日减仓超2万手→预警。即使持仓还在高位、CFTC也拥挤，当天大幅减仓这个更新的信息应该优先显示。"""
    s = state(152092, -25000, 100.0)
    assert s["code"] == "retreat" and s["level"] == "yellow" and "减仓" in s["label"], s
    ok("单日大幅减仓优先于'拥挤'(更新的信息)：高盛15.2万、CFTC100分位、但当天减仓2.5万→撤退预警")


def test_state_when_data_is_missing_never_claims_neutral():
    """★数据缺失时不能写'中性'(那是在没有信息的情况下给出结论)。"""
    # 没有高盛数据、但CFTC到顶(100分位)：CFTC拥挤是一个独立的、真实的信息，所以是elevated(只满足一个条件)；但label必须写明依据只有CFTC(高盛那一半不知道)，不能写"外资多头高位"
    s1 = state(None, None, 100.0)
    assert s1["code"] == "elevated" and s1["level"] == "yellow" and "CFTC" in s1["label"] and "高盛" not in s1["label"].replace("高盛未进榜", ""), s1
    s0 = state(None, None, 50.0)
    assert s0["code"] == "unknown" and "数据不足" in s0["label"], "没有高盛数据、CFTC也不拥挤：无法判断→unknown，不写中性"
    s = state(None, None, None)
    assert s["code"] == "unknown" and s["level"] == "gray" and "数据不足" in s["label"], s
    mc = fd.build_market_capital({"sep": None, "may": None, "jan": None}, None)
    assert mc["available"] is False and mc["state"]["code"] == "unknown"
    ok("数据缺失：没有高盛也没有CFTC→unknown/灰色/数据不足，绝不写中性；三个合约都没有数据→available=False")


def test_state_explains_what_it_can_and_cannot_judge():
    s = state(152092, 2181, 100.0)
    assert "拥挤度" in s["note"] and "价格突破" in s["note"] and "美豆" in s["note"] and "未判断" in s["note"], s["note"]
    assert "连续" in s["note"] and "历史" in s["note"], "必须说明：连续N日的规则没有历史数据，现在判断不了"
    # v100写过"已开始累积"但并没有实现(错的)；v101真的实现了每天累积，所以现在的措辞要如实：已开始累积、但刚开始，连续N日要等攒够，不能说"已有足够历史"
    assert "还没有开始累积历史" not in s["note"], "★v101起已经在累积龙虎榜历史了，不能再写'还没有开始累积'"
    assert "v101起每天累积" in s["note"] and "刚开始" in s["note"] and "攒够" in s["note"], s["note"]
    assert "已有足够" not in s["note"] and "历史充足" not in s["note"], "也不能夸大成已有足够历史"
    assert s["thresholdSource"] == "文档经验值，暂定，未回测"
    ok("状态说明：写明只能判断持仓拥挤度，文档要求的价格突破/美豆联动/连续N日目前判断不了(未判断)；阈值来源=文档经验值未回测")


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
