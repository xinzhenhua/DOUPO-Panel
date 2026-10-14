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
print(f"\n结果：{n}项通过，0项失败")
