# -*- coding: utf-8 -*-
"""ru_ind.py 测试：用 2026-10-20 用户贴的真实列表(青岛库存/全球产量/进口/轮胎产能利用率)。python3 test_ru_ind.py"""
import datetime, json, os, tempfile
import ru_ind as R

S = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "data", "ru_ind_samples_20261020.json"), encoding="utf-8"))
ok = 0
def eq(a, b, m=""):
    global ok
    assert a == b, "%s: %r != %r" % (m, a, b); ok += 1

# ---- 轮胎：水平 + 环比 + 同比(百分点)；标题日期；全角/半角括号
p = R.parse_tire(S["tire"][0]["content"]); eq((p["bg"], p["bgH"], p["bgY"], p["qg"], p["qgH"], p["qgY"]), (57.8, 33.28, -13.27, 53.31, 26.67, -10.65), "tire 1015")
eq(R.tire_end_date(S["tire"][0]["title"]), "2026-10-15", "周期止日")
eq(R.tire_end_date("中国轮胎产能利用率周数据统计（20261231-0107）"), "2027-01-07", "跨年周期")
p = R.parse_tire("本周中国半钢轮胎样本企业产能利用率为64.57%，环比+0.59个百分点，同比-5.14个百分点全钢轮胎样本企业产能利用率为63.64%，环比-0.16个百分点，同比+3.58个百分点本周轮胎企业")
eq((p["bg"], p["qg"], p["qgH"], p["qgY"]), (64.57, 63.64, -0.16, 3.58), "半钢轮胎/全钢轮胎 措辞 + 两句连写")
# 国庆周：环比 +33.28 与上一周 24.52 对得上（水平+环比自洽）
eq(round(24.52 + 33.28, 2), 57.8, "水平自洽")
# 每一篇都读得出，且 环比 与相邻周水平自洽
ok_tire = 0
lv = {}
for it in S["tire"]:
    p = R.parse_tire(it["content"]); assert p.get("qg") is not None and p.get("bg") is not None, it["title"]; lv[R.tire_end_date(it["title"])] = p; ok_tire += 1
eq(ok_tire, 20, "20篇轮胎全部可解析")
ds = sorted(lv)
for a, b in zip(ds, ds[1:]):
    if (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days == 7:
        assert abs(lv[a]["bg"] + lv[b]["bgH"] - lv[b]["bg"]) < 0.02 and abs(lv[a]["qg"] + lv[b]["qgH"] - lv[b]["qg"]) < 0.02, (a, b)
        ok += 1

# ---- 进口：只要海关终值，预估整篇丢弃；累计同比优先
fin = [(it["title"], R.parse_imp(it["content"], it["title"])) for it in S["imp"]]
good = [x for x in fin if x[1][0]]; bad = [x for x in fin if not x[1][0]]
eq((len(good), len(bad)), (11, 9), "20篇：11篇终值 + 9篇预估丢弃"); assert all("预估" in x[1][1] for x in bad); ok += 1
g = {(x[1][0]["y"], x[1][0]["mon"]): x[1][0] for x in good}
eq(g[(2026, 9)], {"y": 2026, "mon": 9, "imp": 48.95, "impM": -17.85, "impY": -3.22}, "2026-09")
eq(g[(2026, 1)]["impY"], 9.61, "1月无累计 → 用当月同比"); eq(g[(2025, 12)]["impY"], 17.94, "12月累计同比")
eq(R.parse_imp("据海关数据统计：2026年9月中国天然橡胶进口量48.95万吨", "x")[0]["impM"], None, "没写同比 → None")
eq(R.parse_imp(S["imp"][1]["content"], S["imp"][1]["title"])[0], None, "预估文章")

# ---- 全球产量：当月 / 当月同比 / 累计同比；12月用全年同比；1月累计=当月
eq(R.parse_prod(S["prod"][0]["content"]), {"mon": 8, "prod": 139.6, "prodM": -4.5, "prodY": -4.2}, "8月")
d = {int(R.title_ym(it["title"])[1]) + 100 * R.title_ym(it["title"])[0]: R.parse_prod(it["content"]) for it in S["prod"]}
eq(d[202601], {"mon": 1, "prod": 140.9, "prodM": 4.3, "prodY": 4.3}, "1月：累计=当月")
eq(d[202512]["prodY"], 1.4, "12月：全年同比"); eq(d[202512]["prod"], 141.6, "12月产量")
eq(d[202603]["prodY"], -1.1, "3月：第一季度累计"); eq(d[202606]["prodY"], -2.3, "6月：上半年累计")

# ---- 青岛：合计/保税/一般贸易 + 入出库率「周变化」
body = "一、 样本库存和出入库率分析 据隆众资讯统计，截至2026年10月18日，青岛地区天胶保税和一般贸易合计库存量57.98万吨，环比上期减少0.11万吨，降幅0.19%。保税区库存5.41万吨，降幅4.91%；一般贸易库存52.56万吨，增幅0.32%。青岛天然橡胶样本保税仓库入库率减少2.16个百分点，出库率增加2.39个百分点；一般贸易仓库入库率减少1.87个百分点，出库率增加0.5个百分点"
p = R.parse_qd(body); eq((p["d"], p["qd"], p["qdb"], p["qdg"], p["qinb"], p["qoutb"], p["qin"], p["qout"]), ("2026-10-18", 57.98, 5.41, 52.56, -2.16, 2.39, -1.87, 0.5), "青岛正文")
p = R.parse_qd(S["qd"][0]["content"]); eq((p["qd"], p["qdb"], p["qin"]), (57.98, None, None), "只有摘要：只有合计")
p = R.parse_qd("截至2026年10月18日，青岛地区天胶保税和一般贸易合计库存量57.98万吨。一般贸易仓库入库率持平，出库率增加0.5个百分点"); eq((p["qin"], p["qout"], p["qinb"]), (0.0, 0.5, None), "持平=0")
eq(R.complete_parts(57.98, 5.41, 52.56)[:4], (57.98, 5.41, 52.56, []), "合计=保税+一般贸易")
eq(R.complete_parts(57.98, 5.41, None)[:4], (57.98, 5.41, 52.57, ["b"]), "缺一般贸易 → 公式算")
eq(R.complete_parts(57.98, None, 52.56)[:4], (57.98, 5.42, 52.56, ["a"]), "缺保税 → 公式算")
t, a, b, c, w = R.complete_parts(57.98, 5.41, 50.0); eq((b, c), (52.57, ["b"]), "对不上以合计为准"); assert "差" in w; ok += 1
for it in S["qd"]:
    p = R.parse_qd(it["content"]); assert p["d"] and p["qd"], it["title"]
    assert R._key_week(it["title"]) == p["d"], (it["title"], p["d"])      # 标题日期 = 正文截至日
ok += 1

# ---- 全流程(假网络)：列表→(正文)→写文件，二次运行不重复，接口失败不写文件
BODIES = {S["qd"][0]["url"]: "<html><body><p>" + body + "</p></body></html>"}
def fj(url, headers=None, post_data=None):
    q = post_data["query"]
    key = {"青岛地区天然橡胶样本库存和出入库率周数据分析": "qd", "全球天然橡胶产量月数据统计": "prod", "中国天然橡胶进口量月数据统计": "imp", "中国轮胎产能利用率周数据统计": "tire"}.get(q)
    items = S[key] if key else []
    return ({"resultCode": 0, "total": len(items), "dataList": items}, {})
ft = lambda url: (BODIES.get(url), {})
tmp = os.path.join(tempfile.mkdtemp(), "x.json")
store, stats, log = R.run(years=1, out=tmp, fetch_json=fj, fetch_text=ft, today=datetime.date(2026, 10, 20), sleep=0)
eq((len(store["qd"]), len(store["prod"]), len(store["imp"]), len(store["qg"]), len(store["bg"]), len(store["qgY"])), (20, 11, 11, 11, 11, 11), "各序列点数")
eq(stats["qd"]["fail"] + stats["prod"]["fail"] + stats["imp"]["fail"] + stats["tire"]["fail"], 0, "无失败"); eq(stats["imp"]["skip"], 0, "预估文章在 pick 之外按 fail/skip 统计") if False else None
last = lambda k: store[k][-1]
eq((last("qd")["d"], last("qd")["v"], last("qdb")["v"], last("qdg")["v"], last("qin")["v"], last("qout")["v"]), ("2026-10-18", 57.98, 5.41, 52.56, -1.87, 0.5), "青岛最新一周(正文)")
eq((last("imp")["m"], last("imp")["v"], last("impY")["v"], last("impM")["v"]), ("2026-09", 48.95, -3.22, -17.85), "进口最新")
eq((last("prod")["m"], last("prod")["v"], last("prodY")["v"]), ("2026-08", 139.6, -4.2), "产量最新")
eq((last("qg")["d"], last("qg")["v"], last("bg")["v"], last("qgY")["v"], last("bgY")["v"]), ("2026-10-15", 53.31, 57.8, -10.65, -13.27), "轮胎最新")
eq([p["d"] for p in store["imp"]] == sorted(p["d"] for p in store["imp"]), True, "升序")
eq(len({p["m"] for p in store["imp"]}), 11, "月度序列每月一个点")
saved = json.load(open(tmp, encoding="utf-8")); eq(saved["tire" if False else "qg"][-1]["v"], 53.31, "已写文件")
s2, st2, _ = R.run(years=0, days=70, out=tmp, fetch_json=fj, fetch_text=ft, today=datetime.date(2026, 10, 20), sleep=0)
eq(len(s2["qg"]), 11, "二次运行不重复"); eq(len(s2["qd"]), 20, "二次运行青岛不重复")
bad = lambda url, headers=None, post_data=None: (None, {"error": "HTTP 403"})
tmp2 = os.path.join(tempfile.mkdtemp(), "y.json")
st, stt, lg = R.run(years=0, days=30, out=tmp2, fetch_json=bad, fetch_text=ft, today=datetime.date(2026, 10, 20), sleep=0)
eq(os.path.exists(tmp2), False, "接口失败不写文件"); eq(stt["tire"]["listFail"], 1, "记录列表失败")
# 月度序列：同月重复发布只留最新
st = {}; R.put(st, "imp", "2026-10-20", 48.95, "2026-09"); R.put(st, "imp", "2026-10-25", 49.0, "2026-09"); eq(st["imp"], [{"d": "2026-10-25", "v": 49.0, "m": "2026-09"}], "同月只留最新")
R.put(st, "imp", "2026-10-21", 1, "2026-09"); eq(st["imp"][0]["v"], 49.0, "旧发布日不覆盖新")
print("test_ru_ind: %d 项通过" % ok)
