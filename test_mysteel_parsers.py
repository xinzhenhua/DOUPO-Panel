# -*- coding: utf-8 -*-
"""Mysteel搜索结果解析器(mysteel_parsers.py)：用用户2026-10-02跑采样诊断得到的真实样本做测试(tests/data/mysteel_samples_20261002.json)。
每个陷阱都是这次采样里真实出现过的，不是我编的。运行：python3 test_mysteel_parsers.py"""
import os, sys, json, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mysteel_parsers as P

_pass = 0
HERE = os.path.dirname(os.path.abspath(__file__))
FX = json.load(open(os.path.join(HERE, "tests", "data", "mysteel_samples_20261002.json"), encoding="utf-8"))["samples"]


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


# ===================== 进口量：真实写法 =====================
def test_import_real_wordings_each_parse():
    cases = [
        ("据海关总署数据显示 ：中国2025年6月大豆进口1226.4万吨，环比5月进口减少165.44万吨", "2025-07-14", "2025-06", 1226.4, True),
        ("海关总署：2023年6月份中国大豆进口量1027万吨，同比去年增加202万吨，同比增幅24.5%", "2023-07-13", "2023-06", 1027.0, True),
        ("海关总署：中国3月大豆进口量为635.3万吨，1-2月为1394万吨", "2022-04-13", "2022-03", 635.3, False),
        ("2022年6月9日，海关总署公布的数据显示，5月中国大豆进口量约为966.5万吨，环比4月增加158.6万吨", "2022-06-09", "2022-05", 966.5, False),
        ("海关总署：2023年4月中国进口大豆量为726.3万吨，环比增加41万吨", "2023-05-09", "2023-04", 726.3, True),
        ("据海关总署发布的相关消息显示，12月大豆进口数量攀升至1055.5万吨，环比增加达43.6%", "2023-01-18", "2022-12", 1055.5, False),
    ]
    for text, pub, month, val, explicit in cases:
        got, _ = P.parse_soy_import(text, pub)
        assert len(got) == 1 and got[0]["month"] == month and got[0]["value"] == val and got[0]["yearExplicit"] is explicit, (text[:40], got)
    ok("进口量：6种真实写法(中国N月大豆进口/进口量为/约为/进口大豆量/数量攀升至)各提取正确，年份缺失时按发布日推断(12月→发布于1月→前一年)并标注yearExplicit=False")


def test_import_excludes_cumulative_and_combined_wordings():
    for text in ("数据显示，中国2023年1-2月大豆进口1617.3万吨，同比增长16%", "2024年1-2月份中国大豆进口量1303.7万吨", "中国2026年1-5月大豆进口3694.2万吨",
                 "2022年度累计中国1-3月大豆进口量为2029.3万吨", "2023年1-8月份进口大豆累计7166万吨", "10月从乌拉圭进口31.39万吨大豆，同比上升422.27%"):
        got, rej = P.parse_soy_import(text, "2024-03-07")
        assert got == [], (text, got)
    got, rej = P.parse_soy_import("2024年1-2月份中国大豆进口量1303.7万吨", "2024-03-07")
    assert rej and "累计/合并" in rej[0]
    ok("★海关合并公布的1-2月/累计/1-N月/分国别：全部排除并写明原因(1-2月缺失是真实的，不是解析问题)")


def test_import_excludes_values_pointing_to_other_periods():
    """★真实陷阱：2023-09-08那篇写'去年8月份中国大豆进口量为717万吨'(2022年8月)，被当成2023-08；
    还有'作为对比，4月大豆进口量为726万吨'。靠同月另外3篇936万吨的多数一致才没进历史；只有一篇的月份就会直接进去了。"""
    got, rej = P.parse_soy_import("海关数据显示，2023年8月份中国进口了936.2万吨大豆，同比增长30.6%。去年8月份中国大豆进口量为717万吨。", "2023-09-08")
    assert [g["value"] for g in got] == [] or all(g["value"] != 717 for g in got)
    assert any("去年" in r for r in rej)
    got, rej = P.parse_soy_import("港口卸货；作为对比，4月大豆进口量为726万吨", "2023-06-21")
    assert got == [] and any("对比" in r for r in rej)
    got, rej = P.parse_soy_import("较上年同期，上年8月份中国大豆进口量为717万吨", "2023-09-08")
    assert got == []
    ok("★指向其他时期('去年8月份…717万吨'/'作为对比，4月…726万吨')：在源头排除，不依赖多数投票")


def test_import_dedups_same_value_within_one_article():
    got, _ = P.parse_soy_import("2023年8月份中国大豆进口量936万吨，同比增加220万吨。据海关总署数据显示，2023年8月份中国大豆进口量936万吨。", "2023-09-07")
    assert len(got) == 1
    ok("同一篇里同一(月,值)重复出现只算1条观察(标题+正文拼接时不会虚增'多篇一致')")


def test_import_on_the_whole_real_fixture():
    obs = []
    for r in FX["soy_import"]:
        g, _ = P.parse_soy_import(r["title"] + "。" + r["text"], r["d"])
        obs += [(x["month"], x["value"], r["d"], x["yearExplicit"]) for x in g]
    acc, doubt, skipped = P.select_import_months(obs)
    assert doubt == [], f"真实夹具里不应再有同月冲突(去年717已在源头排除): {doubt}"
    assert acc["2023-08"]["value"] == 936.0 and acc["2023-08"]["how"] == "agree" and acc["2023-08"]["n"] >= 3
    assert acc["2023-06"]["value"] == 1027.0 and acc["2025-06"]["value"] == 1226.4
    assert acc["2022-01"]["value"] == 885.0 and acc["2022-01"]["how"] == "single", "原文明确写'中国2022年1月大豆进口量为885万吨'：只有一篇但年份明确，采用并标single"
    assert acc["2022-12"] == {"value": 1055.5, "n": 1, "pubs": ["2023-01-18"], "how": "single_inferred"}, "夹具里2022-12只有1篇('12月大豆进口数量攀升至1055.5万吨'，年份靠发布日2023-01-18推断，间隔1个月)"
    assert acc["2024-08"]["value"] == 1214.4 and acc["2024-08"]["how"] == "single_inferred", "标题只写'8月份'，年份靠发布日(2024-09-10)推断，间隔1个月，采用并标single_inferred"
    assert acc["2024-09"]["value"] == 1137.1 and acc["2024-10"]["value"] == 808.7 and abs(acc["2024-08"]["value"] - 77.3 - acc["2024-09"]["value"]) < 0.01, "文章自带的环比('较2024年8月减少77.3万吨')与提取值独立自洽：1214.4-77.3=1137.1"
    assert skipped == [], "夹具里没有间隔>3个月的推断年份single"
    assert all(200 <= v["value"] <= 2000 for v in acc.values())
    assert len(acc) == 48 and {v["how"] for v in acc.values()} == {"agree", "single", "single_inferred"}
    missing = [f"{y}-{m:02d}" for y in range(2022, 2027) for m in range(1, 13) if "2022-01" <= f"{y}-{m:02d}" <= "2026-07" and f"{y}-{m:02d}" not in acc]
    assert missing == ["2022-02", "2022-11", "2023-01", "2023-02", "2024-01", "2024-02", "2025-01", "2025-02"], missing   # 6个是海关合并公布的1-2月；2022-11源头没有对应文章
    ok("真实夹具整体：48个月0冲突；2023-08=936(3篇一致)、2022-01=885(single)、2024-08=1214.4(single_inferred，且与后两个月的环比自洽)；缺的8个月=6个1-2月合并公布+2022-11源头没有")


def test_two_real_articles_for_2022_12_agree_within_tolerance():
    """2022-12在完整采样文件里有两篇：'12月大豆进口数量攀升至1055.5万吨'(2023-01-18)和'中国12月大豆进口1056万吨'(2023-01-28)，差0.05%。"""
    g1, _ = P.parse_soy_import("据海关总署发布的相关消息显示，12月大豆进口数量攀升至1055.5万吨，环比增加达43.6%", "2023-01-18")
    g2, _ = P.parse_soy_import("据海关总署公布数据显示，中国12月大豆进口1056万吨，环比增加321万吨，增幅44%", "2023-01-28")
    assert g1[0]["month"] == g2[0]["month"] == "2022-12" and (g1[0]["value"], g2[0]["value"]) == (1055.5, 1056.0)
    acc, doubt, _ = P.select_import_months([("2022-12", 1055.5, "2023-01-18", False), ("2022-12", 1056.0, "2023-01-28", False)])
    assert acc["2022-12"]["how"] == "agree" and acc["2022-12"]["value"] in (1055.5, 1056.0) and doubt == []
    ok("2022-12的两篇真实文章(1055.5/1056，差0.05%)：在1%容差内算一致(agree)")


def test_inferred_year_single_rule_uses_the_lag_condition():
    """推断年份的单篇观察：发布月-数据月≤3个月才采用(实测13/13与明确年份一致)；回顾类文章(间隔更久)不采用。"""
    obs = [("2024-08", 1214.4, "2024-09-10", False),     # 间隔1个月：采用
           ("2024-05", 1022.2, "2024-08-10", False),     # 间隔3个月：采用(边界)
           ("2024-03", 554.1, "2024-07-10", False),      # 间隔4个月：不采用
           ("2023-12", 982.0, "2023-11-01", False)]      # 发布早于数据月(推断出错的迹象)：不采用
    acc, _, skipped = P.select_import_months(obs)
    assert acc["2024-08"]["how"] == "single_inferred" and acc["2024-05"]["how"] == "single_inferred"
    assert "2024-03" not in acc and "2023-12" not in acc and {s[0] for s in skipped} == {"2024-03", "2023-12"}
    assert "回顾类" in next(s[3] for s in skipped if s[0] == "2024-03")
    acc2, _, sk2 = P.select_import_months(obs, include_inferred_single=True)
    assert len(acc2) == 4 and sk2 == []
    ok("★推断年份的单篇：间隔1~3个月采用(标single_inferred)；间隔4个月/发布早于数据月不采用并写明；include_inferred_single可全放开")


def test_each_import_exclusion_word_blocks_on_its_own():
    """防护词之间有冗余(如'累计'和'1-N月'常同时出现)，只测组合会让单独误删其中一个时无人发现(变异检查发现原测试漏了)。
    每个写法只含'这一个'排除标志。"""
    each = {
        "累计(无区间)": "据海关数据，2023年累计中国8月大豆进口936万吨",
        "N-M月(半角)": "海关数据显示中国2023年1-8月大豆进口7166万吨",
        "N月至M月": "海关数据显示中国2023年1月至2月大豆进口1617.3万吨",
        "N、M月": "海关数据显示中国2023年1、2月大豆进口1617.3万吨",
        "合计": "海关数据显示合计中国2023年8月大豆进口936万吨",
        "年初至今": "海关数据显示年初至今中国8月大豆进口936万吨",
        "前N月": "海关数据显示前8月中国8月大豆进口936万吨",
        "头N个月": "海关数据显示头2个月中国2月大豆进口1620万吨",
        "上半年": "海关数据显示上半年中国6月大豆进口5000万吨",
        "季度": "海关数据显示二季度中国6月大豆进口3000万吨",
        "同期": "海关数据显示去年同期中国8月大豆进口936万吨",
        "分国别(从X进口)": "10月从乌拉圭进口31.39万吨大豆",
    }
    for name, text in each.items():
        got, _ = P.parse_soy_import(text, "2023-09-07")
        assert got == [], f"只含排除标志'{name}'的写法被当成了单月进口量: {text!r} -> {got}"
    got, _ = P.parse_soy_import("海关数据显示中国2023年8月大豆进口936万吨", "2023-09-07")
    assert got and got[0]["value"] == 936.0, "对照：没有任何排除标志的正常写法仍可提取"
    ok("★12个进口量排除标志逐个单独验证(累计/N-M月/N月至M月/N、M月/合计/年初至今/前N月/头N个月/上半年/季度/同期/分国别)；正常写法不受影响")


def test_each_other_period_word_blocks_on_its_own():
    """'作为对比，4月…'里同时有'作为对比'和'对比'，互为备份——逐个单独验证。"""
    for word in ("去年", "上年", "前年", "去岁", "作为对比", "对比", "较", "比"):
        got, rej = P.parse_soy_import(f"海关数据：{word}8月份中国大豆进口量为717万吨", "2023-09-08")
        assert got == [] and rej, f"前置词'{word}'没能把指向其他时期的数排除: {got}"
    got, _ = P.parse_soy_import("海关数据显示，2023年8月份中国大豆进口量为936万吨", "2023-09-08")
    assert got and got[0]["value"] == 936.0
    ok("★8个指向其他时期的前置词(去年/上年/前年/去岁/作为对比/对比/较/比)逐个单独验证")


def test_exclusion_regexes_work_independently_of_the_patterns():
    """★第二层防护的独立测试。变异检查发现：'至'/顿号/分国别这三个排除词，在当前的_IMPORT_PATS下根本到不了(模式本身已经不匹配'1月至2月大豆进口')，
    '作为对比'/'对比'则被末尾的单字'比'挡住。它们是真实的'冗余第二层'：以后有人放宽_IMPORT_PATS(比如为了兼容新写法)，这一层才起作用。
    所以绕过模式，直接对排除正则做单元测试，让每个词都有独立的验证，不依赖上层碰巧挡住。"""
    bad = P._IMPORT_BAD
    for word, ctx in (("累计", "2023年累计中国8月"), ("N-M月", "中国2023年1-8月大豆进口"), ("N月至M月", "中国2023年1月至2月大豆进口"), ("N、M月", "中国2023年1、2月大豆进口"),
                      ("合计", "合计中国8月大豆进口"), ("年初至今", "年初至今中国8月大豆"), ("前N月", "前8月中国大豆进口"), ("头N个月", "头2个月中国大豆进口"),
                      ("共计", "共计中国8月大豆进口"), ("上半年", "上半年中国大豆进口"), ("下半年", "下半年中国大豆进口"), ("季度", "二季度中国大豆进口"),
                      ("同期", "去年同期中国8月大豆"), ("从X进口", "10月从乌拉圭进口31.39万吨")):
        assert bad.search(ctx), f"排除正则没能识别'{word}': {ctx}"
    for ctx in ("中国2023年8月大豆进口936万吨", "海关总署：2025年6月中国大豆进口量为1226.4万吨", "据海关总署数据显示：中国10月大豆进口808.7万吨"):
        assert not bad.search(ctx), f"正常写法被排除正则误伤: {ctx}"
    other = P._IMPORT_OTHER_PERIOD
    for word in ("去年", "上年", "前年", "去岁", "作为对比", "对比", "较", "比"):
        assert other.search(f"数据{word}"), f"其他时期正则没能识别前置词'{word}'"
    assert other.search("作为对比") and not other.search("海关总署：") and not other.search("据海关总署数据显示：中国")
    # 词表的精确内容(防止有人悄悄删词)
    assert set(P._IMPORT_OTHER_PERIOD.pattern.split("|")) == {"去年", "上年", "前年", "去岁", "作为对比", "对比", "较", "比"}
    ok("★第二层防护：14个累计/范围/分国别排除词、8个其他时期前置词，绕过上层模式直接单元测试(各自独立验证)；正常写法不被误伤；词表内容固定")


def test_majority_vote_picks_the_majority_not_the_max():
    """936×3 vs 717×1：取最大值碰巧也是936，区分不出'多数'和'最大值'。用少数派更大的例子：500×3 vs 900×1。"""
    acc, doubt = P.cross_verify_monthly([("2024-05", 500.0, "a"), ("2024-05", 500.0, "b"), ("2024-05", 500.0, "c"), ("2024-05", 900.0, "d")])
    assert acc["2024-05"]["value"] == 500.0 and acc["2024-05"]["how"] == "majority" and doubt[0]["overruled"] == [(900.0, "d")]
    acc, _ = P.cross_verify_monthly([("2024-06", 500.0, "a"), ("2024-06", 100.0, "b"), ("2024-06", 100.0, "c")])
    assert acc["2024-06"]["value"] == 100.0, "多数是较小的值时也取多数(不是取最小/最大)"
    ok("★多数投票取的是'多数'而不是最大/最小值(500×3 vs 900×1 → 500；100×2 vs 500×1 → 100)")


def test_arrival_requires_ships_and_total_structure():
    """噪声里有'到港…共计…万吨'但缺船数/缺'共计'/缺逗号的写法——必须是'N船，共计(约)X万吨'的完整结构。每一种只缺'这一个'要素。"""
    missing = {
        "缺船数": "2024年8月份国内主要油厂大豆到港预估共计约1043.25万吨",
        "缺船数和共计": "2024年8月份国内全样本油厂大豆到港预估1043.25万吨",
        "缺逗号": "2024年8月份国内全样本油厂大豆到港预估160.5船约1043.25万吨",
        "缺'共计'(写成预计)": "2024年8月份国内全样本油厂大豆到港预估160.5船，预计1043.25万吨",
        "缺逗号(连写)": "2024年8月份国内全样本油厂大豆到港160.5船共计1043.25万吨以上",
    }
    for name, text in missing.items():
        assert P.parse_arrival_forecast(text, "2024-07-25")[0] == [], f"缺要素'{name}'的写法被提取了: {text}"
    want = [{"month": "2024-08", "value": 1043.25, "ships": 160.5}]
    assert P.parse_arrival_forecast("2024年8月份国内全样本油厂大豆到港预估160.5船，共计1043.25万吨", "2024-07-25")[0] == want, "对照：完整结构(无'约')"
    assert P.parse_arrival_forecast("2024年8月份国内全样本油厂大豆到港预估160.5船，共计约1043.25万吨", "2024-07-25")[0] == want, "对照：完整结构(有'约')"
    ok("★到港预报必须是'N船，共计(约)X万吨'的完整结构：缺船数/缺逗号/缺'共计'的5种写法都不提取；完整结构(有无'约')都提取")

def test_select_import_months_rules():
    obs = [("2025-06", 1226.4, "2025-07-14", True), ("2025-06", 1226.5, "2025-07-20", True),      # 差0.01%：一致
           ("2025-05", 1391.8, "2025-09-09", False),                                                # 单篇、推断年份、间隔4个月(回顾类)
           ("2025-04", 608.1, "2025-05-09", True),                                                  # 单篇、年份明确
           ("2025-03", 350.3, "2025-04-14", True), ("2025-03", 350.3, "2025-04-21", True), ("2025-03", 999.0, "2025-04-22", True)]   # 多数一致
    acc, doubt, skipped = P.select_import_months(obs)
    assert acc["2025-06"]["how"] == "agree" and acc["2025-04"]["how"] == "single" and acc["2025-03"]["how"] == "majority" and "2025-05" not in acc
    assert [(s[0]) for s in skipped] == ["2025-05"] and doubt[0]["month"] == "2025-03" and doubt[0]["overruled"][0][0] == 999.0
    acc2, _, sk2 = P.select_import_months(obs, include_inferred_single=True)
    assert "2025-05" in acc2 and sk2 == []
    ok("采用规则：多篇一致/多数一致采用(少数派记入存疑)；单篇+年份明确采用；单篇+年份推断默认不采用(可开关)")


# ===================== 到港预报 =====================
def test_arrival_real_wordings():
    cases = [
        ("2024年9月份国内全样本油厂大豆到港预估133.5船，共计约867.75万吨（本月船重按6.5万吨计）", "2024-09", 867.75, 133.5),
        ("2024年2月份国内主要地区125家油厂大豆到港预估68船，共计约442万吨", "2024-02", 442.0, 68.0),
        ("2024年8月份国内主要油厂大豆到港预估160.5船，共计约1043.25万吨（本月船重按6.5万吨计）", "2024-08", 1043.25, 160.5),
        ("Mysteel农产品团队预估，2026年1月份国内全样本油厂大豆到港117.2船，共计约761.80万吨", "2026-01", 761.8, 117.2),
    ]
    for text, month, val, ships in cases:
        got, rej = P.parse_arrival_forecast(text, "2024-01-01")
        assert len(got) == 1 and got[0] == {"month": month, "value": val, "ships": ships} and rej == [], (text[:30], got)
    ok("到港预报：4种真实写法(全样本/主要地区N家/主要油厂/Mysteel农产品团队预估)各提取正确；'主要油厂'是2024-08那一篇，漏掉它序列会断一个月")


def test_arrival_two_calibers_in_one_article_are_rejected():
    """★真实：2023-11~2024-01同一篇同时给111家(783.25万吨)和123家(845万吨)两个口径，相差8%，样本家数在扩大(111→123→125→全样本)，不可比。"""
    text = ("据Mysteel农产品团队初步统计，2023年11月份国内主要地区111家油厂大豆到港预估120.5船，共计约783.25万吨（本月船重按6.5万吨计）其中东北15船约97.5万吨；华北20船约130万吨 "
            "2023年11月份国内主要地区123家油厂大豆到港预估130船，共计约845万吨（本月船重按6.5万吨计）。")
    got, rej = P.parse_arrival_forecast(text, "2023-11-01")
    assert got == [] and len(rej) == 1 and "2个口径" in rej[0] and "783.25" in rej[0] and "845" in rej[0]
    ok("★同一篇同月出现两个口径(111家783.25 / 123家845)：整月不采用并写明两个值，不替用户悄悄选一个(相差8%)")


def test_arrival_rejects_noise_and_new_wordings():
    for text in ("目前正处美国大豆生长关键期，市场预估八月到港仍达到一千万吨以上", "商务部对外贸易司：2022年4月豆油实际到港0.44万吨，同比下降90.81%；下月预报到港0.02万吨",
                 "2026年7月国内油厂进口大豆到港量预计达1064万吨，环比略有增长", "Mysteel预估2026年10月国内全样本油厂大豆到港约854.10万吨，11月预计870万吨，12月950万吨",
                 "2024年8月大豆到港量为930.8万吨，较上月预报的934.2万吨减少3.4万吨"):
        got, _ = P.parse_arrival_forecast(text, "2026-09-24")
        assert got == [], (text[:40], got)
    ok("★噪声不被误提取：日报里顺带提到的'到港量'、商务部实际到港、2026-06之后的新写法(一篇三个月，远月是初步预估)、'上月预报的934.2万吨'")


def test_arrival_on_the_whole_real_fixture_is_a_continuous_29_months():
    seen = {}
    for r in FX["arrival"]:
        got, _ = P.parse_arrival_forecast(r["text"], r["d"])
        for g in got:
            assert g["month"] not in seen, f"同月重复: {g['month']}"
            seen[g["month"]] = g["value"]
    months = sorted(seen)
    exp = [f"{y}-{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13) if "2024-02" <= f"{y}-{m:02d}" <= "2026-06"]
    assert months == exp and len(months) == 29, [m for m in exp if m not in months]
    assert seen["2024-08"] == 1043.25 and seen["2026-02"] == 500.5 and seen["2026-06"] == 1073.8
    assert not any(m in seen for m in ("2023-11", "2023-12", "2024-01")), "双口径的三个月被排除"
    assert all(200 <= v <= 2000 for v in seen.values())
    ok("★真实夹具整体：2024-02~2026-06连续29个月无缺月，无重复；2023-11/12、2024-01(双口径)不在其中；数值全在合理范围")


def test_arrival_monthly_level_is_continuous_across_caliber_change():
    """样本口径从'主要地区125家'(2024-07)变成'全样本'(2024-09)：数值没有人为的水平跳变(季节性比口径差异大得多)。"""
    seen = {}
    for r in FX["arrival"]:
        for g in P.parse_arrival_forecast(r["text"], r["d"])[0]:
            seen[g["month"]] = g["value"]
    assert abs(seen["2024-09"] - seen["2024-07"]) / seen["2024-07"] < 0.15, (seen["2024-07"], seen["2024-09"])
    ok("口径切换处(2024-07 125家 978万吨 → 2024-09 全样本 868万吨)：变化11%，在季节性波动范围内，没有水平跳变")


# ===================== 豆菜粕价差 / 开机率(解析器已写好，但回填刻意不做——测试守住"为什么不做"的依据) =====================
def test_rm_spread_old_and_new_wordings_differ_in_caliber():
    """★为什么豆菜粕价差回填不做：2026-06-11前后换了口径——旧(沿海地区区间)和新(广东/广西/南通三城市单值)的水平不同，混在一个序列里
    '往年同月'分位会被人为的水平跳变扭曲。这里守住这个事实：旧写法能解析出区间，新写法解析不出(不是同一口径)。"""
    old = "截至2025年6月3日，国内沿海地区豆菜粕现货价差上涨，价差在320-440元/吨之间，涨30元/吨"
    new = "2026年9月30日，国内主要市场豆菜粕价差如下：广东豆粕3310元/吨，菜粕2510元/吨，价差800元/吨；广西豆粕3300元/吨，菜粕2510元/吨，价差790元/吨"
    g_old, _ = P.parse_rm_spread(old, "2025-06-03")
    g_new, _ = P.parse_rm_spread(new, "2026-09-30")
    assert g_old == [{"date": "2025-06-03", "low": 320, "high": 440, "mid": 380.0}] and g_new == []
    old_mid = [g["mid"] for r in FX["rm_spread"] for g in P.parse_rm_spread(r["text"], r["d"])[0]]
    assert 295 <= min(old_mid) and max(old_mid) <= 1055 and sum(old_mid) / len(old_mid) < 700, "旧口径均值明显低于新口径约830"
    ok("豆菜粕价差：旧口径(沿海区间，均值<700)能解析、新口径(三城市单值，约830)解析不出——口径不同，所以回填没有价值(不做)")


def test_crush_rate_requires_oil_mill_context():
    """★真实陷阱：同一个快讯接口里还有别的行业——'砂石矿山开机率28.96%，较上周提升10.82个百分点'(2026-03-06)。"""
    got, rej = P.parse_crush_rate("较上周下跌2.43元/吨，沿海运费开始上涨。砂石矿山开机率28.96%，较上周提升10.82个百分点；产能利用率13.74%", "2026-03-06")
    assert got == [] and any("别的行业" in r for r in rej)
    got, _ = P.parse_crush_rate("9月29日成交方面，全国主要油厂豆粕成交12.89万吨。\r\n\r\n开机方面，今日全国动态全样本油厂开机率为60.95%，较前一日下降1.20%。", "2026-09-29")
    assert got == [{"date": "2026-09-29", "value": 60.95}]
    ok("★开机率：'砂石矿山开机率28.96%'被排除(必须是'油厂开机率')；真实的油厂快讯正确提取60.95%")


def test_crush_rate_festival_lows_are_real_not_errors():
    """★我最初以为9.8%/15.46%是源头错误——错了。2025-01-26=9.80%(较前一日下降33.33%)、2026-02-24=15.46%(较前一日上升7.20%)都在春节期间，
    2025年4月中美关税战时还有25~29%的连续低谷。这些是真实数据。(生产里crushRate合理范围下限是10，会把9.8%误拒——见README，等开机率评分规则一起处理)"""
    for text, v in (("开机方面，今日全国动态全样本油厂开机率为9.80%，较前一日下降33.33%。", 9.8), ("开机方面，今日全国动态全样本油厂开机率为15.46%，较前一日上升7.20%。", 15.46),
                    ("开机方面，今日全国动态全样本油厂开机率为25.15%，较前一日下降0.39%。", 25.15)):
        got, _ = P.parse_crush_rate(text, "2025-01-26")
        assert got and got[0]["value"] == v
    vals = [g["value"] for r in FX["crush_rate"] for g in P.parse_crush_rate(r["text"], r["d"])[0]]
    assert min(vals) == 9.8 and max(vals) < 80 and len(vals) >= 35
    got, rej = P.parse_crush_rate("今日全国动态全样本油厂开机率为3.5%，较前一日下降40%", "2025-01-26")
    assert got == [] and rej == ["开机率3.5%超出合理范围(5~100)"], "有'油厂'但低于5%：超出合理范围，不采用"
    got, rej = P.parse_crush_rate("油厂开机率为100.5%", "2025-01-26")
    assert got == [] and rej == ["开机率100.5%超出合理范围(5~100)"], "高于100%：不采用"
    got, rej = P.parse_crush_rate("开机率为60.5%", "2025-01-26")
    assert got == [] and len(rej) == 1 and "不是'油厂开机率'" in rej[0], "没有'油厂'二字：不是油厂的快讯"
    ok("春节停机9.8%/15.46%、关税战期间25%的真实低值都能提取(之前误判为源头错误)；整个夹具最小值9.8%")


def test_crush_rate_wording_variants():
    for text, v in (("开机方面，今日全国动态全样本油厂开机率上升至56.58%", 56.58), ("开机方面，今日全国动态全样本油厂开机率50.82%", 50.82),
                    ("开机方面，今日全国动态全样本油厂开机率下降至52.33%", 52.33), ("开机方面，今日全国动态全样本油厂开机率为60.82%，较前一日增加0.82%", 60.82),
                    ("今日全国动态全样本油厂开机率小幅上升至58.1%", 58.1)):
        got, _ = P.parse_crush_rate(text, "2025-01-10")
        assert got and got[0]["value"] == v, text
    ok("开机率：为/上升至/下降至/无动词/小幅上升至 五种真实措辞")


# ===================== 多篇交叉验证 =====================
def test_cross_verify_monthly_unit():
    acc, doubt = P.cross_verify_monthly([("2023-08", 936.0, "2023-09-07"), ("2023-08", 936.0, "2023-09-19"), ("2023-08", 936.0, "2023-09-25"), ("2023-08", 717.0, "2023-09-08")])
    assert acc["2023-08"]["value"] == 936.0 and acc["2023-08"]["how"] == "majority" and acc["2023-08"]["n"] == 4
    assert doubt[0]["overruled"] == [(717.0, "2023-09-08")]
    acc, doubt = P.cross_verify_monthly([("2024-01", 100.0, "a"), ("2024-01", 200.0, "b")])
    assert acc == {} and doubt[0]["adopted"] is None and "没有多数一致" in doubt[0]["reason"], "2篇各一个值：没有多数，不采用"
    acc, _ = P.cross_verify_monthly([("2024-02", 1000.0, "a"), ("2024-02", 1005.0, "b")])
    assert acc["2024-02"]["how"] == "agree", "差0.5%在1%容差内算一致"
    acc, _ = P.cross_verify_monthly([("2024-02", 1000.0, "a"), ("2024-02", 1020.0, "b")])
    assert acc == {}, "差2%超出容差，且没有多数"
    acc, _ = P.cross_verify_monthly([("2024-03", 5.0, "a")])
    assert acc["2024-03"]["how"] == "single"
    ok("交叉验证：3:1多数采用并把少数派记入存疑；2:篇各一个值不采用；±1%内算一致；单篇标single")


def test_clean_handles_all_whitespace_kinds():
    assert P._clean("据海关总署数据显示 ：中国\n2025年6月\r\n大豆进口 1226.4 万吨") == "据海关总署数据显示：中国2025年6月大豆进口1226.4万吨"
    assert P._clean(None) == "" and P._clean(123) == "123"
    ok("文本清洗：去掉所有空白(搜索结果里换行/空格位置不稳定，如'数据显示 ：中国')；None/非字符串不报错")


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
