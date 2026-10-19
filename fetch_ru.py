"""橡胶(RU)主力连续日线 → data/ru_live.json（v102.0）。
页面 cockpit/ru_hist.json 只到快照日；这里把快照日之后的真实日线(开高低收)累积下来，页面按换月复权因子接上。
格式（按列）：{"d":[日期],"o":[],"h":[],"l":[],"c":[],"m":[主力月份如"2605"，取不到则省略]}
失败不报错退出码(工作流里 continue-on-error)，不覆盖已有文件。"""
import json, os, sys, datetime

OUT = "data/ru_live.json"
HIST = "cockpit/ru_hist.json"


def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def parse_frame(df):
    """DataFrame(日期/开盘价/最高价/最低价/收盘价) → [(d,o,h,l,c)]，剔除无效行"""
    rows = []
    for _, r in df.iterrows():
        try:
            d = str(r.get("日期") if "日期" in r else r.get("date"))[:10]
            o, h, l, c = (float(r[k]) for k in (("开盘价", "最高价", "最低价", "收盘价") if "收盘价" in r else ("open", "high", "low", "close")))
        except Exception:  # noqa: BLE001
            continue
        if not (o > 0 and h > 0 and l > 0 and c > 0 and h >= l):
            continue
        rows.append((d, o, h, l, c))
    return rows


def merge(live, rows, last_hist):
    """把 rows 里晚于快照最后一天、且不在 live 里的并入 live（同日以新数据覆盖，保持升序）"""
    cur = {d: (o, h, l, c) for d, o, h, l, c in zip(live.get("d", []), live.get("o", []), live.get("h", []), live.get("l", []), live.get("c", []))}
    for d, o, h, l, c in rows:
        if d > last_hist:
            cur[d] = (o, h, l, c)
    ds = sorted(cur)
    out = {"d": ds, "o": [cur[d][0] for d in ds], "h": [cur[d][1] for d in ds], "l": [cur[d][2] for d in ds], "c": [cur[d][3] for d in ds]}
    if live.get("m") and len(live["m"]) == len(live.get("d", [])):
        mm = dict(zip(live["d"], live["m"]))
        if any(mm.get(d) for d in ds):
            out["m"] = [mm.get(d) or "" for d in ds]
    return out


def main():
    hist = load_json(HIST, {})
    last_hist = (hist.get("d") or [""])[-1]
    if not last_hist:
        print("[RU] 找不到快照"); return 0
    import akshare as ak
    start = (datetime.date.fromisoformat(last_hist) - datetime.timedelta(days=3)).strftime("%Y%m%d")
    end = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y%m%d")
    df = ak.futures_main_sina(symbol="RU0", start_date=start, end_date=end)
    rows = parse_frame(df)
    if not rows:
        print("[RU] 没取到数据，保留旧文件"); return 0
    live = merge(load_json(OUT, {}), rows, last_hist)
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(live, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[RU] 快照 {last_hist} 之后 {len(live['d'])} 根日线，最新 {live['d'][-1] if live['d'] else '—'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(f"[RU] 失败：{type(e).__name__}: {str(e)[:150]}"); sys.exit(0)
