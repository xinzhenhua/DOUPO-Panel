# -*- coding: utf-8 -*-
"""月度进口量/到港预报回填任务(backfill_soy_import / backfill_arrival_forecast)：写入格式、与每日累积合并、报告、容错。
用真实夹具(tests/data/mysteel_samples_20261002.json)驱动。运行：python3 test_backfill_mysteel.py"""
import os, sys, json, tempfile, shutil, traceback, copy
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd
import history_store as hs
import backfill_history as bf

_pass = 0
HERE = os.path.dirname(os.path.abspath(__file__))
FX = json.load(open(os.path.join(HERE, "tests", "data", "mysteel_samples_20261002.json"), encoding="utf-8"))["samples"]


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="mbf_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def as_items(rows):
    return [{"publishTime": f"{r['d']} 16:30", "title": r.get("title", ""), "content": r["text"], "url": None} for r in rows]


def fake_search(items, calls=None):
    def _s(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        if calls is not None:
            calls.append({"query": query, "start": start.date().isoformat(), "end": end.date().isoformat(), "url": url})
        return list(items), len(items), None
    return _s


def pts(d, key):
    return hs.load_series(key, d)["points"]


# ===================== 进口量 =====================
def test_soy_import_writes_cross_verified_months_in_the_daily_accumulation_format():
    with Tmp() as d:
        calls = []
        rep = bf.backfill_soy_import(base_dir=d, today=date(2026, 10, 1), search=fake_search(as_items(FX["soy_import"]), calls))
        p = pts(d, "soy_import")
        assert len(p) == rep["added"] == 48 and rep["how"] == {"agree": 25, "single": 13, "single_inferred": 10}
        assert all(len(x["d"]) == 7 and x["d"][4] == "-" for x in p), "d='YYYY-MM'，与每日累积一致"
        by = {x["d"]: x for x in p}
        assert by["2023-08"]["v"] == 936.0 and by["2023-08"]["x"] == {"how": "agree", "n": 3}, by["2023-08"]
        assert by["2026-02"]["v"] == 597.6 and by["2026-03"]["v"] == 401.9, "全角'1－2月'累计(1254.7)被排除，真正的2月是597.6；3月401.9与latest.json里'2026年最低'吻合"
        assert by["2022-01"]["x"]["how"] == "single" and "pub" in by["2022-01"]
        assert calls[0]["query"] == "海关总署中国大豆进口量" and calls[0]["url"] == fd.MYSTEEL_ARTICLE_SEARCH_URL and calls[0]["start"] == "2022-01-01"
    ok("★进口量：用真实夹具写入48个月(25个多篇一致+13个单篇+10个单篇推断年份)，格式与每日累积一致；2023-08=936、2026-02=597.6(全角1－2月累计被排除)、2026-03=401.9")


def test_soy_import_report_lists_what_was_not_adopted_and_why():
    with Tmp() as d:
        rep = bf.backfill_soy_import(base_dir=d, today=date(2026, 10, 1), search=fake_search(as_items(FX["soy_import"])))
        na = {x["month"]: x for x in rep["notAdopted(只有一篇且年份靠推断/超范围)"]}
        assert na == {}, "夹具里没有间隔>3个月的推断年份single，也没有超范围值"
        assert rep["doubtful(同月数值冲突)"] == []
        assert any("累计" in x for x in rep["excludedWordings(累计/去年/对比等，前8条)"])
        assert "1-2月累计没有单月数据" in rep["notes"][-1]
    ok("报告：未采用为空(夹具里没有回顾类/超范围)、0个同月冲突、被排除的累计写法有记录、说明1-2月缺失是真实的")
    # 回顾类文章(间隔>3个月)确实会进入notAdopted并写明原因
    items = [{"publishTime": "2024-09-10 10:00", "title": "海关总署：3月份中国大豆进口量为554.1万吨", "content": "", "url": None}]
    with Tmp() as d:
        rep = bf.backfill_soy_import(base_dir=d, today=date(2026, 10, 1), search=fake_search(items))
        assert pts(d, "soy_import") == [] and "回顾类" in rep["notAdopted(只有一篇且年份靠推断/超范围)"][0]["why"] and rep["notAdopted(只有一篇且年份靠推断/超范围)"][0]["month"] == "2024-03"
    ok("回顾类文章(发布月-数据月=6个月)：不写入，notAdopted里写明'回顾类文章容易引用旧月份'")


def test_soy_import_merges_with_daily_accumulation_not_duplicates():
    with Tmp() as d:
        # 每日累积先写入了2026-08(明确的monthLabel)
        hs.record_points("soy_import", [{"d": "2026-08", "v": 1214.14, "pub": "2026-09-09"}], d)
        bf.backfill_soy_import(base_dir=d, today=date(2026, 10, 1), search=fake_search(as_items(FX["soy_import"])))
        p = pts(d, "soy_import")
        assert [x["d"] for x in p].count("2026-08") == 1 and next(x for x in p if x["d"] == "2026-08")["v"] == 1214.14, "回填没有覆盖每日累积的值，也没有重复"
        assert [x["d"] for x in p] == sorted({x["d"] for x in p}), "按月份有序、无重复"
        n1 = len(p)
        bf.backfill_soy_import(base_dir=d, today=date(2026, 10, 1), search=fake_search(as_items(FX["soy_import"])))
        assert len(pts(d, "soy_import")) == n1, "重复运行无变化(幂等)"
    ok("与每日累积合并：2026-08不重复、没被覆盖；按月有序；重复运行幂等")


def test_soy_import_drops_implausible_values():
    items = [{"publishTime": "2025-07-14 10:00", "title": "海关总署：2025年6月中国大豆进口量为12264万吨", "content": "", "url": None},
             {"publishTime": "2025-07-15 10:00", "title": "海关总署：2025年6月中国大豆进口量为12264万吨", "content": "", "url": None}]
    with Tmp() as d:
        rep = bf.backfill_soy_import(base_dir=d, today=date(2026, 10, 1), search=fake_search(items))
        assert pts(d, "soy_import") == [] and rep["notAdopted(只有一篇且年份靠推断/超范围)"][0]["why"].startswith("超出合理范围")
    ok("数值超出合理范围(200~2000万吨)：即使两篇一致也不写入，报告写明")


# ===================== 到港预报 =====================
def test_arrival_writes_29_continuous_months_in_the_daily_accumulation_format():
    with Tmp() as d:
        calls = []
        rep = bf.backfill_arrival_forecast(base_dir=d, today=date(2026, 10, 1), search=fake_search(as_items(FX["arrival"]), calls))
        p = pts(d, "arrival_forecast")
        assert len(p) == rep["added"] == 29 and p[0]["d"] == "2024-02" and p[-1]["d"] == "2026-06"
        assert all(len(x["d"]) == 7 and "pub" in x and "ships" in x["x"] for x in p), "d=预报月份'YYYY-MM'，带发布日和船数，与每日累积一致"
        by = {x["d"]: x for x in p}
        assert by["2024-08"]["v"] == 1043.25 and by["2024-08"]["x"]["ships"] == 160.5, "'主要油厂'那一篇没漏"
        assert by["2026-02"]["v"] == 500.5 and by["2025-06"]["v"] == 1056.25
        assert not ({"2023-11", "2023-12", "2024-01"} & set(by)), "双口径的三个月不写入"
        assert calls[0]["query"] == "大豆到港预报"
    ok("★到港预报：用真实夹具写入2024-02~2026-06连续29个月(2024-08的'主要油厂'没漏)，格式与每日累积一致；2023-11/12、2024-01双口径不写入")


def test_arrival_report_explains_exclusions_and_the_newer_wording_boundary():
    with Tmp() as d:
        rep = bf.backfill_arrival_forecast(base_dir=d, today=date(2026, 10, 1), search=fake_search(as_items(FX["arrival"])))
        ex = " ".join(str(x) for x in rep["excluded(同一篇多个口径/超范围)"])
        assert "2023-11" in ex and "2个口径" in ex and "783.25" in ex and "845" in ex
        assert "2026-06之后的新写法" in rep["notes"][-1] and "每日累积接上" in rep["notes"][-1]
    ok("报告：写明双口径月份被排除的原因和两个值；写明2026-06之后新写法由每日累积接上、回填不处理")


def test_arrival_same_month_in_several_articles_takes_the_latest_publication():
    items = [{"publishTime": "2025-03-27 10:00", "title": "", "content": "2025年4月份国内全样本油厂大豆到港预估125.8船，共计约817.7万吨（本月船重按6.5万吨计）", "url": None},
             {"publishTime": "2025-04-10 10:00", "title": "", "content": "2025年4月份国内全样本油厂大豆到港预估130船，共计约845万吨（本月船重按6.5万吨计）", "url": None}]
    with Tmp() as d:
        bf.backfill_arrival_forecast(base_dir=d, today=date(2026, 10, 1), search=fake_search(items))
        p = pts(d, "arrival_forecast")
        assert len(p) == 1 and p[0]["v"] == 845.0 and p[0]["pub"] == "2025-04-10", "同月多篇(修订/转载)取发布最晚的一篇(最终预估)"
    ok("同一个月多篇(修订)：取发布最晚的一篇")


def test_arrival_merges_with_daily_accumulation():
    with Tmp() as d:
        hs.record_points("arrival_forecast", [{"d": "2026-10", "v": 854.1, "pub": "2026-09-24"}], d)
        bf.backfill_arrival_forecast(base_dir=d, today=date(2026, 10, 1), search=fake_search(as_items(FX["arrival"])))
        p = pts(d, "arrival_forecast")
        assert p[-1]["d"] == "2026-10" and p[-1]["v"] == 854.1 and len(p) == 30, "每日累积的2026-10(新写法)保留，回填的29个月在前"
    ok("与每日累积合并：2026-10(新写法，由每日累积记录)保留，回填的29个月在前，共30个月")


# ===================== 公共 =====================
def test_failure_modes_empty_and_garbage():
    with Tmp() as d:
        r1 = bf.backfill_soy_import(base_dir=d, today=date(2026, 10, 1), search=fake_search([]))
        r2 = bf.backfill_arrival_forecast(base_dir=d, today=date(2026, 10, 1), search=fake_search([]))
        assert r1["added"] == 0 and r2["added"] == 0 and pts(d, "soy_import") == [] and pts(d, "arrival_forecast") == []
        junk = [{"publishTime": "乱码", "title": "x", "content": "海关总署2023年8月份中国大豆进口量936万吨"}, {"publishTime": "2025-01-01 10:00", "title": None, "content": None}]
        bf.backfill_soy_import(base_dir=d, today=date(2026, 10, 1), search=fake_search(junk))
        bf.backfill_arrival_forecast(base_dir=d, today=date(2026, 10, 1), search=fake_search(junk))
    ok("空结果/日期乱码/title和content为None：不报错、不写入")


def test_registered_and_in_default_jobs():
    assert "soy_import" in bf.JOBS and "arrival" in bf.JOBS and "soy_import" in bf.DEFAULT_JOBS and "arrival" in bf.DEFAULT_JOBS
    # v101.4：原来这里断言"豆菜粕价差的回填有意不做(口径2026-06换了)"。2026-10-02 的真实采样推翻了这个判断：主系列《国内主要市场豆菜粕价差统计分析》
    #   211篇、2024-01~2026-09，区间写法与城市单值写法在切换点上数值连续(区间680↔单值696.7、区间800↔单值826.7)，用户也明确要求做。
    #   原守卫想防的"口径不一致的文章混进来"现在由两处承担：①标题必须含"价差统计分析"(月度解读等其它类文章排除)；②报告标出口径切换点。见 test_rmspread_backfill.py。
    assert "rm_spread" in bf.JOBS and "rm_spread" in bf.DEFAULT_JOBS and bf.JOBS["rm_spread"] is bf.backfill_rm_spread
    # v96.3时开机率的回填也是有意不做(评分规则要先改)；v98重做了开机率规则(滚动365天分位)需要历史，所以现在做了(见test_crush_rate_rule.py)
    assert "crush_rate" in bf.JOBS and "crush_rate" in bf.DEFAULT_JOBS
    assert bf.JOBS["soy_import"] is bf.backfill_soy_import and bf.JOBS["arrival"] is bf.backfill_arrival_forecast
    ok("两个任务已注册并进默认清单；豆菜粕价差回填v101.4起有了(主系列标题过滤+城市平均优先，见test_rmspread_backfill.py)；开机率回填v98起有了(规则重做要用历史)")


def test_no_body_fetch_no_link_following():
    old = fd.fetch_text_debug
    fd.fetch_text_debug = lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应抓正文"))
    try:
        with Tmp() as d:
            items = [{"publishTime": "2025-07-14 10:00", "title": "海关总署：2025年6月中国大豆进口量为1226.4万吨", "content": "x", "url": "https://evil.example.com/a"}]
            bf.backfill_soy_import(base_dir=d, today=date(2026, 10, 1), search=fake_search(items))
            bf.backfill_arrival_forecast(base_dir=d, today=date(2026, 10, 1), search=fake_search(items))
    finally:
        fd.fetch_text_debug = old
    ok("只用搜索摘要：不抓正文、不跟随任何链接(含不可信域名的url)")


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
