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


def test_backfill_meal_stock_weekly():
    def art(pub, text, title="Mysteel：2026年第38周全国主要区域大豆及豆粕库存统计"):
        return {"title": title, "publishTime": pub + " 09:00", "content": text}
    items = [art("2026-09-21", "2026年第38周全国主要油厂大豆库存上升，豆粕库存上升，其中大豆库存856.85万吨，豆粕库存117.32万吨，较上周增加6.33万吨"),
             art("2026-09-14", "全国主要油厂豆粕库存111万吨，较上周增加", title="Mysteel：2026年第37周全国主要区域大豆及豆粕库存统计"),
             art("2026-09-07", "华东豆粕库存45万吨", title="Mysteel：华东豆粕库存"),         # 区域数据，拒绝
             art("2026-08-31", "本周豆粕库存上升0.7万吨")]                                       # 变动量，拒绝
    with Tmp() as d, Patch(fetch_json_debug=lambda *a, **k: ({"resultCode": 0, "total": 4, "dataList": items}, {})):
        rep = bf.backfill_meal_stock(base_dir=d, today=date(2026, 9, 29))
        pts = {p["d"]: p["v"] for p in hs.load_series("meal_stock", d)["points"]}
        assert pts == {"2026-09-21": 117.32, "2026-09-14": 111.0}, pts
        assert rep["total"] == 2 and rep["extractStats"]["提取成功(来自摘要)"] == 2, rep["extractStats"]
    ok("回填豆粕周度库存：按现有规则拒绝区域数据/变动量，全国库存逐周落盘")


def test_backfill_meal_stock_fetches_bodies_when_summary_has_no_numbers():
    """★上一版的问题：搜索到750篇只提取出12个点。摘要多半没有数字，数字在正文里。
    (下面是合成样本，格式参照9月21日那篇真实摘要；正文里写的是Mysteel周报的常见句式。)"""
    def art(pub, week, summary, url):
        return {"title": f"Mysteel：{week}全国主要区域大豆及豆粕库存统计", "publishTime": pub + " 09:00", "content": summary, "url": url}
    items = [art("2026-08-31", "2026年第35周", "全国主要油厂大豆库存下降，豆粕库存上升，未执行合同减少。", "https://x/35"),
             art("2026-05-29", "2026年第22周", "全国主要油厂大豆库存上升，豆粕库存上升。", "https://x/22"),
             art("2026-05-30", "2026年第22周", "更正版：全国主要油厂大豆库存上升。", "https://x/22b"),     # 同一周的更晚一篇，应取代
             art("2026-06-08", "2026年第23周", "本周库存数据发布。", "https://x/23"),                       # 正文请求会失败
             {"title": "Mysteel：豆粕现货价格日评", "publishTime": "2026-06-09 09:00", "content": "价格上涨", "url": "https://x/other"},   # 不像周度库存文章
             {"title": "Mysteel：华东豆粕库存", "publishTime": "2026-06-10 09:00", "content": "华东豆粕库存45万吨", "url": "https://x/east"}]
    bodies = {"https://x/35": "<h1>Mysteel：2026年第35周全国主要区域大豆及豆粕库存统计</h1><p>2026年第35周，全国主要油厂大豆库存827.97万吨，较上周减少11.13万吨，豆粕库存116.73万吨，较上周增加5.75万吨。</p>免责声明：xx",
              "https://x/22": "<h1>Mysteel：2026年第22周全国主要区域大豆及豆粕库存统计</h1><p>全国主要油厂大豆库存662.88万吨，豆粕库存34.74万吨，较上周增加3.56万吨。</p>免责声明：xx",
              "https://x/22b": "<h1>Mysteel：2026年第22周全国主要区域大豆及豆粕库存统计</h1><p>更正：全国主要油厂豆粕库存34.80万吨，较上周增加3.62万吨。</p>免责声明：xx"}
    fetched = []
    def fake_text(url, headers=None, retries=2, timeout=20):
        fetched.append(url)
        return (bodies[url], {}) if url in bodies else (None, {"error": "HTTP 403"})
    with Tmp() as d, Patch(fetch_json_debug=lambda *a, **k: ({"resultCode": 0, "total": len(items), "dataList": items}, {}), fetch_text_debug=fake_text):
        rep = bf.backfill_meal_stock(base_dir=d, today=date(2026, 9, 29))
        pts = {p["d"]: p for p in hs.load_series("meal_stock", d)["points"]}
        assert pts["2026-08-31"]["v"] == 116.73 and pts["2026-08-31"]["x"] == {"week": "2026-W35"}, pts
        assert "2026-05-29" not in pts and pts["2026-05-30"]["v"] == 34.8, "同一周有两篇时取发布更晚的"
        assert "2026-06-08" not in pts and "2026-06-09" not in pts and "2026-06-10" not in pts
        assert "https://x/other" not in fetched, "不像周度库存文章(标题没有第N周/库存)不抓正文，省请求"
        assert "https://x/east" in fetched, "标题含'库存'+'豆粕'的按周度候选处理(会抓正文，抓不到/提取不出就如实归类，不会采用区域数据)"
        st = rep["extractStats"]
        assert st["提取成功(来自正文)"] == 3 and st["正文请求失败"] == 2 and any("不像周度库存文章" in k for k in st), st
        assert all(x["text"] == "HTTP 403" for x in rep["rejectedSamples(每类前5篇)"]["正文请求失败"])
        checks = {c["week"]: c for c in rep["spotChecks(独立来源Mysteel英文站周报)"]}
        assert checks["2026年第35周"]["result"] == "通过"
        assert checks["2026年第22周"]["got"] == 34.8 and checks["2026年第22周"]["result"] == "通过", "更正版34.80 vs 校验点34.74：差0.06，在0.1容差内"
    ok("回填周度库存：摘要没数字→抓正文；同一周取更晚；不像周报的不抓；失败/拒绝如实分类，带校验点核对")


def test_backfill_meal_stock_no_bodies_flag():
    items = [{"title": "Mysteel：2026年第35周全国主要区域大豆及豆粕库存统计", "publishTime": "2026-08-31 09:00", "content": "全国主要油厂豆粕库存上升。", "url": "https://x/35"}]
    calls = []
    with Tmp() as d, Patch(fetch_json_debug=lambda *a, **k: ({"resultCode": 0, "total": 1, "dataList": items}, {}), fetch_text_debug=lambda *a, **k: calls.append(1) or (None, {})):
        rep = bf.backfill_meal_stock(base_dir=d, today=date(2026, 9, 29), fetch_bodies=False)
        assert not calls, "fetch_bodies=False时一次正文都不能请求"
    ok("回填周度库存：fetch_bodies=False时不请求正文")


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
    old = [("Mysteel：全国10月豆粕供需平衡表", "2025-09-30 14:41", "https://x/old", "简析：2025年9月油厂维持高开机高压榨，豆粕物理库存处于饱和状态，整体消化进度偏慢。"),
           ("Mysteel：全国豆粕供需平衡表（2026年5月）", "2026-05-29 14:41", "https://x/may", MB_REAL_ARTICLES[3][3])]
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
        assert c["meal_stu"]["currentThresholds"] == {"tight<=10": 25.0, "loose>=14": 50.0}
        m = c["meal_stock"]
        assert m["currentThresholds"] == {"tight<50": 33.3, "loose>100": 66.7} and m["pointsPerYear"] == {"2026": 3}
        by = {x["week"]: x for x in m["spotChecks(独立来源Mysteel英文站周报)"]}
        assert by["2026年第22周"]["result"] == "通过" and by["2026年第22周"]["got"] == 34.74
        assert by["2026年第35周"]["result"] == "通过", "8月31日116.73与8月28日那期校验点相差3天、数值一致"
        assert by["2026年第5周"]["result"].startswith("缺失")
    ok("校准摘要：美豆库消比/出口信号触发比例/国内库消比/周度库存的当前阈值在历史里的位置、校验点核对")


def test_spot_checks_detect_wrong_and_missing_points():
    pts = [{"d": "2026-08-31", "v": 116.73}, {"d": "2026-05-29", "v": 856.85}]     # 5月那个取成了大豆库存
    by = {c["week"]: c for c in bf.meal_stock_spot_checks(pts)}
    assert by["2026年第35周"]["result"] == "通过" and by["2026年第22周"]["result"] == "不一致" and by["2026年第22周"]["got"] == 856.85
    assert by["2026年第5周"]["result"].startswith("缺失")
    ok("周度库存校验点：通过/不一致(取错指标)/缺失 都能识别")


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
