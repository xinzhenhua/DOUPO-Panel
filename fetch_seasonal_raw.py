# -*- coding: utf-8 -*-
"""一次性抓取季节性分析要用的原始数据(v101.14)。在 GitHub Actions 里手动运行(开发环境连不上新浪/Yahoo/大商所，所以只能用假接口测试)。
用法：python3 fetch_seasonal_raw.py --only main,contracts,cbot,fx [--out data/raw/seasonal]
      python3 fetch_seasonal_raw.py --only dce_rank --rank-list "2023-06:m2309,2023-07:m2309" --rank-out data/raw/dce_rank_hist
项目：
  main       新浪 M0(豆粕主连)10年日K，含持仓量 → <out>/M0_daily.csv
  contracts  各具体合约(M1701…M2709 的 1/3/4/5/6/7/8/9/11/12月)日K → <out>/contracts/M{yymm}.csv；已有的不重抓，有时间预算，可重复运行接着补
  cbot       CBOT 豆粕(ZM)、大豆(ZS)10年日收盘 → <out>/cbot_ZM.csv、cbot_ZS.csv；先 Yahoo，失败换 akshare 备选代码；报告里列出 akshare 的海外品种代码
  fx         美元兑人民币(USD/CNY)10年 → <out>/usdcny.csv；先 Yahoo(CNY=X)，失败换 akshare
  probe      探测生意社分地区(江苏)报价接口 dp.100ppi.com 是否真的存在、返回什么(把状态/表头/前几行写进报告；不写数据文件)
  dce_rank   大商所"日成交持仓排名"：按'月份:合约'清单，每个工作日请求一次(akshare 实际调的就是大商所下载页)，
             转成与手动下载同格式的 txt → 单独目录 data/raw/dce_rank_hist/(★不写进 data/raw/dce_rank/，免得干扰 v101.13 的龙虎榜回填)；已有文件跳过
每一项单独 try/except，失败只在 <out>/_fetch_report.json 里写原因，不影响其它项。
★Yahoo 的 ZM=F/ZS=F 是连续合约，换月处同样有缺口(与豆粕主连同理)，用它算涨跌幅时需要像 seasonal_stats 那样处理。"""
import argparse, csv, datetime, json, os, re, sys, time

JOBS = ["main", "contracts", "cbot", "fx", "dce_rank", "probe"]
CONTRACT_MONTHS = (1, 3, 4, 5, 6, 7, 8, 9, 11, 12)
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=10y"
CBOT_YAHOO = {"ZM": "ZM=F", "ZS": "ZS=F"}
CBOT_AK = {"ZM": ["ZMD", "SM"], "ZS": ["ZSD", "S"]}   # 新浪海外期货代码的候选，没法在开发环境验证 → 依次试，并把可用代码列进报告


# ---------- 小工具 ----------
def _records(df):
    if df is None:
        return []
    return list(df.to_dict("records"))


def _write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _summ(rows, first_i=0):
    ds = sorted(r[first_i] for r in rows)
    return {"rows": len(rows), "first": ds[0] if ds else None, "last": ds[-1] if ds else None}


def parse_rank_list(s):
    out = []
    for part in re.split(r"[,;，；\s]+", (s or "").strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d{4})-(\d{2}):([mM]\d{4})", part)
        if not m or not 1 <= int(m.group(2)) <= 12:
            raise ValueError(f"龙虎榜清单格式应为 2023-07:m2309，收到 {part!r}")
        out.append((f"{m.group(1)}-{m.group(2)}", m.group(3).lower()))
    return out


def weekdays_of_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    d = datetime.date(y, m, 1)
    out = []
    while d.month == m:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


# ---------- 龙虎榜文本 ----------
def _int_rank(v):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def rank_to_text(date_str, df):
    recs = [r for r in _records(df) if _int_rank(r.get("rank")) is not None]
    if not recs:
        return None
    recs.sort(key=lambda r: _int_rank(r["rank"]))
    recs = recs[:20]

    def n(v):
        return f"{int(float(v)):,} "

    lines = ["大连商品交易所_日成交持仓排名_" + date_str.replace("-", ""),
             "名次\t会员简称\t成交量\t增减\t名次\t会员简称\t持买单量\t增减\t名次\t会员简称\t持卖单量\t增减"]
    for r in recs:
        k = _int_rank(r["rank"])
        lines.append("\t".join([str(k), str(r.get("vol_party_name", "")), n(r.get("vol", 0)), n(r.get("vol_chg", 0)),
                                str(k), str(r.get("long_party_name", "")), n(r.get("long_open_interest", 0)), n(r.get("long_open_interest_chg", 0)),
                                str(k), str(r.get("short_party_name", "")), n(r.get("short_open_interest", 0)), n(r.get("short_open_interest_chg", 0))]))
    return "\r\n".join(lines) + "\r\n"


# ---------- 各项 ----------
def job_main(out, ak):
    try:
        recs = _records(ak.futures_zh_daily_sina("M0"))
        rows = [[str(r["date"])[:10], r["open"], r["high"], r["low"], r["close"], r.get("volume"), r.get("hold"), r.get("settle")] for r in recs]
        if not rows:
            return {"ok": False, "reason": "接口返回空表"}
        _write_csv(os.path.join(out, "M0_daily.csv"), ["date", "open", "high", "low", "close", "volume", "hold", "settle"], rows)
        return {"ok": True, **_summ(rows)}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"[:300]}


def job_contracts(out, kline, years=(2016, 2027), months=CONTRACT_MONTHS, budget_s=2400, sleep=time.sleep, clock=time.time, pause=0.8):
    d = os.path.join(out, "contracts")
    os.makedirs(d, exist_ok=True)
    rep = {"ok": True, "fetched": [], "missing": [], "skippedExisting": [], "failed": {}, "stoppedByBudget": False, "remaining": []}
    todo = [f"M{y % 100:02d}{m:02d}" for y in range(years[0], years[1] + 1) for m in months]
    t0 = clock()
    for i, sym in enumerate(todo):
        path = os.path.join(d, sym + ".csv")
        if os.path.exists(path):
            rep["skippedExisting"].append(sym)
            continue
        if clock() - t0 > budget_s:
            rep["stoppedByBudget"] = True
            rep["remaining"] = [s for s in todo[i:] if not os.path.exists(os.path.join(d, s + ".csv"))]
            break
        try:
            r = kline(sym, max_rows=5000)
        except Exception as e:
            rep["failed"][sym] = f"{type(e).__name__}: {e}"[:150]
            continue
        if not r or not r.get("available"):
            reason = (r or {}).get("reason", "")
            if "没有合约" in reason or "空数据" in reason:
                rep["missing"].append(sym)
            else:
                rep["failed"][sym] = reason[:150]
        else:
            rows = [[b["date"], b["open"], b["high"], b["low"], b["close"], b.get("volume"), b.get("hold")] for b in r["bars"]]
            _write_csv(path, ["date", "open", "high", "low", "close", "volume", "hold"], rows)
            rep["fetched"].append(sym)
        sleep(pause)
    return rep


def parse_yahoo_chart(obj):
    try:
        res = obj["chart"]["result"][0]
        ts = res["timestamp"]
        cl = res["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        return []
    return [(datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date().isoformat(), float(c)) for t, c in zip(ts, cl) if c is not None]


def _foreign_symbols(ak):
    try:
        out = []
        for r in _records(ak.futures_foreign_commodity_subscribe_exchange_symbol()):
            v = r.get("symbol") if "symbol" in r else next(iter(r.values()), None)
            if v is not None:
                out.append(str(v))
        return out
    except Exception:
        return []


def _fetch_one_series(sym_yahoo, ak_candidates, get_json, ak):
    why = []
    try:
        rows = parse_yahoo_chart(get_json(YAHOO.format(sym=sym_yahoo)))
        if rows:
            return rows, "yahoo", why
        why.append("Yahoo 返回空")
    except Exception as e:
        why.append(f"Yahoo: {type(e).__name__}: {e}"[:200])
    for c in ak_candidates:
        try:
            rows = [(str(r["date"])[:10], float(r["close"])) for r in _records(ak.futures_foreign_hist(symbol=c)) if r.get("close") is not None]
            if rows:
                return rows, f"akshare:{c}", why
            why.append(f"akshare {c} 空")
        except Exception as e:
            why.append(f"akshare {c}: {type(e).__name__}: {e}"[:200])
    return [], None, why


def job_cbot(out, get_json, ak):
    rep = {}
    for k in ("ZM", "ZS"):
        rows, src, why = _fetch_one_series(CBOT_YAHOO[k], CBOT_AK[k], get_json, ak)
        if rows:
            _write_csv(os.path.join(out, f"cbot_{k}.csv"), ["date", "close"], rows)
            rep[k] = {"ok": True, "source": src, **_summ(rows)}
        else:
            rep[k] = {"ok": False, "reason": " | ".join(why)}
    rep["availableForeignSymbols"] = _foreign_symbols(ak)
    return rep


def job_fx(out, get_json, ak):
    rows, src, why = _fetch_one_series("CNY=X", [], get_json, ak)
    if not rows:
        try:
            recs = _records(ak.forex_hist_em(symbol="USDCNH"))
            rows = [(str(r.get("日期") or r.get("date"))[:10], float(r.get("最新价") or r.get("收盘") or r.get("close"))) for r in recs]
            src = "akshare:forex_hist_em(USDCNH，离岸价，与在岸略有差异)"
        except Exception as e:
            why.append(f"akshare forex_hist_em: {type(e).__name__}: {e}"[:200])
            rows = []
    if not rows:
        return {"ok": False, "reason": " | ".join(why)}
    _write_csv(os.path.join(out, "usdcny.csv"), ["date", "close"], rows)
    return {"ok": True, "source": src, **_summ(rows)}


def job_rank(out, ak, spec, days=None, sleep=time.sleep, clock=time.time, budget_s=2400, pause=0.8):
    os.makedirs(out, exist_ok=True)
    rep = {"ok": True, "written": 0, "skippedExisting": 0, "noData": [], "errors": 0, "stoppedByBudget": False, "stoppedByFailures": False}
    want = {}
    for ym, c in spec:
        for day in (days if days is not None else weekdays_of_month(ym)):
            if days is None or day.startswith(ym):
                want.setdefault(day, []).append(c)
    t0, fails = clock(), 0
    for day in sorted(want):
        ds = day.replace("-", "")
        need = []
        for c in want[day]:
            if os.path.exists(os.path.join(out, f"{c.upper()}_{ds}.txt")):
                rep["skippedExisting"] += 1
            else:
                need.append(c)
        if not need:
            continue
        if clock() - t0 > budget_s:
            rep["stoppedByBudget"] = True
            break
        try:
            got = ak.futures_dce_position_rank(date=ds)
            fails = 0
        except Exception:
            rep["errors"] += 1
            fails += 1
            rep["noData"] += [f"{c.upper()}:{day}" for c in need]
            if fails >= 25:
                rep["stoppedByFailures"] = True
                break
            sleep(pause)
            continue
        for c in need:
            txt = rank_to_text(day, (got or {}).get(c))
            if txt is None:
                rep["noData"].append(f"{c.upper()}:{day}")
            else:
                with open(os.path.join(out, f"{c.upper()}_{ds}.txt"), "w", encoding="utf-8", newline="") as f:
                    f.write(txt)
                rep["written"] += 1
        sleep(pause)
    return rep


# ---------- 探测：生意社分地区(江苏)报价接口是否真的存在 ----------
def probe_urls(today=None):
    t = today or datetime.date.today()
    ds = (t - datetime.timedelta(days=14)).isoformat()
    return [f"https://dp.100ppi.com/get_ptable.php?pid=83&ds={ds}&de={t.isoformat()}", "https://dp.100ppi.com/"]


def _cells(row_html):
    return [re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", c)) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, flags=re.S | re.I)]


def probe_parse(html):
    tables = re.findall(r"<table.*?</table>", html or "", flags=re.S | re.I)
    if not tables:
        return {"tables": 0, "headers": [], "rows": [], "hasJiangsu": False}
    trs = re.findall(r"<tr.*?</tr>", tables[0], flags=re.S | re.I)
    parsed = [_cells(t) for t in trs]
    parsed = [r for r in parsed if r]
    headers = parsed[0] if parsed else []
    return {"tables": len(tables), "headers": headers, "rows": parsed[1:6], "hasJiangsu": any("江苏" in h for h in headers)}


def job_probe(get_raw, urls=None):
    rep = {}
    for u in (urls or probe_urls()):
        try:
            status, ctype, body = get_raw(u)
            text = None
            for enc in ("utf-8", "gb18030"):
                try:
                    text = body.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            text = text if text is not None else body.decode("utf-8", "replace")
            rep[u] = {"status": status, "contentType": ctype, "bytes": len(body), "head": re.sub(r"\s+", " ", text)[:1500], **probe_parse(text)}
        except Exception as e:
            rep[u] = {"error": f"{type(e).__name__}: {e}"[:300]}
    return rep


def _http_get_raw(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


# ---------- 入口 ----------
def _http_get_json(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main(argv=None, ak=None, get_json=None, kline=None):
    p = argparse.ArgumentParser()
    p.add_argument("--only", default="main,contracts,cbot,fx")
    p.add_argument("--out", default="data/raw/seasonal")
    p.add_argument("--rank-list", default="")
    p.add_argument("--rank-out", default="data/raw/dce_rank_hist")
    p.add_argument("--budget", type=int, default=2400, help="合约日K/龙虎榜各自的时间预算(秒)")
    a = p.parse_args(argv)
    jobs = [j.strip() for j in a.only.split(",") if j.strip()]
    bad = [j for j in jobs if j not in JOBS]
    if bad or not jobs:
        sys.exit(f"不认识的项目 {bad}；可选：{','.join(JOBS)}")
    spec = parse_rank_list(a.rank_list) if "dce_rank" in jobs else []
    if "dce_rank" in jobs and not spec:
        sys.exit("dce_rank 需要 --rank-list，例如 2023-06:m2309,2023-07:m2309")
    if ak is None:
        import akshare as ak
    if get_json is None:
        get_json = _http_get_json
    if kline is None:
        import fetch_data
        kline = fetch_data.fetch_dce_daily_kline
    os.makedirs(a.out, exist_ok=True)
    rep_path = os.path.join(a.out, "_fetch_report.json")
    try:
        rep = json.load(open(rep_path, encoding="utf-8"))
    except Exception:
        rep = {}
    rep["runAt"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for j in jobs:
        print("▶", j, flush=True)
        try:
            if j == "main":
                rep[j] = job_main(a.out, ak)
            elif j == "contracts":
                rep[j] = job_contracts(a.out, kline, budget_s=a.budget)
            elif j == "cbot":
                rep[j] = job_cbot(a.out, get_json, ak)
            elif j == "fx":
                rep[j] = job_fx(a.out, get_json, ak)
            elif j == "probe":
                rep[j] = job_probe(_http_get_raw)
            else:
                rep[j] = job_rank(a.rank_out, ak, spec, budget_s=a.budget)
        except Exception as e:
            rep[j] = {"ok": False, "reason": f"{type(e).__name__}: {e}"[:300]}
        print("  ", json.dumps(rep[j], ensure_ascii=False)[:400], flush=True)
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
