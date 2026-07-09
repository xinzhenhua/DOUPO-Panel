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
6. USDA/AMS 谷物出口检验数据（用来推算"本周到港预报"）
7. AI辅助搜索（Groq跑DeepSeek开源蒸馏模型 + Tavily搜索）：
   豆粕商业库存 / 猪粮比 / 能繁母猪存栏 / 现货基差 / 开机率

关于第7项的技术选型说明：
用户明确要求"免费"方案，这里用的是官方、合法的免费层组合：
- Groq(groq.com)：官方免费开发者层，用来调用DeepSeek R1蒸馏模型做推理
  （不是逆向工程DeepSeek官方付费API，是Groq自己合法托管的开源权重版本）
- Tavily(tavily.com)：官方免费层，每月1000次搜索，无需绑卡
这套组合完全合法、稳定，跟"抓取/逆向工程免费个人聊天产品来做自动化"
这种ToS风险很高、随时可能失效的方案是两回事。

运行方式：
    export USDA_API_KEY=你的api.data.gov密钥
    export GROQ_API_KEY=你的groq.com密钥
    export TAVILY_API_KEY=你的tavily.com密钥
    export UNCOMTRADE_API_KEY=你的comtradeplus.un.org密钥
    python3 fetch_data.py

输出：
    data/latest.json  ← 网页会读取这个文件
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

USDA_API_KEY = os.environ.get("USDA_API_KEY", "")
USDA_BASE = "https://api.fas.usda.gov/api"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = "deepseek-r1-distill-llama-70b"
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_BASE = "https://api.tavily.com"
UNCOMTRADE_API_KEY = os.environ.get("UNCOMTRADE_API_KEY", "")
UNCOMTRADE_BASE = "https://comtradeapi.un.org/data/v1"
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


# ---------------------------------------------------------------------------
# AI辅助搜索核心框架：Tavily搜索 + Groq(DeepSeek蒸馏模型)提取 + 时效性验证
# ---------------------------------------------------------------------------
def tavily_search(query, max_results=5):
    """调用Tavily搜索API（官方免费层，每月1000次，无需绑卡）。
    返回搜索结果列表：[{title, url, content, published_date}, ...]，失败返回None。

    ★ 已修复真实bug：之前把api_key塞进了请求body里，但Tavily官方文档和多个独立示例
      一致确认认证方式是"Authorization: Bearer tvly-xxx"这个HTTP请求头，
      body里不需要（也不应该）带api_key。之前代码完全没设置这个请求头，
      导致每次请求都认证失败，这就是5个AI搜索指标全部失败的真正原因。"""
    if not TAVILY_API_KEY:
        return None, {"error": "缺少 TAVILY_API_KEY"}
    url = f"{TAVILY_BASE}/search"
    payload = json.dumps({
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "include_answer": False,
    }).encode("utf-8")
    debug = {"url": url, "query": query}
    try:
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TAVILY_API_KEY}",
            },
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            debug["resultCount"] = len(results)
            return results, debug
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        debug["error"] = f"HTTP {e.code}: {e.reason}"
        debug["rawSnippet"] = body
        print(f"[WARN] Tavily搜索失败(HTTP {e.code}): {query} -> {body}", file=sys.stderr)
        return None, debug
    except Exception as e:  # noqa: BLE001
        debug["error"] = str(e)
        print(f"[WARN] Tavily搜索失败: {query} -> {e}", file=sys.stderr)
        return None, debug


def groq_extract(system_prompt, user_prompt):
    """调用Groq API跑DeepSeek R1蒸馏模型做信息提取（官方免费开发者层）。
    返回模型输出的文本，失败返回None。

    ★ 已修复真实bug："error code: 1010"是Cloudflare WAF的错误码，不是Groq自己的报错格式，
      意思是"根据你的请求签名判定为非人类流量并拦截"。查了Cloudflare官方社区多个案例，
      确认常见原因就是缺少正常的User-Agent请求头——Python urllib默认发送的
      "Python-urllib/x.x"这个UA本身就是最常见被拦截的特征之一（跟Java默认UA被拦截是同一类问题）。
      加上一个正常的User-Agent后即可绕开这个WAF规则。"""
    if not GROQ_API_KEY:
        return None, {"error": "缺少 GROQ_API_KEY"}
    url = f"{GROQ_BASE}/chat/completions"
    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,  # 要的是准确提取事实，不是创意发散，温度调低
        "max_tokens": 800,
    }).encode("utf-8")
    debug = {"url": url}
    try:
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return content, debug
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        debug["error"] = f"HTTP {e.code}: {e.reason}"
        debug["rawSnippet"] = body
        print(f"[WARN] Groq调用失败(HTTP {e.code}): {body}", file=sys.stderr)
        return None, debug
    except Exception as e:  # noqa: BLE001
        debug["error"] = str(e)
        print(f"[WARN] Groq调用失败: {e}", file=sys.stderr)
        return None, debug


def _extract_json_from_ai_response(text):
    """DeepSeek R1蒸馏模型是推理模型，输出里常带<think>...</think>思考过程，
    真正的JSON答案在思考过程之后。这里做容错提取：
    先去掉<think>标签，再找文本里第一个{...}JSON块。"""
    if not text:
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # 去掉可能的markdown代码块包裹
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned.strip())
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def ai_search_with_staleness_check(indicator_name, search_queries, extraction_instruction,
                                     max_age_days, max_retries=2):
    """
    时效性分级验证模块（核心机制）：
    ① 用Tavily搜索 → 把结果喂给Groq/DeepSeek提取 {数值, 日期, 来源, 原文片段}
    ② 解析AI返回的日期，算出距今天数
    ③ 超过 max_age_days → 判定过期，换一个更强调"要最新"的搜索词重试
    ④ 最多重试 max_retries 次，仍过期则返回结果但标记 isStale=True
       （前端会显示+橙色警告，但不会隐藏数值，方便你自己判断要不要用）

    search_queries: 一个列表，按优先级尝试的搜索词（比如开机率先试"我的钢铁网豆粕开机率"再试通用词）
    """
    all_debug = {"indicator": indicator_name, "attempts": []}
    last_stale_result = None

    for attempt in range(max_retries + 1):
        query_idx = min(attempt, len(search_queries) - 1)
        query = search_queries[query_idx]
        if attempt > 0:
            # 重试时明确要求"更新的数据"，而不是重复同一个搜索词指望运气
            query = query + f"（请找最近{max_age_days}天内发布的最新数据，不要旧数据）"

        results, search_debug = tavily_search(query, max_results=5)
        attempt_log = {"attempt": attempt + 1, "query": query, "searchDebug": search_debug}

        if not results:
            attempt_log["outcome"] = "搜索失败或无结果"
            all_debug["attempts"].append(attempt_log)
            continue

        # 把搜索结果拼成上下文喂给AI
        context = "\n\n".join(
            f"来源{i+1}: {r.get('title','')}\nURL: {r.get('url','')}\n"
            f"发布日期: {r.get('published_date','未知')}\n内容: {r.get('content','')[:800]}"
            for i, r in enumerate(results)
        )
        system_prompt = (
            "你是一个专业的农产品期货数据助手。根据提供的搜索结果，提取用户要求的具体数据。"
            "必须只返回一个JSON对象，不要有任何其他文字说明。"
            'JSON格式严格为：{"数值": <数字或字符串>, "日期": "YYYY-MM-DD", "来源": "<URL>", "原文片段": "<支持这个数值的原文摘录，20字以内>"}'
            "如果搜索结果里找不到明确数据，数值字段填null。日期必须是文中明确提到的发布/统计日期，不能是你的推测。"
        )
        user_prompt = f"{extraction_instruction}\n\n搜索结果：\n{context}"

        ai_text, groq_debug = groq_extract(system_prompt, user_prompt)
        attempt_log["groqDebug"] = groq_debug

        if not ai_text:
            attempt_log["outcome"] = "Groq调用失败"
            all_debug["attempts"].append(attempt_log)
            continue

        parsed = _extract_json_from_ai_response(ai_text)
        if not parsed or parsed.get("数值") is None:
            attempt_log["outcome"] = "AI未能从搜索结果中提取到有效数值"
            attempt_log["aiRawResponse"] = ai_text[:500]
            all_debug["attempts"].append(attempt_log)
            continue

        # 计算数据新鲜度
        date_str = parsed.get("日期")
        age_days = None
        if date_str:
            try:
                parsed_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - parsed_date).days
            except ValueError:
                age_days = None

        is_stale = age_days is None or age_days > max_age_days
        attempt_log["outcome"] = f"提取成功，数据日期{date_str}，距今{age_days}天" + ("（过期）" if is_stale else "（新鲜）")
        all_debug["attempts"].append(attempt_log)

        if not is_stale:
            return {
                "available": True,
                "value": parsed.get("数值"),
                "date": date_str,
                "ageDays": age_days,
                "isStale": False,
                "source": parsed.get("来源"),
                "quote": parsed.get("原文片段"),
                "attemptsUsed": attempt + 1,
                "debug": all_debug,
            }
        # 过期就继续下一轮重试（如果还有重试次数的话），先把这轮结果存起来备用
        last_stale_result = {
            "available": True,
            "value": parsed.get("数值"),
            "date": date_str,
            "ageDays": age_days,
            "isStale": True,
            "source": parsed.get("来源"),
            "quote": parsed.get("原文片段"),
            "attemptsUsed": attempt + 1,
            "debug": all_debug,
        }

    # 重试次数用完，仍然过期：按用户确认的方案——显示+警告+仍可手动覆盖
    if last_stale_result is not None:
        return last_stale_result
    return {"available": False, "reason": f"{max_retries+1}次尝试后仍未能提取到有效数据", "debug": all_debug}


# ---------------------------------------------------------------------------
# AI辅助搜索：5个手动指标的自动化（用户确认可以AI搜索直接同步的部分）
# ---------------------------------------------------------------------------
def fetch_soymeal_stock_ai():
    """全国豆粕商业库存(万吨)，每周更新，10天有效期"""
    return ai_search_with_staleness_check(
        indicator_name="豆粕商业库存",
        search_queries=["全国豆粕商业库存 最新 万吨", "豆粕库存 汇易 mysteel 周度数据"],
        extraction_instruction="提取中国全国豆粕商业库存的最新数值，单位是万吨。只要一个全国总量数字，不要地区分项。",
        max_age_days=10,
        max_retries=2,
    )


def fetch_hog_grain_ratio_ai():
    """猪粮比，每周更新，10天有效期"""
    return ai_search_with_staleness_check(
        indicator_name="猪粮比",
        search_queries=["猪粮比 最新 农业农村部", "生猪价格 玉米价格 比价 最新周度"],
        extraction_instruction="提取中国最新的猪粮比数值（生猪价格与玉米价格的比值，正常盈亏线是6:1）。只要比值数字本身，比如6.2。",
        max_age_days=10,
        max_retries=2,
    )


def fetch_breeding_sows_ai():
    """能繁母猪存栏(万头)，每月更新，45天有效期"""
    return ai_search_with_staleness_check(
        indicator_name="能繁母猪存栏",
        search_queries=["能繁母猪存栏量 最新 农业农村部 万头", "能繁母猪 存栏 环比 月度数据"],
        extraction_instruction="提取中国最新的能繁母猪存栏量，单位是万头。国家产能调控目标是3750万头。",
        max_age_days=45,
        max_retries=2,
    )


def fetch_spot_basis_ai():
    """现货基差(元/吨)，全国平均，只需要符号方向，10天有效期"""
    return ai_search_with_staleness_check(
        indicator_name="现货基差",
        search_queries=["豆粕现货基差 全国平均 最新 元/吨", "豆粕基差报价 汇总 本周"],
        extraction_instruction=(
            "提取中国豆粕现货基差的全国平均水平，单位元/吨。"
            "基差=现货价-期货价，正数代表现货贵(正基差)，负数代表现货便宜(负基差)。"
            "只需要一个能代表全国平均水平的数字，如果只找到分地区数据，请取平均或选一个有代表性的数字并说明。"
        ),
        max_age_days=10,
        max_retries=2,
    )


def fetch_crush_rate_ai():
    """油厂开机率(%)，优先尝试我的钢铁网(Mysteel)搜索，找不到再用通用搜索兜底"""
    return ai_search_with_staleness_check(
        indicator_name="油厂开机率",
        search_queries=[
            "我的钢铁网 mysteel 豆粕 油厂开机率 全国",  # 优先：Mysteel专门查询
            "豆粕 油厂开机率 全国 最新 汇易咨询",       # 次选：汇易咨询
            "大豆压榨开机率 全国平均 本周",             # 兜底：通用搜索
        ],
        extraction_instruction=(
            "提取中国全国大豆油厂开机率的最新数值，单位是百分比。"
            "只需要一个能代表全国平均水平的百分比数字（不要单个地区的数字），"
            "参考阈值：低于40%算偏多信号，高于60%算偏空信号。"
        ),
        max_age_days=10,
        max_retries=2,
    )


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
    # （那样可能取到"同一周的另一个国家"而不是"上一周"）。
    # 必须先拿到"去重后的周次日期"排序，再取最近两个不同的周。
    unique_weeks = sorted(set(r.get("weekEndingDate") for r in rows if r.get("weekEndingDate")))
    if len(unique_weeks) < 2:
        return {
            "available": False,
            "reason": "数据量不足以计算环比（不足两个不同周次）",
            "debug": {"note": f"拿到{len(rows)}条记录，但去重后只有{len(unique_weeks)}个周次", "sampleRawRow": rows[0] if rows else None},
        }

    latest_week_date = unique_weeks[-1]
    prev_week_date = unique_weeks[-2]

    # 汇总所有国家在某一周的净销售量（weeklyExports字段名可能随API版本略有差异，做容错）
    def week_total(week_rows, field_candidates):
        total = 0
        for r in week_rows:
            for f in field_candidates:
                if f in r and r[f] is not None:
                    total += r[f]
                    break
        return total

    latest_week = [r for r in rows if r.get("weekEndingDate") == latest_week_date]
    prev_week = [r for r in rows if r.get("weekEndingDate") == prev_week_date]

    net_sales_field_candidates = ["weeklyExports", "grossNewSales", "netSales"]
    latest_total = week_total(latest_week, net_sales_field_candidates)
    prev_total = week_total(prev_week, net_sales_field_candidates)

    china_latest = sum(
        r.get("weeklyExports", 0) or 0
        for r in latest_week
        if "china" in (r.get("countryName") or "").lower()
    )

    wow_change_pct = None
    if prev_total:
        wow_change_pct = round((latest_total - prev_total) / abs(prev_total) * 100, 1)

    # 计算数据新鲜度：即便三个候选年份里选出了"最新的"，也可能三个都不新鲜
    # （比如接口本身更新滞后）。ESR是每周更新的报告，超过25天没更新就该提醒一下。
    try:
        latest_date_parsed = datetime.fromisoformat(latest_week_date.replace("Z", "+00:00"))
        if latest_date_parsed.tzinfo is None:
            latest_date_parsed = latest_date_parsed.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - latest_date_parsed).days
    except (ValueError, AttributeError):
        age_days = None
    is_stale = age_days is not None and age_days > 25

    result = {
        "available": True,
        "weekEnding": latest_week_date,
        "marketYearUsed": best_year,
        "dataAgeDays": age_days,
        "isStale": is_stale,
        "latestTotalMT": latest_total,
        "prevTotalMT": prev_total,
        "wowChangePct": wow_change_pct,
        "chinaLatestMT": china_latest,
        "source": "USDA-FAS ESR API",
        "sourceUrl": "https://apps.fas.usda.gov/esrqs/",
    }
    if is_stale:
        result["debug"] = {
            "warning": f"三个候选年份({candidate_years})里最新数据是{latest_week_date}，距今{age_days}天，"
                       f"已超过25天的新鲜度阈值，ESR是每周更新的报告，这可能意味着接口有延迟或候选年份范围需要调整",
            "allCandidateYearsResults": all_attempts_debug,
        }
    # 如果拿到了记录，但汇总出来的数值全是0，很可能是 weeklyExports/grossNewSales/netSales
    # 这几个候选字段名都没命中，附上实际字段名方便诊断
    if latest_total == 0 and prev_total == 0 and latest_week:
        result["debug"] = {
            "warning": "已连接上接口并拿到数据，但汇总净销售量为0，可能是字段名候选(weeklyExports/grossNewSales/netSales)都没匹配上",
            "actualFieldsSeen": sorted(latest_week[0].keys()) if latest_week else [],
            "sampleRawRow": latest_week[0] if latest_week else None,
        }
    return result


# ---------------------------------------------------------------------------
# 2. USDA-FAS 供需库存数据 (PSD) —— 等同 WASDE 里豆粕/大豆的核心数字
# ---------------------------------------------------------------------------
def get_soybean_meal_psd_code():
    """返回 (code, debug)，跟ESR那边一样区分'请求失败'和'没匹配上'两种不同情况。"""
    data, debug = fetch_json_debug(f"{USDA_BASE}/psd/commodities", headers={"X-Api-Key": USDA_API_KEY})
    if not data:
        debug["failureStage"] = "请求/psd/commodities本身失败（网络问题、认证失败、或被限流）"
        return None, debug
    for item in data:
        name = (item.get("commodityName") or "").lower()
        if "soybean" in name and "meal" in name:
            return item.get("commodityCode"), None
    debug["failureStage"] = "接口请求成功，拿到了商品列表，但没有一条命中'soybean'+'meal'关键词"
    debug["actualCommodityNamesSeen"] = sorted(set((item.get("commodityName") or "") for item in data))[:50]
    debug["totalCommoditiesReturned"] = len(data)
    return None, debug


def get_psd_attribute_names():
    """
    获取 attributeId → 属性名称 的对照表。
    真实部署后发现：PSD接口返回的数据行里只有数字的 attributeId（比如7），
    没有人类可读的 attributeName 字符串，所以需要额外查一次"属性名称对照表"接口。
    接口的确切路径没有100%确认（USDA没有给出完整的可交互文档），
    这里按最可能的几种命名尝试，只要有一个成功就用哪个。
    """
    candidate_paths = [
        f"{USDA_BASE}/psd/commodityAttributes",
        f"{USDA_BASE}/psd/attributes",
        f"{USDA_BASE}/psd/commodityattribute",
    ]
    for path in candidate_paths:
        data, debug = fetch_json_debug(path, headers={"X-Api-Key": USDA_API_KEY})
        if data:
            mapping = {}
            for item in data:
                aid = item.get("attributeId")
                name = item.get("attributeName") or item.get("attributeDesc") or item.get("name")
                if aid is not None and name:
                    mapping[aid] = name
            if mapping:
                return mapping, path
    return None, None


def _parse_psd_rows(rows, attr_map):
    """把一批PSD原始行解析成 {Ending Stocks:.., Production:.., ...} 的字典，
    同时返回这批数据里最新的 (calendarYear, month) 组合，用来判断新鲜度。"""
    has_string_names = any(r.get("attributeName") for r in rows)
    wanted_normalized = {
        "ending stocks": "Ending Stocks",
        "production": "Production",
        "total supply": "Total Supply",
        "domestic consumption": "Domestic Consumption",
    }
    out = {}
    seen_attrs = set()
    latest_vintage = None  # (calendarYear, month) 里最新的一个，代表这批数据最新是哪个月的WASDE修订版本

    for r in rows:
        cy, mo = r.get("calendarYear"), r.get("month")
        if cy and mo:
            vintage = (cy, mo)
            if latest_vintage is None or vintage > latest_vintage:
                latest_vintage = vintage

    if has_string_names:
        for r in rows:
            attr = r.get("attributeName") or r.get("AttributeName") or r.get("attribute_name")
            val = r.get("value") if "value" in r else r.get("Value")
            if attr is None:
                continue
            seen_attrs.add(attr)
            norm = " ".join(attr.lower().split())
            if norm in wanted_normalized:
                out[wanted_normalized[norm]] = val
    elif attr_map:
        rows_sorted = sorted(rows, key=lambda r: (r.get("calendarYear") or "", r.get("month") or ""))
        latest_by_attr = {}
        for r in rows_sorted:
            aid = r.get("attributeId")
            if aid is not None:
                latest_by_attr[aid] = r
        for aid, r in latest_by_attr.items():
            name = attr_map.get(aid)
            if not name:
                continue
            seen_attrs.add(f"{aid}:{name}")
            norm = " ".join(name.lower().split())
            if norm in wanted_normalized:
                out[wanted_normalized[norm]] = r.get("value")
    else:
        seen_attrs = {f"attributeId={r.get('attributeId')}" for r in rows}

    return out, seen_attrs, has_string_names, latest_vintage


def fetch_psd_supply_demand():
    code, code_lookup_debug = get_soybean_meal_psd_code()
    if not code:
        return {
            "available": False,
            "reason": "未能找到豆粕的PSD商品编码",
            "debug": code_lookup_debug,
        }

    attr_map, attr_map_source = get_psd_attribute_names()

    # ★ 同样的教训：不再猜哪个"year"参数值对应当前活跃的市场年度，
    #   而是同时试几个候选年份，用每批数据里真实出现的"最新WASDE修订月份"来判断哪个最新。
    now_year = datetime.now(timezone.utc).year
    candidate_years = [now_year - 1, now_year, now_year + 1]
    best = None  # {"year":, "rows":, "out":, "seen_attrs":, "has_string_names":, "vintage":}
    all_attempts = {}

    for candidate_year in candidate_years:
        url = f"{USDA_BASE}/psd/commodity/{code}/country/US/year/{candidate_year}"
        rows, debug = fetch_json_debug(url, headers={"X-Api-Key": USDA_API_KEY})
        all_attempts[str(candidate_year)] = {
            "httpStatus": debug.get("httpStatus"),
            "rowCount": len(rows) if rows else 0,
        }
        if not rows:
            continue
        out, seen_attrs, has_string_names, vintage = _parse_psd_rows(rows, attr_map)
        all_attempts[str(candidate_year)]["latestVintage"] = vintage
        candidate = {
            "year": candidate_year, "rows": rows, "out": out,
            "seen_attrs": seen_attrs, "has_string_names": has_string_names, "vintage": vintage,
        }
        # 优先选"有实际匹配到数值"且"vintage最新"的候选；vintage为None时排到最后
        if best is None:
            best = candidate
        else:
            best_sort_key = (bool(best["out"]), best["vintage"] or ("", ""))
            cand_sort_key = (bool(out), vintage or ("", ""))
            if cand_sort_key > best_sort_key:
                best = candidate

    if best is None:
        return {
            "available": False,
            "reason": "PSD接口无返回数据（已尝试" + "、".join(str(y) for y in candidate_years) + "这几个候选年份）",
            "debug": all_attempts,
        }

    year = best["year"]
    out = best["out"]
    seen_attrs = best["seen_attrs"]
    has_string_names = best["has_string_names"]
    vintage = best["vintage"]

    result = {
        "available": True,
        "marketYear": year,
        "wasdeVintage": f"{vintage[0]}年{vintage[1]}月版" if vintage else "未知",
        "endingStocks": out.get("Ending Stocks"),
        "production": out.get("Production"),
        "totalSupply": out.get("Total Supply"),
        "domesticConsumption": out.get("Domestic Consumption"),
        "source": "USDA-FAS PSD API (WASDE同源数据)",
        "sourceUrl": "https://apps.fas.usda.gov/psdonline/",
    }

    # 如果四个关键字段一个都没匹配上，说明还是没能正确识别，
    # 把实际收到的信息列出来，方便直接看出真实情况是什么，不用去翻原始接口。
    if not out:
        if has_string_names:
            warning = "已连接上接口并拿到数据，但字段名一个都没匹配上，可能是接口实际用的attributeName和预期不同"
        else:
            warning = "接口返回的是数字attributeId而不是字符串名称，且未能成功获取attributeId对照表（这个对照表接口的确切路径尚未100%确认）"
        result["debug"] = {
            "warning": warning,
            "actualAttributeNamesSeen": sorted(str(a) for a in seen_attrs)[:30],
            "sampleRawRow": best["rows"][0] if best["rows"] else None,
            "allCandidateYearsAttempted": all_attempts,
        }

    return result


# ---------------------------------------------------------------------------
# 3. CBOT 豆粕期货价格（Yahoo Finance 非官方接口，免注册）
# ---------------------------------------------------------------------------
def fetch_cbot_price():
    # ZM=F 是 CBOT 豆粕期货代码；这个 chart 接口是非官方但被广泛使用
    url = "https://query1.finance.yahoo.com/v8/finance/chart/ZM=F?interval=1d&range=5d"
    data, debug = fetch_json_debug(url, headers={"User-Agent": "Mozilla/5.0"})
    if not data:
        return {"available": False, "reason": "Yahoo Finance接口无返回（可能被限流或接口变更）", "debug": debug}

    try:
        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        timestamps = result["timestamp"]
        # 过滤掉 None（非交易日）
        pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
        if len(pairs) < 2:
            return {"available": False, "reason": "价格数据点不足", "debug": {"note": f"只拿到{len(pairs)}个有效数据点", "sampleRawRow": data}}
        latest_ts, latest_close = pairs[-1]
        prev_ts, prev_close = pairs[-2]
        change = round(latest_close - prev_close, 2)
        change_pct = round(change / prev_close * 100, 2)
        return {
            "available": True,
            "price": round(latest_close, 2),
            "change": change,
            "changePct": change_pct,
            "asOf": datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat(),
            "source": "Yahoo Finance (非官方接口，仅供参考)",
        }
    except (KeyError, IndexError, TypeError) as e:
        return {"available": False, "reason": f"数据解析失败: {e}", "debug": {"note": "接口返回的JSON结构和预期不一致", "sampleRawRow": data}}


# ---------------------------------------------------------------------------
# 4. 美国干旱监测 (US Drought Monitor) —— 真正的官方干旱等级数据
#    区别于天气预报推算的"风险"，这是 NDMC/USDA/NOAA 每周四联合发布的
#    实测干旱分级 (D0-D4)，网页端(index.html)里天气板块用降雨预报算的是
#    "风险倾向"，这里补的是"官方实际认定的干旱状态"。
# ---------------------------------------------------------------------------
# 州名用两字母缩写做显示/内部key，但查询接口的aoi参数官方文档明确要求"两位数FIPS代码"
# （之前的bug就在这里：用了邮政缩写"IA"当aoi值，接口返回200+空数组，因为查无此州）
DROUGHT_STATES = ["IA", "IL", "MN"]  # 爱荷华/伊利诺伊/明尼苏达，豆粕主产区
DROUGHT_STATE_FIPS = {"IA": "19", "IL": "17", "MN": "27"}  # 官方文档：droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx


def fetch_drought_monitor():
    from datetime import timedelta

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=14)  # 拉两周，确保能覆盖最近一次周四更新

    out = {}
    debugs = {}
    for state in DROUGHT_STATES:
        fips = DROUGHT_STATE_FIPS[state]
        url = (
            "https://usdmdataservices.unl.edu/api/StateStatistics/"
            f"GetDroughtSeverityStatisticsByArea?aoi={fips}"
            f"&startdate={start.strftime('%-m/%-d/%Y')}&enddate={end.strftime('%-m/%-d/%Y')}"
            "&statisticsType=1"
        )
        rows, debug = fetch_json_debug(url, headers={"Accept": "application/json"})
        if rows:
            debug["sampleRawRow"] = rows[0]
            debug["totalRowsReturned"] = len(rows)
        debugs[state] = debug
        if not rows:
            out[state] = {"available": False}
            continue
        # 取最新一条记录
        rows_sorted = sorted(rows, key=lambda r: r.get("ValidStart") or r.get("validStart") or "")
        latest = rows_sorted[-1]

        def g(*keys):
            for k in keys:
                if k in latest and latest[k] is not None:
                    return latest[k]
            return None

        # ★ 已确认修复（感谢实测原始数据核实）：
        # d0/d1/d2/d3/d4 不是百分比，是"平方英里"的原始面积！
        # 证据：爱荷华 none(37534.63) + d0(18776.87) = 56311.5 ≈ 爱荷华全州面积(56273平方英里)
        # 说明"none"代表无干旱区域面积，"d0"代表D0及以上(至少轻度干旱)的区域面积，
        # 两者相加 = 全州面积。真正的百分比 = 各等级面积 ÷ (none+d0) × 100
        none_area = g("none", "None", "NONE")
        d0_area, d1_area = g("D0", "d0"), g("D1", "d1")
        d2_area = g("D2", "d2") or 0
        d3_area = g("D3", "d3") or 0
        d4_area = g("D4", "d4") or 0

        if none_area is not None and d0_area is not None and (none_area + d0_area) > 0:
            total_area = none_area + d0_area
            d0 = round(d0_area / total_area * 100, 2)
            d1 = round(d1_area / total_area * 100, 2) if d1_area is not None else None
            d2 = round(d2_area / total_area * 100, 2)
            d3 = round(d3_area / total_area * 100, 2)
            d4 = round(d4_area / total_area * 100, 2)
            d2_plus = d2 + d3 + d4
            is_anomalous = False
        else:
            # 拿不到 none 字段时没法换算，保留原始数值但标记异常，不能装作换算成功了
            d0, d1, d2, d3, d4 = d0_area, d1_area, d2_area, d3_area, d4_area
            d2_plus = (d2 or 0) + (d3 or 0) + (d4 or 0)
            is_anomalous = True
            debugs[state]["anomalyWarning"] = "找不到'none'字段，无法换算成百分比（需要 none+d0=全州面积 这个关系式来计算）"

        out[state] = {
            "available": True,
            "anomalous": is_anomalous,
            "validDate": g("ValidStart", "validStart", "MapDate", "mapDate"),
            "d0": d0,
            "d1": d1,
            "d2": d2,
            "d3": d3,
            "d4": d4,
            "severeOrWorsePct": round(d2_plus, 1),
        }

    available_states = {k: v for k, v in out.items() if v.get("available")}
    if not available_states:
        return {"available": False, "reason": "USDM接口未返回任何州的数据", "debug": debugs}

    avg_severe = sum(v["severeOrWorsePct"] for v in available_states.values()) / len(available_states)
    any_anomalous = any(v.get("anomalous") for v in available_states.values())

    return {
        "available": True,
        "anomalous": any_anomalous,
        "byState": out,
        "avgSevereOrWorsePct": round(avg_severe, 1),
        "source": "US Drought Monitor (NDMC/USDA/NOAA联合发布)",
        "sourceUrl": "https://droughtmonitor.unl.edu/",
        # 不管本次是否异常，都附上原始样本方便随时核对，不用等到下次出问题才临时加诊断
        "debug": debugs,
    }


# ---------------------------------------------------------------------------
# 中国大豆进口量：UN Comtrade 官方API（免费注册，每天500次额度）
# ---------------------------------------------------------------------------
CHINA_REPORTER_CODE = "156"  # UN Comtrade 国家代码：中国
SOYBEAN_HS_CODE = "1201"      # HS编码：大豆


def fetch_china_soybean_imports_comtrade():
    """从UN Comtrade官方API拿中国大豆月度进口量。这是真正的官方国际贸易统计数据，不是AI搜索。

    ★ 已修复：实测报错"Maximum number of periods for preview is 1"，
      说明免费的/public/v1/preview/端点一次只能查1个月份，不能像之前那样
      12个月份逗号拼一起查。现在改成从最近的候选月份开始，一个一个单独查，
      查到第一个有数据的就停（用query loop而不是combined query）。"""
    now = datetime.now(timezone.utc)
    periods = []
    for months_back in range(1, 14):
        y, m = now.year, now.month - months_back
        while m <= 0:
            m += 12
            y -= 1
        periods.append(f"{y}{m:02d}")

    all_attempts = {}
    for period in periods:
        url = (
            f"https://comtradeapi.un.org/public/v1/preview/C/M/HS"
            f"?reporterCode={CHINA_REPORTER_CODE}&period={period}"
            f"&partnerCode=0&cmdCode={SOYBEAN_HS_CODE}&flowCode=M"
        )
        data, debug = fetch_json_debug(url)
        rows = data.get("data") if isinstance(data, dict) else data
        all_attempts[period] = {
            "httpStatus": debug.get("httpStatus"),
            "error": debug.get("error"),
            "rowCount": len(rows) if rows else 0,
        }
        if not rows:
            continue

        latest = rows[0]
        net_weight_kg = latest.get("netWgt") or latest.get("qty")
        if net_weight_kg is None:
            all_attempts[period]["note"] = "有数据但找不到重量字段"
            continue

        wan_tons = round(net_weight_kg / 1000 / 10000, 1)  # 公斤→吨→万吨
        return {
            "available": True,
            "period": f"{period[:4]}年{period[4:]}月",
            "importsWanTons": wan_tons,
            "source": "UN Comtrade（联合国贸易统计数据库，官方数据，preview端点，通常有发布滞后）",
            "sourceUrl": "https://comtradeplus.un.org/",
        }

    return {
        "available": False,
        "reason": f"UN Comtrade对{periods[0]}~{periods[-1]}这些月份逐个查询都没有数据",
        "debug": {"periodsAttempted": all_attempts, "note": "已改为逐月单独查询(preview端点限制一次只能查1个月)"},
    }


# ---------------------------------------------------------------------------
# 本周到港预报（推算）：USDA/AMS 谷物出口检验数据 + 分港口海运时间推算
# ---------------------------------------------------------------------------
GRAIN_INSPECTIONS_URL = "https://agtransport.usda.gov/resource/sruw-w49i.json"

# 用户确认：按港口分别计算海运天数（比统一按30天更精确）
PORT_TRANSIT_DAYS = {
    "gulf": 35,     # 墨西哥湾港口 → 中国，约35天
    "pnw": 18,      # 西北太平洋港口(太平洋西北) → 中国，约18天
}


def fetch_arrival_estimate():
    """
    推算逻辑：这周从美国装船"发往中国"的大豆，还在海上，
    要过几周才会真正到港。所以反过来推：
    "N周前从湾区装船的量" + "M周前从西北太平洋装船的量"
    ≈ "这周大约会到港的量"（N=35天≈5周，M=18天≈2.5周）

    这是推算/估计方法，不是直接测量，前端会标注清楚。
    """
    from datetime import timedelta

    debug = {"url": GRAIN_INSPECTIONS_URL}
    # 拉最近70天的检验数据，足够覆盖两种港口的推算窗口
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=70)
    # ★ 已修复：之前猜测的字段名"inspection_date"不存在，实测报错
    #   "No such column: inspection_date"，报错信息里显示真实字段是"date"开头。
    #   为避免再猜错其他字段名导致SoQL查询报错，这里不在$where里做日期筛选，
    #   而是直接按"date"降序拉最近一批数据，日期范围筛选放到Python这边做，更安全。
    # ★ 再次修复URL编码问题：上次修的是$where里的空格，这次重写查询时又在
    #   "$order=date DESC"里引入了同样的问题(DESC前面的空格没编码)。
    #   这次统一用urllib.parse.quote处理整个参数值，避免再犯同类错误。
    import urllib.parse
    order_param = urllib.parse.quote("date DESC")
    query_url = f"{GRAIN_INSPECTIONS_URL}?$order={order_param}&$limit=3000"
    rows, fetch_debug = fetch_json_debug(query_url)
    debug.update(fetch_debug)
    if not rows:
        return {"available": False, "reason": "USDA谷物出口检验接口无返回数据", "debug": debug}

    debug["totalRowsReturned"] = len(rows)
    debug["sampleRawRow"] = rows[0] if rows else None

    # ★ 已用真实原始数据确认字段名（之前全是猜测）：
    #   数量字段是"mt"（字符串形式的metric tons，不是quantity/metric_tons这些猜测名）
    #   commodity字段确认是"grain"（值形如"SOYBEANS"），destination确认就是"destination"
    #   port字段存在，但实测很多记录是"INTERIOR"（内陆装运点），没法直接判断走哪个海岸，
    #   所以改用"state"（发货州）作为湾区/西北太平洋的主要判断依据，port作为辅助信号。
    GULF_STATES = {"ia","il","in","mo","ks","ne","oh","ky","tn","ar","la","ms","tx","mn","wi","sd","nd"}
    PNW_STATES = {"wa","or","id","mt"}

    def parse_row(r):
        commodity = (r.get("grain") or r.get("commodity") or "").lower()
        destination = (r.get("destination") or r.get("country") or "").lower()
        port_field = (r.get("port") or r.get("port_region") or "").lower()
        state = (r.get("state") or "").lower()
        date_str = r.get("date") or r.get("cert_date") or r.get("week_ending")
        qty_raw = r.get("mt") or r.get("quantity") or r.get("metric_tons")
        try:
            qty = float(qty_raw) if qty_raw is not None else None
        except (ValueError, TypeError):
            qty = None
        return commodity, destination, port_field, state, date_str, qty

    def is_gulf(port_field, state):
        if any(k in port_field for k in ["gulf", "new orleans", "louisiana", "mississippi"]):
            return True
        return state in GULF_STATES

    def is_pnw(port_field, state):
        if any(k in port_field for k in ["pnw", "pacific northwest", "portland", "seattle", "tacoma", "columbia"]):
            return True
        return state in PNW_STATES

    gulf_target_date = end - timedelta(days=PORT_TRANSIT_DAYS["gulf"])
    pnw_target_date = end - timedelta(days=PORT_TRANSIT_DAYS["pnw"])

    gulf_total, pnw_total = 0, 0
    matched_rows = 0
    all_field_names_seen = set()
    for r in rows:
        all_field_names_seen.update(r.keys())
        commodity, destination, port_field, state, date_str, qty = parse_row(r)
        if not date_str:
            continue
        try:
            row_date = datetime.fromisoformat(str(date_str).replace("Z", "")[:10]).date()
        except (ValueError, TypeError):
            continue
        if row_date < start or row_date > end:
            continue  # 日期筛选放这里做，而不是在SoQL的$where里
        if "soybean" not in commodity or "china" not in destination or qty is None:
            continue
        matched_rows += 1
        # 落在湾区推算窗口(±3天容差，因为检验不是每天都有)附近 且 确实是湾区相关(港口名或发货州)
        if is_gulf(port_field, state) and abs((row_date - gulf_target_date).days) <= 3:
            gulf_total += qty
        elif is_pnw(port_field, state) and abs((row_date - pnw_target_date).days) <= 3:
            pnw_total += qty

    debug["matchedSoybeanChinaRows"] = matched_rows
    debug["allFieldNamesSeenInData"] = sorted(all_field_names_seen)
    if matched_rows == 0:
        debug["warning"] = "没有匹配到'大豆+发往中国'的记录，请核对上面allFieldNamesSeenInData列出的真实字段名"
        return {"available": False, "reason": "未能从检验数据中匹配到大豆发往中国的记录", "debug": debug}

    total_metric_tons = gulf_total + pnw_total
    wan_tons = round(total_metric_tons / 10000, 1)

    return {
        "available": True,
        "estimatedWanTons": wan_tons,
        "gulfPortionMetricTons": gulf_total,
        "pnwPortionMetricTons": pnw_total,
        "methodology": f"湾区港口约{PORT_TRANSIT_DAYS['gulf']}天海运+西北太平洋港口约{PORT_TRANSIT_DAYS['pnw']}天海运，"
                       f"按此反推{gulf_target_date}(湾区)和{pnw_target_date}(西北太平洋)前后装船量",
        "source": "USDA/AMS 谷物出口检验数据（推算值，非直接测量）",
        "sourceUrl": "https://agtransport.usda.gov/",
        "debug": debug if matched_rows < 5 else None,  # 匹配数太少时也把诊断带上，方便核对
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    if not USDA_API_KEY:
        print(
            "[WARN] 未设置 USDA_API_KEY 环境变量，USDA相关数据将标记为不可用。\n"
            "       请到 https://api.data.gov/signup/ 免费申请，"
            "并在 GitHub 仓库 Settings → Secrets 里添加 USDA_API_KEY。",
            file=sys.stderr,
        )
    if not GROQ_API_KEY or not TAVILY_API_KEY:
        print(
            "[WARN] 未设置 GROQ_API_KEY / TAVILY_API_KEY，AI辅助搜索的5个指标（库存/猪粮比/"
            "能繁母猪/基差/开机率）将标记为不可用。\n"
            "       Groq密钥：console.groq.com（官方免费开发者层）\n"
            "       Tavily密钥：tavily.com（官方免费层，每月1000次）",
            file=sys.stderr,
        )
    # 注：UN Comtrade已改用/public/v1/preview/免费端点，不再需要UNCOMTRADE_API_KEY

    no_usda_key = {"available": False, "reason": "缺少 USDA_API_KEY"}
    no_ai_key = {"available": False, "reason": "缺少 GROQ_API_KEY 或 TAVILY_API_KEY"}

    result = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "cbotPrice": fetch_cbot_price(),
        "droughtMonitor": fetch_drought_monitor(),
        "exportSales": fetch_esr_export_sales() if USDA_API_KEY else no_usda_key,
        "supplyDemand": fetch_psd_supply_demand() if USDA_API_KEY else no_usda_key,
        "chinaImportsOfficial": fetch_china_soybean_imports_comtrade(),
        "arrivalEstimate": fetch_arrival_estimate(),
        # 以下5个是AI辅助搜索的指标（用户确认可以直接自动同步的部分）
        "soymealStock": fetch_soymeal_stock_ai() if (GROQ_API_KEY and TAVILY_API_KEY) else no_ai_key,
        "hogGrainRatio": fetch_hog_grain_ratio_ai() if (GROQ_API_KEY and TAVILY_API_KEY) else no_ai_key,
        "breedingSows": fetch_breeding_sows_ai() if (GROQ_API_KEY and TAVILY_API_KEY) else no_ai_key,
        "spotBasis": fetch_spot_basis_ai() if (GROQ_API_KEY and TAVILY_API_KEY) else no_ai_key,
        "crushRate": fetch_crush_rate_ai() if (GROQ_API_KEY and TAVILY_API_KEY) else no_ai_key,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] 数据已写入 {OUTPUT_PATH}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
