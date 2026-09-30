# -*- coding: utf-8 -*-
"""月差/期限结构(近月-远月，占近月价格%)的后端测试。独立成文件。运行：python3 test_term_spread.py"""
import os, sys, tempfile, shutil, traceback
from datetime import date, datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd
import history_store as hs
import backfill_history as bf

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="spread_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


UTC = timezone.utc


def _bars(pairs):
    return [{"date": d, "close": c} for d, c in pairs]


def test_symbols_follow_dce_standard_spreads():
    """9月合约=9-1(对次年1月)、5月合约=5-9、1月合约=1-5；近月复用get_current_contract_code，合约到期后自动滚动到下一年。"""
    f = fd.term_spread_symbols
    assert f(9, datetime(2026, 7, 12, tzinfo=UTC)) == ("M2609", "M2701")
    assert f(5, datetime(2026, 7, 12, tzinfo=UTC)) == ("M2705", "M2709"), "7月已过5月，看下一年的5月合约"
    assert f(1, datetime(2026, 7, 12, tzinfo=UTC)) == ("M2701", "M2705")
    assert f(9, datetime(2026, 12, 10, tzinfo=UTC)) == ("M2709", "M2801"), "12月已过9月：滚动到2027年9月合约，远月=2028年1月(跨年)"
    assert f(5, datetime(2026, 3, 1, tzinfo=UTC)) == ("M2605", "M2609")
    ok("月差合约代码：9-1(跨年)、5-9、1-5，随日期自动滚动")


def test_series_uses_percentage_of_near_price_and_only_common_dates():
    near = _bars([("2026-05-04", 3000.0), ("2026-05-05", 3100.0), ("2026-05-06", 3200.0)])
    far = _bars([("2026-05-04", 2900.0), ("2026-05-05", 3200.0)])               # 缺5/6
    s = fd.term_spread_series(near, far)
    assert sorted(s) == ["2026-05-04", "2026-05-05"], "只算两个合约都有收盘价的日期"
    assert s["2026-05-04"] == round((3000 - 2900) / 3000 * 100, 2) == 3.33, "手算：(3000-2900)/3000=3.33%，正=近强远弱"
    assert s["2026-05-05"] == round((3100 - 3200) / 3100 * 100, 2) == -3.23, "远月升水(contango)为负"
    assert fd.term_spread_series(near, [{"date": "2026-05-04", "close": None}]) == {}
    assert fd.term_spread_series([{"date": "2026-05-04", "close": 0}], far) == {}, "近月价格为0：不算(避免除零)"
    ok("月差逐日序列：占近月价格的百分比(手算3.33%/-3.23%)，只算共同日期，近月为0不算")


def test_percentage_makes_different_price_levels_comparable():
    """为什么用百分比：2018年价格约3000，2026年约3000~4000，同样的'近强远弱100元'含义不同。"""
    low = fd.term_spread_series(_bars([("2020-05-04", 2500.0)]), _bars([("2020-05-04", 2400.0)]))["2020-05-04"]
    high = fd.term_spread_series(_bars([("2026-05-04", 4000.0)]), _bars([("2026-05-04", 3900.0)]))["2026-05-04"]
    assert low == 4.0 and high == 2.5 and low > high, "同样是100元价差，价格水平低的年份占比更高——绝对价差没法跨年比"
    ok("用百分比：同样100元价差，2500的年份占4.0%、4000的年份占2.5%")


def test_fetch_term_spread_result_and_failures():
    old = fd.fetch_dce_daily_kline
    try:
        table = {"M2609": ("2026-07-10", 3000.0), "M2701": ("2026-07-10", 3100.0)}
        def fake(symbol, max_rows=260):
            if symbol not in table:
                return {"available": False, "reason": "测试里没配置这个合约"}
            d, c = table[symbol]
            return {"available": True, "symbol": symbol, "bars": [{"date": d, "close": c}], "source": "测试"}
        fd.fetch_dce_daily_kline = fake
        r = fd.fetch_term_spread(9, datetime(2026, 7, 12, tzinfo=UTC))
        assert r["available"] and r["nearSymbol"] == "M2609" and r["farSymbol"] == "M2701"
        assert r["spread"] == -100.0 and r["spreadPct"] == -3.33 and r["date"] == "2026-07-10" and r["datesAligned"] is True, "远月比近月高100：contango，-3.33%"
        table["M2701"] = ("2026-07-09", 3100.0)
        r2 = fd.fetch_term_spread(9, datetime(2026, 7, 12, tzinfo=UTC))
        assert r2["date"] == "2026-07-09" and r2["datesAligned"] is False, "两个合约最新日期不一致：以最旧的为准并标注"
        del table["M2701"]
        r3 = fd.fetch_term_spread(9, datetime(2026, 7, 12, tzinfo=UTC))
        assert r3["available"] is False and "远月M2701" in r3["reason"], "缺一个合约整体不可用，点名缺的是哪个"
        table.clear()
        r4 = fd.fetch_term_spread(9, datetime(2026, 7, 12, tzinfo=UTC))
        assert "近月M2609" in r4["reason"] and "远月M2701" in r4["reason"], "两个都缺：都点名"
        table.update({"M2609": ("2026-07-10", 0.0), "M2701": ("2026-07-10", 3100.0)})
        assert fd.fetch_term_spread(9, datetime(2026, 7, 12, tzinfo=UTC))["available"] is False, "近月收盘价为0：不可用"
    finally:
        fd.fetch_dce_daily_kline = old
    ok("月差抓取：符号/百分比/日期(不一致取最旧)；缺一个合约或近月为0都不可用并点名")


def test_history_accumulates_daily_with_seasonal_percentile():
    with Tmp() as d:
        # 往年同月(7月)：8年×20个交易日=160个点，值0.0~15.9(%)
        pts = [{"d": f"{2018 + y}-07-{i + 1:02d}", "v": round(y * 2 + i * 0.1, 2)} for y in range(8) for i in range(20)]
        hs.record_points("term_spread_sep", pts, d)
        r = {"termSpreads": {"sep": {"available": True, "date": "2026-07-10", "nearSymbol": "M2609", "farSymbol": "M2701", "spread": 90.0, "spreadPct": 8.0},
                             "may": {"available": False, "reason": "x"}, "jan": {"available": True, "date": None, "spreadPct": 1.0}}}
        touched = hs.update_and_attach(r, base_dir=d)
        assert "term_spread_sep" in touched and "term_spread_may" not in touched and "term_spread_jan" not in touched
        h = r["termSpreads"]["sep"]["history"]
        vals = [p["v"] for p in pts]
        assert h["seasonal"]["month"] == 7 and h["seasonal"]["n"] == 160 and h["seasonal"]["percentile"] == hs.percentile_rank(8.0, vals)
        assert h["sparse"] is None, "seasonal-daily不做样本密度检查"
        pt = [p for p in hs.load_series("term_spread_sep", d)["points"] if p["d"] == "2026-07-10"][0]
        assert pt["v"] == 8.0 and pt["x"] == {"near": "M2609", "far": "M2701", "spread": 90.0}
        assert "history" not in r["termSpreads"]["may"] and "history" not in r["termSpreads"]["jan"], "不可用/没有日期的不记录"
        assert hs.update_and_attach(r, base_dir=d) == [], "重复运行无变化"
    ok("月差累积：逐日追加、往年同月分位、不可用/无日期不记录、重复运行无变化")


def test_backfill_term_spread_windows_pairs_and_failures():
    def series(d0, n, price):
        return [{"date": (d0 + timedelta(days=i)).isoformat(), "close": price} for i in range(n)]
    table = {"M2509": series(date(2025, 3, 20), 200, 3000.0), "M2601": series(date(2025, 3, 20), 400, 3090.0),          # 2025年9月合约=M2509对M2601
             "M2609": series(date(2026, 3, 20), 40, 3000.0), "M2701": series(date(2026, 3, 20), 40, 3090.0)}
    fetched = []
    def fake(symbol, max_rows=260):
        fetched.append((symbol, max_rows))
        return {"available": True, "symbol": symbol, "bars": table[symbol]} if symbol in table else {"available": False, "reason": "已到期，接口返回空数据"}
    old_sleep, old_k = bf.time.sleep, fd.fetch_dce_daily_kline
    bf.time.sleep = lambda s: None
    fd.fetch_dce_daily_kline = fake
    try:
        with Tmp() as d:
            rep = bf.backfill_term_spread(base_dir=d, from_year=2025, to_year=2026)
            sep = hs.load_series("term_spread_sep", d)["points"]
            ds = [p["d"] for p in sep]
            assert len(sep) == 122 + 28 and min(ds) == "2025-04-01" and max(ds) == "2026-04-28", (len(sep), min(ds), max(ds))
            assert all(int(x[5:7]) in (4, 5, 6, 7) for x in ds), "只存建议交易窗口(4-7月)内的点"
            assert all(p["v"] == round((3000 - 3090) / 3000 * 100, 2) == -3.0 for p in sep), "手算：(3000-3090)/3000=-3.00%"
            assert {p["x"]["near"] for p in sep} == {"M2509", "M2609"} and {p["x"]["far"] for p in sep} == {"M2601", "M2701"}, "9月合约：近月M25/26 09，远月次年01(跨年)"
            failed = [c for c in rep["pairs"] if c["failed"]]
            assert {(c["type"], c["near"]) for c in failed} == {("may", "M2505"), ("may", "M2605"), ("jan", "M2501"), ("jan", "M2601")}, "5月/1月的桩数据没配"
            # 桩数据里M2509/M2601/M2609/M2701存在，所以有的对只缺一个代码：只列出真正取不到的那个，不多列
            got = {(c["type"], c["near"]): [x.split("(")[0] for x in c["failed"]] for c in failed}
            assert got == {("may", "M2505"): ["M2505"], ("may", "M2605"): ["M2605"], ("jan", "M2501"): ["M2501", "M2505"], ("jan", "M2601"): ["M2605"]}, got
            assert all("已到期" in x for c in failed for x in c["failed"]), "每个取不到的代码都带原因"
            assert "取不到" in rep["notes"][0]
            assert all(m >= 6000 for _, m in fetched), "取全部历史(max_rows很大)"
            assert {e["key"] for e in rep["series"]} == {"term_spread_sep", "term_spread_may", "term_spread_jan"}
    finally:
        bf.time.sleep, fd.fetch_dce_daily_kline = old_sleep, old_k
    ok("回填月差：窗口内逐日、9月合约跨年对(M2509/M2601)、取不到的合约对(近月+远月)如实列出")


def test_backfill_far_month_mapping_matches_fetch():
    """回填和实时抓取的近远月推导必须一致，否则历史和当前不可比。"""
    for cm, far in ((9, (1, 1)), (5, (9, 0)), (1, (5, 0))):
        assert fd.TERM_SPREAD_FAR[cm] == far
    now = datetime(2026, 7, 12, tzinfo=UTC)
    for cm in (9, 5, 1):
        near, farsym = fd.term_spread_symbols(cm, now)
        fm, ya = fd.TERM_SPREAD_FAR[cm]
        assert farsym == f"M{(int(near[1:3]) + ya) % 100:02d}{fm:02d}"
    ok("回填与实时抓取用同一张近远月映射表")


def test_calibration_summary_includes_term_spread():
    with Tmp() as d:
        hs.record_points("term_spread_sep", [{"d": f"2025-0{m}-01", "v": v} for m, v in [(4, -4.0), (5, -1.0), (6, 2.0), (7, 5.0)]], d)
        c = bf.calibration_summary(d)["term_spread_sep"]
        assert c["n"] == 4 and c["share<0(远月升水)"] == 50.0
        assert c["medianByMonth(%)"] == {"04": -4.0, "05": -1.0, "06": 2.0, "07": 5.0} and c["pointsPerYear"] == {"2025": 4}
    ok("校准摘要：月差的分位数、按月中位、远月升水占比")


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
