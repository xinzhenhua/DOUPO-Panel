# -*- coding: utf-8 -*-
"""现货基差改用 AKShare(生意社)自己计算(v101.7)。运行：python3 test_spot_basis.py
数据源：ak.futures_spot_price(date, vars_list=['M'])，生意社 100ppi.com/sf/day-日期.html。
★读 akshare 1.19.1 的源码(_check_information)确认的**真实列名**：symbol(英文品种代码，豆粕=M)、spot_price、near_contract、near_contract_price、dominant_contract、dominant_contract_price、
near_basis、dom_basis、near_basis_rate、dom_basis_rate、date。函数的 docstring 写的是 var/sp/dom_price/dom_symbol——**过时了**，用户给的 dominant_contract_price 才是真实列名(我最初当成记错了，错的是我)。
★**符号约定相反**：akshare 的 dom_basis = dominant_contract_price − spot_price(期货−现货，也就是'期现价差')；本页面的基差 = 现货 − 期货(现货升水为正，规则'正基差偏多/负基差偏空')。
  所以站点基差要**取反**后才能和自算的核对(否则每一天都会报'不一致')。
★合约代码经 akshare 处理后是小写带品种前缀，如 m2701。夹具仍是构造的 DataFrame(没有真实响应样本)，但列名、符号、合约代码格式都按源码确认过的真实情况来。
★sp 的口径文档只写'现货价格'，生意社的商品现货价通常是它自己的基准价(多地报价综合)，是否全国综合没有明确说明。"""
import os, sys, time, traceback, tempfile, shutil, threading
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import fetch_data as fd
import backfill_history as bf
import history_store as hs

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


COLS = ["symbol", "spot_price", "near_contract", "near_contract_price", "dominant_contract", "dominant_contract_price", "near_basis", "dom_basis", "near_basis_rate", "dom_basis_rate", "date"]


def row(var="M", sp=3300.0, near="m2609", near_p=3350.0, dom="m2701", dom_p=3372.0, near_b=None, dom_b=None, d="2026-09-30"):
    """真实格式：dom_basis = 主力结算价 − 现货价(期货−现货，akshare 的约定)，所以现货3300、主力3372时站点给的是 +72；我们自算的页面基差是 -72。
    dom_b 参数是'站点给的值'(期货−现货的符号)；不传就按真实公式生成。"""
    nb = near_b if near_b is not None else round(near_p - sp, 2)
    db = dom_b if dom_b is not None else round(dom_p - sp, 2)
    return [var, sp, near, near_p, dom, dom_p, nb, db, round(near_p / sp - 1, 6), round(dom_p / sp - 1, 6), d]


def df(*rows):
    return pd.DataFrame(list(rows), columns=COLS)


# ---------------- parse_spot_basis ----------------
def test_basis_is_computed_as_spot_minus_the_dominant_settlement_price():
    r, why = fd.parse_spot_basis(df(row(sp=3300.0, dom_p=3372.0)))
    assert why is None and r["value"] == -72.0, (r, why)      # 3300 - 3372 = -72
    assert r["spot"] == 3300.0 and r["domPrice"] == 3372.0 and r["domSymbol"] == "m2701" and r["nearSymbol"] == "m2609" and r["nearPrice"] == 3350.0, r      # akshare 处理后的合约代码是小写带品种前缀
    r2, _ = fd.parse_spot_basis(df(row(sp=3450.5, dom_p=3372.0)))
    assert r2["value"] == 78.5, r2      # 3450.5 - 3372 = +78.5：现货高于期货为正
    ok("★基差 = 现货价 - 主力合约结算价，自己算：3300-3372=-72；3450.5-3372=+78.5(现货高于期货为正，与页面'正基差偏多/负基差偏空'的符号一致)")


def test_only_the_soymeal_row_is_used_when_the_page_has_many_products():
    d = df(row(var="RB", sp=3100.0, dom_p=3200.0), row(var="M", sp=3300.0, dom_p=3372.0), row(var="Y", sp=8000.0, dom_p=8100.0))
    r, _ = fd.parse_spot_basis(d)
    assert r["value"] == -72.0, r
    r2, why = fd.parse_spot_basis(df(row(var="RB")))
    assert r2 is None and "M" in why, (r2, why)
    ok("表里有螺纹/豆粕/豆油多个品种时只取 var=='M' 那一行；没有豆粕行：返回 None 并说明")


def test_alternative_column_names_are_understood():
    d = pd.DataFrame([{"symbol": "M", "spot_price": 3300.0, "dominant_contract": "M2701", "dominant_contract_price": 3372.0, "near_contract": "M2609", "near_contract_price": 3350.0, "date": "2026-09-30"}])
    r, why = fd.parse_spot_basis(d)
    assert why is None and r["value"] == -72.0 and r["domSymbol"] == "M2701" and r["siteBasis"] is None, (r, why)
    ok("★列名兼容另一套写法(symbol/spot_price/dominant_contract/dominant_contract_price——你提到的 dominant_contract_price)；没有站点基差列时 siteBasis=None")


def test_computed_value_wins_over_the_sites_own_basis_and_a_mismatch_is_flagged():
    d = df(row(sp=3300.0, dom_p=3372.0, dom_b=5.0))      # 站点给 +5(期货-现货的符号)，取反是 -5(页面符号)，与自算的 -72 对不上
    r, _ = fd.parse_spot_basis(d)
    assert r["value"] == -72.0 and r["siteBasis"] == -5.0 and r["siteDiff"] == -67.0 and r["consistent"] is False, r
    r1, _ = fd.parse_spot_basis(df(row(sp=3300.0, dom_p=3372.0, dom_b=71.6)))      # 站点 +71.6 → 取反 -71.6
    assert r1["consistent"] is True and r1["siteDiff"] == -0.4, r1      # 差0.4(四舍五入级别)算一致
    r2, _ = fd.parse_spot_basis(df(row(sp=3300.0, dom_p=3372.0, dom_b=70.5)))
    assert r2["consistent"] is False, r2      # 差1.5以内才算一致：这里差 -1.5，边界上
    ok("★取自己算的值(不信站点的 dom_basis)，并把站点值和差额带出来：对不上(-5 vs -72)标 consistent=False；差0.4算一致；差1.5(含)以上不算")


def test_boundary_of_the_consistency_tolerance():
    r_in, _ = fd.parse_spot_basis(df(row(sp=3300.0, dom_p=3372.0, dom_b=70.6)))      # 取反 -70.6，差 -1.4
    r_edge, _ = fd.parse_spot_basis(df(row(sp=3300.0, dom_p=3372.0, dom_b=70.5)))     # 取反 -70.5，差 -1.5
    assert r_in["consistent"] is True and r_edge["consistent"] is False and r_in["siteDiff"] == -1.4 and r_edge["siteDiff"] == -1.5, (r_in["siteDiff"], r_edge["siteDiff"])
    ok("一致性容差的边界：差1.4算一致，差1.5不算(用 < 不是 <=)")


def test_bad_or_missing_data_is_rejected_with_a_reason():
    cases = [(None, "没有返回"), (pd.DataFrame(), "没有返回"), (df(row(sp=float("nan"))), "现货价"), (df(row(dom_p=0.0)), "主力"), (df(row(dom_p=-5.0)), "主力"),
             (df(row(sp=50.0)), "超出合理范围"), (df(row(sp=99999.0)), "超出合理范围"), (df(row(sp=3300.0, dom_p=9000.0)), "超出合理范围")]
    for d, kw in cases:
        r, why = fd.parse_spot_basis(d)
        assert r is None and kw in why, (kw, r, why)
    strs = pd.DataFrame([{"var": "M", "sp": "3,300", "dom_symbol": "M2701", "dom_price": "3372"}])      # 站点把价格写成字符串(带千分位逗号)：直接用字典造这一行
    r, _ = fd.parse_spot_basis(strs)
    assert r is not None and r["value"] == -72.0, r
    ok("★坏数据逐类拒绝并说明：无返回/空表/现货价NaN/主力价为0或负/现货价50或99999超范围/基差超±1000；数字写成字符串('3,300')也能读")


def test_missing_dominant_symbol_does_not_stop_the_calculation():
    d = df(row())
    d["dom_symbol"] = None
    r, why = fd.parse_spot_basis(d)
    assert why is None and r["value"] == -72.0 and r["domSymbol"] is None, (r, why)
    ok("主力合约代码缺失(None)：基差照样算，domSymbol=None(不因为一个说明字段丢掉数值)")


def test_each_plausibility_check_fires_on_its_own():
    """★变异检查发现：坏数据用例里每个都同时触发了多条检查，其中一条被拿掉也看不出来。这里构造只会触发某一条的数据。"""
    # 只有基差范围会拦：现货、主力价各自都在 1500~6000，但差额 -2500 超出 ±1000
    r, why = fd.parse_spot_basis(df(row(sp=3000.0, dom_p=5500.0)))
    assert r is None and "自算基差" in why and "超出合理范围" in why, (r, why)
    # 只有现货价范围会拦：现货 1400(<1500)，主力 1900(在范围内)，差额 -500 在 ±1000 内
    r, why = fd.parse_spot_basis(df(row(sp=1400.0, dom_p=1900.0)))
    assert r is None and "现货价" in why and "超出合理范围" in why, (r, why)
    # 只有主力价范围会拦：主力 6100(>6000)，现货 5500，差额 -600 在 ±1000 内
    r, why = fd.parse_spot_basis(df(row(sp=5500.0, dom_p=6100.0)))
    assert r is None and "主力合约结算价" in why and "超出合理范围" in why, (r, why)
    ok("★三个合理范围检查各自单独起作用：只有基差超(现货3000/主力5500)、只有现货价超(1400)、只有主力价超(6100)")


def test_a_non_daemon_style_hang_never_blocks_the_process_exit():
    """★变异检查发现：没有测试守着'线程是守护线程'——它才是卡住的 akshare 调用不阻止进程退出的关键。"""
    stop = threading.Event()
    th_before = {t for t in threading.enumerate()}
    fd._run_with_deadline(lambda: stop.wait(30), 0.2)
    new = [t for t in threading.enumerate() if t not in th_before and t.is_alive()]
    stop.set()
    assert new and all(t.daemon for t in new), f"卡住的线程必须是守护线程：{[(t.name, t.daemon) for t in new]}"
    ok("★被放弃的卡住调用留下的线程是守护线程(进程退出时不会等它)")


def test_fallback_days_count_from_the_preferred_date_not_from_today():
    """早上10点：首选日是上一个交易日(09-30)，不是今天(10-08)。用的恰好是首选日→不算回退(fallbackDays=0)；退到再前一个交易日(09-29)→1天。"""
    morning = datetime(2026, 10, 8, 10, 0)
    r0 = fd.fetch_spot_basis(now_bj=morning, fetch=fetcher({"2026-09-30": df(row(d="2026-09-30"))}))
    assert r0["usedFallback"] is False and r0["fallbackDays"] == 0 and r0["ageDays"] == 8, r0
    r1 = fd.fetch_spot_basis(now_bj=morning, fetch=fetcher({"2026-09-30": pd.DataFrame(), "2026-09-29": df(row(d="2026-09-29"))}))
    assert r1["usedFallback"] is True and r1["fallbackDays"] == 1 and r1["ageDays"] == 9, r1
    ok("★fallbackDays 从'本该用的最新交易日'算：早上用09-30不算回退(0天，但数据已是8天前=ageDays)；退到09-29是1天")


def test_backfill_consecutive_misses_reset_after_a_success():
    days = trading_days(date(2026, 9, 1), date(2026, 10, 8))
    tab = full_table(days)
    newest_first = list(reversed(days))
    for i in (1, 2, 3, 5, 6, 7):      # 失败3个、成功1个、再失败3个：任何一段都没到8个连续
        tab[newest_first[i].isoformat()] = pd.DataFrame()
    d = tempfile.mkdtemp()
    try:
        rep = run_bf(d, tab, max_consecutive_misses=4)
        assert rep["blocked"] is False and rep["added"] == len(days) - 6, rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★连续失败计数在成功后清零：失败3、成功1、失败3(上限4)——不会因为累计6次失败就误判被限流")


# ---------------- 硬性时限 ----------------
def test_a_stuck_call_is_abandoned_at_the_deadline_without_blocking():
    """★akshare 的 futures_spot_price 内部是 while True 循环，页面加载成功但日期对不上时只 sleep(3) 就继续、不累计失败次数，可能长时间不返回。"""
    stop = threading.Event()
    def stuck():
        stop.wait(30)
        return "不该返回"
    t0 = time.time()
    ok_, res = fd._run_with_deadline(stuck, 0.3)
    el = time.time() - t0
    stop.set()
    assert ok_ is False and "超时" in res and el < 2.0, (ok_, res, el)
    assert fd._run_with_deadline(lambda: 42, 2.0) == (True, 42)
    ok_, res = fd._run_with_deadline(lambda: (_ for _ in ()).throw(ValueError("炸了")), 2.0)
    assert ok_ is False and "ValueError" in res and "炸了" in res, res
    ok("★硬性时限：卡住的调用0.3秒后被放弃(耗时<2秒)，正常返回照常，抛异常带回类型和信息")


# ---------------- 候选日期 ----------------
def test_candidate_dates_skip_today_before_the_evening_publication():
    # 2026-10-08(周四，国庆休市结束，交易日)
    before = fd._spot_candidate_dates(datetime(2026, 10, 8, 10, 0), 4)
    assert before == [date(2026, 9, 30), date(2026, 9, 29), date(2026, 9, 28), date(2026, 9, 25)], before      # 10-01~10-07 休市；今天傍晚前不试
    after = fd._spot_candidate_dates(datetime(2026, 10, 8, 20, 0), 4)
    assert after == [date(2026, 10, 8), date(2026, 9, 30), date(2026, 9, 29), date(2026, 9, 28)], after
    edge_in = fd._spot_candidate_dates(datetime(2026, 10, 8, 18, 30), 1)
    edge_out = fd._spot_candidate_dates(datetime(2026, 10, 8, 18, 29), 1)
    assert edge_in == [date(2026, 10, 8)] and edge_out == [date(2026, 9, 30)], (edge_in, edge_out)
    ok("★候选日期只含交易日(国庆休市10-01~10-07跳过)；18:30 前不试当天(站点收盘后才有，白等会拖慢每小时的抓取)，18:30 起先试当天；边界精确到分钟")


# ---------------- fetch_spot_basis ----------------
def fetcher(table, log=None):
    def _f(d_iso):
        if log is not None:
            log.append(d_iso)
        v = table.get(d_iso)
        if isinstance(v, Exception):
            raise v
        return v
    return _f


NOW = datetime(2026, 10, 8, 20, 0)


def test_live_uses_the_first_candidate_that_has_data_and_reports_all_fields():
    log = []
    r = fd.fetch_spot_basis(now_bj=NOW, fetch=fetcher({"2026-10-08": df(row(d="2026-10-08", sp=3310.0, dom_p=3380.0))}, log))
    assert r["available"] and r["value"] == -70.0 and r["date"] == "2026-10-08" and r["usedFallback"] is False and r["fallbackDays"] == 0, r
    assert log == ["2026-10-08"], log
    for k in ("spot", "domSymbol", "domPrice", "nearSymbol", "nearPrice", "siteBasis", "consistent", "source", "sourceUrl", "spotDefinition"):
        assert k in r, k
    assert "100ppi" in r["sourceUrl"] and "2026-10-08" in r["sourceUrl"] and "生意社" in r["source"], r
    ok("★线上：当天有数据就用当天(-70=3310-3380)，只请求一次；带出现货价/主力合约/结算价/站点基差/一致性/来源/网址/现货口径说明")


def test_live_falls_back_to_earlier_trading_days_and_says_so():
    log = []
    table = {"2026-10-08": pd.DataFrame(), "2026-09-30": df(row(d="2026-09-30", sp=3300.0, dom_p=3372.0))}
    r = fd.fetch_spot_basis(now_bj=NOW, fetch=fetcher(table, log))
    assert r["available"] and r["date"] == "2026-09-30" and r["usedFallback"] is True and r["fallbackDays"] == 8 and log == ["2026-10-08", "2026-09-30"], (r, log)
    ok("★当天还没有(空表)：退到前一个交易日(09-30，跨过国庆休市)，usedFallback=True、fallbackDays=8(距今天8天)，只试了2个日期")


def test_live_exceptions_and_empties_never_crash_and_give_a_diagnostic():
    table = {"2026-10-08": RuntimeError("连接被重置"), "2026-09-30": None, "2026-09-29": pd.DataFrame(), "2026-09-28": df(row(var="RB"))}
    log = []
    r = fd.fetch_spot_basis(now_bj=NOW, fetch=fetcher(table, log), max_attempts=4)
    assert r["available"] is False and len(log) == 4 and len(r["debug"]["attempted"]) == 4, (r, log)
    assert "连接被重置" in str(r["debug"]["attempted"][0]) and "没有豆粕" in str(r["debug"]["attempted"][3]) or "M" in str(r["debug"]["attempted"][3]), r["debug"]
    ok("★每个候选日抛异常/返回None/空表/没有豆粕行：都不崩，最多试4个日期，诊断里逐日写明原因(连接被重置…)")


def test_live_respects_the_attempt_limit_and_the_per_call_deadline():
    log = []
    fd.fetch_spot_basis(now_bj=NOW, fetch=fetcher({}, log), max_attempts=2)
    assert len(log) == 2, log
    stop = threading.Event()
    def stuck(d_iso):
        stop.wait(30)
    t0 = time.time()
    r = fd.fetch_spot_basis(now_bj=NOW, fetch=stuck, max_attempts=2, deadline_s=0.3)
    el = time.time() - t0
    stop.set()
    assert r["available"] is False and el < 3.0 and "超时" in str(r["debug"]["attempted"]), (r, el)
    ok("★最多试 max_attempts 个日期；卡住的抓取按单次时限放弃(2次×0.3秒，总耗时<3秒)，整体仍返回诊断")


def test_live_flags_a_mismatch_with_the_sites_own_basis():
    r = fd.fetch_spot_basis(now_bj=NOW, fetch=fetcher({"2026-10-08": df(row(d="2026-10-08", sp=3310.0, dom_p=3380.0, dom_b=12.0))}))      # 站点 +12 → 取反 -12
    assert r["available"] and r["value"] == -70.0 and r["consistent"] is False and r["siteBasis"] == -12.0, r
    ok("站点自己的基差(-12)和自算(-70)对不上：仍取自算值，consistent=False，让页面能提示")


# ---------------- 历史 ----------------
def test_history_records_the_spot_basis_with_its_context():
    d = tempfile.mkdtemp()
    try:
        assert "spot_basis" in hs.SERIES_META and hs.SERIES_META["spot_basis"]["freq"] == "daily"
        res = {"spotBasis": {"available": True, "value": -72.0, "date": "2026-09-30", "spot": 3300.0, "domSymbol": "M2701", "domPrice": 3372.0, "siteBasis": -72.0}}
        hs.update_and_attach(res, base_dir=d)
        p = hs.load_series("spot_basis", d)["points"][0]
        assert p["d"] == "2026-09-30" and p["v"] == -72.0 and p["x"] == {"sp": 3300.0, "dom": "M2701", "dp": 3372.0, "sb": -72.0}, p
        assert "history" in res["spotBasis"], "摘要要挂回结果里(页面的分位说明读它)"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★历史：spot_basis 序列(日频)，点里带 x={sp现货价, dom主力合约, dp结算价, sb站点基差}；摘要挂回结果")


# ---------------- 回填 ----------------
def trading_days(a, b):
    out, d = [], a
    while d <= b:
        if __import__("cn_calendar").dce_is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def full_table(days, base=3300.0, dom="m2701"):
    return {x.isoformat(): df(row(d=x.isoformat(), sp=base + i, dom_p=base + i + 70.0, dom=dom)) for i, x in enumerate(days)}


def run_bf(d, table, log=None, **kw):
    kw.setdefault("sleep_s", 0)
    return bf.backfill_spot_basis(base_dir=d, today=kw.pop("today", date(2026, 10, 8)), start=kw.pop("start", date(2026, 9, 1)), fetch=fetcher(table, log), **kw)


def test_backfill_writes_one_point_per_trading_day_newest_first_and_never_asks_for_closed_days():
    days = trading_days(date(2026, 9, 1), date(2026, 10, 8))
    log = []
    d = tempfile.mkdtemp()
    try:
        rep = run_bf(d, full_table(days), log)
        p = hs.load_series("spot_basis", d)["points"]
        assert [x["d"] for x in p] == [x.isoformat() for x in days] and rep["added"] == len(days) == rep["total"], (len(p), len(days), rep["added"])
        assert log == [x.isoformat() for x in reversed(days)], "从最新的交易日开始请求"
        assert all(date.fromisoformat(x).weekday() < 5 for x in log) and not any("2026-10-0" in x and x <= "2026-10-07" for x in log), "周末和国庆休市日一次都没请求"
        assert all(x["v"] == -70.0 for x in p), "每天 sp 比 dom_price 低70：基差恒为-70"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★回填：每个交易日一个点(基差-70)，从最新开始请求，周末和国庆休市日一次都不请求(不浪费对站点的请求)")


def test_backfill_skips_dates_already_in_history_and_is_idempotent():
    days = trading_days(date(2026, 9, 1), date(2026, 10, 8))
    d = tempfile.mkdtemp()
    try:
        hs.record_points("spot_basis", [{"d": days[0].isoformat(), "v": 999.0}, {"d": days[-1].isoformat(), "v": 888.0}], d)
        log = []
        run_bf(d, full_table(days), log)
        p = {x["d"]: x["v"] for x in hs.load_series("spot_basis", d)["points"]}
        assert p[days[0].isoformat()] == 999.0 and p[days[-1].isoformat()] == 888.0 and len(p) == len(days), "已有的点原样保留(线上累积的不被覆盖)"
        assert days[0].isoformat() not in log and days[-1].isoformat() not in log and len(log) == len(days) - 2, log
        log2 = []
        rep2 = run_bf(d, full_table(days), log2)
        assert log2 == [] and rep2["added"] == 0, (log2, rep2)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★已有历史的日期不请求、不覆盖(999/888 原样保留)；补完后再跑一次一个请求都不发(幂等)")


def test_backfill_time_budget_stops_gracefully_and_resumes():
    days = trading_days(date(2026, 9, 1), date(2026, 10, 8))
    d = tempfile.mkdtemp()
    try:
        t = {"now": 0.0}
        tab = full_table(days)
        base = fetcher(tab)
        def slow(x):
            t["now"] += 100.0
            return base(x)
        rep = bf.backfill_spot_basis(base_dir=d, today=date(2026, 10, 8), start=date(2026, 9, 1), fetch=slow, sleep_s=0, time_budget_s=250, clock=lambda: t["now"])
        n = len(hs.load_series("spot_basis", d)["points"])
        assert rep["stoppedEarly"] is True and n == 3 and rep["remaining"] == len(days) - 3, (rep["stoppedEarly"], n, rep["remaining"])      # 已用时 0、100、200 都 ≤250，第4个(300>250)才停
        rep2 = run_bf(d, tab)
        assert rep2["stoppedEarly"] is False and rep2["remaining"] == 0 and len(hs.load_series("spot_basis", d)["points"]) == len(days), rep2
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★时间预算：超时就停(已补3个点保存)，报告 stoppedEarly 和 remaining；再点一次接着补完")


def test_backfill_time_budget_boundary_is_exactly_the_budget():
    """★变异检查发现：预算测试里已用时是 0/100/200/300，从来不会恰好等于预算。预算200、每次100秒：开始每个交易日前已用时 0、100、200——
    恰好等于预算(200)时还允许请求第3个(用 > 不是 >=)，到300才停，共请求3个。"""
    days = trading_days(date(2026, 9, 1), date(2026, 10, 8))
    d = tempfile.mkdtemp()
    try:
        t = {"now": 0.0}
        base = fetcher(full_table(days))
        def slow(x):
            t["now"] += 100.0
            return base(x)
        rep = bf.backfill_spot_basis(base_dir=d, today=date(2026, 10, 8), start=date(2026, 9, 1), fetch=slow, sleep_s=0, time_budget_s=200, clock=lambda: t["now"])
        assert rep["attempted"] == 3 and rep["stoppedEarly"] is True and len(hs.load_series("spot_basis", d)["points"]) == 3, (rep["attempted"], rep["stoppedEarly"])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★预算边界：已用时恰好等于预算(200秒)时还请求第3个，超过(300秒)才停——共请求3个")


def test_backfill_stops_when_the_site_seems_to_block_us_but_keeps_what_it_has():
    days = trading_days(date(2026, 9, 1), date(2026, 10, 8))
    tab = full_table(days)
    for x in days[:-3]:      # 最新的3天有数据，之后全部返回空(像被限流)
        tab[x.isoformat()] = pd.DataFrame()
    log = []
    d = tempfile.mkdtemp()
    try:
        rep = run_bf(d, tab, log, max_consecutive_misses=8)
        assert rep["blocked"] is True and rep["added"] == 3 and len(log) == 3 + 8, (rep["blocked"], rep["added"], len(log))
        assert len(hs.load_series("spot_basis", d)["points"]) == 3 and any("限流" in n for n in rep["notes"]), rep["notes"]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★连续8天空表/失败：判断站点在限流，停手(不继续消耗请求)，已拿到的3个点保存，报告 blocked=True")


def test_backfill_isolated_misses_do_not_stop_the_run_and_are_listed():
    days = trading_days(date(2026, 9, 1), date(2026, 10, 8))
    tab = full_table(days)
    tab[days[5].isoformat()] = pd.DataFrame()
    tab[days[9].isoformat()] = RuntimeError("超时")
    d = tempfile.mkdtemp()
    try:
        rep = run_bf(d, tab, max_consecutive_misses=8)
        assert rep["blocked"] is False and rep["added"] == len(days) - 2 and sorted(rep["misses"]) == sorted([days[5].isoformat(), days[9].isoformat()]), rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("零星的缺失(一天空表、一天超时)不叫停整个回填，记进 misses")


def test_backfill_reports_site_mismatches_and_contract_rolls():
    days = trading_days(date(2026, 9, 21), date(2026, 10, 8))
    tab = {}
    for i, x in enumerate(days):
        dom = "m2609" if i < 4 else "m2701"      # 第4个交易日起主力合约换月(akshare 的合约代码是小写带品种前缀)
        tab[x.isoformat()] = df(row(d=x.isoformat(), sp=3300.0, dom_p=3370.0 if dom == "m2609" else 3420.0, dom=dom, dom_b=(-999.0 if i == 6 else None)))
    d = tempfile.mkdtemp()
    try:
        rep = run_bf(d, tab, start=date(2026, 9, 21))
        assert rep["siteMismatches"] == 1 and rep["siteMismatchSamples"][0]["d"] == days[6].isoformat(), rep["siteMismatches"]
        assert rep["contractRolls"] == [{"from": days[3].isoformat(), "to": days[4].isoformat(), "dom": "m2609→m2701"}], rep["contractRolls"]
        pts = {x["d"]: x["v"] for x in hs.load_series("spot_basis", d)["points"]}
        assert pts[days[3].isoformat()] == -70.0 and pts[days[4].isoformat()] == -120.0, "换月处基差从-70跳到-120(换了对比的合约)"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★报告标出站点基差与自算不符的日期(1个)和主力合约换月点(m2609→m2701：基差从-70跳到-120，是换月造成的断层，不是行情)")


def test_backfill_saves_progress_incrementally_and_reports_nothing_found_as_error():
    days = trading_days(date(2026, 8, 1), date(2026, 10, 8))
    d = tempfile.mkdtemp()
    orig = hs.record_points
    calls = []
    hs.record_points = lambda key, pts, base_dir=None: (calls.append(len(pts)), orig(key, pts, base_dir))[1]
    try:
        run_bf(d, full_table(days), start=date(2026, 8, 1), save_every=10)
    finally:
        hs.record_points = orig
        shutil.rmtree(d, ignore_errors=True)
    assert len(calls) >= len(days) // 10 and sum(calls) >= len(days), (calls, len(days))
    d2 = tempfile.mkdtemp()
    try:
        rep = run_bf(d2, {}, max_consecutive_misses=100)
        assert "error" in rep and not os.path.exists(os.path.join(d2, "spot_basis.json")), rep
    finally:
        shutil.rmtree(d2, ignore_errors=True)
    ok("★每攒够 save_every 个点就落盘一次(被强杀也不丢)；一个点都没拿到：报告写 error，不写文件")


def test_the_collection_routine_actually_calls_the_new_fetch_and_not_the_mysteel_one():
    """★打包前的核对发现：我写了 fetch_spot_basis、前端也改成读 spotBasis，**但主流程里调用抓取的那一行忘了改**(仍是 mysteelBasis: fetch_mysteel_basis())，
    所以线上不会产生 spotBasis，页面会一直显示'暂无数据'。所有测试都通过，是因为没有任何测试检查'主流程里调的是新函数'。
    这条测试读主流程的源码：结果字典里必须有 spotBasis→fetch_spot_basis()，且不能再有 mysteelBasis→fetch_mysteel_basis()；
    并且前端读的 dataKey 必须就是主流程写出的键(两头对上，否则一头写、一头读不同的名字，页面静默没数据)。"""
    import re
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_data.py"), encoding="utf-8").read()
    assert re.search(r'"spotBasis"\s*:\s*fetch_spot_basis\(\)', src), "主流程里没有 spotBasis: fetch_spot_basis()"
    assert not re.search(r'"mysteelBasis"\s*:\s*fetch_mysteel_basis\(\)', src), "主流程里还在调用 Mysteel 基差"
    html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), encoding="utf-8").read()
    m = re.search(r"key:'basis'.*?dataKey:'(\w+)'", html, re.S)
    assert m and m.group(1) == "spotBasis", f"前端基差卡读的键是 {m.group(1) if m else None}，主流程写的是 spotBasis"
    ok("★主流程调用的是 fetch_spot_basis(键 spotBasis)，不再调用 Mysteel 基差；前端基差卡读的 dataKey 与主流程写出的键一致")


def test_end_to_end_main_run_writes_spot_basis_into_latest_json_and_the_history():
    """★端到端：真的跑一遍 main()——把它调用的其它 fetch_* 全部换成'不可用'的桩，只让基差走假的 akshare 表——检查 latest.json 里有 spotBasis(带 history 摘要)、
    history 目录里有 spot_basis.json、没有 mysteelBasis。单点测试(解析/回填/历史)都绿也不能保证它们在主流程里接得上——上一轮就漏过一次。"""
    import json, io, contextlib
    d = tempfile.mkdtemp()
    keep = ("fetch_spot_basis", "fetch_json_debug", "fetch_text_debug", "fetch_basis_page", "fetch_dce_position_rank_multi")      # 基差走真代码；工具函数不换；龙虎榜返回的是'以合约代码为键的字典'，下面单独给符合真实形状的桩
    names = [n for n in dir(fd) if n.startswith("fetch_") and callable(getattr(fd, n)) and n not in keep]
    saved = {n: getattr(fd, n) for n in names}
    saved["fetch_dce_position_rank_multi"] = fd.fetch_dce_position_rank_multi
    saved_out, saved_akshare = fd.OUTPUT_PATH, fd._akshare_spot_price
    try:
        for n in names:
            setattr(fd, n, lambda *a, **k: {"available": False, "reason": "测试桩"})
        fd.fetch_dce_position_rank_multi = lambda codes, *a, **k: {c: {"available": False, "reason": "测试桩"} for c in codes}
        fd.OUTPUT_PATH = os.path.join(d, "latest.json")
        fd._akshare_spot_price = lambda d_iso: df(row(d=d_iso, sp=3300.0, dom_p=3372.0))
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                fd.main()
        except SystemExit:
            pass
        assert os.path.exists(fd.OUTPUT_PATH), "main() 没有写出 latest.json：\n" + buf.getvalue()[-800:]
        out = json.load(open(fd.OUTPUT_PATH, encoding="utf-8"))
        sb = out.get("spotBasis")
        assert sb and sb["available"] is True and sb["value"] == -72.0 and sb["domSymbol"] == "m2701" and sb["consistent"] is True, sb
        assert "mysteelBasis" not in out, "latest.json 里不应该再有 mysteelBasis"
        assert "history" in sb, "history_store 没有给 spotBasis 挂摘要"
        assert os.path.exists(os.path.join(d, "history", "spot_basis.json")), os.listdir(os.path.join(d, "history")) if os.path.isdir(os.path.join(d, "history")) else "没有 history 目录"
        pts = hs.load_series("spot_basis", os.path.join(d, "history"))["points"]
        assert len(pts) == 1 and pts[0]["v"] == -72.0 and pts[0]["x"]["dom"] == "m2701", pts
    finally:
        for n, f in saved.items():
            setattr(fd, n, f)
        fd.OUTPUT_PATH, fd._akshare_spot_price = saved_out, saved_akshare
        shutil.rmtree(d, ignore_errors=True)
    ok("★端到端：真跑 main()(其它数据源全换成桩)：latest.json 里有 spotBasis(-72，m2701，一致，带 history 摘要)、history/spot_basis.json 有1个点、没有 mysteelBasis")


def test_backfill_registration_and_the_mysteel_basis_job_is_retired():
    assert "spot_basis" in bf.JOBS and bf.JOBS["spot_basis"] is bf.backfill_spot_basis
    assert "spot_basis" not in bf.DEFAULT_JOBS, "要请求约700次站点，不进默认(all)，需要时 only=spot_basis"
    assert "basis" not in bf.JOBS and "basis" not in bf.DEFAULT_JOBS, "Mysteel 基差回填已停用"
    ok("spot_basis 已登记且不在默认(all)里；Mysteel 的 basis 回填任务已从任务表移除")


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
