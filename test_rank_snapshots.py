"""龙虎榜每日原始数据留档(v101.19)：线上每次抓到的前20名表格，按 合约_日期.json 存一份，幂等、不覆盖。"""
import json, os, tempfile, unittest
import fetch_data as fd

PR = {"M2701": {"available": True, "date": "2026-10-09", "tables": {"netLong": [{"member": "高盛期货", "v": 1}], "netShort": [{"member": "中粮期货", "v": 2}]}, "source": "x"},
      "M2705": {"available": False, "reason": "没数据"},
      "M2709": {"available": True, "date": "", "tables": {}}}


class T(unittest.TestCase):
    def test_saves_available_only_with_date(self):
        d = tempfile.mkdtemp()
        n = fd.save_rank_snapshots(PR, d)
        self.assertEqual(n, 1)
        self.assertEqual(os.listdir(d), ["M2701_20261009.json"])
        j = json.load(open(os.path.join(d, "M2701_20261009.json"), encoding="utf-8"))
        self.assertEqual(j["date"], "2026-10-09"); self.assertEqual(j["tables"]["netLong"][0]["member"], "高盛期货")

    def test_idempotent_never_overwrites(self):
        d = tempfile.mkdtemp()
        fd.save_rank_snapshots(PR, d)
        p = os.path.join(d, "M2701_20261009.json"); open(p, "w").write('{"keep": 1}')
        self.assertEqual(fd.save_rank_snapshots(PR, d), 0)
        self.assertEqual(json.load(open(p)), {"keep": 1})

    def test_bad_input_no_crash(self):
        self.assertEqual(fd.save_rank_snapshots(None, tempfile.mkdtemp()), 0)


if __name__ == "__main__":
    unittest.main()
