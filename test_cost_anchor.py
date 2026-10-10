"""成本锚(v101.19)：CBOT美豆×汇率×关税×增值税+港杂 → 到港完税成本；再按压榨公式倒推豆粕理论成本。
期望值全部手算(见各用例注释)，不用被测函数自己的输出当期望。"""
import unittest
import cost_anchor as ca


class TestBeanCost(unittest.TestCase):
    def test_bean_landed_cost_hand_calc(self):
        # (1295+250)=1545美分/蒲 ×0.367437=567.690美元/吨；×6.8=3860.29；×1.03=3976.10；×1.09=4333.95；+100港杂=4433.95
        v = ca.bean_landed_cost(1295, 250, 6.8, 0.03, 0.09, 100)
        self.assertAlmostEqual(v, 4433.95, delta=0.05)

    def test_each_parameter_matters(self):
        base = ca.bean_landed_cost(1295, 250, 6.8, 0.03, 0.09, 100)
        self.assertGreater(ca.bean_landed_cost(1395, 250, 6.8, 0.03, 0.09, 100), base)   # 期价+100美分 → +100×0.367437×6.8×1.03×1.09≈+280.5
        self.assertAlmostEqual(ca.bean_landed_cost(1395, 250, 6.8, 0.03, 0.09, 100) - base, 280.5, delta=0.5)
        self.assertAlmostEqual(ca.bean_landed_cost(1295, 250, 6.8, 0.13, 0.09, 100) - base, 3860.29 * 0.10 * 1.09, delta=0.1)  # 关税3%→13%
        self.assertAlmostEqual(ca.bean_landed_cost(1295, 250, 6.8, 0.03, 0.09, 150) - base, 50, delta=1e-6)               # 港杂只加不乘

    def test_bad_inputs_rejected(self):
        for args in [(0, 250, 6.8, .03, .09, 100), (1295, 250, 0, .03, .09, 100), (None, 250, 6.8, .03, .09, 100)]:
            with self.assertRaises(ValueError):
                ca.bean_landed_cost(*args)


class TestMealCost(unittest.TestCase):
    def test_meal_cost_hand_calc(self):
        # (4433.95+150-8000×0.185)/0.785 = (4583.95-1480)/0.785 = 3103.95/0.785 = 3954.1
        v = ca.meal_theory_cost(4433.95, 8000, 150)
        self.assertAlmostEqual(v, 3954.1, delta=0.1)

    def test_oil_price_lowers_meal_cost(self):
        self.assertLess(ca.meal_theory_cost(4433.95, 9000, 150), ca.meal_theory_cost(4433.95, 8000, 150))


class TestBuild(unittest.TestCase):
    P = dict(premium_cents=250, tariff=0.03, vat=0.09, port_fee=100, crush_fee=150, premium_step=50,
             asof='2026-10-10', source_note='测试参数')

    def test_build_gap_and_sensitivity(self):
        r = ca.build(zs_cents=1295, fx=6.8, meal_price=3400, oil_price=8000, params=self.P)
        self.assertTrue(r['available'])
        self.assertAlmostEqual(r['beanCost'], 4433.95, delta=0.1)   # 输出保留1位小数
        self.assertAlmostEqual(r['mealCost'], 3954.1, delta=0.1)
        # 盘面3400 − 理论3954.1 = −554.1 ；占比 −554.1/3954.1 = −14.0%
        self.assertAlmostEqual(r['gap'], -554.1, delta=0.2)
        self.assertAlmostEqual(r['gapPct'], -14.0, delta=0.1)
        self.assertEqual(r['position'], 'below')
        # 升贴水±50美分：每50美分 → 豆成本变 50×0.367437×6.8×1.03×1.09=140.25，豆粕成本变 140.25/0.785=178.7
        self.assertAlmostEqual(r['mealCostHigh'] - r['mealCost'], 178.7, delta=0.3)
        self.assertAlmostEqual(r['mealCost'] - r['mealCostLow'], 178.7, delta=0.3)

    def test_position_labels(self):
        # 盘面在 [low,high] 区间内 → within；高于high → above
        r = ca.build(1295, 6.8, 3954, 8000, self.P)
        self.assertEqual(r['position'], 'within')
        r = ca.build(1295, 6.8, 4300, 8000, self.P)
        self.assertEqual(r['position'], 'above')

    def test_missing_input_unavailable_not_zero(self):
        for kw in [dict(zs_cents=None), dict(fx=None), dict(meal_price=None), dict(oil_price=None)]:
            a = dict(zs_cents=1295, fx=6.8, meal_price=3400, oil_price=8000, params=self.P); a.update(kw)
            r = ca.build(**a)
            self.assertFalse(r['available']); self.assertTrue(r['reason'])

    def test_params_carry_disclosure(self):
        r = ca.build(1295, 6.8, 3400, 8000, self.P)
        self.assertEqual(r['params']['asof'], '2026-10-10')
        self.assertIn('不是回测过的信号', r['note'])




class TestPlan(unittest.TestCase):
    def test_cbot_symbol_follows_shipping_month(self):
        # 1月豆粕合约：10~11月船期 → CBOT 11月(X)，年份比合约年份早1年；5月合约：2~3月船期 → 3月(H)；9月合约：6~7月船期 → 7月(N)
        self.assertEqual(ca.cbot_symbol(1, "M2701"), "ZSX26.CBT")
        self.assertEqual(ca.cbot_symbol(5, "M2705"), "ZSH27.CBT")
        self.assertEqual(ca.cbot_symbol(9, "M2709"), "ZSN27.CBT")

    def test_primary_origin_per_contract(self):
        self.assertEqual(ca.PLAN[1]["primary"], "us")        # 1月以美豆为主
        self.assertEqual(ca.PLAN[5]["primary"], "brazil")    # 5月以南美(巴西)为主
        self.assertIsNone(ca.PLAN[9]["primary"])             # 9月两者并列

    def test_premiums_from_user_table_midpoints(self):
        # 用户给的Mysteel 2026-04-22快照，取区间中值：
        #  美豆 10月277~281、11月282~283 → 约280；巴西 无10~11月，借9月X 240
        #  巴西 2月130~135(132.5)、3月100~112(106) → 119；巴西 6月155、7月175 → 165；美豆 7月N 265~272 → 268
        self.assertEqual(ca.PLAN[1]["origins"]["us"]["premium_cents"], 280)
        self.assertEqual(ca.PLAN[1]["origins"]["brazil"]["premium_cents"], 240)
        self.assertEqual(ca.PLAN[5]["origins"]["brazil"]["premium_cents"], 119)
        self.assertIsNone(ca.PLAN[5]["origins"]["us"])       # 5月对应船期没有美豆报价，不编
        self.assertEqual(ca.PLAN[9]["origins"]["brazil"]["premium_cents"], 165)
        self.assertEqual(ca.PLAN[9]["origins"]["us"]["premium_cents"], 268)

    def test_tariffs(self):
        self.assertEqual(ca.ORIGINS["brazil"]["tariff"], 0.03)
        self.assertEqual(ca.ORIGINS["us"]["tariff"], 0.13)

    def test_us_cost_hand_calc(self):
        # 美豆: (1295+230)=1525 ×0.367437=560.3415；×6.8=3810.32；×1.13=4305.66；×1.09=4693.15；+100=4793.15
        self.assertAlmostEqual(ca.bean_landed_cost(1295, 230, 6.8, 0.13, 0.09, 100), 4793.15, delta=0.1)

    def test_params_for_merges_origin_and_plan(self):
        p = ca.params_for(1, "us")
        self.assertEqual((p["tariff"], p["premium_cents"], p["premium_confirmed"]), (0.13, 280, False))
        self.assertIn("2026", p["ship"])
        self.assertIsNone(ca.params_for(5, "us"))


class TestMulti(unittest.TestCase):
    CM = {"sep": {"available": False},
          "may": {"available": True, "mealPrice": 3300, "oilPrice": 8000, "mealSymbol": "M2705", "date": "2026-10-09"},
          "jan": {"available": True, "mealPrice": 3400, "oilPrice": 8000, "mealSymbol": "M2701", "date": "2026-10-09"}}

    def test_each_contract_uses_its_own_cbot_and_premium(self):
        import fetch_data as fd
        prices = {"ZSX26.CBT": (1300.0, "2026-10-09"), "ZSH27.CBT": (1330.0, "2026-10-09"), "ZS=F": (1295.0, "2026-10-09")}
        r = fd.build_cost_anchor_multi(self.CM, 6.8, lambda sym: prices.get(sym, (None, "无")))
        self.assertTrue(r["available"]); self.assertEqual(sorted(r["contracts"]), ["jan", "may"])
        j = r["contracts"]["jan"]
        self.assertEqual((j["cbotSymbol"], j["zsExact"], j["zsCents"], j["primary"]), ("ZSX26.CBT", True, 1300.0, "us"))
        self.assertTrue(j["us"]["available"] and j["brazil"]["available"])
        # 美豆 (1300+280)×0.367437×6.8×1.13×1.09+100 = 1580×0.367437=580.55；×6.8=3947.7；×1.13=4460.9；×1.09=4862.4；+100=4962.4
        self.assertAlmostEqual(j["us"]["beanCost"], 4962.4, delta=0.5)
        m = r["contracts"]["may"]
        self.assertEqual((m["cbotSymbol"], m["zsCents"], m["primary"]), ("ZSH27.CBT", 1330.0, "brazil"))
        self.assertFalse(m["us"]["available"]); self.assertIn("没有", m["us"]["reason"])

    def test_fallback_to_front_month_is_flagged(self):
        import fetch_data as fd
        prices = {"ZS=F": (1295.0, "2026-10-09")}
        r = fd.build_cost_anchor_multi(self.CM, 6.8, lambda sym: prices.get(sym, (None, "无")))
        j = r["contracts"]["jan"]
        self.assertFalse(j["zsExact"]); self.assertEqual(j["zsCents"], 1295.0); self.assertIn("近月连续", j["zsNote"])

    def test_no_price_at_all_unavailable(self):
        import fetch_data as fd
        self.assertFalse(fd.build_cost_anchor_multi(self.CM, 6.8, lambda sym: (None, "无"))["available"])


if __name__ == "__main__":
    unittest.main()
