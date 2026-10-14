# -*- coding: utf-8 -*-
"""只抓盘中价格（v101.39）：三个合约的 15 分钟线 → data/prices.json。
比整套基本面更新轻很多（3 次请求，几秒），交易时段每 15 分钟跑一次。
文件很小（约 100KB），且只有K线真的变了才改写，避免每次产生无意义的提交。
页面读它来显示「盘中价、盘中浮盈亏、15分K线」；信号和平仓结论仍按日线收盘。"""
import datetime, json, os, sys, urllib.request
import net_timeout
net_timeout.install()

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "prices.json")


def merge(old, fresh, now):
    """old/fresh: {key: {symbol, bars}}；fresh 里取不到的合约沿用旧的。返回 (新文件内容, 是否有变化)。"""
    cons = dict((old or {}).get("contracts") or {})
    changed = False
    for k, v in fresh.items():
        if not v or not v.get("bars"):
            continue
        v = dict(v); v.setdefault("daily", (cons.get(k) or {}).get("daily"))
        if v.get("daily") is None: v.pop("daily", None)
        if cons.get(k) != v:
            cons[k] = v; changed = True
    out = {"updatedAt": now if changed else (old or {}).get("updatedAt", now), "source": "新浪财经(akshare) 15分钟线，东方财富备用", "contracts": cons}
    return out, changed


EM_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=114.%s&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57&klt=%s&fqt=0&end=20500101&lmt=%d"


def parse_em(obj):
    """东方财富 klines：'时间,开,收,高,低,量,额'（注意开收顺序）→ 和新浪同样的 bars。取不到返回 []。"""
    ks = ((obj or {}).get("data") or {}).get("klines") or []
    bars = []
    for r in ks:
        f = str(r).split(",")
        if len(f) < 6:
            continue
        try:
            t = f[0] + ":00" if len(f[0]) == 16 else f[0]
            b = {"datetime": t[:19], "open": float(f[1]), "close": float(f[2]), "high": float(f[3]), "low": float(f[4]), "volume": float(f[5]), "hold": None}
        except ValueError:
            continue
        if b["close"] > 0 and b["high"] > 0 and b["low"] > 0:
            bars.append(b)
    return bars


def fetch_em(code, klt="15", lmt=300, opener=None):
    """备用源：东方财富。opener(url)->dict 便于测试；失败返回 []（不抛）。"""
    url = EM_URL % (str(code).lower(), klt, lmt)
    try:
        if opener:
            return parse_em(opener(url))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return parse_em(json.loads(r.read().decode("utf-8", "ignore")))
    except Exception as e:  # noqa: BLE001
        print("⚠️ 东方财富", code, e)
        return []


def cross_check(a, b, tol=0.005):
    """两个源在共有的最新一根15分钟线上收盘价差；返回 {ok,diff,dt}，没有共有时间返回 None。"""
    mb = {x["datetime"]: x for x in b or []}
    for x in reversed(a or []):
        y = mb.get(x["datetime"])
        if y and y["close"] > 0:
            d = abs(x["close"] / y["close"] - 1)
            return {"ok": d <= tol, "diff": round(d, 5), "dt": x["datetime"], "a": x["close"], "b": y["close"]}
    return None


def main():
    import fetch_data as fd
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    codes = {"M09": fd.get_current_contract_code(9), "M05": fd.get_current_contract_code(5), "M01": fd.get_current_contract_code(1)}
    fresh = {}
    for k, code in codes.items():
        r = fd.fetch_dce_hourly_kline(code, max_bars=300, period="15")
        em = fetch_em(code)
        if r.get("available"):
            fresh[k] = {"symbol": r["symbol"], "bars": r["bars"]}
            ck = cross_check(r["bars"], em)
            if ck:
                fresh[k]["check"] = ck
                if not ck["ok"]:
                    print("⚠️ 两个价格源对不上", k, ck)
            try:   # 日线最近几根：收盘后新浪马上有当天收盘价，页面/提醒用它把价格序列接到最新一天
                d = fd.fetch_dce_daily_kline(code, max_rows=8)
                if d.get("available") and d.get("bars"):
                    fresh[k]["daily"] = [{"date": str(b["date"])[:10], "close": b["close"]} for b in d["bars"][-8:]]
            except Exception as e:  # noqa: BLE001
                print("⚠️ 日线", k, e)
        elif em:
            print("⚠️ 新浪取不到，改用东方财富备用源", k, code)
            fresh[k] = {"symbol": code, "bars": em[-300:], "src": "eastmoney"}
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
