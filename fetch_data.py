#!/usr/bin/env python3
"""
豆粕基本面数据自动抓取脚本
============================
这个脚本设计为在 GitHub Actions 里运行（服务器端），不是在浏览器里运行。
服务器端运行不受 CORS 限制，可以自由请求任何网站的数据。

抓取的数据：
1. USDA-FAS 出口销售数据（ESR）- 豆粕(Soybean Cake and Meal)
2. USDA-FAS 供需库存数据（PSD）- 等同 WASDE 核心数据
3. CBOT 豆粕期货价格（通过 Yahoo Finance 非官方接口）
4. US Drought Monitor 官方干旱监测数据
5. UN Comtrade 中国大豆进口官方数据
6. USDA/AMS 谷物出口检验数据（用来推算"本月到港预报"）

关于开机率/商业库存/现货基差/猪粮比/能繁母猪这5项：
之前用Groq+Tavily做过AI辅助搜索自动化，实测发现数据质量不稳定
（比如把某公司PDF公告误当成全国数据、把价格表格误判成基差数据），
已放弃这个方向。现在改用"批量粘贴解析"方案：用户自己选择任意AI工具
获取数据(网页里有一键复制的提示词按钮)，把AI的回答粘贴回网页，
由前端JS纯文本解析并自动填充到对应输入框。这样数据的可信度由用户自己
选择的信息源和AI工具决定，网页本身只负责"解析+填充"这个机械环节，
不再涉及自动判断数据是否权威/相关。

运行方式：
    export USDA_API_KEY=你的api.data.gov密钥
    python3 fetch_data.py

输出：
    data/latest.json  ← 网页会读取这个文件
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

USDA_API_KEY = os.environ.get("USDA_API_KEY", "")
NASS_API_KEY = os.environ.get("NASS_API_KEY", "")  # 单独申请：quickstats.nass.usda.gov/api（跟FAS的密钥是两套系统）
USDA_BASE = "https://api.fas.usda.gov/api"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "latest.json")

# ---------------------------------------------------------------------------
# 通用请求函数（带重试，避免单次网络抖动导致整个流程失败）
# ---------------------------------------------------------------------------
def fetch_json(url, headers=None, retries=3, timeout=20):
    data, _ = fetch_json_debug(url, headers=headers, retries=retries, timeout=timeout)
    return data


def fetch_json_debug(url, headers=None, retries=3, timeout=20):
    """
    跟 fetch_json 一样，但额外返回诊断信息 (data, debug)。
    debug 里包含：实际请求的url、HTTP状态码、响应体前500字符、异常信息。
    这样接口返回的东西跟预期不一致时，不需要去翻GitHub Actions运行日志，
    直接看 data/latest.json 里的诊断字段就知道真实情况是什么。
    """
    headers = dict(headers or {})
    # 防御性修复：很多网站/API服务(包括Groq)会挡掉Python urllib默认的User-Agent
    # (被Cloudflare等WAF当作机器人流量拦截，报错"error code: 1010")，
    # 这里统一给个正常浏览器UA垫底，调用方传入的headers仍可以覆盖它。
    headers.setdefault("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    debug = {"url": url}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                debug["httpStatus"] = resp.status
                debug["rawSnippet"] = raw[:500]
                try:
                    return json.loads(raw), debug
                except json.JSONDecodeError as je:
                    debug["error"] = f"JSON解析失败: {je}（接口可能返回了非JSON内容，比如CSV或HTML）"
                    print(f"[WARN] JSON解析失败: {url} -> {je}\n  原始内容片段: {raw[:300]}", file=sys.stderr)
                    return None, debug
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:  # noqa: BLE001
                pass
            debug["httpStatus"] = e.code
            debug["error"] = f"HTTP {e.code}: {e.reason}"
            debug["rawSnippet"] = body
            print(f"[WARN] 请求失败(HTTP {e.code}): {url} -> {e.reason}\n  响应体: {body}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # noqa: BLE001 - 抓取脚本，任何异常都要能继续
            debug["error"] = str(e)
            print(f"[WARN] 请求失败: {url} -> {e}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return None, debug


def get_soybean_meal_esr_code():
    """动态查找"大豆粕/豆饼"在 ESR 商品列表里的编码，避免硬编码错误的代码。
    返回 (code, debug)：code为None时，debug里会说明具体是"请求失败"还是"没匹配上"，
    这两种情况原因完全不同，不应该用同一句模糊的错误信息掩盖。"""
    data, debug = fetch_json_debug(f"{USDA_BASE}/esr/commodities", headers={"X-Api-Key": USDA_API_KEY})
    if not data:
        debug["failureStage"] = "请求/esr/commodities本身失败（网络问题、认证失败、或被限流）"
        return None, debug
    for item in data:
        name = (item.get("commodityName") or "").lower()
        if "soybean" in name and ("meal" in name or "cake" in name):
            return item.get("commodityCode"), None
    # 请求成功、拿到了数据，但没有一条命中"soybean"+"meal/cake"，
    # 这跟"请求失败"是完全不同的情况——很可能是接口把商品名称改了，附上实际收到的完整列表方便核对
    debug["failureStage"] = "接口请求成功，拿到了商品列表，但没有一条命中'soybean'+'meal或cake'关键词"
    debug["actualCommodityNamesSeen"] = sorted(set((item.get("commodityName") or "") for item in data))[:50]
    debug["totalCommoditiesReturned"] = len(data)
    return None, debug


def fetch_esr_export_sales():
    code, code_lookup_debug = get_soybean_meal_esr_code()
    if not code:
        return {
            "available": False,
            "reason": "未能找到豆粕的ESR商品编码",
            "debug": code_lookup_debug,
        }

    # ★ 已修复：之前用"10月做分界"猜市场年度，实测发现猜错了
    #   （查到marketYear=2025时，最新数据停在2025-10-02，说明那是个已完结、不再更新的年度）。
    #   现在不再猜，而是同时试几个候选年份，用真实返回数据里最新的日期来判断哪个年度是当前活跃的。
    now = datetime.now(timezone.utc)
    candidate_years = [now.year - 1, now.year, now.year + 1]
    best_rows, best_debug, best_year = None, None, None
    all_attempts_debug = {}

    for candidate_my in candidate_years:
        url = f"{USDA_BASE}/esr/exports/commodityCode/{code}/allCountries/marketYear/{candidate_my}"
        rows, debug = fetch_json_debug(url, headers={"X-Api-Key": USDA_API_KEY})
        all_attempts_debug[str(candidate_my)] = {
            "httpStatus": debug.get("httpStatus"),
            "rowCount": len(rows) if rows else 0,
            "latestWeekFound": max((r.get("weekEndingDate") for r in rows if r.get("weekEndingDate")), default=None) if rows else None,
        }
        if not rows:
            continue
        candidate_latest_week = max((r.get("weekEndingDate") for r in rows if r.get("weekEndingDate")), default=None)
        if candidate_latest_week is None:
            continue
        best_latest_week = max((r.get("weekEndingDate") for r in best_rows if r.get("weekEndingDate")), default=None) if best_rows else None
        if best_rows is None or candidate_latest_week > best_latest_week:
            best_rows, best_debug, best_year = rows, debug, candidate_my

    rows, debug = best_rows, best_debug
    if not rows:
        return {
            "available": False,
            "reason": "ESR接口无返回数据（已尝试" + "、".join(str(y) for y in candidate_years) + "这几个候选年份）",
            "debug": all_attempts_debug,
        }

    # 关键点：每周有多个国家的记录，不能直接用 rows[-1]/rows[-2]
