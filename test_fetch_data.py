"""
用模拟数据测试 fetch_data.py 里的解析逻辑
==========================================
因为我的代码沙盒不能访问 api.fas.usda.gov / query1.finance.yahoo.com，
没法做真正的端到端联网测试。这个文件用"看起来跟官方文档一致的模拟数据"
来验证解析函数本身逻辑没写错。

真正联网请求那部分（fetch_json函数）由 GitHub Actions 实际跑的时候验证。
"""
import sys
import os
import urllib.request
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))

import fetch_data as fd

# ---- 模拟 ESR commodities 列表返回 ----
MOCK_ESR_COMMODITIES = [
    {"commodityCode": 107, "commodityName": "All Wheat"},
    {"commodityCode": 801, "commodityName": "Corn"},
    {"commodityCode": 2223, "commodityName": "Soybean Cake and Meal"},
    {"commodityCode": 2222, "commodityName": "Soybeans"},
]

# ---- 模拟 ESR exports 返回（两周数据，用来测环比计算） ----
MOCK_ESR_EXPORTS = [
    {"weekEndingDate": "2026-06-25", "countryName": "China", "weeklyExports": 120000, "unitId": 1},
    {"weekEndingDate": "2026-06-25", "countryName": "Mexico", "weeklyExports": 30000, "unitId": 1},
    {"weekEndingDate": "2026-07-02", "countryName": "China", "weeklyExports": 80000, "unitId": 1},
    {"weekEndingDate": "2026-07-02", "countryName": "Mexico", "weeklyExports": 25000, "unitId": 1},
]

# ---- 模拟 PSD commodities 列表 ----
MOCK_PSD_COMMODITIES = [
    {"commodityCode": "0813200", "commodityName": "Soybean Meal"},
    {"commodityCode": "2222000", "commodityName": "Soybeans"},
]

# ---- 模拟 PSD 数据返回 ----
MOCK_PSD_DATA = [
    {"attributeName": "Production", "value": 52000},
    {"attributeName": "Total Supply", "value": 55000},
    {"attributeName": "Domestic Consumption", "value": 34000},
    {"attributeName": "Ending Stocks", "value": 400},
]

MOCK_DROUGHT_IA = [
    # 用户实测的真实原始数据（爱荷华）：none+d0 应约等于全州面积56273平方英里
    {"mapDate": "2026-06-23T00:00:00", "validStart": "2026-06-23T00:00:00", "none": 37724.00, "d0": 18587.50, "d1": 4659.61, "d2": 1.90, "d3": 0.00, "d4": 0.00},
    {"mapDate": "2026-06-30T00:00:00", "validStart": "2026-06-30T00:00:00", "none": 37534.63, "d0": 18776.87, "d1": 6840.84, "d2": 1.90, "d3": 0.00, "d4": 0.00},
]
MOCK_DROUGHT_IL = [
    {"mapDate": "2026-06-30T00:00:00", "validStart": "2026-06-30T00:00:00", "none": 50339.32, "d0": 6043.23, "d1": 0.00, "d2": 0.00, "d3": 0.00, "d4": 0.00},
]
MOCK_DROUGHT_MN = [
    {"mapDate": "2026-06-30T00:00:00", "validStart": "2026-06-30T00:00:00", "none": 23674.66, "d0": 60706.52, "d1": 25537.95, "d2": 9779.32, "d3": 0.00, "d4": 0.00},
]


def test_weighted_avg_large_producer_dominates_over_small_producer(monkeypatch_fetch):
    """直接验证用户提出的场景：伊利诺伊(全国最大产区，权重10800)严重干旱，
    而威斯康星(小产区，权重2150)完全没有干旱——加权平均应该明显偏向伊利诺伊的情况，
    而不是被简单平均"平摊"到看起来问题不大。"""
    state_values = {"IL": 80.0, "WI": 0.0}  # 伊利诺伊80%严重干旱，威斯康星0%
    weighted = fd.weighted_avg(state_values)
    simple = sum(state_values.values()) / len(state_values)
    assert simple == 40.0, "简单平均会显示40%，看起来只是中等程度"
    # 加权平均 = 80*10800/(10800+2150) = 864000/12950 ≈ 66.7，应该明显更高、更接近伊利诺伊的实际严重程度
    assert weighted > 60, f"加权平均应该明显高于简单平均的40%，更贴近伊利诺伊(大产区)的真实严重程度，实际{weighted}"
    print(f"✅ 用户场景验证通过：简单平均{simple}% vs 加权平均{round(weighted,1)}%——"
          f"加权平均正确地让大产区(伊利诺伊)的严重干旱主导结果，而不是被小产区(威斯康星)的正常情况稀释")


def test_weighted_avg_small_producer_drought_gets_diluted_appropriately(monkeypatch_fetch):
    """反过来验证：如果是小产区(威斯康星)严重干旱，大产区(伊利诺伊)正常，
    加权平均应该明显偏低(体现小产区对全国供给影响有限)，而不是简单平均的'各打五十大板'。"""
    state_values = {"IL": 0.0, "WI": 80.0}  # 伊利诺伊0%，威斯康星80%严重干旱
    weighted = fd.weighted_avg(state_values)
    simple = sum(state_values.values()) / len(state_values)
    assert simple == 40.0
    # 加权平均 = 80*2150/(10800+2150) ≈ 13.3，应该明显低于简单平均，因为小产区问题对全国影响有限
    assert weighted < 20, f"加权平均应该明显低于简单平均，因为威斯康星只是小产区，实际{weighted}"
    print(f"✅ 反向场景验证通过：小产区(威斯康星)严重干旱时，加权平均{round(weighted,1)}%正确低于简单平均{simple}%，"
          f"体现小产区问题对全国供给的实际影响有限")


def test_esr_code_lookup(monkeypatch_fetch):
    monkeypatch_fetch({"esr/commodities": MOCK_ESR_COMMODITIES})
    code, debug = fd.get_soybean_meal_esr_code()
    assert code == 2223, f"期望 2223，实际 {code}"
    assert debug is None, "找到匹配时不应该有debug信息"
    print("✅ ESR 商品编码查找逻辑正确")


def test_esr_export_parsing(monkeypatch_fetch):
    monkeypatch_fetch({
        "esr/commodities": MOCK_ESR_COMMODITIES,
        "esr/exports": MOCK_ESR_EXPORTS,
    })
    result = fd.fetch_esr_export_sales()
    assert result["available"] is True
    assert result["latestTotalMT"] == 105000, f"最新周总量应为105000，实际{result['latestTotalMT']}"
    assert result["prevTotalMT"] == 150000, f"上周总量应为150000，实际{result['prevTotalMT']}"
    expected_pct = round((105000 - 150000) / 150000 * 100, 1)
    assert result["wowChangePct"] == expected_pct
    assert result["chinaLatestMT"] == 80000
    print("✅ ESR 出口销售解析与环比计算逻辑正确")
    print(f"   示例输出: {result}")


def test_psd_code_lookup(monkeypatch_fetch):
    monkeypatch_fetch({"psd/commodities": MOCK_PSD_COMMODITIES})
    code, debug = fd.get_soybean_meal_psd_code()
    assert code == "0813200"
    assert debug is None
    print("✅ PSD 商品编码查找逻辑正确")


def test_psd_parsing(monkeypatch_fetch):
    monkeypatch_fetch({
        "psd/commodities": MOCK_PSD_COMMODITIES,
        "psd/commodity": MOCK_PSD_DATA,
    })
    result = fd.fetch_psd_supply_demand()
    assert result["available"] is True
    assert result["endingStocks"] == 400
    assert result["production"] == 52000
    print("✅ PSD 供需数据解析逻辑正确")
    print(f"   示例输出: {result}")


def test_drought_area_to_percentage_conversion(monkeypatch_fetch):
    """核心回归测试：验证'平方英里面积→百分比'的换算公式正确。
    这是用真实实测数据反推出的确认公式：pct = area / (none+d0) × 100
    （用户报告的原始bug就是没做这层换算，直接把平方英里数字当成百分比显示）"""
    monkeypatch_fetch({
        "aoi=19": MOCK_DROUGHT_IA,
        "aoi=17": MOCK_DROUGHT_IL,
        "aoi=27": MOCK_DROUGHT_MN,
    })
    result = fd.fetch_drought_monitor()
    assert result["available"] is True
    assert result["anomalous"] is False, "换算成功后不应再标记为异常"
    # 用真实数据精确验算过的期望值（爱荷华 6/30 那一条：none=37534.63, d0=18776.87）
    assert result["byState"]["IA"]["d0"] == 33.34, result["byState"]["IA"]
    assert result["byState"]["IA"]["d1"] == 12.15
    assert result["byState"]["IL"]["d0"] == 10.72
    assert result["byState"]["MN"]["d0"] == 71.94
    assert result["byState"]["MN"]["d1"] == 30.26
    assert result["byState"]["MN"]["d2"] == 11.59
    assert result["byState"]["MN"]["severeOrWorsePct"] == 11.6
    print("✅ 面积→百分比换算公式正确（用真实数据精确验算：MN的D0从60706.52平方英里正确换算为71.94%）")


def test_drought_monitor_parsing(monkeypatch_fetch):
    monkeypatch_fetch({
        "aoi=19": MOCK_DROUGHT_IA,  # Iowa FIPS=19
        "aoi=17": MOCK_DROUGHT_IL,  # Illinois FIPS=17
        "aoi=27": MOCK_DROUGHT_MN,  # Minnesota FIPS=27
    })
    result = fd.fetch_drought_monitor()
    assert result["available"] is True
    # 验证"取最新一条(6/30)而不是6/23那条旧数据"：6/30的d0=33.34%，6/23的d0=33.01%，两者接近但不同，
    # 用这个差异确认真的取到了正确的那一条
    assert result["byState"]["IA"]["d0"] == 33.34, "应该取6/30这条，而不是6/23那条(d0应为33.01)"
    assert result["byState"]["IA"]["validDate"] == "2026-06-30T00:00:00"
    # ★ 已改进：从简单平均改成按种植面积加权。IA(权重10050)+IL(权重10800)都是0%，
    #   MN(权重7400)是11.6%，加权后 = 11.6*7400/(10050+10800+7400) = 3.0(不再是简单平均的3.9)
    expected_weighted_avg = 3.0
    assert result["avgSevereOrWorsePct"] == expected_weighted_avg, result["avgSevereOrWorsePct"]
    assert result["simpleSevereOrWorsePct"] == 3.9, "简单平均应该还是3.9，保留做对比参考"
    print("✅ 干旱监测数据解析逻辑正确（含'取最新一周而非最早一周'的校验）")
    print(f"   示例输出: 加权平均D2+级别占比 {result['avgSevereOrWorsePct']}%（简单平均{result['simpleSevereOrWorsePct']}%，"
          f"加权后更贴近伊利诺伊/爱荷华这两个大产区的实际权重）")


def test_esr_picks_freshest_among_multiple_candidate_years(monkeypatch_fetch):
    """复现用户实际报告的bug：之前靠'10月分界'猜市场年度，猜中了一个
    已经完结、停留在2025-10-02不再更新的年度。这个测试验证新逻辑——
    同时尝试多个候选年份，自动选出真正数据最新的那一个。"""
    old_completed_year_data = [
        {"weekEndingDate": "2025-09-25", "countryName": "China", "weeklyExports": 50000},
        {"weekEndingDate": "2025-10-02", "countryName": "China", "weeklyExports": 60000},
    ]
    current_active_year_data = [
        {"weekEndingDate": "2026-06-25", "countryName": "China", "weeklyExports": 90000},
        {"weekEndingDate": "2026-07-02", "countryName": "China", "weeklyExports": 110000},
    ]
    def fake_debug(url, headers=None, retries=3, timeout=20):
        if "esr/commodities" in url:
            return MOCK_ESR_COMMODITIES, {}
        if "marketYear/2025" in url:
            return old_completed_year_data, {"httpStatus": 200}
        if "marketYear/2026" in url:
            return current_active_year_data, {"httpStatus": 200}
        return None, {}
    fd.fetch_json_debug = fake_debug
    fd.fetch_json = lambda *a, **k: fake_debug(*a, **k)[0]

    result = fd.fetch_esr_export_sales()
    assert result["available"] is True
    assert result["weekEnding"] == "2026-07-02", \
        f"应该选中2026年这个真正最新的候选年份，而不是停在2025-10-02的旧年度，实际: {result['weekEnding']}"
    assert result["marketYearUsed"] == 2026
    print("✅ ESR多候选年份选择逻辑正确：正确避开了停留在2025-10-02不再更新的旧年度，选中了真正最新的2026年数据")


def test_esr_code_lookup_distinguishes_failure_types(monkeypatch_fetch):
    """复现用户实际报告的问题：ESR突然显示'未能找到豆粕的ESR商品编码'，
    但这句话之前完全没有区分'请求本身失败'和'请求成功但没匹配上'这两种情况，
    导致没法诊断真正原因。这个测试验证新加的诊断能正确区分这两种。"""
    # 场景A：请求本身失败（比如被限流、网络问题）
    def fail_fetch(url, headers=None, retries=3, timeout=20):
        return None, {"httpStatus": 429, "error": "HTTP 429: Too Many Requests"}
    fd.fetch_json_debug = fail_fetch
    code, debug = fd.get_soybean_meal_esr_code()
    assert code is None
    assert "请求" in debug["failureStage"] and "失败" in debug["failureStage"]
    assert debug.get("httpStatus") == 429
    print("✅ 场景A（请求失败/被限流）：正确识别为'请求本身失败'，而非笼统的'没找到编码'")

    # 场景B：请求成功，但商品列表里确实没有匹配的豆粕条目（比如接口改了命名方式）
    def success_no_match(url, headers=None, retries=3, timeout=20):
        return [{"commodityCode": 999, "commodityName": "Some Other Product"}], {"httpStatus": 200}
    fd.fetch_json_debug = success_no_match
    code2, debug2 = fd.get_soybean_meal_esr_code()
    assert code2 is None
    assert "没有一条命中" in debug2["failureStage"]
    assert debug2["actualCommodityNamesSeen"] == ["Some Other Product"]
    print("✅ 场景B（请求成功但没匹配上）：正确识别为'没匹配上'，并列出实际收到的商品名称")


def test_psd_fuzzy_matching(monkeypatch_fetch):
    """验证大小写/多余空格不一致时，容错匹配逻辑依然能找到正确字段（这是本轮修复的重点）"""
    mock_variant_case = [
        {"attributeName": "ending stocks", "value": 400},   # 全小写
        {"attributeName": "Production ", "value": 52000},   # 末尾多个空格
        {"attributeName": "TOTAL SUPPLY", "value": 55000},  # 全大写
        {"attributeName": "Domestic  Consumption", "value": 34000},  # 中间两个空格
    ]
    monkeypatch_fetch({
        "psd/commodities": MOCK_PSD_COMMODITIES,
        "psd/commodity": mock_variant_case,
    })
    result = fd.fetch_psd_supply_demand()
    assert result["available"] is True
    assert result["endingStocks"] == 400, f"大小写/空格容错匹配失败: {result}"
    assert result["production"] == 52000
    assert result["totalSupply"] == 55000
    assert result["domesticConsumption"] == 34000
    assert "debug" not in result, "字段都匹配上了，不应该出现debug诊断信息"
    print("✅ PSD容错匹配逻辑正确（大小写、多余空格都能正确识别）")


def test_psd_debug_on_field_mismatch(monkeypatch_fetch):
    """验证当接口返回数据、但字段名完全对不上时，诊断信息(debug)确实会被写出来，
    这样以后再遇到类似问题时，不用去翻GitHub Actions日志，直接看输出的json就知道真实字段名。"""
    mock_totally_different_fields = [
        {"someOtherFieldName": "Ending Stocks", "someOtherValue": 400},
    ]
    monkeypatch_fetch({
        "psd/commodities": MOCK_PSD_COMMODITIES,
        "psd/commodity": mock_totally_different_fields,
    })
    result = fd.fetch_psd_supply_demand()
    assert result["available"] is True
    assert result["endingStocks"] is None, "字段名完全不对，应该取不到值"
    assert "debug" in result, "字段一个都没匹配上时，应该附带diagnostic debug信息"
    assert "warning" in result["debug"]
    print("✅ 字段完全不匹配时，diagnostic debug信息正确生成")
    print(f"   debug内容示例: {result['debug']}")


def test_drought_missing_none_field_fallback(monkeypatch_fetch):
    """如果接口哪天返回的数据里没有'none'字段（换算公式的分母缺失），
    应该优雅降级标记为异常，而不是用错误公式硬算出一个数字。"""
    mock_no_none_field = [
        {"validStart": "2026-06-30T00:00:00", "d0": 18776.87, "d1": 6840.84, "d2": 1.9, "d3": 0, "d4": 0},
    ]
    monkeypatch_fetch({
        "aoi=19": mock_no_none_field,
        "aoi=17": MOCK_DROUGHT_IL,
        "aoi=27": MOCK_DROUGHT_MN,
    })
    result = fd.fetch_drought_monitor()
    assert result["byState"]["IA"]["anomalous"] is True, "缺少none字段时应该标记异常，而不是硬算出错误数字"
    print("✅ 缺少'none'字段时正确降级为异常标记，不会用错误公式硬算")


def test_drought_uses_fips_code_not_postal_abbreviation(monkeypatch_fetch):
    """回归测试：这次真实报告的bug就是把aoi参数误用邮政缩写(IA)而不是FIPS代码(19)，
    导致接口返回200+空数组。这个测试确保以后不会又改回邮政缩写。"""
    captured_urls = []
    def spy_fetch_json_debug(url, headers=None, retries=3, timeout=20):
        captured_urls.append(url)
        if 'aoi=19' in url: return MOCK_DROUGHT_IA, {}
        if 'aoi=17' in url: return MOCK_DROUGHT_IL, {}
        if 'aoi=27' in url: return MOCK_DROUGHT_MN, {}
        return None, {}
    fd.fetch_json_debug = spy_fetch_json_debug
    fd.fetch_drought_monitor()
    assert any('aoi=19' in u for u in captured_urls), f"应该用Iowa的FIPS代码19，实际请求: {captured_urls}"
    assert any('aoi=17' in u for u in captured_urls), f"应该用Illinois的FIPS代码17，实际请求: {captured_urls}"
    assert any('aoi=27' in u for u in captured_urls), f"应该用Minnesota的FIPS代码27，实际请求: {captured_urls}"
    assert not any('aoi=IA' in u or 'aoi=IL' in u or 'aoi=MN' in u for u in captured_urls), \
        f"不应该再用邮政缩写作为aoi参数值，实际请求: {captured_urls}"
    print("✅ 干旱监测确实使用FIPS代码(19/17/27)而非邮政缩写(IA/IL/MN)，本次报告的bug已修复")


def test_psd_real_world_attributeId_schema(monkeypatch_fetch):
    """用户实际部署后报告的真实数据结构就是这样：只有数字attributeId，没有字符串attributeName。
    这个测试模拟"attributeId对照表查询成功"的情况，验证能正确转换出结果。"""
    # 模拟真实报告的原始数据行结构（来自用户截图里的sampleRawRow）
    mock_real_rows = [
        {"commodityCode":"0813100","countryCode":"US","marketYear":"2026","calendarYear":"2026","month":"06","attributeId":7,"unitId":8,"value":74843},
        {"commodityCode":"0813100","countryCode":"US","marketYear":"2026","calendarYear":"2026","month":"06","attributeId":20,"unitId":8,"value":300000},
        {"commodityCode":"0813100","countryCode":"US","marketYear":"2026","calendarYear":"2026","month":"06","attributeId":88,"unitId":8,"value":52000},
        {"commodityCode":"0813100","countryCode":"US","marketYear":"2026","calendarYear":"2026","month":"06","attributeId":125,"unitId":8,"value":34000},
    ]
    # 模拟attributeId对照表接口成功返回（真实ID是猜测占位，重点是验证"查表+匹配"这条逻辑链路本身走得通）
    mock_attribute_names = [
        {"attributeId":7, "attributeName":"Production"},
        {"attributeId":20, "attributeName":"Ending Stocks"},
        {"attributeId":88, "attributeName":"Total Supply"},
        {"attributeId":125, "attributeName":"Domestic Consumption"},
    ]
    monkeypatch_fetch({
        "psd/commodities": MOCK_PSD_COMMODITIES,
        "psd/commodityAttributes": mock_attribute_names,
        "psd/commodity": mock_real_rows,
    })
    result = fd.fetch_psd_supply_demand()
    assert result["available"] is True
    assert result["production"] == 74843, f"应通过attributeId=7查到Production: {result}"
    assert result["endingStocks"] == 300000, f"应通过attributeId=20查到Ending Stocks: {result}"
    assert result["totalSupply"] == 52000
    assert result["domesticConsumption"] == 34000
    assert "debug" not in result, "attributeId对照表查成功且全部匹配上时，不应该出现debug警告"
    print("✅ 真实场景还原测试通过：数字attributeId + 对照表查询 → 正确解析出四个关键字段")


def test_psd_attribute_lookup_fails_gracefully(monkeypatch_fetch):
    """如果attributeId对照表接口也查不到（比如路径确实不对），应该优雅降级，
    不崩溃，并且debug信息里说明白是"对照表查不到"而不是泛泛的"字段名不对"。"""
    mock_real_rows = [
        {"commodityCode":"0813100","countryCode":"US","marketYear":"2026","calendarYear":"2026","month":"06","attributeId":7,"unitId":8,"value":74843},
    ]
    monkeypatch_fetch({
        "psd/commodities": MOCK_PSD_COMMODITIES,
        "psd/commodity": mock_real_rows,
        # 故意不提供 psd/commodityAttributes 等任何对照表匹配，模拟全部查表尝试都失败
    })
    result = fd.fetch_psd_supply_demand()
    assert result["available"] is True, "接口本身是连通的，只是对照表查不到，available应仍为True"
    assert result["production"] is None
    assert "debug" in result
    assert "对照表" in result["debug"]["warning"], f"应明确说明是对照表查询失败: {result['debug']}"
    print("✅ 对照表查询失败时优雅降级，debug信息清楚说明原因而非笼统报错")




def test_noaa_outlook_url_uses_urlencode_no_raw_special_chars(monkeypatch_fetch):
    """回归测试：这个项目已经因为手动拼URL漏编码空格踩过2次坑了(到港预报那边)，
    这次改用urllib.parse.urlencode()，这个测试直接检查请求URL里不应该有
    未编码的裸空格/花括号/引号(这些正是之前出问题的具体字符)。
    ★ 已升级为8点/州架构，现在监测12个大豆主产州(8核心+4次要)：12州×8点=96次请求。"""
    captured_urls = []
    def spy_fetch(url, headers=None, retries=3, timeout=20):
        captured_urls.append(url)
        return None, {}
    fd.fetch_json_debug = spy_fetch
    fd.fetch_noaa_drought_outlook()
    assert len(captured_urls) == 96, f"12州×8点应该是96次请求，实际{len(captured_urls)}次"
    for url in captured_urls:
        assert " " not in url, f"URL里不应该有原始空格: {url}"
        assert "{" not in url, f"URL里不应该有原始花括号(应已被urlencode编码成%7B): {url}"
        assert '"' not in url, f"URL里不应该有原始引号: {url}"
    print("✅ NOAA展望查询URL正确编码(24次请求)，没有重犯之前2次踩过的'裸空格导致control characters错误'")


def _make_noaa_fake_fetch(outlook_by_state):
    """测试辅助函数：给定{"IA": ["Development"]*8, ...}这种"每州对应的outlook列表"，
    返回一个fake_fetch函数，按查询点的lat值判断属于哪个州，依次返回对应的outlook。"""
    call_index_by_state = {state: 0 for state in fd.OUTLOOK_LOCATIONS}
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        for state, points in fd.OUTLOOK_LOCATIONS.items():
            for pt in points:
                if f"{pt['lat']}" in url and f"{pt['lon']}" in url:
                    idx = call_index_by_state[state]
                    outlooks_for_state = outlook_by_state.get(state, ["No_Drought"]*8)
                    outlook = outlooks_for_state[idx % len(outlooks_for_state)]
                    call_index_by_state[state] += 1
                    return {"features": [{"attributes": {"outlook": outlook, "fcst_date": "06/30/2026", "target": "Jul 2026"}}]}, {"httpStatus": 200}
        return None, {}
    return fake_fetch


def test_noaa_outlook_percentage_aggregation_across_8_points(monkeypatch_fetch):
    """核心测试：验证'8点里有百分之多少展望在发展/持续'的统计逻辑正确。
    模拟明尼苏达8个点里有3个显示Persistence/Development，验证算出37.5%，
    而不是简单地"任一点变差就整州变差"或者被单点采样掩盖。"""
    fd.fetch_json_debug = _make_noaa_fake_fetch({
        "IA": ["No_Drought"]*8,  # 爱荷华全部无旱
        "IL": ["No_Drought"]*8,  # 伊利诺伊全部无旱
        "MN": ["Persistence","Persistence","Development","No_Drought","No_Drought","No_Drought","No_Drought","No_Drought"],  # 明尼苏达8点里3个显示变差
    })
    result = fd.fetch_noaa_drought_outlook()
    assert result["available"] is True
    assert result["byState"]["MN"]["worseningCount"] == 3, result["byState"]["MN"]
    assert result["byState"]["MN"]["totalPoints"] == 8
    assert result["byState"]["MN"]["worseningPct"] == 37.5, f"3/8=37.5%，实际{result['byState']['MN']['worseningPct']}"
    assert result["byState"]["IA"]["worseningPct"] == 0.0
    print(f"✅ 8点采样统计正确：明尼苏达3/8个点显示恶化 → {result['byState']['MN']['worseningPct']}%，"
          f"这样才能跟干旱监测的'全州XX%面积'做有意义对比，而不是单点采样掩盖局部旱情")


def test_noaa_outlook_dominant_category_and_overall_signal(monkeypatch_fetch):
    """验证'众数展望'和跟干旱监测口径一致的阈值判断(>=20%明显,>=5%中等,否则偏空)。
    ★ 已改进为按种植面积加权：MN(权重7400)=25%，其余11州权重合计63830，都是0%，
    加权平均 = 25*7400/71230 ≈ 2.6%，落在<5%区间，应判定偏空。"""
    fd.fetch_json_debug = _make_noaa_fake_fetch({
        "MN": ["Persistence"]*2 + ["No_Drought"]*6,  # 25%
    })
    result = fd.fetch_noaa_drought_outlook()
    assert result["byState"]["MN"]["dominantOutlook"] == "No_Drought", "6/8是No_Drought，众数应该是这个"
    assert result["avgWorseningPct"] == 2.6, f"25%×7400权重/71230总权重≈2.6%，实际{result['avgWorseningPct']}"
    assert result["simpleWorseningPct"] == 2.1, "简单平均应该还是2.1(25/12)，保留做对比参考"
    assert result["overallSignal"] == -1, f"加权平均仅2.6%(<5%阈值)，应判定偏空: {result}"
    print("✅ 众数展望识别正确，加权平均阈值判断(>=20偏多/>=5中性/否则偏空)跟干旱监测口径一致")
    print(f"   加权平均{result['avgWorseningPct']}% vs 简单平均{result['simpleWorseningPct']}%——"
          f"明尼苏达权重(7400)在加权后被适度放大，比简单平均(每州权重相等)更贴近实际经济影响")


def test_noaa_outlook_point_outside_any_outlook_zone(monkeypatch_fetch):
    """如果某个点没有落在任何展望区域内(features为空数组)，应该优雅标记该州不可用，
    而不是崩溃或误报数据。"""
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return {"features": []}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch

    result = fd.fetch_noaa_drought_outlook()
    assert result["available"] is False, "所有点都查不到任何展望区域时，应该整体标记不可用"
    assert "debug" in result
    print("✅ 查询点不在任何展望区域内时优雅降级，不崩溃")


def test_soybean_condition_parsing_and_wow_change(monkeypatch_fetch):
    """验证美豆优良率解析：Excellent+Good两个独立字段相加，且能算出环比变化。
    用查证过的真实新闻数据模拟(7月5日64%，前一周65%)。"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = "test-key"
    mock_response = {
        "data": [
            {"week_ending": "2026-06-28", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT EXCELLENT", "Value": "10"},
            {"week_ending": "2026-06-28", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT GOOD", "Value": "55"},
            {"week_ending": "2026-07-05", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT EXCELLENT", "Value": "9"},
            {"week_ending": "2026-07-05", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT GOOD", "Value": "55"},
            {"week_ending": "2026-07-05", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT VERY POOR", "Value": "2"},
        ]
    }
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch

    try:
        result = fd.fetch_soybean_condition()
        assert result["available"] is True
        assert result["weekEnding"] == "2026-07-05", "应该取最新一周(7月5日)，不是6月28日那条"
        assert result["goodExcellentPct"] == 64.0, f"9+55=64，实际{result['goodExcellentPct']}"
        assert result["wowChangePts"] == -1.0, f"64-65=-1，实际{result['wowChangePts']}"
        print("✅ 美豆优良率解析正确：正确取最新一周、Excellent+Good相加、环比计算正确")
        print(f"   示例输出: {result}")
    finally:
        fd.NASS_API_KEY = old_key


def test_soybean_condition_missing_api_key(monkeypatch_fetch):
    """没配置NASS_API_KEY时应该优雅提示，不崩溃"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = ""
    try:
        result = fd.fetch_soybean_condition()
        assert result["available"] is False
        assert "NASS_API_KEY" in result["reason"]
        print("✅ 缺少NASS密钥时优雅提示，不崩溃")
    finally:
        fd.NASS_API_KEY = old_key


def test_soybean_condition_field_mismatch_gives_diagnostic(monkeypatch_fetch):
    """如果字段名对不上(比如接口改了描述格式)，应该给出诊断信息而不是静默返回None"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = "test-key"
    mock_response = {"data": [{"week_ending": "2026-07-05", "short_desc": "SOMETHING ELSE ENTIRELY", "Value": "10"}]}
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    try:
        result = fd.fetch_soybean_condition()
        assert result["available"] is False
        assert "debug" in result
        print("✅ 字段名对不上时给出诊断信息，而不是静默失败")
    finally:
        fd.NASS_API_KEY = old_key


def test_south_america_weather_weighted_avg(monkeypatch_fetch):
    """验证南美天气加权平均：马托格罗索(权重30，巴西最大产区)应该比
    米纳斯吉拉斯(权重5，小产区)在加权平均里占更大比重。"""
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        if "latitude=-12.5" in url:  # MT
            return {"daily": {"precipitation_sum": [10,10,10,10,10,10,10], "temperature_2m_max": [30]*7}}, {}
        return {"daily": {"precipitation_sum": [0,0,0,0,0,0,0], "temperature_2m_max": [30]*7}}, {}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_south_america_weather()
    assert result["available"] is True
    # MT(权重30)=70mm，其余5个州(权重共38)=0mm；加权平均=70*30/68≈30.9，明显高于简单平均(70/6≈11.7)
    assert result["avgPrecip7d"] > 25, f"马托格罗索权重最大，应该显著拉高加权平均，实际{result['avgPrecip7d']}"
    print(f"✅ 南美天气加权平均正确：马托格罗索(权重30)主导结果，加权平均{result['avgPrecip7d']}mm")


def test_south_america_psd_uses_soybean_not_meal_code(monkeypatch_fetch):
    """回归测试：南美关心的是大豆原豆产量，不是豆粕产量，这个测试确认
    get_soybean_psd_code()正确排除了包含'meal'的商品，只匹配纯'Soybeans'。"""
    mock_commodities = [
        {"commodityCode": "0813200", "commodityName": "Soybean Meal"},
        {"commodityCode": "0813500", "commodityName": "Soybean Oil"},
        {"commodityCode": "2222000", "commodityName": "Soybeans"},
    ]
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_commodities, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    code, debug = fd.get_soybean_psd_code()
    assert code == "2222000", f"应该匹配纯Soybeans(不含meal/oil)，实际{code}"
    print("✅ 南美PSD正确使用大豆(非豆粕)商品代码，避免查错数据类型")


def test_south_america_psd_handles_oilseed_soybean_naming(monkeypatch_fetch):
    """回归测试：这次真实报告的bug——USDA很可能把大豆归类命名成"Oilseed, Soybean"
    (大豆本来就属于油籽类作物)，"oilseed"这个词本身包含"oil"，之前的排除逻辑
    (排除任何含"oil"的名字)会连"Oilseed, Soybean"这条真正该匹配的也一起排除掉。"""
    mock_commodities = [
        {"commodityCode": "0813200", "commodityName": "Oilseed, Soybean Meal"},
        {"commodityCode": "0813500", "commodityName": "Oilseed, Soybean Oil"},
        {"commodityCode": "2222000", "commodityName": "Oilseed, Soybean"},  # 真正该匹配的这条
    ]
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_commodities, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    code, debug = fd.get_soybean_psd_code()
    assert code == "2222000", f"应该正确匹配'Oilseed, Soybean'这条，不应该被'oilseed'里的'oil'误伤排除，实际{code}"
    print("✅ 已修复：'Oilseed, Soybean'这种真实命名方式能被正确匹配，不再被'oil'子串误伤")


def test_south_america_psd_exact_match_beats_decoy_commodity(monkeypatch_fetch):
    """回归测试：这次真实实测报告的第二个bug——巴西产量实测只有13,260(千吨)，
    但查证过真实数字是180,000，只有7.4%。排查发现Production+BeginningStocks+Imports=
    TotalSupply在数学上是自洽的(13260+197+100=13557)，说明USDA接口本身数值没问题，
    是宽松匹配("soybean"+不含meal+不含soybean oil")抓到了列表里排在"Oilseed, Soybean"
    前面的另一个小分类("诱饵"商品，比如某个大豆细分子类)，而不是主要统计口径那条。
    这个测试模拟"诱饵商品排在正确商品前面"的场景，确认精确匹配优先，不会被诱饵带偏。"""
    mock_commodities = [
        {"commodityCode": "9999999", "commodityName": "Soybean, Forage"},  # 诱饵：排在前面，也满足"含soybean不含meal/oil"
        {"commodityCode": "8888888", "commodityName": "Soybean Cake, Feed"},  # 另一个诱饵
        {"commodityCode": "2222000", "commodityName": "Oilseed, Soybean"},  # 真正该匹配的这条，排在后面
    ]
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_commodities, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    code, debug = fd.get_soybean_psd_code()
    assert code == "2222000", (
        f"精确匹配'Oilseed, Soybean'应该优先于列表顺序，不应该被排在前面的诱饵商品"
        f"('Soybean, Forage'/'Soybean Cake, Feed')带偏，实际匹配到了{code}"
    )
    assert debug["matchedBy"] == "精确匹配'Oilseed, Soybean'", f"应该走精确匹配路径，实际{debug}"
    print("✅ 已修复第二个真实bug：精确匹配'Oilseed, Soybean'不会被列表顺序中排在前面的诱饵商品带偏")


def test_south_america_psd_falls_back_when_exact_name_missing(monkeypatch_fetch):
    """如果确实没有'Oilseed, Soybean'这个精确名称(比如USDA改了命名规范)，
    应该优雅退回宽松匹配兜底，而不是直接失败——同时debug信息要明确标注
    这是走的兜底路径，提醒之后核对抓到的是不是真的对。"""
    mock_commodities = [
        {"commodityCode": "0813200", "commodityName": "Soybean Meal"},
        {"commodityCode": "5555555", "commodityName": "Soybeans"},  # 没有"Oilseed, Soybean"这个精确名称，只有这个变体
    ]
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_commodities, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    code, debug = fd.get_soybean_psd_code()
    assert code == "5555555", f"精确匹配失败时应该退回宽松匹配兜底，实际{code}"
    assert "兜底" in debug["matchedBy"], f"debug应该明确标注这是走的兜底路径，实际{debug}"
    print("✅ 精确匹配失败时正确退回宽松匹配兜底，且debug信息清楚标注这是兜底路径")


def test_south_america_psd_diagnostic_shows_soybean_entries_not_generic_alphabet(monkeypatch_fetch):
    """验证诊断信息改进：如果匹配失败，应该专门列出所有含'soybean'的条目，
    而不是笼统列出前50个按字母排序的商品(可能全是A/B/C开头，看不到真正相关的部分)。"""
    # 制造60个不相关的commodity(消耗掉"前50个"这个名额)，混入几个真正含soybean但排除条件下不该匹配的
    mock_commodities = [{"commodityCode": f"999{i:04d}", "commodityName": f"Aardvark Product {i}"} for i in range(60)]
    mock_commodities.append({"commodityCode": "0813200", "commodityName": "Soybean Meal"})
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_commodities, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    code, debug = fd.get_soybean_psd_code()
    assert code is None, "只有Soybean Meal(含meal，应被排除)，不应该匹配到任何代码"
    assert "Soybean Meal" in debug["allSoybeanRelatedEntries"], \
        f"即使前面有60个不相关商品，也应该能在诊断信息里看到真正含soybean的那条: {debug}"
    assert len(debug["allSoybeanRelatedEntries"]) == 1, "不应该把60个不相关的Aardvark条目也塞进来"
    print("✅ 诊断信息已改进：专门列出含soybean的条目，不会被大量不相关商品淹没")


def test_south_america_weather_handles_partial_failure(monkeypatch_fetch):
    """如果只有部分产区数据可用(比如阿根廷查询失败)，应该用可用的数据继续计算，不整体失败。"""
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        if "latitude=-12.5" in url:  # 只有巴西MT成功
            return {"daily": {"precipitation_sum": [5]*7, "temperature_2m_max": [28]*7}}, {}
        return None, {"error": "模拟失败"}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_south_america_weather()
    assert result["available"] is True, "只要有至少1个产区数据可用，就不应该整体标记失败"
    print("✅ 南美天气部分产区失败时，用可用数据继续计算，不因个别产区失败而整体不可用")


def test_us_planting_progress_parsing_and_wow_change(monkeypatch_fetch):
    """验证美豆播种进度解析：正确识别PCT PLANTED字段、取最新一周、算出环比。"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = "test-key"
    mock_response = {
        "data": [
            {"week_ending": "2026-05-04", "short_desc": "SOYBEANS - PROGRESS, MEASURED IN PCT PLANTED", "Value": "62"},
            {"week_ending": "2026-05-11", "short_desc": "SOYBEANS - PROGRESS, MEASURED IN PCT PLANTED", "Value": "78"},
        ]
    }
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    try:
        result = fd.fetch_us_planting_progress()
        assert result["available"] is True
        assert result["weekEnding"] == "2026-05-11", "应该取最新一周(5/11)，不是5/4那条"
        assert result["pctPlanted"] == 78.0
        assert result["wowChangePts"] == 16.0, f"78-62=16，实际{result['wowChangePts']}"
        print(f"✅ 美豆播种进度解析正确：正确取最新一周、环比计算正确，示例：{result}")
    finally:
        fd.NASS_API_KEY = old_key


def test_us_planting_progress_filters_out_annual_survey_data(monkeypatch_fetch):
    """回归测试：这个bug经历了三次修复才找对方向——
    第一次(错误)修复：以为要加freq_desc=WEEKLY才能把"AREA PLANTED"底下混杂的
    ANNUAL(年度调查)和周度进度数据分开。但用户实测发现，加了freq_desc=WEEKLY后
    NASS API直接返回"bad request - invalid query"，说明这个参数组合本身不合法。
    第二次(方向不对)修复：改成不加freq_desc，靠short_desc字符串过滤——这个能让
    查询不报错，但用户实测发现"AREA PLANTED"这个分类底下，在NATIONAL层级根本
    没有任何"PCT PLANTED"记录，只有年度英亩数调查，说明从一开始statisticcat_desc
    就选错了分类。
    第三次(真正找到根因)修复：查到确切的NASS API使用案例，确认周度进度百分比
    根本不在"AREA PLANTED"底下，而是独立的statisticcat_desc="PROGRESS"，还需要
    额外指定unit_desc="PCT PLANTED"才能从PROGRESS大类(还包含emerged/blooming等
    其他生长阶段)里筛出播种进度这一项。
    这个测试确认：请求URL里应该带上正确的statisticcat_desc=PROGRESS和
    unit_desc=PCT+PLANTED这组参数，不能是错误的AREA+PLANTED。"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = "test-key"
    captured_params = {}
    mock_response = {
        "data": [
            {"week_ending": "2026-06-01", "short_desc": "SOYBEANS - PROGRESS, MEASURED IN PCT PLANTED", "Value": "92", "freq_desc": "WEEKLY"},
        ]
    }
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        captured_params["url"] = url
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    try:
        result = fd.fetch_us_planting_progress()
        assert "freq_desc" not in captured_params["url"], \
            "请求URL不应该带freq_desc参数——实测确认这个参数会让NASS API拒绝查询(bad request - invalid query)"
        assert "statisticcat_desc=PROGRESS" in captured_params["url"], \
            f"★核心验证：请求应该用statisticcat_desc=PROGRESS(不是错误的AREA+PLANTED)，实际URL: {captured_params['url']}"
        assert "unit_desc=PCT" in captured_params["url"] and "PLANTED" in captured_params["url"], \
            f"★核心验证：请求应该带unit_desc=PCT PLANTED来筛出具体的生长阶段，实际URL: {captured_params['url']}"
        assert result["available"] is True
        assert result["pctPlanted"] == 92.0
        print(f"✅ 已修复(第三次，找到确切根因)：用statisticcat_desc=PROGRESS+unit_desc=PCT PLANTED正确查到播种进度(92%)")
    finally:
        fd.NASS_API_KEY = old_key


def test_us_planting_progress_missing_api_key(monkeypatch_fetch):
    """没配置NASS_API_KEY时应该优雅提示，不崩溃"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = ""
    try:
        result = fd.fetch_us_planting_progress()
        assert result["available"] is False
        assert "NASS_API_KEY" in result["reason"]
        print("✅ 缺少NASS密钥时优雅提示，不崩溃")
    finally:
        fd.NASS_API_KEY = old_key


def test_us_planting_progress_field_mismatch_gives_diagnostic(monkeypatch_fetch):
    """字段名对不上时应给出诊断信息，而不是静默返回None"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = "test-key"
    mock_response = {"data": [{"week_ending": "2026-05-04", "short_desc": "SOMETHING ELSE ENTIRELY", "Value": "10"}]}
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    try:
        result = fd.fetch_us_planting_progress()
        assert result["available"] is False
        assert "debug" in result
        print("✅ 字段名对不上时给出诊断信息，而不是静默失败")
    finally:
        fd.NASS_API_KEY = old_key


def test_us_harvest_progress_parsing_and_wow_change(monkeypatch_fetch):
    """验证美豆收获进度解析：正确识别PCT HARVESTED字段(区别于PCT PLANTED)、取最新一周、算出环比。"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = "test-key"
    mock_response = {
        "data": [
            {"week_ending": "2026-10-05", "short_desc": "SOYBEANS - PROGRESS, MEASURED IN PCT HARVESTED", "Value": "45"},
            {"week_ending": "2026-10-12", "short_desc": "SOYBEANS - PROGRESS, MEASURED IN PCT HARVESTED", "Value": "68"},
        ]
    }
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    try:
        result = fd.fetch_us_harvest_progress()
        assert result["available"] is True
        assert result["weekEnding"] == "2026-10-12"
        assert result["pctHarvested"] == 68.0
        assert result["wowChangePts"] == 23.0, f"68-45=23，实际{result['wowChangePts']}"
        print(f"✅ 美豆收获进度解析正确，示例：{result}")
    finally:
        fd.NASS_API_KEY = old_key


def test_us_harvest_progress_distinguishes_from_planting(monkeypatch_fetch):
    """回归测试：确认收获进度用的是"PCT HARVESTED"过滤条件，不会跟播种进度的
    "PCT PLANTED"混淆——如果混进了PCT PLANTED的数据行，不应该被误当成收获数据。"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = "test-key"
    mock_response = {
        "data": [
            {"week_ending": "2026-10-05", "short_desc": "SOYBEANS - PROGRESS, MEASURED IN PCT PLANTED", "Value": "100"},  # 混入的播种数据，不该被用
            {"week_ending": "2026-10-05", "short_desc": "SOYBEANS - PROGRESS, MEASURED IN PCT HARVESTED", "Value": "45"},
        ]
    }
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    try:
        result = fd.fetch_us_harvest_progress()
        assert result["pctHarvested"] == 45.0, f"应该只取PCT HARVESTED这条(45)，不该被混入的PCT PLANTED(100)干扰，实际{result['pctHarvested']}"
        print("✅ 收获进度正确区分'PCT HARVESTED'和'PCT PLANTED'，不会互相混淆")
    finally:
        fd.NASS_API_KEY = old_key


def test_contract_code_computation(monkeypatch_fetch):
    """验证合约代码计算：给定"今天"的日期，算出的M09/M01/M05具体代码是否正确。
    这个逻辑很容易出的错：月份边界判断反了、年份进位算错等。"""
    from datetime import datetime, timezone
    now = datetime(2026, 7, 12, tzinfo=timezone.utc)
    assert fd.get_current_contract_code(9, now) == "M2609", "7月，9月合约还没到，应该是今年的M2609"
    assert fd.get_current_contract_code(1, now) == "M2701", "7月，1月合约已经过了，应该是明年的M2701"
    assert fd.get_current_contract_code(5, now) == "M2705", "7月，5月合约已经过了，应该是明年的M2705"

    # 边界测试：1月份看1月合约，应该是"今年"而不是"明年"(容易被<=判断反了)
    now2 = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert fd.get_current_contract_code(1, now2) == "M2601", "1月份看1月合约，应该是今年的M2601，不是提前跳到明年"

    # ★用户明确举了这个例子担心算错：2026年8月该做1月合约，必须是2027年1月(M2701)，
    #   不能是2026年1月(M2601，那个早已经过期7个月了)——这个具体场景之前测试里没有覆盖到
    now3 = datetime(2026, 8, 20, tzinfo=timezone.utc)
    assert fd.get_current_contract_code(1, now3) == "M2701", "★2026年8月找1月合约，必须往后跳到2027年1月(M2701)，不能是已过期的2026年1月"
    print("✅ 合约代码计算正确：7月看9月合约=M2609，看1/5月合约(已过)=明年M2701/M2705；边界情况(1月看1月合约)也正确；用户举例的8月找1月合约场景也验证通过")


def test_main_fetches_all_three_contracts(monkeypatch_fetch):
    """★验证多合约接入：main()应该对9月/5月/1月三个合约都分别调用日线+小时线抓取，
    以及持仓排名(龙虎榜)，用get_current_contract_code()算出的具体合约代码去请求，
    存进以月份命名(不含具体年份)的key里。用手动monkeypatch记录实际被调用时传入了
    什么symbol，而不是真的跑akshare请求。"""
    import json as json_module
    import tempfile

    monkeypatch_fetch({})  # 其他依赖fetch_json_debug的函数用空url_map，全部优雅降级为不可用，不影响本测试要验证的东西

    daily_calls = []
    hourly_calls = []
    position_rank_calls = []
    def fake_daily(symbol, max_rows=260):
        daily_calls.append(symbol)
        return {"available": True, "symbol": symbol, "totalBarsReturned": 1, "bars": [{"date": "2026-01-01", "open": 1, "high": 1, "low": 1, "close": 1}], "source": "测试"}
    def fake_hourly(symbol, max_bars=180):
        hourly_calls.append(symbol)
        return {"available": True, "symbol": symbol, "totalBarsReturned": 1, "bars": [{"datetime": "2026-01-01 10:00:00", "open": 1, "high": 1, "low": 1, "close": 1}], "source": "测试"}
    def fake_position_rank(symbols, max_attempts=6):
        position_rank_calls.append(list(symbols))
        return {s: {"available": True, "symbol": s, "date": "20260712", "rows": [], "source": "测试"} for s in symbols}

    old_daily, old_hourly = fd.fetch_dce_daily_kline, fd.fetch_dce_hourly_kline
    old_position_rank = fd.fetch_dce_position_rank_multi
    old_output_path = fd.OUTPUT_PATH
    old_key = fd.USDA_API_KEY
    fd.fetch_dce_daily_kline = fake_daily
    fd.fetch_dce_hourly_kline = fake_hourly
    fd.fetch_dce_position_rank_multi = fake_position_rank
    fd.USDA_API_KEY = ""  # 避免main()真的去跑USDA相关的网络请求路径

    tmp_dir = tempfile.mkdtemp()
    fd.OUTPUT_PATH = os.path.join(tmp_dir, "latest.json")
    try:
        from datetime import datetime as real_datetime, timezone as real_timezone
        now = real_datetime(2026, 7, 12, tzinfo=real_timezone.utc)  # 固定"现在"，让期望值可预测
        expected_codes = {
            fd.get_current_contract_code(9, now),  # M2609
            fd.get_current_contract_code(5, now),  # M2705
            fd.get_current_contract_code(1, now),  # M2701
        }
        fd.main()

        assert set(daily_calls) == expected_codes, f"main()应该对这3个日线合约代码发起请求: {expected_codes}，实际请求了: {daily_calls}"
        assert set(hourly_calls) == expected_codes, f"main()应该对这3个小时线合约代码发起请求: {expected_codes}，实际请求了: {hourly_calls}"
        assert len(position_rank_calls) == 1, f"★持仓排名应该只调用1次(批量传入3个合约，不是分别调用3次)，实际调用了{len(position_rank_calls)}次"
        assert set(position_rank_calls[0]) == expected_codes, f"持仓排名批量调用时传入的合约代码应该是这3个: {expected_codes}，实际传入: {position_rank_calls[0]}"

        with open(fd.OUTPUT_PATH, "r", encoding="utf-8") as f:
            written = json_module.load(f)
        for key in ["dceM09Daily", "dceM09Hourly", "dceM05Daily", "dceM05Hourly", "dceM01Daily", "dceM01Hourly",
                    "dceM09PositionRank", "dceM05PositionRank", "dceM01PositionRank"]:
            assert key in written, f"输出JSON里应该有{key}这个字段(用月份命名，不含具体年份，这样合约年份滚动时key不用改)"
        print(f"✅ main()正确对三个合约(9/5/1月)都发起了日线+小时线+持仓排名请求(持仓排名批量1次调用而非3次)，输出JSON的9个key都存在")
    finally:
        fd.fetch_dce_daily_kline, fd.fetch_dce_hourly_kline = old_daily, old_hourly
        fd.fetch_dce_position_rank_multi = old_position_rank
        fd.OUTPUT_PATH = old_output_path
        fd.USDA_API_KEY = old_key


def test_dce_daily_kline_parsing(monkeypatch_fetch):
    """验证日K线解析：用akshare确认过的真实字段结构(date/open/high/low/close/volume/hold/settle)
    模拟DataFrame返回，确认能正确转换成JSON可序列化的格式，并且只取最近N条。"""
    import pandas as pd
    import fetch_data as fd_module

    # 模拟300条数据，验证max_rows裁剪逻辑生效
    mock_df = pd.DataFrame({
        "date": [f"2025-{(i%12)+1:02d}-01" for i in range(300)],
        "open": [3300.0+i for i in range(300)],
        "high": [3320.0+i for i in range(300)],
        "low": [3280.0+i for i in range(300)],
        "close": [3310.0+i for i in range(300)],
        "volume": [100000.0+i for i in range(300)],
        "hold": [500000.0+i for i in range(300)],
        "settle": [3305.0+i for i in range(300)],
    })

    original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
    class FakeAkshare:
        @staticmethod
        def futures_zh_daily_sina(symbol):
            return mock_df

    import sys
    sys.modules['akshare'] = FakeAkshare()
    try:
        result = fd_module.fetch_dce_daily_kline("M2609", max_rows=260)
        assert result["available"] is True
        assert result["totalBarsReturned"] == 260, f"300条数据裁剪到max_rows=260，实际{result['totalBarsReturned']}"
        assert result["bars"][-1]["close"] == 3310.0+299, "应该保留最新(最后)的那些行，不是最早的"
        assert result["symbol"] == "M2609"
        assert "settle" in result["bars"][-1], "★补上的字段：结算价(settle)之前mock数据里有但代码没提取，现在应该正确带出来"
        assert result["bars"][-1]["settle"] == 3305.0+299, f"结算价数值应该正确，实际{result['bars'][-1].get('settle')}"
        print(f"✅ 日K线解析正确：300条数据正确裁剪到260条，且保留的是最新数据(最后一条close={result['bars'][-1]['close']})，结算价字段也正确带出来了")
    finally:
        del sys.modules['akshare']


def test_dce_hourly_kline_parsing(monkeypatch_fetch):
    """验证小时K线解析：字段结构跟日K线不同，时间字段实测确认叫datetime(不是date)。
    ★这个测试之前mock数据里意外写成了"date"，跟同期出现的真实bug(代码里也错误地
      用了row["date"])保持了一致，导致测试没能抓到这个真实问题——这次改成用实测
      确认过的"datetime"，跟GitHub Actions真实返回的字段结构对齐。"""
    import pandas as pd
    import fetch_data as fd_module

    mock_df = pd.DataFrame({
        "datetime": [f"2026-07-{(i%28)+1:02d} 10:00:00" for i in range(200)],
        "open": [3300.0+i*0.1 for i in range(200)],
        "high": [3320.0+i*0.1 for i in range(200)],
        "low": [3280.0+i*0.1 for i in range(200)],
        "close": [3310.0+i*0.1 for i in range(200)],
        "volume": [1000.0+i for i in range(200)],
        "hold": [50000.0+i for i in range(200)],
    })

    import sys
    class FakeAkshare:
        @staticmethod
        def futures_zh_minute_sina(symbol, period):
            assert period == "60", f"小时线应该传period='60'，实际传了{period}"
            return mock_df

    sys.modules['akshare'] = FakeAkshare()
    try:
        result = fd_module.fetch_dce_hourly_kline("M2609", max_bars=180)
        assert result["available"] is True
        assert result["totalBarsReturned"] == 180, f"200条裁剪到max_bars=180，实际{result['totalBarsReturned']}"
        print(f"✅ 小时K线解析正确：确认period='60'参数正确传递，200条数据正确裁剪到180条")
    finally:
        del sys.modules['akshare']


def test_dce_continuous_kline_handles_chinese_column_names(monkeypatch_fetch):
    """★真实用户报告的bug：futures_main_sina()很可能返回中文字段名(日期/开盘价/最高价/
    最低价/收盘价/成交量/持仓量)，不是futures_zh_daily_sina()那种英文字段名。之前直接
    假设是英文，用户实测报错'字段解析失败: close'。这次改成同时兼容中英文两种可能。"""
    import pandas as pd
    import fetch_data as fd_module

    # 模拟中文字段名的DataFrame(用户遇到的真实情况)
    mock_df_cn = pd.DataFrame({
        "日期": ["2016-01-04", "2016-01-05", "2016-01-06"],
        "开盘价": [2500.0, 2510.0, 2505.0],
        "最高价": [2520.0, 2525.0, 2515.0],
        "最低价": [2490.0, 2500.0, 2495.0],
        "收盘价": [2510.0, 2505.0, 2508.0],
        "成交量": [50000.0, 52000.0, 51000.0],
        "持仓量": [200000.0, 201000.0, 202000.0],
    })
    import sys
    class FakeAkshareCn:
        @staticmethod
        def futures_main_sina(symbol, start_date):
            return mock_df_cn
    sys.modules['akshare'] = FakeAkshareCn()
    try:
        result = fd_module.fetch_dce_continuous_kline("M0", years=3)
        assert result["available"] is True, f"中文字段名的数据应该能正确解析，实际：{result}"
        assert result["bars"][-1]["close"] == 2508.0
        assert result["bars"][-1]["open"] == 2505.0
        assert result["bars"][-1]["volume"] == 51000.0
        assert result["bars"][-1]["hold"] == 202000.0
        print(f"✅ 中文字段名(日期/开盘价/收盘价等)能正确解析，不再报'字段解析失败: close'")
    finally:
        del sys.modules['akshare']

    # 反过来验证：英文字段名(futures_zh_daily_sina风格)也应该继续兼容，不能顾此失彼
    mock_df_en = pd.DataFrame({
        "date": ["2016-01-04"], "open": [2500.0], "high": [2520.0],
        "low": [2490.0], "close": [2510.0], "volume": [50000.0], "hold": [200000.0],
    })
    class FakeAkshareEn:
        @staticmethod
        def futures_main_sina(symbol, start_date):
            return mock_df_en
    sys.modules['akshare'] = FakeAkshareEn()
    try:
        result = fd_module.fetch_dce_continuous_kline("M0", years=3)
        assert result["available"] is True, "英文字段名也应该继续兼容(不能因为改支持中文就弄坏了英文)"
        assert result["bars"][0]["close"] == 2510.0
        print(f"✅ 英文字段名同样正确解析，两种命名方式都兼容")
    finally:
        del sys.modules['akshare']


def test_dce_continuous_kline_debug_output_is_json_safe(monkeypatch_fetch):
    """★真实用户报告的第二个bug：字段解析失败时，debug信息里如果含有date/Timestamp
    这类物件，json.dumps会直接崩溃(TypeError: Object of type date is not JSON serializable)，
    导致连'显示诊断信息'这一步都跑不完，反而看不到真正有用的错误内容。"""
    import pandas as pd
    import datetime as dt
    import json
    import fetch_data as fd_module

    # 模拟一个完全没有任何可用字段名的DataFrame(触发解析失败路径)，
    # 且故意让某一列是真正的date物件(不是字符串)，模拟用户遇到的真实情况
    mock_df_bad = pd.DataFrame({
        "某个日期字段": [dt.date(2016, 1, 4)],  # 真正的date物件，不是字符串
        "完全无关的字段": ["不知道是什么"],
    })
    import sys
    class FakeAkshareBad:
        @staticmethod
        def futures_main_sina(symbol, start_date):
            return mock_df_bad
    sys.modules['akshare'] = FakeAkshareBad()
    try:
        result = fd_module.fetch_dce_continuous_kline("M0", years=3)
        assert result["available"] is False
        assert "debug" in result
        try:
            json.dumps(result["debug"], ensure_ascii=False)
            json_safe = True
        except TypeError:
            json_safe = False
        assert json_safe, "★关键验证：debug信息本身必须能被json.dumps正常序列化，不能因为含有date物件就崩溃"
        print(f"✅ debug信息即使含有date物件，也能被正常JSON序列化(不会在'显示诊断信息'这一步自己先崩溃)")
    finally:
        del sys.modules['akshare']


def test_eastmoney_position_url_construction(monkeypatch_fetch):
    """★龙虎榜(东方财富版)：URL构造应该精确匹配真实抓包结果——这个URL结构是用户在
    浏览器F12开发者工具里实测抓到的真实请求，不是看文档/猜测的，所以这里用抓包
    结果的固定部分做精确字符串比对(时间戳_=参数每次都变，只比对其余固定部分)。"""
    import fetch_data as fd_module

    url = fd_module._build_eastmoney_position_url("M2701", "2026-09-18", "LPRANK")
    expected_fixed_part = (
        "https://datacenter-web.eastmoney.com/api/data/v1/get?"
        "reportName=RPT_FUTU_DAILYPOSITION&columns=ALL&"
        "filter=(SECURITY_CODE%3D%22M2701%22)(TRADE_DATE%3D%272026-09-18%27)(TYPE%3D%220%22)(LPRANK%3C%3E9999)&"
        "sortTypes=1&sortColumns=LPRANK&pageNumber=1&pageSize=20&source=WEB&client=WEB"
    )
    assert url.startswith(expected_fixed_part), f"URL构造应该跟真实抓包结果完全一致，实际: {url}"
    print("✅ URL构造精确匹配真实抓包结果(括号不转义、参数顺序、filter语法全部一致)")


def test_eastmoney_position_row_parsing(monkeypatch_fetch):
    """★龙虎榜(东方财富版)：用用户提供的真实响应数据验证解析逻辑——包括排名9999
    (无排名)要被过滤掉、多头/空头分开填充不串号、用干净的会员名(不带"代客"后缀)。"""
    import fetch_data as fd_module

    raw_rows = [
        {"MEMBER_NAME_ABBR": "国泰君安（代客）", "ORG_NAME_ABBR_NEW": "国泰君安",
         "LP_RANK": 1, "SP_RANK": 4, "VOLUME": 611840, "VOLUME_CHANGE": 107078,
         "LONG_POSITION": 282361, "LP_CHANGE": -6712, "SHORT_POSITION": 148453, "SP_CHANGE": 1450},
        {"MEMBER_NAME_ABBR": "中粮期货（代客）", "ORG_NAME_ABBR_NEW": "中粮期货",
         "LP_RANK": 12, "SP_RANK": 1, "VOLUME": 87954, "VOLUME_CHANGE": 52320,
         "LONG_POSITION": 56303, "LP_CHANGE": 6780, "SHORT_POSITION": 591686, "SP_CHANGE": -34650},
        {"MEMBER_NAME_ABBR": "国联期货（代客）", "ORG_NAME_ABBR_NEW": "国联期货",
         "LP_RANK": 9999, "SP_RANK": 9999, "VOLUME": 89447, "VOLUME_CHANGE": 15268,
         "LONG_POSITION": None, "LP_CHANGE": None, "SHORT_POSITION": None, "SP_CHANGE": None},
    ]

    long_rows = fd_module._parse_eastmoney_position_rows(raw_rows, "LPRANK")
    assert len(long_rows) == 2, f"LP_RANK=9999(国联期货)应该被过滤掉，剩2条，实际{len(long_rows)}条"
    assert long_rows[0]["rank"] == 1 and long_rows[0]["longPartyName"] == "国泰君安"
    assert long_rows[0]["longOpenInterest"] == 282361 and long_rows[0]["longOpenInterestChg"] == -6712
    assert long_rows[0]["shortPartyName"] == "", "★按多头排序解析时，不应该混入空头会员名"
    assert "代客" not in long_rows[0]["longPartyName"], "应该用ORG_NAME_ABBR_NEW干净名字，不带'代客'后缀"

    short_rows = fd_module._parse_eastmoney_position_rows(raw_rows, "SPRANK")
    assert short_rows[0]["rank"] == 1 and short_rows[0]["shortPartyName"] == "中粮期货", "★应该按SP_RANK排序，中粮期货(SP_RANK=1)排第一"
    assert short_rows[0]["shortOpenInterest"] == 591686
    assert short_rows[0]["longPartyName"] == "", "★按空头排序解析时，不应该混入多头会员名"
    print("✅ 用真实响应数据验证：多头/空头分开解析正确，9999哨兵值被过滤，显示名不带'代客'后缀")


def test_eastmoney_position_jsonp_unwrap(monkeypatch_fetch):
    """★龙虎榜(东方财富版)：fetch_jsonp_debug应该正确剥掉JSONP回调包装(真实响应实测
    确认是这个格式)，同时也要能正确处理万一哪天接口直接返回纯JSON(无包装)的情况。"""
    import fetch_data as fd_module

    class FakeResponse:
        def __init__(self, body):
            self._body = body.encode("utf-8")
            self.status = 200
        def read(self):
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    jsonp_body = 'jQuery1123041726061443928875_1789959148296({"success":true,"result":{"data":[{"a":1}]},"message":"ok"});'
    old_urlopen = fd_module.urllib.request.urlopen
    fd_module.urllib.request.urlopen = lambda req, timeout=20: FakeResponse(jsonp_body)
    try:
        data, debug = fd_module.fetch_jsonp_debug("https://example.com/test")
        assert data is not None and data["success"] is True, "★应该正确剥掉JSONP包装并解析出JSON内容"
        assert data["result"]["data"] == [{"a": 1}]
        print("✅ fetch_jsonp_debug正确剥掉真实响应格式的JSONP包装")
    finally:
        fd_module.urllib.request.urlopen = old_urlopen

    plain_body = '{"success":true,"result":{"data":[{"b":2}]},"message":"ok"}'
    fd_module.urllib.request.urlopen = lambda req, timeout=20: FakeResponse(plain_body)
    try:
        data, debug = fd_module.fetch_jsonp_debug("https://example.com/test2")
        assert data is not None and data["result"]["data"] == [{"b": 2}], "★纯JSON(无JSONP包装)也应该能正确处理，不误判成需要剥括号"
        print("✅ fetch_jsonp_debug对纯JSON(万一接口哪天不带回调了)也能正确兜底处理")
    finally:
        fd_module.urllib.request.urlopen = old_urlopen


def test_eastmoney_position_rank_integration(monkeypatch_fetch):
    """★龙虎榜(东方财富版)：完整集成测试——mock掉fetch_jsonp_debug，验证
    fetch_dce_position_rank_multi()对每个合约正确发起2次请求(多头+空头)、
    正确处理T+1重试(模拟"今天"数据还没发布，要往前找)、结果正确合并成一个rows列表。"""
    import fetch_data as fd_module

    call_log = []
    def fake_fetch_jsonp(url, headers=None, retries=3, timeout=20):
        call_log.append(url)
        if "TRADE_DATE%3D%272026-09-20%27" in url:
            # 模拟"今天"数据还没发布
            return {"success": True, "result": {"data": []}, "message": "ok"}, {"url": url}
        if "LPRANK" in url and "TRADE_DATE%3D%272026-09-19%27" in url:
            return {"success": True, "result": {"data": [
                {"MEMBER_NAME_ABBR": "国泰君安", "ORG_NAME_ABBR_NEW": "国泰君安", "LP_RANK": 1, "SP_RANK": 9999,
                 "VOLUME": 1000, "VOLUME_CHANGE": 10, "LONG_POSITION": 5000, "LP_CHANGE": 100, "SHORT_POSITION": None, "SP_CHANGE": None},
            ]}, "message": "ok"}, {"url": url}
        if "SPRANK" in url and "TRADE_DATE%3D%272026-09-19%27" in url:
            return {"success": True, "result": {"data": [
                {"MEMBER_NAME_ABBR": "中粮期货", "ORG_NAME_ABBR_NEW": "中粮期货", "LP_RANK": 9999, "SP_RANK": 1,
                 "VOLUME": 900, "VOLUME_CHANGE": 5, "LONG_POSITION": None, "LP_CHANGE": None, "SHORT_POSITION": 4000, "SP_CHANGE": -50},
            ]}, "message": "ok"}, {"url": url}
        return {"success": True, "result": {"data": []}, "message": "ok"}, {"url": url}

    old_fn = fd_module.fetch_jsonp_debug
    fd_module.fetch_jsonp_debug = fake_fetch_jsonp
    try:
        from datetime import datetime as real_datetime, timezone as real_timezone
        old_datetime = fd_module.datetime
        class FixedDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return real_datetime(2026, 9, 20, 12, 0, 0, tzinfo=real_timezone.utc)
        fd_module.datetime = FixedDatetime
        try:
            result = fd_module.fetch_dce_position_rank_multi(["M2701"], max_attempts=3)
        finally:
            fd_module.datetime = old_datetime

        assert result["M2701"]["available"] is True, "★应该往前找到9-19号的数据(9-20号模拟还没发布)"
        assert result["M2701"]["date"] == "2026-09-19"
        rows = result["M2701"]["rows"]
        assert len(rows) == 2, f"多头1条+空头1条应该合并成2条，实际{len(rows)}条"
        assert any(r["longPartyName"] == "国泰君安" for r in rows)
        assert any(r["shortPartyName"] == "中粮期货" for r in rows)
        assert "东方财富" in result["M2701"]["source"], "数据来源说明应该提到东方财富(不再是大商所官网直连)"
        print(f"✅ 完整集成测试通过：正确处理T+1重试(9-20无数据→往前找到9-19)，多头+空头数据正确合并")
    finally:
        fd_module.fetch_jsonp_debug = old_fn


def test_eastmoney_position_rank_complete_failure(monkeypatch_fetch):
    """★龙虎榜(东方财富版)：所有日期都拿不到数据时，应该诚实报告失败，不崩溃、不伪造数据。"""
    import fetch_data as fd_module

    def fake_fetch_jsonp_empty(url, headers=None, retries=3, timeout=20):
        return {"success": True, "result": {"data": []}, "message": "ok"}, {"url": url}

    old_fn = fd_module.fetch_jsonp_debug
    fd_module.fetch_jsonp_debug = fake_fetch_jsonp_empty
    try:
        result = fd_module.fetch_dce_position_rank_multi(["M2701"], max_attempts=2)
        assert result["M2701"]["available"] is False
        assert "M2701" in result["M2701"]["reason"]
        assert "debug" in result["M2701"] and len(result["M2701"]["debug"]["attempts"]) > 0
        print("✅ 所有日期都没数据时，诚实报告失败原因(不崩溃、不伪造数据)")
    finally:
        fd_module.fetch_jsonp_debug = old_fn


def test_dce_continuous_kline_parsing(monkeypatch_fetch):
    """验证连续合约(M0)解析：用于3年回测，字段结构应该跟具体合约的日K线类似。"""
    import pandas as pd
    import fetch_data as fd_module

    mock_df = pd.DataFrame({
        "date": [f"2023-{(i%12)+1:02d}-01" for i in range(700)],
        "open": [3300.0+i*0.1 for i in range(700)],
        "high": [3320.0+i*0.1 for i in range(700)],
        "low": [3280.0+i*0.1 for i in range(700)],
        "close": [3310.0+i*0.1 for i in range(700)],
        "volume": [100000.0+i for i in range(700)],
        "hold": [500000.0+i for i in range(700)],
    })
    import sys
    class FakeAkshare:
        @staticmethod
        def futures_main_sina(symbol, start_date):
            assert symbol == "M0", f"应该用M0(豆粕连续合约代码)，实际传了{symbol}"
            return mock_df
    sys.modules['akshare'] = FakeAkshare()
    try:
        result = fd_module.fetch_dce_continuous_kline("M0", years=3)
        assert result["available"] is True
        assert result["totalBarsReturned"] == 700
        assert "suspectedRolloverDates" in result, "应该带上疑似换月跳空日的诊断字段"
        print(f"✅ 连续合约解析正确：700根数据(平缓价格变化，无跳空)，正确识别symbol=M0")
    finally:
        del sys.modules['akshare']


def test_dce_continuous_kline_detects_rollover_jumps(monkeypatch_fetch):
    """★核心验证：连续合约是简单拼接、未做平滑处理，换月时可能出现价格跳空(不是真实波动)。
    这个测试构造一个明显的跳空(单日涨跌超过6%)，确认能被正确标记出来，供回测时排查。"""
    import pandas as pd
    import fetch_data as fd_module

    closes = [3300.0]*10 + [3300.0*1.08]*10  # 前10天平稳，第11天起永久性台阶上跳8%(模拟真实换月：新合约价格水平从此不同，不是临时尖峰又跌回去)
    mock_df = pd.DataFrame({
        "date": [f"2023-01-{i+1:02d}" for i in range(20)],
        "open": closes, "high": [c*1.01 for c in closes], "low": [c*0.99 for c in closes], "close": closes,
        "volume": [100000.0]*20, "hold": [500000.0]*20,
    })
    import sys
    class FakeAkshare:
        @staticmethod
        def futures_main_sina(symbol, start_date):
            return mock_df
    sys.modules['akshare'] = FakeAkshare()
    try:
        result = fd_module.fetch_dce_continuous_kline("M0", years=3)
        assert len(result["suspectedRolloverDates"]) == 1, f"应该恰好识别出1处疑似跳空，实际{result['suspectedRolloverDates']}"
        assert result["suspectedRolloverDates"][0]["date"] == "2023-01-11", "应该精确定位到跳空发生的那一天"
        assert result["suspectedRolloverDates"][0]["pctChange"] > 6.0, "涨跌幅记录应该准确"
        print(f"✅ 正确识别出疑似换月跳空日：{result['suspectedRolloverDates']}")
    finally:
        del sys.modules['akshare']


def test_dce_kline_missing_akshare_gives_clear_reason(monkeypatch_fetch):
    """如果akshare没装成功(比如GitHub Actions的pip install步骤失败)，
    应该给出清楚的原因说明，而不是笼统的ImportError堆栈。"""
    import sys
    import fetch_data as fd_module
    # 确保sys.modules里没有残留的假akshare
    if 'akshare' in sys.modules:
        del sys.modules['akshare']
    # 用一个会触发ImportError的方式：临时移除akshare(如果真装了的话不好模拟，
    # 这里改用检查函数内部try/except ImportError的路径是否存在)
    import inspect
    source = inspect.getsource(fd_module.fetch_dce_daily_kline)
    assert "ImportError" in source, "函数里应该有捕获ImportError的逻辑"
    assert "pip install akshare" in source, "错误信息里应该提示具体的修复方式"
    print("✅ 确认fetch_dce_daily_kline有ImportError兜底，且错误信息包含具体修复建议")


def make_monkeypatch():
    """一个简化的手动 monkeypatch 工具，替换 fetch_json / fetch_json_debug 让它们返回预设的模拟数据。"""
    def _patch(url_map):
        def fake_fetch_json(url, headers=None, retries=3, timeout=20):
            for key, val in url_map.items():
                if key in url:
                    return val
            return None
        def fake_fetch_json_debug(url, headers=None, retries=3, timeout=20):
            for key, val in url_map.items():
                if key in url:
                    return val, {"url": url, "note": "来自测试模拟数据"}
            return None, {"url": url, "note": "测试模拟数据里没有匹配的url"}
        fd.fetch_json = fake_fetch_json
        fd.fetch_json_debug = fake_fetch_json_debug
    return _patch


if __name__ == "__main__":
    monkeypatch_fetch = make_monkeypatch()
    tests = [test_contract_code_computation, test_main_fetches_all_three_contracts, test_dce_daily_kline_parsing, test_dce_hourly_kline_parsing,
              test_eastmoney_position_url_construction, test_eastmoney_position_row_parsing,
              test_eastmoney_position_jsonp_unwrap, test_eastmoney_position_rank_integration,
              test_eastmoney_position_rank_complete_failure,
              test_dce_continuous_kline_handles_chinese_column_names, test_dce_continuous_kline_debug_output_is_json_safe,
              test_dce_continuous_kline_parsing, test_dce_continuous_kline_detects_rollover_jumps,
              test_us_planting_progress_filters_out_annual_survey_data,
              test_dce_kline_missing_akshare_gives_clear_reason,
              test_us_harvest_progress_parsing_and_wow_change, test_us_harvest_progress_distinguishes_from_planting,
              test_us_planting_progress_parsing_and_wow_change, test_us_planting_progress_missing_api_key,
              test_us_planting_progress_field_mismatch_gives_diagnostic,
              test_south_america_weather_weighted_avg, test_south_america_psd_uses_soybean_not_meal_code,
              test_south_america_psd_handles_oilseed_soybean_naming,
              test_south_america_psd_exact_match_beats_decoy_commodity,
              test_south_america_psd_falls_back_when_exact_name_missing,
              test_south_america_psd_diagnostic_shows_soybean_entries_not_generic_alphabet,
              test_south_america_weather_handles_partial_failure,
              test_weighted_avg_large_producer_dominates_over_small_producer,
              test_weighted_avg_small_producer_drought_gets_diluted_appropriately,
              test_soybean_condition_parsing_and_wow_change, test_soybean_condition_missing_api_key,
              test_soybean_condition_field_mismatch_gives_diagnostic,
              test_noaa_outlook_url_uses_urlencode_no_raw_special_chars,
              test_noaa_outlook_percentage_aggregation_across_8_points,
              test_noaa_outlook_dominant_category_and_overall_signal,
              test_noaa_outlook_point_outside_any_outlook_zone,
              test_esr_code_lookup, test_esr_export_parsing, test_esr_picks_freshest_among_multiple_candidate_years,
              test_esr_code_lookup_distinguishes_failure_types,
              test_psd_code_lookup, test_psd_parsing,
              test_psd_fuzzy_matching, test_psd_debug_on_field_mismatch, test_drought_monitor_parsing,
              test_drought_uses_fips_code_not_postal_abbreviation, test_psd_real_world_attributeId_schema,
              test_psd_attribute_lookup_fails_gracefully, test_drought_area_to_percentage_conversion,
              test_drought_missing_none_field_fallback]
    failed = 0
    for t in tests:
        try:
            t(monkeypatch_fetch)
        except AssertionError as e:
            failed += 1
            print(f"❌ {t.__name__} 失败: {e}")
    print()
    if failed == 0:
        print(f"🎉 全部 {len(tests)} 项解析逻辑测试通过")
    else:
        print(f"⚠️ {failed}/{len(tests)} 项测试失败，请检查 fetch_data.py")
