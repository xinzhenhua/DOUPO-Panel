# -*- coding: utf-8 -*-
"""Python 3.11 兼容性守卫(v101.1)。运行：python3 test_py311_compat.py
背景：回填和校准在 GitHub Actions(固定 Python 3.11)里失败了——mysteel_parsers.py 第153行在 f-string 的表达式里重用了外层引号，
3.12 才允许，3.11 是 SyntaxError。开发环境是 3.12，所以所有测试都通过，没发现。
本测试用 tokenize 在**任何版本**下检查 3.12 才有的两类 f-string 写法，不依赖手边有没有 3.11；如果能找到真的 python3.11，再用它逐个文件编译一遍(最权威)。"""
import os, sys, glob, io, tokenize, subprocess, shutil, traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def _quote_of(tok_str):
    """f-string 起始 token 如 f" / f' / rf\" / f\"\"\" 的引号字符。"""
    s = tok_str.lstrip("fFrRbBuU")
    return s[:3] if s[:3] in ('"""', "'''") else s[:1]


def py312_only_fstring_issues(src):
    """返回 [(行号, 说明)]：f-string 里 3.12 才合法的写法。仅在 3.12+ 的 tokenize 下可用(它把 f-string 拆成 FSTRING_START/MIDDLE/END)。
    ①替换字段 {...} 里出现与外层相同的引号(重用引号)  ②替换字段里出现反斜杠。"""
    if not hasattr(tokenize, "FSTRING_START"):
        return None
    issues, stack = [], []          # stack：正在其中的 f-string 的引号；depth：当前是否在 {...} 内
    depth_stack = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        t = tok.type
        if t == tokenize.FSTRING_START:
            q = _quote_of(tok.string)
            if stack and depth_stack and depth_stack[-1] > 0 and q[0] == stack[-1][0]:
                issues.append((tok.start[0], f"f-string 的 {{}} 里又开了一个用 {q} 的 f-string，与外层引号相同(3.12 才允许)"))
            stack.append(q)
            depth_stack.append(0)
        elif t == tokenize.FSTRING_END:
            if stack:
                stack.pop()
                depth_stack.pop()
        elif stack:
            if t == tokenize.OP and tok.string == "{":
                depth_stack[-1] += 1
            elif t == tokenize.OP and tok.string == "}":
                depth_stack[-1] = max(0, depth_stack[-1] - 1)
            elif depth_stack[-1] > 0:
                if t == tokenize.STRING:
                    q = _quote_of(tok.string)
                    if q[0] == stack[-1][0]:
                        issues.append((tok.start[0], f"f-string 的 {{}} 里出现了与外层相同的引号 {q[0]}(3.12 才允许)：{tok.string[:30]}"))
                if "\\" in tok.string and t != tokenize.FSTRING_MIDDLE:
                    issues.append((tok.start[0], "f-string 的 {} 里出现反斜杠(3.12 才允许)"))
    return issues


def test_checker_catches_the_real_bug_that_broke_the_backfill():
    """★检查器自己要有牙：对导致回填失败的那行真实写法，必须报出来。"""
    if not hasattr(tokenize, "FSTRING_START"):
        ok("(当前不是3.12+，跳过检查器自检；真3.11编译那条仍然有效)")
        return
    bad = "rejected.append(f\"{month}: 出现{len(vals)}个口径({', '.join(f'{i['sample'][12:20]}…{i['value']:g}万吨' for i in items)})，不采用\")\n"
    iss = py312_only_fstring_issues(bad)
    assert iss and iss[0][0] == 1, f"检查器没抓到导致回填失败的那种写法：{iss}"
    ok("★检查器能抓到导致回填失败的真实写法(f-string 的 {} 里重用了单引号)")


def test_checker_does_not_cry_wolf_on_valid_311_code():
    if not hasattr(tokenize, "FSTRING_START"):
        ok("(跳过)")
        return
    good = [
        "x = f\"{a['k']}\"\n",                                  # 外双内单：合法
        "x = f'{a[\"k\"]}'\n",                                  # 外单内双：合法
        "x = f\"{', '.join(str(i) for i in items)}\"\n",       # 内部是普通字符串用不同引号：合法
        "x = f\"{a:>10}{b!r}\"\n",
        "x = f\"{f'{y}'}\"\n",                                  # 外双、内f单、内内无引号：合法
        "x = f\"总计{n}个，其中{m}个\"\n",
        "x = f\"\"\"{a['k']}\"\"\"\n",
    ]
    for g in good:
        iss = py312_only_fstring_issues(g)
        assert iss == [], f"误报了合法的 3.11 写法：{g!r} -> {iss}"
    ok("★不误报：外双内单、外单内双、内部不同引号、格式说明符、三引号等 7 种合法写法都不报")


def test_checker_flags_backslash_and_same_quote_nesting_variants():
    if not hasattr(tokenize, "FSTRING_START"):
        ok("(跳过)")
        return
    bads = [
        ("x = f\"{'a\\nb'}\"\n", "反斜杠"),
        ("x = f\"{d[\"k\"]}\"\n", "重用双引号"),
        ("x = f'{d['k']}'\n", "重用单引号"),
        ("x = f\"{f\"{y}\"}\"\n", "嵌套f-string重用双引号"),
    ]
    for src, name in bads:
        assert py312_only_fstring_issues(src), f"没抓到：{name}：{src!r}"
    ok("★能抓到 4 种 3.12 才有的写法：反斜杠、重用双引号、重用单引号、嵌套 f-string 重用引号")


def test_whole_project_has_no_py312_only_fstring():
    if not hasattr(tokenize, "FSTRING_START"):
        ok("(当前不是3.12+，跳过逐文件扫描)")
        return
    bad = []
    for f in sorted(glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True)):
        iss = py312_only_fstring_issues(open(f, encoding="utf-8").read())
        for ln, msg in iss or []:
            bad.append(f"{os.path.relpath(f, ROOT)}:{ln} {msg}")
    assert not bad, "这些写法在 GitHub Actions 的 Python 3.11 里是 SyntaxError：\n  " + "\n  ".join(bad)
    ok(f"★整个项目没有 3.12 才合法的 f-string 写法(扫描 {len(glob.glob(os.path.join(ROOT, '**', '*.py'), recursive=True))} 个文件)")


def _find_311():
    for name in ("python3.11",):
        p = shutil.which(name)
        if p:
            return p
    p = os.path.expanduser("~/.local/bin/python3.11")
    return p if os.path.exists(p) else None


def test_every_file_compiles_under_real_python311_when_available():
    p = _find_311()
    if not p:
        ok("(这台机器上没有 python3.11：跳过最权威的逐文件编译；上面的 tokenize 检查仍然有效。你本机/CI 用 3.11 跑这条更好)")
        return
    code = ("import glob,sys\nbad=[]\nfor f in sorted(glob.glob('**/*.py',recursive=True)):\n    try: compile(open(f,encoding='utf-8').read(),f,'exec')\n"
            "    except SyntaxError as e: bad.append(f'{f}:{e.lineno} {e.msg}')\nprint('\\n'.join(bad)); sys.exit(1 if bad else 0)")
    r = subprocess.run([p, "-c", code], cwd=ROOT, capture_output=True, text=True, errors="replace")
    assert r.returncode == 0, "真 Python 3.11 编译失败：\n" + r.stdout[:600]
    ver = subprocess.run([p, "--version"], capture_output=True, text=True).stdout.strip()
    ok(f"★{ver} 逐个文件编译全部通过(这就是 GitHub Actions 用的版本)")


def test_workflows_pin_python_311_and_this_guard_matches():
    import re
    vers = {}
    for f in glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")):
        for m in re.finditer(r'python-version:\s*"?([\d.]+)"?', open(f, encoding="utf-8").read()):
            vers[os.path.basename(f)] = m.group(1)
    assert vers, "没找到任何工作流的 python-version"
    assert set(vers.values()) == {"3.11"}, f"工作流的 Python 版本不是都固定在 3.11：{vers}；如果改了版本，要同步改这个守卫的假设"
    ok(f"工作流都固定在 Python 3.11：{vers}——本守卫的假设成立；以后升级版本时这条会提醒你同步")


def test_both_workflows_check_syntax_before_installing_dependencies():
    """★回填这次是跑了15秒、装完全部依赖之后才在导入时炸出语法错误。两个工作流都应该在'装依赖'之前先做一步语法检查：
    不需要任何依赖、几乎瞬间完成、失败时直接指出文件和行号。位置必须在 setup-python 之后(同一个解释器)、pip install 之前。"""
    import re
    for name in ("backfill-history.yml", "update-data.yml"):
        s = open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8").read()
        i_setup = s.index("actions/setup-python@")
        m = re.search(r"compileall", s)
        assert m, f"{name} 没有语法检查步骤(python -m compileall)"
        i_pip = s.index("pip install")
        assert i_setup < m.start() < i_pip, f"{name}：语法检查必须在 setup-python 之后、pip install 之前"
        step = s[max(0, m.start() - 300): m.start() + 300]
        assert "-q" in step or "compileall" in step
    ok("★两个工作流都在'装依赖'之前先做语法检查(setup-python 之后、pip install 之前)——语法错误会在几秒内失败并指出行号，不再跑完安装才炸")


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
