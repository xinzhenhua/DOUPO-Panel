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
    "basis": {"name": "豆粕现货基差(沿海代表，Mysteel，v101.7起停止更新)", "unit": "元/吨", "freq": "daily"},
    "poultry_ndrc": {"name": "肉鸡养殖预期盈利(发改委价格监测中心×卓创)", "unit": "元/只", "freq": "weekly"},
    "spot_basis": {"name": "豆粕现货基差(生意社现货价-主力合约，自算)", "unit": "元/吨", "freq": "daily"},
    "arrival_forecast": {"name": "大豆到港预报(按预报月份)", "unit": "万吨", "freq": "monthly"},
    "soy_import": {"name": "大豆月度进口量", "unit": "万吨", "freq": "monthly"},
    "reserve_auction": {"name": "国储进口大豆拍卖计划量", "unit": "万吨", "freq": "irregular"},
    "hog_ratio": {"name": "猪粮比", "unit": "", "freq": "daily"},
    "sow_inventory": {"name": "能繁母猪存栏(季度末)", "unit": "万头", "freq": "quarterly"},
    "poultry_profit": {"name": "白羽肉鸡养殖利润", "unit": "元/只", "freq": "weekly"},
    "rm_spread": {"name": "豆菜粕价差", "unit": "元/吨", "freq": "weekly"},
    # ---- 资金面(v101)：龙虎榜主力合约的席位净持仓(日频，每个点带x.contract——主力合约会换月，不同合约的净持仓规模完全不同，不可比；
    #      "连续N日/近N日变化"只能在同一个合约内算，见consecutive_run/change_over) + CFTC管理基金净多(周频，可立即回填156周) ----
    "capital_gs_net": {"name": "高盛期货净持仓(龙虎榜主力合约，正=净多；换月不可比，点带合约代码)", "unit": "手", "freq": "daily"},
    "capital_jpm_net": {"name": "摩根大通净持仓(龙虎榜主力合约，正=净多；换月不可比，点带合约代码)", "unit": "手", "freq": "daily"},
    "capital_ubs_net": {"name": "瑞银期货净持仓(龙虎榜主力合约，正=净多；换月不可比，点带合约代码)", "unit": "手", "freq": "daily"},
    "capital_zl_net": {"name": "中粮期货净持仓(龙虎榜主力合约，负=净空；换月不可比，点带合约代码)", "unit": "手", "freq": "daily"},
    "capital_gt_net": {"name": "国投期货净持仓(龙虎榜主力合约，负=净空；换月不可比，点带合约代码)", "unit": "手", "freq": "daily"},
    "cftc_mm_net": {"name": "CFTC管理基金净多(CBOT豆粕，周频，d=报告日期周二)", "unit": "手", "freq": "weekly"},
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
import re as _re

# ===================== 序列质量声明：口径断点 + 已知可疑点 =====================
# 原始点永远保留在文件里(可追溯、可撤销)；只是计算分位/校准时不用它们。
#
# ★口径断点：该日期之前的点和之后的点"口径不同，不可比"，计算分位时只用断点之后的。
#   meal_stock(豆粕周度库存)：Mysteel在每期周报的"特别声明"里写——"为了数据更能贴合市场变化趋势，Mysteel农产品对样本点进行了优化，
#   自2024年1月5日(第一周)开始，网页端只发一版动态全样本数据，原口径历史数据在钢联数据终端可查看"。(用户2026-10-01核对原文)
#   也就是2024-01-05之前(我们回填到的2022-06起的约31个点：2022年28个+2023年3个)是旧口径，之后是"动态全样本"口径，混在一起算分位/阈值校准没有意义。
#   ⚠️"动态全样本"意味着样本点本身会随时间调整，2024年之后的数据也不能保证完全同口径——这是个残留的不确定性，只能如实标注。
SERIES_BREAKS = {
    "meal_stock": ("2024-01-05", "Mysteel 2024年1月5日起网页端只发一版动态全样本数据，之前的旧口径不可比"),
}
# ★已知可疑点：{序列key: {日期: 原因}}。离群、且缺少佐证、又无法在现有数据里核实的点，计算分位时不用(文件里仍保留)。
#   meal_stu 2025-04 = 1.56%：是整条序列(其余5.9%~21%)里的离群最小值；该点只存了"how":"stated"，没有存期末库存/消费量，无法反算；
#   周度库存在2024-12-25~2025-09-30之间只有1个点，无法交叉验证；但同期饲料库存天数创5年最低(2025-04-25 4.35天)，说明当时确实极度紧缺——
#   所以既不能证实也不能证伪(用户2026-10-01决定不再追查)。不让它继续悬着：不参与分位，文件里保留。以后核实了真实值，删掉这一行即可恢复。
KNOWN_SUSPECT_POINTS = {
    "meal_stu": {"2025-04": "离群最小值(1.56%，其余5.9%~21%)，缺期末库存/消费量佐证，无法在现有数据里核实"},
}


def usable_points(key, points):
    """计算分位/校准时真正用的点：去掉口径断点之前的、去掉已知可疑点。原始点不动。"""
    brk = SERIES_BREAKS.get(key)
    bad = KNOWN_SUSPECT_POINTS.get(key) or {}
    out = []
    for p in points:
        if brk and str(p["d"])[:10] < brk[0]:
            continue
        if str(p["d"]) in bad or str(p["d"])[:7] in bad:
            continue
        if key == "crush_rate" and cn_calendar.crush_festival_window(str(p["d"])[:10]):
            continue                      # ★春节停机窗口(节前7天~节后14天)的读数是放假，不是供应松紧：不进参照分布(否则p0/p20会被拉到10~15%)
        out.append(p)
    return out


def excluded_points(key, points):
    """被排除的点及原因(给报告/校准用)：[(日期, 原因)]。"""
    brk = SERIES_BREAKS.get(key)
    bad = KNOWN_SUSPECT_POINTS.get(key) or {}
    out = []
    for p in points:
        d = str(p["d"])
        if brk and d[:10] < brk[0]:
            out.append((d, "口径断点之前：" + brk[1]))
        elif d in bad or d[:7] in bad:
            out.append((d, "已知可疑点：" + bad.get(d, bad.get(d[:7]))))
        elif key == "crush_rate" and cn_calendar.crush_festival_window(d[:10]):
            out.append((d, "春节停机窗口(节前7天~节后14天)：放假，不代表供应松紧"))
    return out


def window_ok(d, ctype, expiry_year):
    """日期d(YYYY-MM-DD)是否落在这个合约类型(到期年expiry_year)的建议交易窗口内。回填和每日累积共用同一个判断。
    9月合约：到期年的4-7月；5月合约：到期年前一年的12月 + 到期年的1-3月；1月合约：到期年前一年的8-11月。"""
    w = CRUSH_MARGIN_WINDOWS[ctype]
    y, m = int(d[:4]), int(d[5:7])
    if m not in w["months"]:
        return False
    return y == expiry_year - 1 if m in w["prevYearMonths"] else y == expiry_year


def expiry_year_of(symbol_or_code):
    """'M2609'/'2609'/'M2701' → 到期年份2026/2026/2027；解析不了返回None。"""
    m = _re.search(r"(\d{2})(\d{2})$", str(symbol_or_code or ""))
    return 2000 + int(m.group(1)) if m else None


def in_trading_window(d, ctype, symbol):
    """每日累积用：这一天、这个合约(代码如M2609)是否在建议交易窗口内。合约代码解析不了时返回False(宁可不记，也不把来源不明的点混进去)。"""
    ey = expiry_year_of(symbol)
    return ey is not None and window_ok(d, ctype, ey)


def prune_out_of_window(key, ctype, base_dir=None, symbol_field="contract"):
    """一次性清理：删掉序列里窗口外的旧点(之前每日累积没有按窗口过滤，把窗口外/临近到期的数据也记进来了)。
    x里取不到合约代码的点保留(不确定的不删)。返回删掉的点数。"""
    series = load_series(key, base_dir)
    keep, removed = [], []
    for p in series["points"]:
        sym = (p.get("x") or {}).get(symbol_field)
        ey = expiry_year_of(sym)
        if ey is not None and not window_ok(p["d"], ctype, ey):
            removed.append(p)
        else:
            keep.append(p)
    if removed:
        series["points"] = keep
        save_series(series, base_dir)
    return len(removed)


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


# ===================== 资金面：同一合约内的"连续N日"和"近N日变化"(v101) =====================
# 为什么必须"同一合约内"：龙虎榜的主力合约会换月(M2701→M2705)，换月前后同一个席位的净持仓规模完全不同(M2701高盛15万手 vs M2705可能几千手)。
#   跨合约相减会得到一个假的巨大变化。所以：每个点带x.contract；从最新点往回算，遇到合约变了就停；
#   也不能跨过缺的交易日(采集失败)——相邻两点之间如果隔着一个没有点的交易日，就不是"连续"，同样停。
def _trading_day_between(a, b):
    """a<b(date)之间是否还隔着至少一个大商所交易日(不含a、b)。"""
    d = a + _timedelta(days=1)
    while d < b:
        if cn_calendar.dce_is_trading_day_ex(d):
            return True
        d += _timedelta(days=1)
    return False


def _clean_contract_points(points):
    """过滤坏点(日期乱码/v不是数字)，按日期升序，返回[(date, v, contract)]。"""
    out = []
    for p in points or []:
        d = _to_date(p.get("d")) if isinstance(p, dict) else None
        if d is None or not _is_num(p.get("v")):
            continue
        out.append((d, p["v"], (p.get("x") or {}).get("contract")))
    out.sort(key=lambda t: t[0])
    return out


def consecutive_run(points):
    """从最新点往回数：同一方向(升/降)连续了几个交易日、累计变化多少。只在最新点所属的合约内算；遇到打平、方向反转、合约变了、缺了交易日就停。
    返回{direction:'up'|'down'|None, days, total, since(连续区间的起点日期), contract(最新点的合约)}；最新一天打平/只有1个点=direction None、days 0。"""
    pts = _clean_contract_points(points)
    empty = {"direction": None, "days": 0, "total": 0, "since": None, "contract": None}
    if not pts:
        return empty
    out = dict(empty, contract=pts[-1][2])
    if len(pts) < 2:
        return out
    direction, days, i = None, 0, len(pts) - 1
    while i > 0:
        d1, v1, c1 = pts[i]
        d0, v0, c0 = pts[i - 1]
        if c0 != c1 or _trading_day_between(d0, d1):
            break
        diff = v1 - v0
        step = "up" if diff > 0 else "down" if diff < 0 else None
        if step is None or (direction is not None and step != direction):
            break
        direction = step
        days += 1
        i -= 1
    if days == 0:
        return out
    start_idx = len(pts) - 1 - days
    return {"direction": direction, "days": days, "total": pts[-1][1] - pts[start_idx][1], "since": pts[start_idx + 1][0].isoformat(), "contract": pts[-1][2]}


def change_over(points, n):
    """较n个交易日前(往前数第n个点)的变化。要求这n+1个点都在同一个合约内、相邻点之间没有缺交易日；否则返回None(不给跨合约/跨缺口的假变化)。"""
    pts = _clean_contract_points(points)
    if len(pts) < n + 1:
        return None
    win = pts[-(n + 1):]
    if len({c for _, _, c in win}) != 1:
        return None
    for (d0, _, _), (d1, _, _) in zip(win, win[1:]):
        if _trading_day_between(d0, d1):
            return None
    return {"change": win[-1][1] - win[0][1], "from": win[0][0].isoformat(), "to": win[-1][0].isoformat(), "contract": win[-1][2], "n": n}


# 龙虎榜席位 → 序列key(只在marketCapital里有净持仓时才记；未进榜=None=不记点，记0会让"连续N日"误以为降到了0)
CAPITAL_MEMBER_SERIES = {"高盛期货": "capital_gs_net", "摩根大通": "capital_jpm_net", "瑞银期货": "capital_ubs_net", "中粮期货": "capital_zl_net", "国投期货": "capital_gt_net"}


def _prev_trading_day(day):
    d = _to_date(day)
    if d is None:
        return None
    d -= _timedelta(days=1)
    for _ in range(15):
        if cn_calendar.dce_is_trading_day_ex(d):
            return d.isoformat()
        d -= _timedelta(days=1)
    return None


def _record_capital(result, base_dir, touched, note):
    """把marketCapital里各席位的净持仓记成日频序列(带合约代码)，再把连续N日/近N日变化挂回members[席位].history，页面直接展示。
    v101.18：①线上只有当天快照时，用源数据给的"当日变化"推算出缺的前一个交易日(前一日净持仓=今日净持仓-当日变化；点上标x.derived=1，已有的点绝不覆盖)——
    国庆后只有10-09一个点、却已知当日-8,421手，推算后立刻有10-08和10-09两个点，不用干等；②再算外资趋势trend和合成结论verdict(capital_trend.py)。"""
    mc = result.get("marketCapital")
    if not (isinstance(mc, dict) and mc.get("available") and mc.get("date") and isinstance(mc.get("mainContract"), dict) and mc["mainContract"].get("symbol")):
        return
    members = mc.get("members")
    if not isinstance(members, dict):
        return
    contract, day = mc["mainContract"]["symbol"], str(mc["date"])[:10]
    prev_day = _prev_trading_day(day)
    series_points = {}
    for name, key in CAPITAL_MEMBER_SERIES.items():
        m = members.get(name)
        if not isinstance(m, dict) or not _is_num(m.get("net")):
            continue
        try:
            if prev_day and _is_num(m.get("change")):
                have = {p.get("d") for p in load_series(key, base_dir)["points"]}
                if prev_day not in have:
                    _, ch0 = record_points(key, [{"d": prev_day, "v": m["net"] - m["change"], "x": {"contract": contract, "derived": 1}}], base_dir)
                    if ch0:
                        touched.append(key)
            x = {"contract": contract}
            if _is_num(m.get("change")):
                x["change"] = m["change"]
            series, changed = record_points(key, [{"d": day, "v": m["net"], "x": x}], base_dir)
            if changed:
                touched.append(key)
            pts_all = series["points"]
            series_points[name] = pts_all
            m["history"] = {"n": len(pts_all), "since": pts_all[0]["d"] if pts_all else None, "run": consecutive_run(pts_all),
                            "change5": change_over(pts_all, 5), "change20": change_over(pts_all, 20)}
        except Exception as e:  # noqa: BLE001 - 历史是锦上添花
            note(key, e)
    try:
        import capital_trend
        capital_trend.attach(mc, series_points)
    except Exception as e:  # noqa: BLE001
        note("capital_trend", e)


# ★滚动窗口分位(v98，油厂开机率用)：当前值在"最近window_days天"参照样本里的位置。
#   为什么不用"往年同月"：开机率快讯只保留到2024-12，只有1个往年可比，而且2025年3~4月关税战的真实低谷会直接污染同月参照；
#   为什么不用"全部历史"：同一个理由——水平会随行情漂移(2025年中位61.8、2026年62.2，比绝对阈值"60"高)，滚动窗口自适应水平。
#   等攒够2个往年再切到往年同月(见TODO.md)。
TRAILING_SERIES = {"crush_rate": {"window_days": 365, "min_n": 120}}


def _quantile_table(vals_sorted):
    """21个分位点(0%,5%,...,100%)，线性插值。页面靠它对任意值(含用户手填的)算位置，不用把全部历史传过去。"""
    n = len(vals_sorted)
    out = []
    for k in range(21):
        pos = (n - 1) * k / 20
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        out.append(round(vals_sorted[lo] + (vals_sorted[hi] - vals_sorted[lo]) * (pos - lo), 2))
    return out


def summarize_trailing(points, value, as_of, window_days=365, min_n=120):
    """当前值value(日期as_of)在最近window_days天里的位置。参照样本=[as_of-window_days, as_of)内的点——不含as_of当天
    (当天的点就是当前值自己，不能拿自己跟自己比)。enough=样本≥min_n才能用于计分(不足时仍给统计，让页面能说明"历史积累中")。"""
    end = _to_date(as_of)
    out = {"n": 0, "windowDays": window_days, "minN": min_n, "asOf": as_of, "since": None, "median": None, "percentile": None, "quantiles": None, "enough": False}
    if end is None:
        return out
    start = end - _timedelta(days=window_days)
    refs = []
    for p in points:
        d = _to_date(p.get("d"))
        if d is not None and start <= d < end and _is_num(p.get("v")):
            refs.append((d, p["v"]))
    refs.sort()
    vals = [v for _, v in refs]
    out["n"] = len(vals)
    if not vals:
        return out
    sv = sorted(vals)
    out["since"] = refs[0][0].isoformat()
    out["median"] = round(statistics.median(sv), 2)
    out["quantiles"] = _quantile_table(sv)
    out["percentile"] = percentile_rank(value, vals) if _is_num(value) else None
    out["enough"] = len(vals) >= min_n
    return out


# ★往年同月分位(v99，油厂开机率的第一档)：当前值在"同一个日历月、不同日历年"的读数里的位置。
#   v98先用了滚动365天(因为当时只有1个往年)；v99按你的决定改成往年同月，并保留保护：同月参照≥min_n才计分，否则自动退到滚动分位，再退到固定阈值。
#   季节性是真的(5~9月两年同月中位数几乎一样：60/59、66/65、66/65、64/66、67/62)。
#   ★关税战(2025-03-01~04-30)：大豆到港受阻，油厂真实停机到25~40%(同月中位数2025年40/35，2026年53/47)——是真实数据，但不代表往年同月的常态；
#   不排除的话，明年3~4月的正常读数(50~55%)会被拿去跟这些低谷比，显得"偏高"。所以只在往年同月参照里排除(不删数据，滚动分位的参照里仍有它)。
#   区间是判断，不是精确值：采样里3月前几天和4月底已经回升；核实/改区间只需改这个常量。
KNOWN_ABNORMAL_PERIODS = {
    "crush_rate": [("2025-03-01", "2025-04-30", "2025年3~4月中美关税战：大豆到港受阻，油厂真实停机(25~40%)，不代表往年同月的常态")],
}
SAME_MONTH_SERIES = {"crush_rate": {"min_n": 20}}      # 与榨利/月差的"同月样本≥20"一致


def summarize_same_month(points, value, as_of, min_n=20, exclude_key=None):
    """当前值value(日期as_of)在往年同月(同日历月、不同日历年)的读数里的位置。参照里排除KNOWN_ABNORMAL_PERIODS[exclude_key]里的区间。
    返回month、n、years(参照来自哪几年)、since、median、percentile、21个分位点表、enough(n≥min_n才能计分)、minN。"""
    out = {"month": None, "n": 0, "years": [], "since": None, "median": None, "percentile": None, "quantiles": None, "enough": False, "minN": min_n}
    cur = _to_date(as_of)
    if cur is None:
        return out
    out["month"] = cur.month
    skip = KNOWN_ABNORMAL_PERIODS.get(exclude_key) or []
    refs = []
    for p in points:
        d = _to_date(p.get("d"))
        if d is None or not _is_num(p.get("v")) or d.month != cur.month or d.year == cur.year:
            continue
        if any(a <= str(p["d"])[:10] <= b for a, b, _ in skip):
            continue
        refs.append((d, p["v"]))
    if not refs:
        return out
    refs.sort()
    vals = sorted(v for _, v in refs)
    out["n"] = len(vals)
    out["years"] = sorted({d.year for d, _ in refs})
    out["since"] = refs[0][0].isoformat()
    out["median"] = round(statistics.median(vals), 2)
    out["quantiles"] = _quantile_table(vals)
    out["percentile"] = percentile_rank(value, vals) if _is_num(value) else None
    out["enough"] = len(vals) >= min_n
    return out


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


SAME_CONTRACT_MIN_N = 20     # 当前主力合约自己的历史至少这么多个交易日才给分位(约一个月)

# ★换月断层的统一处理(用户2026-10-08规定)：凡是受"主力/近月合约换月"影响的序列，分位只在**当前合约自己的历史**里算，不跨合约混算。
#   这张表登记每个这类序列及其处理方式；以后新增含合约信息的序列，必须来这里登记，并检查它的分位口径。
#   sameContract=序列里每个点带合约标记(x.dom)，算分位时只取同一合约的点；perContractFile=每个合约窗口单独一个文件，天然不混；retired=已停用。
CONTRACT_ROLL_SERIES = {
    "spot_basis": {"method": "sameContract", "note": "现货-主力结算价；主力换月时基差一天内可跳几百元（5月/1月合约天然大、9月合约接近0）"},
    "crush_margin_sep": {"method": "perContractFile", "note": "盘面榨利，按合约窗口分文件"},
    "crush_margin_may": {"method": "perContractFile", "note": "盘面榨利，按合约窗口分文件"},
    "crush_margin_jan": {"method": "perContractFile", "note": "盘面榨利，按合约窗口分文件"},
    "term_spread_sep": {"method": "perContractFile", "note": "月差，按合约对分文件"},
    "term_spread_may": {"method": "perContractFile", "note": "月差，按合约对分文件"},
    "term_spread_jan": {"method": "perContractFile", "note": "月差，按合约对分文件"},
    "basis": {"method": "retired", "note": "Mysteel沿海基差(v101.7起停用)，里面有表内合约月份x.contract，换月处有断层"},
}


def summarize_same_contract(points, value, cur_d, dom, min_n=SAME_CONTRACT_MIN_N):
    """value 在"同一主力合约"自己历史里的位置。只取 x.dom 与 dom 相同(大小写不敏感)的点，剔除 cur_d 当天自己；
    没有合约标记的点不算任何合约的样本。样本不足 min_n 时 percentile=None 并写明原因——不退回混合所有合约的分位。"""
    code = (dom or "").strip().lower()
    out = {"contract": code or None, "n": 0, "minN": min_n, "percentile": None, "median": None, "min": None, "max": None, "since": None, "why": ""}
    if not code:
        out["why"] = "没有主力合约代码，无法按合约分组"
        return out
    refs = [p for p in points
            if p.get("d") != cur_d and _is_num(p.get("v"))
            and str(((p.get("x") or {}).get("dom")) or "").strip().lower() == code]
    refs.sort(key=lambda p: str(p["d"]))
    vals = [p["v"] for p in refs]
    out["n"] = len(vals)
    if vals:
        out["min"], out["max"], out["median"] = round(min(vals), 2), round(max(vals), 2), round(statistics.median(vals), 2)
        out["since"] = refs[0]["d"]
    if len(vals) >= min_n:
        out["percentile"] = percentile_rank(value, vals)
    else:
        out["why"] = f"{code}作为主力合约的历史只有{len(vals)}个交易日（需要≥{min_n}个），换月后约一个月内这一项暂不计分"
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
        ("ndrcPoultryProfit", "poultry_ndrc", lambda r: (_day(r.get("date")), r.get("value"), None, {"ratio": r.get("ratio"), "bal": r.get("balance"), "wk": r.get("weekLabel"), "cp": r.get("chickenPrice"), "fp": r.get("feedPrice")})),
        ("spotBasis", "spot_basis", lambda r: (_day(r.get("date")), r.get("value"), None, {"sp": r.get("spot"), "dom": r.get("domSymbol"), "dp": r.get("domPrice"), "sb": r.get("siteBasis")})),
        ("mysteelBasis", "basis", lambda r: (_day(r.get("date")), r.get("value"), None, {"city": r.get("city"), "src": r.get("src"), "contract": r.get("contract")})),
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

    # 猪粮比：数据源每次返回生猪价和玉米价的整段历史，抓取时带出 seriesPoints。★必须在下面逐个指标算摘要之前记进去，摘要才基于整段历史；
    #   记完(或不可用时)一律从 latest.json 里去掉，不留明细。
    try:
        res = result.get("hogRatio")
        if isinstance(res, dict):
            raw = res.pop("seriesPoints", None)
            if res.get("available") and isinstance(raw, list):
                pts = [{"d": p["d"], "v": p["v"]} for p in raw if isinstance(p, dict) and isinstance(p.get("d"), str) and p.get("d") and _is_num(p.get("v"))]
                if pts:
                    _s, changed = record_points("hog_ratio", pts, base_dir)
                    if changed:
                        touched.append("hog_ratio")
    except Exception as e:  # noqa: BLE001
        note("hogRatio", e)

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
            res["history"] = summarize(usable_points(series["key"], series["points"]), v, d, series["freq"])
            if key in TRAILING_SERIES:       # ★开机率：再挂一份滚动窗口分位(含分位点表)，页面的评分规则读它(第二档)
                res["history"]["trailing"] = summarize_trailing(usable_points(series["key"], series["points"]), v, d, **TRAILING_SERIES[key])
            if key == "spot_basis":          # ★现货基差：再挂一份"同一主力合约内部"的分位，页面的评分规则读它(整体摘要只展示)
                res["history"]["sameContract"] = summarize_same_contract(usable_points(series["key"], series["points"]), v, d, res.get("domSymbol"))
            if key in SAME_MONTH_SERIES:     # ★开机率：往年同月分位(含分位点表)，页面的评分规则优先读它(第一档)；参照里排除关税战区间
                res["history"]["sameMonth"] = summarize_same_month(usable_points(series["key"], series["points"]), v, d, exclude_key=key, **SAME_MONTH_SERIES[key])
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
            res["history"] = summarize(usable_points("meal_stock", series["points"]), res["value"], _day(res.get("date")), series["freq"])
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
            res["history"] = summarize(usable_points("feed_days", series["points"]), res["value"], _day(res.get("date")), series["freq"])
    except Exception as e:  # noqa: BLE001
        note("mysteelFeedDays", e)

    # ★资金面(v101)：龙虎榜主力合约的席位净持仓(日频，带合约代码)。放在CFTC之前不重要，两者互相独立。
    try:
        _record_capital(result, base_dir, touched, note)
    except Exception as e:  # noqa: BLE001
        note("marketCapital", e)

    # ★CFTC管理基金净多(周频)：抓取一次就拉了156周明细(res["history"])，第一次运行就记下整段，不用等；之后每周补新的一周。
    #   没有history明细(旧版结果)时至少记最新一周。
    try:
        res = result.get("cftcManagedMoney")
        if isinstance(res, dict) and res.get("available"):
            pts = [p for p in (res.get("history") or []) if isinstance(p, dict) and p.get("d") and _is_num(p.get("v"))]
            if not pts and res.get("reportDate") and _is_num(res.get("netPosition")):
                pts = [{"d": _day(res["reportDate"]), "v": res["netPosition"]}]
            if pts:
                series, changed = record_points("cftc_mm_net", pts, base_dir)
                if changed:
                    touched.append("cftc_mm_net")
                res.pop("history", None)      # 156周明细(约12KB)已存进序列文件，不需要留在latest.json里每小时重复写一遍；摘要字段(netPosition/streakWeeks/historyPercentile…)保留
    except Exception as e:  # noqa: BLE001
        note("cftcManagedMoney", e)

    # 盘面压榨毛利：三个合约各存一条序列(逐日追加)；分位只看"往年同月"——毛利的绝对数没有意义(没扣加工费，几乎永远为正)，
    #   只有跟历史同期比才知道"油厂现在的压榨动力强还是弱"。需要往年数据(回填)，没有回填时seasonal为空，前端不据此计分。
    try:
        for k in ("sep", "may", "jan"):
            res = (result.get("crushMargins") or {}).get(k)
            if not (isinstance(res, dict) and res.get("available") and res.get("date") and _is_num(res.get("grossMargin"))):
                continue
            key = "crush_margin_" + k
            # ★只记"这个合约的建议交易窗口内"的点(与回填口径一致)：窗口外(比如9月合约在10月、已到期或刚滚动到下一年合约)的毛利
            #   含到期/移仓扰动，记进来会污染以后"往年同月"的比较。窗口外只展示(用已有历史算分位)，不记录。
            if in_trading_window(_day(res["date"]), k, res.get("mealSymbol")):
                series, changed = record_points(key, [{"d": _day(res["date"]), "v": res["grossMargin"], "x": {"contract": res.get("mealSymbol")}}], base_dir)
                if changed:
                    touched.append(key)
            else:
                series = load_series(key, base_dir)
            res["history"] = summarize(usable_points(series["key"], series["points"]), res["grossMargin"], _day(res["date"]), series["freq"])
    except Exception as e:  # noqa: BLE001
        note("crushMargins", e)

    # 月差/期限结构：跟榨利同一套——三个合约类型各存一条序列，分位只看"往年同月"(粮食的月差有强烈的季节性，比如5-9月差受南美到港节奏影响)。
    try:
        for k in ("sep", "may", "jan"):
            res = (result.get("termSpreads") or {}).get(k)
            if not (isinstance(res, dict) and res.get("available") and res.get("date") and _is_num(res.get("spreadPct"))):
                continue
            key = "term_spread_" + k
            if in_trading_window(_day(res["date"]), k, res.get("nearSymbol")):       # 只记窗口内(同榨利)
                series, changed = record_points(key, [{"d": _day(res["date"]), "v": res["spreadPct"], "x": {"near": res.get("nearSymbol"), "far": res.get("farSymbol"), "spread": res.get("spread")}}], base_dir)
                if changed:
                    touched.append(key)
            else:
                series = load_series(key, base_dir)
            res["history"] = summarize(usable_points(series["key"], series["points"]), res["spreadPct"], _day(res["date"]), series["freq"])
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
            res["history"] = summarize(usable_points("meal_stu", series["points"]), res["value"], res["month"], "monthly",
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
