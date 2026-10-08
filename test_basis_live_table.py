# -*- coding: utf-8 -*-
"""线上基差抓取改读数据表(v101.6)。运行：python3 test_basis_live_table.py
背景(2026-10-08 报告)：每篇《全国主要市场豆粕基差价格汇总》正文底下有一张每市场一行的表，页面顶部"智能摘要 内容由AI生成"只是概括，线上一直解析的是概括。
回填跑下来：735 个日期里只有 24 个读到了表——怀疑是正文截取把表丢了(取"标题最后一次出现"到"免责声明"之间，推荐区重复标题或表在免责声明之后就会丢)。
★HTML 夹具是我按真实页面结构**构造**的(没有拿到完整的原始网页)，位置假设(推荐区重复标题 / 表在免责声明之后)是对失败原因的**推测**，用整页解析兜底 + 详细诊断来应对。"""
import os, sys, traceback, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd
import history_store as hs

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


TITLE = "Mysteel：全国主要市场豆粕基差价格汇总（20261008）"
NEIGHBOR = "Mysteel：全国主要市场豆粕基差价格汇总（20261007）"
URL = "https://ncp.mysteel.com/a/26100811/ABC.html"
TABLE = ("<table><tr><th>省份</th><th>市场</th><th>期货合约</th><th>现货基差</th><th>涨跌</th></tr>"
         "<tr><td>云南</td><td>昆明</td><td>01</td><td>-20</td><td>0</td></tr>"
         "<tr><td>山东</td><td>日照</td><td>01</td><td>-110</td><td>-20</td></tr>"
         "<tr><td>江苏</td><td>南通</td><td>01</td><td>-120</td><td>0</td></tr></table>")
SUMMARY = "2026年10月8日全国主要市场豆粕基差价格汇总显示，多数地区基差下跌。具体数值方面，大连基差最高为100，南通最低为-100。"      # 取'南通 -100'(摘要口径)


def page(table_html=TABLE, recommend_title=False, table_after_disclaimer=False, extra=""):
    rec = f"<div>相关推荐 <a>{TITLE}</a></div>" if recommend_title else ""
    inner = "" if table_after_disclaimer else table_html
    after = table_html if table_after_disclaimer else ""
    return (f"<html><head><style>.x{{}}</style><script>var a=1;</script></head><body><div>首页 资讯 {NEIGHBOR}</div><h1>{TITLE}</h1>"
            f"<p>智能摘要 内容由AI生成 {SUMMARY}</p>{inner}{extra}{rec}<p>免责声明：本文仅供参考</p>{after}<div>相关文章 {NEIGHBOR}</div></body></html>")


def fetcher(raw=None, err=None, boom=False, log=None):
    def _f(url, headers=None, retries=2, timeout=20):
        if log is not None:
            log.append({"url": url, "retries": retries, "timeout": timeout, "headers": headers})
        if boom:
            raise RuntimeError("网络炸了")
        if err:
            return None, {"error": err}
        return raw, {}
    return _f


# ---------------- fetch_basis_page ----------------
def test_page_table_inside_the_region_is_read_from_the_region():
    r = fd.fetch_basis_page(URL, TITLE, fetch=fetcher(page()))
    assert r["ok"] and r["where"] == "region", r
    assert fd.basis_from_table(r["text"]) == ("日照", -110.0, "01"), fd.basis_from_table(r["text"])
    ok("★HTML 表格(td 单元格)被压平成文字后能读：日照 01合约 -110；表在正文区域里 → where='region'")


def test_page_table_is_found_even_when_the_title_is_repeated_in_a_recommendation_block():
    """★推测的失败原因之一：正文之后的推荐区又出现了同一个标题，区域截取取'标题最后一次出现'，截出来的区域里没有表。"""
    raw = page(recommend_title=True)
    region_only = fd._extract_article_region(fd._html_to_text(raw), TITLE)
    assert fd.parse_basis_table(region_only) == {}, "夹具有效：旧的区域截取在这种页面上确实丢了表"
    r = fd.fetch_basis_page(URL, TITLE, fetch=fetcher(raw))
    assert r["ok"] and r["where"] == "page" and fd.basis_from_table(r["text"])[:2] == ("日照", -110.0), r
    ok("★推荐区重复了标题：旧的区域截取读不到表(夹具有效)；整页兜底读到了(where='page')")


def test_page_table_is_found_when_it_sits_after_the_disclaimer():
    raw = page(table_after_disclaimer=True)
    assert fd.parse_basis_table(fd._extract_article_region(fd._html_to_text(raw), TITLE)) == {}, "夹具有效：区域(到免责声明为止)里没有表"
    r = fd.fetch_basis_page(URL, TITLE, fetch=fetcher(raw))
    assert r["ok"] and r["where"] == "page" and fd.basis_from_table(r["text"])[:2] == ("日照", -110.0), r
    ok("★表在免责声明之后：区域里没有(夹具有效)；整页兜底读到了")


def test_page_without_a_table_returns_rich_diagnostics():
    other = "<p>现货基差 日照 -90 20 南通 -100 0（这种写法没有合约列）</p>"
    r = fd.fetch_basis_page(URL, TITLE, fetch=fetcher(page(table_html=other)))
    assert r["ok"] and r["where"] is None, r
    d = r["diag"]
    assert d["tableTags"] == 0 and d["headerSeen"] is True and "日照" in d["afterHeader"] and d["titleCount"] == 1, d      # 这个夹具里标题只出现一次
    assert d["rawLen"] == len(page(table_html=other)) and d["fullLen"] > 0 and d["regionLen"] > 0 and "regionHead" in d, d
    assert d["disclaimerAt"] > 0, d
    r3 = fd.fetch_basis_page(URL, TITLE, fetch=fetcher(page(table_html=other, recommend_title=True)))
    assert r3["diag"]["titleCount"] == 2, r3["diag"]      # 推荐区重复了标题：诊断能数出来(这正是定位'区域被截偏'的线索)
    r2 = fd.fetch_basis_page(URL, TITLE, fetch=fetcher("<html><body><h1>%s</h1><img src='a.png'><img src='b.png'><p>免责声明</p></body></html>" % TITLE))
    assert r2["diag"]["imgTags"] == 2 and r2["diag"]["headerSeen"] is False and r2["diag"]["afterHeader"] == "", r2["diag"]
    ok("★没有表时给出能定位原因的诊断：table标签数、图片数、有没有'现货基差'表头及其后面300字、标题出现次数、免责声明位置、原始/整页/区域长度、区域开头")


def test_page_with_table_tag_but_unusable_rows_is_reported_as_such():
    bad = "<table><tr><th>市场</th><th>基差</th></tr><tr><td>日照</td><td>-90</td></tr></table>"
    r = fd.fetch_basis_page(URL, TITLE, fetch=fetcher(page(table_html=bad)))
    assert r["ok"] and r["where"] is None and r["diag"]["tableTags"] == 1, r
    ok("有 <table> 但行格式不对(缺合约/涨跌列)：读不出，诊断里 tableTags=1(说明页面有表，是格式不认识)")


def test_page_request_failures_never_raise():
    r = fd.fetch_basis_page(URL, TITLE, fetch=fetcher(err="HTTP 403"))
    assert r["ok"] is False and "403" in r["err"], r
    r = fd.fetch_basis_page(URL, TITLE, fetch=fetcher(boom=True))
    assert r["ok"] is False and "网络炸了" in r["err"], r
    r = fd.fetch_basis_page(URL, TITLE, fetch=fetcher(raw=""))
    assert r["ok"] is False and r["err"], r
    ok("请求失败(403)、抛异常、返回空：都返回 ok=False 和原因，绝不抛异常(线上抓取不能被这一步拖垮)")


def test_page_fetch_uses_a_light_retry_and_timeout_and_the_mysteel_referer():
    log = []
    fd.fetch_basis_page(URL, TITLE, fetch=fetcher(page(), log=log))
    assert log[0]["retries"] <= 2 and log[0]["timeout"] <= 15 and log[0]["headers"]["Referer"] == "https://ncp.mysteel.com/", log
    ok("正文请求：重试≤2次、超时≤15秒(每小时的线上抓取不能被拖慢)，带 Mysteel 的 Referer")


# ---------------- 线上 fetch_mysteel_basis ----------------
def with_search(items, fn):
    orig = fd.fetch_json_debug
    fd.fetch_json_debug = lambda *a, **k: ({"resultCode": 0, "total": len(items), "dataList": items}, {})
    try:
        return fn()
    finally:
        fd.fetch_json_debug = orig


def art(d, content=SUMMARY, url=URL, title=None, hhmm="10:00:00"):
    return {"publishTime": f"{d} {hhmm}", "title": title or f"Mysteel：全国主要市场豆粕基差价格汇总（{d.replace('-', '')}）", "content": content, "url": url}


def page_ok(text_html=None):
    def _p(url, title):
        r = fd.fetch_basis_page(url, title, fetch=fetcher(text_html or page()))
        return r
    return _p


def test_live_prefers_the_table_over_the_ai_summary():
    items = [art("2026-10-08")]
    r = with_search(items, lambda: fd.fetch_mysteel_basis(today=__import__("datetime").date(2026, 10, 8), fetch_page=page_ok()))
    assert r["available"] and r["value"] == -110.0 and r["city"] == "日照" and r["src"] == "table" and r["contract"] == "01", r
    ok("★线上：摘要说南通 -100，表里日照 -110 → 取表：-110、日照、src='table'、合约01")


def test_live_falls_back_to_the_summary_when_the_page_has_no_table_or_fails():
    import datetime
    t = datetime.date(2026, 10, 8)
    for label, fp in (("页面请求失败", lambda url, title: {"ok": False, "err": "HTTP 403", "text": "", "where": None, "diag": {}}),
                      ("页面没有表", lambda url, title: {"ok": True, "err": None, "text": "没有表", "where": None, "diag": {}}),
                      ("抓取函数抛异常", lambda url, title: (_ for _ in ()).throw(RuntimeError("炸了")))):
        r = with_search([art("2026-10-08")], lambda: fd.fetch_mysteel_basis(today=t, fetch_page=fp))
        assert r["available"] and r["value"] == -100.0 and r["city"] == "南通" and r["src"] == "summary" and r["contract"] is None, (label, r)
    ok("★页面请求失败(403) / 页面没有表 / 抓取抛异常：都退回摘要(南通 -100，src='summary')，线上不崩、行为与以前一致")


def test_live_does_not_fetch_untrusted_or_missing_urls():
    import datetime
    calls = []
    def fp(url, title):
        calls.append(url)
        return {"ok": True, "err": None, "text": "", "where": None, "diag": {}}
    for u in ("https://evil.example.com/a", "", None):
        with_search([art("2026-10-08", url=u)], lambda: fd.fetch_mysteel_basis(today=datetime.date(2026, 10, 8), fetch_page=fp))
    assert calls == [], calls
    ok("不可信域名 / 空网址 / 没有网址：不请求正文")


def test_live_table_can_rescue_an_article_whose_summary_has_no_value():
    import datetime
    items = [art("2026-10-08", content="2026年10月8日，全国主要市场豆粕基差以01合约为准。多数地区基差下跌10-20元/吨。"), art("2026-10-07", url="https://ncp.mysteel.com/a/26100711/OLD.html")]
    r = with_search(items, lambda: fd.fetch_mysteel_basis(today=datetime.date(2026, 10, 8), fetch_page=page_ok()))
    assert r["available"] and r["date"] == "2026-10-08" and r["usedFallback"] is False and r["src"] == "table", r
    ok("★最新一篇摘要取不出值，但正文有表：直接用最新这篇的表(usedFallback=False)，不用退回前一天")


def test_live_body_fetches_are_limited_per_run():
    import datetime
    calls = []
    def fp(url, title):
        calls.append(url)
        return {"ok": True, "err": None, "text": "没有表", "where": None, "diag": {}}
    items = [art(f"2026-10-0{i}", content="2026年10月，各地基差持平。", url=f"https://ncp.mysteel.com/a/2610{i}/x.html") for i in (8, 7, 6, 5, 4)]
    r = with_search(items, lambda: fd.fetch_mysteel_basis(today=datetime.date(2026, 10, 8), fetch_page=fp))
    assert len(calls) == fd.BASIS_LIVE_MAX_BODY_FETCHES == 2, calls
    assert r["available"] is False and "沿海代表城市" in r["reason"], r
    ok("★每次运行最多请求2篇正文(BASIS_LIVE_MAX_BODY_FETCHES)；都取不出时仍给出原来的诊断(沿海代表城市没有确切数值)")


def test_live_table_value_still_obeys_the_plausibility_range():
    import datetime
    bad = page(table_html=TABLE.replace("-110", "-9999"))
    r = with_search([art("2026-10-08")], lambda: fd.fetch_mysteel_basis(today=datetime.date(2026, 10, 8), fetch_page=page_ok(bad)))
    # 日照 -9999 超出合理范围 → 表里取下一个优先级的城市(南通 -120)
    assert r["available"] and r["value"] == -120.0 and r["city"] == "南通" and r["src"] == "table", r
    ok("表里日照 -9999 超出合理范围：当没有，取优先级里下一个有数值的南通 -120(src 仍是 table)")


def test_live_result_keeps_all_the_old_fields():
    import datetime
    r = with_search([art("2026-10-08")], lambda: fd.fetch_mysteel_basis(today=datetime.date(2026, 10, 8), fetch_page=page_ok()))
    for k in ("available", "value", "city", "date", "latestArticleDate", "usedFallback", "fallbackDays", "articleTitle", "source", "sourceUrl", "src", "contract"):
        assert k in r, k
    assert r["sourceUrl"] == URL and "基差" in r["source"]
    ok("线上结果保留所有原来的字段(value/city/date/latestArticleDate/usedFallback/fallbackDays/articleTitle/source/sourceUrl)，新增 src 和 contract")


# ---------------- 历史里记来源和合约 ----------------
def test_history_records_city_source_and_contract_for_the_basis_point():
    d = tempfile.mkdtemp()
    try:
        res = {"mysteelBasis": {"available": True, "value": -110.0, "city": "日照", "date": "2026-10-08", "src": "table", "contract": "01"}}
        hs.update_and_attach(res, base_dir=d)
        p = hs.load_series("basis", d)["points"][0]
        assert p["x"] == {"city": "日照", "src": "table", "contract": "01"}, p
        d2 = tempfile.mkdtemp()
        res2 = {"mysteelBasis": {"available": True, "value": -100.0, "city": "南通", "date": "2026-10-08", "src": "summary", "contract": None}}
        hs.update_and_attach(res2, base_dir=d2)
        assert hs.load_series("basis", d2)["points"][0]["x"] == {"city": "南通", "src": "summary"}, hs.load_series("basis", d2)["points"][0]
        d3 = tempfile.mkdtemp()
        hs.update_and_attach({"mysteelBasis": {"available": True, "value": -90.0, "city": "日照", "date": "2026-10-08"}}, base_dir=d3)
        assert hs.load_series("basis", d3)["points"][0]["x"] == {"city": "日照"}, "没有 src/contract 的旧结果照常只记城市"
        shutil.rmtree(d2, ignore_errors=True)
        shutil.rmtree(d3, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★线上基差记历史：x={city, src, contract}(None 不记)；没有 src/contract 的旧结果照常只记城市")


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
