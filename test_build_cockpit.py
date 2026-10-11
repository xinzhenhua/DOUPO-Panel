#!/usr/bin/env python3
"""index.html 必须和 cockpit/ 源文件一致（改了源文件忘了重新生成会在这里失败）。"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
p = subprocess.run([sys.executable, os.path.join(HERE, 'build_cockpit.py'), '--check'], capture_output=True, text=True)
print(p.stdout.strip() or p.stderr.strip())
html = open(os.path.join(HERE, 'index.html'), encoding='utf-8').read()
checks = [
    ('index.html 与 cockpit/ 源文件一致', p.returncode == 0),
    ('index.html 里没有残留的原型数据块 window.__DATA__=', 'window.__DATA__=' not in html),
    ('index.html 引用评分引擎 engine.html', "base + 'engine.html'" in html),
    ('engine.html 存在并带驾驶舱需要的两个钩子', all(s in open(os.path.join(HERE, 'engine.html'), encoding='utf-8').read() for s in ('window._votesDump', "note: note || ''"))),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print('✅' if ok else '❌', n)
print('\n结果：%d项通过，%d项失败' % (len(checks) - len(bad), len(bad))); sys.exit(1 if bad else 0)
