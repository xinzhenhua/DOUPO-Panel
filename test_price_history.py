"""价格位置补历史(v101.19)：本合约上市不久(如1月合约只有173根、9月合约11根)时，用其他合约按重叠日比例换算补前面的历史。
期望值手算。"""
import unittest
import price_history as ph


def S(pairs):
    return [(d, c) for d, c in pairs]


class TestExtend(unittest.TestCase):
    OWN = S([("2026-01-03", 12.0), ("2026-01-04", 13.0)])

    def test_extend_with_scaled_donor(self):
        # 重叠日1-03：12/6=2，1-04：13/6.5=2 → 比例2；前史1-01,1-02 = 5×2, 5.5×2 = 10, 11
        donor = S([("2026-01-01", 5.0), ("2026-01-02", 5.5), ("2026-01-03", 6.0), ("2026-01-04", 6.5)])
        r = ph.extend_closes(self.OWN, {"A": donor}, target=260, min_overlap=2)
        self.assertEqual(r["closes"], [10.0, 11.0, 12.0, 13.0])
        self.assertEqual((r["ownCount"], r["extendedCount"], r["donor"]), (2, 2, "A"))

    def test_median_ratio_ignores_outlier(self):
        own = S([("d3", 12.0), ("d4", 12.0), ("d5", 12.0)])
        donor = S([("d1", 5.0), ("d2", 5.0), ("d3", 6.0), ("d4", 6.0), ("d5", 1.2)])   # 比例 2,2,10 → 中位数2
        r = ph.extend_closes(own, {"A": donor}, 260, min_overlap=3)
        self.assertEqual(r["closes"][:2], [10.0, 10.0])

    def test_too_little_overlap_not_used(self):
        donor = S([("2026-01-01", 5.0), ("2026-01-02", 5.5), ("2026-01-03", 6.0)])
        r = ph.extend_closes(self.OWN, {"A": donor}, 260, min_overlap=2)      # 只重叠1天
        self.assertEqual(r["extendedCount"], 0); self.assertEqual(r["closes"], [12.0, 13.0]); self.assertIsNone(r["donor"])

    def test_picks_donor_with_longest_prehistory(self):
        short = S([("2026-01-02", 5.5), ("2026-01-03", 6.0), ("2026-01-04", 6.5)])
        long_ = S([("2026-01-01", 5.0), ("2026-01-02", 5.5), ("2026-01-03", 6.0), ("2026-01-04", 6.5)])
        r = ph.extend_closes(self.OWN, {"short": short, "long": long_}, 260, min_overlap=2)
        self.assertEqual(r["donor"], "long"); self.assertEqual(r["extendedCount"], 2)

    def test_only_dates_before_own_start_are_borrowed(self):
        donor = S([("2026-01-01", 5.0), ("2026-01-03", 6.0), ("2026-01-04", 6.5), ("2026-01-05", 99.0)])
        r = ph.extend_closes(self.OWN, {"A": donor}, 260, min_overlap=2)
        self.assertEqual(r["closes"], [10.0, 12.0, 13.0])         # 1-05 的99不借；1-02没有就没有

    def test_trim_to_target(self):
        own = S([(f"2026-02-{i:02d}", 100.0 + i) for i in range(1, 11)])
        donor = S([(f"2026-01-{i:02d}", 50.0 + i) for i in range(1, 29)] + [(f"2026-02-{i:02d}", (100.0 + i) / 2) for i in range(1, 11)])
        r = ph.extend_closes(own, {"A": donor}, target=15, min_overlap=3)
        self.assertEqual(len(r["closes"]), 15); self.assertEqual(r["extendedCount"], 5); self.assertEqual(r["closes"][:5], [148.0, 150.0, 152.0, 154.0, 156.0])   # 取最近的5个前史日(1-24~1-28)：(50+i)×2

    def test_own_already_enough_no_extension(self):
        own = S([(f"d{i:03d}", float(i)) for i in range(300)])
        r = ph.extend_closes(own, {"A": own}, 260)
        self.assertEqual(len(r["closes"]), 260); self.assertEqual(r["extendedCount"], 0)

    def test_empty_own(self):
        self.assertEqual(ph.extend_closes([], {}, 260)["closes"], [])



class TestBuildPosition(unittest.TestCase):
    def test_build_from_csv_donors_and_live_bars(self):
        import os, tempfile, fetch_data as fd
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "M2601.csv"), "w") as f:       # 老合约：比例2
            f.write("date,open,high,low,close,volume,hold\n")
            for dt, c in [("2026-01-01", 5.0), ("2026-01-02", 5.5), ("2026-01-03", 6.0), ("2026-01-04", 6.5)]:
                f.write(f"{dt},{c},{c},{c},{c},1,1\n")
        with open(os.path.join(d, "M2701.csv"), "w") as f:       # 目标自己的CSV不能当donor(否则自己借自己)
            f.write("date,open,high,low,close,volume,hold\n2026-01-01,1,1,1,1,1,1\n")
        daily = {"jan": {"available": True, "symbol": "M2701", "bars": [{"date": "2026-01-03", "close": 12.0}, {"date": "2026-01-04", "close": 13.0}]}}
        r = fd.build_price_position(daily, d, target=4, min_overlap=2)
        j = r["jan"]
        self.assertEqual(j["closes"], [10.0, 11.0, 12.0, 13.0]); self.assertEqual(j["symbol"], "M2701")
        self.assertEqual((j["ownCount"], j["extendedCount"], j["donor"]), (2, 2, "M2601"))

    def test_unavailable_daily_skipped(self):
        import fetch_data as fd
        self.assertEqual(fd.build_price_position({"jan": {"available": False}}, "/nonexistent"), {})

if __name__ == "__main__":
    unittest.main()
