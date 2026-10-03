# -*- coding: utf-8 -*-
"""
数据同步停止的主动警告(看门狗)。

为什么需要：页面的"数据健康度"面板已经会检测"每小时同步本身是否还活着"(错过的大商所交易日数)，但那是**被动**的——
得你打开页面才看得到。同步停了时所有卡片看起来都正常、只是数据越来越旧，这种故障最隐蔽。这里把同一套判断搬到一个独立的
GitHub Actions 定时任务里，停了就主动通知(开GitHub Issue + 让这次运行变红，GitHub默认会发失败邮件)。

★口径必须和页面的syncHealth完全一致：错过≤1个交易日=ok、2~3个=degraded、≥4个=stale；
  数据日期落在非交易日时按前一个交易日算(最多往前10天)；截止点是北京时间18:00(18点前算到昨天，18点后算到今天)；最多数60个。
  test_sync_watchdog.py 里用 Node 调用页面里真实的 tradingDaysMissed 函数逐点对拍。

用法：python3 sync_watchdog.py --latest data/latest.json [--now ISO时间] [--no-fail]
  最后一行输出一个JSON({state, alert, severity, missed, label, ...})；报警时退出码1(--no-fail时仍是0)。
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import cn_calendar

BJ = timezone(timedelta(hours=8))
STATE_OK, STATE_DEGRADED, STATE_STALE, STATE_NODATA = "ok", "degraded", "stale", "nodata"


def _bj(dt):
    return dt.astimezone(BJ)


def trading_days_missed(date_str, now):
    """从数据所在交易日之后到"截止点"之间错过了几个大商所交易日。与页面的tradingDaysMissed逐行对应。
    date_str：数据日期'YYYY-MM-DD'(取前10位)；now：带时区的datetime。无法解析返回None。"""
    try:
        y, m, d = (int(x) for x in str(date_str)[:10].split("-"))
        d0 = date(y, m, d)
    except (ValueError, TypeError):
        return None
    for _ in range(10):                                   # 数据落在非交易日(周末/休市)时，按前一个交易日算
        if cn_calendar.dce_is_trading_day(d0):
            break
        d0 -= timedelta(days=1)
    nb = _bj(now)
    as_of = date(nb.year, nb.month, nb.day) - (timedelta(0) if nb.hour >= 18 else timedelta(days=1))     # 18点后今天已收盘，算到今天；之前算到昨天
    miss, t = 0, d0 + timedelta(days=1)
    while t <= as_of and miss < 60:
        if cn_calendar.dce_is_trading_day(t):
            miss += 1
        t += timedelta(days=1)
    return miss


def assess(generated_at, now):
    """评估同步状态。返回{state, alert, severity, missed, label, detail}。
    alert=True表示该主动通知：degraded(错过≥2个交易日，已经是明确的异常)、stale、nodata(连时间戳都没有，比"晚了"更严重)。"""
    if generated_at is None or generated_at == "":
        return {"state": STATE_NODATA, "alert": True, "severity": STATE_NODATA, "missed": None, "label": "latest.json里没有generatedAt", "detail": "同步可能从未成功过，或文件被改坏了"}
    try:
        g = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        if g.tzinfo is None:
            g = g.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return {"state": STATE_NODATA, "alert": True, "severity": STATE_NODATA, "missed": None, "label": "同步时间格式无法识别", "detail": str(generated_at)}
    gb = _bj(g)
    ds = f"{gb.year:04d}-{gb.month:02d}-{gb.day:02d}"
    miss = trading_days_missed(ds, now)
    when = f"{ds} {gb.hour:02d}:{gb.minute:02d}"
    if miss <= 1:
        return {"state": STATE_OK, "alert": False, "severity": None, "missed": miss, "label": f"同步正常：{when}", "detail": ""}
    if miss <= 3:
        return {"state": STATE_DEGRADED, "alert": True, "severity": STATE_DEGRADED, "missed": miss, "label": f"同步晚了：{when}，错过{miss}个交易日",
                "detail": "每小时同步可能中断了，检查GitHub Actions的运行记录"}
    return {"state": STATE_STALE, "alert": True, "severity": STATE_STALE, "missed": miss, "label": f"同步可能已停止：{when}，错过{miss}个交易日",
            "detail": "所有卡片的数据都在变旧却看不出来——请检查GitHub Actions(是否被禁用/报错/token失效)"}


def decide_action(alert, open_issue):
    """怎么通知：报警且还没有未关闭的issue→open；已有→keep(不重复开，失败邮件每天仍会提醒)；恢复且有未关issue→close；否则none。"""
    if alert:
        return "keep" if open_issue else "open"
    return "close" if open_issue else "none"


def load_generated_at(path):
    """读latest.json的generatedAt。文件不存在/不是合法JSON/不是对象都返回None(按nodata报警，不是崩溃)。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data.get("generatedAt") if isinstance(data, dict) else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", default="data/latest.json")
    ap.add_argument("--now", default=None, help="测试用：指定'现在'(ISO时间)；默认真实时间")
    ap.add_argument("--no-fail", action="store_true", help="只输出结果，报警时也以0退出(工作流里要先拿到结果再决定怎么通知时用)")
    a = ap.parse_args(argv)
    now = datetime.fromisoformat(a.now) if a.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    res = assess(load_generated_at(a.latest), now)
    res["checkedAt"] = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    print(json.dumps(res, ensure_ascii=False))
    return 0 if (not res["alert"] or a.no_fail) else 1


if __name__ == "__main__":
    sys.exit(main())
