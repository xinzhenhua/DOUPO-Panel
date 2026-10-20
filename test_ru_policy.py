# -*- coding: utf-8 -*-
"""ru_policy 测试：python3 test_ru_policy.py"""
import datetime, os, tempfile
import ru_policy as P
ok = 0
def eq(a, b, m=""):
    global ok
    assert a == b, "%s: %r != %r" % (m, a, b); ok += 1
H = lambda t, c="": P.classify(t, c)[0]
eq(H("泰国、印尼、马来西亚三国联合限制天然橡胶出口"), True, "2016式三国限出口")
eq(H("三国橡胶理事会ITRC部长会议：同意削减出口61.5万吨"), True, "削减出口")
eq(H("泰国宣布暂停橡胶出口"), True)
eq(H("印尼拟对橡胶实施出口配额"), True)
eq(H("泰国取消橡胶出口限制"), False, "放宽不算")
eq(H("[天胶快讯]：泰国橡胶管理局启动一项种植补贴计划"), False, "无限出口动作")
eq(H("天然橡胶社会库存周数据分析"), False)
eq(H("国内橡胶出口退税政策调整"), False, "无主产国词")
eq(H("", ""), False)
# 2026-10-20 回看日志里的真实误报标题（全部应不命中）
for t in ["橡胶基本面支撑犹存", "浙商期货：2月28日建议RU05剩余多单谨慎持有", "“胶胶扰扰”何时休 暗流涌动的橡胶何时再度发力？", "涨幅扩大 胶价反弹还是反转", "沪胶：关注下方11500元/吨支撑", "谨慎看待后市橡胶反弹高度",
          "橡胶期权卖出宽跨式策略盈利机会较大", "沪胶呈现弱势寻底格局", "多空因素交织 沪胶上下两难", "瑞达期货：8月20日沪胶反弹承压 20号胶成交萎缩", "供应增速放缓 沪胶重心预计小幅抬升",
          "[隆众聚焦]：原料“服软”，硬脂酸处境艰难", "[隆众聚焦]：泰国2月份出口天然橡胶对全球及中国同环比双增", "[数据分析]：泰国天然橡胶出口量月数据分析（2026年2月）",
          "[天然橡胶]：由于美国考虑征收反倾销税 泰国轮胎出口美国数量将减少", "[隆众聚焦]：10月印尼天胶出口量三连跌 11月份仍难乐观", "[热点聚焦]：2024年中国促进剂出口有望再创新高", "[热点聚焦]：4月泰国天然橡胶出口环比减少，同比增加"]:
    eq(H(t, "泰国 ITRC 三国 削减出口"), False, t)
eq(H("ITRC决定削减天然橡胶出口", ""), True, "真政策标题"); eq(H("[天胶快讯]：三国同意自3月起限制橡胶出口", ""), True, "快讯式标题"); eq(H("泰国拟对橡胶出口设配额"), True)
eq(H("ITRC：3月起联合禁止橡胶出口6个月"), True, "2016式标题(中橡协)"); eq(H("东南亚橡胶主产国决定减少天然橡胶出口量"), True, "决定+减少+出口"); eq(H("全球限产叠加需求趋旺 天然橡胶业迎景气红利"), False, "仅限产无出口，保守不报")
eq(H("产胶国联合消减出口 橡胶或迎短期上涨红利"), True, "天然橡胶协会式标题"); eq(H("全球三大橡胶生产国限制出口 刺激橡胶价格连续上涨"), True, "生产国+限制出口")
eq(H("供应压力有望缓解 橡胶短多长空节奏不改", "受东南亚主产国计划3月初开始限制天胶出口利好消息的影响"), False, "标题无动作词→不报(已知漏报)")
eq(H("泰国天然橡胶出口量环比减少"), False, "纯数据描述仍不报")
st = {"items": [], "scanned": 0}; today = datetime.date(2027, 3, 20)
its = [{"title": "三国联合限制橡胶出口", "url": "u1", "publishTime": "2027-03-15 10:00:00", "content": ""}, {"title": "三国联合限制橡胶出口", "url": "u1", "publishTime": "2027-03-15 10:00:00"},
       {"title": "泰国橡胶产量预估", "url": "u2", "publishTime": "2027-03-16 10:00:00"}, {"title": "印尼限制橡胶出口（旧）", "url": "u3", "publishTime": "2026-01-01 00:00:00"}]
n = P.merge(st, its, today); eq((n, len(st["items"]), st["scanned"]), (1, 1, 4), "去重+只留120天内")
# run：全部失败不写文件；有数据写文件
d = tempfile.mkdtemp(); out = os.path.join(d, "p.json")
bad = lambda url, headers=None, post_data=None: (None, {"error": "403"})
s, a, w = P.run(days=14, out=out, fetch_json=bad, today=today, sleep=0); eq((w, os.path.exists(out), len(s["errors"])), (False, False, len(P.QUERIES)), "全失败不写")
good = lambda url, headers=None, post_data=None: ({"resultCode": 0, "total": 1, "dataList": [{"title": "泰国限制橡胶出口", "url": "x" + str(post_data["query"]), "publishTime": "2027-03-18 09:00:00", "content": ""}]}, {})
s, a, w = P.run(days=14, out=out, fetch_json=good, today=today, sleep=0); eq((w, os.path.exists(out), len(s["items"])), (True, True, len(P.QUERIES)), "有数据写文件")
print("test_ru_policy: %d 项通过" % ok)
