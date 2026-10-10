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


if __name__ == '__main__':
    unittest.main()


class TestWiring(unittest.TestCase):
    def test_build_from_inputs_picks_jan_first(self):
        import fetch_data as fd
        cm = {"sep": {"available": True, "mealPrice": 1, "oilPrice": 1, "mealSymbol": "M2609"},
              "jan": {"available": True, "mealPrice": 3400, "oilPrice": 8000, "mealSymbol": "M2701", "date": "2026-10-09"},
              "may": {"available": False}}
        r = fd.build_cost_anchor_from_inputs(1295, 6.8, cm)
        self.assertTrue(r["available"]); self.assertEqual(r["mealSymbol"], "M2701"); self.assertEqual(r["mealPrice"], 3400)

    def test_no_margin_unavailable(self):
        import fetch_data as fd
        r = fd.build_cost_anchor_from_inputs(1295, 6.8, {"sep": {"available": False}})
        self.assertFalse(r["available"])
