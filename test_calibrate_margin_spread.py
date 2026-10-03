# -*- coding: utf-8 -*-
"""榨利/月差窗口与阈值校准诊断(calibrate_margin_spread.py)。运行：python3 test_calibrate_margin_spread.py
诊断用生产代码自己的history_store.summarize(同一个口径)，回答：年水平有没有漂移、同月样本够不够、80/20规则历史上到底触发多少、
去掉年水平后结论是否一致、逐日数据相当于多少个独立观测。全部期望值手算。"""
import os, sys, json, tempfile, shutil, traceback, statistics
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_store as hs
import calibrate_margin_spread as cm
import backfill_history as bf

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def ramp_years(years=(2023, 2024, 2025, 2026), month=5, n=25, step=10, base=100):
    """每年5月n个点，值=base+step*(年-首年)+k：年水平每年上移step，年内是同样的0..n-1斜坡。"""
    out = []
    for y in years:
        for k in range(n):
            out.append({"d": (date(y, month, 1) + timedelta(days=k)).isoformat(), "v": float(base + step * (y - years[0]) + k)})
    return out


def brute_pct(value, vals):
    less = sum(1 for v in vals if v < value)
    eq = sum(1 for v in vals if v == value)
    return round((less + 0.5 * eq) / len(vals) * 100, 1)


# ===================== 基础 =====================
def test_contract_year_assignment_for_the_three_windows():
    f = cm.contract_year
    assert f("2026-05-10", "sep") == 2026 and f("2026-07-31", "sep") == 2026, "9月合约窗口4-7月：同一日历年"
    assert f("2025-12-15", "may") == 2026 and f("2026-01-10", "may") == 2026 and f("2026-03-31", "may") == 2026, "5月合约窗口12-3月：12月属于下一年的合约"
    assert f("2025-08-01", "jan") == 2026 and f("2025-11-30", "jan") == 2026, "1月合约窗口8-11月：属于下一年的合约"
    ok("合约年归属：9月合约=当年；5月合约的12月→次年；1月合约的8-11月→次年")


def test_level_drift_per_contract_year_hand_calculated():
    """每年0..24斜坡+年水平每年上移10：各年中位数=112, 122, 132, 142(=100+10*i+12)；n=25；四分位=中位±6(24个间隔的q1/q3：k=6和k=18 → 值=base+6/18)。"""
    d = cm.level_drift(ramp_years(), "sep")
    assert [r["year"] for r in d] == [2023, 2024, 2025, 2026] and all(r["n"] == 25 for r in d)
    assert [r["median"] for r in d] == [112.0, 122.0, 132.0, 142.0], [r["median"] for r in d]
    assert d[0]["q1"] == 106.0 and d[0]["q3"] == 118.0, (d[0]["q1"], d[0]["q3"])
    assert d[-1]["median"] - d[0]["median"] == 30.0
    ok("水平漂移：各合约年中位数112/122/132/142(手算)，四分位=中位±6；最新年比最老年高30")


def test_month_sufficiency_flags_months_below_the_rule_minimum():
    pts = ramp_years(n=25) + [{"d": f"2023-06-{k + 1:02d}", "v": 100.0 + k} for k in range(8)] + [{"d": f"2024-06-{k + 1:02d}", "v": 110.0 + k} for k in range(8)]
    r = cm.month_sufficiency(pts, "sep", min_n=20)
    assert r["5"]["byYear"] == {"2023": 25, "2024": 25, "2025": 25, "2026": 25}
    assert r["5"]["refNForLatestYear"] == 75 and r["5"]["ok"] is True, "5月：最新年(2026)的参照=其余3年共75个≥20"
    assert r["6"]["byYear"] == {"2023": 8, "2024": 8} and r["6"]["refNForLatestYear"] == 8 and r["6"]["ok"] is False, "6月只有2年各8个：参照8个<20，不够"
    ok("同月样本充足度：5月(最新年参照75个)够；6月(参照只有8个<20)标出不够")


# ===================== 现行规则历史上的触发频率 =====================
def test_rule_trigger_history_matches_a_brute_force_percentile():
    pts = ramp_years()
    rows = cm.rule_trigger_history(pts, "sep", hi=80, lo=20, min_n=20)
    assert len(rows) == 100
    for r in rows:
        y = int(r["d"][:4])
        same = [p["v"] for p in pts if p["d"][5:7] == r["d"][5:7] and int(p["d"][:4]) != y]
        v = next(p["v"] for p in pts if p["d"] == r["d"])
        assert r["n"] == len(same) == 75 and r["pct"] == brute_pct(v, same), (r["d"], r["pct"], brute_pct(v, same))
        # 信号编码：高端(≥hi)=+1、低端(≤lo)=-1、中间=0(方向无关，只描述"在哪一端")；与榨利/月差各自的多空含义无关
        assert r["signal"] == (1 if r["pct"] >= 80 else -1 if r["pct"] <= 20 else 0), (r["d"], r["pct"], r["signal"])
    ok("每个点的分位与独立的暴力计数完全一致(100个点，参照=同月不同年的75个)")


def test_level_drift_makes_the_latest_year_fire_far_more_than_20_percent():
    """★核心发现的形状：年水平每年上移，现行规则(同月其他年的分位)对最新年几乎总在高端触发、对最老年几乎总在低端触发。
    手算(2026年，值130..154)：k=24(154)比75个参照都大→100%；k=0(130)：小于130的25+20+10=55个、等于的2个→(55+1)/75=74.7%。"""
    rows = cm.rule_trigger_history(ramp_years(), "sep", hi=80, lo=20, min_n=20)
    by = {(r["d"]): r for r in rows}
    assert by["2026-05-25"]["pct"] == 100.0 and by["2026-05-01"]["pct"] == 74.7, (by["2026-05-25"]["pct"], by["2026-05-01"]["pct"])
    assert by["2023-05-01"]["pct"] == 0.0, "最老年最低点比75个参照都小"
    share = cm.trigger_share_by_year(rows)
    assert share["2026"]["high"] > 60 and share["2026"]["low"] == 0.0, share["2026"]
    assert share["2023"]["low"] > 60 and share["2023"]["high"] == 0.0, share["2023"]
    ok("★年水平漂移的后果(手算：2026最高点100%、最低点74.7%；2023最低点0%)：最新年高端触发>60%、最老年低端触发>60%，远偏离理想的20%")


def test_trigger_requires_the_minimum_reference_sample():
    pts = ramp_years(n=25)
    rows = cm.rule_trigger_history(pts, "sep", hi=80, lo=20, min_n=100)
    assert all(r["signal"] is None for r in rows) and all(r["n"] == 75 for r in rows), "参照75个<min_n=100：不给信号(与线上'样本不足不计分'一致)"
    rows2 = cm.rule_trigger_history(pts, "sep", hi=80, lo=20, min_n=75)
    assert all(r["signal"] is not None for r in rows2), "恰好等于min_n：给信号"
    ok("样本门槛：参照数<min_n不给信号(None)；恰好等于min_n给信号")


# ===================== 去掉年水平 =====================
def test_level_adjusted_percentile_removes_the_drift_hand_calculated():
    """去掉各合约年中位数后，4年曲线完全相同(k-12)。点k在其他3年里：小于它的有3k个、等于的3个 → pct=(3k+1.5)/75*100。
    k=0→2.0；k=4→(12+1.5)/75=18.0(≤20触发)；k=5→20.0；k=19→78.0；k=20→82.0(≥80触发)；k=24→98.0。触发恰好各5个点=20%。"""
    adj = cm.rule_trigger_history(ramp_years(), "sep", hi=80, lo=20, min_n=20, adjust_level=True)
    by = {r["d"]: r for r in adj if r["d"].startswith("2026")}
    exp = lambda k: round((3 * k + 1.5) / 75 * 100, 1)
    for k in (0, 4, 5, 19, 20, 24):
        assert by[f"2026-05-{k + 1:02d}"]["pct"] == exp(k), (k, by[f"2026-05-{k + 1:02d}"]["pct"], exp(k))
    share = cm.trigger_share_by_year(adj)
    assert all(abs(share[y]["high"] - 20.0) < 1e-9 and abs(share[y]["low"] - 20.0) < 1e-9 for y in share), share
    ok("★去掉年水平后每年恰好触发20%/20%(手算：k=0→2.0, k=4→18.0, k=20→82.0, k=24→98.0)——漂移消除，规则回到设计的频率")


def test_agreement_between_raw_and_level_adjusted_rules():
    raw = cm.rule_trigger_history(ramp_years(), "sep", hi=80, lo=20, min_n=20)
    adj = cm.rule_trigger_history(ramp_years(), "sep", hi=80, lo=20, min_n=20, adjust_level=True)
    a = cm.agreement(raw, adj)
    assert a["n"] == 100
    same = sum(1 for r, s in zip(raw, adj) if r["signal"] == s["signal"])
    assert a["agreeShare"] == round(same / 100 * 100, 1) and a["agreeShare"] < 100, a
    opp = sum(1 for r, s in zip(raw, adj) if r["signal"] is not None and s["signal"] is not None and r["signal"] * s["signal"] == -1)
    assert a["opposite"] == opp, "方向相反的点数"
    ok("两种口径的一致率与方向相反点数，与逐点暴力对比完全一致")


# ===================== 阈值敏感性 =====================
def test_threshold_sensitivity_is_monotone_and_matches_counts():
    rows = cm.rule_trigger_history(ramp_years(), "sep", hi=80, lo=20, min_n=20, adjust_level=True)
    t = cm.threshold_sensitivity(rows, pairs=((90, 10), (85, 15), (80, 20), (75, 25)))
    assert [x["hi"] for x in t] == [90, 85, 80, 75]
    highs = [x["highShare"] for x in t]
    assert highs == sorted(highs), "阈值越宽触发越多：90<85<80<75"
    pcts = [r["pct"] for r in rows]
    exp80 = round(sum(1 for p in pcts if p >= 80) / len(pcts) * 100, 1)
    assert next(x for x in t if x["hi"] == 80)["highShare"] == exp80 == 20.0
    ok("阈值敏感性：触发率随阈值放宽单调上升；80/20恰好20%(与手算一致)")


# ===================== 自相关/有效样本 =====================
def test_autocorrelation_and_effective_n_hand_calculated():
    """[1,2,3,4,5]：均值3，偏差[-2,-1,0,1,2]，分子=(-2)(-1)+(-1)(0)+(0)(1)+(1)(2)=4，分母=10 → ρ=0.4；n_eff=5*(1-0.4)/(1+0.4)=2.142857。"""
    assert abs(cm.lag1_autocorr([1, 2, 3, 4, 5]) - 0.4) < 1e-12
    assert abs(cm.effective_n(5, 0.4) - 2.142857142857143) < 1e-9
    assert cm.lag1_autocorr([1, -1, 1, -1, 1, -1]) < -0.5, "交替：强负相关"
    assert cm.lag1_autocorr([3, 3, 3, 3]) is None and cm.lag1_autocorr([1]) is None and cm.lag1_autocorr([]) is None, "常数/太短：None"
    assert cm.effective_n(100, 0.0) == 100.0 and cm.effective_n(100, 0.9) < 6, "ρ=0.9时100个点只相当于约5个独立观测(100*0.1/1.9=5.26)"
    assert cm.effective_n(100, -0.5) == 100.0, "负相关不放大(封顶n)"
    assert cm.effective_n(100, None) is None
    ok("自相关/有效样本(手算[1..5]：ρ=0.4，n_eff=2.1429；ρ=0.9时100点≈5.3个独立观测)；常数/过短/负相关的边界")


def test_autocorrelation_is_computed_within_contract_years_not_across_gaps():
    """相邻两个合约年之间隔着很久(窗口外)，跨年的'相邻点'不是相邻交易日，不能算进滞后1自相关。"""
    pts = [{"d": f"2024-05-{k + 1:02d}", "v": float(k)} for k in range(10)] + [{"d": f"2025-05-{k + 1:02d}", "v": float(k)} for k in range(10)]
    r = cm.series_autocorr(pts, "sep")
    assert abs(r["rho"] - cm.lag1_autocorr([float(k) for k in range(10)])) < 1e-9, "两个合约年各自是同样的0..9斜坡：分年算的rho=单年的rho=0.2……(手算见下)"
    assert abs(cm.lag1_autocorr([float(k) for k in range(10)]) - 0.7) < 1e-12, "0..9：偏差[-4.5..4.5]，分子=Σd_t*d_{t+1}=57.75，分母=Σd²=82.5 → 0.7"
    pooled = cm.lag1_autocorr([float(k) for k in range(10)] * 2)
    assert abs(r["rho"] - pooled) > 1e-6, "分年算与把两年首尾相接混着算不同(混着算会把2024年末→2025年初这个跳变当成相邻点)"
    ok("自相关按合约年分别算再加权，不把跨年的跳变当成相邻交易日")


# ===================== 变异检查补的边界(原测试的盲区，期望值全部手算) =====================
def test_contract_year_boundary_when_month_equals_contract_month():
    """三个真实窗口里没有窗口月等于合约月(所以'>'与'>='对真实数据等价)，但函数对自定义窗口应该正确：合约月当月仍属于当年。"""
    assert cm.contract_year("2026-09-15", "sep") == 2026, "9月合约的9月：当年(用>=会得2027)"
    assert cm.contract_year("2026-05-31", "may") == 2026, "5月合约的5月：当年"
    assert cm.contract_year("2026-01-02", "jan") == 2026, "1月合约的1月：当年"
    assert cm.contract_year("2026-10-01", "sep") == 2027, "9月合约之后的月份：下一年"
    ok("合约年边界：合约月当月仍属于当年；之后的月份属于下一年")


def test_level_adjustment_uses_the_median_not_the_mean():
    """★变异检查发现测试用的是对称斜坡，均值=中位数。偏斜数据：[0,0,0,0,10]，中位数0、均值2。去水平后第一个点：用中位数→0.0；用均值→-2.0。"""
    pts = [{"d": f"2026-05-{k + 1:02d}", "v": v} for k, v in enumerate([0.0, 0.0, 0.0, 0.0, 10.0])]
    adj = cm._adjusted(pts, "sep")
    assert [a["v"] for a in adj] == [0.0, 0.0, 0.0, 0.0, 10.0], [a["v"] for a in adj]
    ok("★去水平用中位数(手算：[0,0,0,0,10]的中位数0、均值2；去水平后第一个点0.0而不是-2.0)")


def test_trigger_share_denominator_excludes_points_without_a_signal():
    """★变异检查发现测试里每个点都有信号。构造：2个有信号(1个高端1个中间)+2个参照不足被跳过：高端占比=1/2=50%，不是1/4=25%。"""
    rows = [{"d": "2026-05-01", "pct": 90.0, "n": 75, "signal": 1}, {"d": "2026-05-02", "pct": 50.0, "n": 75, "signal": 0},
            {"d": "2026-05-03", "pct": None, "n": 5, "signal": None}, {"d": "2026-05-04", "pct": None, "n": 5, "signal": None}]
    r = cm.trigger_share_by_year(rows)["2026"]
    assert r == {"n": 2, "skipped": 2, "high": 50.0, "low": 0.0}, r
    ok("触发率分母只含有信号的点(手算：2个有信号里1个高端=50%，不是1/4=25%)；被跳过的单独报skipped")


def test_agreement_only_counts_points_where_both_rules_have_a_signal():
    """★变异检查发现测试里没有无信号的点。raw=[1,None,0]，adj=[1,1,-1]：两边都有信号的只有第1、3个(n=2)，一致1个→50.0%，方向相反0个。"""
    mk = lambda sigs: [{"d": f"2026-05-{i + 1:02d}", "pct": 50.0, "n": 75, "signal": s} for i, s in enumerate(sigs)]
    a = cm.agreement(mk([1, None, 0]), mk([1, 1, -1]))
    assert a == {"n": 2, "agreeShare": 50.0, "opposite": 0}, a
    a2 = cm.agreement(mk([1, -1]), mk([-1, 1]))
    assert a2 == {"n": 2, "agreeShare": 0.0, "opposite": 2}, a2
    ok("一致率只数两边都有信号的点(手算：n=2，一致50.0%)；方向相反的单独计数")


def test_threshold_sensitivity_counts_the_boundary_inclusively():
    """★变异检查发现斜坡数据的分位(3k+1.5)/75*100不会恰好等于80或20。构造恰好等于阈值的点：参照[1,2,3,4,5]，当前值4.5→less=4,eq=0→80.0；当前值1.5→less=1→20.0。"""
    assert hs.percentile_rank(4.5, [1, 2, 3, 4, 5]) == 80.0 and hs.percentile_rank(1.5, [1, 2, 3, 4, 5]) == 20.0
    rows = [{"d": "2026-05-01", "pct": 80.0, "n": 75, "signal": 1}, {"d": "2026-05-02", "pct": 20.0, "n": 75, "signal": -1}, {"d": "2026-05-03", "pct": 50.0, "n": 75, "signal": 0}]
    t = {x["hi"]: x for x in cm.threshold_sensitivity(rows, pairs=((80, 20), (81, 19)))}
    assert t[80]["highShare"] == round(1 / 3 * 100, 1) and t[80]["lowShare"] == round(1 / 3 * 100, 1), "恰好等于阈值(80.0/20.0)：计入(≥/≤)"
    assert t[81]["highShare"] == 0.0 and t[81]["lowShare"] == 0.0, "阈值收紧一点就不计入"
    ok("阈值敏感性边界：分位恰好=80.0/20.0计入(≥/≤)；阈值81/19则不计入")


def test_month_sufficiency_boundary_exactly_at_the_minimum():
    """★变异检查发现测试里参照数75/8，没有恰好=20的情形。旧年20个+新年5个：最新年参照恰好20→ok；旧年19个→不ok。"""
    mk = lambda ny, nn: [{"d": f"2024-05-{k + 1:02d}", "v": float(k)} for k in range(ny)] + [{"d": f"2025-05-{k + 1:02d}", "v": float(k)} for k in range(nn)]
    assert cm.month_sufficiency(mk(20, 5), "sep", min_n=20)["5"]["ok"] is True and cm.month_sufficiency(mk(20, 5), "sep", min_n=20)["5"]["refNForLatestYear"] == 20
    assert cm.month_sufficiency(mk(19, 5), "sep", min_n=20)["5"]["ok"] is False
    ok("充足度边界：参照恰好20个→ok，19个→不ok(与线上'同月样本≥20'一致)")


# ===================== 报告与集成 =====================
def test_series_report_is_compact_and_has_all_sections():
    r = cm.calibrate_series(ramp_years(), "sep", "crush_margin_sep")
    for k in ("n", "contractYears", "levelDrift", "monthSufficiency", "ruleToday", "levelAdjusted", "agreement", "thresholdSensitivity", "autocorr", "caveats"):
        assert k in r, k
    assert r["ruleToday"]["byYear"]["2026"]["high"] > 60 and r["levelAdjusted"]["byYear"]["2026"]["high"] == 20.0
    assert len(json.dumps(r, ensure_ascii=False).encode("utf-8")) < 8 * 1024, "单个序列的校准报告<8KB(回填报告会被日志截断，见v96.2)"
    cv = " ".join(r["caveats"])
    assert "没有价格" in cv and "事后" in cv and "有效样本" in cv, "必须写明：点里没有价格所以不能做前向检验；去水平用的是事后年中位数；逐日点高度相关"
    ok("单序列报告：含全部诊断段、<8KB；注意事项写明(没价格无法前向检验/去水平是事后的/逐日高度相关)")


def test_integration_into_calibration_summary_with_failure_isolation():
    with tempfile.TemporaryDirectory() as d:
        for ctype in ("sep", "may", "jan"):
            hs.record_points("crush_margin_" + ctype, ramp_years(month={"sep": 5, "may": 1, "jan": 9}[ctype]), d)
        hs.record_points("term_spread_sep", ramp_years(), d)
        out = bf.calibration_summary(d)
        ms = out["marginSpreadCalibration"]
        assert set(ms) == {"crush_margin_sep", "crush_margin_may", "crush_margin_jan", "term_spread_sep"}, set(ms)
        assert "error" not in ms["crush_margin_sep"] and ms["crush_margin_sep"]["n"] == 100
        # 单个序列出错不影响其他
        orig = cm.calibrate_series
        def boom(points, ctype, key):
            if key == "crush_margin_may":
                raise RuntimeError("坏了")
            return orig(points, ctype, key)
        cm.calibrate_series = boom
        try:
            ms2 = cm.margin_spread_calibration(d)
        finally:
            cm.calibrate_series = orig
        assert "坏了" in ms2["crush_margin_may"]["error"] and "levelDrift" in ms2["crush_margin_sep"] and "levelDrift" in ms2["term_spread_sep"]
    with tempfile.TemporaryDirectory() as d2:
        assert cm.margin_spread_calibration(d2) == {}, "没有任何序列：返回空，不报错"
    ok("集成进calibration_summary(only=calibrate)：有数据的序列都出报告；单个序列出错只记那一个的error；没数据返回空")


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
