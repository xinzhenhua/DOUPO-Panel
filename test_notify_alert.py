# -*- coding: utf-8 -*-
"""提醒发送与持仓记录的测试：python3 test_notify_alert.py（不联网，发送函数全部是假的）"""
import json, os, sys, tempfile, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_alert as na, record_position as rp
_pass = 0
def ok(n): 
    global _pass; _pass += 1; print("✅", n)

def alert(side=0, events=None, pd="2026-10-09", gate=True):
    return {"priceDate": pd, "side": side, "gate": {"ok": gate}, "events": events or []}
ENTRY = lambda side=1, pd="2026-10-09": {"type": "entry", "side": side, "key": f"entry|{pd}|{side}", "title": "做多", "body": "b"}
EXIT = lambda pd="2026-10-09": {"type": "exit", "key": f"exit|{pd}|2026-09-10|止损", "title": "平", "body": "b"}
class Rec:
    def __init__(s, ret=True): s.calls = []; s.ret = ret
    def __call__(s, env, t, b): s.calls.append(t); return s.ret

def test_entry_sent_once_then_not_repeated_while_signal_persists():
    r = Rec(); st, rep = na.run(alert(1, [ENTRY()]), {}, {}, "2026-10-12", {"x": r})
    assert r.calls == ["做多"] and st["lastSide"] == 1 and rep["sent"], (r.calls, st)
    r2 = Rec(); st2, _ = na.run(alert(1, [ENTRY(pd="2026-10-10")]), st, {}, "2026-10-12", {"x": r2})
    assert r2.calls == [], "信号持续（价格日变了）不重复发"
    st3, _ = na.run(alert(0), st2, {}, "2026-10-13", {"x": Rec()}); assert st3["lastSide"] == 0
    r4 = Rec(); na.run(alert(1, [ENTRY(pd="2026-10-14")], pd="2026-10-14"), st3, {}, "2026-10-14", {"x": r4}); assert r4.calls == ["做多"], "信号消失后再出现会再发"
    r5 = Rec(); na.run(alert(-1, [ENTRY(-1, "2026-10-15")], pd="2026-10-15"), dict(st3, lastSide=1), {}, "2026-10-15", {"x": r5}); assert r5.calls == ["做多"], "方向变了再发"
    ok("入场信号：从无变有/方向变了才发，持续不重复")

def test_failed_send_is_not_recorded_and_retries():
    r = Rec(False); st, rep = na.run(alert(1, [ENTRY()]), {}, {}, "2026-10-12", {"x": r})
    assert st.get("sent") == [] and st.get("lastSide") is None and rep["skipped"] == 1, st
    r2 = Rec(True); st2, _ = na.run(alert(1, [ENTRY()]), st, {}, "2026-10-12", {"x": r2}); assert r2.calls, "下一小时重试"
    ok("发送失败不记账，下一小时重试")

def test_unconfigured_channels_are_skipped_and_nothing_recorded():
    st, rep = na.run(alert(1, [ENTRY()]), {}, {}, "2026-10-12", {"a": lambda e, t, b: None})
    assert st["sent"] == [] and rep["channels"] == [] and rep["skipped"] == 1
    ok("一个渠道都没配：不记账（配好后还能收到）")

def test_stale_events_are_not_sent():
    r = Rec(); na.run(alert(1, [ENTRY(pd="2026-10-01")], pd="2026-10-01"), {}, {}, "2026-10-12", {"x": r}); assert r.calls == []
    r = Rec(); na.run(alert(0, [EXIT(pd="2026-10-01")], pd="2026-10-01"), {}, {}, "2026-10-12", {"x": r}); assert r.calls == []
    ok("价格日超过3天前的事件不补发")

def test_exit_repeats_each_new_price_day_until_position_closed():
    r = Rec(); st, _ = na.run(alert(0, [EXIT("2026-10-09")]), {}, {}, "2026-10-12", {"x": r}); assert len(r.calls) == 1
    r = Rec(); st, _ = na.run(alert(0, [EXIT("2026-10-09")]), st, {}, "2026-10-12", {"x": r}); assert r.calls == [], "同一个价格日不重复"
    r = Rec(); st, _ = na.run(alert(0, [EXIT("2026-10-12")], pd="2026-10-12"), st, {}, "2026-10-13", {"x": r}); assert len(r.calls) == 1, "下一个价格日还没平仓 → 再提醒"
    ok("离场提醒：同价格日只发一次，持仓没记平仓则次日再催")

def test_channels_use_env_and_exact_requests():
    seen = []
    post = lambda url, data=None, js=None, headers=None: (seen.append((url, data, js, headers)) or (200, '{"code":0}' if "ftqq" in url else '{"code":200}' if "pushplus" in url else "{}"))
    env = {"GITHUB_REPOSITORY": "o/r", "GITHUB_TOKEN": "t", "GITHUB_REPOSITORY_OWNER": "o", "SERVERCHAN_KEY": "SCT1", "PUSHPLUS_TOKEN": "pp"}
    assert na.send_issue(env, "T", "B", post) and na.send_serverchan(env, "T", "B", post) and na.send_pushplus(env, "T", "B", post)
    assert seen[0][0] == "https://api.github.com/repos/o/r/issues" and seen[0][2]["body"].startswith("@o") and seen[0][3]["Authorization"] == "Bearer t"
    assert seen[1][0] == "https://sctapi.ftqq.com/SCT1.send" and seen[1][1]["title"] == "T"
    assert seen[2][2]["token"] == "pp"
    assert na.send_issue({"GITHUB_REPOSITORY": "o/r", "GITHUB_TOKEN": "t", "ALERT_ISSUE": "0"}, "T", "B", post) is None
    assert na.send_serverchan({}, "T", "B", post) is None and na.send_pushplus({}, "T", "B", post) is None and na.send_smtp({}, "T", "B") is None
    ok("Issue/Server酱/PushPlus 请求地址和参数正确，没配密钥返回 None")

def test_smtp_sends_with_utf8():
    sent = {}
    class FakeSMTP:
        def __init__(s, host, port, timeout=0): sent["host"] = (host, port)
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def login(s, u, p): sent["login"] = (u, p)
        def sendmail(s, f, to, msg): sent["to"] = to; sent["msg"] = msg
    assert na.send_smtp({"SMTP_HOST": "smtp.x.com", "SMTP_USER": "a@x.com", "SMTP_PASS": "pw"}, "豆粕提醒", "正文", FakeSMTP)
    assert sent["host"] == ("smtp.x.com", 465) and sent["to"] == ["a@x.com"] and "UTF-8" in sent["msg"].upper()
    ok("邮件：默认465、收件人默认自己、UTF-8")

def test_exception_in_one_channel_does_not_block_others():
    def boom(e, t, b): raise RuntimeError("down")
    r = Rec(); st, rep = na.run(alert(1, [ENTRY()]), {}, {}, "2026-10-12", {"bad": boom, "ok": r})
    assert r.calls and rep["sent"] and any("down" in f for f in rep["failed"])
    ok("一个渠道挂了不影响其它渠道，也不影响记账")

def test_record_position():
    o = rp.build("open", "多", "5", "2026-10-12", "3402", now="N"); assert o == {"side": 1, "lots": 5, "entryD": "2026-10-12", "entryPx": 3402.0, "updated": "N"}
    assert rp.build("open", "做空", 3, "2026-10-12", 3500, now="N")["side"] == -1
    assert rp.build("close", now="N") == {"flat": True, "updated": "N"}
    for bad in (("open", "上", 5, "2026-10-12", 3400), ("open", "多", 0, "2026-10-12", 3400), ("open", "多", 5, "2026/10/12", 3400), ("open", "多", 5, "2026-13-40", 3400), ("open", "多", 5, "2026-10-12", 34), ("open", "多", "x", "2026-10-12", 3400)):
        try: rp.build(*bad); assert False, bad
        except ValueError: pass
    d = tempfile.mkdtemp()
    try:
        out = os.path.join(d, "x", "position.json"); assert rp.main(["open", "--side", "空", "--lots", "2", "--date", "2026-10-12", "--price", "3400", "--out", out]) == 0 and json.load(open(out))["side"] == -1
        assert rp.main(["open", "--side", "上", "--lots", "2", "--date", "2026-10-12", "--price", "3400", "--out", out]) == 2
        assert rp.main(["close", "--out", out]) == 0 and json.load(open(out))["flat"]
    finally: shutil.rmtree(d, ignore_errors=True)
    ok("记录持仓：方向/手数/日期/价格校验，写文件，平仓写 flat")

def test_end_to_end_with_node_script():
    root = os.path.dirname(os.path.abspath(__file__))
    if not shutil.which("node"): print("⚠️ 跳过：没有 node"); return
    d = tempfile.mkdtemp()
    try:
        data = os.path.join(d, "data"); os.makedirs(os.path.join(data, "raw", "seasonal"))
        # 合成数据：350 天，前 300 天缓跌，之后 50 天急跌再反弹 → 低位+反弹确认；外资 5 日 +5000（没去杠杆）
        import datetime as dt
        days = []; x = dt.date(2025, 1, 1)
        while len(days) < 350:
            if x.weekday() < 5: days.append(x.isoformat())
            x += dt.timedelta(days=1)
        px = [3600 - i * 2 for i in range(300)] + [3000 - (i * 20) for i in range(40)] + [2200 + i * 20 for i in range(10)]
        open(os.path.join(data, "raw", "seasonal", "M0_daily.csv"), "w").write("date,open,high,low,close,volume,hold,settle\n" + "\n".join(f"{dd},{p},{p},{p},{p},1,1,0" for dd, p in zip(days, px)))
        json.dump({"d": days, "i": [round(p / px[0] * 100, 5) for p in px], "k": ["m2701"] * len(days)}, open(os.path.join(data, "main_adj.json"), "w"))
        json.dump({"marketCapital": {"members": {"摩根大通": {"foreign": True, "history": {"change5": {"change": 5000, "to": days[-1]}}}}}}, open(os.path.join(data, "latest.json"), "w"))
        out = os.path.join(d, "a.json")
        subprocess.run(["node", os.path.join(root, "scripts", "plan_alert.js"), "--data", data, "--out", out, "--today", days[-1]], check=True, capture_output=True)
        a = json.load(open(out))
        assert a["gate"]["ok"] and a["side"] == 1 and a["events"][0]["type"] == "entry" and "做多" in a["events"][0]["title"], a
        # 持仓：空单开在 2200，价格涨到 2380（−8%）→ 止损
        pos = os.path.join(d, "position.json"); json.dump({"side": -1, "lots": 3, "entryD": days[-10], "entryPx": 2200}, open(pos, "w"))
        subprocess.run(["node", os.path.join(root, "scripts", "plan_alert.js"), "--data", data, "--position", pos, "--out", out, "--today", days[-1]], check=True, capture_output=True)
        b = json.load(open(out)); assert b["position"] and b["manage"]["action"] == "止损" and [e["type"] for e in b["events"]] == ["exit"], b
        # 缺换月调整价 → 数据不足事件
        os.remove(os.path.join(data, "main_adj.json"))
        subprocess.run(["node", os.path.join(root, "scripts", "plan_alert.js"), "--data", data, "--out", out, "--today", days[-1]], check=True, capture_output=True)
        c = json.load(open(out)); assert not c["gate"]["ok"] and c["events"][0]["type"] == "gate" and c["side"] == 0, c
        # 全流程：notify 用假渠道
        st, rep = na.run(a, {}, {}, days[-1], {"x": Rec()}); assert rep["sent"]
    finally: shutil.rmtree(d, ignore_errors=True)
    ok("端到端：合成数据 → node 算出做多信号/止损离场/数据不足 → 发送记账")

def test_workflows_wired():
    root = os.path.dirname(os.path.abspath(__file__))
    w = open(os.path.join(root, ".github", "workflows", "update-data.yml"), encoding="utf-8").read()
    assert "issues: write" in w and "scripts/plan_alert.js" in w and "notify_alert.py" in w and "SERVERCHAN_KEY" in w and "PUSHPLUS_TOKEN" in w and "SMTP_PASS" in w
    assert "data/main_adj.json" in w and "data/alert_state.json" in w and w.index("plan_alert.js") < w.index("提交更新后的数据文件")
    r = open(os.path.join(root, ".github", "workflows", "record-position.yml"), encoding="utf-8").read()
    assert "workflow_dispatch" in r and "record_position.py" in r and "group: data-writes" in r and "data/position.json" in r
    ok("工作流接线：提醒步骤在提交之前、有 issues 权限和各渠道密钥；记录持仓工作流共用并发组")

if __name__ == "__main__":
    import traceback
    fails = []
    for n, t in list(globals().items()):
        if n.startswith("test_") and callable(t):
            try: t()
            except Exception:
                fails.append(n); print("❌", n); traceback.print_exc()
    print(f"\n结果：{_pass}项通过，{len(fails)}项失败" + (f"：{fails}" if fails else "")); sys.exit(1 if fails else 0)
