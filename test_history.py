# -*- coding: utf-8 -*-
"""历史序列存储/分位/日常累积/回填 的测试。运行：python3 test_history.py"""
import json
import os
import sys
import tempfile
import shutil
import traceback
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_store as hs
import fetch_data as fd
import backfill_history as bf
from test_fetch_data import MB_REAL_ARTICLES, MB_REAL_BODY_HTML, MOCK_ESR_COMMODITIES, MOCK_PSD_COMMODITIES, _esr_row

_pass = 0


def ok(msg):
    global _pass
    _pass += 1
    print("✅", msg)


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="hist_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


# ===================== 分位 =====================
def test_percentile_rank():
    assert hs.percentile_rank(5, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) == 45.0, "5在1..10里：4个更小+0.5个相等=4.5/10=45%"
    assert hs.percentile_rank(0, [1, 2, 3]) == 0.0 and hs.percentile_rank(99, [1, 2, 3]) == 100.0
    assert hs.percentile_rank(5, [5, 5, 5, 5]) == 50.0, "全部并列时应是50%，不是0或100"
    assert hs.percentile_rank(1, []) is None
    ok("百分位：mid-rank处理并列，空样本为None")


# ===================== 合并/存取 =====================
def test_merge_points_rules():
    a = [{"d": "2026-08", "v": 15.0, "pub": "2026-07-31"}]
    m, ch = hs.merge_points(a, [{"d": "2026-08", "v": 15.12, "pub": "2026-08-31"}])
    assert m[0]["v"] == 15.12 and ch, "后发布的文章取代先发布的预测"
    m, ch = hs.merge_points(m, [{"d": "2026-08", "v": 14.0, "pub": "2026-07-01"}])
    assert m[0]["v"] == 15.12 and not ch, "更早发布的来源不能覆盖更晚发布的"
    m, ch = hs.merge_points(m, [{"d": "2026-08", "v": 15.12, "pub": "2026-08-31"}])
    assert not ch, "完全相同的点重复写入不算变化(避免每小时产生空提交)"
    m, ch = hs.merge_points(m, [{"d": "2026-09", "v": 16.04}, {"d": "2026-07", "v": 13.0}, {"d": "2026-10", "v": None}, {"d": "x", "v": True}])
    assert [p["d"] for p in m] == ["2026-07", "2026-08", "2026-09"] and ch, "按日期排序，非数值(None/bool)的点被丢弃"
    m, ch = hs.merge_points([{"d": "2026-09-01", "v": 1.0}], [{"d": "2026-09-01", "v": 2.0}])
    assert m[0]["v"] == 2.0 and ch, "没有pub时以新值为准"
    ok("合并规则：后发布优先/更早不覆盖/重复不算变化/丢弃非数值/按日期排序")


def test_save_load_roundtrip_and_format():
    with Tmp() as d:
        s = hs.load_series("meal_stu", d)
        assert s["points"] == [] and s["unit"] == "%" and s["freq"] == "monthly" and "库存消费比" in s["name"]
        s, ch = hs.record_points("meal_stu", [{"d": "2026-09", "v": 16.04, "pub": "2026-08-31"}, {"d": "2026-08", "v": 15.12}], d)
        assert ch
        raw = open(os.path.join(d, "meal_stu.json"), encoding="utf-8").read()
        data = json.loads(raw)                                    # 是合法JSON
        assert [p["d"] for p in data["points"]] == ["2026-08", "2026-09"] and data["unit"] == "%"
        lines = raw.strip().split("\n")
        assert len(lines) == 2 + 2 + 1 and lines[3].startswith('{"d":"2026-09"'), f"每个点应独占一行(git diff友好): {lines}"
        assert "库存消费比" in raw, "中文不能被转义成\\uXXXX"
        mtime = os.path.getmtime(os.path.join(d, "meal_stu.json"))
        _, ch2 = hs.record_points("meal_stu", [{"d": "2026-09", "v": 16.04, "pub": "2026-08-31"}], d)
        assert not ch2 and os.path.getmtime(os.path.join(d, "meal_stu.json")) == mtime, "没有变化时不重写文件"
        assert hs.load_series("meal_stu", d)["points"][1]["v"] == 16.04
    ok("存取：往返一致、每点一行、中文不转义、无变化不重写")


def test_load_corrupt_or_missing_returns_empty():
    with Tmp() as d:
        open(os.path.join(d, "basis.json"), "w").write("{not json")
        assert hs.load_series("basis", d)["points"] == []
        assert hs.load_series("nope_key", d)["points"] == [] and hs.load_series("nope_key", d)["freq"] == "irregular"
        open(os.path.join(d, "hog_ratio.json"), "w").write(json.dumps({"points": [{"d": "2026-01-01", "v": "abc"}, {"d": "2026-01-02", "v": 6.1}, {"x": 1}]}))
        assert hs.load_series("hog_ratio", d)["points"] == [{"d": "2026-01-02", "v": 6.1}], "损坏/非数值的点被丢弃"
    ok("读取：文件损坏/不存在/含坏点都不抛异常")


# ===================== summarize =====================
def test_summarize_min_points_and_exclude_self():
    pts = [{"d": f"2020-{m:02d}", "v": float(m)} for m in range(1, 12)]     # 11个点
    s = hs.summarize(pts + [{"d": "2021-01", "v": 5.0}], 5.0, "2021-01", "monthly")
    assert s["n"] == 11 and s["percentile"] is None, "参考样本剔除当前点自己；不足12个不给百分位"
    pts.append({"d": "2020-12", "v": 12.0})                                   # 12个
    s = hs.summarize(pts + [{"d": "2021-01", "v": 6.5}], 6.5, "2021-01", "monthly")
    assert s["n"] == 12 and s["percentile"] == 50.0, s   # 6.5：6个更小(1..6)，无相等 → 6/12
    assert s["min"] == 1.0 and s["max"] == 12.0 and s["median"] == 6.5 and s["since"] == "2020-01"
    ok("summarize：剔除自身、样本<12不给百分位、最小/最大/中位/起点")


def test_summarize_seasonal_uses_same_month_other_years():
    pts = []
    for y in range(2018, 2026):
        for m in range(1, 13):
            pts.append({"d": f"{y}-{m:02d}", "v": 10.0 + (m == 9) * 5 + (y - 2018) * 0.1})   # 每年9月比其它月高5
    s = hs.summarize(pts + [{"d": "2026-09", "v": 15.5}], 15.5, "2026-09", "monthly")
    assert s["seasonal"]["month"] == 9 and s["seasonal"]["n"] == 8, "同月样本=2018~2025年的9月共8个(15.0~15.7)"
    assert s["seasonal"]["percentile"] == 68.8, f"15.5在15.0/15.1/…/15.7里：5个更小+1个相等的一半=5.5/8=68.8%，实际{s['seasonal']}"
    assert s["percentile"] > 90, "总体：15.5高于全部非9月的月份(约10~10.7)，只低于/等于其它年份的9月"
    s = hs.summarize(pts + [{"d": "2026-09", "v": 16.0}], 16.0, "2026-09", "monthly")
    assert s["seasonal"]["percentile"] == 100.0 and s["percentile"] == 100.0
    # 同年份的点不算同期样本
    s2 = hs.summarize([{"d": "2026-09-01", "v": 1}, {"d": "2026-09-08", "v": 2}, {"d": "2026-09-15", "v": 3}, {"d": "2026-09-22", "v": 4}, {"d": "2026-09-29", "v": 9}], 9, "2026-09-29", "weekly")
    assert s2["seasonal"] is None, "同一年的近邻点不能当同期样本(没有其它年份的同月数据时不给同期分位)"
    # 同月样本<4：给n但不给百分位
    few = [{"d": "2024-09", "v": 1.0}, {"d": "2025-09", "v": 2.0}]
    s3 = hs.summarize(few, 3.0, "2026-09", "monthly")
    assert s3["seasonal"] == {"month": 9, "n": 2, "percentile": None, "median": None}
    # 年度序列不做同月比较
    assert hs.summarize([{"d": str(y), "v": float(y)} for y in range(2000, 2020)], 5.0, "2026", "yearly")["seasonal"] is None
    ok("summarize：同月不同年的同期分位；同年近邻不算；同月<4个不给分位；年度序列无同期")


def test_rolling_sum_skips_windows_with_gaps():
    w = [{"d": d, "v": 10.0} for d in ["2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22", "2026-01-29"]]
    r = hs.rolling_sum(w, 4)
    assert [x["d"] for x in r] == ["2026-01-22", "2026-01-29"] and r[0]["v"] == 40.0
    gap = [{"d": d, "v": 10.0} for d in ["2026-01-01", "2026-01-08", "2026-02-05", "2026-02-12", "2026-02-19"]]
    assert hs.rolling_sum(gap, 4) == [], "缺了几周的窗口不能冒充完整的4周"
    ok("滚动4周合计：连续周才算，缺周的窗口跳过")


# ===================== 日常累积 =====================
def _fake_result():
    return {
        "mysteelCrushRate": {"available": True, "value": 69.98, "date": "2026-09-22"},
        "mysteelBasis": {"available": True, "value": -100, "city": "日照", "date": "2026-09-28"},
        "mysteelPoultryProfit": {"available": True, "value": 0.71, "date": "2026-09-25"},
        "mysteelRmSpread": {"available": True, "value": 550, "date": "2026-09-25"},
        "hogRatio": {"available": True, "value": 5.6, "date": "2026-09-28"},
        "mysteelMealStock": {"available": True, "value": 117.32, "date": "2026-09-21 09:00:00"},
        "mysteelArrivalForecast": {"available": True, "value": 1100, "forecastYear": 2026, "forecastMonth": 10, "date": "2026-09-27"},
        "mysteelSoyImport": {"available": True, "value": 1214.14, "monthLabel": "2026年8月", "date": "2026-09-10"},
        "mysteelReserveAuction": {"available": True, "value": 54.3, "auctionDate": "2026-09-25", "soldRate": 37.3},
        "sowInventory": {"available": True, "value": 3980, "quarterLabel": "2026年二季度末", "date": "2026-08-01"},
        "supplyDemand": {"available": True, "commodity": "Oilseed, Soybean", "marketYear": 2026, "stocksToUsePct": 6.9},
        "mysteelMealStu": {"available": True, "value": 16.04, "month": "2026-09", "method": "stated", "date": "2026-08-31"},
        "exportSales": {"available": True, "commodity": "Soybeans(大豆)", "weekEnding": "2026-09-24", "total4wSumMT": 3000000,
                        "recentWeeks": [{"weekEnding": f"2026-{m:02d}-{dd:02d}", "netSalesMT": 500000 + i * 1000, "chinaNetSalesMT": 1, "unknownNetSalesMT": 2}
                                        for i, (m, dd) in enumerate([(8, 6), (8, 13), (8, 20), (8, 27), (9, 3), (9, 10), (9, 17), (9, 24)])]},
    }


def test_update_and_attach_records_every_indicator_and_is_idempotent():
    with Tmp() as d:
        r = _fake_result()
        touched = hs.update_and_attach(r, base_dir=d)
        expect = {"crush_rate": ("2026-09-22", 69.98), "basis": ("2026-09-28", -100), "poultry_profit": ("2026-09-25", 0.71),
                  "rm_spread": ("2026-09-25", 550), "hog_ratio": ("2026-09-28", 5.6), "meal_stock": ("2026-09-21", 117.32),
                  "arrival_forecast": ("2026-10", 1100), "soy_import": ("2026-08", 1214.14), "reserve_auction": ("2026-09-25", 54.3),
                  "sow_inventory": ("2026-06", 3980), "us_stocks_to_use": ("2026", 6.9), "meal_stu": ("2026-09", 16.04)}
        for key, (dd, vv) in expect.items():
            pts = hs.load_series(key, d)["points"]
            assert pts and pts[-1]["d"] == dd and pts[-1]["v"] == vv, f"{key}: {pts}"
        esr = hs.load_series("esr_net_sales", d)["points"]
        assert len(esr) == 8 and esr[0]["x"] == {"chinaNetSalesMT": 1, "unknownNetSalesMT": 2}, "出口净销售：最近8周逐周记下"
        assert set(touched) == set(expect) | {"esr_net_sales"}
        assert hs.load_series("basis", d)["points"][0]["x"] == {"city": "日照"}
        assert hs.load_series("meal_stu", d)["points"][0]["pub"] == "2026-08-31"
        # 每个结果都挂上了history；样本不足时percentile=None但n有值
        assert r["mysteelBasis"]["history"]["n"] == 0 and r["mysteelBasis"]["history"]["percentile"] is None
        assert r["mysteelMealStu"]["history"]["asOf"] == "2026-09"
        # 第二次运行：数据没变，不应有任何序列被标记为变化
        assert hs.update_and_attach(_fake_result(), base_dir=d) == [], "每小时跑一次：没有新数据就不产生改动"
    ok("日常累积：12个指标+出口逐周都正确落盘、挂上history，重复运行无变化")


def test_update_and_attach_skips_unavailable_and_weekly_fallback_stu():
    with Tmp() as d:
        r = _fake_result()
        r["mysteelBasis"] = {"available": False, "reason": "x"}
        r["mysteelMealStu"]["method"] = "weekly"       # 周度库存÷预计消费的回退推算，不是月度平衡表的数
        r["supplyDemand"] = {"available": True, "marketYear": 2026, "stocksToUsePct": 33.0}   # 旧版数据(没有commodity字段)
        r["mysteelCrushRate"]["value"] = "abc"
        touched = hs.update_and_attach(r, base_dir=d)
        assert "basis" not in touched and not os.path.exists(os.path.join(d, "basis.json")), "抓取失败的不记录"
        assert "meal_stu" not in touched and not os.path.exists(os.path.join(d, "meal_stu.json")), "周度回退值不能混进月度历史"
        assert "us_stocks_to_use" not in touched, "旧版(豆粕口径)数据不进历史"
        assert "crush_rate" not in touched, "非数值不记录"
        assert "history" in r["mysteelMealStu"], "回退值仍然挂上历史分位(参考已有的月度历史)，只是不写入"
    ok("日常累积：失败/回退值/旧版数据/非数值都不进历史")


def test_update_and_attach_one_bad_indicator_does_not_break_others():
    with Tmp() as d:
        r = _fake_result()
        r["mysteelArrivalForecast"]["forecastYear"] = None      # int(None)会抛异常
        r["exportSales"]["recentWeeks"] = "坏数据"
        touched = hs.update_and_attach(r, base_dir=d)
        assert "arrival_forecast" not in touched and "crush_rate" in touched and "meal_stock" in touched
    ok("日常累积：单个指标出错只跳过它自己")


def test_esr_history_percentile_uses_rolling_4w_sums():
    with Tmp() as d:
        # 造3年逐周历史：每周净销售100000；再把最近4周改大
        from datetime import timedelta
        start = date(2023, 1, 5)
        pts = [{"d": (start + timedelta(days=7 * i)).isoformat(), "v": 100000.0} for i in range(150)]
        hs.record_points("esr_net_sales", pts, d)
        last = pts[-1]["d"]
        r = {"exportSales": {"available": True, "commodity": "Soybeans", "weekEnding": last, "total4wSumMT": 900000,
                             "recentWeeks": [{"weekEnding": last, "netSalesMT": 100000.0}]}}
        hs.update_and_attach(r, base_dir=d)
        h = r["exportSales"]["history"]
        assert h["basis"] == "近4周净销售合计" and h["n"] > 100 and h["percentile"] == 100.0, h
        assert h["min"] == 400000.0 and h["max"] == 400000.0, "历史里每个4周窗口合计都是400000"
    ok("出口净销售历史：用近4周滚动合计跟历史同口径比较")


# ===================== 回填 =====================
class Patch:
    """临时替换fd里的网络函数，退出时还原。"""
    def __init__(self, **kw):
        self.kw = kw
        self.old = {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = getattr(fd, k)
            setattr(fd, k, v)
        self.old_sleep = bf.time.sleep
        bf.time.sleep = lambda s: None
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            setattr(fd, k, v)
        bf.time.sleep = self.old_sleep


def test_backfill_us_stocks_to_use():
    def rows_for(year, es, dc, ex):
        base = {"marketYear": str(year), "calendarYear": str(year + 1), "month": "05"}
        return [dict(base, attributeId=1, value=es), dict(base, attributeId=2, value=dc), dict(base, attributeId=3, value=ex)]
    table = {2018: (25000, 56000, 55000), 2019: (24000, 57000, 45000), 2020: (7000, 60000, 61000), 2021: (7000, 61000, 58000),
             2022: (9000, 62000, 54000), 2024: (0, 0, 0)}
    def fake(url, headers=None, retries=3, timeout=20, post_data=None):
        if "psd/commodities" in url:
            return MOCK_PSD_COMMODITIES, {}
        if "commodityAttributes" in url or "attributes" in url:
            return [{"attributeId": 1, "attributeName": "Ending Stocks"}, {"attributeId": 2, "attributeName": "Domestic Consumption"}, {"attributeId": 3, "attributeName": "Exports"}], {}
        for y, (es, dc, ex) in table.items():
            if url.endswith(f"/year/{y}"):
                return rows_for(y, es, dc, ex), {"httpStatus": 200}
        return None, {"httpStatus": 404}
    with Tmp() as d, Patch(fetch_json_debug=fake):
        rep = bf.backfill_us_stocks_to_use(base_dir=d, from_year=2018, to_year=2024)
        pts = {p["d"]: p["v"] for p in hs.load_series("us_stocks_to_use", d)["points"]}
        assert pts["2018"] == round(25000 / 111000 * 100, 2) and pts["2020"] == round(7000 / 121000 * 100, 2) == 5.79
        assert "2024" not in pts, "期末库存0/消费0(取不到有效数据)的年份不记"
        assert "2023" not in pts, "接口无返回的年份不记"
        assert rep["total"] == 5 and rep["first"] == "2018" and rep["last"] == "2022" and "2023" in rep["notes"][0] and "2024" in rep["notes"][1]
        assert rep["lowest3"][0]["d"] in ("2020", "2021") and "min" in rep
    ok("回填美豆库消比：逐年算 期末库存÷(国内消费+出口)，缺失/无效年份如实报告")


def test_backfill_esr_weekly_merges_market_years_and_skips_no_net_sales_field():
    y2024 = [_esr_row("2024-08-29", "CHINA", 100000), _esr_row("2024-08-29", "JAPAN", 50000), _esr_row("2024-09-05", "CHINA", 60000), _esr_row("2024-09-05", "UNKNOWN", 40000)]
    y2025 = [_esr_row("2024-09-05", "CHINA", 60000), _esr_row("2024-09-05", "UNKNOWN", 40000), _esr_row("2024-09-12", "CHINA", 10000)]   # 交界周重复
    y2023_noflds = [{"weekEndingDate": "2023-09-07", "countryName": "CHINA", "weeklyExports": 999}]
    def fake(url, headers=None, retries=3, timeout=20, post_data=None):
        if "esr/commodities" in url:
            return MOCK_ESR_COMMODITIES, {}
        if "marketYear/2024" in url: return y2024, {"httpStatus": 200}
        if "marketYear/2025" in url: return y2025, {"httpStatus": 200}
        if "marketYear/2023" in url: return y2023_noflds, {"httpStatus": 200}
        return None, {"httpStatus": 404}
    with Tmp() as d, Patch(fetch_json_debug=fake):
        rep = bf.backfill_esr_weekly(base_dir=d, from_year=2023, to_year=2026)
        pts = {p["d"]: p for p in hs.load_series("esr_net_sales", d)["points"]}
        assert sorted(pts) == ["2024-08-29", "2024-09-05", "2024-09-12"], "2023只有装船量没有净销售字段→跳过，不拿装船量冒充"
        assert pts["2024-08-29"]["v"] == 150000 and pts["2024-09-05"]["v"] == 100000, "交界周只算一次"
        assert pts["2024-09-05"]["x"] == {"chinaNetSalesMT": 60000, "unknownNetSalesMT": 40000}
        assert "2023" in rep["notes"][1] and rep["total"] == 3
    ok("回填ESR逐周：交界周不重复、没有净销售字段的年度跳过、中国/未知一并保存")


def test_backfill_meal_stu_from_real_articles():
    items = [{"title": t, "publishTime": pt, "url": u, "content": c} for (t, pt, u, c) in MB_REAL_ARTICLES]
    def fake_json(url, headers=None, retries=3, timeout=20, post_data=None):
        assert post_data["query"] == "全国豆粕供需平衡表" and post_data["startTime"].startswith("2020-01-01")
        return {"resultCode": 0, "total": len(items), "dataList": items}, {}
    def fake_text(url, headers=None, retries=2, timeout=20):
        if url == MB_REAL_ARTICLES[0][2]:
            return MB_REAL_BODY_HTML, {}
        return None, {"error": "403"}
    with Tmp() as d, Patch(fetch_json_debug=fake_json, fetch_text_debug=fake_text):
        rep = bf.backfill_meal_stu(base_dir=d, today=date(2026, 9, 29))
        pts = {p["d"]: p for p in hs.load_series("meal_stu", d)["points"]}
        assert pts["2026-08"]["v"] == 15.12 and pts["2026-08"]["pub"] == "2026-08-31", "8月：最新一篇(8月31日)的正文15.12%，优先于7月31日摘要里的'达15%'"
        assert pts["2026-09"]["v"] == 16.04, "9月(当月)的预测也记，之后被9月底的文章更新"
        assert pts["2026-07"]["v"] == round(105 / 796 * 100, 2) and pts["2026-07"]["x"]["how"] == "computed"
        assert pts["2026-05"]["v"] == 5.94 and pts["2026-01"]["v"] == 12.45
        assert pts["2025-12"]["v"] == 16.3 and pts["2025-11"]["v"] == 15.4
        assert "2026-10" not in pts and "2026-06" not in pts, "未来月份不记；6月摘要只有多月区间，没法给出"
        assert any("403" in b["reason"] for b in rep["bodyProblems"]), "正文请求失败要在报告里如实列出原因"
        assert rep["total"] == len(pts) and "missingMonths" in rep and "2026-06" in rep["missingMonths"]
        # 半年报不是平衡表，不能混进来
        assert all("半年报" not in str(p) for p in pts.values())
    ok("回填国内库消比：真实文章逐月落盘，后发布优先，未来月份/区间/半年报都不误记，缺失月份如实报告")


def test_backfill_meal_stu_no_bodies_uses_summaries_only():
    items = [{"title": t, "publishTime": pt, "url": u, "content": c} for (t, pt, u, c) in MB_REAL_ARTICLES]
    calls = []
    def fake_text(url, headers=None, retries=2, timeout=20):
        calls.append(url); return None, {}
    with Tmp() as d, Patch(fetch_json_debug=lambda *a, **k: ({"resultCode": 0, "total": len(items), "dataList": items}, {}), fetch_text_debug=fake_text):
        rep = bf.backfill_meal_stu(base_dir=d, today=date(2026, 9, 29), fetch_bodies=False)
        pts = {p["d"]: p["v"] for p in hs.load_series("meal_stu", d)["points"]}
        assert not calls, "--no-bodies时一次正文都不能请求"
        assert pts["2026-08"] == 15.0 and "2026-09" not in pts, "只用摘要：8月取7月31日摘要里的'达15%'，9月没有数字"
        assert "未抓正文" in rep["notes"][-1] or any("未抓正文" in n for n in rep["notes"])
    ok("回填国内库消比(--no-bodies)：不请求正文，只用摘要")


def test_meal_balance_ratio_name_variants_and_keep_text():
    r = fd._parse_meal_balance_text("2025年7月产量700万吨，消费690万吨，期末库存105万吨，库存消费比15.20%；8月库销比14.8%。", date(2025, 7, 31), keep_text=True)
    assert r[(2025, 7)]["stu"] == 15.2 and r[(2025, 8)]["stu"] == 14.8, r
    assert "产量700万吨" in r[(2025, 7)]["seg"] and len(r[(2025, 7)]["seg"]) <= 200
    # 有月份标记但一个数都没有：keep_text时保留(回填报告要展示原文)，默认不保留
    only_text = "2025年9月油厂维持高开机高压榨，豆粕物理库存处于饱和状态。"
    assert fd._parse_meal_balance_text(only_text, date(2025, 9, 30)) == {}
    kept = fd._parse_meal_balance_text(only_text, date(2025, 9, 30), keep_text=True)
    assert (2025, 9) in kept and "饱和" in kept[(2025, 9)]["seg"] and fd._usable_meal_record(kept[(2025, 9)])[0] is None
    ok("库消比解析：兼容库存消费比/库销比叫法；keep_text诊断模式保留无数字月份的原文")


def test_backfill_meal_stu_reports_unusable_month_text_and_body_problems():
    old = [("Mysteel：全国10月豆粕供需平衡表", "2025-09-30 14:41", "https://ncp.mysteel.com/a/old.html", "简析：2025年9月油厂维持高开机高压榨，豆粕物理库存处于饱和状态，整体消化进度偏慢。"),
           ("Mysteel：全国豆粕供需平衡表（2026年5月）", "2026-05-29 14:41", "https://ncp.mysteel.com/a/may.html", MB_REAL_ARTICLES[3][3])]
    items = [{"title": t, "publishTime": pt, "url": u, "content": c} for (t, pt, u, c) in old]
    with Tmp() as d, Patch(fetch_json_debug=lambda *a, **k: ({"resultCode": 0, "total": 2, "dataList": items}, {}), fetch_text_debug=lambda url, **k: ("<html>免责声明</html>", {})):
        rep = bf.backfill_meal_stu(base_dir=d, today=date(2026, 9, 29))
        um = {u["month"]: u for u in rep["unusableMonths(前12个，附该月片段原文)"]}
        assert "2025-09" in um and "饱和" in um["2025-09"]["segment"], um
        assert rep["total"] == 1 and rep["first"] == "2026-05"
        assert rep["bodyProblems"] and all("reason" in b for b in rep["bodyProblems"])
    ok("回填国内库消比：给不出数的月份带原文片段，正文问题带原因——供修解析规则用")


# ===================== 校准摘要 =====================
def test_quantiles_share_and_outliers_helpers():
    assert bf.quantiles([1, 2, 3, 4, 5], (0, 25, 50, 100)) == {"p0": 1, "p25": 2, "p50": 3, "p100": 5}
    assert bf.quantiles([], (50,)) == {}
    assert bf.share([1, 2, 3, 4], lambda v: v > 2) == 50.0 and bf.share([], lambda v: True) is None
    pts = [{"d": f"2020-01-{i:02d}", "v": 100.0 + (i % 3)} for i in range(1, 29)] + [{"d": "2020-02-01", "v": 5000.0}]
    out = bf.find_outliers(pts)
    assert len(out) == 1 and out[0]["d"] == "2020-02-01" and out[0]["prev"] == 100.0 + (28 % 3) and out[0]["next"] is None
    assert bf.find_outliers(pts[:10]) == [], "样本<20不做异常检测"
    assert bf.esr_boundary_weeks([{"d": "2020-08-27", "v": 1.0}, {"d": "2020-09-03", "v": 2.0}, {"d": "2020-10-01", "v": 3.0}]) == {"2020": ["08-27:1", "09-03:2"]}
    ok("报告工具：分位数/占比/稳健异常点/市场年度切换周")


def test_calibration_summary_from_synthetic_series():
    with Tmp() as d:
        hs.record_points("us_stocks_to_use", [{"d": str(2000 + i), "v": v} for i, v in enumerate([3, 4, 6, 7, 8, 5.5, 12, 15, 6.5, 9])], d)
        # ESR：40周，每周100万吨；第20周暴增到300万吨(相对前4周均值+200%)；第21周回到100万吨(相对前4周均值(3个100+300)/4=150 → -33%)
        from datetime import timedelta
        w = [{"d": (date(2024, 1, 4) + timedelta(days=7 * i)).isoformat(), "v": 1000000.0} for i in range(40)]
        w[20]["v"] = 3000000.0
        hs.record_points("esr_net_sales", w, d)
        hs.record_points("meal_stu", [{"d": "2026-01", "v": 12.45}, {"d": "2026-02", "v": 20.95}, {"d": "2026-05", "v": 5.94}, {"d": "2026-08", "v": 15.12}], d)
        hs.record_points("meal_stock", [{"d": "2026-05-29", "v": 34.74}, {"d": "2026-08-31", "v": 116.73}, {"d": "2026-08-24", "v": 111.0}], d)
        c = bf.calibration_summary(d)
        u = c["us_stocks_to_use"]
        assert u["n"] == 10 and u["currentThresholds"]["tight<5"]["years"] == ["2000", "2001"], u["currentThresholds"]
        assert u["currentThresholds"]["loose>10"] == {"shareOfYears%": 20.0, "years": ["2006", "2007"]}
        assert u["latest"]["d"] == "2009" and u["latestPercentile"] == round((sum(1 for v in [3, 4, 6, 7, 8, 5.5, 12, 15, 6.5] if v < 9) + 0) / 9 * 100, 1)
        e = c["esr_net_sales"]
        assert e["weeksEvaluated"] == 36 and e["weeksWithBaseBelow100k(判中性)"] == 0
        sig = e["signalShare%(当前±40%)"]
        # 36个评估周里：第20周(+200%)偏多；第21周(-33%)中性；第22~24周：前4周均值含300万吨，当周100万吨→-33%/-38%/-40%... 逐周手算见下
        bull = sig["bullish"]
        assert bull == round(1 / 36 * 100, 1), f"只有第20周超过+40%: {sig}"
        assert abs(sig["bullish"] + sig["bearish"] + sig["neutral"] - 100) < 0.2, sig
        assert c["meal_stu"]["currentThresholds(v84: 松阈值14→16)"] == {"tight<=10": 25.0, "loose>=14": 50.0, "loose>=16": 25.0}
        bc = c["meal_stu"]["byFestivalCohort"]
        assert bc["春节扰动月"] == {"n": 1, "values": [20.95]}, bc          # 合成数据里只有2026-02是春节扰动月
        assert bc["平常月"]["n"] == 3 and bc["平常月"]["share>=16%"] == 0.0 and bc["平常月"]["share<=10%"] == 33.3, bc   # 2026-01/05/08
        m = c["meal_stock"]
        assert m["currentThresholds"] == {"tight<50": 33.3, "loose>100": 66.7} and m["pointsPerYear"] == {"2026": 3}
        by = {x["week"]: x for x in m["spotChecks(独立来源Mysteel英文站周报)"]}
        assert all(x["result"].startswith("缺失") for x in by.values()), "合成数据没有x.week，按周次匹配不到——不会按日期最近去乱配"
        assert "不足180天" in m["coverage"], m["coverage"]       # 合成的3个点只跨3个月：跨度不够，如实说明
    ok("校准摘要：美豆库消比/出口信号触发比例/国内库消比/周度库存的当前阈值在历史里的位置、校验点核对")


def test_spot_checks_match_by_week_label_not_nearest_date():
    """★上一份报告的教训：第31周校验点(8月3日)没有对应的点，按"日期最近"被错配到第30周的点(7月27日，96.73)，误报"不一致"。
    现在按点的x.week匹配：没有这一周的点就如实报告"缺失"。"""
    pts = [{"d": "2026-08-31", "v": 116.73, "x": {"week": "2026-W35"}},
           {"d": "2026-07-27", "v": 96.73, "x": {"week": "2026-W30"}},      # 第30周，离第31周(8月3日)最近，但不能拿来比
           {"d": "2026-06-01", "v": 856.85, "x": {"week": "2026-W22"}},      # 取成了大豆库存
           {"d": "2026-06-08", "v": 50.6, "x": {"week": "2026-W23"}}]
    by = {c["week"]: c for c in bf.meal_stock_spot_checks(pts)}
    assert by["2026-W35"]["result"] == "通过"
    assert by["2026-W31"]["result"].startswith("缺失"), "第31周没有点：不能被第30周的96.73冒充"
    assert by["2026-W22"]["result"] == "不一致" and by["2026-W22"]["got"] == 856.85
    assert by["2026-W23"]["result"] == "通过", "50.6 vs 50.65，差0.05在0.1容差内"
    assert bf.meal_stock_spot_checks([{"d": "2026-08-31", "v": 116.73}])[-1]["result"].startswith("缺失"), "没有x.week的旧点匹配不上"
    ok("周度库存校验点：按周次匹配，缺失/不一致/通过分得清，不再被相邻周错配")


def test_main_calibrate_only_makes_no_network_calls():
    with Tmp() as d:
        hs.record_points("us_stocks_to_use", [{"d": str(2000 + i), "v": 3.0 + i} for i in range(6)], d)
        def boom(*a, **k):
            raise AssertionError("calibrate不应该联网")
        with Patch(fetch_json_debug=boom, fetch_text_debug=boom):
            rep = bf.main(["--only", "calibrate"], base_dir=d)
        assert rep["series"] == [] and rep["calibration"]["us_stocks_to_use"]["n"] == 6
        saved = json.load(open(os.path.join(d, "_backfill_report.json"), encoding="utf-8"))
        assert "calibration" in saved
    ok("回填入口：--only calibrate 不联网，只重新生成校准摘要")


# ===================== 春节日历 =====================
def test_spring_festival_calendar_and_month_context():
    import cn_calendar as cc
    # 21个日期已用独立农历库(lunardate)逐年校验过一致，这里锁住几个关键年份
    assert cc.spring_festival(2024).isoformat() == "2024-02-10" and cc.spring_festival(2025).isoformat() == "2025-01-29" and cc.spring_festival(2026).isoformat() == "2026-02-17"
    assert cc.spring_festival(2040) is None
    c = cc.festival_month_context(2026, 2)
    assert c["disturbed"] and c["coreDays"] == 22 and c["phase"] == "假期停摆" and c["festivalDate"] == "2026-02-17" and "骤降" in c["bias"], c
    c = cc.festival_month_context(2026, 3)
    assert c["disturbed"] and c["coreDays"] == 10 and c["phase"] == "节后恢复", c
    assert not cc.festival_month_context(2026, 1)["disturbed"], "2026年1月：核心窗口从2月7日才开始"
    c = cc.festival_month_context(2025, 1)
    assert c["disturbed"] and c["coreDays"] == 13 and c["phase"] == "节前备货", c
    c = cc.festival_month_context(2025, 2)
    assert c["disturbed"] and c["coreDays"] == 19 and c["phase"] == "假期停摆", c
    assert not cc.festival_month_context(2025, 3)["disturbed"]
    assert cc.festival_month_context(2024, 2)["disturbed"] and not cc.festival_month_context(2024, 1)["disturbed"], "2024春节2月10日：1月只有1天(1/31)落在窗口里"
    assert not any(cc.festival_month_context(y, m)["disturbed"] for y in (2024, 2025, 2026) for m in range(4, 13)), "4~12月永远不是春节扰动月"
    assert cc.festival_month_context(2040, 2) == {"festivalDate": None, "coreDays": 0, "disturbed": False, "phase": None, "bias": None}, "日期表之外的年份：不知道就不假装知道"
    assert cc.festival_cohort("2026-02") == "春节扰动月" and cc.festival_cohort("2026-08") == "平常月" and cc.festival_cohort("2026-02-17") == "春节扰动月" and cc.festival_cohort("坏") is None
    ok("春节日历：21个日期(独立校验过)+当月扰动判定(2026-02假期停摆22天、2025-01节前备货13天…)")


# ===================== 样本代表性 + 同类月份 =====================
def test_national_day_context_and_unified_holiday_entry():
    import cn_calendar as cc
    c = cc.national_day_month_context(2026, 10)
    assert c["disturbed"] and c["coreDays"] == 14 and c["phase"] == "假期停摆" and c["festivalDate"] == "2026-10-01" and "油厂" in c["bias"], c
    n9 = cc.national_day_month_context(2026, 9)
    assert n9["coreDays"] == 4 and not n9["disturbed"], "9月只有27~30日4天落在窗口里，不足7天"
    assert not any(cc.national_day_month_context(2026, m)["disturbed"] for m in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12))
    h = cc.holiday_month_context(2026, 10)
    assert h["name"] == "国庆" and h["level"] == "mild" and h["disturbed"]
    h = cc.holiday_month_context(2026, 2)
    assert h["name"] == "春节" and h["level"] == "strong" and h["coreDays"] == 22
    h = cc.holiday_month_context(2026, 8)
    assert h["name"] is None and h["level"] is None and not h["disturbed"]
    assert cc.festival_cohort("2026-10") == "国庆扰动月" and cc.festival_cohort("2026-02") == "春节扰动月" and cc.festival_cohort("2026-08") == "平常月"
    ok("国庆日历：10月为国庆扰动月(mild)，统一入口区分春节(strong)/国庆(mild)/无")


def test_coverage_guard_rejects_sparse_and_short_samples():
    from datetime import timedelta
    # 稀疏：4年里只有20个周点(应有约208个)
    sparse = [{"d": (date(2022, 6, 20) + timedelta(days=70 * i)).isoformat(), "v": float(50 + i)} for i in range(20)]
    assert "样本不连续" in hs.coverage_problem(sparse, "weekly")
    s = hs.summarize(sparse + [{"d": "2026-09-28", "v": 129.0}], 129.0, "2026-09-28", "weekly")
    assert s["percentile"] is None and "样本不连续" in s["sparse"] and s["seasonal"] is None, "样本不连续时总体分位和同月分位都不给"
    # 跨度太短：14周
    short = [{"d": (date(2026, 6, 1) + timedelta(days=7 * i)).isoformat(), "v": float(i)} for i in range(14)]
    assert "不足180天" in hs.coverage_problem(short, "weekly")
    # 连续：一年零一周的周度点
    full = [{"d": (date(2025, 9, 1) + timedelta(days=7 * i)).isoformat(), "v": float(i)} for i in range(55)]
    assert hs.coverage_problem(full, "weekly") is None
    s = hs.summarize(full + [{"d": "2026-09-28", "v": 30.0}], 30.0, "2026-09-28", "weekly")
    assert s["percentile"] is not None and s["sparse"] is None
    # 年度/不定期序列不做连续性检查
    assert hs.coverage_problem([{"d": "2006", "v": 1.0}, {"d": "2026", "v": 2.0}], "yearly") is None
    # 月度：20个点跨29个月(69%)通过；同样跨度只有10个点(34%)不通过
    monthly_ok = [{"d": f"2024-{m:02d}", "v": float(m)} for m in range(1, 13)] + [{"d": f"2025-{m:02d}", "v": float(m)} for m in range(1, 9)]
    assert hs.coverage_problem(monthly_ok, "monthly") is None
    monthly_sparse = [{"d": d, "v": 1.0} for d in ("2024-01", "2024-05", "2024-09", "2025-01", "2025-05", "2025-09", "2026-01", "2026-03", "2026-05", "2026-07")]
    assert "样本不连续" in hs.coverage_problem(monthly_sparse, "monthly")
    ok("样本代表性：稀疏/跨度短的序列不给分位(第一次回填里的周度库存就是这种)，连续的照常给")


def test_cohort_percentile_compares_only_like_months():
    import cn_calendar as cc
    pts = []
    for y in range(2018, 2026):
        for m in range(1, 13):
            v = 20.0 if cc.festival_cohort(f"{y}-{m:02d}") == "春节扰动月" else 10.0
            pts.append({"d": f"{y}-{m:02d}", "v": v + (y - 2018) * 0.1})
    cur = {"d": "2026-02", "v": 20.5}
    s = hs.summarize(pts + [cur], 20.5, "2026-02", "monthly", cohort_fn=lambda p: cc.festival_cohort(p["d"]))
    assert s["percentile"] > 90, "总体：20.5高于几乎所有平常月"
    # 春节扰动月(2018~2025年共13个，值20.0~20.7)里，当前20.5在中间偏上
    assert s["cohort"] == {"label": "春节扰动月", "n": 13, "percentile": 69.2, "median": 20.4}, s["cohort"]
    s2 = hs.summarize(pts + [{"d": "2026-08", "v": 10.5}], 10.5, "2026-08", "monthly", cohort_fn=lambda p: cc.festival_cohort(p["d"]))
    assert s2["cohort"]["label"] == "平常月" and s2["cohort"]["n"] == 75, "平常月只跟平常月比(2018~2025年共96个月，去掉13个春节扰动月和8个国庆扰动月=75)"
    few = [{"d": "2025-01", "v": 7.4}, {"d": "2025-02", "v": 9.86}, {"d": "2026-03", "v": 15.54}]
    s3 = hs.summarize(few, 20.95, "2026-02", "monthly", cohort_fn=lambda p: cc.festival_cohort(p["d"]))
    assert s3["cohort"] == {"label": "春节扰动月", "n": 3, "percentile": None, "median": 9.86}, s3["cohort"]
    ok("同类月份分位：春节扰动月只跟往年春节月比、平常月只跟平常月比，同类<4个不给分位")


# ===================== ESR清洗 =====================
def test_clean_esr_points_drops_shutdown_and_replaces_rollover_weeks():
    w = [{"d": d, "v": v} for d, v in [("2018-12-13", 1000000), ("2018-12-27", 0), ("2019-01-03", -610910), ("2019-02-14", 6772242), ("2019-03-07", 700000),
                                        ("2020-08-20", 1865387), ("2020-08-27", 1781287), ("2020-09-03", 5642515), ("2020-09-10", 2398936), ("2020-09-17", 3194675)]]
    c = hs.clean_esr_points(w)
    ds = [p["d"] for p in c]
    assert "2018-12-27" not in ds and "2019-01-03" not in ds and "2019-02-14" not in ds, "政府停摆期间(2018-12-20~2019-02-28)的点被剔除"
    assert "2018-12-13" in ds and "2019-03-07" in ds
    roll = next(p for p in c if p["d"] == "2020-09-03")
    assert roll["v"] == (1781287 + 2398936) / 2 and roll["x"] == {"rolloverAdjusted": True}, "切换周用相邻两周均值代替"
    assert next(p for p in c if p["d"] == "2020-09-10")["v"] == 2398936, "其它周不动"
    # 切换周在末尾(下一周还没出)或相邻周缺失(间隔>10天)：丢弃，不硬造
    assert [p["d"] for p in hs.clean_esr_points([{"d": "2026-08-27", "v": 1.0}, {"d": "2026-09-03", "v": 9.0}])] == ["2026-08-27"]
    assert [p["d"] for p in hs.clean_esr_points([{"d": "2026-08-13", "v": 1.0}, {"d": "2026-09-03", "v": 9.0}, {"d": "2026-09-10", "v": 2.0}])] == ["2026-08-13", "2026-09-10"]
    for d, exp in [("2026-08-31", True), ("2026-09-06", True), ("2026-09-03", True), ("2026-08-30", False), ("2026-09-07", False), ("2025-09-04", True), ("2024-08-29", False)]:
        assert hs.is_rollover_week(d) is exp, d
    ok("ESR清洗：剔除政府停摆期间、切换周(8/31~9/6)用相邻两周均值代替、无法代替就丢弃")


def test_esr_history_uses_cleaned_rolling_sums_and_skips_rollover_latest():
    with Tmp() as d:
        from datetime import timedelta
        start = date(2023, 1, 5)
        pts = [{"d": (start + timedelta(days=7 * i)).isoformat(), "v": 100000.0} for i in range(150)]
        for p in pts:                                       # 每年切换周设成虚高
            if hs.is_rollover_week(p["d"]):
                p["v"] = 3000000.0
        hs.record_points("esr_net_sales", pts, d)
        last = pts[-1]["d"]
        r = {"exportSales": {"available": True, "commodity": "Soybeans", "weekEnding": last, "total4wSumMT": 400000, "recentWeeks": [{"weekEnding": last, "netSalesMT": 100000.0}]}}
        hs.update_and_attach(r, base_dir=d)
        h = r["exportSales"]["history"]
        assert h["max"] == 400000.0, f"清洗后历史里所有4周合计都是400000，切换周的虚高(300万)不应出现: {h}"
        r2 = {"exportSales": {"available": True, "commodity": "Soybeans", "weekEnding": "2026-09-03", "latestIsRollover": True, "total4wSumMT": None,
                              "recentWeeks": [{"weekEnding": "2026-09-03", "netSalesMT": 900000.0}]}}
        hs.update_and_attach(r2, base_dir=d)
        assert "history" not in r2["exportSales"], "最新一周是切换周：不给分位"
    ok("出口净销售历史：分位基于清洗后的4周合计；最新周是切换周时不给分位")


# ===================== 日常累积：周度库存recentWeeks / 库消比richer x =====================
def test_meal_stock_accumulates_every_recent_week():
    with Tmp() as d:
        r = {"mysteelMealStock": {"available": True, "value": 129.64, "date": "2026-09-28", "weekLabel": "2026年第39周",
                                  "recentWeeks": [{"date": "2026-09-28", "value": 129.64, "week": "2026年第39周"}, {"date": "2026-09-21", "value": 117.32, "week": "2026年第38周"},
                                                  {"date": "2026-09-07", "value": 105.0, "week": "2026年第36周"}]}}
        touched = hs.update_and_attach(r, base_dir=d)
        pts = {p["d"]: p for p in hs.load_series("meal_stock", d)["points"]}
        assert sorted(pts) == ["2026-09-07", "2026-09-21", "2026-09-28"] and pts["2026-09-21"]["x"] == {"week": "2026年第38周"}
        assert "meal_stock" in touched
        # 下一次运行窗口里多了一周(之前漏的第37周)：补上；已有的不变
        r2 = {"mysteelMealStock": {"available": True, "value": 129.64, "date": "2026-09-28", "weekLabel": "2026年第39周",
                                   "recentWeeks": [{"date": "2026-09-14", "value": 111.0, "week": "2026年第37周"}, {"date": "2026-09-28", "value": 129.64, "week": "2026年第39周"}]}}
        assert hs.update_and_attach(r2, base_dir=d) == ["meal_stock"]
        assert len(hs.load_series("meal_stock", d)["points"]) == 4
        assert hs.update_and_attach(r2, base_dir=d) == [], "再跑一次没有新周：不产生改动"
        assert r2["mysteelMealStock"]["history"]["n"] == 3 and r2["mysteelMealStock"]["history"]["percentile"] is None
    ok("周度库存累积：窗口里所有能提取的周都记下，漏掉的周之后补上，重复运行无变化")


def test_meal_stu_accumulates_richer_fields_and_attaches_cohort():
    import cn_calendar as cc
    with Tmp() as d:
        seed = [{"d": f"{y}-{m:02d}", "v": (20.0 if cc.festival_cohort(f"{y}-{m:02d}") == "春节扰动月" else 12.0) + m * 0.05} for y in (2023, 2024, 2025) for m in range(1, 13)]
        hs.record_points("meal_stu", seed, d)
        r = {"mysteelMealStu": {"available": True, "value": 20.95, "month": "2026-02", "method": "stated", "date": "2026-02-28",
                                "stockWan": 93.0, "consumptionWan": 444.0, "productionWan": 500.0}}
        hs.update_and_attach(r, base_dir=d)
        pt = [p for p in hs.load_series("meal_stu", d)["points"] if p["d"] == "2026-02"][0]
        assert pt["x"] == {"how": "stated", "stock": 93.0, "consumption": 444.0, "production": 500.0} and pt["pub"] == "2026-02-28"
        h = r["mysteelMealStu"]["history"]
        assert h["cohort"]["label"] == "春节扰动月" and h["cohort"]["n"] == 5 and h["cohort"]["percentile"] is not None, h["cohort"]     # 2023-01/02、2024-02、2025-01/02
        assert h["cohort"]["percentile"] >= 90, "20.95高于往年春节月(约20.1~20.2)"
    ok("国内库消比累积：库存/消费/产量一并存下，历史分位按同类月份(春节扰动月/平常月)比")


def test_backfill_meal_stu_stores_stock_consumption_and_defaults_skip_meal_stock():
    items = [{"title": t, "publishTime": pt, "url": u, "content": c} for (t, pt, u, c) in MB_REAL_ARTICLES]
    with Tmp() as d, Patch(fetch_json_debug=lambda *a, **k: ({"resultCode": 0, "total": len(items), "dataList": items}, {}), fetch_text_debug=lambda url, **k: (MB_REAL_BODY_HTML, {}) if url == MB_REAL_ARTICLES[0][2] else (None, {"error": "x"})):
        bf.backfill_meal_stu(base_dir=d, today=date(2026, 9, 29))
        pts = {p["d"]: p for p in hs.load_series("meal_stu", d)["points"]}
        assert pts["2026-08"]["x"] == {"how": "stated", "stock": 117.0, "consumption": 772.0, "production": 800.0}, pts["2026-08"]
        assert pts["2026-05"]["x"]["consumption"] == 673.0 and "stock" not in pts["2026-05"]["x"], "5月：库存30万吨与库消比不自洽被丢弃，不存"
    assert bf.DEFAULT_JOBS == list(bf.JOBS.keys()) and "hog_ratio" in bf.DEFAULT_JOBS and "meal_stock" not in bf.JOBS and "sample" not in bf.JOBS and "margin" in bf.JOBS and "spread" in bf.JOBS      # v96.3起默认清单加了soy_import、arrival，v98加了crush_rate；meal_stock(补不全)和sample(一次性诊断)仍不在默认里
    assert "meal_stock" not in bf.DEFAULT_JOBS and "sample" not in bf.DEFAULT_JOBS and set(bf.DEFAULT_JOBS) <= set(bf.JOBS)      # ★v99起meal_stock(一直补不全)和sample(一次性诊断)都已移除，见REMOVED_backfill_sample_and_meal_stock.md；这条守卫防止它们被悄悄加回来；默认清单里的每一项都必须是已注册的任务
    ok("回填国内库消比：存库存/消费/产量；默认回填项不含补不全的周度库存")


def test_sparse_history_falls_back_to_recent_continuous_window():
    """★第一次回填的周度库存：早年零零散散(2022年28个、2023年3个…)，之后才逐周累积。整体判"不连续"会让它永远恢复不了；
    近两年连续时应改用近两年的样本，并如实说明。近两年也不连续才不给分位。"""
    from datetime import timedelta
    old = [{"d": (date(2022, 6, 20) + timedelta(days=60 * i)).isoformat(), "v": 20.0 + i} for i in range(12)]      # 零散旧点(约每两个月一个，止于2024-04)
    recent = [{"d": (date(2025, 1, 6) + timedelta(days=7 * i)).isoformat(), "v": 60.0 + (i % 40)} for i in range(90)]   # 近两年逐周
    pts = old + recent
    cur = {"d": "2026-09-28", "v": 95.0}
    s = hs.summarize(pts + [cur], 95.0, "2026-09-28", "weekly")
    assert s["percentile"] is not None and s["sparse"] is None, s
    assert "仅用最近2年" in s["window"] and s["since"] >= "2024-09", s["since"]
    assert s["min"] >= 60.0, "早年20~31的零散低值不能混进来拉低/扭曲分位"
    # 近两年也稀疏：不给
    thin = old + [{"d": (date(2025, 1, 6) + timedelta(days=45 * i)).isoformat(), "v": 60.0 + i} for i in range(16)]
    s2 = hs.summarize(thin + [cur], 95.0, "2026-09-28", "weekly")
    assert s2["percentile"] is None and "样本不连续" in s2["sparse"] and s2["window"] is None
    # 整体连续：不触发回退
    full = [{"d": (date(2024, 1, 4) + timedelta(days=7 * i)).isoformat(), "v": float(i)} for i in range(140)]
    assert hs.summarize(full + [cur], 95.0, "2026-09-28", "weekly")["window"] is None
    ok("样本不连续时退回近两年连续样本(并说明)；近两年也不连续才不给分位")



# ===================== 盘面压榨毛利 =====================
def _kl(dates_prices):
    return [{"date": d, "close": c} for d, c in dates_prices]


def test_crush_margin_series_only_dates_present_in_all_three_contracts():
    m = _kl([("2026-05-04", 3400), ("2026-05-05", 3410), ("2026-05-06", 3420)])
    o = _kl([("2026-05-04", 8500), ("2026-05-05", 8510)])                    # 缺5/6
    b = _kl([("2026-05-05", 4200), ("2026-05-06", 4210), ("2026-05-04", 4200)])
    ser = fd.crush_margin_series(m, o, b)
    assert sorted(ser) == ["2026-05-04", "2026-05-05"], "5/6豆油缺 → 不算(缺一个就不算，不用0硬凑)"
    assert ser["2026-05-04"] == round(3400 * 0.785 + 8500 * 0.185 - 4200, 1) == 41.5, "手算验证：3400×0.785+8500×0.185-4200=41.5"
    assert fd.crush_margin_series([], m, o) == {}
    assert fd.crush_margin_series([{"date": None, "close": 1}, {"date": "2026-05-04", "close": None}], m, o) == {}
    ok("榨利逐日序列：只算三个合约都有收盘价的日期，手算41.5验证")


def test_fetch_crush_margin_carries_data_date_oldest_of_three():
    old = fd.fetch_dce_daily_kline
    def fake(symbol, max_rows=260):
        d = {"M2609": "2026-09-29", "Y2609": "2026-09-29", "B2609": "2026-09-28"}[symbol]
        p = {"M2609": 3400, "Y2609": 8500, "B2609": 4200}[symbol]
        return {"available": True, "symbol": symbol, "bars": [{"date": d, "close": p}], "source": "测试"}
    fd.fetch_dce_daily_kline = fake
    try:
        from datetime import datetime as dt, timezone as tz
        r = fd.fetch_crush_margin(9, dt(2026, 7, 12, tzinfo=tz.utc))
        assert r["date"] == "2026-09-28" and r["datesAligned"] is False, "三个合约最新日期不一致：以最旧的为准并标注"
        fd.fetch_dce_daily_kline = lambda symbol, max_rows=260: {"available": True, "symbol": symbol, "bars": [{"date": "2026-09-29", "close": {"M2609": 3400, "Y2609": 8500, "B2609": 4200}[symbol]}]}
        r2 = fd.fetch_crush_margin(9, dt(2026, 7, 12, tzinfo=tz.utc))
        assert r2["date"] == "2026-09-29" and r2["datesAligned"] is True
        fd.fetch_dce_daily_kline = lambda symbol, max_rows=260: {"available": True, "symbol": symbol, "bars": [{"close": {"M2609": 3400, "Y2609": 8500, "B2609": 4200}[symbol]}]}
        r3 = fd.fetch_crush_margin(9, dt(2026, 7, 12, tzinfo=tz.utc))
        assert r3["date"] is None and r3["grossMargin"] == 41.5, "K线没有日期字段(旧测试的桩数据)：date为None，不报错"
    finally:
        fd.fetch_dce_daily_kline = old
    ok("榨利抓取：带数据日期(三者取最旧，不一致时标注)，没有日期字段时不报错")


def test_crush_margin_windows_match_contract_trading_windows():
    W = hs.CRUSH_MARGIN_WINDOWS
    assert W["sep"]["months"] == [4, 5, 6, 7] and W["may"]["months"] == [12, 1, 2, 3] and W["jan"]["months"] == [8, 9, 10, 11]
    assert bf._window_ok("2026-06-15", "sep", 2026) and not bf._window_ok("2026-08-01", "sep", 2026) and not bf._window_ok("2025-06-15", "sep", 2026)
    assert bf._window_ok("2025-12-10", "may", 2026), "5月合约(2026到期)的12月窗口在前一年"
    assert bf._window_ok("2026-02-10", "may", 2026) and not bf._window_ok("2026-12-10", "may", 2026), "2026年12月属于2027到期的5月合约"
    assert bf._window_ok("2026-09-15", "jan", 2027), "1月合约(2027到期)的8-11月窗口在前一年(2026)"
    assert not bf._window_ok("2027-09-15", "jan", 2027) and not bf._window_ok("2026-12-15", "jan", 2027)
    ok("榨利窗口：9月合约4-7月、5月合约12-3月(12月在前一年)、1月合约8-11月(在前一年)")


def test_backfill_crush_margin_windows_dedup_and_reports_unfetchable_contracts():
    def bars(d0, n, price):
        from datetime import timedelta as td
        return [{"date": (d0 + td(days=i)).isoformat(), "close": price} for i in range(n)]
    d_sep = date(2025, 3, 20)                     # 2509合约：3/20起200天，覆盖4-7月窗口及窗口外
    table = {"M2509": bars(d_sep, 200, 3400), "Y2509": bars(d_sep, 200, 8500), "B2509": bars(d_sep, 200, 4200),
             "M2609": bars(date(2026, 3, 20), 40, 3400), "Y2609": bars(date(2026, 3, 20), 40, 8500), "B2609": bars(date(2026, 3, 20), 40, 4200)}
    fetched = []
    def fake_kline(symbol, max_rows=260):
        fetched.append((symbol, max_rows))
        return {"available": True, "symbol": symbol, "bars": table[symbol]} if symbol in table else {"available": False, "reason": "已到期，接口返回空数据"}
    with Tmp() as d, Patch(fetch_dce_daily_kline=fake_kline):
        rep = bf.backfill_crush_margin(base_dir=d, from_year=2025, to_year=2026)
        sep = hs.load_series("crush_margin_sep", d)["points"]
        ds = [p["d"] for p in sep]
        # 2509合约：3/20起200天(到10/5)，窗口(2025年4-7月)内=4/1~7/31共122个日历日；2609合约：3/20起40天(到4/28)，窗口内=4/1~4/28共28个
        assert len(sep) == 122 + 28 and min(ds) == "2025-04-01" and max(ds) == "2026-04-28", (len(sep), min(ds), max(ds))
        assert all(int(x[5:7]) in (4, 5, 6, 7) for x in ds), "只存建议交易窗口(4-7月)内的点：3月和8月以后的不存"
        assert not any(x.startswith("2025-03") or x.startswith("2025-08") or x.startswith("2026-03") for x in ds)
        assert all(p["v"] == 41.5 for p in sep)
        assert sum(1 for p in sep if p["x"]["contract"] == "2509") == 122 and sum(1 for p in sep if p["x"]["contract"] == "2609") == 28
        assert hs.load_series("crush_margin_may", d)["points"] == [] and hs.load_series("crush_margin_jan", d)["points"] == []
        failed = [c for c in rep["contracts"] if c["failed"]]
        assert {(c["type"], c["contract"]) for c in failed} == {("may", "2505"), ("may", "2605"), ("jan", "2501"), ("jan", "2601")}, "5月/1月合约的桩数据没配 → 明确列出取不到的合约"
        assert all(len(c["failed"]) == 3 and all("已到期" in f for f in c["failed"]) for c in failed), "每个取不到的合约列出M/Y/B三个代码和原因"
        assert "取不到" in rep["notes"][0]
        assert any(m >= 6000 for _, m in fetched), "取全部历史(max_rows很大)，不是只取最近260根"
        assert {e["key"] for e in rep["series"]} == {"crush_margin_sep", "crush_margin_may", "crush_margin_jan"}
    ok("回填榨利：只存建议交易窗口内的逐日毛利；取不到的合约(已到期等)明确列出；取全部历史")


def test_crush_margin_accumulates_daily_and_attaches_seasonal_percentile():
    with Tmp() as d:
        # 回填了往年同月(7月)的样本：8年×20个交易日=160个点，值0~159
        pts = [{"d": f"{2018 + y}-07-{i + 1:02d}", "v": float(y * 20 + i)} for y in range(8) for i in range(20)]
        hs.record_points("crush_margin_sep", pts, d)
        r = {"crushMargins": {"sep": {"available": True, "contractMonth": 9, "date": "2026-07-10", "mealSymbol": "M2609", "grossMargin": 150.0},
                              "may": {"available": False, "reason": "x"}, "jan": {"available": True, "date": None, "grossMargin": 5.0}}}
        touched = hs.update_and_attach(r, base_dir=d)
        assert "crush_margin_sep" in touched and "crush_margin_may" not in touched and "crush_margin_jan" not in touched
        h = r["crushMargins"]["sep"]["history"]
        assert h["seasonal"]["month"] == 7 and h["seasonal"]["n"] == 160, "往年同月样本160个(2026年自己的点不算)"
        assert h["seasonal"]["percentile"] == 94.1, h["seasonal"]     # 150在0..159里：150个更小+1个相等的一半=150.5/160=94.1%
        assert h["sparse"] is None, "seasonal-daily不做样本密度检查(回填的是各年窗口内的点，本来就不连续)"
        assert "history" not in r["crushMargins"]["may"] and "history" not in r["crushMargins"]["jan"], "不可用/没有日期的不记录"
        assert hs.update_and_attach(r, base_dir=d) == [], "重复运行无变化"
        pt = [p for p in hs.load_series("crush_margin_sep", d)["points"] if p["d"] == "2026-07-10"][0]
        assert pt["v"] == 150.0 and pt["x"] == {"contract": "M2609"}
    ok("榨利累积：逐日追加、往年同月分位、不做密度检查、不可用不记录、重复运行无变化")


def test_calibration_summary_includes_crush_margin():
    with Tmp() as d:
        hs.record_points("crush_margin_sep", [{"d": f"2025-0{m}-01", "v": v} for m, v in [(4, -50.0), (5, 100.0), (6, 250.0), (7, 400.0)]], d)
        c = bf.calibration_summary(d)["crush_margin_sep"]
        assert c["n"] == 4 and c["share<0"] == 25.0 and c["share>300"] == 25.0
        assert c["medianByMonth"] == {"04": -50.0, "05": 100.0, "06": 250.0, "07": 400.0}
        assert c["pointsPerYear"] == {"2025": 4}
    ok("校准摘要：榨利的分位数、按月中位、<0和>300的占比")



# ===================== 饲料企业豆粕库存天数：回填/诊断 =====================
# 唯一的真实样本(2026-07-03那期摘要，来自第一次回填报告)。其余各周是合成的(格式照它写)，测试里标明。
FEED_REAL_SUMMARY = "Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（20260703） 2026-07-03 16:51 来源：我的钢铁网(Mysteel) 资讯监督 智能摘要 截至7月3日，全国饲料企业豆粕物理库存为7.41天，环比微增0.17天，同比下滑0.50天。供应端受7月超千万吨大豆到港及油厂高开机"


def _feed_item(pub, asof8, text, url=None, title_extra=""):
    return {"title": f"Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（{asof8}）{title_extra}", "publishTime": pub + " 16:51", "url": url or f"https://ncp.mysteel.com/a/{asof8}.html", "content": text}


def test_feed_days_mom_check_uses_consecutive_weeks():
    wk = [{"d": "2026-06-05", "v": 7.10}, {"d": "2026-06-12", "v": 7.30, "x": {"mom": 0.20}}, {"d": "2026-06-19", "v": 7.24, "x": {"mom": -0.06}},
          {"d": "2026-06-26", "v": 7.24, "x": {"mom": 0.99}},            # 文章写的环比与实际差不符
          {"d": "2026-07-17", "v": 7.50, "x": {"mom": 0.26}},            # 隔了3周：不可比，不参与
          {"d": "2026-07-24", "v": 7.60}]                                   # 没写环比：不参与
    c = bf.feed_days_mom_check(wk)
    assert c["comparable"] == 3 and c["matched"] == 2 and c["mismatched"] == 1, c
    assert c["examples"] == [{"d": "2026-06-26", "value": 7.24, "prevValue": 7.24, "computedChange": 0.0, "statedMom": 0.99}], c["examples"]
    assert bf.feed_days_mom_check([]) == {"comparable": 0, "matched": 0, "mismatched": 0, "examples": []}
    ok("环比独立校验：连续两周之差 vs 文章写的环比；隔周/没写环比的不参与；不符的列出")


def test_backfill_feed_days_from_real_sample_and_synthetic_weeks():
    """真实样本(07-03)+ 3个合成周(格式照真实样本写)：摘要提得出的走摘要，摘要没数的抓正文，抓不到的如实报告。"""
    items = [_feed_item("2026-07-03", "20260703", FEED_REAL_SUMMARY),
             _feed_item("2026-06-26", "20260626", "截至6月26日，全国饲料企业豆粕物理库存为7.24天，环比下降0.06天，同比增加0.31天。"),       # 合成：7.41-0.17=7.24 ✓
             _feed_item("2026-06-19", "20260619", "本期调查结果发布，详见正文。", url="https://ncp.mysteel.com/a/body19.html"),                                      # 合成：摘要没数字→抓正文
             _feed_item("2026-06-12", "20260612", "本期调查结果发布。", url="https://ncp.mysteel.com/a/fail12.html"),                                              # 合成：正文请求失败
             _feed_item("2026-06-05", "20260605", "截至6月5日，全国饲料企业豆粕物理库存为7.10天，环比微增0.20天。", title_extra=""),         # 合成
             {"title": "Mysteel：豆粕现货价格日评", "publishTime": "2026-06-04 10:00", "url": "https://ncp.mysteel.com/a/other.html", "content": "价格上涨"}]     # 不是这个指标
    bodies = {"https://ncp.mysteel.com/a/body19.html": "<h1>Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（20260619）</h1><p>截至6月19日，全国饲料企业豆粕物理库存为7.30天，环比增加0.20天，同比下滑0.10天。</p>免责声明：xx"}
    fetched = []
    def fake_text(url, headers=None, retries=2, timeout=20):
        fetched.append(url)
        return (bodies[url], {}) if url in bodies else (None, {"error": "HTTP 403"})
    with Tmp() as d, Patch(fetch_json_debug=lambda *a, **k: ({"resultCode": 0, "total": len(items), "dataList": items}, {}), fetch_text_debug=fake_text):
        rep = bf.backfill_feed_days(base_dir=d, today=date(2026, 7, 10))
        pts = {p["d"]: p for p in hs.load_series("feed_days", d)["points"]}
        assert sorted(pts) == ["2026-06-05", "2026-06-19", "2026-06-26", "2026-07-03"], sorted(pts)
        assert pts["2026-07-03"]["v"] == 7.41 and pts["2026-07-03"]["x"] == {"mom": 0.17, "yoy": -0.5}, "真实样本：7.41天/环比+0.17/同比-0.50"
        assert pts["2026-06-26"]["x"] == {"mom": -0.06, "yoy": 0.31}, "'环比下降0.06天'→-0.06，'同比增加0.31天'→+0.31"
        assert pts["2026-06-19"]["v"] == 7.30 and pts["2026-06-19"]["x"]["mom"] == 0.2, "摘要没数字→抓正文取到"
        assert pts["2026-06-05"]["x"] == {"mom": 0.2}, "只写了环比、没写同比：同比不存(不猜)"
        assert "https://ncp.mysteel.com/a/other.html" not in fetched, "标题不含'饲料企业豆粕库存天数'的不处理"
        st = rep["extractStats"]
        assert st["提取成功(来自摘要)"] == 3 and st["提取成功(来自正文)"] == 1 and st["正文请求失败"] == 1, st
        assert rep["failedSamples(前8篇)"][0]["reason"].startswith("正文请求失败") and rep["failedSamples(前8篇)"][0]["pub"] == "2026-06-12"
        mc = rep["momIndependentCheck(连续两周库存之差 vs 文章写的环比)"]
        # 6/5→6/12缺一周，6/12→6/19中间断；可比的：6/19→6/26(7.30→7.24=-0.06 ✓)、6/26→7/3(7.24→7.41=+0.17 ✓)
        assert mc["comparable"] == 2 and mc["matched"] == 2 and mc["mismatched"] == 0, mc
        assert rep["knownSampleCheck"][0]["result"] == "通过", rep["knownSampleCheck"]
        assert rep["total"] == 4 and rep["first"] == "2026-06-05" and rep["last"] == "2026-07-03"
    ok("回填饲料库存天数：真实样本+合成周，摘要/正文两级提取，环比方向符号，失败如实报告，环比独立校验通过")


def test_backfill_feed_days_detects_wrong_parse_via_mom_check():
    """如果解析把别的数当成了库存天数(这里模拟：某一周被取成了另一个数)，环比独立校验能发现。"""
    items = [_feed_item("2026-06-26", "20260626", "截至6月26日，全国饲料企业豆粕物理库存为9.99天，环比下降0.06天。"),      # 库存应为7.24，模拟取错
             _feed_item("2026-06-19", "20260619", "截至6月19日，全国饲料企业豆粕物理库存为7.30天，环比增加0.20天。"),
             _feed_item("2026-07-03", "20260703", FEED_REAL_SUMMARY)]
    with Tmp() as d, Patch(fetch_json_debug=lambda *a, **k: ({"resultCode": 0, "total": 3, "dataList": items}, {}), fetch_text_debug=lambda *a, **k: (None, {})):
        rep = bf.backfill_feed_days(base_dir=d, today=date(2026, 7, 10), fetch_bodies=False)
        mc = rep["momIndependentCheck(连续两周库存之差 vs 文章写的环比)"]
        assert mc["mismatched"] == 2 and mc["examples"][0]["d"] == "2026-06-26" and mc["examples"][0]["computedChange"] == 2.69, mc
    ok("环比独立校验能发现取错数(库存被取成9.99：与前后两周的差都对不上)")


def test_backfill_feed_days_failure_modes():
    with Tmp() as d, Patch(fetch_json_debug=lambda *a, **k: ({"resultCode": 0, "total": 1, "dataList": [{"title": "Mysteel：某无关文章", "publishTime": "2026-06-04 10:00", "content": "x"}]}, {})):
        r = bf.backfill_feed_days(base_dir=d, today=date(2026, 7, 10))
        assert "没有搜到" in r["error"] and r["skippedTitles"] == ["Mysteel：某无关文章"]
    items = [_feed_item("2026-07-03", "20260703", "本期调查发布。", url="https://ncp.mysteel.com/a/a.html"), _feed_item("2026-06-26", "20260626", "本期调查发布。", url="https://ncp.mysteel.com/a/b.html")]
    with Tmp() as d, Patch(fetch_json_debug=lambda *a, **k: ({"resultCode": 0, "total": 2, "dataList": items}, {}), fetch_text_debug=lambda url, **k: ("<html>免责声明</html>", {})):
        r = bf.backfill_feed_days(base_dir=d, today=date(2026, 7, 10))
        assert r["total"] == 0 or r.get("added") == 0
        assert r["extractStats"]["摘要和正文都没提取出库存天数"] == 2 and len(r["failedSamples(前8篇)"]) == 2 and r["failedSamples(前8篇)"][0]["reason"].startswith("提取不出")
    ok("回填饲料库存天数：没搜到/全部提取不出时如实报告(带原文片段)，不报错")


def test_feed_days_main_flow_registered_and_calibration():
    assert "feed_days" in bf.JOBS and "feed_days" in bf.DEFAULT_JOBS
    with Tmp() as d:
        hs.record_points("feed_days", [{"d": f"2026-0{m}-0{dd}", "v": 7.0 + m * 0.1, "x": {"mom": 0.1}} for m, dd in [(1, 5), (2, 6), (3, 6)]], d)
        c = bf.calibration_summary(d)["feed_days"]
        assert c["n"] == 3 and "不足180天" in c["coverage"] and c["medianByMonth"] == {"01": 7.1, "02": 7.2, "03": 7.3}
    ok("饲料库存天数：进默认回填项，校准摘要含分位数/按月中位/覆盖情况/环比校验")


def test_backfill_main_report_and_job_isolation():
    with Tmp() as d:
        real = dict(bf.JOBS)
        bf.JOBS["us_stu"] = lambda **kw: (_ for _ in ()).throw(RuntimeError("接口挂了"))
        bf.JOBS["esr"] = lambda **kw: {"key": "esr_net_sales", "total": 3}
        try:
            rep = bf.main(["--only", "us_stu,esr,bogus"], base_dir=d)
        finally:
            bf.JOBS.clear(); bf.JOBS.update(real)
        by = {e["key"]: e for e in rep["series"]}
        assert "RuntimeError" in by["us_stu"]["error"] and by["esr_net_sales"]["total"] == 3 and by["bogus"]["error"] == "未知的回填项"
        saved = json.load(open(os.path.join(d, "_backfill_report.json"), encoding="utf-8"))
        assert len(saved["series"]) == 3 and "generatedAt" in saved
    ok("回填入口：一项失败不影响其它项，报告写入_backfill_report.json")


def test_missing_months_and_weekly_gaps_helpers():
    assert bf._missing_months(["2025-11", "2025-12", "2026-02", "2026-05"]) == ["2026-01", "2026-03", "2026-04"]
    assert bf._weekly_gaps(["2026-01-01", "2026-01-08", "2026-02-05"]) == ["2026-01-08→2026-02-05"]
    ok("回填报告：缺失月份/周度断档的检测")


def test_fetch_data_main_attaches_history_next_to_output(monkeypatch=None):
    """main()把历史目录放在OUTPUT_PATH旁边(测试改输出路径时不会污染仓库)。"""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_data.py"), encoding="utf-8").read()
    assert 'os.path.join(os.path.dirname(OUTPUT_PATH), "history")' in src
    ok("main()：历史目录跟随OUTPUT_PATH")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    only = sys.argv[1:]
    fails = []
    for t in TESTS:
        if only and not any(o in t.__name__ for o in only):
            continue
        try:
            t()
        except Exception:
            fails.append(t.__name__)
            print("❌", t.__name__)
            traceback.print_exc()
    print(f"\n结果：{_pass}项通过，{len(fails)}项失败" + (f"：{fails}" if fails else ""))
    sys.exit(1 if fails else 0)
