# -*- coding: utf-8 -*-
"""豆菜粕价差回填 + 统一取值规则(v101.4)。运行：python3 test_rmspread_backfill.py
夹具全部是 2026-10-02 采样里的**真实文章摘要**(逐字)。
规则：摘要里有≥2个城市的价差单值→取城市平均；否则取区间中点；只有1个单值→取该单值。
为什么：同一篇文章常同时有"各城市单值"和一句概括"各区域价差在700-900元/吨区间"，旧代码区间优先，会因为概括句写"700-900"(短横线)还是
"720至920"(至字)而取到不同的值——重叠的4篇上两种取法相差 +5/+33/-5/+37。"""
import os, sys, json, traceback, tempfile, shutil
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
T_20240109 = "今日国内豆菜粕价差涨跌互现，截至2024年1月9日，国内沿海地区豆菜粕现货价差在970-1030元/吨之间今日菜粕现货价格表现坚挺，豆粕方面华南地区豆粕价格相对稳定，豆菜粕价差稳定；而江苏地区豆粕偏弱运行，豆菜粕价差缩小目前豆菜粕价差仍高位运行，菜粕具有性价比优势，替代豆粕需求有望增加 美豆期价维持偏弱运行，盘中触及逾两年来的最低水平，因原油价格下跌和巴西大豆种植区干旱天气改善给市场造成拖累。"
T_20260508 = "截至2026年5月8日，国内沿海地区豆菜粕现货价差下跌，价差在420-600元/吨之间，跌10-20元/吨具体来看，今日豆粕现货价格跌20元/吨，菜粕今日市场价格涨跌互现连粕主力09合约震荡上涨，今日豆粕现货稳中偏弱运行，下游需求企业多执行合同提货为主菜粕现货价格随盘上涨豆菜粕价差震荡，菜粕替代价值一般 备注： 1、各品种取价如下：豆粕为43%蛋白，菜粕为36%蛋白； 2、豆菜粕价格均为当地市场现货主流销售价格； 3、单位：元/吨 。"
T_20260716 = "2026年7月16日，国内沿海地区豆菜粕现货价差上涨，区间在480-550元/吨，较前一日涨20元/吨。具体来看，豆粕现货价格涨10元/吨，菜粕现货价格涨跌互现。其中广东价差480元/吨，广西价差530元/吨，南通价差550元/吨。"
T_20260811 = "2026年8月11日，国内主要市场豆菜粕价差整体持稳。广东地区豆粕3020元/吨，菜粕2340元/吨，价差680元/吨；广西豆粕3000元/吨，菜粕2340元/吨，价差660元/吨；南通豆粕3020元/吨，菜粕2310元/吨，价差710元/吨。近期各区域价差波动幅度有限，市场表现相对平稳。"
T_20260819 = "2026年8月19日，国内主要市场豆菜粕价差呈现区域分化。广东地区豆粕3100元/吨，菜粕2400元/吨，价差700元/吨；广西豆粕3070元/吨，菜粕2390元/吨，价差680元/吨；南通豆粕3090元/吨，菜粕2330元/吨，价差760元/吨。近期价差整体在600-760元/吨区间波动，南通地区价差相对较宽，广东与广西价差处于中等水平。"
T_20260914 = "截至2026年9月14日，国内主要市场豆菜粕价差呈现震荡走势。广东地区豆粕3270元/吨，菜粕2460元/吨，价差810元/吨；广西地区豆粕3260元/吨，菜粕2460元/吨，价差800元/吨；南通地区豆粕3280元/吨，菜粕2380元/吨，价差900元/吨。近期各区域价差在700-900元/吨区间波动，南通价差相对较大，整体市场表现平稳。"
T_20260917 = "截至2026年9月17日，国内主要市场豆菜粕价差呈现区域分化。广东地区豆粕3370元/吨，菜粕2570元/吨，价差800元/吨；广西地区价差760元/吨；南通地区价差920元/吨。近期数据显示，各地价差在720至920元/吨区间波动，整体保持相对稳定，未出现大幅单边变动，市场供需关系处于动态平衡状态。"
T_20260930 = "2026年9月30日，国内主要市场豆菜粕价差如下：广东豆粕3310元/吨，菜粕2510元/吨，价差800元/吨；广西豆粕3300元/吨，菜粕2510元/吨，价差790元/吨；南通豆粕3280元/吨，菜粕2400元/吨，价差880元/吨。数据来源于钢联数据。"
T_NONUM = ["豆菜粕价差", "价差下跌", "豆菜粕价差上涨", "价差震荡"]      # 2026-06-16/22/25、07-21 的真实摘要：只有定性描述，没有数字
T_MONTHLY_2023 = "10月豆菜粕价差冲高回落，上半月豆粕表现强于菜粕，豆菜粕价差走扩，豆菜粕价差最高达到了1000元/吨下半月豆菜粕价差开始走弱，截至2023年10月30日沿海地区豆菜粕现货价差850元/吨，较2023年9月28日价格缩小50元/吨豆菜粕价差仍处于高位"
TITLE = lambda d: f"Mysteel数据：国内主要市场豆菜粕价差统计分析（{d.replace('-', '')}）"


def test_real_articles_hand_calculated():
    P = fd.parse_rmspread
    def val(t):
        r, _ = P(t)
        return (r["value"], r["fmt"]) if r else None
    assert val(T_20240109) == (1000.0, "range"), val(T_20240109)                   # (970+1030)/2
    assert val(T_20260508) == (510.0, "range"), val(T_20260508)                    # (420+600)/2；"跌10-20元/吨"(中点15)被合理范围挡掉，不会抢先
    assert val(T_20260716) == (520.0, "cities"), val(T_20260716)                   # 城市 480/530/550 → 1560/3=520.0；旧规则取区间中点 515
    assert val(T_20260811) == (683.3, "cities"), val(T_20260811)                   # (680+660+710)/3=683.33
    assert val(T_20260819) == (713.3, "cities"), val(T_20260819)                   # (700+680+760)/3=713.33；旧规则取概括句"600-760"的中点 680
    assert val(T_20260914) == (836.7, "cities"), val(T_20260914)                   # (810+800+900)/3=836.67；旧规则取"700-900"的中点 800
    assert val(T_20260917) == (826.7, "cities"), val(T_20260917)                   # (800+760+920)/3=826.67
    assert val(T_20260930) == (823.3, "cities"), val(T_20260930)                   # (800+790+880)/3=823.33，与线上 latest.json 的 823.3 一致
    ok("★8篇真实文章手算：区间中点(2024-01-09→1000、2026-05-08→510)，城市平均(07-16→520、08-11→683.3、08-19→713.3、09-14→836.7、09-17→826.7、09-30→823.3)")


def test_cities_win_over_the_summary_range_in_the_same_article():
    """★这条就是取值规则：同一篇里有城市单值和概括区间时，城市平均优先。09-14：旧规则800，新规则836.7(差36.7)。"""
    r, _ = fd.parse_rmspread(T_20260914)
    assert r["fmt"] == "cities" and r["value"] == 836.7 and r["samples"] == [810.0, 800.0, 900.0], r
    # 概括句换成"至"字(09-17 的写法)结果不受影响——取值不再取决于短横线还是"至"
    t2 = T_20260914.replace("700-900元/吨区间", "700至900元/吨区间")
    assert fd.parse_rmspread(t2)[0]["value"] == 836.7
    ok("★同一篇里城市单值优先于概括区间(09-14：836.7 而不是800)；概括句写'700-900'还是'700至900'不再影响结果")


def test_one_single_value_does_not_beat_a_range_and_a_lone_single_is_still_accepted():
    both = "国内沿海地区豆菜粕现货价差在420-600元/吨之间，其中广东价差480元/吨。"
    r, _ = fd.parse_rmspread(both)
    assert r["fmt"] == "range" and r["value"] == 510.0, r
    alone = "广东价差480元/吨，其余地区暂无数据。"
    r, _ = fd.parse_rmspread(alone)
    assert r["fmt"] == "single" and r["value"] == 480.0, r
    two = "广东价差480元/吨，广西价差520元/吨，近期价差在420-600元/吨之间。"
    r, _ = fd.parse_rmspread(two)
    assert r["fmt"] == "cities" and r["value"] == 500.0, r
    ok("★恰好1个单值+区间→区间(1个城市不足以代表)；只有1个单值→该单值(沿用线上行为)；2个单值+区间→城市平均500")


def test_implausible_values_are_dropped_individually():
    t = "广东价差800元/吨，广西价差5元/吨，南通价差900元/吨，价差在3500-4000元/吨之间"      # 5 和 3500-4000 都不在 100~3000
    r, rej = fd.parse_rmspread(t)
    assert r["fmt"] == "cities" and r["value"] == 850.0 and r["samples"] == [800.0, 900.0], r
    assert len(rej) >= 2, rej
    ok("★离谱的值单独丢掉不拉偏平均(5 被丢，800 和 900 → 850)，被丢的原因记在 rejected 里")


def test_change_amplitude_range_is_not_taken_as_the_spread():
    r, rej = fd.parse_rmspread("今日价差下跌，较前一日跌10-20元/吨。")
    assert r is None and any("15" in x or "超出合理范围" in x for x in rej), (r, rej)
    for t in T_NONUM:
        assert fd.parse_rmspread(t)[0] is None, t
    ok("★'较前一日跌10-20元/吨'(变动幅度)和4篇只有定性描述的真实摘要都取不出值，不当成价差")


def test_range_with_swapped_bounds_is_rejected():
    r, rej = fd.parse_rmspread("价差在900-700元/吨之间")
    assert r is None and any("颠倒" in x for x in rej), (r, rej)
    ok("区间上下限写反(900-700)被拒绝并说明原因")


# ---------------- 回填任务 ----------------
def mk(d, text, title=None, hhmm="17:30"):
    return {"publishTime": f"{d} {hhmm}", "title": title if title is not None else TITLE(d), "content": text, "url": f"http://m/{d}/{hhmm}"}


def fake_search(items, calls=None):
    def _s(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        if calls is not None:
            calls.append({"query": query, "start": start.date(), "end": end.date(), "url": url})
        sel = [i for i in items if start.date().isoformat() <= i["publishTime"][:10] <= end.date().isoformat()]
        return sel, len(sel), None
    return _s


def run_backfill(items, d, today=date(2026, 10, 1), **kw):
    calls = kw.pop("calls", None)
    return bf.backfill_rm_spread(base_dir=d, today=today, search=fake_search(items, calls), **kw)


def test_job_writes_points_with_format_and_skips_other_article_types():
    items = [mk("2024-01-09", T_20240109), mk("2026-07-16", T_20260716), mk("2026-09-14", T_20260914), mk("2026-09-30", T_20260930),
             mk("2026-07-20", T_MONTHLY_2023, title="Mysteel解读：7月豆粕菜粕价差缩窄，但菜粕替代性仍高"),      # 月度解读类文章(文本里有'沿海地区豆菜粕现货价差850元/吨')，必须落在搜索区间内才能验证被按标题排除
             mk("2026-06-22", "价差下跌")]
    d = tempfile.mkdtemp()
    try:
        rep = run_backfill(items, d)
        pts = hs.load_series("rm_spread", d)["points"]
        got = [(p["d"], p["v"], p["x"]["fmt"]) for p in pts]
        assert got == [("2024-01-09", 1000.0, "range"), ("2026-07-16", 520.0, "cities"), ("2026-09-14", 836.7, "cities"), ("2026-09-30", 823.3, "cities")], got
        assert rep["key"] == "rm_spread" and rep["added"] == 4 and rep["total"] == 4, rep
        assert rep["otherTitlesSkipped"] == 1 and len(rep["noValueSamples"]) == 1 and rep["noValueSamples"][0]["d"] == "2026-06-22", rep
        assert rep["formatCounts"] == {"range": 1, "cities": 3}, rep["formatCounts"]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★回填：4篇主系列文章入库(1000/520/836.7/823.3，每点带 x.fmt)；月度解读(文本里有'价差850元/吨')按标题排除(计数1)；'价差下跌'无数字记入 noValueSamples")


def test_job_uses_the_publication_date_and_keeps_the_latest_of_the_same_day():
    items = [mk("2026-09-14", T_20260914, hhmm="09:30"), mk("2026-09-14", T_20260930, hhmm="18:00")]      # 同一天两篇(第二篇更晚)
    d = tempfile.mkdtemp()
    try:
        run_backfill(items, d)
        p = hs.load_series("rm_spread", d)["points"]
        assert [(x["d"], x["v"]) for x in p] == [("2026-09-14", 823.3)], p
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("同一天多篇：取发布最晚的一篇(与每日累积'最后一次运行胜出'一致)")


def test_job_flags_format_switches_and_large_gaps():
    items = [mk("2026-07-10", "国内沿海地区豆菜粕现货价差在480-540元/吨之间"), mk("2026-07-16", T_20260716), mk("2026-08-11", T_20260811), mk("2026-09-30", T_20260930)]
    d = tempfile.mkdtemp()
    try:
        rep = run_backfill(items, d)
        sw = rep["formatSwitches"]
        assert sw == [{"from": "2026-07-10", "to": "2026-07-16", "fmt": "range→cities"}], sw
        assert rep["gapsOver14Days"] == [{"from": "2026-07-16", "to": "2026-08-11", "days": 26}, {"from": "2026-08-11", "to": "2026-09-30", "days": 50}], rep["gapsOver14Days"]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★报告标出口径切换点(07-10 区间→07-16 城市平均，这里可能有±5%的断层)和超过14天的缺口(07-16→08-11 共26天、08-11→09-30 共50天)")


def test_job_merges_with_daily_points_and_is_idempotent():
    items = [mk("2026-09-30", T_20260930)]
    d = tempfile.mkdtemp()
    try:
        hs.record_points("rm_spread", [{"d": "2026-09-29", "v": 823.3}, {"d": "2026-09-30", "v": 823.3}], d)
        run_backfill(items, d)
        p = hs.load_series("rm_spread", d)["points"]
        assert [x["d"] for x in p] == ["2026-09-29", "2026-09-30"], p
        before = open(os.path.join(d, "rm_spread.json"), "rb").read()
        run_backfill(items, d)
        assert open(os.path.join(d, "rm_spread.json"), "rb").read() == before, "第二次运行没有变化时不改文件"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("与每日累积的点合并不重复；重复运行幂等(文件字节不变)")


def test_job_windows_and_adaptive_split_recover_a_capped_window():
    ds = [date(2026, 6, 1) + timedelta(days=i) for i in range(90)]
    items = []
    for i, dd in enumerate(ds):
        items.append(mk(dd.isoformat(), "国内沿海地区豆菜粕现货价差在%d-%d元/吨之间" % (400 + i, 500 + i)))
        for n in range(8):      # 同一天还有8条不相关的结果，把窗口顶到 >750
            items.append(mk(dd.isoformat(), "别的文章", title=f"别的{n}", hhmm=f"09:{n:02d}"))
    assert len(items) == 810
    def capped(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        sel = sorted((i for i in items if start.date().isoformat() <= i["publishTime"][:10] <= end.date().isoformat()), key=lambda i: i["publishTime"], reverse=True)
        return sel[:750], min(len(sel), 750), None
    d = tempfile.mkdtemp()
    try:
        rep = bf.backfill_rm_spread(base_dir=d, start=ds[0], today=ds[-1], search=capped)
        assert rep["added"] == 90 and rep["windowsHitCap"] == [], rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★窗口被接口750条上限截断时自适应切窗：90天×9条=810条，90篇主系列文章一篇不丢(旧的固定窗口会丢最老约7篇)")


def test_job_reports_when_nothing_found_and_does_not_write():
    d = tempfile.mkdtemp()
    try:
        rep = run_backfill([], d)
        assert rep["key"] == "rm_spread" and "error" in rep and not os.path.exists(os.path.join(d, "rm_spread.json")), rep
        rep2 = run_backfill([mk("2026-06-22", "价差下跌")], d)
        assert "error" in rep2 and not os.path.exists(os.path.join(d, "rm_spread.json")), rep2
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("没搜到文章 / 搜到了但一篇都提取不出数值：报告写 error，不写任何文件")


def test_job_query_and_default_start_and_registration():
    calls = []
    d = tempfile.mkdtemp()
    try:
        run_backfill([], d, calls=calls)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert calls[0]["query"] == "豆菜粕价差" and calls[0]["start"] == date(2023, 12, 1) and calls[-1]["end"] == date(2026, 10, 1)
    for a, b in zip(calls, calls[1:]):
        assert b["start"] == a["end"] + timedelta(days=1)
    assert "rm_spread" in bf.JOBS and "rm_spread" in bf.DEFAULT_JOBS
    ok("搜索词是'豆菜粕价差'，默认从 2023-12-01 到今天分窗口无缝覆盖；rm_spread 已登记且在默认里")


def test_live_fetch_output_fields_are_unchanged_for_both_formats():
    """线上 fetch_mysteel_rmspread 改用共用解析后，输出字段(formatUsed 标签、rangeLow/High、citySamples)不变。"""
    def run(text):
        orig = fd.fetch_json_debug
        fd.fetch_json_debug = lambda *a, **k: ({"resultCode": 0, "total": 1, "dataList": [{"publishTime": "2026-09-30 17:00:00", "title": "t", "content": text}]}, {})
        try:
            return fd.fetch_mysteel_rmspread()
        finally:
            fd.fetch_json_debug = orig
    r = run(T_20240109)
    assert r["available"] and r["value"] == 1000.0 and r["formatUsed"] == "区间中点" and r["rangeLow"] == 970.0 and r["rangeHigh"] == 1030.0, r
    r = run(T_20260930)
    assert r["available"] and r["value"] == 823.3 and r["formatUsed"] == "多城市单值平均" and r["citySamples"] == [800.0, 790.0, 880.0], r
    r = run(T_20260914)
    assert r["value"] == 836.7 and r["formatUsed"] == "多城市单值平均", "线上也用同一个规则：城市平均优先(旧规则会得到800)"
    ok("★线上 fetch_mysteel_rmspread 输出字段不变；09-14 这类文章线上也改成城市平均 836.7(与回填口径一致)")


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
