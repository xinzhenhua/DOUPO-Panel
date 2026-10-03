# -*- coding: utf-8 -*-
"""
中国春节日历(纯标准库)
======================
为什么需要：国内豆粕库存消费比 = 月末库存 ÷ **当月消费量**。春节前饲料厂集中备货、假期里养殖/饲料/贸易停摆，
月消费量会随假期骤降又回升，比值被机械地压低或抬高，跟"供应是松是紧"没有关系。
已有的月度数据里能看到：2026-02(春节2月17日) 库消比 20.95%，前后月份是 12.45% 和 15.54%。
固定阈值(比如≥14%判偏空)在春节前后会不看行情地触发，所以春节扰动月不能套用固定阈值。

春节日期表(公历初一，2015~2035)：来自农历，逐年固定，不需要联网。
核心窗口 = 春节前10天 ~ 春节后21天：涵盖节前备货的最后阶段、约一周的假期、以及节后复工/恢复。
某个月与核心窗口重叠 ≥7 天，就算"春节扰动月"。
"""
from datetime import date, timedelta

SPRING_FESTIVAL = {
    2015: "2015-02-19", 2016: "2016-02-08", 2017: "2017-01-28", 2018: "2018-02-16", 2019: "2019-02-05",
    2020: "2020-01-25", 2021: "2021-02-12", 2022: "2022-02-01", 2023: "2023-01-22", 2024: "2024-02-10",
    2025: "2025-01-29", 2026: "2026-02-17", 2027: "2027-02-06", 2028: "2028-01-26", 2029: "2029-02-13",
    2030: "2030-02-03", 2031: "2031-01-23", 2032: "2032-02-11", 2033: "2033-01-31", 2034: "2034-02-19",
    2035: "2035-02-08",
}
CORE_BEFORE = 10        # 春节前10天起算
CORE_AFTER = 21         # 到春节后21天止
MIN_CORE_DAYS = 7       # 当月与核心窗口重叠天数达到这个数，算春节扰动月

# 阶段(按距春节初一的天数t)：t<0 节前备货；0<=t<=14 假期停摆(含假期约一周+节后一周的缓慢复工)；15<=t<=21 节后恢复
PHASE_BIAS = {
    "节前备货": "饲料厂集中提货备库，月消费偏高，库消比容易被压低",
    "假期停摆": "养殖/饲料/贸易停摆，月消费骤降，库消比容易被机械抬高",
    "节后恢复": "复工补库中，月消费回升但还没到常态，库消比仍偏高并逐步回落",
}


def spring_festival(year):
    s = SPRING_FESTIVAL.get(year)
    return date.fromisoformat(s) if s else None


def _phase(t):
    if t < 0:
        return "节前备货"
    if t <= 14:
        return "假期停摆"
    return "节后恢复"


def festival_month_context(year, month):
    """某个自然月的春节扰动情况。返回：
    {"festivalDate": 春节初一(iso), "coreDays": 当月落在核心窗口里的天数, "disturbed": 是否扰动月,
     "phase": 当月占比最多的阶段(不扰动时为None), "bias": 该阶段对库消比的影响说明}
    春节日期表之外的年份返回disturbed=False(不知道就不假装知道)。"""
    f = spring_festival(year)
    if f is None:
        return {"festivalDate": None, "coreDays": 0, "disturbed": False, "phase": None, "bias": None}
    d = date(year, month, 1)
    counts = {}
    while d.month == month:
        t = (d - f).days
        if -CORE_BEFORE <= t <= CORE_AFTER:
            ph = _phase(t)
            counts[ph] = counts.get(ph, 0) + 1
        d += timedelta(days=1)
    core = sum(counts.values())
    disturbed = core >= MIN_CORE_DAYS
    phase = max(counts, key=counts.get) if disturbed else None
    return {"festivalDate": f.isoformat(), "coreDays": core, "disturbed": disturbed, "phase": phase,
            "bias": PHASE_BIAS.get(phase) if phase else None}


# ---------------------------------------------------------------------------
# 国庆长假：每年10月1日固定，假期约一周(10/1~10/7或10/8，具体天数每年国务院公布，这里按一周估)。
# 影响比春节轻：油厂假期里常有计划停机/降负荷(2026年国庆油厂开机率预计约30%，近五年最低)，养殖/饲料/贸易放缓一周左右，
# 月消费被压低、库消比容易被抬高——但复工恢复快、也没有节前大规模备货。所以做成"轻度扰动"：不暂停判方向，只把票权降一档。
# 核心窗口 = 国庆前4天 ~ 后13天(9/27~10/14)，与某月重叠≥7天算国庆扰动月(实际只有10月)。
# ---------------------------------------------------------------------------
NATIONAL_BEFORE = 4
NATIONAL_AFTER = 13
NATIONAL_BIAS = {
    "节前备货": "节前少量备货，月消费略偏高",
    "假期停摆": "油厂假期计划停机/降负荷、养殖饲料贸易放缓约一周，月消费被压低，库消比容易被抬高(幅度比春节小)",
    "节后恢复": "复工补库中，月消费回升，库消比逐步回落",
}


def national_day_month_context(year, month):
    """某个自然月的国庆扰动情况，返回结构同festival_month_context(festivalDate=当年10月1日)。"""
    f = date(year, 10, 1)
    d = date(year, month, 1)
    counts = {}
    while d.month == month:
        t = (d - f).days
        if -NATIONAL_BEFORE <= t <= NATIONAL_AFTER:
            ph = "节前备货" if t < 0 else ("假期停摆" if t <= 7 else "节后恢复")
            counts[ph] = counts.get(ph, 0) + 1
        d += timedelta(days=1)
    core = sum(counts.values())
    disturbed = core >= MIN_CORE_DAYS
    phase = max(counts, key=counts.get) if disturbed else None
    return {"festivalDate": f.isoformat(), "coreDays": core, "disturbed": disturbed, "phase": phase,
            "bias": NATIONAL_BIAS.get(phase) if phase else None}


def holiday_month_context(year, month):
    """★统一入口：这个月受哪个长假扰动、扰动多强。春节=strong(库消比暂停判方向)，国庆=mild(降权不暂停)。
    同一个月两个都命中(不可能，春节在1~2月、国庆在10月)时取春节。不扰动时name/level为None。"""
    f = festival_month_context(year, month)
    if f["disturbed"]:
        return dict(f, name="春节", level="strong")
    n = national_day_month_context(year, month)
    if n["disturbed"]:
        return dict(n, name="国庆", level="mild")
    return dict(f, name=None, level=None)


# ---------------------------------------------------------------------------
# 日期级的"节前备货/假期"窗口(周度数据用，比月度的核心窗口更靠前)
# 饲料企业豆粕库存天数：饲料厂会在长假前提前提货备库(库存天数被抬高)，假期里采购停摆。
#   依据是Mysteel自己周报里的措辞(2026-09-11：'华南部分市场因节前备货略有增加'；09-18：'受双节临近影响，企业刚需补货')。
#   这种"提前备货"抬高的天数不代表真实的需求强弱，所以窗口内的读数票权降一档。
#   ★窗口已用真实数据校准(用户2026-10-01贴出的270周饲料库存天数，2021-05~2026-09)：5个春节合并，相对春节后基线(+10~+45天中位数)的平均超额——
#       节前42~21天：+0.1~+0.5天(几乎没有)；节前21~14天：+1.8天；节前14~7天：+2.9天；节前7~0天：+2.9天；节后7~14天：-0.1天(已回到基线)。
#     所以备货从节前约21天开始(原先暂定的10天漏掉了+1.8天那一段)，节后7天内回到正常。窗口=节前21天~节后7天。
#     国庆的备货更平缓(节前35~28天已+0.9天，逐步升到节前7~0天的+2.3天)，没有明显的起点，同样用21天。
#   中秋没有单独建日历(日期每年不同，有时与国庆相邻)；2026年中秋(9月25日)落在国庆前21天窗口里，一并覆盖了。
# ---------------------------------------------------------------------------
HOLIDAY_WINDOW_BEFORE = 21
HOLIDAY_WINDOW_AFTER = 7


def holiday_window(d, before=HOLIDAY_WINDOW_BEFORE, after=HOLIDAY_WINDOW_AFTER):
    """日期d(date对象或'YYYY-MM-DD')是否落在春节/国庆的备货-假期窗口里。
    返回None或{"name":"春节"/"国庆","daysTo":距假期第一天的天数(负=节前),"phase":"节前备货"/"假期","holidayDate":iso}。"""
    if not isinstance(d, date):
        try:
            d = date.fromisoformat(str(d)[:10])
        except ValueError:
            return None
    cands = []
    f = spring_festival(d.year)
    if f:
        cands.append(("春节", f))
    cands.append(("国庆", date(d.year, 10, 1)))
    nxt = spring_festival(d.year + 1)       # 12月底的日期，下一个春节在明年，但离得太远(>10天)不会命中；这里只处理同一年的
    for name, h in cands:
        t = (d - h).days
        if -before <= t <= after:
            return {"name": name, "daysTo": t, "phase": "节前备货" if t < 0 else "假期", "holidayDate": h.isoformat()}
    return None


# ★油厂开机率的春节停机扰动窗口：节前7天 ~ 节后14天，只对春节生效(国庆油厂不停机)。
#   依据(用户2026-10-02采样的真实开机率，2024-12~2026-09)：
#     春节2025-01-29：节前20天57、节前15天69、节前7天55、节前3天10、节后9天37、节后20天61 → 节前约7天开始掉，节后约14天回到常态
#     春节2026-02-17：节前13天67、节前6天43、节后7天15、节后10天40、节后14天54、节后24天55 → 同样
#     国庆2025-10-01：节前6天60、节后12天60，基线63% → 没有扰动，所以不处理
#   不处理的后果：节日停机时读数掉到10~40%，规则"<40偏多"会把放假误判成供应紧(2026-02-24 15.46%、2025-01-26 9.80%都是真实数据)。
CRUSH_FESTIVAL_BEFORE = 7
CRUSH_FESTIVAL_AFTER = 14


def crush_festival_window(d):
    """日期d是否在油厂开机率的春节停机扰动窗口内(节前7天~节后14天)。只认春节；返回None或同holiday_window的字典。"""
    w = holiday_window(d, before=CRUSH_FESTIVAL_BEFORE, after=CRUSH_FESTIVAL_AFTER)
    return w if w and w["name"] == "春节" else None


def festival_cohort(d):
    """'YYYY-MM'(或'YYYY-MM-DD')所在月的类别：'春节扰动月'/'国庆扰动月'/'平常月'。用于按同类月份比较历史分位。"""
    try:
        y, m = int(str(d)[:4]), int(str(d)[5:7])
    except ValueError:
        return None
    h = holiday_month_context(y, m)
    return "春节扰动月" if h["name"] == "春节" else "国庆扰动月" if h["name"] == "国庆" else "平常月"
