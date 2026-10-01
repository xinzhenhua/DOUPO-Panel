# -*- coding: utf-8 -*-
"""
历史序列存储 + 历史分位(纯标准库，没有第三方依赖)
==================================================
为什么需要：仪表盘里的阈值(美豆库消比5%/10%、国内库消比10%/14%、出口销售±40%…)都是暂定值，
没有历史数据就没法回答"当前值在历史上算高还是低"，也没法校准阈值。

两种数据来源：
  ① 一次性回填(backfill_history.py)：数据源本身能往前拉的——美豆库消比(PSD按市场年度)、
     出口净销售(ESR按市场年度取整周)、国内库消比(Mysteel月度平衡表)、豆粕周度库存(Mysteel周度)
  ② 日常累积(每次fetch_data.py运行时追加)：其余指标(基差/开机率/猪粮比…)的接口只返回最新值，
     没法往前拉，只能从现在开始每次抓取都存一个点，按日期去重，自然越积越多

存储：data/history/<key>.json，每个点一行(git diff干净，且每小时一次的提交里没有新点就不会产生改动)：
  {"key":..,"name":..,"unit":..,"freq":..,
  "points":[
  {"d":"2026-09","v":16.04,"pub":"2026-08-31"},
  ...
  ]}
点的字段：d=日期(年'2026'/月'2026-09'/日'2026-09-28')，v=数值，pub=数据发布日期(可选，同一个d有多个来源时后发布的优先)，
          x=附加信息dict(可选)
"""
import json
import os
import re
import statistics
from datetime import date as _date, timedelta as _timedelta

import cn_calendar

HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "history")
MIN_POINTS = 12            # 算"总体历史分位"至少需要的样本数，不够就只显示"历史积累中"，不给一个没有统计意义的百分位
MIN_SEASONAL_POINTS = 4    # 算"同月历史分位"至少需要的同月样本数(不同年份)

SERIES_META = {
    # ---- 可回填 ----
    "us_stocks_to_use": {"name": "美豆库存消费比(按市场年度)", "unit": "%", "freq": "yearly"},
    "esr_net_sales": {"name": "美豆出口净销售(周度，全部国家)", "unit": "吨", "freq": "weekly"},
    "meal_stu": {"name": "国内豆粕库存消费比(月度)", "unit": "%", "freq": "monthly"},
    "meal_stock": {"name": "国内豆粕商业库存(周度)", "unit": "万吨", "freq": "weekly"},
    "feed_days": {"name": "饲料企业豆粕库存天数(周度)", "unit": "天", "freq": "weekly"},
    # ---- 每天记录两个系统的方向(record_systems.py)：v=基本面(仅供需票)的净倾向(-1~+1)，x里是其余字段(市场结构方向/综合/价格/覆盖情况/规则版本) ----
    "systems_sep": {"name": "每日系统方向记录(9月合约：基本面仅供需 + 市场结构 + 价格)", "unit": "净倾向", "freq": "daily"},
    "systems_may": {"name": "每日系统方向记录(5月合约：基本面仅供需 + 市场结构 + 价格)", "unit": "净倾向", "freq": "daily"},
    "systems_jan": {"name": "每日系统方向记录(1月合约：基本面仅供需 + 市场结构 + 价格)", "unit": "净倾向", "freq": "daily"},
    # ---- 只能日常累积 ----
    "crush_rate": {"name": "油厂开机率", "unit": "%", "freq": "weekly"},
    "basis": {"name": "豆粕现货基差(沿海代表)", "unit": "元/吨", "freq": "daily"},
    "arrival_forecast": {"name": "大豆到港预报(按预报月份)", "unit": "万吨", "freq": "monthly"},
    "soy_import": {"name": "大豆月度进口量", "unit": "万吨", "freq": "monthly"},
    "reserve_auction": {"name": "国储进口大豆拍卖计划量", "unit": "万吨", "freq": "irregular"},
    "hog_ratio": {"name": "猪粮比", "unit": "", "freq": "daily"},
    "sow_inventory": {"name": "能繁母猪存栏(季度末)", "unit": "万头", "freq": "quarterly"},
    "poultry_profit": {"name": "白羽肉鸡养殖利润", "unit": "元/只", "freq": "weekly"},
    "rm_spread": {"name": "豆菜粕价差", "unit": "元/吨", "freq": "weekly"},
    # ---- 盘面压榨毛利(可回填：新浪日K线；只存各合约的"建议交易窗口"内的点，所以不同年份的同一窗口可比) ----
    # freq='seasonal-daily'：日频但只有窗口内的点，样本密度检查不适用；分位只看"往年同月"(seasonal)
    "crush_margin_sep": {"name": "盘面压榨毛利(9月合约，4-7月窗口)", "unit": "元/吨", "freq": "seasonal-daily"},
    "crush_margin_may": {"name": "盘面压榨毛利(5月合约，12-3月窗口)", "unit": "元/吨", "freq": "seasonal-daily"},
    "crush_margin_jan": {"name": "盘面压榨毛利(1月合约，8-11月窗口)", "unit": "元/吨", "freq": "seasonal-daily"},
    # ---- 月差/期限结构：近月-远月，占近月价格的百分比(不同年份价格水平不同，绝对价差不可比)；窗口同榨利 ----
    "term_spread_sep": {"name": "月差9-1(占近月价格%，4-7月窗口)", "unit": "%", "freq": "seasonal-daily"},
    "term_spread_may": {"name": "月差5-9(占近月价格%，12-3月窗口)", "unit": "%", "freq": "seasonal-daily"},
    "term_spread_jan": {"name": "月差1-5(占近月价格%，8-11月窗口)", "unit": "%", "freq": "seasonal-daily"},
}
# 每个合约类型的建议交易窗口(与前端合约选择里的窗口一致)：(合约月份, 窗口内的日历月, 窗口月份落在合约到期年的前一年的哪些月)
CRUSH_MARGIN_WINDOWS = {
    "sep": {"contractMonth": 9, "months": [4, 5, 6, 7], "prevYearMonths": []},
    "may": {"contractMonth": 5, "months": [12, 1, 2, 3], "prevYearMonths": [12]},
    "jan": {"contractMonth": 1, "months": [8, 9, 10, 11], "prevYearMonths": [8, 9, 10, 11]},
}


# ---------------------------------------------------------------------------
# 存取
# ---------------------------------------------------------------------------
def _path(key, base_dir=None):
    return os.path.join(base_dir or HISTORY_DIR, f"{key}.json")


def load_series(key, base_dir=None):
    """读取一个序列；文件不存在/损坏时返回空序列(不抛异常——历史数据不能拖垮主流程)。"""
    meta = SERIES_META.get(key, {})
    empty = {"key": key, "name": meta.get("name", key), "unit": meta.get("unit", ""),
             "freq": meta.get("freq", "irregular"), "points": []}
    try:
        with open(_path(key, base_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
        pts = [p for p in (data.get("points") or []) if isinstance(p, dict) and "d" in p and _is_num(p.get("v"))]
        empty["points"] = sorted(pts, key=lambda p: p["d"])
    except (OSError, ValueError):
        pass
    return empty


def save_series(series, base_dir=None):
    """每个点一行，按日期排序。返回写入路径。"""
    os.makedirs(base_dir or HISTORY_DIR, exist_ok=True)
    head = {k: series[k] for k in ("key", "name", "unit", "freq")}
    head_s = json.dumps(head, ensure_ascii=False, separators=(",", ":"))[:-1]   # 去掉最后的}，后面接points
    lines = [json.dumps(p, ensure_ascii=False, separators=(",", ":")) for p in sorted(series["points"], key=lambda p: p["d"])]
    text = head_s + ',\n"points":[\n' + ",\n".join(lines) + "\n]}\n"
    path = _path(series["key"], base_dir)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def merge_points(existing, new_points):
    """按日期d去重合并。同一个d有两个点时：都有pub就取pub更晚的(比如8月31日文章里对9月的预测，
    会被9月30日文章里对9月的更新值取代)；否则以新的为准。返回(合并后按日期排序的列表, 是否有变化)。"""
    by_d = {p["d"]: p for p in existing}
    changed = False
    for np_ in new_points:
        if not (isinstance(np_, dict) and "d" in np_ and _is_num(np_.get("v"))):
            continue
        old = by_d.get(np_["d"])
        if old is None:
            by_d[np_["d"]] = np_
            changed = True
            continue
        if old.get("pub") and np_.get("pub") and np_["pub"] < old["pub"]:
            continue          # 旧点来自更晚发布的来源，不被更早的覆盖
        if old != np_:
            by_d[np_["d"]] = np_
            changed = True
    return sorted(by_d.values(), key=lambda p: p["d"]), changed


def record_points(key, new_points, base_dir=None):
    """把新点合并进序列并落盘(没有变化就不写文件)。返回(序列, 是否有变化)。"""
    series = load_series(key, base_dir)
    merged, changed = merge_points(series["points"], new_points)
    series["points"] = merged
    if changed or not os.path.exists(_path(key, base_dir)):
        if merged:
            save_series(series, base_dir)
    return series, changed


# ---------------------------------------------------------------------------
# 分位
# ---------------------------------------------------------------------------
def percentile_rank(value, values):
    """value在values里的百分位(0~100)，相同值按一半计(mid-rank)，避免大量并列值时百分位失真。"""
    n = len(values)
    if n == 0:
        return None
    less = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return round((less + 0.5 * equal) / n * 100, 1)


def _year_month(d):
    m = re.match(r"^(\d{4})(?:-(\d{2}))?", str(d))
    if not m:
        return None, None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


def rolling_sum(points, window=4, max_gap_days=10):
    """周度序列的滚动合计(默认4周)，d=窗口最后一周。相邻两周间隔超过max_gap_days(缺周)的窗口跳过，
    不拿缺了周的窗口冒充完整的4周。用于出口净销售——单周噪音太大，4周合计更稳。"""
    from datetime import date as _d
    pts = sorted(points, key=lambda p: p["d"])
    out = []
    for i in range(window - 1, len(pts)):
        win = pts[i - window + 1:i + 1]
        try:
            ds = [_d.fromisoformat(p["d"][:10]) for p in win]
        except ValueError:
            continue
        if any((ds[j + 1] - ds[j]).days > max_gap_days for j in range(len(ds) - 1)):
            continue
        out.append({"d": pts[i]["d"], "v": sum(p["v"] for p in win)})
    return out


# 样本代表性要求(仅周度/日度/月度序列)：既要跨度够长，又不能是"东一个西一个"的稀疏样本。
# ★第一次回填里豆粕周度库存有70个点，但2023年只有3个、2025年只有1个、中间空了近两年——直接算百分位会严重失真
#   (比如漏掉了2026年5月34.74万吨的真实低点)，所以样本不连续时明确说"不连续"，不给百分位。
MIN_SPAN_DAYS = {"weekly": 180, "daily": 180, "monthly": 330}
MIN_DENSITY = 0.5           # 实际期数 ÷ 跨度内应有期数，低于它算不连续
RECENT_WINDOW_DAYS = 730    # 整体不连续时退回只看最近这么多天


def _to_date(d):
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", str(d))
    if not m:
        return None
    return _date(int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1))


def coverage_problem(points, freq):
    """样本是否有代表性。返回None(可用)或原因文字。points已剔除当前点。"""
    if freq not in MIN_SPAN_DAYS or len(points) < 2:
        return None
    d0, d1 = _to_date(points[0]["d"]), _to_date(points[-1]["d"])
    if not d0 or not d1:
        return None
    span = (d1 - d0).days
    if span < MIN_SPAN_DAYS[freq]:
        return f"样本只跨{span}天，不足{MIN_SPAN_DAYS[freq]}天"
    expected = {"weekly": span / 7 + 1, "daily": span * 5 / 7 + 1, "monthly": span / 30.4 + 1}[freq]
    density = len(points) / expected
    if density < MIN_DENSITY:
        return f"样本不连续：跨{span}天应有约{int(expected)}期，实际只有{len(points)}期({int(density * 100)}%)"
    return None


def summarize(points, value, cur_d, freq=None, cohort_fn=None):
    """当前值value(日期cur_d)在历史里的位置。参考样本里剔除cur_d自己(不能拿自己跟自己比)。
    percentile：全部历史样本里的分位。样本<MIN_POINTS期，或样本不连续/跨度太短(coverage_problem)时为None——宁可说"积累中"也不给失真的分位。
    seasonal：同一个日历月、不同年份的样本(周度/日度/月度序列才有)；同年份的不算，避免跟当前值高度相关的近邻点混进来。
    cohort：cohort_fn(点)→类别标签(如'春节扰动月'/'平常月')；只跟当前值同类别的历史点比(至少4个)——
            春节前后月消费骤变，春节月的库消比只能跟往年春节月比，不能跟平常月比。"""
    refs = [p for p in points if p["d"] != cur_d and _is_num(p.get("v"))]
    window = None
    problem = coverage_problem(refs, freq) if len(refs) >= MIN_POINTS else None
    if problem and freq in MIN_SPAN_DAYS:
        # ★整体样本不连续(比如早年零零散散、近两年才开始逐周累积)时，退回只看最近RECENT_WINDOW_DAYS天：
        #   近两年连续的话就用它，不让早年的零散点永久拖累；近两年也不连续才说"不给分位"。
        last = _to_date(refs[-1]["d"])
        recent = [p for p in refs if last and _to_date(p["d"]) and (last - _to_date(p["d"])).days <= RECENT_WINDOW_DAYS]
        if len(recent) >= MIN_POINTS and coverage_problem(recent, freq) is None:
            refs, problem, window = recent, None, f"整体样本不连续，仅用最近{RECENT_WINDOW_DAYS // 365}年的连续样本({recent[0]['d']}起)"
    vals = [p["v"] for p in refs]
    n = len(vals)
    out = {"n": n, "minPoints": MIN_POINTS, "asOf": cur_d, "since": refs[0]["d"] if refs else None,
           "percentile": None, "min": None, "max": None, "median": None, "seasonal": None, "cohort": None, "sparse": None, "window": window}
    if n:
        out["min"], out["max"], out["median"] = round(min(vals), 2), round(max(vals), 2), round(statistics.median(vals), 2)
    if n >= MIN_POINTS and problem is None:
        out["percentile"] = percentile_rank(value, vals)
    elif problem:
        out["sparse"] = problem
    cy, cm = _year_month(cur_d)
    if cm is not None and freq not in ("yearly",) and problem is None:
        same = [p["v"] for p in refs if _year_month(p["d"])[1] == cm and _year_month(p["d"])[0] != cy]
        if len(same) >= MIN_SEASONAL_POINTS:
            out["seasonal"] = {"month": cm, "n": len(same), "percentile": percentile_rank(value, same),
                               "median": round(statistics.median(same), 2)}
        elif same:
            out["seasonal"] = {"month": cm, "n": len(same), "percentile": None, "median": None}
    if cohort_fn is not None:
        label = cohort_fn({"d": cur_d})
        same_c = [p["v"] for p in refs if cohort_fn(p) == label]
        if label:
            out["cohort"] = {"label": label, "n": len(same_c),
                             "percentile": percentile_rank(value, same_c) if len(same_c) >= MIN_SEASONAL_POINTS else None,
                             "median": round(statistics.median(same_c), 2) if same_c else None}
    return out


# ---------------------------------------------------------------------------
# 出口净销售的两类数据毛病(第一次回填报告里发现的)
# ---------------------------------------------------------------------------
# ① 美国政府停摆(2018-12-22~2019-01-25)导致ESR周报延迟、补发：2019-02-14这一周净销售677万吨，而前一周是0
#    (稳健异常检测z=9.0，相邻周0和212万吨)，2019-01-03是-61万吨。这段时间的周度数字不可靠，剔除。
ESR_ARTIFACT_RANGES = [("2018-12-20", "2019-02-28")]


def is_rollover_week(d):
    """市场年度切换周：周截止日落在8月31日~9月6日(恰好包含9月1日的那一周)。
    ② 每年切换周的净销售系统性偏高：报告里12年逐年的这一周都是尖峰(比前后两周高一到三倍，2020年564万吨)。
       原因(推断)：新年度第一周的"本年度净销售"里带入了上年度已经报过的"下年度销售"(结转)，
       而我们把 本年度净销售+下年度净销售 加总，等于把结转的部分重复算了一次。"""
    try:
        m, day = int(str(d)[5:7]), int(str(d)[8:10])
    except ValueError:
        return False
    return (m == 8 and day == 31) or (m == 9 and day <= 6)


def clean_esr_points(points, max_gap_days=10):
    """出口周度序列的清洗(读取时做，落盘的原始点不动)：剔除政府停摆期间的点；
    市场年度切换周用相邻两周的均值代替(前后两周都在、且间隔正常才代替，否则丢弃这个点)。"""
    pts = [p for p in sorted(points, key=lambda p: p["d"])
           if not any(a <= p["d"][:10] <= b for a, b in ESR_ARTIFACT_RANGES)]
    out = []
    for i, p in enumerate(pts):
        if not is_rollover_week(p["d"]):
            out.append(p)
            continue
        if 0 < i < len(pts) - 1:
            try:
                g1 = (_date.fromisoformat(p["d"][:10]) - _date.fromisoformat(pts[i - 1]["d"][:10])).days
                g2 = (_date.fromisoformat(pts[i + 1]["d"][:10]) - _date.fromisoformat(p["d"][:10])).days
            except ValueError:
                continue
            if g1 <= max_gap_days and g2 <= max_gap_days:
                out.append({"d": p["d"], "v": (pts[i - 1]["v"] + pts[i + 1]["v"]) / 2, "x": {"rolloverAdjusted": True}})
    return out


# ---------------------------------------------------------------------------
# 日常累积：每次fetch_data.py运行后，把各指标最新值追加进序列，并把历史分位挂到对应结果上
# ---------------------------------------------------------------------------
_QUARTER_END_MONTH = {"一": 3, "二": 6, "三": 9, "四": 12}


def _day(s):
    return str(s)[:10] if s else None


def _month_from_label(label):
    m = re.search(r"(\d{4})年(\d{1,2})月", str(label or ""))
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}" if m else None


def _quarter_end_from_label(label):
    m = re.search(r"(\d{4})年(一|二|三|四)季度", str(label or ""))
    return f"{int(m.group(1)):04d}-{_QUARTER_END_MONTH[m.group(2)]:02d}" if m else None


def _simple_specs():
    """(结果字段, 序列key, 取(日期, 数值, 发布日期, 附加信息)的函数, 什么情况下不记录)"""
    return [
        ("mysteelCrushRate", "crush_rate", lambda r: (_day(r.get("date")), r.get("value"), None, None)),
        ("mysteelBasis", "basis", lambda r: (_day(r.get("date")), r.get("value"), None, {"city": r.get("city")})),
        ("mysteelPoultryProfit", "poultry_profit", lambda r: (_day(r.get("date")), r.get("value"), None, None)),
        ("mysteelRmSpread", "rm_spread", lambda r: (_day(r.get("date")), r.get("value"), None, None)),
        ("hogRatio", "hog_ratio", lambda r: (_day(r.get("date")), r.get("value"), None, None)),
        ("mysteelArrivalForecast", "arrival_forecast",
         lambda r: (f"{int(r['forecastYear']):04d}-{int(r['forecastMonth']):02d}", r.get("value"), _day(r.get("date")), None)),
        ("mysteelSoyImport", "soy_import", lambda r: (_month_from_label(r.get("monthLabel")), r.get("value"), _day(r.get("date")), None)),
        ("mysteelReserveAuction", "reserve_auction",
         lambda r: (_day(r.get("auctionDate")), r.get("value"), None, {"soldRate": r.get("soldRate")})),
        ("sowInventory", "sow_inventory", lambda r: (_quarter_end_from_label(r.get("quarterLabel")), r.get("value"), _day(r.get("date")), None)),
        ("supplyDemand", "us_stocks_to_use",
         lambda r: (str(r["marketYear"]) if r.get("commodity") else None, r.get("stocksToUsePct"), None, None)),
    ]


def update_and_attach(result, base_dir=None):
    """把result里各指标的最新值追加进历史序列，并给每个结果挂上history(历史分位摘要)。
    任何一个指标出错都只跳过它自己，绝不影响其它指标、更不影响latest.json的写出。返回本次新增/更新了点的序列key列表。"""
    touched, errors = [], []

    def note(key, err):
        errors.append(f"{key}: {err}")

    for rk, key, extract in _simple_specs():
        try:
            res = result.get(rk)
            if not (isinstance(res, dict) and res.get("available")):
                continue
            d, v, pub, x = extract(res)
            if not d or not _is_num(v):
                continue
            pt = {"d": d, "v": v}
            if pub:
                pt["pub"] = pub
            if x:
                pt["x"] = {k: val for k, val in x.items() if val is not None}
                if not pt["x"]:
                    del pt["x"]
            series, changed = record_points(key, [pt], base_dir)
            if changed:
                touched.append(key)
            res["history"] = summarize(series["points"], v, d, series["freq"])
        except Exception as e:  # noqa: BLE001 - 历史是锦上添花，不能拖垮主流程
            note(rk, e)

    # 国内豆粕周度库存：把搜索窗口里所有能提取出数字的周都记下来(recentWeeks)，不只是最新一周——
    #   回填时Mysteel周报大多没法补全(摘要没数字、正文改版)，所以靠每次抓取顺带把窗口里已有的周补齐，缺的周从此不再缺。
    try:
        res = result.get("mysteelMealStock")
        if isinstance(res, dict) and res.get("available") and _is_num(res.get("value")):
            pts = []
            for w in (res.get("recentWeeks") or []) + [{"date": res.get("date"), "value": res.get("value"), "week": res.get("weekLabel")}]:
                d = _day(w.get("date"))
                if d and _is_num(w.get("value")):
                    p = {"d": d, "v": w["value"]}
                    if w.get("week"):
                        p["x"] = {"week": w["week"]}
                    pts.append(p)
            series, changed = record_points("meal_stock", pts, base_dir)
            if changed:
                touched.append("meal_stock")
            res["history"] = summarize(series["points"], res["value"], _day(res.get("date")), series["freq"])
    except Exception as e:  # noqa: BLE001
        note("mysteelMealStock", e)

    # 饲料企业豆粕库存天数：搜索窗口里所有能提取出数字的周(recentWeeks)都记下来——第一次运行就能一次性累积出整段历史，
    #   不需要单独回填；环比/同比(文章里写的变动量)存在x里。
    try:
        res = result.get("mysteelFeedDays")
        if isinstance(res, dict) and res.get("available") and _is_num(res.get("value")):
            pts = []
            for w in list(res.get("recentWeeks") or []) + [{"date": res.get("date"), "value": res.get("value"), "mom": res.get("momDays"), "yoy": res.get("yoyDays")}]:
                d = _day(w.get("date"))
                if d and _is_num(w.get("value")):
                    p = {"d": d, "v": w["value"]}
                    x = {k: w[k] for k in ("mom", "yoy") if _is_num(w.get(k))}
                    if x:
                        p["x"] = x
                    pts.append(p)
            series, changed = record_points("feed_days", pts, base_dir)
            if changed:
                touched.append("feed_days")
            res["history"] = summarize(series["points"], res["value"], _day(res.get("date")), series["freq"])
    except Exception as e:  # noqa: BLE001
        note("mysteelFeedDays", e)

    # 盘面压榨毛利：三个合约各存一条序列(逐日追加)；分位只看"往年同月"——毛利的绝对数没有意义(没扣加工费，几乎永远为正)，
    #   只有跟历史同期比才知道"油厂现在的压榨动力强还是弱"。需要往年数据(回填)，没有回填时seasonal为空，前端不据此计分。
    try:
        for k in ("sep", "may", "jan"):
            res = (result.get("crushMargins") or {}).get(k)
            if not (isinstance(res, dict) and res.get("available") and res.get("date") and _is_num(res.get("grossMargin"))):
                continue
            key = "crush_margin_" + k
            series, changed = record_points(key, [{"d": _day(res["date"]), "v": res["grossMargin"], "x": {"contract": res.get("mealSymbol")}}], base_dir)
            if changed:
                touched.append(key)
            res["history"] = summarize(series["points"], res["grossMargin"], _day(res["date"]), series["freq"])
    except Exception as e:  # noqa: BLE001
        note("crushMargins", e)

    # 月差/期限结构：跟榨利同一套——三个合约类型各存一条序列，分位只看"往年同月"(粮食的月差有强烈的季节性，比如5-9月差受南美到港节奏影响)。
    try:
        for k in ("sep", "may", "jan"):
            res = (result.get("termSpreads") or {}).get(k)
            if not (isinstance(res, dict) and res.get("available") and res.get("date") and _is_num(res.get("spreadPct"))):
                continue
            key = "term_spread_" + k
            series, changed = record_points(key, [{"d": _day(res["date"]), "v": res["spreadPct"], "x": {"near": res.get("nearSymbol"), "far": res.get("farSymbol"), "spread": res.get("spread")}}], base_dir)
            if changed:
                touched.append(key)
            res["history"] = summarize(series["points"], res["spreadPct"], _day(res["date"]), series["freq"])
    except Exception as e:  # noqa: BLE001
        note("termSpreads", e)

    # 国内库消比：只记"文章明示/由库存÷消费推算"的月度值；"周度库存÷预计消费"是回退推算，不是月度平衡表的数，不进历史。
    #   同时存下当月库存/消费/产量(以后要做"春节调整后库消比"、按同类月份比较时用得上)。
    #   分位按"同类月份"比：春节扰动月只跟往年春节扰动月比，平常月只跟平常月比(cn_calendar)。
    try:
        res = result.get("mysteelMealStu")
        if isinstance(res, dict) and res.get("available") and _is_num(res.get("value")):
            if res.get("method") in ("stated", "computed"):
                x = {"how": res["method"]}
                for k, src in (("stock", "stockWan"), ("consumption", "consumptionWan"), ("production", "productionWan")):
                    if _is_num(res.get(src)):
                        x[k] = res[src]
                pt = {"d": res["month"], "v": res["value"], "pub": _day(res.get("date")), "x": x}
                series, changed = record_points("meal_stu", [pt], base_dir)
                if changed:
                    touched.append("meal_stu")
            else:
                series = load_series("meal_stu", base_dir)
            res["history"] = summarize(series["points"], res["value"], res["month"], "monthly",
                                       cohort_fn=lambda p: cn_calendar.festival_cohort(p["d"]))
    except Exception as e:  # noqa: BLE001
        note("mysteelMealStu", e)

    # 出口净销售：把最近8周逐周记下来(每周都补齐，原始值不动)；分位用"近4周合计"跟历史同口径比较，
    #   比较前先做清洗(剔除政府停摆期间、市场年度切换周用相邻两周均值代替，见clean_esr_points)。
    #   最新一周本身就是切换周时不给分位(前端也不据此判方向)。
    try:
        res = result.get("exportSales")
        if isinstance(res, dict) and res.get("available") and res.get("commodity"):
            pts = []
            for w in res.get("recentWeeks") or []:
                if _is_num(w.get("netSalesMT")) and w.get("weekEnding"):
                    x = {k: w[k] for k in ("chinaNetSalesMT", "unknownNetSalesMT") if _is_num(w.get(k))}
                    p = {"d": _day(w["weekEnding"]), "v": w["netSalesMT"]}
                    if x:
                        p["x"] = x
                    pts.append(p)
            series, changed = record_points("esr_net_sales", pts, base_dir)
            if changed:
                touched.append("esr_net_sales")
            cur4 = res.get("total4wSumMT")
            if _is_num(cur4) and not res.get("latestIsRollover"):
                roll = rolling_sum(clean_esr_points(series["points"]), 4)
                res["history"] = summarize(roll, cur4, _day(res.get("weekEnding")), "weekly")
                res["history"]["basis"] = "近4周净销售合计"
    except Exception as e:  # noqa: BLE001
        note("exportSales", e)

    if errors:
        import sys
        print("[WARN] 历史序列更新时有指标出错(已跳过，不影响其它数据): " + "; ".join(errors), file=sys.stderr)
    return touched
