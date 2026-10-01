# -*- coding: utf-8 -*-
"""v95.2：①每日累积只记"建议交易窗口内"的点(榨利/月差)；一次性清理窗口外旧点；②依赖锁定文件与工作流。运行：python3 test_window_and_deps.py"""
import os, sys, tempfile, shutil, traceback, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_store as hs
import backfill_history as bf

_pass = 0
ROOT = os.path.dirname(os.path.abspath(__file__))


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="win_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def pts(d, key):
    return hs.load_series(key, d)["points"]


# ===================== 窗口判断 =====================
def test_window_ok_matches_the_recommended_trading_windows():
    w = hs.window_ok
    assert [w(f"2026-{m:02d}-15", "sep", 2026) for m in range(1, 13)] == [False] * 3 + [True] * 4 + [False] * 5, "9月合约(2026到期)：4-7月"
    assert w("2025-12-10", "may", 2026) and w("2026-01-10", "may", 2026) and w("2026-03-31", "may", 2026) and not w("2026-04-01", "may", 2026) and not w("2026-12-10", "may", 2026), "5月合约：前一年12月+当年1-3月"
    assert all(w(f"2026-{m:02d}-15", "jan", 2027) for m in (8, 9, 10, 11)) and not w("2026-12-15", "jan", 2027) and not w("2027-09-15", "jan", 2027), "1月合约(2027到期)：2026年8-11月"
    ok("窗口判断：9月合约4-7月、5月合约12-3月(12月在前一年)、1月合约8-11月(在前一年)")


def test_expiry_year_parsing_handles_both_code_formats():
    f = hs.expiry_year_of
    assert f("M2609") == 2026 and f("2609") == 2026 and f("M2701") == 2027 and f("Y2509") == 2025, "每日累积用M2609，回填用2509，都要认"
    assert f(None) is None and f("") is None and f("abc") is None and f("M26") is None
    ok("到期年份解析：M2609/2609/M2701(两种格式都认)；None/空/畸形返回None")


def test_in_trading_window_is_conservative_when_code_unknown():
    assert hs.in_trading_window("2026-06-10", "sep", "M2609") is True
    assert hs.in_trading_window("2026-09-30", "sep", "M2709") is False, "滚动到2027年9月合约后，9月30日不在窗口"
    assert hs.in_trading_window("2026-06-10", "sep", None) is False and hs.in_trading_window("2026-06-10", "sep", "乱码") is False, "合约代码解析不了：宁可不记"
    ok("合约代码解析不了时不记录(宁可不记，也不把来源不明的点混进去)")


# ===================== 每日累积只记窗口内(用报告里的真实点) =====================
def _res_margin(date, symbol, gm):
    return {"available": True, "contractMonth": 9, "date": date, "mealSymbol": symbol, "grossMargin": gm}


def test_daily_accumulation_records_only_in_window_points_margin():
    """★真实场景(用户报告)：9月30日，9月合约(滚动到M2709)和5月合约(M2705)都在窗口外；1月合约(M2701)在8-11月窗口内。"""
    with Tmp() as d:
        r = {"crushMargins": {"sep": _res_margin("2026-09-30", "M2709", 152.8), "may": _res_margin("2026-09-30", "M2705", 166.7), "jan": _res_margin("2026-09-30", "M2701", 177.8)}}
        touched = hs.update_and_attach(r, base_dir=d)
        assert pts(d, "crush_margin_sep") == [] and pts(d, "crush_margin_may") == [], "窗口外的不记录"
        assert [p["d"] for p in pts(d, "crush_margin_jan")] == ["2026-09-30"] and "crush_margin_jan" in touched and "crush_margin_sep" not in touched
        assert "history" in r["crushMargins"]["sep"] and "history" in r["crushMargins"]["may"], "窗口外仍然附带历史摘要(卡片要显示'积累中'，不能没有)"
        assert r["crushMargins"]["sep"]["history"]["n"] == 0
    ok("★每日累积：9月30日sep(M2709)、may(M2705)在窗口外不记录，jan(M2701)在窗口内记录；窗口外仍附历史摘要")


def test_daily_accumulation_window_edges_margin():
    with Tmp() as d:
        for day, sym, want in (("2026-04-01", "M2609", 1), ("2026-07-31", "M2609", 1), ("2026-03-31", "M2609", 0), ("2026-08-01", "M2609", 0)):
            with Tmp() as d2:
                hs.update_and_attach({"crushMargins": {"sep": _res_margin(day, sym, 100.0)}}, base_dir=d2)
                assert len(pts(d2, "crush_margin_sep")) == want, (day, want)
    ok("窗口边界：9月合约4月1日/7月31日记录，3月31日/8月1日不记录")


def test_daily_accumulation_records_only_in_window_points_term_spread():
    def sp(date, near, far, pct):
        return {"available": True, "contractMonth": 9, "date": date, "nearSymbol": near, "farSymbol": far, "spread": 10.0, "spreadPct": pct}
    with Tmp() as d:
        r = {"termSpreads": {"sep": sp("2026-09-14", "M2609", "M2701", -1.6), "may": sp("2026-09-30", "M2705", "M2709", -3.08), "jan": sp("2026-09-30", "M2701", "M2705", 11.45)}}
        hs.update_and_attach(r, base_dir=d)
        assert pts(d, "term_spread_sep") == [] and pts(d, "term_spread_may") == [], "9月14日(sep窗口外)、9月30日(may窗口外)不记录"
        assert [p["v"] for p in pts(d, "term_spread_jan")] == [11.45], "jan在窗口内"
        assert all("history" in r["termSpreads"][k] for k in ("sep", "may", "jan"))
    ok("★月差同样只记窗口内(报告里的真实点：sep 9/14、may 9/30被拒，jan 9/30保留)")


# ===================== 一次性清理 =====================
def test_prune_removes_only_out_of_window_points():
    with Tmp() as d:
        hs.record_points("crush_margin_sep", [{"d": "2026-09-14", "v": 397.4, "x": {"contract": "M2609"}}, {"d": "2026-09-30", "v": 152.8, "x": {"contract": "M2709"}},
                                              {"d": "2026-06-10", "v": 210.0, "x": {"contract": "M2609"}}, {"d": "2025-06-10", "v": 180.0, "x": {"contract": "2509"}},
                                              {"d": "2024-06-10", "v": 150.0}], d)
        n = hs.prune_out_of_window("crush_margin_sep", "sep", d, "contract")
        assert n == 2 and [p["d"] for p in pts(d, "crush_margin_sep")] == ["2024-06-10", "2025-06-10", "2026-06-10"]
        assert hs.prune_out_of_window("crush_margin_sep", "sep", d, "contract") == 0, "再清理一次：没有可删的(幂等)"
    ok("清理：删掉窗口外的2点；窗口内的保留；没有合约代码的点保留(不确定的不删)；幂等")


def test_prune_handles_empty_and_missing_series():
    with Tmp() as d:
        assert hs.prune_out_of_window("crush_margin_sep", "sep", d, "contract") == 0
        hs.record_points("term_spread_may", [{"d": "2026-09-30", "v": -3.08, "x": {"near": "M2705", "far": "M2709"}}], d)
        assert hs.prune_out_of_window("term_spread_may", "may", d, "near") == 1 and pts(d, "term_spread_may") == []
    ok("清理：序列不存在/为空不报错；月差用near字段")


def test_backfill_jobs_prune_before_recording_and_report_it():
    def series(from_date, n, price):
        from datetime import date, timedelta
        d0 = date.fromisoformat(from_date)
        return [{"date": (d0 + timedelta(days=i)).isoformat(), "close": price} for i in range(n)]
    import fetch_data as fd
    table = {s: series("2026-03-20", 40, p) for s, p in (("M2609", 3400.0), ("Y2609", 8500.0), ("B2609", 4200.0), ("M2701", 3500.0))}
    old_k, old_sleep = fd.fetch_dce_daily_kline, bf.time.sleep
    fd.fetch_dce_daily_kline = lambda symbol, max_rows=260: {"available": True, "symbol": symbol, "bars": table[symbol]} if symbol in table else {"available": False, "reason": "测试没配置"}
    bf.time.sleep = lambda s: None
    try:
        with Tmp() as d:
            hs.record_points("crush_margin_sep", [{"d": "2026-09-14", "v": 397.4, "x": {"contract": "M2609"}}, {"d": "2026-06-10", "v": 210.0, "x": {"contract": "M2609"}}], d)
            hs.record_points("term_spread_sep", [{"d": "2026-09-14", "v": -1.6, "x": {"near": "M2609", "far": "M2701"}}], d)
            rep = bf.backfill_crush_margin(base_dir=d, from_year=2026, to_year=2026)
            assert rep["prunedOutOfWindow"] == {"sep": 1, "may": 0, "jan": 0} and "清理了窗口外的旧点" in rep["notes"][1]
            assert "2026-09-14" not in [p["d"] for p in pts(d, "crush_margin_sep")] and "2026-06-10" in [p["d"] for p in pts(d, "crush_margin_sep")]
            rep2 = bf.backfill_term_spread(base_dir=d, from_year=2026, to_year=2026)
            assert rep2["prunedOutOfWindow"] == {"sep": 1, "may": 0, "jan": 0}, rep2["prunedOutOfWindow"]
            # M2609/M2701两个合约都配了桩数据：2026年9月合约(M2609对M2701)窗口(4-7月)内应有点，窗口外的9月14日已被清掉
            ds = [p["d"] for p in pts(d, "term_spread_sep")]
            assert ds and all(x[5:7] in ("04", "05", "06", "07") for x in ds), ds
            assert "2026-09-14" not in [p["d"] for p in pts(d, "term_spread_sep")]
    finally:
        fd.fetch_dce_daily_kline, bf.time.sleep = old_k, old_sleep
    ok("★两个回填任务都先清理窗口外旧点再写入，并在报告里写明清理了几个")


# ===================== 依赖锁定 =====================
def _pins(fn):
    lines = [l.strip() for l in open(os.path.join(ROOT, fn), encoding="utf-8").read().split("\n") if l.strip() and not l.startswith("#")]
    return lines


def test_lock_files_pin_every_package_exactly():
    for fn in ("requirements-akshare.lock.txt", "requirements-agrobr.lock.txt"):
        pins = _pins(fn)
        assert len(pins) >= 20 and all(re.match(r"^[A-Za-z0-9_.\-]+==[0-9][A-Za-z0-9_.+!\-]*$", l) for l in pins), [l for l in pins if "==" not in l]
        names = [l.split("==")[0].lower().replace("_", "-") for l in pins]
        assert len(names) == len(set(names)), "同一个包不能出现两次"
    a, g = {l.split("==")[0]: l.split("==")[1] for l in _pins("requirements-akshare.lock.txt")}, {l.split("==")[0]: l.split("==")[1] for l in _pins("requirements-agrobr.lock.txt")}
    assert a["akshare"] == "1.19.1" and a["pandas"] == "3.0.6" and a["numpy"] == "2.4.6" and g["agrobr"] == "1.1.0", "与2026-10-01 Actions实际装成功的版本一致"
    assert not ({k.lower().replace("_", "-") for k in a} & {k.lower().replace("_", "-") for k in g}), "两个文件之间不重叠(各对应一个安装步骤)"
    ok("两个锁定文件：全部精确版本(==)，无重复；akshare 1.19.1/pandas 3.0.6/numpy 2.4.6/agrobr 1.1.0")


def test_workflows_use_lock_files_and_backfill_installs_akshare():
    import yaml
    bfw = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "backfill-history.yml"), encoding="utf-8"))
    steps = bfw["jobs"]["backfill"]["steps"]
    runs = [(i, s.get("run") or "") for i, s in enumerate(steps)]
    i_pip = next(i for i, r in runs if "pip install" in r)
    i_run = next(i for i, r in runs if "backfill_history.py" in r)
    assert i_pip < i_run and "requirements-akshare.lock.txt" in steps[i_pip]["run"], "★回填工作流必须先装akshare再跑回填(之前没装，榨利/月差回填全部失败)"
    uw = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "update-data.yml"), encoding="utf-8"))
    pips = [s["run"] for s in uw["jobs"]["fetch-and-commit"]["steps"] if "pip install" in (s.get("run") or "")]
    assert any("requirements-akshare.lock.txt" in p for p in pips) and any("requirements-agrobr.lock.txt" in p for p in pips)
    assert not any(re.search(r"pip install\s+(akshare|agrobr|pandas)\b", p) for p in pips + [r for _, r in runs]), "不能再有不锁版本的 pip install akshare/agrobr/pandas"
    ok("★回填工作流先装akshare(锁定版本)再回填；更新工作流两个安装步骤都用锁定文件；不再有不锁版本的pip install")


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
