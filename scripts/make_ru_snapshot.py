#!/usr/bin/env python3
"""橡胶(RU)历史快照：cockpit/ru_hist.json（换月调整后的 开高低收 用来算信号和历史3月，r = 主连真实收盘价用来显示）。
用法：python3 scripts/make_ru_snapshot.py <QH-Screen 的 adj/RU.csv> <RU-Data 的 main_RU0.csv>
页面还会读 data/ru_live.json（可选，Actions 以后追加最新几天的真实 开高低收），把快照往后接。"""
import json, os, sys
import pandas as pd
adj = pd.read_csv(sys.argv[1], parse_dates=['date']).set_index('date').sort_index()
raw = pd.read_csv(sys.argv[2], parse_dates=['date']).set_index('date').sort_index()
adj = adj[adj.index >= '2013-01-01']
r = raw.close.reindex(adj.index).ffill()
out = {'d': [x.strftime('%Y-%m-%d') for x in adj.index]}
for k, c in (('o', 'O'), ('h', 'H'), ('l', 'L'), ('c', 'C')): out[k] = [round(float(v), 4) for v in adj[c]]
out['r'] = [None if pd.isna(v) else round(float(v), 1) for v in r]
f = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cockpit', 'ru_hist.json')
json.dump(out, open(f, 'w'), separators=(',', ':'))
print(f, len(out['d']), out['d'][0], out['d'][-1], os.path.getsize(f), 'bytes')
