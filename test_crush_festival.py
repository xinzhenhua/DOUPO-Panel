# -*- coding: utf-8 -*-
"""油厂开机率春节停机扰动窗口(cn_calendar.crush_festival_window + fetch_mysteel_crush_rate打标记)。运行：python3 test_crush_festival.py"""
import os, sys, traceback
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cn_calendar as cc
import fetch_data as fd

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def test_window_boundaries_use_real_festival_dates():
    w = cc.crush_festival_window
    assert (cc.CRUSH_FESTIVAL_BEFORE, cc.CRUSH_FESTIVAL_AFTER) == (7, 14)
    # 春节2026-02-17：节前7天=02-10(在)、节前8天=02-09(不在)；节后14天=03-03(在)、节后15天=03-04(不在)
    assert w("2026-02-10")["daysTo"] == -7 and w("2026-02-09") is None
    assert w("2026-02-17")["daysTo"] == 0 and w("2026-03-03")["daysTo"] == 14 and w("2026-03-04") is None
    # 春节2025-01-29
    assert w("2025-01-22")["daysTo"] == -7 and w("2025-01-21") is None and w("2025-02-12")["daysTo"] == 14 and w("2025-02-13") is None
    ok("窗口边界：春节前7天~后14天(2025-01-29、2026-02-17两个真实春节)；前8天/后15天不在")


def test_only_spring_festival_not_national_day():
    """★用数据证明国庆油厂不停机(节前6天60%→节后12天60%，基线63%)，所以不处理国庆。"""
    for d in ("2025-09-24", "2025-10-01", "2025-10-02", "2025-10-05", "2025-10-15", "2026-10-01", "2026-09-28"):
        assert cc.crush_festival_window(d) is None, d
    assert cc.holiday_window("2025-10-02", before=7, after=14)["name"] == "国庆", "对照：通用holiday_window会命中国庆，crush_festival_window必须把它过滤掉"
    ok("★国庆(含通用holiday_window会命中的日期)不在开机率的扰动窗口里——只认春节")


def test_window_is_different_from_the_feed_days_window():
    """饲料库存天数的备货窗口是节前21天~节后7天(用270周数据校准)，开机率是节前7天~节后14天——两个指标的节日效应不同，不能共用。"""
    assert (cc.HOLIDAY_WINDOW_BEFORE, cc.HOLIDAY_WINDOW_AFTER) == (21, 7)
    assert cc.holiday_window("2026-01-30") and cc.crush_festival_window("2026-01-30") is None, "节前18天：饲料备货窗口内，开机率窗口外"
    assert cc.holiday_window("2026-03-03") is None and cc.crush_festival_window("2026-03-03")["daysTo"] == 14, "节后14天：饲料备货窗口外，开机率窗口内"
    ok("两个窗口各自独立(饲料备货21/7天 vs 开机率停机7/14天)：同一天可能一个在窗口内、另一个不在")


def test_invalid_dates_do_not_crash():
    for d in (None, "", "乱码", "2026-13-45", 123):
        assert cc.crush_festival_window(d) is None
    ok("日期为空/乱码/不存在：返回None，不报错")


def _run(item_content, publish):
    old = fd.fetch_json_debug
    fd.fetch_json_debug = lambda *a, **k: ({"resultCode": 0, "total": 1, "dataList": [{"publishTime": publish + " 16:30", "content": item_content}]}, {})
    try:
        return fd.fetch_mysteel_crush_rate()
    finally:
        fd.fetch_json_debug = old


def test_backend_tags_festival_only_inside_the_window():
    inside = _run("开机方面，今日全国动态全样本油厂开机率为15.46%，较前一日上升7.20%。", "2026-02-24")
    assert inside["available"] and inside["value"] == 15.46 and inside["festival"] == {"name": "春节", "daysTo": 7, "phase": "假期", "holidayDate": "2026-02-17"}
    outside = _run("开机方面，今日全国动态全样本油厂开机率为60.95%，较前一日下降1.20%。", "2026-09-29")
    assert outside["available"] and outside["value"] == 60.95 and outside["festival"] is None
    national = _run("开机方面，今日全国动态全样本油厂开机率为60.00%，较前一日下降1.00%。", "2025-10-02")
    assert national["available"] and national["festival"] is None
    ok("★后端：2026-02-24(春节后7天)的15.46%带festival标记；2026-09-29、国庆2025-10-02的开机率festival=None")


def test_backend_value_below_the_floor_is_still_rejected():
    """9.80%(2025-01-26，春节前3天)低于合理范围下限10：照旧被当作异常丢弃(同样不投票)。有意不改下限：改了会让节日外的真实异常也放行。"""
    r = _run("开机方面，今日全国动态全样本油厂开机率为9.80%，较前一日下降33.33%。", "2025-01-26")
    assert r["available"] is False and "不合理" in r["reason"]
    assert fd.PLAUSIBLE_RANGES["crushRate"][0] == 10.0
    ok("下限10没改：9.80%(春节前3天)仍被丢弃——春节期间两种情形(<10丢弃、10~40抑制)都是不投票")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    fails = []
    for t in TESTS:
        try:
            t()
        except Exception:
            fails.append(t.__name__)
            print("❌", t.__name__)
            traceback.print_exc()
    print(f"\n结果：{_pass}项通过，{len(fails)}项失败" + (f"：{fails}" if fails else ""))
    sys.exit(1 if fails else 0)
