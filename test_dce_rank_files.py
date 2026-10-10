# -*- coding: utf-8 -*-
"""大商所"日成交持仓排名"文件 → 龙虎榜席位净持仓历史回填(v101.13)。运行：python3 test_dce_rank_files.py
★期望值全部来自真实文件(data/raw/dce_rank/M2701_*.txt，用户 2026-10-09 提供的 2026年9月 M2701 合约)，手算；
★最关键的一条：用 2026-09-30 这一天对账线上已经累积的点(history 里 09-30 的 5 个席位，线上抓取得到)——3个'两边都在前20'的席位数值和变化完全一致，
  2个'只在一边进前20'的席位(高盛、瑞银)也完全一致，从而证明线上口径是：缺失的那一边用该榜第20名的数值顶替(净持仓是下限估计，不是精确值)，回填沿用同一口径。"""
import os, sys, shutil, tempfile, traceback, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dce_rank_files as dr
import history_store as hs
import backfill_history as bf

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "raw", "dce_rank")
# 这批测试的期望值是按"2026年9月21个文件"手算的；v101.18 往同一目录加了 2026-08 的 21 个文件(另有专门测试)，所以回填类测试只看9月的子集
import tempfile as _tf
RAW9 = _tf.mkdtemp(prefix="raw9_")
for _f in sorted(os.listdir(RAW)):
    if _f.startswith("M2701_202609") and _f.endswith(".txt"):
        shutil.copyfile(os.path.join(RAW, _f), os.path.join(RAW9, _f))
_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def load(day):
    return dr.parse_rank_text(open(os.path.join(RAW, f"M2701_{day}.txt"), encoding="utf-8").read())


def test_parse_reads_date_and_the_three_top20_tables():
    p = load("20260930")
    assert p["date"] == "2026-09-30" and len(p["buy"]) == 20 and len(p["sell"]) == 20, (p["date"], len(p["buy"]), len(p["sell"]))
    assert p["buy"][0] == {"rank": 1, "name": "国泰君安（代客）", "value": 291237, "change": -5714} or p["buy"][0]["rank"] == 1
    assert p["sell"][-1] == {"rank": 20, "name": "新湖期货（代客）", "value": 22853, "change": -819}, p["sell"][-1]
    assert p["buy"][-1]["name"].startswith("瑞银期货") and p["buy"][-1]["value"] == 34342 and p["buy"][-1]["change"] == 10, p["buy"][-1]
    ok("解析真实文件(09-30)：日期取自首行，持买/持卖各20行，千分位逗号和负号正确，'合计'行不算；第20名持卖=新湖期货22,853(−819)")


def test_members_on_both_sides_match_the_live_series_exactly_on_0930():
    p = load("20260930")
    live = {"摩根大通": (-9739, -7014), "中粮期货": (-482209, 5234), "国投期货": (-226091, -2906)}      # history 里线上累积的 2026-09-30 点
    for name, (net, chg) in live.items():
        r = dr.member_net(p, name)
        assert r["net"] == net and r["change"] == chg and r["approx"] is False, (name, r)
    ok("★对账线上：摩根大通/中粮/国投 2026-09-30 的净持仓与变化与线上累积的点逐位一致(-9,739/-7,014，-482,209/+5,234，-226,091/-2,906)")


def test_members_on_one_side_use_the_20th_place_of_the_missing_side_like_the_live_series():
    p = load("20260930")
    gs, ubs = dr.member_net(p, "高盛期货"), dr.member_net(p, "瑞银期货")
    assert (gs["net"], gs["change"], gs["approx"]) == (152092, 2181, True), gs          # 174,945−22,853；1,362−(−819)
    assert (ubs["net"], ubs["change"], ubs["approx"]) == (11489, 829, True), ubs        # 34,342−22,853；10−(−819)
    ok("★对账线上：高盛 152,092(+2,181)、瑞银 11,489(+829)——持卖不在前20，用第20名持卖22,853(−819)顶替，与线上一致；标 approx=下限估计")


def test_hand_calculated_values_on_0901():
    p = load("20260901")
    r = dr.member_net(p, "摩根大通")
    assert (r["net"], r["change"]) == (77767 - 67092, 6501 - 500) == (10675, 6001), r
    r = dr.member_net(p, "中粮期货")
    assert (r["net"], r["change"]) == (45905 - 665717, 4030 - 5331), r
    r = dr.member_net(p, "国投期货")
    assert (r["net"], r["change"]) == (60706 - 365297, 1466 - 13420), r
    gs = dr.member_net(p, "高盛期货")
    assert (gs["net"], gs["change"]) == (158298 - 22545, 5503 - 1053) and gs["approx"] is True, gs      # 第20名持卖=五矿期货 22,545(+1,053)
    u = dr.member_net(p, "瑞银期货")
    assert (u["net"], u["change"]) == (36265 - 22545, 525 - 1053), u
    ok("手算 09-01：摩根大通+10,675、中粮−619,812、国投−304,591、高盛+135,753(估)、瑞银+13,720(估)")


def test_a_member_in_neither_list_has_no_point_not_zero():
    p = load("20260904")
    assert dr.member_net(p, "瑞银期货") is None
    ok("两边都没进前20：返回 None(不记0——和线上一致，记0会让'连续N日'误判)")


def test_sell_side_only_uses_the_20th_place_of_the_buy_side():
    txt = "大连商品交易所_日成交持仓排名_20260105\n名次\t会员简称\t成交量\t增减\t名次\t会员简称\t持买单量\t增减\t名次\t会员简称\t持卖单量\t增减\n" + "".join(
        f"{i}\tA{i}（代客）\t1\t0\t{i}\tB{i}（代客）\t{1000 - i}\t{i}\t{i}\t{'某某期货' if i == 3 else 'C%d' % i}（代客）\t{5000 - i}\t{-i}\n" for i in range(1, 21)) + "合计\t\t1\t1\t合计\t\t1\t1\t合计\t\t1\t1\n"
    r = dr.member_net(dr.parse_rank_text(txt), "某某期货")
    assert r["net"] == 980 - 4997 and r["change"] == 20 - (-3) and r["approx"] is True, r      # 买用第20名(980,+20)顶替；卖=5000-3=4997(−3)
    ok("只在持卖榜：买的一边用第20名持买顶替(净空头的下限估计)")


def test_incomplete_table_gives_no_estimate():
    txt = "大连商品交易所_日成交持仓排名_20260105\n名次\t会员简称\t成交量\t增减\t名次\t会员简称\t持买单量\t增减\t名次\t会员简称\t持卖单量\t增减\n" \
          "1\tA（代客）\t1\t0\t1\t高盛期货（代客）\t100\t5\t1\tC（代客）\t50\t1\n"
    p = dr.parse_rank_text(txt)
    assert dr.member_net(p, "高盛期货") is None, "榜单不足20行，不知道第20名是多少：不估计"
    ok("榜单不足20行时不估计(不知道截断位置)，宁缺勿造")


def test_job_backfills_five_series_with_the_live_point_shape_and_never_overwrites_live_points():
    d = tempfile.mkdtemp()
    try:
        # 先放线上已有的 09-30 点(精确值)和一个故意不一致的 09-29 点(冲突)
        hs.record_points("capital_zl_net", [{"d": "2026-09-30", "v": -482209, "x": {"contract": "M2701", "change": 5234}}, {"d": "2026-09-29", "v": 1, "x": {"contract": "M2701", "change": 0}}], d)
        e = bf.backfill_capital_rank(base_dir=d, raw_dir=RAW9)
        assert "error" not in e, e
        n = {k: len(hs.load_series(k, d)["points"]) for k in ("capital_gs_net", "capital_jpm_net", "capital_ubs_net", "capital_zl_net", "capital_gt_net")}
        assert n == {"capital_gs_net": 21, "capital_jpm_net": 21, "capital_ubs_net": 12, "capital_zl_net": 21, "capital_gt_net": 21}, n
        zl = {p["d"]: p for p in hs.load_series("capital_zl_net", d)["points"]}
        assert zl["2026-09-29"]["v"] == 1, "线上已有的点不被覆盖"
        assert e["conflicts"] and e["conflicts"][0]["series"] == "capital_zl_net" and e["conflicts"][0]["d"] == "2026-09-29", e["conflicts"]
        assert zl["2026-09-01"] == {"d": "2026-09-01", "v": -619812, "x": {"contract": "M2701", "change": -1301}}, zl["2026-09-01"]
        gs = {p["d"]: p for p in hs.load_series("capital_gs_net", d)["points"]}
        assert gs["2026-09-01"] == {"d": "2026-09-01", "v": 135753, "x": {"contract": "M2701", "change": 4450, "approx": 1}}, gs["2026-09-01"]
        ubs_days = [p["d"] for p in hs.load_series("capital_ubs_net", d)["points"]]
        assert "2026-09-04" not in ubs_days and "2026-09-01" in ubs_days
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★回填：高盛/摩根/中粮/国投各21个交易日，瑞银12个(其余9天两边都没进前20，不记0)；点的结构与线上一致(估计值多一个 approx 标记)；线上已有点不被覆盖，数值不一致只记冲突")


def test_incomplete_buy_table_gives_no_estimate_for_a_sell_only_member():
    txt = "大连商品交易所_日成交持仓排名_20260105\n名次\t会员简称\t成交量\t增减\t名次\t会员简称\t持买单量\t增减\t名次\t会员简称\t持卖单量\t增减\n" \
          "1\tA（代客）\t1\t0\t1\tB（代客）\t100\t5\t1\t高盛期货（代客）\t50\t1\n"
    assert dr.member_net(dr.parse_rank_text(txt), "高盛期货") is None
    ok("买榜不足20行、席位只在卖榜：同样不估计")


def test_job_is_idempotent_and_reports_coverage_and_bounds():
    d = tempfile.mkdtemp()
    try:
        bf.backfill_capital_rank(base_dir=d, raw_dir=RAW9)
        before = {f: open(os.path.join(d, f), "rb").read() for f in os.listdir(d)}
        e = bf.backfill_capital_rank(base_dir=d, raw_dir=RAW9)
        after = {f: open(os.path.join(d, f), "rb").read() for f in os.listdir(d)}
        assert before == after and e["added"] == 0, e["added"]
        assert e["files"] == 21 and e["firstDay"] == "2026-09-01" and e["lastDay"] == "2026-09-30", e
        cov = e["coverage"]
        assert cov["高盛期货"] == {"exact": 0, "estimated": 21, "absent": 0} and cov["摩根大通"]["exact"] == 21 and cov["瑞银期货"] == {"exact": 0, "estimated": 12, "absent": 9}, cov
        assert e["perSeries"]["capital_gs_net"]["total"] == 21
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("重复运行幂等(文件字节不变、added=0)；报告列出每个席位'精确/估计/缺席'的天数")


def test_bad_files_are_reported_not_fatal():
    d, raw = tempfile.mkdtemp(), tempfile.mkdtemp()
    try:
        for day in ("20260901", "20260902"):
            shutil.copyfile(os.path.join(RAW, f"M2701_{day}.txt"), os.path.join(raw, f"M2701_{day}.txt"))
        shutil.copyfile(os.path.join(RAW, "M2701_20260903.txt"), os.path.join(raw, "M2701_20260910.txt"))      # 文件名日期和内容日期对不上
        open(os.path.join(raw, "M2701_20260911.txt"), "w", encoding="utf-8").write("垃圾内容")
        open(os.path.join(raw, "notes.txt"), "w", encoding="utf-8").write("不是排名文件(文件名不合规)")
        e = bf.backfill_capital_rank(base_dir=d, raw_dir=raw)
        assert e["files"] == 2 and len(e["skippedFiles"]) == 3, e
        why = " ".join(x["why"] for x in e["skippedFiles"])
        assert "对不上" in why and "解析" in why and "文件名" in why, why
        assert len(hs.load_series("capital_zl_net", d)["points"]) == 2
        e2 = bf.backfill_capital_rank(base_dir=d, raw_dir=os.path.join(raw, "不存在"))
        assert "error" in e2 and "没有" in e2["error"], e2
    finally:
        shutil.rmtree(d, ignore_errors=True); shutil.rmtree(raw, ignore_errors=True)
    ok("坏文件(日期对不上/内容不是排名/文件名不合规)只跳过并写明原因，好的照常入库；目录不存在给清晰错误")


def test_registered_as_a_manual_job_outside_the_defaults_and_documented_in_the_workflow():
    assert bf.JOBS["capital_rank"] is bf.backfill_capital_rank and "capital_rank" not in bf.DEFAULT_JOBS
    wf = open(os.path.join(HERE, ".github", "workflows", "backfill-history.yml"), encoding="utf-8").read()
    assert "capital_rank" in wf
    ok("capital_rank 登记为手动回填项(不在默认 all 里)，工作流说明里有")


def test_merged_with_live_points_the_series_runs_through_the_holiday_gap():
    d = tempfile.mkdtemp()
    try:
        hs.record_points("capital_gs_net", [{"d": "2026-09-30", "v": 152092, "x": {"contract": "M2701", "change": 2181}}, {"d": "2026-10-08", "v": 137983, "x": {"contract": "M2701", "change": -14109}}], d)
        bf.backfill_capital_rank(base_dir=d, raw_dir=RAW9)
        pts = hs.load_series("capital_gs_net", d)["points"]
        assert len(pts) == 22 and pts[0]["d"] == "2026-09-01" and pts[-1]["d"] == "2026-10-08", (len(pts), pts[0]["d"], pts[-1]["d"])
        assert pts[-2] == {"d": "2026-09-30", "v": 152092, "x": {"contract": "M2701", "change": 2181}}, "线上的精确点原样保留(没被加 approx)"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("和线上点合并：9月21天 + 10-08 = 22个点，线上的 09-30 原样保留")


def test_august_files_extend_the_series_and_run_into_september():
    """v101.18：2026-08 的 21 个文件(用户的 p1 外资时代包)。手算(从文件里读)：
    08-03 摩根大通 持买57,647(+171)、持卖33,130(+8,104) → 净+24,517、变化171-8,104=-7,933，两边都在前20=精确；
    08-31 高盛 持买152,795，持卖不在前20，第20名持卖=新湖期货25,002 → 净下限152,795-25,002=127,793，标approx；
    08-31 → 09-01 是相邻交易日，序列在合并后连续。"""
    d = tempfile.mkdtemp()
    try:
        e = bf.backfill_capital_rank(base_dir=d, raw_dir=RAW)
        assert e["files"] == 42 and e["firstDay"] == "2026-08-03" and e["lastDay"] == "2026-09-30" and e["conflicts"] == [] and e["skippedFiles"] == [], e
        jpm = {p["d"]: p for p in hs.load_series("capital_jpm_net", d)["points"]}
        assert jpm["2026-08-03"]["v"] == 24517 and jpm["2026-08-03"]["x"]["change"] == -7933 and "approx" not in jpm["2026-08-03"]["x"], jpm["2026-08-03"]
        gs = {p["d"]: p for p in hs.load_series("capital_gs_net", d)["points"]}
        assert gs["2026-08-31"]["v"] == 127793 and gs["2026-08-31"]["x"].get("approx") == 1 and gs["2026-08-31"]["x"]["contract"] == "M2701", gs["2026-08-31"]
        assert len(gs) == 42 and hs.change_over(list(gs.values()), 21) is not None, "08-03→09-30 连续42个点，近21个交易日变化可算(跨08-31→09-01无缺口)"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★8月21个文件 + 9月21个文件 = 42个连续点；摩根大通08-03(+24,517/-7,933)与高盛08-31(下限127,793, approx)手算一致")


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
