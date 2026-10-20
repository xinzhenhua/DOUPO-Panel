/* 橡胶3月季节性规则的纯函数测试：node tests/test_rubber.js */
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'cockpit', 'rubber.js'), 'utf8');
const a = src.indexOf('/* RU_BEGIN */'), b = src.indexOf('/* RU_END */'); if (a < 0 || b < 0) { console.log('找不到 RU_BEGIN/RU_END'); process.exit(1); }
const P = new Function(src.slice(a, b) + '\nreturn {ruIndMerge,RUIND,ruIndTrend,ruIndSummary,RUP,RUREG,ruSimYear,ruHistory,ruStats,ruPlan,ruSize,ruRegionWx,ruWxVerdict,ruLastWeekdayOfMarch,ruTickUp,ruMA,ruAddDays};')();
const HIST = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'cockpit', 'ru_hist.json'), 'utf8'));
let pass = 0, fail = 0; const eq = (n, x, y) => { const ok = JSON.stringify(x) === JSON.stringify(y); ok ? pass++ : (fail++, console.log('✗', n, '\n  得到', JSON.stringify(x), '\n  期望', JSON.stringify(y))); };
const near = (n, x, y, t = 0.02) => { const ok = Math.abs(x - y) <= t; ok ? pass++ : (fail++, console.log('✗', n, x, '≠', y)); };
// 合成序列：从 startDate 起连续工作日，价格 closes，开高低收按给定
function mk(start, closes, hi = 0.004) { const d = [], o = [], h = [], l = [], c = [], r = []; let t = new Date(start + 'T00:00:00Z'); for (const x of closes) { while ([0, 6].includes(t.getUTCDay())) t.setUTCDate(t.getUTCDate() + 1); d.push(t.toISOString().slice(0, 10)); o.push(x); h.push(x * (1 + hi)); l.push(x * (1 - hi)); c.push(x); r.push(x * 100); t.setUTCDate(t.getUTCDate() + 1); } return { d, o, h, l, c, r }; }
// ---- 日期 / 工具
eq('2026-3月最后工作日=31', P.ruLastWeekdayOfMarch(2026), '2026-03-31'); eq('2025-3月最后工作日=28(31日周一?)', P.ruLastWeekdayOfMarch(2025), '2025-03-31'); eq('2027-3月最后工作日=31', P.ruLastWeekdayOfMarch(2027), '2027-03-31'); eq('2028-3月最后工作日=31', P.ruLastWeekdayOfMarch(2028), '2028-03-31'); eq('2029-3月31日周六→3-30', P.ruLastWeekdayOfMarch(2029), '2029-03-30');
eq('向上取整到5元', P.ruTickUp(17231.5), 17235); eq('已是5的倍数', P.ruTickUp(17235), 17235);
eq('MA5', P.ruMA([1, 2, 3, 4, 5], 4, 5), 3); eq('MA5不足', P.ruMA([1, 2, 3], 2, 5), null);
// ---- 历史：与 Python 回测一致（E_ma5：首个收盘≥MA5的3月日，次日限价≥收盘×1.003，5%止损，月底平仓）
const H = P.ruHistory(HIST), want = { 2013: 9.03, 2014: -5.06, 2015: 1.53, 2016: -5.06, 2017: 15.50, 2018: 11.28, 2019: 11.68, 2020: 15.15, 2021: 10.87, 2022: 2.11, 2023: 5.36, 2024: -5.06, 2025: 6.95, 2026: 5.38 };
eq('14个3月', H.length, 14); H.forEach(x => near('历史 ' + x.y, x.ret * 100, want[x.y], 0.01));
const ST = P.ruStats(H); near('平均 5.69%', ST.mean, 5.69, 0.02); near('胜率 78.6%', ST.win, 78.57, 0.05); near('最差 -5.06%', ST.worst, -5.06, 0.01); eq('成交年数14', ST.n, 14);
// ---- 合成：下跌趋势里等反弹
const t0 = ['2027-02-24', '2027-02-25', '2027-02-26'];
function ser(extra) { const base = []; for (let i = 0; i < 10; i++) base.push(200 - i); return mk('2027-02-15', base.concat(extra)); }
let S = ser([188, 187, 186]);           // 2/15起共13个工作日，最后到 3/3(周三)？按生成器：先看日期
const last = S.d[S.d.length - 1];
// 日期在3月之前：准备期
let pl = P.ruPlan(S, '2027-02-20', null, null); eq('2/20 准备期', pl.st, 'pre'); eq('距3/1天数', pl.daysTo, 9);
pl = P.ruPlan(S, '2027-01-20', null, null); eq('1/20 休眠', pl.st, 'sleep');
pl = P.ruPlan(S, '2027-04-05', null, null); eq('4/5 休眠，下个窗口2028', pl.nextWin, '2028-03-01');
// 3月：价格低于MA5 → 等反弹
const S2 = mk('2027-02-22', [200, 199, 198, 197, 196, 195, 194, 193, 192]);   // 2/22起：3/1是第6个工作日
const pw = P.ruPlan(S2, S2.d[S2.d.length - 1], null, null); eq('3月下跌中 → 等反弹', pw.st, 'wait');
// 反弹：最后一天收盘>MA5
const S3 = mk('2027-02-22', [200, 199, 198, 197, 196, 195, 194, 193, 197]); const lastD3 = S3.d[S3.d.length - 1];
const pg = P.ruPlan(S3, lastD3, { level: 'ok', text: '主产区天气正常' }, null); eq('3月反弹 → 做空信号', pg.st, 'go'); eq('限价=收盘×1.003向上取5', pg.order.lim, P.ruTickUp(197 * 100 * 1.003)); eq('止损=限价×1.05', pg.order.stop, Math.round(pg.order.lim * 1.05));
eq('天气严重异常 → 暂缓', P.ruPlan(S3, lastD3, { level: 'block', text: '泰国南部 严重偏旱' }, null).st, 'blocked');
eq('天气轻度异常 → 仍出信号', P.ruPlan(S3, lastD3, { level: 'warn', text: 'x' }, null).st, 'go');
eq('天气没取到 → 不拦', P.ruPlan(S3, lastD3, { level: 'unknown', text: 'x' }, null).st, 'go');
// 数据没更新到3月
eq('3月但价格停在2月中 → stale', P.ruPlan(S, '2027-03-20', null, null).st, 'stale');
eq('今天3/1，最新价是2月最后一天 → 等第一个3月收盘', P.ruPlan(mk('2027-02-22', [200, 199, 198, 197, 196]), '2027-03-01', null, null).st, 'pre');
// 持仓
const posd = { d: '2027-03-02', px: 19700, lots: 1 };
let ph = P.ruPlan(S3, lastD3, { level: 'ok', text: '' }, posd); eq('持仓 → 持有', ph.st, 'hold'); near('浮盈(真实价)', ph.pos.r, -(19700 / 19700 - 1) * 100, 0.01); eq('止损价', Math.round(ph.pos.stop), Math.round(19700 * 1.05));
ph = P.ruPlan(S3, lastD3, { level: 'block', text: '云南 严重偏旱' }, posd); eq('持仓+天气异常 → 考虑离场', ph.st, 'holdwx');
const Sx = mk('2027-02-22', [200, 199, 198, 197, 196, 195, 194, 193, 197 * 1.06]); eq('触及止损 → 平仓', P.ruPlan(Sx, Sx.d[Sx.d.length - 1], null, { d: '2027-03-02', px: 19700, lots: 1 }).st, 'exit');
eq('3/31 持仓 → 该平仓', P.ruPlan(S3, '2027-03-31', null, posd).st, 'exit');
eq('4月还拿着 → 平仓', P.ruPlan(S3, '2027-04-08', null, posd).st, 'exit');
// ---- 手动录入、合约、换合约、止损后不再开
const S4 = mk('2027-02-22', [200, 199, 198, 197, 196, 195, 194, 193, 197]); S4.m = S4.d.map(() => '2705'); const L4 = S4.d[S4.d.length - 1], okw = { level: 'ok', text: '' };
eq('出信号时带上当前主力合约', P.ruPlan(S4, L4, okw, null, {}).order.contract, 'RU2705'); eq('3月05合约代码', P.ruPlan(S4, L4, okw, null, {}).mar05, 'RU2705'); eq('3月09合约代码', P.ruPlan(S4, L4, okw, null, {}).mar09, 'RU2709');
eq('手动：延迟开割 → 暂缓', P.ruPlan(S4, L4, okw, null, { st: 'delay' }).st, 'blocked'); eq('手动：需求走强 → 暂缓', P.ruPlan(S4, L4, okw, null, { demand: true }).st, 'blocked');
eq('手动：正常开割 → 不拦', P.ruPlan(S4, L4, okw, null, { st: 'ok' }).st, 'go'); eq('手动：停割中 → 不拦', P.ruPlan(S4, L4, okw, null, { st: 'stop' }).st, 'go');
eq('持仓+需求走强 → 考虑离场', P.ruPlan(S4, L4, okw, { d: '2027-03-02', px: 19700, lots: 1, contract: 'RU2705' }, { demand: true }).st, 'holdwx');
eq('持仓+延迟开割 → 考虑离场', P.ruPlan(S4, L4, okw, { d: '2027-03-02', px: 19700, lots: 1, contract: 'RU2705' }, { st: 'delay' }).st, 'holdwx');
eq('拦截原因写在 bad 里', P.ruPlan(S4, L4, okw, null, { st: 'delay', demand: true }).bad.length, 2);
const S5 = mk('2027-03-10', [197, 197]); S5.m = ['2709', '2709'];
eq('主力换到09、持仓在05 → roll提示', P.ruPlan(S5, S5.d[1], okw, { d: '2027-03-02', px: 19700, lots: 1, contract: 'RU2705' }, {}).roll, true);
eq('持仓合约=主力 → 无roll提示', P.ruPlan(S5, S5.d[1], okw, { d: '2027-03-02', px: 19700, lots: 1, contract: 'RU2709' }, {}).roll, false);
eq('今年已止损 → 不再开仓', P.ruPlan(S4, L4, okw, null, { stopY: 2027 }).st, 'done'); eq('去年止损不影响今年', P.ruPlan(S4, L4, okw, null, { stopY: 2026 }).st, 'go');
// ---- 手数
let z = P.ruSize(500000, 17235, 2, 12); eq('50万/2%风险 → 1手', z.lots, 1); near('1手止损亏', z.perLot, 17235 * 10 * 0.05, 0.01);
z = P.ruSize(2000000, 17235, 2, 12); eq('200万/2% → 4手(风险) ', z.byRisk, 4); eq('保证金上限不超30%', z.lots <= z.byMargin, true);
eq('权益0 → 0手', P.ruSize(0, 17235, 2, 12).lots, 0); eq('很小权益 → 0手', P.ruSize(50000, 17235, 2, 12).lots, 0);
// ---- 天气
function wxfc(today, p30each, tx) { const d = [], p = [], t = []; for (let i = -34; i <= 7; i++) { d.push(P.ruAddDays(today, i)); p.push(i <= 0 ? p30each : 1); t.push(tx); } return { d, p, tx: t }; }
function wxh(p, tx, yrs) { const d = [], pp = [], t = []; yrs.forEach(y => { let x = new Date(y + '-01-01T00:00:00Z'); while (x.getUTCFullYear() === y) { d.push(x.toISOString().slice(0, 10)); pp.push(p); t.push(tx); x.setUTCDate(x.getUTCDate() + 1); } }); return { d, p: pp, tx: t }; }
const Y = [2021, 2022, 2023, 2024, 2025], hh = wxh(3, 32, Y), td = '2027-03-10';   // 常年30天约90mm
let w = P.ruRegionWx(wxfc(td, 3, 32), hh, td, Y); eq('降水正常 → sev0', w.sev, 0); near('常年30天=90mm', w.n30, 90, 0.5);
w = P.ruRegionWx(wxfc(td, 0.5, 32), hh, td, Y); eq('降水15mm(17%)且少75mm → 严重偏旱', [w.sev, w.msg], [2, '严重偏旱']);
w = P.ruRegionWx(wxfc(td, 0.7, 32), hh, td, Y); eq('降水约23%(<25%) → 严重偏旱边界', w.sev, 2);
w = P.ruRegionWx(wxfc(td, 0.9, 32), hh, td, Y); eq('降水约30%(25~50%) → 偏旱', w.sev, 1);
w = P.ruRegionWx(wxfc(td, 1.2, 32), hh, td, Y); eq('降水36mm(40%) → 偏旱 sev1', [w.sev, w.msg], [1, '偏旱']);
w = P.ruRegionWx(wxfc(td, 10, 32), hh, td, Y); eq('降水300mm(333%) → 严重偏涝', w.sev, 2);
w = P.ruRegionWx(wxfc(td, 3, 36), hh, td, Y); eq('最高温高4℃ → 高温 sev1', [w.sev, w.msg], [1, '高温']);
const small = wxh(0.3, 30, Y); w = P.ruRegionWx(wxfc(td, 0, 30), small, td, Y); eq('常年降水很少(<20mm)时不做降水判断', w.sev, 0);
const reg = (k, core, sev, msg) => ({ k, n: k, core, sev, msg });
eq('全部正常', P.ruWxVerdict([reg('a', true, 0, '正常'), reg('b', false, 0, '正常')]).level, 'ok');
eq('非核心区1个注意 → warn', P.ruWxVerdict([reg('a', true, 0, '正常'), reg('b', false, 1, '偏旱')]).level, 'warn');
eq('核心区严重 → block', P.ruWxVerdict([reg('a', true, 2, '严重偏旱'), reg('b', false, 0, '正常')]).level, 'block');
eq('非核心区严重(单个) → warn不拦', P.ruWxVerdict([reg('a', true, 0, '正常'), reg('b', false, 2, '严重偏旱')]).level, 'warn');
eq('注意累计3 → block', P.ruWxVerdict([reg('a', true, 1, 'x'), reg('b', false, 1, 'x'), reg('c', false, 1, 'x')]).level, 'block');
eq('全部取失败 → unknown不拦', P.ruWxVerdict([{ err: 'x' }, { err: 'y' }]).level, 'unknown');

// ---- v102.1：天气产区调整（泰北/泰东北/越南东南=开割节奏；印尼巨港=降雨偏多）
eq('产区=泰北/泰东北/越南东南/印尼巨港', P.RUREG.map(g => g.k), ['thn', 'the', 'vn', 'id']);
eq('不再看西双版纳/泰国南部/海南', P.RUREG.some(g => /西双版纳|泰国南部|海南/.test(g.n)), false);
eq('前三个第一优先(open)，印尼第二优先(wet)', P.RUREG.map(g => g.kind + g.pri), ['open1', 'open1', 'open1', 'wet2']);
eq('只有印尼不是核心', P.RUREG.filter(g => !g.core).map(g => g.k), ['id']);
const wToday = '2027-03-20', yrs = [2022, 2023, 2024, 2025, 2026];
function mkwx(pPerDay, txPast, normPerDay, txNorm, p7perDay) {
  const day = (d, n) => { const t = new Date(d + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };
  const fc = { d: [], p: [], tx: [] }; for (let i = -34; i <= 7; i++) { fc.d.push(day(wToday, i)); fc.p.push(i > -7 && i <= 0 && p7perDay != null ? p7perDay : pPerDay); fc.tx.push(txPast); }
  const hist = { d: [], p: [], tx: [] }; yrs.forEach(y => { for (let i = -34; i <= 0; i++) { hist.d.push(day(y + wToday.slice(4), i)); hist.p.push(normPerDay); hist.tx.push(txNorm); } });
  return [fc, hist];
}
let [f1, h1] = mkwx(0.1, 36, 1.2, 33);                    // 近30天几乎无雨(同期36mm)+比常年热3℃
let r1 = P.ruRegionWx(f1, h1, wToday, yrs, 'open'); eq('开割产区：严重偏旱+偏热 → 严重(2)', r1.sev, 2); eq('带高温标记', /高温/.test(r1.msg), true);
eq('一周无雨且均温≥33 → ur 提示为真', r1.ur, true);
let r1w = P.ruRegionWx(f1, h1, wToday, yrs, 'wet'); eq('印尼(wet)：干旱+高温不算异常', r1w.sev, 0); eq('印尼(wet)干旱说明', /对空头无影响/.test(r1w.msg), true);
[f1, h1] = mkwx(1.2, 33, 1.2, 33); r1 = P.ruRegionWx(f1, h1, wToday, yrs, 'open'); eq('降水气温都正常 → 0', r1.sev, 0); eq('正常不触发ur(7天累计>5mm)', r1.ur, false);
[f1, h1] = mkwx(3.4, 31, 1.2, 31); r1 = P.ruRegionWx(f1, h1, wToday, yrs, 'wet'); eq('印尼降雨283%、多66mm→偏多(1)', r1.sev, 1); eq('文字=降雨偏多', /降雨偏多/.test(r1.msg), true);
[f1, h1] = mkwx(4.7, 31, 1.2, 31); r1 = P.ruRegionWx(f1, h1, wToday, yrs, 'wet'); eq('印尼降雨392%、多105mm→严重(2)', r1.sev, 2);
[f1, h1] = mkwx(0.1, 33, 1.2, 33); r1 = P.ruRegionWx(f1, h1, wToday, yrs, 'open'); eq('仅严重偏旱(不偏热) → 严重(2)', r1.sev, 2);
[f1, h1] = mkwx(0.8, 33.5, 2, 33); r1 = P.ruRegionWx(f1, h1, wToday, yrs, 'open'); eq('30天降水40%（少36mm）、均温偏热0.5 → 偏旱注意(1)', r1.sev, 1);
eq('印尼单独严重不拦(非核心)', P.ruWxVerdict([{ core: true, sev: 0, n: 'a', msg: '正常' }, { core: false, sev: 2, n: '印尼', msg: '降雨严重偏多' }]).level, 'warn');
eq('印尼严重+泰北注意 累计≥3 → 拦', P.ruWxVerdict([{ core: true, sev: 1, n: 'a', msg: 'x' }, { core: false, sev: 2, n: '印尼', msg: 'y' }]).level, 'block');
// ---- 四类指标
const T0 = '2027-03-10', I1 = { stk: [{ d: '2027-03-02', v: 100 }, { d: '2027-03-09', v: 103 }], dark: [{ d: '2027-03-02', v: 50 }, { d: '2027-03-09', v: 47 }], qg: [{ d: '2027-03-02', v: 60 }, { d: '2027-03-09', v: 64 }], qin: [{ d: '2027-03-02', v: 8 }, { d: '2027-03-09', v: 14 }], qout: [{ d: '2027-03-02', v: 9 }, { d: '2027-03-09', v: 6 }], prod: [{ d: '2027-02-20', v: 38 }], prodY: [{ d: '2027-02-20', v: 4 }], imp: [{ d: '2027-02-20', v: 30 }], impY: [{ d: '2027-02-20', v: -8 }] };
const S1 = P.ruIndSummary(I1, T0), by = S1.by;
eq('社会库存+3% → 偏空(-1)', by.stk.m, -1); eq('深色胶-6% → 偏多(+1)', by.dark.m, 1); eq('全钢开工率+4点 → 偏多(+1)', by.qg.m, 1);
eq('青岛入库率+6点 → 偏空(-1)', by.qin.m, -1); eq('青岛出库率-3点 → 偏空(-1)', by.qout.m, -1);
eq('产量同比+4% → 偏空(-1)', by.prod.m, -1); eq('进口同比-8% → 偏多(+1)', by.imp.m, 1);
eq('没录入的指标 n=0 m=0', [by.light.n, by.light.m], [0, 0]); eq('录入项数', [S1.n, S1.tot], [7, 9]);
eq('空4(库存/入库/出库/产量)、多3(深色/开工率/进口) → 中性', [S1.bear, S1.bull, S1.dir], [4, 3, '中性']);
eq('深色胶去库≥3% → 提示警惕', S1.warns.some(w => /深色胶.*去库/.test(w)), true); eq('全钢开工率+4点≥3 → 提示需求回升', S1.warns.some(w => /全钢胎开工率.*升 4\.0/.test(w)), true);
eq('青岛入库大升出库走低 → 利空佐证', S1.goods.some(w => /青岛入库率/.test(w)), true);
eq('不足3项 → 数据不足', P.ruIndSummary({ stk: I1.stk }, T0).dir, 'na');
eq('周数据>10天没更新 → 过期', P.ruIndTrend(P.RUIND.find(d => d.k === 'stk'), I1, '2027-03-25').stale, true); eq('月数据30天内不过期', P.ruIndTrend(P.RUIND.find(d => d.k === 'prod'), I1, '2027-03-25').stale, false);
eq('变化小于阈值 → 不明显(0)', P.ruIndTrend(P.RUIND.find(d => d.k === 'stk'), { stk: [{ d: '2027-03-02', v: 100 }, { d: '2027-03-09', v: 100.5 }] }, T0).m, 0);
eq('只录入一期 → 无较上期、含义0', P.ruIndTrend(P.RUIND.find(d => d.k === 'qg'), { qg: [{ d: '2027-03-09', v: 60 }] }, T0).m, 0);
eq('偏空占优≥2 → 偏空', P.ruIndSummary({ stk: I1.stk, qin: I1.qin, qout: I1.qout }, T0).dir, '偏空');
const MG = P.ruIndMerge({ stk: [{ d: '2026-10-04', v: 100 }, { d: '2026-10-11', v: 999 }], qg: [{ d: '2026-10-09', v: 60 }] }, { stk: [{ d: '2026-10-11', v: 110.4 }, { d: '2026-09-27', v: 109.6 }], dark: [{ d: '2026-10-11', v: 74.5 }] });
eq('合并：同日以自动为准', MG.stk.find(p => p.d === '2026-10-11').v, 110.4); eq('合并：自动没有的日期保留手动并升序', MG.stk.map(p => p.d).join(), '2026-09-27,2026-10-04,2026-10-11');
eq('合并：只有手动的指标原样保留', MG.qg.length, 1); eq('合并：只有自动的指标', MG.dark[0].v, 74.5); eq('合并：空输入', JSON.stringify(P.ruIndMerge(null, null)), '{}');
console.log('结果：%d项通过，%d项失败', pass, fail); process.exit(fail ? 1 : 0);
