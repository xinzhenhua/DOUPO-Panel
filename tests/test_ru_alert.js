/* 橡胶提醒测试：node tests/test_ru_alert.js */
const { compute, loadSeries } = require('../scripts/ru_alert.js');
let pass = 0, fail = 0; const eq = (n, x, y) => { const ok = JSON.stringify(x) === JSON.stringify(y); ok ? pass++ : (fail++, console.log('✗', n, '\n  得到', JSON.stringify(x), '\n  应为', JSON.stringify(y))); };
const has = (n, c) => { c ? pass++ : (fail++, console.log('✗', n)); };
function mk(start, closes) { const d = [], o = [], h = [], l = [], c = [], r = [], m = []; let t = new Date(start + 'T00:00:00Z'); for (const x of closes) { while ([0, 6].includes(t.getUTCDay())) t.setUTCDate(t.getUTCDate() + 1); d.push(t.toISOString().slice(0, 10)); o.push(x); h.push(x * 1.004); l.push(x * 0.996); c.push(x); r.push(x * 100); m.push('2705'); t.setUTCDate(t.getUTCDate() + 1); } return { d, o, h, l, c, r, m }; }
const keys = o => o.events.map(e => e.key);
// 休眠
let S = mk('2027-02-22', [200, 199, 198, 197, 196]);
eq('10月休眠无事件', compute(S, '2026-10-19', null).events.length, 0);
// 准备期
let o = compute(S, '2027-02-12', null); eq('2/12 准备期提醒', keys(o), ['ru|2027|pre']); eq('有主题', /橡胶/.test(o.events[0].title), true);
// 3/1 窗口开始（最新价已有3月）
S = mk('2027-02-22', [200, 199, 198, 197, 196, 195, 194, 193, 192]);   // 3/1 = 第6个工作日
o = compute(S, S.d[S.d.length - 1], null); has('窗口开始事件', keys(o).includes('ru|2027|open')); eq('下跌中无信号', o.plan.st, 'wait'); has('下跌中无go', !keys(o).some(k => k.includes('|go|')));
// 反弹出信号
S = mk('2027-02-22', [200, 199, 198, 197, 196, 195, 194, 193, 197]); const L = S.d[S.d.length - 1];
o = compute(S, L, { level: 'ok', text: '主产区天气正常' }); const g = o.events.find(e => e.key === 'ru|2027|go|' + L); has('出go事件', !!g);
has('含限价', /≥19\d{3}|≥1\d{4}/.test(g.title)); has('含止损价', /止损 \d+/.test(g.body)); has('提醒手动项', /手动/.test(g.body));
eq('同一天重复计算key不变(防重复)', keys(compute(S, L, { level: 'ok', text: 'x' })).filter(k => k.includes('|go|')), ['ru|2027|go|' + L]);
// 天气拦截
o = compute(S, L, { level: 'block', text: '泰国南部 严重偏旱' }); has('被拦下事件', keys(o).includes('ru|2027|blk|' + L)); has('天气转坏事件', keys(o).some(k => k.includes('|wxb|'))); has('不出go', !keys(o).some(k => k.includes('|go|')));
// 天气没取到不拦
o = compute(S, L, { level: 'unknown', text: 'x' }); has('天气未知仍出信号', keys(o).some(k => k.includes('|go|')));
// 数据没更新到3月
o = compute(mk('2027-01-20', [200, 199, 198]), '2027-03-10', null); eq('价格停在1月 → stale 无信号', o.events.some(e => e.key.includes('|go|')), false);
// 最后交易日
S = mk('2027-03-20', [200, 199, 198, 197, 196, 195, 194, 193, 192]);
o = compute(S, '2027-03-31', null); has('3/31平仓提醒', keys(o).includes('ru|2027|exit'));
o = compute(S, '2027-03-30', null); has('3/30无平仓提醒', !keys(o).includes('ru|2027|exit'));
o = compute(S, '2027-04-01', null); has('4/1补提醒', keys(o).includes('ru|2027|late'));
// 2024年3月最后工作日=29(31日周日)
o = compute(mk('2024-03-18', [200, 199, 198, 197, 196, 195]), '2024-03-29', null); has('2024平仓在3/29', keys(o).includes('ru|2024|exit'));
// 真实快照可加载，live 合并
const R = loadSeries('/nonexistent'); has('快照可加载', R && R.d.length > 3000 && R.m.length === R.d.length);
const fs = require('fs'), os = require('os'), p = require('path'), dir = fs.mkdtempSync(p.join(os.tmpdir(), 'ru')); const last = R.d[R.d.length - 1], rl = R.r[R.r.length - 1];
fs.writeFileSync(p.join(dir, 'ru_live.json'), JSON.stringify({ d: ['2099-01-04'], o: [rl], h: [rl * 1.01], l: [rl * 0.99], c: [rl * 1.02], m: ['RU2705'] }));
const R2 = loadSeries(dir); eq('live 并入一根', R2.d.length, R.d.length + 1); near = Math.abs(R2.c[R2.c.length - 1] / R2.r[R2.r.length - 1] - R.c[R.c.length - 1] / R.r[R.r.length - 1]) < 1e-9; has('复权因子沿用', near); eq('主力月份去掉RU前缀', R2.m[R2.m.length - 1], '2705');
console.log(`结果：${pass}项通过` + (fail ? `，${fail}项失败` : '')); process.exit(fail ? 1 : 0);
