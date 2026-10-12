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


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("✅", n)
