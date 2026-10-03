# -*- coding: utf-8 -*-
"""
Mysteel搜索结果的解析器(纯函数：文本进、事实出，不联网、不做业务判断)。供历史回填使用。

★设计原则(来自用户2026-10-02跑采样诊断拿到的真实数据——不是凭一条样本写的)：
  1. 宁严勿松：只收明确的写法，逐一枚举，不用"万能正则"。采样里搜索词匹配到的大量是噪声(天气、南美产量、日报顺带提到"到港量")，
     宽松的正则会把噪声当数据。
  2. 上下文校验：数值前后必须是目标主体。例："砂石矿山开机率28.96%"被"开机率"关键词误匹配，不是油厂。
  3. 排除"累计/1-N月/合计/分国别"：海关会合并公布1-2月累计，没有单月数据，缺失是真实的，不是解析问题。
  4. 月度数据多篇交叉验证：同一个月在多篇文章里重复出现(进口量2023-06有5篇)，多数一致才采用；冲突的月份(2023-08：936×3 vs 717×1)
     不让错误值悄悄进历史。只有一篇的月份标注single，由调用方决定用不用。
  5. 每个解析器同时返回"被排除的及原因"，便于下次诊断。
"""
import re
from collections import defaultdict


_DASHES = str.maketrans({"－": "-", "—": "-", "–": "-", "~": "-", "～": "-", "－": "-"})


def _clean(text):
    """去掉所有空白(搜索结果正文里的换行/空格位置不稳定，如'据海关总署数据显示 ：中国')；
    并把全角连字符/破折号/波浪线统一成半角'-'。★真实陷阱：'2026年1－2月中国大豆进口1254.7万吨'(全角－)是1-2月累计，
    原先的排除词只认半角'-'，它被当成了2026-02=1254.7(真正的2月是597.6)；同一篇里还有1月657.1、2月597.6，靠同篇内值矛盾才暴露。"""
    return re.sub(r"\s+", "", str(text or "")).translate(_DASHES)


# ===========================================================================
# 1. 中国大豆月度进口量(海关总署数据，Mysteel文章转述)
# ===========================================================================
_V = r"(?P<v>\d+(?:\.\d+)?)万吨"
_YM = r"(?:(?P<y>\d{4})年)?(?P<m>\d{1,2})月(?:份)?"
# 逐一枚举真实出现过的单月写法(都来自2022-04~2026-07的真实样本)：
_IMPORT_PATS = [
    # 中国2025年6月大豆进口1226.4万吨 / 中国3月大豆进口量为635.3万吨
    re.compile(r"中国" + _YM + r"大豆进口(?:量)?(?:约为|约|为|达)?" + _V),
    # 2023年5月份中国大豆进口量1202万吨 / 5月中国大豆进口量约为966.5万吨 / 2023年3月中国进口大豆量为685.3万吨
    re.compile(_YM + r"中国(?:大豆进口量|进口大豆量|大豆进口)(?:约为|约|为|达)?" + _V),
    # 12月大豆进口数量攀升至1055.5万吨
    re.compile(_YM + r"大豆进口(?:数量|量)?(?:攀升至|增至|降至|为|达到|达)" + _V),
]
# 紧邻匹配点的这些字样说明不是"单月进口量"(累计/合并公布的1-2月/分国别…)
_IMPORT_OTHER_PERIOD = re.compile(r"去年|上年|前年|去岁|作为对比|对比|较|比")
# 范围/累计写法的真实分隔符：半角- (85次)、全角－(6次，_clean已统一成-)、至(4次，'1月至2月')、顿号(2次，'1、2月')
_IMPORT_BAD = re.compile(r"累计|\d+-\d+月|\d+月至\d+月|\d+、\d+月|合计|年初至今|前\d+月|头\d+个月|共计|上半年|下半年|季度|同期|从[^，。]{1,6}进口")


def parse_soy_import(text, pub_date):
    """一篇文章里的所有单月进口量。pub_date='YYYY-MM-DD'(发布日，用于推断没写年份的月份)。
    返回([{"month":"YYYY-MM","value":万吨}], [被排除的说明])。"""
    t = _clean(text)
    out, rejected = [], []
    for p in _IMPORT_PATS:
        for m in p.finditer(t):
            ctx = t[max(0, m.start() - 12): m.end() + 1]
            if _IMPORT_BAD.search(ctx):
                rejected.append(f"累计/合并/分国别写法: {ctx[:40]}")
                continue
            # ★指向其他时期的写法：紧挨在匹配前面的"去年/上年/前年/作为对比/较/比"说明这个数不是本月的
            #   (真实例子：2023-09-08那篇'去年8月份中国大豆进口量为717万吨'——是2022年8月，被当成2023-08，
            #    靠同月另外3篇936万吨的多数一致才没进历史；如果那个月只有这一篇，错误值就直接进去了)
            if _IMPORT_OTHER_PERIOD.search(t[max(0, m.start() - 8): m.start()]):
                rejected.append(f"指向其他时期(去年/对比): {t[max(0, m.start() - 8): m.end()][:40]}")
                continue
            mo = int(m.group("m"))
            if not 1 <= mo <= 12:
                continue
            explicit = bool(m.group("y"))
            if explicit:
                y = int(m.group("y"))
            else:
                # 没写年份：数据当月的次月发布，所以年份=发布年；若月份>发布月，说明是去年的数据(推断，可能出错)
                py, pm = int(pub_date[:4]), int(pub_date[5:7])
                y = py if mo <= pm else py - 1
            out.append({"month": f"{y:04d}-{mo:02d}", "value": float(m.group("v")), "yearExplicit": explicit})
    # 同一篇里同月重复(多个写法命中同一句)去重
    seen, uniq = set(), []
    for r in out:
        k = (r["month"], r["value"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq, rejected


def _months_between(data_month, pub_date):
    y, m = int(data_month[:4]), int(data_month[5:7])
    return (int(pub_date[:4]) - y) * 12 + (int(pub_date[5:7]) - m)


# 推断年份的单篇观察，只在"发布月 - 数据月"不超过这个月数时采用。依据(用户2026-10-02采样的真实数据)：
#   推断年份的观察与同月"年份明确"的观察对照，13个全部一致、0个不一致；它们的发布月-数据月间隔：1个月36个、2个月6个、3个月1个，没有跨年错误。
#   间隔更久的(回顾类文章)容易引用旧月份，不采用。
MAX_INFERRED_LAG_MONTHS = 3


def select_import_months(observations, include_inferred_single=False):
    """月度进口量的采用规则。observations: [(month, value, pub_date, year_explicit)]。
    返回(采用的{month:{value,n,pubs,how}}, 存疑的[...], 未采用的single月份[(month,value,pub,原因)])。
      · 多篇一致/多数一致(agree/majority)：采用
      · 只有一篇、且原文写明了'YYYY年M月'：采用，标how='single'(官方数据+明确写法+已过累计/去年/对比防护；2022-01的885就是这种，确认是对的)
      · 只有一篇、年份是靠发布日期推断的：发布月-数据月≤3个月才采用(实测13/13与明确年份一致)，更晚发布的回顾类文章不采用；
        include_inferred_single=True则全部采用"""
    explicit = {(m, v, p): ex for m, v, p, ex in observations}
    acc, doubt = cross_verify_monthly([(m, v, p) for m, v, p, _ in observations])
    skipped = {}
    for mo in list(acc):
        info = acc[mo]
        if info["how"] != "single":
            continue
        pub = info["pubs"][0]
        if include_inferred_single or explicit.get((mo, info["value"], pub), False):
            continue
        lag = _months_between(mo, pub)
        if 0 <= lag <= MAX_INFERRED_LAG_MONTHS:
            info["how"] = "single_inferred"          # 采用，但标出年份是推断的，便于以后核查
            continue
        skipped[mo] = (mo, info["value"], pub, f"只有一篇、年份靠发布日期推断，且发布月-数据月={lag}个月(>{MAX_INFERRED_LAG_MONTHS}，回顾类文章容易引用旧月份)，不采用")
        del acc[mo]
    return acc, doubt, list(skipped.values())


# ===========================================================================
# 2. 大豆到港预报(Mysteel每月月底发下月预估，每月1篇)
# ===========================================================================
# 真实写法(2023-11~2026-06共32个月，没有缺月)：
#   2024年9月份国内全样本油厂大豆到港预估133.5船，共计约867.75万吨
#   2024年2月份国内主要地区125家油厂大豆到港预估68船，共计约442万吨
#   Mysteel农产品团队预估，2026年1月份国内全样本油厂大豆到港117.2船，共计约761.80万吨
# 样本口径的三种叫法(都是真实出现过的)：国内全样本油厂 / 国内主要地区N家油厂 / 国内主要油厂(2024-08那一篇，漏掉它会让序列在2024-08断一个月)
_ARRIVAL_PAT = re.compile(r"(?P<y>\d{4})年(?P<m>\d{1,2})月份国内(?:全样本|主要地区\d+家|主要)油厂大豆到港(?:预估)?(?P<ships>\d+(?:\.\d+)?)船[，,]共计约?(?P<v>\d+(?:\.\d+)?)万吨")
# ★刻意不处理2026-06之后的新写法("Mysteel预估2026年10月国内全样本油厂大豆到港约854.10万吨，11月预计870万吨，12月950万吨")：
#   ①那是每日累积正在抓的(fetch_mysteel_arrival_forecast)，回填是补历史，由每日累积接上；
#   ②一篇给出当月+后两个月的预估，后两个月是"远月数据后期可能修正"的初步预估，不能当当月值；样本只有4~5篇，没法验证区分规则。


def parse_arrival_forecast(text, pub_date):
    """预报文章：返回([{"month":"YYYY-MM","value":万吨,"ships":船数}], [被排除的说明])。
    严格要求"国内…油厂大豆到港…船，共计约…万吨"整句结构——采样里搜索词匹配到的大量是日报/快讯里顺带提到'到港量'的噪声(天气、南美产量、化肥)。"""
    t = _clean(text)
    by_month = defaultdict(list)
    for m in _ARRIVAL_PAT.finditer(t):
        mo = int(m.group("m"))
        if not 1 <= mo <= 12:
            continue
        by_month[f"{int(m.group('y')):04d}-{mo:02d}"].append({"value": float(m.group("v")), "ships": float(m.group("ships")), "sample": m.group(0)[:40]})
    out, rejected = [], []
    for month, items in by_month.items():
        vals = {i["value"] for i in items}
        if len(vals) > 1:
            # ★同一篇里同一个月给了多个不同的万吨值：Mysteel在2023-11~2024-01同时发布了两个样本口径(111家 783.25万吨 / 123家 845万吨，相差8%)，
            #   样本家数在扩大(111→123→125→全样本)，口径不同则船数和万吨都不可比。不替用户悄悄选一个，整月不采用，写进存疑。
            rejected.append(f"{month}: 同一篇出现{len(vals)}个口径({', '.join(f'{i['sample'][12:20]}…{i['value']:g}万吨' for i in items)})，不可比，不采用")
            continue
        out.append({"month": month, "value": items[0]["value"], "ships": items[0]["ships"]})
    return out, rejected


# ===========================================================================
# 3. 豆菜粕现货价差(沿海地区，区间写法)
# ===========================================================================
# 真实写法(2024-07~2026-06几乎全是这一种)：
#   截至2025年6月3日，国内沿海地区豆菜粕现货价差上涨，价差在320-440元/吨之间，涨30元/吨
#   今日国内豆菜粕价差上涨，截至2024年7月5日，国内沿海地区豆菜粕现货价差在600-760元/吨之间，涨…
_RM_PATS = [
    re.compile(r"截至(?:(?P<y>\d{4})年)?(?P<mo>\d{1,2})月(?P<d>\d{1,2})日[，,]?国内沿海地区豆菜粕现货价差[^，。]{0,6}[，,]?价差在(?P<lo>\d{2,4})-(?P<hi>\d{2,4})元/吨之间"),
    re.compile(r"截至(?:(?P<y>\d{4})年)?(?P<mo>\d{1,2})月(?P<d>\d{1,2})日[，,]?国内沿海地区豆菜粕现货价差在(?P<lo>\d{2,4})-(?P<hi>\d{2,4})元/吨之间"),
]


def parse_rm_spread(text, pub_date):
    """返回([{"date":"YYYY-MM-DD","low":..,"high":..,"mid":区间中点}], [被排除的说明])。
    只收"沿海地区豆菜粕现货价差在LO-HI元/吨之间"的区间写法(与生产抓取一致：取区间中点)。
    不收：价格报告里的'备注'(不含价差)、空内容、单值写法(散文里的'价差850元/吨'，口径不同)。"""
    t = _clean(text)
    out, rejected = [], []
    for p in _RM_PATS:
        for m in p.finditer(t):
            lo, hi = int(m.group("lo")), int(m.group("hi"))
            if lo > hi:
                rejected.append(f"区间上下限颠倒: {lo}-{hi}")
                continue
            mo, d = int(m.group("mo")), int(m.group("d"))
            if m.group("y"):
                y = int(m.group("y"))
            else:
                py, pm = int(pub_date[:4]), int(pub_date[5:7])
                y = py if mo <= pm else py - 1
            try:
                import datetime as _dt
                dd = _dt.date(y, mo, d)
            except ValueError:
                rejected.append(f"日期不合法: {y}-{mo}-{d}")
                continue
            out.append({"date": dd.isoformat(), "low": lo, "high": hi, "mid": (lo + hi) / 2})
    seen, uniq = set(), []
    for r in out:
        if r["date"] not in seen:
            seen.add(r["date"])
            uniq.append(r)
    return uniq, rejected


# ===========================================================================
# 4. 油厂开机率(Mysteel快讯，日频)
# ===========================================================================
# 真实写法(2024-12~2026-10)：
#   开机方面，今日全国动态全样本油厂开机率为63.11%，较前一日下降2.81%
#   开机方面，今日全国动态全样本油厂开机率上升至56.58% / 下降至52.33% / 开机率50.82%(无动词)
# ★陷阱：同一个快讯接口里还有别的行业——"砂石矿山开机率28.96%，较上周提升10.82个百分点"(2026-03-06)，不是油厂。
#   所以必须要求"油厂开机率"，不能只看"开机率+数字+%"。
# ★春节期间油厂真的会停机到10%上下(2025-01-26=9.80%、2026-02-24=15.46%，原文"较前一日下降33.33%/上升7.20%")，
#   2025年4月中美关税战时也有25~29%的连续低谷——这些是真实数据，不是源头错误。
_CRUSH_PAT = re.compile(r"油厂开机率(?:为|上升至|下降至|回升至|回落至|增至|降至|小幅上升至|小幅下降至)?(?P<v>\d{1,3}(?:\.\d+)?)%")


def parse_crush_rate(text, pub_date):
    """一条快讯里的油厂开机率。返回([{"date":发布日,"value":%}], [被排除的说明])。
    只取"油厂开机率…X%"；一条快讯里有多个时取第一个(开机方面通常只有一句)。"""
    t = _clean(text)
    rejected = []
    if "开机率" in t and "油厂开机率" not in t:
        rejected.append("含'开机率'但不是'油厂开机率'(别的行业的快讯，如砂石矿山)")
    m = _CRUSH_PAT.search(t)
    if not m:
        return [], rejected
    v = float(m.group("v"))
    if not 5.0 <= v <= 100.0:
        rejected.append(f"开机率{v}%超出合理范围(5~100)")
        return [], rejected
    return [{"date": pub_date, "value": v}], rejected


# ===========================================================================
# 月度数据的多篇交叉验证
# ===========================================================================
def cross_verify_monthly(observations, tol=0.01):
    """observations: [(month, value, pub_date)]。同月多篇文章：取多数一致的值。
    返回(采用的{month: {"value","n","pubs","how"}}, 冲突/存疑的[{...}])。
      how='agree'   ：≥2篇且多数在±tol内一致，取多数的中位数——可信
      how='single'  ：只有1篇——无法交叉验证，调用方自己决定用不用
      how='majority'：有冲突但多数一致(如936×3 vs 717×1)，取多数，同时把被少数派否决的值记在冲突里
      冲突无多数(如2篇各一个值)：不采用，记入冲突。"""
    by = defaultdict(list)
    for mo, v, pub in observations:
        by[mo].append((v, pub))
    accepted, doubtful = {}, []
    for mo in sorted(by):
        vals = by[mo]
        if len(vals) == 1:
            accepted[mo] = {"value": vals[0][0], "n": 1, "pubs": [vals[0][1]], "how": "single"}
            continue
        # 找"最大的一致簇"：以每个值为中心，数±tol内有多少个
        best = None
        for v0, _ in vals:
            cluster = [v for v, _ in vals if abs(v - v0) <= tol * max(abs(v0), 1e-9)]
            if best is None or len(cluster) > len(best):
                best = cluster
        n_all = len(vals)
        if len(best) == n_all:
            accepted[mo] = {"value": sorted(best)[len(best) // 2], "n": n_all, "pubs": [p for _, p in vals], "how": "agree"}
        elif len(best) * 2 > n_all:
            outl = [(v, p) for v, p in vals if v not in best]
            accepted[mo] = {"value": sorted(best)[len(best) // 2], "n": n_all, "pubs": [p for _, p in vals], "how": "majority"}
            doubtful.append({"month": mo, "adopted": accepted[mo]["value"], "overruled": outl, "all": vals})
        else:
            doubtful.append({"month": mo, "adopted": None, "overruled": [], "all": vals, "reason": "没有多数一致"})
    return accepted, doubtful
