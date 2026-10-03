# -*- coding: utf-8 -*-
"""数据同步停止的主动警告(sync_watchdog.py)：与页面的syncHealth同口径 + 决定怎么通知。运行：python3 test_sync_watchdog.py"""
import os, sys, json, subprocess, shutil, tempfile, traceback, re
from datetime import datetime, timezone, timedelta, date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cn_calendar as cc
import sync_watchdog as sw

_pass = 0
_skipped = []          # 被跳过的测试(没装jsdom时与真实JS函数的对拍)——必须在汇总里点名，不能让"全部通过"掩盖"最重要的那条没跑"
HERE = os.path.dirname(os.path.abspath(__file__))
BJ = timezone(timedelta(hours=8))


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def bj(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=BJ)


# ===================== 休市日历：与index.html不能漂移 =====================
def test_closures_in_python_match_index_html_exactly():
    """★年底更新日历时只改了一边(比如只改index.html)会让页面和看门狗对"今天是不是交易日"的判断不一致——这条测试会立刻失败。"""
    html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    i = html.index("const DCE_CLOSURES")
    block = html[i: html.index("];", i)]
    js = [(m.group(1), m.group(2)) for m in re.finditer(r"\{from:'(\d{4}-\d{2}-\d{2})',\s*to:'(\d{4}-\d{2}-\d{2})'", block)]
    py = [(a, b) for a, b in cc.DCE_CLOSURES]
    assert js and js == py, f"index.html={js}  cn_calendar={py}"
    m = re.search(r"EVENT_CALENDAR_END = '([^']+)'", html)
    assert m.group(1) == cc.EVENT_CALENDAR_END, "日历截止日也要一致"
    ok(f"休市表与index.html完全一致({js})，日历截止日一致({cc.EVENT_CALENDAR_END})——年底只改一边会立刻失败")


def test_is_trading_day_weekends_and_closures():
    t = cc.dce_is_trading_day
    assert t(date(2026, 9, 30)) is True and t(date(2026, 10, 8)) is True
    assert t(date(2026, 10, 3)) is False and t(date(2026, 10, 4)) is False, "周末"
    assert all(t(date(2026, 10, d)) is False for d in range(1, 8)), "国庆休市10-01~10-07(含周三到周五)"
    assert t(date(2026, 9, 30)) and not t(date(2026, 10, 1)) and t(date(2026, 10, 8)), "边界"
    ok("交易日判断：周末、国庆休市(10-01~10-07)不是；09-30、10-08是")


# ===================== 与页面的tradingDaysMissed对拍(调用真实的JS函数) =====================
JSDOM_PATH = os.environ.get("NODE_PATH", "")


def js_missed_batch(cases):
    """用jsdom加载真实页面，对每个(数据日期, 现在的北京时间ms)调用真实的tradingDaysMissed。返回[miss...]。没有node/jsdom时返回None。"""
    if not shutil.which("node"):
        return None
    script = r"""
const {JSDOM, VirtualConsole} = require('jsdom'); const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8').replace(/<script[^>]+src="https?:\/\/[^"]*"[^>]*><\/script>/g, '');
const cases = JSON.parse(process.argv[2]);
const dom = new JSDOM(html, {runScripts:'dangerously', url:'http://localhost/', virtualConsole:new VirtualConsole(), beforeParse(w){ w.fetch = async()=>({ok:false}); }});
setTimeout(()=>{ const w = dom.window; const out = cases.map(c=>w.tradingDaysMissed(c[0], c[1])); console.log(JSON.stringify(out)); process.exit(0); }, 400);
"""
    p = subprocess.run(["node", "-e", script, os.path.join(HERE, "index.html"), json.dumps(cases)], capture_output=True, text=True, timeout=60, env=os.environ)
    if "Cannot find module 'jsdom'" in p.stderr:
        return None                                        # 确实没装jsdom：允许跳过(运行器会点名)
    assert p.returncode == 0 and p.stdout.strip(), f"对拍用的Node脚本自己出错了(这不是'没装jsdom')：{p.stderr[:300]}"   # 脚本坏了必须失败，不能悄悄当成跳过——这正是上一版的bug
    return json.loads(p.stdout.strip().split("\n")[-1])


def test_python_missed_days_equals_the_real_js_function_pointwise():
    """★对拍：Python的trading_days_missed与页面里真实的tradingDaysMissed逐点比较。覆盖：18:00前后、周末、国庆、数据落在休市日、跨月/跨年。"""
    cases = []
    for data_day in ("2026-09-25", "2026-09-28", "2026-09-30", "2026-10-02", "2026-10-03", "2026-10-08", "2026-12-31", "2026-01-02", "2026-02-17"):
        for now in (bj(2026, 9, 29, 10), bj(2026, 9, 30, 17, 59), bj(2026, 9, 30, 18, 0), bj(2026, 10, 1, 9), bj(2026, 10, 5, 12), bj(2026, 10, 8, 9), bj(2026, 10, 9, 18), bj(2026, 10, 12, 10), bj(2026, 11, 2, 9), bj(2027, 1, 4, 20)):
            cases.append((data_day, now))
    js = js_missed_batch([(d, int(n.timestamp() * 1000)) for d, n in cases])
    if js is None:
        _skipped.append("与页面真实tradingDaysMissed的逐点对拍(没装jsdom：NODE_PATH=<含jsdom的node_modules> python3 test_sync_watchdog.py)")
        print("⏭️ 没有node/jsdom：跳过与真实JS函数的对拍(其余测试照常，汇总里会点名)")
        return
    py = [sw.trading_days_missed(d, n) for d, n in cases]
    diff = [(c, a, b) for c, a, b in zip(cases, py, js) if a != b]
    assert not diff, f"Python与JS不一致{len(diff)}处，前3个: {[(c[0], c[1].isoformat(), a, b) for c, a, b in diff[:3]]}"
    ok(f"★与页面里真实的tradingDaysMissed逐点一致：{len(cases)}个组合(18:00前后、周末、国庆、数据落在休市日、跨月跨年)")


def test_generated_at_timezone_is_converted_to_beijing_before_taking_the_date():
    """★变异检查发现原测试的generatedAt都是北京下午，换成UTC日期结果相同。真正会不同的是北京凌晨(UTC还是前一天)：
    2026-10-08T17:30:00Z = 北京10-09(周五)01:30，数据所在交易日是10-09。现在=10-14(周三)18:00：
      按北京日期10-09：错过10-12、10-13、10-14 = 3 → degraded；若误当UTC日期10-08：多算10-09 = 4 → stale。"""
    G = "2026-10-08T17:30:00+00:00"
    a = sw.assess(G, bj(2026, 10, 14, 18))
    assert a["missed"] == 3 and a["state"] == "degraded" and "2026-10-09 01:30" in a["label"], a
    a2 = sw.assess("2026-10-08T17:30:00Z", bj(2026, 10, 14, 18))
    assert (a2["missed"], a2["state"]) == (3, "degraded"), "'Z'结尾写法同样"
    ok("★generatedAt先转北京时间再取日期(手算：UTC 10-08 17:30=北京10-09 01:30，到10-14 18:00错过3个，不是误当UTC日期的4个)")


def test_naive_timestamp_is_treated_as_utc_defensive_branch():
    """latest.json里的generatedAt由Python写，带时区(+00:00)，所以无时区的情形实际不会出现，这是防御分支：无时区一律按UTC。
    2026-10-08T17:30:00(无时区)按UTC=北京10-09 01:30 → 到10-14 18:00错过3个；若误按北京=10-08 17:30 → 错过4个。"""
    a = sw.assess("2026-10-08T17:30:00", bj(2026, 10, 14, 18))
    assert (a["missed"], a["state"]) == (3, "degraded"), a
    ok("无时区的时间戳按UTC处理(防御分支；手算：按UTC错过3个，误按北京是4个)")


def test_lookback_to_previous_trading_day_is_mathematically_a_noop_but_kept_for_parity():
    """变异检查里"数据落在休市日不往前找/只往前找2天"没被任何测试抓到——不是测试漏洞，是等价变异：往前找是遇到第一个交易日即停，
    而数据日之后被数的只有交易日，休市日本来就不计入，所以起点挪到更早的休市日之前不改变计数。
    实证(暴力搜索)：随机20000组(数据日×现在)+数据日在休市日的专门组合440组，结果一次都没有不同。
    页面的tradingDaysMissed里有这个循环，这里保留它是为了和页面逐行一致(便于对照)，不是因为它有可观察的效果。这里重做一次小规模验证，防止以后改了日历逻辑让这个结论失效。"""
    import random
    def no_lookback(ds, now):
        y, m, d = (int(x) for x in ds[:10].split("-"))
        d0 = date(y, m, d)
        nb = now.astimezone(BJ)
        as_of = date(nb.year, nb.month, nb.day) - (timedelta(0) if nb.hour >= 18 else timedelta(days=1))
        miss, t = 0, d0 + timedelta(days=1)
        while t <= as_of and miss < 60:
            if cc.dce_is_trading_day(t):
                miss += 1
            t += timedelta(days=1)
        return miss
    random.seed(7)
    for _ in range(3000):
        dd = date(2026, 1, 1) + timedelta(days=random.randint(0, 360))
        now = datetime(2026, 1, 1, tzinfo=BJ) + timedelta(days=random.randint(0, 400), hours=random.randint(0, 23))
        assert sw.trading_days_missed(dd.isoformat(), now) == no_lookback(dd.isoformat(), now), (dd, now)
    for dd in [date(2026, 10, d) for d in range(1, 8)] + [date(2026, 10, 3), date(2026, 9, 27)]:
        for k in range(30):
            now = datetime(2026, 9, 25, tzinfo=BJ) + timedelta(days=k, hours=19)
            assert sw.trading_days_missed(dd.isoformat(), now) == no_lookback(dd.isoformat(), now)
    ok("往前找前一个交易日在数学上不改变结果(3000组随机+休市日专门组合全部相同)——所以相关变异是等价变异，不是测试漏洞")


# ===================== 阈值与状态(与页面syncHealth一致) =====================
def gen(dt):
    return dt.astimezone(timezone.utc).isoformat()


def test_assess_thresholds_match_the_page():
    """手算(数据日期2026-10-08周四，国庆后第一个交易日，收盘后同步)：截止点=北京时间18:00前算到昨天、18:00后算到今天；
    只数数据日之后的交易日(周末不算)。
      10-09(周五)18:00 → 截止10-09 → {10-09}                 = 1 → ok
      10-12(周一)09:00 → 截止10-11(周日) → {10-09}             = 1 → ok      (周末不算！)
      10-12(周一)18:00 → 截止10-12 → {10-09, 10-12}            = 2 → degraded
      10-13(周二)18:00 → 截止10-13 → {10-09, 10-12, 10-13}     = 3 → degraded
      10-14(周三)18:00 → 截止10-14 → 再加10-14                 = 4 → stale"""
    G = gen(bj(2026, 10, 8, 15, 5))
    for now, state, miss in [(bj(2026, 10, 8, 16), "ok", 0), (bj(2026, 10, 9, 10), "ok", 0), (bj(2026, 10, 9, 18), "ok", 1), (bj(2026, 10, 12, 9), "ok", 1),
                             (bj(2026, 10, 12, 18), "degraded", 2), (bj(2026, 10, 13, 18), "degraded", 3), (bj(2026, 10, 14, 18), "stale", 4), (bj(2026, 10, 20, 9), "stale", 7)]:
        a = sw.assess(G, now)
        assert (a["state"], a["missed"]) == (state, miss), (now.isoformat(), a["state"], a["missed"], "期望", state, miss)
    # 18:00的边界：17:59算到昨天，18:00算到今天
    assert sw.assess(G, bj(2026, 10, 12, 17, 59))["missed"] == 1 and sw.assess(G, bj(2026, 10, 12, 18, 0))["missed"] == 2
    ok("★阈值与页面一致(手算8个时点)：错过≤1=ok、2~3=degraded、≥4=stale；周末不算；18:00前后差1个交易日(17:59→1，18:00→2)")


def test_weekend_and_holiday_never_trigger_a_false_alarm():
    """★最重要的防误报：周末、国庆休市期间同步本来就不更新(工作流只在交易时段跑)，不能报警。"""
    G = gen(bj(2026, 9, 30, 15, 5))                                       # 国庆前最后一个交易日(周三)收盘后同步
    for now in (bj(2026, 10, 1, 10), bj(2026, 10, 3, 12), bj(2026, 10, 5, 9), bj(2026, 10, 7, 20), bj(2026, 10, 8, 8)):
        a = sw.assess(G, now)
        assert a["state"] == "ok", (now, a)
    Gfri = gen(bj(2026, 9, 25, 15, 5))                                    # 周五收盘后
    for now in (bj(2026, 9, 26, 12), bj(2026, 9, 27, 12), bj(2026, 9, 28, 8)):
        assert sw.assess(Gfri, now)["state"] == "ok", now
    ok("★不误报：周末、国庆休市期间(10-01~10-08早上)、周五收盘后到周一早上，状态都是ok")


def test_missing_or_garbage_generated_at_is_nodata_and_alerts():
    for g in (None, "", "乱码", "2026-13-45T00:00:00Z", 12345):
        a = sw.assess(g, bj(2026, 9, 30, 10))
        assert a["state"] == "nodata" and a["alert"] is True, (g, a)
    ok("generatedAt缺失/乱码：state=nodata且要报警(同步坏到连时间戳都没有，比晚了更严重)")


def test_alert_levels():
    G = gen(bj(2026, 10, 8, 15, 5))
    assert sw.assess(G, bj(2026, 10, 12, 9))["alert"] is False, "错过1个：不报警"
    a2 = sw.assess(G, bj(2026, 10, 12, 18))
    assert a2["state"] == "degraded" and a2["alert"] is True and a2["severity"] == "degraded", "错过2个：报警(degraded)——已经是明确的异常"
    a4 = sw.assess(G, bj(2026, 10, 14, 18))
    assert a4["state"] == "stale" and a4["alert"] is True and a4["severity"] == "stale", "错过4个：报警且级别更高"
    ok("报警级别：ok(≤1)不报；degraded(2~3)报；stale(≥4)报且级别更高")


# ===================== 决定怎么通知(开/保持/关) =====================
def test_decide_action_matrix():
    d = sw.decide_action
    assert d(alert=True, open_issue=False) == "open"
    assert d(alert=True, open_issue=True) == "keep", "已有未关闭的issue：不重复开(失败邮件每天仍会提醒)"
    assert d(alert=False, open_issue=True) == "close", "恢复后自动关闭"
    assert d(alert=False, open_issue=False) == "none"
    ok("通知决策：报警且没有issue→开；已有→不重复开；恢复且有未关issue→关；都没事→什么都不做")


# ===================== 命令行 =====================
def test_cli_outputs_and_exit_codes():
    with tempfile.TemporaryDirectory() as d:
        lp = os.path.join(d, "latest.json")
        json.dump({"generatedAt": gen(bj(2026, 10, 8, 15, 5))}, open(lp, "w"))
        def run(now_iso, extra=()):
            return subprocess.run([sys.executable, os.path.join(HERE, "sync_watchdog.py"), "--latest", lp, "--now", now_iso, *extra], capture_output=True, text=True)
        r = run(bj(2026, 10, 9, 18).isoformat())
        assert r.returncode == 0 and json.loads(r.stdout.strip().split("\n")[-1])["state"] == "ok"
        r = run(bj(2026, 10, 15, 18).isoformat())
        out = json.loads(r.stdout.strip().split("\n")[-1])
        assert r.returncode == 1 and out["state"] == "stale" and out["alert"] is True, (r.returncode, out)
        r = run(bj(2026, 10, 12, 18).isoformat(), ("--no-fail",))                       # 错过2个→alert=True，但--no-fail仍以0退出
        assert r.returncode == 0 and json.loads(r.stdout.strip().split("\n")[-1])["alert"] is True, "--no-fail：只输出结果、不以非0退出"
        r = run(bj(2026, 10, 12, 18).isoformat())
        assert r.returncode == 1, "对照：同样的时点不加--no-fail，报警时退出1"
        r2 = subprocess.run([sys.executable, os.path.join(HERE, "sync_watchdog.py"), "--latest", os.path.join(d, "不存在.json"), "--now", bj(2026, 10, 9, 18).isoformat()], capture_output=True, text=True)
        out2 = json.loads(r2.stdout.strip().split("\n")[-1])
        assert r2.returncode == 1 and out2["state"] == "nodata" and out2["alert"] is True, "latest.json不存在也要报警，不是崩溃"
        open(lp, "w").write("{坏json")
        r3 = run(bj(2026, 10, 9, 18).isoformat())
        assert r3.returncode == 1 and json.loads(r3.stdout.strip().split("\n")[-1])["state"] == "nodata"
    ok("命令行：ok退出0；报警时退出1(让工作流变红，GitHub默认会发失败邮件)；--no-fail只输出；latest.json缺失/坏了也报警而不是崩溃")


# ===================== 工作流 =====================
def _wf():
    import yaml
    return yaml.safe_load(open(os.path.join(HERE, ".github", "workflows", "sync-watchdog.yml"), encoding="utf-8")), open(os.path.join(HERE, ".github", "workflows", "sync-watchdog.yml"), encoding="utf-8").read()


def test_workflow_is_independent_minimal_permission_and_scheduled_daily():
    w, raw = _wf()
    tr = w.get(True) or w.get("on")
    assert "schedule" in tr and "workflow_dispatch" in tr, "定时 + 可手动触发"
    crons = [c["cron"] for c in tr["schedule"]]
    assert crons == ["30 2 * * *"], f"★每天一次、固定时间(UTC 02:30=北京10:30)、含周末——是否交易日由脚本自己判断，不会误报；写成每小时会每小时发邮件: {crons}"
    assert (w.get("concurrency") or {}).get("group") != "data-writes", "★不能和更新/回填共用并发组：看门狗不写数据，共用了会被排队甚至被取消——数据同步卡住时正是它最需要运行的时候"
    perms = w.get("permissions")
    assert perms == {"contents": "read", "issues": "write"}, f"最小权限：只读代码+写issue，不碰其他: {perms}"
    assert "secrets." not in raw.replace("secrets.GITHUB_TOKEN", ""), "不使用任何自定义密钥"
    ok(f"工作流：定时每天一次({crons[0]})+可手动；不在data-writes并发组；权限只有contents:read+issues:write；不用自定义密钥")


def test_workflow_steps_assess_then_notify_then_fail_loudly():
    w, raw = _wf()
    job = list(w["jobs"].values())[0]
    steps = job["steps"]
    names = [st.get("name", "") for st in steps]
    run_all = "\n".join(st.get("run", "") for st in steps)
    i_assess = next(i for i, st in enumerate(steps) if "sync_watchdog.py" in st.get("run", ""))
    assert steps[i_assess].get("id") == "assess" and "--no-fail" in steps[i_assess]["run"], "先拿到评估结果(--no-fail)，再决定怎么通知"
    assert "--latest data/latest.json" in steps[i_assess]["run"]
    uses = [st.get("uses", "") for st in steps if st.get("uses")]
    assert any(u.startswith("actions/checkout@") for u in uses), "需要检出代码(读latest.json)"
    assert not any(u.startswith("actions/setup-python") or u.startswith("actions/setup-node") for u in uses), "看门狗只用标准库(sync_watchdog.py)，不装任何依赖——依赖装不上本身就不该让看门狗失效"
    # 通知：开issue / 关issue
    assert "gh issue create" in run_all and "gh issue close" in run_all and "gh issue list" in run_all
    by_id_steps = {st["id"]: st["run"] for st in steps if st.get("id")}
    assert "gh issue list --label sync-stalled --state open --json number --jq 'length'" in by_id_steps["existing"], "★'找已有issue'(existing步骤)必须带固定标签，否则找不到→每天重复开(之前只在整个文件里搜子串，关issue那一步也有同样的子串，删掉这里的标签测试仍通过)"
    assert "gh issue list --label sync-stalled --state open --json number --jq '.[].number'" in by_id_steps["close_issue"], "★关issue(close_issue步骤)列出的也必须带标签，否则会把别的issue也关掉"
    assert "gh issue create --label sync-stalled" in run_all, "★开issue也必须带同一个标签，否则下次找不到它"

    # 最后一步：报警时让整次运行变红(GitHub默认会发失败邮件)
    last = steps[-1]
    assert "exit 1" in last["run"] and "alert" in (last.get("if", "") + last["run"]), "最后一步报警时exit 1，运行变红 → GitHub失败邮件"
    assert last.get("if") == "always() && steps.assess.outputs.alert == 'true'", f"★精确：报警(alert=='true')时才变红，且用always()保证前面开issue失败也变红。写反会变成'同步正常时每天报红、故障时反而不报红': {last.get('if')}"
    ok("工作流步骤：评估(--no-fail)→开/关issue(固定标签防重复)→最后一步报警时exit 1(always()，开issue失败也变红)")


def test_workflow_decision_logic_matches_decide_action():
    """工作流里用shell实现的"开/保持/关"必须和decide_action一致：这里把YAML里的条件逐项对照decide_action的真值表。"""
    w, raw = _wf()
    job = list(w["jobs"].values())[0]
    by_id = {st["id"]: st for st in job["steps"] if st.get("id")}              # 按稳定的id取，不按中文名子串(上一版用"关"字匹配，"未关闭"也含"关"，取错了步骤)
    open_step = by_id["open_issue"]["if"]
    close_step = by_id["close_issue"]["if"]
    # 开：报警 且 没有未关闭的issue；关：没报警 且 有未关闭的issue
    assert "alert == 'true'" in open_step and "open_issue != 'true'" in open_step and "alert != 'true'" not in open_step, open_step
    assert "alert != 'true'" in close_step and "open_issue == 'true'" in close_step, close_step
    for alert, issue in [(True, False), (True, True), (False, True), (False, False)]:
        act = sw.decide_action(alert, issue)
        runs_open = alert and not issue
        runs_close = (not alert) and issue
        assert (act == "open") == runs_open and (act == "close") == runs_close, (alert, issue, act)
    ok("工作流里'开/关issue'的条件与decide_action的真值表逐项一致")


def test_workflow_issue_text_names_the_state_and_what_to_check():
    w, raw = _wf()
    assert "同步" in raw and "GitHub Actions" in raw and "更新豆粕基本面数据" in raw, "issue正文要点名要去看哪个工作流"
    w2 = w
    step = next(st for st in list(w2["jobs"].values())[0]["steps"] if st.get("id") == "open_issue")
    run = step["run"]
    body = run[run.index("BODY="):run.index("gh issue create")]
    assert "${W_STATE}" in body and "${W_LABEL}" in body and "${W_DETAIL}" in body, "★issue**正文**(BODY=…里)带状态、标签、建议(标题里也有label，不能只在整个文件里搜)"
    assert "恢复后看门狗会自动关闭" in body and '--body "$BODY"' in run
    assert step["env"]["W_STATE"] == "${{ steps.assess.outputs.state }}" and step["env"]["W_LABEL"] == "${{ steps.assess.outputs.label }}" and step["env"]["W_DETAIL"] == "${{ steps.assess.outputs.detail }}", "环境变量从评估结果取值"
    # ★安全写法：run里不能直接内插${{ ... }}(GitHub官方警告的脚本注入模式)；值只通过env传入
    for st in list(w2["jobs"].values())[0]["steps"]:
        assert "${{" not in st.get("run", ""), f"步骤'{st.get('name')}'的run里直接内插了表达式，应通过env传值: {st['run'][:80]}"
    ok("issue正文写明状态和要检查什么")


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
    print(f"\n结果：{_pass}项通过，{len(fails)}项失败" + (f"：{fails}" if fails else "") + (f"，{len(_skipped)}项被跳过" if _skipped else ""))
    for sk in _skipped:
        print("⚠️ 被跳过：" + sk + "——这是看门狗最重要的一条验证(Python与页面口径一致)，不要在没跑过它的情况下相信结果")
    sys.exit(1 if fails else 0)
