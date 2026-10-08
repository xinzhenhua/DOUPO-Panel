# -*- coding: utf-8 -*-
"""现货基差的分位只在"当前主力合约"自己的历史里算(v101.9)。运行：python3 test_same_contract_basis.py
★为什么：基差 = 现货 − 主力合约结算价。主力是5月/1月合约时基差天然很大(2023-11 换到5月合约，基差一天内从118跳到553)，主力是9月合约时接近0。
  旧规则"正数偏多、负数偏空"在主力为5月/1月时几乎永远偏多；把所有合约混在一起算分位也一样会被合约月份污染。
  用户规定(2026-10-08)：现货基差以及所有换月造成的断层，都只看当前合约内部的分位。
★计算：只拿 x.dom 和当前主力相同的点(大小写不敏感)，剔除当天自己；该合约样本不足 min_n(20) 时不给分位——换月后约一个月内这一票缺席(诚实标出)，不退回混合分位。"""
import os, sys, tempfile, shutil, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_store as hs

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


def pts(dom, start_i, n, base, step, day0=1):
    """n 个点：日期用 2026-01-01 起顺延的递增天数(只为唯一)，值 base+step*i"""
    from datetime import date, timedelta
    out = []
    for i in range(n):
        d = (date(2025, 1, 1) + timedelta(days=start_i + i)).isoformat()
        out.append({"d": d, "v": base + step * i, "x": {"dom": dom, "sp": 1.0, "dp": 1.0}})
    return out


A = pts("m2605", 0, 30, 300, 5)          # 5月合约：300..445
B = pts("m2609", 40, 30, -50, 3)         # 9月合约：-50..37


def test_percentile_uses_only_the_current_contracts_own_history():
    cur_d = "2025-03-20"                  # 不在 A/B 日期里(B 最晚 2025-03-11 前后)，单独的当天点
    s = hs.summarize_same_contract(A + B, 40, cur_d, "m2609")
    # B 的 30 个点全部 < 40(最大 37) → 100.0。若错把两个合约混在一起：40 只大于 B 的 30 个，A 的 30 个都更大 → 50.0
    assert s["n"] == 30 and s["percentile"] == 100.0, s
    assert s["contract"] == "m2609" and s["min"] == -50 and s["max"] == 37 and s["median"] == -6.5, s
    s2 = hs.summarize_same_contract(A + B, 460, cur_d, "m2605")
    assert s2["n"] == 30 and s2["percentile"] == 100.0, s2        # 460 比 A 的最大值 445 还大；B 里再低的值都不影响它
    ok("★只在同一合约内算分位：9月合约的40在自己30个点里是100%（混算会得50%）")


def test_ties_use_mid_rank_like_the_rest_of_the_history_module():
    s = hs.summarize_same_contract(A + B, 300, "2025-03-20", "m2605")
    assert s["percentile"] == 1.7, s       # (0 个更小 + 0.5×1 个相等)/30 = 1.67 → 1.7
    ok("并列值按一半计（与 percentile_rank 一致）：300 在 A 里 = 1.7%")


def test_the_current_day_itself_is_never_in_the_reference():
    cur = B[-1]
    s = hs.summarize_same_contract(A + B, cur["v"], cur["d"], "m2609")
    assert s["n"] == 29, s
    ok("参照样本剔除当天自己（不能拿自己跟自己比）")


def test_too_few_points_in_the_contract_gives_no_percentile_and_says_why():
    few = pts("m2701", 100, 19, 10, 1)
    s = hs.summarize_same_contract(A + B + few, 15, "2025-06-01", "m2701")
    assert s["n"] == 19 and s["percentile"] is None and "19" in s["why"] and "20" in s["why"], s
    few20 = pts("m2701", 100, 20, 10, 1)
    s = hs.summarize_same_contract(A + B + few20, 15, "2025-06-01", "m2701")
    assert s["n"] == 20 and s["percentile"] is not None, s          # 恰好 20 个就给
    ok("★边界：该合约样本19个不给分位并说明原因，恰好20个给；不退回混合分位")


def test_the_day_a_new_contract_becomes_dominant_has_no_reference_at_all():
    s = hs.summarize_same_contract(A + B, 53, "2025-09-01", "m2701")
    assert s["n"] == 0 and s["percentile"] is None and s["min"] is None, s
    ok("换月当天：新合约一个历史点都没有 → 无分位、无最小最大，不报错")


def test_points_without_a_contract_label_are_never_counted_for_any_contract():
    legacy = [{"d": "2024-01-0%d" % i, "v": 1000.0 + i} for i in range(1, 9)] + [{"d": "2024-02-01", "v": 5.0, "x": {"sp": 1.0}}]
    s = hs.summarize_same_contract(B + legacy, 40, "2025-03-20", "m2609")
    assert s["n"] == 30 and s["percentile"] == 100.0, s
    ok("没有合约标记的老点（x 里没有 dom）不算任何合约的样本")


def test_contract_code_case_is_ignored_and_a_missing_code_is_reported():
    s = hs.summarize_same_contract(A + B, 40, "2025-03-20", "M2609")
    assert s["n"] == 30 and s["percentile"] == 100.0, s
    for bad in (None, "", "  "):
        z = hs.summarize_same_contract(A + B, 40, "2025-03-20", bad)
        assert z["percentile"] is None and z["n"] == 0 and z["why"], z
    ok("合约代码大小写不敏感（实时抓到的是大写 M2701，回填存的是小写）；没有代码时说明原因")


def test_stored_points_with_upper_case_contract_codes_still_match():
    upper = [dict(p, x=dict(p["x"], dom="M2609")) for p in B]       # 早期实时抓取存的是大写
    s = hs.summarize_same_contract(upper, 40, "2025-03-20", "m2609")
    assert s["n"] == 30 and s["percentile"] == 100.0, s
    mixed = upper[:15] + B[15:]
    assert hs.summarize_same_contract(mixed, 40, "2025-03-20", "M2609")["n"] == 30
    ok("已存的点大小写混用也能匹配到同一合约")


def test_non_numeric_values_are_ignored():
    bad = [{"d": "2025-04-01", "v": None, "x": {"dom": "m2609"}}, {"d": "2025-04-02", "v": "x", "x": {"dom": "m2609"}}]
    s = hs.summarize_same_contract(B + bad, 40, "2025-05-01", "m2609")
    assert s["n"] == 30, s
    ok("非数值点被忽略")


def test_update_and_attach_hangs_the_same_contract_summary_on_the_result():
    d = tempfile.mkdtemp()
    try:
        hs.record_points("spot_basis", A + B, d)
        res = {"spotBasis": {"available": True, "value": 40.0, "date": "2025-03-20", "spot": 3300.0, "domSymbol": "M2609", "domPrice": 3260.0, "siteBasis": 40.0}}
        hs.update_and_attach(res, base_dir=d)
        h = res["spotBasis"]["history"]
        assert h["sameContract"]["contract"] == "M2609".lower() and h["sameContract"]["percentile"] == 100.0 and h["sameContract"]["n"] == 30, h
        assert "percentile" in h, "原来的整体摘要照常保留(只展示，不计分)"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("★接线：update_and_attach 把 sameContract 摘要挂到 spotBasis 的 history 上（整体摘要保留，只展示）")


def test_only_the_spot_basis_series_gets_the_contract_summary():
    d = tempfile.mkdtemp()
    try:
        res = {"spotBasis": {"available": True, "value": 40.0, "date": "2025-03-20", "spot": 3300.0, "domSymbol": "m2609", "domPrice": 3260.0, "siteBasis": 40.0},
               "mysteelBasis": {"available": True, "value": 10.0, "date": "2025-03-20", "city": "日照", "src": "table", "contract": "09"}}
        hs.update_and_attach(res, base_dir=d)
        assert "sameContract" in res["spotBasis"]["history"]
        assert "sameContract" not in (res["mysteelBasis"].get("history") or {}), "停用的 Mysteel 基差不加"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok("只有 spot_basis 带 sameContract")


def test_a_registry_lists_every_series_that_needs_per_contract_treatment():
    """用户要求'所有换月导致的数据问题都这样处理并在后续检查'：登记表里列出每个受换月影响的序列及其处理方式，新增这类序列必须来这里登记。"""
    reg = hs.CONTRACT_ROLL_SERIES
    assert reg["spot_basis"]["method"] == "sameContract", reg
    for k in ("crush_margin_sep", "crush_margin_may", "crush_margin_jan", "term_spread_sep", "term_spread_may", "term_spread_jan"):
        assert reg[k]["method"] == "perContractFile", (k, reg.get(k))
    for k, v in reg.items():
        assert k in hs.SERIES_META or k == "basis", k          # 登记的都是真实存在的序列
        assert v["method"] in ("sameContract", "perContractFile", "retired"), (k, v)
    assert reg["basis"]["method"] == "retired"
    ok("★登记表 CONTRACT_ROLL_SERIES：现货基差=sameContract；榨利/月差按合约分文件；Mysteel 旧基差=retired")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    fails = []
    for t in TESTS:
        try:
            t()
        except Exception:
            fails.append(t.__name__)
            print("❌", t.__name__)
            traceback.print_exc()
    print(f"\n结果：{_pass}项通过，{len(fails)}项失败" + (f"：{fails}" if fails else ""))
    sys.exit(1 if fails else 0)
