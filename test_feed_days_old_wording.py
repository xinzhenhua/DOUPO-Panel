# -*- coding: utf-8 -*-
"""饲料企业豆粕库存天数：2021年底~2022年初的旧措辞(数值后面没有'天'字、环比写'较前一周')。
4篇真实摘要来自用户2026-10-01贴出的回填报告(failedSamples)——这5篇提取失败，正是报告里2021-12-10→2022-01-21 那个6周缺口的原因。
运行：python3 test_feed_days_old_wording.py"""
import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd

_pass = 0


def ok(m):
    global _pass
    _pass += 1
    print("✅", m)


# (日期, 摘要原文, 期望天数, 期望环比)——原文来自回填报告 failedSamples
OLD = [
    ("2022-01-14", "Mysteel农产品对全国主要地区调查显示，截止到2022年1月14日当周（第2周），国内饲料企业豆粕库存天数（物理库存天数）为10.85，较前一周增加1.33天，增幅13.97%库存天数整体大幅增加本周豆粕市场价格震荡回落，现货价格相对坚挺，基差持续走强在春节备货的推动下，大部分地区饲料企业库存天数明显增加，局部地区", 10.85, 1.33),
    ("2022-01-07", "据Mysteel农产品对全国主要地区调查显示，截止到2022年1月7日当周（第1周），国内饲料企业豆粕库存天数（物理库存天数）为9.52，较前一周减少0.4天，减幅4.04%。", 9.52, -0.4),
    ("2021-12-31", "据Mysteel农产品对全国主要地区调查显示，截止到2021年12月31日当周（第52周），国内饲料企业豆粕库存天数（物理库存天数）为9.92，较前一周增加0.26天，增幅2.67%。", 9.92, 0.26),
    ("2021-12-24", "据Mysteel农产品对全国主要地区调查显示，截止到2021年12月24日当周（第51周），国内饲料企业豆粕库存天数（物理库存天数）为9.66，较前一周减少0.49天，减幅4.83%。", 9.66, -0.49),
]


def test_old_wording_real_samples_now_parse():
    for d, txt, ev, em in OLD:
        r, rej = fd._extract_feed_days(txt)
        assert r is not None, f"{d}: 仍然提取不出(拒绝原因:{rej})"
        assert r["value"] == ev and r["mom"] == em, f"{d}: 期望({ev},{em})，实际({r['value']},{r['mom']})"
    ok("★4篇真实旧措辞摘要(数值无'天'字、'较前一周增加/减少')：天数和环比全部提取正确")


def test_old_wording_does_not_take_percentages_or_other_numbers():
    """陷阱：放宽'没有天字'的匹配时，不能把'增幅13.97%'、'第2周'、'2022年1月14日'、'万吨'当成库存天数。"""
    txt = OLD[0][1]
    r, _ = fd._extract_feed_days(txt)
    assert r["value"] == 10.85, "不能取到13.97(增幅百分比)、2(第2周)、2022、1.33(环比变动量)"
    r2, _ = fd._extract_feed_days("全国饲料企业豆粕库存天数调查，库存天数增幅13.97%，油厂豆粕库存累积至115万吨。")
    assert r2 is None, "只有百分比和万吨、没有库存天数本身：不能硬提取"
    r3, rej3 = fd._extract_feed_days("国内饲料企业豆粕库存天数（物理库存天数）为13.97%，较前一周增加0.4天。")
    assert r3 is None, "'为13.97%'后面紧跟%：不是天数"
    r4, _ = fd._extract_feed_days("国内饲料企业豆粕库存天数（物理库存天数）为115万吨。")
    assert r4 is None, "后面紧跟万吨：不是天数"
    ok("★陷阱：增幅百分比/第N周/年份/变动量/万吨/%结尾的数字，都不会被当成库存天数")


def test_old_wording_value_must_be_plausible():
    r, rej = fd._extract_feed_days("国内饲料企业豆粕库存天数（物理库存天数）为88.5，较前一周增加0.4天。")
    assert r is None and any("超出合理范围" in x for x in rej), "88.5天超出1~30天合理范围，仍然拒绝"
    ok("放宽后仍然过合理范围检查(88.5拒绝)")


def test_new_wording_is_unchanged_by_the_fix():
    """回归：20期真实新措辞(2026-05~09)必须仍然全部正确——放宽不能破坏旧的正确行为。"""
    sys.path.insert(0, "/tmp")
    import test_feed_days as T
    for d, txt, ev, em, ey in T.FEED_REAL:
        r, _ = fd._extract_feed_days(txt)
        assert (r["value"], r["mom"], r["yoy"]) == (ev, em, ey), d
    ok("回归：20期真实新措辞全部仍然正确")


def test_mom_wording_variants_with_the_previous_week():
    for txt, want in (("为9.52，较前一周减少0.4天", -0.4), ("为9.52，较上周增加0.4天", 0.4), ("为9.52，较上一周减少0.4天", -0.4), ("为9.52，较前一周持平", 0.0)):
        r, _ = fd._extract_feed_days("国内饲料企业豆粕库存天数（物理库存天数）" + txt)
        assert r["mom"] == want, (txt, r)
    ok("环比措辞：'较前一周/较上周/较上一周' + 增加/减少/持平")


def test_old_wording_requires_the_wei_structure_and_a_unit_free_plausible_number():
    """★放宽后的两个最容易误取的情形(变异检查发现原测试没覆盖)：
    ①只有变动量没有库存本身('库存天数较前一周增加1.33天')——1.33在1~30的合理范围内，不靠'为'的结构约束就会被当成库存天数；
    ②数值本身合理但单位是万吨/百分号('为9.5万吨'、'为9.5%')——不靠'后面不能紧跟万吨/%'的约束就会被接受。"""
    for txt in ("国内饲料企业豆粕库存天数较前一周增加1.33天。",
                "国内饲料企业豆粕库存天数（物理库存天数）较前一周减少0.4天，减幅4.04%。",
                "国内饲料企业豆粕库存天数调查显示当周（第2周）整体偏高。",
                "饲料企业豆粕库存天数增加至9.5。",
                "国内饲料企业豆粕库存天数（物理库存天数）为9.5万吨。",
                "国内饲料企业豆粕库存天数（物理库存天数）为9.5%。",
                "国内饲料企业豆粕库存天数（物理库存天数）为9.5吨。"):
        r, _ = fd._extract_feed_days(txt)
        assert r is None, f"不该提取出库存天数: {txt!r} -> {r}"
    r, _ = fd._extract_feed_days("国内饲料企业豆粕库存天数（物理库存天数）为9.5，较前一周增加0.4天。")
    assert r and r["value"] == 9.5 and r["mom"] == 0.4, "对照：正常的旧措辞仍然能提取"
    ok("★放宽后的误取防护：只有变动量/第N周/'增加至'/万吨/%/吨，都不会被当成库存天数；正常旧措辞仍可提取")


def test_each_change_marker_word_blocks_on_its_own():
    """变动量的标志词互为冗余(如'较前一周增加'里'较'和'增'都能拦住)——逐个用'只含这一个标志词'的写法验证，免得以后误删其中一个。"""
    for marker, txt in (("较", "国内饲料企业豆粕库存天数较1.33天"), ("增", "国内饲料企业豆粕库存天数增1.33天"), ("减", "国内饲料企业豆粕库存天数减1.33天"),
                        ("升", "国内饲料企业豆粕库存天数升1.33天"), ("降", "国内饲料企业豆粕库存天数降1.33天"), ("涨", "国内饲料企业豆粕库存天数涨1.33天"),
                        ("跌", "国内饲料企业豆粕库存天数跌1.33天"), ("下", "国内饲料企业豆粕库存天数下1.33天"), ("上", "国内饲料企业豆粕库存天数上1.33天"),
                        ("比", "国内饲料企业豆粕库存天数比1.33天"), ("持平", "国内饲料企业豆粕库存天数持平1.33天")):
        assert marker in fd._FEED_CHANGE_MARKERS, marker
        r, rej = fd._extract_feed_days(txt)
        assert r is None, f"只含标志词'{marker}'的变动量写法被当成了库存天数: {txt!r} -> {r}"
    assert set(fd._FEED_CHANGE_MARKERS) == {"比", "较", "增", "减", "升", "降", "涨", "跌", "下", "上", "持平"}
    r, _ = fd._extract_feed_days("国内饲料企业豆粕库存天数7.41天，环比微增0.17天")
    assert r and r["value"] == 7.41, "对照：正常写法(库存天数7.41天)不受影响"
    ok("★11个变动量标志词逐个单独验证(每个词单独出现都能拦住变动量)；正常写法不受影响")


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
