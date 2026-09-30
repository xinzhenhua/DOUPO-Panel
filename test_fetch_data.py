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
from datetime import datetime, timezone, date
sys.path.insert(0, os.path.dirname(__file__))

import fetch_data as fd

# ★保存"真正原始"的fetch_json_debug引用——整个测试文件里很多测试函数会直接
#   给fd.fetch_json_debug赋值成各自的mock版本，且没有机制在测试结束后自动
#   恢复。绝大多数测试不关心这个（它们本来就是想替换掉网络请求那部分），
#   但少数像下面这样需要验证"fetch_json_debug函数本身的内部逻辑"的测试，
#   必须用这个模块加载时刻保存下来的引用，而不是fd.fetch_json_debug这个
#   随时可能已经被前面某个测试污染过的属性。
_REAL_FETCH_JSON_DEBUG = fd.fetch_json_debug

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


def _esr_row(week, country, net_cur=0, net_next=0, shipped=0):
    return {"weekEndingDate": week, "countryName": country, "currentMYNetSales": net_cur,
            "nextMYNetSales": net_next, "weeklyExports": shipped, "unitId": 1}


def test_esr_uses_soybeans_not_meal(monkeypatch_fetch):
    """★口径修正：ESR应该查大豆(Soybeans)，不是豆粕(Soybean Cake and Meal)。"""
    monkeypatch_fetch({"esr/commodities": MOCK_ESR_COMMODITIES})
    code, debug = fd.get_soybean_esr_code()
    assert code == 2222, f"应查到大豆编码2222，不是豆粕的2223，实际{code}"
    assert debug is None
    # 只有豆粕/豆油时不能退而求其次拿豆粕当大豆
    monkeypatch_fetch({"esr/commodities": [{"commodityCode": 2223, "commodityName": "Soybean Cake and Meal"},
                                           {"commodityCode": 2224, "commodityName": "Soybean Oil"}]})
    code2, debug2 = fd.get_soybean_esr_code()
    assert code2 is None and "没有一条是" in debug2["failureStage"]
    print("✅ ESR商品编码：查大豆(2222)，只有豆粕/豆油时不会误用")


def test_esr_export_parsing(monkeypatch_fetch):
    """★净销售=currentMYNetSales+nextMYNetSales；装船量(weeklyExports)单独放，绝不混进净销售。
    6周数据：净销售依次为100000×4周、150000(上周)、300000(最新周)。
    最新周之前的4周=[100000,100000,100000,150000]，均值112500，最新周相对均值+166.7%。"""
    rows = []
    for w in ["2026-05-28", "2026-06-04", "2026-06-11", "2026-06-18"]:
        rows.append(_esr_row(w, "China", 60000, 0, 999))   # 装船量故意写成999，验证不会被当净销售
        rows.append(_esr_row(w, "Mexico", 40000, 0, 999))
    rows.append(_esr_row("2026-06-25", "China", 100000, 0, 999))
    rows.append(_esr_row("2026-06-25", "Mexico", 30000, 20000, 999))     # 净销售=当年30000+下一年20000
    rows.append(_esr_row("2026-07-02", "China", 250000, 10000, 5))
    rows.append(_esr_row("2026-07-02", "Mexico", 40000, 0, 5))
    monkeypatch_fetch({"esr/commodities": MOCK_ESR_COMMODITIES, "esr/exports": rows})
    result = fd.fetch_esr_export_sales()
    assert result["available"] is True
    assert result["netSalesMT"] == 300000, f"最新周净销售应=250000+10000+40000=300000，实际{result['netSalesMT']}"
    assert result["prevNetSalesMT"] == 150000, f"上周应=100000+30000+20000=150000，实际{result['prevNetSalesMT']}"
    assert result["shipmentsMT"] == 10, "装船量应单独统计(5+5)，不能混进净销售"
    assert result["avg4wNetSalesMT"] == 112500, f"最新周之前4周均值应=112500，实际{result['avg4wNetSalesMT']}"
    assert result["vs4wAvgPct"] == round((300000 - 112500) / 112500 * 100, 1) == 166.7, f"实际{result['vs4wAvgPct']}"
    assert result["wowChangePct"] == 100.0
    assert result["chinaNetSalesMT"] == 260000
    assert "latestTotalMT" not in result, "旧字段名(会让人误以为是净销售)不应再出现"
    assert len(result["recentWeeks"]) == 6
    print("✅ ESR：净销售=当年+下一年净销售，装船量分开，4周均值基准正确")


def test_esr_no_silent_fallback_to_shipments(monkeypatch_fetch):
    """★接口只返回装船量、没有净销售字段时，必须明确报不可用，不能退回用装船量冒充净销售
    (旧版本正是这样把装船量标成'净销售'的)。"""
    rows = [{"weekEndingDate": "2026-06-25", "countryName": "China", "weeklyExports": 90000},
            {"weekEndingDate": "2026-07-02", "countryName": "China", "weeklyExports": 110000}]
    monkeypatch_fetch({"esr/commodities": MOCK_ESR_COMMODITIES, "esr/exports": rows})
    result = fd.fetch_esr_export_sales()
    assert result["available"] is False
    assert "净销售字段" in result["reason"]
    assert "actualFieldsSeen" in result["debug"]
    print("✅ 没有净销售字段时明确报不可用，不会拿装船量冒充")


def test_esr_market_year_boundary_merges_weeks_without_double_count(monkeypatch_fetch):
    """9月初市场年度切换：同一周不能被两个年度重复计入；切换周(9/3在8/31~9/6内)用相邻两周均值代替(见rollover测试)。
    周次：08-13/08-20/08-27=100000，09-03(切换周，原始100000)，09-10=300000(最新)。
    调整后09-03=(08-27的100000+09-10的300000)/2=200000；最新周之前4周=[08-13,08-20,08-27,09-03]，均值125000。"""
    old_year = [_esr_row("2026-08-13", "China", 100000), _esr_row("2026-08-20", "China", 100000),
                _esr_row("2026-08-27", "China", 100000)]
    new_year = [_esr_row("2026-09-03", "China", 100000), _esr_row("2026-09-10", "China", 300000),
                _esr_row("2026-08-27", "China", 100000)]   # 交界周两个年度都有：只应计一次
    def fake_debug(url, headers=None, retries=3, timeout=20, post_data=None):
        if "esr/commodities" in url: return MOCK_ESR_COMMODITIES, {}
        if "marketYear/2025" in url: return old_year, {"httpStatus": 200}
        if "marketYear/2026" in url: return new_year, {"httpStatus": 200}
        return None, {}
    fd.fetch_json_debug = fake_debug
    result = fd.fetch_esr_export_sales()
    assert result["available"] is True
    assert result["weekEnding"] == "2026-09-10" and result["marketYearUsed"] == 2026
    assert result["avg4wNetSalesMT"] == 125000, f"交界周只算一次+切换周被均值代替后，4周均值应=125000，实际{result['avg4wNetSalesMT']}"
    assert result["vs4wAvgPct"] == 140.0
    print("✅ 市场年度交界：上一年度最后几周并入4周均值，交界周不重复计")


def test_esr_rollover_week_is_replaced_by_neighbor_average(monkeypatch_fetch):
    """★12年历史里每年市场年度切换周(8/31~9/6)都是尖峰(推断：新年度第一周带入了上年度已报过的下年度销售)。
    切换周用相邻两周均值代替，避免把结转的销售重复算一次。"""
    rows = []
    for w, v in [("2026-08-13", 100000), ("2026-08-20", 100000), ("2026-08-27", 100000), ("2026-09-03", 900000),   # 09-03是切换周，虚高
                 ("2026-09-10", 100000), ("2026-09-17", 100000)]:
        rows += [_esr_row(w, "CHINA", v // 2), _esr_row(w, "JAPAN", v // 2)]
    monkeypatch_fetch({"esr/commodities": MOCK_ESR_COMMODITIES, "esr/exports": rows})
    r = fd.fetch_esr_export_sales()
    assert r["rolloverAdjustedWeeks"] == ["2026-09-03"] and r["latestIsRollover"] is False
    assert r["prevNetSalesMT"] == 100000, "上周(09-10)不是切换周，不变"
    # 09-03被(08-27:100000 + 09-10:100000)/2=100000代替：近4周(08-27,09-03,09-10,09-17)合计=400000，不是1,200,000
    assert r["total4wSumMT"] == 400000, r["total4wSumMT"]
    assert r["avg4wNetSalesMT"] == 100000 and r["vs4wAvgPct"] == 0.0
    assert r["chinaNetSalesMT"] == 50000 and r["china4wSumMT"] == 200000, "中国/未知/其他同样用相邻周代替"
    print("✅ ESR：市场年度切换周用相邻两周均值代替，不再虚高")


def test_esr_latest_week_is_rollover_blocks_comparisons(monkeypatch_fetch):
    """最新一周本身就是切换周(周五刚发布时正是9月初)：下一周还没出，没法代替，含结转的数字不能拿来比 → 一律给None。"""
    rows = []
    for w, v in [("2026-08-13", 100000), ("2026-08-20", 100000), ("2026-08-27", 100000), ("2026-09-03", 900000)]:
        rows += [_esr_row(w, "CHINA", v)]
    monkeypatch_fetch({"esr/commodities": MOCK_ESR_COMMODITIES, "esr/exports": rows})
    r = fd.fetch_esr_export_sales()
    assert r["available"] is True and r["latestIsRollover"] is True and r["rolloverAdjustedWeeks"] == []
    assert r["netSalesMT"] == 900000, "原始数字照常展示(标注为切换周)"
    assert r["vs4wAvgPct"] is None and r["wowChangePct"] is None and r["total4wSumMT"] is None and r["china4wSumMT"] is None and r["chinaShare4wPct"] is None
    print("✅ ESR：最新周是切换周时不给4周合计/相对均值/环比")


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
        _esr_row("2025-09-25", "China", 50000),
        _esr_row("2025-10-02", "China", 60000),
    ]
    current_active_year_data = [
        _esr_row("2026-06-25", "China", 90000),
        _esr_row("2026-07-02", "China", 110000),
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


def test_soybean_condition_yoy_and_five_year_avg_full_integration(monkeypatch_fetch):
    """★用户明确要求的功能：美豆优良率不能只看环比，要能看出"今年这个水平算不算异常"。
    用真正按年份区分的mock(根据URL里的year=参数返回不同数据)，完整验证从
    fetch_soybean_condition()到同比/五年均值的端到端链路——不是只测试内部计算函数，
    是测试真实调用路径下year参数有没有被正确传递、多次请求有没有被正确拼起来。"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = "test-key"

    # 模拟：2026年最新一周58%，去年同期61%，2024年65%，2023年60%，2022年缺失(查不到)，2021年64%
    yearly_data = {
        "2026": [
            {"week_ending": "2026-09-13", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT EXCELLENT", "Value": "8"},
            {"week_ending": "2026-09-13", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT GOOD", "Value": "52"},
            {"week_ending": "2026-09-20", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT EXCELLENT", "Value": "8"},
            {"week_ending": "2026-09-20", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT GOOD", "Value": "50"},  # 合计58
        ],
        "2025": [
            {"week_ending": "2025-09-21", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT EXCELLENT", "Value": "11"},
            {"week_ending": "2025-09-21", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT GOOD", "Value": "50"},  # 合计61
        ],
        "2024": [
            {"week_ending": "2024-09-15", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT EXCELLENT", "Value": "15"},
            {"week_ending": "2024-09-15", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT GOOD", "Value": "50"},  # 合计65
        ],
        "2023": [
            {"week_ending": "2023-09-17", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT EXCELLENT", "Value": "10"},
            {"week_ending": "2023-09-17", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT GOOD", "Value": "50"},  # 合计60
        ],
        "2022": [],  # 模拟这一年查不到数据(真实世界里可能是接口临时失败)
        "2021": [
            {"week_ending": "2021-09-19", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT EXCELLENT", "Value": "14"},
            {"week_ending": "2021-09-19", "short_desc": "SOYBEANS - CONDITION, MEASURED IN PCT GOOD", "Value": "50"},  # 合计64
        ],
    }
    call_log = []
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        call_log.append(url)
        import re
        m = re.search(r"year=(\d{4})", url)
        year = m.group(1) if m else None
        rows = yearly_data.get(year, [])
        if not rows:
            return None, {"error": "该年份无数据(模拟)"}
        return {"data": rows}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch

    try:
        result = fd.fetch_soybean_condition()
        assert result["available"] is True
        assert result["goodExcellentPct"] == 58.0, f"8+50=58，实际{result['goodExcellentPct']}"
        assert len(call_log) == 6, f"应该发起6次请求(今年+往前5年)，实际{len(call_log)}次"
        assert result["yoyValue"] == 61.0, f"★去年同期应该是61(2025-09-21那一周)，实际{result['yoyValue']}"
        assert result["yoyChangePts"] == -3.0, f"★同比变化应该是58-61=-3，实际{result['yoyChangePts']}"
        assert result["fiveYearAvg"] == 62.5, f"★五年均值应该是(61+65+60+64)/4=62.5(2022年缺失不计入分母)，实际{result['fiveYearAvg']}"
        assert result["fiveYearAvgChangePts"] == -4.5, f"★五年均值对比应该是58-62.5=-4.5，实际{result['fiveYearAvgChangePts']}"
        print(f"✅ 端到端验证：优良率58% vs 去年同期61%(-3) vs 五年均值62.5%(-4.5)，2022年缺失正确排除在均值分母外")
        print(f"   完整输出: yoyValue={result['yoyValue']}, fiveYearAvg={result['fiveYearAvg']}")
    finally:
        fd.NASS_API_KEY = old_key


def test_us_harvest_progress_yoy_and_five_year_avg(monkeypatch_fetch):
    """收获进度同样要验证同比/五年均值——跟优良率共用同一套_compute_yoy_and_five_year_avg，
    但取值逻辑不同(单一PCT HARVESTED字段，不是两个字段相加)，要单独验证一次不是简单复制粘贴对了。"""
    old_key = fd.NASS_API_KEY
    fd.NASS_API_KEY = "test-key"
    yearly_data = {
        "2026": [{"week_ending": "2026-09-20", "short_desc": "SOYBEANS - PROGRESS, MEASURED IN PCT HARVESTED", "Value": "12"}],
        "2025": [{"week_ending": "2025-09-21", "short_desc": "SOYBEANS - PROGRESS, MEASURED IN PCT HARVESTED", "Value": "8"}],
        "2024": [{"week_ending": "2024-09-15", "short_desc": "SOYBEANS - PROGRESS, MEASURED IN PCT HARVESTED", "Value": "10"}],
        "2023": [],
        "2022": [],
        "2021": [],
    }
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        import re
        m = re.search(r"year=(\d{4})", url)
        rows = yearly_data.get(m.group(1) if m else None, [])
        return ({"data": rows}, {"httpStatus": 200}) if rows else (None, {"error": "无数据"})
    fd.fetch_json_debug = fake_fetch
    try:
        result = fd.fetch_us_harvest_progress()
        assert result["available"] is True
        assert result["pctHarvested"] == 12.0
        assert result["yoyValue"] == 8.0, f"★去年同期收获率应该是8，实际{result['yoyValue']}"
        assert result["yoyChangePts"] == 4.0, f"★同比变化应该是12-8=+4，实际{result['yoyChangePts']}"
        assert result["fiveYearAvg"] == 9.0, f"★五年均值应该是(8+10)/2=9(只有2年有数据)，实际{result['fiveYearAvg']}"
        print(f"✅ 收获进度同比/五年均值验证正确：12% vs 去年同期8%(+4) vs 均值9%(+3)")
    finally:
        fd.NASS_API_KEY = old_key


def test_cftc_managed_money_parsing(monkeypatch_fetch):
    """★用户明确要求：CFTC持仓报告是美国版龙虎榜，Managed Money(基金/投机资金)
    这一类最接近"外资/资金动向"这个概念。用实测抓包确认过的真实字段结构模拟
    (数据集72hh-3qpy，字段名m_money_positions_long_all等)，验证解析逻辑正确。"""
    mock_response = [{
        "market_and_exchange_names": "SOYBEAN MEAL - CHICAGO BOARD OF TRADE",
        "report_date_as_yyyy_mm_dd": "2026-09-16T00:00:00.000",
        "m_money_positions_long_all": "115467",
        "m_money_positions_short_all": "37899",
        "change_in_m_money_long_all": "6950",
        "change_in_m_money_short_all": "-11514",
    }]
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        assert "72hh-3qpy" in url, "★应该请求Disaggregated数据集(72hh-3qpy)，不是Legacy"
        assert "m_money" not in url or "$where" in url, "确认请求带了筛选条件"
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch

    result = fd.fetch_cftc_managed_money()
    assert result["available"] is True
    assert result["reportDate"] == "2026-09-16"
    assert result["longPositions"] == 115467
    assert result["shortPositions"] == 37899
    assert result["netPosition"] == 115467 - 37899, f"净多头应该是多单减空单，实际{result['netPosition']}"
    assert result["longChange"] == 6950
    assert result["shortChange"] == -11514
    assert result["netChange"] == 6950 - (-11514), f"净变化应该是多单变化减空单变化，实际{result['netChange']}"
    print(f"✅ CFTC Managed Money解析正确：净多头{result['netPosition']}手，净变化{result['netChange']}手")


def test_cftc_managed_money_no_data_found(monkeypatch_fetch):
    """如果查询的市场名称在CFTC那边找不到匹配记录(比如命名细微差异)，应该诚实报告，不崩溃"""
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return [], {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_cftc_managed_money()
    assert result["available"] is False
    assert "SOYBEAN MEAL" in result["reason"]
    print("✅ 查不到匹配市场名称时诚实报告原因，不崩溃")


def test_cftc_managed_money_field_mismatch_gives_diagnostic(monkeypatch_fetch):
    """如果CFTC改了字段名，应该给出诊断信息(实际有哪些字段)，而不是静默失败"""
    mock_response = [{"market_and_exchange_names": "SOYBEAN MEAL - CHICAGO BOARD OF TRADE", "some_other_field": "123"}]
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_cftc_managed_money()
    assert result["available"] is False
    assert "debug" in result and "actualKeysSeen" in result["debug"]
    print("✅ 字段名对不上时给出诊断信息(实际有哪些字段)，而不是静默失败")


def test_cftc_streak_weeks_consecutive_increase(monkeypatch_fetch):
    """★用户明确要求：净多头"持续增加"要能看出来，不是只看这周涨跌。
    用手算验证过的例子(100→90→80→60→70，从新到旧)验证连续上升3周被正确识别，
    第4周(60比70低，打破了上升趋势)之后不再往前累加。"""
    def make_row(date, long_pos, short_pos, is_latest=False):
        row = {
            "market_and_exchange_names": "SOYBEAN MEAL - CHICAGO BOARD OF TRADE",
            "report_date_as_yyyy_mm_dd": date,
            "m_money_positions_long_all": str(long_pos), "m_money_positions_short_all": str(short_pos),
        }
        if is_latest:
            row["change_in_m_money_long_all"] = "5000"
            row["change_in_m_money_short_all"] = "-5000"
        return row
    # 净持仓(long-short)序列：100(最新), 90, 80, 60, 70(最旧)——净多头连续3周上升后，第4周才打破
    mock_response = [
        make_row("2026-09-16", 150, 50, is_latest=True),  # net=100
        make_row("2026-09-09", 140, 50),                   # net=90
        make_row("2026-09-02", 130, 50),                   # net=80
        make_row("2026-08-26", 110, 50),                   # net=60
        make_row("2026-08-19", 120, 50),                   # net=70
    ]
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_cftc_managed_money()
    assert result["available"] is True
    assert result["streakWeeks"] == 3, f"★应该识别出连续3周上升，实际{result['streakWeeks']}"
    assert result["streakDirection"] == "up", f"★方向应该是up，实际{result['streakDirection']}"
    print(f"✅ 连续上升周数正确识别：{result['streakWeeks']}周(手算验证过)")


def test_cftc_streak_weeks_consecutive_decrease(monkeypatch_fetch):
    """反过来验证连续下降的情况，确认不是只认得上升方向"""
    def make_row(date, long_pos, short_pos, is_latest=False):
        row = {
            "market_and_exchange_names": "SOYBEAN MEAL - CHICAGO BOARD OF TRADE",
            "report_date_as_yyyy_mm_dd": date,
            "m_money_positions_long_all": str(long_pos), "m_money_positions_short_all": str(short_pos),
        }
        if is_latest:
            row["change_in_m_money_long_all"] = "-3000"
            row["change_in_m_money_short_all"] = "2000"
        return row
    # 净持仓序列：50(最新), 70, 90(最旧)——连续2周下降
    mock_response = [
        make_row("2026-09-16", 100, 50, is_latest=True),  # net=50
        make_row("2026-09-09", 120, 50),                   # net=70
        make_row("2026-09-02", 140, 50),                   # net=90
    ]
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_cftc_managed_money()
    assert result["streakWeeks"] == 2, f"★应该识别出连续2周下降，实际{result['streakWeeks']}"
    assert result["streakDirection"] == "down"
    print(f"✅ 连续下降周数正确识别：{result['streakWeeks']}周")


def test_cftc_history_percentile_calculation(monkeypatch_fetch):
    """★用户明确要求：净多头"处于历史高位"要能看出来。用构造的60周数据
    (刚好超过52周门槛)验证百分位计算——当前值是历史最高，百分位应该是100。"""
    rows = []
    # 构造60周数据：最新一周net=1000(全场最高)，其余59周net从100到990递增(但都比1000低)
    for i in range(60):
        date = f"2025-{(i%12)+1:02d}-01"
        if i == 0:
            rows.append({
                "market_and_exchange_names": "SOYBEAN MEAL - CHICAGO BOARD OF TRADE",
                "report_date_as_yyyy_mm_dd": "2026-09-16", "m_money_positions_long_all": "1000", "m_money_positions_short_all": "0",
                "change_in_m_money_long_all": "100", "change_in_m_money_short_all": "0",
            })
        else:
            rows.append({
                "market_and_exchange_names": "SOYBEAN MEAL - CHICAGO BOARD OF TRADE",
                "report_date_as_yyyy_mm_dd": date, "m_money_positions_long_all": str(500+i), "m_money_positions_short_all": "0",
            })
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return rows, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_cftc_managed_money()
    assert result["available"] is True
    assert result["historyWeeksUsed"] == 60
    assert result["historyPercentile"] == 100.0, f"★当前值是历史最高，百分位应该是100，实际{result['historyPercentile']}"
    print(f"✅ 历史百分位计算正确：当前净持仓处于回看窗口的第{result['historyPercentile']}百分位")


def test_cftc_history_percentile_none_when_insufficient_data(monkeypatch_fetch):
    """★历史数据不够52周时，historyPercentile应该是None，不能硬凑一个没有统计意义的百分位"""
    mock_response = [{
        "market_and_exchange_names": "SOYBEAN MEAL - CHICAGO BOARD OF TRADE",
        "report_date_as_yyyy_mm_dd": "2026-09-16", "m_money_positions_long_all": "100", "m_money_positions_short_all": "50",
        "change_in_m_money_long_all": "10", "change_in_m_money_short_all": "5",
    }]  # 只有1周数据
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_cftc_managed_money()
    assert result["historyPercentile"] is None, "★历史数据不足52周时，不应该硬算一个百分位出来"
    print("✅ 历史数据不足52周时，正确返回None而不是硬凑一个没有统计意义的百分位")


def test_get_current_contract_code_prefix_param(monkeypatch_fetch):
    """★验证get_current_contract_code新增的prefix参数：压榨利润要复用这个函数
    算豆油(Y)/豆二(B)的合约代码，不能破坏原本豆粕(M)的默认行为。"""
    from datetime import datetime as real_datetime, timezone as real_timezone
    now = real_datetime(2026, 7, 12, tzinfo=real_timezone.utc)
    assert fd.get_current_contract_code(9, now) == "M2609", "不传prefix应该保持默认M，不能破坏现有调用方"
    assert fd.get_current_contract_code(9, now, prefix="Y") == "Y2609", "★传Y应该算出豆油合约代码"
    assert fd.get_current_contract_code(9, now, prefix="B") == "B2609", "★传B应该算出豆二合约代码"
    print("✅ get_current_contract_code的prefix参数正确：默认M不受影响，Y/B也能正确生成")


def test_crush_margin_calculation(monkeypatch_fetch):
    """★用户明确要求：压榨利润=豆粕价格×出粕率+豆油价格×出油率-大豆价格。
    用手算验证过的例子(3400×0.785+8500×0.185-4200=41.5)验证代入公式的结果正确。"""
    old_daily = fd.fetch_dce_daily_kline
    def fake_daily(symbol, max_rows=260):
        prices = {"M2609": 3400, "Y2609": 8500, "B2609": 4200}
        if symbol not in prices:
            return {"available": False, "reason": "测试里没配置这个合约"}
        return {"available": True, "symbol": symbol, "bars": [{"close": prices[symbol]}], "source": "测试"}
    fd.fetch_dce_daily_kline = fake_daily
    try:
        from datetime import datetime as real_datetime, timezone as real_timezone
        now = real_datetime(2026, 7, 12, tzinfo=real_timezone.utc)
        result = fd.fetch_crush_margin(9, now)
        assert result["available"] is True
        assert result["mealPrice"] == 3400 and result["oilPrice"] == 8500 and result["beanPrice"] == 4200
        assert result["grossMargin"] == 41.5, f"★手算验证值应该是41.5，实际{result['grossMargin']}"
        assert result["yieldMeal"] == 0.785 and result["yieldOil"] == 0.185, "★系数应该是DCE官方交割置换标准(78.5%/18.5%)"
        print(f"✅ 压榨利润计算正确：{result['grossMargin']}元/吨(手算验证过)")
    finally:
        fd.fetch_dce_daily_kline = old_daily


def test_crush_margin_missing_one_contract_reports_all_missing(monkeypatch_fetch):
    """★三个合约价格有一个缺失就应该整体标记不可用，不能用0硬凑一个看似正常的数字。
    还要验证：缺失原因里应该点名到底是哪个合约缺(不是笼统一句"数据不足")。"""
    old_daily = fd.fetch_dce_daily_kline
    def fake_daily(symbol, max_rows=260):
        if symbol == "Y2609":
            return {"available": False, "reason": "接口调用失败"}
        prices = {"M2609": 3400, "B2609": 4200}
        return {"available": True, "symbol": symbol, "bars": [{"close": prices[symbol]}], "source": "测试"}
    fd.fetch_dce_daily_kline = fake_daily
    try:
        from datetime import datetime as real_datetime, timezone as real_timezone
        now = real_datetime(2026, 7, 12, tzinfo=real_timezone.utc)
        result = fd.fetch_crush_margin(9, now)
        assert result["available"] is False
        assert "豆油" in result["reason"] and "Y2609" in result["reason"], "★缺失原因应该点名是豆油缺失，不是笼统报告"
        assert "豆粕" not in result["reason"] or "M2609" not in result["reason"].split("豆油")[0], "不应该错误地把正常的豆粕也报成缺失"
        print("✅ 三个合约中有一个缺失时，整体标记不可用且准确点名是哪个合约缺失")
    finally:
        fd.fetch_dce_daily_kline = old_daily


def test_crush_margin_all_three_missing_lists_all(monkeypatch_fetch):
    """三个合约全部缺失时，reason里应该把三个都列出来，不是只报第一个就停"""
    old_daily = fd.fetch_dce_daily_kline
    def fake_daily(symbol, max_rows=260):
        return {"available": False, "reason": "全部没有"}
    fd.fetch_dce_daily_kline = fake_daily
    try:
        result = fd.fetch_crush_margin(9)
        assert result["available"] is False
        assert "豆粕" in result["reason"] and "豆油" in result["reason"] and "豆二" in result["reason"]
        print("✅ 三个合约全部缺失时，三个都被列在错误信息里，不是只报第一个")
    finally:
        fd.fetch_dce_daily_kline = old_daily


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
    def fake_position_rank(symbols, max_attempts=6, categories=None):
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

        # ★压榨利润功能上线后，fetch_dce_daily_kline还会被拿去查豆油(Y)/豆二(B)合约价格，
        #   daily_calls不再是"只有这3个M合约"了，改成检查这3个M合约都在里面(子集关系)，
        #   而不是要求完全相等——压榨利润那部分自己有专门的测试覆盖，这里不重复断言。
        assert expected_codes.issubset(set(daily_calls)), f"main()至少应该对这3个日线合约代码发起请求: {expected_codes}，实际请求了: {daily_calls}"
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
    (无排名)要被过滤掉、用干净的会员名(不带"代客"后缀)、统一的rank/name/value/change
    字段结构对多个类别都适用。"""
    import fetch_data as fd_module

    raw_rows = [
        {"MEMBER_NAME_ABBR": "国泰君安（代客）", "ORG_NAME_ABBR_NEW": "国泰君安",
         "LP_RANK": 1, "SP_RANK": 4, "NLP_RANK": 3, "NSP_RANK": 9999, "LP_UP_RANK": 26, "LP_DOWN_RANK": 7,
         "LONG_POSITION": 282361, "LP_CHANGE": -6712, "SHORT_POSITION": 148453, "SP_CHANGE": 1450,
         "NET_LONG_POSITION": 133908, "NLP_CHANGE": -8162, "NET_SHORT_POSITION": None, "NSP_CHANGE": None},
        {"MEMBER_NAME_ABBR": "中粮期货（代客）", "ORG_NAME_ABBR_NEW": "中粮期货",
         "LP_RANK": 12, "SP_RANK": 1, "NLP_RANK": 9999, "NSP_RANK": 1, "LP_UP_RANK": 2, "LP_DOWN_RANK": 31,
         "LONG_POSITION": 56303, "LP_CHANGE": 6780, "SHORT_POSITION": 591686, "SP_CHANGE": -34650,
         "NET_LONG_POSITION": None, "NLP_CHANGE": None, "NET_SHORT_POSITION": 535383, "NSP_CHANGE": -41430},
        {"MEMBER_NAME_ABBR": "国联期货（代客）", "ORG_NAME_ABBR_NEW": "国联期货",
         "LP_RANK": 9999, "SP_RANK": 9999, "NLP_RANK": 9999, "NSP_RANK": 9999, "LP_UP_RANK": 9999, "LP_DOWN_RANK": 9999,
         "LONG_POSITION": None, "LP_CHANGE": None, "SHORT_POSITION": None, "SP_CHANGE": None,
         "NET_LONG_POSITION": None, "NLP_CHANGE": None, "NET_SHORT_POSITION": None, "NSP_CHANGE": None},
    ]

    long_rows = fd_module._parse_eastmoney_position_rows(raw_rows, "long")
    assert len(long_rows) == 2, f"LP_RANK=9999(国联期货)应该被过滤掉，剩2条，实际{len(long_rows)}条"
    assert long_rows[0]["rank"] == 1 and long_rows[0]["name"] == "国泰君安"
    assert long_rows[0]["value"] == 282361 and long_rows[0]["change"] == -6712
    assert "代客" not in long_rows[0]["name"], "应该用ORG_NAME_ABBR_NEW干净名字，不带'代客'后缀"

    short_rows = fd_module._parse_eastmoney_position_rows(raw_rows, "short")
    assert short_rows[0]["rank"] == 1 and short_rows[0]["name"] == "中粮期货", "★应该按SP_RANK排序，中粮期货(SP_RANK=1)排第一"
    assert short_rows[0]["value"] == 591686

    net_long_rows = fd_module._parse_eastmoney_position_rows(raw_rows, "netLong")
    assert len(net_long_rows) == 1 and net_long_rows[0]["name"] == "国泰君安", "★净多头：只有国泰君安有NLP_RANK(3)，中粮期货NLP_RANK=9999应该被过滤"
    assert net_long_rows[0]["value"] == 133908

    net_short_rows = fd_module._parse_eastmoney_position_rows(raw_rows, "netShort")
    assert len(net_short_rows) == 1 and net_short_rows[0]["name"] == "中粮期货" and net_short_rows[0]["value"] == 535383

    long_up_rows = fd_module._parse_eastmoney_position_rows(raw_rows, "longUp")
    assert long_up_rows[0]["name"] == "中粮期货", "★多头增仓：中粮期货LP_UP_RANK=2排第一(比国泰君安的26靠前)"

    long_down_rows = fd_module._parse_eastmoney_position_rows(raw_rows, "longDown")
    assert long_down_rows[0]["name"] == "国泰君安", "★多头减仓：国泰君安LP_DOWN_RANK=7排第一(比中粮期货的31靠前)"

    print("✅ 用真实响应数据验证：6个类别(多头/空头/净多头/净空头/多头增仓/多头减仓)解析全部正确，9999哨兵值被过滤")


def test_foreign_futures_firm_detection(monkeypatch_fetch):
    """★外资标注：验证4家已确认的境内外资独资期货公司能被正确识别，且是包含匹配
    (能兼容"(代客)"这类后缀，或"高盛期货(深圳)"这种更完整的写法)，国内期货公司
    不应该被误判成外资。"""
    import fetch_data as fd_module

    assert fd_module._is_foreign_futures_firm("高盛期货") is True
    assert fd_module._is_foreign_futures_firm("高盛期货（深圳）有限公司") is True, "★应该是包含匹配，兼容更完整的公司全称"
    assert fd_module._is_foreign_futures_firm("高盛期货（代客）") is True, "★应该能兼容'(代客)'后缀"
    assert fd_module._is_foreign_futures_firm("摩根大通期货") is True
    assert fd_module._is_foreign_futures_firm("摩根士丹利期货") is True
    assert fd_module._is_foreign_futures_firm("瑞银期货") is True
    assert fd_module._is_foreign_futures_firm("中信期货") is False, "★国内期货公司不应该被误判成外资"
    assert fd_module._is_foreign_futures_firm("国泰君安") is False

    # 解析流程里也要验证isForeign字段确实被正确设置
    raw_rows = [
        {"MEMBER_NAME_ABBR": "高盛期货（代客）", "ORG_NAME_ABBR_NEW": "高盛期货", "LP_RANK": 5, "LONG_POSITION": 1000, "LP_CHANGE": 50},
        {"MEMBER_NAME_ABBR": "中信期货（代客）", "ORG_NAME_ABBR_NEW": "中信期货", "LP_RANK": 1, "LONG_POSITION": 5000, "LP_CHANGE": 100},
    ]
    parsed = fd_module._parse_eastmoney_position_rows(raw_rows, "long")
    goldman_row = next(r for r in parsed if r["name"] == "高盛期货")
    citic_row = next(r for r in parsed if r["name"] == "中信期货")
    assert goldman_row["isForeign"] is True, "★高盛期货这一行应该被标注isForeign=true"
    assert citic_row["isForeign"] is False, "★中信期货不应该被标注为外资"
    print("✅ 外资独资期货公司(高盛/摩根大通/摩根士丹利/瑞银)识别正确，国内公司不会被误判，isForeign字段正确写入解析结果")


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
    fetch_dce_position_rank_multi()对指定的类别(净多头/净空头/多头增仓/多头减仓)
    正确发起请求、正确处理T+1重试(模拟"今天"数据还没发布，要往前找)、
    结果正确组织成tables字典结构(不是扁平的rows列表)。"""
    import fetch_data as fd_module

    def fake_fetch_jsonp(url, headers=None, retries=3, timeout=20):
        if "TRADE_DATE%3D%272026-09-20%27" in url:
            # 模拟"今天"数据还没发布
            return {"success": True, "result": {"data": []}, "message": "ok"}, {"url": url}
        if "TRADE_DATE%3D%272026-09-19%27" in url:
            if "NLPRANK" in url:
                return {"success": True, "result": {"data": [
                    {"MEMBER_NAME_ABBR": "国泰君安", "ORG_NAME_ABBR_NEW": "国泰君安", "NLP_RANK": 1, "NET_LONG_POSITION": 5000, "NLP_CHANGE": 100},
                ]}, "message": "ok"}, {"url": url}
            if "NSPRANK" in url:
                return {"success": True, "result": {"data": [
                    {"MEMBER_NAME_ABBR": "高盛期货", "ORG_NAME_ABBR_NEW": "高盛期货", "NSP_RANK": 1, "NET_SHORT_POSITION": 4000, "NSP_CHANGE": -50},
                ]}, "message": "ok"}, {"url": url}
            if "LPUPRANK" in url:
                return {"success": True, "result": {"data": [
                    {"MEMBER_NAME_ABBR": "中粮期货", "ORG_NAME_ABBR_NEW": "中粮期货", "LP_UP_RANK": 1, "LONG_POSITION": 3000, "LP_CHANGE": 200},
                ]}, "message": "ok"}, {"url": url}
            if "LPDOWNRANK" in url:
                return {"success": True, "result": {"data": [
                    {"MEMBER_NAME_ABBR": "中信期货", "ORG_NAME_ABBR_NEW": "中信期货", "LP_DOWN_RANK": 1, "LONG_POSITION": 2000, "LP_CHANGE": -150},
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
            result = fd_module.fetch_dce_position_rank_multi(["M2701"], max_attempts=3, categories=["netLong", "netShort", "longUp", "longDown"])
        finally:
            fd_module.datetime = old_datetime

        assert result["M2701"]["available"] is True, "★应该往前找到9-19号的数据(9-20号模拟还没发布)"
        assert result["M2701"]["date"] == "2026-09-19"
        tables = result["M2701"]["tables"]
        assert set(tables.keys()) == {"netLong", "netShort", "longUp", "longDown"}, f"★应该只包含请求的4个类别，实际: {list(tables.keys())}"
        assert tables["netLong"][0]["name"] == "国泰君安"
        assert tables["netShort"][0]["name"] == "高盛期货" and tables["netShort"][0]["isForeign"] is True, "★净空头榜里的高盛期货应该被标注isForeign=true"
        assert tables["longUp"][0]["name"] == "中粮期货"
        assert tables["longDown"][0]["name"] == "中信期货"
        assert "东方财富" in result["M2701"]["source"], "数据来源说明应该提到东方财富(不再是大商所官网直连)"
        print(f"✅ 完整集成测试通过：正确处理T+1重试(9-20无数据→往前找到9-19)，4个指定类别正确组织成tables字典，外资标注正确")
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
        result = fd_module.fetch_dce_position_rank_multi(["M2701"], max_attempts=2, categories=["netLong"])
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
        def fake_fetch_json(url, headers=None, retries=3, timeout=20, post_data=None):
            for key, val in url_map.items():
                if key in url:
                    return val
            return None
        def fake_fetch_json_debug(url, headers=None, retries=3, timeout=20, post_data=None):
            for key, val in url_map.items():
                if key in url:
                    return val, {"url": url, "note": "来自测试模拟数据"}
            return None, {"url": url, "note": "测试模拟数据里没有匹配的url"}
        fd.fetch_json = fake_fetch_json
        fd.fetch_json_debug = fake_fetch_json_debug
    return _patch


def _make_conab_mock_df(rows):
    import pandas as pd
    return pd.DataFrame(rows)


def test_brazil_planting_progress_extracts_national_row(monkeypatch_fetch):
    """★核心逻辑验证：CONAB数据按州分行(MT/PR/BR等)，必须正确取到estado='BR'
    的全国汇总行，不能误取某个州的行当成全国数据。用实际查过的agrobr真实
    列结构(cultura/safra/operacao/estado/semana_atual/pct_*四个百分比字段)构造mock。"""
    import agrobr
    mock_df = _make_conab_mock_df([
        {"cultura": "Soja", "safra": "2026/27", "operacao": "Plantio", "estado": "MT",
         "semana_atual": "2026-10-04", "pct_ano_anterior": 15.0, "pct_semana_anterior": 20.0,
         "pct_semana_atual": 25.0, "pct_media_5_anos": 22.0},
        {"cultura": "Soja", "safra": "2026/27", "operacao": "Plantio", "estado": "BR",
         "semana_atual": "2026-10-04", "pct_ano_anterior": 5.1, "pct_semana_anterior": 3.5,
         "pct_semana_atual": 8.2, "pct_media_5_anos": 9.4},
    ])
    async def fake_progresso_safra(**kwargs):
        return mock_df
    old_conab = getattr(agrobr, "conab", None)
    agrobr.conab = type("obj", (), {"progresso_safra": staticmethod(fake_progresso_safra)})
    try:
        result = fd.fetch_brazil_planting_progress()
        assert result["available"] is True
        assert result["pctCurrent"] == 8.2, f"★应该取全国(BR)行的8.2，不是MT州的25.0，实际{result['pctCurrent']}"
        assert result["pctYearAgo"] == 5.1
        assert result["pctPrevWeek"] == 3.5
        assert result["pctFiveYearAvg"] == 9.4
        print(f"✅ 正确从全国(BR)行提取数据(8.2%)，没有误取MT州的行(25.0%)")
    finally:
        if old_conab is not None:
            agrobr.conab = old_conab


def test_brazil_planting_progress_no_national_row_found(monkeypatch_fetch):
    """如果返回数据里完全没有estado='BR'的行(比如CONAB改了全国汇总行的标记方式)，
    应该诚实报告，并且debug信息里要列出实际看到的estado值，方便排查"""
    import agrobr
    mock_df = _make_conab_mock_df([
        {"cultura": "Soja", "safra": "2026/27", "operacao": "Plantio", "estado": "MT",
         "semana_atual": "2026-10-04", "pct_ano_anterior": 15.0, "pct_semana_anterior": 20.0,
         "pct_semana_atual": 25.0, "pct_media_5_anos": 22.0},
    ])
    async def fake_progresso_safra(**kwargs):
        return mock_df
    old_conab = getattr(agrobr, "conab", None)
    agrobr.conab = type("obj", (), {"progresso_safra": staticmethod(fake_progresso_safra)})
    try:
        result = fd.fetch_brazil_planting_progress()
        assert result["available"] is False
        assert "BR" in result["reason"]
        assert result["debug"]["actualEstadoValues"] == ["MT"]
        print("✅ 找不到全国汇总行时诚实报告，debug信息列出了实际看到的estado值")
    finally:
        if old_conab is not None:
            agrobr.conab = old_conab


def test_brazil_planting_progress_missing_columns(monkeypatch_fetch):
    """★列结构跟预期不符(比如CONAB改了字段名)时应该给出诊断信息，不静默失败或崩溃"""
    import agrobr
    mock_df = _make_conab_mock_df([
        {"cultura": "Soja", "estado": "BR", "algum_campo_diferente": 123},
    ])
    async def fake_progresso_safra(**kwargs):
        return mock_df
    old_conab = getattr(agrobr, "conab", None)
    agrobr.conab = type("obj", (), {"progresso_safra": staticmethod(fake_progresso_safra)})
    try:
        result = fd.fetch_brazil_planting_progress()
        assert result["available"] is False
        assert "debug" in result and "actualColumns" in result["debug"]
        print("✅ 列结构跟预期不符时给出诊断信息(实际有哪些列)，不崩溃")
    finally:
        if old_conab is not None:
            agrobr.conab = old_conab


def test_brazil_planting_progress_exception_handled_gracefully(monkeypatch_fetch):
    """★CONAB接口调用过程中抛出任何异常(网络问题/解析失败等)都应该被兜底捕获，
    返回明确的不可用原因，不能让整个main()因为这一项失败而崩溃"""
    import agrobr
    async def fake_progresso_safra(**kwargs):
        raise ConnectionError("模拟网络连接失败")
    old_conab = getattr(agrobr, "conab", None)
    agrobr.conab = type("obj", (), {"progresso_safra": staticmethod(fake_progresso_safra)})
    try:
        result = fd.fetch_brazil_planting_progress()
        assert result["available"] is False
        assert "ConnectionError" in result["reason"]
        print("✅ 接口调用抛出异常时被正确捕获兜底，不会让整个程序崩溃")
    finally:
        if old_conab is not None:
            agrobr.conab = old_conab


def test_brazil_planting_progress_empty_dataframe(monkeypatch_fetch):
    """返回空DataFrame(比如播种季还没开始)时应该诚实报告，不报错"""
    import agrobr
    mock_df = _make_conab_mock_df([])
    async def fake_progresso_safra(**kwargs):
        return mock_df
    old_conab = getattr(agrobr, "conab", None)
    agrobr.conab = type("obj", (), {"progresso_safra": staticmethod(fake_progresso_safra)})
    try:
        result = fd.fetch_brazil_planting_progress()
        assert result["available"] is False
        print("✅ 空DataFrame时诚实报告不可用，不报错")
    finally:
        if old_conab is not None:
            agrobr.conab = old_conab


def _make_grain_inspections_mock(records, capture_url=None):
    """构造agtransport.usda.gov(Socrata)的mock：返回一个记录列表(不是{results:[...]}
    这种包装，Socrata的/resource/{id}.json直接返回顶层数组)。"""
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        if capture_url is not None:
            capture_url.append(url)
        return records, {"httpStatus": 200}
    return fake_fetch


def test_export_inspections_url_uses_correct_dataset_and_filter(monkeypatch_fetch):
    """★验证请求的是正确的数据集id(sruw-w49i，多个独立来源交叉确认过)，
    并且用grain='SOYBEANS'筛选、按date(即Week Ending Date)降序排列。"""
    urls_called = []
    fd.fetch_json_debug = _make_grain_inspections_mock([
        {"date": "2026-09-21T00:00:00.000", "grain": "SOYBEANS", "mt": "450000"},
    ], capture_url=urls_called)
    result = fd.fetch_us_export_inspections()
    assert len(urls_called) == 1
    assert "sruw-w49i" in urls_called[0], f"★应该请求Grain Inspections数据集(sruw-w49i)，实际URL: {urls_called[0]}"
    assert "SOYBEANS" in urls_called[0] and "grain" in urls_called[0].lower()
    assert "date" in urls_called[0] and "%24order" in urls_called[0]
    print("✅ 请求了正确的数据集(sruw-w49i)，用grain='SOYBEANS'筛选并按周次降序排列")


def test_export_inspections_aggregates_same_week_multiple_ports(monkeypatch_fetch):
    """★核心逻辑验证(手算验证过)：同一周的记录按港口/目的地拆分成多条，
    必须把同一周的所有记录加总才是当周总检验量，不能只取第一条。"""
    records = [
        {"date": "2026-09-21T00:00:00.000", "grain": "SOYBEANS", "mt": "450000", "port": "MISSISSIPPI R."},
        {"date": "2026-09-21T00:00:00.000", "grain": "SOYBEANS", "mt": "223000", "port": "COLUMBIA R."},
        {"date": "2026-09-14T00:00:00.000", "grain": "SOYBEANS", "mt": "380000", "port": "MISSISSIPPI R."},
    ]
    fd.fetch_json_debug = _make_grain_inspections_mock(records)
    result = fd.fetch_us_export_inspections()
    assert result["available"] is True
    assert result["quantityMetricTons"] == 673000.0, f"★应该是最新周(09-21)两条记录加总450000+223000=673000，不是只取第一条，实际{result['quantityMetricTons']}"
    assert result["recordCountThisWeek"] == 2
    assert result["weekEndingDate"] == "2026-09-21"
    print(f"✅ 同一周多港口记录正确加总：{result['quantityMetricTons']}公吨(2条记录)，没有漏算旧周次的记录")


def test_export_inspections_empty_list_gives_diagnostic(monkeypatch_fetch):
    """筛选grain='SOYBEANS'后一条记录都没有时(比如字段名/值大小写跟预期不同)，
    应该诚实报告，不崩溃"""
    fd.fetch_json_debug = _make_grain_inspections_mock([])
    result = fd.fetch_us_export_inspections()
    assert result["available"] is False
    assert "没有查到任何记录" in result["reason"]
    print("✅ 筛选后没有记录时诚实报告，不崩溃")


def test_export_inspections_non_list_response_gives_diagnostic(monkeypatch_fetch):
    """★如果返回的不是列表(比如字段名grain猜错了，Socrata可能返回错误对象而不是
    数组)，应该给出诊断信息，不是假设它一定是列表然后崩溃"""
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return {"error": "invalid column grain"}, {"httpStatus": 400, "rawSnippet": '{"error": "invalid column grain"}'}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_us_export_inspections()
    assert result["available"] is False
    assert "rawType" in result["debug"] or "rawSnippet" in result.get("debug", {})
    print("✅ 返回非列表结构时给出诊断信息，不假设结构直接崩溃")


def test_export_inspections_missing_date_field(monkeypatch_fetch):
    """如果记录里没有date这个字段(字段名猜错了)，应该给出诊断信息
    (实际有哪些字段)，不是KeyError崩溃"""
    fd.fetch_json_debug = _make_grain_inspections_mock([{"grain": "SOYBEANS", "some_other_field": "123"}])
    result = fd.fetch_us_export_inspections()
    assert result["available"] is False
    assert "actualKeysSeen" in result["debug"]
    assert "some_other_field" in result["debug"]["actualKeysSeen"]
    print("✅ 缺少date字段时给出诊断信息(实际有哪些字段)，不崩溃")


def test_export_inspections_mt_field_unparseable(monkeypatch_fetch):
    """如果mt字段值没法解析成数字(字段名可能不叫mt，或者值本身格式有问题)，
    应该诚实报告，不是把0当成真实检验量展示出来"""
    fd.fetch_json_debug = _make_grain_inspections_mock([
        {"date": "2026-09-21T00:00:00.000", "grain": "SOYBEANS", "mt": "not-a-number"},
    ])
    result = fd.fetch_us_export_inspections()
    assert result["available"] is False
    assert "mt字段值都无法解析" in result["reason"]
    print("✅ mt字段值无法解析成数字时诚实报告，不会假装解析成功展示一个错误的0")


def test_export_inspections_no_network_response(monkeypatch_fetch):
    """接口完全无响应时应该诚实报告，不崩溃"""
    def fake_fetch(url, headers=None, retries=3, timeout=20):
        return None, {"httpStatus": None, "error": "连接超时"}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_us_export_inspections()
    assert result["available"] is False
    assert "agtransport接口无返回数据" in result["reason"]
    print("✅ 接口无响应时诚实报告，不崩溃")









def test_mysteel_crush_rate_parsing_real_content(monkeypatch_fetch):
    """★用户实测抓包确认过的真实content格式(2026-09-22那条)，验证正则提取正确。"""
    mock_response = {
        "resultCode": 0, "resultMsg": "succeed!", "total": 750,
        "dataList": [
            {
                "content": "9月22日成交方面，全国主要油厂豆粕成交10.70万吨，较前一交易日减1.54万吨，其中现货成交8.85万吨，较前一交易日减1.49万吨，远月基差成交1.85万吨，较前一交易日减0.05万吨。\r\n开机方面，今日全国动态全样本油厂开机率为69.98%，较前一日持平。",
                "publishTime": "2026-09-22 18:20", "id": "4883044",
            },
        ],
    }
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_crush_rate()
    assert result["available"] is True
    assert result["value"] == 69.98, f"★应该正确提取69.98，实际{result['value']}"
    assert result["date"] == "2026-09-22"
    print(f"✅ 真实content格式解析正确：开机率{result['value']}%")


def test_mysteel_crush_rate_missing_linebreak_still_parses(monkeypatch_fetch):
    """★用户实测抓包里9月11日那条缺少\\r\\n换行符(跟其他条格式略有出入)，
    验证正则不依赖这个换行符，核心句式匹配依然稳。"""
    mock_response = {
        "resultCode": 0,
        "dataList": [
            {"content": "9月11日成交方面，全国主要油厂豆粕成交20.63万吨，较前一交易日增10.64万吨，其中现货成交7.63万吨，较前一交易日持平，远月基差成交13.00万吨，较前一交易日增10.64万吨。开机方面，今日全国动态全样本油厂开机率为61.52%，较前一日上升0.41%。",
             "publishTime": "2026-09-11 18:42"},
        ],
    }
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_crush_rate()
    assert result["available"] is True
    assert result["value"] == 61.52
    print("✅ 缺少换行符的记录依然能正确解析(不依赖\\r\\n这种次要格式)")


def test_mysteel_crush_rate_skips_non_matching_items(monkeypatch_fetch):
    """★如果排在最前面的记录碰巧不含"开机率为"这个句式(比如被关键字模糊匹配
    进来的不相关新闻)，应该跳过继续找下一条，不是直接放弃或者报错。"""
    mock_response = {
        "resultCode": 0,
        "dataList": [
            {"content": "这是一条不相关的新闻，没有提到开机率", "publishTime": "2026-09-24 10:00"},
            {"content": "开机方面，今日全国动态全样本油厂开机率为68.84%，较前一日下降1.14%。", "publishTime": "2026-09-23 18:08"},
        ],
    }
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_crush_rate()
    assert result["available"] is True
    assert result["value"] == 68.84, "★应该跳过第1条不匹配的，用第2条能匹配的"
    assert result["date"] == "2026-09-23"
    print("✅ 第一条不匹配时正确跳过，继续找下一条能匹配的记录")


def test_mysteel_crush_rate_token_and_post_data_sent_correctly(monkeypatch_fetch):
    """★验证token(实测值-1)和查询关键词都正确发送"""
    captured = {}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        captured["headers"] = headers
        captured["post_data"] = post_data
        captured["url"] = url
        return {"resultCode": 0, "dataList": []}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    fd.fetch_mysteel_crush_rate()
    assert captured["url"] == "https://search.mysteel.com/searchapi/search/searchFlashNews"
    assert captured["headers"]["token"] == "-1", "★token应该固定发送实测确认过的占位值-1"
    assert captured["post_data"]["query"] == "全国动态全样本油厂开机率"
    print("✅ 正确用POST发送查询关键词，token正确设为实测确认的占位值-1")


def test_mysteel_crush_rate_no_matching_content_gives_diagnostic(monkeypatch_fetch):
    """如果搜索结果里所有记录都没有"开机率为XX%"这个格式(比如措辞真的变了)，
    应该诚实报告，debug里带上第一条记录的实际内容方便排查"""
    mock_response = {"resultCode": 0, "dataList": [{"content": "完全不相关的内容", "publishTime": "2026-09-24"}]}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_crush_rate()
    assert result["available"] is False
    assert "firstItemContent" in result["debug"]
    print("✅ 没有任何记录匹配时诚实报告，debug带上实际内容方便排查")


def test_mysteel_crush_rate_empty_result_list(monkeypatch_fetch):
    """搜索结果完全为空时应该诚实报告，不崩溃"""
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return {"resultCode": 0, "dataList": [], "total": 0}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_crush_rate()
    assert result["available"] is False
    assert "为空" in result["reason"]
    print("✅ 搜索结果为空时诚实报告，不崩溃")


def test_mysteel_crush_rate_bad_result_code(monkeypatch_fetch):
    """resultCode不是0(接口返回了错误状态)时应该诚实报告，不假装成功"""
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return {"resultCode": 1, "resultMsg": "token invalid"}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_crush_rate()
    assert result["available"] is False
    assert "resultCode=1" in result["reason"]
    print("✅ resultCode非0时诚实报告，不假装成功")


def test_fetch_json_debug_post_mode_backward_compatible(monkeypatch_fetch):
    """★向后兼容验证：不传post_data参数时(所有既有15+个调用方都是这样用的)，
    fetch_json_debug应该完全保持GET请求的既有行为，不受这次扩充影响。
    ★用_REAL_FETCH_JSON_DEBUG(模块加载时保存的原始引用)而不是fd.fetch_json_debug，
    因为跑到这个测试之前，前面好几个测试已经把fd.fetch_json_debug替换成了
    各自的mock版本，直接用fd.fetch_json_debug测不到真正的函数实现。"""
    import urllib.request
    captured_reqs = []
    original_urlopen = urllib.request.urlopen
    class FakeResp:
        status = 200
        def read(self): return b'{"ok": true}'
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake_urlopen(req, timeout=20):
        captured_reqs.append(req)
        return FakeResp()
    urllib.request.urlopen = fake_urlopen
    try:
        data, debug = _REAL_FETCH_JSON_DEBUG("https://example.com/test")
        assert len(captured_reqs) > 0, "★fake_urlopen应该被调用到——如果这里是0，说明测的不是真正的fetch_json_debug实现"
        assert captured_reqs[0].data is None, "★不传post_data时，请求体应该是None(GET请求)，不应该被这次扩充意外改成POST"
        assert data == {"ok": True}
        print("✅ 不传post_data时完全保持向后兼容(GET请求，body为None)")
    finally:
        urllib.request.urlopen = original_urlopen


def test_mysteel_poultry_profit_loss_cases_real_examples(monkeypatch_fetch):
    """★用户实测抓包提供的5条真实内容样本，措辞各不相同，验证正则都能正确
    提取(含正确处理正负号)。"""
    examples_and_expected = [
        ("本周白羽肉鸡平均理论养殖亏损4.18元/只", -4.18),
        ("本周白羽肉鸡养殖端理论亏损2.23元/只", -2.23),
        ("本周白羽肉鸡养殖全面亏损，平均理论亏损1.06元/只。", -1.06),  # ★陷阱案例：亏损出现两次
        ("本周白羽肉鸡平均理论养殖盈利0.56元/只", 0.56),
        ("本周毛鸡平均理论养殖盈利在0.82元/只", 0.82),  # ★第二轮实测发现的新变体："盈利"和数字间隔了"在"字
    ]
    for content, expected in examples_and_expected:
        mock_response = {"resultCode": 0, "dataList": [{"content": content, "publishTime": "2026-09-24 10:00"}]}
        def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
            return mock_response, {"httpStatus": 200}
        fd.fetch_json_debug = fake_fetch
        result = fd.fetch_mysteel_poultry_profit()
        assert result["available"] is True, f"应该能解析: {content}"
        assert result["value"] == expected, f"★内容'{content}'应该提取到{expected}，实际{result['value']}"
    print("✅ 5条真实措辞各异的样本(含陷阱案例+带连接词案例)全部正确提取，正负号处理正确")


def test_mysteel_poultry_profit_trap_case_skips_false_lead(monkeypatch_fetch):
    """★专门验证"陷阱"案例：'亏损'这个词出现两次，第一次后面紧跟逗号(不是
    数字)，第二次才紧跟真正的数值——必须正确跳过第一次的假信号，取第二次。"""
    mock_response = {"resultCode": 0, "dataList": [
        {"content": "本周白羽肉鸡养殖全面亏损，平均理论亏损1.06元/只。", "publishTime": "2026-09-24"},
    ]}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_poultry_profit()
    assert result["available"] is True
    assert result["value"] == -1.06, f"★应该跳过'全面亏损，'这个假信号(后面是逗号不是数字)，取真正带数值的第二次'亏损'，实际{result['value']}"
    print("✅ 正确跳过'亏损'第一次出现(后面紧跟逗号)的假信号，取到第二次(带真实数值)")


def test_mysteel_poultry_profit_connector_word_allowance_excludes_punctuation(monkeypatch_fetch):
    """★第二轮修复后新增的边界验证：正则放宽到允许"在/为/约"这类连接词后，
    要确认标点符号依然被排除在允许范围外——构造一个更极端的案例(亏损后面
    直接跟逗号+一段不相关文字，再出现一次真正带数值的亏损)，确认不会因为
    放宽后误吞了标点导致提前匹配到错误位置。"""
    mock_response = {"resultCode": 0, "dataList": [
        {"content": "今日市场全面亏损，情绪低迷，不过白羽肉鸡平均理论养殖亏损约3.50元/只。", "publishTime": "2026-09-24"},
    ]}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_poultry_profit()
    assert result["available"] is True
    assert result["value"] == -3.50, f"★逗号依然应该被排除在连接词允许范围外，正确取到带'约'字的那次亏损，实际{result['value']}"
    print("✅ 放宽连接词允许范围后，标点符号依然被正确排除，没有引入新的误判")


def test_mysteel_poultry_profit_does_not_assume_content_field_name(monkeypatch_fetch):
    """★这次是"文章"搜索，不是"快讯"搜索，字段结构可能不一样——验证不管
    这个匹配上的字段叫什么名字(不一定是"content")，都能扫描到并正确提取。"""
    mock_response = {"resultCode": 0, "dataList": [
        {"articleBody": "白羽肉鸡平均理论养殖盈利0.71元/只", "publishTime": "2026-05-01", "title": "行业周报"},
    ]}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_poultry_profit()
    assert result["available"] is True, "★不该假设字段名一定叫content，应该扫描到articleBody这个字段"
    assert result["value"] == 0.71
    print("✅ 不预设字段名(这次匹配到的是articleBody而不是content)，扫描所有字符串字段都能正确提取")


def test_mysteel_poultry_profit_query_uses_correct_endpoint(monkeypatch_fetch):
    """★验证请求的是searchArticle这个端点(不是开机率用的searchFlashNews)，
    查询关键词也对应换成"白羽肉鸡养殖利润"。"""
    captured = {}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        captured["url"] = url
        captured["post_data"] = post_data
        return {"resultCode": 0, "dataList": []}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    fd.fetch_mysteel_poultry_profit()
    assert captured["url"] == "https://search.mysteel.com/searchapi/search/searchArticle"
    assert captured["post_data"]["query"] == "白羽肉鸡养殖利润"
    print("✅ 正确请求searchArticle端点，查询关键词正确设为'白羽肉鸡养殖利润'")


def test_mysteel_poultry_profit_no_matching_content_gives_diagnostic(monkeypatch_fetch):
    """完全没有匹配的记录时应该诚实报告，debug带上第一条样本方便排查"""
    mock_response = {"resultCode": 0, "dataList": [{"content": "完全不相关的内容", "publishTime": "2026-09-24"}]}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_poultry_profit()
    assert result["available"] is False
    assert "firstItemSample" in result["debug"]
    print("✅ 没有任何记录匹配时诚实报告，debug带上第一条样本方便排查")


def test_mysteel_poultry_profit_empty_result(monkeypatch_fetch):
    """搜索结果为空时应该诚实报告，不崩溃"""
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return {"resultCode": 0, "dataList": [], "total": 0}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_poultry_profit()
    assert result["available"] is False
    assert "为空" in result["reason"]
    print("✅ 搜索结果为空时诚实报告，不崩溃")


def test_mysteel_rmspread_range_format_real_examples(monkeypatch_fetch):
    """★用户实测抓包提供的6条真实"区间"格式样本，验证都能正确取中点，
    而且没有被同一句话里的"涨跌幅度"区间干扰(只取价差本身的区间)。"""
    examples_and_expected = [
        ("2026年7月9日，国内沿海地区豆菜粕现货价差下跌，区间为480-520元/吨，较前一日跌10-20元/吨。具体表现为豆粕现货价格下跌10-20元/吨，而菜粕现货价格保持稳定。", 500.0),
        ("2026年7月8日，国内沿海地区豆菜粕现货价差上涨，价差在490-540元/吨，涨20元/吨。具体来看，今日豆粕现货价格涨10-30元/吨，菜粕现货价格涨跌互现。", 515.0),
        ("2026年7月7日，国内沿海地区豆菜粕现货价差收窄至490-520元/吨，较前一交易日下跌10元/吨。当日豆粕现货价格小幅上涨10元/吨，菜粕现货价格涨幅略高，上涨10-20元/吨。受菜粕涨幅大于豆粕影响，两者价差呈现下行趋势。", 505.0),
        ("2026年7月6日，国内沿海地区豆菜粕现货价差走阔，区间为490-530元/吨，较前一交易日上涨20元/吨。分项来看，豆粕现货价格上调40-50元/吨，菜粕现货价格上调10-40元/吨。豆粕涨幅高于菜粕，驱动价差进一步扩大。", 510.0),
        ("截至2025年11月25日，国内沿海地区豆菜粕现货价差下跌，价差在410-570元/吨之间，跌10元/吨具体来看，今日豆粕现货价格稳定，菜粕今日市场价格涨10元/吨连粕主力01合约震荡运行，油厂豆粕库存高企，下游饲料企业库存充", 490.0),
        ("截至2025年11月20日，国内沿海地区豆菜粕现货价差上涨，价差在470-570元/吨之间，涨10-20元/吨具体来看，今日豆粕现货价格跌10元/吨，菜粕今日市场价格跌20元/吨连粕主力01合约震荡下跌，豆粕现货价格下跌，", 520.0),
    ]
    for content, expected_mid in examples_and_expected:
        mock_response = {"resultCode": 0, "dataList": [{"content": content, "publishTime": "2026-07-09 15:34"}]}
        def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
            return mock_response, {"httpStatus": 200}
        fd.fetch_json_debug = fake_fetch
        result = fd.fetch_mysteel_rmspread()
        assert result["available"] is True, f"应该能解析: {content[:30]}"
        assert result["value"] == expected_mid, f"★内容'{content[:30]}...'应该取中点{expected_mid}，实际{result['value']}"
        assert result["formatUsed"] == "区间中点"
    print("✅ 6条真实区间格式样本全部正确取中点，没有被涨跌幅度区间干扰")


def test_mysteel_rmspread_city_specific_format_real_example(monkeypatch_fetch):
    """★用户实测抓包提供的第7条(8月28日)样本，是完全不同的"分城市单值"格式，
    验证能正确识别并取多城市平均值(不是误判成区间格式)。"""
    content = ("2026年8月28日，国内主要市场豆菜粕价差整体持稳。广东地区豆粕3190元/吨，"
               "菜粕2450元/吨，价差740元/吨；广西地区豆粕3170元/吨，菜粕2460元/吨，"
               "价差710元/吨；南通地区豆粕3190元/吨，菜粕2380元/吨，价差810元/吨。"
               "近期各区域价差波动幅度较小，市场表现相对平稳。")
    mock_response = {"resultCode": 0, "dataList": [{"content": content, "publishTime": "2026-08-28 15:45"}]}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_rmspread()
    assert result["available"] is True
    assert result["formatUsed"] == "多城市单值平均", f"★应该识别为多城市单值格式，实际{result.get('formatUsed')}"
    expected_avg = round((740 + 710 + 810) / 3, 1)
    assert result["value"] == expected_avg, f"★应该是740/710/810三个城市的平均值{expected_avg}，实际{result['value']}"
    assert result["citySamples"] == [740.0, 710.0, 810.0]
    print(f"✅ 分城市单值格式正确识别，三城市平均值{result['value']}元/吨计算正确")


def test_mysteel_rmspread_two_formats_mutually_exclusive(monkeypatch_fetch):
    """★核心设计验证：两种格式的正则不会交叉误判——区间格式的正则对
    "分城市单值"样本应该完全匹配不到(没有横线区间)，单值格式的正则对
    "区间"样本也应该完全匹配不到(价差后面不是直接跟数字)。"""
    range_content = "国内沿海地区豆菜粕现货价差下跌，区间为480-520元/吨，较前一日跌10-20元/吨。"
    city_content = "广东地区豆粕3190元/吨，菜粕2450元/吨，价差740元/吨；广西地区豆粕3170元/吨，菜粕2460元/吨，价差710元/吨。"

    assert fd.MYSTEEL_RMSPREAD_RANGE_PATTERN.search(city_content) is None, "★区间正则不应该在分城市单值样本里意外匹配到东西"
    assert fd.MYSTEEL_RMSPREAD_SINGLE_PATTERN.findall(range_content) == [], "★单值正则不应该在区间样本里意外抓到480或520这类数字"
    print("✅ 两种格式的正则确认互斥，不会交叉误判")


def test_mysteel_rmspread_query_uses_correct_keyword(monkeypatch_fetch):
    """验证查询关键词正确设为'豆菜粕价差'，用的是文章搜索端点"""
    captured = {}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        captured["url"] = url
        captured["post_data"] = post_data
        return {"resultCode": 0, "dataList": []}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    fd.fetch_mysteel_rmspread()
    assert captured["url"] == "https://search.mysteel.com/searchapi/search/searchArticle"
    assert captured["post_data"]["query"] == "豆菜粕价差"
    print("✅ 正确请求searchArticle端点，查询关键词正确设为'豆菜粕价差'")


def test_mysteel_rmspread_no_matching_content_gives_diagnostic(monkeypatch_fetch):
    """完全没有匹配的记录时应该诚实报告，debug带上第一条样本方便排查"""
    mock_response = {"resultCode": 0, "dataList": [{"content": "完全不相关的内容", "publishTime": "2026-09-24"}]}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_rmspread()
    assert result["available"] is False
    assert "firstItemSample" in result["debug"]
    print("✅ 没有任何记录匹配时诚实报告，debug带上第一条样本方便排查")


def test_mysteel_rmspread_empty_result(monkeypatch_fetch):
    """搜索结果为空时应该诚实报告，不崩溃"""
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return {"resultCode": 0, "dataList": [], "total": 0}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_rmspread()
    assert result["available"] is False
    assert "为空" in result["reason"]
    print("✅ 搜索结果为空时诚实报告，不崩溃")


def test_mysteel_arrival_forecast_five_standard_examples(monkeypatch_fetch):
    """★用户实测抓包提供的5条真实"标准格式"样本(月份+份字+共计约XXX万吨)，
    验证都能正确提取出年份+月份+万吨数值。"""
    examples = [
        ("Mysteel农产品团队预估，2026年6月份国内全样本油厂大豆到港165.2船，共计约1073.80万吨（本月船重按6.5万吨计）。", 2026, 6, 1073.80),
        ("Mysteel农产品团队预估，2026年5月份国内全样本油厂大豆到港152.1船，共计约988.65万吨（本月船重按6.5万吨计）。", 2026, 5, 988.65),
        ("Mysteel农产品团队预估，2026年3月份国内全样本油厂大豆到港103.5船，共计约672.75万吨（本月船重按6.5万吨计）。", 2026, 3, 672.75),
        ("2025年12月份国内全样本油厂大豆到港预估139.2船，共计约904.8万吨（本月船重按6.5万吨计）其中东北13船约84.5万吨；华北（京津冀）18船约117万吨；陕西2船约13万吨；", 2025, 12, 904.8),
        ("2025年10月份国内全样本油厂大豆到港预估146船，共计约949万吨（本月船重按6.5万吨计）其中东北14.5船约94.25万吨；华北（京津冀）20船约130万吨；", 2025, 10, 949.0),
    ]
    for content, exp_year, exp_month, exp_value in examples:
        mock_response = {"resultCode": 0, "dataList": [{"content": content, "publishTime": "2026-06-26 17:53"}]}
        def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
            return mock_response, {"httpStatus": 200}
        fd.fetch_json_debug = fake_fetch
        result = fd.fetch_mysteel_arrival_forecast()
        assert result["available"] is True, f"应该能解析: {content[:30]}"
        assert result["forecastYear"] == exp_year and result["forecastMonth"] == exp_month, f"★年月应该是{exp_year}年{exp_month}月，实际{result['forecastYear']}年{result['forecastMonth']}月"
        assert result["value"] == exp_value, f"★数值应该是{exp_value}，实际{result['value']}"
    print("✅ 5条真实'月份+共计约'样本全部正确提取年份+月份+万吨数值")


def test_mysteel_arrival_forecast_cascade_format_real_example(monkeypatch_fetch):
    """★用户实测抓包提供的第6条(预测未来3个月，"预计达"措辞)样本，验证只取
    最近月(7月)的数值，不尝试解析后面提到的8月/9月次要数据(格式不统一，且
    原文自己标注远月数据可靠性存疑)。"""
    content = ("2026年7月国内油厂进口大豆到港量预计达1064万吨，环比略有增长。分区域看，"
               "华东地区到港量占比最高，山东及华北次之。8月预估到港1050万吨，"
               "9月预计回落至930万吨。远月到港数据仍存修正可能，需持续跟踪船期变化。")
    mock_response = {"resultCode": 0, "dataList": [{"content": content, "publishTime": "2026-06-26 17:53"}]}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_arrival_forecast()
    assert result["available"] is True
    assert result["forecastYear"] == 2026 and result["forecastMonth"] == 7, f"★应该识别为2026年7月(最近月)，实际{result['forecastYear']}年{result['forecastMonth']}月"
    assert result["value"] == 1064.0, f"★应该取1064(最近月的数值)，不是1050或930(次要月份)，实际{result['value']}"
    print(f"✅ '预计达'措辞(预测未来3个月)正确只取最近月(7月，1064万吨)，不解析次要的8月/9月数据")


def test_mysteel_arrival_forecast_third_variant_real_example(monkeypatch_fetch):
    """★真实运行后新发现的第三种措辞变体："YYYY年M月"(没有"份"字)+"到港约XXX万吨"
    (不是"共计约"也不是"预计达"，只是简单的"约")——这条曾经把之前两个各自
    死板的正则都打穿过，是这次改成"限定字符数上限、不穷举具体连接词"这个
    更宽松策略的直接触发案例。"""
    content = ("Mysteel预估2026年10月国内全样本油厂大豆到港约854.10万吨，11月预计870万吨，"
               "12月950万吨。10月分区域看：东北约71.50万吨；华北（含西北）约130.00万吨；"
               "山东（含河南）约185.25万吨；华东地区（含沿江）约272.35万吨；福建约32.50万吨；"
               "广西（含海南/云南）约52.00万吨；广东约110.50万吨。远月数据后期可能修正。")
    mock_response = {"resultCode": 0, "dataList": [{"content": content, "publishTime": "2026-09-24 17:36", "title": "Mysteel数据：2026年10月国内油厂进口大豆船期及11月-12月到港预报"}]}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_arrival_forecast()
    assert result["available"] is True, "★这条真实内容之前会解析失败，这是这次修复要解决的真实案例"
    assert result["forecastYear"] == 2026 and result["forecastMonth"] == 10, f"★应该识别为2026年10月，实际{result['forecastYear']}年{result['forecastMonth']}月"
    assert result["value"] == 854.10, f"★应该取854.10(最近月/10月的数值)，不是870(11月)、950(12月)，也不是71.50这类分区域细分数字，实际{result['value']}"
    print(f"✅ 第三种措辞变体('到港约XXX万吨'，无'份'字)正确提取，没有被后续月份或分区域数据干扰")


def test_mysteel_arrival_forecast_query_uses_correct_keyword(monkeypatch_fetch):
    """验证查询关键词正确设为'大豆到港预报'，用的是文章搜索端点"""
    captured = {}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        captured["url"] = url
        captured["post_data"] = post_data
        return {"resultCode": 0, "dataList": []}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    fd.fetch_mysteel_arrival_forecast()
    assert captured["url"] == "https://search.mysteel.com/searchapi/search/searchArticle"
    assert captured["post_data"]["query"] == "大豆到港预报"
    print("✅ 正确请求searchArticle端点，查询关键词正确设为'大豆到港预报'")


def test_mysteel_arrival_forecast_no_matching_content_gives_diagnostic(monkeypatch_fetch):
    """完全没有匹配的记录时应该诚实报告，debug带上第一条样本方便排查"""
    mock_response = {"resultCode": 0, "dataList": [{"content": "完全不相关的内容", "publishTime": "2026-09-24"}]}
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return mock_response, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_arrival_forecast()
    assert result["available"] is False
    assert "firstItemSample" in result["debug"]
    print("✅ 没有任何记录匹配时诚实报告，debug带上第一条样本方便排查")


def test_mysteel_arrival_forecast_empty_result(monkeypatch_fetch):
    """搜索结果为空时应该诚实报告，不崩溃"""
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        return {"resultCode": 0, "dataList": [], "total": 0}, {"httpStatus": 200}
    fd.fetch_json_debug = fake_fetch
    result = fd.fetch_mysteel_arrival_forecast()
    assert result["available"] is False
    assert "为空" in result["reason"]
    print("✅ 搜索结果为空时诚实报告，不崩溃")


def test_hog_df_retries_and_succeeds_on_second_attempt(monkeypatch_fetch):
    """★真实运行遇到过ConnectTimeoutError，验证重试机制：第一次调用失败
    (模拟连接超时)，第二次成功时，应该正确返回成功结果，不是直接放弃。
    用retry_delay_seconds=0跳过真正的等待，测试能快速跑完。"""
    import pandas as pd
    import fetch_data as fd_module
    import sys

    call_count = [0]
    class FakeAkshare:
        @staticmethod
        def futures_hog_supply(symbol):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("模拟第一次连接超时")
            return pd.DataFrame({"date": ["2026-09-22"], "value": [8.22]})

    sys.modules['akshare'] = FakeAkshare()
    try:
        df, err = fd_module._fetch_akshare_hog_df("猪粮比价", retry_delay_seconds=0)
        assert err is None, f"★第二次成功后应该返回成功结果，不应该有错误，实际{err}"
        assert df is not None and len(df) == 1
        assert call_count[0] == 2, f"★应该恰好调用2次(第一次失败+第二次重试成功)，实际{call_count[0]}次"
        print("✅ 第一次连接超时、第二次成功时，重试机制正确工作")
    finally:
        del sys.modules['akshare']


def test_hog_df_exhausts_retries_reports_honestly(monkeypatch_fetch):
    """★如果重试次数用完依然失败(比如xt.yangzhu.vip持续连接超时)，应该
    诚实报告，debug里带上重试次数和真实错误类型，不是笼统报错。"""
    import fetch_data as fd_module
    import sys

    call_count = [0]
    class FakeAkshare:
        @staticmethod
        def futures_hog_supply(symbol):
            call_count[0] += 1
            raise ConnectionError("Connection to xt.yangzhu.vip timed out")

    sys.modules['akshare'] = FakeAkshare()
    try:
        df, err = fd_module._fetch_akshare_hog_df("猪粮比价", retries=2, retry_delay_seconds=0)
        assert df is None
        assert call_count[0] == 2, f"★应该恰好重试2次后放弃，实际调用了{call_count[0]}次"
        assert "已重试2次" in err["reason"]
        assert "xt.yangzhu.vip" in err["reason"], "★应该保留真实的错误信息，方便判断是不是网络连接问题"
        assert err["debug"]["retriesAttempted"] == 2
        assert err["debug"]["errorType"] == "ConnectionError"
        print("✅ 重试次数用完后诚实报告，debug带上重试次数和真实错误类型")
    finally:
        del sys.modules['akshare']


def test_hog_df_socket_timeout_always_restored(monkeypatch_fetch):
    """★关键验证：socket.setdefaulttimeout()是进程级全局设置，用完必须
    恢复原值——不管成功还是失败(重试耗尽)，都不能影响同一进程里其他部分
    的网络请求超时设置。"""
    import socket
    import fetch_data as fd_module
    import sys

    original_timeout = socket.getdefaulttimeout()

    class FakeAkshareAlwaysFail:
        @staticmethod
        def futures_hog_supply(symbol):
            raise ConnectionError("模拟持续失败")

    sys.modules['akshare'] = FakeAkshareAlwaysFail()
    try:
        fd_module._fetch_akshare_hog_df("猪粮比价", retries=2, retry_delay_seconds=0)
        assert socket.getdefaulttimeout() == original_timeout, "★即使全部重试都失败，socket超时设置也必须恢复原值"
        print("✅ 即使全部重试失败，socket全局超时设置依然正确恢复，不会污染后续其他网络请求")
    finally:
        del sys.modules['akshare']


def _install_fake_hog_akshare(core_df, cost_df, core_exc=None, cost_exc=None):
    """安装一个假的akshare：futures_hog_core/futures_hog_cost分别返回给定的
    DataFrame(或抛出给定异常)，同时记录被调用时的symbol参数。"""
    import sys
    calls = []
    class FakeAkshare:
        @staticmethod
        def futures_hog_core(symbol):
            calls.append(("futures_hog_core", symbol))
            if core_exc: raise core_exc
            return core_df
        @staticmethod
        def futures_hog_cost(symbol):
            calls.append(("futures_hog_cost", symbol))
            if cost_exc: raise cost_exc
            return cost_df
    sys.modules['akshare'] = FakeAkshare()
    return calls


def _run_hog_ratio_with_fake(core_df, cost_df, **kw):
    """跑fetch_hog_ratio并保证：清理假akshare、跳过重试等待(不真的sleep)。"""
    import sys
    import fetch_data as fd_module
    calls = _install_fake_hog_akshare(core_df, cost_df, **kw)
    real_sleep = fd_module.time.sleep
    fd_module.time.sleep = lambda s: None
    try:
        return fd_module.fetch_hog_ratio(), calls
    finally:
        fd_module.time.sleep = real_sleep
        del sys.modules['akshare']


def test_hog_ratio_xuantian_real_screenshot_case(monkeypatch_fetch):
    """★用户截图里的真实数据(猪价系统首页2026-09-27：外三元10.37、玉米2358、
    猪粮比4.40:1)：验证10.37÷(2358/1000)算出4.4，并确认两次调用用的是
    akshare源码里外三元=futures_hog_core、玉米=futures_hog_cost这两个函数。"""
    import datetime as dt, pandas as pd
    core = pd.DataFrame({"date": [dt.date(2026,9,25), dt.date(2026,9,26), dt.date(2026,9,27)], "value": [10.45, 10.41, 10.37]})
    cost = pd.DataFrame({"date": [dt.date(2026,9,25), dt.date(2026,9,26), dt.date(2026,9,27)], "value": [2354.0, 2354.0, 2358.0]})
    result, calls = _run_hog_ratio_with_fake(core, cost)
    assert result["available"] is True, result
    assert result["value"] == 4.4, f"★10.37÷2.358应该是4.4(页面4.40:1)，实际{result['value']}"
    assert result["date"] == "2026-09-27" and result["pigPrice"] == 10.37 and result["cornPricePerTon"] == 2358.0
    assert calls == [("futures_hog_core", "外三元"), ("futures_hog_cost", "玉米")], calls
    print("✅ 截图真实数据算出猪粮比4.4(页面显示4.40:1)，且正确调用外三元+玉米两个序列")


def test_hog_ratio_uses_latest_common_date_not_last_row(monkeypatch_fetch):
    """★两个序列的最新日期可能不同(玉米当天还没更新)，且行顺序不一定升序——
    必须取两边共同的最新一天，不能假设最后一行就是同一天。"""
    import datetime as dt, pandas as pd
    core = pd.DataFrame({"date": [dt.date(2026,9,27), dt.date(2026,9,25), dt.date(2026,9,26)], "value": [10.37, 10.45, 10.41]})  # 故意乱序
    cost = pd.DataFrame({"date": [dt.date(2026,9,26), dt.date(2026,9,25)], "value": [2354.0, 2350.0]})  # 玉米只到9-26
    result, _ = _run_hog_ratio_with_fake(core, cost)
    assert result["available"] is True
    assert result["date"] == "2026-09-26", f"★应该取共同的最新一天9-26，实际{result['date']}"
    assert result["value"] == round(10.41 / 2.354, 2)
    assert result["pigLatestDate"] == "2026-09-27" and result["cornLatestDate"] == "2026-09-26"
    print("✅ 取两个序列共同的最新一天(9-26)，不被乱序行或单边更新的日期误导")


def test_hog_ratio_skips_nan_and_bad_dates(monkeypatch_fetch):
    """akshare内部用errors="coerce"转换，异常行会变成NaN/NaT而不是报错——
    这类行必须被丢掉，不能当成"最新一天"。"""
    import datetime as dt, pandas as pd
    core = pd.DataFrame({"date": [dt.date(2026,9,26), dt.date(2026,9,27), pd.NaT], "value": [10.41, float("nan"), 99.0]})
    cost = pd.DataFrame({"date": [dt.date(2026,9,26), dt.date(2026,9,27)], "value": [2354.0, 2358.0]})
    result, _ = _run_hog_ratio_with_fake(core, cost)
    assert result["available"] is True
    assert result["date"] == "2026-09-26", f"★9-27生猪价是NaN、NaT那行日期无效，都应该被丢掉，实际{result['date']}"
    print("✅ NaN价格和NaT日期的行被正确丢弃")


def test_hog_ratio_corn_already_per_kg_not_divided_twice(monkeypatch_fetch):
    """如果玉米价格哪天改成元/公斤(2.358)，不能再除以1000(否则算出4398这种荒谬值)"""
    import datetime as dt, pandas as pd
    core = pd.DataFrame({"date": [dt.date(2026,9,27)], "value": [10.37]})
    cost = pd.DataFrame({"date": [dt.date(2026,9,27)], "value": [2.358]})
    result, _ = _run_hog_ratio_with_fake(core, cost)
    assert result["available"] is True and result["value"] == 4.4
    print("✅ 玉米价格已是元/公斤量级时不重复除以1000")


def test_hog_ratio_absurd_result_rejected(monkeypatch_fetch):
    """单位/序列取错导致算出离谱的猪粮比时，宁可不展示也不展示错数字"""
    import datetime as dt, pandas as pd
    core = pd.DataFrame({"date": [dt.date(2026,9,27)], "value": [10.37]})
    cost = pd.DataFrame({"date": [dt.date(2026,9,27)], "value": [90000.0]})  # 玉米价格荒谬
    result, _ = _run_hog_ratio_with_fake(core, cost)
    assert result["available"] is False
    assert "超出合理范围" in result["reason"] and "cornPrice" in result["debug"]
    print("✅ 算出离谱猪粮比时诚实报告，不展示错数字")


def test_hog_ratio_no_common_dates_gives_diagnostic(monkeypatch_fetch):
    import datetime as dt, pandas as pd
    core = pd.DataFrame({"date": [dt.date(2026,9,27)], "value": [10.37]})
    cost = pd.DataFrame({"date": [dt.date(2026,8,1)], "value": [2358.0]})
    result, _ = _run_hog_ratio_with_fake(core, cost)
    assert result["available"] is False
    assert result["debug"]["pigLatestDate"] == "2026-09-27" and result["debug"]["cornLatestDate"] == "2026-08-01"
    print("✅ 两个序列没有共同日期时诚实报告，debug带上各自的最新日期")


def test_hog_ratio_pig_fetch_failure_reports_which_series(monkeypatch_fetch):
    import pandas as pd
    result, calls = _run_hog_ratio_with_fake(pd.DataFrame(), pd.DataFrame(), core_exc=ConnectionError("模拟连接超时"))
    assert result["available"] is False
    assert "生猪价格(外三元)获取失败" in result["reason"] and "模拟连接超时" in result["reason"]
    assert all(c[0] == "futures_hog_core" for c in calls), "★生猪序列失败后不应该再去请求玉米"
    print("✅ 生猪价格序列获取失败时明确指出是哪个序列，且不继续请求玉米")


def test_hog_ratio_corn_fetch_failure_reports_which_series(monkeypatch_fetch):
    import datetime as dt, pandas as pd
    core = pd.DataFrame({"date": [dt.date(2026,9,27)], "value": [10.37]})
    result, _ = _run_hog_ratio_with_fake(core, pd.DataFrame(), cost_exc=ConnectionError("模拟玉米接口超时"))
    assert result["available"] is False
    assert "玉米价格获取失败" in result["reason"] and "模拟玉米接口超时" in result["reason"]
    print("✅ 玉米价格序列获取失败时明确指出是哪个序列")


def test_hog_ratio_field_mismatch_gives_column_diagnostic(monkeypatch_fetch):
    import datetime as dt, pandas as pd
    core = pd.DataFrame({"某个改名的字段": [1.0]})
    cost = pd.DataFrame({"date": [dt.date(2026,9,27)], "value": [2358.0]})  # 玉米序列本身要合法，才能走到生猪序列的字段检查
    result, _ = _run_hog_ratio_with_fake(core, cost)
    assert result["available"] is False
    assert "pigColumns" in result["debug"] and "某个改名的字段" in result["debug"]["pigColumns"]
    print("✅ 字段名对不上时给出实际列名，方便排查")



_REAL_SOW_CONTENT = ("2026年生猪行业处于产能去化周期，短期市场低位磨底。二季度末能繁母猪存栏3780万头，8月新生仔猪环比回落，"
                     "但短期出栏总量仍偏高。江西等地疫病致散户产能去化，风险猪源北调对冲供给缺口，猪价呈现“周中回落、周末反弹”震荡特征。"
                     "虽双节临近消费修复，但9-10月供给压力仍存，猪价大幅上涨条件不具备。后市需关注疫病导致的产能去化幅度及消费兑现程度，"
                     "待供需拐点显现，猪价中枢有望稳步抬升。")


def _sow_resp(items, total=None):
    return {"resultCode": 0, "resultMsg": "succeed!", "total": total if total is not None else len(items), "dataList": items}


def _sow_item(content, publish="2026-09-24 16:31", title="测试文章"):
    return {"content": content, "publishTime": publish, "title": title, "url": "https://ncp.mysteel.com/a/test.html"}


import datetime as _sow_dt
_SOW_TEST_TODAY = _sow_dt.date(2026, 9, 28)   # 固定"今天"，测试不随真实日期变化


def _run_sow_with_pages(pages, capture=None, today=None):
    """pages是{pageNo: 响应dict}，按请求里的pageNo返回对应页。today固定为2026-09-28。"""
    import fetch_data as fd_module
    real = fd_module.fetch_json_debug
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        if capture is not None:
            capture.append({"url": url, "headers": headers, "post_data": post_data})
        page = (post_data or {}).get("pageNo", 1)
        return pages.get(page, _sow_resp([])), {"httpStatus": 200}
    fd_module.fetch_json_debug = fake_fetch
    try:
        return fd_module.fetch_mysteel_sow_inventory(today=today or _SOW_TEST_TODAY)
    finally:
        fd_module.fetch_json_debug = real


def test_sow_inventory_mysteel_real_sample(monkeypatch_fetch):
    """★用户贴的真实响应里唯一展开了正文的那条(2026-09-24发布，"二季度末能繁母猪
    存栏3780万头")：验证提取出2026年二季度末=3780万头。"""
    result = _run_sow_with_pages({1: _sow_resp([_sow_item(_REAL_SOW_CONTENT, title="Mysteel解读：生猪震荡磨底阶段 重点关产能去化节奏")])})
    assert result["available"] is True, result
    assert result["value"] == 3780.0
    assert result["quarterLabel"] == "2026年二季度末" and result["quarterEnd"] == "2026-06-30"
    assert result["date"] == "2026-09-24"
    print("✅ 真实样本正确提取：2026年二季度末能繁母猪存栏3780万头")


def test_sow_inventory_picks_latest_quarter_across_articles(monkeypatch_fetch):
    """★用户强调的时间维度：把所有文章里的季度都收集起来取最新的季度末，不是取
    最新发布的那篇；同一季度多篇提到时取发布最晚的。"""
    items = [
        _sow_item("一季度末能繁母猪存栏3800万头。", "2026-05-10 09:00"),
        _sow_item("2025年四季度末能繁母猪存栏3850万头。", "2026-01-20 09:00"),
        _sow_item("二季度末能繁母猪存栏3790万头。", "2026-09-01 09:00"),   # 二季度，较早发布
        _sow_item("二季度末能繁母猪存栏3780万头。", "2026-09-24 09:00"),   # 二季度，较晚发布 → 应选这条
        _sow_item("最新的文章但没有提到具体季度存栏数据。", "2026-09-27 09:00"),  # 发布最晚，但不含数据，不能影响结果
    ]
    result = _run_sow_with_pages({1: _sow_resp(items)})
    assert result["value"] == 3780.0 and result["quarterLabel"] == "2026年二季度末", result
    assert result["quartersSeen"] == ["2026年二季度末", "2026年一季度末", "2025年四季度末"], result["quartersSeen"]
    print("✅ 取到最新季度末(2026Q2)，同季度多篇取发布最晚(3780，不是3790)，无关的最新文章不干扰")


def test_sow_inventory_q4_newer_than_q3_in_same_year(monkeypatch_fetch):
    """★用户原话："同一年中4季度的数据是最新的，在4季度末到来之前3季度末的数据是
    最新的"。用过去的年份(2025)验证：同时有三季度和四季度→选四季度；只有三季度→选三季度。"""
    q3 = _sow_item("2025年三季度末能繁母猪存栏3900万头。", "2025-10-20 09:00")
    q4 = _sow_item("2025年四季度末能繁母猪存栏3850万头。", "2026-01-20 09:00")
    both = _run_sow_with_pages({1: _sow_resp([q3, q4])}, today=_sow_dt.date(2026, 2, 15))
    only_q3 = _run_sow_with_pages({1: _sow_resp([q3])}, today=_sow_dt.date(2026, 2, 15))
    assert both["quarterLabel"] == "2025年四季度末" and both["value"] == 3850.0
    assert only_q3["quarterLabel"] == "2025年三季度末" and only_q3["value"] == 3900.0
    print("✅ 同年四季度比三季度新；四季度末数据出来之前，三季度末就是最新的")


def test_sow_inventory_infer_quarter_year_from_publish_date(monkeypatch_fetch):
    """文章只写"X季度末"不写年份时，按发布日期推断年份(季度末日期不能晚于发布日期)"""
    import datetime as dt
    import fetch_data as fd_module
    assert fd_module._infer_quarter_year(4, dt.date(2027, 1, 10)) == 2026   # 1月发布提到四季度末=去年
    assert fd_module._infer_quarter_year(2, dt.date(2026, 9, 24)) == 2026
    assert fd_module._infer_quarter_year(3, dt.date(2026, 9, 24)) == 2025   # 2026年三季度末9月30日还没到
    assert fd_module._infer_quarter_year(3, dt.date(2026, 10, 20)) == 2026
    print("✅ 年份推断正确(跨年的四季度、还没到的三季度都处理对了)")


def test_sow_inventory_forecast_and_target_values_ignored(monkeypatch_fetch):
    """★预测/目标值不是实际数据："预计四季度末能繁母猪存栏将降至3700万头"要丢掉；
    显式写了未来年份的季度末(还没到)也要丢掉。"""
    items = [
        _sow_item("预计四季度末能繁母猪存栏将降至3700万头。", "2026-09-24 09:00"),
        _sow_item("2099年四季度末能繁母猪存栏3000万头。", "2026-09-24 09:00"),
        _sow_item("二季度末能繁母猪存栏3780万头。", "2026-09-20 09:00"),
    ]
    result = _run_sow_with_pages({1: _sow_resp(items)})
    assert result["value"] == 3780.0 and result["quarterLabel"] == "2026年二季度末", result
    only_forecast = _run_sow_with_pages({1: _sow_resp(items[:2])})
    assert only_forecast["available"] is False
    print("✅ 预测值和未来季度末被正确丢掉，只剩预测值时诚实报告没有数据")


def test_sow_inventory_change_amount_not_mistaken_for_stock(monkeypatch_fetch):
    """★"二季度末能繁母猪存栏较一季度末减少20万头"里的20万头是变动量，不是存栏量；
    落在1000~10000万头合理范围之外的数值也不认。"""
    items = [
        _sow_item("二季度末能繁母猪存栏较一季度末减少20万头。", "2026-09-24 09:00"),
        _sow_item("二季度末能繁母猪存栏20万头。", "2026-09-24 09:00"),
    ]
    result = _run_sow_with_pages({1: _sow_resp(items)})
    assert result["available"] is False, result
    ok = _run_sow_with_pages({1: _sow_resp(items + [_sow_item("二季度末能繁母猪存栏3780万头，较一季度末减少20万头。", "2026-09-24 09:00")])})
    assert ok["value"] == 3780.0, ok
    print("✅ 变动量(20万头)和范围外数值不被当成存栏量；同一句里带变动量时仍取到真正的存栏量3780")


def test_sow_inventory_paginates_until_exhausted(monkeypatch_fetch):
    """搜索结果有多页(total=41，每页20条)时，翻页取完(最多3页)——最新季度只出现在
    第3页时也能拿到。"""
    page1 = [_sow_item(f"无关文章{i}", "2026-09-01 09:00") for i in range(20)]
    page2 = [_sow_item(f"无关文章{i}", "2026-09-01 09:00") for i in range(20)]
    page3 = [_sow_item("二季度末能繁母猪存栏3780万头。", "2026-09-24 09:00")]
    captured = []
    result = _run_sow_with_pages({1: _sow_resp(page1, 41), 2: _sow_resp(page2, 41), 3: _sow_resp(page3, 41)}, capture=captured)
    assert [c["post_data"]["pageNo"] for c in captured] == [1, 2, 3], [c["post_data"]["pageNo"] for c in captured]
    assert result["value"] == 3780.0
    print("✅ 翻页取完3页，只出现在第3页的数据也能拿到，且不会多翻")


def test_sow_inventory_request_shape(monkeypatch_fetch):
    """★请求跟用户实际抓包验证过的请求逐项对照：searchArticle端点、
    query="季度末能繁母猪存栏"、sortType=complex、platform=pc、pageNo=1、pageSize=20，
    字段集合完全一致(不多不少)；时间窗口是一年(抓包是2025-09-27到2026-09-27=365天，
    之前我写成150天没被真实接口验证过)；请求头带token=-1。一页取完时不多翻页。"""
    import datetime as dt
    captured = []
    _run_sow_with_pages({1: _sow_resp([_sow_item(_REAL_SOW_CONTENT)])}, capture=captured)
    assert len(captured) == 1, "结果不足一页时不应该继续翻页"
    c = captured[0]
    assert c["url"] == "https://search.mysteel.com/searchapi/search/searchArticle"
    p = c["post_data"]
    assert set(p) == {"query", "startTime", "endTime", "sortType", "platform", "pageNo", "pageSize"}, set(p)
    assert (p["query"], p["sortType"], p["platform"], p["pageNo"], p["pageSize"]) == ("季度末能繁母猪存栏", "complex", "pc", 1, 20)
    days = (dt.datetime.strptime(p["endTime"][:10], "%Y-%m-%d") - dt.datetime.strptime(p["startTime"][:10], "%Y-%m-%d")).days
    assert days == 365, f"★时间窗口应该是365天(跟用户抓包一致)，实际{days}天"
    assert p["startTime"].endswith("00:00:00") and c["headers"]["token"] == "-1"
    print("✅ 请求逐项对照抓包一致：端点/关键词/排序/平台/分页/字段集合/一年窗口/token")


def test_sow_inventory_stale_old_data_is_rejected_not_shown(monkeypatch_fetch):
    """★用户指出的问题：今天是2026-09-28，二季度末数据已发布、三季度末还没到，绝不能把
    2025年的陈年数据当成最新值填进去。只搜到2025年数据(样本2的2025年三季度末、样本8的
    2025年一季度末)时，必须拒绝并说明原因，而不是取"找到的最新一期"。"""
    items = [_sow_item(text, pub.isoformat() + " 12:00") for name, pub, text, _ in _REAL_SOW_SAMPLES if name.startswith(("样本2", "样本8"))]
    result = _run_sow_with_pages({1: _sow_resp(items)})
    assert result["available"] is False, result
    assert "较旧" in result["reason"] and "2026年二季度末" in result["reason"], result["reason"]
    assert result["debug"]["quartersSeen"] == ["2025年三季度末", "2025年一季度末"], result["debug"]
    print("✅ 只搜到2025年的旧数据时拒绝展示，并说明今天最近已完成的季度是2026年二季度末")


def test_sow_inventory_falls_back_to_previous_quarter_only(monkeypatch_fetch):
    """★用户的规则："二季度末找不到，可以找一季度末，但不至于是上一年的数据"。
    只有2026年一季度末的文章(样本3~7)时采用一季度末；二季度末也在时优先二季度末。"""
    q1_items = [_sow_item(text, pub.isoformat() + " 12:00") for name, pub, text, _ in _REAL_SOW_SAMPLES if name.startswith(("样本3", "样本4", "样本5", "样本6", "样本7"))]
    only_q1 = _run_sow_with_pages({1: _sow_resp(q1_items)})
    assert only_q1["available"] is True and only_q1["quarterLabel"] == "2026年一季度末" and only_q1["value"] == 3904.0, only_q1
    with_q2 = _run_sow_with_pages({1: _sow_resp(q1_items + [_sow_item("二季度末能繁母猪存栏3780万头。", "2026-09-24 09:00")])})
    assert with_q2["quarterLabel"] == "2026年二季度末" and with_q2["value"] == 3780.0
    print("✅ 二季度末找不到时退到一季度末(3904)；二季度末在时优先二季度末(3780)")


def test_sow_inventory_acceptance_window_rolls_with_calendar(monkeypatch_fetch):
    """接受的季度随日历滚动：三季度末(9-30)一过，最近已完成的季度变成三季度，此时二季度末
    (三季度数据还没发布)仍可接受，一季度末就太旧了；到了年底四季度也过了，二季度末也不再接受。"""
    q2 = _sow_item("二季度末能繁母猪存栏3780万头。", "2026-09-24 09:00")
    q1 = _sow_item("2026年一季度末，全国能繁母猪存栏3904万头。", "2026-04-17 09:00")
    D = _sow_dt.date
    assert _run_sow_with_pages({1: _sow_resp([q2])}, today=D(2026, 10, 5))["quarterLabel"] == "2026年二季度末"
    assert _run_sow_with_pages({1: _sow_resp([q1])}, today=D(2026, 10, 5))["available"] is False
    assert _run_sow_with_pages({1: _sow_resp([q2])}, today=D(2027, 1, 5))["available"] is False
    print("✅ 接受窗口随日历滚动：10月初二季度末仍可用、一季度末过旧；次年1月二季度末也过旧")


def test_latest_completed_quarter_helper(monkeypatch_fetch):
    import datetime as dt
    import fetch_data as fd_module
    D = dt.date
    assert fd_module._latest_completed_quarter(D(2026, 9, 28)) == (2026, 2)   # 三季度末9-30还没到
    assert fd_module._latest_completed_quarter(D(2026, 9, 30)) == (2026, 3)
    assert fd_module._latest_completed_quarter(D(2027, 1, 5)) == (2026, 4)
    assert fd_module._latest_completed_quarter(D(2026, 1, 2)) == (2025, 4)
    assert fd_module._previous_quarter((2026, 2)) == (2026, 1) and fd_module._previous_quarter((2026, 1)) == (2025, 4)
    print("✅ 最近已完成季度/上一季度计算正确(含跨年)")


def test_sow_inventory_failure_modes_give_diagnostics(monkeypatch_fetch):
    """空结果/接口异常/没有可提取内容，都诚实报告；没有可提取内容时debug带第一条样本。"""
    import fetch_data as fd_module
    empty = _run_sow_with_pages({1: _sow_resp([])})
    assert empty["available"] is False and "为空" in empty["reason"]
    bad = _run_sow_with_pages({1: {"resultCode": 1, "resultMsg": "err"}})
    assert bad["available"] is False and "resultCode=1" in bad["reason"]
    nothing = _run_sow_with_pages({1: _sow_resp([_sow_item("完全不相关的内容")])})
    assert nothing["available"] is False and "firstItemSample" in nothing["debug"] and nothing["debug"]["itemsChecked"] == 1
    real = fd_module.fetch_json_debug
    fd_module.fetch_json_debug = lambda *a, **k: (None, {"httpStatus": None, "error": "连接超时"})
    try:
        none_resp = fd_module.fetch_mysteel_sow_inventory()
    finally:
        fd_module.fetch_json_debug = real
    assert none_resp["available"] is False and "无返回" in none_resp["reason"]
    print("✅ 空结果/接口异常/无可提取内容/网络无响应都诚实报告")


import datetime as _sow_dt
_SD = _sow_dt.date
_REAL_SOW_SAMPLES = [
 ("样本1 2026-09-24 二季度末(写法A:季度末能繁母猪存栏X)", _SD(2026,9,24),
  "2026年生猪行业处于产能去化周期，短期市场低位磨底。二季度末能繁母猪存栏3780万头，8月新生仔猪环比回落，但短期出栏总量仍偏高。江西等地疫病致散户产能去化，风险猪源北调对冲供给缺口，猪价呈现“周中回落、周末反弹”震荡特征。虽双节临近消费修复，但9-10月供给压力仍存，猪价大幅上涨条件不具备。后市需关注疫病导致的产能去化幅度及消费兑现程度，待供需拐点显现，猪价中枢有望稳步抬升。",
  [(2026,2,3780.0)]),
 ("样本2 2025-10-20 三季度末(生猪总存栏在前，其中能繁母猪在后)", _SD(2025,10,20),
  "三季度末，全国生猪存栏43680万头，同比增加986万头，增长2.3%，环比增加1233万头，增长2.9%其中，能繁母猪存栏4035万头，同比减少28万头，下降0.7%，环比减少9万头，略降0.2% 牛羊生产基本稳定前三季度，全国肉牛出栏3564万头，同比增加71万头，增长2.0%；牛肉产量550万吨，同比增加18万吨，增长3.3%；牛奶产量2921万吨，同比增加19万吨，增长0.7%。",
  [(2025,3,4035.0)]),
 ("样本3 2026-04-17 2026年一季度末(全国能繁母猪存栏X，后带基准值3900)", _SD(2026,4,17),
  "最新官方数据显示，2026年一季度末，全国能繁母猪存栏3904万头，环比减少1.44%，同比下降3.3%这一数字仅略高于3900万头的传统正常保有量，虽处于产能调控的绿色合理区域，但尚未达到预期缩减目标，是解读本轮猪价反弹及预判下半年行情的核心依据。",
  [(2026,1,3904.0)]),
 ("样本4 2026-04-17 一季度末(生猪总存栏在前，其中能繁母猪在后)", _SD(2026,4,17),
  "一季度，全国生猪出栏20026万头，增长2.8%猪肉产量1669万吨，增长4.2%一季度末，全国生猪存栏42358万头，增长1.5%其中，能繁母猪存栏3904万头，下降3.3%，目前为正常保有量的100.1% 牛羊生产基本稳定。",
  [(2026,1,3904.0)]),
 ("样本5 2026-04-24 截至2026年第一季度末(存栏量降至X)", _SD(2026,4,24),
  "截至2026年第一季度末，全国能繁母猪存栏量降至3904万头，较2025年6月的高点减少了139万头，已连续9个月下降当前存栏量处于国家设定的3900万头正常保有量的101%左右，告别了此前明显偏高的格局，回归合理区间，为后续猪价企稳回升奠定了坚实基础 2026年以来生猪期货主力合约呈“探底 -反弹”走势。",
  [(2026,1,3904.0)]),
 ("样本6 2026-04-27 2026年一季度末(全国能繁母猪存栏X)", _SD(2026,4,27),
  "2026年一季度末，全国能繁母猪存栏3904万头，环比、同比均有所下降，但仍略高于正常保有量，去化幅度未达预期规模场以种群结构优化为主，去化力度相对温和；散户补栏意愿低迷，后备母猪交易清淡，行业对后市整体持谨慎态度产能去化不到位，意味着未来半年商品猪供给仍将维持高位，市场难以快速摆脱供应过剩局面 仔猪市场同样维持弱势运行。",
  [(2026,1,3904.0)]),
 ("样本7 2026-05-21 能繁母猪存栏在前，2026年一季度末存栏量仍有X，后带基准值3650", _SD(2026,5,21),
  "国内能繁母猪存栏自2025年7月持续去化，但2026年一季度末存栏量仍有3904万头，显著高于3650万头的合理保有量，产能富余的基本面并未彻底改善按照10个月生猪养殖传导周期，前期高位产能持续释放，带动5月商品猪出栏量维持高位同时行业养殖水平提升，PSY升至24头以上，同等存栏规模下生猪出栏基数进一步扩大叠加最新一周的全国生猪出栏均重123.2公斤，市场猪肉供给十分充裕为对冲行业深度亏损、稳定市场情绪，5月中央启动冻猪肉双向轮换操作，配套地方收储举措，对猪价形成底部支撑，但收储规模有限，仅能防范行情非理性下跌，无法逆转整体供给宽松格局。",
  [(2026,1,3904.0)]),
 ("样本8 2025-09-28 历史回顾(先有3986/4080两个非季度末数字，再2025年一季度末仍维持在X)", _SD(2025,9,28),
  "2024年5月起，能繁母猪存栏量进入持续回升通道，从3986万头逐步攀升至11月的4080万头，即便到2025年一季度末，仍维持在4039万头的高位，同比增长1.17%与此同时，养殖技术的提升进一步放大了产能——当前第一梯队集团厂的PSY（每头母猪年提供断奶仔猪数）已达到32头左右，较此前提升0.5-1头，仔猪产能持续释放 需求端的疲软则加剧了价格压力仔猪育肥存在6个月左右的周期，现阶段补栏的仔猪将推迟至2026年春节后出栏，既错过春节消费旺季，又将面临节后淡季价格走弱的风险。",
  [(2025,1,4039.0)]),
]


def test_sow_inventory_eight_real_articles_all_recognized(monkeypatch_fetch):
    """★用户贴的8条真实Mysteel正文，逐条验证提取结果。这8条的写法各不相同：
    ①"季度末能繁母猪存栏X"(样本1)；②先写生猪总存栏再写"其中，能繁母猪存栏X"，
    中间隔得很远(样本2、4)；③"存栏量降至X"，"降至"里有"降"字(样本5)；
    ④顺序反过来"能繁母猪存栏自…，但2026年一季度末存栏量仍有X"(样本7、8)；
    ⑤后面带"3900万头的正常保有量"这种基准值(样本3、5、7)。
    ★第一版正则(要求季度末后面紧跟能繁母猪存栏)在这8条里只识别出3条。"""
    import datetime as dt
    import fetch_data as fd_module
    today = dt.date(2026, 9, 28)
    for name, pub, text, expected in _REAL_SOW_SAMPLES:
        got = fd_module._extract_sow_candidates(text, pub, today)
        assert got == expected, f"★{name}: 期望{expected}，实际{got}"
    print(f"✅ 8条真实正文全部正确识别(第一版逻辑只能识别3条)")


def test_sow_inventory_other_indicators_not_mistaken_for_sow(monkeypatch_fetch):
    """★别的指标的"XXXX万头"不能被当成能繁母猪存栏：肉牛出栏3564万头落在1000~10000
    的合理范围内，只靠范围过滤挡不住，必须靠"主语"判断(样本2里就有这个数)。
    生猪总存栏43680、生猪出栏20026这类更是不能取。"""
    import datetime as dt
    import fetch_data as fd_module
    today = dt.date(2026, 9, 28)
    pub = dt.date(2025, 10, 20)
    assert fd_module._extract_sow_candidates("三季度末，全国肉牛出栏3564万头，同比增加71万头。", pub, today) == []
    assert fd_module._extract_sow_candidates("三季度末，全国生猪存栏43680万头，同比增加986万头。", pub, today) == []
    assert fd_module._extract_sow_candidates("一季度末，全国生猪出栏5000万头。", pub, today) == []
    print("✅ 肉牛出栏(3564，在合理范围内)、生猪总存栏、生猪出栏都不会被误认成能繁母猪存栏")


def test_sow_inventory_level_verbs_allowed_but_change_amounts_rejected(monkeypatch_fetch):
    """★"降至/增至/升至3904万头"是到达某个水平(要放行)；"较上季度减少20万头"、
    "同比减少28万头"是变动量(要拒绝)；"高于3650万头的合理保有量"是基准值(要拒绝)。"""
    import datetime as dt
    import fetch_data as fd_module
    today = dt.date(2026, 9, 28)
    pub = dt.date(2026, 4, 24)
    f = lambda t: fd_module._extract_sow_candidates(t, pub, today)
    assert f("一季度末能繁母猪存栏降至3904万头。") == [(2026, 1, 3904.0)]
    assert f("一季度末能繁母猪存栏增至3904万头。") == [(2026, 1, 3904.0)]
    assert f("一季度末能繁母猪存栏较上年减少28万头。") == []
    assert f("一季度末能繁母猪存栏同比减少2800万头。") == []      # 数值在范围内也要靠措辞拒绝
    assert f("一季度末能繁母猪存栏显著高于3650万头的合理保有量。") == []
    print("✅ 降至/增至放行，变动量和基准值拒绝(数值即使落在合理范围内也一样)")


def test_sow_inventory_full_flow_with_eight_real_articles(monkeypatch_fetch):
    """★端到端：把8条真实文章(各自的发布时间)放进一次搜索响应，最终应选出最新的
    2026年二季度末3780万头，并且收集到的季度末包括2026Q2/2026Q1/2025Q3/2025Q1。"""
    items = [_sow_item(text, pub.isoformat() + " 12:00") for _, pub, text, _ in _REAL_SOW_SAMPLES]
    result = _run_sow_with_pages({1: _sow_resp(items)})
    assert result["available"] is True, result
    assert result["value"] == 3780.0 and result["quarterLabel"] == "2026年二季度末", result
    assert result["quartersSeen"] == ["2026年二季度末", "2026年一季度末", "2025年三季度末", "2025年一季度末"], result["quartersSeen"]
    print("✅ 8条真实文章端到端：选出2026年二季度末3780万头，收集到4个不同的季度末")


def test_sow_inventory_next_quarter_takes_over_once_published(monkeypatch_fetch):
    """★用户强调的时间维度：二季度末数据是当前最新；等三季度末数据发布后(一篇
    新文章写"2026年三季度末，全国能繁母猪存栏3700万头")，最新就应该自动变成三季度末。
    用显式年份+假的"今天"无法在这里改，所以直接测提取函数：today在2026-10-25时
    三季度末已过，应被识别；today在2026-09-28时三季度末还没到，应被丢掉。"""
    import datetime as dt
    import fetch_data as fd_module
    text = "2026年三季度末，全国能繁母猪存栏3700万头，环比减少80万头。"
    pub = dt.date(2026, 10, 25)
    assert fd_module._extract_sow_candidates(text, pub, dt.date(2026, 10, 25)) == [(2026, 3, 3700.0)]
    assert fd_module._extract_sow_candidates(text, pub, dt.date(2026, 9, 28)) == []
    print("✅ 三季度末数据发布后自动成为最新；发布之前(季度末还没到)不会被提前采用")


def _run_mysteel_fn(fn_name, items):
    """用给定的文章列表(每篇是dict)模拟Mysteel搜索接口，运行指定的抓取函数。"""
    import fetch_data as fd_module
    real = fd_module.fetch_json_debug
    fd_module.fetch_json_debug = lambda *a, **k: ({"resultCode": 0, "total": len(items), "dataList": items}, {"httpStatus": 200})
    try:
        return getattr(fd_module, fn_name)()
    finally:
        fd_module.fetch_json_debug = real


def test_plausibility_helpers(monkeypatch_fetch):
    import fetch_data as fd_module
    assert fd_module._plausibility_problem("mealStock", 117.32) is None
    assert "超出合理范围" in fd_module._plausibility_problem("mealStock", 0.7)
    assert "无效" in fd_module._plausibility_problem("mealStock", float("nan"))
    assert fd_module._looks_like_change("较上周增加") and fd_module._looks_like_change("周环比下降")
    assert not fd_module._looks_like_change("为") and not fd_module._looks_like_change("降至") and not fd_module._looks_like_change("约")
    print("✅ 合理范围判断和变动量识别正确(\"降至\"这种到达某水平的写法不算变动量)")


def test_crush_rate_out_of_range_rejected(monkeypatch_fetch):
    for text in ["今日全国动态全样本油厂开机率为1.14%", "开机率为150%"]:
        r = _run_mysteel_fn("fetch_mysteel_crush_rate", [{"content": text, "publishTime": "2026-09-28 18:00"}])
        assert r["available"] is False and "不合理" in r["reason"], r
    ok = _run_mysteel_fn("fetch_mysteel_crush_rate", [{"content": "开机率为1.14%", "publishTime": "2026-09-28"}, {"content": "开机方面，今日全国动态全样本油厂开机率为68.84%，较前一日下降1.14%。", "publishTime": "2026-09-23"}])
    assert ok["available"] is True and ok["value"] == 68.84
    print("✅ 开机率超出10~100%合理范围时丢弃，后面合理的仍能取到")


def test_poultry_profit_out_of_range_rejected(monkeypatch_fetch):
    r = _run_mysteel_fn("fetch_mysteel_poultry_profit", [{"content": "白羽肉鸡平均理论养殖亏损99元/只", "publishTime": "2026-09-24"}])
    assert r["available"] is False and "不合理" in r["reason"], r
    ok = _run_mysteel_fn("fetch_mysteel_poultry_profit", [{"content": "亏损99元/只", "publishTime": "2026-09-24"}, {"content": "本周白羽肉鸡平均理论养殖亏损4.18元/只", "publishTime": "2026-09-17"}])
    assert ok["available"] is True and ok["value"] == -4.18
    print("✅ 养殖利润超出±20元/只时丢弃，后面合理的仍能取到")


def test_rmspread_change_range_not_mistaken_for_spread(monkeypatch_fetch):
    """★"价差下跌，较前一日跌10-20元/吨"里的10-20是变动幅度，中点15不是价差(合理范围100~3000)；
    多城市格式里个别离谱的城市值单独丢掉，不拉偏平均值。"""
    r = _run_mysteel_fn("fetch_mysteel_rmspread", [{"content": "豆菜粕现货价差下跌，较前一日跌10-20元/吨。", "publishTime": "2026-09-28"}])
    assert r["available"] is False and "不合理" in r["reason"], r
    ok = _run_mysteel_fn("fetch_mysteel_rmspread", [{"content": "豆菜粕现货价差下跌，较前一日跌10-20元/吨。", "publishTime": "2026-09-28"},
                                                    {"content": "现货价差下跌，区间为480-520元/吨，较前一日跌10-20元/吨。", "publishTime": "2026-09-27"}])
    assert ok["available"] is True and ok["value"] == 500.0, ok
    city = _run_mysteel_fn("fetch_mysteel_rmspread", [{"content": "广东价差740元/吨；广西价差10元/吨；南通价差810元/吨。", "publishTime": "2026-09-28"}])
    assert city["available"] is True and city["citySamples"] == [740.0, 810.0] and city["value"] == 775.0, city
    print("✅ 变动幅度区间(10-20)不被当成价差；离谱的单个城市值被剔除，不拉偏平均")


def test_arrival_forecast_change_and_out_of_range_rejected(monkeypatch_fetch):
    """"到港较上月减少300万吨"是变动量；"到港30万吨"超出合理范围(200~2000)。"""
    for text in ["2026年10月国内全样本油厂大豆到港较上月减少300万吨", "2026年10月国内全样本油厂大豆到港30万吨"]:
        r = _run_mysteel_fn("fetch_mysteel_arrival_forecast", [{"content": text, "publishTime": "2026-09-24"}])
        assert r["available"] is False and "不合理" in r["reason"], f"{text}: {r}"
    ok = _run_mysteel_fn("fetch_mysteel_arrival_forecast", [{"content": "2026年10月国内全样本油厂大豆到港较上月减少300万吨", "publishTime": "2026-09-25"},
                                                            {"content": "Mysteel预估2026年10月国内全样本油厂大豆到港约854.10万吨", "publishTime": "2026-09-24"}])
    assert ok["available"] is True and ok["value"] == 854.10
    print("✅ 到港的变动量/超范围数值被丢弃，后面真正的到港预报仍能取到")


def test_export_inspections_limit_raised_and_truncation_detected(monkeypatch_fetch):
    """★审计发现：$limit=50，用户页面上"当周记录数"正好是50，当周总量被截断。现在上限放到5000；
    记录数触达上限且全部属于同一周时拒绝展示；加总结果也要过合理范围。"""
    import fetch_data as fd_module
    urls = []
    real = fd_module.fetch_json_debug
    def fake(url, headers=None, retries=3, timeout=20, post_data=None):
        urls.append(url)
        return [{"date": "2026-09-17T00:00:00.000", "grain": "SOYBEANS", "mt": "1000"}] * fd_module.EXPORT_INSPECTIONS_LIMIT, {"httpStatus": 200}
    fd_module.fetch_json_debug = fake
    try:
        r = fd_module.fetch_us_export_inspections()
    finally:
        fd_module.fetch_json_debug = real
    assert "limit=5000" in urls[0].replace("%24", "$").replace("$limit", "limit"), urls[0]
    assert r["available"] is False and "触达查询上限" in r["reason"], r
    tiny = _run_export([{"date": "2026-09-17T00:00:00.000", "grain": "SOYBEANS", "mt": "10"}])
    assert tiny["available"] is False and "不合理" in tiny["reason"], tiny
    ok = _run_export([{"date": "2026-09-17T00:00:00.000", "grain": "SOYBEANS", "mt": "450000"}, {"date": "2026-09-17T00:00:00.000", "grain": "SOYBEANS", "mt": "223000"}])
    assert ok["available"] is True and ok["quantityMetricTons"] == 673000.0
    print("✅ 出口检验查询上限放宽到5000，触达上限时拒绝展示；加总结果异常小时拒绝；正常情况不受影响")


def _run_export(rows):
    import fetch_data as fd_module
    real = fd_module.fetch_json_debug
    fd_module.fetch_json_debug = lambda *a, **k: (rows, {"httpStatus": 200})
    try:
        return fd_module.fetch_us_export_inspections()
    finally:
        fd_module.fetch_json_debug = real


def test_hog_ratio_each_price_must_be_plausible(monkeypatch_fetch):
    """比值本身在合理范围，但两个价格取错了(比如取错序列)时也要拒绝：
    生猪价格45元/公斤、玉米10000元/吨 → 比值4.5看起来正常，但两个价格都荒谬。"""
    import datetime as dt, pandas as pd
    core = pd.DataFrame({"date": [dt.date(2026, 9, 27)], "value": [45.0]})
    cost = pd.DataFrame({"date": [dt.date(2026, 9, 27)], "value": [10000.0]})
    result, _ = _run_hog_ratio_with_fake(core, cost)
    assert result["available"] is False and "生猪价格" in result["reason"], result
    print("✅ 猪粮比：比值正常但价格荒谬时也拒绝(可能取错了序列)")


def test_frontend_and_backend_plausible_ranges_are_identical(monkeypatch_fetch):
    """★前端SANITY_RANGES和后端PLAUSIBLE_RANGES是同一张表的两份拷贝，必须一致——以后改了一边
    忘了另一边，这个测试会直接报错(否则两层防线的判断标准不一样，会出现后端放行前端拦截的怪事)。"""
    import json, os, re
    import fetch_data as fd_module
    html = open(os.path.join(os.path.dirname(__file__), "index.html"), encoding="utf-8").read()
    m = re.search(r"const SANITY_RANGES = (\{.*?\});", html, re.S)
    assert m, "index.html里找不到SANITY_RANGES"
    frontend = json.loads(m.group(1))
    backend = {k: [v[0], v[1], v[2]] for k, v in fd_module.PLAUSIBLE_RANGES.items()}
    assert set(frontend) == set(backend), (set(frontend) ^ set(backend))
    for k in backend:
        assert [float(frontend[k][0]), float(frontend[k][1]), frontend[k][2]] == backend[k], f"{k}: 前端{frontend[k]} 后端{backend[k]}"
    print(f"✅ 前后端合理范围表完全一致({len(backend)}个指标)")


import datetime as _meal_dt
_MEAL_TEST_TODAY = _meal_dt.date(2026, 9, 28)   # 固定"今天"(这次对话的真实日期)，测试不随真实日期变化
_REAL_MEAL_CONTENT = ("据Mysteel数据，2026年第38周全国主要油厂大豆库存上升，豆粕库存上升，未执行合同下降。其中大豆库存856.85万吨，"
                      "较上周增加24.66万吨；豆粕库存117.32万吨，较上周增加6.33万吨；未执行合同459.91万吨，较上周减少78.76万吨；"
                      "豆粕表观消费量178.08万吨，较上周减少4.19万吨。")
_MEAL_TITLE = "Mysteel数据：全国主要区域大豆及豆粕库存统计"


def _meal_item(content, publish, title=_MEAL_TITLE):
    return {"content": content, "publishTime": publish, "title": title, "url": "https://ncp.mysteel.com/a/meal.html"}


def _weekly_meal_article(week, stock, publish):
    """仿照用户贴的真实文章格式造一期每周统计(只改周数、库存、发布日期)。"""
    return _meal_item(f"据Mysteel数据，2026年第{week}周全国主要油厂大豆库存上升，豆粕库存上升，未执行合同下降。其中大豆库存856.85万吨，"
                      f"较上周增加24.66万吨；豆粕库存{stock}万吨，较上周增加6.33万吨；未执行合同459.91万吨，较上周减少78.76万吨。", publish + " 16:02")


def _run_meal_with_pages(pages, capture=None, today=None):
    """pages是{pageNo: 响应dict}，按请求里的pageNo返回对应页；today默认固定为2026-09-28。"""
    import fetch_data as fd_module
    real = fd_module.fetch_json_debug
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        if capture is not None:
            capture.append({"url": url, "headers": headers, "post_data": post_data})
        return pages.get((post_data or {}).get("pageNo", 1), _sow_resp([])), {"httpStatus": 200}
    fd_module.fetch_json_debug = fake_fetch
    try:
        return fd_module.fetch_mysteel_meal_stock(today=today or _MEAL_TEST_TODAY)
    finally:
        fd_module.fetch_json_debug = real


def test_meal_stock_real_weekly_article(monkeypatch_fetch):
    """★用户贴的真实文章("全国主要区域大豆及豆粕库存统计"，2026-09-21发布)：同一段话里有大豆库存856.85、
    豆粕库存117.32、未执行合同459.91、豆粕表观消费量178.08四个数，必须只取豆粕库存117.32。"""
    r = _run_meal_with_pages({1: _sow_resp([_meal_item(_REAL_MEAL_CONTENT, "2026-09-21 16:02")])})
    assert r["available"] is True, r
    assert r["value"] == 117.32 and r["date"] == "2026-09-21" and r["weekLabel"] == "2026年第38周", r
    print("✅ 真实文章正确取到豆粕库存117.32万吨(2026年第38周)，没有被大豆库存/合同/表观消费量干扰")


def test_meal_stock_takes_latest_article_across_pages_not_first_match(monkeypatch_fetch):
    """★一年窗口搜出几十篇每周一期的文章，排序是按相关度不是时间：最新一期(第38周117.32)放在第3页，
    前两页全是旧的周报——必须翻页收齐后按发布日期取最新，不能取"第一个匹配"(旧版的做法)。"""
    old = [_weekly_meal_article(i % 52 + 1, 100 + i, (_meal_dt.date(2025, 10, 6) + _meal_dt.timedelta(days=7 * i)).isoformat()) for i in range(40)]
    latest = [_weekly_meal_article(36, 112.0, "2026-09-07"), _weekly_meal_article(38, 117.32, "2026-09-21"), _weekly_meal_article(37, 110.99, "2026-09-14")]
    captured = []
    r = _run_meal_with_pages({1: _sow_resp(old[:20], 43), 2: _sow_resp(old[20:], 43), 3: _sow_resp(latest, 43)}, capture=captured)
    assert [c["post_data"]["pageNo"] for c in captured] == [1, 2, 3]
    assert r["available"] is True and r["value"] == 117.32 and r["date"] == "2026-09-21", r
    print("✅ 翻页收齐3页，最新一期在第3页也能选中(按发布日期，不是第一个匹配)")


def test_meal_stock_stale_data_rejected(monkeypatch_fetch):
    """★新鲜度限制(周度数据，最多21天)：只搜到旧数据时拒绝；边界：21天前接受，22天前拒绝。"""
    def run(publish):
        return _run_meal_with_pages({1: _sow_resp([_weekly_meal_article(30, 105.0, publish)])})
    assert run("2026-09-07")["available"] is True                      # 21天前：接受
    r22 = run("2026-09-06")                                            # 22天前：拒绝
    assert r22["available"] is False and "新鲜度限制" in r22["reason"] and "22天前" in r22["reason"], r22
    old = run("2025-10-06")                                            # 一年前的旧一期
    assert old["available"] is False and "新鲜度限制" in old["reason"]
    print("✅ 新鲜度限制生效：21天内接受，22天和一年前的旧数据拒绝并说明原因")


def test_meal_stock_requires_national_scope(monkeypatch_fetch):
    """标题和正文都没有"全国"字样时不确认是全国口径，拒绝；标题有"全国"就放行。"""
    body = "豆粕库存117.32万吨，较上周增加6.33万吨。"
    no_scope = _run_meal_with_pages({1: _sow_resp([_meal_item(body, "2026-09-21 16:02", title="某篇文章")])})
    assert no_scope["available"] is False and "全国" in no_scope["reason"], no_scope
    with_scope = _run_meal_with_pages({1: _sow_resp([_meal_item(body, "2026-09-21 16:02")])})
    assert with_scope["available"] is True and with_scope["value"] == 117.32
    print("✅ 没有'全国'字样时拒绝，标题有'全国'时放行")


def test_meal_stock_region_other_subject_and_change_rejected(monkeypatch_fetch):
    """★区域数据("华东地区豆粕库存25万吨")、别的指标("豆粕库存上升，大豆库存856.85万吨")、变动量
    ("豆粕库存较上周增加0.7万吨"，用户遇到的真实错误)都不能被当成全国豆粕库存。"""
    for bad in ["华东地区豆粕库存25万吨。", "全国豆粕库存上升，大豆库存856.85万吨。", "全国豆粕库存较上周增加0.7万吨。", "全国豆粕库存0.7万吨。"]:
        r = _run_meal_with_pages({1: _sow_resp([_meal_item(bad, "2026-09-21 16:02")])})
        assert r["available"] is False and r["debug"]["rejectedImplausible"], f"「{bad}」: {r}"
    mixed = _run_meal_with_pages({1: _sow_resp([_meal_item("全国豆粕库存较上周增加0.7万吨。", "2026-09-24 10:00"), _meal_item(_REAL_MEAL_CONTENT, "2026-09-21 16:02")])})
    assert mixed["available"] is True and mixed["value"] == 117.32, mixed
    print("✅ 区域数据/别的指标/变动量(0.7)都被丢弃，后面真正的全国库存(117.32)仍能取到")


def test_meal_stock_request_matches_user_capture(monkeypatch_fetch):
    """★请求跟用户抓包逐项对照：query="全国主要区域大豆"、sortType=complex、platform=pc、pageNo=1、
    pageSize=20，字段集合完全一致；一年窗口(2025-09-28到2026-09-28=365天)；token=-1；不足一页时不多翻页。"""
    import datetime as dt
    captured = []
    _run_meal_with_pages({1: _sow_resp([_meal_item(_REAL_MEAL_CONTENT, "2026-09-21 16:02")])}, capture=captured)
    assert len(captured) == 1
    c = captured[0]; p = c["post_data"]
    assert c["url"] == "https://search.mysteel.com/searchapi/search/searchArticle"
    assert set(p) == {"query", "startTime", "endTime", "sortType", "platform", "pageNo", "pageSize"}, set(p)
    assert (p["query"], p["sortType"], p["platform"], p["pageNo"], p["pageSize"]) == ("全国主要区域大豆", "complex", "pc", 1, 20)
    days = (dt.datetime.strptime(p["endTime"][:10], "%Y-%m-%d") - dt.datetime.strptime(p["startTime"][:10], "%Y-%m-%d")).days
    assert days == 365 and p["startTime"] == "2025-09-28 00:00:00", (days, p["startTime"])
    assert c["headers"]["token"] == "-1"
    print("✅ 请求逐项对照抓包一致：端点/关键词/排序/平台/分页/字段集合/一年窗口(起点2025-09-28)/token")


def test_meal_stock_failure_modes_give_diagnostics(monkeypatch_fetch):
    import fetch_data as fd_module
    empty = _run_meal_with_pages({1: _sow_resp([])})
    assert empty["available"] is False and "为空" in empty["reason"]
    bad = _run_meal_with_pages({1: {"resultCode": 1, "resultMsg": "err"}})
    assert bad["available"] is False and "resultCode=1" in bad["reason"]
    nothing = _run_meal_with_pages({1: _sow_resp([_meal_item("完全不相关的内容", "2026-09-21 16:02")])})
    assert nothing["available"] is False and nothing["debug"]["itemsChecked"] == 1 and "firstItemSample" in nothing["debug"]
    real = fd_module.fetch_json_debug
    fd_module.fetch_json_debug = lambda *a, **k: (None, {"httpStatus": None, "error": "连接超时"})
    try:
        none_resp = fd_module.fetch_mysteel_meal_stock()
    finally:
        fd_module.fetch_json_debug = real
    assert none_resp["available"] is False and "无返回" in none_resp["reason"]
    print("✅ 空结果/接口异常/无可提取内容/网络无响应都诚实报告")


import datetime as _soy_dt
_SD = _soy_dt.date
# (名称, 发布日期, 标题, 正文, 期望提取结果[(年,月,万吨)])——全部来自用户文档里的真实Mysteel响应
_SOY_SAMPLES = [
 ("样本0 7月官方快讯(含1-7月累计)", _SD(2026,8,7), "海关总署：2026年7月中国大豆进口量为1147.7万吨 同比减少1.62%",
  "海关总署数据显示，2026年7月中国大豆进口量为1147.7万吨，同比减少1.62%，环比减少15.28%。今年1-7月累计进口大豆6151.1万吨，较去年同期增长0.7%。整体来看，月度进口量有所回落，但年初至今累计进口量仍保持微幅增长态势。",
  [(2026,7,1147.7)]),
 ("样本1 4月(含1-4月累计)", _SD(2026,5,9), "海关总署：2026年4月中国大豆进口量为847.8万吨 同比增39.42%",
  "据海关总署数据显示 ：中国2026年4月大豆进口847.8万吨，环比3月增加445.90万吨，增110.95% ；较2025年4月进口量同比增加239.70万吨，增幅39.42% 中国2026年1-4月大豆进口2515.1 万吨，同比2025年1－4月进口量多196.2万吨，增幅8.46% 。",
  [(2026,4,847.8)]),
 ("样本2 6月(含上半年累计)", _SD(2026,7,14), "海关总署：2026年6月中国大豆进口量为1354.7万吨 同比增加10.46%",
  "海关总署数据显示，2026年6月中国大豆进口量为1354.7万吨，同比增长10.46%，环比增长14.89%。上半年累计进口大豆5015.4万吨，较去年同期4938.9万吨增长1.5%。整体呈现稳步上涨态势，供应保持充足。",
  [(2026,6,1354.7)]),
 ("样本3 3月(标题漏了月字，含1-3月累计)", _SD(2026,4,15), "海关总署：2026年3中国大豆进口量为401.9万吨 同比增14.7%",
  "据海关总署数据显示 ：中国2026年3月大豆进口401.9万吨，环比2月减少195.7万吨，降32.8% ；较2025年3月进口量同比增加51.6万吨，增幅14.7% 中国2026年1-3月大豆进口1656.6 万吨，同比2025年1－3月进口量少54.7万吨，降幅3.1% 。",
  [(2026,3,401.9)]),
 ("样本4 5月(写法：进口大豆X万吨)", _SD(2026,6,9), "海关总署：2026年5月中国大豆进口量为1179.1万吨 同比减少15.28%",
  "据海关总署数据显示 ：中国2026年5月进口大豆1179.1万吨，同比减少15.28%，环比增长39.08% 中国2026年1-5月大豆进口3694.2万吨，去年同期1-5月进口3710.6万吨，同比减少0.4% 。",
  [(2026,5,1179.1)]),
 ("样本5 1月+2月合并发布(含1－2月累计，全角横线)", _SD(2026,3,10), "海关总署：2026年1－2月中国大豆进口量为1254.7万吨 同比降7.8％",
  "据海关总署数据显示 ：中国2026年1月大豆进口657.1万吨，环比12月进口减少147.3万吨，较2025年1月进口量同比减少120.9万吨，降幅15.54% 中国2026年2月大豆进口597.6万吨，环比1月进口减少59.5万吨，较2025年2月进口量同比增加14.6万吨，增幅2.5% 中国2026年1－2月大豆进口1254.7万吨，同比2025年１－２月进口量少106.3万吨，降幅7.8%。",
  [(2026,1,657.1),(2026,2,597.6)]),
 ("样本6 2025年12月(含全年累计)", _SD(2026,1,14), "海关总署：2025年12月中国大豆进口量为804.4万吨 同比增加1.3％",
  "据海关总署数据显示 ：中国2025年12月大豆进口804.4万吨，环比11月进口减少6.3万吨，较2024年12月进口量同比增加10.3万吨，增幅为1.3%2025年1－12月中国累计进口大豆总量为11183.3万吨，同比增678.82万吨，增幅为6.46% 。",
  [(2025,12,804.4)]),
 ("样本7 2025年11月(含1-11月累计)", _SD(2025,12,8), "海关总署：2025年11月中国大豆进口量为810.7万吨 同比增加13.32％",
  "据海关总署数据显示 ：中国2025年11月大豆进口810.7万吨，环比10月进口减少137.30万吨，较2024年11月进口量同比增加95.30万吨，增幅为13.32%2025年1-11月中国累计进口大豆总量为10378.14万吨，同比增668.72万吨，增幅为6.89% 。",
  [(2025,11,810.7)]),
 ("样本8 2025年10月", _SD(2025,11,7), "海关总署：2025年10月中国大豆进口量为948.2万吨 同比增加17.25%",
  "据海关总署数据显示 ：中国2025年10月大豆进口948.2万吨，环比9月进口减少338.7万吨，较2024年10月进口量同比增加139.5万吨，增幅为17.25%2025年1-10月中国累计进口大豆总量为9568.2万吨，同比增574.5万吨，增幅为6.39% 。",
  [(2025,10,948.2)]),
 ("样本9 2025年9月", _SD(2025,10,13), "海关总署：2025年9月中国大豆进口量为1286.9万吨 同比增加13.17%",
  "据海关总署数据显示 ：中国2025年9月大豆进口1286.9万吨，环比8月进口增加59万吨，较2024年9月进口量同比增加149.8万吨，增幅为13.17%2025年1-9月中国累计进口大豆总量为8618万吨，同比增433.1万吨，增幅为5.29% 。",
  [(2025,9,1286.9)]),
 ("样本10 9-9早报(没写年份：8月中国大豆进口X万吨)", _SD(2026,9,9), "Mysteel早报：华北市场豆粕价格或小幅下调（20260909）",
  "华北豆粕现货前日上涨至3300-3330元/吨。夜盘连粕下跌，CBOT大豆上涨，市场等待USDA报告。8月中国大豆进口1214.14万吨，同比增1.1%。巴西开始新季大豆播种，美豆优良率58%符合预期。华北油厂开机率84.55%，库存下降，可售量少，下游采购积极性好转。预计今日豆粕现货价格小幅下调至3280-3320元/吨区间运行。",
  [(2026,8,1214.14)]),
 ("样本11 9-9早报川渝", _SD(2026,9,9), "Mysteel早报：川渝豆粕市场报价震荡运行（20260909）",
  "昨日川渝豆粕现货价格上调至3350-3440元/吨，油厂开机率41%。夜盘连粕下跌，CBOT大豆上涨，市场等待USDA报告。8月中国大豆进口1214.14万吨，同比增1.1%；巴西开始新季播种，美豆优良率58%符合预期。目前川渝油厂开机持稳，库存小幅增加，终端刚需补库。预计今日川渝市场豆粕价格将震荡运行。",
  [(2026,8,1214.14)]),
 ("样本12 棉粕日报(只说进口量增加，无数值)", _SD(2026,9,9), "Mysteel日报：棉粕市场价格暂无变化（20260909）",
  "棉粕市场供应偏紧，厂商挺价惜售，但下游需求平淡，替代优势不明显，预计短期维持窄幅偏强震荡。新疆及山东46%蛋白棉粕报价在2550-3070元/吨。豆粕方面，连盘高位震荡，成本支撑强劲，但国内大豆进口量增加，现货供给充裕，基差承压。沿海现货价格3250-3290元/吨，下游补库意愿略有回升。后市需关注新季棉籽上市节奏、USDA报告及豆粕走势。",
  []),
 ("样本13 豆粕日报(8月大豆进口量大增，无数值)", _SD(2026,9,9), "Mysteel日报：全国油厂开机及豆粕成交量统计（20260909）",
  "9月9日国内豆粕现货价格涨跌互现，连粕主力合约报3425元/吨。全国油厂豆粕成交13.71万吨，开机率62.34%。虽进口大豆到港成本攀升支撑盘面，但8月大豆进口量大增致供应充裕，基差承压。短期盘面受成本主导呈高位震荡，参考区间3380-3430元/吨。需关注美豆天气溢价收窄背景下，9月USDA报告单产调整及下游补库节奏变化。",
  []),
 ("样本14 快讯(8月大豆进口同比增1.1%，无数值)", _SD(2026,9,9), "Mysteel快讯：美豆等待USDA报告指引 国内豆粕区间震荡",
  "美豆受高温干旱及出口需求支撑，主力合约持稳1310美分上方，市场静待USDA报告指引。国内豆粕高位震荡，区间参考3380-3430元/吨。进口成本攀升夯实底部，但8月大豆进口同比增1.1%，供应充裕致基差承压至-110至-150元/吨。下游补库意愿回升，短期盘面由成本主导，需关注USDA单产调整及补库节奏。",
  []),
 ("样本15 5-29解读(4月进口+到港预估：7月预计1100万吨，8月1050万吨)", _SD(2026,5,29), "Mysteel解读：供应宽松格局明确 6月豆粕仍将承压",
  "据海关总署数据显示 ：中国2026年4月大豆进口847.8万吨，环比3月增加445.90万吨，增110.95%；较2025年4月进口量同比增加239.70万吨，增幅39.42% 据Mysteel农产品团队预估，2026年5月份国内全样本油厂大豆到港共计约988.65万吨6月份国内全样本油厂大豆到港共计约1073.80万吨此外，根据船期及调研初步预估，7月预计1100万吨，8月1050万吨集中到港窗口已正式开启，供应压力从港口逐步传导至油厂加工端。",
  [(2026,4,847.8)]),
 ("样本16 2025全年进口量(年度数，不是月度)", _SD(2026,2,6), "Mysteel解读 ：中央一号文件给豆粕市场释放哪些信号？",
  "目前我国大豆进口依存度较高，单一来源地过度集中可能带来供应链风险进口多元化包括来源地多元、品种多元与渠道多元，据海关总署数据统计显示：2025年全年中国大豆进口量共11181.89万吨，同比增加678.35万吨，增幅6.45%进口主要来源国为巴西，这一点延续近几年趋势，中国大豆进口来源 “巴西化” 的格局已经非常稳固巴西凭借其广阔的耕地面积和持续增长的产量，已超越美国，成为中国最可靠、最主要的大豆供应国。",
  []),
 ("样本17 分国别统计(2025年11月)", _SD(2025,12,22), "2025年11月份大豆海关进口数据统计（分国别）",
  "据海关总署数据显示 ：中国2025年11月大豆进口810.7万吨，环比10月进口减少137.30万吨，较2024年11月进口量同比增加95.30万吨，增幅为13.32%2025年1-11月中国累计进口大豆总量为10378.14万吨，同比增668.72万吨，增幅为6.89% 。",
  [(2025,11,810.7)]),
]


_SOY_TEST_TODAY = _soy_dt.date(2026, 9, 28)


def _run_soy_with_pages(pages, capture=None, today=None):
    import fetch_data as fd_module
    real = fd_module.fetch_json_debug
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        if capture is not None:
            capture.append({"url": url, "headers": headers, "post_data": post_data})
        return pages.get((post_data or {}).get("pageNo", 1), _sow_resp([])), {"httpStatus": 200}
    fd_module.fetch_json_debug = fake_fetch
    try:
        return fd_module.fetch_mysteel_soy_import(today=today or _SOY_TEST_TODAY)
    finally:
        fd_module.fetch_json_debug = real


def _soy_items(predicate=lambda name: True):
    return [{"content": content, "title": title, "publishTime": pub.isoformat() + " 12:00", "url": "https://ncp.mysteel.com/a/soy.html"}
            for name, pub, title, content, _ in _SOY_SAMPLES if predicate(name)]


def test_soy_import_real_articles_all_recognized(monkeypatch_fetch):
    """★用户文档里的18条真实Mysteel文章(标题+正文都扫)，逐条验证提取结果。这些文章里有大量"长得像月度
    进口量、其实不是"的数：累计数(1-7月累计进口大豆6151.1万吨、上半年累计…、1-4月大豆进口2515.1万吨)、
    年度数(2025年全年11181.89万吨)、变动量(环比12月进口减少147.3万吨)、预测(7月预计1100万吨)、
    没数值的(8月大豆进口同比增1.1%)；还有1月+2月合并发布(不能把"1－2月大豆进口1254.7万吨"当成2月)、
    "进口大豆X万吨"的反序写法、没写年份的市场早报。"""
    import fetch_data as fd_module
    for name, pub, title, content, expected in _SOY_SAMPLES:
        got = []
        for text in (content, title):
            for c in fd_module._extract_soy_import_candidates(text, pub, _SOY_TEST_TODAY):
                if c not in got:
                    got.append(c)
        assert got == expected, f"★{name}: 期望{expected}，实际{got}"
    print(f"✅ {len(_SOY_SAMPLES)}条真实文章全部正确识别(累计数/年度数/变动量/预测值/区间横线/无数值全部没被误认)")


def test_soy_import_full_flow_picks_august_2026(monkeypatch_fetch):
    """★端到端：真实文章(最新的官方快讯只到7月，8月的数只出现在9-9的市场早报里)，今天2026-09-28
    应该选出上个月(8月)的1214.14万吨，标注"2026年8月"。"""
    r = _run_soy_with_pages({1: _sow_resp(_soy_items(), 24)})
    assert r["available"] is True, r
    assert r["value"] == 1214.14 and r["monthLabel"] == "2026年8月" and r["date"] == "2026-09-09", r
    assert r["monthsSeen"][0] == "2026年8月" and "2026年7月" in r["monthsSeen"], r["monthsSeen"]
    print("✅ 真实文章端到端：选出2026年8月大豆进口1214.14万吨(来自9-9市场早报)")


def test_soy_import_falls_back_to_previous_month_when_latest_not_published(monkeypatch_fetch):
    """海关快讯一般次月7号前后发布——上个月的数还没出时，允许退到上上个月，但不能更旧。
    去掉所有提到8月的文章：2026-09-28应退到7月的1147.7；今天换成2026-11-05(接受10月/9月)则拒绝。"""
    no_aug = _soy_items(lambda name: not name.startswith(("样本10", "样本11")))
    r = _run_soy_with_pages({1: _sow_resp(no_aug)})
    assert r["available"] is True and r["monthLabel"] == "2026年7月" and r["value"] == 1147.7, r
    stale = _run_soy_with_pages({1: _sow_resp(no_aug)}, today=_soy_dt.date(2026, 11, 5))
    assert stale["available"] is False and "较旧" in stale["reason"] and "2026年10月" in stale["reason"], stale
    print("✅ 8月数据没出时退到7月(1147.7)；更旧(今天11月、只有8月及以前)时拒绝并说明原因")


def test_soy_import_acceptance_window_rolls_with_calendar(monkeypatch_fetch):
    """接受窗口随日历滚动：10月2日(9月数据还没出)接受8月；次年1月中旬只有8月数据就太旧了。"""
    aug_only = _soy_items(lambda name: name.startswith(("样本10",)))
    assert _run_soy_with_pages({1: _sow_resp(aug_only)}, today=_soy_dt.date(2026, 10, 2))["monthLabel"] == "2026年8月"
    assert _run_soy_with_pages({1: _sow_resp(aug_only)}, today=_soy_dt.date(2026, 11, 2))["available"] is False
    print("✅ 接受窗口随日历滚动(10月初接受8月，11月起8月就太旧)")


def test_soy_import_year_inference_and_future_months(monkeypatch_fetch):
    """没写年份时按发布日期推断；当月及以后的月份不可能已有进口数据。"""
    import fetch_data as fd_module
    D = _soy_dt.date
    f = lambda text, pub, today: fd_module._extract_soy_import_candidates(text, pub, today)
    assert f("8月中国大豆进口1214.14万吨", D(2026, 9, 9), D(2026, 9, 28)) == [(2026, 8, 1214.14)]
    assert f("12月中国大豆进口804.4万吨", D(2027, 1, 12), D(2027, 1, 20)) == [(2026, 12, 804.4)]   # 1月发布提到12月=去年
    assert f("9月中国大豆进口1000万吨", D(2026, 9, 9), D(2026, 9, 28)) == []                       # 当月不可能已有数据
    print("✅ 年份按发布日期推断(跨年的12月、当月都处理对了)")


def test_soy_import_synthetic_traps_rejected(monkeypatch_fetch):
    """合成的陷阱句(真实样本里没出现，但很可能出现)：预测值、超范围、各种累计写法、变动量。"""
    import fetch_data as fd_module
    D = _soy_dt.date
    f = lambda text: fd_module._extract_soy_import_candidates(text, D(2026, 9, 9), D(2026, 9, 28))
    assert f("预计8月中国大豆进口1300万吨") == []                 # 预测
    assert f("8月中国大豆进口12万吨") == []                        # 超出合理范围(200~2000)
    assert f("1-8月累计进口大豆7365万吨") == []                    # 累计
    assert f("中国2026年1－8月大豆进口7365万吨") == []              # 区间(全角横线)
    assert f("中国2026年1-8月大豆进口7365万吨") == []              # 区间(半角横线)
    assert f("前8月中国累计进口大豆总量为7365万吨") == []           # 累计总量
    assert f("较去年8月进口量同比减少30万吨") == []                # 变动量
    assert f("8月我国大豆进口量为1214万吨") == [(2026, 8, 1214.0)]  # 换个说法仍能识别
    print("✅ 预测/超范围/累计/区间横线/变动量都被丢弃，换成\"我国…进口量为\"的说法仍能识别")


def test_soy_import_paginates_and_request_matches_user_capture(monkeypatch_fetch):
    """★请求跟用户抓包逐项对照(query=海关总署中国大豆进口量、sortType=complex、platform=pc、pageNo=1、
    pageSize=20，字段集合一致，一年窗口起点2025-09-28)；用户实测total=24(两页)，8月的数只在第2页时也能取到。"""
    import datetime as dt
    page1 = [{"content": f"无关文章{i}", "publishTime": "2026-09-01 09:00", "title": "无关"} for i in range(20)]
    page2 = _soy_items(lambda name: name.startswith("样本10"))
    captured = []
    r = _run_soy_with_pages({1: _sow_resp(page1, 24), 2: _sow_resp(page2, 24)}, capture=captured)
    assert [c["post_data"]["pageNo"] for c in captured] == [1, 2] and r["value"] == 1214.14, r
    p = captured[0]["post_data"]
    assert set(p) == {"query", "startTime", "endTime", "sortType", "platform", "pageNo", "pageSize"}
    assert (p["query"], p["sortType"], p["platform"], p["pageSize"]) == ("海关总署中国大豆进口量", "complex", "pc", 20)
    days = (dt.datetime.strptime(p["endTime"][:10], "%Y-%m-%d") - dt.datetime.strptime(p["startTime"][:10], "%Y-%m-%d")).days
    assert days == 365 and p["startTime"] == "2025-09-28 00:00:00" and captured[0]["headers"]["token"] == "-1"
    print("✅ 请求逐项对照抓包一致；total=24分两页，只在第2页出现的8月数据也能取到")


def test_soy_import_failure_modes_give_diagnostics(monkeypatch_fetch):
    import fetch_data as fd_module
    assert "为空" in _run_soy_with_pages({1: _sow_resp([])})["reason"]
    assert "resultCode=1" in _run_soy_with_pages({1: {"resultCode": 1}})["reason"]
    nothing = _run_soy_with_pages({1: _sow_resp([{"content": "完全不相关", "publishTime": "2026-09-09 08:00"}])})
    assert nothing["available"] is False and nothing["debug"]["itemsChecked"] == 1 and "firstItemSample" in nothing["debug"]
    real = fd_module.fetch_json_debug
    fd_module.fetch_json_debug = lambda *a, **k: (None, {"httpStatus": None, "error": "连接超时"})
    try:
        assert "无返回" in fd_module.fetch_mysteel_soy_import()["reason"]
    finally:
        fd_module.fetch_json_debug = real
    print("✅ 空结果/接口异常/无可提取内容/网络无响应都诚实报告")


import datetime as _rs_dt
_RESERVE_TEST_TODAY = _rs_dt.date(2026, 9, 28)
# ★用户文档里第1页的20条真实Mysteel响应(查询"进口大豆竞价销售结果"，total=115)：9条交易公告 + 6条"原油基差"竞价 + 5条真正的拍卖结果
_RESERVE_REAL_ITEMS = [{'publishTime': '2026-09-22 17:00', 'title': '2026年9月28日进口大豆竞价销售交易公告', 'content': '中储粮油脂有限公司委托于2026年9月28日13:30开展进口大豆竞价销售交易。', 'url': 'https://ncp.mysteel.com/a/26092217/FCA671B054C65B26.html'},
 {'publishTime': '2026-09-18 16:03', 'title': '2026年9月22日进口大豆竞价销售交易公告', 'content': '中储粮油脂委托于2026年9月22日开展进口大豆竞价销售。', 'url': 'https://ncp.mysteel.com/a/26091816/5C83CE69A2A27C87.html'},
 {'publishTime': '2026-09-04 17:10', 'title': '2026年9月9日进口大豆竞价销售交易公告', 'content': '中储粮油脂委托于2026年9月9日开展进口大豆竞价销售。', 'url': 'https://ncp.mysteel.com/a/26090417/C8ECBE427BD404A9.html'},
 {'publishTime': '2026-08-29 09:36', 'title': '2026年9月2日进口大豆竞价销售交易公告', 'content': '中储粮油脂有限公司将于2026年9月2日13:30开展进口大豆竞价销售交易。', 'url': 'https://ncp.mysteel.com/a/26082909/3B8CA810C77E0F26.html'},
 {'publishTime': '2026-08-26 09:55', 'title': '2026年8月26日进口大豆竞价销售交易公告', 'content': '中储粮油脂委托于2026年8月26日13:30开展进口大豆竞价销售。', 'url': 'https://ncp.mysteel.com/a/26082609/51829FF56AF32767.html'},
 {'publishTime': '2026-08-17 11:47', 'title': '2026年8月19日进口大豆竞价销售交易公告', 'content': '中储粮油脂有限公司将于2026年8月19日13:30开展进口大豆竞价销售交易。', 'url': 'https://ncp.mysteel.com/a/26081711/6AA0B2B569D7CD1A.html'},
 {'publishTime': '2026-08-12 15:01',
  'title': '【中储粮网】2026年8月14日油脂公司进口大豆原油基差竞价销售交易清单',
  'content': '中储粮网公布2026年8月14日油脂公司进口大豆原油基差竞价销售交易清单。此次销售涉及山西（太原、大同）、陕西（宝鸡）及宁夏（银川）地区，计划销售总量为19884吨。点价期统一为2026年8月14日至9月10日，交货期根据地区不同，截止于10月15日或10月31日。目前成交数量、计划及销售价格暂未公布。',
  'url': 'https://ncp.mysteel.com/a/26081215/97E64340D70A7F0D.html'},
 {'publishTime': '2026-08-07 15:20', 'title': '2026年8月12日进口大豆竞价销售交易公告', 'content': '中储粮油脂有限公司将于2026年8月12日开展进口大豆竞价销售。', 'url': 'https://ncp.mysteel.com/a/26080715/173BFFCAAA53EEC7.html'},
 {'publishTime': '2026-08-07 13:41',
  'title': '【中储粮网】2026年8月7日油脂公司进口大豆原油基差竞价销售交易结果',
  'content': '2026年8月7日，中储粮油脂公司进行进口大豆原油基差竞价销售。交易涉及山西太原、大同，陕西宝鸡及宁夏银川等地，计划销售总量19884吨。所有标的基差报价在09-100至09-320之间，点价期为8月7日至20日。最终结果显示，全部标的成交数量均为0，整体流拍。',
  'url': 'https://ncp.mysteel.com/a/26080713/2853279CD0BDF5A2.html'},
 {'publishTime': '2026-08-05 09:18',
  'title': '【中储粮网】2026年8月7日油脂公司进口大豆原油基差竞价销售交易清单',
  'content': '中储粮网公布2026年8月7日油脂公司进口大豆原油基差竞价销售交易清单。本次计划销售总量为19884吨，涉及山西太原、大同，陕西宝鸡及宁夏银川等地。点价期为2026年8月7日至8月20日，交货期主要集中在8月7日至9月30日，部分宁夏地区货源交货期延至10月31日。当前成交数量、计划销售价及实际销售价均未显示，具体交易结果需待竞价结束后确定。',
  'url': 'https://ncp.mysteel.com/a/26080509/DD1662FAA28901E5.html'},
 {'publishTime': '2026-07-31 16:39', 'title': '2026年8月5日进口大豆竞价销售交易公告', 'content': '中储粮油脂有限公司将于2026年8月5日13:30开展进口大豆竞价销售。', 'url': 'https://ncp.mysteel.com/a/26073116/A209441A34077E8E.html'},
 {'publishTime': '2026-07-28 18:15',
  'title': '2026年7月31日进口大豆竞价销售交易公告',
  'content': '受中储粮油脂有限公司委托，2026年7月31日13:30将开展进口大豆竞价销售交易。交易通过国家粮食交易平台进行，报价递增度为10元/次。价格类型为卖方散粮车板交货价，不执行水分、杂质增扣量，筛下物随货出库，卖方负责装货。实际销售数量以官网发布的交易清单为准。公告提供了看样及业务联系人信息，提醒交易会员登录平台参与。',
  'url': 'https://ncp.mysteel.com/a/26072818/BE17C0DC1D3AAE2E.html'},
 {'publishTime': '2026-09-28 14:15',
  'title': '9月28日进口大豆竞价销售结果',
  'content': '2026年9月28日，计划拍卖22、23、24年产进口大豆514312.514吨，水分9.44%-13.00%，分布在四川、天津等地。交货期为2026年11月-2027年1月。竞拍底价4310元/吨，最高价4390元/吨。最终成交191698.792吨，成交率37.27%。',
  'url': 'https://ncp.mysteel.com/a/26092814/4AD8FEC894730B4A.html'},
 {'publishTime': '2026-09-22 14:31',
  'title': '9月22日进口大豆竞价销售结果',
  'content': '2026年9月22日进口大豆竞价销售，计划拍卖542992.291吨，生产年限为23、24、25年，水分9.32%-12.70%，分布在广西、天津等多地。交货期为2026年11月-2027年1月。价格区间为4280元/吨至4450元/吨。最终成交338674.098吨，成交率62.37%。',
  'url': 'https://ncp.mysteel.com/a/26092214/5FC437DC5587FB76.html'},
 {'publishTime': '2026-09-17 09:54',
  'title': '【中储粮网】2026年9月18日油脂公司进口大豆原油基差竞价销售交易清单',
  'content': '中储粮网发布2026年9月18日油脂公司进口大豆原油基差竞价销售交易清单。计划于9月18日在宁夏银川销售2012吨2024年产进口大豆原油。点价期为2026年9月18日至10月15日，交货作业期为2026年9月18日至10月31日。清单未列示具体底价及实际销售价，需通过竞价确定最终成交价格。',
  'url': 'https://ncp.mysteel.com/a/26091709/27AC379A9934148A.html'},
 {'publishTime': '2026-09-14 16:51',
  'title': '9月2日进口大豆竞价销售结果',
  'content': '2026年9月2日进口大豆竞价销售中，计划拍卖68012.56吨，生产年限涵盖22、24、25年，水分9.63%-10.80%，分布于四川、广西，交货期为2026年9月至2027年1月。起拍价区间为4330-4380元/吨。最终成交量为0吨，成交率为0%，本次拍卖未达成任何交易。',
  'url': 'https://ncp.mysteel.com/a/26091416/74CF602EE324E30E.html'},
 {'publishTime': '2026-09-09 14:42',
  'title': '9月9日进口大豆竞价销售结果',
  'content': '2026年9月9日，计划拍卖进口大豆68012.56吨，生产年限涵盖22、24、25年，水分9.63%-10.80%，分布在四川、广西，交货期为2026年9月至2027年1月。起拍价区间为4320-4390元/吨。最终成交量为0吨，成交率为0%。',
  'url': 'https://ncp.mysteel.com/a/26090914/26FCFF9729615648.html'},
 {'publishTime': '2026-09-07 13:37',
  'title': '【中储粮网】2026年9月8日油脂公司进口大豆原油基差竞价销售交易清单',
  'content': '中储粮网公布2026年9月8日油脂公司进口大豆原油基差竞价销售交易清单。计划在宁夏银川地区销售两笔进口大豆原油，数量分别为950吨和938吨。点价期为2026年9月8日至10月15日，交货期为2026年9月8日至10月31日。当前成交数量、底价及实际销售价暂未显示。',
  'url': 'https://ncp.mysteel.com/a/26090713/536A6B884CB20A18.html'},
 {'publishTime': '2026-09-01 08:40',
  'title': '【中储粮网】2026年9月1日油脂公司进口大豆原油基差竞价销售交易清单',
  'content': '中储粮网公布2026年9月1日油脂公司进口大豆原油基差竞价销售交易清单。陕西宝鸡地区计划销售进口大豆原油1988吨，点价期为2026年9月1日至9月30日，交货期为2026年9月1日至10月31日。本次交易底价及实际销售价格暂未显示，成交数量待竞价结束后确定。',
  'url': 'https://ncp.mysteel.com/a/26090108/F7D2FC830DFB427C.html'},
 {'publishTime': '2026-08-26 14:18',
  'title': '8月26日进口大豆竞价销售结果',
  'content': '2026年8月26日进口大豆竞价销售中，计划拍卖290794.339吨，实际成交222781.779吨，成交率76.61%。拍卖大豆生产年限涵盖22至25年，水分8.9%-12%，分布于河南、四川等地。成交价格区间为4110-4200元/吨，成交均价4162.73元/吨，交货期为2026年10月至2027年1月。',
  'url': 'https://ncp.mysteel.com/a/26082614/7DF0A81F540462A5.html'}]


def _run_reserve_with_pages(pages, capture=None, today=None):
    import fetch_data as fd_module
    real = fd_module.fetch_json_debug
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        if capture is not None:
            capture.append({"url": url, "headers": headers, "post_data": post_data})
        return pages.get((post_data or {}).get("pageNo", 1), _sow_resp([])), {"httpStatus": 200}
    fd_module.fetch_json_debug = fake_fetch
    try:
        return fd_module.fetch_mysteel_reserve_auction(today=today or _RESERVE_TEST_TODAY)
    finally:
        fd_module.fetch_json_debug = real


def _parse_real(i):
    import fetch_data as fd_module
    it = _RESERVE_REAL_ITEMS[i]
    pub = _rs_dt.datetime.strptime(it["publishTime"][:10], "%Y-%m-%d").date()
    return fd_module._parse_reserve_auction(it["title"], it["content"], pub)


def test_reserve_real_articles_parsed_and_noise_excluded(monkeypatch_fetch):
    """★20条真实文章逐条验证：5条拍卖结果提取出计划量/成交量/成交率/价格；9条交易公告(只有日期没有数量)和
    6条"原油基差"竞价(卖的是大豆原油，计划销售总量19884吨，标题也叫"进口大豆…竞价销售交易结果")必须排除。"""
    D = _rs_dt.date
    expected = {  # 序号: (拍卖日期, 计划万吨, 成交万吨, 成交率, 均价, 价格低, 价格高, 价格类型)
        12: (D(2026, 9, 28), 51.43, 19.17, 37.27, None, 4310.0, 4390.0, "底价~最高价"),
        13: (D(2026, 9, 22), 54.3, 33.87, 62.37, None, 4280.0, 4450.0, "价格区间"),
        15: (D(2026, 9, 2), 6.8, 0.0, 0.0, None, 4330.0, 4380.0, "起拍价区间"),
        16: (D(2026, 9, 9), 6.8, 0.0, 0.0, None, 4320.0, 4390.0, "起拍价区间"),
        19: (D(2026, 8, 26), 29.08, 22.28, 76.61, 4162.73, 4110.0, 4200.0, "成交价格区间"),
    }
    for i in range(len(_RESERVE_REAL_ITEMS)):
        r, why = _parse_real(i)
        if i in expected:
            got = (r["auctionDate"], r["plannedWan"], r["soldWan"], r["soldRate"], r["avgPrice"], r["priceLow"], r["priceHigh"], r["priceKind"])
            assert got == expected[i], f"★[{i}] 期望{expected[i]}，实际{got}"
        elif i in (6, 8, 9, 14, 17, 18):
            assert r is None and "原油" in why, f"★[{i}]原油基差竞价必须排除: {r} {why}"
        else:
            assert r is None and "计划拍卖" in why, f"★[{i}]交易公告必须排除: {r} {why}"
    print("✅ 20条真实文章：5条拍卖结果全部正确提取，9条交易公告+6条原油基差竞价全部排除")


def test_reserve_full_flow_latest_auction_with_previous(monkeypatch_fetch):
    """★端到端：今天2026-09-28，最近一次拍卖就是今天(9-28)：计划51.43万吨、成交19.17万吨、成交率37.27%。
    自动填入的是计划拍卖量51.43(口径跟现有计分一致：>=40万吨偏空)；同时带上上一次(9-22，54.3万吨，成交率62.37%)。"""
    r = _run_reserve_with_pages({1: _sow_resp(_RESERVE_REAL_ITEMS, 115)})
    assert r["available"] is True, r
    assert r["value"] == 51.43 and r["auctionDate"] == "2026-09-28" and r["ageDays"] == 0, r
    assert (r["plannedWan"], r["soldWan"], r["soldRate"]) == (51.43, 19.17, 37.27)
    assert r["previous"] == {"auctionDate": "2026-09-22", "plannedWan": 54.3, "soldWan": 33.87, "soldRate": 62.37, "avgPrice": None}, r["previous"]
    assert r["auctionsSeen"] == 5
    print("✅ 端到端：最近一次拍卖2026-09-28，计划51.43万吨/成交率37.27%，上一次54.3万吨/62.37%")


def test_reserve_uses_auction_date_not_publish_date(monkeypatch_fetch):
    """★"最近一次"按拍卖日期取，不是文章发布日期：9月2日那次的结果文章是9月14日才发的，
    比9月9日那次(当天发)发布得晚——最近一次仍然应该是9月9日。"""
    r = _run_reserve_with_pages({1: _sow_resp([_RESERVE_REAL_ITEMS[15], _RESERVE_REAL_ITEMS[16]])}, today=_rs_dt.date(2026, 9, 20))
    assert r["auctionDate"] == "2026-09-09" and r["previous"]["auctionDate"] == "2026-09-02", r
    print("✅ 按拍卖日期取最近一次(9-9)，虽然9-2那次的文章发布得更晚(9-14)")


def test_reserve_paginates_all_pages_latest_on_last_page(monkeypatch_fetch):
    """搜索结果按相关度排序，共115条(6页)——最新一次拍卖只出现在最后一页时也必须能取到，
    不能只看第1页。"""
    filler = [{"title": "无关文章", "content": "无关内容", "publishTime": "2026-01-01 09:00"} for _ in range(20)]
    captured = []
    pages = {i: _sow_resp(filler, 101) for i in range(1, 6)}
    pages[6] = _sow_resp([_RESERVE_REAL_ITEMS[12]], 101)
    r = _run_reserve_with_pages(pages, capture=captured)
    assert [c["post_data"]["pageNo"] for c in captured] == [1, 2, 3, 4, 5, 6], [c["post_data"]["pageNo"] for c in captured]
    assert r["available"] is True and r["auctionDate"] == "2026-09-28"
    print("✅ 翻6页取完，只出现在最后一页的最新拍卖也能取到")


def test_reserve_crude_oil_basis_never_mistaken_for_soybean_auction(monkeypatch_fetch):
    """★原油基差竞价(卖的是大豆原油，量只有几千吨)即使措辞伪装成"计划拍卖"也必须排除；
    只有这类文章时诚实报告，并且把排除原因写进诊断信息。"""
    fake = {"title": "【中储粮网】进口大豆原油基差竞价销售交易结果", "publishTime": "2026-09-28 10:00",
            "content": "2026年9月28日，计划拍卖进口大豆原油1988吨，最终成交1988吨，成交率100%。"}
    only_oil = [_RESERVE_REAL_ITEMS[i] for i in (6, 8, 9, 14, 17, 18)] + [fake]
    r = _run_reserve_with_pages({1: _sow_resp(only_oil)})
    assert r["available"] is False and any("原油" in s for s in r["debug"]["skipped"]), r
    print("✅ 原油基差竞价(含伪装成'计划拍卖'的)全部排除，并在诊断信息里说明原因")


def test_reserve_integrity_check_and_derived_fields(monkeypatch_fetch):
    """完整性校验：成交量÷计划量必须跟文中的成交率对得上，对不上说明取错了数，整条丢弃；
    缺成交量/成交率时可以由另一个推算；"流拍"表示成交为0；什么结果都没有就不采用。"""
    import fetch_data as fd_module
    D = _rs_dt.date(2026, 9, 28)
    f = lambda content: fd_module._parse_reserve_auction("9月28日进口大豆竞价销售结果", content, D)
    bad, why = f("2026年9月28日，计划拍卖500000吨，最终成交100000吨，成交率90%。")
    assert bad is None and "对不上" in why, (bad, why)
    only_rate, _ = f("2026年9月28日，计划拍卖100000吨，成交率50%。")
    assert only_rate["soldWan"] == 5.0 and only_rate["soldRate"] == 50.0
    only_sold, _ = f("2026年9月28日，计划拍卖100000吨，实际成交25000吨。")
    assert only_sold["soldRate"] == 25.0
    fail, _ = f("2026年9月28日，计划拍卖100000吨，本次拍卖全部流拍。")
    assert fail["soldWan"] == 0.0 and fail["soldRate"] == 0.0
    none, why2 = f("2026年9月28日，计划拍卖100000吨。")
    assert none is None and "成交" in why2
    print("✅ 成交率对不上时整条丢弃；缺一个可由另一个推算；流拍=0；没有结果就不采用")


def test_reserve_stale_and_future_and_price_guards(monkeypatch_fetch):
    """新鲜度：最近一次拍卖超过45天(可能已暂停)就拒绝，45天内接受(边界有测试)；拍卖日期在未来的丢弃；
    价格离谱只丢价格本身，不丢整条(计划量/成交率仍然有效)。"""
    only_928 = {1: _sow_resp([_RESERVE_REAL_ITEMS[12]])}
    assert _run_reserve_with_pages(only_928, today=_rs_dt.date(2026, 11, 12))["available"] is True          # 45天
    r46 = _run_reserve_with_pages(only_928, today=_rs_dt.date(2026, 11, 13))                                 # 46天
    assert r46["available"] is False and "暂停" in r46["reason"] and "46天前" in r46["reason"], r46
    future = {"title": "1月1日进口大豆竞价销售结果", "publishTime": "2026-09-28 10:00", "content": "2027年1月1日，计划拍卖100000吨，最终成交50000吨，成交率50%。"}
    assert _run_reserve_with_pages({1: _sow_resp([future])})["available"] is False
    import fetch_data as fd_module
    weird, _ = fd_module._parse_reserve_auction("9月28日进口大豆竞价销售结果", "2026年9月28日，计划拍卖100000吨，最终成交50000吨，成交率50%。竞拍底价4元/吨，最高价5元/吨。", _rs_dt.date(2026, 9, 28))
    assert weird["plannedWan"] == 10.0 and weird["soldRate"] == 50.0 and weird["priceLow"] is None
    print("✅ 45天内接受/46天拒绝(可能已暂停)；未来日期丢弃；离谱价格只丢价格本身")


def test_reserve_auction_date_fallback_and_dedup(monkeypatch_fetch):
    """正文没有完整日期时用标题里的"M月D日"+发布日期推断年份；同一次拍卖有多篇文章时取发布最晚的。"""
    import fetch_data as fd_module
    r, _ = fd_module._parse_reserve_auction("9月28日进口大豆竞价销售结果", "计划拍卖100000吨，最终成交50000吨，成交率50%。", _rs_dt.date(2026, 9, 28))
    assert r["auctionDate"] == _rs_dt.date(2026, 9, 28)
    early = {"title": "9月28日进口大豆竞价销售结果", "publishTime": "2026-09-28 14:00", "content": "2026年9月28日，计划拍卖100000吨，最终成交50000吨，成交率50%。"}
    late = {"title": "9月28日进口大豆竞价销售结果(更正)", "publishTime": "2026-09-29 09:00", "content": "2026年9月28日，计划拍卖100000吨，最终成交60000吨，成交率60%。"}
    out = _run_reserve_with_pages({1: _sow_resp([late, early])}, today=_rs_dt.date(2026, 9, 30))
    assert out["soldRate"] == 60.0 and out["auctionsSeen"] == 1, out
    print("✅ 日期回退(标题+发布日期)正确；同一次拍卖多篇文章取发布最晚的(更正版)")


def test_reserve_request_matches_user_capture(monkeypatch_fetch):
    """★请求跟用户抓包逐项对照：query=进口大豆竞价销售结果、sortType=complex、platform=pc、pageNo=1、pageSize=20，
    字段集合一致，一年窗口起点2025-09-28，token=-1；不足一页时不多翻页。"""
    import datetime as dt
    captured = []
    _run_reserve_with_pages({1: _sow_resp([_RESERVE_REAL_ITEMS[12]])}, capture=captured)
    assert len(captured) == 1
    c = captured[0]; p = c["post_data"]
    assert c["url"] == "https://search.mysteel.com/searchapi/search/searchArticle"
    assert set(p) == {"query", "startTime", "endTime", "sortType", "platform", "pageNo", "pageSize"}
    assert (p["query"], p["sortType"], p["platform"], p["pageNo"], p["pageSize"]) == ("进口大豆竞价销售结果", "complex", "pc", 1, 20)
    days = (dt.datetime.strptime(p["endTime"][:10], "%Y-%m-%d") - dt.datetime.strptime(p["startTime"][:10], "%Y-%m-%d")).days
    assert days == 365 and p["startTime"] == "2025-09-28 00:00:00" and c["headers"]["token"] == "-1"
    print("✅ 请求逐项对照抓包一致(关键词/一年窗口起点2025-09-28/分页/字段集合/token)")


def test_reserve_failure_modes_give_diagnostics(monkeypatch_fetch):
    import fetch_data as fd_module
    assert "为空" in _run_reserve_with_pages({1: _sow_resp([])})["reason"]
    assert "resultCode=1" in _run_reserve_with_pages({1: {"resultCode": 1}})["reason"]
    nothing = _run_reserve_with_pages({1: _sow_resp([{"title": "完全不相关", "content": "无关", "publishTime": "2026-09-28 10:00"}])})
    assert nothing["available"] is False and nothing["debug"]["itemsChecked"] == 1 and "firstItemSample" in nothing["debug"]
    real = fd_module.fetch_json_debug
    fd_module.fetch_json_debug = lambda *a, **k: (None, {"httpStatus": None, "error": "连接超时"})
    try:
        assert "无返回" in fd_module.fetch_mysteel_reserve_auction()["reason"]
    finally:
        fd_module.fetch_json_debug = real
    print("✅ 空结果/接口异常/无可解析文章/网络无响应都诚实报告")


import datetime as _basis_dt
_BASIS_TEST_TODAY = _basis_dt.date(2026, 9, 28)
# ★用户文档里第1页的20条真实Mysteel响应(查询"全国主要市场豆粕基差价格汇总"，total=245，每日一篇)
_BASIS_REAL_ITEMS = [{'publishTime': '2026-09-28 11:39',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260928）',
  'content': '2026年9月28日，全国主要市场豆粕01合约现货基差普遍上涨。其中长春基差150元/吨，涨30元；大连90元/吨，涨30元；昆明、成都均为60元/吨，各涨20元；西安70元/吨，涨20元。日照、湛江、东莞、南通基差均为-70至-80元/吨，各涨20元；防城港-100元/吨，涨20元。天津、沧州、周口基差分别为-30、-30、-20元/吨，各涨30元。厦门基差30元/吨，涨50元。',
  'url': 'https://ncp.mysteel.com/a/26092811/74E13684FD6F9EA5.html'},
 {'publishTime': '2026-09-24 14:16',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260924）',
  'content': '2026年9月24日全国主要市场豆粕基差价格汇总显示，多数地区基差下跌。长春基差120，跌20；天津-60，跌20；日照、湛江、东莞均为-90，跌10；防城港-140，跌10；南通-110，跌10。昆明30，成都40，大连60，西安50，均跌10。南昌-20，周口-50，武汉-30，厦门-20，重庆-10，其中南昌、周口、武汉、厦门基差持平，其余地区基差均有不同程度下跌。',
  'url': 'https://ncp.mysteel.com/a/26092414/3BB742943907E419.html'},
 {'publishTime': '2026-09-23 13:31',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260923）',
  'content': '2026年9月23日，全国主要市场豆粕基差价格多数上涨。云南昆明、吉林长春、四川成都基差分别为40、140、50，均涨10；辽宁大连基差70，涨20。天津、山东日照、江苏南通等地基差为负值，其中广西防城港-130，山东日照-70，广东东莞及湛江-80，多数地区上涨10。广东两地持平。重庆基差0，涨10。陕西西安、河北沧州、河南周口等地基差在-50至60之间，普遍上涨10。',
  'url': 'https://ncp.mysteel.com/a/26092313/3CE7BDD8A53838B0.html'},
 {'publishTime': '2026-09-22 11:42',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260922）',
  'content': '2026年9月22日全国主要市场豆粕基差价格汇总显示，多数地区基差下跌。昆明、长春基差分别为30、130，均跌10；天津、日照、湛江、东莞、防城港、南通、沧州、岳阳、大连基差分别跌20、10、10、10、10、10、10、10、10；周口、武汉、西安基差均跌20；厦门基差涨10；成都、南昌、重庆基差持平。',
  'url': 'https://ncp.mysteel.com/a/26092211/2FE967A1B580F927.html'},
 {'publishTime': '2026-09-21 11:54',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260921）',
  'content': '2026年9月21日全国主要市场豆粕基差价格汇总显示，多数地区基差随01合约波动。昆明、长春基差分别为40、140，上涨10；成都、防城港、沧州、周口、重庆基差持平。天津下跌10至-30，厦门下跌10至-40。日照、东莞、湛江、南通基差均上涨20，分别为-70、-90、-80、-70。南昌、武汉、岳阳、大连、西安基差上涨10，分别为-30、-10、-40、60、70。',
  'url': 'https://ncp.mysteel.com/a/26092111/7F7FA116005EEECA.html'},
 {'publishTime': '2026-09-20 11:47',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260920）',
  'content': '2026年9月20日，全国主要市场豆粕基差以01合约为基准普遍下跌。云南昆明、陕西西安及辽宁大连等地基差为正，其余多数地区为负。其中，广西防城港基差最低为-120，广东东莞为-110。跌幅方面，河北沧州与河南周口均下跌60，吉林长春、四川成都、天津、江西南昌及重庆等地下跌40。山东日照与广东湛江基差持平。整体显示现货基差走弱态势。',
  'url': 'https://ncp.mysteel.com/a/26092011/82241235A4580058.html'},
 {'publishTime': '2026-09-18 12:20',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260918）',
  'content': '2026年9月18日，全国主要市场豆粕基差普遍上涨。其中长春基差最高为170元/吨，防城港最低为-80元/吨。各地涨幅多在60-80元/吨之间，厦门涨幅最小为40元/吨。整体来看，豆粕现货基差呈现上行趋势，各地区价差结构保持稳定，北方地区基差相对高于南方沿海地区。',
  'url': 'https://ncp.mysteel.com/a/26091812/1724D5B948361D13.html'},
 {'publishTime': '2026-09-17 12:04',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260917）',
  'content': '2026年9月17日全国主要市场豆粕基差价格汇总显示，各区域表现分化。长春基差为110，上涨30；大连基差30，上涨20；成都基差10，上涨10。昆明基差0，下跌10。多地基差为负值，其中防城港最低为-160，下跌20；东莞、日照、南通等地基差在-110至-120之间，均出现不同程度下跌。天津、沧州、西安等地基差变动较小或持平。整体来看，部分北方地区基差走强，而南方及沿海多数地区基差走弱。',
  'url': 'https://ncp.mysteel.com/a/26091712/544ECDCFC0CB713D.html'},
 {'publishTime': '2026-09-15 13:02',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260915）',
  'content': '2026年9月15日，全国主要市场豆粕基差价格互有涨跌。昆明、长春、日照等地上涨10-20元/吨；成都、天津、防城港等地持平。具体来看，长春基差110元/吨，昆明30元/吨；华南地区湛江、东莞基差分别为-100、-110元/吨；华东南通基差-110元/吨。整体呈现区域分化态势，部分沿海及内陆市场基差小幅修复，其余地区保持稳定。',
  'url': 'https://ncp.mysteel.com/a/26091513/F73CCE1FC7636E74.html'},
 {'publishTime': '2026-09-11 13:44',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260911）',
  'content': '2026年9月11日，全国主要市场豆粕基差多数上涨。昆明、长春、成都等地基差分别为10、80、50，涨幅在10-30之间。天津、山东、广东等地基差为负值，其中日照、湛江、东莞及防城港均为-120至-140区间，除湛江持平外，其余小幅上涨10-20。厦门基差下跌10至-60。整体来看，大部分地区基差呈现上涨趋势，仅个别地区出现下跌或持稳。',
  'url': 'https://ncp.mysteel.com/a/26091113/B8E4CBB789988808.html'},
 {'publishTime': '2026-09-10 11:57',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260910）',
  'content': '2026年9月10日全国主要市场豆粕基差价格汇总显示，多数地区基差为负值。其中山东日照、广西防城港基差最低，均为-150；云南昆明、陕西西安基差为0；吉林长春基差最高，为50。涨跌方面，福建厦门上涨30，天津、河北沧州分别上涨10和20；山东日照、广东湛江下跌20；其余大部分地区持稳或小幅波动。整体来看，沿海及部分内陆地区基差表现较弱，东北及西南部分地区相对坚挺。',
  'url': 'https://ncp.mysteel.com/a/26091011/AAF0D9EC456AAE97.html'},
 {'publishTime': '2026-09-09 11:41',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260909）',
  'content': '2026年9月9日，全国主要市场豆粕基差以01合约为准。昆明、长春基差分别为0和50；天津、日照、湛江等地基差为负，其中日照、防城港低至-150。多数地区基差上涨10-20点，如昆明、长春、天津等；南昌下跌10点；厦门、西安持平。整体来看，除个别地区外，大部分市场豆粕基差呈现小幅上涨态势，区域间价差依然存在。',
  'url': 'https://ncp.mysteel.com/a/26090911/FD41F8BC3CA33B29.html'},
 {'publishTime': '2026-09-08 12:18',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260908）',
  'content': '2026年9月8日，全国主要市场豆粕基差以01合约为准。长春基差30元/吨，成都10元/吨，西安持平。其余地区多为负值，其中广西防城港最低为-170元/吨，山东日照-160元/吨，江苏南通-150元/吨。当日多数地区基差下跌10-20元/吨，如昆明、长春、湛江等；成都、南昌、重庆、西安等地基差持稳。整体呈现弱势调整格局。',
  'url': 'https://ncp.mysteel.com/a/26090812/07D26EF533DF81E2.html'},
 {'publishTime': '2026-09-07 11:59',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260907）',
  'content': '2026年9月7日，全国主要市场豆粕基差普遍上涨。云南昆明、陕西西安基差为0；吉林长春基差最高，达50。沿海及内陆多数地区基差为负值，其中广西防城港最低，为-160。各地涨幅在10至60之间，吉林长春涨幅最大，广东东莞、湛江涨幅最小。整体来看，豆粕现货基差呈现上行趋势，区域间价差依然存在。',
  'url': 'https://ncp.mysteel.com/a/26090711/3D18661B59FE8D56.html'},
 {'publishTime': '2026-09-04 14:00',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260904）',
  'content': '2026年9月4日，全国主要市场豆粕基差以01合约为准，整体呈现下跌趋势。其中广西防城港基差为-200，江苏南通为-190，山东日照为-180，天津为-160。多数地区基差下跌10至30个点，如昆明、成都、天津等地；长春和大连基差持平。数据显示沿海及内陆主要产区基差普遍走弱，反映现货相对期货价格承压。',
  'url': 'https://ncp.mysteel.com/a/26090414/1F292B2B7AEE322E.html'},
 {'publishTime': '2026-09-03 12:06',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260903）',
  'content': '2026年9月3日全国主要市场豆粕基差普遍下跌。其中山东日照、广西防城港基差均为-170，分别下跌60和10；天津、河北沧州基差为-140，均下跌40；江苏南通基差-160，下跌30。广东湛江、福建厦门基差持平，分别为-120和-80。云南昆明、吉林长春等地基差在-10至-20区间，小幅下跌。整体来看，多数地区基差呈现弱势运行态势。',
  'url': 'https://ncp.mysteel.com/a/26090312/6AFA78D87468E1F3.html'},
 {'publishTime': '2026-09-02 12:01',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260902）',
  'content': '2026年9月2日全国主要市场豆粕基差以负值为主。天津、山东日照、江苏南通等地基差上涨20-30元；福建厦门、陕西西安基差下跌10元；其余多数地区如昆明、长春、成都等持稳。其中广西防城港基差最低为-160，陕西西安最高为40。整体来看，部分沿海及华北地区基差有所修复，华南及西南部分地区保持稳定，市场呈现分化走势。',
  'url': 'https://ncp.mysteel.com/a/26090212/94707E957D9C06C2.html'},
 {'publishTime': '2026-09-01 11:56',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260901）',
  'content': '2026年9月1日全国主要市场豆粕基差价格汇总显示，多数地区基差为负值。其中广西防城港基差最低为-180，陕西西安最高为50。涨跌方面，河北沧州上涨40，天津上涨30，山东日照、河南周口及湖北武汉均上涨20；广东湛江下跌10；云南昆明、吉林长春等其余多地持稳。整体来看，沿海及部分内陆地区基差小幅波动，区域间价差依然存在。',
  'url': 'https://ncp.mysteel.com/a/26090111/A26DB8FC2AAEB771.html'},
 {'publishTime': '2026-08-31 13:43',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260831）',
  'content': '2026年8月31日全国主要市场豆粕基差数据显示，多数地区基差为负值。其中广西防城港基差最低为-180，山东日照为-170；陕西西安基差最高为40。较前一交易日，大连、东莞等地基差上涨30点，昆明、长春等地下跌10点，成都、天津等地持平。整体来看，各地基差变动幅度有限，市场呈现小幅震荡格局。',
  'url': 'https://ncp.mysteel.com/a/26083113/C60FA0AC01DBDD86.html'},
 {'publishTime': '2026-08-28 11:58',
  'title': 'Mysteel：全国主要市场豆粕基差价格汇总（20260828）',
  'content': '2026年8月28日，全国主要市场豆粕基差以01合约为准。多数地区基差为负值，其中广西防城港最低为-180，山东日照、广东东莞及河北沧州均为-160。云南昆明基差为-20，吉林长春为10，陕西西安为30。当日基差变动方面，成都上涨10；长春、岳阳、大连、重庆及西安持平；其余多地基差下跌，如山东日照下跌30，天津、广东湛江、江苏南通等地下跌10至20不等。',
  'url': 'https://ncp.mysteel.com/a/26082811/33B500DCC6AC6CC7.html'}]


def _run_basis_with_pages(pages, capture=None, today=None):
    import fetch_data as fd_module
    real = fd_module.fetch_json_debug
    def fake_fetch(url, headers=None, retries=3, timeout=20, post_data=None):
        if capture is not None:
            capture.append({"url": url, "headers": headers, "post_data": post_data})
        return pages.get((post_data or {}).get("pageNo", 1), _sow_resp([])), {"httpStatus": 200}
    fd_module.fetch_json_debug = fake_fetch
    try:
        return fd_module.fetch_mysteel_basis(today=today or _BASIS_TEST_TODAY)
    finally:
        fd_module.fetch_json_debug = real


def test_basis_real_articles_extraction_matches_manual_verification(monkeypatch_fetch):
    """★用户文档里20条真实正文，逐条验证：17条能提取出沿海代表城市的确切基差，
    3条(9-22/9-21/9-11)原文本身没有给出任何沿海候选城市的确切数值(全是范围或纯变动量)，
    这是数据源本身的限制，不是正则的问题——每条都手算验证过下面这些具体数值。"""
    import fetch_data as fd_module
    expected = {
        "2026-09-28": ("防城港", -100.0), "2026-09-24": ("日照", -90.0), "2026-09-23": ("日照", -70.0),
        "2026-09-20": ("东莞", -110.0), "2026-09-18": ("防城港", -80.0), "2026-09-17": ("防城港", -160.0),
        "2026-09-15": ("南通", -110.0), "2026-09-10": ("防城港", -150.0), "2026-09-09": ("日照", -150.0),
        "2026-09-08": ("日照", -160.0), "2026-09-07": ("防城港", -160.0), "2026-09-04": ("日照", -180.0),
        "2026-09-03": ("南通", -160.0), "2026-09-02": ("防城港", -160.0), "2026-09-01": ("防城港", -180.0),
        "2026-08-31": ("日照", -170.0), "2026-08-28": ("防城港", -180.0),
    }
    no_data_days = {"2026-09-22", "2026-09-21", "2026-09-11"}
    for it in _BASIS_REAL_ITEMS:
        d = it["publishTime"][:10]
        city, v = fd_module._extract_basis_from_article(it["content"])
        if d in expected:
            assert (city, v) == expected[d], f"★{d}: 期望{expected[d]}，实际{(city, v)}"
        elif d in no_data_days:
            assert v is None, f"★{d}: 应该提取不到任何确切值(原文只有范围/纯变动量)，实际{(city, v)}"
    print(f"✅ 20条真实文章：17条提取出确切值且完全正确，3条(9-22/9-21/9-11，原文本身无确切值)正确识别为无数据")


def test_basis_end_to_end_uses_latest_when_available(monkeypatch_fetch):
    """★端到端：真实20条文章，今天2026-09-28，最新一篇(9-28)本身就能提取出确切值(防城港-100)，
    不需要触发回退机制。"""
    r = _run_basis_with_pages({1: _sow_resp(_BASIS_REAL_ITEMS, 245)})
    assert r["available"] is True, r
    assert r["value"] == -100.0 and r["city"] == "防城港" and r["date"] == "2026-09-28", r
    assert r["usedFallback"] is False and r["fallbackDays"] == 0
    print("✅ 端到端：最新一篇(9-28)本身可解析，直接采用，未触发回退")


def test_basis_falls_back_when_latest_articles_unparseable(monkeypatch_fetch):
    """★用户真实数据里连续两天(9-22、9-21)都没有确切值——模拟"今天恰好是9-22发布当天"这种情况，
    最新一篇解析失败时应该往前退到9-20(-110)，并诚实标注用的是2天前的数据，不是当天的。"""
    items_922_back = [it for it in _BASIS_REAL_ITEMS if it["publishTime"][:10] in ("2026-09-22", "2026-09-21", "2026-09-20")]
    r = _run_basis_with_pages({1: _sow_resp(items_922_back)}, today=_basis_dt.date(2026, 9, 22))
    assert r["available"] is True, r
    assert r["value"] == -110.0 and r["city"] == "东莞" and r["date"] == "2026-09-20", r
    assert r["usedFallback"] is True and r["fallbackDays"] == 2 and r["latestArticleDate"] == "2026-09-22"
    print("✅ 最新两篇(9-22/9-21)都解析失败时，正确回退到9-20(-110)，并诚实标注滞后2天")


def test_basis_all_recent_articles_unparseable_gives_diagnostic(monkeypatch_fetch):
    """回退窗口内的文章全部解析失败时，诚实报告，debug带上尝试过的所有日期。"""
    items_all_bad = [it for it in _BASIS_REAL_ITEMS if it["publishTime"][:10] in ("2026-09-22", "2026-09-21", "2026-09-11")]
    r = _run_basis_with_pages({1: _sow_resp(items_all_bad)}, today=_basis_dt.date(2026, 9, 22))
    assert r["available"] is False and "没有给出确切数值" in r["reason"], r
    assert len(r["debug"]["attemptedDates"]) == 3
    print("✅ 回退窗口内全部解析失败时诚实报告，debug带上尝试过的所有日期")


def test_basis_stale_data_rejected(monkeypatch_fetch):
    """新鲜度：每日更新的指标，超过7天(实测最大间隔4天)就拒绝。"""
    old = [it for it in _BASIS_REAL_ITEMS if it["publishTime"][:10] == "2026-08-28"]
    r_ok = _run_basis_with_pages({1: _sow_resp(old)}, today=_basis_dt.date(2026, 9, 4))   # 7天前
    assert r_ok["available"] is True
    r_stale = _run_basis_with_pages({1: _sow_resp(old)}, today=_basis_dt.date(2026, 9, 5))  # 8天前
    assert r_stale["available"] is False and "新鲜度限制" in r_stale["reason"] and "8天前" in r_stale["reason"]
    print("✅ 7天内接受，8天前拒绝(每日更新的指标，滞后太久就不该用)")


def test_basis_range_and_change_only_rejected_synthetic(monkeypatch_fetch):
    """合成陷阱句：范围表达、纯变动量(无基准值)、超出合理范围都要拒绝，换清单里下一个城市。"""
    import fetch_data as fd_module
    f = fd_module._extract_basis_from_article
    assert f("日照、南通基差均为-70至-80元/吨。") == (None, None)     # 范围
    assert f("日照基差较上周上涨20元/吨。") == (None, None)            # 纯变动量无基准值
    # ★_extract_basis_from_article本身不做范围合理性校验(那是fetch函数层的职责，见下一个测试)，
    #   -800这种超出合理范围的值，提取函数本身应该能正常拿到，不在这一层被拦下
    assert f("日照基差-800元/吨。") == ("日照", -800.0)
    print("✅ 范围表达、纯变动量正确拒绝，换下一个候选城市；提取函数本身不做范围校验(留给fetch函数层)")


def test_basis_implausible_value_rejected_by_fetch_function(monkeypatch_fetch):
    """★合理范围校验在fetch函数层做：日照给出的数值超出-500~500会被拒绝，回退到下一篇文章。"""
    weird = {"title": "测试", "content": "日照基差-800元/吨。", "publishTime": "2026-09-28 12:00", "url": ""}
    normal = {"title": "测试2", "content": "日照基差-90元/吨。", "publishTime": "2026-09-27 12:00", "url": ""}
    r = _run_basis_with_pages({1: _sow_resp([weird, normal])})
    assert r["available"] is True and r["value"] == -90.0 and r["date"] == "2026-09-27", r
    print("✅ 超出合理范围的数值被fetch函数层拒绝，正确回退到下一篇正常的文章")


def test_basis_request_matches_user_capture(monkeypatch_fetch):
    """★请求跟用户抓包逐项对照：query=全国主要市场豆粕基差价格汇总、sortType=complex、platform=pc、
    pageNo=1、pageSize=20，字段集合一致，一年窗口起点2025-09-28，token=-1；不足一页时不多翻页。"""
    import datetime as dt
    captured = []
    _run_basis_with_pages({1: _sow_resp([_BASIS_REAL_ITEMS[0]])}, capture=captured)
    assert len(captured) == 1
    c = captured[0]; p = c["post_data"]
    assert c["url"] == "https://search.mysteel.com/searchapi/search/searchArticle"
    assert set(p) == {"query", "startTime", "endTime", "sortType", "platform", "pageNo", "pageSize"}
    assert (p["query"], p["sortType"], p["platform"], p["pageSize"]) == ("全国主要市场豆粕基差价格汇总", "complex", "pc", 20)
    days = (dt.datetime.strptime(p["endTime"][:10], "%Y-%m-%d") - dt.datetime.strptime(p["startTime"][:10], "%Y-%m-%d")).days
    assert days == 365 and p["startTime"] == "2025-09-28 00:00:00" and c["headers"]["token"] == "-1"
    print("✅ 请求逐项对照抓包一致(关键词/一年窗口起点2025-09-28/分页/字段集合/token)")


def test_basis_future_articles_ignored(monkeypatch_fetch):
    """发布日期在未来的文章(时钟不同步等异常情况)应该被忽略，不当成"最新"。"""
    future = {"title": "未来", "content": "日照基差-50元/吨。", "publishTime": "2026-10-05 12:00", "url": ""}
    normal = {"title": "正常", "content": "日照基差-90元/吨。", "publishTime": "2026-09-27 12:00", "url": ""}
    r = _run_basis_with_pages({1: _sow_resp([future, normal])})
    assert r["available"] is True and r["date"] == "2026-09-27", r
    print("✅ 发布日期在未来的文章被忽略")


def test_basis_failure_modes_give_diagnostics(monkeypatch_fetch):
    import fetch_data as fd_module
    assert "为空" in _run_basis_with_pages({1: _sow_resp([])})["reason"]
    assert "resultCode=1" in _run_basis_with_pages({1: {"resultCode": 1}})["reason"]
    real = fd_module.fetch_json_debug
    fd_module.fetch_json_debug = lambda *a, **k: (None, {"httpStatus": None, "error": "连接超时"})
    try:
        assert "无返回" in fd_module.fetch_mysteel_basis()["reason"]
    finally:
        fd_module.fetch_json_debug = real
    print("✅ 空结果/接口异常/网络无响应都诚实报告")


# ===================== 国内豆粕库消比(Mysteel《全国豆粕供需平衡表》) =====================
# 下面12篇是用户抓包给的真实搜索结果(标题/发布时间/摘要原文)，加上我抓到的8月那篇正文的真实文字。
MB_REAL_ARTICLES = [
    ("Mysteel：全国豆粕供需平衡表（2026年8月）", "2026-08-31 18:26", "https://ncp.mysteel.com/a/26083118/BC0AFB400C5ACDC2.html",
     "2026年8-11月中国豆粕市场供强需弱。8-9月产量高企、消费疲弱，库存攀升至125万吨峰值，基差承压。10月产量收缩低于消费，出现供需逆差，过剩拐点显现。11月消费回暖但产量回升，去库缓慢，库消比仍处高位。整体看，市场由“显著宽松”过渡至“温和偏松”，彻底转向紧平衡仍需产量持续低位或消费超预期回暖。"),
    ("Mysteel：全国豆粕供需平衡表（2026年7月）", "2026-07-31 18:27", "https://ncp.mysteel.com/a/26073118/9FF36D9CCB44EFCF.html",
     "2026年7-10月中国豆粕市场呈现“显著供强需弱”格局。7月产量838万吨，消费796万吨，库存升至105万吨；8月库存预计攀升至120万吨，库消比达15%。9-10月产量与消费同步回落，但库存仍高企于110-115万吨，库消比维持15%-16%高位。在高开机、高压榨背景下，供应充沛而饲料需求乏力，库存去化困难，基本面压力持续施压豆粕价格。"),
    ("Mysteel：全国豆粕供需平衡表（2026年6月）", "2026-06-30 17:28", "https://ncp.mysteel.com/a/26063017/AE9AB8BE03D4723E.html",
     "2026年6-9月大豆集中到港叠加高温天气影响，油厂维持高开机率，豆粕产量保持高位，月均超750万吨。同期消费端表现平稳，月消费量743-766万吨，出口稳定在8万吨左右。供过于求导致期末库存由74万吨增至125万吨，累计上升约69%；库消比从10.06%升至15.27%，市场供应宽松压力持续加大。"),
    ("Mysteel：全国豆粕供需平衡表（2026年5月）", "2026-05-29 14:41", "https://ncp.mysteel.com/a/26052914/9207FD950F1F4D92.html",
     "2026年5月，国内豆粕产量为673万吨，但期初库存仅43万吨，而消费量高达673万吨，导致5月中旬豆粕库存一度降至30万吨以下，月底虽预计小幅回升至40万吨，整体供应依然紧张，库消比仅为5.94%。"),
    ("Mysteel：全国豆粕供需平衡表（2026年4月）", "2026-04-02 16:09", "https://ncp.mysteel.com/a/26040216/D50E02C891B62166.html",
     "2026年3月至6月，豆粕市场呈现供应先紧后松、库存逐步累积的格局其中，3月至4月受到港节奏影响，产量分别为658万吨和566万吨，消费则维持在657万至570万吨，豆粕消费需求前置，期末库存从68万吨降至60万吨的低点，库消比处于10.3%至10.5%的中低水平，供应偏紧对价格形成支撑；进入5月至6月后，随着压榨恢复，产量回升至711万吨和790万吨，消费同步增长至683万至767万吨，但产量增幅更大，推动期末库存连续回升至85万吨和105万吨，库消比也逐月上升至12.45%和13.70%，显示供应紧张局面逐步缓解，市场供需趋于宽松。"),
    ("Mysteel：全国豆粕供需平衡表（2026年3月）", "2026-02-28 16:47", "https://ncp.mysteel.com/a/26022816/892E22631E43F2B7.html",
     "根据国内豆粕供需平衡表的最新数据，2026年2月至5月期间，豆粕市场在供应恢复与需求回暖的共同作用下，呈现产量逐月回升、消费稳步增长、库存先降后升的运行态势。"),
    ("Mysteel：全国豆粕供需平衡表（2026年2月）", "2026-01-30 18:00", "https://ncp.mysteel.com/a/26013018/E810E5C2150CE5D3.html",
     "进入2026年1月，产量略有下降至698万吨，而消费增至722万吨，期末库存进一步减少至90万吨，库消比回落至12.45%，反映春节期间备货需求对库存的消耗。"),
    ("Mysteel：全国豆粕供需平衡表（2026年1月）", "2026-01-04 08:39", "https://ncp.mysteel.com/a/26010408/896EE0EF49C79A8D.html",
     "简析：2025年12月至2026年3月期间国内豆粕市场将逐步进入去库周期12月预计产量为716万吨，消费量716万吨，产销基本平衡，期末库存小幅降至117万吨，库消比为16.30%。"),
    ("Mysteel：全国12月豆粕供需平衡表", "2025-11-28 19:04", "https://ncp.mysteel.com/a/25112819/DBBF9057A8F16AFE.html",
     "简析：2025年11月国内豆粕产量为712万吨，消费量为714万吨，产需基本持平期末库存为110万吨，环比微降5万吨，库消比为15.40%，供需结构整体维持宽松格局。"),
    ("Mysteel：全国10月豆粕供需平衡表", "2025-10-31 18:22", "https://ncp.mysteel.com/a/25103118/700CA2E3A3A53F42.html",
     "2025年10月受假期影响国内油厂压榨量回落，豆粕库存虽小幅下降但仍处百万吨高位。预计11月压榨量增加但需求疲软，去库放缓，月底库存降至90万吨左右。12月因大豆到港减少及压榨亏损，压榨量收缩，库存继续下滑。展望2026年一季度，受买船进度偏缓影响，大豆供应趋紧，豆粕库存或将持续处于较低水平。"),
    ("Mysteel：全国10月豆粕供需平衡表", "2025-09-30 14:41", "https://ncp.mysteel.com/a/25093014/2BF58BF705529A89.html",
     "简析：2025年9月油厂维持高开机高压榨，而饲料企业长期维持高头寸滚动，豆粕物理库存处于饱和状态，整体消化进度偏慢。"),
    ("Mysteel半年报：2026年下半年豆粕价格或呈现先抑后扬走势", "2026-06-29 09:51", "https://ncp.mysteel.com/a/26062909/EE674EE44D1ED87D.html",
     "2026年上半年豆粕市场呈现冲高回落态势，受南美丰产及国内供应宽松压制，现货价格重心下移，同比跌幅近2%。三季度预计大豆到港量维持高位，豆粕库存持续累积。"),
]
# 8月那篇正文(真实抓取)：前后夹着大量导航/推荐文章标题(含\"9月29日…\"这种会被误当月份标记的文字)，用来验证只取标题→免责声明之间的正文
MB_REAL_BODY_HTML = """<html><head><title>Mysteel：全国豆粕供需平衡表（2026年8月）_我的钢铁网</title><script>var x='9月29日 产量999万吨';</script></head><body>
<div class="nav">价格 快讯 数据 9月29日江西油厂豆粕销售价格 Mysteel月报：8月花生价格同比下跌 8月31日 产量123万吨 库消比99%</div>
<h1>Mysteel：全国豆粕供需平衡表（2026年8月）</h1><div>2026-08-31 18:26 来源：我的钢铁网(Mysteel)</div>
<div class="ai">智能摘要 内容由AI生成 2026年8-11月中国豆粕市场供强需弱。8-9月产量高企、消费疲弱，库存攀升至125万吨峰值，基差承压。10月产量收缩低于消费，出现供需逆差，过剩拐点显现。</div>
<p>2026年8-11月中国豆粕市场呈现显著供强需弱格局。8月产量800万吨，消费772万吨，供大于求28万吨，期末库存跳增至117万吨，库消比15.12%，油厂库存压力加大，现货基差价格整体承压。9月产量微降至795万吨，消费仅779万吨，供需差扩大至16万吨，库存进一步攀升至125万吨，库消比达16.04%的区间峰值，供应压力最为集中。10月产量大幅收缩</p>
<div class="disclaimer">免责声明：Mysteel发布的原创及转载内容，仅供客户参考。</div>
<ul><li>[08-31] Mysteel解读：“金九”已至 9月产量888万吨</li><li>9月29日陕西油厂豆粕销售价格</li></ul></body></html>"""


def _mb_items(articles=MB_REAL_ARTICLES):
    return [{"title": t, "publishTime": pt, "url": u, "content": c, "score": 90} for (t, pt, u, c) in articles]


def _mb_install(monkeypatch_fetch, items, body_map=None, body_fail=False):
    """搜索接口返回items；正文请求：body_map里有的url返回对应HTML，body_fail=True时全部失败。返回还原函数。"""
    monkeypatch_fetch({"searchapi/search/searchArticle": {"resultCode": 0, "total": len(items), "dataList": items}})
    real = fd.fetch_text_debug
    calls = []
    def fake_text(url, headers=None, retries=2, timeout=20):
        calls.append(url)
        if body_fail:
            return None, {"url": url, "error": "HTTP 403: Forbidden", "httpStatus": 403}
        if body_map and url in body_map:
            return body_map[url], {"url": url, "httpStatus": 200}
        return None, {"url": url, "error": "测试里没有这个url的正文"}
    fd.fetch_text_debug = fake_text
    def restore():
        fd.fetch_text_debug = real
    restore.calls = calls
    return restore


def test_meal_balance_parses_real_body_and_ignores_page_noise(monkeypatch_fetch):
    """★真实正文：8月800/772/117/15.12%，9月795/779/125/16.04%。页面里导航/推荐/脚本里的\"9月29日…产量999万吨\"
    \"8月31日 产量123万吨 库消比99%\"这类会被误当月份标记的文字，必须被排除在解析范围之外。"""
    text = fd._html_to_text(MB_REAL_BODY_HTML)
    region = fd._extract_article_region(text, "Mysteel：全国豆粕供需平衡表（2026年8月）")
    assert "999" not in region and "库消比99%" not in region and "888" not in region, f"导航/脚本噪音混进了正文区域: {region[:200]}"
    recs = fd._parse_meal_balance_text(region, date(2026, 8, 31))
    assert recs[(2026, 8)] == {"production": 800.0, "consumption": 772.0, "stock": 117.0, "stu": 15.12, "stuStated": True}, recs
    assert recs[(2026, 9)] == {"production": 795.0, "consumption": 779.0, "stock": 125.0, "stu": 16.04, "stuStated": True}, recs
    assert (2026, 10) not in recs, "10月只有一句被截断的话，没有任何数字，不应产生记录"
    print("✅ 库消比：真实正文解析正确(8月15.12%/9月16.04%)，页面噪音被排除")


def test_meal_balance_all_real_summaries(monkeypatch_fetch):
    """★12篇真实摘要逐条核对：能解析的解析对，区间/多月/月中低点/没数字的一律不误取。"""
    def P(i):
        t, pt, u, c = MB_REAL_ARTICLES[i]
        return fd._parse_meal_balance_text(c, date.fromisoformat(pt[:10]))
    assert P(0) == {}, "8月摘要没有任何数字(只有'库消比仍处高位')，不应产生记录"
    r = P(1)   # 7月：产量838/消费796/库存105，没有明示库消比；8月：库存120，\"库消比达15%\"；9-10月是区间
    assert r[(2026, 7)]["stu"] is None and r[(2026, 7)]["stock"] == 105 and r[(2026, 7)]["consumption"] == 796
    assert r[(2026, 8)]["stu"] == 15.0 and r[(2026, 8)]["stock"] == 120
    assert (2026, 9) not in r and (2026, 10) not in r, "'9-10月…库存110-115万吨，库消比维持15%-16%'是区间，不能记到9月或10月头上"
    assert P(2) == {}, "6月摘要全是'6-9月'区间和'库消比从10.06%升至15.27%'多月变化，一律不采用"
    r = P(3)   # 5月：库消比5.94%；\"库存一度降至30万吨以下\"是月中低点，30÷673=4.46%与5.94%不自洽 → 库存丢弃
    assert r[(2026, 5)]["stu"] == 5.94 and r[(2026, 5)]["consumption"] == 673 and r[(2026, 5)]["stock"] is None, r
    assert P(4) == {}, "4月摘要('3月至6月''10.3%至10.5%''12.45%和13.70%'逐月上升)全是区间/多月，不采用"
    assert P(5) == {}, "3月摘要没有数字"
    r = P(6)   # 2026年1月：698/722/90/12.45%，90÷722=12.47%自洽 → 库存保留
    assert r[(2026, 1)] == {"production": 698.0, "consumption": 722.0, "stock": 90.0, "stu": 12.45, "stuStated": True}, r
    r = P(7)   # 1月4日发布的文章里的\"12月\"没写年份 → 应推断为上一年(2025年12月)，而不是2026年12月
    assert (2025, 12) in r and (2026, 12) not in r, r
    assert r[(2025, 12)]["stu"] == 16.30 and r[(2025, 12)]["stock"] == 117 and r[(2025, 12)]["consumption"] == 716
    r = P(8)   # 2025年11月：712/714/110/15.40%(\"环比微降5万吨\"不是库存)
    assert r[(2025, 11)] == {"production": 712.0, "consumption": 714.0, "stock": 110.0, "stu": 15.4, "stuStated": True}, r
    r = P(9)   # 10月摘要：\"预计11月…月底库存降至90万吨左右\" → 只有库存没有消费和库消比，产生的记录不可用
    assert all(fd._usable_meal_record(v)[0] is None for v in r.values()), r
    assert P(10) == {}, "2025年9月摘要没有数字"
    assert "半年报" in MB_REAL_ARTICLES[11][0]
    print("✅ 库消比：12篇真实摘要逐条核对——区间/多月/月中低点都没被误取，年份推断正确")


def test_meal_balance_full_flow_uses_body(monkeypatch_fetch):
    """★完整流程(今天=2026-09-29)：最新一篇是8月31日发布的。摘要没数字，必须靠正文拿到9月16.04%。"""
    items = _mb_items()
    rest = _mb_install(monkeypatch_fetch, items, body_map={MB_REAL_ARTICLES[0][2]: MB_REAL_BODY_HTML})
    try:
        r = fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29))
    finally:
        rest()
    assert r["available"] is True, r
    assert r["value"] == 16.04 and r["month"] == "2026-09" and r["method"] == "stated" and r["recordSource"] == "body", r
    assert r["isForecast"] is True, "9月记录来自8月31日的文章，属于预测"
    assert r["usedFallbackMonth"] is False and r["bodiesFetched"] == 1
    assert r["stockWan"] == 125 and r["consumptionWan"] == 779
    assert r["next"] is None and r["trend"] is None, "正文只到9月(10月被截断)，不应编出下月数据"
    assert r["date"] == "2026-08-31" and r["articleAgeDays"] == 29
    assert "半年报" not in (r["articleTitle"] or "")
    print("✅ 库消比：完整流程——靠正文拿到9月16.04%，标记为预测，不编造下月")


def test_meal_balance_current_and_next_month_with_trend(monkeypatch_fetch):
    """今天=2026-08-31：当月8月15.12%，下月9月16.04%，差+0.92个百分点 → 基本持平；改成差1.5以上则标\"上升(累库)\"。"""
    rest = _mb_install(monkeypatch_fetch, _mb_items(), body_map={MB_REAL_ARTICLES[0][2]: MB_REAL_BODY_HTML})
    try:
        r = fd.fetch_mysteel_meal_balance(today=date(2026, 8, 31))
    finally:
        rest()
    assert r["month"] == "2026-08" and r["value"] == 15.12 and r["isForecast"] is False
    assert r["next"]["month"] == "2026-09" and r["next"]["value"] == 16.04
    assert r["trend"]["delta"] == 0.92 and r["trend"]["direction"] == "基本持平"
    body2 = MB_REAL_BODY_HTML.replace("库消比达16.04%", "库消比达17.50%")
    rest = _mb_install(monkeypatch_fetch, _mb_items(), body_map={MB_REAL_ARTICLES[0][2]: body2})
    try:
        r2 = fd.fetch_mysteel_meal_balance(today=date(2026, 8, 31))
    finally:
        rest()
    assert r2["trend"]["direction"] == "上升(累库)" and r2["trend"]["delta"] == 2.38
    print("✅ 库消比：当月+下月+趋势方向(累库/去库)")


def test_meal_balance_body_blocked_falls_back_to_summary(monkeypatch_fetch):
    """★第二级回退：正文请求全部被拦(403)时，退回摘要。最新一篇摘要没数字→9月没有→往回找到8月
    (7月那篇摘要里\"8月…库消比达15%\")，并且如实标注\"用了8月的数、正文没取到\"。"""
    rest = _mb_install(monkeypatch_fetch, _mb_items(), body_fail=True)
    try:
        r = fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29))
    finally:
        rest()
    assert r["available"] is True and r["month"] == "2026-08" and r["value"] == 15.0, r
    assert r["usedFallbackMonth"] is True and r["recordSource"] == "summary"
    assert r["bodiesFetched"] == 0 and any("403" in n for n in r["bodyNotes"]), "必须如实说明正文没取到及原因"
    print("✅ 库消比：正文被拦→退回摘要，如实标注用了8月的数")


def test_meal_balance_third_level_weekly_stock_fallback(monkeypatch_fetch):
    """★第三级回退：文章只有消费量，没有库消比也没有库存 → 用周度商业库存÷当月消费，方式标\"weekly\"(可信度较低)。"""
    art = [("Mysteel：全国豆粕供需平衡表（2026年9月）", "2026-09-28 16:00", "https://x/a.html", "2026年9月产量795万吨，消费779万吨，供需趋于宽松。")]
    rest = _mb_install(monkeypatch_fetch, _mb_items(art), body_fail=True)
    try:
        r = fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29), weekly_stock={"available": True, "value": 125.0, "date": "2026-09-26"})
        r_none = fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29), weekly_stock=None)
    finally:
        rest()
    assert r["available"] is True and r["method"] == "weekly" and r["value"] == round(125.0 / 779 * 100, 2) == 16.05, r
    assert "可信度较低" in r["methodLabel"]
    assert r_none["available"] is False, "没有周度库存可用时不能编造，应该不可用"
    print("✅ 库消比：第三级回退=周度库存÷当月消费，标注可信度较低；没有周度库存就不可用")


def test_meal_balance_weekly_cross_check_shown(monkeypatch_fetch):
    """有文中明示值时，若周度库存也在，额外给出\"最新周度库存÷当月消费\"作交叉核对(不改变采用值)。"""
    rest = _mb_install(monkeypatch_fetch, _mb_items(), body_map={MB_REAL_ARTICLES[0][2]: MB_REAL_BODY_HTML})
    try:
        r = fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29), weekly_stock={"available": True, "value": 121.0, "date": "2026-09-26"})
    finally:
        rest()
    assert r["value"] == 16.04 and r["method"] == "stated"
    assert r["weeklyCheck"]["value"] == round(121.0 / 779 * 100, 2) == 15.53 and r["weeklyCheck"]["stockDate"] == "2026-09-26"
    print("✅ 库消比：周度库存交叉核对(15.53%)与文中明示值(16.04%)并列展示")


def test_meal_balance_month_rollover_uses_previous_month_record(monkeypatch_fetch):
    """月初(10月1日)：9月底那篇还没发，当月(10月)没有记录 → 用最近一个月(9月)，标注usedFallbackMonth。"""
    rest = _mb_install(monkeypatch_fetch, _mb_items(), body_map={MB_REAL_ARTICLES[0][2]: MB_REAL_BODY_HTML})
    try:
        r = fd.fetch_mysteel_meal_balance(today=date(2026, 10, 1))
    finally:
        rest()
    assert r["month"] == "2026-09" and r["value"] == 16.04 and r["usedFallbackMonth"] is True, r
    print("✅ 库消比：月初当月记录未发布时，沿用上月记录并标注")


def test_meal_balance_failure_modes(monkeypatch_fetch):
    # 最新文章太旧
    old = [("Mysteel：全国豆粕供需平衡表（2026年6月）", "2026-06-30 17:28", "https://x/1", "6月产量800万吨，消费700万吨，库消比10.00%")]
    rest = _mb_install(monkeypatch_fetch, _mb_items(old), body_fail=True)
    try:
        r = fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29))
    finally:
        rest()
    assert r["available"] is False and "新鲜度" in r["reason"] and "停更" in r["reason"]
    # 只有不是平衡表的文章
    rest = _mb_install(monkeypatch_fetch, _mb_items([MB_REAL_ARTICLES[11]]), body_fail=True)
    try:
        r = fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29))
    finally:
        rest()
    assert r["available"] is False and "豆粕供需平衡表" in r["reason"] and r["debug"]["skippedTitles"], r
    # 搜索接口无返回 / 空结果 / resultCode异常
    monkeypatch_fetch({})
    r = fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29))
    assert r["available"] is False and "无返回" in r["reason"]
    monkeypatch_fetch({"searchapi/search/searchArticle": {"resultCode": 0, "total": 0, "dataList": []}})
    assert "为空" in fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29))["reason"]
    monkeypatch_fetch({"searchapi/search/searchArticle": {"resultCode": 500}})
    assert "resultCode=500" in fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29))["reason"]
    # 全部文章都解析不出任何单月数据
    junk = [("Mysteel：全国豆粕供需平衡表（2026年9月）", "2026-09-28 16:00", "https://x/j", "整体供强需弱，库消比仍处高位。")]
    rest = _mb_install(monkeypatch_fetch, _mb_items(junk), body_fail=True)
    try:
        r = fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29))
    finally:
        rest()
    assert r["available"] is False and "没有解析出任何单月" in r["reason"] and r["debug"]["bodyNotes"], r
    print("✅ 库消比：文章太旧/不是平衡表/接口失败/空结果/全部解析不出，都给出明确原因")


def test_meal_balance_implausible_values_rejected(monkeypatch_fetch):
    """荒谬值不采用：库消比59%(超出1~40%)、月消费量9999万吨(超出300~1200)。"""
    recs = fd._parse_meal_balance_text("9月产量795万吨，消费9999万吨，库存125万吨，库消比59%。", date(2026, 9, 28))
    assert (2026, 9) in recs and recs[(2026, 9)]["stu"] is None and recs[(2026, 9)]["consumption"] is None, recs
    assert fd._plausibility_problem("mealStu", 59.0) and not fd._plausibility_problem("mealStu", 5.94)
    print("✅ 库消比：荒谬的库消比/消费量被丢弃")


def test_meal_balance_request_shape(monkeypatch_fetch):
    """请求体：跟用户抓包一致(query=全国豆粕供需平衡表，一年窗口，platform=pc，pageSize=20，sortType=complex)。"""
    seen = {}
    def fake_debug(url, headers=None, retries=3, timeout=20, post_data=None):
        seen["url"], seen["payload"], seen["headers"] = url, post_data, headers
        return {"resultCode": 0, "total": 0, "dataList": []}, {}
    fd.fetch_json_debug = fake_debug
    fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29))
    p = seen["payload"]
    assert seen["url"].endswith("/searchapi/search/searchArticle")
    assert p["query"] == "全国豆粕供需平衡表" and p["platform"] == "pc" and p["pageSize"] == 20 and p["sortType"] == "complex" and p["pageNo"] == 1
    assert p["startTime"] == "2025-09-29 00:00:00" and p["endTime"] == "2026-09-29 23:59:59", p
    print("✅ 库消比：请求体与用户抓包一致")



def test_meal_stock_recent_weeks_collects_every_extractable_week(monkeypatch_fetch):
    """★累积用：搜索窗口里所有能提取出数字的周都放进recentWeeks(同一发布日期一条)，不只是最新一周。"""
    def art(pub, val, wk):
        return {"title": f"Mysteel数据：全国主要区域大豆及豆粕库存统计", "publishTime": pub + " 16:00",
                "content": f"2026年第{wk}周，全国主要油厂大豆库存上升，豆粕库存{val}万吨，较上周增加"}
    items = [art("2026-09-21", 117.32, 38), art("2026-09-14", 111.0, 37), art("2026-09-14", 111.0, 37),
             {"title": "Mysteel：某无关文章", "publishTime": "2026-09-10 10:00", "content": "价格上涨"}]
    monkeypatch_fetch({"searchapi/search/searchArticle": {"resultCode": 0, "total": 4, "dataList": items}})
    r = fd.fetch_mysteel_meal_stock(today=date(2026, 9, 22))
    assert r["available"] and r["value"] == 117.32 and r["date"] == "2026-09-21"
    assert r["recentWeeks"] == [{"date": "2026-09-21", "value": 117.32, "week": "2026年第38周"},
                                {"date": "2026-09-14", "value": 111.0, "week": "2026年第37周"}], r["recentWeeks"]
    print("✅ 周度库存：recentWeeks收齐窗口里所有能提取的周(去重)")


def test_meal_balance_result_carries_festival_context(monkeypatch_fetch):
    """★库消比结果带上春节扰动信息：2026年9月不受影响；把'今天'挪到2027年2月(春节2月6日)就是扰动月。"""
    rest = _mb_install(monkeypatch_fetch, _mb_items(), body_map={MB_REAL_ARTICLES[0][2]: MB_REAL_BODY_HTML})
    try:
        r = fd.fetch_mysteel_meal_balance(today=date(2026, 9, 29))
    finally:
        rest()
    assert r["festival"]["disturbed"] is False and r["festival"]["festivalDate"] == "2026-02-17"
    # 构造一篇2027年2月发布、写2月记录的文章
    art = [("Mysteel：全国豆粕供需平衡表（2027年2月）", "2027-02-05 16:00", "https://x/f", "2027年2月产量600万吨，消费500万吨，期末库存100万吨，库消比20.00%。")]
    rest = _mb_install(monkeypatch_fetch, _mb_items(art), body_fail=True)
    try:
        r2 = fd.fetch_mysteel_meal_balance(today=date(2027, 2, 8))
    finally:
        rest()
    assert r2["month"] == "2027-02" and r2["festival"]["disturbed"] is True and r2["festival"]["phase"] == "假期停摆", r2["festival"]
    assert r2["festival"]["name"] == "春节" and r2["festival"]["level"] == "strong"
    # 国庆：10月是轻度扰动月
    art3 = [("Mysteel：全国豆粕供需平衡表（2026年10月）", "2026-09-30 16:00", "https://x/n", "2026年10月产量700万吨，消费690万吨，期末库存100万吨，库消比14.50%。")]
    rest = _mb_install(monkeypatch_fetch, _mb_items(art3), body_fail=True)
    try:
        r3 = fd.fetch_mysteel_meal_balance(today=date(2026, 10, 2))
    finally:
        rest()
    assert r3["month"] == "2026-10" and r3["festival"]["name"] == "国庆" and r3["festival"]["level"] == "mild" and r3["festival"]["disturbed"] is True
    print("✅ 库消比：结果带长假扰动信息(2027年2月=春节strong；2026年10月=国庆mild)")


def test_esr_china_unknown_other_split(monkeypatch_fetch):
    """★出口销售拆分：中国/未知目的地/其他分开统计；未知不算中国；4周滚动合计抹平目的地变更的跳动。
    模拟目的地变更：第5周未知-200000、中国+200000(净销售合计不变)。"""
    rows = []
    for w in ["2026-05-28", "2026-06-04", "2026-06-11"]:
        rows += [_esr_row(w, "CHINA", 50000), _esr_row(w, "UNKNOWN", 100000), _esr_row(w, "JAPAN", 50000)]
    rows += [_esr_row("2026-06-18", "CHINA", 50000), _esr_row("2026-06-18", "UNKNOWN", 100000), _esr_row("2026-06-18", "JAPAN", 50000)]
    rows += [_esr_row("2026-06-25", "CHINA", 250000), _esr_row("2026-06-25", "UNKNOWN", -200000), _esr_row("2026-06-25", "JAPAN", 50000)]
    monkeypatch_fetch({"esr/commodities": MOCK_ESR_COMMODITIES, "esr/exports": rows})
    r = fd.fetch_esr_export_sales()
    assert r["chinaNetSalesMT"] == 250000 and r["unknownNetSalesMT"] == -200000 and r["otherNetSalesMT"] == 50000
    assert r["netSalesMT"] == 100000, "目的地变更不改变净销售合计"
    assert r["china4wSumMT"] == 50000 * 3 + 250000 and r["unknown4wSumMT"] == 100000 * 3 - 200000
    assert r["total4wSumMT"] == 200000 * 3 + 100000
    assert r["chinaShare4wPct"] == round(400000 / 700000 * 100, 1)
    assert r["chinaMatched"] is True and "CHINA" in r["countryNamesSeen"] and "UNKNOWN" in r["countryNamesSeen"]
    # 中国名称没匹配上时要能被发现
    rows2 = [_esr_row(w, "PEOPLES REP OF CN", 10000) for w in ["2026-06-18", "2026-06-25"]]
    monkeypatch_fetch({"esr/commodities": MOCK_ESR_COMMODITIES, "esr/exports": rows2})
    r2 = fd.fetch_esr_export_sales()
    assert r2["chinaMatched"] is False and "PEOPLES REP OF CN" in r2["countryNamesSeen"]
    print("✅ ESR：中国/未知/其他拆分正确，目的地变更不影响总量，名称没匹配上时可被发现")



if __name__ == "__main__":
    monkeypatch_fetch = make_monkeypatch()
    tests = [test_contract_code_computation, test_main_fetches_all_three_contracts, test_dce_daily_kline_parsing, test_dce_hourly_kline_parsing,
              test_eastmoney_position_url_construction, test_eastmoney_position_row_parsing, test_foreign_futures_firm_detection,
              test_eastmoney_position_jsonp_unwrap, test_eastmoney_position_rank_integration,
              test_eastmoney_position_rank_complete_failure,
              test_dce_continuous_kline_handles_chinese_column_names, test_dce_continuous_kline_debug_output_is_json_safe,
              test_dce_continuous_kline_parsing, test_dce_continuous_kline_detects_rollover_jumps,
              test_us_planting_progress_filters_out_annual_survey_data,
              test_dce_kline_missing_akshare_gives_clear_reason,
              test_us_harvest_progress_parsing_and_wow_change, test_us_harvest_progress_distinguishes_from_planting,
              test_us_planting_progress_parsing_and_wow_change, test_us_planting_progress_missing_api_key,
              test_us_planting_progress_field_mismatch_gives_diagnostic,
              test_south_america_psd_uses_soybean_not_meal_code,
              test_south_america_psd_handles_oilseed_soybean_naming,
              test_south_america_psd_exact_match_beats_decoy_commodity,
              test_south_america_psd_falls_back_when_exact_name_missing,
              test_south_america_psd_diagnostic_shows_soybean_entries_not_generic_alphabet,
              test_weighted_avg_large_producer_dominates_over_small_producer,
              test_weighted_avg_small_producer_drought_gets_diluted_appropriately,
              test_soybean_condition_parsing_and_wow_change, test_soybean_condition_missing_api_key,
              test_soybean_condition_field_mismatch_gives_diagnostic,
              test_soybean_condition_yoy_and_five_year_avg_full_integration, test_us_harvest_progress_yoy_and_five_year_avg,
              test_cftc_managed_money_parsing, test_cftc_managed_money_no_data_found, test_cftc_managed_money_field_mismatch_gives_diagnostic,
              test_cftc_streak_weeks_consecutive_increase, test_cftc_streak_weeks_consecutive_decrease,
              test_cftc_history_percentile_calculation, test_cftc_history_percentile_none_when_insufficient_data,
              test_get_current_contract_code_prefix_param, test_crush_margin_calculation,
              test_crush_margin_missing_one_contract_reports_all_missing, test_crush_margin_all_three_missing_lists_all,
              test_brazil_planting_progress_extracts_national_row, test_brazil_planting_progress_no_national_row_found,
              test_brazil_planting_progress_missing_columns, test_brazil_planting_progress_exception_handled_gracefully,
              test_brazil_planting_progress_empty_dataframe,
              test_export_inspections_url_uses_correct_dataset_and_filter,
              test_export_inspections_aggregates_same_week_multiple_ports,
              test_export_inspections_empty_list_gives_diagnostic, test_export_inspections_non_list_response_gives_diagnostic,
              test_export_inspections_missing_date_field, test_export_inspections_mt_field_unparseable,
              test_export_inspections_no_network_response,
              test_noaa_outlook_url_uses_urlencode_no_raw_special_chars,
              test_noaa_outlook_percentage_aggregation_across_8_points,
              test_noaa_outlook_dominant_category_and_overall_signal,
              test_noaa_outlook_point_outside_any_outlook_zone,
              test_esr_code_lookup, test_meal_stock_recent_weeks_collects_every_extractable_week, test_meal_balance_result_carries_festival_context, test_esr_rollover_week_is_replaced_by_neighbor_average, test_esr_latest_week_is_rollover_blocks_comparisons, test_meal_balance_parses_real_body_and_ignores_page_noise, test_meal_balance_all_real_summaries, test_meal_balance_full_flow_uses_body, test_meal_balance_current_and_next_month_with_trend, test_meal_balance_body_blocked_falls_back_to_summary, test_meal_balance_third_level_weekly_stock_fallback, test_meal_balance_weekly_cross_check_shown, test_meal_balance_month_rollover_uses_previous_month_record, test_meal_balance_failure_modes, test_meal_balance_implausible_values_rejected, test_meal_balance_request_shape, test_esr_china_unknown_other_split, test_esr_uses_soybeans_not_meal, test_esr_export_parsing, test_esr_no_silent_fallback_to_shipments, test_esr_market_year_boundary_merges_weeks_without_double_count, test_psd_soybean_stocks_to_use_uses_total_use, test_psd_stocks_to_use_none_when_exports_missing, test_psd_target_market_year_rule, test_psd_picks_target_year_even_when_older_year_has_same_vintage, test_esr_picks_freshest_among_multiple_candidate_years,
              test_esr_code_lookup_distinguishes_failure_types,
              test_psd_code_lookup, test_psd_parsing,
              test_psd_fuzzy_matching, test_psd_debug_on_field_mismatch, test_drought_monitor_parsing,
              test_drought_uses_fips_code_not_postal_abbreviation, test_psd_real_world_attributeId_schema,
              test_psd_attribute_lookup_fails_gracefully, test_drought_area_to_percentage_conversion,
              test_drought_missing_none_field_fallback,
              test_mysteel_crush_rate_parsing_real_content, test_mysteel_crush_rate_missing_linebreak_still_parses,
              test_mysteel_crush_rate_skips_non_matching_items, test_mysteel_crush_rate_token_and_post_data_sent_correctly,
              test_mysteel_crush_rate_no_matching_content_gives_diagnostic, test_mysteel_crush_rate_empty_result_list,
              test_mysteel_crush_rate_bad_result_code, test_fetch_json_debug_post_mode_backward_compatible,
              test_mysteel_poultry_profit_loss_cases_real_examples, test_mysteel_poultry_profit_trap_case_skips_false_lead,
              test_mysteel_poultry_profit_connector_word_allowance_excludes_punctuation,
              test_mysteel_poultry_profit_does_not_assume_content_field_name, test_mysteel_poultry_profit_query_uses_correct_endpoint,
              test_mysteel_poultry_profit_no_matching_content_gives_diagnostic, test_mysteel_poultry_profit_empty_result,
              test_mysteel_rmspread_range_format_real_examples, test_mysteel_rmspread_city_specific_format_real_example,
              test_mysteel_rmspread_two_formats_mutually_exclusive, test_mysteel_rmspread_query_uses_correct_keyword,
              test_mysteel_rmspread_no_matching_content_gives_diagnostic, test_mysteel_rmspread_empty_result,
              test_mysteel_arrival_forecast_five_standard_examples, test_mysteel_arrival_forecast_cascade_format_real_example,
              test_mysteel_arrival_forecast_third_variant_real_example,
              test_mysteel_arrival_forecast_query_uses_correct_keyword, test_mysteel_arrival_forecast_no_matching_content_gives_diagnostic,
              test_mysteel_arrival_forecast_empty_result,
              test_hog_df_retries_and_succeeds_on_second_attempt, test_hog_df_exhausts_retries_reports_honestly,
              test_hog_df_socket_timeout_always_restored,
              test_hog_ratio_xuantian_real_screenshot_case, test_hog_ratio_uses_latest_common_date_not_last_row,
              test_hog_ratio_skips_nan_and_bad_dates, test_hog_ratio_corn_already_per_kg_not_divided_twice,
              test_hog_ratio_absurd_result_rejected, test_hog_ratio_no_common_dates_gives_diagnostic,
              test_hog_ratio_pig_fetch_failure_reports_which_series, test_hog_ratio_corn_fetch_failure_reports_which_series,
              test_hog_ratio_field_mismatch_gives_column_diagnostic,
              test_sow_inventory_mysteel_real_sample, test_sow_inventory_picks_latest_quarter_across_articles, test_sow_inventory_q4_newer_than_q3_in_same_year, test_sow_inventory_infer_quarter_year_from_publish_date, test_sow_inventory_forecast_and_target_values_ignored, test_sow_inventory_change_amount_not_mistaken_for_stock, test_sow_inventory_paginates_until_exhausted, test_sow_inventory_request_shape, test_sow_inventory_failure_modes_give_diagnostics,
              test_sow_inventory_eight_real_articles_all_recognized, test_sow_inventory_other_indicators_not_mistaken_for_sow, test_sow_inventory_level_verbs_allowed_but_change_amounts_rejected, test_sow_inventory_full_flow_with_eight_real_articles, test_sow_inventory_next_quarter_takes_over_once_published,
              test_sow_inventory_stale_old_data_is_rejected_not_shown, test_sow_inventory_falls_back_to_previous_quarter_only,
              test_sow_inventory_acceptance_window_rolls_with_calendar, test_latest_completed_quarter_helper,
              test_plausibility_helpers, test_crush_rate_out_of_range_rejected, test_poultry_profit_out_of_range_rejected, test_rmspread_change_range_not_mistaken_for_spread, test_arrival_forecast_change_and_out_of_range_rejected, test_export_inspections_limit_raised_and_truncation_detected, test_hog_ratio_each_price_must_be_plausible,
              test_frontend_and_backend_plausible_ranges_are_identical,
              test_meal_stock_real_weekly_article, test_meal_stock_takes_latest_article_across_pages_not_first_match, test_meal_stock_stale_data_rejected, test_meal_stock_requires_national_scope, test_meal_stock_region_other_subject_and_change_rejected, test_meal_stock_request_matches_user_capture, test_meal_stock_failure_modes_give_diagnostics,
              test_soy_import_real_articles_all_recognized, test_soy_import_full_flow_picks_august_2026, test_soy_import_falls_back_to_previous_month_when_latest_not_published, test_soy_import_acceptance_window_rolls_with_calendar, test_soy_import_year_inference_and_future_months, test_soy_import_synthetic_traps_rejected, test_soy_import_paginates_and_request_matches_user_capture, test_soy_import_failure_modes_give_diagnostics,
              test_reserve_real_articles_parsed_and_noise_excluded, test_reserve_full_flow_latest_auction_with_previous, test_reserve_uses_auction_date_not_publish_date, test_reserve_paginates_all_pages_latest_on_last_page, test_reserve_crude_oil_basis_never_mistaken_for_soybean_auction, test_reserve_integrity_check_and_derived_fields, test_reserve_stale_and_future_and_price_guards, test_reserve_auction_date_fallback_and_dedup, test_reserve_request_matches_user_capture, test_reserve_failure_modes_give_diagnostics,
              test_basis_real_articles_extraction_matches_manual_verification, test_basis_end_to_end_uses_latest_when_available, test_basis_falls_back_when_latest_articles_unparseable, test_basis_all_recent_articles_unparseable_gives_diagnostic, test_basis_stale_data_rejected, test_basis_range_and_change_only_rejected_synthetic, test_basis_implausible_value_rejected_by_fetch_function, test_basis_request_matches_user_capture, test_basis_future_articles_ignored, test_basis_failure_modes_give_diagnostics]
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
