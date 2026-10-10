# -*- coding: utf-8 -*-
"""外资趋势判断(v101.18)：capital_trend.py。运行：python3 test_capital_trend.py
期望值全部手算；主力合约(带合约代码)内才比较，换月/缺交易日就断开。真实数据段落来自 2026-08~10 的 M2701 高盛净多(龙虎榜文件+10-09线上值)。"""
import os, sys, tempfile, shutil
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capital_trend as ct
import history_store as hs
import cn_calendar as cc

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def tdays(start, n):
    out, d = [], date.fromisoformat(start)
    while len(out) < n:
        if cc.dce_is_trading_day_ex(d):
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def pts(dates, vals, contract="M2701", approx=()):
    out = []
    for i, (d, v) in enumerate(zip(dates, vals)):
        x = {"contract": contract}
        if i in approx:
            x["approx"] = 1
        out.append({"d": d, "v": v, "x": x})
    return out


D = tdays("2026-08-03", 12)

# ---------- 1. 点太少 / 换月 / 缺交易日 ----------
def test_insufficient_history():
    a = ct.assess_member(pts(D[:2], [100000, 90000]), high=120000)
    assert a["code"] == "insufficient" and a["n"] == 2, a
    assert ct.assess_member([], high=120000)["code"] == "insufficient"
    # 换月：最新合约只有2个点 → 不足
    p = pts(D[:4], [1, 2, 3, 4], "M2605") + pts(D[4:6], [150000, 140000], "M2701")
    a = ct.assess_member(p, high=120000)
    assert a["code"] == "insufficient" and a["contract"] == "M2701" and a["n"] == 2, a
    # 缺一个交易日：断开，只用缺口之后的点
    q = pts(D[:3], [100, 200, 300]) + pts(D[4:7], [400, 380, 360])
    a = ct.assess_member(q, high=None)
    assert a["n"] == 3 and a["peak"]["d"] == D[4], a
    ok("点<3→insufficient；换月/缺交易日在缺口处断开(不跨合约、不跨缺口算峰值和连续)")


# ---------- 2. 状态分类(手算) ----------
def test_classification():
    # 小幅连减：152000→150000→147000? 构造[110000,108000,105000]：连2日降，累计-5000 <1万 → trimming
    a = ct.assess_member(pts(D[:3], [110000, 108000, 105000]), high=120000)
    assert a["run"]["direction"] == "down" and a["run"]["days"] == 2 and a["run"]["total"] == -5000 and a["code"] == "trimming", a
    # 连2日累计-1万(边界，含)：152000→147000→142000 → retreating；峰值152000(第1点)，回落10000，=6.6%
    a = ct.assess_member(pts(D[:4], [150000, 152000, 147000, 142000]), high=120000)
    assert a["code"] == "retreating" and a["run"]["total"] == -10000 and a["run"]["days"] == 2, a
    assert a["peak"] == {"v": 152000, "d": D[1]} and a["drawdown"] == 10000 and a["drawdownPct"] == 6.6, a
    # 单日-2万 → retreat_fast
    a = ct.assess_member(pts(D[:3], [150000, 150000, 129000]), high=120000)
    assert a["code"] == "retreat_fast" and a["dayChange"] == -21000, a
    # 连3日累计-2万 → retreat_fast：150→146→142→130(千) 总-20000 3日
    a = ct.assess_member(pts(D[:4], [150000, 146000, 138000, 130000]), high=120000)
    assert a["run"]["days"] == 3 and a["run"]["total"] == -20000 and a["code"] == "retreat_fast", a
    # 连2日累计+1.2万 → building
    a = ct.assess_member(pts(D[:3], [100000, 105000, 112000]), high=120000)
    assert a["code"] == "building" and a["run"]["total"] == 12000, a
    # 连2日小幅增 → adding
    a = ct.assess_member(pts(D[:3], [100000, 101000, 103000]), high=120000)
    assert a["code"] == "adding", a
    # 震荡持平：6个点，5日变化 0 → flat
    a = ct.assess_member(pts(D[:6], [100000, 103000, 99000, 101000, 98000, 100000]), high=120000)
    assert a["code"] == "flat" and a["change5"]["change"] == 0, a
    # 日内涨跌交替但5日累计-1.1万 → 按5日变化判 retreating
    a = ct.assess_member(pts(D[:6], [140000, 138000, 139000, 133000, 134000, 129000]), high=120000)
    assert a["run"]["days"] == 1 and a["change5"]["change"] == -11000 and a["code"] == "retreating", a
    ok("手算分类：连2日-5000=trimming；连2日-1万=retreating(含边界)；单日-2.1万/连3日-2万=retreat_fast；连2日+1.2万=building；+4000=adding；5日0=flat；交替但5日-1.1万=retreating")


def test_mid_autumn_is_not_a_missing_trading_day_for_the_series():
    from datetime import date as d_
    assert cc.dce_is_trading_day(d_(2026, 9, 25)) is True and cc.dce_is_trading_day_ex(d_(2026, 9, 25)) is False, "页面休市表没有中秋，逐日序列计算要排除它"
    assert not hs._trading_day_between(d_(2026, 9, 24), d_(2026, 9, 28))
    assert hs._trading_day_between(d_(2026, 9, 23), d_(2026, 9, 28)), "9-24是交易日，隔着它就是缺口"
    ok("中秋(09-25)对逐日序列不算缺失的交易日(9-24→9-28相邻)，真缺的交易日仍然算缺口")


# ---------- 3. 国庆/近似标记 ----------
def test_holiday_and_approx_flags():
    d = ["2026-09-29", "2026-09-30", "2026-10-08", "2026-10-09"]
    a = ct.assess_member(pts(d, [149911, 152092, 137983, 129562], approx=(0, 1)), high=120000)
    assert a["run"]["days"] == 2 and a["run"]["total"] == -22530 and a["acrossHoliday"] is True and a["approx"] is True, a
    a2 = ct.assess_member(pts(D[:4], [150000, 152000, 147000, 142000]), high=120000)
    assert a2["acrossHoliday"] is False and a2["approx"] is False, a2
    ok("连续区间跨过休市长假(9-30→10-08)→acrossHoliday；区间内有下限估计点→approx；普通周末不算长假")


# ---------- 4. 真实数据：2026-08-03~10-09 高盛(M2701) ----------
GS_REAL = [("2026-08-31", 127793), ("2026-09-01", 135753), ("2026-09-02", 136253), ("2026-09-03", 137720), ("2026-09-04", 142121), ("2026-09-07", 142328), ("2026-09-08", 141448),
           ("2026-09-09", 141383), ("2026-09-10", 141523), ("2026-09-11", 142713), ("2026-09-14", 143208), ("2026-09-15", 141940), ("2026-09-16", 140171), ("2026-09-17", 143905),
           ("2026-09-18", 149777), ("2026-09-21", 143204), ("2026-09-22", 143569), ("2026-09-23", 141683), ("2026-09-24", 141449), ("2026-09-28", 141480), ("2026-09-29", 149911),
           ("2026-09-30", 152092), ("2026-10-08", 137983), ("2026-10-09", 129562)]


def real_points():
    return [{"d": d, "v": v, "x": {"contract": "M2701", **({"approx": 1} if d < "2026-10-08" else {})}} for d, v in GS_REAL]


def test_real_goldman_case_is_detected_as_retreat_from_high():
    a = ct.assess_member(real_points(), high=120000)
    assert a["n"] == 24, "中秋(9-25)休市后，9-24→9-28相邻，整段连续"
    assert a["run"]["direction"] == "down" and a["run"]["days"] == 2 and a["run"]["total"] == -22530, a["run"]
    assert a["peak"] == {"v": 152092, "d": "2026-09-30"} and a["drawdown"] == 22530 and a["drawdownPct"] == 14.8, a
    assert a["dayChange"] == -8421 and a["code"] == "retreating", a
    ok("★真实案例(高盛M2701)：峰值152,092(09-30)→129,562，连续2日减仓累计-22,530、较峰值-14.8%、单日-8,421→retreating(不是'拥挤'一句话)")

    cf = {"percentile": 100.0, "weeksUsed": 156, "streakWeeks": 7, "streakDirection": "up", "reportDate": "2026-09-29", "net": 207578.0}
    v = ct.build_verdict(a, cf, old_state={"code": "crowded", "level": "red", "label": "外资多头拥挤"})
    assert v["code"] == "retreat_from_high" and v["level"] == "yellow", v
    assert v["short"] == "外资高位撤退中", v["short"]
    assert "高位撤退" in v["label"] and "129,562" in v["label"] and "152,092" in v["label"] and "22,530" in v["label"], v["label"]
    txt = " ".join(v["lines"])
    assert "9,562" in txt and "12万" in txt, "距12万手警戒线还差9,562手"
    assert "国庆" in txt, "跨国庆长假要打折提示"
    assert "下限" in txt, "含下限估计要说明"
    assert "100%" in txt and "7周" in txt and "未反映" in txt, "CFTC：近156周100%分位、连续7周增加、周度数据未反映最新交易日"
    assert "没有证据" in " ".join(v["evidence"]) or "没有证据" in txt, "必须诚实写：减仓→下跌没有历史证据"
    ok("★verdict：retreat_from_high/yellow；标题带峰值→现值→累计；距12万警戒线差9,562；国庆折扣、下限估计、CFTC周度滞后、'减仓预示下跌没有证据'都写明")


def test_other_verdict_codes():
    cf_hi = {"percentile": 95.0, "weeksUsed": 156}
    cf_lo = {"percentile": 40.0, "weeksUsed": 156}
    old_red = {"code": "crowded", "level": "red", "label": "外资多头拥挤"}
    # 高位 + 持平 → 拥挤(无撤退迹象)
    flat_hi = ct.assess_member(pts(D[:6], [130000, 131000, 129000, 130500, 130000, 130000]), high=120000)
    v = ct.build_verdict(flat_hi, cf_hi, old_red)
    assert v["code"] == "crowded_flat" and v["level"] == "red" and "持平" in v["label"], v
    # 高位 + 加仓 → build_high red
    up = ct.assess_member(pts(D[:3], [125000, 130000, 140000]), high=120000)
    v = ct.build_verdict(up, cf_hi, old_red)
    assert v["code"] == "build_high" and v["level"] == "red" and "加仓" in v["label"], v
    # 低位 + 加仓 → build yellow
    lo = ct.assess_member(pts(D[:3], [20000, 30000, 45000]), high=120000)
    v = ct.build_verdict(lo, cf_lo, {"code": "neutral", "level": "green", "label": "外资中性"})
    assert v["code"] == "build" and v["level"] == "yellow" and "进场" in v["label"], v
    # 低位 + 减仓 → retreat yellow 外资减仓中
    dn = ct.assess_member(pts(D[:3], [60000, 50000, 40000]), high=120000)
    v = ct.build_verdict(dn, cf_lo, {"code": "neutral", "level": "green", "label": "外资中性"})
    assert v["code"] == "retreat" and v["level"] == "yellow" and "减仓" in v["label"], v
    # 低位 + 持平 → 沿用旧中性
    nf = ct.assess_member(pts(D[:6], [20000, 21000, 19000, 20500, 20000, 20000]), high=120000)
    v = ct.build_verdict(nf, cf_lo, {"code": "neutral", "level": "green", "label": "外资中性(高盛净多头不在高位，CFTC不拥挤)"})
    assert v["code"] == "neutral_flat" and v["level"] == "green", v
    # 历史不足 → 沿用旧状态，并如实写趋势不可判
    ins = ct.assess_member(pts(D[:1], [129562]), high=120000)
    v = ct.build_verdict(ins, cf_hi, old_red)
    assert v["code"] == "insufficient" and v["level"] == "red" and "趋势" in v["label"] and "1" in v["label"], v
    # 高盛没有数据 → 不下结论
    v = ct.build_verdict(None, cf_hi, {"code": "elevated", "level": "yellow", "label": "x"})
    assert v["code"] == "no_member" and v["level"] == "gray", v
    ok("verdict其余分支：高位持平=crowded_flat(红)；高位加仓=build_high(红)；低位加仓=build(黄,进场)；低位减仓=retreat(黄)；低位持平=neutral_flat(绿)；历史不足沿用旧状态并注明；没有高盛=gray")


def test_other_foreign_seats_are_summarised_in_one_line():
    mc = _mc("2026-10-09", 129562, -8421)
    mc["verdict"] = None
    series = {"高盛期货": real_points(),
              "摩根大通": pts(D[:3], [-7000, -2000, 4000]),                      # 连2日增加，累计+11,000 → 加仓
              "瑞银期货": pts(D[:6], [10000, 10500, 9800, 10300, 9900, 10000])}   # 5日0 → 持平
    ct.attach(mc, series)
    txt = " ".join(mc["verdict"]["lines"])
    assert "其他外资席位" in txt and "摩根大通" in txt and "+11,000" in txt and "加仓" in txt and "瑞银" in txt and "持平" in txt, txt
    assert mc["trend"]["摩根大通"]["code"] == "building" and mc["trend"]["瑞银期货"]["code"] == "flat"
    # 其他席位历史不足：不写
    mc2 = _mc("2026-10-09", 129562, -8421)
    ct.attach(mc2, {"高盛期货": real_points(), "摩根大通": pts(D[:1], [1635])})
    assert "其他外资席位" not in " ".join(mc2["verdict"]["lines"])
    ok("其他外资席位(摩根大通/瑞银)一句话概括(加仓/减仓/持平+累计)，回答'外资是再来还是走'；历史不足的席位不写")


def test_trend_never_mutates_inputs():
    p = real_points()
    snap = [dict(x) for x in p]
    ct.assess_member(p, high=120000)
    assert p == snap
    ok("assess_member 不修改入参")


# ---------- 5. 与累积(history_store)联动：补上节后缺的前一交易日 + 挂trend/verdict ----------
def _mc(day, net, change, cftc=None):
    return {"available": True, "mainContract": {"key": "jan", "symbol": "M2701", "gross": 822654}, "date": day,
            "members": {"高盛期货": {"net": net, "change": change, "side": "long", "rank": 2, "foreign": True},
                        "摩根大通": {"net": 1635, "change": 9505, "side": "long", "rank": 12, "foreign": True},
                        "瑞银期货": {"net": None, "change": None, "side": None, "rank": None, "foreign": True},
                        "中粮期货": {"net": -502772, "change": -27174, "side": "short", "rank": 1, "foreign": False},
                        "国投期货": {"net": -208344, "change": 7773, "side": "short", "rank": 2, "foreign": False}},
            "cftc": cftc or {"net": 207578.0, "percentile": 100.0, "weeksUsed": 156, "streakWeeks": 7, "streakDirection": "up", "reportDate": "2026-09-29"},
            "state": {"code": "crowded", "level": "red", "label": "外资多头拥挤"}}


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="trend_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def test_missing_previous_trading_day_is_reconstructed_from_the_reported_change():
    with Tmp() as d:
        hs.record_points("capital_gs_net", real_points()[:-2], d)       # 回填到09-30
        res = {"marketCapital": _mc("2026-10-09", 129562, -8421)}
        hs.update_and_attach(res, base_dir=d)
        p = {x["d"]: x for x in hs.load_series("capital_gs_net", d)["points"]}
        assert p["2026-10-08"]["v"] == 137983 and p["2026-10-08"]["x"]["derived"] == 1 and p["2026-10-08"]["x"]["contract"] == "M2701", p["2026-10-08"]
        assert p["2026-10-09"]["v"] == 129562 and "derived" not in p["2026-10-09"]["x"]
        mc = res["marketCapital"]
        assert mc["verdict"]["code"] == "retreat_from_high" and mc["trend"]["高盛期货"]["run"]["days"] == 2, mc["verdict"]
        assert mc["members"]["高盛期货"]["history"]["run"]["days"] == 2 and mc["members"]["高盛期货"]["history"]["run"]["total"] == -22530
        # 第二次跑(同一天)不重复添加、结果不变
        before = open(os.path.join(d, "capital_gs_net.json"), encoding="utf-8").read()
        hs.update_and_attach({"marketCapital": _mc("2026-10-09", 129562, -8421)}, base_dir=d)
        assert open(os.path.join(d, "capital_gs_net.json"), encoding="utf-8").read() == before
    ok("★10-09只有当日值+当日变化(-8,421)时，自动补出10-08(=129,562+8,421=137,983，标derived)，国庆后连续2日减仓立刻可判；重复运行幂等")


def test_reconstruction_never_overwrites_and_needs_a_change():
    with Tmp() as d:
        hs.record_points("capital_gs_net", pts(["2026-10-08"], [140000]), d)       # 10-08已有真实点(值不同)
        hs.update_and_attach({"marketCapital": _mc("2026-10-09", 129562, -8421)}, base_dir=d)
        p = {x["d"]: x for x in hs.load_series("capital_gs_net", d)["points"]}
        assert p["2026-10-08"]["v"] == 140000 and "derived" not in p["2026-10-08"].get("x", {}), "已有的点绝不覆盖"
    with Tmp() as d:
        hs.update_and_attach({"marketCapital": _mc("2026-10-09", 129562, None)}, base_dir=d)
        assert [x["d"] for x in hs.load_series("capital_gs_net", d)["points"]] == ["2026-10-09"], "没有当日变化：不编前一天"
    ok("已有真实点不覆盖；源数据没给当日变化就不推算")


def test_verdict_with_thin_history_falls_back_and_says_so():
    with Tmp() as d:
        res = {"marketCapital": _mc("2026-10-09", 129562, None)}
        hs.update_and_attach(res, base_dir=d)
        v = res["marketCapital"]["verdict"]
        assert v["code"] == "insufficient" and "拥挤" in v["label"] and "趋势暂不可判" in v["label"] and v["level"] == "red", v
    ok("历史只有1天(没有当日变化可推算)：沿用'外资多头拥挤'并写明'趋势暂不可判'，不假装有趋势")


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception:
                fails += 1
                print("❌", name)
                traceback.print_exc()
    print(f"\n{_pass} 条通过，{fails} 个失败")
    sys.exit(1 if fails else 0)
