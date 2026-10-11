// 驾驶舱取数装配的纯函数测试：node tests/test_cockpit_loader.js
const path = require('path'), CL = require(path.join(__dirname, '..', 'cockpit', 'loader.js'));
let pass = 0, fail = 0;
const eq = (n, a, b) => { const ok = JSON.stringify(a) === JSON.stringify(b); ok ? pass++ : (fail++, console.log('❌', n, '\n  实际', JSON.stringify(a), '\n  期望', JSON.stringify(b))); if (ok) console.log('✅', n); };

// ---- CSV ----
eq('parseCsv 带BOM和空行', CL.parseCsv('﻿date,close\n2020-01-02,10\n\n2020-01-03,11\n'), [{ date: '2020-01-02', close: '10' }, { date: '2020-01-03', close: '11' }]);
eq('parseCsv 只有表头→空', CL.parseCsv('date,close\n'), []);
eq('histFromCsv 过滤起始日', CL.histFromCsv('date,close\n2014-01-01,5\n2015-04-03,10\n2015-04-06,11\n', '2015-04-03'), { d: ['2015-04-03', '2015-04-06'], c: [10, 11] });
eq('histFromCsv 跳过非正数/空收盘价', CL.histFromCsv('date,close\n2020-01-02,0\n2020-01-03,\n2020-01-06,12\n', null), { d: ['2020-01-06'], c: [12] });
eq('histFromCsv 乱序+重复日期：升序、后者覆盖', CL.histFromCsv('date,close\n2020-01-03,2\n2020-01-02,1\n2020-01-03,3\n', null), { d: ['2020-01-02', '2020-01-03'], c: [1, 3] });
eq('histFromCsv 空输入', CL.histFromCsv('', null), { d: [], c: [] });

// ---- windowRun：取最近一段推荐月份 ----
const P = (...ds) => ds.map((d, i) => ({ d, v: i }));
eq('windowRun 最近一段(4-7月)，当前在10月', CL.windowRun(P('2026-03-30', '2026-04-01', '2026-05-10', '2026-06-20', '2026-07-31', '2026-10-09'), [4, 5, 6, 7]).map(p => p.d), ['2026-04-01', '2026-05-10', '2026-06-20', '2026-07-31']);
eq('windowRun 两个窗口只取最近', CL.windowRun(P('2025-04-02', '2025-07-30', '2026-04-01', '2026-05-01', '2026-06-01'), [4, 5, 6, 7]).map(p => p.d), ['2026-04-01', '2026-05-01', '2026-06-01']);
eq('windowRun 窗口里间隔>45天就断开', CL.windowRun(P('2026-04-01', '2026-06-20', '2026-07-01'), [4, 5, 6, 7]).map(p => p.d), ['2026-06-20', '2026-07-01']);
eq('windowRun 间隔恰好45天仍连续', CL.windowRun(P('2026-05-01', '2026-06-15'), [4, 5, 6, 7]).map(p => p.d), ['2026-05-01', '2026-06-15']);
eq('windowRun 跨年窗口(12-3月)', CL.windowRun(P('2025-12-01', '2026-01-05', '2026-02-15', '2026-03-31', '2026-10-09'), [12, 1, 2, 3]).map(p => p.d), ['2025-12-01', '2026-01-05', '2026-02-15', '2026-03-31']);
eq('windowRun 没有任何点在窗口→空', CL.windowRun(P('2026-10-01', '2026-10-09'), [4, 5, 6, 7]), []);
eq('windowRun 空输入', CL.windowRun([], [4]), []);

// ---- buildSeries ----
const meta = { stock: { name: '库存' }, esr: { name: '出口' }, basis: { name: '基差', note: 'x' }, margin_sep: { name: '毛利', ctx: 'sep' }, spread_sep: {}, margin_may: {}, spread_may: {}, margin_jan: {}, spread_jan: {}, ustu: {}, gs: {}, cftc: {}, zl: {}, hog: {}, poultry: {}, rm: {}, crush: {}, arrival: {}, import: {}, feed: {}, stu: {} };
const ctx = { sep: { recommendedMonths: [4, 5, 6, 7] }, may: { recommendedMonths: [12, 1, 2, 3] }, jan: { recommendedMonths: [8, 9, 10, 11] } };
const many = n => Array.from({ length: n }, (_, i) => ({ d: '2024-01-' + String(i % 28 + 1).padStart(2, '0'), v: i, x: { dom: 'm2701' } }));
let S = CL.buildSeries(meta, { meal_stock: many(200), us_stocks_to_use: many(30), crush_rate: many(150), soy_import: many(60), spot_basis: many(300) }, ctx);
eq('库存：取最后160个，nTotal=全部', [S.stock.pts.length, S.stock.nTotal, S.stock.pts[0].v], [160, 200, 40]);
eq('美豆库消比：最后10个', [S.ustu.pts.length, S.ustu.nTotal], [10, 30]);
eq('开机率最后140、进口最后40', [S.crush.pts.length, S.import.pts.length], [140, 40]);
eq('基差：160个+说明里写当前合约', [S.basis.pts.length, S.basis.nTotal, S.basis.note.includes('M2701')], [160, 300, true]);
eq('点只保留 d 和 v（不带 x）', Object.keys(S.basis.pts[0]), ['d', 'v']);
eq('没有历史文件的指标：空 pts、nTotal=0', [S.hog.pts, S.hog.nTotal], [[], 0]);
eq('原骨架信息保留', S.stock.name, '库存');
const es = Array.from({ length: 8 }, (_, i) => ({ d: '2026-0' + (i + 1) + '-01', v: (i + 1) * 40000 }));
S = CL.buildSeries(meta, { esr_net_sales: es }, ctx);
eq('出口销售：4周均值/1万，第4个点=(1+2+3+4)*4万/4/1万=10', [S.esr.pts.length, S.esr.pts[0].v, S.esr.pts[0].d, S.esr.nTotal], [5, 10, '2026-04-01', 5]);
S = CL.buildSeries(meta, { esr_net_sales: es.slice(0, 3) }, ctx);
eq('出口销售不足4个点→没有点', [S.esr.pts.length, S.esr.nTotal], [0, 0]);
S = CL.buildSeries(meta, { crush_margin_sep: P('2026-04-01', '2026-05-15', '2026-06-25', '2026-07-31', '2026-10-09'), term_spread_jan: P('2026-10-09') }, ctx);
eq('毛利按合约窗口取：sep 只留4-7月，nTotal=全部5个', [S.margin_sep.pts.map(p => p.d), S.margin_sep.nTotal], [['2026-04-01', '2026-05-15', '2026-06-25', '2026-07-31'], 5]);
eq('月差jan：10月在8-11月窗口内→1个', S.spread_jan.pts.map(p => p.d), ['2026-10-09']);

// ---- systems / basisSame / crush ----
eq('systems：只取带x的点并改名', CL.buildSystems({ systems_sep: [{ d: '2026-10-09', v: -0.75, x: { fundDir: '偏空', fundN: 7 } }, { d: '2026-10-08', v: 0 }] }).sep, [{ d: '2026-10-09', v: -0.75, dir: '偏空', n: 7 }]);
eq('systems 缺文件→空数组', CL.buildSystems({}).jan, []);
eq('basisSame：同合约样本(不含最后一天)', CL.basisSame({ spot_basis: [{ d: '1', x: { dom: 'M2609' } }, { d: '2', x: { dom: 'm2701' } }, { d: '3', x: { dom: 'M2701' } }, { d: '4', x: { dom: 'm2701' } }] }), { contract: 'm2701', n: 2, min: 20 });
eq('basisSame 无数据', CL.basisSame({}), { contract: '', n: 0, min: 20 });
eq('crushFrom', CL.crushFrom({ crushMargins: { sep: { available: true, mealSymbol: 'M2709', mealPrice: 1, oilPrice: 2, beanPrice: 3, date: 'd', extra: 9 } } }).sep, { available: true, mealSymbol: 'M2709', mealPrice: 1, oilPrice: 2, beanPrice: 3, date: 'd' });
eq('crushFrom 缺合约→available:false', CL.crushFrom({}).may, { available: false });

// ---- fill：就地灌入（界面持有旧引用）----
const keep = { a: 1, b: 2 }, ref = keep; CL.fill(keep, { b: 3, c: 4 });
eq('fill 就地：删多余、改旧值、加新键，且是同一个对象', [ref === keep, keep], [true, { b: 3, c: 4 }]);

// ---- assemble ----
const mkState = () => {
  const votes = [{ label: '量价关系(5日)', side: 'structure', signal: 1, weight: 1, baseWeight: 1, q: 1, qwhy: '', note: 'n', group: null, grp: 'g' }, { label: '库存', side: 'supply', signal: -1, weight: 1, baseWeight: 1, q: 1, qwhy: '' }];
  const c = sym => ({ symbol: sym, votes, pure: { ratio: 0 }, structure: { n: 1, direction: '偏多', ratio: 1, thin: false, extra: 1 }, tech: { d: 1 }, confidence: null, dims: {}, vpStatus: 'ok', vpReason: null, bars: Array.from({ length: 200 }, (_, i) => ({ date: '2026-01-01T00:00:00', open: i, high: i + 1, low: i - 1, close: i, volume: 5, hold: 6 })), vpSeq: [], health: { level: 'ok', sync: { label: 's' }, bad: 0, warn: 0, missing: [], rows: [] } });
  return { scoringVersion: 'v100', contracts: { sep: c('M2709'), may: c('M2705'), jan: c('M2701') }, indicators: [{ key: 'crush', inputId: 'm_crush', title: 't', freq: 'f', source: 's', noVote: null, unit: '%', input: '42', badge: 'b' }], events: [{ kind: 'usda', label: 'l', title: 't', ms: 1, extra: 0 }], closure: null };
};
const STATIC = { polarity: { a: 1 }, ctx, series: meta };
const D = CL.assemble({ state: mkState(), latest: { generatedAt: 'G', marketCapital: { z: 1 }, cftcManagedMoney: { history: [] }, pricePosition: { p: 1 }, costAnchor: { c: 1 }, crushMargins: {} }, H: { hog_ratio: [{ d: '2026-10-09', v: 1 }], systems_sep: [{ d: '2026-10-09', v: 0, x: { fundDir: '中性', fundN: 3 } }] }, seasonal: { m: 1 }, histCsv: 'date,close\n2026-01-01,3000\n', now: Date.UTC(2026, 9, 11, 13), STATIC });
eq('assemble：K线只取160根且改名', [D.contracts.sep.kline.length, Object.keys(D.contracts.sep.kline[0])], [160, ['d', 'o', 'h', 'l', 'c', 'v', 'oi']]);
eq('assemble：K线日期截成10位', D.contracts.sep.kline[0].d, '2026-01-01');
eq('assemble：量价票的信号→vp.signal', D.contracts.jan.vp, { status: 'ok', reason: null, signal: 1 });
eq('assemble：structure 只留4个字段', Object.keys(D.contracts.may.structure), ['n', 'direction', 'ratio', 'thin']);
eq('assemble：票只留约定字段', Object.keys(D.contracts.sep.votes[1]), ['label', 'side', 'signal', 'weight', 'baseWeight', 'q', 'qwhy', 'note']);
eq('assemble：基础字段', [D.generatedAt, D.scoring, D.snapshotMs, D.cftcRawHasHistory, D.capital, D.costAnchor], ['G', 'v100', Date.UTC(2026, 9, 11, 13), true, { z: 1 }, { c: 1 }]);
eq('assemble：10月(北京)自动合约=jan，健康度取jan的', D.health.level, 'ok');
eq('assemble：seriesAsOf', D.seriesAsOf, { history: '2026-10-09', systems: '2026-10-09' });
eq('assemble：hist 与 sea', [D.hist, D.sea], [{ d: ['2026-01-01'], c: [3000] }, { m: 1 }]);
eq('assemble：事件只留4字段', Object.keys(D.events[0]), ['kind', 'label', 'title', 'ms']);
eq('assemble：指标带 key 和 inputId', [D.indicators[0].key, D.indicators[0].inputId], ['crush', 'm_crush']);
const D2 = CL.assemble({ state: mkState(), latest: null, H: {}, seasonal: null, histCsv: '', now: Date.UTC(2026, 9, 11, 13), STATIC });
eq('assemble：所有外部文件都缺失也不崩，给空值', [D2.capital, D2.cftc, D2.hist, D2.sea, D2.pricePosition, D2.generatedAt, D2.seriesAsOf], [null, null, { d: [], c: [] }, null, {}, '', { history: '', systems: '' }]);
// 北京时间跨日：UTC 7月31日17:00 = 北京8月1日01:00 → 8月→自动合约 jan(8-11月)
const D3 = CL.assemble({ state: (() => { const s = mkState(); s.contracts.jan.health.level = 'JAN'; s.contracts.sep.health.level = 'SEP'; return s; })(), latest: {}, H: {}, seasonal: null, histCsv: '', now: Date.UTC(2026, 6, 31, 17), STATIC });
eq('assemble：UTC还是7月、北京已是8月 → 用北京月份选 jan', D3.health.level, 'JAN');

// ---- 席位覆盖 ----
const REP = { generatedAt: 'G', series: [{ key: 'soy_import' }, { key: 'capital_rank', firstDay: '2022-01-04', lastDay: '2026-10-09', files: 1073, coverage: { 高盛期货: { exact: 10, estimated: 103, absent: 960 }, 摩根大通: { exact: '807', estimated: 218 } } }] };
eq('coverageFrom：取 capital_rank 那项，数字规整，缺项补0', CL.coverageFrom(REP), { firstDay: '2022-01-04', lastDay: '2026-10-09', files: 1073, runAt: 'G', seats: { 高盛期货: { exact: 10, estimated: 103, absent: 960 }, 摩根大通: { exact: 807, estimated: 218, absent: 0 } } });
eq('coverageFrom：没有 capital_rank → null', CL.coverageFrom({ series: [{ key: 'x' }] }), null);
eq('coverageFrom：capital_rank 报错项 → null', CL.coverageFrom({ series: [{ key: 'capital_rank', error: 'boom', coverage: {} }] }), null);
eq('coverageFrom：报告缺失/结构不对 → null', [CL.coverageFrom(null), CL.coverageFrom({}), CL.coverageFrom({ series: 'x' })], [null, null, null]);
eq('assemble：把报告里的覆盖放进 D.capitalCoverage', CL.assemble({ state: mkState(), latest: {}, H: {}, seasonal: null, histCsv: '', report: REP, now: Date.UTC(2026, 9, 11, 13), STATIC }).capitalCoverage.seats['高盛期货'].absent, 960);
eq('assemble：没给报告 → capitalCoverage=null', D2.capitalCoverage, null);

console.log(`\n结果：${pass}项通过，${fail}项失败`); process.exit(fail ? 1 : 0);
