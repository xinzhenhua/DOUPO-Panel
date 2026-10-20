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
