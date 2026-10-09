# -*- coding: utf-8 -*-
"""季节性统计(v101.14)：换月修正指数、月度收益/上冲/下探、各月统计与分级、年内路径带。运行：python3 test_seasonal_stats.py
★期望值全部手算；真实数据回归值来自用户 2026-10-09 提供的 10 年 CSV(data/raw/seasonal/meal_spot_futures_10y.csv)，
  已用另一套独立实现(pandas)交叉核对过：换月修正后 12月均值 −0.12%、7月上涨 8/10、现货 8月均值 +4.36% 等。"""
import os, sys, json, math, traceback, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seasonal_stats as ss

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "raw", "seasonal")
_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def near(a, b, t=1e-9):
    return a is not None and b is not None and abs(a - b) <= t


def test_adjusted_index_ignores_the_roll_day_gap():
    rows = [{"d": "2020-01-02", "c": 100, "k": "m2005"}, {"d": "2020-01-03", "c": 110, "k": "m2005"},
            {"d": "2020-01-06", "c": 50, "k": "m2009"}, {"d": "2020-01-07", "c": 55, "k": "m2009"}]
    idx = ss.adjusted_index(rows)
    assert [round(x["i"], 6) for x in idx] == [100.0, 110.0, 110.0, 121.0], idx
    assert ss.adjusted_index([]) == []
    ok("换月日的价格缺口不计入收益：100→110→(换月 50)→55 的指数是 100,110,110,121(同合约相邻日收益才计)")


def test_adjusted_index_without_contract_info_is_plain_prices():
    rows = [{"d": "2020-01-02", "c": 100}, {"d": "2020-01-03", "c": 90}]
    assert [round(x["i"], 6) for x in ss.adjusted_index(rows)] == [100.0, 90.0]
    ok("没有合约列(现货)时就是原价序列")


def _mk(prices_by_month):
    """每个月两个交易日(月中、月末)，用于构造月度表。prices_by_month: [(y,m,mid,end)]"""
    rows = []
    for y, m, a, b in prices_by_month:
        rows.append({"d": f"{y}-{m:02d}-10", "c": a}); rows.append({"d": f"{y}-{m:02d}-25", "c": b})
    return rows


def test_monthly_returns_and_excursions_hand_calculated():
    rows = _mk([(2020, 1, 100, 100), (2020, 2, 120, 110), (2020, 3, 90, 99)])
    idx = ss.adjusted_index(rows)
    r = ss.monthly_returns(idx)
    assert r[2020][1] is None, "首月没有上月末，不算"
    assert near(r[2020][2], 10.0) and near(r[2020][3], -10.0), r
    ex = ss.excursions(idx)
    assert near(ex[2020][2]["up"], 20.0) and near(ex[2020][2]["dn"], 0.0), ex[2020][2]     # 2月最高120/上月末100=+20%；最低110>100 → 没跌破上月末，下探记0
    assert near(ex[2020][3]["up"], 0.0) and near(ex[2020][3]["dn"], -18.181818181818183, 1e-9), ex[2020][3]   # 3月最高99<110 → 上冲0；最低90/110-1
    ok("月度收益(2月+10%、3月−10%)与月内上冲/下探(相对上月末收盘：2月最高+20%，3月最低−18.18%)手算一致；首月无上月末不计")


def test_month_stats_hand_calculated():
    st = ss.month_stats([1, 2, -1, 4])
    assert st["n"] == 4 and near(st["mean"], 1.5) and near(st["median"], 1.5) and near(st["upPct"], 75.0)
    assert near(st["std"], math.sqrt(13 / 3), 1e-9) and near(st["t"], 1.5 / (math.sqrt(13 / 3) / 2), 1e-9), st
    assert ss.month_stats([])["n"] == 0 and ss.month_stats([])["mean"] is None
    assert ss.month_stats([3.0])["std"] is None and ss.month_stats([3.0])["t"] is None
    ok("各月统计手算：[1,2,−1,4] → 均值1.5、中位1.5、上涨75%、样本标准差√(13/3)、t=1.44；空/单样本不报错且不编造")


def test_grade_is_honest_about_instability():
    # 两半方向一致、上涨比例≥70%或≤30%、|t|≥1.5 → 较稳
    g = ss.grade_month([2, 3, 1, 4, 2, 3, 5, 2, 1, 3], split_year=2021, years=list(range(2017, 2027)))
    assert g["label"] == "较稳", g
    # 前半正后半负 → 不稳
    g = ss.grade_month([3, 3, 3, 3, 3, -3, -3, -3, -3, -3], split_year=2021, years=list(range(2017, 2027)))
    assert g["label"] == "不稳", g
    # 两半一致但上涨比例/ t 不够 → 一般
    g = ss.grade_month([0.2, -0.1, 0.3, -0.2, 0.1, 0.2, -0.3, 0.1, 0.2, -0.1], split_year=2021, years=list(range(2017, 2027)))
    assert g["label"] == "一般", g
    # 两半同向(+12/+5)、7/10 年上涨，但波动极大 t≈0.7 → 一般(不能只看胜率)
    g = ss.grade_month([30, -60, 30, 30, 30, 30, -60, 30, 30, -5], split_year=2021, years=list(range(2017, 2027)))
    assert g["label"] == "一般", g
    g = ss.grade_month([1, 2, 3], split_year=2021, years=[2024, 2025, 2026])
    assert g["label"] == "样本不足", g
    ok("分级：两半同向且胜率/ t 够强=较稳；前后两半方向相反=不稳；其余=一般；少于6个样本=样本不足")


def test_weekly_path_and_bands():
    # 两个完整年份，每年两个点：年初基准=上年最后一个指数
    rows = [{"d": "2019-12-30", "c": 100}, {"d": "2020-01-07", "c": 110}, {"d": "2020-12-28", "c": 120},
            {"d": "2021-01-07", "c": 126}, {"d": "2021-12-27", "c": 132}, {"d": "2022-01-07", "c": 133.2}]
    idx = ss.adjusted_index(rows)
    p = ss.weekly_paths(idx, min_days=1)
    assert near(p[2020][0], 10.0) and near(p[2020][51], 20.0, 1e-9), (p[2020][0], p[2020][51])
    assert near(p[2021][0], 5.0, 1e-9) and near(p[2021][51], 10.0, 1e-9), (p[2021][0], p[2021][51])
    b = ss.path_bands({2020: p[2020], 2021: p[2021]})
    assert near(b["median"][0], 7.5) and near(b["p25"][0], 6.25) and near(b["p75"][0], 8.75), b["median"][0]
    ok("年内路径：以上年最后收盘为基准的周度累计收益；两年中位 7.5%、p25 6.25%、p75 8.75% 手算一致")


def test_current_year_position_against_the_band():
    pos = ss.position_in_band(15.0, [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0])
    assert pos["percentile"] == 100.0 and pos["flag"] == "高于历史带", pos
    pos = ss.position_in_band(8.5, [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0])
    assert near(pos["percentile"], 40.0) and pos["flag"] == "带内", pos
    assert ss.position_in_band(1, [1, 2])["flag"] == "样本不足"
    ok("今年相对历史带的位置：高于全部10年=100分位『高于历史带』；中间=40分位『带内』；<5年样本=样本不足")


def test_contract_follow_builder_removes_rolls_by_following_yesterdays_dominant():
    # 两个合约：A 持仓大到第3天，B 之后持仓更大；第3→4天主力从A换到B，B 比 A 便宜 20 → 不应产生 −20% 缺口
    A = [{"d": "2020-01-02", "close": 100, "hold": 900}, {"d": "2020-01-03", "close": 110, "hold": 800}, {"d": "2020-01-06", "close": 121, "hold": 500}, {"d": "2020-01-07", "close": 121, "hold": 100}]
    B = [{"d": "2020-01-02", "close": 80, "hold": 100}, {"d": "2020-01-03", "close": 88, "hold": 300}, {"d": "2020-01-06", "close": 96.8, "hold": 600}, {"d": "2020-01-07", "close": 106.48, "hold": 900}]
    idx = ss.index_from_contracts({"m2005": A, "m2009": B})
    assert [round(x["i"], 4) for x in idx] == [100.0, 110.0, 121.0, 133.1], idx            # 前一日主力的当日收益：A +10%,+10%；第3日主力已是B → 第4日用 B 的 +10%
    assert [x["k"] for x in idx] == ["m2005", "m2005", "m2009", "m2009"], idx
    ok("按合约自己构造：每天沿用『前一天的主力合约』的当日涨跌，换月不产生缺口；主力按持仓量最大判定")


def test_contract_follow_builder_is_flat_when_yesterdays_dominant_has_no_price():
    A = [{"d": "2020-01-02", "close": 100, "hold": 900}, {"d": "2020-01-03", "close": 110, "hold": 800}]
    B = [{"d": "2020-01-02", "close": 80, "hold": 100}, {"d": "2020-01-03", "close": 88, "hold": 300}, {"d": "2020-01-06", "close": 96.8, "hold": 600}]
    idx = ss.index_from_contracts({"m2005": A, "m2009": B})
    assert [round(x["i"], 4) for x in idx] == [100.0, 110.0, 110.0], idx          # 01-06：前一日主力是 B(300>... 01-03 hold A800>B300→A)，A 当日无价 → 持平
    ok("前一日主力当天没有价格(已摘牌/缺数据)时指数持平，不拿别的合约的价格硬接")


def test_real_data_regression_matches_the_independent_pandas_run():
    res = ss.build_from_baseline_csv(os.path.join(RAW, "meal_spot_futures_10y.csv"))
    fm = {m["month"]: m for m in res["months"]}
    assert near(round(fm[12]["futures"]["mean"], 2), -0.12) and fm[7]["futures"]["upPct"] == 80.0 and fm[7]["futures"]["n"] == 10, fm[12]["futures"]
    assert near(round(fm[11]["futures"]["mean"], 2), 0.94), fm[11]["futures"]
    assert near(round(fm[8]["spot"]["mean"], 2), 4.36) and fm[8]["spot"]["upPct"] == 80.0, fm[8]["spot"]
    assert fm[10]["futures"]["n"] == 9, "2016年只有10-12月，10月样本9个"
    assert near(round(res["monthlyTable"]["futures"]["2022"]["12"], 1), 7.1) and near(round(res["monthlyTable"]["futures"]["2023"]["7"], 1), 13.2)
    assert res["meta"]["firstDate"] == "2016-10-10" and res["meta"]["lastDate"] == "2026-09-30" and res["meta"]["rollMethod"]
    ok("真实 10 年数据回归(与 pandas 独立实现一致)：修正后12月 −0.12%、11月 +0.94%、7月上涨8/10；现货8月 +4.36%(8/10上涨)；2022-12 +7.1%、2023-07 +13.2%")


def test_output_is_pure_json_with_no_nan_and_documents_its_limits():
    res = ss.build_from_baseline_csv(os.path.join(RAW, "meal_spot_futures_10y.csv"))
    txt = json.dumps(res, ensure_ascii=False, allow_nan=False)      # allow_nan=False：有 NaN/inf 会直接报错
    assert len(txt) < 400_000, len(txt)
    assert len(res["months"]) == 12 and all({"futures", "spot", "excursion", "gradeFutures", "gradeSpot"} <= set(m) for m in res["months"])
    assert len(res["path"]["bands"]["median"]) == 52 and "current" in res["path"] and res["path"]["current"]["year"] == 2026
    assert res["meta"]["priceBasis"] == "收盘价" and any("多重比较" in x for x in res["meta"]["caveats"]) and any("换月" in x for x in res["meta"]["caveats"])
    ok("输出是纯 JSON(无 NaN)、体积<400KB；12个月、52周路径带、今年(2026)曲线齐全；说明里带多重比较与换月的局限")


def test_grades_on_real_data_say_futures_are_weak_and_spot_is_steadier():
    res = ss.build_from_baseline_csv(os.path.join(RAW, "meal_spot_futures_10y.csv"))
    gf = [m["gradeFutures"]["label"] for m in res["months"]]; gs = [m["gradeSpot"]["label"] for m in res["months"]]
    assert gf.count("较稳") <= 2 and gs.count("较稳") >= 2, (gf, gs)
    assert res["months"][11]["gradeFutures"]["label"] != "较稳", "12月期货『偏空』是换月缺口造成的，修正后不应被标成较稳"
    ok("分级与结论一致：期货『较稳』的月份不超过2个，现货至少2个；12月期货不再被标成较稳")


def test_cli_builds_from_a_raw_dir_and_prefers_contract_files_when_present():
    d = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(d, "raw"))      # 只拷基线CSV(线上 data/raw/seasonal 现在已有真实 contracts/ 目录，整个拷会干扰"合约文件太少"这一步)
        shutil.copy(os.path.join(RAW, "meal_spot_futures_10y.csv"), os.path.join(d, "raw", "meal_spot_futures_10y.csv"))
        out = os.path.join(d, "seasonal.json")
        r = ss.main(["--raw", os.path.join(d, "raw"), "--out", out])
        assert r["source"] == "baseline_csv" and os.path.exists(out)
        os.makedirs(os.path.join(d, "raw", "contracts"))
        # 两个很短的合约文件 → 数据太少，应回退基线并说明原因
        for code in ("M1701", "M1705"):
            open(os.path.join(d, "raw", "contracts", code + ".csv"), "w", encoding="utf-8").write("date,open,high,low,close,volume,hold,settle\n2016-10-10,1,1,1,1,1,1,1\n")
        r = ss.main(["--raw", os.path.join(d, "raw"), "--out", out])
        assert r["source"] == "baseline_csv" and "合约文件" in r["note"], r
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("命令行：默认用基线 CSV；合约文件太少/不完整时回退基线并写明原因，不拿残缺数据出结果")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
if __name__ == "__main__":
    fails = []
    for t in TESTS:
        try:
            t()
        except Exception:
            fails.append(t.__name__); print("❌", t.__name__); traceback.print_exc()
    print(f"\n结果：{_pass}项通过，{len(fails)}项失败" + (f"：{fails}" if fails else ""))
    sys.exit(1 if fails else 0)
