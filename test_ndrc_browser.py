# -*- coding: utf-8 -*-
"""发改委《猪料、鸡料、蛋料比价》文章列表改用 Selenium 读取(v101.9)的离线测试。运行：python3 test_ndrc_browser.py
★这里测的是 **Python 这一层的编排逻辑**(等待/超时/翻页/去重/点击兜底/排序/清理/不抛异常/诊断)，用一个假的 driver：
  它按 JS 脚本的身份返回预设的"页面状态"。**真实页面的 DOM 结构、点击子栏目后列表怎么出现，我在沙盒里没法验证**(沙盒访问不了这个站点)——
  所以 JS 本身(JS_COLLECT/JS_CLICK_TEXT)只能靠第一次真实运行的诊断来校准。这是已知的、写在 TODO 里的未验证项。"""
import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd
import ndrc_browser as nb
import test_ndrc_poultry as T      # 复用真实周报夹具(P_0904/P_0301)和 web()

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def item(title, href, date, text=None):
    return {"text": text or title, "href": href, "dateText": date, "outer": f"<span>{title}</span>", "parentOuter": f"<li><span>{title}</span></li>"}


D = "https://www.jgjcndrc.org.cn/detail?clmId=1840280592963387394&tId="
W4 = "2026年9月第4周猪料、鸡料、蛋料比价"
W3 = "2026年9月第3周猪料、鸡料、蛋料比价"
W1 = "2026年3月第1周猪料、鸡料、蛋料比价"


class FakeDriver:
    """pages: 列表页序列(每页是 item 列表)；nav_delay: 点击子栏目后要再轮询几次才出现条目；click_nav: 导航元素是否存在"""

    def __init__(self, pages, nav_delay=0, click_nav=True, has_next=True, next_changes=True, resolve=None, boom_on=None, clock=None, slow_get=0,
                 works=("native", "js", "ancestor", "events"), hydrate_at=0.0, direct_ok=False, new_tab=False, native_item=True, nuxt_ids=None):
        # works: 哪些点击办法真的能让列表加载；hydrate_at: 前端框架在这个(假)时刻之后才激活，之前的点击没有任何效果；direct_ok: 直接打开带子栏目 id 的地址就能加载
        self.works, self.hydrate_at, self.direct_ok, self.clicks = set(works), hydrate_at, direct_ok, []
        self.new_tab, self.native_item, self.nuxt_ids = new_tab, native_item, nuxt_ids or []     # new_tab: 点标题在新标签页打开详情页(真实站点的行为)；native_item: 原生点击标题可用(否则只有JS点击)
        self.handles, self.cur, self.tabs, self.closed_tabs = ["main"], "main", {}, 0
        self.switch_to = self
        self.pages, self.nav_delay, self.click_nav, self.has_next, self.next_changes = pages, nav_delay, click_nav, has_next, next_changes
        self.resolve = resolve or {}          # 条目文字 -> 点击后跳转到的详情页 URL
        self.boom_on, self.clock, self.slow_get = boom_on, clock, slow_get
        self._url, self._src = "about:blank", "<html></html>"
        self.loaded, self.page_i, self.polls_after_nav, self.quit_called, self.calls, self.stack = False, 0, 0, False, [], []

    @property
    def current_url(self):
        return self.tabs[self.cur] if self.cur in self.tabs else self._url

    @current_url.setter
    def current_url(self, v):
        self._url = v

    @property
    def page_source(self):
        return f"<html>详情 {self.tabs[self.cur]}</html>" if self.cur in self.tabs else self._src

    @page_source.setter
    def page_source(self, v):
        self._src = v

    def get(self, url):
        self.calls.append(("get", url))
        if self.clock:
            self.clock.t += self.slow_get
        self.current_url = url
        self.loaded = bool(self.direct_ok and "sclmId=1840280592963387394" in url or self.direct_ok and url.endswith("list?clmId=1840280592963387394"))
        self.polls_after_nav = 0

    @property
    def window_handles(self):
        return list(self.handles)

    @property
    def current_window_handle(self):
        return self.cur

    def window(self, h):
        self.cur = h

    def close(self):
        self.handles.remove(self.cur)
        self.closed_tabs += 1

    def find_elements(self, by, expr):
        if nb.NAV_TEXT in expr:
            return [_El(self)] if self.click_nav else []
        for it in self.pages[self.page_i]:
            if it["text"] in expr and self.native_item:
                return [_El(self, it["text"])]
        return []

    def _item_click(self, text):
        url = self.resolve.get(text)
        if not url or not any(it["text"] == text for it in self.pages[self.page_i]):
            return False
        if self.new_tab:
            h = "tab%d" % (len(self.tabs) + 1)
            self.tabs[h] = url
            self.handles.append(h)
            return True
        self.stack.append(self.current_url)
        self.current_url, self.page_source = url, f"<html>详情 {url}</html>"
        return True

    def _nav_click(self, how):
        self.clicks.append(how)
        if not self.click_nav:
            return "NOT_FOUND"
        if (self.clock.t if self.clock else 0.0) >= self.hydrate_at and how in self.works:
            self.loaded, self.polls_after_nav = True, 0
        return "CLICKED"

    def back(self):
        self.calls.append(("back",))
        self.current_url = self.stack.pop() if self.stack else self.current_url

    def quit(self):
        self.quit_called = True
        if self.boom_on == "quit":
            raise RuntimeError("quit 出错")

    def execute_script(self, script, *args):
        if self.boom_on == "script":
            raise RuntimeError("脚本炸了")
        if script == nb.JS_COLLECT:
            if not self.loaded:
                return []
            self.polls_after_nav += 1
            if self.polls_after_nav <= self.nav_delay:
                return []
            return self.pages[self.page_i]
        if script == nb.JS_CLICK_TEXT:
            want = args[0]
            if want == nb.NAV_TEXT:
                return self._nav_click("js")
            if want == "下一页":
                if not self.has_next:
                    return "NOT_FOUND"
                if self.page_i + 1 < len(self.pages) and self.next_changes:
                    self.page_i += 1
                return "CLICKED"
        if script == nb.JS_CLICK_ITEM:
            return "CLICKED" if self._item_click(args[0]) else "NOT_FOUND"      # 只能点到当前页上还显示着的条目（真实浏览器验证时发现的问题）
        if script == nb.JS_NUXT_IDS:
            return self.nuxt_ids
        if script == nb.JS_CLICK_ANCESTOR:
            return self._nav_click("ancestor")
        if script == nb.JS_CLICK_EVENTS:
            return self._nav_click("events")
        if script == nb.JS_DESCRIBE:
            return {"readyState": "complete", "nuxt": True, "candidates": [], "anchors": []}
        if script == "return document.readyState":
            return "complete"
        if script == nb.JS_BODY_HEAD:
            return "监测信息 猪料、鸡料、蛋料比价信息"
        if "innerText.length > 50" in script:
            return True
        return None


class _El:
    def __init__(self, drv, item_text=None):
        self.drv, self.item_text = drv, item_text

    def is_displayed(self):
        return True

    def click(self):
        if self.item_text is not None:
            self.drv._item_click(self.item_text)
        else:
            self.drv._nav_click("native")


def lister(drv, clk=None, **kw):
    clk = clk or Clock()
    if drv.clock is None:
        drv.clock = clk
    kw.setdefault("settle_s", 0.5)
    kw.setdefault("click_wait_s", 2.0)
    kw.setdefault("direct_wait_s", 2.0)
    kw.setdefault("total_timeout_s", 90)
    return nb.SeleniumLister(driver_factory=lambda: drv, sleep=clk.sleep, clock=clk.now, **kw), clk


def test_happy_path_returns_links_newest_first_with_dates_and_closes_the_browser():
    drv = FakeDriver([[item(W1, D + "1", "2026-03-06"), item(W4, D + "4", "2026-09-25"), item(W3, D + "3", "2026-09-18")]], nav_delay=2)
    L, _ = lister(drv)
    r = L.list_articles(max_pages=1)
    L.close()
    assert r["error"] is None and [x["week"] for x in r["links"]] == ["2026年9月第4周", "2026年9月第3周", "2026年3月第1周"], r
    assert r["links"][0]["url"] == D + "4" and r["links"][0]["pageDate"] == "2026-09-25" and r["links"][0]["title"] == W4, r["links"][0]
    assert r["pages"] == 1 and r["debug"]["items"] == 3 and r["debug"]["itemsWithHref"] == 3 and drv.quit_called
    ok("★浏览器版列表：点子栏目后等条目出现(延迟2次轮询)→3个条目，按日期最新在前排序，带详情页地址/周标签/页面日期；浏览器关掉了")


def test_items_that_never_appear_give_a_timeout_error_with_diagnostics_and_no_exception():
    drv = FakeDriver([[item(W4, D + "4", "2026-09-25")]], nav_delay=10 ** 6)
    L, clk = lister(drv)
    r = L.list_articles()
    assert r["links"] == [] and "等不到" in r["error"] and r["debug"]["navClick"] == "CLICKED" and "afterClickBodyHead" in r["debug"], r
    assert clk.t <= 31, f"等待要有上限(30秒)：用了{clk.t}秒"
    L.close()
    assert drv.quit_called
    ok("★条目一直不出现：最多等30秒，错误里写明'点了子栏目后等不到条目'，诊断带上点击结果和页面开头文字；不抛异常，浏览器关掉")


def test_click_before_the_front_end_is_hydrated_does_nothing_so_the_lister_waits_then_retries():
    """★真实运行(2026-10-08)的现象：点击执行了、页面没变。假设：Nuxt 还没激活，点击无处理函数。fake 在假时刻 3.0 才激活。"""
    page = [[item(W4, D + "4", "2026-09-25")]]
    early = FakeDriver(page, hydrate_at=3.0)
    L, clk = lister(early, settle_s=0.5, click_wait_s=1.0)
    r = L.list_articles()
    assert r["error"] is None and len(r["links"]) == 1 and r["debug"]["opened"] in ("js", "ancestor", "events", "native"), r
    assert early.clicks[0] == "native" and len(early.clicks) >= 2, early.clicks          # 第一次点击没效果 → 换办法再点
    ok("★前端没激活时第一次点击无效：不放弃，换办法再点，激活后成功")


def test_each_click_strategy_is_tried_in_order_until_one_works():
    page = [[item(W4, D + "4", "2026-09-25")]]
    d = FakeDriver(page, works=("events",))
    L, _ = lister(d)
    r = L.list_articles()
    assert r["error"] is None and r["debug"]["opened"] == "events" and d.clicks == ["native", "js", "ancestor", "events"], (r["debug"], d.clicks)
    assert [a["how"] for a in r["debug"]["attempts"]] == ["native", "js", "ancestor", "events"]
    ok("★点击办法依次：原生点击→JS点击→祖先元素→完整鼠标事件，哪个先奏效用哪个，诊断记录每一步")


def test_when_no_click_works_the_direct_sub_column_url_is_tried_and_can_succeed():
    page = [[item(W4, D + "4", "2026-09-25")]]
    d = FakeDriver(page, works=(), direct_ok=True)
    L, _ = lister(d)
    r = L.list_articles()
    assert r["error"] is None and r["debug"]["opened"] == "direct" and len(r["links"]) == 1, r["debug"]
    gets = [c[1] for c in d.calls if c[0] == "get"]
    assert gets[0] == fd.NDRC_ENTRY_LIST and "sclmId=1840280592963387394" in gets[1], gets
    ok("★所有点击都无效 → 直接打开带子栏目 id 的地址，能加载就用")


def test_all_strategies_failing_leaves_complete_diagnostics():
    d = FakeDriver([[item(W4, D + "4", "2026-09-25")]], works=())
    L, clk = lister(d)
    r = L.list_articles()
    dbg = r["debug"]
    assert "等不到" in r["error"] and len(dbg["attempts"]) == 6 and dbg["describe"]["readyState"] == "complete" and dbg["currentUrl"], dbg
    assert clk.t < 30, clk.t
    ok("全部失败：错误+6次尝试(4种点击+2个直接地址)+页面现场描述，且耗时有限")


def test_item_click_opens_the_article_in_a_new_tab_and_the_lister_reads_it_and_comes_back():
    """★真实站点(2026-10-09 诊断)：条目是 <a title target=_blank> 没有 href，点击在新标签页打开详情页，原标签页地址不变。"""
    p = [item(W4, "", "2026-09-25"), item(W3, "", "2026-09-18")]
    d = FakeDriver([p], resolve={W4: D + "4", W3: D + "3"}, new_tab=True)
    L, _ = lister(d)
    r = L.list_articles(resolve_limit=2)
    assert [x["url"] for x in r["links"]] == [D + "4", D + "3"] and "详情" in r["links"][0]["html"], r
    assert d.cur == "main" and d.handles == ["main"] and d.closed_tabs == 2, (d.cur, d.handles, d.closed_tabs)
    assert [x["via"] for x in r["debug"]["resolve"]] == ["new-tab", "new-tab"], r["debug"]["resolve"]
    ok("★点标题在新标签页打开：切过去读地址和源码、关掉、切回原标签页；两条都取到")


def test_when_native_click_is_unavailable_the_js_click_is_used_for_the_new_tab_too():
    d = FakeDriver([[item(W4, "", "2026-09-25")]], resolve={W4: D + "4"}, new_tab=True, native_item=False)
    L, _ = lister(d)
    r = L.list_articles(resolve_limit=1)
    assert r["links"][0]["url"] == D + "4" and r["debug"]["resolve"][0]["click"] == "js", r["debug"]
    ok("原生点击找不到元素时退到 JS 点击")


def test_if_nothing_opens_the_article_id_is_taken_from_the_nuxt_page_data():
    d = FakeDriver([[item(W4, "", "2026-09-25")]], resolve={}, nuxt_ids=[{"key": "tId", "val": "2104842012139241474"}, {"key": "other", "val": "1111111111111111111"}])
    L, _ = lister(d)
    r = L.list_articles(resolve_limit=1)
    assert r["links"][0]["url"] == "https://www.jgjcndrc.org.cn/detail?clmId=1840280592963387394&tId=2104842012139241474", r
    assert r["debug"]["resolve"][0]["via"] == "nuxt-id"
    d2 = FakeDriver([[item(W4, "", "2026-09-25")]], resolve={}, nuxt_ids=[{"key": "a", "val": "1111111111111111111"}, {"key": "b", "val": "2222222222222222222"}])
    r2 = lister(d2)[0].list_articles(resolve_limit=1)
    assert r2["links"] == [] and "取不到任何详情页地址" in r2["error"], r2
    ok("★点击没有任何效果时，从 Nuxt 页面数据取 tId 拼地址（优先 tId/id 这类键名）；有歧义(多个候选且键名不明)就不猜")


def test_missing_navigation_element_is_reported():
    drv = FakeDriver([[]], click_nav=False)
    L, _ = lister(drv)
    r = L.list_articles()
    assert "找不到文字为" in r["error"] and r["debug"]["navClick"] == "NOT_FOUND" and r["links"] == [], r
    ok("导航元素找不到：错误写明按哪个文字找的，诊断里 navClick=NOT_FOUND")


def test_paging_collects_more_pages_dedups_and_reports_when_there_is_no_next():
    p1 = [item(W4, D + "4", "2026-09-25"), item(W3, D + "3", "2026-09-18")]
    p2 = [item(W3, D + "3", "2026-09-18"), item(W1, D + "1", "2026-03-06")]          # 第二页和第一页有重复的一条
    drv = FakeDriver([p1, p2])
    L, _ = lister(drv)
    r = L.list_articles(max_pages=5)
    assert r["pages"] == 2 and len(r["links"]) == 3 and r["noNext"] is True, r          # 第三次点"下一页"时列表没变 → 判定到头
    assert [x["url"] for x in r["links"]] == [D + "4", D + "3", D + "1"], r["links"]
    drv2 = FakeDriver([p1], has_next=False)
    L2, _ = lister(drv2)
    r2 = L2.list_articles(max_pages=5)
    assert r2["noNext"] is True and r2["pages"] == 1 and len(r2["links"]) == 2, r2
    ok("★翻页：第2页的重复条目去重；点'下一页'后列表没变/找不到'下一页'→ noNext=True，不无限翻")


def test_max_pages_is_respected():
    pages = [[item(f"2026年{m}月第1周猪料、鸡料、蛋料比价", D + str(m), f"2026-{m:02d}-05")] for m in (9, 8, 7, 6)]
    drv = FakeDriver(pages)
    L, _ = lister(drv)
    r = L.list_articles(max_pages=2)
    assert r["pages"] == 2 and len(r["links"]) == 2, r
    ok("max_pages=2 就只翻2页")


def test_items_without_links_are_resolved_by_clicking_only_for_the_newest_few():
    p = [item(W4, "", "2026-09-25"), item(W3, "", "2026-09-18"), item(W1, "", "2026-03-06")]
    drv = FakeDriver([p], resolve={W4: D + "4", W3: D + "3", W1: D + "1"})
    L, _ = lister(drv)
    r = L.list_articles(max_pages=1, resolve_limit=2)
    assert [x["url"] for x in r["links"]] == [D + "4", D + "3"], r["links"]       # 第三条没有链接且超过 resolve_limit → 不进结果
    assert "<html>详情" in r["links"][0]["html"] and r["debug"]["resolvedByClick"] == 2 and r["debug"]["itemsWithHref"] == 0, r
    assert ("back",) in drv.calls
    ok("★条目没有 href(政府站点可能用点击跳转)：只对最新的 resolve_limit 条点开、读地址栏和页面源码(省得再请求)，然后退回列表；其余无链接的不进结果")


def test_items_without_links_are_clicked_on_the_page_where_they_are_visible_before_paging_on():
    p1 = [item(W4, "", "2026-09-25"), item(W3, "", "2026-09-18")]
    p2 = [item(W1, "", "2026-03-06")]
    drv = FakeDriver([p1, p2], resolve={W4: D + "4", W3: D + "3", W1: D + "1"})
    L, _ = lister(drv)
    r = L.list_articles(max_pages=2, resolve_limit=None)
    assert [x["url"] for x in r["links"]] == [D + "4", D + "3", D + "1"], r["links"]           # 先翻完页再点的话，第1页的两条已经不在页面上了
    r2 = lister(FakeDriver([p1, p2], resolve={W4: D + "4", W3: D + "3", W1: D + "1"}))[0].list_articles(max_pages=2, resolve_limit=2)
    assert [x["url"] for x in r2["links"]] == [D + "4", D + "3"], r2["links"]
    r3 = lister(FakeDriver([p1, p2], resolve={W4: D + "4", W3: D + "3", W1: D + "1"}))[0].list_articles(max_pages=2, resolve_limit=None, skip_weeks={"2026年9月第3周"})
    assert [x["url"] for x in r3["links"]] == [D + "4", D + "1"], r3["links"]                  # 已有的周不点
    ok("★没有链接的条目在它还显示着的那一页就点开（先翻完页再点只能点到最后一页——真实 Chromium 对模拟页验证时发现的 bug）；resolve_limit 跨页计数；skip_weeks 里已有的周不点")


def test_items_with_no_links_and_no_navigation_say_so_with_the_html_sample():
    drv = FakeDriver([[item(W4, "", "2026-09-25")]], resolve={})
    L, _ = lister(drv)
    r = L.list_articles()
    assert r["links"] == [] and "取不到任何详情页地址" in r["error"] and "<span>" in r["debug"]["sampleOuter"] and "<li>" in r["debug"]["sampleParent"], r
    ok("★有条目但既没链接、点击也没跳转：错误写明，诊断带第一个条目的 HTML 片段(下一轮据此调整选择器)")


def test_an_item_with_a_non_detail_link_is_not_treated_as_an_article_link():
    drv = FakeDriver([[item(W4, "https://www.jgjcndrc.org.cn/list?clmId=1", "2026-09-25")]])
    L, _ = lister(drv)
    r = L.list_articles()
    assert r["links"] == [] and r["debug"]["itemsWithHref"] == 0, r
    ok("href 里没有 detail 的不当文章链接")


def test_factory_failure_script_failure_and_quit_failure_never_raise():
    def bad():
        raise RuntimeError("chrome not found")
    L = nb.SeleniumLister(driver_factory=bad)
    r = L.list_articles()
    assert r["links"] == [] and "浏览器启动失败" in r["error"] and "chrome not found" in r["error"], r
    L.close()
    drv = FakeDriver([[item(W4, D + "4", "2026-09-25")]], boom_on="script")
    L, _ = lister(drv)
    r = L.list_articles()
    assert "出错" in r["error"] and r["links"] == [], r
    L.close()
    assert drv.quit_called
    drv = FakeDriver([[item(W4, D + "4", "2026-09-25")]], boom_on="quit")
    L, _ = lister(drv)
    L.list_articles()
    L.close()                                  # quit 抛异常也不能冒出来
    ok("★启动失败/脚本出错/quit 出错：都不抛异常，错误写明原因，浏览器照样 quit")


def test_total_time_limit_stops_paging():
    clk = Clock()
    pages = [[item(f"2026年{m}月第1周猪料、鸡料、蛋料比价", D + str(m), f"2026-{m:02d}-05")] for m in (9, 8, 7, 6, 5, 4)]
    drv = FakeDriver(pages, clock=clk, slow_get=0)
    L, _ = lister(drv, clk, total_timeout_s=8)
    orig = L._collect

    def slow_collect():
        clk.t += 3.0                           # 每次读列表耗时3秒
        return orig()
    L._collect = slow_collect
    r = L.list_articles(max_pages=6)
    assert 1 <= r["pages"] < 6, r["pages"]
    ok("总时限(这里8秒)用完就不再翻页，返回已拿到的")


def test_close_is_idempotent_and_page_html_uses_the_browser():
    drv = FakeDriver([[]])
    L, _ = lister(drv)
    html_, err = L.page_html("https://x/detail?a=1")
    assert err is None and html_ == "<html></html>" and ("get", "https://x/detail?a=1") in drv.calls
    L.close(); L.close()
    ok("page_html 用浏览器读页面；重复 close 不出错")


def test_week_sort_key_prefers_page_date_then_title_week():
    a = {"title": W4, "pageDate": "2026-09-25"}
    b = {"title": W3, "pageDate": None}
    c = {"title": "2026年9月第3周猪料、鸡料、蛋料比价", "pageDate": "2026-09-18"}
    d = {"title": "无关", "pageDate": None}
    order = sorted([d, b, c, a], key=nb.week_sort_key, reverse=True)
    assert order[0] is a and order[1] is c and order[2] is b and order[3] is d, order
    ok("排序键：有页面日期的排前面(按日期)，没有日期的按标题里的年月周，都没有的最后")


def test_end_to_end_live_fetch_with_the_browser_lister_and_plain_http_details():
    drv = FakeDriver([[item(W4, T.URL_0904, "2026-09-25"), item(W1, T.URL_0301, "2026-03-06")]], nav_delay=1)
    L, _ = lister(drv)
    log = []
    r = fd.fetch_ndrc_poultry(now_bj=T.NOW, fetch=T.web({T.URL_0904: T.P_0904, T.URL_0301: T.P_0301}, log), lister=L)
    assert r["available"] and r["value"] == -4.10 and r["date"] == "2026-09-23" and r["weekLabel"] == "2026年9月第4周" and r["sourceUrl"] == T.URL_0904, r
    assert [x["url"] for x in log] == [T.URL_0904], "详情页纯 HTTP 读，只请求最新一篇"
    assert drv.quit_called, "抓完浏览器一定关掉"
    ok("★端到端：浏览器给出列表 → 纯 HTTP 读最新一篇详情 → -4.10（监测日09-23）；浏览器关掉；只请求1次详情页")


def test_live_fetch_falls_back_to_the_browser_for_the_detail_page_when_plain_http_fails():
    drv = FakeDriver([[item(W4, T.URL_0904, "2026-09-25")]])
    drv.page_source = T.P_0904
    L, _ = lister(drv)
    r = fd.fetch_ndrc_poultry(now_bj=T.NOW, fetch=T.web({}), lister=L)          # 纯 HTTP 什么都取不到
    assert r["available"] and r["value"] == -4.10, r
    assert ("get", T.URL_0904) in drv.calls
    ok("★详情页纯 HTTP 失败时退回用浏览器读源码")


def test_live_fetch_uses_the_page_source_captured_by_clicking_without_another_request():
    drv = FakeDriver([[item(W4, "", "2026-09-25")]], resolve={W4: T.URL_0904})
    L, _ = lister(drv)
    orig = L._resolve_by_click

    def resolve_and_set(it):
        res = orig(it)
        it["html"] = T.P_0904              # 假 driver 的 page_source 是占位，换成真实夹具
        return res
    L._resolve_by_click = resolve_and_set
    log = []
    r = fd.fetch_ndrc_poultry(now_bj=T.NOW, fetch=T.web({}, log), lister=L)
    assert r["available"] and r["value"] == -4.10 and log == [], (r, log)
    ok("点击进入详情页时已拿到源码 → 不再发第二次请求")


def test_live_fetch_reports_the_listing_failure_with_its_diagnostics():
    drv = FakeDriver([[]], click_nav=False)
    L, _ = lister(drv)
    r = fd.fetch_ndrc_poultry(now_bj=T.NOW, fetch=T.web({}), lister=L)
    assert r["available"] is False and "文章列表取不到" in r["reason"] and r["debug"]["navClick"] == "NOT_FOUND", r
    assert drv.quit_called
    ok("★列表取不到：reason 写明哪一环，debug 带浏览器诊断（会随 latest.json 出来，我据此调整）；浏览器关掉")


def test_backfill_uses_the_browser_lister_and_stores_every_week():
    import tempfile, shutil
    from datetime import date
    import backfill_history as bf
    import history_store as hs
    drv = FakeDriver([[item(W4, T.URL_0904, "2026-09-25"), item(W1, T.URL_0301, "2026-03-06")]])
    L, _ = lister(drv)
    d = tempfile.mkdtemp()
    try:
        rep = bf.backfill_poultry_ndrc(base_dir=d, today=date(2026, 10, 8), fetch=T.web({T.URL_0904: T.P_0904, T.URL_0301: T.P_0301}), lister=L, sleep_s=0)
        assert rep.get("added") == 2 or rep.get("total") == 2, rep
        pts = hs.load_series("poultry_ndrc", d)["points"]
        assert sorted(p["d"] for p in pts) == ["2026-03-04", "2026-09-23"] and drv.quit_called, pts
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★回填：浏览器列表 → 逐篇纯 HTTP 解析 → 2个周入库；浏览器关掉")


def test_backfill_reports_listing_failure_with_diagnostics():
    import tempfile, shutil
    from datetime import date
    import backfill_history as bf
    drv = FakeDriver([[]], click_nav=False)
    L, _ = lister(drv)
    d = tempfile.mkdtemp()
    try:
        rep = bf.backfill_poultry_ndrc(base_dir=d, today=date(2026, 10, 8), fetch=T.web({}), lister=L, sleep_s=0)
        assert rep.get("error") and "找不到文字为" in rep["error"] and rep["debug"]["navClick"] == "NOT_FOUND" and drv.quit_called, rep
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("回填：列表取不到时报告 error + 浏览器诊断(debug)，浏览器关掉")


def test_workflows_install_the_pinned_selenium_without_letting_a_failure_break_the_sync():
    import re
    base = os.path.dirname(os.path.abspath(__file__))
    lock = open(os.path.join(base, "requirements-selenium.lock.txt"), encoding="utf-8").read()
    reqs = [l.strip() for l in lock.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    assert any(l.startswith("selenium==") for l in reqs) and all("==" in l for l in reqs), reqs      # 精确版本，不是范围
    for wf in ("update-data.yml", "backfill-history.yml"):
        y = open(os.path.join(base, ".github", "workflows", wf), encoding="utf-8").read()
        m = re.search(r"- name: [^\n]*selenium[^\n]*\n((?:        [^\n]*\n)+)", y)
        assert m and "pip install -r requirements-selenium.lock.txt" in m.group(1) and "continue-on-error: true" in m.group(1), (wf, m and m.group(0))
    ok("★两个工作流都用锁定文件装 selenium(精确版本)，且 continue-on-error：装失败只让肉鸡一项不可用，不拖垮数据同步/其它回填")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v) and v.__module__ == __name__]

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
