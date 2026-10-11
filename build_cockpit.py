#!/usr/bin/env python3
"""把 cockpit/ 下的源文件拼成单文件 index.html（驾驶舱）。

  python3 build_cockpit.py            # 生成 index.html
  python3 build_cockpit.py --check    # 只检查 index.html 是不是最新（不一致则退出码1，测试里用）

源文件：shell.html(页面骨架+样式) / logic.js(纯计算) / loader.js(取数与装配) / ui.js(界面) / static.json(静态骨架：趋势墙每格的名称单位等)。
改了 cockpit/ 下的任何文件都要重新运行本脚本并提交 index.html；engine.html 是原来的完整评分页面，不由本脚本生成。"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
rd = lambda n: open(os.path.join(HERE, 'cockpit', n), encoding='utf-8').read()

BOOT_CSS = """
.boot{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;background:var(--bg);color:var(--ink);padding:24px;text-align:center}
.boot .bx{max-width:460px}.boot h1{font:600 20px/1.4 var(--font);margin-bottom:8px}.boot p{color:var(--ink2);font-size:14px;margin-top:8px}
.boot .sp{width:28px;height:28px;border:3px solid var(--line);border-top-color:var(--focus);border-radius:50%;margin:0 auto 16px;animation:bsp .9s linear infinite}
.boot a,.boot button{display:inline-block;margin:12px 8px 0;padding:8px 16px;border:1px solid var(--line);border-radius:8px;color:var(--ink);background:var(--surface);text-decoration:none;font-size:14px}
.boot pre{margin-top:12px;text-align:left;font:12px/1.5 ui-monospace,monospace;color:var(--ink3);white-space:pre-wrap;word-break:break-all;max-height:140px;overflow:auto}
@keyframes bsp{to{transform:rotate(360deg)}}
.bootwarn{position:fixed;left:0;right:0;bottom:0;z-index:150;padding:8px 16px;background:var(--surface);border-top:1px solid var(--line);color:var(--ink2);font-size:12.5px;display:flex;gap:12px;align-items:center}
.bootwarn button{margin-left:auto;padding:2px 10px;border:1px solid var(--line);border-radius:6px}
@media (prefers-reduced-motion:reduce){.boot .sp{animation:none}}
"""
BOOT_HTML = """<div class="boot" id="boot" role="status" aria-live="polite"><div class="bx"><div class="sp" id="bootSp"></div><h1 id="bootT">豆粕驾驶舱</h1><p id="bootM">正在启动评分引擎并读取数据…</p><div id="bootX"></div></div></div>
"""
BOOT_JS = r"""
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  function runUI() {
    var s = document.createElement('script'); s.textContent = $('uiSrc').textContent; document.body.appendChild(s);
    var b = $('boot'); if (b) b.remove();
  }
  function warn(fails) {
    var old = document.querySelector('.bootwarn'); if (old) old.remove();
    if (!fails || !fails.length) return;
    var d = document.createElement('div'); d.className = 'bootwarn';
    d.innerHTML = '<span>部分数据文件没取到（不影响其他部分）：' + fails.map(function (x) { return String(x).replace(/[<&]/g, ''); }).join('、') + '</span><button type="button">知道了</button>';
    d.querySelector('button').onclick = function () { d.remove(); };
    document.body.appendChild(d);
  }
  function status(msg, fails, err) {
    if (msg === 'error') {
      var first = !window.__DATA__;
      if (first) {
        $('bootSp').style.display = 'none'; $('bootT').textContent = '没能启动';
        $('bootM').textContent = '评分引擎或数据没有读到。';
        $('bootX').innerHTML = '<button type="button" id="bootRetry">重试</button><a href="engine.html">打开旧版完整页面</a><pre></pre>';
        $('bootX').querySelector('pre').textContent = String(err && err.message || err);
        $('bootRetry').onclick = function () { location.reload(); };
      } else warn(fails);
      return;
    }
    if (msg && $('bootM')) $('bootM').textContent = msg;
    warn(fails);
  }
  if (location.protocol === 'file:') {
    $('bootSp').style.display = 'none'; $('bootT').textContent = '需要通过网址打开';
    $('bootM').textContent = '驾驶舱要在后台运行评分引擎并读取 data/ 下的数据，浏览器不允许 file:// 方式这样做。请用 GitHub Pages 的网址打开，或在项目目录运行 python3 -m http.server 后访问 http://localhost:8000/。';
    $('bootX').innerHTML = '<a href="engine.html">直接打开旧版完整页面</a>';
    return;
  }
  window.CockpitData.boot({ STATIC: window.__STATIC__, runUI: runUI, status: status });
})();
"""

def build():
    shell = rd('shell.html')
    assert shell.count('</style>') == 1 and shell.count('</aside>') == 1 and shell.count('<body>') == 1
    shell = shell.replace('</style>', BOOT_CSS + '</style>')
    shell = shell.replace('<body>\n', '<body>\n' + BOOT_HTML, 1)
    static = json.dumps(json.load(open(os.path.join(HERE, 'cockpit', 'static.json'), encoding='utf-8')), ensure_ascii=False, separators=(',', ':'))
    ui = rd('ui.js')
    assert '</script' not in ui and '</script' not in rd('logic.js') and '</script' not in rd('loader.js')
    parts = [shell.rstrip('\n'),
             '<script>\n' + rd('logic.js').rstrip('\n') + '\n</script>',
             '<script>\n' + rd('loader.js').rstrip('\n') + '\n</script>',
             '<script>\nwindow.__STATIC__=' + static + ';\n</script>',
             '<script type="text/plain" id="uiSrc">\n' + ui.rstrip('\n') + '\n</script>',
             '<script>' + BOOT_JS + '</script>',
             '</body>\n</html>\n']
    return '\n'.join(parts)

if __name__ == '__main__':
    out = os.path.join(HERE, 'index.html'); html = build()
    if '--check' in sys.argv:
        cur = open(out, encoding='utf-8').read() if os.path.exists(out) else ''
        if cur != html:
            print('index.html 不是最新：请运行 python3 build_cockpit.py'); sys.exit(1)
        print('index.html 与 cockpit/ 源文件一致'); sys.exit(0)
    open(out, 'w', encoding='utf-8').write(html); print('index.html', len(html), 'bytes')
