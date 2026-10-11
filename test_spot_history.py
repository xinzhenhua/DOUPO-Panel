# -*- coding: utf-8 -*-
"""现货/期货每日自动累积(v101.20)：upsert、缺口计算、带预算的回补、与基线CSV合并、近期趋势、并入 seasonal.json。运行：python3 test_spot_history.py
★期望值全部手算。"""
import os, sys, json, csv, tempfile, shutil, traceback, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spot_history as sh
import seasonal_stats as ss
import pandas as pd

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def row(d, spot, fut, k="m2701"):
    return {"date": d, "spot": spot, "dominant_contract": k, "futures": fut, "near_contract": "m2611", "near_contract_price": fut - 20}


def tmp():
    return tempfile.mkdtemp()


def test_upsert_is_idempotent_sorted_and_updates():
    d = tmp(); p = os.path.join(d, "a.csv")
    assert sh.upsert(p, [row("2026-10-09", 3402, 3389), row("2026-10-08", 3390, 3388)]) == (2, 0)
    assert sh.upsert(p, [row("2026-10-09", 3402, 3389)]) == (0, 0)
    assert sh.upsert(p, [row("2026-10-09", 3410, 3389), row("2026-10-12", 3420, 3395)]) == (1, 1)
    rows = sh.load_rows(p)
    assert list(rows) == ["2026-10-08", "2026-10-09", "2026-10-12"], list(rows)
    assert rows["2026-10-09"]["spot"] == 3410.0 and rows["2026-10-12"]["futures"] == 3395.0
    shutil.rmtree(d); ok("upsert：重复写同一天不新增(0,0)；改了价格算更新；新日期新增；文件按日期升序")


def test_load_rows_missing_file_and_bad_lines():
    d = tmp(); p = os.path.join(d, "none.csv")
    assert sh.load_rows(p) == {}
    open(p, "w", encoding="utf-8").write("date,spot,dominant_contract,futures,near_contract,near_contract_price\n2026-10-08,3390,m2701,3388,m2611,3368\n坏行,abc,,,,\n2026-10-09,,m2701,3389,,\n")
    r = sh.load_rows(p)
    assert list(r) == ["2026-10-08"], r
    shutil.rmtree(d); ok("文件不存在返回空；坏行/缺现货价的行跳过，不崩")


def test_missing_dates_newest_first_skips_existing_and_non_trading():
    trading = {"2026-09-28", "2026-09-29", "2026-09-30", "2026-10-09"}
    isT = lambda dt: dt.isoformat() in trading
    got = sh.missing_dates({"2026-09-30"}, "2026-09-28", "2026-10-09", isT)
    assert got == ["2026-10-09", "2026-09-29", "2026-09-28"], got
    assert sh.missing_dates(set(trading), "2026-09-28", "2026-10-09", isT) == []
    ok("缺口按从新到旧排；已有的和非交易日不算缺")


def _clock():
    t = [0.0]
    def c():
        t[0] += 1.0
        return t[0]
    return c


def test_backfill_budget_failures_and_consecutive_abort():
    d = tmp(); p = os.path.join(d, "a.csv")
    days = [f"2026-09-{n:02d}" for n in range(1, 11)]       # 10个都是交易日
    calls = []
    def get_row(ds):
        calls.append(ds)
        return (row(ds, 3000 + int(ds[-2:]), 3000), None)
    rep = sh.backfill(p, "2026-09-01", "2026-09-10", get_row, lambda dt: dt.isoformat() in days, budget_s=3.5, pause=0, clock=_clock(), sleep=lambda s: None)
    # clock 每次调用+1：t0=1；循环里每次检查 clock()-t0>3.5：第1次2-1=1,第2次3-1=2... 第4次检查 5-1=4>3.5 → 抓了3个就停
    assert len(rep["fetched"]) == 3 and rep["stoppedByBudget"] and rep["remaining"] == 7, rep
    assert calls == ["2026-09-10", "2026-09-09", "2026-09-08"], calls
    assert len(sh.load_rows(p)) == 3
    # 边界：已用时间恰好等于预算还可以抓(只有严格超过才停)：预算3.0 → 检查时已用 1、2、3 都抓，第4次已用4才停 → 抓3个
    p3 = os.path.join(d, "c.csv")
    rep3 = sh.backfill(p3, "2026-09-01", "2026-09-10", get_row, lambda dt: dt.isoformat() in days, budget_s=3.0, pause=0, clock=_clock(), sleep=lambda s: None)
    assert len(rep3["fetched"]) == 3, rep3
    # 连续失败3次中止，中间有一次成功会清零
    seq = {"2026-09-10": (None, "空"), "2026-09-09": (row("2026-09-09", 3000, 3000), None), "2026-09-08": (None, "空"), "2026-09-07": (None, "空"), "2026-09-06": (None, "空")}
    p2 = os.path.join(d, "b.csv")
    rep2 = sh.backfill(p2, "2026-09-01", "2026-09-10", lambda ds: seq[ds], lambda dt: dt.isoformat() in days, budget_s=1e9, pause=0, max_consecutive_fail=3, clock=_clock(), sleep=lambda s: None)
    assert rep2["abortedByFailures"] and set(rep2["failed"]) == {"2026-09-10", "2026-09-08", "2026-09-07", "2026-09-06"}, rep2
    assert list(sh.load_rows(p2)) == ["2026-09-09"], sh.load_rows(p2)
    shutil.rmtree(d); ok("回补：预算到了就停并报告剩余7天；连续3次失败(中间成功清零)就中止，说明站点在限流；失败的日子写明原因")


def test_get_row_adapter_parses_akshare_frame_and_reports_reasons():
    df = pd.DataFrame([{"symbol": "M", "spot_price": 3402.0, "dominant_contract": "m2701", "dominant_contract_price": 3389.0, "near_contract": "m2611", "near_contract_price": 3360.0, "dom_basis": -13.0}])
    g = sh.make_get_row(lambda ds: df, deadline_s=5)
    r, why = g("2026-10-09")
    assert why is None and r == {"date": "2026-10-09", "spot": 3402.0, "dominant_contract": "m2701", "futures": 3389.0, "near_contract": "m2611", "near_contract_price": 3360.0}, (r, why)
    r2, why2 = sh.make_get_row(lambda ds: pd.DataFrame(), deadline_s=5)("2026-10-10")
    assert r2 is None and "没有返回" in why2, why2
    def boom(ds): raise RuntimeError("限流")
    r3, why3 = sh.make_get_row(boom, deadline_s=5)("2026-10-10")
    assert r3 is None and "限流" in why3
    ok("适配器：把 akshare 表转成累积行(现货、主力合约、主力价、近月)；空表/异常都返回原因不崩")


def test_refresh_recent_contracts_only_overwrites_with_complete_data():
    import fetch_seasonal_raw as fs
    d = tmp(); cdir = os.path.join(d, "contracts"); os.makedirs(cdir)
    def wr(sym, n):
        with open(os.path.join(cdir, sym + ".csv"), "w", encoding="utf-8", newline="") as f:
            f.write("date,open,high,low,close,volume,hold\n")
            for i in range(n):
                f.write(f"2026-01-{i + 1:02d},1,1,1,{100 + i},1,1\n")
    wr("M2611", 5); wr("M2701", 5); wr("M2609", 5); wr("M2612", 5)           # M2609 已到期(今天 2026-10-10)，不该动
    got = {}
    def kline(sym, max_rows=5000):
        got[sym] = got.get(sym, 0) + 1
        n = {"M2611": 8, "M2701": 3, "M2612": 5}.get(sym)
        if n is None:
            return {"available": False, "reason": "没有合约"}
        return {"available": True, "bars": [{"date": f"2026-01-{i + 1:02d}", "open": 1, "high": 1, "low": 1, "close": 200 + i, "volume": 1, "hold": 1} for i in range(n)]}
    rep = fs.job_refresh_contracts(d, kline, datetime.date(2026, 10, 10), horizon_months=4, sleep=lambda s: None, pause=0)
    assert "M2609" not in got, got
    assert set(got) == {"M2611", "M2612", "M2701"}, got        # 2610~2702 范围内真实存在的合约月份(1/3/4/5/6/7/8/9/11/12)：2611、2612、2701
    assert rep["updated"] == ["M2611", "M2612"] and rep["keptOld"] == ["M2701"], rep
    assert sum(1 for _ in open(os.path.join(cdir, "M2611.csv"), encoding="utf-8")) == 9 and sum(1 for _ in open(os.path.join(cdir, "M2701.csv"), encoding="utf-8")) == 6
    shutil.rmtree(d); ok("刷新近月合约：只动未到期的、在时间范围内的；新抓到的行数不少于旧文件才覆盖(M2611 5→8 覆盖)，行数相等也覆盖(M2612 5→5)，变少就保留旧的(M2701 5→3 保留)")


def test_merge_rows_prefers_auto_when_consistent_and_flags_conflict():
    base = {"2026-09-28": row("2026-09-28", 3300, 3350), "2026-09-29": row("2026-09-29", 3310, 3355), "2026-09-30": row("2026-09-30", 3320, 3360)}
    auto = {"2026-09-30": row("2026-09-30", 3320.4, 3360), "2026-10-09": row("2026-10-09", 3402, 3389)}
    m, rep = sh.merge_rows(base, auto, tol=1.0)
    assert [r["d"] for r in m] == ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-09"]
    assert rep["overlap"] == 1 and rep["consistent"] and abs(rep["maxAbsSpot"] - 0.4) < 1e-9, rep
    assert [r["spot"] for r in m] == [3300.0, 3310.0, 3320.4, 3402.0]       # 重叠日用自动抓取的
    auto2 = {"2026-09-30": row("2026-09-30", 3370, 3360), "2026-10-09": row("2026-10-09", 3402, 3389)}
    m2, rep2 = sh.merge_rows(base, auto2, tol=1.0)
    assert not rep2["consistent"] and rep2["maxAbsSpot"] == 50.0 and m2[2]["spot"] == 3320.0 and m2[3]["spot"] == 3402.0, (rep2, m2)
    auto3 = {"2026-09-30": row("2026-09-30", 3320, 3400), "2026-10-09": row("2026-10-09", 3402, 3389)}     # 现货一致但主力价差40
    m5, rep5 = sh.merge_rows(base, auto3, tol=1.0)
    assert rep5["consistent"] is False and rep5["maxAbsFut"] == 40.0 and m5[2]["futures"] == 3360.0, rep5
    m3, rep3 = sh.merge_rows(base, {"2026-10-09": row("2026-10-09", 3402, 3389)}, tol=1.0)
    assert rep3["overlap"] == 0 and len(m3) == 4 and rep3["consistent"] is None
    m4, rep4 = sh.merge_rows(base, {}, tol=1.0)
    assert len(m4) == 3 and rep4["autoRows"] == 0
    ok("合并：重叠日一致(最大差0.4≤1)就以自动抓取为准；差到50就保留基线并标不一致；无重叠/无自动数据也能合")


def test_recent_trend_hand_calculated():
    n = 64
    ds = [(datetime.date(2026, 7, 1) + datetime.timedelta(days=i)).isoformat() for i in range(n)]
    spot = [{"d": d, "c": 100.0 + i} for i, d in enumerate(ds)]
    fut = [{"d": d, "c": 90.0 + i, "k": "m2701"} for i, d in enumerate(ds)]
    basis = [i % 7 for i in range(n)]
    t = ss.recent_trend(spot, ss.adjusted_index(fut), basis_rows=[{"d": d, "b": b} for d, b in zip(ds, basis)])
    s = t["spot"]
    assert s["last"] == 163.0 and s["w1"] == round((163 / 158 - 1) * 100, 2) == 3.16 and s["m1"] == 14.79 and s["q1"] == 63.0, s
    f = t["futures"]      # 指数基准100，同合约：指数=100*(90+i)/90；最近/5日前
    assert f["w1"] == round((153 / 148 - 1) * 100, 2) == 3.38 and f["q1"] == 70.0, f
    b = t["basis"]
    assert b["last"] == 0 and b["w1"] == -2 and b["pct"] == 15.6 and b["n"] == 64, b
    short = ss.recent_trend(spot[:30], ss.adjusted_index(fut[:30]))
    assert short["spot"]["w1"] is not None and short["spot"]["m1"] is not None and short["spot"]["q1"] is None, short
    assert ss.recent_trend([], [])["spot"]["last"] is None
    ok("近期趋势：现货1周+3.16%/1月+14.79%/3月+63%；期货按换月修正指数；基差最新0、较5日前−2、近64日分位15.6%；样本不够的周期给 None")


def test_main_merges_auto_rows_into_seasonal_json():
    d = tmp(); raw = os.path.join(d, "raw"); os.makedirs(raw)
    # 基线：2018-01~2019-03 每月两天(月中、月末)，spot 与 futures 逐月上涨1%
    rows = []; v = 100.0
    for y, m in [(2018, mm) for mm in range(1, 13)] + [(2019, 1), (2019, 2), (2019, 3)]:
        for dd in (15, 28):
            v *= 1.005
            rows.append((f"{y}-{m:02d}-{dd:02d}", round(v, 4)))
    with open(os.path.join(raw, "meal_spot_futures_10y.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "symbol", "spot", "near_contract", "near_contract_price", "dominant_contract", "futures"])
        for dt, x in rows:
            w.writerow([dt, "M", x, "m1", x, "m2", x])
    last = rows[-1][0]
    sh.upsert(os.path.join(raw, "spot_auto.csv"), [row("2019-04-15", 130.0, 130.0, "m2"), row("2019-04-28", 131.0, 131.0, "m2")])
    out = os.path.join(d, "seasonal.json")
    ss.main(["--raw", raw, "--out", out])
    j = json.load(open(out, encoding="utf-8"))
    assert j["meta"]["lastDate"] == "2019-04-28" and j["meta"]["autoMerge"]["autoRows"] == 2 and j["meta"]["autoMerge"]["overlap"] == 0, j["meta"]
    assert j["recent"]["spot"]["last"] == 131.0 and j["recent"]["futures"]["last"] is not None
    assert "4" in j["monthlyTable"]["spot"]["2019"] and j["months"][3]["spot"]["n"] == 2, j["months"][3]["spot"]    # 4月：2018 和新累积的 2019 两个年份
    shutil.rmtree(d); ok("seasonal_stats 主流程：基线 + spot_auto.csv 合并，lastDate 延伸到自动累积的最新日，meta 带合并报告，附带近期趋势 recent")


def test_baseline_only_still_works_without_auto_file():
    d = tmp(); raw = os.path.join(d, "raw"); os.makedirs(raw)
    with open(os.path.join(raw, "meal_spot_futures_10y.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "symbol", "spot", "near_contract", "near_contract_price", "dominant_contract", "futures"])
        for i, dt in enumerate(["2018-01-15", "2018-01-28", "2018-02-15"]):
            w.writerow([dt, "M", 100 + i, "m1", 100, "m2", 100 + i])
    out = os.path.join(d, "s.json"); ss.main(["--raw", raw, "--out", out])
    j = json.load(open(out, encoding="utf-8"))
    assert j["meta"]["autoMerge"]["autoRows"] == 0 and j["meta"]["lastDate"] == "2018-02-15"
    shutil.rmtree(d); ok("没有自动累积文件时行为不变(只用基线)")


def test_workflow_runs_daily_accumulation_after_close_and_commits_it():
    y = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".github", "workflows", "update-data.yml"), encoding="utf-8").read()
    import re
    m = re.search(r"github\.event\.schedule == '([^']+)'", y)
    assert m and f'cron: "{m.group(1)}"' in y, "触发条件里的 cron 必须是文件里真实存在的那一行"
    assert "夜盘刚收盘" in y.split(f'cron: "{m.group(1)}"')[1].split("\n")[0], "必须是夜盘收盘后(北京23:05)那次，生意社18:30后才有当天数据"
    i_acc, i_fetch, i_commit = y.index("spot_daily,refresh"), y.index("python3 fetch_data.py"), y.index("git add data/raw/seasonal/")
    assert i_fetch < i_acc < i_commit
    assert "workflow_dispatch" in y[y.index("季节性数据每日累积(现货+期货)"):i_acc] and "continue-on-error: true" in y[y.index("季节性数据每日累积(现货+期货)"):i_acc]
    ok("工作流：每日累积只在夜盘收盘后那次(cron 与文件里真实存在的一致)和手动运行时做，continue-on-error，在抓数据之后、提交之前，并提交 data/raw/seasonal/ 与 seasonal.json")


def test_job_spot_skips_the_range_covered_by_the_baseline_and_only_fetches_after_it():
    """用户 2026-10-11 的实测：auto 与基线 927 个重叠日差 0.0；整段回补只撞假日→'连续失败8次中止'，remaining 虚高 1665。"""
    d = tmp()
    try:
        with open(os.path.join(d, sh.BASE_NAME), "w", encoding="utf-8-sig") as f:
            f.write("date,symbol,spot,near_contract,near_contract_price,dominant_contract,futures\n"
                    "2026-09-29,M,3400,m2611,3349,m2701,3372\n2026-09-30,M,3400,m2611,3349,m2701,3372\n")
        calls = []
        def fetch(ds):
            calls.append(ds)
            return pd.DataFrame([{"symbol": "M", "spot_price": 3418.0, "dominant_contract": "m2701", "dominant_contract_price": 3366.0, "near_contract": "m2611", "near_contract_price": 3341.0, "dom_basis": -52.0}])
        rep = sh.job_spot(d, years=1, fetch=fetch, today=datetime.date(2026, 10, 9), pause=0, sleep=lambda s_: None)
        # 基线覆盖 09-29~09-30 整段不抓(含它们之间/之前的假日)；10-01~10-07 国庆休市(日历里有)；只剩 10-08(周四)、10-09(周五)；09-29 之前一年内的工作日全部不在 [09-29,09-30] 内 → 仍属'基线之前'要抓，所以只断言基线区间内没有请求
        assert "2026-09-29" not in calls and "2026-09-30" not in calls, calls
        assert "2026-10-08" in calls and "2026-10-09" in calls, calls
        assert rep["skippedBecauseBaselineCovers"] == ["2026-09-29", "2026-09-30"], rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("回补 job_spot：基线覆盖区间[首日,末日]内不请求(假日也不撞)，只抓区间之外缺的交易日；报告写明跳过的区间")


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception:
                fails += 1
                print("❌", name); traceback.print_exc()
    print(f"\n结果：{_pass}项通过，{fails}项失败")
    sys.exit(1 if fails else 0)
