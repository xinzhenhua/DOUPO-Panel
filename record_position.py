# -*- coding: utf-8 -*-
"""记录持仓到仓库(v101.31)：data/position.json 是「离场提醒」读的持仓。由 .github/workflows/record-position.yml 手动触发写入。
  开仓：open --side 多|空 --lots 5 --date 2026-10-12 --price 3402
  平仓：close
文件格式 {side:1|-1, lots, entryD, entryPx, updated} ；空仓 {flat:true, updated}。只做参数校验和写文件，不联网。"""
import argparse, datetime, json, os, re, sys


def build(action, side=None, lots=None, date=None, price=None, now=None):
    now = now or datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    if action == "close":
        return {"flat": True, "updated": now}
    if action != "open":
        raise ValueError("action 只能是 open 或 close")
    s = {"多": 1, "做多": 1, "long": 1, "1": 1, "空": -1, "做空": -1, "short": -1, "-1": -1}.get(str(side).strip().lower())
    if s is None:
        raise ValueError("方向要填 多 或 空")
    try:
        n = int(float(lots))
        px = float(price)
    except Exception:  # noqa: BLE001
        raise ValueError("手数和成交均价要填数字")
    if n < 1 or not (500 <= px <= 20000):
        raise ValueError("手数至少1手，成交均价应是 元/吨 的合理数值(500~20000)")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date or "")):
        raise ValueError("开仓日期格式 YYYY-MM-DD")
    datetime.date.fromisoformat(date)
    return {"side": s, "lots": n, "entryD": date, "entryPx": px, "updated": now}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("action", choices=["open", "close"])
    ap.add_argument("--side", default=""); ap.add_argument("--lots", default=""); ap.add_argument("--date", default=""); ap.add_argument("--price", default="")
    ap.add_argument("--out", default="data/position.json")
    a = ap.parse_args(argv)
    try:
        rec = build(a.action, a.side, a.lots, a.date, a.price)
    except ValueError as e:
        print("❌", e); return 2
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    print("✅ 已记录：", json.dumps(rec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
