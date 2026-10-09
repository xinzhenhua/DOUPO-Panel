# -*- coding: utf-8 -*-
"""一次性抓取原始数据(v101.14)：全部用假接口测试(开发环境连不上新浪/Yahoo/大商所)。运行：python3 test_fetch_seasonal_raw.py
★测的是：文件格式能被现有解析器读回、已有文件不重复抓、单项失败不拖垮其它项、报告如实写明失败原因。"""
import os, sys, json, csv, shutil, tempfile, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_seasonal_raw as fr
import dce_rank_files as drf
import seasonal_stats as ss

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


class FakeDF:
    def __init__(self, recs): self._r = recs
    def to_dict(self, orient="records"): return [dict(x) for x in self._r]
    def __len__(self): return len(self._r)


def tmp():
    return tempfile.mkdtemp()


def read_csv(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_parse_rank_list():
    got = fr.parse_rank_list("2023-06:m2309, 2023-07:M2309;2022-12:m2305")
    assert got == [("2023-06", "m2309"), ("2023-07", "m2309"), ("2022-12", "m2305")], got
    assert fr.parse_rank_list("") == [] and fr.parse_rank_list(None) == []
    for bad in ["2023-13:m2309", "2023-06", "2023-06:x"]:
        try:
            fr.parse_rank_list(bad); assert False, bad
        except ValueError:
            pass
    ok("龙虎榜清单'月份:合约'解析；格式不对直接报错而不是悄悄跳过")


def test_weekdays_of_month():
    d = fr.weekdays_of_month("2026-09")
    assert d[0] == "2026-09-01" and d[-1] == "2026-09-30" and len(d) == 22, (d[0], d[-1], len(d))
    assert "2026-09-05" not in d and "2026-09-06" not in d
    ok("某月的工作日列表：2026-09 共22个(周六日不请求)")


def test_rank_text_roundtrips_through_existing_parser():
    recs = []
    for i in range(1, 21):
        recs.append({"rank": i, "vol_party_name": f"成交席位{i}", "vol": 1000 - i, "vol_chg": i,
                     "long_party_name": "高盛期货（代客）" if i == 1 else f"多头{i}", "long_open_interest": 5000 - i, "long_open_interest_chg": -i,
                     "short_party_name": "中信期货" if i == 1 else f"空头{i}", "short_open_interest": 4000 - i, "short_open_interest_chg": 2 * i})
    recs.append({"rank": "总计", "vol_party_name": "", "vol": 99999})   # 合计行必须被忽略
    txt = fr.rank_to_text("2023-07-03", FakeDF(recs))
    p = drf.parse_rank_text(txt)
    assert p["date"] == "2023-07-03" and len(p["buy"]) == 20 and len(p["sell"]) == 20, (p["date"], len(p["buy"]))
    assert p["buy"][0] == {"rank": 1, "name": "高盛期货（代客）", "value": 4999, "change": -1}, p["buy"][0]
    assert p["sell"][1] == {"rank": 2, "name": "空头2", "value": 3998, "change": 4}, p["sell"][1]
    ok("akshare 的榜单表转成大商所文本后，能被 v101.13 的解析器原样读回(含千分位、跳过合计行)")


def test_rank_text_none_when_empty_or_short():
    assert fr.rank_to_text("2023-07-03", FakeDF([])) is None
    assert fr.rank_to_text("2023-07-03", None) is None
    ok("空表/没有榜单 → 不写文件(休市日)")


def test_job_main_writes_csv_and_reports():
    out = tmp()
    class AK:
        def futures_zh_daily_sina(self, symbol):
            assert symbol == "M0"
            return FakeDF([{"date": "2016-10-10", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10, "hold": 20, "settle": 1.4},
                           {"date": "2016-10-11", "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 11, "hold": 21, "settle": 2.4}])
    rep = fr.job_main(out, AK())
    rows = read_csv(os.path.join(out, "M0_daily.csv"))
    assert len(rows) == 2 and rows[0]["date"] == "2016-10-10" and rows[1]["hold"] == "21", rows
    assert rep["ok"] and rep["rows"] == 2 and rep["first"] == "2016-10-10" and rep["last"] == "2016-10-11"
    shutil.rmtree(out)
    ok("M0 主连：写 date/open/high/low/close/volume/hold/settle，报告写点数和起止日期")


def test_job_main_failure_is_reported_not_raised():
    class AK:
        def futures_zh_daily_sina(self, symbol): raise RuntimeError("被限流")
    rep = fr.job_main(tmp(), AK())
    assert rep["ok"] is False and "被限流" in rep["reason"], rep
    ok("接口抛错 → 报告里写原因，不崩")


def test_job_contracts_skips_existing_missing_and_respects_budget():
    out = tmp()
    os.makedirs(os.path.join(out, "contracts"))
    pre = os.path.join(out, "contracts", "M1701.csv")
    open(pre, "w").write("date,open,high,low,close,volume,hold\n2016-12-01,1,1,1,1,1,1\n")
    calls = []
    def kline(sym, max_rows=0):
        calls.append(sym)
        if sym == "M1703":
            return {"available": False, "reason": "新浪没有合约M1703的数据"}
        return {"available": True, "bars": [{"date": "2017-01-03", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 5, "hold": 9, "settle": 1.4}]}
    rep = fr.job_contracts(out, kline, years=(2017, 2017), months=(1, 3, 5), budget_s=1000, sleep=lambda s: None, clock=lambda: 0)
    assert "M1701" not in calls and calls == ["M1703", "M1705"], calls
    assert os.path.exists(os.path.join(out, "contracts", "M1705.csv")) and not os.path.exists(os.path.join(out, "contracts", "M1703.csv"))
    assert rep["skippedExisting"] == ["M1701"] and rep["missing"] == ["M1703"] and rep["fetched"] == ["M1705"], rep
    # 预算用完：停手并记录剩余
    t = [0]
    def clock():
        t[0] += 100; return t[0]
    calls.clear()
    out2 = tmp()
    rep2 = fr.job_contracts(out2, kline, years=(2017, 2017), months=(1, 5, 9), budget_s=150, sleep=lambda s: None, clock=clock)
    assert rep2["stoppedByBudget"] is True and rep2["remaining"], rep2
    shutil.rmtree(out); shutil.rmtree(out2)
    ok("合约日K：已有的不重抓、没有的记入 missing、时间预算用完就停并列出还剩哪些")


def test_contract_files_are_readable_by_seasonal_stats():
    out = tmp()
    def kline(sym, max_rows=0):
        return {"available": True, "bars": [{"date": "2017-01-03", "open": 1, "high": 2, "low": 1, "close": 3000.0, "volume": 5, "hold": 900.0, "settle": 1}]}
    fr.job_contracts(out, kline, years=(2017, 2017), months=(5,), budget_s=1000, sleep=lambda s: None, clock=lambda: 0)
    c = ss.load_contract_files(os.path.join(out, "contracts"))
    assert c == {"m1705": [{"d": "2017-01-03", "close": 3000.0, "hold": 900.0}]}, c
    ok("合约文件 M1705.csv 能被 seasonal_stats.load_contract_files 读回")


YAHOO = {"chart": {"result": [{"timestamp": [1475000000, 1475086400, 1475172800],
                               "indicators": {"quote": [{"close": [300.5, None, 302.0]}]}}], "error": None}}


def test_parse_yahoo_chart_drops_null_closes():
    rows = fr.parse_yahoo_chart(YAHOO)
    assert rows == [("2016-09-27", 300.5), ("2016-09-29", 302.0)], rows
    for bad in [{}, {"chart": {"result": None}}, {"chart": {"result": []}}]:
        assert fr.parse_yahoo_chart(bad) == []
    ok("Yahoo 返回解析：丢掉收盘为空的日子，异常结构返回空表而不是崩")


def test_job_cbot_and_fx_use_yahoo_then_fallback():
    out = tmp()
    urls = []
    def get_json(url):
        urls.append(url)
        if "ZS=F" in url:
            raise RuntimeError("403")
        return YAHOO
    class AK:
        def futures_foreign_hist(self, symbol):
            if symbol == "ZSD":
                return FakeDF([{"date": "2016-10-10", "open": 1, "high": 1, "low": 1, "close": 950.0, "volume": 1}])
            raise RuntimeError("nope")
        def futures_foreign_commodity_subscribe_exchange_symbol(self):
            return FakeDF([{"symbol": "ZSD"}, {"symbol": "ZMD"}])
    rep = fr.job_cbot(out, get_json, AK())
    assert rep["ZM"]["ok"] and rep["ZM"]["source"] == "yahoo" and rep["ZM"]["rows"] == 2, rep
    assert rep["ZS"]["ok"] and rep["ZS"]["source"].startswith("akshare:ZSD"), rep["ZS"]
    assert "ZSD" in rep["availableForeignSymbols"], rep
    assert os.path.exists(os.path.join(out, "cbot_ZM.csv")) and os.path.exists(os.path.join(out, "cbot_ZS.csv"))
    assert any("range=10y" in u or "period1" in u for u in urls)
    r2 = fr.job_fx(out, get_json, AK())
    assert r2["ok"] and os.path.exists(os.path.join(out, "usdcny.csv")), r2
    shutil.rmtree(out)
    ok("CBOT 豆粕/大豆、USD/CNY：优先 Yahoo，失败换 akshare 备选代码，并把 akshare 可用的海外品种代码列进报告")


def test_job_cbot_all_fail_reports_reasons():
    class AK:
        def futures_foreign_hist(self, symbol): raise RuntimeError("x")
        def futures_foreign_commodity_subscribe_exchange_symbol(self): raise RuntimeError("y")
    rep = fr.job_cbot(tmp(), lambda u: (_ for _ in ()).throw(RuntimeError("blocked")), AK())
    assert rep["ZM"]["ok"] is False and "blocked" in rep["ZM"]["reason"], rep
    ok("全部失败：报告写明 Yahoo 和 akshare 各自的原因")


def test_job_rank_writes_to_separate_dir_and_resumes():
    out = tmp()
    calls = []
    def mk():
        return {"m2309": FakeDF([{"rank": i, "vol_party_name": f"a{i}", "vol": 100 - i, "vol_chg": 0, "long_party_name": f"b{i}",
                                  "long_open_interest": 90 - i, "long_open_interest_chg": 1, "short_party_name": f"c{i}",
                                  "short_open_interest": 80 - i, "short_open_interest_chg": -1} for i in range(1, 21)]),
                "m2401": FakeDF([])}
    class AK:
        def futures_dce_position_rank(self, date):
            calls.append(date)
            if date.endswith("0704"):
                raise RuntimeError("休市")
            return mk()
    spec = [("2023-07", "m2309")]
    rep = fr.job_rank(out, AK(), spec, days=["2023-07-03", "2023-07-04", "2023-07-05"], sleep=lambda s: None, clock=lambda: 0, budget_s=1000)
    f3 = os.path.join(out, "M2309_20230703.txt")
    assert os.path.exists(f3) and os.path.exists(os.path.join(out, "M2309_20230705.txt")) and not os.path.exists(os.path.join(out, "M2309_20230704.txt"))
    assert drf.parse_rank_text(open(f3, encoding="utf-8").read())["date"] == "2023-07-03"
    assert rep["written"] == 2 and rep["noData"] == ["M2309:2023-07-04"], rep
    assert rep["firstError"].startswith("RuntimeError") and "休市" in rep["firstError"] and rep["errors"] == 1, rep
    calls.clear()
    rep2 = fr.job_rank(out, AK(), spec, days=["2023-07-03", "2023-07-05"], sleep=lambda s: None, clock=lambda: 0, budget_s=1000)
    assert calls == [] and rep2["written"] == 0 and rep2["skippedExisting"] == 2, (calls, rep2)
    shutil.rmtree(out)
    ok("龙虎榜：每天一次请求、休市日记 noData、已有文件不再请求(可重复点)")


def test_main_runs_each_job_independently_and_writes_report():
    out = tmp()
    class AK:
        def futures_zh_daily_sina(self, symbol): raise RuntimeError("boom")
    rc = fr.main(["--only", "main,fx", "--out", out], ak=AK(), get_json=lambda u: YAHOO, kline=None)
    rep = json.load(open(os.path.join(out, "_fetch_report.json"), encoding="utf-8"))
    assert rep["main"]["ok"] is False and rep["fx"]["ok"] is True, rep
    assert os.path.exists(os.path.join(out, "usdcny.csv"))
    assert "contracts" not in rep
    shutil.rmtree(out)
    ok("main 失败不影响 fx；只跑 --only 指定的项；写 _fetch_report.json")


def test_main_rejects_unknown_job():
    try:
        fr.main(["--only", "nope", "--out", tmp()], ak=object(), get_json=None, kline=None); assert False
    except SystemExit:
        pass
    ok("写错项目名 → 直接报错退出，不悄悄什么都不做")



HTML = ("<html><body><table><tr><th>日期</th><th>北京市</th><th>江苏省</th></tr>"
        "<tr><td>2026-10-08</td><td>3380</td><td>3310</td></tr>"
        "<tr><td>2026-10-09</td><td>-</td><td>3330</td></tr></table></body></html>")


def test_probe_parse_table():
    r = fr.probe_parse(HTML)
    assert r["headers"] == ["日期", "北京市", "江苏省"], r
    assert r["rows"] == [["2026-10-08", "3380", "3310"], ["2026-10-09", "-", "3330"]], r
    assert r["hasJiangsu"] is True and r["tables"] == 1
    r2 = fr.probe_parse("<html>登录</html>")
    assert r2["tables"] == 0 and r2["headers"] == [] and r2["hasJiangsu"] is False
    ok("探测：把返回的网页里的表头和前几行读出来，判断有没有'江苏省'列；没有表格也不崩")


def test_job_probe_reports_each_url_even_when_some_fail():
    seen = []
    def get_raw(url):
        seen.append(url)
        if "bad" in url:
            raise RuntimeError("403")
        return 200, "text/html", HTML.encode("gbk")
    rep = fr.job_probe(get_raw, urls=["https://x/ok", "https://x/bad"])
    assert rep["https://x/ok"]["status"] == 200 and rep["https://x/ok"]["hasJiangsu"] is True, rep
    assert "403" in rep["https://x/bad"]["error"], rep
    assert "江苏省" in rep["https://x/ok"]["head"]
    ok("探测：每个网址单独记状态/表头/开头文字(GBK 也能解码)，失败的只记原因")



def test_job_jiangsu_windows_merge_and_write():
    import datetime as dt
    sample = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw", "mysteel_meal_daily", "sample_20260908_20261009.json"), encoding="utf-8"))
    calls = []
    def search(query, start, end):
        calls.append((query, start.year, end.year))
        if start.year == 2025:
            return [], 0, "搜索接口无返回/返回异常"
        return [dict(x) for x in sample], 20, None
    out = tmp()
    rep = fr.job_jiangsu(out, search, today=dt.date(2026, 10, 9), start_year=2025)
    assert [c[1] for c in calls] == [2025, 2026] and all(c[0] == "全国豆粕价格日报" for c in calls), calls
    rows = read_csv(os.path.join(out, "jiangsu_spot_daily.csv"))
    assert len(rows) == 19 and rows[-1]["date"] == "2026-10-09" and rows[-1]["js_price"] == "3340" and rows[-1]["js_basis"] == "-62" and rows[0]["js_price"] == "", rows[-1]
    raw = [json.loads(l) for l in open(os.path.join(out, "jiangsu_daily_raw.jsonl"), encoding="utf-8")]
    assert len(raw) == 19 and "content" in raw[0] and "url" in raw[0], len(raw)       # 原文留着，以后改解析不用重新联网
    assert rep["ok"] and rep["days"] == 19 and rep["jsPriceDays"] == 11 and rep["windows"][0]["note"] and rep["windows"][1]["fetched"] == 20, rep
    # 再跑一次且这次接口全挂：已有的原文不丢
    rep2 = fr.job_jiangsu(out, lambda q, a, b: ([], 0, "挂了"), today=dt.date(2026, 10, 9), start_year=2025)
    assert rep2["days"] == 19 and len(read_csv(os.path.join(out, "jiangsu_spot_daily.csv"))) == 19, rep2
    shutil.rmtree(out)
    ok("江苏现货：按年分窗口搜索 → 解析 → 写原文jsonl和解析csv；接口失败时已有数据不丢，报告写明每个窗口的结果")


def test_job_jiangsu_nothing_found():
    import datetime as dt
    rep = fr.job_jiangsu(tmp(), lambda q, a, b: ([], 0, "无返回"), today=dt.date(2026, 10, 9), start_year=2026)
    assert rep["ok"] is False and rep["days"] == 0 and "无返回" in json.dumps(rep, ensure_ascii=False)
    ok("一篇都没搜到 → ok=False 并带原因")


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
