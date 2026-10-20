# -*- coding: utf-8 -*-
"""ru_stock.py 测试：用 2026-10 用户贴的真实正文/列表样本。python3 test_ru_stock.py"""
import json, os, tempfile, ru_stock as R

S1011 = "一、 库存趋势分析截至2026年10月11日，中国天然橡胶社会库存110.4万吨，环比增加0.8万吨，增幅0.75%。图1 中国天然橡胶社会库存（20261011）中国深色胶社会总库存为74.5万吨，环比增1%。其中青岛现货库存增1%；云南增0.3%；越南10增20%；NR库存小计持平。图2 中国深色天然橡胶社会库存（20261011）中国浅色胶社会总库存为"
S0927 = "一、 库存趋势分析截至2026年9月27日，中国天然橡胶社会库存109.6万吨，环比下降1.3万吨，降幅1.2%。图1 中国天然橡胶社会库存（20260927）中国深色胶社会总库存为73.7万吨，环比下降1.7%。其中青岛现货库存降1.7%；云南增0.3%；越南10增18%；NR库存小计环比降35%。图2 中国深色天然橡胶社会库存（20260927）中国浅色"
S0301 = "一、 库存趋势分析\n截至2026年3月1日，中国天然橡胶社会库存138.3万吨，环比增加1.7万吨，增幅1.21%。中国深色胶社会总库存为93.8万吨，增1.32%。其中青岛现货库存增1.82%；云南增0.11%；越南10持平；NR库存小计降0.38%。中国浅色胶社会总库存为44.5万吨，环比增1%。其中老全乳胶环比降0.42%，3L环比增6.56%，RU库存小计增0.32%"
SNIP = "一、 库存趋势分析 截至2026年10月11日，中国天然橡胶社会库存110.4万吨，环比增加0.8万吨，增幅0.75%。"
ok = 0
def eq(a, b, m=""):
    global ok
    assert a == b, "%s: %r != %r" % (m, a, b); ok += 1

p = R.parse_stock_text(S1011); eq((p["d"], p["stk"], p["dark"], p["light"]), ("2026-10-11", 110.4, 74.5, None), "1011")
s, d, l, calc, w = R.reconcile(p); eq((s, d, l, calc, w), (110.4, 74.5, 35.9, ["light"], ""), "1011 公式算浅色")
p = R.parse_stock_text(S0927); s, d, l, calc, w = R.reconcile(p); eq((p["d"], s, d, l), ("2026-09-27", 109.6, 73.7, 35.9), "0927")
p = R.parse_stock_text(S0301); eq((p["stk"], p["dark"], p["light"]), (138.3, 93.8, 44.5), "0301 三项齐全")
s, d, l, calc, w = R.reconcile(p); eq((calc, w), ([], ""), "0301 对得上不用算")
p = R.parse_stock_text(SNIP); eq((p["d"], p["stk"], p["dark"], p["light"]), ("2026-10-11", 110.4, None, None), "摘要只有总库存")
s, d, l, calc, w = R.reconcile(p); eq((s, d, l, calc), (110.4, None, None, []), "只有总库存不猜")
# 缺深色、有浅色
s, d, l, calc, w = R.reconcile({"stk": 110.4, "dark": None, "light": 35.9}); eq((d, calc), (74.5, ["dark"]), "缺深色")
# 三项对不上：以总为准
s, d, l, calc, w = R.reconcile({"stk": 110.4, "dark": 74.5, "light": 40.0}); eq((l, calc), (35.9, ["light"]), "对不上"); assert "差" in w; ok += 1
# 离谱值丢弃
s, d, l, calc, w = R.reconcile({"stk": 11.04, "dark": 74.5, "light": None}); eq((s, d), (None, 74.5), "总库存超范围当没读到")
# 空白/换行容错
p = R.parse_stock_text("截至2026年 3月 1日，中国天然橡胶社会库存\n 138.3 万吨，中国深色胶社会总库存 为 93.8万吨"); eq((p["d"], p["stk"], p["dark"]), ("2026-03-01", 138.3, 93.8), "空白")
eq(R.title_date("[数据分析]：中国天然橡胶社会库存周数据分析（20261011）"), "2026-10-11", "标题日期")
eq(R.title_date("无日期"), None, "无标题日期")
eq(R.html_to_text("<p>中国<b>深色胶</b>&nbsp;社会总库存为74.5万吨</p><script>var a=1;</script>").replace(" ", "").replace("\xa0", ""), "中国深色胶社会总库存为74.5万吨", "html")

# 列表筛选
items = [{"title": "[数据分析]：中国天然橡胶社会库存周数据分析（20261011）", "publishTime": "2026-10-14 10:43", "url": "u1", "content": SNIP},
         {"title": "[数据分析]：中国天然橡胶社会库存周数据分析（20261011）", "publishTime": "2026-10-14 12:00", "url": "u1b", "content": SNIP},
         {"title": "天然橡胶周评", "publishTime": "2026-10-14 10:00", "url": "x", "content": ""},
         {"title": "中国天然橡胶社会库存周数据分析（无日期）", "publishTime": "2026-10-14 10:00", "url": "y", "content": ""}]
a = R.pick_articles(items); eq(list(a), ["2026-10-11"], "筛选"); eq(a["2026-10-11"]["url"], "u1b", "同日取最晚")

# 全流程（假网络）：正文能取到 → 三项；取不到 → 摘要只有总库存
BODY = {"u1": "<html><body><div>" + S1011.replace("，", "，") + "</div></body></html>", "u2": "<html>" + S0927 + "</html>"}
def fj(url, headers=None, post_data=None):
    lst = [{"title": "[数据分析]：中国天然橡胶社会库存周数据分析（20261011）", "publishTime": "2026-10-14 10:43", "url": "u1", "content": SNIP},
           {"title": "[数据分析]：中国天然橡胶社会库存周数据分析（20260927）", "publishTime": "2026-09-30 08:24", "url": "u2", "content": "截至2026年9月27日，中国天然橡胶社会库存109.6万吨，环比下降1.3万吨"},
           {"title": "[数据分析]：中国天然橡胶社会库存周数据分析（20260920）", "publishTime": "2026-09-23 08:05", "url": "u3", "content": "截至2026年9月20日，中国天然橡胶社会库存111万吨，环比下降1.7万吨"}]
    return ({"resultCode": 0, "total": 3, "dataList": lst}, {})
def ft(url):
    return (BODY.get(url), {})
import datetime
tmp = os.path.join(tempfile.mkdtemp(), "x.json")
store, stats, log = R.run(days=40, out=tmp, fetch_json=fj, fetch_text=ft, today=datetime.date(2026, 10, 20), sleep=0)
eq(stats, {"ok": 3, "fail": 0, "skip": 0, "listFail": 0}, "stats")
eq([(p["d"], p["v"]) for p in store["stk"]], [("2026-09-20", 111.0), ("2026-09-27", 109.6), ("2026-10-11", 110.4)], "stk序列")
eq([(p["d"], p["v"]) for p in store["dark"]], [("2026-09-27", 73.7), ("2026-10-11", 74.5)], "dark 序列（0920 正文取不到，只有总）")
eq([(p["d"], p["v"]) for p in store["light"]], [("2026-09-27", 35.9), ("2026-10-11", 35.9)], "light 由公式算出")
eq(sorted(store["calc"]), ["2026-09-27:light", "2026-10-11:light"], "calc 标记")
saved = json.load(open(tmp, encoding="utf-8")); eq(saved["stk"][-1]["v"], 110.4, "已写文件")
# 再跑一次：已齐全且非算出的会跳过；算出的（calc）会重抓以便正文改版后补真值
store2, st2, _ = R.run(days=40, out=tmp, fetch_json=fj, fetch_text=ft, today=datetime.date(2026, 10, 20), sleep=0)
eq(st2["ok"] + st2["skip"], 3, "二次运行"); eq(len(store2["stk"]), 3, "不重复")
# 接口失败：不抛异常、不覆盖
bad = lambda url, headers=None, post_data=None: (None, {"error": "HTTP 403"})
tmp2 = os.path.join(tempfile.mkdtemp(), "y.json")
st, stt, lg = R.run(days=40, out=tmp2, fetch_json=bad, fetch_text=ft, today=datetime.date(2026, 10, 20), sleep=0)
eq((stt["listFail"], os.path.exists(tmp2)), (1, False), "失败不写文件")
print("test_ru_stock: %d 项通过" % ok)
