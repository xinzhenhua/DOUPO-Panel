# -*- coding: utf-8 -*-
"""外资(龙虎榜席位)趋势判断(v101.18)。纯函数、不联网。

为什么要有：v100/v101 的"资金面"只看水平——高盛净多头≥12万手 + CFTC分位≥90 = "外资多头拥挤"，
同一个标签在 高盛还在加仓、持平、已经连续减仓 三种情况下一模一样（2026-10-09 高盛已从15.2万降到13.0万，页面仍写"拥挤"）。
这里补上"方向"：同一合约内的连续增减天数、累计变化、较峰值回落、5日变化，并诚实写出历史检验结论。

口径：
- 只在同一合约内比较(主力合约换月时净持仓不可比)；相邻点之间缺大商所交易日就断开。
- 阈值来自文档经验值：连续2~3日、累计1~2万手(取下限1万手判"撤退中"，单日≥2万手或连3日≥2万手判"加速")。
  历史检验(见 EVIDENCE)只能部分支持"加仓"一侧，不支持"减仓→下跌"，所以标签只描述状态，不写预测。
- 点上有 x.approx(只进了买或卖一边前20，另一边用第20名顶替=净持仓下限估计)的，结论里标"含下限估计"。
"""
from datetime import date as _date

import history_store as hs

RETREAT_TOTAL = -10000          # 连续2日以上累计≤-1万手 = 撤退中(文档：连续2~3日累计减仓1~2万手)
FAST_TOTAL = -20000             # 连续3日以上累计≤-2万手 或 单日≤-2万手 = 加速(文档：单日减仓超2万手→预警)
BUILD_TOTAL = 10000             # 连续2日以上累计≥+1万手 = 加仓中
CHANGE5_THRESHOLD = 10000       # 日内交替时，5个交易日净变化≥1万手(绝对值)也算
MIN_POINTS = 3                  # 同合约连续点数不足3个，不判趋势
MAX_WINDOW = 60                 # 峰值只看最近60个交易日(约3个月)
HOLIDAY_GAP_DAYS = 3            # 相邻两点相隔>3个日历日(普通周末最多3天)=跨过了休市长假

EVIDENCE = [
    "历史检验(龙虎榜文件2020-12~2026-08，9个合约；高盛只有2026年入榜，样本主要是摩根大通)：外资3日净加仓≥1万手后，同合约未来5个交易日平均约+1.2%(约12个独立事件，无条件基准约+0.8%)，方向偏涨但样本小；",
    "外资3日净减仓≥1万手后，未来5个交易日平均约-0.2%(约17个独立事件)，和基准没有明显差别——减仓预示下跌没有证据，所以这里只描述'在撤退'，不写成看空信号；",
    "2020年4月及以前的龙虎榜无法取得，阈值是文档经验值，只检验了方向、没有调优。",
]


def _fmt(n):
    return f"{abs(int(round(n))):,}"


def _sgn(n):
    n = int(round(n))
    return f"{'+' if n > 0 else '-' if n < 0 else ''}{abs(n):,}"


def _clean(points):
    out = []
    for p in points or []:
        if not isinstance(p, dict):
            continue
        d = hs._to_date(p.get("d"))
        if d is None or not hs._is_num(p.get("v")):
            continue
        x = p.get("x") or {}
        out.append((d, p["v"], x.get("contract"), bool(x.get("approx"))))
    out.sort(key=lambda t: t[0])
    return out


def _segment(points):
    """最新合约、且相邻点之间没有缺交易日的那一段(时间升序)，最多MAX_WINDOW个点。"""
    pts = _clean(points)
    if not pts:
        return [], None
    contract = pts[-1][2]
    seg = [pts[-1]]
    for i in range(len(pts) - 2, -1, -1):
        d0, _, c0, _ = pts[i]
        d1 = seg[0][0]
        if c0 != contract or hs._trading_day_between(d0, d1):
            break
        seg.insert(0, pts[i])
        if len(seg) >= MAX_WINDOW:
            break
    return seg, contract


def assess_member(points, high=None):
    """一个席位的趋势。high=该席位的'高位'线(高盛12万手)，None=不分高低位。返回字典，code见下。"""
    seg, contract = _segment(points)
    n = len(seg)
    base = {"n": n, "contract": contract, "high": high}
    if n < MIN_POINTS:
        last = {"d": seg[-1][0].isoformat(), "v": seg[-1][1]} if seg else None
        return dict(base, code="insufficient", last=last)
    vals = [v for _, v, _, _ in seg]
    last_d, last_v = seg[-1][0], seg[-1][1]
    # 连续同方向
    direction, days, i = None, 0, n - 1
    while i > 0:
        diff = vals[i] - vals[i - 1]
        step = "up" if diff > 0 else "down" if diff < 0 else None
        if step is None or (direction is not None and step != direction):
            break
        direction = step
        days += 1
        i -= 1
    start = n - 1 - days
    run = {"direction": direction, "days": days, "total": (vals[-1] - vals[start]) if days else 0, "since": seg[start + 1][0].isoformat() if days else None}
    day_change = vals[-1] - vals[-2]
    change5 = None
    if n >= 6:
        change5 = {"change": vals[-1] - vals[-6], "from": seg[-6][0].isoformat(), "to": last_d.isoformat()}
    pk_i = max(range(n), key=lambda k: (vals[k], -k))     # 最大值；并列取最早
    peak = {"v": vals[pk_i], "d": seg[pk_i][0].isoformat()}
    dd = peak["v"] - last_v
    dd_pct = round(dd / peak["v"] * 100, 1) if peak["v"] > 0 else None
    window = seg[start:] if days else seg[-2:]
    across = any((b[0] - a[0]).days > HOLIDAY_GAP_DAYS for a, b in zip(window, window[1:]))
    approx = any(p[3] for p in window)
    total = run["total"]
    c5 = change5["change"] if change5 else 0
    if day_change <= FAST_TOTAL or (direction == "down" and days >= 3 and total <= FAST_TOTAL):
        code = "retreat_fast"
    elif (direction == "down" and days >= 2 and total <= RETREAT_TOTAL) or c5 <= -CHANGE5_THRESHOLD:
        code = "retreating"
    elif day_change >= -FAST_TOTAL or (direction == "up" and days >= 2 and total >= BUILD_TOTAL) or c5 >= CHANGE5_THRESHOLD:
        code = "building"
    elif direction == "down" and days >= 2:
        code = "trimming"
    elif direction == "up" and days >= 2:
        code = "adding"
    else:
        code = "flat"
    return dict(base, code=code, last={"d": last_d.isoformat(), "v": last_v}, run=run, dayChange=day_change, change5=change5, peak=peak,
                drawdown=dd, drawdownPct=dd_pct, acrossHoliday=across, approx=approx)


def build_verdict(a, cftc, old_state):
    """把高盛的趋势 + CFTC + 旧的水平状态合成一条结论。返回{code, level, label, lines[], evidence[]}。level:red/yellow/green/gray。"""
    old_state = old_state or {}
    old_level, old_label = old_state.get("level") or "gray", old_state.get("label") or "外资状态：数据不足"
    if a is None:
        return {"code": "no_member", "level": "gray", "short": "外资状态：高盛未进榜，趋势无法判断", "label": "外资状态：高盛未进榜，趋势无法判断", "lines": [], "evidence": []}
    if a["code"] == "insufficient":
        lab = f"{old_label}(趋势暂不可判：同合约连续历史仅{a['n']}个交易日，攒够{MIN_POINTS}日才判断)"
        return {"code": "insufficient", "level": old_level, "short": lab, "label": lab, "lines": [], "evidence": EVIDENCE}
    last, peak, run, high = a["last"]["v"], a["peak"], a["run"], a.get("high")
    from_high = high is not None and peak["v"] >= high
    at_high = high is not None and last >= high
    md = peak["d"][5:]
    days_txt = f"连续{run['days']}个交易日" if run["days"] >= 2 else ""
    code = a["code"]
    if code in ("retreat_fast", "retreating"):
        speed = "加速" if code == "retreat_fast" else "中"
        if from_high:
            short = f"外资高位撤退{speed}"
            vcode, lab = "retreat_from_high", f"外资高位撤退{speed}：高盛净多从峰值{_fmt(peak['v'])}手({md})降到{_fmt(last)}手，较峰值回落{_fmt(a['drawdown'])}手({a['drawdownPct']}%)" + (f"，{days_txt}减仓" if days_txt else "")
        else:
            short = f"外资减仓{speed}"
            vcode, lab = "retreat", f"外资减仓{'加速' if code == 'retreat_fast' else '中'}：高盛净多{_fmt(last)}手" + (f"，{days_txt}减仓累计{_fmt(run['total'])}手" if days_txt else f"，近5个交易日{_sgn(a['change5']['change'])}手" if a["change5"] else "")
        level = "yellow"
    elif code == "building":
        if at_high:
            short = "外资高位继续加仓(拥挤加剧)"
            vcode, level, lab = "build_high", "red", f"外资高位继续加仓(拥挤在加剧)：高盛净多{_fmt(last)}手" + (f"，{days_txt}加仓累计{_sgn(run['total'])}手" if days_txt else "")
        else:
            short = "外资进场/加仓中"
            vcode, level, lab = "build", "yellow", f"外资进场/加仓中：高盛净多{_fmt(last)}手" + (f"，{days_txt}加仓累计{_sgn(run['total'])}手" if days_txt else "")
    else:
        # trimming / adding / flat：没有明确方向，沿用水平状态，补一句近期动向
        tail = {"flat": "近5日基本持平", "trimming": f"小幅减仓{_sgn(run['total'])}手，未到撤退线", "adding": f"小幅加仓{_sgn(run['total'])}手，未到加仓线"}[code]
        c = old_state.get("code")
        vcode = "crowded_flat" if c == "crowded" else "elevated_flat" if c == "elevated" else "neutral_flat" if c == "neutral" else "unknown_flat"
        level, lab = old_level, f"{old_label}({tail})"
        short = lab
    lines = []
    ap = ""
    if code in ("retreat_fast", "retreating", "building"):
        # 标题(label)里已经有 现值/峰值/回落/连续天数，这里只补标题里没有的5日变化，避免同一串数字写两遍
        if a["change5"]:
            lines.append(f"近5个交易日高盛净多{_sgn(a['change5']['change'])}手。")
    else:
        lines.append(f"高盛净多{_fmt(last)}手；{md}峰值{_fmt(peak['v'])}手，回落{_fmt(a['drawdown'])}手({a['drawdownPct']}%)" + (f"；{days_txt}{'减仓' if run['direction']=='down' else '加仓'}累计{_sgn(run['total'])}手" if days_txt else "") + (f"；近5个交易日{_sgn(a['change5']['change'])}手" if a["change5"] else "") + ap + "。")
    if a["approx"]:
        lines.append("注：这段里的部分点是下限估计(高盛只进了买方前20，卖方用第20名持仓顶替，该名次约2万多手)，绝对数值可能有几千到2万手的出入，所以看方向和量级，不要看个位数。")
    if high is not None:
        gap = last - high
        lines.append(f"距文档的{high // 10000}万手警戒线" + (f"还差{_fmt(gap)}手(文档：从16万级降到12万以下，资金市可能接近尾声)" if gap > 0 else f"：已低于警戒线{_fmt(gap)}手") + "。")
    if a["acrossHoliday"]:
        lines.append("这段减仓跨过国庆长假(节前减风险、节后复盘的成分较大)，文档提示长假前后的变动要打折看，且假期后只有很少几个交易日，是否延续要再看几天。")
    if cftc:
        pct, wk, st, sd, rd = cftc.get("percentile"), cftc.get("weeksUsed"), cftc.get("streakWeeks"), cftc.get("streakDirection"), cftc.get("reportDate")
        seg = []
        if pct is not None:
            seg.append(f"CFTC管理基金净多处近{wk or '—'}周的{round(pct)}%分位")
        if st:
            seg.append(f"连续{st}周{'增加' if sd == 'up' else '减少'}")
        if seg:
            lines.append("，".join(seg) + f"(周度数据，截至{rd or '—'}，未反映之后的交易日；CBOT美国市场，与国内高盛是否同向没有验证过)。")
    return {"code": vcode, "level": level, "short": short, "label": lab, "lines": lines, "evidence": EVIDENCE}


def attach(mc, series_points):
    """给marketCapital加 trend(高盛/摩根大通/瑞银各自的趋势)和 verdict(合成结论)。series_points={席位名:该席位的序列points}。出错不影响其它。"""
    if not (isinstance(mc, dict) and mc.get("available")):
        return mc
    trend = {}
    for name, hi in (("高盛期货", 120000), ("摩根大通", None), ("瑞银期货", None)):
        pts = series_points.get(name)
        if pts:
            trend[name] = assess_member(pts, high=hi)
    mc["trend"] = trend
    gs = trend.get("高盛期货")
    mc["verdict"] = build_verdict(gs, mc.get("cftc"), mc.get("state"))
    # 其他外资席位一句话：回答"外资整体是再来还是走"，而不只看高盛。摩根大通净持仓常在零附近来回，方向意义弱，只描述。
    parts = []
    word = {"retreat_fast": "在减仓(加速)", "retreating": "在减仓", "building": "在加仓", "trimming": "小幅减仓", "adding": "小幅加仓", "flat": "近5日基本持平"}
    for name in ("摩根大通", "瑞银期货"):
        t = trend.get(name)
        if not t or t["code"] not in word:
            continue
        net = t["last"]["v"]
        seg = word[t["code"]]
        if t["run"]["days"] >= 2 and t["code"] != "flat":
            seg += f"(连续{t['run']['days']}日累计{_sgn(t['run']['total'])}手)"
        parts.append(f"{name}{seg}，净{'多' if net >= 0 else '空'}{_fmt(net)}手")
    if parts and mc["verdict"].get("lines") is not None and gs and gs["code"] != "insufficient":
        mc["verdict"]["lines"].append("其他外资席位：" + "；".join(parts) + "(摩根大通净持仓常在零附近来回，方向意义弱)。")
    return mc
