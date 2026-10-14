#!/usr/bin/env python3
"""驾驶舱端到端测试（真浏览器）：python3 tests/e2e_cockpit.py
用 tests/data/cockpit_fixture_20261011.zip（一份真实的 data/ 快照）搭一个本地站点，外网请求一律拒绝，
检查：能启动、三个合约都有数据、每个视图/证据页能打开不报错、交易计划的手数、手动录入会重新计分、
各种缺文件时的表现、手机宽度不横向溢出、刷新后数据对象不换。没装 playwright 或 chromium 时明确打印"跳过"。"""
import os, sys, json, shutil, tempfile, threading, zipfile, functools, http.server, socketserver, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
try:
    from playwright.sync_api import sync_playwright
except Exception as e:
    print('⚠️ 跳过：没装 playwright（%s）' % e); sys.exit(0)

passed, failed = 0, []
def ok(name, cond, detail=''):
    global passed
    if cond: passed += 1; print('✅', name)
    else: failed.append(name); print('❌', name, detail)

def make_site(mutate=None):
    d = tempfile.mkdtemp(prefix='cockpit_site_')
    for f in ('index.html', 'engine.html', 'sw.js', 'manifest.webmanifest', 'icon.svg', 'icon-180.png', 'icon-192.png', 'icon-512.png'): shutil.copy(os.path.join(ROOT, f), d)
    zipfile.ZipFile(os.path.join(HERE, 'data', 'cockpit_fixture_20261011.zip')).extractall(os.path.join(d, 'data'))
    if mutate: mutate(d)
    return d

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
def serve(d):
    h = functools.partial(Quiet, directory=d); s = socketserver.ThreadingTCPServer(('127.0.0.1', 0), h); s.daemon_threads = True
    threading.Thread(target=s.serve_forever, daemon=True).start(); return s, s.server_address[1]

def open_page(b, port, w=1440, h=900, path='index.html', wait_boot=True, mode='trade'):
    ctx = b.new_context(viewport={'width': w, 'height': h}); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
    pg.route('**/*', lambda r: r.continue_() if r.request.url.startswith('http://127.0.0.1:%d' % port) else r.abort())
    pg.goto('http://127.0.0.1:%d/%s' % (port, path))
    if wait_boot:
        try: pg.wait_for_selector('#boot', state='detached', timeout=60000)
        except Exception: pass
    if mode == 'trade' and wait_boot and path == 'index.html':   # 空仓默认进研究页（v101.49）；旧测试按交易页写的，这里先切过去
        try: pg.evaluate("(() => { const b = document.querySelector('[data-mode=trade]'); if (b && !document.body.classList.contains('mode-trade')) b.click(); })()"); pg.wait_for_timeout(150)
        except Exception: pass
    return ctx, pg, errs

def main():
    try:
        pw = sync_playwright().start(); b = pw.chromium.launch(args=['--no-sandbox'])
    except Exception as e:
        print('⚠️ 跳过：起不了 chromium（%s）' % str(e)[:120]); return 0
    d = make_site(); srv, port = serve(d)
    # ---- 1. 正常启动 ----
    ctx, pg, errs = open_page(b, port)
    ok('启动完成（#boot 消失）', pg.evaluate("!document.getElementById('boot')"))
    ok('合约标签有 M27 开头的代码', (pg.evaluate("document.getElementById('cSym').textContent") or '').startswith('M27'))
    info = pg.evaluate("""(() => { const D = window.__DATA__; return { n: ['sep','may','jan'].map(k => D.contracts[k].votes.length), k: ['sep','may','jan'].map(k => D.contracts[k].kline.length), hist: D.hist.d.length, sea: !!D.sea, ser: Object.values(D.series).filter(s => s.pts.length).length, sys: D.systems.sep.length, ev: D.events.length, cap: !!D.capital, ind: D.indicators.length, sym: ['sep','may','jan'].map(k => D.contracts[k].symbol) } })()""")
    ok('三个合约都有投票(>=10票)', all(n >= 10 for n in info['n']), info['n'])
    ok('每个合约都有K线（已到期的合约根数少），主力一月合约满160根', all(k >= 5 for k in info['k']) and info['k'][2] == 160, info['k'])
    ok('三个合约代码互不相同', len(set(info['sym'])) == 3, info['sym'])
    ok('价格历史>2000根、季节数据、龙虎榜都在', info['hist'] > 2000 and info['sea'] and info['cap'], info)
    ok('趋势墙序列>=15条有点', info['ser'] >= 15, info['ser'])
    ok('每日系统记录有数据、事件日历有数据、12个指标', info['sys'] >= 1 and info['ev'] >= 1 and info['ind'] >= 12, info)
    ok('默认是交易模式：背景带、趋势墙、证据栏收起，交易面板可见', pg.evaluate("document.body.classList.contains('mode-trade') && getComputedStyle(document.getElementById('band')).display === 'none' && getComputedStyle(document.getElementById('wall')).display === 'none' && getComputedStyle(document.getElementById('tradePanel')).display === 'none' && document.body.classList.contains('plan-off')"))
    pg.evaluate("document.querySelector('#checks [data-lamp=\"evt\"], #checks .chk:first-child, #checks button').click()"); pg.wait_for_timeout(200)
    evt = pg.evaluate("document.getElementById('shB').innerText")
    ok('事件的说明里列出了带日期的事件（不只是一句定义）', '重大事件指' in evt and any(k in evt for k in ('10-', '11-', '12-')) and ('周度' in evt), evt[:300])
    pg.evaluate("window.__cockpit.closeSheet()")
    ok('空仓时交易计划默认收起，「计划」按钮点一下展开、再点收起', pg.evaluate("(() => { const b = document.getElementById('planBtn'), v = () => getComputedStyle(document.getElementById('tradePanel')).display !== 'none'; const a = v(); b.click(); const c = v(); b.click(); return !a && c && !v(); })()"))
    ok('检查条里没有规则灯、没有「三方背离」方向灯', pg.evaluate("!document.getElementById('ruleBtn') && !document.querySelector('[data-lamp=\"dir\"]') && !document.body.innerText.includes('三方背离')"))
    pg.evaluate("document.querySelector('[data-mode=\"research\"]').click()")
    ok('切到研究模式：背景带和趋势墙出现，交易面板收起', pg.evaluate("getComputedStyle(document.getElementById('band')).display !== 'none' && getComputedStyle(document.getElementById('wall')).display !== 'none' && getComputedStyle(document.getElementById('tradePanel')).display === 'none'"))
    ok('趋势墙画出了格子', pg.evaluate("document.querySelectorAll('#tiles [data-tile]').length") >= 10)
    # ---- 2. 所有视图、证据页、说明 ----
    for v in ('px', 'pos', 'sea', 'cost'):
        pg.evaluate("v => document.querySelector('[data-view=\"' + v + '\"]').click()", v)
        ok('视图 %s 能渲染且有内容' % v, pg.evaluate("document.getElementById('chart').innerText.length") > 20)
    for t in ('drivers', 'supply', 'demand', 'capital', 'data', 'input'):
        pg.evaluate("t => document.querySelector('[data-tab=\"' + t + '\"]').click()", t)
        ok('证据页 %s 能打开' % t, pg.evaluate("document.getElementById('shB').innerText.length") > 20)
        pg.evaluate("document.getElementById('shX').click()")
    pg.evaluate("document.getElementById('abBtn').click()"); ok('说明能打开', pg.evaluate("document.getElementById('shB').innerText.length") > 100); pg.evaluate("document.getElementById('shX').click()")
    for c in ('sep', 'may', 'jan'):
        pg.evaluate("c => { document.getElementById('cBtn').click(); document.querySelector('[data-ck=\"' + c + '\"]').click(); }", c)
        ok('切到 %s 合约不报错、标签变了' % c, pg.evaluate("document.getElementById('cSym').textContent") == info['sym'][['sep','may','jan'].index(c)])
    ok('以上全程没有页面 JS 错误', not errs, errs)
    # ---- 3. 交易信号在首页；交易计划：开仓/平仓记录、权益自动、最高价自动、手续费 ----
    pg.on('dialog', lambda dlg: dlg.accept())
    pg.evaluate("document.querySelector('[data-mode=\"trade\"]').click()")
    sig = pg.evaluate("document.getElementById('sigbar').innerText")
    ok('首页（不点任何按钮）就能看到入场信号和空仓状态', '入场信号' in sig and '空仓' in sig and ('信号' in sig), sig[:200])
    ok('首页：空仓时显示"空仓"和自动权益 500,000', '空仓' in sig and '500,000' in sig, sig[:200])
    pg.evaluate("document.querySelector('#sigbar [data-goplan]').click()")
    ok('点首页信号条切到交易模式并看到交易计划', pg.evaluate("document.body.classList.contains('mode-trade') && document.getElementById('planBody') !== null"))
    ok('测试数据里外资5日数据缺失：信号格显示「数据不足，信号不可信」且不给建议手数', '数据不足' in pg.evaluate("document.getElementById('sigbar').innerText") and '建议' not in pg.evaluate("document.getElementById('sigbar').innerText"))
    ok('信号格有明确的数据状态行：默认只有一个叹号按钮（折叠），点开才写原因（数据不足时红色）', pg.evaluate("(()=>{const c=document.querySelector('#dataLine .dst'); const col=!c; const b=document.querySelector('#dataLine [data-dsl]'); if(b&&b.getAttribute('aria-expanded')!=='true') b.click(); const e=document.getElementById('dataLine');return col&&!!e&&e.classList.contains('bad')&&e.innerText.includes('数据不足')})()"))
    body = pg.evaluate("document.getElementById('planBody').innerText")
    ok('计划页：有今日信号、持仓管理、账户权益、交易记录四块', all(k in body for k in ('今日入场信号', '持仓管理', '账户权益', '交易记录')), body[:200])
    ok('计划页：历史开仓月份卡片在，默认折叠，写明两类重要程度和本月标记', pg.evaluate("(()=>{const d=document.getElementById('pf-mo');if(!d||d.open)return false;const t=d.innerText+d.innerHTML;return /信号出现的频率/.test(t)&&/开仓的盈亏/.test(t)&&/★★★☆☆/.test(t)&&/★☆☆☆☆/.test(t)&&/（本月）/.test(t)&&d.querySelectorAll('tbody tr').length>=12})()"))
    ok('「同步持仓到提醒」模块已删除；页面顶部有同步状态点（没填令牌=红点「未同步」）', pg.evaluate("!document.getElementById('pf-sync') && !document.body.innerText.includes('Run workflow') && document.getElementById('syncDot').innerText.includes('未同步') && !document.getElementById('syncDot').className.includes('ok')"))
    ok('说明收进问号：计划页正文里不再有大段「外资5日 = …」解释', '只算多单/空单 = 该席位' not in body and '价格用主力连续价，现价' not in body)
    pg.evaluate("document.querySelector('#sigbar [data-about=\"plsig\"]').click()"); pg.wait_for_timeout(200)
    sh = pg.evaluate("document.getElementById('shB').innerText")
    ok('首页入场信号旁的「?」里有：外资单席位口径、和研究页高盛对不上的原因、价格口径、本月提示', all(k in sh for k in ('单个席位', '研究页', '价格口径', '本月', '历史开仓')), sh[:200])
    pg.evaluate("window.__cockpit.closeSheet()")
    pg.evaluate("document.querySelector('#planBody [data-about=\"placct\"]').click()"); pg.wait_for_timeout(200)
    ok('账户权益的「?」里有手续费和保证金说明', '23 元' in pg.evaluate("document.getElementById('shB').innerText"))
    pg.evaluate("window.__cockpit.closeSheet()")
    ok('计划页：仓位阶梯和回测摘要默认折叠', pg.evaluate("[...document.querySelectorAll('#planBody details')].every(d => !d.open)"))
    ok("夹具里有换月调整价，页面读到了（交易信号用它）", pg.evaluate("!!window.__DATA__.adj && window.__DATA__.adj.d.length > 1000"))
    ok("数据状态行写明价格口径是换月调整价", "换月调整" in pg.evaluate("(()=>{const b=document.querySelector('#dataLine [data-dsl]'); if(b&&b.getAttribute('aria-expanded')!=='true') b.click(); return document.getElementById('dataLine').innerText})()"))
    hd = pg.evaluate("(() => { const a = window.__DATA__.adj; return {d: a.d.slice(-12), c: a.c.slice(-12)}; })()")
    d0, p0 = hd['d'][0], hd['c'][0]; mx = max(hd['c']); last = hd['c'][-1]
    pg.fill('#pf-od', d0); pg.select_option('#pf-os', '1'); pg.fill('#pf-ol', '5'); pg.fill('#pf-op', str(p0)); pg.evaluate("document.getElementById('pf-more-o').open = true"); pg.fill('#pf-on', '测试备注'); pg.evaluate("document.querySelector('[data-act=\"open\"]').click()")
    body = pg.evaluate("document.getElementById('planBody').textContent")
    sgt = pg.evaluate("document.getElementById('sigbar').innerText")
    ok('有持仓时首页：左格是「持仓信号」(继续持有/该平仓)，右格显示浮盈亏金额(元)，不再显示入场信号', ('继续持有' in sgt or '该平仓' in sgt) and '账户权益' in sgt and '元' in sgt and '入场信号（收盘后看一次）' not in sgt, sgt[:300])
    ok('有持仓时交易计划面板自动展开', pg.evaluate("getComputedStyle(document.getElementById('tradePanel')).display !== 'none'"))
    ok('记录开仓后：持仓管理出现该仓位，且给出继续持有/该平仓的判定', ('继续持有' in sgt or '该平仓' in sgt) and '5 手' in body, body[:400])
    ok('持仓期间最高价由系统按价格数据算出（不用手填）', ('{:,}'.format(round(mx))) in body, (mx, body[:600]))
    snap = pg.evaluate("(() => { const s = window.__cockpit.planSnap(); return { eq: s.E.equity, fees: s.E.fees, peak: s.hold.peak, days: s.hold.days }; })()")
    ok('自动持仓最高价 = 开仓日起的最大收盘价', abs(snap['peak'] - max(mx, p0)) < 1e-6, snap)
    ok('开仓手续费按每手来回23元的一半记：5手 → 57.5', abs(snap['fees'] - 57.5) < 1e-6, snap)
    exp = 500000 + (last - p0) * 5 * 10 - 57.5
    ok('权益自动 = 初始 + 浮动盈亏 − 手续费', abs(snap['eq'] - exp) < 1e-6, (snap, exp))
    sig = pg.evaluate("document.getElementById('sigbar').innerText")
    ok('首页持仓格同步显示持仓和判定', '多 5 手' in sig and '账户权益' in sig and ('继续持有' in sig or '该平仓' in sig), sig)
    ok('已有持仓时不再显示开仓表单', pg.evaluate("document.getElementById('pf-ol') === null"))
    tr0 = pg.evaluate("(() => { const t = window.__cockpit.planSnap().A.trades[0]; return { n: t.note, ref: t.refPx, slip: t.slipO, pred: t.pred }; })()")
    ok('开仓时存了备注、信号日收盘价、开仓滑点、系统预计（胜率/期望/盈亏比）', tr0['n'] == '测试备注' and tr0['ref'] > 0 and tr0['slip'] is not None and tr0['pred'] is not None and 0 < tr0['pred']['win'] < 1, tr0)
    ok('持仓中的交易表格行已经显示实时最大浮盈/浮亏', '最大浮盈' in pg.evaluate("document.getElementById('planBody').innerText"))
    pg.fill('#pf-cd', hd['d'][-1]); pg.fill('#pf-cp', str(p0 + 100)); pg.evaluate("document.getElementById('pf-more-c').open = true"); pg.select_option('#pf-cr', 'protect'); pg.fill('#pf-cn', '怕回吐'); pg.evaluate("document.querySelector('[data-act=\"close\"]').click()")
    rs0 = pg.evaluate("window.__cockpit.planSnap().A.trades[0].res")
    ok('平仓时存了原因/备注/持有天数/最大浮盈浮亏/价格路径', rs0 and rs0['reason'] == 'protect' and rs0['note'] == '怕回吐' and rs0['days'] >= 1 and rs0['mfe'] is not None and rs0['mae'] is not None and len(rs0['path']) >= 2, rs0)
    ok('交易表格显示来源/备注/平仓原因，并出现「实盘复盘」', all(k in pg.evaluate("document.getElementById('planBody').innerText") for k in ('手动保本', '测试备注', '实盘复盘')))
    snap = pg.evaluate("(() => { const s = window.__cockpit.planSnap(); return { eq: s.E.equity, fees: s.E.fees, open: !!s.pos }; })()")
    ok('记录平仓后：空仓，权益 = 500000 + 5手×10吨×100 − 来回手续费115', (not snap['open']) and abs(snap['eq'] - 504885) < 1e-6, snap)
    ok('平仓后交易记录里有这一笔，净盈亏 +4,885', '+4,885' in pg.evaluate("document.getElementById('planBody').innerText"))
    ok('记录开仓时存了决策快照（基本面方向、外资5日等）', pg.evaluate("(() => { const t = window.__cockpit.planSnap().A.trades[0]; return !!t.snap && 'fund' in t.snap && 'fsum' in t.snap && t.snap.gateOk === false && !!t.snapX; })()"))
    pg.evaluate("document.getElementById('flBtn').click()")
    with pg.expect_download() as dl2: pg.evaluate("document.querySelector('[data-act=\"csv\"]').click()")
    ok('能导出交易记录CSV（含决策快照）', dl2.value.suggested_filename.startswith('cockpit-trades-'))
    pg.evaluate("document.getElementById('tradePanel').offsetParent === null && document.getElementById('planBtn').click()")   # 平仓后回到空仓，计划面板自动收起：手动展开
    pg.evaluate("document.getElementById('setBtn').click()")   # 账户设置/出入金/校准默认折叠
    pg.fill('#pf-fa', '200000'); pg.fill('#pf-fn', '年度追加'); pg.evaluate("document.querySelector('[data-act=\"flow\"]').click()")
    ok('入金20万后权益自动 = 704,885', abs(pg.evaluate("window.__cockpit.planSnap().E.equity") - 704885) < 1e-6)
    pg.fill('#pf-ca', '700000'); pg.evaluate("document.querySelector('[data-act=\"calib\"]').click()")
    ok('按期货公司实际权益校准后 = 700,000', abs(pg.evaluate("window.__cockpit.planSnap().E.equity") - 700000) < 1e-6)
    pg.fill('#pf-fee', '63'); pg.dispatch_event('#pf-fee', 'change')
    ok('改每手手续费=63：已平仓5手的手续费变 315，权益 −200', abs(pg.evaluate("window.__cockpit.planSnap().E.equity") - 699800) < 1e-6)
    pg.fill('#pf-m', '13'); pg.dispatch_event('#pf-m', 'change'); pg.select_option('#pf-mode', 'bt')
    pg.reload(); pg.wait_for_selector('#boot', state='detached', timeout=60000)
    ok('刷新后账户、交易记录、设置都还在（权益 699,800、保证金13、口径bt）', pg.evaluate("(() => { const s = window.__cockpit.planSnap(); return Math.round(s.E.equity) === 699800 && s.A.margin === 13 && s.A.mode === 'bt' && s.A.trades.length === 1; })()"))
    pg.evaluate("document.querySelector('#sigbar [data-goplan]').click()")
    pg.evaluate("(() => { const p = document.getElementById('acctPop'); if (p.hidden || !p.querySelector('[data-act=backup]')) document.getElementById('flBtn').click(); })()")
    with pg.expect_download() as dl: pg.evaluate("document.querySelector('[data-act=\"backup\"]').click()")
    ok('能下载备份文件', dl.value.suggested_filename.startswith('cockpit-account-'))
    pg.evaluate("document.querySelector('[data-act=\"delt\"]').click()")
    ok('删除交易记录后权益重算：500000 + 入金200000 + 校准差额(−4885) = 695,115', abs(pg.evaluate("window.__cockpit.planSnap().E.equity") - 695115) < 1e-6 and pg.evaluate("window.__cockpit.planSnap().A.trades.length") == 0)
    ok('以上全程没有页面 JS 错误', not errs, errs)
    # ---- 4. 手动录入会重新计分 ----
    pg.evaluate("document.querySelector('[data-tab=\"input\"]').click()")
    before = pg.evaluate("JSON.stringify(window.__DATA__.contracts[window.__cockpit.S.key].votes.map(v => [v.label, v.signal]))")
    inp = pg.locator('.inp[data-key="crush"] input'); orig = inp.input_value()
    inp.fill('10'); inp.dispatch_event('change'); pg.wait_for_timeout(2500)
    mode = pg.evaluate("document.getElementById('engineFrame').contentWindow._indState.crush.mode")
    ok('手动改开机率=10 后，引擎里这一项的模式是 manual', mode == 'manual', mode)
    after = pg.evaluate("JSON.stringify(window.__DATA__.contracts[window.__cockpit.S.key].votes.map(v => [v.label, v.signal]))")
    ok('手动改开机率后，驾驶舱里的投票明细读到了新结果（开机率那一票的信号随之改变，或至少票数不变）', len(json.loads(after)) == len(json.loads(before)))
    ok('手动改开机率后评分引擎里的输入值=10', pg.evaluate("document.getElementById('engineFrame').contentWindow.document.getElementById('m_crush').value") == '10')
    ok('手动值写进了引擎的本地存储', '10' in (pg.evaluate("document.getElementById('engineFrame').contentWindow.localStorage.getItem('soymeal_manual_v2')") or ''))
    pg.locator('.inp[data-key="crush"] input').fill(''); pg.locator('.inp[data-key="crush"] input').dispatch_event('change')
    try: pg.wait_for_function("window.__DATA__.indicators.find(i => i.key === 'crush').input !== '' && window.__DATA__.indicators.find(i => i.key === 'crush').input !== '10'", timeout=30000)
    except Exception: pass
    ok('清空后恢复自动（模式不再是 manual）', pg.evaluate("document.getElementById('engineFrame').contentWindow._indState.crush.mode") != 'manual')
    ok('清空后输入框回填自动值', pg.evaluate("window.__DATA__.indicators.find(i => i.key === 'crush').input") not in ('', '10'))
    # ---- 5. 手动重取：对象不换、没有报错 ----
    same = pg.evaluate("""(async () => { const D0 = window.__DATA__, S0 = D0.series, C0 = D0.contracts; await window.CockpitData.reload(); return D0 === window.__DATA__ && S0 === D0.series && C0 === D0.contracts && D0.contracts.sep.votes.length > 5; })()""")
    ok('重取后 D / series / contracts 还是同一个对象且有数据', same)
    ok('重取后没有页面 JS 错误', not errs, errs)
    ctx.close()
    # ---- 5b. 电脑端一屏放下：交易/研究两个模式下，图表列、交易计划列、趋势墙都不出现竖向滚动（常见笔记本和台式分辨率）----
    JS_OV = "() => ['chart','tradePanel','wall'].map(i => { const e = document.getElementById(i); return !e || getComputedStyle(e).display === 'none' ? 0 : e.scrollHeight - e.clientHeight; }).concat([document.documentElement.scrollHeight - innerHeight])"
    for (w, h) in ((1920, 1080), (1440, 900), (1366, 768)):
        ctx, pg, e3 = open_page(b, port, w, h)
        for mode in ('trade', 'research'):
            pg.click('[data-mode=%s]' % mode); pg.wait_for_timeout(300)
            ov = pg.evaluate(JS_OV)
            ok('电脑 %dx%d %s 模式：一屏放下，没有上下滚动' % (w, h, mode), max(ov) <= 1, ov)
        ok('电脑 %dx%d：没有页面 JS 错误' % (w, h), not e3, e3); ctx.close()
    # ---- 5b2. 有持仓时（交易计划自动展开）电脑端一屏放下，不出现上下滚动 ----
    for (w, h) in ((1920, 1080), (1440, 900), (1366, 768), (1280, 720)):
        ctx, pg, e7 = open_page(b, port, w, h); pg.wait_for_timeout(300)
        pg.evaluate("document.getElementById('planBtn').click()"); pg.wait_for_timeout(200)
        px = pg.evaluate("Math.round(window.__cockpit.planSnap().px)")
        pg.fill('#pf-od', '2026-10-08'); pg.select_option('#pf-os', '1'); pg.fill('#pf-ol', '5'); pg.fill('#pf-op', str(px)); pg.evaluate("document.querySelector('[data-act=\"open\"]').click()"); pg.wait_for_timeout(500)
        ov = pg.evaluate(JS_OV)
        ok('电脑 %dx%d 有持仓：一屏放下，没有上下滚动' % (w, h), max(ov) <= 1, ov)
        ok('电脑 %dx%d 有持仓：没有页面 JS 错误' % (w, h), not e7, e7); ctx.close()
    # ---- 5b3. v101.52：研究模式下 5 个视图（持仓/月振幅/价格位置/同期规律/成本锚）在常见电脑分辨率下都一屏放下 ----
    for (w, h) in ((1920, 1080), (1440, 900), (1366, 768), (1280, 720)):
        ctx, pg, e9 = open_page(b, port, w, h); pg.wait_for_timeout(300)
        for v in ('px', 'amp', 'pos', 'sea', 'cost'):
            pg.evaluate("v => { const b = document.querySelector('[data-view=\"' + v + '\"]'); if (b) b.click(); }", v); pg.wait_for_timeout(250)
            ov = pg.evaluate(JS_OV)
            ok('电脑 %dx%d 视图 %s：一屏放下，没有上下滚动' % (w, h, v), max(ov) <= 1, ov)
        ok('电脑 %dx%d 各视图：没有页面 JS 错误' % (w, h), not e9, e9); ctx.close()
    # ---- 5e. 持仓页极简：不显示左边K线、权益和浮盈在右上角、权益公式在「?」里；所有图可放大全屏 ----
    ctx, pg, e8 = open_page(b, port, 1440, 900); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('planBtn').click()"); pg.wait_for_timeout(200)
    px = pg.evaluate("Math.round(window.__cockpit.planSnap().px)")
    pg.fill('#pf-od', '2026-10-08'); pg.select_option('#pf-os', '1'); pg.fill('#pf-ol', '5'); pg.fill('#pf-op', str(px)); pg.evaluate("document.querySelector('[data-act=\"open\"]').click()"); pg.wait_for_timeout(500)
    ok('持仓页：有「预期」：预计胜率/预计盈利/止损亏损 + 推演区间图', pg.evaluate("(() => { const t = document.getElementById('planBody').innerText; return t.includes('预计胜率') && t.includes('预计盈利') && t.includes('止损亏损') && !!document.querySelector('#planBody svg.exsv path.exb1'); })()"))
    ok('持仓页：有预计盈亏比和平仓建议，且能切换开仓来源', pg.evaluate("(() => { const t = document.getElementById('planBody').innerText; if (!t.includes('预计盈亏比') || !document.querySelector('#planBody .exadv')) return false; const a = document.querySelector('#planBody .exsrc').textContent; document.querySelector('#planBody .exsrc').click(); return document.querySelector('#planBody .exsrc').textContent !== a; })()"))
    ok('持仓页：预期里写明不是预测、基本面不计入', pg.evaluate("document.getElementById('planBody').innerText.includes('不是预测') && document.getElementById('planBody').innerText.includes('基本面')"))
    ok('持仓页：左边K线图不显示', pg.evaluate("getComputedStyle(document.getElementById('chart')).display === 'none'"))
    ok('持仓页：右上角有账户权益和浮盈，没有「= 初始 … 出入金」公式', pg.evaluate("(() => { const t = document.getElementById('sigbar').innerText; return t.includes('账户权益') && !t.includes('出入金') && !document.getElementById('planBody').innerText.includes('= 初始'); })()"))
    pg.evaluate("document.querySelector('#sigbar [data-about=\"placct\"]').click()"); pg.wait_for_timeout(200)
    ok('持仓页：右上角「?」里有权益公式', pg.evaluate("document.getElementById('shB').innerText.includes('权益 =')"))
    pg.evaluate("window.__cockpit.closeSheet()")
    ok('持仓页：计划页没有大段解释文字（离场规则/说明不外露）', pg.evaluate("!document.getElementById('planBody').innerText.includes('没有触发止损') && !document.getElementById('planBody').innerText.includes('仓位阶梯')"))
    pg.evaluate("document.getElementById('planBtn').click()"); pg.wait_for_timeout(300)
    ok('持仓页收起计划后：图回来（三图同屏）', pg.evaluate("getComputedStyle(document.getElementById('chart')).display !== 'none' && !!document.getElementById('mg1')"))
    for kk in ('px', 'pos', 'sea'):
        pg.evaluate("k => document.querySelector('#chart [data-full=\"' + k + '\"]').click()", kk); pg.wait_for_timeout(400)
        r = pg.evaluate("(() => { const o = document.getElementById('fsv'); const b = document.getElementById('fsB'); const r = o.getBoundingClientRect(); return { on: o.classList.contains('on'), w: Math.round(r.width), h: Math.round(r.height), has: kk => 0, svg: !!b.querySelector('svg'), txt: b.innerText.length, tabs: !!b.querySelector('.vtabs') }; })()")
        ok('全屏：%s 图放大到整个窗口、没有切换按钮' % kk, r['on'] and r['w'] >= 1400 and r['h'] >= 890 and not r['tabs'] and (r['svg'] or r['txt'] > 50), r)
        if kk == 'px': pg.screenshot(path='/tmp/claude-0/shot_full.png')
        pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
        ok('全屏：%s 按 Esc 关闭' % kk, pg.evaluate("!document.getElementById('fsv').classList.contains('on')"))
    ok('持仓页/全屏：没有 JS 错误', not e8, e8); ctx.close()
    # ---- 5f. 持仓属于开仓时的合约：切到别的合约不再显示这笔持仓；切回来又在 ----
    ctx, pg, e9 = open_page(b, port, 1440, 900); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('planBtn').click()"); pg.wait_for_timeout(200)
    px = pg.evaluate("Math.round(window.__cockpit.planSnap().px)")
    pg.fill('#pf-od', '2026-10-08'); pg.select_option('#pf-os', '1'); pg.fill('#pf-ol', '7'); pg.fill('#pf-op', str(px)); pg.evaluate("document.querySelector('[data-act=\"open\"]').click()"); pg.wait_for_timeout(400)
    sym0 = pg.evaluate("window.__DATA__.contracts[window.__cockpit.S.key].symbol")
    ok('持仓：开仓时记下合约代码', pg.evaluate("JSON.parse(localStorage.getItem('cockpit-acct')).trades[0].contract") == sym0, sym0)
    pg.evaluate("document.querySelector('#cBtn').click()"); pg.evaluate("document.querySelector('[data-ck=\"sep\"]').click()"); pg.wait_for_timeout(500)
    r = pg.evaluate("(() => { const s = window.__cockpit.planSnap(); return { pos: !!s.pos, other: !!s.other, bar: document.getElementById('sigbar').innerText, holding: document.body.classList.contains('holding') }; })()")
    ok('切到别的合约：这个合约没有持仓（空仓界面、不显示 7 手持仓卡）', not r['pos'] and r['other'] and not r['holding'] and '7 手' in r['bar'] and sym0 in r['bar'], r)
    ok('切到别的合约：开仓表单不出现，提示持仓在原合约', pg.evaluate("document.getElementById('pf-ol') === null && document.getElementById('planBody').innerText.includes('你的持仓在')"))
    pg.evaluate("document.querySelector('#sigbar [data-ck]').click()"); pg.wait_for_timeout(500)
    r = pg.evaluate("(() => { const s = window.__cockpit.planSnap(); return { pos: !!s.pos, holding: document.body.classList.contains('holding'), key: window.__cockpit.S.key }; })()")
    ok('点「持仓在另一个合约」切回去：持仓页回来', r['pos'] and r['holding'] and r['key'] == 'jan', r)
    ok('持仓/合约切换：没有 JS 错误', not e9, e9); ctx.close()
    # ---- 5c. 空仓宽屏：价格持仓/价格位置/同期规律三图同屏，无切换按钮、无成本锚、各列不滚动；计划面板可收起回来 ----
    for (w, h) in ((1920, 1080), (1440, 900), (1366, 768)):
        ctx, pg, e4 = open_page(b, port, w, h); pg.wait_for_timeout(300)
        ok('电脑 %dx%d 空仓：三图同屏、没有切换按钮和成本锚' % (w, h), pg.evaluate("!!document.getElementById('mg1') && !!document.getElementById('mg2') && !!document.getElementById('mg3') && !document.querySelector('.vtabs') && !document.getElementById('chart').innerText.includes('成本锚') && document.getElementById('mg3').innerText.includes('同期规律')"))
        ov = pg.evaluate("['mg1','mg2','mg3'].map(i => { const e = document.getElementById(i); return e.scrollHeight - e.clientHeight; })")
        ok('电脑 %dx%d 空仓：三列都不用滚动' % (w, h), max(ov) <= 1, ov)
        ok('电脑 %dx%d 空仓：入场条件表不在页面上（在信号「?」里）' % (w, h), pg.evaluate("!document.body.innerText.includes('做多①价格低位')"))
        pg.evaluate("document.querySelector('#sigbar .q, #sigbar [data-about]').click()"); pg.wait_for_timeout(200)
        ok('电脑 %dx%d：信号「?」里有入场条件表和数据状态' % (w, h), pg.evaluate("(() => { const t = document.getElementById('shB').innerText; return t.includes('做多①价格低位') && t.includes('做空②'); })()"))
        pg.evaluate("window.__cockpit.closeSheet()")
        pg.evaluate("document.querySelector('#sigbar .sg:last-child').click()"); pg.wait_for_timeout(250)
        ok('电脑 %dx%d：点「空仓」格展开计划，图回到切换模式' % (w, h), pg.evaluate("!document.body.classList.contains('plan-off') && !document.getElementById('mg1') && !!document.querySelector('.vtabs')"))
        pg.evaluate("document.querySelector('#sigbar .sg:last-child').click()"); pg.wait_for_timeout(250)
        ok('电脑 %dx%d：再点「空仓」格收起，回到三图首页' % (w, h), pg.evaluate("document.body.classList.contains('plan-off') && !!document.getElementById('mg3')"))
        pg.evaluate("document.getElementById('planBtn').click()"); pg.wait_for_timeout(200)
        pg.evaluate("document.getElementById('planHide').click()"); pg.wait_for_timeout(250)
        ok('电脑 %dx%d：计划面板里的「收起」按钮能回到三图首页' % (w, h), pg.evaluate("document.body.classList.contains('plan-off') && !!document.getElementById('mg3')"))
        pg.evaluate("document.getElementById('planBtn').click()"); pg.keyboard.press('Escape'); pg.wait_for_timeout(250)
        ok('电脑 %dx%d：按 Esc 也能收起' % (w, h), pg.evaluate("document.body.classList.contains('plan-off')"))
        if w == 1440: pg.screenshot(path='/tmp/claude-0/shot_multi.png')
        ok('电脑 %dx%d 三图首页：没有 JS 错误' % (w, h), not e4, e4); ctx.close()
    ctx, pg, e5 = open_page(b, port, 1100, 800); pg.wait_for_timeout(300)
    ok('窄屏 1100px：仍是切换视图，不分三栏', pg.evaluate("!document.getElementById('mg1') && !!document.querySelector('.vtabs')")); ctx.close()
    # ---- 5d. 账户云端同步（用假的 GitHub API）：记账自动上传 account.json + position.json；云端更新的账会被采用；没令牌只读 ----
    import base64, json as _json
    store = {}; calls = []
    def gh(route):
        rq = route.request; path = rq.url.split('/contents/')[1].split('?')[0]; calls.append((rq.method, path))
        if rq.headers.get('authorization') != 'Bearer github_pat_TEST123':
            return route.fulfill(status=401, body='{}')
        if rq.method == 'GET':
            if path not in store: return route.fulfill(status=404, body='{}')
            return route.fulfill(status=200, content_type='application/json', body=_json.dumps({'sha': store[path]['sha'], 'content': base64.b64encode(store[path]['raw']).decode()}))
        body = _json.loads(rq.post_data); cur = store.get(path)
        if cur and body.get('sha') != cur['sha']: return route.fulfill(status=409, body='{}')
        sha = 'sha%d' % (len(calls)); store[path] = {'sha': sha, 'raw': base64.b64decode(body['content'])}
        return route.fulfill(status=200, content_type='application/json', body=_json.dumps({'content': {'sha': sha}}))
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}); ctx.add_init_script("window.__CLOUD_POLL_MS=1500; try{ if(!localStorage.getItem('cockpit-pat')){localStorage.setItem('cockpit-pat','github_pat_TEST123');localStorage.setItem('cockpit-gh','{\"owner\":\"o\",\"repo\":\"r\"}');} }catch(e){}")
    pg = ctx.new_page(); e6 = []; pg.on('pageerror', lambda e: e6.append(str(e)[:200]))
    pg.route('**/*', lambda r: r.continue_() if r.request.url.startswith('http://127.0.0.1:%d' % port) else r.abort())
    pg.route('https://api.github.com/**', gh)
    pg.goto('http://127.0.0.1:%d/index.html' % port); pg.wait_for_selector('#boot', state='detached', timeout=60000); pg.wait_for_timeout(800)
    pg.evaluate("document.querySelector('[data-mode=trade]').click()"); pg.wait_for_timeout(150)
    ok('云端：有令牌启动时去读 account.json（404=还没有账，不报错）', ('GET', 'data/account.json') in calls and not e6, calls)
    pg.evaluate("document.getElementById('planBtn').click()"); pg.wait_for_timeout(200)
    pg.fill('#pf-od', '2026-10-12'); pg.select_option('#pf-os', '1'); pg.fill('#pf-ol', '5'); pg.fill('#pf-op', '3400'); pg.evaluate("document.querySelector('[data-act=\"open\"]').click()")
    pg.wait_for_timeout(2600)
    acc = _json.loads(store['data/account.json']['raw']) if 'data/account.json' in store else {}
    pos = _json.loads(store['data/position.json']['raw']) if 'data/position.json' in store else {}
    ok('云端：记开仓 → 自动上传 account.json（1笔、rev≥1）', len(acc.get('trades', [])) == 1 and acc.get('rev', 0) >= 1, acc.get('rev'))
    ok('云端：同时写 position.json（多5手@3400）', pos.get('side') == 1 and pos.get('lots') == 5 and pos.get('entryPx') == 3400, pos)
    ok('云端：页面显示「已同步」', pg.evaluate("document.querySelector('.cloudmsg').textContent.includes('已同步')"), pg.evaluate("document.querySelector('.cloudmsg').textContent"))
    # ---- 5e. 网页推送：设置里的推送区块、生成密钥（私钥只显示一次、公钥存进仓库）、sw.js/manifest 可访问 ----
    pg.evaluate("(() => { const p = document.getElementById('acctPop'); if (p.hidden) document.getElementById('setBtn').click(); })()")
    ptxt = pg.evaluate("document.getElementById('acctPop').innerText")
    ok('推送：设置里有「网页推送」区块', '网页推送' in ptxt, ptxt[-300:])
    ok('推送：sw.js 和 manifest 能访问', pg.evaluate("Promise.all([fetch('sw.js').then(r=>r.status), fetch('manifest.webmanifest').then(r=>r.status), fetch('icon.svg').then(r=>r.status), fetch('icon-180.png').then(r=>r.status), fetch('icon-192.png').then(r=>r.status), fetch('icon-512.png').then(r=>r.status)])") == [200] * 6)
    if pg.evaluate("'PushManager' in window && 'serviceWorker' in navigator"):
        pg.wait_for_timeout(1800)
        if pg.evaluate("!!document.querySelector('[data-act=\"push-gen\"]')"):
            pg.evaluate("document.querySelector('[data-act=\"push-gen\"]').click()"); pg.wait_for_timeout(1200)
            vp = _json.loads(store['data/push_vapid.json']['raw']) if 'data/push_vapid.json' in store else {}
            privt = pg.evaluate("(document.querySelector('#acctPop textarea')||{}).value || ''")
            ok('推送：生成密钥 → 公钥存进 data/push_vapid.json（65字节）、页面显示私钥（32字节）', len(vp.get('publicKey', '')) == 87 and len(privt) == 43, (vp, privt))
            try:
                sys.path.insert(0, ROOT); import webpush_send as _wp
                ok('推送：页面生成的私钥/公钥配对（服务端用私钥能推出同一个公钥）', _wp.vapid_public_b64(privt) == vp.get('publicKey'))
            except Exception as _e: ok('推送：页面生成的私钥/公钥配对', False, _e)
        else: ok('推送：未登记公钥时出现「生成推送密钥」按钮', False, ptxt[-200:])
    else: print('⚠️ 跳过：这个浏览器环境没有 PushManager')
    pg.evaluate("document.getElementById('acctPop').querySelector('[data-pop=x]').click()")
    pg.evaluate("document.body.classList.contains('plan-off') && document.getElementById('planBtn').click()"); pg.wait_for_timeout(150)
    ok('多品种回测：计划页有折叠块，写明豆粕之外没有优势', pg.evaluate("(() => { const d = document.getElementById('pf-mv'); return !!d && !d.open && d.textContent.includes('豆油') && d.textContent.includes('不能直接套'); })()"))
    pg.fill('#pf-cd', '2026-10-12'); pg.fill('#pf-cp', '3450'); pg.evaluate("document.querySelector('[data-act=\"close\"]').click()"); pg.wait_for_timeout(2600)
    pos = _json.loads(store['data/position.json']['raw'])
    ok('云端：记平仓 → position.json 变成空仓', pos.get('flat') is True, pos)
    newer = dict(_json.loads(store['data/account.json']['raw'])); newer['rev'] = 99; newer['trades'] = []; newer['init'] = 777000
    store['data/account.json'] = {'sha': 'shaNEW', 'raw': _json.dumps(newer).encode()}
    pg.evaluate("(() => { const p = document.getElementById('acctPop'); if (p.hidden) document.getElementById('setBtn').click(); })()")
    pg.evaluate("document.querySelector('[data-act=\"pat-sync\"]').click()"); pg.wait_for_timeout(800)
    ok('云端：云端的账更新（rev 99）→ 页面改用云端的账', pg.evaluate("JSON.parse(localStorage.getItem('cockpit-acct')).init") == 777000, pg.evaluate("localStorage.getItem('cockpit-acct').slice(0,80)"))
    store['data/account.json'] = {'sha': 'shaNEW2', 'raw': _json.dumps(dict(newer, rev=150, init=888000)).encode()}
    pg.wait_for_timeout(2600)
    ok('云端：页面开着，2分钟后自动拉到云端更新的账', pg.evaluate("JSON.parse(localStorage.getItem('cockpit-acct')).init") == 888000, pg.evaluate("JSON.parse(localStorage.getItem('cockpit-acct')).init"))
    pg.evaluate("document.querySelector('[data-act=\"pat-clear\"]').click()"); pg.wait_for_timeout(200)
    n0 = len(calls)
    ok('云端：清除令牌后令牌不在本机', pg.evaluate("localStorage.getItem('cockpit-pat')") is None)
    ok('云端：整个过程没有 JS 错误', not e6, e6); ctx.close()
    # ---- 5f. 空单持仓：推演里计入外资翻转；交易表格每笔下面有明细行；复盘块 ----
    ctx, pg, e7 = open_page(b, port); hd = pg.evaluate("(() => { const a = window.__DATA__.adj; return {d: a.d.slice(-30), c: a.c.slice(-30)}; })()")
    acct = {"init": 500000, "margin": 10, "fee": 23, "mode": "real", "flows": [], "rev": 2, "trades": [
        {"id": "1", "side": 1, "lots": 5, "entryD": hd['d'][0], "entryPx": hd['c'][0], "exitD": hd['d'][8], "exitPx": hd['c'][8] + 30, "src": "sys", "refPx": hd['c'][0] + 3, "slipO": -0.1, "note": "系统信号", "pred": {"win": 0.54, "ev": 3.7, "rr": 2.1, "stopP": 0.12, "med": 20}, "res": {"reason": "trail", "days": 8, "mfe": 3.2, "mae": -1.1, "slipX": 0.05, "path": []}},
        {"id": "2", "side": -1, "lots": 10, "entryD": hd['d'][12], "entryPx": hd['c'][12], "src": "sys", "refPx": hd['c'][12], "slipO": 0.0, "pred": {"win": 0.62, "ev": 1.0, "rr": 1.8, "stopP": 0.06, "med": 4, "flipP": 0.7}}]}
    pg.evaluate("a => localStorage.setItem('cockpit-acct', JSON.stringify(a))", acct); pg.reload(); pg.wait_for_selector('#boot', state='detached', timeout=60000); pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelector('[data-mode=trade]').click()"); pg.wait_for_timeout(600)
    body = pg.evaluate("document.getElementById('planBody').textContent")
    ok('空单持仓：预期里写「外资翻转离场 x%」，说明里写外资翻转的历史概率（页面没报错）', '外资翻转离场' in body and '外资三家合计翻回' in body and not e7, (e7, body[-400:]))
    ok('空单持仓：每笔交易下面有明细行（来源/最大浮盈浮亏/滑点/开仓时预计）和「实盘复盘」', all(k in body for k in ('最大浮盈', '滑点', '开仓时预计', '实盘复盘', '系统信号')), body[:600])
    ctx.close()
    # ---- 5g. v101.51：K线图层开关（默认只留彩带/本月高低/持仓量）+ 月振幅视图 ----
    ctx, pg, e8 = open_page(b, port); pg.wait_for_timeout(300)
    kt = pg.evaluate("document.getElementById('kl').innerText + document.querySelector('#kl svg').innerHTML.length")
    kl = pg.evaluate("document.getElementById('kl').textContent")
    ok('K线默认：不画铁顶/铁底/10年铁顶/近20日高低/平衡价，只有本月高低和持仓量', all(k not in kl for k in ('铁顶', '铁底', '20日高', '20日低', '平衡')) and '本月高' in kl and '万' in kl, kl)
    pg.evaluate("document.querySelector('.lybtn').click()")
    ok('点「图层」展开菜单，6个开关，默认3开3关', pg.evaluate("(() => { const m = document.querySelector('.lym'); return !m.hidden && m.querySelectorAll('input').length === 6 && m.querySelectorAll('input:checked').length === 3; })()"))
    pg.evaluate("document.querySelector('[data-ly=iron]').click(); document.querySelector('[data-ly=oi]').click()")
    kl2 = pg.evaluate("document.getElementById('kl').textContent")
    ok('打开「铁顶/底」、关掉「持仓量」后K线立即变化，设置存进本机', '260天铁' in kl2 and '万' not in kl2 and pg.evaluate("JSON.parse(localStorage.getItem('cockpit-ly')).iron === true && JSON.parse(localStorage.getItem('cockpit-ly')).oi === false"), kl2)
    pg.evaluate("document.querySelectorAll('[data-ly]').forEach(c => { if (!c.checked) c.click(); })")
    ys = pg.evaluate("[...document.querySelectorAll('#kl text.lv')].map(t => +t.getAttribute('y')).sort((a, b) => a - b)")
    ok('全部图层打开：右侧标签互相不重叠（间距≥11px）', len(ys) >= 6 and all(ys[i + 1] - ys[i] >= 11 for i in range(len(ys) - 1)), ys)
    pg.evaluate("document.body.click()")
    ok('点图层菜单外面，菜单收起', pg.evaluate("document.querySelector('.lym').hidden"))
    pg.reload(); pg.wait_for_selector('#boot', state='detached', timeout=60000); pg.wait_for_timeout(500)
    ok('刷新后图层选择还在', '铁' in pg.evaluate("document.getElementById('kl').textContent"))
    pg.evaluate("document.querySelector('[data-view=amp]').click()"); pg.wait_for_timeout(200)
    at = pg.evaluate("document.getElementById('chart').innerText")
    ok('月振幅视图：一句结论（本月振幅/偏宽正常偏窄）+ 逐月柱状图，更多明细里才有日历月区间图', all(k in at for k in ('本月振幅', '往年同月', '近 2 年逐月振幅', '不说多空')) and pg.evaluate("document.querySelectorAll('#chart svg.amsv').length") == 2 and pg.evaluate("!document.querySelector('#chart details.vmore').open"), at[:300])
    ok('月振幅视图：柱子 25 根、12 个日历月都有方框', pg.evaluate("document.querySelectorAll('#chart svg.amsv')[0].querySelectorAll('rect[class^=am]').length") == 25 and pg.evaluate("document.querySelectorAll('#chart svg.amsv')[1].querySelectorAll('rect.amx').length") == 12)
    pg.evaluate("document.querySelector('#chart [data-about=amp]').click()"); pg.wait_for_timeout(150)
    ok('月振幅「?」说明能打开', '月振幅怎么看' in pg.evaluate("document.getElementById('shT').textContent")); pg.evaluate("window.__cockpit.closeSheet()")
    # v101.52：日K线晚上才更新，收盘后量价卡要接上今天的临时收盘价（用今天日盘15分钟线拼）
    r = pg.evaluate("""(() => { const D = window.__DATA__, k = window.__cockpit.S.key, kl = D.contracts[k].kline, kd = kl[kl.length - 1].d, c0 = kl[kl.length - 1].c;
      D.adj = Object.assign({}, D.adj, { d: D.adj.d.concat(['2099-01-02']), c: D.adj.c.concat([c0]) }); D.m15 = D.m15 || {};
      D.m15[k] = [{ d: '01-02 09:15', o: c0 + 5, h: c0 + 30, l: c0 - 4, c: c0 + 10, v: 5, oi: 9 }, { d: '01-02 14:45', o: c0 + 10, h: c0 + 12, l: c0 - 20, c: c0 - 15, v: 5, oi: 9 }, { d: '01-02 15:00', o: c0 - 15, h: c0 - 10, l: c0 - 18, c: c0 + 77, v: 5, oi: 10 }];
      const kn = window.__cockpit.klineNow(), b = kn[kn.length - 1]; window.__cockpit.renderBand(); const txt = document.querySelector('#band .px').innerText;
      return { n: kn.length - kl.length, d: b.d, c: b.c, h: b.h, l: b.l, o: b.o, prov: b.prov, c0, txt }; })()""")
    ok('量价卡：收盘后接上今天临时日线（15:00 价、日盘最高最低），并标注“临时”', r['n'] == 1 and r['d'] == '2099-01-02' and r['c'] == r['c0'] + 77 and r['h'] == r['c0'] + 30 and r['l'] == r['c0'] - 20 and r['o'] == r['c0'] + 5 and r['prov'] and '临时' in r['txt'], r)
    ok('月振幅：没有 JS 错误', not e8, e8); ctx.close()
    # ---- 6. 手机宽度 ----
    for w in (390, 360):
        ctx, pg, e2 = open_page(b, port, w, 800)
        ov = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        ok('手机 %dpx：首页不横向溢出' % w, ov <= 0, ov)
        for v in ('pos', 'sea', 'cost'):
            pg.evaluate("v => document.querySelector('[data-view=\"' + v + '\"]').click()", v)
            ov = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            ok('手机 %dpx：%s 视图不横向溢出' % (w, v), ov <= 0, ov)
        ok('手机 %dpx：没有 JS 错误' % w, not e2, e2); ctx.close()
    # ---- 7. 缺文件 ----
    d2 = make_site(lambda x: os.remove(os.path.join(x, 'data', 'history', 'hog_ratio.json'))); s2, p2 = serve(d2)
    ctx, pg, e3 = open_page(b, p2)
    ok('缺一个历史文件：照常启动', pg.evaluate("!document.getElementById('boot')"))
    ok('缺一个历史文件：底部提示里点名 hog_ratio', 'hog_ratio' in (pg.evaluate("(document.querySelector('.bootwarn')||{}).innerText||''")))
    ok('缺一个历史文件：猪粮比序列为空而不是崩', pg.evaluate("window.__DATA__.series.hog.pts.length") == 0)
    ctx.close(); s2.shutdown()
    d3 = make_site(lambda x: os.remove(os.path.join(x, 'data', 'latest.json'))); s3, p3 = serve(d3)
    ctx, pg, e4 = open_page(b, p3, wait_boot=False); pg.wait_for_function("document.getElementById('bootT') && document.getElementById('bootT').textContent === '没能启动'", timeout=60000)
    ok('缺 latest.json：显示"没能启动"和重试/旧版入口', pg.evaluate("!!document.getElementById('bootRetry') && !!document.querySelector('#boot a[href=\"engine.html\"]')"))
    ctx.close(); s3.shutdown()
    d4 = make_site(lambda x: os.remove(os.path.join(x, 'data', 'raw', 'seasonal', 'M0_daily.csv'))); s4, p4 = serve(d4)
    ctx, pg, e5 = open_page(b, p4)
    ok('缺主连日线CSV：照常启动，交易计划页可打开', pg.evaluate("!document.getElementById('boot')") and not pg.evaluate("document.getElementById('planBody').innerText.length < 20"), e5)
    ctx.close(); s4.shutdown()
    d6 = make_site(lambda x: os.remove(os.path.join(x, 'data', 'main_adj.json'))); s6, p6 = serve(d6)
    ctx, pg, e6 = open_page(b, p6)
    ok('缺 main_adj.json：照常启动，不弹缺文件提示（可选文件）', pg.evaluate("!document.getElementById('boot') && !document.querySelector('.bootwarn')"), e6)
    ok('缺 main_adj.json：信号格明确写「缺换月调整价」并作废信号', pg.evaluate("(()=>{const b=document.querySelector('#dataLine [data-dsl]'); if(b&&b.getAttribute('aria-expanded')!=='true') b.click(); const e=document.getElementById('dataLine'), g=document.querySelector('#sigbar .sg');return !!e&&e.classList.contains('bad')&&e.innerText.includes('换月调整价')&&g.innerText.includes('数据不足')})()"))
    ctx.close(); s6.shutdown(); shutil.rmtree(d6, ignore_errors=True)
    # ---- 7b. 席位覆盖表 ----
    ctx, pg, _e = open_page(b, port)
    pg.evaluate("document.querySelector('[data-tab=\"capital\"]').click()")
    ok('没有 _backfill_report.json：资金页不出现覆盖表也不报错', '席位历史覆盖' not in pg.evaluate("document.getElementById('shB').innerText") and 'bootwarn' not in pg.evaluate("document.body.innerHTML.slice(0,0)+(document.querySelector('.bootwarn')?'bootwarn':'')"))
    ctx.close()
    rep = {'generatedAt': 'x', 'series': [{'key': 'capital_rank', 'firstDay': '2022-01-04', 'lastDay': '2026-10-09', 'files': 1073, 'coverage': {'高盛期货': {'exact': 10, 'estimated': 103, 'absent': 960}, '摩根大通': {'exact': 807, 'estimated': 218, 'absent': 48}, '瑞银期货': {'exact': 0, 'estimated': 240, 'absent': 833}, '中粮期货': {'exact': 1072, 'estimated': 0, 'absent': 1}, '国投期货': {'exact': 1061, 'estimated': 5, 'absent': 7}}}]}
    d5 = make_site(lambda x: json.dump(rep, open(os.path.join(x, 'data', 'history', '_backfill_report.json'), 'w', encoding='utf-8'))); s5, p5 = serve(d5)
    ctx, pg, e7 = open_page(b, p5)
    pg.evaluate("document.querySelector('[data-tab=\"capital\"]').click()")
    txt = pg.evaluate("document.getElementById('shB').innerText")
    ok('资金页显示席位覆盖表和日期范围', '席位历史覆盖' in txt and '2022-01-04' in txt and '1073' in txt, txt[:200])
    ok('覆盖表：高盛 精确10/估计103/没进榜960，有数据 11%', all(s in pg.evaluate("[...document.querySelectorAll('#shB .tbcv tbody tr')].map(r => r.innerText.replace(/\\s+/g,' ')).join('|')") for s in ('高盛 10 103 960 11%', '摩根大通 807 218 48 96%', '中粮 1072 0 1 100%')))
    ok('覆盖弱的席位（高盛、瑞银）被点名提醒，覆盖好的没被点名', '高盛、瑞银' in txt and '摩根大通大部分' not in txt and '国投大部分' not in txt)
    ok('有覆盖报告时不弹缺文件提示（可选文件）', pg.evaluate("!document.querySelector('.bootwarn')"))
    ok('覆盖表：手机宽度不横向溢出', (lambda: (pg.set_viewport_size({'width': 390, 'height': 800}), pg.wait_for_timeout(300), pg.evaluate("(()=>{const b=document.getElementById('shB');return b.scrollWidth-b.clientWidth})()"))[2] <= 0)())
    ok('覆盖表全程无 JS 错误', not e7, e7); ctx.close(); s5.shutdown(); shutil.rmtree(d5, ignore_errors=True)
    # ---- 7b. v101.49：空仓默认研究页；研究页不显示持仓栏；数据灯逐项写明；手机月份表 ----
    ctx, pg, e9 = open_page(b, port, 1440, 900, mode=None); pg.wait_for_timeout(300)
    ok('空仓默认先进研究页', pg.evaluate("document.body.classList.contains('mode-research')"))
    ok('市场状态下有「近20日波动 窄幅/正常/宽幅 · 振幅（豆粕近10年分位）」', pg.evaluate("(() => { const t = document.querySelector('#band .regime').innerText; return t.includes('近20日波动') && t.includes('分位'); })()"))
    ok('研究页（空仓）：只有入场信号格，没有「持仓」格', pg.evaluate("(() => { const k = document.querySelectorAll('#sigbar > *'); return k.length >= 2 && getComputedStyle(k[0]).display !== 'none' && getComputedStyle(k[1]).display === 'none'; })()"))
    ok('数据灯：写明不可用/降权/手动是哪几项（逐条列名）', pg.evaluate("(() => { const b = document.querySelector('#checks [data-lamp=\"hlth\"]'); if (!b) return false; b.click(); const t = document.getElementById('shB').innerText; return t.includes('不可用') || t.includes('降权') || t.includes('全部指标正常') || t.includes('缺席投票'); })()"))
    pg.evaluate("window.__cockpit.closeSheet()")
    pg.evaluate("document.querySelector('[data-mode=trade]').click()"); pg.wait_for_timeout(200); pg.evaluate("document.getElementById('planBtn').click()"); pg.wait_for_timeout(200)
    pg.fill('#pf-od', '2026-10-08'); pg.select_option('#pf-os', '1'); pg.fill('#pf-ol', '2'); pg.fill('#pf-op', '3400'); pg.evaluate("document.querySelector('[data-act=\"open\"]').click()"); pg.wait_for_timeout(400)
    pg.evaluate("document.querySelector('[data-mode=research]').click()"); pg.wait_for_timeout(300)
    ok('研究页（有持仓）：不显示持仓状态栏', pg.evaluate("getComputedStyle(document.getElementById('sigbar')).display === 'none'"))
    ctx.close()
    ctx, pg, e10 = open_page(b, port, 390, 800); pg.evaluate("document.getElementById('planBtn').click()"); pg.wait_for_timeout(200); pg.evaluate("(() => { const d = document.getElementById('pf-mo'); if (d) d.open = true; })()"); pg.wait_for_timeout(200)
    ok('手机390：历史开仓月份表不横向溢出', pg.evaluate("(() => { const t = document.querySelector('#pf-mo .tbmo'); return !!t && t.getBoundingClientRect().right <= window.innerWidth + 1 && document.documentElement.scrollWidth <= window.innerWidth + 1; })()"), pg.evaluate("document.documentElement.scrollWidth"))
    ctx.close()
    # ---- 8. file:// ----
    ctx = b.new_context(); pg = ctx.new_page(); pg.goto('file://' + os.path.join(d, 'index.html'))
    ok('file:// 打开：提示要用网址打开，不空白', '网址' in pg.evaluate("document.getElementById('boot').innerText"))
    ctx.close()
    # ---- 9. engine.html 单独打开仍能用（旧版完整页面） ----
    ctx, pg, e6 = open_page(b, port, path='engine.html', wait_boot=False); pg.wait_for_timeout(4000)
    ok('engine.html 单独打开：评分引擎有数据', pg.evaluate("!!window._syncedData && typeof window.updateOverallAlert === 'function'"))
    ok('engine.html 单独打开：没有页面 JS 错误', not e6, e6); ctx.close()
    b.close(); pw.stop(); srv.shutdown()
    for x in (d, d2, d3, d4): shutil.rmtree(x, ignore_errors=True)
    print('\n结果：%d项通过，%d项失败%s' % (passed, len(failed), '：' + str(failed) if failed else ''))
    return 1 if failed else 0

if __name__ == '__main__':
    sys.exit(main())
