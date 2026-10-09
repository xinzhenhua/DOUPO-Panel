# -*- coding: utf-8 -*-
"""Mysteel《全国豆粕价格日报》摘要解析(v101.16)：取江苏(及其它主销区)43%豆粕现货价和Mysteel公布的基差水平。运行：python3 test_mysteel_meal_daily.py
★期望值来自用户 2026-10-09 在 Mysteel 搜索接口里复制出来的真实 19 篇日报摘要(data/raw/mysteel_meal_daily/sample_20260908_20261009.json)，逐篇人工读出来的：
  读不出确切数字的(只有涨跌、只有区间"3300-3310"、只说"江苏与广东持平或微涨")一律期望 None——宁可缺，不猜。"""
import os, sys, json, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mysteel_meal_daily as mm

HERE = os.path.dirname(os.path.abspath(__file__))
_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


SAMPLE = json.load(open(os.path.join(HERE, "data", "raw", "mysteel_meal_daily", "sample_20260908_20261009.json"), encoding="utf-8"))
BY = {x["publishTime"][:10]: x["content"] for x in SAMPLE if "全国豆粕价格日报" in x["title"]}

# 日期: (江苏价, 江苏基差)  ——手工读出
JS = {"2026-10-09": (3340, -62), "2026-10-08": (3340, None), "2026-09-30": (3310, None), "2026-09-29": (3290, -69),
      "2026-09-28": (3320, -43), "2026-09-24": (None, None), "2026-09-23": (3310, None), "2026-09-22": (3320, None),
      "2026-09-21": (3310, None), "2026-09-20": (3300, None), "2026-09-18": (None, None), "2026-09-17": (None, None),
      "2026-09-16": (3370, None), "2026-09-15": (None, None), "2026-09-14": (None, None), "2026-09-11": (None, None),
      "2026-09-10": (3270, None), "2026-09-09": (None, None), "2026-09-08": (None, None)}


def test_sample_has_19_daily_reports():
    assert len(BY) == 19 and set(BY) == set(JS), (len(BY), set(BY) ^ set(JS))
    ok("样本：19篇日报(第20条是玉米副产品日报，按标题排除)")


def test_jiangsu_price_and_basis_match_hand_reading_for_every_day():
    bad = []
    for d, (p, b) in sorted(JS.items()):
        r = mm.parse_meal_daily(BY[d])
        if (r["price"].get("江苏"), r["basis"].get("江苏")) != (p, b):
            bad.append((d, (r["price"].get("江苏"), r["basis"].get("江苏")), (p, b)))
    assert not bad, bad
    ok("★19天江苏现货价和基差，与人工读数逐天一致(含读不出就是None的8天价/16天基差)")


def test_other_regions_on_1009_and_0928():
    r = mm.parse_meal_daily(BY["2026-10-09"])
    assert r["price"] == {"辽宁": 3480, "天津": 3380, "山东": 3340, "江苏": 3340, "广东": 3330}, r["price"]
    assert r["basis"] == {"辽宁": 78, "天津": -22, "山东": -62, "江苏": -62, "广东": -72}, r["basis"]
    r = mm.parse_meal_daily(BY["2026-09-28"])
    assert r["price"] == {"辽宁": 3470, "天津": 3360, "山东": 3320, "江苏": 3320, "广东": 3320}, r["price"]
    assert r["basis"] == {"辽宁": 107, "天津": -3, "山东": -43, "江苏": -43, "广东": -43}, r["basis"]
    r = mm.parse_meal_daily(BY["2026-09-29"])
    assert r["price"]["山东"] == 3300 and r["price"]["广东"] == 3300 and r["basis"] == {"辽宁": 91, "天津": -39, "山东": -59, "广东": -59, "江苏": -69}, r
    ok("其它地区也对：10-09 五地价/基差、09-28 的'山东、江苏、广东均为-43'、09-29 的'山东、广东-59'共用一个值")


def test_list_forms():
    c = "9月30日全国豆粕价格多数上涨。43%豆粕方面，辽宁、天津、江苏涨20元/吨至3470、3340、3310元/吨；山东、广东涨10元/吨至3310元/吨。高蛋白豆粕中，盘锦45%涨20元/吨至3600元/吨。"
    r = mm.parse_meal_daily(c)
    assert r["price"] == {"辽宁": 3470, "天津": 3340, "江苏": 3310, "山东": 3310, "广东": 3310}, r["price"]
    ok("并列写法：'辽宁、天津、江苏涨20元至3470、3340、3310' 按位置对应；'山东、广东涨10元至3310'共用；高蛋白(盘锦45%)不混进来")


def test_ranges_and_change_only_sentences_are_not_prices():
    assert mm.parse_meal_daily("山东、江苏及广东地区价格在3300-3310元/吨区间，涨幅30-40元/吨。")["price"] == {}
    assert mm.parse_meal_daily("山东、江苏地区价格在3300至3310元/吨区间")["price"] == {}
    assert mm.parse_meal_daily("辽宁、天津、江苏涨7，山东、广东跌3。基差方面，辽宁、天津、江苏涨7")["basis"] == {}
    assert mm.parse_meal_daily("基差方面，辽宁、天津、山东、江苏、广东分别变动40、70、20、20、20。")["basis"] == {}
    ok("★区间('3300-3310')、只有涨跌幅('江苏涨7')、'分别变动40、70…' 都不当成价格/基差水平")


def test_names_count_must_match_numbers_count():
    r = mm.parse_meal_daily("辽宁、天津、江苏涨20元/吨至3470、3340元/吨")
    assert r["price"] == {}, r
    ok("名字3个、数字2个对不上 → 一个都不取(不猜)")


def test_implausible_values_rejected():
    assert mm.parse_meal_daily("江苏33400元/吨")["price"] == {}
    assert mm.parse_meal_daily("江苏报1200元/吨")["price"] == {}
    assert mm.parse_meal_daily("基差方面，江苏-9999")["basis"] == {}
    ok("价格不在2000~6000、基差不在±500 → 丢弃(多半是读错了)")


def test_basis_only_read_inside_basis_clause():
    r = mm.parse_meal_daily("江苏3340元/吨涨10。高蛋白豆粕中，南通46%报3510元/吨。豆粕菜粕价差690下跌20，豆粕葵粕价差850下跌40。")
    assert r["basis"] == {}, r
    ok("没有'基差'字样的句子不取基差(豆菜粕价差690不是基差)")


def test_empty_and_garbage():
    for c in ("", None, "全国玉米副产品市场价格维持稳定"):
        r = mm.parse_meal_daily(c)
        assert r == {"price": {}, "basis": {}}, (c, r)
    ok("空/无关文字 → 空结果，不崩")


def test_article_date_from_title_or_publish_time():
    assert mm.article_date({"title": "Mysteel：全国豆粕价格日报（20261009）", "publishTime": "2026-10-10 01:00"}) == "2026-10-09"
    assert mm.article_date({"title": "无日期", "publishTime": "2026-10-09 15:44"}) == "2026-10-09"
    assert mm.article_date({"title": "x", "publishTime": ""}) is None
    assert mm.is_daily_report({"title": "Mysteel：全国豆粕价格日报（20261009）"}) and not mm.is_daily_report({"title": "Mysteel日报：全国玉米副产品受豆粕价格影响（20260914）"})
    ok("日期优先取标题里的(20261009)，退而取发布时间；玉米副产品日报不算豆粕日报")


def test_build_rows_dedups_by_date_and_sorts():
    its = [dict(x) for x in SAMPLE]
    its.append(dict(SAMPLE[1], publishTime="2026-10-08 18:00"))    # 同一天重复发布
    rows, rep = mm.build_rows(its)
    assert [r["date"] for r in rows] == sorted({r["date"] for r in rows}) and len(rows) == 19, len(rows)
    r1009 = [r for r in rows if r["date"] == "2026-10-09"][0]
    assert r1009["js_price"] == 3340 and r1009["js_basis"] == -62 and r1009["ln_price"] == 3480
    assert rep["days"] == 19 and rep["jsPriceDays"] == 11 and rep["jsBasisDays"] == 3 and rep["skippedNotDaily"] == 1, rep
    ok("按日期去重排序；报告：江苏价11天、基差3天(19天里)，另有1篇非豆粕日报被排除")



def test_more_guards():
    assert mm.parse_meal_daily("江苏价格区间3300元/吨")["price"] == {}
    assert mm.parse_meal_daily("江苏地区近期豆粕现货价格整体偏稳，市场成交一般，报价为3300元/吨")["price"] == {}     # 名字和数字隔太远，不认
    assert mm.parse_meal_daily("基差方面，江苏-600")["basis"] == {} and mm.parse_meal_daily("基差方面，江苏-62")["basis"] == {"江苏": -62}
    assert mm.parse_meal_daily("基差方面，江苏56元/吨")["basis"] == {} and mm.parse_meal_daily("基差方面，江苏40点")["basis"] == {}
    ok("守卫：'区间'字样、名字和数字隔太远、基差超±500、基差后面跟'元/点'(是涨跌不是水平) 都不取")


def test_dedup_prefers_richer_over_later():
    rich = dict(SAMPLE[0]); poor = {"title": rich["title"], "publishTime": "2026-10-09 23:00", "content": "江苏持稳"}
    rows, _ = mm.build_rows([poor, rich]); rows2, _ = mm.build_rows([rich, poor])
    assert rows[0]["js_price"] == 3340 and rows2[0]["js_price"] == 3340
    ok("同一天两篇：取解析出字段多的，不是取发布更晚的(与顺序无关)")


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
