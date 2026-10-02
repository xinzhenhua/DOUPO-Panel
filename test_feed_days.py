# -*- coding: utf-8 -*-
"""饲料企业豆粕库存天数：用户2026-09-30贴出的Mysteel真实搜索结果(20期，2026-05-15~09-24)驱动的测试。
独立成文件(不和test_history.py混在一起)。运行：python3 test_feed_days.py"""
import os, sys, tempfile, shutil, traceback
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd
import history_store as hs
import cn_calendar as cc

_pass = 0
def ok(m):
    global _pass; _pass += 1; print("✅", m)

# (标题里的日期, 摘要原文, 期望天数, 期望环比, 期望同比)——期望值是逐期对照原文手工核对的
FEED_REAL = [
    ('2026-09-24', '截至9月24日，全国饲料企业豆粕物理库存8.55天，较上期增0.32天，同比减1.05天。进口大豆供应充足，油厂高开机致库存增加，国庆假期停机或缓解压力。豆粕M01合约呈“成本端有支撑、现货端有压制”格局，预计短期区间震荡。因下游需求下滑及价格高企抑制消费，现货价格或震荡运行，基差缓慢修复。本周全国库存小幅增加，东北、福建及华北增幅较大，广东因涨价抑制需求库存略降。', 8.55, 0.32, -1.05),
    ('2026-09-18', '截至9月18日，全国饲料企业豆粕物理库存8.23天，环比微增0.08天，同比下降1.19天。近期连粕冲高回落，油厂开机率高、库存偏高且催提积极，但下游提货节奏偏慢。受双节临近影响，企业刚需补货，但高价下积极性一般。中美关税磋商推进，贸易休战预期增加，美豆出口向好支撑盘面。区域上，四川、华北等地库存增加，福建、广东等地因涨价抑制需求，库存略降。', 8.23, 0.08, -1.19),
    ('2026-09-11', '截至9月11日，全国饲料企业豆粕物理库存8.15天，环比减0.22天，同比减1.07天。近期连盘豆粕高位震荡，外盘成本支撑与供应宽松博弈。虽库存环比下降但仍处同期偏高，油厂催提明显，基差深度贴水致成交清淡。短期受USDA报告及进口成本攀升影响，价格料维持震荡，但供需宽松压制基差。区域上两湖等地库存降幅较大，华南部分市场因节前备货略有增加。', 8.15, -0.22, -1.07),
    ('2026-09-04', '截至9月4日，全国饲料企业豆粕物理库存8.37天，环比增0.27天，同比减0.43天。连粕M2701合约报收3388元/吨，现货基差维持M2701-110至-160元/吨。近期油厂开机略低于预估，催提积极，终端补库意愿平平。江苏、两湖及广东等地库存增幅较大，广西、福建及四川等地因涨价抑制需求，库存略有下降。预计连粕短期维持区间高位震荡运行。', 8.37, 0.27, -0.43),
    ('2026-08-28', '截至8月28日，全国饲料企业豆粕物理库存8.1天，环比增0.52天，同比减0.77天。近期连粕偏强震荡，但国内大豆到港高峰延续，油厂压榨高位，供给充裕。库存小幅增加主要因油厂催提及企业适当增加头寸，非养殖端主动补库，现货成交持续性不足。除四川市场消化前期库存导致天数下降外，鲁豫、东北及广东等地增幅较大。基本面仍约束价格上行空间，饲料企业维持刚需随采，集中备货意愿偏弱。', 8.1, 0.52, -0.77),
    ('2026-08-21', '截至8月21日，全国饲料企业豆粕物理库存7.58天，环比增0.10天，同比减0.93天。受美豆成本支撑及国内供强需弱影响，连粕震荡运行，现货成交意愿差限制价格上涨。油厂压榨高位，豆粕库存累积至115万吨。华北、广东等地库存增幅较大，四川、福建等地以消化前期库存为主。国储拍卖成交良好，市场对远期供应缺口预期建立。', 7.58, 0.1, -0.93),
    ('2026-08-14', '截至8月14日，全国饲料企业豆粕物理库存7.48天，环比持平，同比减0.87天。基本面供应压力较大，沿海油厂大豆及豆粕库存处高位，成交清淡，下游维持刚需采购。主力M2701合约偏弱运行，虽美豆成本端有支撑，但国内高库存压制近月反弹空间。区域上，江苏等地库存下降，四川、东北等地因催提积极库存略增。整体看，全国库存稳定，同比呈下降态势。', 7.48, 0.0, -0.87),
    ('2026-08-07', '截至8月7日，全国饲料企业豆粕物理库存7.48天，环比微降。近期连粕冲高至3120元/吨压力位，现货普遍上调但成交降温，下游谨慎刚需补库。当前供强需弱，油厂高压榨致库存破百万吨，催提现象普遍，限制价格上涨空间。但受进口成本上移预期支撑，价格底部坚实。短期豆粕市场将在成本支撑与供需压力间博弈，现货区间震荡偏强，重心缓慢上移，基差缩窄，回调深度有限。', 7.48, None, None),
    ('2026-07-31', '截至7月31日，全国饲料企业豆粕物理库存7.54天，环比微降。期货M09合约资金离场，维持弱势震荡，关注3030-3050点支撑。现货因月底合同有限及到港成本高，油厂挺价，基差修复至-80到-100元/吨。但油厂库存近百万吨且持续累库，预计8月催提力度加大。在美豆天气溢价退场及国内供需宽松背景下，预计豆粕现货一口价在2950-3050元/吨承压运行，基差在-80至-120元/吨区间震荡。', 7.54, None, None),
    ('2026-07-24', '截至7月24日，全国饲料企业豆粕物理库存7.57天，环比微降。油厂高开机致库存累积，供应压力凸显；养殖端因亏损调整配方，需求承压，高价抑制补库意愿。期货M09合约高位震荡，多空博弈加剧。当前市场核心矛盾为成本推升与供强需弱，基差短期难修复，预计现货价格延续高位震荡，市场等待回调后触发大规模补库。', 7.57, None, None),
    ('2026-07-17', '截至7月17日，全国饲料企业豆粕物理库存7.63天，环比微增。供应端油厂高开机致库存累积至77.95万吨，需求端因养殖亏损及高温天气表现清淡，企业多随用随采。M2609合约受供强需弱影响，预计在3050-3100元/吨区间震荡。现货因油厂催提及替代效应，价格易跌难涨，基差窄幅波动。后续需关注美豆生长及中国采购情况。', 7.63, None, None),
    ('2026-07-10', '截至7月10日，全国饲料企业豆粕物理库存7.58天，环比增0.17天，同比减0.34天。供需呈现实宽松、预期偏紧格局，油厂高压榨致库存进入季节性累库周期，现货基差偏弱。虽美豆天气升水支撑盘面震荡走强，但供强需弱基本面未变，短期单边大涨动力不足。下游随采随用，追涨意愿低，操作以区间波段为主。预计豆粕现货易跌难涨，基差底部震荡，重点跟踪美豆天气与国内到港节奏。', 7.58, 0.17, -0.34),
    ('2026-07-03', '截至7月3日，全国饲料企业豆粕物理库存为7.41天，环比微增0.17天，同比下滑0.50天。供应端受7月超千万吨大豆到港及油厂高开机率影响，豆粕持续累库，局部出现胀库停机；需求端因养殖亏损，饲企维持随采随用低库存策略，仅四川、福建等地库存增幅较明显。尽管外盘天气题材提振情绪，但国内供强需弱格局未改，连粕在3000元/吨附近承压，短期呈现震荡走势。油厂挺价意愿较强，但现货基差在催提压力下预计继续下探。考虑到下半年成本驱动，价格重心或有缓慢上移预期，部分饲企已开始试探性增加采购头寸，整体市场仍以区间震荡为主。', 7.41, 0.17, -0.5),
    ('2026-06-26', '全国饲料企业豆粕库存7.24天，环比微增但同比略降。供应端压力显著，7月进口大豆到港维持高位，油厂高开机率推动库存加速累积；需求端受养殖亏损影响，企业采购谨慎，维持低库存策略。外盘天气题材短期提振内盘情绪，但高库存弱需求格局未改，反弹空间有限，预计维持震荡。基差承压运行，地区间库存增减不一，催提现象频现。', 7.24, None, None),
    ('2026-06-18', '全国饲料企业豆粕库存7.15天，环比微增0.09天，同比减0.59天。进口大豆压榨利润跌至盈亏线，油厂挺价意愿强，但开机率维持70%高位，豆粕供应压力不减。下游采购积极性一般，随用随采策略拖累现货价格。区域库存分化明显，福建、江苏、广西增幅较大，四川、东北、鲁豫小幅下降。豆粕期货主力合约区间震荡，现货价格进入长周期筑底阶段，基差承压。', 7.15, 0.09, -0.59),
    ('2026-06-12', '全国饲料企业豆粕库存天数7.06天，环比微增0.12天，同比略增0.23天。市场受外盘成本承压与内盘供需过剩双重压制，油厂进入加速累库周期，但压榨亏损支撑挺价意愿，限制下跌空间。区域分化明显，福建、东北及广西库存增幅较大，四川、广东小幅下降。现货价格陷入横盘格局，基差持续承压，短期缺乏明确利好驱动。', 7.06, 0.12, 0.23),
    ('2026-06-05', '据Mysteel农产品对全国主要地区的50家饲料企业样本调查显示，截至6月5日（2026年第23周），全国饲料企业豆粕物理库存6.94天，较上一期减0.08天，较去年同期增0.63天。', 6.94, -0.08, 0.63),
    ('2026-05-29', '据Mysteel农产品对全国主要地区的50家饲料企业样本调查显示，截至5月29日（2026年第22周），全国饲料企业豆粕物理库存7.02天，较上一期增0.41天，较去年同期增1.03天。', 7.02, 0.41, 1.03),
    ('2026-05-22', '据Mysteel农产品对全国主要地区的50家饲料企业样本调查显示，截至5月22日（2026年第21周），全国饲料企业豆粕物理库存6.61天，较上一期减0.14天，较去年同期增0.88天。', 6.61, -0.14, 0.88),
    ('2026-05-15', '据Mysteel农产品对全国主要地区的50家饲料企业样本调查显示，截至5月15日（2026年第20周），全国饲料企业豆粕物理库存6.75天，较上一期减0.58天，较去年同期增1.61天。', 6.75, -0.58, 1.61),
]


class Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="feed_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def _items():
    """把20期真实摘要包装成搜索接口返回的dataList(标题带(YYYYMMDD)，跟真实一致)。"""
    out = []
    for d, txt, *_ in FEED_REAL:
        out.append({"title": f"Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（{d.replace('-', '')}）", "publishTime": f"{d} 17:30",
                    "content": txt, "url": f"https://ncp.mysteel.com/a/{d}.html"})
    return out


def _fetch_with(items, today=date(2026, 9, 30), total=None):
    old = fd.fetch_json_debug
    seen = []
    def fake(url, headers=None, retries=3, timeout=20, post_data=None):
        seen.append(post_data)
        return {"resultCode": 0, "total": total if total is not None else len(items), "dataList": items}, {}
    fd.fetch_json_debug = fake
    try:
        return fd.fetch_mysteel_feed_days(today=today), seen
    finally:
        fd.fetch_json_debug = old


# ===================== 解析器 =====================
def test_parser_all_20_real_articles():
    for d, txt, ev, em, ey in FEED_REAL:
        r, _rej = fd._extract_feed_days(txt)
        assert r is not None, f"{d}: 没提取出库存天数"
        assert (r["value"], r["mom"], r["yoy"]) == (ev, em, ey), f"{d}: 期望{(ev, em, ey)}，实际{(r['value'], r['mom'], r['yoy'])}"
    ok("解析器：20期真实摘要的库存天数/环比/同比全部与手工核对一致")


def test_parser_not_fooled_by_other_numbers_in_the_summary():
    """摘要里有很多别的数字：'豆粕库存累积至115万吨'(8-21)、'库存累积至77.95万吨'(7-17)、'开机率维持70%'、M2701合约、3388元/吨。"""
    by = {d: txt for d, txt, *_ in FEED_REAL}
    assert "115万吨" in by["2026-08-21"] and fd._extract_feed_days(by["2026-08-21"])[0]["value"] == 7.58
    assert "77.95万吨" in by["2026-07-17"] and fd._extract_feed_days(by["2026-07-17"])[0]["value"] == 7.63
    assert "3388元/吨" in by["2026-09-04"] and fd._extract_feed_days(by["2026-09-04"])[0]["value"] == 8.37
    ok("解析器：不会把'115万吨''77.95万吨''3388元/吨'当成库存天数")


def test_parser_wording_variants_found_in_real_data():
    """9月24日和5~6月初那几期写'较上期增/较上一期减/较去年同期增'，不是'环比/同比'——只认后者会漏掉这5期。"""
    r, _ = fd._extract_feed_days("全国饲料企业豆粕物理库存8.55天，较上期增0.32天，同比减1.05天。")
    assert r == {"value": 8.55, "mom": 0.32, "yoy": -1.05}, r
    r, _ = fd._extract_feed_days("全国饲料企业豆粕物理库存6.94天，较上一期减0.08天，较去年同期增0.63天。")
    assert r == {"value": 6.94, "mom": -0.08, "yoy": 0.63}, r
    r, _ = fd._extract_feed_days("全国饲料企业豆粕物理库存7.48天，环比持平，同比减0.87天。")
    assert r["mom"] == 0.0 and r["yoy"] == -0.87, "环比持平=0"
    r, _ = fd._extract_feed_days("全国饲料企业豆粕物理库存7.48天，较上期持平，较去年同期持平。")
    assert r["mom"] == 0.0 and r["yoy"] == 0.0
    r, _ = fd._extract_feed_days("全国饲料企业豆粕库存天数7.06天，环比微增0.12天，同比略增0.23天。")
    assert r == {"value": 7.06, "mom": 0.12, "yoy": 0.23}, "'库存天数7.06天'、'同比略增'"
    r, _ = fd._extract_feed_days("全国饲料企业豆粕物理库存7.54天，环比微降。")
    assert r["value"] == 7.54 and r["mom"] is None and r["yoy"] is None, "只写方向没有数字：不猜"
    r, _ = fd._extract_feed_days("全国饲料企业豆粕库存7.24天，环比微增但同比略降。")
    assert r["mom"] is None and r["yoy"] is None
    ok("解析器：兼容'较上期/较上一期/较去年同期'，环比持平=0，只有方向没数字时不猜")


def test_parser_never_takes_a_change_as_the_stock():
    assert fd._extract_feed_days("同比下滑0.50天，环比微增0.17天")[0] is None, "没有库存本身：不能把变动量当库存"
    r, rej = fd._extract_feed_days("库存环比增加0.17天，物理库存为7.41天")
    assert r["value"] == 7.41 and any("变动量" in x for x in rej)
    r, rej = fd._extract_feed_days("全国饲料企业豆粕物理库存88天")
    assert r is None and any("超出合理范围" in x for x in rej), "88天超出1~30天合理范围"
    ok("解析器：变动量不会被当成库存；荒谬数值(88天)被拒绝")


def test_mom_stated_equals_consecutive_difference_in_real_data():
    """自洽检查：文章写的环比 = 本期 - 上期。20期里有数字的环比全部吻合，既验证解析器也说明数据源内部一致。"""
    checked = 0
    for i in range(len(FEED_REAL) - 1):
        (d0, _t0, v0, m0, _y0), (d1, _t1, v1, _m1, _y1) = FEED_REAL[i], FEED_REAL[i + 1]
        if m0 is not None:
            assert abs((v0 - v1) - m0) <= 0.015, f"{d0}: 写的环比{m0}，实际差{round(v0 - v1, 3)}"
            checked += 1
    # 20期里：14期环比带数字(含1期"环比持平"=0)，5期只写"微增/微降"没数字，最早一期(5-15)没有更早的一期可比
    assert checked == 14, f"应有14期带数字的环比可以核对，实际{checked}"
    ok("真实数据自洽：14期带数字的环比(含1期环比持平=0)全部等于相邻两期的差")


# ===================== 完整抓取流程 =====================
def test_full_fetch_flow_with_real_20_weeks():
    r, seen = _fetch_with(_items())
    assert r["available"] is True
    assert r["value"] == 8.55 and r["date"] == "2026-09-24" and r["momDays"] == 0.32 and r["yoyDays"] == -1.05
    assert r["lastYearValue"] == 9.6, "去年同期=本期-同比变动=8.55-(-1.05)=9.60"
    assert r["extractedFrom"] == "summary" and r["publishDate"] == "2026-09-24"
    assert len(r["recentWeeks"]) == 20 and r["recentWeeks"][0]["date"] == "2026-09-24" and r["recentWeeks"][-1]["date"] == "2026-05-15"
    assert [w["value"] for w in r["recentWeeks"]][:3] == [8.55, 8.23, 8.15]
    assert r["holiday"] == {"name": "国庆", "daysTo": -7, "phase": "节前备货", "holidayDate": "2026-10-01"}, r["holiday"]
    p = seen[0]
    assert p["query"] == "全国主要地区饲料企业豆粕库存天数调查" and p["pageSize"] == 20 and p["platform"] == "pc" and p["startTime"] == "2025-09-30 00:00:00"
    ok("完整流程：20期真实数据 → 8.55天/环比+0.32/同比-1.05/去年同期9.6/国庆前7天窗口/20周recentWeeks")


def test_full_fetch_flow_holiday_none_for_mid_september():
    # 窗口已按真实数据校准为节前21天：9-04距国庆27天(不在窗口)、9-11距国庆20天(在窗口)
    items = [i for i in _items() if "20260904" in i["title"]]
    r, _ = _fetch_with(items, today=date(2026, 9, 8))
    assert r["date"] == "2026-09-04" and r["value"] == 8.37 and r["holiday"] is None, "9-04距国庆27天，不在备货窗口"
    items = [i for i in _items() if "20260911" in i["title"]]
    r2, _ = _fetch_with(items, today=date(2026, 9, 14))
    assert r2["date"] == "2026-09-11" and r2["holiday"] == {"name": "国庆", "daysTo": -20, "phase": "节前备货", "holidayDate": "2026-10-01"}, r2["holiday"]
    ok("完整流程：9-04(距国庆27天)不在备货窗口；9-11(距国庆20天)在窗口内(窗口已按数据校准为节前21天)")


def test_fetch_stale_and_not_feed_articles_and_failures():
    old = [i for i in _items() if "20260515" in i["title"]]
    r, _ = _fetch_with(old, today=date(2026, 9, 30))
    assert r["available"] is False and "超过30天" in r["reason"] and "停更" in r["reason"]
    r, _ = _fetch_with([{"title": "Mysteel：豆粕现货价格日评", "publishTime": "2026-09-24 10:00", "content": "价格上涨"}])
    assert r["available"] is False and "饲料企业豆粕库存天数" in r["reason"]
    r, _ = _fetch_with([{"title": "Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（20260924）", "publishTime": "2026-09-24 17:00", "content": "库存偏高，请关注。"}])
    assert r["available"] is False and "措辞可能变了" in r["reason"]
    ok("完整流程：停更(>30天)/不是这个系列的文章/摘要里没有数字，都给出明确原因")


def test_last_year_value_only_when_yoy_is_a_number():
    items = [i for i in _items() if "20260807" in i["title"]]          # 环比微降、没有同比数字
    r, _ = _fetch_with(items, today=date(2026, 8, 10))
    assert r["value"] == 7.48 and r["yoyDays"] is None and r["lastYearValue"] is None
    ok("去年同期值：同比没有数字时为None，不编造")


# ===================== 节假日窗口 =====================
def test_holiday_window_dates():
    w = cc.holiday_window
    assert w("2026-09-24") == {"name": "国庆", "daysTo": -7, "phase": "节前备货", "holidayDate": "2026-10-01"}
    assert w("2026-09-10")["daysTo"] == -21 and w("2026-09-09") is None, "窗口=节前21天(用270周真实数据校准：节前21~14天平均超额+1.8天，更早几乎没有)"
    assert w("2026-09-18")["daysTo"] == -13, "9-18距国庆13天：在窗口内(原先暂定10天时不在)"
    assert w("2026-10-08")["daysTo"] == 7 and w("2026-10-08")["phase"] == "假期" and w("2026-10-09") is None, "窗口=节后7天"
    assert w("2026-09-04") is None and w("2026-07-10") is None, "距国庆27天/远离假期：不在窗口"
    assert w("2027-01-30") == {"name": "春节", "daysTo": -7, "phase": "节前备货", "holidayDate": "2027-02-06"}
    assert w("2027-02-13")["phase"] == "假期" and w("2027-02-14") is None
    assert w(date(2026, 9, 24))["name"] == "国庆" and w("坏") is None and w("") is None
    assert w("2040-02-01") is None, "春节日期表之外的年份：不知道就不假装知道(国庆是固定日期，仍然有)"
    assert w("2040-09-25")["name"] == "国庆"
    ok("节假日窗口：节前10天~节后7天；9-24命中、9-18不命中；春节/国庆；坏输入None")


# ===================== 历史累积与分位 =====================
def test_history_real_20_weeks_span_too_short_for_percentile():
    """★真实场景：这20期只跨约4个月。历史样本必须跨度够长(周度≥180天)才给分位——所以第一次运行时如果older文章解析不出来，
    只有这20期的话会显示'暂不给分位'和原因，而不是拿4个月的样本给一个失真的百分位。"""
    r, _ = _fetch_with(_items())
    with Tmp() as d:
        res = {"mysteelFeedDays": r}
        touched = hs.update_and_attach(res, base_dir=d)
        assert "feed_days" in touched
        pts = hs.load_series("feed_days", d)["points"]
        assert len(pts) == 20 and pts[0]["d"] == "2026-05-15" and pts[-1]["d"] == "2026-09-24"
        assert pts[-1]["x"] == {"mom": 0.32, "yoy": -1.05}, "环比/同比存在x里"
        h = r["history"]
        span = (date(2026, 9, 18) - date(2026, 5, 15)).days
        assert h["n"] == 19 and h["percentile"] is None and f"样本只跨{span}天，不足180天" in h["sparse"], h
        assert hs.update_and_attach({"mysteelFeedDays": r}, base_dir=d) == [], "重复运行无变化"
    ok("历史累积：20期(跨126天)→样本跨度不足，暂不给分位并写明原因；重复运行无变化")


def test_history_full_year_gives_percentile():
    """如果older文章也解析成功、凑够一整年：分位可用。用20期真实数据 + 合成的更早33周(2025-09-26~2026-05-08)。"""
    from datetime import timedelta
    real, _ = _fetch_with(_items())
    early = []
    for i in range(33):
        dd = date(2025, 9, 26) + timedelta(days=7 * i)
        early.append({"d": dd.isoformat(), "v": round(8.9 - 0.07 * i, 2)})          # 合成：从8.9缓降到6.6
    with Tmp() as d:
        hs.record_points("feed_days", early, d)
        hs.update_and_attach({"mysteelFeedDays": real}, base_dir=d)
        h = real["history"]
        vals = [p["v"] for p in hs.load_series("feed_days", d)["points"] if p["d"] != "2026-09-24"]
        assert h["n"] == 52 and h["sparse"] is None and h["percentile"] == hs.percentile_rank(8.55, vals), h
        assert h["percentile"] is not None and 60 < h["percentile"] < 100
        assert h["since"] == "2025-09-26"
    ok("历史累积：凑够一整年(52期)→给出分位，样本剔除本期自己")


def test_recent_weeks_records_every_extractable_week():
    r, _ = _fetch_with(_items())
    assert [w["date"] for w in r["recentWeeks"]] == sorted([d for d, *_ in FEED_REAL], reverse=True)
    assert r["recentWeeks"][7] == {"date": "2026-08-07", "value": 7.48, "mom": None, "yoy": None}, "只写方向的周：值照记，环比同比为None"
    ok("recentWeeks：20周全部记录，只写方向的周值照记")


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
