# -*- coding: utf-8 -*-
"""每天记录两个系统的方向：record_systems.py(合并策略/写入)、analyze_systems.py(分类/前瞻收益/警示)、工作流配置。
运行：python3 test_record_systems.py"""
import json, os, sys, tempfile, shutil, traceback, subprocess, copy
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_store as hs
import record_systems as rs
import analyze_systems as an

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="sys_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def contract_snap(contract="sep", fund=("偏多", 0.6, 9), struct=("偏空", -1.0, 3, False), comp=("偏多", 0.3, 12), close=3319, price_date="2026-09-14", symbol="M2609", missing=None, in_window=True):
    return {"contract": contract, "inWindow": in_window,
            "fund": None if fund is None else {"direction": fund[0], "ratio": fund[1], "n": fund[2]},
            "structure": None if struct is None else {"direction": struct[0], "ratio": struct[1], "n": struct[2], "thin": struct[3], "items": [{"label": "现货基差", "signal": -1}, {"label": "月差/期限结构", "signal": -1}, {"label": "量价关系", "signal": -1}][:struct[2]]},
            "composite": {"direction": comp[0], "ratio": comp[1], "n": comp[2], "total": comp[2]},
            "tech": "偏多", "foreign": "calm", "quality": 0.97, "confidence": "中", "vpStatus": "ok", "missing": missing or [],
            "symbol": symbol, "close": close, "priceDate": price_date}


def snapshot(d="2026-09-30", version="v95", contracts=None, failures=0, trading=True):
    return {"date": d, "scoringVersion": version, "tradingDay": trading, "dataGeneratedAt": d + "T02:00:00+00:00", "timedOut": False,
            "fetchFailures": ["x"] * failures, "pageErrors": [], "contracts": contracts if contracts is not None else [contract_snap("sep"), contract_snap("may", close=None, price_date=None, symbol=None), contract_snap("jan", close=None, price_date=None, symbol=None)]}


def pts(d, key):
    return hs.load_series(key, d)["points"]


# ===================== 记录 =====================
def test_ingest_writes_one_point_per_contract_with_all_fields():
    with Tmp() as d:
        rep = rs.ingest_snapshot(snapshot(), d)
        assert sorted(rep["recorded"]) == ["systems_jan", "systems_may", "systems_sep"] and rep["skipped"] == {}
        p = pts(d, "systems_sep")
        assert len(p) == 1 and p[0]["d"] == "2026-09-30" and p[0]["v"] == 0.6, p
        x = p[0]["x"]
        assert x["fundDir"] == "偏多" and x["fundN"] == 9 and x["structDir"] == "偏空" and x["structRatio"] == -1.0 and x["structN"] == 3 and x["structThin"] is False
        assert x["compDir"] == "偏多" and x["compRatio"] == 0.3 and x["compN"] == 12 and x["tech"] == "偏多" and x["foreign"] == "calm"
        assert x["symbol"] == "M2609" and x["close"] == 3319 and x["priceDate"] == "2026-09-14" and x["scoringVersion"] == "v95" and x["tradingDay"] is True and x["inWindow"] is True
        assert x["quality"] == 0.97 and x["confidence"] == "中" and x["vpStatus"] == "ok" and x["failures"] == 0 and len(x["structItems"]) == 3
        assert pts(d, "systems_may")[0]["x"]["close"] is None, "没有K线的合约：价格为空照常记录方向"
    ok("记录：每个合约一条，方向/综合/价格/覆盖情况/规则版本/交易日标记都在")


def test_series_meta_registered():
    for k in ("systems_sep", "systems_may", "systems_jan"):
        assert hs.SERIES_META[k]["freq"] == "daily" and "每日系统方向" in hs.SERIES_META[k]["name"] and hs.SERIES_META[k]["unit"] == "净倾向"
    ok("序列元信息已登记(systems_sep/may/jan)")


def test_skips_contract_without_fundamental_direction():
    with Tmp() as d:
        s = snapshot(contracts=[contract_snap("sep"), contract_snap("may", fund=None), {"contract": "jan", "error": "页面计算出错"}])
        rep = rs.ingest_snapshot(s, d)
        assert rep["recorded"] == ["systems_sep"]
        assert "数据不足" in rep["skipped"]["may"] and "页面计算出错" in rep["skipped"]["jan"]
        assert pts(d, "systems_may") == [] and pts(d, "systems_jan") == [], "基本面没有方向：不拿别的东西凑，不记录"
        assert rs.build_point(s, {"contract": "sep", "fund": {"direction": "偏多", "ratio": None, "n": 3}})[0] is None
    ok("基本面没有方向(数据不足)或页面出错：跳过并写明原因，不凑数")


def test_same_day_rerun_is_idempotent():
    with Tmp() as d:
        rs.ingest_snapshot(snapshot(), d)
        before = open(os.path.join(d, "systems_sep.json"), encoding="utf-8").read()
        rep = rs.ingest_snapshot(snapshot(), d)
        assert rep["recorded"] == [] and open(os.path.join(d, "systems_sep.json"), encoding="utf-8").read() == before
        assert len(pts(d, "systems_sep")) == 1
    ok("同一份快照重复写入：无变化，不产生重复点")


def test_same_day_more_complete_coverage_wins_direction():
    """★天气被限流导致覆盖变少：方向沿用覆盖更完整的那次，只更新价格。"""
    with Tmp() as d:
        rs.ingest_snapshot(snapshot(contracts=[contract_snap("sep", fund=("偏多", 0.6, 9), struct=("偏空", -1.0, 3, False), close=3300, price_date="2026-09-29")]), d)
        # 之后一次：天气票缺席，基本面只剩6票，方向翻成中性——网络噪声；价格更新了
        poor = contract_snap("sep", fund=("中性", 0.1, 6), struct=("偏空", -1.0, 3, False), close=3330, price_date="2026-09-30")
        rep = rs.ingest_snapshot(snapshot(contracts=[poor], failures=12), d)
        x = pts(d, "systems_sep")[0]
        assert x["v"] == 0.6 and x["x"]["fundDir"] == "偏多" and x["x"]["fundN"] == 9, "方向保留覆盖完整的那次"
        assert x["x"]["close"] == 3330 and x["x"]["priceDate"] == "2026-09-30", "价格字段取最新"
        assert "保留之前的方向" in rep["notes"]["sep"]
        assert x["x"]["failures"] == 0, "failures跟着方向走(属于方向那次运行)"
    ok("★覆盖更少的后一次(天气被限流)：保留之前的方向，只更新价格——网络噪声不污染方向")


def test_same_day_equal_or_better_coverage_takes_latest():
    with Tmp() as d:
        rs.ingest_snapshot(snapshot(contracts=[contract_snap("sep", fund=("偏多", 0.6, 9), close=3300)]), d)
        rs.ingest_snapshot(snapshot(contracts=[contract_snap("sep", fund=("中性", 0.1, 9), close=3330)]), d)
        assert pts(d, "systems_sep")[0]["x"]["fundDir"] == "中性", "覆盖相同：取最新一次"
        rs.ingest_snapshot(snapshot(contracts=[contract_snap("sep", fund=("偏空", -0.5, 10), struct=("偏空", -1.0, 3, False), close=3340)]), d)
        x = pts(d, "systems_sep")[0]
        assert x["x"]["fundDir"] == "偏空" and x["x"]["fundN"] == 10 and x["v"] == -0.5, "覆盖更完整：胜出"
        assert len(pts(d, "systems_sep")) == 1
    ok("覆盖相同取最新、更完整的胜出；同一天始终只有一条")


def test_coverage_counts_both_systems():
    a = {"x": {"fundN": 9, "structN": 3}}
    b = {"x": {"fundN": 10, "structN": 1}}
    assert rs.coverage(a) == 12 and rs.coverage(b) == 11
    with Tmp() as d:
        rs.ingest_snapshot(snapshot(contracts=[contract_snap("sep", fund=("偏多", 0.6, 9), struct=("偏空", -1.0, 3, False))]), d)
        rs.ingest_snapshot(snapshot(contracts=[contract_snap("sep", fund=("偏多", 0.7, 10), struct=("偏空", -1.0, 1, True))]), d)
        assert pts(d, "systems_sep")[0]["x"]["structN"] == 3, "基本面多1票但市场结构少2项：总覆盖更少，保留之前的"
    ok("覆盖=基本面票数+市场结构项数(两个系统都算)")


def test_scoring_version_change_same_day_new_wins_even_with_less_coverage():
    with Tmp() as d:
        rs.ingest_snapshot(snapshot(version="v95", contracts=[contract_snap("sep", fund=("偏多", 0.6, 9))]), d)
        rep = rs.ingest_snapshot(snapshot(version="v96", contracts=[contract_snap("sep", fund=("偏空", -0.3, 6))]), d)
        x = pts(d, "systems_sep")[0]
        assert x["x"]["scoringVersion"] == "v96" and x["x"]["fundDir"] == "偏空" and "评分规则版本变了" in rep["notes"]["sep"]
    ok("★当天部署了新评分规则：新版本整体胜出(规则变了，旧规则算的方向不能保留)")


def test_different_days_accumulate_in_order():
    with Tmp() as d:
        for day in ("2026-09-30", "2026-10-08", "2026-10-09"):
            rs.ingest_snapshot(snapshot(d=day, contracts=[contract_snap("sep")]), d)
        assert [p["d"] for p in pts(d, "systems_sep")] == ["2026-09-30", "2026-10-08", "2026-10-09"]
    ok("不同日期按顺序累积")


def test_non_trading_day_is_recorded_but_flagged():
    with Tmp() as d:
        rs.ingest_snapshot(snapshot(d="2026-10-03", trading=False, contracts=[contract_snap("sep")]), d)
        assert pts(d, "systems_sep")[0]["x"]["tradingDay"] is False
    ok("非交易日(周末/休市)的手动运行也记录，但标tradingDay=false(分析时排除)")


def test_cli_paths():
    with Tmp() as d:
        snap = os.path.join(d, "s.json")
        json.dump(snapshot(contracts=[contract_snap("sep")]), open(snap, "w", encoding="utf-8"), ensure_ascii=False)
        assert rs.main([]) == 2
        assert rs.main([os.path.join(d, "不存在.json")]) == 1, "快照文件不存在(快照步骤失败了)：退出码1"
        old = hs.HISTORY_DIR
        try:
            hs.HISTORY_DIR = os.path.join(d, "h")
            assert rs.main([snap]) == 0
            assert hs.load_series("systems_sep")["points"][0]["d"] == "2026-09-30"
        finally:
            hs.HISTORY_DIR = old
    ok("命令行：缺参数2、文件不存在1、正常0并写入")


def test_fundamental_with_null_direction_but_a_ratio_is_skipped():
    """★v97起数据不足时页面导出的fund是{direction:null, ratio:1, n:1}(对象，不是null——为让共振面板写"数据不足"而不是"加载中")。
    ratio=1只是"只有1票"的比值，没有意义。记录模块必须靠direction为空来跳过，不能只看ratio是否存在——
    否则会把一条"1票偏多100%"的假记录写进历史，污染以后检验背离的数据。(用快照脚本在真实旧latest.json上跑出来的真实形状)"""
    with Tmp() as d:
        c = contract_snap("sep", fund=None)
        c["fund"] = {"direction": None, "ratio": 1, "n": 1}
        rep = rs.ingest_snapshot(snapshot(contracts=[c]), d)
        assert rep["recorded"] == [] and "数据不足" in rep["skipped"]["sep"] and pts(d, "systems_sep") == []
        pt, why = rs.build_point(snapshot(), {"contract": "sep", "fund": {"direction": None, "ratio": 0.8, "n": 3}})
        assert pt is None and why, "direction为null即使ratio=0.8也不记录"
        pt, why = rs.build_point(snapshot(), {"contract": "sep", "fund": {"direction": "偏多", "ratio": 0.8, "n": 9}})
        assert pt is not None and pt["v"] == 0.8, "对照：direction有值才记录"
    ok("★fund={direction:null, ratio:1, n:1}(数据不足的真实形状)：必须跳过，不能只看ratio存在就记录；对照direction有值才记录")


# ===================== 分析 =====================
def test_classify_nine_states():
    c = an.classify
    assert c("偏多", "偏多") == "同向偏多" and c("偏空", "偏空") == "同向偏空"
    assert c("偏多", "偏空") == "背离(基本面偏多/结构偏空)" and c("偏空", "偏多") == "背离(基本面偏空/结构偏多)"
    assert c("中性", "偏多") == "基本面中性/结构偏多" and c("中性", "偏空") == "基本面中性/结构偏空"
    assert c("偏多", "中性") == "基本面偏多/结构中性" and c("偏空", "中性") == "基本面偏空/结构中性" and c("中性", "中性") == "都中性"
    assert len({c(f, s) for f in ("偏多", "偏空", "中性") for s in ("偏多", "偏空", "中性")}) == 9 == len(an.STATES_ORDER)
    ok("9种状态组合分类齐全")


def _fill(d, n, path, states, version="v95", symbol="M2609", start=date(2026, 3, 2)):
    """造n个交易日的记录：价格按path(i)，状态按states(i)=(fundDir, structDir)；跳过周末。"""
    k = 0; day = start
    while k < n:
        if day.weekday() < 5:
            fd, sd = states(k)
            c = contract_snap("sep", fund=(fd, 0.5, 9), struct=(sd, 0.5, 3, False), close=path(k), price_date=day.isoformat(), symbol=symbol)
            rs.ingest_snapshot(snapshot(d=day.isoformat(), version=version, contracts=[c]), d)
            k += 1
        day += timedelta(days=1)


def test_forward_return_hand_computed():
    with Tmp() as d:
        _fill(d, 40, lambda i: 3000 + 10 * i, lambda i: ("偏多", "偏多"))        # 价格每天+10
        res = an.summarize("sep", 5, d)
        row = res["rows"][0]
        assert row["state"] == "同向偏多" and res["usable"] == 40 and res["withReturn"] == 35
        # 第0天收盘3000，5个交易日后3050：+1.6667%；第34天3340→3390: +1.497%。均值在两者之间，全为正
        assert abs(an.forward_return(an.price_series(an.load_records("sep", d)), 0, 5) - (3050 / 3000 - 1) * 100) < 1e-9
        assert row["n"] == 35 and row["effectiveN"] == 7.0 and row["upShare"] == 100.0 and 1.4 < row["mean"] < 1.7
        assert row["enough"] is True
    ok("前瞻收益：手算(3000→3050=+1.667%)一致；n=35、有效样本≈n/5=7、全部上涨")


def test_states_separate_and_sample_warning():
    with Tmp() as d:
        # 前20天：基本面偏多/结构偏空(背离)，价格下跌；后30天：同向偏多，价格上涨
        _fill(d, 50, lambda i: 3000 - 5 * i if i < 20 else 2900 + 8 * (i - 20), lambda i: ("偏多", "偏空") if i < 20 else ("偏多", "偏多"))
        res = an.summarize("sep", 5, d)
        by = {r["state"]: r for r in res["rows"]}
        assert by["背离(基本面偏多/结构偏空)"]["mean"] < 0 < by["同向偏多"]["mean"]
        assert by["背离(基本面偏多/结构偏空)"]["enough"] is False, "背离只有15个样本(<30)：标样本不足"
        txt = an.render(res)
        assert "样本不足" in txt and "多重比较" in txt and "不是结论" in txt and "重叠" in txt
    ok("各状态分开统计；样本<30标'样本不足'；输出里必带'描述统计不是结论/重叠/多重比较'的警示")


def test_excludes_non_trading_thin_and_missing_price():
    with Tmp() as d:
        for i in range(10):
            day = (date(2026, 3, 2) + timedelta(days=i)).isoformat()
            rs.ingest_snapshot(snapshot(d=day, trading=False, contracts=[contract_snap("sep", close=3000 + i, price_date=day)]), d)
        for i in range(10, 20):
            day = (date(2026, 3, 2) + timedelta(days=i)).isoformat()
            rs.ingest_snapshot(snapshot(d=day, contracts=[contract_snap("sep", struct=("偏空", -1.0, 1, True), close=3000 + i, price_date=day)]), d)
        for i in range(20, 30):
            day = (date(2026, 3, 2) + timedelta(days=i)).isoformat()
            rs.ingest_snapshot(snapshot(d=day, contracts=[contract_snap("sep", close=None, price_date=None, symbol=None)]), d)
        res = an.summarize("sep", 5, d)
        assert res["records"] == 30 and res["usable"] == 0 and res["rows"] == []
        assert "还没有可用的样本" in an.render(res)
    ok("排除：非交易日、市场结构只有1项(thin)、没有价格的记录")


def test_symbol_change_and_gaps_not_used():
    with Tmp() as d:
        _fill(d, 30, lambda i: 3000 + i, lambda i: ("偏多", "偏多"), symbol="M2609")
        # 合约代码从M2609换成M2701：跨代码的前瞻收益不可比
        prices = an.price_series(an.load_records("sep", d))
        for p_ in prices[20:]:
            p_["symbol"] = "M2701"                                   # 移仓：从第20个价格日起全部换成新合约
        assert an.forward_return(prices, 17, 5) is None, "17→22：跨了M2609/M2701，不可比"
        assert an.forward_return(prices, 17, 2) is not None, "17→19：都还是M2609，照常计算"
        assert an.forward_return(prices, 22, 5) is not None, "22→27：都是M2701，照常计算"
        # 间隔异常(缺了很多天)
        prices2 = [{"symbol": "M", "close": 100, "priceDate": "2026-03-02", "d": "2026-03-02"}, {"symbol": "M", "close": 110, "priceDate": "2026-05-20", "d": "2026-05-20"}]
        assert an.forward_return(prices2, 0, 1) is None, "相邻两条相隔80多天(>1×2+5)：不算"
        assert an.forward_return(prices, 28, 5) is None, "超出末尾：None"
    ok("合约代码变了/日历间隔异常/超出末尾：不计算前瞻收益")


def test_price_series_dedups_by_price_date_keeping_latest_record():
    recs = [{"d": "2026-09-14", "priceDate": "2026-09-14", "close": 3300, "symbol": "M"}, {"d": "2026-09-15", "priceDate": "2026-09-14", "close": 3319, "symbol": "M"},
            {"d": "2026-09-16", "priceDate": "2026-09-16", "close": 3340, "symbol": "M"}, {"d": "x", "priceDate": None, "close": None, "symbol": "M"}]
    ps = an.price_series(recs)
    assert [p["priceDate"] for p in ps] == ["2026-09-14", "2026-09-16"] and ps[0]["close"] == 3319
    ok("价格序列：按价格日去重(取最晚的记录)，空价格丢弃")


def test_out_of_window_records_are_kept_but_excluded_from_analysis_by_default():
    """★窗口外(比如9月合约在10月)价格可能已过期、合约可能已到期，而且那时你并不在交易这个合约——记录照常记，分析默认排除。"""
    with Tmp() as d:
        k = 0; day = date(2026, 3, 2)
        while k < 40:
            if day.weekday() < 5:
                inw = k < 20
                c = contract_snap("sep", fund=("偏多", 0.5, 9), struct=("偏多", 0.5, 3, False), close=3000 + 10 * k, price_date=day.isoformat(), in_window=inw)
                rs.ingest_snapshot(snapshot(d=day.isoformat(), contracts=[c]), d)
                k += 1
            day += timedelta(days=1)
        recs = an.load_records("sep", d)
        assert len(recs) == 40 and sum(1 for r in recs if r["inWindow"] is False) == 20, "窗口外的也记录了"
        assert an.summarize("sep", 5, d)["usable"] == 20, "默认只用窗口内的"
        assert an.summarize("sep", 5, d, in_window_only=False)["usable"] == 40, "需要时可以包含窗口外"
        assert not an.usable({"tradingDay": True, "structThin": False, "inWindow": None, "fundDir": "偏多", "structDir": "偏多", "close": 1, "priceDate": "2026-03-02", "symbol": "M"})
        assert not an.usable({"tradingDay": True, "structThin": False, "inWindow": False, "fundDir": "偏多", "structDir": "偏多", "close": 1, "priceDate": "2026-03-02", "symbol": "M"})
    ok("★窗口外(inWindow=false/未知)：照常记录，分析默认排除；可以用in_window_only=False包含")


def test_versions_are_not_mixed():
    with Tmp() as d:
        _fill(d, 25, lambda i: 3000 + i, lambda i: ("偏空", "偏空"), version="v95", start=date(2026, 3, 2))
        _fill(d, 25, lambda i: 3100 + i, lambda i: ("偏多", "偏多"), version="v96", start=date(2026, 5, 4))
        res = an.summarize("sep", 5, d)
        assert res["version"] == "v96" and {r["state"] for r in res["rows"]} == {"同向偏多"}, "默认只用最新版本"
        assert "多个评分规则版本" in an.render(res) and "v95" in an.render(res) and "没有混用" in an.render(res)
        old = an.summarize("sep", 5, d, version="v95")
        assert {r["state"] for r in old["rows"]} == {"同向偏空"}
        assert an.latest_version([{"scoringVersion": "v9"}, {"scoringVersion": "v10"}]) == "v10", "版本号按数字比较，不是字符串比较"
    ok("★评分规则版本不混用：默认只用最新版本，并提示历史里有多个版本；版本号按数字比较(v10>v9)")


def test_prices_use_all_versions_but_directions_only_the_chosen_version():
    """★市场价格跟评分规则版本无关：新版本刚上线(只有1天的方向记录)，它之后的价格来自旧版本的记录，前瞻收益仍然可以算。"""
    with Tmp() as d:
        _fill(d, 12, lambda i: 3000 + 10 * i, lambda i: ("偏空", "偏空"), version="v95", start=date(2026, 3, 2))       # 前12个交易日：v95
        day13 = date(2026, 3, 2) + timedelta(days=16)                                                               # 第13个交易日附近，随后几天还是v95
        # 在第6个交易日那天，再写入一条v96记录(规则当天升级，新版本胜出)
        six = [date(2026, 3, 2) + timedelta(days=i) for i in range(20) if (date(2026, 3, 2) + timedelta(days=i)).weekday() < 5][5]
        c = contract_snap("sep", fund=("偏多", 0.5, 9), struct=("偏多", 0.5, 3, False), close=3000 + 10 * 5, price_date=six.isoformat())
        rs.ingest_snapshot(snapshot(d=six.isoformat(), version="v96", contracts=[c]), d)
        res = an.summarize("sep", 5, d)                                   # 默认最新版本=v96：只有这1条方向记录
        assert res["version"] == "v96" and res["usable"] == 1
        assert [(r["state"], r["n"]) for r in res["rows"]] == [("同向偏多", 1)], "这1条v96记录的前瞻收益用的是v95记录里的后续价格"
        assert abs(res["rows"][0]["mean"] - ((3000 + 10 * 10) / (3000 + 10 * 5) - 1) * 100) < 1e-3, "第6天→第11天：3050→3100=+1.639%"
        assert "同向偏空" not in {r["state"] for r in res["rows"]}, "v95的方向标签不混进来"
    ok("★价格用全部版本的记录(市场价格与规则无关)，方向标签只用选定版本——新版本刚上线也能算前瞻收益")


def test_analyze_cli_runs_on_empty_history():
    with Tmp() as d:
        old = hs.HISTORY_DIR
        hs.HISTORY_DIR = d
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                assert an.main(["sep"]) == 0
            assert buf.getvalue().count("【sep合约】") == 3 and "还没有可用的样本" in buf.getvalue()
        finally:
            hs.HISTORY_DIR = old
    ok("分析脚本：没有任何记录时也正常运行(3个观察期)")


# ===================== 工作流 =====================
def test_workflow_steps_order_and_failure_isolation():
    import yaml
    root = os.path.dirname(os.path.abspath(__file__))
    w = yaml.safe_load(open(os.path.join(root, ".github", "workflows", "update-data.yml"), encoding="utf-8"))
    steps = w["jobs"]["fetch-and-commit"]["steps"]
    names = [s.get("name", "") for s in steps]
    i_fetch = next(i for i, n in enumerate(names) if "运行数据抓取脚本" in n)
    i_node = next(i for i, n in enumerate(names) if "Node" in n)
    i_jsdom = next(i for i, n in enumerate(names) if "jsdom" in n)
    i_rec = next(i for i, n in enumerate(names) if "记录两个系统的方向" in n)
    i_commit = next(i for i, n in enumerate(names) if "提交" in n)
    assert i_fetch < i_node < i_jsdom < i_rec < i_commit, "顺序：抓取 → Node → jsdom → 记录 → 提交(记录的历史要随这次一起提交)"
    for i in (i_node, i_jsdom, i_rec):
        assert steps[i].get("continue-on-error") is True, f"{names[i]} 必须continue-on-error：失败不能影响数据同步"
    assert steps[i_node]["uses"].startswith("actions/setup-node@") and str(steps[i_node]["with"]["node-version"]) == "22"
    assert "jsdom@30.1.1" in steps[i_jsdom]["run"], "jsdom要锁版本(测试用的就是这个版本)"
    run = steps[i_rec]["run"]
    assert "scripts/snapshot_systems.js" in run and "--html index.html" in run and "--latest data/latest.json" in run and "record_systems.py" in run
    assert steps[i_fetch].get("continue-on-error") is None, "数据抓取本身不能被设成忽略失败"
    assert "git add data/history/" in steps[i_commit]["run"], "记录写在data/history/，提交步骤会一并提交"
    gi = open(os.path.join(root, ".gitignore"), encoding="utf-8").read()
    assert "node_modules/" in gi
    ok("工作流：抓取→Node→jsdom→记录→提交；三个新步骤都continue-on-error；jsdom锁版本；node_modules已忽略")


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
