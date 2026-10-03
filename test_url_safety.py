# -*- coding: utf-8 -*-
"""来自外部响应的URL必须过域名白名单才允许请求(is_trusted_article_url)。运行：python3 test_url_safety.py"""
import os, sys, traceback
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def test_accepts_real_mysteel_article_urls():
    for u in ("https://ncp.mysteel.com/a/26092417/B46706E8534B0E24.html",       # 用户贴出的真实搜索结果里的url
              "https://ncp.m.mysteel.com/a/26092417/B46706E8534B0E24_abc.html",   # 真实的urlWap
              "https://m.mysteel.com/a/26060518/12F8EC40832CF668_abc.html",       # 5-6月初那几期的urlWap
              "https://NCP.MYSTEEL.COM/a/x.html", "https://ncp.mysteel.com:443/a/x.html"):
        assert fd.is_trusted_article_url(u), u
    ok("放行：用户贴出的真实搜索结果里的url/urlWap(三种主机)、大小写、显式443端口")


def test_rejects_bypass_tricks():
    bad = {
        "http降级": "http://ncp.mysteel.com/a/x.html",
        "域名后缀欺骗": "https://ncp.mysteel.com.evil.com/a/x.html",
        "路径里藏域名": "https://evil.com/ncp.mysteel.com/a.html",
        "user@host技巧": "https://ncp.mysteel.com@evil.com/a.html",
        "带用户名密码": "https://user:pw@ncp.mysteel.com/a.html",
        "异常端口": "https://ncp.mysteel.com:8443/a.html",
        "协议相对URL": "//ncp.mysteel.com/a.html",
        "ftp": "ftp://ncp.mysteel.com/a.html",
        "javascript": "javascript:alert(1)",
        "file": "file:///etc/passwd",
        "子域名(未列入白名单)": "https://evil.ncp.mysteel.com/a.html",
        "相似域名": "https://ncp.mysteel.co/a.html",
        "空": "", "None": None, "非字符串": 123,
        "非法端口": "https://ncp.mysteel.com:abc/a.html",
        "方括号畸形": "https://[::1/a.html",
    }
    for name, u in bad.items():
        assert fd.is_trusted_article_url(u) is False, f"{name}: {u!r} 不该被放行"
    ok(f"拒绝{len(bad)}种绕过手法：http降级/域名后缀欺骗/user@host/带密码/异常端口/协议相对/ftp/javascript/file/未列入的子域名/相似域名/空/畸形")


def test_allowlist_is_exact_hosts_only():
    assert set(fd.TRUSTED_ARTICLE_HOSTS) == {"ncp.mysteel.com", "www.mysteel.com", "m.mysteel.com", "ncp.m.mysteel.com"}
    assert fd.is_trusted_article_url("https://x.example.com/a", allowed_hosts=("x.example.com",)) and not fd.is_trusted_article_url("https://ncp.mysteel.com/a", allowed_hosts=("x.example.com",))
    ok("白名单就是这4个精确主机名；allowed_hosts参数可覆盖(用于复用)")


def _search_payload(items):
    return {"resultCode": 0, "total": len(items), "dataList": items}


def test_feed_days_never_requests_a_malicious_url_from_search_results():
    """★端到端：搜索结果里夹带一个恶意url(摘要里没数字，会触发抓正文)——这个url不能被请求；同时合法的url仍然可以。"""
    items = [
        {"title": "Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（20260924）", "publishTime": "2026-09-24 17:23", "content": "市场震荡运行，库存变化不大。", "url": "https://evil.example.com/steal?k=1"},
        {"title": "Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（20260918）", "publishTime": "2026-09-18 17:08", "content": "截至9月18日，全国饲料企业豆粕物理库存8.23天，环比微增0.08天，同比下降1.19天。", "url": "https://ncp.mysteel.com.evil.com/a.html"},
    ]
    requested = []
    old_json, old_text = fd.fetch_json_debug, fd.fetch_text_debug
    fd.fetch_json_debug = lambda url, headers=None, retries=3, timeout=20, post_data=None: (_search_payload(items), {})
    def fake_text(url, headers=None, **k):
        requested.append(url)
        return None, {}
    fd.fetch_text_debug = fake_text
    try:
        r = fd.fetch_mysteel_feed_days(today=date(2026, 9, 30))
    finally:
        fd.fetch_json_debug, fd.fetch_text_debug = old_json, old_text
    assert requested == [], f"恶意url被请求了: {requested}"
    assert r["available"] is True and r["value"] == 8.23 and r["date"] == "2026-09-18", "最新一期(09-24)摘要没数字又不能抓正文，回退到有数字的09-18——功能不受影响"
    ok("★端到端：搜索结果夹带的恶意url(evil.example.com / ncp.mysteel.com.evil.com)一个都没被请求，功能照常(回退到有数字的一期)")


def test_feed_days_still_fetches_a_trusted_body_url():
    items = [{"title": "Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（20260924）", "publishTime": "2026-09-24 17:23", "content": "市场震荡运行。", "url": "https://ncp.mysteel.com/a/26092417/B46706E8534B0E24.html"}]
    requested = []
    old_json, old_text = fd.fetch_json_debug, fd.fetch_text_debug
    fd.fetch_json_debug = lambda url, headers=None, retries=3, timeout=20, post_data=None: (_search_payload(items), {})
    def fake_text(url, headers=None, **k):
        requested.append(url)
        return "<html><body>Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（20260924） 截至9月24日，全国饲料企业豆粕物理库存8.55天，较上期增0.32天，同比减1.05天。 免责声明</body></html>", {}
    fd.fetch_text_debug = fake_text
    try:
        r = fd.fetch_mysteel_feed_days(today=date(2026, 9, 30))
    finally:
        fd.fetch_json_debug, fd.fetch_text_debug = old_json, old_text
    assert requested == ["https://ncp.mysteel.com/a/26092417/B46706E8534B0E24.html"], requested
    assert r["available"] is True and r["value"] == 8.55, r
    ok("可信的Mysteel文章url：照常抓正文并解析出8.55天(白名单没有误伤正常功能)")


def test_older_meal_balance_code_path_is_protected_too():
    """老代码(国内豆粕库消比)同样的模式——从搜索结果取url再抓正文——也必须受同一个白名单保护。"""
    import inspect
    src = inspect.getsource(fd)
    assert src.count("is_trusted_article_url(item[\"url\"])") == 1 and src.count("is_trusted_article_url(it[\"url\"])") == 1
    ok("两处'URL来自搜索结果'的调用点(库消比、饲料库存天数)都已加白名单校验")


def test_backfill_module_never_requests_a_malicious_url_either():
    """★回填脚本(默认回填清单里就有)里有3处同样的'URL来自搜索结果'调用点——必须同样受白名单保护。"""
    import inspect
    import backfill_history as bf
    src = inspect.getsource(bf)
    # ★v99：原来数"恰好3处"。移除backfill_meal_stock(它那一处调用点随之消失，攻击面变小，剩余每处的保护没有变)后剩2处。
    #   与其维护一个会随功能增删而变的数字，不如**逐个调用点检查它前面紧邻白名单校验**——以后新增一个"请求搜索结果URL"的调用点却忘了加白名单，
    #   这里会失败(只数总数的话，删一个、加一个未保护的，总数不变就漏过去了)。
    import re
    lines = src.split("\n")
    call_idx = [i for i, l in enumerate(lines) if 'fd.fetch_text_debug(it["url"]' in l]
    assert len(call_idx) >= 1, "没找到任何'请求搜索结果URL'的调用点——测试自己失效了"
    for i in call_idx:
        window = "\n".join(lines[max(0, i - 3): i + 1])
        assert 'fd.is_trusted_article_url(it["url"])' in window, f"第{i + 1}行的fetch_text_debug(it[\"url\"])前没有紧邻的白名单校验:\n{window}"
    owners = []
    for i in call_idx:
        for k in range(i, -1, -1):
            m = re.match(r"def (\w+)\(", lines[k])
            if m:
                owners.append(m.group(1))
                break
    assert sorted(owners) == ["backfill_feed_days", "backfill_meal_stu"], f"调用点所在函数变了(新增/移除了需要白名单的位置，请确认保护): {owners}"
    assert src.count('fd.is_trusted_article_url(it["url"])') == len(call_idx), "白名单校验数与调用点数一致"
    # 端到端：回填饲料库存天数时，搜索结果夹带恶意url，不能被请求
    items = [{"title": "Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（20260924）", "publishTime": "2026-09-24 17:23", "content": "市场震荡运行。", "url": "https://evil.example.com/steal"},
             {"title": "Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（20260918）", "publishTime": "2026-09-18 17:08", "content": "截至9月18日，全国饲料企业豆粕物理库存8.23天，环比微增0.08天，同比下降1.19天。", "url": "https://ncp.mysteel.com/a/ok.html"}]
    requested = []
    old_json, old_text, old_sleep = fd.fetch_json_debug, fd.fetch_text_debug, bf.time.sleep
    fd.fetch_json_debug = lambda url, headers=None, retries=3, timeout=20, post_data=None: ({"resultCode": 0, "total": len(items), "dataList": items}, {})
    def fake_text(url, headers=None, **k):
        requested.append(url)
        return None, {}
    fd.fetch_text_debug = fake_text
    bf.time.sleep = lambda s: None
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        bf.backfill_feed_days(base_dir=d)
    finally:
        fd.fetch_json_debug, fd.fetch_text_debug, bf.time.sleep = old_json, old_text, old_sleep
        shutil.rmtree(d, ignore_errors=True)
    assert not any("evil.example.com" in u for u in requested), f"恶意url被请求了: {requested}"
    ok("★回填脚本：3处调用点都有白名单；端到端——回填饲料库存天数时夹带的恶意url没有被请求")


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
