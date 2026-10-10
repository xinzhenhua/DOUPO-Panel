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
_COMMON = {"asof": "2026-10-10", "premium_step": 50, "vat": 0.09, "port_fee": 100, "crush_fee": 150}
# 两个豆源。premium_confirmed=False：升贴水都是待你确认的值(没有历史、没有逐条核实的报价)，页面会照实标出。
ORIGINS = {
    "brazil": dict(_COMMON, label="巴西豆", tariff=0.03, premium_cents=250, premium_confirmed=False,
                   source_note="关税3%(最惠国)、压榨费150(Mysteel)；升贴水250美分取公开报价区间(约220~310)中间偏低，增值税9%、港杂100为经验口径"),
    "us": dict(_COMMON, label="美豆", tariff=0.13, premium_cents=230, premium_confirmed=False,
               source_note="关税13%(3%+10%附加，标普2026-09)；美豆CNF升贴水230美分是占位估计(美湾FOB+海运)，没有核实的报价，请用你的实际报价替换"),
}
PARAMS = ORIGINS["brazil"]      # build()不传params时的默认

# 每个豆粕合约对应的进口船期 → CBOT基准合约 → 升贴水(取用户提供的Mysteel 2026-04-22快照区间中值；未逐条核实)
#   到港压榨时间 ≈ 船期 + 1~2个月：1月合约(12~1月压榨)←10~11月船期；5月合约(3~5月压榨)←2~3月船期；9月合约(7~8月压榨)←6~7月船期。
#   cbot=(月份代码, 相对豆粕合约年份的偏移)。注意：Mysteel备注里的"05/09/01"是连盘豆粕合约，不是CBOT合约。
_SNAP = "Mysteel 2026-04-22快照(使用者提供，未逐条核实)；升贴水波动频繁，两周可变20美分以上"
PLAN = {
    1: {"cbot": ("X", -1), "primary": "us", "origins": {
        "us": {"premium_cents": 280, "ship": "2026年10~11月船期", "note": f"美湾CNF：10月277~281、11月282~283，取中值约280。{_SNAP}"},
        "brazil": {"premium_cents": 240, "ship": "2026年10~11月船期(无报价，借用9月船期)", "note": f"巴西10~11月船期没有报价，借用9月船期X合约240美分，仅作参考。{_SNAP}"}}},
    5: {"cbot": ("H", 0), "primary": "brazil", "origins": {
        "brazil": {"premium_cents": 119, "ship": "2027年2~3月船期", "note": f"巴西2月130~135(中值132.5)、3月100~112(中值106)，平均约119，对CBOT 3月(H)。阿根廷豆没有单独报价。{_SNAP}"},
        "us": None}},
    9: {"cbot": ("N", 0), "primary": None, "origins": {
        "brazil": {"premium_cents": 165, "ship": "2027年6~7月船期(用2026年同月快照类推)", "note": f"巴西2026年6月155、7月175(对N合约)，平均165，拿去类推2027年同月，不确定性大。{_SNAP}"},
        "us": {"premium_cents": 268, "ship": "2027年7月船期(用2026年同月快照类推)", "note": f"美湾2026年7月265~272(对N合约)，取中值268，拿去类推2027年同月，不确定性大。{_SNAP}"}}},
}


def cbot_symbol(contract_month, meal_symbol):
    """豆粕合约 → 成本对应的CBOT美豆基准合约(Yahoo代码)，如 M2701 → ZSX26.CBT(11月合约)。"""
    letter, off = PLAN[contract_month]["cbot"]
    return f"ZS{letter}{int(meal_symbol[1:3]) + off:02d}.CBT"


def params_for(contract_month, origin):
    """合约×豆源的完整参数(ORIGINS里的关税/税费 + PLAN里的升贴水/船期/说明)；该合约这个豆源没有报价则返回None。"""
    o = PLAN[contract_month]["origins"].get(origin)
    if o is None:
        return None
    p = dict(ORIGINS[origin]); p.update(o)
    return p


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
