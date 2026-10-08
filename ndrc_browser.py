# -*- coding: utf-8 -*-
"""用 Selenium(无头 Chrome)读发改委价格监测中心 jgjcndrc.org.cn 的《猪料、鸡料、蛋料比价》文章列表(v101.9)。

★为什么需要浏览器：这个站点的列表页，服务器端渲染出来的永远是默认栏目("生猪出场价与玉米价格周报")，不管 URL 里写什么 sclmId；
  "猪料、鸡料、蛋料比价信息"子栏目的文章列表是页面里点了子栏目之后才加载的(导航上它只有文字、没有 href)。用 WebFetch/纯 HTTP 都拿不到(2026-10-08 实测)，
  用户在 F12 里也找不到像 Mysteel 那样的数据接口——所以按用户最初的建议用 Selenium。文章详情页本身是服务器端渲染，纯 HTTP 就能读(已验证)，浏览器只负责"拿到文章列表"。

★我没法在沙盒里验证的部分(沙盒访问不了这个站点)：真实页面的 DOM 结构、点击子栏目后列表怎么出现、"下一页"的元素。所以这个模块：
  ① 用通用的办法找元素(按文字找最小的元素，不依赖 class 名)，找不到链接时退而"点开条目、读地址栏"；
  ② 每一步都把看到的东西写进诊断(找到几个导航元素、几个条目、有几个带链接、第一个条目的 HTML 片段)，第一次真实运行如果还不对，这些诊断足够让我改对；
  ③ 浏览器用完一定关掉(finally)，有总时限，绝不抛异常到主流程。
"""
import re
import time
import fetch_data as fd

NAV_TEXT = "猪料、鸡料、蛋料比价信息"
TITLE_RX = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*第\s*(\d)\s*周\s*猪料、鸡料、蛋料比价")
DATE_RX = re.compile(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})")

# 在页面里找"标题含 YYYY年M月第N周猪料、鸡料、蛋料比价"的最小元素(自己的文字匹配、子元素不再匹配)，连同它的链接、日期文字、HTML 片段一起返回。
JS_COLLECT = r"""
const rx = /20\d{2}\s*年\s*\d{1,2}\s*月\s*第\s*\d\s*周\s*猪料、鸡料、蛋料比价/;
const dx = /20\d{2}[-\/.]\d{1,2}[-\/.]\d{1,2}/;
const res = [];
const all = Array.from(document.querySelectorAll('body *'));
for (const el of all) {
  const t = (el.innerText || '').trim();
  if (!t || t.length > 120 || !rx.test(t)) continue;
  if (Array.from(el.children).some(c => rx.test((c.innerText || '').trim()))) continue;   // 只要最小的那一层
  const a = el.closest('a') || el.querySelector('a');
  let row = el, dateText = '';
  for (let i = 0; i < 4 && row; i++, row = row.parentElement) {
    const m = (row.innerText || '').match(dx);
    if (m) { dateText = m[0]; break; }
    if ((row.innerText || '').length > 300) break;
  }
  res.push({text: t, href: a ? (a.href || '') : '', dateText: dateText,
            outer: (el.outerHTML || '').slice(0, 300), parentOuter: el.parentElement ? (el.parentElement.outerHTML || '').slice(0, 400) : ''});
}
return res;
"""

# 点击"文字恰好是 X 的最小元素"。返回 'CLICKED' 或 'NOT_FOUND'。
JS_CLICK_TEXT = r"""
const want = arguments[0];
const els = Array.from(document.querySelectorAll('body *')).filter(e => e.children.length === 0 && (e.innerText || e.textContent || '').trim() === want);
if (!els.length) return 'NOT_FOUND';
const el = els[0];
try { el.scrollIntoView({block: 'center'}); } catch (e) {}
el.click();
return 'CLICKED';
"""

# 点击第 index 个"标题匹配"的最小元素(用于条目没有链接、要靠点击进入详情页的情形)
JS_CLICK_ITEM = r"""
const rx = /20\d{2}\s*年\s*\d{1,2}\s*月\s*第\s*\d\s*周\s*猪料、鸡料、蛋料比价/;
const want = arguments[0];
const hits = Array.from(document.querySelectorAll('body *')).filter(el => {
  const t = (el.innerText || '').trim();
  return t && t.length <= 120 && rx.test(t) && !Array.from(el.children).some(c => rx.test((c.innerText || '').trim())) && t === want;
});
if (!hits.length) return 'NOT_FOUND';
try { hits[0].scrollIntoView({block: 'center'}); } catch (e) {}
hits[0].click();
return 'CLICKED';
"""

JS_BODY_HEAD = "return (document.body && document.body.innerText || '').slice(0, 400);"


def open_chrome():
    """启动无头 Chrome。GitHub Actions 的 ubuntu-latest 自带 Chrome 和 chromedriver；selenium 4.6+ 的 selenium-manager 会自己找。"""
    from selenium import webdriver
    opts = webdriver.ChromeOptions()
    for a in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--window-size=1400,2400", "--lang=zh-CN"):
        opts.add_argument(a)
    opts.page_load_strategy = "eager"
    drv = webdriver.Chrome(options=opts)
    drv.set_page_load_timeout(30)
    return drv


def week_sort_key(item):
    """排序键(越大越新)：页面日期优先，否则用标题里的'年-月-第N周'。"""
    if item.get("pageDate"):
        return (1, item["pageDate"], "")
    m = TITLE_RX.search(item.get("title") or "")
    return (0, "%04d-%02d-%d" % (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else "", "")


def _norm_date(s):
    m = DATE_RX.search(s or "")
    return "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


class SeleniumLister:
    """文章列表提供者(浏览器版)。接口：list_articles(max_pages) / page_html(url) / close()。driver_factory 可注入(测试用假 driver)。"""

    def __init__(self, driver_factory=None, total_timeout_s=90, poll_s=0.5, sleep=time.sleep, clock=time.monotonic, entry_url=None):
        self._factory = driver_factory or open_chrome
        self._drv = None
        self.total_timeout_s = total_timeout_s
        self.poll_s = poll_s
        self._sleep = sleep
        self._clock = clock
        self.entry_url = entry_url or fd.NDRC_ENTRY_LIST
        self._t0 = None

    # ---- 内部 ----
    def _left(self):
        return self.total_timeout_s - (self._clock() - self._t0)

    def _wait(self, cond, timeout):
        """轮询 cond() 直到为真或超时；返回最后一次的值(超时返回假值)。"""
        end = self._clock() + max(0.0, timeout)
        v = cond()
        while not v and self._clock() < end:
            self._sleep(self.poll_s)
            v = cond()
        return v

    def _collect(self):
        raw = self._drv.execute_script(JS_COLLECT) or []
        items = []
        for r in raw:
            m = TITLE_RX.search(r.get("text") or "")
            if not m:
                continue
            href = (r.get("href") or "").strip()
            items.append({"title": (m.group(0)), "text": r.get("text") or "", "url": (href if "detail" in href else ""), "week": "%s年%d月第%s周" % (m.group(1), int(m.group(2)), m.group(3)),
                          "pageDate": _norm_date(r.get("dateText")), "_outer": r.get("outer"), "_parent": r.get("parentOuter")})
        # 去重(同一条目可能被匹配到两层)
        seen, out = set(), []
        for it in items:
            k = (it["title"], it["pageDate"], it["url"])
            if k not in seen:
                seen.add(k)
                out.append(it)
        return out

    def _signature(self, items):
        return tuple((i["title"], i["pageDate"]) for i in items)

    def _resolve_by_click(self, it):
        """条目没有链接时：点它，读地址栏里的详情页地址和页面源码，然后退回列表。成功返回 True。"""
        before = self._drv.current_url
        r = self._drv.execute_script(JS_CLICK_ITEM, it["text"])
        if r != "CLICKED":
            return False
        moved = self._wait(lambda: "detail" in (self._drv.current_url or "") and self._drv.current_url != before, min(15, max(1, self._left())))
        if not moved:
            return False
        it["url"] = self._drv.current_url
        it["html"] = self._drv.page_source
        try:
            self._drv.back()
            self._wait(lambda: bool(self._collect()), min(15, max(1, self._left())))
        except Exception:  # noqa: BLE001
            pass
        return True

    # ---- 对外 ----
    def list_articles(self, max_pages=1, resolve_limit=3, skip_weeks=()):
        """返回 {"links": [...], "pages": n, "noNext": bool, "error": str|None, "debug": {...}}；绝不抛异常。
        links 里每项 {url,title,week,pageDate[,html]}，按"最新在前"排序。条目没有 href 时，用点击来取地址——**必须在条目还显示在页面上的那一页就点**(翻到下一页后上一页的条目就不在页面上了，
        真实浏览器验证时发现：先翻完页再点，只能点到最后一页的条目)；最多点 resolve_limit 条(None=不限，只受总时限约束)，skip_weeks 里已有的周不点(省时间)。"""
        self._t0 = self._clock()
        dbg = {"entry": self.entry_url, "steps": []}
        out = {"links": [], "pages": 0, "noNext": False, "error": None, "debug": dbg}
        try:
            self._drv = self._factory()
        except Exception as e:  # noqa: BLE001
            out["error"] = f"浏览器启动失败(selenium 没装或没有 Chrome?): {type(e).__name__}: {str(e)[:150]}"
            return out
        try:
            self._drv.get(self.entry_url)
            self._wait(lambda: bool(self._drv.execute_script("return document.body && document.body.innerText.length > 50")), min(30, self._left()))
            dbg["bodyHead"] = (self._drv.execute_script(JS_BODY_HEAD) or "")[:200]
            r = self._drv.execute_script(JS_CLICK_TEXT, NAV_TEXT)
            dbg["navClick"] = r
            if r != "CLICKED":
                out["error"] = f"页面上找不到文字为'{NAV_TEXT}'的导航元素(页面可能改版，或还没渲染出来)"
                return out
            first = self._wait(self._collect, min(30, self._left()))
            if not first:
                out["error"] = "点了子栏目后，等不到标题含'猪料、鸡料、蛋料比价'的文章条目(列表没加载出来，或被站点拦截)"
                dbg["afterClickBodyHead"] = (self._drv.execute_script(JS_BODY_HEAD) or "")[:300]
                dbg["currentUrl"] = self._drv.current_url
                return out
            links, seen, page = [], set(), 0
            items = first
            while True:
                page += 1
                for it in items:
                    k = (it["title"], it["pageDate"])
                    if k not in seen:
                        seen.add(k)
                        links.append(it)
                dbg["steps"].append({"page": page, "items": len(items), "withHref": sum(1 for i in items if i["url"])})
                for it in sorted(items, key=week_sort_key, reverse=True):          # 在这一页还显示着的时候就把没有链接的条目点开
                    if it["url"] or it["week"] in skip_weeks or self._left() <= 5:
                        continue
                    if resolve_limit is not None and dbg.get("resolveTried", 0) >= resolve_limit:
                        break
                    dbg["resolveTried"] = dbg.get("resolveTried", 0) + 1
                    if self._resolve_by_click(it):
                        dbg["resolvedByClick"] = dbg.get("resolvedByClick", 0) + 1
                if page >= max_pages or self._left() <= 5:
                    break
                sig = self._signature(items)
                if self._drv.execute_script(JS_CLICK_TEXT, "下一页") != "CLICKED":
                    out["noNext"] = True
                    break
                items = self._wait(lambda: (lambda c: c if c and self._signature(c) != sig else None)(self._collect()), min(20, max(1, self._left())))
                if not items:
                    dbg["steps"].append({"page": page + 1, "error": "点了下一页但列表没变化"})
                    out["noNext"] = True
                    break
            out["pages"] = page
            links.sort(key=week_sort_key, reverse=True)
            dbg["items"] = len(links)
            dbg["itemsWithHref"] = sum(1 for l in links if l["url"] and "html" not in l)
            if links:
                dbg["sampleOuter"] = links[0].get("_outer")
                dbg["sampleParent"] = links[0].get("_parent")
            for it in links:
                it.pop("_outer", None)
                it.pop("_parent", None)
            out["links"] = [l for l in links if l["url"]]
            if not out["links"]:
                out["error"] = f"找到{len(links)}个文章条目，但取不到任何详情页地址(条目没有链接、点击也没跳转)；诊断见 debug.sampleOuter"
            return out
        except Exception as e:  # noqa: BLE001
            out["error"] = f"浏览器读取列表时出错: {type(e).__name__}: {str(e)[:150]}"
            return out

    def page_html(self, url):
        """用浏览器取一个页面的源码(纯 HTTP 取不到详情页时的后备)。返回 (html, 错误)。"""
        try:
            if self._drv is None:
                self._t0 = self._clock()
                self._drv = self._factory()
            self._drv.get(url)
            self._wait(lambda: bool(self._drv.execute_script("return document.body && document.body.innerText.length > 50")), 20)
            return self._drv.page_source, None
        except Exception as e:  # noqa: BLE001
            return None, f"浏览器取页面失败: {type(e).__name__}: {str(e)[:120]}"

    def close(self):
        d, self._drv = self._drv, None
        if d is not None:
            try:
                d.quit()
            except Exception:  # noqa: BLE001
                pass
