# -*- coding: utf-8 -*-
"""肉鸡养殖利润改用 国家发改委价格监测中心×卓创资讯《猪料、鸡料、蛋料比价》周报(v101.8)。运行：python3 test_ndrc_poultry.py
★为什么换：Mysteel 的"白羽肉鸡养殖利润"采样里只能提取 25 个不规则的点，不够画趋势。发改委周报每周三监测、周五前后发布，模板固定，2023 年起一直有。
★这一轮用搜索/网页抓取工具看到的事实(夹具里的文本都是真实的)：
  - 文章页和栏目列表页都是服务器端渲染(Nuxt)：纯 HTTP 就能拿到完整正文，**不需要 Selenium**；
  - 肉鸡段的模板：'本周全国鸡料比价为X，环比上涨/下跌Y%。按目前价格及成本推算，未来肉鸡养殖预期盈利/预期亏损 Z元/只'；**亏损时写"预期亏损3.31元/只"(正数)，要转成 -3.31**；
  - 同一篇里还有生猪('头均亏损')和蛋鸡('每只盈利/亏损')，不能被误取；
  - 公式脚注 预期盈利=2.75×(鸡料比价-平衡点)×饲料价格；卓创转载页的脚注把系数写成过 2.5(官方页是 2.75，用公布数字验算 2.75 才对)——**直接取公布的数字，不重算**；
  - 表格排版偶有错误('本 周'中间有空格、'2.2 5')；正文里的日期偶有年份笔误(2023年9月第3周那篇写成 2024年9月18日)。
★没有拿到的：列表页里文章链接的真实 HTML(web_fetch 把链接丢了)、分页参数、从 GitHub Actions 访问这个国内政府站点是否可达——这些只能靠真实运行后的诊断。"""
import os, sys, re, traceback, tempfile, shutil
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd
import backfill_history as bf
import history_store as hs

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


# ---------------- 真实文章文本(逐字，来自 2026-10-08 抓到的页面/搜索结果) ----------------
# 发改委价格监测中心官方页：2026年3月第1周(web_fetch 取到的完整正文，表格已转成 HTML 单元格以模拟真实页面)
P_0301 = """<html><head><title>中华人民共和国国家发展和改革委员会 - 2026年3月第1周猪料、鸡料、蛋料比价</title></head><body><h1>2026年3月第1周猪料、鸡料、蛋料比价</h1>
<div>发布时间：2026/03/06</div><div>浏览量：14862</div>
<p>生猪饲料价格信息</p><p>国家发展和改革委员会价格监测中心  卓创资讯</p><p>2026年3月4日</p><p>全国生猪出场价格及饲料市场价格</p>
<table><tr><td>日期</td><td>生猪价格<br>(元/公斤)</td><td>饲料价格<br>(元/公斤)</td><td>猪料比价</td><td>猪料比价<br>平衡点</td><td>预期盈利<br>(元/头)</td></tr>
<tr><td>本周</td><td>11.07</td><td>2.67</td><td>4.15</td><td>5.11</td><td>-307.58</td></tr><tr><td>环比</td><td>-5.22%</td><td>-0.37%</td><td>-4.82%</td><td>-0.78%</td><td>--</td></tr></table>
<p>注：5.预期盈利=120×（猪料比价<b>-</b>平衡点）×饲料价格。</p>
<p>肉鸡饲料价格信息</p><p>国家发展和改革委员会价格监测中心  卓创资讯</p><p>2026年3月4日</p><p>全国肉鸡（活鸡）棚前收购价格及饲料市场价格</p>
<table><tr><td>日期</td><td>肉鸡价格（活鸡）<br>（元/公斤）</td><td>饲料价格<br>（元/公斤）</td><td>鸡料比价</td><td>鸡料比价<br>平衡点</td><td>预期盈利<br>(元/只)</td></tr>
<tr><td>本周</td><td>7.04</td><td>3.12</td><td>2.26</td><td>2.08</td><td>1.54</td></tr><tr><td>环比</td><td>-3.69%</td><td>0.00</td><td>-3.42%</td><td>-5.02%</td><td>--</td></tr></table>
<p>注：5.预期盈利=2.75×（鸡料比价<b>-</b>平衡点）×饲料价格。</p>
<p>本周全国鸡料比价为2.26，环比下跌3.42%。按目前价格及成本推算，未来肉鸡养殖预期盈利1.54元/只。屠宰企业开工逐步回升，收购量增加，但短期内鸡源供应相对充足，走货不快，鸡价继续下滑。下周鸡源供应较为稳定，但产品市场走货不快，屠宰企业收购平稳，供需波动不大，预计下周鸡价平稳运行为主。</p>
<p>鸡蛋饲料价格信息</p><p>国家发展和改革委员会价格监测中心  卓创资讯</p><p>2026年3月4日</p><p>全国鸡蛋出场价格及饲料市场价格</p>
<table><tr><td>本周</td><td>6.00</td><td>2.68</td><td>2.40</td><td>2.84</td><td>-23.58</td></tr></table>
<p>本周全国蛋料比价为2.40，环比下跌0.83%。按目前价格及成本推算，未来蛋鸡养殖每只亏损23.58元。本周鸡蛋价格涨后下跌。</p>
<p>免责声明</p></body></html>"""
# 9月第4周：真实搜索结果里的排版错误('本 周'、'环 比'、'2.2 5')，亏损 -4.10
P_0904 = """<html><body><h1>2026年9月第4周猪料、鸡料、蛋料比价</h1><div>发布时间：2026/09/25</div>
<p>国家发展和改革委员会价格监测中心  卓创资讯</p><p>2026年9月23日</p><p><b>全国肉鸡（活鸡）棚前收购价格及饲料市场价格</b></p>
<table><tr><td>日 期</td><td>肉鸡价格（活鸡） （元/公斤）</td><td>饲料价格 （元/公斤）</td><td>鸡料比价</td><td>鸡料比价 平衡点</td><td>预期盈利 (元/只)</td></tr>
<tr><td>本 周</td><td>5.81</td><td>3.24</td><td>1.79</td><td>2.2 5</td><td>-4.10</td></tr><tr><td>环 比</td><td>-2.52%</td><td>-0.31%</td><td>-2.19%</td><td>2.27%</td><td>--</td></tr></table>
<p>本周全国鸡料比价为1.79，环比下跌2.19%。按目前价格及成本推算，未来肉鸡养殖预期亏损4.10元/只。本周产品需求欠佳，屠宰企业收购积极性不高，叠加毛鸡供应相对充足，走货放缓，鸡价继续下滑。</p>
<p>国家发展和改革委员会价格测中心  卓创资讯</p><p>2026年9月23日</p><p><b>全国鸡蛋出场价格及饲料市场价格</b></p></body></html>"""
# 9月第3周：真实的转载文本(搜狐)，只有文字
P_0903_TEXT = "3.鸡料比价是指肉鸡价格与饲料价格的比值； 本周全国鸡料比价为1.83，环比下跌4.19%。按目前价格及成本推算，未来肉鸡养殖预期亏损3.31元/只。本周产品需求欠佳，屠宰企业收购积极性下滑，毛鸡走货放缓，鸡价继续下滑。"
# 2023年2月第4周：真实转载，生猪(头均亏损)、肉鸡(预期盈利为3.28)、蛋鸡(每只24.41元)三句话在同一段里
P_2302_TEXT = ("2月第4周，全国猪料比价为4.29，环比上涨4.89%。按目前价格及成本推算，未来生猪养殖头均亏损为178.20元。"
               "全国肉鸡（活鸡）棚前收购价格及饲料市场价格方面，2月第4周，全国鸡料比价为2.41，环比上涨1.69%。按目前价格及成本推算，未来肉鸡养殖预期盈利为3.28元/只。本周屠宰企业收购量较为稳定。"
               "全国鸡蛋出场价格及饲料市场价格方面，2月第4周，全国蛋料比价为2.66，环比上涨1.14%。按目前价格及成本推算，未来蛋鸡养殖盈利为每只24.41元。")


def html_text(h):
    return fd._html_to_text(h)


# ---------------- 解析 ----------------
def test_real_march_page_is_parsed_from_the_official_html():
    r, why = fd.parse_ndrc_poultry(html_text(P_0301))
    assert why is None, why
    assert r["value"] == 1.54 and r["ratio"] == 2.26 and r["balance"] == 2.08 and r["chickenPrice"] == 7.04 and r["feedPrice"] == 3.12 and r["ratioChangePct"] == -3.42, r
    assert r["monitorDate"] == "2026-03-04" and r["weekLabel"] == "2026年3月第1周" and r["publishDate"] == "2026-03-06", r
    ok("★发改委 2026年3月第1周(官方页真实内容)：预期盈利 +1.54，鸡料比价 2.26(环比-3.42%)，平衡点 2.08，肉鸡价 7.04，饲料价 3.12，监测日 2026-03-04，发布 03-06")


def test_loss_is_negative_and_the_messy_table_does_not_matter():
    r, why = fd.parse_ndrc_poultry(html_text(P_0904))
    assert why is None, why
    assert r["value"] == -4.10 and r["ratio"] == 1.79 and r["ratioChangePct"] == -2.19, r
    assert r["balance"] == 2.25, f"表里写成 '2.2 5'(中间有空格)，应该读成 2.25：{r['balance']}"
    assert r["monitorDate"] == "2026-09-23" and r["weekLabel"] == "2026年9月第4周", r
    ok("★9月第4周(真实排版错误：'本 周'、'2.2 5')：预期亏损4.10 → -4.10；平衡点 '2.2 5' 读成 2.25；鸡料比价 1.79")


def test_prose_only_reprint_works_and_loss_wording_is_signed():
    r, why = fd.parse_ndrc_poultry(P_0903_TEXT)
    assert why is None and r["value"] == -3.31 and r["ratio"] == 1.83 and r["ratioChangePct"] == -4.19, (r, why)
    ok("★只有文字的转载(9月第3周)：'预期亏损3.31元/只' → -3.31，鸡料比价 1.83，环比 -4.19%")


def test_only_the_broiler_sentence_is_used_not_pig_or_layer():
    r, why = fd.parse_ndrc_poultry(P_2302_TEXT)
    assert why is None and r["value"] == 3.28 and r["ratio"] == 2.41 and r["ratioChangePct"] == 1.69, (r, why)
    for bad in ("2月第4周，全国猪料比价为4.29，环比上涨4.89%。按目前价格及成本推算，未来生猪养殖头均亏损为178.20元。",
                "按目前价格及成本推算，未来蛋鸡养殖盈利为每只24.41元。本周全国蛋料比价为2.66。",
                "未来蛋鸡养殖每只亏损23.58元。"):
        r2, why2 = fd.parse_ndrc_poultry(bad)
        assert r2 is None, f"没有肉鸡句子的文本不能取出值：{bad[:20]} → {r2}"
    ok("★三句话在同一段里(生猪头均亏损178.20、肉鸡预期盈利为3.28、蛋鸡每只24.41)：只取肉鸡 +3.28；只有生猪/蛋鸡句子的文本取不出")


def test_wording_variants_and_year_formats():
    cases = [("本周全国鸡料比价为2.36，环比上涨1.29%。按目前价格及成本推算，未来肉鸡养殖预期盈利1.21元/只。", 1.21, 2.36, 1.29),
             ("本周全国鸡料比价为2.36，环比下跌1.29%。未来肉鸡养殖预期盈利为1.13元/只。", 1.13, 2.36, -1.29),
             ("本周全国鸡料比价为2.37，环比持平。按目前价格及成本推算，未来肉鸡养殖预期盈利1.11元/只。", 1.11, 2.37, 0.0),
             ("本周全国鸡料比价为1.83，环比下跌4.19%。未来肉鸡养殖预期亏损为3.31元/只。", -3.31, 1.83, -4.19),
             ("本周全国鸡料比价为2.30，环比上涨0.50%。未来肉鸡养殖预期盈利 0.00 元/只。", 0.0, 2.30, 0.5)]
    for t, v, ratio, chg in cases:
        r, why = fd.parse_ndrc_poultry(t)
        assert r and r["value"] == v and r["ratio"] == ratio and r["ratioChangePct"] == chg, (t, r, why)
    ok("措辞变体都能读：盈利/盈利为/亏损/亏损为/0.00；环比上涨/下跌/持平(持平=0.0)")


def test_implausible_or_missing_values_are_rejected_with_a_reason():
    for t, kw in (("本周全国鸡料比价为2.36，环比上涨1.29%。未来肉鸡养殖预期盈利99.00元/只。", "超出合理范围"),
                  ("本周全国鸡料比价为9.99，环比上涨1.29%。未来肉鸡养殖预期盈利1.00元/只。", "鸡料比价"),
                  ("本周全国鸡料比价为0.20，环比上涨1.29%。未来肉鸡养殖预期盈利1.00元/只。", "鸡料比价"),
                  ("", "没有"), (None, "没有"), ("今天天气不错", "没有")):
        r, why = fd.parse_ndrc_poultry(t)
        assert r is None and kw in why, (t, r, why)
    ok("★坏数据逐类拒绝并说明：预期盈利99(超±20)、鸡料比价9.99/0.20(超0.5~6)、空/None/无关文字")


def test_the_published_value_is_taken_never_recomputed_from_the_formula():
    """卓创转载页脚注把系数写成过2.5(官方页是2.75)。用公布数字验算：2.75×(2.26-2.08)×3.12=1.544→1.54；2.5×…=1.404。我们取公布的 1.54。"""
    r, _ = fd.parse_ndrc_poultry(html_text(P_0301))
    assert r["value"] == 1.54 and abs(2.75 * (2.26 - 2.08) * 3.12 - 1.54) < 0.01 and abs(2.5 * (2.26 - 2.08) * 3.12 - 1.54) > 0.1
    assert r.get("formulaCheckOk") is True and r.get("formulaCheckValue") == 1.54, r
    ok("★取公布的数字(1.54)，不自己重算；另外用 2.75×(鸡料比价-平衡点)×饲料价 验算一次(得 1.54 ✓，2.5 的系数得 1.40 ✗)，对不上只记 formulaCheckOk=False 不改值")


def test_formula_cross_check_flags_a_disagreement_without_changing_the_value():
    t = "全国肉鸡 本周 7.04 3.12 2.26 2.08 5.00 环比 -3.69% 0.00 -3.42% -5.02% -- 本周全国鸡料比价为2.26，环比下跌3.42%。按目前价格及成本推算，未来肉鸡养殖预期盈利5.00元/只。"
    r, _ = fd.parse_ndrc_poultry(t)
    assert r["value"] == 5.0 and r["formulaCheckOk"] is False and r["formulaCheckValue"] == 1.54, r
    ok("公布值 5.00 与公式验算 1.54 对不上：取公布值，formulaCheckOk=False 带出验算值，页面/报告可以提示")


def test_broiler_anchor_holds_even_when_the_layer_and_pig_sentences_use_the_same_wording():
    """★变异检查发现：之前的蛋鸡/生猪夹具措辞是'每只亏损…''头均亏损…'，本来就不匹配放宽的写法，锚定有没有都看不出来。
    这里让蛋鸡/生猪的句子用**和肉鸡一模一样的句式**('养殖预期盈利X元/只')，只有'肉鸡'二字能区分。"""
    t = ("本周全国蛋料比价为3.61，环比下跌2.96%。按目前价格及成本推算，未来蛋鸡养殖预期盈利53.95元/只。"
         "本周全国猪料比价为4.00，环比下跌0.99%。按目前价格及成本推算，未来生猪养殖预期亏损280.50元/只。")
    r, why = fd.parse_ndrc_poultry(t)
    assert r is None and "肉鸡" in why, (r, why)
    both = t + "本周全国鸡料比价为1.79，环比下跌2.19%。按目前价格及成本推算，未来肉鸡养殖预期亏损4.10元/只。"
    r2, _ = fd.parse_ndrc_poultry(both)
    assert r2["value"] == -4.1 and r2["ratio"] == 1.79, r2
    ok("★蛋鸡/生猪的句子用和肉鸡一模一样的句式('养殖预期盈利/亏损X元/只')：只有'肉鸡'二字能区分——单独出现取不出；三句并存只取肉鸡 -4.10")


# ---------------- 日期 ----------------
def test_monitor_date_is_validated_against_the_title_and_publish_date():
    pm = fd.pick_ndrc_monitor_date
    assert pm("2026年3月第1周", date(2026, 3, 4), date(2026, 3, 6)) == (date(2026, 3, 4), False)
    # ★真实笔误：2023年9月第3周那篇正文写成 2024年9月18日。年份与标题不符 → 不用，退到发布日之前的周三
    d, fb = pm("2023年9月第3周", date(2024, 9, 18), date(2023, 9, 20))
    assert fb is True and d == date(2023, 9, 20) and d.weekday() == 2, (d, fb)
    d, fb = pm("2023年9月第3周", date(2024, 9, 18), date(2023, 9, 22))      # 周五发布 → 最近的周三是 09-20
    assert fb is True and d == date(2023, 9, 20), (d, fb)
    d, fb = pm("2026年9月第4周", None, date(2026, 9, 25))
    assert fb is True and d == date(2026, 9, 23), (d, fb)
    d, fb = pm("2026年9月第4周", date(2026, 9, 23), None)
    assert fb is False and d == date(2026, 9, 23), (d, fb)
    d, fb = pm("2026年9月第4周", date(2026, 9, 23), date(2026, 9, 20))      # 监测日晚于发布日：不合理
    assert fb is True and d == date(2026, 9, 16), (d, fb)
    # ★变异检查发现：上面的年份笔误用例同时违反了'不早于发布日前14天'，被那一条盖住。这里年份不符但日期落在发布日前14天内——只有年份检查能拦住
    d, fb = pm("2023年9月第3周", date(2024, 9, 18), date(2024, 9, 20))      # 标题2023、正文2024-09-18、发布日2024-09-20：日期关系完全合理，只有年份和标题对不上
    assert fb is True and d == date(2024, 9, 18), (d, fb)      # 退回发布日之前最近的周三 2024-09-18(碰巧与正文日期相同，但 fb=True 说明是退回的、不是采用的)
    assert pm("", None, None) == (None, True)
    ok("★监测日用正文里的，但要核对：年份必须与标题一致且不晚于发布日、不早于发布日前14天；2023年9月第3周那篇正文写成2024年→退到发布日之前的周三(09-20)；没有正文日期/发布日也能退")


# ---------------- 列表页与链接 ----------------
LIST_HTML = """<html><body><nav><a href="/list?clmId=1832298113994649601&amp;sclmId=1836667772799598593">生猪出场价与玉米价格周报</a>
<a href="/list?clmId=1832298113994649601&amp;sclmId=1840280592963387394">猪料、鸡料、蛋料比价信息</a><a href="/list?clmId=1832298113994649601&amp;sclmId=999">全国钢材批发市场价格周报</a></nav>
<ul><li><a href="/detail?clmId=1840280592963387394&amp;tId=2031111111111111111">2026年9月第4周猪料、鸡料、蛋料比价</a><span>2026-09-25</span></li>
<li><a href="/detail?clmId=1840280592963387394&amp;tId=2030000000000000000">2026年9月第3周猪料、鸡料、蛋料比价</a><span>2026-09-18</span></li>
<li><a href="detail?clmId=1840280592963387394&tId=2029842375813152770">2026年3月第1周猪料、鸡料、蛋料比价</a><span>2026-03-06</span></li>
<li><a href="/detail?clmId=1&amp;tId=5">2026年9月23日全国生猪出场价格及主要批发市场玉米价格</a></li></ul>
<div><a href="/list?clmId=1840280592963387394&amp;page=2">下一页</a><a href="/list?clmId=1840280592963387394&amp;page=45">尾页</a></div></body></html>"""
BASE = "https://www.jgjcndrc.org.cn/list?clmId=1832298113994649601&sclmId=1836667772799598593"


def test_the_subcolumn_link_is_discovered_from_the_parent_list_page():
    u = fd.find_ndrc_feed_ratio_list_url(LIST_HTML, BASE)
    assert u == "https://www.jgjcndrc.org.cn/list?clmId=1832298113994649601&sclmId=1840280592963387394", u
    assert fd.find_ndrc_feed_ratio_list_url("<html>没有这个栏目</html>", BASE) is None
    ok("★从父栏目页导航里找到'猪料、鸡料、蛋料比价信息'子栏目的链接(&amp; 还原、相对路径补全)；找不到返回 None")


def test_article_links_are_extracted_in_page_order_and_other_articles_are_ignored():
    links = fd.extract_ndrc_article_links(LIST_HTML, BASE)
    assert [l["title"] for l in links] == ["2026年9月第4周猪料、鸡料、蛋料比价", "2026年9月第3周猪料、鸡料、蛋料比价", "2026年3月第1周猪料、鸡料、蛋料比价"], links
    assert links[0]["url"] == "https://www.jgjcndrc.org.cn/detail?clmId=1840280592963387394&tId=2031111111111111111", links[0]
    assert links[2]["url"] == "https://www.jgjcndrc.org.cn/detail?clmId=1840280592963387394&tId=2029842375813152770", "相对路径(没有前导斜杠)和没转义的&也要对"
    assert [l["week"] for l in links] == ["2026年9月第4周", "2026年9月第3周", "2026年3月第1周"] and links[0]["pageDate"] == "2026-09-25", links
    ok("★只收标题含'猪料、鸡料、蛋料比价'的详情链接(生猪出场价那条被排除)；保持页面顺序；相对路径/&amp;都能补全；带上周标签和页面上的日期")


def test_pagination_next_link_is_found():
    assert fd.find_ndrc_next_page(LIST_HTML, "https://www.jgjcndrc.org.cn/list?clmId=1832298113994649601&sclmId=1840280592963387394") == "https://www.jgjcndrc.org.cn/list?clmId=1840280592963387394&page=2"
    assert fd.find_ndrc_next_page("<html><a href='/x'>上一页</a></html>", BASE) is None
    ok("从列表页找'下一页'链接；没有就返回 None")


# ---------------- 线上抓取 ----------------
SUB_URL = "https://www.jgjcndrc.org.cn/list?clmId=1832298113994649601&sclmId=1840280592963387394"
URL_0904 = "https://www.jgjcndrc.org.cn/detail?clmId=1840280592963387394&tId=2031111111111111111"
URL_0301 = "https://www.jgjcndrc.org.cn/detail?clmId=1840280592963387394&tId=2029842375813152770"
SUB_LIST = """<html><body><ul><li><a href="/detail?clmId=1840280592963387394&amp;tId=2031111111111111111">2026年9月第4周猪料、鸡料、蛋料比价</a><span>2026-09-25</span></li>
<li><a href="/detail?clmId=1840280592963387394&amp;tId=2029842375813152770">2026年3月第1周猪料、鸡料、蛋料比价</a><span>2026-03-06</span></li></ul>
<a href="/list?clmId=1832298113994649601&amp;sclmId=1840280592963387394&amp;page=2">下一页</a></body></html>"""
SUB_LIST_2 = """<html><body><ul><li><a href="/detail?clmId=1840280592963387394&amp;tId=2020000000000000001">2026年2月第4周猪料、鸡料、蛋料比价</a><span>2026-02-27</span></li></ul></body></html>"""


def web(pages, log=None):
    """假的网页抓取 fetch(url, headers, retries, timeout) -> (raw, dbg)；pages: {url: html 或 Exception 或 None}"""
    def _f(url, headers=None, retries=2, timeout=20):
        if log is not None:
            log.append({"url": url, "retries": retries, "timeout": timeout})
        v = pages.get(url)
        if isinstance(v, Exception):
            raise v
        return (v, {}) if v else (None, {"error": "无返回(测试)"})
    return _f


class _TestLister(fd.NdrcHttpLister):
    """没有浏览器的测试列表提供者：详情页纯 HTTP 失败后的'浏览器后备'在这里直接报失败(不重复请求，请求次数的断言才有意义)。"""
    def page_html(self, url):
        return None, "测试里没有浏览器"


def both(f):
    """同一个假抓取函数同时给详情页(fetch)和列表(NdrcHttpLister)用：下游逻辑(解析/选日期/回填)沿用原来构造的页面验证；真实站点的列表靠 Selenium，见 test_ndrc_browser.py"""
    return dict(fetch=f, lister=_TestLister(f))


PAGES = {fd.NDRC_ENTRY_LIST: LIST_HTML, SUB_URL: SUB_LIST, URL_0904: P_0904, URL_0301: P_0301}
NOW = datetime(2026, 10, 8, 12, 0)


def test_live_follows_parent_list_then_sub_column_then_latest_article():
    log = []
    r = fd.fetch_ndrc_poultry(now_bj=NOW, **both(web(PAGES, log)))
    assert r["available"] and r["value"] == -4.10 and r["date"] == "2026-09-23" and r["ratio"] == 1.79 and r["balance"] == 2.25 and r["weekLabel"] == "2026年9月第4周", r
    assert [x["url"] for x in log] == [fd.NDRC_ENTRY_LIST, SUB_URL, URL_0904], [x["url"] for x in log]
    assert r["sourceUrl"] == URL_0904 and r["ageDays"] == 15 and r["stale"] is False and "发改委" in r["source"], r
    ok("★线上：父栏目页 → 找到子栏目 → 取最新一篇(9月第4周) → 解析：-4.10，监测日 09-23，鸡料比价 1.79，平衡点 2.25；只请求3次；距今15天不算过期")


def test_live_marks_stale_data_but_still_returns_it():
    old = datetime(2026, 11, 20, 12, 0)      # 距 09-23 已 58 天
    r = fd.fetch_ndrc_poultry(now_bj=old, **both(web(PAGES)))
    assert r["available"] and r["stale"] is True and r["ageDays"] == 58, r
    ok("数据距今58天(超过21天)：仍然返回(页面的新鲜度规则会处理)，但标 stale=True")


def test_live_reports_which_step_failed():
    cases = [({fd.NDRC_ENTRY_LIST: None}, "父栏目"), ({fd.NDRC_ENTRY_LIST: "<html>没有子栏目链接</html>"}, "子栏目"),
             ({fd.NDRC_ENTRY_LIST: LIST_HTML, SUB_URL: None}, "子栏目列表"), ({fd.NDRC_ENTRY_LIST: LIST_HTML, SUB_URL: "<html>空列表</html>"}, "没有文章"),
             ({fd.NDRC_ENTRY_LIST: LIST_HTML, SUB_URL: SUB_LIST, URL_0904: None}, "详情页"), ({fd.NDRC_ENTRY_LIST: LIST_HTML, SUB_URL: SUB_LIST, URL_0904: "<html>改版了，没有那句话</html>", URL_0301: "<html>也改版了，没有那句话</html>"}, "没有找到")]      # 两篇都要给页面，否则第二篇的'取不到'会盖住'没有找到'(上一版用例就是这样设计错的)
    for pages, kw in cases:
        r = fd.fetch_ndrc_poultry(now_bj=NOW, **both(web(pages)))
        assert r["available"] is False and kw in r["reason"], (kw, r)
    r = fd.fetch_ndrc_poultry(now_bj=NOW, **both(web({fd.NDRC_ENTRY_LIST: RuntimeError("网络炸了")})))
    assert r["available"] is False and "网络炸了" in r["reason"], r
    ok("★每一环失败都写明是哪一环：父栏目页取不到/没有子栏目链接/子栏目列表取不到/列表里没有文章/详情页取不到/详情页改版找不到那句话/网络异常——绝不抛异常")


def test_live_falls_back_to_the_next_article_when_the_latest_one_cannot_be_parsed():
    pages = dict(PAGES)
    pages[URL_0904] = "<html>这一期页面还没排好版，没有数据</html>"
    r = fd.fetch_ndrc_poultry(now_bj=NOW, **both(web(pages)), max_articles=2)
    assert r["available"] and r["value"] == 1.54 and r["date"] == "2026-03-04" and r["usedFallback"] is True and r["fallbackWeeks"] == 1, r
    ok("最新一篇解析不出(刚发布、排版没好)：退到前一篇(2026年3月第1周 +1.54)，usedFallback=True；最多试 max_articles 篇")


def test_live_request_budget_and_light_retry():
    log = []
    fd.fetch_ndrc_poultry(now_bj=NOW, **both(web(PAGES, log)))
    assert len(log) == 3 and all(x["retries"] <= 2 and x["timeout"] <= 15 for x in log), log
    log2 = []
    fd.fetch_ndrc_poultry(now_bj=NOW, **both(web({}, log2)))
    assert len(log2) == 1, "父栏目页取不到就停，不再请求别的"
    ok("★请求预算：成功只用3次、重试≤2次、超时≤15秒(每小时的线上抓取不能被拖慢)；父栏目页取不到就只请求1次")


def test_live_uses_the_publish_date_fallback_when_the_body_date_has_a_typo():
    typo = P_0301.replace("2026年3月4日", "2025年3月4日")      # 正文日期年份笔误
    pages = dict(PAGES)
    pages[URL_0904] = None
    pages[URL_0301] = typo
    r = fd.fetch_ndrc_poultry(now_bj=NOW, **both(web(pages)), max_articles=2)
    assert r["available"] and r["date"] == "2026-03-04" and r["dateFallback"] is True, r      # 发布日 03-06(周五) → 最近的周三 03-04
    ok("★正文日期年份笔误(2025年3月4日，标题是2026年)：退到发布日(03-06)之前最近的周三 03-04，dateFallback=True")


def test_adjacent_list_items_are_all_extracted_even_when_packed_tightly():
    """★上一轮抓到并修好的bug('</a>后面贪婪吞N个字符，下一个链接被吃掉')，当时没留下能防止复发的用例：测试的列表页里条目隔得够远。
    这里 5 个条目**紧挨着**，每两个链接之间不到 40 个字符——旧写法(吞160字符)只能取到 1~2 个。"""
    items = "".join(f'<li><a href="/detail?clmId=1&amp;tId={i}">2026年{m}月第{w}周猪料、鸡料、蛋料比价</a>|{d}</li>' for i, (m, w, d) in enumerate([(9, 4, "2026-09-25"), (9, 3, "2026-09-18"), (9, 2, "2026-09-11"), (9, 1, "2026-09-04"), (8, 4, "2026-08-28")]))
    links = fd.extract_ndrc_article_links(f"<html><ul>{items}</ul></html>", BASE)
    assert [l["week"] for l in links] == ["2026年9月第4周", "2026年9月第3周", "2026年9月第2周", "2026年9月第1周", "2026年8月第4周"], [l["week"] for l in links]
    assert [l["pageDate"] for l in links] == ["2026-09-25", "2026-09-18", "2026-09-11", "2026-09-04", "2026-08-28"], "每个条目的日期是它自己紧跟着的那个，不是下一个条目的"
    ok("★5个紧挨着的列表条目(间隔<40字符)全部取到，且每个条目的日期是它自己的(旧的贪婪写法会漏链接)")


def test_an_item_without_its_own_date_must_not_borrow_the_next_items_date():
    """★变异检查发现：我的'紧挨着'用例每个条目都有自己的日期，所以日期取成'后面160字符里的第一个'和'取自己的'结果一样。
    这里第 1 个条目**没有**日期、紧跟着的第 2 个条目有——取自己的得到 None，误取后面的会得到第 2 个条目的日期。"""
    html_ = ('<ul><li><a href="/detail?clmId=1&amp;tId=1">2026年9月第4周猪料、鸡料、蛋料比价</a></li>'
             '<li><a href="/detail?clmId=1&amp;tId=2">2026年9月第3周猪料、鸡料、蛋料比价</a>|2026-09-18</li></ul>')
    links = fd.extract_ndrc_article_links(html_, BASE)
    assert [l["pageDate"] for l in links] == [None, "2026-09-18"], links
    ok("★第1个条目没有自己的日期(pageDate=None)，不借用紧跟着的第2个条目的日期 2026-09-18；第2个取到自己的")


def _many_week_pages(n, bad_from=None, good_value=1.0):
    """构造 n 篇周报：详情页 URL 各不相同；bad_from 起(含)的详情页取不到。返回 (pages, 链接列表html)"""
    items, pages = [], {}
    base = date(2026, 9, 23)
    for i in range(n):
        d = base - timedelta(days=7 * i)
        wk = f"{d.year}年{d.month}月第{(d.day - 1) // 7 + 1}周"
        url = f"https://www.jgjcndrc.org.cn/detail?clmId=1840280592963387394&tId={9000 + i}"
        items.append(f'<li><a href="/detail?clmId=1840280592963387394&amp;tId={9000 + i}">{wk}猪料、鸡料、蛋料比价</a><span>{(d + timedelta(days=2)).isoformat()}</span></li>')
        if bad_from is None or i < bad_from:
            pages[url] = (f"<html><h1>{wk}猪料、鸡料、蛋料比价</h1><div>发布时间：{(d + timedelta(days=2)).strftime('%Y/%m/%d')}</div><p>{d.year}年{d.month}月{d.day}日 全国肉鸡（活鸡）棚前收购价格及饲料市场价格</p>"
                          f"<p>本周全国鸡料比价为2.30，环比持平。未来肉鸡养殖预期盈利{good_value + i * 0.01:.2f}元/只。</p></html>")
    return pages, "<html><ul>" + "".join(items) + "</ul></html>"


def test_backfill_saves_in_batches_so_a_killed_run_keeps_what_it_has():
    pages, lst = _many_week_pages(7)
    pages[fd.NDRC_ENTRY_LIST] = LIST_HTML
    pages[SUB_URL] = lst
    d = tempfile.mkdtemp()
    orig, calls = hs.record_points, []
    hs.record_points = lambda key, pts, base_dir=None: (calls.append(len(pts)), orig(key, pts, base_dir))[1]
    try:
        run_bf(d, pages, save_every=3)
    finally:
        hs.record_points = orig
        shutil.rmtree(d, ignore_errors=True)
    assert calls == [3, 3, 1], f"7个点、每3个落盘一次：应该是 3、3、1：{calls}"
    ok("★每攒够 save_every(3)个点落盘一次：7个点分 3+3+1 三批写入(被强杀时已落盘的不丢)")


def test_backfill_stops_after_consecutive_failures_but_isolated_ones_do_not_stop_it():
    pages, lst = _many_week_pages(10, bad_from=3)      # 前3篇正常，后7篇取不到
    pages[fd.NDRC_ENTRY_LIST] = LIST_HTML
    pages[SUB_URL] = lst
    log = []
    d = tempfile.mkdtemp()
    try:
        rep = run_bf(d, pages, log, max_consecutive_misses=4)
        detail_calls = [x for x in log if "detail" in x["url"]]
        assert rep["added"] == 3 and len(detail_calls) == 3 + 4, f"连续4篇失败就停手：应该只请求 3+4=7 个详情页：{len(detail_calls)}"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    # 零星失败：失败、成功、失败、成功…不叫停
    pages2, lst2 = _many_week_pages(8)
    for i in (1, 3, 5):      # 第2、4、6篇取不到
        pages2.pop(f"https://www.jgjcndrc.org.cn/detail?clmId=1840280592963387394&tId={9000 + i}")
    pages2[fd.NDRC_ENTRY_LIST] = LIST_HTML
    pages2[SUB_URL] = lst2
    d2 = tempfile.mkdtemp()
    try:
        rep2 = run_bf(d2, pages2, max_consecutive_misses=2)
        assert rep2["added"] == 5 and len(rep2["misses"]) == 3, rep2      # 8篇里5篇成功，3篇零星失败，每次连续失败都只有1(<2)，不叫停
    finally:
        shutil.rmtree(d2, ignore_errors=True)
    ok("★连续4篇取不到→停手(只请求了7个详情页，不再浪费请求)；零星失败(失败/成功交错，连续最多1次)不叫停，连续计数在成功后清零")


def test_live_tries_at_most_max_articles_before_giving_up():
    many = "".join(f'<li><a href="/detail?clmId=1840280592963387394&amp;tId={i}">2026年{9 - i // 4}月第{4 - i % 4}周猪料、鸡料、蛋料比价</a><span>2026-09-{25 - i:02d}</span></li>' for i in range(6))
    pages = {fd.NDRC_ENTRY_LIST: LIST_HTML, SUB_URL: f"<html>{many}</html>"}
    log = []
    r = fd.fetch_ndrc_poultry(now_bj=NOW, **both(web(pages, log)), max_articles=2)
    details = [x["url"] for x in log if "detail" in x["url"]]
    assert r["available"] is False and len(details) == 2, details
    log2 = []
    fd.fetch_ndrc_poultry(now_bj=NOW, **both(web(pages, log2)), max_articles=4)
    assert len([x for x in log2 if "detail" in x["url"]]) == 4
    ok("★6篇文章都取不到时，最多只试 max_articles 篇(2→2次详情请求，4→4次)，不会把整个列表都请求一遍")


def test_backfill_paging_phase_respects_the_budget_and_does_not_guess_pagination():
    # v101.9：翻页由 lister 负责(浏览器版有自己的总时限)；回填这边验证的是"翻页已经用掉了整个预算 → 一篇详情页都不再请求，stoppedEarly=True，并说明是预算用完"
    pages = {fd.NDRC_ENTRY_LIST: LIST_HTML, SUB_URL: SUB_LIST, "https://www.jgjcndrc.org.cn/list?clmId=1832298113994649601&sclmId=1840280592963387394&page=2": SUB_LIST_2,
             URL_0904: P_0904, URL_0301: P_0301}
    t = {"now": 0.0}
    log = []
    base = web(pages, log)

    class SlowPaging(_TestLister):
        def list_articles(self, max_pages=1, **kw):
            t["now"] += 200.0                 # 翻页用掉200秒
            return super().list_articles(max_pages=max_pages)
    d = tempfile.mkdtemp()
    try:
        rep = bf.backfill_poultry_ndrc(base_dir=d, today=date(2026, 10, 8), fetch=base, lister=SlowPaging(base), sleep_s=0, time_budget_s=150, clock=lambda: t["now"], save_every=1)
        assert rep.get("stoppedEarly") is True and "预算" in rep.get("error", ""), rep
        detail = [x["url"] for x in log if "detail" in x["url"]]
        assert detail == [], f"预算用完后不应再请求详情页：{detail}"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    # 没有'下一页'链接：绝不猜 &page=2 去请求
    log = []
    d2 = tempfile.mkdtemp()
    try:
        no_next = dict(pages)
        no_next[SUB_URL] = SUB_LIST.replace("下一页", "更多")
        bf.backfill_poultry_ndrc(base_dir=d2, today=date(2026, 10, 8), **both(web(no_next, log)), sleep_s=0)
        guessed = [x["url"] for x in log if "page=" in x["url"]]
        assert guessed == [], f"没有'下一页'链接时不能猜分页参数去请求：{guessed}"
    finally:
        shutil.rmtree(d2, ignore_errors=True)
    ok("★翻页阶段也受时间预算约束(翻到第1页就超预算→停，stoppedEarly=True)；没有'下一页'链接时一个带 page= 的请求都不发(不猜分页)")


def test_backfill_never_overwrites_a_stored_week_even_if_the_list_and_label_do_not_reveal_it():
    """已有一个点日期是 2026-09-23，没有 x.wk，列表上也没有发布日(pageDate=None)——两道'省请求'的快捷去重都不起作用，
    最后一道(解析出日期后核对历史)必须保住它不被覆盖。"""
    no_date_list = SUB_LIST.replace("<span>2026-09-25</span>", "").replace("<span>2026-03-06</span>", "")
    pages = dict(PAGES)
    pages[SUB_URL] = no_date_list
    d = tempfile.mkdtemp()
    try:
        hs.record_points("poultry_ndrc", [{"d": "2026-09-23", "v": -9.9}], d)
        log = []
        run_bf(d, pages, log)
        p = {x["d"]: x["v"] for x in hs.load_series("poultry_ndrc", d)["points"]}
        assert p["2026-09-23"] == -9.9, p
        assert URL_0904 in [x["url"] for x in log], "夹具有效：两道快捷去重都没起作用，详情页确实被取了"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★已有 2026-09-23 的点(无 x.wk、列表上也没有发布日)：快捷去重都不起作用，详情页被取了，但解析出日期后核对历史，-9.9 原样保留不被覆盖")


def test_week_label_shortcut_saves_the_detail_requests():
    d = tempfile.mkdtemp()
    try:
        hs.record_points("poultry_ndrc", [{"d": "2026-09-23", "v": -4.1, "x": {"wk": "2026年9月第4周"}}, {"d": "2026-03-04", "v": 1.54, "x": {"wk": "2026年3月第1周"}}], d)
        no_date_list = SUB_LIST.replace("<span>2026-09-25</span>", "").replace("<span>2026-03-06</span>", "")
        pages = dict(PAGES)
        pages[SUB_URL] = no_date_list
        log = []
        run_bf(d, pages, log)
        assert [x for x in log if "detail" in x["url"]] == [], "两周都已按周标签存在：一个详情页都不该请求"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★周标签快捷去重：两周都已存在(x.wk)且列表上没有发布日，一个详情页请求都不发(省请求，而不只是结果相同)")


# ---------------- 历史 ----------------
def test_history_records_the_ndrc_poultry_point_with_its_context():
    d = tempfile.mkdtemp()
    try:
        assert "poultry_ndrc" in hs.SERIES_META and hs.SERIES_META["poultry_ndrc"]["freq"] == "weekly"
        res = {"ndrcPoultryProfit": {"available": True, "value": -4.1, "date": "2026-09-23", "ratio": 1.79, "balance": 2.25, "weekLabel": "2026年9月第4周", "chickenPrice": 5.81, "feedPrice": 3.24}}
        hs.update_and_attach(res, base_dir=d)
        p = hs.load_series("poultry_ndrc", d)["points"][0]
        assert p["d"] == "2026-09-23" and p["v"] == -4.1 and p["x"] == {"ratio": 1.79, "bal": 2.25, "wk": "2026年9月第4周", "cp": 5.81, "fp": 3.24}, p
        assert "history" in res["ndrcPoultryProfit"]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★历史：poultry_ndrc 序列(周频，与 Mysteel 的 poultry_profit 分开，定义不同不混)，点里带 x={ratio鸡料比价, bal平衡点, wk周标签, cp肉鸡价, fp饲料价}；摘要挂回结果")


# ---------------- 回填 ----------------
def run_bf(d, pages, log=None, **kw):
    kw.setdefault("sleep_s", 0)
    return bf.backfill_poultry_ndrc(base_dir=d, today=kw.pop("today", date(2026, 10, 8)), **both(web(pages, log)), **kw)


def test_backfill_walks_the_list_pages_and_stores_every_week_newest_first():
    pages = dict(PAGES)
    pages[SUB_URL.replace("&sclmId", "&sclmId")] = SUB_LIST
    pages["https://www.jgjcndrc.org.cn/list?clmId=1832298113994649601&sclmId=1840280592963387394&page=2"] = SUB_LIST_2
    URL_0227 = "https://www.jgjcndrc.org.cn/detail?clmId=1840280592963387394&tId=2020000000000000001"
    pages[URL_0227] = P_0301.replace("2026年3月第1周", "2026年2月第4周").replace("2026年3月4日", "2026年2月25日").replace("2026/03/06", "2026/02/27").replace("1.54", "1.40")
    log = []
    d = tempfile.mkdtemp()
    try:
        rep = run_bf(d, pages, log)
        pts = hs.load_series("poultry_ndrc", d)["points"]
        assert [(p["d"], p["v"]) for p in pts] == [("2026-02-25", 1.4), ("2026-03-04", 1.54), ("2026-09-23", -4.1)], pts
        assert rep["added"] == 3 and rep["total"] == 3 and rep["articlesSeen"] == 3 and rep["listPages"] == 2, rep
        det = [x["url"] for x in log if "detail" in x["url"]]
        assert det == [URL_0904, URL_0301, URL_0227], det
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★回填：沿'下一页'翻 2 页列表，3篇文章，从最新开始取详情页，每周一个点(02-25 +1.40、03-04 +1.54、09-23 -4.10)")


def test_backfill_skips_weeks_already_in_history_and_is_idempotent():
    d = tempfile.mkdtemp()
    try:
        hs.record_points("poultry_ndrc", [{"d": "2026-09-23", "v": -9.9}], d)
        log = []
        run_bf(d, PAGES, log)
        p = {x["d"]: x["v"] for x in hs.load_series("poultry_ndrc", d)["points"]}
        assert p["2026-09-23"] == -9.9 and p["2026-03-04"] == 1.54, p
        assert URL_0904 not in [x["url"] for x in log], "已有的周不重抓详情页"
        log2 = []
        rep2 = run_bf(d, PAGES, log2)
        assert rep2["added"] == 0 and not [x for x in log2 if "detail" in x["url"]], rep2
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★已有的周不覆盖(-9.9 原样保留)、不重抓详情页；补完后再跑不再请求任何详情页(幂等)")


def test_backfill_skips_known_week_labels_without_fetching_when_the_week_is_already_stored():
    d = tempfile.mkdtemp()
    try:
        hs.record_points("poultry_ndrc", [{"d": "2026-09-23", "v": -4.1, "x": {"wk": "2026年9月第4周"}}], d)
        log = []
        run_bf(d, PAGES, log)
        assert URL_0904 not in [x["url"] for x in log]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("列表上的周标签(2026年9月第4周)已经在历史里(x.wk)：不请求详情页")


def test_backfill_stops_without_guessing_when_there_is_no_next_page_link_and_says_so():
    d = tempfile.mkdtemp()
    try:
        pages = dict(PAGES)
        pages[SUB_URL] = SUB_LIST.replace("下一页", "更多")
        rep = run_bf(d, pages)
        assert rep["listPages"] == 1 and rep["noNextPageLink"] is True and rep["added"] == 2, rep
        assert any("下一页" in n for n in rep["notes"]), rep["notes"]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★列表页没有'下一页'链接：不猜分页参数，只处理这一页的文章，报告写明 noNextPageLink=True 和原因")


def test_backfill_budget_miss_streak_and_errors():
    d = tempfile.mkdtemp()
    try:
        t = {"now": 0.0}
        base = web(PAGES)
        def slow(*a, **k):
            t["now"] += 100.0
            return base(*a, **k)
        rep = bf.backfill_poultry_ndrc(base_dir=d, today=date(2026, 10, 8), **both(slow), sleep_s=0, time_budget_s=250, clock=lambda: t["now"])
        assert rep["stoppedEarly"] is True, rep
        d2 = tempfile.mkdtemp()
        rep2 = run_bf(d2, {fd.NDRC_ENTRY_LIST: None})
        assert "error" in rep2 and not os.path.exists(os.path.join(d2, "poultry_ndrc.json")), rep2
        shutil.rmtree(d2, ignore_errors=True)
        d3 = tempfile.mkdtemp()
        pages = dict(PAGES)
        pages[URL_0904] = None
        pages[URL_0301] = None
        rep3 = run_bf(d3, pages, max_consecutive_misses=2)
        assert "error" in rep3 and rep3["misses"], rep3
        shutil.rmtree(d3, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("时间预算到了就停；父栏目页取不到/文章全部取不到：报告写 error 和 misses，不写文件")


def test_end_to_end_main_run_writes_ndrc_poultry_into_latest_json_and_the_history():
    """★端到端：真跑 main()(其它数据源换成桩，龙虎榜桩要给'以合约代码为键的字典'，肉鸡走假网页)：latest.json 里有 ndrcPoultryProfit(带 history 摘要)、history/poultry_ndrc.json 有点、
    没有 mysteelPoultryProfit。——上一轮基差就是'每个零件都绿、主流程没接上'，这一条把整条链连起来。"""
    import json, io, contextlib
    d = tempfile.mkdtemp()
    keep = ("fetch_ndrc_poultry", "fetch_json_debug", "fetch_text_debug", "fetch_basis_page", "fetch_dce_position_rank_multi", "fetch_spot_basis")
    names = [n for n in dir(fd) if n.startswith("fetch_") and callable(getattr(fd, n)) and n not in keep]
    saved = {n: getattr(fd, n) for n in names}
    saved["fetch_dce_position_rank_multi"] = fd.fetch_dce_position_rank_multi
    saved["fetch_text_debug"] = fd.fetch_text_debug
    saved["fetch_spot_basis"] = fd.fetch_spot_basis
    saved_out = fd.OUTPUT_PATH
    try:
        for n in names:
            setattr(fd, n, lambda *a, **k: {"available": False, "reason": "测试桩"})
        fd.fetch_dce_position_rank_multi = lambda codes, *a, **k: {c: {"available": False, "reason": "测试桩"} for c in codes}
        fd.fetch_spot_basis = lambda *a, **k: {"available": False, "reason": "测试桩"}
        fd.fetch_text_debug = web(PAGES)      # 肉鸡走假网页(父栏目页→子栏目→最新一篇)
        saved["default_ndrc_lister"] = fd.default_ndrc_lister
        fd.default_ndrc_lister = lambda *a, **k: _TestLister(web(PAGES))      # 线上默认是 Selenium；测试里换成喂构造页面的列表提供者
        fd.OUTPUT_PATH = os.path.join(d, "latest.json")
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                fd.main()
        except SystemExit:
            pass
        assert os.path.exists(fd.OUTPUT_PATH), "main() 没有写出 latest.json：\n" + buf.getvalue()[-800:]
        out = json.load(open(fd.OUTPUT_PATH, encoding="utf-8"))
        pr = out.get("ndrcPoultryProfit")
        assert pr and pr["available"] is True and pr["value"] == -4.10 and pr["date"] == "2026-09-23" and pr["ratio"] == 1.79 and pr["balance"] == 2.25, pr
        assert "mysteelPoultryProfit" not in out, "latest.json 里不应该再有 mysteelPoultryProfit"
        assert "history" in pr, "history_store 没有给 ndrcPoultryProfit 挂摘要"
        pts = hs.load_series("poultry_ndrc", os.path.join(d, "history"))["points"]
        assert len(pts) == 1 and pts[0]["v"] == -4.1 and pts[0]["x"]["wk"] == "2026年9月第4周", pts
    finally:
        for n, f in saved.items():
            setattr(fd, n, f)
        fd.OUTPUT_PATH = saved_out
        shutil.rmtree(d, ignore_errors=True)
    ok("★端到端：真跑 main()：latest.json 里有 ndrcPoultryProfit(-4.10，监测日09-23，鸡料比价1.79，平衡点2.25，带 history 摘要)、history/poultry_ndrc.json 有1个点(2026年9月第4周)、没有 mysteelPoultryProfit")


def test_backfill_registration_and_main_routine_wiring():
    assert "poultry_ndrc" in bf.JOBS and bf.JOBS["poultry_ndrc"] is bf.backfill_poultry_ndrc and "poultry_ndrc" not in bf.DEFAULT_JOBS
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_data.py"), encoding="utf-8").read()
    assert re.search(r'"ndrcPoultryProfit"\s*:\s*fetch_ndrc_poultry\(\)', src), "主流程里没有 ndrcPoultryProfit: fetch_ndrc_poultry()"
    assert not re.search(r'"mysteelPoultryProfit"\s*:\s*fetch_mysteel_poultry_profit\(\)', src), "主流程里还在调用 Mysteel 肉鸡利润"
    html_ = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), encoding="utf-8").read()
    m = re.search(r"key:'poultry'.*?dataKey:'(\w+)'", html_, re.S)
    assert m and m.group(1) == "ndrcPoultryProfit", f"前端肉鸡卡读的键是 {m.group(1) if m else None}"
    ok("★poultry_ndrc 已登记且不在默认里；主流程调用 fetch_ndrc_poultry(键 ndrcPoultryProfit)、不再调用 Mysteel；前端肉鸡卡读的键与主流程一致(上一轮基差就漏过这一环)")


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
