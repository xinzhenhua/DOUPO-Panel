# -*- coding: utf-8 -*-
"""龙虎榜(大商所会员持仓排名)历史自动回填(v101.21)。开发环境连不上东方财富/新浪，所以网络层全部可注入，测试用假接口。
数据源(按可靠度)：
  em    东方财富 datacenter-web RPT_FUTU_DAILYPOSITION(线上每天抓龙虎榜用的就是它，按 TRADE_DATE 过滤，理论上能取历史日期——这点没验证过，先跑 rank_probe)
  sina  新浪 vFutures_Positions_cjcc.php(akshare.futures_hold_pos_sina，成交量/多单/空单三张表，自带名次/会员/数量/增减)
输出：与手动下载同格式的 txt(M2701_YYYYMMDD.txt)，写到 data/raw/dce_rank_auto/(不混进手动文件目录)，backfill_capital_rank 两个目录都读，同合约同日期手动文件优先。
合约怎么定：用基线 CSV(meal_spot_futures_10y.csv)里当天的 dominant_contract(生意社给的主力合约)，不自己推导——推导错了会静默把错合约的数据存进序列(见 README v101)。
防污染：每一行都核对 SECURITY_CODE==请求的合约 且 TRADE_DATE==请求的日期，对不上整天丢弃；两边(多/空)行数必须一致才写；写不出就记原因，不写空文件。"""
import os, re, time, datetime
import urllib.parse

POS_EM = {
    "long":  {"sortField": "LPRANK", "rank": "LP_RANK", "value": "LONG_POSITION", "chg": "LP_CHANGE"},
    "short": {"sortField": "SPRANK", "rank": "SP_RANK", "value": "SHORT_POSITION", "chg": "SP_CHANGE"},
}


def _n(v):
    return f"{int(float(v)):,} "


def build_txt(day, buy, sell, vol=None):
    """buy/sell: [{rank,name,value,change}] 各最多20行，已按名次升序；vol 缺省(东方财富没有成交量榜)→成交量三列写占位。
    输出与大商所下载文件同格式，dce_rank_files.parse_rank_text 能直接读。行数取两边较短者(榜单不足20时 member_net 会按'不足20行不估计'处理)。"""
    k = min(len(buy), len(sell))
    if k == 0:
        return None
    lines = ["大连商品交易所_日成交持仓排名_" + day.replace("-", ""),
             "名次\t会员简称\t成交量\t增减\t名次\t会员简称\t持买单量\t增减\t名次\t会员简称\t持卖单量\t增减"]
    for i in range(k):
        b, s = buy[i], sell[i]
        v = vol[i] if vol and i < len(vol) else None
        v_name, v_val, v_chg = (v["name"], _n(v["value"]), _n(v["change"])) if v else ("-", "0 ", "0 ")
        lines.append("\t".join([str(i + 1), v_name, v_val, v_chg,
                                str(i + 1), b["name"], _n(b["value"]), _n(b["change"]),
                                str(i + 1), s["name"], _n(s["value"]), _n(s["change"])]))
    return "\r\n".join(lines) + "\r\n"


# ---------- 东方财富 ----------
def _em_url(contract, day, cat):
    import fetch_data
    return fetch_data._build_eastmoney_position_url(contract.upper(), day, POS_EM[cat]["sortField"])


def _em_table(fetch, contract, day, cat):
    """返回 (rows, reason)。rows=[{rank,name,value,change}] 按名次升序，最多20行；reason 仅在拿不到时给。"""
    cfg = POS_EM[cat]
    data, dbg = fetch(_em_url(contract, day, cat))
    if data is None:
        return None, "请求失败：" + str((dbg or {}).get("error", "未知"))[:120]
    if not data.get("success"):
        return None, f"success=false：{data.get('message')}"
    raw = (data.get("result") or {}).get("data") or []
    if not raw:
        return None, "该日期/合约没有返回数据"
    rows = []
    for r in raw:
        code, td = r.get("SECURITY_CODE"), str(r.get("TRADE_DATE") or "")[:10]
        if code is not None and str(code).upper() != contract.upper():
            return None, f"返回的合约是{code}，不是请求的{contract.upper()}"
        if td and td != day:
            return None, f"返回的日期是{td}，不是请求的{day}"
        rk = r.get(cfg["rank"])
        if rk is None or rk == 9999 or r.get(cfg["value"]) is None:
            continue
        name = r.get("ORG_NAME_ABBR_NEW") or r.get("MEMBER_NAME_ABBR") or ""
        rows.append({"rank": int(rk), "name": name, "value": r[cfg["value"]], "change": r.get(cfg["chg"]) or 0})
    rows.sort(key=lambda x: x["rank"])
    return rows[:20], (None if rows else "没有进入前20的有效行")


def em_day(fetch, contract, day):
    """返回 (txt, reason)。"""
    buy, why = _em_table(fetch, contract, day, "long")
    if buy is None:
        return None, "多头榜：" + why
    sell, why = _em_table(fetch, contract, day, "short")
    if sell is None:
        return None, "空头榜：" + why
    if len(buy) != len(sell):
        return None, f"多头榜{len(buy)}行、空头榜{len(sell)}行不一致，不写(防止错位)"
    return build_txt(day, buy, sell), None


# ---------- 新浪 ----------
def _sina_rows(df, name_i=1, val_i=2, chg_i=3):
    out = []
    if df is None:
        return out
    for rec in df.itertuples(index=False):
        try:
            rk = int(float(rec[0]))
            out.append({"rank": rk, "name": str(rec[name_i]).strip(), "value": float(rec[val_i]), "change": float(rec[chg_i])})
        except (ValueError, TypeError, IndexError):
            continue
    out.sort(key=lambda x: x["rank"])
    return out[:20]


def sina_day(ak, contract, day):
    ds = day.replace("-", "")
    c = contract.upper()
    try:
        vol = _sina_rows(ak.futures_hold_pos_sina(symbol="成交量", contract=c, date=ds))
        buy = _sina_rows(ak.futures_hold_pos_sina(symbol="多单持仓", contract=c, date=ds))
        sell = _sina_rows(ak.futures_hold_pos_sina(symbol="空单持仓", contract=c, date=ds))
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"[:160]
    if not buy or not sell:
        return None, "新浪返回的多/空榜为空(该日期/合约无数据)"
    if len(buy) != len(sell):
        return None, f"多头榜{len(buy)}行、空头榜{len(sell)}行不一致，不写"
    return build_txt(day, buy, sell, vol if len(vol) >= len(buy) else None), None


# ---------- 计划与回填 ----------
def plan(baseline_rows, start, end, is_trading):
    """baseline_rows: spot_history.load_rows 的结果 {date: {dominant_contract,...}}。返回 [(day, 'M2701')] 从新到旧。
    只取 start<=day<=end 且是交易日且基线有主力合约的日子(基线没有的日子不猜合约)。"""
    out = []
    for d in sorted(baseline_rows, reverse=True):
        if not (start <= d <= end):
            continue
        k = (baseline_rows[d].get("dominant_contract") or "").strip().upper()
        if not re.fullmatch(r"M\d{4}", k):
            continue
        if not is_trading(datetime.date.fromisoformat(d)):
            continue
        out.append((d, k))
    return out


def backfill(out_dir, todo, day_fn, budget_s=2400, pause=0.5, max_consecutive_fail=12, clock=time.time, sleep=time.sleep):
    """todo=[(day,contract)] 从新到旧；已有文件跳过；连续失败太多判断被限流/源头没有历史并停手。
    '没有数据'(reason 含 没有返回/为空)和'请求失败'分开计：前者是该日期真没有(假日/太早)，后者才算限流征兆。"""
    os.makedirs(out_dir, exist_ok=True)
    rep = {"ok": True, "written": 0, "skippedExisting": 0, "noData": 0, "failed": 0, "remaining": 0, "stoppedByBudget": False,
           "stoppedByFailures": False, "firstError": None, "firstDay": None, "lastDay": None, "noDataSamples": []}
    t0, consec = clock(), 0
    for i, (day, c) in enumerate(todo):
        path = os.path.join(out_dir, f"{c}_{day.replace('-', '')}.txt")
        if os.path.exists(path):
            rep["skippedExisting"] += 1
            continue
        if clock() - t0 > budget_s:
            rep["stoppedByBudget"] = True
            rep["remaining"] = sum(1 for d2, c2 in todo[i:] if not os.path.exists(os.path.join(out_dir, f"{c2}_{d2.replace('-', '')}.txt")))
            break
        txt, why = day_fn(c, day)
        if txt:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(txt)
            rep["written"] += 1
            rep["firstDay"] = day if rep["firstDay"] is None or day < rep["firstDay"] else rep["firstDay"]
            rep["lastDay"] = day if rep["lastDay"] is None or day > rep["lastDay"] else rep["lastDay"]
            consec = 0
        elif why and ("请求失败" in why or "Error" in why or "Exception" in why):
            rep["failed"] += 1
            consec += 1
            rep["firstError"] = rep["firstError"] or f"{c} {day}: {why}"
            if consec >= max_consecutive_fail:
                rep["stoppedByFailures"] = True
                rep["remaining"] = sum(1 for d2, c2 in todo[i + 1:] if not os.path.exists(os.path.join(out_dir, f"{c2}_{d2.replace('-', '')}.txt")))
                break
        else:
            rep["noData"] += 1
            consec = 0
            if len(rep["noDataSamples"]) < 8:
                rep["noDataSamples"].append(f"{c} {day}: {why}")
        sleep(pause)
    return rep


def probe(day_fns, samples):
    """每个来源在若干(日期,合约)样本上各试一次，报告有没有数据、第一行会员；不写文件。day_fns={'em':fn,'sina':fn}。"""
    out = {}
    for name, fn in day_fns.items():
        res = []
        for day, c in samples:
            txt, why = fn(c, day)
            first = None
            if txt:
                lines = txt.strip().split("\r\n")
                first = {"rows": len(lines) - 2, "top": lines[2].split("\t")[5:7] if len(lines) > 2 else None}
            res.append({"day": day, "contract": c, "ok": bool(txt), "why": why, **({"info": first} if first else {})})
        out[name] = {"okCount": sum(1 for r in res if r["ok"]), "total": len(res), "samples": res}
    return out


def pick_samples(baseline_rows, years=(2020, 2021, 2022, 2023, 2024, 2025, 2026)):
    """每年挑一个 7 月第一个有基线主力合约的日子，另加最新一天——覆盖'东方财富保留多久'这个未知量。"""
    out = []
    for y in years:
        for d in sorted(baseline_rows):
            if d.startswith(f"{y}-07") and re.fullmatch(r"M\d{4}", (baseline_rows[d].get("dominant_contract") or "").upper()):
                out.append((d, baseline_rows[d]["dominant_contract"].upper()))
                break
    if baseline_rows:
        d = max(baseline_rows)
        k = (baseline_rows[d].get("dominant_contract") or "").upper()
        if re.fullmatch(r"M\d{4}", k) and (d, k) not in out:
            out.append((d, k))
    return out
