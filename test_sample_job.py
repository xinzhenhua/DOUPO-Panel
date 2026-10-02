# -*- coding: utf-8 -*-
"""采样诊断(backfill_sample)：把Mysteel各指标的真实措辞收集回来，按"含关键词的那一句"聚类，扫描口径变化类字样。运行：python3 test_sample_job.py"""
import os, sys, json, tempfile, shutil, traceback
from datetime import date, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd
import backfill_history as bf

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="smp_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


# 用户latest.json里的真实开机率快讯(2026-09-29)
REAL_FLASH = "9月29日成交方面，全国主要油厂豆粕成交12.89万吨，较前一交易日减0.05万吨，其中现货成交10.99万吨，较前一交易日增1.05万吨，远月基差成交1.90万吨，较前一交易日减1.10万吨。\r\n\r\n开机方面，今日全国动态全样本油厂开机率为60.95%，较前一日下降1.20%。"


def mk(d, text, title="", url=None):
    return {"publishTime": f"{d} 16:30", "title": title, "content": text, "url": url}


def fake_search(items_by_query, calls=None):
    def _s(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        if calls is not None:
            calls.append({"query": query, "url": url, "start": start.date().isoformat(), "end": end.date().isoformat(), "max_pages": max_pages})
        its = items_by_query.get(query, [])
        return list(its), len(its), None
    return _s


def test_indicator_table_matches_production_queries():
    """采样用的查询词/接口必须和生产抓取函数完全一致，否则采回来的措辞不是生产会遇到的。"""
    expect = {"crush_rate": ("flash", "全国动态全样本油厂开机率"), "meal_stock": ("article", "全国主要区域大豆"), "basis": ("article", "全国主要市场豆粕基差价格汇总"),
              "arrival": ("article", "大豆到港预报"), "soy_import": ("article", "海关总署中国大豆进口量"), "poultry": ("article", "白羽肉鸡养殖利润"),
              "rm_spread": ("article", "豆菜粕价差"), "sow": ("article", "季度末能繁母猪存栏")}
    assert {k: (v[1], v[2]) for k, v in bf.SAMPLE_INDICATORS.items()} == expect
    import inspect
    src = inspect.getsource(fd)
    for ch, q in expect.values():
        assert f'"{q}"' in src, f"生产代码里找不到查询词{q}"
    assert "def fetch_mysteel_crush_rate" in src and 'MYSTEEL_SEARCH_URL, headers=headers' in src, "开机率生产里走的是快讯接口"
    ok("采样的8个指标：查询词、接口(开机率=快讯，其余=文章)与生产抓取函数完全一致")


def test_focus_sentence_and_wording_pattern_on_the_real_flash():
    s = bf._focus_sentence(REAL_FLASH, "开机率")
    assert s == "开机方面，今日全国动态全样本油厂开机率为60.95%，较前一日下降1.20%", s
    assert bf._focus_sentence("没有关键词的一段话。", "开机率") == "" and bf._focus_sentence("", "开机率") == "" and bf._focus_sentence(None, "x") == ""
    p1 = bf._wording_pattern("今日全国动态全样本油厂开机率为60.95%，较前一日下降1.20%")
    p2 = bf._wording_pattern("今日全国动态全样本油厂开机率为58.3%，较前一日上升0.4%")
    assert p1 == "今日全国动态全样本油厂开机率为#，较前一日下降#" and p2 != p1, "'下降/上升'是不同措辞，指纹应当不同(它影响环比符号解析)"
    assert bf._wording_pattern("2026年9月28日全国开机率为60%") == bf._wording_pattern("2026年9月29日全国开机率为61%") == "D全国开机率为#"
    assert bf._wording_pattern("截至9月24日 第39周 库存129.64万吨") == "截至DD库存#万吨", bf._wording_pattern("截至9月24日 第39周 库存129.64万吨")      # 日期→D后再去空白，所以两个D连在一起
    ok("焦点句(用真实开机率快讯)；措辞指纹：数字/日期→占位符，'下降/上升'这种会影响解析的差别保留，同写法不同日期同指纹")


def test_wording_change_is_visible_in_clusters_with_dates():
    """★核心场景：措辞在某个日期变过。聚类要能一眼看出'旧写法最后一次出现在哪天、新写法从哪天开始'。"""
    old = [mk(f"2023-0{m}-{d:02d}", f"今日全国油厂开机率为{50 + m}.{d}%，较前一日增{d}.0%") for m in (3, 4) for d in (6, 13, 20)]
    new = [mk(f"2024-0{m}-{d:02d}", f"今日全国动态全样本油厂开机率为{60 + m}.{d}%，较前一日下降{d}.0%") for m in (3, 4) for d in (6, 13, 20)]
    with Tmp() as d:
        calls = []
        rep = bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), only=["crush_rate"], search=fake_search({"全国动态全样本油厂开机率": old + new}, calls))
        ind = rep["indicators"][0]
        assert ind["fetched"] == 12 and ind["firstDate"] == "2023-03-06" and ind["lastDate"] == "2024-04-20"
        cl = {c["pattern"]: c for c in ind["wordingClusters(按次数，前10；措辞在哪个日期段出现，一眼看出什么时候改过)"]}
        assert ind["wordingClusterCount"] == 2 and len(cl) == 2
        oldc = next(c for p, c in cl.items() if "动态全样本" not in p)
        newc = next(c for p, c in cl.items() if "动态全样本" in p)
        assert (oldc["first"], oldc["last"], oldc["count"]) == ("2023-03-06", "2023-04-20", 6), oldc
        assert (newc["first"], newc["last"], newc["count"]) == ("2024-03-06", "2024-04-20", 6), newc
        assert "全国动态全样本" in newc["example"] and "全国油厂开机率" in oldc["example"]
    ok("★措辞变过：聚类显示旧写法(2023-03-06~04-20，6条)和新写法'动态全样本'(2024-03-06~04-20，6条)——哪天换的一目了然")


def test_caliber_words_are_detected_with_context_and_dates():
    items = [mk("2026-07-06", "2026年第27周，全国主要油厂豆粕库存环比减少2.45%。"),
             mk("2026-08-03", "2026年第31周豆粕库存上升。特别声明：为了数据更能贴合市场变化趋势，Mysteel农产品对样本点进行了优化，自2024年1月5日（第一周）开始，网页端只发一版动态全样本数据，原口径历史数据在钢联数据终端可查看。"),
             mk("2026-09-07", "2026年第36周豆粕库存下降。特别声明：为了数据更能贴合市场变化趋势，Mysteel农产品对样本点进行了优化，自2024年1月5日（第一周）开始，网页端只发一版动态全样本数据。")]
    with Tmp() as d:
        rep = bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), only=["meal_stock"], search=fake_search({"全国主要区域大豆": items}))
        cw = {c["word"]: c for c in rep["indicators"][0]["caliberWords(口径变化类字样)"]}
        assert cw["特别声明"]["count"] == 2 and cw["特别声明"]["first"] == "2026-08-03" and cw["特别声明"]["last"] == "2026-09-07"
        assert cw["动态全样本"]["count"] == 2 and cw["原口径"]["count"] == 1 and cw["样本点"]["count"] == 2
        assert "2024年1月5日" in cw["特别声明"]["context"] or "为了数据更能贴合" in cw["特别声明"]["context"]
        assert "口径调整" not in cw and "停止发布" not in cw, "没出现的字样不列"
    ok("★口径变化类字样：特别声明/动态全样本/原口径/样本点，带次数、最早最晚日期和上下文(周度库存那条声明就是这样才发现的)；没出现的不列")


def test_samples_file_content_and_sampling():
    items = [mk(f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", f"今日全国动态全样本油厂开机率为{50 + i % 20}.5%，较前一日增0.1%。" + "无关内容" * 80, title=f"快讯{i}") for i in range(300)]
    with Tmp() as d:
        rep = bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), only=["crush_rate"], max_items=50, search=fake_search({"全国动态全样本油厂开机率": items}))
        data = json.load(open(os.path.join(d, "_samples.json"), encoding="utf-8"))
        smp = data["samples"]["crush_rate"]
        assert len(smp) == 50, "抽样条数=max_items"
        assert smp[0]["d"] == "2025-01-01" and smp[-1]["d"] == max(i["publishTime"][:10] for i in items), "始终含最早和最晚"
        assert all(len(x["text"]) <= 240 for x in smp), "正文截到240字"
        assert [x["d"] for x in smp] == sorted(x["d"] for x in smp), "按时间升序"
        assert data["from"] == "2022-01-01" and "generatedAt" in data
        ind = rep["indicators"][0]
        assert ind["fetched"] == 300 and ind["searchTotal"] == 300 and rep["samplesFile"] == "data/history/_samples.json"
        rep_json = json.dumps(rep, ensure_ascii=False)
        assert "无关内容" * 40 not in rep_json, "320字的无关内容整段不应出现在报告摘要里(例子只截80字)"
        assert all(len(c["example"]) <= 50 for c in ind["wordingClusters(按次数，前10；措辞在哪个日期段出现，一眼看出什么时候改过)"]), "聚类例子最多50字"
    ok("样本文件：均匀抽样max_items条(含最早最晚)、正文截240字、按时间升序；报告摘要里不放大段原文")


def test_does_not_write_any_history_series_or_follow_links():
    with Tmp() as d:
        before = set(os.listdir(d))
        calls = []
        bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), search=fake_search({"全国动态全样本油厂开机率": [mk("2026-09-29", REAL_FLASH, url="https://evil.example.com/x")]}, calls))
        after = set(os.listdir(d))
        assert after - before == {"_samples.json"}, f"只应写出_samples.json: {after - before}"
        assert len(calls) == 8, "8个指标各搜一次"
        data = json.load(open(os.path.join(d, "_samples.json"), encoding="utf-8"))
        assert data["samples"]["crush_rate"][0]["url"] is None, "不可信域名的url不写进样本文件(采样本身也不跟随任何链接)"
    old_t = fd.fetch_text_debug
    fd.fetch_text_debug = lambda *a, **k: (_ for _ in ()).throw(AssertionError("采样不应该抓正文"))
    try:
        with Tmp() as d2:
            bf.backfill_sample(base_dir=d2, today=date(2026, 10, 1), search=fake_search({}))
    finally:
        fd.fetch_text_debug = old_t
    ok("采样只写_samples.json、不写任何历史序列、不抓任何正文；不可信域名的url不进样本文件")


def test_search_params_use_production_endpoints_and_window():
    calls = []
    with Tmp() as d:
        bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), search=fake_search({}, calls))
    by = {c["query"]: c for c in calls}
    assert by["全国动态全样本油厂开机率"]["url"] == fd.MYSTEEL_SEARCH_URL, "开机率走快讯接口"
    assert all(c["url"] == fd.MYSTEEL_ARTICLE_SEARCH_URL for q, c in by.items() if q != "全国动态全样本油厂开机率"), "其余走文章接口"
    assert all(c["start"] == "2022-01-01" and c["end"] == "2026-10-01" for c in calls), "默认从2022-01-01起(覆盖2024-01-05口径断点前后)到今天"
    with Tmp() as d:
        calls2 = []
        bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), start=date(2024, 1, 1), only=["basis", "sow"], search=fake_search({}, calls2))
        assert [c["query"] for c in calls2] == ["全国主要市场豆粕基差价格汇总", "季度末能繁母猪存栏"] and all(c["start"] == "2024-01-01" for c in calls2)
    ok("搜索参数：开机率走快讯接口、其余走文章接口；默认2022-01-01起；start/only可控")


def test_failure_isolation_and_empty_results():
    def flaky(query, start, end, max_pages=40, url=None, sleep_s=0.5):
        if "开机率" in query:
            raise RuntimeError("接口挂了")
        return [], 0, "搜索接口无返回/返回异常"
    with Tmp() as d:
        rep = bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), search=flaky)
        by = {i["key"]: i for i in rep["indicators"]}
        assert len(by) == 8 and "采样出错" in by["crush_rate"]["error"] and "接口挂了" in by["crush_rate"]["error"], "一个指标出错不影响其他"
        assert "没有搜到任何结果" in by["basis"]["error"] and by["basis"]["note"] == "搜索接口无返回/返回异常"
        assert os.path.exists(os.path.join(d, "_samples.json")), "全部失败也照常写出文件(空样本)"
        # 日期解析不了的条目被忽略，不报错
        rep2 = bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), only=["basis"], search=fake_search({"全国主要市场豆粕基差价格汇总": [{"publishTime": "乱码", "content": "基差-100", "title": "x"}, mk("2026-09-30", "今日基差-100元/吨")]}))
        assert rep2["indicators"][0]["fetched"] == 1
    ok("容错：单个指标出错/没结果不影响其他；全部失败也写出文件；日期乱码的条目被忽略")


def test_sample_is_not_in_default_jobs_and_registered():
    assert "sample" in bf.JOBS and "sample" not in bf.DEFAULT_JOBS, "采样是一次性诊断，不进默认回填清单"
    ok("sample已注册但不在默认清单里(默认all不会跑它)")


def test_gap_detection_by_frequency():
    daily = [mk("2025-01-02", "今日基差-100"), mk("2025-01-10", "今日基差-100"), mk("2025-03-01", "今日基差-100")]
    monthly = [mk("2025-01-02", "大豆到港预报1000万吨"), mk("2025-03-01", "大豆到港预报1000万吨"), mk("2025-09-01", "大豆到港预报1000万吨")]
    with Tmp() as d:
        r1 = bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), only=["basis"], search=fake_search({"全国主要市场豆粕基差价格汇总": daily}))["indicators"][0]
        r2 = bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), only=["arrival"], search=fake_search({"大豆到港预报": monthly}))["indicators"][0]
    assert r1["gapsOverDays(20)"] == ["2025-01-10→2025-03-01"], r1
    assert r2["gapsOverDays(100)"] == ["2025-03-01→2025-09-01"], r2
    ok("断档：日/周频指标>20天算断档，月/季频>100天算断档")


def test_report_summary_stays_under_the_log_truncation_budget():
    """★用户上次的回填报告在约43KB处被Actions日志截断。8个指标每个都有大量不同措辞(最坏情况)时，报告摘要也必须在预算内——
    完整内容在_samples.json里(文件不会被截断)。"""
    def many(query):
        # 措辞指纹会把数字换成#，所以必须用不同的"汉字"才能造出不同的指纹：用不同的汉字前缀(甲乙丙…)构造120种互不相同的写法
        base = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥天地玄黄宇宙洪荒日月盈昃辰宿列张寒来暑往秋收冬藏闰余成岁律吕调阳云腾致雨露结为霜金生丽水玉出昆冈剑号巨阙珠称夜光果珍李柰菜重芥姜海咸河淡鳞潜羽翔龙师火帝鸟官人皇始制文字乃服衣裳推位让国有虞陶唐吊民伐罪周发殷汤坐朝问道垂拱平章爱育黎首臣伏戎羌遐迩壹体率宾归王鸣凤在竹白驹食场化被草木赖及万方"
        return [mk(f"2025-{1 + i % 12:02d}-{1 + i % 27:02d}", base[i] + base[(i * 7) % len(base)] + f"{query[-3:]}说明" + "字" * 400 + "，" + "".join(v[3] for v in bf.SAMPLE_INDICATORS.values())) for i in range(120)]
    q = {v[2]: many(v[2]) for v in bf.SAMPLE_INDICATORS.values()}
    with Tmp() as d:
        rep = bf.backfill_sample(base_dir=d, today=date(2026, 10, 1), search=fake_search(q))
        size = len(json.dumps(rep, ensure_ascii=False).encode("utf-8"))
        assert size < 45 * 1024, f"报告摘要{size}字节，超过45KB预算(用户上次日志在~43KB处被截断)"
        assert all(i["wordingClusterCount"] >= 100 for i in rep["indicators"]), "确实造出了足够多的不同措辞(最坏情况：每个指标>=100种，聚类只取前10)"
        file_size = os.path.getsize(os.path.join(d, "_samples.json"))
        assert file_size > size, "完整内容在_samples.json里，比摘要大得多"
    ok(f"报告摘要在最坏情况(8指标各120种措辞)下仍<45KB预算；完整内容在_samples.json文件里")


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
