# -*- coding: utf-8 -*-
"""现货基差回填(v101.4)。运行：python3 test_basis_backfill.py
基差每天一篇《全国主要市场豆粕基差价格汇总》。2026-06-16 以后的文章摘要里有数字；更早的 33 个月摘要为空，要抓正文。
★正文路径的夹具是我**构造**的(采样只存了标题和摘要，没有老文章正文的真实样本)——正文格式是否能被解析器认出，只能在你的环境第一次真实运行后看报告里的诊断。
摘要路径的夹具全部是 2026-10-02 采样里的真实摘要(逐字)。取值规则与线上 fetch_mysteel_basis 一致：沿海城市优先级(日照/南通/东莞/湛江/防城港/厦门/天津)里第一个有确切数值的城市。"""
import os, sys, traceback, tempfile, shutil
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd
import backfill_history as bf
import history_store as hs

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


# ---- 真实摘要(逐字) ----
S_0616 = "6月16日全国豆粕基差整体稳定，绝大多数市场维持平水状态。区域分化明显：华南地区基差最深达-200，华北地区在-80至-160区间，华中地区集中在-110至-120，西南地区表现最强为+30。仅湖南岳阳出现10个点的下跌，其余市场涨跌幅均为零，反映现货市场供需平衡格局未改。"
S_0626 = "全国豆粕市场基差整体呈现小幅走强态势，多数地区基差出现上涨。华南地区基差维持深度贴水格局，东莞、防城港基差达-180，为全国最低水平。华北及华中地区基差普遍在-70至-110区间波动，其中天津、日照等地基差单日上涨10个点。西南地区基差相对坚挺，昆明、成都等地基差持平或小幅升水。福建厦门成为唯一基差下跌地区，单日回落10个点。整体市场呈现区域分化特征，沿海地区基差压力仍较大。"
S_0730 = "2026年7月30日，全国主要市场豆粕09合约基差多数上涨。昆明、长春基差分别为70和60元/吨，涨幅30元；成都30元/吨，涨20元。沿海及内陆多地基差为负，如南通-100元/吨、日照-90元/吨、防城港-90元/吨，普遍上涨20-30元。天津、沧州、南昌基差持平。整体呈现基差修复态势，部分地区现货相对期货走强。"
S_0812 = "2026年8月12日，全国主要市场豆粕基差以09合约为准。昆明、南通、武汉及岳阳基差持平；其余多数地区基差下跌10-20元/吨。"
S_0924 = "2026年9月24日全国主要市场豆粕基差价格汇总显示，多数地区基差下跌。长春基差120，跌20；天津-60，跌20；日照、湛江、东莞均为-90，跌10；防城港-140，跌10；南通-110，跌10。昆明30，成都40，大连60，西安50，均跌10。南昌-20，周口-50，武汉-30，厦门-20，重庆-10，其中南昌、周口、武汉、厦门基差持平，其余地区基差均有不同程度下跌。"
S_0930 = "2026年9月30日全国主要市场豆粕基差价格汇总显示，多数地区现货基差较前一日下跌。昆明、防城港及南昌等地基差下跌30；日照、东莞、湛江、南通及武汉等地下跌20；长春、成都、天津、周口、厦门、大连及重庆等地下跌10；西安下跌20。仅沧州基差上涨10。岳阳基差持平为0。具体数值方面，大连基差最高为100，南通最低为-100。"
# ---- 构造的正文(老文章正文的真实格式未知，仅用于验证'摘要为空→抓正文→解析→入库'这条逻辑链) ----
B_OK = lambda city, v: f"全国主要市场豆粕基差价格汇总。其中{city}基差{v}元/吨，其余地区暂无变动。"
B_NO = "今日各地基差维持稳定，无明显变化。"

TITLE = lambda d: f"Mysteel：全国主要市场豆粕基差价格汇总（{d.replace('-', '')}）"


def mk(d, text="", title=None, url=None, hhmm="14:00"):
    return {"publishTime": f"{d} {hhmm}", "title": title if title is not None else TITLE(d), "content": text, "url": url if url is not None else f"https://ncp.mysteel.com/a/{d.replace('-', '')}/{hhmm.replace(':', '')}.html"}      # 网址含发布时间：同一天两篇文章网址不同(真实世界如此；否则会被按网址去重合并)


def fake_search(items, calls=None):
    def _s(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        if calls is not None:
            calls.append({"query": query, "start": start.date(), "end": end.date()})
        sel = [i for i in items if start.date().isoformat() <= i["publishTime"][:10] <= end.date().isoformat()]
        return sel, len(sel), None
    return _s


class Bodies:
    """假的正文抓取：按 url 返回 (文本, 错误)；记录抓取顺序。"""
    def __init__(self, mapping=None, default=(None, "正文请求失败(假)")):
        self.mapping, self.default, self.log = mapping or {}, default, []

    def __call__(self, url, title):
        self.log.append(url)
        return self.mapping.get(url, self.default)


def run(items, d, fetch=None, today=date(2026, 10, 1), start=date(2026, 6, 1), **kw):
    return bf.backfill_basis(base_dir=d, today=today, start=start, search=fake_search(items, kw.pop("calls", None)), fetch_body=fetch or Bodies(), sleep_s=0, **kw)


def pts(d):
    return [(p["d"], p["v"], p["x"]["city"], p["x"]["src"]) for p in hs.load_series("basis", d)["points"]]


def test_real_summaries_hand_extracted_with_the_live_rule():
    f = fd._extract_basis_from_article
    assert f(S_0626) == ("东莞", -180.0), f(S_0626)      # 优先级里日照/南通没有确切值；东莞、防城港基差达-180 → 东莞
    assert f(S_0730) == ("日照", -90.0), f(S_0730)       # 日照-90 先于 南通-100、防城港-90
    assert f(S_0924) == ("日照", -90.0), f(S_0924)       # "日照、湛江、东莞均为-90"：共享值，取日照
    assert f(S_0930) == ("南通", -100.0), f(S_0930)      # "南通最低为-100"
    assert f(S_0812) == (None, None) and f(S_0616) == (None, None), "只有持平/区间描述、没有确切城市值的摘要取不出"
    ok("★6篇真实摘要：06-26→东莞-180、07-30→日照-90(同篇还有南通-100/防城港-90)、09-24→日照-90、09-30→南通-100；08-12(只有持平)和06-16(只有区间)取不出")


def test_job_from_summaries_only_stores_city_and_source_and_counts_what_needs_a_body():
    items = [mk("2026-06-16", S_0616), mk("2026-06-26", S_0626), mk("2026-07-30", S_0730), mk("2026-08-12", S_0812), mk("2026-09-24", S_0924), mk("2026-09-30", S_0930)]
    d = tempfile.mkdtemp()
    try:
        fb = Bodies()
        rep = run(items, d, fetch=fb, max_bodies=0)
        assert pts(d) == [("2026-06-26", -180.0, "东莞", "summary"), ("2026-07-30", -90.0, "日照", "summary"), ("2026-09-24", -90.0, "日照", "summary"), ("2026-09-30", -100.0, "南通", "summary")], pts(d)
        assert rep["key"] == "basis" and rep["added"] == 4 and rep["viaSummary"] == 4 and rep["viaBody"] == 0, rep
        assert fb.log == [], "max_bodies=0：不抓任何正文"
        assert rep["needBodyRemaining"] == 2 and rep["bodiesFetched"] == 0, rep      # 06-16、08-12 摘要里取不出，也没抓正文
        assert rep["cityCounts"] == {"东莞": 1, "日照": 2, "南通": 1}, rep["cityCounts"]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★只靠摘要：4个点入库(每点带 x.city 和 x.src='summary')，摘要取不出的2篇记入 needBodyRemaining，报告给出取到的城市分布(东莞1/日照2/南通1)")


def test_empty_summary_triggers_body_fetch_and_the_body_is_parsed():
    items = [mk("2024-03-05", ""), mk("2024-03-06", "")]
    fb = Bodies({items[0]["url"]: (B_OK("日照", -50), None), items[1]["url"]: (B_OK("南通", -70), None)})
    d = tempfile.mkdtemp()
    try:
        rep = run(items, d, fetch=fb, start=date(2024, 3, 1), today=date(2024, 3, 31))
        assert pts(d) == [("2024-03-05", -50.0, "日照", "body"), ("2024-03-06", -70.0, "南通", "body")], pts(d)
        assert rep["viaBody"] == 2 and rep["viaSummary"] == 0 and rep["bodiesFetched"] == 2 and rep["needBodyRemaining"] == 0, rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("摘要为空→抓正文→按线上同一规则解析→入库(x.src='body')")


def test_body_cap_newest_first_and_resume_continues_where_it_stopped():
    ds = [date(2024, 3, 1) + timedelta(days=i) for i in range(5)]
    items = [mk(x.isoformat(), "") for x in ds]
    mapping = {i["url"]: (B_OK("日照", -10 * (k + 1)), None) for k, i in enumerate(items)}
    d = tempfile.mkdtemp()
    try:
        fb = Bodies(mapping)
        rep = run(items, d, fetch=fb, start=date(2024, 3, 1), today=date(2024, 3, 31), max_bodies=2)
        assert len(fb.log) == 2 and fb.log == [items[4]["url"], items[3]["url"]], f"最多2篇，且从最新的开始：{fb.log}"
        assert [p[0] for p in pts(d)] == ["2024-03-04", "2024-03-05"] and rep["needBodyRemaining"] == 3 and rep["bodiesFetched"] == 2, rep
        fb2 = Bodies(mapping)
        run(items, d, fetch=fb2, start=date(2024, 3, 1), today=date(2024, 3, 31), max_bodies=2)
        assert fb2.log == [items[2]["url"], items[1]["url"]], f"第二次跳过已有日期，接着抓更早的2篇：{fb2.log}"
        fb3 = Bodies(mapping)
        rep3 = run(items, d, fetch=fb3, start=date(2024, 3, 1), today=date(2024, 3, 31), max_bodies=2)
        assert fb3.log == [items[0]["url"]] and rep3["needBodyRemaining"] == 0 and len(pts(d)) == 5, (fb3.log, rep3)
        fb4 = Bodies(mapping)
        run(items, d, fetch=fb4, start=date(2024, 3, 1), today=date(2024, 3, 31), max_bodies=2)
        assert fb4.log == [] , "全部补完后再跑：一篇正文都不再抓(幂等)"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★每次最多抓 max_bodies 篇且从最新的开始；可重复点：已有的日期跳过，第二次接着抓更早的，补完后再点一篇都不抓(幂等)；needBodyRemaining 递减 3→…→0")


def test_every_body_request_is_followed_by_the_rate_limit_pause():
    """★变异检查发现：没有测试验证'抓一篇正文就等一会儿'。约700篇正文不等待会被 Mysteel 限流甚至封，这是对对方网站的礼貌，也是保护我们自己。"""
    items = [mk("2024-03-05", ""), mk("2024-03-06", ""), mk("2024-03-07", "")]
    fb = Bodies({i["url"]: (B_OK("日照", -50), None) for i in items})
    slept = []
    orig = bf.time.sleep
    bf.time.sleep = lambda x: slept.append(x)
    d = tempfile.mkdtemp()
    try:
        bf.backfill_basis(base_dir=d, today=date(2024, 3, 31), start=date(2024, 3, 1), search=fake_search(items), fetch_body=fb, sleep_s=0.8)
    finally:
        bf.time.sleep = orig
        shutil.rmtree(d, ignore_errors=True)
    assert len(fb.log) == 3 and slept.count(0.8) >= 3, (len(fb.log), slept)
    ok("★抓3篇正文就等3次(每次0.8秒)：限速保护真的在起作用")


def test_body_failures_are_diagnosed_not_hidden():
    items = [mk("2024-03-01", ""), mk("2024-03-02", ""), mk("2024-03-03", ""), mk("2024-03-04", "")]
    fb = Bodies({items[3]["url"]: (None, "正文请求失败(HTTP 403)"), items[2]["url"]: (B_NO, None), items[1]["url"]: (B_OK("日照", -99999), None), items[0]["url"]: (B_OK("日照", -50), None)})
    d = tempfile.mkdtemp()
    try:
        rep = run(items, d, fetch=fb, start=date(2024, 3, 1), today=date(2024, 3, 31))
        assert pts(d) == [("2024-03-01", -50.0, "日照", "body")], pts(d)
        reasons = {f["d"]: f["reason"] for f in rep["bodyFailures"]}
        assert "403" in reasons["2024-03-04"] and "没有" in reasons["2024-03-03"] and "超出合理范围" in reasons["2024-03-02"], reasons
        assert any(f["d"] == "2024-03-03" and f.get("regionHead") == B_NO[:220] for f in rep["bodyFailures"]), "没解析出值时要把正文开头带出来，方便改解析规则"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★正文失败逐篇说明原因：请求失败(403)、正文里没有沿海城市确切值(附正文开头)、数值-99999超出合理范围被拒；只有解析成功的1篇入库")


def test_untrusted_url_is_never_fetched():
    items = [mk("2024-03-05", "", url="https://evil.example.com/a"), mk("2024-03-06", "", url="")]
    fb = Bodies()
    d = tempfile.mkdtemp()
    try:
        rep = run(items, d, fetch=fb, start=date(2024, 3, 1), today=date(2024, 3, 31))
        assert fb.log == [] and rep["untrustedOrMissingUrl"] == 2, (fb.log, rep.get("untrustedOrMissingUrl"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★不可信域名(evil.example.com)和没有网址的文章：不抓正文，计入 untrustedOrMissingUrl")


def test_only_the_summary_series_is_used_and_publication_date_is_the_key():
    items = [mk("2026-09-30", S_0930, hhmm="08:00"), mk("2026-09-30", "别的文章南通基差-999", title="Mysteel解读：9月豆粕基差走势", hhmm="09:00")]
    d = tempfile.mkdtemp()
    try:
        rep = run(items, d, fetch=Bodies(), max_bodies=0)
        assert pts(d) == [("2026-09-30", -100.0, "南通", "summary")] and rep["otherTitlesSkipped"] == 1, (pts(d), rep.get("otherTitlesSkipped"))
        items2 = [mk("2026-09-30", S_0930, title=TITLE("2026-09-29"))]      # 标题日期(09-29)与发布日(09-30)不同：以发布日为准(与线上一致)
        d2 = tempfile.mkdtemp()
        run(items2, d2, fetch=Bodies(), max_bodies=0)
        assert [p[0] for p in pts(d2)] == ["2026-09-30"], pts(d2)
        shutil.rmtree(d2, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("只收标题含'豆粕基差价格汇总'的文章(月度解读按标题排除并计数)；日期用发布日(与线上 fetch_mysteel_basis 一致)，不用标题里的日期")


def test_same_day_two_articles_keeps_the_latest_publication():
    items = [mk("2026-09-30", S_0924, hhmm="09:00"), mk("2026-09-30", S_0930, hhmm="18:00")]
    d = tempfile.mkdtemp()
    try:
        run(items, d, fetch=Bodies(), max_bodies=0)
        assert pts(d) == [("2026-09-30", -100.0, "南通", "summary")], pts(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("同一天两篇：取发布最晚的一篇")


def test_existing_daily_points_are_never_overwritten_or_refetched():
    d = tempfile.mkdtemp()
    try:
        hs.record_points("basis", [{"d": "2026-09-30", "v": -999.0, "x": {"city": "日照"}}], d)      # 线上已累积的点
        fb = Bodies()
        items = [mk("2026-09-30", S_0930), mk("2026-09-24", S_0924)]
        rep = run(items, d, fetch=fb)
        p = {x["d"]: x["v"] for x in hs.load_series("basis", d)["points"]}
        assert p == {"2026-09-24": -90.0, "2026-09-30": -999.0}, p
        assert rep["existingSkipped"] == 1 and rep["added"] == 1, rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★线上已累积的日期不覆盖、不重抓(2026-09-30 的 -999 原样保留)；只补缺的日期，报告里 existingSkipped=1")


def test_adaptive_windows_recover_a_capped_window():
    ds = [date(2026, 6, 1) + timedelta(days=i) for i in range(90)]
    items = []
    for i, dd in enumerate(ds):
        items.append(mk(dd.isoformat(), "日照基差-%d元/吨，" % (50 + i)))
        for n in range(8):
            items.append(mk(dd.isoformat(), "别的", title=f"别的{n}", hhmm=f"07:{n:02d}"))
    def capped(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        sel = sorted((i for i in items if start.date().isoformat() <= i["publishTime"][:10] <= end.date().isoformat()), key=lambda i: i["publishTime"], reverse=True)
        return sel[:750], min(len(sel), 750), None
    d = tempfile.mkdtemp()
    try:
        rep = bf.backfill_basis(base_dir=d, start=ds[0], today=ds[-1], search=capped, fetch_body=Bodies(), sleep_s=0, max_bodies=0)
        assert rep["added"] == 90 and rep["windowsHitCap"] == [], rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★窗口被750条上限截断时自适应切窗：90天×9条=810条，90篇基差文章一篇不丢")


def test_nothing_found_reports_error_and_writes_nothing():
    d = tempfile.mkdtemp()
    try:
        rep = run([], d)
        assert rep["key"] == "basis" and "error" in rep and not os.path.exists(os.path.join(d, "basis.json")), rep
        rep2 = run([mk("2026-08-12", S_0812)], d, max_bodies=0)
        assert "error" in rep2 and not os.path.exists(os.path.join(d, "basis.json")), rep2
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("没搜到文章 / 一篇都取不出：报告写 error，不写任何文件")


# ================= v101.5：正文里的数据表 =================
# 真实正文开头(逐字，来自 2026-10-08 的回填报告 bodyFailures)。每篇文章底下有一张每个市场一行的数据表(省份 市场 期货合约 现货基差 涨跌)，
# 页面顶部"智能摘要 内容由AI生成"那段只是它的AI概括——线上抓取和之前的回填解析的都是那段概括，不是表。
R_0811 = "Mysteel：全国主要市场豆粕基差价格汇总（20260811） 2026-08-11 13:41 来源：我的钢铁网(Mysteel) 资讯监督 智能摘要 内容由AI生成 2026年8月11日，全国主要市场豆粕基差针对09合约普遍上涨。 省份 市场 期货合约 现货基差 涨跌 云南 昆明 09 60 0 吉林 长春 09 110 20 四川 成都 09 50 20 天津 天津 09 -30 20 山东 日照 09 -90 20 广东 湛江"
R_0812 = "Mysteel：全国主要市场豆粕基差价格汇总（20260812） 2026-08-12 11:52 来源：我的钢铁网(Mysteel) 资讯监督 智能摘要 内容由AI生成 2026年8月12日，全国主要市场豆粕基差以09合约为准。昆明、南通、武汉及岳阳基差持平；其余多数地区基差下跌10-20元/吨。 省份 市场 期货合约 现货基差 涨跌 云南 昆明 09 60 0 吉林 长春 09 100 -10 四川 成都 09 40 -10 天津 "
# 以下是我按表的格式构造的完整表(真实表的其余行没有样本)，用来验证多城市、合约月份切换、负数涨跌
R_FULL = ("Mysteel：全国主要市场豆粕基差价格汇总（20260828） 2026-08-28 12:00 来源：我的钢铁网(Mysteel) 资讯监督 智能摘要 内容由AI生成 2026年8月28日，全国主要市场豆粕基差以01合约为准。 "
          "省份 市场 期货合约 现货基差 涨跌 云南 昆明 01 -20 0 吉林 长春 01 10 -10 天津 天津 01 -80 10 山东 日照 01 -160 -10 江苏 南通 01 -170 0 广东 东莞 01 -160 20 广东 湛江 01 -150 10 广西 防城港 01 -180 -20 福建 厦门 01 -100 0")


def test_table_parser_reads_every_market_row_from_the_real_body_head():
    t = fd.parse_basis_table
    r = t(R_0811)
    assert r["日照"] == {"value": -90.0, "change": 20.0, "contract": "09"} and r["天津"] == {"value": -30.0, "change": 20.0, "contract": "09"}, r
    assert r["昆明"]["value"] == 60.0 and r["长春"]["value"] == 110.0 and r["成都"]["value"] == 50.0, r
    assert "湛江" not in r, "正文开头在 湛江 处被截断(没有基差数字)，不能编造"
    r2 = t(R_0812)
    assert r2["昆明"]["value"] == 60.0 and r2["长春"] == {"value": 100.0, "change": -10.0, "contract": "09"} and "天津" not in r2, r2
    ok("★真实正文(逐字)：08-11 表里日照 09合约 -90(涨20)、天津 -30、昆明 60…；被截断的湛江不编造；08-12 长春 100(跌10)，被截断的天津不编造")


def test_table_parser_full_table_negative_changes_and_contract_months():
    r = fd.parse_basis_table(R_FULL)
    assert r["日照"] == {"value": -160.0, "change": -10.0, "contract": "01"} and r["防城港"]["value"] == -180.0 and r["防城港"]["change"] == -20.0, r
    assert {c: r[c]["contract"] for c in ("日照", "南通", "东莞", "湛江", "防城港", "厦门", "天津")} == {c: "01" for c in ("日照", "南通", "东莞", "湛江", "防城港", "厦门", "天津")}
    assert len(r) == 9, sorted(r)
    ok("（构造的完整表）9个市场都读到；涨跌为负(日照 -10、防城港 -20)；合约月份 01 被记下来")


def test_table_parser_ignores_prose_numbers_and_malformed_rows():
    prose = "日照基差-90元/吨，南通基差-100。昆明、长春基差分别为70和60。"
    assert fd.parse_basis_table(prose) == {}, "没有表格行的纯文字里不能误读(那是摘要，交给原来的解析器)"
    assert fd.parse_basis_table("") == {} and fd.parse_basis_table(None) == {}
    odd = "省份 市场 期货合约 现货基差 涨跌 山东 日照 09 abc 20 广东 东莞 09 -50"      # 基差不是数字 / 缺涨跌列
    r = fd.parse_basis_table(odd)
    assert "日照" not in r and "东莞" not in r, r
    ok("纯文字(摘要)里不会被当成表；空/None 不崩；基差不是数字或缺涨跌列的残缺行被跳过")


def test_table_value_follows_the_same_coastal_priority_and_plausibility_as_live():
    assert fd.basis_from_table(R_0811) == ("日照", -90.0, "09"), fd.basis_from_table(R_0811)      # 日照是优先级第一，表里有
    t = R_FULL.replace("山东 日照 01 -160 -10 ", "")      # 去掉日照：优先级里下一个是 南通
    assert fd.basis_from_table(t) == ("南通", -170.0, "01"), fd.basis_from_table(t)
    only_inland = "省份 市场 期货合约 现货基差 涨跌 云南 昆明 09 60 0 吉林 长春 09 100 -10"
    assert fd.basis_from_table(only_inland) == (None, None, None), "表里没有沿海代表城市：取不出，不拿内陆城市凑"
    assert fd.basis_from_table("省份 市场 期货合约 现货基差 涨跌 山东 日照 09 -9999 20") == (None, None, None), "日照 -9999 超出合理范围(-500~500)：当没有，取不出(上一版这里写成了 A or B，两种结果都放行，等于没测)"
    assert fd.basis_from_table("省份 市场 期货合约 现货基差 涨跌 山东 日照 09 -9999 20 江苏 南通 09 -110 10") == ("南通", -110.0, "09"), "日照离谱：退到优先级里的下一个南通"
    ok("★表里按沿海城市优先级取第一个：有日照取日照(-90，合约09)；没有日照取南通(-170，合约01)；只有内陆城市取不出，不拿内陆凑")


def test_job_prefers_the_table_over_the_ai_summary_and_always_picks_the_same_city():
    """★表是权威数据，AI摘要只是概括，两者可能不一致；表里每天都有日照，所以选城市不再每天切换。"""
    items = [mk("2026-08-11", "AI摘要里写的是南通基差-999元/吨，日照基差-888元/吨")]
    fb = Bodies({items[0]["url"]: (R_0811, None)})
    d = tempfile.mkdtemp()
    try:
        rep = run(items, d, fetch=fb, start=date(2026, 8, 1), today=date(2026, 8, 31))
        assert pts(d) == [("2026-08-11", -90.0, "日照", "table")], pts(d)
        p = hs.load_series("basis", d)["points"][0]
        assert p["x"] == {"city": "日照", "src": "table", "contract": "09"}, p
        assert rep["viaTable"] == 1 and rep["viaSummary"] == 0 and rep["bodiesFetched"] == 1, rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★有表就用表：AI摘要写 -888/-999，表里日照是 -90 → 取 -90；点里记下 x={city:日照, src:table, contract:09}")


def test_job_falls_back_to_summary_when_the_body_has_no_usable_table():
    items = [mk("2026-09-30", S_0930), mk("2026-09-24", S_0924)]
    fb = Bodies({items[0]["url"]: ("正文里没有表格，只有一句话。", None)}, default=(None, "正文请求失败(HTTP 403)"))
    d = tempfile.mkdtemp()
    try:
        rep = run(items, d, fetch=fb, start=date(2026, 9, 1), today=date(2026, 9, 30))
        assert pts(d) == [("2026-09-24", -90.0, "日照", "summary"), ("2026-09-30", -100.0, "南通", "summary")], pts(d)
        assert rep["viaSummary"] == 2 and rep["viaTable"] == 0 and len(rep["bodyFailures"]) == 2, rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("表取不出(正文没表 / 正文请求失败)时退回摘要(用线上同一规则)，两种失败原因都记进 bodyFailures")


def test_old_summary_points_are_upgraded_by_the_table_but_live_points_are_never_touched():
    items = [mk("2026-09-30", S_0930), mk("2026-09-24", S_0924), mk("2026-08-11", "")]
    fb = Bodies({items[0]["url"]: ("省份 市场 期货合约 现货基差 涨跌 山东 日照 01 -110 -20", None), items[1]["url"]: ("正文没有表", None), items[2]["url"]: (R_0811, None)})
    d = tempfile.mkdtemp()
    try:
        hs.record_points("basis", [{"d": "2026-09-30", "v": -100.0, "x": {"city": "南通", "src": "summary"}},      # 上一版回填用摘要写的
                                   {"d": "2026-09-24", "v": -91.0, "x": {"city": "日照", "src": "summary"}},      # 故意与摘要里重新取到的 -90 不同：升级失败(正文没表)时必须保持这个原点，不能被重写
                                   {"d": "2026-09-29", "v": -777.0, "x": {"city": "日照"}}], d)         # 线上每天累积的(没有 src)
        rep = run(items, d, fetch=fb, start=date(2026, 8, 1), today=date(2026, 9, 30))
        p = {x["d"]: (x["v"], x["x"]) for x in hs.load_series("basis", d)["points"]}
        assert p["2026-09-30"] == (-110.0, {"city": "日照", "src": "table", "contract": "01"}), p["2026-09-30"]      # 摘要点被表升级
        assert p["2026-09-24"][0] == -91.0 and p["2026-09-24"][1]["src"] == "summary", "这篇正文没有表：保留原来的摘要点(-91，不是重新取到的-90)，不丢不改"
        assert p["2026-09-29"] == (-777.0, {"city": "日照"}), "线上累积的点(没有src)原样保留"
        assert p["2026-08-11"][0] == -90.0 and rep["upgraded"] == 1, rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★上一版用摘要写的点会被表升级(09-30：摘要南通-100 → 表日照-110)；正文没有表的保留原摘要点；线上累积的点(无src)永不动")


def test_bodies_without_a_table_are_remembered_and_not_refetched_until_the_parser_version_changes():
    """★正文请求成功但里面没有表的日期记进 triedNoTable，下次不再重抓(否则顽固的日期每次占掉抓取配额)；parserVersion 变了就全部重试。"""
    items = [mk("2024-03-05", ""), mk("2024-03-06", "")]
    d = tempfile.mkdtemp()
    try:
        fb = Bodies({items[0]["url"]: ("这篇没有表，也没有城市。", None), items[1]["url"]: (R_0811, None)})
        rep = run(items, d, fetch=fb, start=date(2024, 3, 1), today=date(2024, 3, 31))
        assert rep["triedNoTable"] == ["2024-03-05"] and rep["parserVersion"] == bf.BASIS_PARSER_VERSION and len(fb.log) == 2, rep
        report = {"generatedAt": "x", "series": [dict(rep, ranAt="x")], "calibration": {}}
        import json
        json.dump(report, open(os.path.join(d, "_backfill_report.json"), "w", encoding="utf-8"), ensure_ascii=False)
        fb2 = Bodies({items[0]["url"]: (R_0811, None)})
        rep2 = run(items, d, fetch=fb2, start=date(2024, 3, 1), today=date(2024, 3, 31))
        assert rep2["skippedKnownNoTable"] == 1 and rep2["existingSkipped"] == 1, rep2      # 03-05 已知没有表、也没有摘要值→跳过并计数；03-06 已有表点→跳过
        assert fb2.log == [], f"已知没有表的日期不再重抓：{fb2.log}"
        report["series"][0]["parserVersion"] = "table-v0"
        json.dump(report, open(os.path.join(d, "_backfill_report.json"), "w", encoding="utf-8"), ensure_ascii=False)
        fb3 = Bodies({items[0]["url"]: (R_0811, None)})
        run(items, d, fetch=fb3, start=date(2024, 3, 1), today=date(2024, 3, 31))
        assert fb3.log == [items[0]["url"]], f"解析规则版本变了：重新尝试：{fb3.log}"
        assert ("2024-03-05", -90.0, "日照", "table") in pts(d), pts(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★正文没有表的日期被记下来、同版本下次不再重抓；parserVersion 变了就全部重试(这次用新规则从正文里读到了表)")


def test_table_row_requires_exactly_a_two_digit_contract_and_accepts_glued_province():
    """★变异检查发现：没有测试验证合约月份必须恰好两位——否则别的数字序列会被误读成表格行。另：省份和市场粘在一起写(山东日照)也要能读。"""
    assert fd.parse_basis_table("山东 日照 123 -90 20") == {}, "三位数不是合约月份：不当成表格行"
    assert fd.parse_basis_table("山东 日照 9 -90 20") == {}, "一位数不是合约月份：不当成表格行"
    assert fd.parse_basis_table("山东 日照 09 -90 20")["日照"]["contract"] == "09"
    g = fd.parse_basis_table("山东日照 09 -90 20 广东东莞 09 -80 10")
    assert g["日照"]["value"] == -90.0 and g["东莞"]["value"] == -80.0, g
    ok("★合约月份必须恰好两位(123、9都不行)；省份和市场粘在一起写(山东日照、广东东莞)也能读——原来多余的'城市名前不能是汉字'限制已删")


def test_table_parser_uses_the_first_occurrence_of_a_market():
    t = "省份 市场 期货合约 现货基差 涨跌 山东 日照 09 -90 20 备注 山东 日照 09 -500 0"
    assert fd.parse_basis_table(t)["日照"]["value"] == -90.0, fd.parse_basis_table(t)
    ok("同一个市场在正文里出现两次(比如备注里又列了一遍)：取第一次(数据表里的)")


def test_a_failed_body_request_is_transient_and_never_remembered_as_no_table():
    """★变异检查发现：403/超时是暂时性的，如果被记成'这篇没有表'，下次就永远不重抓了。只有'请求成功但里面没有表'才记。"""
    items = [mk("2024-03-05", "")]
    d = tempfile.mkdtemp()
    try:
        fb = Bodies(default=(None, "正文请求失败(HTTP 403)"))
        rep = run(items, d, fetch=fb, start=date(2024, 3, 1), today=date(2024, 3, 31))
        assert rep.get("triedNoTable", []) == [] and len(fb.log) == 1, rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★请求失败(403)不记进 triedNoTable(暂时性的，下次还要重试)；只有请求成功但没有表才记")


def test_registration_query_default_start_and_not_in_default_jobs():
    calls = []
    d = tempfile.mkdtemp()
    try:
        bf.backfill_basis(base_dir=d, today=date(2026, 10, 1), search=fake_search([], calls), fetch_body=Bodies(), sleep_s=0)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert calls[0]["query"] == "全国主要市场豆粕基差价格汇总" and calls[0]["start"] == date(2023, 9, 1) and calls[-1]["end"] == date(2026, 10, 1)
    for a, b in zip(calls, calls[1:]):
        assert b["start"] == a["end"] + timedelta(days=1)
    assert "basis" in bf.JOBS and bf.JOBS["basis"] is bf.backfill_basis
    assert "basis" not in bf.DEFAULT_JOBS, "基差要抓约700篇正文、可能分几次，不进默认(all)，需要时 only=basis 单独点"
    ok("搜索词'全国主要市场豆粕基差价格汇总'，默认从2023-09-01分窗口无缝覆盖到今天；basis 已登记但不在默认(all)里——要抓大量正文，单独 only=basis")


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
