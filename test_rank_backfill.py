# -*- coding: utf-8 -*-
"""龙虎榜历史自动回填(v101.21)：文本构造、东方财富/新浪解析与防污染、计划、预算与停手、探测、双目录读取。运行：python3 test_rank_backfill.py
★期望值全部手算。网络层全部是假接口(开发环境连不上东方财富/新浪)。"""
import os, sys, tempfile, shutil, traceback, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import rank_backfill as rb
import dce_rank_files as dr
import backfill_history as bf
import history_store as hs
import fetch_seasonal_raw as fsr

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def em_row(code, day, rk_l, name, lv, lc, rk_s, sv, sc):
    return {"SECURITY_CODE": code, "TRADE_DATE": day + " 00:00:00", "ORG_NAME_ABBR_NEW": name,
            "LP_RANK": rk_l, "LONG_POSITION": lv, "LP_CHANGE": lc, "SP_RANK": rk_s, "SHORT_POSITION": sv, "SP_CHANGE": sc}


def fake_em(code="M2701", day="2026-09-01", n=20, gs_long=150000, gs_short=None, bad_code=None, bad_day=None, short_n=None):
    """买榜 n 行：名次1=高盛(gs_long, 增减+100)，其余 filler_i = 10000-i*100；卖榜 short_n 行：名次1 = 中粮 50000，其余 20000-i*100。"""
    short_n = n if short_n is None else short_n
    def fetch(url):
        is_long = "sortColumns=LPRANK" in url
        rows = []
        if is_long:
            for i in range(1, n + 1):
                rows.append(em_row(bad_code or code, bad_day or day, i, "高盛期货（代客）" if i == 1 else f"买{i}", gs_long if i == 1 else 10000 - i * 100, 100 if i == 1 else i, 9999, None, None))
        else:
            for i in range(1, short_n + 1):
                rows.append(em_row(bad_code or code, bad_day or day, 9999, "中粮期货（代客）" if i == 1 else f"卖{i}", None, None, i, 50000 if i == 1 else 20000 - i * 100, -300 if i == 1 else -i))
        return {"success": True, "result": {"data": rows}}, {}
    return fetch


def test_build_txt_roundtrips_through_the_existing_parser():
    buy = [{"name": "高盛期货（代客）", "value": 150000, "change": 100}] + [{"name": f"买{i}", "value": 10000 - i * 100, "change": i} for i in range(2, 21)]
    sell = [{"name": "中粮期货（代客）", "value": 50000, "change": -300}] + [{"name": f"卖{i}", "value": 20000 - i * 100, "change": -i} for i in range(2, 21)]
    txt = rb.build_txt("2026-09-01", buy, sell)
    p = dr.parse_rank_text(txt)
    assert p["date"] == "2026-09-01" and len(p["buy"]) == 20 and len(p["sell"]) == 20
    # 高盛只在买榜：卖榜用第20名顶替=20000-20*100=18000；净=150000-18000=132000，变化=100-(-20)=120，approx
    assert dr.member_net(p, "高盛期货") == {"net": 132000, "change": 120, "approx": True}, dr.member_net(p, "高盛期货")
    # 中粮只在卖榜：买榜第20名=10000-20*100=8000；净=8000-50000=-42000，变化=20-(-300)=320
    assert dr.member_net(p, "中粮期货") == {"net": -42000, "change": 320, "approx": True}
    ok("build_txt 输出能被现有解析器读回：高盛净+132000(估计)、中粮净-42000(估计)，与手算一致")


def test_em_day_ok_and_pollution_guards():
    t, why = rb.em_day(fake_em(), "M2701", "2026-09-01")
    assert why is None and len(dr.parse_rank_text(t)["buy"]) == 20
    t, why = rb.em_day(fake_em(bad_code="M2705"), "M2701", "2026-09-01")
    assert t is None and "M2705" in why, why
    t, why = rb.em_day(fake_em(bad_day="2026-08-31"), "M2701", "2026-09-01")
    assert t is None and "2026-08-31" in why, why
    t, why = rb.em_day(fake_em(short_n=19), "M2701", "2026-09-01")
    assert t is None and "20行" in why.replace("19", "20") or "不一致" in why, why
    assert "多头榜20行、空头榜19行" in why, why
    ok("东方财富：正常 20/20 行写出；返回的合约/日期和请求不符 → 整天丢弃(防污染)；多空行数不一致 → 不写")


def test_em_day_failure_modes_have_reasons():
    t, why = rb.em_day(lambda u: (None, {"error": "HTTP 403"}), "M2701", "2026-09-01")
    assert t is None and why.startswith("多头榜：请求失败") and "403" in why
    t, why = rb.em_day(lambda u: ({"success": True, "result": {"data": []}}, {}), "M2701", "2020-01-02")
    assert t is None and "没有返回数据" in why
    t, why = rb.em_day(lambda u: ({"success": False, "message": "限流"}, {}), "M2701", "2026-09-01")
    assert "success=false" in why and "限流" in why
    ok("失败原因分三类写明：请求失败(含HTTP码)、没有返回数据(日期太早/休市)、接口success=false")


class FakeAk:
    def __init__(self, n=20, fail=False):
        self.n, self.fail, self.calls = n, fail, []

    def futures_hold_pos_sina(self, symbol, contract, date):
        self.calls.append((symbol, contract, date))
        if self.fail:
            raise ValueError("boom")
        col = {"成交量": "成交量", "多单持仓": "多单持仓", "空单持仓": "空单持仓"}[symbol]
        base = {"成交量": 90000, "多单持仓": 100000, "空单持仓": 80000}[symbol]
        names = {"成交量": "成交A", "多单持仓": "买方", "空单持仓": "卖方"}[symbol]
        rows = [{"名次": i, "会员简称": f"{names}{i}", col: base - i * 1000, "比上交易增减": i} for i in range(1, self.n + 1)]
        rows.append({"名次": "合计", "会员简称": "", col: 999999, "比上交易增减": 0})
        return pd.DataFrame(rows).iloc[:-1]


def test_sina_day_builds_text_with_volume_and_passes_args_uppercase():
    ak = FakeAk()
    t, why = rb.sina_day(ak, "m2701", "2026-09-01")
    assert why is None
    assert ak.calls == [("成交量", "M2701", "20260901"), ("多单持仓", "M2701", "20260901"), ("空单持仓", "M2701", "20260901")], ak.calls
    p = dr.parse_rank_text(t)
    assert p["buy"][0] == {"rank": 1, "name": "买方1", "value": 99000, "change": 1}, p["buy"][0]
    assert p["sell"][19] == {"rank": 20, "name": "卖方20", "value": 60000, "change": 20}, p["sell"][19]
    assert "成交A1" in t
    t2, why2 = rb.sina_day(FakeAk(fail=True), "M2701", "2026-09-01")
    assert t2 is None and "ValueError" in why2
    t3, why3 = rb.sina_day(FakeAk(n=0), "M2701", "2020-01-02")
    assert t3 is None and "为空" in why3
    ok("新浪：三张表→同格式文本(买1=99000 增减1，卖20=60000)；合约转大写、日期转 YYYYMMDD；异常/空表都给原因")


def base_rows():
    r = {}
    for d, k in [("2026-09-30", "m2701"), ("2026-09-29", "m2701"), ("2026-09-26", "m2701"), ("2026-09-27", "m2701"), ("2026-09-25", "m2701"), ("2026-08-31", "m2609"), ("2021-12-31", "m2205"), ("2026-09-28", "")]:
        r[d] = {"dominant_contract": k}
    return r


def test_plan_uses_baseline_contract_only_in_range_trading_days_newest_first():
    trading = lambda d: d.weekday() < 5 and d.isoformat() != "2026-09-25"    # 周末与中秋休市
    got = rb.plan(base_rows(), "2022-01-01", "2026-09-30", trading)
    # 2026-09-30 是周三 → 09-27 周日、09-26 周六、09-25 周五(中秋休市)都被排除；09-28(周一)基线没有主力合约不猜；2021-12-31 在范围外
    assert got == [("2026-09-30", "M2701"), ("2026-09-29", "M2701"), ("2026-08-31", "M2609")], got
    ok("计划：只取范围内、交易日、基线有主力合约的日子，合约取基线(大写)，从新到旧；周六日/休市/基线空合约/范围外都不出现")


def test_backfill_writes_skips_existing_and_reports():
    d = tempfile.mkdtemp()
    try:
        calls = []
        def fn(c, day):
            calls.append((c, day))
            return (rb.build_txt(day, [{"name": "a", "value": 1, "change": 0}], [{"name": "b", "value": 1, "change": 0}]), None) if day != "2026-09-29" else (None, "该日期/合约没有返回数据")
        todo = [("2026-09-30", "M2701"), ("2026-09-29", "M2701"), ("2026-09-26", "M2701")]
        r = rb.backfill(d, todo, fn, sleep=lambda s: None)
        assert (r["written"], r["noData"], r["failed"], r["skippedExisting"]) == (2, 1, 0, 0), r
        assert sorted(os.listdir(d)) == ["M2701_20260926.txt", "M2701_20260930.txt"]
        assert r["firstDay"] == "2026-09-26" and r["lastDay"] == "2026-09-30" and r["noDataSamples"] == ["M2701 2026-09-29: 该日期/合约没有返回数据"], r
        calls.clear()
        r2 = rb.backfill(d, todo, fn, sleep=lambda s: None)
        assert calls == [("M2701", "2026-09-29")] and r2["skippedExisting"] == 2 and r2["written"] == 0, (calls, r2)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("回填：写 2 个、'没数据' 1 个(记样例)；第二次只重试没数据的那天，已有文件不重请求")


def test_backfill_budget_and_failure_stop_boundaries():
    d = tempfile.mkdtemp()
    try:
        todo = [(f"2026-09-{30 - i:02d}", "M2701") for i in range(5)]
        t = {"now": 0}
        def fn(c, day):
            t["now"] += 10
            return rb.build_txt(day, [{"name": "a", "value": 1, "change": 0}], [{"name": "b", "value": 1, "change": 0}]), None
        r = rb.backfill(d, todo, fn, budget_s=20, clock=lambda: t["now"], sleep=lambda s: None)
        # 预算20秒、每次10秒：第1天 t=0 → 请求，t=10；第2天 t=10 → t=20；第3天 t=20 恰好等于预算(不算超) → 请求，t=30；第4天 30>20 停；写3个，剩2个
        assert r["written"] == 3 and r["stoppedByBudget"] and r["remaining"] == 2, r
        r = rb.backfill(d, todo, fn, budget_s=30, clock=lambda: t["now"] + 1000 * 0, sleep=lambda s: None)
        d2 = tempfile.mkdtemp()
        n = {"i": 0}
        def bad(c, day):
            n["i"] += 1
            return None, "多头榜：请求失败：HTTP 403"
        r = rb.backfill(d2, todo + [(f"2026-08-{31 - i:02d}", "M2609") for i in range(10)], bad, max_consecutive_fail=3, sleep=lambda s: None)
        assert n["i"] == 3 and r["stoppedByFailures"] and r["failed"] == 3 and r["remaining"] == 12 and "403" in r["firstError"], (n, r)
        shutil.rmtree(d2, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("时间预算边界(20秒预算、每次10秒：第3次恰好踩在预算线上仍要请求→写3个剩2个)；连续3次请求失败即停手并写第一条错误(剩余12天)")


def test_no_data_does_not_count_as_failure():
    d = tempfile.mkdtemp()
    try:
        r = rb.backfill(d, [(f"2021-0{1 + i // 10}-{1 + i % 10:02d}", "M2105") for i in range(30)], lambda c, day: (None, "该日期/合约没有返回数据"), max_consecutive_fail=3, sleep=lambda s: None)
        assert r["noData"] == 30 and r["failed"] == 0 and not r["stoppedByFailures"], r
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("'没有数据'连续30次也不触发停手(那是日期太早/休市，不是限流)；只有'请求失败'才累计")


def test_probe_and_samples():
    base = {"2020-07-01": {"dominant_contract": "m2009"}, "2020-07-02": {"dominant_contract": "m2009"}, "2023-07-03": {"dominant_contract": "m2309"},
            "2026-09-30": {"dominant_contract": "m2701"}, "2024-07-01": {"dominant_contract": ""}, "2024-07-02": {"dominant_contract": "m2409"}}
    s = rb.pick_samples(base)
    assert s == [("2020-07-01", "M2009"), ("2023-07-03", "M2309"), ("2024-07-02", "M2409"), ("2026-09-30", "M2701")], s
    res = rb.probe({"em": lambda c, d: (rb.build_txt(d, [{"name": "高盛期货（代客）", "value": 1, "change": 0}], [{"name": "b", "value": 1, "change": 0}]), None) if d >= "2023" else (None, "没有返回数据"),
                    "sina": lambda c, d: (None, "ValueError: x")}, s)
    assert res["em"]["okCount"] == 3 and res["em"]["total"] == 4 and res["sina"]["okCount"] == 0, res
    assert res["em"]["samples"][1]["info"] == {"rows": 1, "top": ["高盛期货（代客）", "1 "]}, res["em"]["samples"][1]
    ok("探测：每年 7 月第一个有主力合约的日子+最新日(空合约的 2024-07-01 跳过到 07-02)；按来源统计 ok 数与首行会员")


def test_job_rank_auto_wiring_with_fakes():
    d = tempfile.mkdtemp()
    try:
        seas = os.path.join(d, "seasonal"); os.makedirs(seas)
        with open(os.path.join(seas, "meal_spot_futures_10y.csv"), "w", encoding="utf-8-sig") as f:
            f.write("date,symbol,spot,near_contract,near_contract_price,dominant_contract,futures\n2026-09-30,M,3000,m2611,3000,m2701,3010\n2026-09-29,M,3000,m2611,3000,m2701,3010\n")
        class A: pass
        a = A(); a.out = seas; a.rank_source = "em"; a.rank_start = "2026-09-01"; a.rank_end = "2026-09-30"; a.rank_auto_out = os.path.join(d, "auto"); a.budget = 100
        orig = rb.backfill
        rb.backfill = lambda *x, **k: orig(*x, **{**k, "sleep": lambda s: None})
        try:
            rep = fsr.job_rank_auto("rank_auto", a, None, fetch=fake_em(day="2026-09-30"), is_trading=lambda d: True)
        finally:
            rb.backfill = orig
        # 假接口永远返回 2026-09-30 的日期：09-30 通过，09-29 因日期不符被丢弃(防污染生效)
        assert rep["written"] == 1 and rep["noData"] == 1 and rep["failed"] == 0 and rep["planned"] == 2 and rep["source"] == "em", rep
        assert "返回的日期是2026-09-30，不是请求的2026-09-29" in rep["noDataSamples"][0], rep["noDataSamples"]
        assert os.listdir(a.rank_auto_out) == ["M2701_20260930.txt"], os.listdir(a.rank_auto_out)
        pr = fsr.job_rank_auto("rank_probe", a, None, fetch=fake_em(day="2026-09-30"), is_trading=lambda d: True) if False else None
        a.out = os.path.join(d, "none")
        os.makedirs(a.out)
        bad = fsr.job_rank_auto("rank_auto", a, None, fetch=fake_em(), is_trading=lambda d: True)
        assert bad["ok"] is False and "基线" in bad["reason"], bad
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("任务接线：基线CSV(带BOM)取主力合约→东方财富；日期对不上的一天被防污染丢弃、只落 1 个文件；没有基线CSV给清晰原因")


def test_capital_rank_reads_both_dirs_manual_wins():
    a, m, base = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    try:
        def mk(gs_long):
            buy = [{"name": "高盛期货（代客）", "value": gs_long, "change": 0}] + [{"name": f"买{i}", "value": 10000 - i * 100, "change": 0} for i in range(2, 21)]
            sell = [{"name": f"卖{i}", "value": 20000 - i * 100, "change": 0} for i in range(1, 21)]
            return buy, sell
        open(os.path.join(a, "M2701_20260901.txt"), "w", encoding="utf-8").write(rb.build_txt("2026-09-01", *mk(100000)))
        open(os.path.join(a, "M2701_20260902.txt"), "w", encoding="utf-8").write(rb.build_txt("2026-09-02", *mk(100000)))
        open(os.path.join(m, "M2701_20260901.txt"), "w", encoding="utf-8").write(rb.build_txt("2026-09-01", *mk(120000)))
        e = bf.backfill_capital_rank(base_dir=base, raw_dir=[a, m])
        assert e["files"] == 2, e
        pts = {p["d"]: p["v"] for p in hs.load_series("capital_gs_net", base)["points"]}
        # 卖榜第20名=20000-2000=18000；09-01 手动文件优先：120000-18000=102000；09-02 自动文件：100000-18000=82000
        assert pts == {"2026-09-01": 102000, "2026-09-02": 82000}, pts
    finally:
        for x in (a, m, base):
            shutil.rmtree(x, ignore_errors=True)
    ok("capital_rank 同时读自动/手动两个目录：同合约同日期手动文件优先(09-01 净+102000)，自动文件补其余日期(09-02 净+82000)")


if __name__ == "__main__":
    fails = []
    for k, t in list(globals().items()):
        if k.startswith("test_") and callable(t):
            try:
                t()
            except Exception:
                traceback.print_exc(); fails.append(k)
    print(f"\n结果：{_pass}项通过，{len(fails)}项失败：{fails}" if fails else f"\n结果：{_pass}项通过，0项失败")
    sys.exit(1 if fails else 0)
