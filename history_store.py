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

HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "history")
MIN_POINTS = 12            # 算"总体历史分位"至少需要的样本数，不够就只显示"历史积累中"，不给一个没有统计意义的百分位
MIN_SEASONAL_POINTS = 4    # 算"同月历史分位"至少需要的同月样本数(不同年份)

SERIES_META = {
    # ---- 可回填 ----
    "us_stocks_to_use": {"name": "美豆库存消费比(按市场年度)", "unit": "%", "freq": "yearly"},
    "esr_net_sales": {"name": "美豆出口净销售(周度，全部国家)", "unit": "吨", "freq": "weekly"},
    "meal_stu": {"name": "国内豆粕库存消费比(月度)", "unit": "%", "freq": "monthly"},
    "meal_stock": {"name": "国内豆粕商业库存(周度)", "unit": "万吨", "freq": "weekly"},
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


def summarize(points, value, cur_d, freq=None):
    """当前值value(日期cur_d)在历史里的位置。参考样本里剔除cur_d自己(不能拿自己跟自己比)。
    seasonal：同一个日历月、不同年份的样本(周度/日度/月度序列才有)；同年份的不算，避免跟当前值高度相关的近邻点混进来。
    样本不够(<MIN_POINTS)时percentile=None，界面显示"历史积累中"。"""
    refs = [p for p in points if p["d"] != cur_d and _is_num(p.get("v"))]
    vals = [p["v"] for p in refs]
    n = len(vals)
    out = {"n": n, "minPoints": MIN_POINTS, "asOf": cur_d, "since": refs[0]["d"] if refs else None,
           "percentile": None, "min": None, "max": None, "median": None, "seasonal": None}
    if n:
        out["min"], out["max"], out["median"] = round(min(vals), 2), round(max(vals), 2), round(statistics.median(vals), 2)
    if n >= MIN_POINTS:
        out["percentile"] = percentile_rank(value, vals)
    cy, cm = _year_month(cur_d)
    if cm is not None and freq not in ("yearly",):
        same = [p["v"] for p in refs if _year_month(p["d"])[1] == cm and _year_month(p["d"])[0] != cy]
        if len(same) >= MIN_SEASONAL_POINTS:
            out["seasonal"] = {"month": cm, "n": len(same), "percentile": percentile_rank(value, same),
                               "median": round(statistics.median(same), 2)}
        elif same:
            out["seasonal"] = {"month": cm, "n": len(same), "percentile": None, "median": None}
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
        ("mysteelMealStock", "meal_stock", lambda r: (_day(r.get("date")), r.get("value"), None, None)),
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

    # 国内库消比：只记"文章明示/由库存÷消费推算"的月度值；"周度库存÷预计消费"是回退推算，不是月度平衡表的数，不进历史
    try:
        res = result.get("mysteelMealStu")
        if isinstance(res, dict) and res.get("available") and res.get("method") in ("stated", "computed") and _is_num(res.get("value")):
            pt = {"d": res["month"], "v": res["value"], "pub": _day(res.get("date"))}
            series, changed = record_points("meal_stu", [pt], base_dir)
            if changed:
                touched.append("meal_stu")
            res["history"] = summarize(series["points"], res["value"], res["month"], "monthly")
        elif isinstance(res, dict) and res.get("available") and _is_num(res.get("value")):
            series = load_series("meal_stu", base_dir)
            res["history"] = summarize(series["points"], res["value"], res.get("month"), "monthly")
    except Exception as e:  # noqa: BLE001
        note("mysteelMealStu", e)

    # 出口净销售：把最近8周逐周记下来(每周都补齐)，分位用"近4周合计"跟历史同一口径的4周合计比
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
            if _is_num(cur4):
                roll = rolling_sum(series["points"], 4)
                res["history"] = summarize(roll, cur4, _day(res.get("weekEnding")), "weekly")
                res["history"]["basis"] = "近4周净销售合计"
    except Exception as e:  # noqa: BLE001
        note("exportSales", e)

    if errors:
        import sys
        print("[WARN] 历史序列更新时有指标出错(已跳过，不影响其它数据): " + "; ".join(errors), file=sys.stderr)
    return touched
