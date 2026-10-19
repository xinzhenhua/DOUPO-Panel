"""fetch_ru.py 合并逻辑测试：python3 tests/test_fetch_ru.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import fetch_ru as F
ok = fail = 0
def eq(n, a, b):
    global ok, fail
    if a == b: ok += 1
    else: fail += 1; print("✗", n, a, b)
rows = [("2026-10-16", 1, 2, 1, 1.5), ("2026-10-19", 10, 12, 9, 11), ("2026-10-20", 11, 13, 10, 12)]
r = F.merge({}, rows, "2026-10-16")
eq("只并入快照之后", r["d"], ["2026-10-19", "2026-10-20"]); eq("收盘", r["c"], [11, 12])
rows2 = [("2026-10-20", 11, 14, 10, 13), ("2026-10-21", 13, 14, 12, 13.5)]
r2 = F.merge(r, rows2, "2026-10-16")
eq("同日覆盖+追加", (r2["d"], r2["c"]), (["2026-10-19", "2026-10-20", "2026-10-21"], [11, 13, 13.5]))
eq("升序", r2["d"], sorted(r2["d"]))
eq("m 沿用", F.merge({"d": ["2026-10-19"], "o": [1], "h": [1], "l": [1], "c": [1], "m": ["2701"]}, rows2, "2026-10-16").get("m"), ["2701", "", ""])
import pandas as pd
df = pd.DataFrame({"日期": ["2026-10-19", "2026-10-20", "2026-10-21"], "开盘价": [1, 0, 3], "最高价": [2, 2, 4], "最低价": [1, 1, 3], "收盘价": [1.5, 1.5, 3.5]})
eq("剔除无效行(开盘=0)", [x[0] for x in F.parse_frame(df)], ["2026-10-19", "2026-10-21"])
print(f"结果：{ok}项通过" + (f"，{fail}项失败" if fail else "")); sys.exit(1 if fail else 0)
