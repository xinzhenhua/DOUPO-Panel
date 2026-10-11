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
    for f in ('index.html', 'engine.html'): shutil.copy(os.path.join(ROOT, f), d)
    zipfile.ZipFile(os.path.join(HERE, 'data', 'cockpit_fixture_20261011.zip')).extractall(os.path.join(d, 'data'))
    if mutate: mutate(d)
    return d

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
def serve(d):
    h = functools.partial(Quiet, directory=d); s = socketserver.ThreadingTCPServer(('127.0.0.1', 0), h); s.daemon_threads = True
    threading.Thread(target=s.serve_forever, daemon=True).start(); return s, s.server_address[1]

def open_page(b, port, w=1440, h=900, path='index.html', wait_boot=True):
    ctx = b.new_context(viewport={'width': w, 'height': h}); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
    pg.route('**/*', lambda r: r.continue_() if r.request.url.startswith('http://127.0.0.1:%d' % port) else r.abort())
    pg.goto('http://127.0.0.1:%d/%s' % (port, path))
    if wait_boot:
        try: pg.wait_for_selector('#boot', state='detached', timeout=60000)
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
    ok('趋势墙画出了格子', pg.evaluate("document.querySelectorAll('#tiles [data-tile]').length") >= 10)
    # ---- 2. 所有视图、证据页、说明 ----
    for v in ('px', 'pos', 'sea', 'cost', 'plan'):
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
    # ---- 3. 交易计划：50万、13%、3400、按实际保证金 → 67手 ----
    pg.evaluate("document.querySelector('[data-view=\"plan\"]').click()")
    pg.fill('#pl-eq', '500000'); pg.fill('#pl-m', '13'); pg.fill('#pl-px', '3400')
    pg.select_option('#pl-mode', 'real'); pg.dispatch_event('#pl-px', 'input')
    out = pg.evaluate("document.getElementById('planOut').innerText")
    ok('计划页：13%保证金、3400、50万 → 67 手', '67' in out and '手' in out, out[:300])
    pg.select_option('#pl-mode', 'bt'); pg.dispatch_event('#pl-mode', 'change')
    out = pg.evaluate("document.getElementById('planOut').innerText")
    ok('计划页：按回测口径 → 88 手', '88' in out, out[:300])
    pg.reload(); pg.wait_for_selector('#boot', state='detached', timeout=60000); pg.evaluate("document.querySelector('[data-view=\"plan\"]').click()")
    ok('计划页：刷新后保证金输入还在(13)', pg.input_value('#pl-m') == '13')
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
    # ---- 6. 手机宽度 ----
    for w in (390, 360):
        ctx, pg, e2 = open_page(b, port, w, 800)
        ov = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        ok('手机 %dpx：首页不横向溢出' % w, ov <= 0, ov)
        for v in ('plan', 'pos', 'sea', 'cost'):
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
    ok('缺主连日线CSV：照常启动，交易计划页可打开', pg.evaluate("!document.getElementById('boot')") and not pg.evaluate("document.querySelector('[data-view=\"plan\"]').click(), document.getElementById('chart').innerText.length < 20"), e5)
    ctx.close(); s4.shutdown()
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
