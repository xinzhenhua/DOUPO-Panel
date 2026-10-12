# -*- coding: utf-8 -*-
"""只抓盘中价格（v101.39）：三个合约的 15 分钟线 → data/prices.json。
比整套基本面更新轻很多（3 次请求，几秒），交易时段每 15 分钟跑一次。
文件很小（约 100KB），且只有K线真的变了才改写，避免每次产生无意义的提交。
页面读它来显示「盘中价、盘中浮盈亏、15分K线」；信号和平仓结论仍按日线收盘。"""
import datetime, json, os, sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "prices.json")


def merge(old, fresh, now):
    """old/fresh: {key: {symbol, bars}}；fresh 里取不到的合约沿用旧的。返回 (新文件内容, 是否有变化)。"""
    cons = dict((old or {}).get("contracts") or {})
    changed = False
    for k, v in fresh.items():
        if not v or not v.get("bars"):
            continue
        if cons.get(k) != v:
            cons[k] = v; changed = True
    out = {"updatedAt": now if changed else (old or {}).get("updatedAt", now), "source": "新浪财经(akshare) 15分钟线", "contracts": cons}
    return out, changed


def main():
    import fetch_data as fd
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    codes = {"M09": fd.get_current_contract_code(9), "M05": fd.get_current_contract_code(5), "M01": fd.get_current_contract_code(1)}
    fresh = {}
    for k, code in codes.items():
        r = fd.fetch_dce_hourly_kline(code, max_bars=300, period="15")
        if r.get("available"):
            fresh[k] = {"symbol": r["symbol"], "bars": r["bars"]}
        else:
            print("⚠️", k, code, r.get("reason"))
    old = None
    try:
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:  # noqa: BLE001
        pass
    out, changed = merge(old, fresh, now)
    if not changed and old:
        print("价格没变化，不改写"); return 0
    if not fresh and not old:
        print("❌ 一个合约都没取到"); return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("✅ 已更新", {k: len(v["bars"]) for k, v in out["contracts"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
