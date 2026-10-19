# -*- coding: utf-8 -*-
"""抓取失败时沿用上次成功值（fetch_data.carry_forward）的测试。运行：python3 test_carry_forward.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd

n = 0


def ok(msg, cond, extra=""):
    global n
    if not cond:
        print("❌", msg, extra); sys.exit(1)
    n += 1; print("✅", msg)


prev = {"generatedAt": "2026-10-14T08:48:00+00:00",
        "hogRatio": {"available": True, "value": 4.28, "date": "2026-10-14", "source": "x"},
        "spotBasis": {"available": True, "value": 52, "date": "2026-10-13"},
        "mysteelFeedDays": {"available": False, "reason": "旧失败"}}
res = {"hogRatio": {"available": False, "reason": "akshare超时"}, "spotBasis": {"available": True, "value": 60, "date": "2026-10-14"},
       "mysteelFeedDays": {"available": False, "reason": "又失败"}, "sowInventory": {"available": False, "reason": "无"}}
c = fd.carry_forward(res, prev)
ok("本次失败、上次成功 → 沿用，且只沿用这一个", c == ["hogRatio"], c)
h = res["hogRatio"]
ok("沿用的值和数据日期是上次的，并写明本次失败原因与上次成功时间", h["available"] and h["value"] == 4.28 and h["date"] == "2026-10-14" and h["carried"] and "akshare超时" in h["carriedReason"] and h["carriedFrom"] == prev["generatedAt"], h)
ok("本次成功的不动（用新值）", res["spotBasis"]["value"] == 60 and "carried" not in res["spotBasis"])
ok("上次也是失败的不凭空造值", res["mysteelFeedDays"]["available"] is False and res["sowInventory"]["available"] is False)
# 连续两次失败：carriedFrom 仍是最初成功的时间，数据日期不变（页面按日期自动判过期）
prev2 = {"generatedAt": "2026-10-14T09:48:00+00:00", "hogRatio": h}
res2 = {"hogRatio": {"available": False, "reason": "还是超时"}}
fd.carry_forward(res2, prev2)
ok("连续失败：carriedFrom 保持最初成功时间，日期不变，原因更新", res2["hogRatio"]["carriedFrom"] == prev["generatedAt"] and res2["hogRatio"]["date"] == "2026-10-14" and "还是超时" in res2["hogRatio"]["carriedReason"], res2)
ok("没有上一次文件/类型不对也不报错", fd.carry_forward({"hogRatio": {"available": False}}, {}) == [] and fd.carry_forward({"hogRatio": {"available": False}}, None) == [])
ok("本次这个 key 压根没抓（不在结果里）不造", fd.carry_forward({}, prev) == [])

# ---- v101.86：USDA 三项（结果里没有 value 字段；latest.json 被失败覆盖后靠 usda_last_good.json 兜底） ----
from datetime import datetime, timezone, timedelta
NOW = datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)
esr_ok = {"available": True, "commodity": "Soybeans", "weekEnding": "2026-10-08", "dataAgeDays": 8, "isStale": False, "netSalesMT": 123456}
psd_ok = {"available": True, "commodity": "Oilseed, Soybean", "stocksToUsePct": 7.9, "marketYearLabel": "2026/27"}
sa_ok = {"available": True, "byCountry": {"BR": {"available": True, "production": 180000}}}
fail = lambda: {"available": False, "reason": "未能找到大豆(Soybeans)的ESR商品编码", "debug": {"httpStatus": 503}}
lg = {}
r_ok = {"exportSales": dict(esr_ok), "supplyDemand": dict(psd_ok), "southAmericaPsd": dict(sa_ok), "hogRatio": {"available": True, "value": 1}}
ok("成功时写进 last_good，只存 USDA 三项", fd.update_usda_last_good(r_ok, lg, NOW) and sorted(lg) == ["exportSales", "southAmericaPsd", "supplyDemand"])
ok("全部成功时不沿用任何东西", fd.carry_usda(r_ok, {}, lg, NOW) == [])
# 1) 上次 latest.json 里是成功的 → 直接沿用，不需要 value 字段
prev3 = {"generatedAt": "2026-10-19T01:00:00+00:00", "exportSales": dict(esr_ok), "supplyDemand": dict(psd_ok), "southAmericaPsd": dict(sa_ok)}
r1 = {"exportSales": fail(), "supplyDemand": fail(), "southAmericaPsd": fail()}
c1 = fd.carry_usda(r1, prev3, {}, NOW)
ok("USDA 三项本次失败、上次成功 → 三项都沿用", sorted(c1) == ["exportSales", "southAmericaPsd", "supplyDemand"], c1)
e1 = r1["exportSales"]
ok("沿用块带 carried/原因(含 503 的原失败原因)/最初成功时间，数据本身是上次的", e1["available"] and e1["carried"] and "ESR" in e1["carriedReason"] and e1["carriedFrom"] == prev3["generatedAt"] and e1["netSalesMT"] == 123456, e1)
ok("出口销售的「距今几天」按今天重算(10-08 → 11 天)，不是上次抓取时的 8 天", e1["dataAgeDays"] == 11, e1)
# 2) 上次 latest.json 也已经是失败（被上一次失败覆盖了）→ 用 last_good 兜底
prev_bad = {"generatedAt": "2026-10-19T02:00:00+00:00", "exportSales": fail(), "supplyDemand": fail(), "southAmericaPsd": fail()}
lg2 = {"exportSales": {"savedAt": (NOW - timedelta(days=3)).isoformat(), "block": dict(esr_ok)}}
r2 = {"exportSales": fail(), "supplyDemand": fail(), "southAmericaPsd": fail()}
c2 = fd.carry_usda(r2, prev_bad, lg2, NOW)
ok("连续两次失败：latest.json 已是失败，用 last_good 兜底，只沿用有存档的那一项", c2 == ["exportSales"] and r2["supplyDemand"]["available"] is False, (c2, r2))
ok("兜底沿用的「最初成功时间」是存档时间", r2["exportSales"]["carriedFrom"] == lg2["exportSales"]["savedAt"])
# 3) 期限：超过 10 天不沿用（不拿太旧的数当现在）
lg3 = {"exportSales": {"savedAt": (NOW - timedelta(days=11)).isoformat(), "block": dict(esr_ok)}}
r3 = {"exportSales": fail()}
ok("存档超过 10 天不沿用，老实显示失败", fd.carry_usda(r3, prev_bad, lg3, NOW) == [] and r3["exportSales"]["available"] is False)
lg3b = {"exportSales": {"savedAt": (NOW - timedelta(days=9, hours=23)).isoformat(), "block": dict(esr_ok)}}
ok("9 天 23 小时还在期限内", fd.carry_usda({"exportSales": fail()}, prev_bad, lg3b, NOW) == ["exportSales"])
# 4) 连续沿用：carriedFrom 不会被刷新成「上次 latest.json 的时间」
prev4 = {"generatedAt": "2026-10-19T02:00:00+00:00", "exportSales": dict(e1)}
r4 = {"exportSales": fail()}
fd.carry_usda(r4, prev4, {}, NOW + timedelta(hours=1))
ok("连续沿用：carriedFrom 保持最初成功时间（期限从最初成功算起，不会越沿越新）", r4["exportSales"]["carriedFrom"] == prev3["generatedAt"], r4)
r4b = {"exportSales": fail()}
ok("最初成功时间超过 10 天后，即使 latest.json 里是沿用块也不再沿用", fd.carry_usda(r4b, prev4, {}, NOW + timedelta(days=10, hours=2)) == [] and r4b["exportSales"]["available"] is False)
# 5) 沿用块不会被当成"新成功"写进存档
lg5 = {}
ok("沿用块不写进 last_good", fd.update_usda_last_good({"exportSales": e1}, lg5, NOW) is False and lg5 == {})
# 6) 本次成功不动；key 没抓不造；没有存档也不报错
r6 = {"exportSales": dict(esr_ok, netSalesMT=999)}
ok("本次成功的不沿用、用新值", fd.carry_usda(r6, prev3, lg2, NOW) == [] and r6["exportSales"]["netSalesMT"] == 999 and "carried" not in r6["exportSales"])
ok("key 不在结果里不造；prev/last_good 为 None 不报错", fd.carry_usda({}, prev3, lg2, NOW) == [] and fd.carry_usda({"exportSales": fail()}, None, None, NOW) == [])
ok("时间字符串坏了不崩、不沿用", fd.carry_usda({"exportSales": fail()}, {}, {"exportSales": {"savedAt": "坏的", "block": dict(esr_ok)}}, NOW) == [])

# ---- 接进主流程的那一层（读写存档文件）----
import tempfile, json as _json
tmp = os.path.join(tempfile.mkdtemp(), "usda_last_good.json")
ra = {"exportSales": dict(esr_ok), "supplyDemand": dict(psd_ok), "southAmericaPsd": dict(sa_ok)}
ok("成功的一轮：不沿用，且把三项写进存档文件", fd.apply_usda_carry(ra, {}, tmp, NOW) == [] and sorted(_json.load(open(tmp, encoding="utf-8"))) == ["exportSales", "southAmericaPsd", "supplyDemand"])
rb = {"exportSales": fail(), "supplyDemand": fail(), "southAmericaPsd": fail()}
ok("失败的一轮（latest.json 已经是失败）：靠存档文件沿用三项", sorted(fd.apply_usda_carry(rb, prev_bad, tmp, NOW + timedelta(hours=2))) == ["exportSales", "southAmericaPsd", "supplyDemand"] and rb["supplyDemand"]["stocksToUsePct"] == 7.9)
ok("失败的一轮不改写存档（还是最初成功那份）", _json.load(open(tmp, encoding="utf-8"))["exportSales"]["savedAt"] == NOW.isoformat())
open(tmp, "w", encoding="utf-8").write("{坏的json")
rc = {"exportSales": fail()}
ok("存档文件坏了不崩，只是没得沿用", fd.apply_usda_carry(rc, {}, tmp, NOW) == [] and rc["exportSales"]["available"] is False)
ok("存档里的块本身是失败的不沿用", fd.carry_usda({"exportSales": fail()}, {}, {"exportSales": {"savedAt": NOW.isoformat(), "block": {"available": False}}}, NOW) == [])
print(f"\n结果：{n}项通过，0项失败")
