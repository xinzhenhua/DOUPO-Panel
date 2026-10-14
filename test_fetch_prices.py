# -*- coding: utf-8 -*-
import fetch_prices as fp

B = lambda c: {"symbol": "M2701", "bars": [{"datetime": "2026-10-12 10:00:00", "close": c}]}


def test_merge_changed():
    out, ch = fp.merge({"updatedAt": "T0", "contracts": {"M01": B(1)}}, {"M01": B(2)}, "T1")
    assert ch and out["updatedAt"] == "T1" and out["contracts"]["M01"] == B(2)


def test_merge_unchanged_keeps_time():
    out, ch = fp.merge({"updatedAt": "T0", "contracts": {"M01": B(1)}}, {"M01": B(1)}, "T1")
    assert not ch and out["updatedAt"] == "T0"


def test_merge_failed_contract_keeps_old():
    out, ch = fp.merge({"updatedAt": "T0", "contracts": {"M01": B(1), "M05": B(5)}}, {"M01": B(2), "M05": None}, "T1")
    assert out["contracts"]["M05"] == B(5) and out["contracts"]["M01"] == B(2)


def test_merge_empty_old():
    out, ch = fp.merge(None, {"M01": B(2)}, "T1")
    assert ch and out["contracts"]["M01"] == B(2)


EM = {"data": {"klines": ["2026-10-14 10:15,3380,3390,3395,3378,1200,4000000", "2026-10-14 10:30,3390,3385,3392,3383,900,3000000", "bad", "2026-10-14 10:45,x,1,2,3,4,5"]}}


def test_parse_em_open_close_order():
    b = fp.parse_em(EM)
    assert len(b) == 2 and b[0] == {"datetime": "2026-10-14 10:15:00", "open": 3380.0, "close": 3390.0, "high": 3395.0, "low": 3378.0, "volume": 1200.0, "hold": None}


def test_parse_em_empty():
    assert fp.parse_em(None) == [] and fp.parse_em({"data": None}) == [] and fp.parse_em({"data": {"klines": None}}) == []


def test_fetch_em_url_and_failure():
    seen = []
    assert len(fp.fetch_em("M2701", opener=lambda u: (seen.append(u), EM)[1])) == 2
    assert "secid=114.m2701" in seen[0] and "klt=15" in seen[0]
    def boom(u): raise OSError("403")
    assert fp.fetch_em("M2701", opener=boom) == []


def test_cross_check():
    a = [{"datetime": "2026-10-14 10:15:00", "close": 3390}, {"datetime": "2026-10-14 10:30:00", "close": 3386}]
    b = fp.parse_em(EM)
    assert fp.cross_check(a, b)["ok"] and fp.cross_check(a, b)["dt"].endswith("10:30:00")
    b[1]["close"] = 3300
    assert not fp.cross_check(a, b)["ok"]
    assert fp.cross_check(a, []) is None and fp.cross_check([{"datetime": "x", "close": 1}], b) is None


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("✅", n)
