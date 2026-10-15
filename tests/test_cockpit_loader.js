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
{ const m2 = Object.assign({ bplant: { name: '巴西播种' } }, meta), bp = [['2025-10-05', 5], ['2025-12-28', 98], ['2026-09-27', 1], ['2026-10-04', 8.2], ['2026-10-11', 15]].map(([d, v]) => ({ d, v }));
  const S2 = CL.buildSeries(m2, { brazil_planting: bp }, ctx);
  eq('巴西播种：只取本季（上一季的点不连到这一季）', [S2.bplant.pts.map(p => p.v), S2.bplant.nTotal], [[1, 8.2, 15], 5]);
  eq('巴西播种：没有历史文件时是空序列', CL.buildSeries(m2, {}, ctx).bplant.pts, []); }
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

// ---- 换月调整价 ----
{ const days = []; const d0 = Date.UTC(2025, 0, 1); for (let n = 0; n < 300; n++) days.push(new Date(d0 + n * 86400e3).toISOString().slice(0, 10));
  const idx = days.map((_, n) => 100 + n * 0.1), raw = days.map((_, n) => (n < 150 ? 3000 : 3150) + n * 5);   // 原始主连在第150天换月，跳了+150
  const hist = { d: days, c: raw }, a = CL.adjFrom({ d: days, i: idx, k: days.map(() => 'm') }, hist);
  eq('adjFrom：最后一天折算后等于原始主连最后一天', Math.abs(a.c[a.c.length - 1] - raw[raw.length - 1]) < 1e-9, true);
  eq('adjFrom：换月日没有缺口（调整价相邻日涨跌与指数一致）', Math.abs((a.c[150] / a.c[149]) / (idx[150] / idx[149]) - 1) < 1e-12, true);
  eq('adjFrom：不足200天/长度对不上/空 → null', [CL.adjFrom({ d: days.slice(0, 50), i: idx.slice(0, 50) }, hist), CL.adjFrom({ d: days, i: idx.slice(1) }, hist), CL.adjFrom(null, hist)], [null, null, null]);
  eq('adjFrom：没有原始主连也能给出（水平为指数本身）', CL.adjFrom({ d: days, i: idx }, null).c[0], 100);
  eq('assemble：D.adj', CL.assemble({ state: mkState(), latest: {}, H: {}, seasonal: null, histCsv: '', report: null, adj: { d: days, i: idx, k: days.map(() => 'm2599') }, now: Date.UTC(2026, 9, 11, 13), STATIC }).adj.d.length, 300); }

{
  const bar = (dt, c) => ({ datetime: dt, open: c, high: c, low: c, close: c, volume: 1, hold: 1 });
  const A = (latest, prices) => CL.assemble({ state: mkState(), latest, H: {}, seasonal: null, histCsv: '', prices, now: Date.UTC(2026, 9, 12, 5), STATIC });
  const lt = { dceM01Min15: { bars: [bar('2026-10-12 10:00:00', 3380)] } };
  eq('prices.json 比 latest 新 → 用 prices 的15分钟价', A(lt, { contracts: { M01: { bars: [bar('2026-10-12 11:15:00', 3365)] } } }).live.jan.c, 3365);
  eq('prices.json 比 latest 旧 → 用 latest 里的', A(lt, { contracts: { M01: { bars: [bar('2026-10-12 09:00:00', 3300)] } } }).live.jan.c, 3380);
  eq('没有 prices.json → 不报错，用 latest', A(lt, null).live.jan.c, 3380);
  eq('D.m15 的 d 字段是 月-日 时:分', A(lt, null).m15.jan[0].d, '10-12 10:00');
}
{
  const adj = { d: ['2026-10-08', '2026-10-09'], c: [3000, 3060], k: ['m2701', 'm2701'] };
  const bars = [{ d: '2026-10-09', c: 3402 }, { d: '2026-10-12', c: 3420 }, { d: '2026-10-13', c: 3500 }];
  const at = (h, m) => Date.UTC(2026, 9, 12, h - 8, m);   // 北京时间
  const e1 = CL.extendAdj(adj, bars, 'M2701', at(15, 30));
  eq('extendAdj：15:30 当天已收盘 → 接上 10-12，按两边同一天收盘比折算（3420×3060/3402）', [e1.d, Math.round(e1.c[2] * 100) / 100, e1.extended], [['2026-10-08', '2026-10-09', '2026-10-12'], 3076.19, 1]);
  eq('extendAdj：14:00 当天还没收盘 → 不接', CL.extendAdj(adj, bars, 'M2701', at(14, 0)).d.length, 2);
  eq('extendAdj：15:00 整还不算（过 15:01 才接）', CL.extendAdj(adj, bars, 'M2701', at(15, 0)).d.length, 2);
  eq('extendAdj：明天的占位（夜盘）不接', CL.extendAdj(adj, bars, 'M2701', at(23, 30)).d.length, 3);
  eq('extendAdj：不是同一个合约（换月了）→ 不接', CL.extendAdj(adj, bars, 'M2705', at(15, 30)).d.length, 2);
  eq('extendAdj：没有新日线 → 原样返回同一个对象', CL.extendAdj(adj, [{ d: '2026-10-09', c: 3402 }], 'M2701', at(15, 30)) === adj, true);
  eq('extendAdj：空输入不报错', [CL.extendAdj(null, bars, 'x', 0), CL.extendAdj(adj, null, 'x', 0) === adj], [null, true]);
  { // 日线晚上才出：用 15:00 那根 15 分钟线当临时收盘价
    const m15 = [{ datetime: '2026-10-12 14:45:00', close: 3382 }, { datetime: '2026-10-12 15:00:00', close: 3383 }, { datetime: '2026-10-12 21:15:00', close: 3390 }];
    eq('provDaily：只取 15:00 那根', CL.provDaily(m15), [{ d: '2026-10-12', c: 3383 }]);
    const nx = CL.extendAdj(adj, CL.provDaily(m15).concat([{ d: '2026-10-09', c: 3402 }]), 'M2701', at(16, 10));
    eq('临时收盘价：16:10 接上 10-12，价格按 15:00 收盘', [nx.d[nx.d.length - 1], Math.round(nx.c[nx.c.length - 1] / adj.c[adj.c.length - 1] * 3402)], ['2026-10-12', 3383]);
    eq('临时收盘价：日线出来后以日线为准', CL.extendAdj(adj, CL.provDaily(m15).concat([{ d: '2026-10-09', c: 3402 }, { d: '2026-10-12', c: 3380 }]), 'M2701', at(16, 10)).c.slice(-1)[0] < nx.c.slice(-1)[0], true);
  }
  { // 新浪15分钟线直连：解析 + 并进 prices.json
    const bars=CL.parseSinaMin([{d:'2026-10-14 10:15:00',o:'3380',h:'3390',l:'3378',c:'3385',v:'120',p:'2400000'},{d:'',c:1},null]);
    eq('parseSinaMin：字段映射，丢掉坏行',bars,[{datetime:'2026-10-14 10:15:00',open:3380,high:3390,low:3378,close:3385,volume:120,hold:2400000}]);
    const base={updatedAt:'x',contracts:{M01:{symbol:'M2701',bars:[{datetime:'2026-10-14 10:00:00',close:3380},{datetime:'2026-10-14 10:15:00',close:3381}],daily:[]}}};
    const mg=CL.mergeSina(base,{jan:{symbol:'M2701',bars:[{datetime:'2026-10-14 10:15:00',close:3385},{datetime:'2026-10-14 10:30:00',close:3390}]}});
    eq('mergeSina：新浪更新的并进去，重叠的以新浪为准',mg.contracts.M01.bars.map(b=>b.close),[3380,3385,3390]);
    eq('mergeSina：新浪没有更新就不动',CL.mergeSina(base,{jan:{symbol:'M2701',bars:[{datetime:'2026-10-14 10:00:00',close:1}]}})._sina,0);
    eq('mergeSina：合约不一致（换月）不并',CL.mergeSina(base,{jan:{symbol:'M2705',bars:[{datetime:'2026-10-14 11:00:00',close:1}]}})._sina,0);
    eq('mergeSina：不改原对象',base.contracts.M01.bars.length,2);
    const em=CL.parseEmKlines({data:{klines:['2026-10-14 10:15,3380,3390,3395,3378,1200,4e6','2026-10-14 10:30,3390,3385,3392,3383,900,3e6','bad','2026-10-14 10:45,x,1,2,3,4,5']}});
    eq('parseEmKlines：东方财富开/收顺序和新浪不同，字段映射正确、丢坏行、补秒',em,[{datetime:'2026-10-14 10:15:00',open:3380,close:3390,high:3395,low:3378,volume:1200,hold:null},{datetime:'2026-10-14 10:30:00',open:3390,close:3385,high:3392,low:3383,volume:900,hold:null}]);
    eq('parseEmKlines：空/异常返回[]',[CL.parseEmKlines(null),CL.parseEmKlines({data:null}),CL.parseEmKlines({data:{klines:null}})],[[],[],[]]);
    eq('emUrl：大商所市场代码114、合约小写、15分钟',/secid=114\.m2701&.*klt=15.*cb=cbx$/.test(CL.emUrl('M2701','cbx')),true);
    const ca=[{datetime:'2026-10-14 10:30:00',close:3386}], ok1=CL.priceCheck(ca,em), bad=CL.priceCheck([{datetime:'2026-10-14 10:30:00',close:3300}],em);
    eq('两个价格源核对：差0.03%算一致；差2.5%不一致；没有共有时间/只有一个源→null',[ok1.ok,bad.ok,CL.priceCheck(ca,[]).ok,CL.priceCheck([{datetime:'z',close:1}],em).ok],[true,false,null,null]);
    const at=(h,m,dow)=>Date.UTC(2026,9,12+((dow+6)%7),h-8,m);
    eq('交易时段：周三10:00是，周三12:00（午休也照常刷，无害）是，周三15:30否，周三21:30是，周六10:00否',[CL.tradingNow(at(10,0,3)),CL.tradingNow(at(12,0,3)),CL.tradingNow(at(15,30,3)),CL.tradingNow(at(21,30,3)),CL.tradingNow(at(10,0,6))],[true,true,false,true,false]);
    eq('tickUrl：1分钟线、合约大写、回调名带上',/symbol=M2701&type=1$/.test(CL.tickUrl('m2701','cbx'))&&CL.tickUrl('M2701','cbx').includes('var%20cbx='),true);
    eq('parseSinaTick：取最后一根1分钟线的收盘=最新价；空/异常→null',[CL.parseSinaTick([{d:'2026-10-14 21:30:00',o:3380,h:3385,l:3378,c:3383,v:10},{d:'2026-10-14 21:31:00',o:3383,h:3390,l:3382,c:3388,v:7}]),CL.parseSinaTick([]),CL.parseSinaTick(null)],[{dt:'2026-10-14 21:31:00',c:3388,v:7,src:'min'},null,null]);
    const dd={a:1,ticks:{sep:{c:1}},priceSrc:{x:1},old:2}; CL.fill(dd,{a:2,nw:3});
    eq('fill：整体重算时保留浏览器自己维护的实时字段（ticks/priceSrc/priceCheck），其余旧键照常清掉',dd,{a:2,ticks:{sep:{c:1}},priceSrc:{x:1},nw:3});
    { const q='豆粕2601,110312,3100,3120,3090,3105,3108,3109,3110,3109,3105,50,60,1200000,45678,0,0,2026-10-15,x';
      eq('parseSinaHq：取最新价/时间/成交量，日期取报价里的',CL.parseSinaHq(q),{dt:'2026-10-15 11:03:12',c:3110,v:45678,src:'hq'});
      eq('parseSinaHq：无日期字段时用北京时间今天',CL.parseSinaHq(q.replace('2026-10-15','a'),Date.UTC(2026,9,15,3,0,0)).dt,'2026-10-15 11:03:12');
      eq('parseSinaHq：空串/价格为0/时间错/字段不够 都返回null',[CL.parseSinaHq(''),CL.parseSinaHq(undefined),CL.parseSinaHq(q.replace(',3110,',',0,')),CL.parseSinaHq(q.replace('110312','999999')),CL.parseSinaHq('a,b,c')],[null,null,null,null,null]);
      eq('hqUrl：指向 hq.sinajs.cn 且合约大写',/^https:\/\/hq\.sinajs\.cn\/list=nf_M2601&_=\d+$/.test(CL.hqUrl('m2601')),true); }
    eq('parseEmTick：f43最新价+f86秒级时间戳(北京时间)',[CL.parseEmTick({data:{f43:3110.5,f86:Date.UTC(2026,9,15,3,3,12)/1000}}),CL.parseEmTick({data:null}),CL.parseEmTick({data:{f43:'-',f86:1}}),CL.parseEmTick(null)],[{dt:'2026-10-15 11:03:12',c:3110.5,v:0,src:'em'},null,null,null]);
    eq('emTickUrl：secid=114.合约小写',/secid=114\.m2601&fields=f43,f57,f86&fltt=2/.test(CL.emTickUrl('M2601','cb')),true);
    { const o = CL.tkSrc; CL.tkSrc = 'em'; const a = CL.tickBase(); CL.tkSrc = 'min'; const b = CL.tickBase(); CL.tkSrc = undefined; const c = CL.tickBase(); CL.tkSrc = o;
      eq('tickBase：东方财富2秒，1分钟线/未知也2秒；被拒后自动放慢的间隔优先', [a, b, c], [2000, 2000, 2000]); CL.tkSrc = 'em'; CL.tkPace = { em: 3000 }; eq('tickBase：东方财富被拒放慢后=3秒', CL.tickBase(), 3000); CL.tkPace = undefined; CL.tkSrc = o; }
    { const s1 = CL.parseEmSse(null, '{"rc":0,"data":{"f43":3110.5,"f57":"m2601","f86":1760500992}}'), s2 = CL.parseEmSse(s1, {data:{f43:3111}}), s3 = CL.parseEmSse(s2, {data:{f86:1760500999}});
      eq('parseEmSse：首条全量，后续只推变化的字段，逐条合并', [s1.f43, s2.f43, s2.f86, s3.f43, s3.f86], [3110.5, 3111, 1760500992, 3111, 1760500999]);
      eq('parseEmSse：坏JSON/没有data/没有关心的字段 → null', [CL.parseEmSse(null, 'x'), CL.parseEmSse(null, '{"rc":0}'), CL.parseEmSse(null, {data:{f57:'m'}}), CL.parseEmSse(null, {data:{f43:'-'}})], [null, null, null, null]);
      eq('emSseTick：取价+秒级时间戳转北京时间', CL.emSseTick({f43:3110.5,f86:Date.UTC(2026,9,15,3,3,12)/1000}, 3100, 0), {dt:'2026-10-15 11:03:12',c:3110.5,v:0,src:'sse'});
      eq('emSseTick：推送给放大100倍的整数时按上一价校正；没有时间戳用现在；价格无效null', [CL.emSseTick({f43:311050,f86:Date.UTC(2026,9,15,3,3,12)/1000}, 3100, 0).c, CL.emSseTick({f43:3110}, 3100, Date.UTC(2026,9,15,3,0,0)).dt, CL.emSseTick({f43:0}, 3100, 0), CL.emSseTick(null,0,0)], [3110.5, '2026-10-15 11:00:00', null, null]);
      eq('emSseUrl：sse接口、合约小写、带fltt=2', /push2\.eastmoney\.com\/api\/qt\/stock\/sse\?.*fltt=2.*secid=114\.m2601$/.test(CL.emSseUrl('M2601')), true); }
    eq('tickDelay：默认3秒；连续失败逐级放慢 6秒→15秒→30秒（被限流时退让）；可自定义基础间隔',[[0,1,2,3,5,6,20].map(f=>CL.tickDelay(f,3000)),CL.tickDelay(0,1500),CL.tickDelay(1,1500)],[[3000,6000,6000,15000,15000,30000,30000],1500,5000]);
  }
}
console.log(`\n结果：${pass}项通过，${fail}项失败`); process.exit(fail ? 1 : 0);
