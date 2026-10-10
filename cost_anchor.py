"""成本锚(v101.19)：进口大豆到港完税成本 → 豆粕理论成本，和盘面价对比。

公式(公开口径)：
  豆完税成本(元/吨) = (CBOT美豆期价 + CNF升贴水)[美分/蒲] × 0.367437 × 汇率 × (1+关税) × (1+增值税) + 港杂费
      0.367437 = 36.7437蒲/吨 ÷ 100(美分→美元)
  豆粕理论成本(元/吨) = (豆完税成本 + 压榨费 − 豆油价 × 0.185) ÷ 0.785
      出粕率0.785、出油率0.185与页面榨利卡同口径；豆油价取盘面(含税)。
诚实边界：
  · 升贴水没有历史数据，无法回测，只能是"带日期的参数"，所以结果同时给±premium_step的区间；
  · 关税默认按巴西豆3%(最惠国)；美豆现行总关税13%(3%+10%附加)，需要看美豆时在参数里改；
  · 港杂费、增值税为公开口径的常用经验值，没有逐笔核实，在参数文件里标注并由使用者确认；
  · 这是"成本参照"，不是回测过的买卖信号。
"""
BU_PER_TONNE_FACTOR = 0.367437     # 美分/蒲 → 美元/吨
YIELD_MEAL = 0.785
YIELD_OIL = 0.185

# 参数(每次改动请同步改asof和source_note)。全部是"待使用者确认"的公开口径。
PARAMS = {
    "asof": "2026-10-10",
    "premium_cents": 250,      # 巴西豆CNF升贴水(美分/蒲，对CBOT近月)。公开报价区间约220~310，取中间偏低；无历史、不可回测
    "premium_step": 50,        # 敏感性区间 ±50美分
    "tariff": 0.03,            # 巴西豆最惠国税率3%；美豆现行13%(3%+10%附加)，据2026-09标普报道
    "vat": 0.09,               # 进口大豆增值税9%(公开口径，未逐条核实原文)
    "port_fee": 100,           # 港杂费 元/吨(经验值，未核实)
    "crush_fee": 150,          # 压榨费 元/吨(Mysteel压榨利润跟踪的口径)
    "source_note": "关税/压榨费来自Mysteel与标普公开报道；升贴水、港杂费、增值税为经验口径，请核对后修改本参数",
}


def _need_pos(name, v):
    if v is None or not isinstance(v, (int, float)) or v <= 0:
        raise ValueError(f"{name}必须是正数，收到{v!r}")


def bean_landed_cost(zs_cents, premium_cents, fx, tariff, vat, port_fee):
    _need_pos("美豆期价", zs_cents); _need_pos("汇率", fx)
    usd_t = (zs_cents + premium_cents) * BU_PER_TONNE_FACTOR
    return usd_t * fx * (1 + tariff) * (1 + vat) + port_fee


def meal_theory_cost(bean_cost, oil_price, crush_fee):
    return (bean_cost + crush_fee - oil_price * YIELD_OIL) / YIELD_MEAL


def build(zs_cents, fx, meal_price, oil_price, params=None):
    p = dict(PARAMS if params is None else params)
    for name, v in (("美豆期价", zs_cents), ("汇率", fx), ("豆粕盘面价", meal_price), ("豆油盘面价", oil_price)):
        if v is None or not isinstance(v, (int, float)) or v <= 0:
            return {"available": False, "reason": f"{name}缺失，不用0硬凑，成本锚不计算"}
    args = (fx, p["tariff"], p["vat"], p["port_fee"])
    bean = bean_landed_cost(zs_cents, p["premium_cents"], *args)
    bean_lo = bean_landed_cost(zs_cents, p["premium_cents"] - p["premium_step"], *args)
    bean_hi = bean_landed_cost(zs_cents, p["premium_cents"] + p["premium_step"], *args)
    cost = meal_theory_cost(bean, oil_price, p["crush_fee"])
    lo = meal_theory_cost(bean_lo, oil_price, p["crush_fee"])
    hi = meal_theory_cost(bean_hi, oil_price, p["crush_fee"])
    gap = meal_price - cost
    pos = "below" if meal_price < lo else "above" if meal_price > hi else "within"
    return {
        "available": True, "zsCents": zs_cents, "fx": fx, "mealPrice": meal_price, "oilPrice": oil_price,
        "beanCost": round(bean, 1), "mealCost": round(cost, 1), "mealCostLow": round(lo, 1), "mealCostHigh": round(hi, 1),
        "gap": round(gap, 1), "gapPct": round(gap / cost * 100, 1), "position": pos,
        "params": p,
        "note": "成本参照，不是回测过的信号：升贴水无历史数据无法回测；盘面低于理论成本不等于会涨(压榨利润可为负、成本也会跟着美豆变)。",
    }
