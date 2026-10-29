// scripts/build_widget.js：手机小组件数据。用仓库里的真实 data/ 拷一份到临时目录，换不同持仓检查状态；不联网。
const fs = require('fs'), path = require('path'), os = require('os');
const ROOT = path.join(__dirname, '..'), BW = require(path.join(ROOT, 'scripts', 'build_widget.js'));
let pass = 0, fail = 0;
const eq = (n, x, y) => { const ok = JSON.stringify(x) === JSON.stringify(y); ok ? pass++ : (fail++, console.log('❌', n, '期望', y, '实际', x)); if (ok) console.log('✅', n); };

// 1 交易合约：和 cockpit/ui.js 的 autoKey 同一规则（月份 → 合约），逐月核对
const stat = JSON.parse(fs.readFileSync(path.join(ROOT, 'cockpit', 'static.json'), 'utf8'));
const mk = (m) => Date.UTC(2026, m - 1, 15, 4, 0, 0);   // 北京时间中午，避开跨日
const exp = { 1: 'may', 2: 'may', 3: 'may', 4: 'sep', 5: 'sep', 6: 'sep', 7: 'sep', 8: 'jan', 9: 'jan', 10: 'jan', 11: 'jan', 12: 'may' };
for (let m = 1; m <= 12; m++) eq('autoKey ' + m + '月', BW.autoKey(stat.ctx, mk(m)), exp[m]);
// 北京时间跨日：UTC 10-31 17:00 = 北京 11-01 01:00，月份按北京算
eq('autoKey 按北京时间算月份', BW.autoKey(stat.ctx, Date.UTC(2026, 6, 31, 17, 0, 0)), 'jan');   // 北京 8-01 → 8月 → jan

// 2 前收盘：日盘 → 更早交易日收盘；夜盘(≥21点) → 当天日盘收盘（夜盘属于下一个交易日）
const mkBar = (dt, c) => ({ datetime: dt, close: c });
const pc = { daily: [{ date: '2026-10-14', close: 3300 }, { date: '2026-10-15', close: 3316 }, { date: '2026-10-16', close: 3281 }], bars: [] };
eq('日盘：前收盘取更早一个交易日', BW.prevCloseOf(pc, mkBar('2026-10-16 10:00:00', 3290)), 3316);
eq('夜盘：前收盘取当天日盘收盘(3281，不是前天的3316)', BW.prevCloseOf(pc, mkBar('2026-10-16 23:00:00', 3268)), 3281);
eq('夜盘 21:00 也算夜盘', BW.prevCloseOf(pc, mkBar('2026-10-16 21:00:00', 3270)), 3281);
// 日线还没刷新到当天：夜盘用15分钟线里当天日盘最后一根(15:00)顶上
const pc2 = { daily: [{ date: '2026-10-15', close: 3316 }], bars: [mkBar('2026-10-16 14:45:00', 3283), mkBar('2026-10-16 15:00:00', 3281), mkBar('2026-10-16 21:15:00', 3270)] };
eq('夜盘+日线缺当天：用日盘最后一根15分钟线', BW.prevCloseOf(pc2, mkBar('2026-10-16 23:00:00', 3268)), 3281);
// 日盘还没收完(最后一根在14点前)不能当收盘 → 退回日线
const pc3 = { daily: [{ date: '2026-10-15', close: 3316 }], bars: [mkBar('2026-10-16 11:00:00', 3290), mkBar('2026-10-16 21:15:00', 3270)] };
eq('夜盘+日盘数据不全：退回日线最近收盘', BW.prevCloseOf(pc3, mkBar('2026-10-16 21:15:00', 3270)), 3316);
eq('没有任何日线 → null', BW.prevCloseOf({ daily: [], bars: [] }, mkBar('2026-10-16 10:00:00', 3290)), null);

// 3 整体：临时目录里放真实数据，换持仓
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'widget-'));
const cp = (rel) => { const d = path.join(tmp, rel); fs.mkdirSync(path.dirname(d), { recursive: true }); fs.copyFileSync(path.join(ROOT, 'data', rel), d); };
['latest.json', 'main_adj.json', 'prices.json', 'raw/seasonal/M0_daily.csv'].forEach(cp);
const prices = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'prices.json'), 'utf8'));
const run = (pos) => { fs.writeFileSync(path.join(tmp, 'position.json'), JSON.stringify(pos)); return BW.build(tmp, { nowMs: mk(10) }); };

let w = run({ flat: true });
const key = w.contract.key, pk = { sep: 'M09', may: 'M05', jan: 'M01' }[key], lastBar = prices.contracts[pk].bars.slice(-1)[0];
eq('合约 = 10月自动合约', key, 'jan');
eq('价格 = prices.json 对应合约最新一根', w.price.c, +lastBar.close);
eq('价格时间到分钟', w.price.dt, String(lastBar.datetime).slice(0, 16));
eq('空仓 → 无持仓字段', w.position, null);
eq('空仓状态只能是 观望/入场/数据不足', ['wait', 'long', 'short', 'nodata'].includes(w.signal.state), true);
eq('版本号（v4：加基本面 fund；v3 的 chk/fx/lv 仍在）', w.v, 4);
eq('没有 history/systems 文件时 fund 为 null（小组件不画基本面块）', w.fund, null);
{ const d2 = fs.mkdtempSync(path.join(os.tmpdir(), 'wf-')); fs.mkdirSync(path.join(d2, 'history'));
  const P = (d, pd, r, dir) => ({ d, v: r, x: { priceDate: pd, fundDir: dir || '偏空', compDir: '偏多', compRatio: 0.9, confidence: '高' } });   // v102.15：取 v/fundDir（页面「基本面」卡），不取 compRatio（综合）
  fs.writeFileSync(path.join(d2, 'history', 'systems_jan.json'), JSON.stringify({ points: [
    P('2026-10-15', '2026-10-15', -0.10, '中性'), P('2026-10-16', '2026-10-16', -0.20), P('2026-10-19', '2026-10-19', -0.34), P('2026-10-20', '2026-10-20', -0.39),
    P('2026-10-21', '2026-10-21', -0.39), P('2026-10-22', '2026-10-22', -0.28),
    P('2026-10-23', '2026-10-23', -0.2827), P('2026-10-24', '2026-10-23', -0.2827), P('2026-10-25', '2026-10-23', -0.2827)] }));   // 周末重复记录，按交易日合并
  const F = BW.readFund(d2, 'jan');
  eq('readFund：基本面方向/倾向/置信度，取最后一条（不是综合 compRatio=0.9）', [F.comp, F.cp, F.conf, F.d], ['偏空', -28, '高', '2026-10-25']);
  eq('readFund：较上一交易日 = −28−(−28) = 0；较5个交易日前（10-16 的 −20）= −28−(−20) = −8', [F.c1, F.c5], [0, -8]);
  eq('readFund：上一交易日方向', F.pd, '偏空');
  eq('readFund 合约文件不存在 → null', BW.readFund(d2, 'may'), null); }
if (w.signal.en) eq('signal.en 含建议手数/占用/止损亏（有账户权益时）', [typeof w.signal.en.lots, w.signal.en.lots >= 0], ['number', true]);
{ const hs = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'history', 'systems_' + w.contract.key + '.json'), 'utf8')).points; const last = hs[hs.length - 1];
  if (w.fund && last && last.v != null) eq('小组件基本面 = 仪表盘基本面卡同一个数(快照 v)', w.fund.cp, Math.round(last.v * 100)); }
eq('文件很小(<2KB)', JSON.stringify(w).length < 2048, true);
{ const c = w.signal.chk, A = require(path.join(ROOT, 'scripts', 'plan_alert.js')).compute(tmp, { nowMs: mk(10), prices, position: { flat: true } });
  eq('chk 做多4条/做空3条，每项 [ok,值]', [c.L.length, c.S.length, c.L.every(x => x.length === 2), c.S.every(x => x.length === 2)], [4, 3, true, true]);
  eq('chk 做多四条 = lowOK/confirm/非去杠杆/基差', c.L.map(x => x[0]), [A.sig.lowOK ? 1 : 0, A.sig.confirm ? 1 : 0, A.sig.delev ? 0 : 1, A.basis.v == null ? null : (A.basis.v >= 0 ? 1 : 0)]);
  eq('chk 做空三条 = 去杠杆/收盘<MA20/分位≥70', c.S.map(x => x[0]), [A.sig.delev ? 1 : 0, A.sig.below20 ? 1 : 0, A.sig.highOK ? 1 : 0]);
  eq('chk 与 signal.longOK 一致：四条全满足 ⇔ 做多', c.L.every(x => x[0] !== 0), !!A.sig.longOK);
  eq('fx = 最弱外资席位5日变化 + 去杠杆线 -20000', [w.signal.fx.v, w.signal.fx.line], [Math.round(A.fsum), -20000]);
  eq('数据等级 lv 取自 gate.level', w.signal.lv, A.gate.level); }

if (w.signal.state === 'long' || w.signal.state === 'short') {   // v102.14 有信号时：限价=收盘价回调/反弹0.3%，止损/启动价从限价算
  const sg = w.signal.state === 'long' ? 1 : -1, e = w.signal.en;
  eq('signal.en 限价 = 收盘价×(1∓0.3%)', e.lim, Math.round(w.signal.ref * (1 - sg * 0.003)), 1);
  eq('signal.en 止损 = 限价×(1∓4%)；signal.stop 同值', [e.stop, w.signal.stop], [Math.round(e.lim * (1 - sg * 0.04)), e.stop], 1);
  eq('signal.en 启动价 = 限价×(1±8%)', e.act, Math.round(e.lim * (1 + sg * 0.08)), 1);
} else eq('无信号时 signal.en=null', w.signal.en, null);
const px = w.signal.ref;   // 信号用的收盘参考价(换月调整价)
const sym = w.contract.symbol;
// 多单：开仓日取近半年里一个比现价低很多的日子，浮盈远超启动价8%（注意：开仓价和当天收盘差>2%会被页面逻辑按换月折算，所以必须用真实历史收盘价）
const rows = fs.readFileSync(path.join(ROOT, 'data', 'raw', 'seasonal', 'M0_daily.csv'), 'utf8').trim().split('\n').slice(1).map(l => l.split(','));
const lastClose = +rows[rows.length - 1][4], lowRow = rows.slice(-120).find(r => +r[4] <= lastClose * 0.88) || [rows[rows.length - 120][0], 0, 0, 0, lastClose * 0.85];   // 近120日没有比现价低12%的日子时（行情上涨后会这样）用一个合成的低位开仓价，测试不依赖当天行情
w = run({ side: 1, lots: 10, entryD: lowRow[0], entryPx: +lowRow[4], contract: sym });
eq('多单浮盈远超启动价 → 有移动止损线', typeof w.position.trail, 'number');
eq('多单移动止损线在开仓价上方(已锁盈)', w.position.trail > w.position.entryPx, true);
eq('持仓有动作字段', typeof w.position.action, 'string');
eq('该平/持有 与 动作一致', w.position.action === '持有' ? w.signal.state === 'hold' : (w.signal.state === 'exit' && w.signal.label === '该平：' + w.position.action), true);
// 多单亏损：开在比现价高10%且开仓日附近不存在这个价 → 被页面逻辑折算，不在此断言；改测止损价公式
w = run({ side: -1, lots: 1, entryD: '2026-10-09', entryPx: 3386, contract: sym });
eq('持仓止损价 = 开仓价×1.04(空单)', w.position.stop, Math.round(3386 * 1.04));
eq('没到启动价 → 无移动止损', w.position.trail, null);

w = run({ side: -1, lots: 5, entryD: '2026-10-09', entryPx: 3386, contract: sym });   // 空单(开仓价3386)，当前价更低 → 浮盈为正
eq('空单浮盈 → r 为正', w.position.r > 0, true);

// v102.25 待操作 need + 确认 ack
{
  const wl = run({ side: 1, lots: 10, entryD: lowRow[0], entryPx: +lowRow[4], contract: sym });
  const nd = wl.position.need;
  if (wl.position.action === '持有') {
    eq('多单浮盈远超启动价且未触发平仓 → need.k=trail', nd && nd.k, 'trail');
    eq('trail need：止损线价 = position.trail', nd && nd.px, wl.position.trail);
    eq('trail need：key 拼法 trail|开仓日|开仓价|止损线', nd && nd.key, 'trail|' + wl.position.entryD + '|' + wl.position.entryPx + '|' + wl.position.trail);
    eq('没有 ack.json → acked=false', nd && nd.acked, false);
    fs.writeFileSync(path.join(tmp, 'ack.json'), JSON.stringify({ soy: { key: nd.key, at: '2026-10-29T08:00:00Z' } }));
    eq('ack.json 的 key 对上 → acked=true', BW.build(tmp, { nowMs: mk(10) }).position.need.acked, true);
    fs.writeFileSync(path.join(tmp, 'ack.json'), JSON.stringify({ soy: { key: 'trail|旧|旧|1', at: '2026-10-29T08:00:00Z' } }));
    eq('ack 的是旧止损线 → 仍未确认（止损线上移要再提醒）', BW.build(tmp, { nowMs: mk(10) }).position.need.acked, false);
    fs.unlinkSync(path.join(tmp, 'ack.json'));
  } else {
    eq('多单已到离场条件 → need.k=exit', nd && nd.k, 'exit');
    eq('exit need：key 含动作', nd && nd.key, 'exit|' + wl.position.entryD + '|' + wl.position.entryPx + '|' + wl.position.action);
  }
}
{
  const TP = { ACT: 8, TRAIL: 4 };
  eq('needOf：有离场动作 → exit，优先于移动止损', BW.needOf(1, '2026-10-12', 3400, '移动止盈', 9, TP), { k: 'exit', key: 'exit|2026-10-12|3400|移动止盈', head: '平仓', sub: '移动止盈' });
  eq('needOf：多单峰值+9% → 止损线=peak×0.96', BW.needOf(1, '2026-10-12', 3400, '持有', 9, TP).px, Math.round(3400 * 1.09 * 0.96));
  eq('needOf：空单峰值+9%（价格跌9%）→ 止损线=peak×1.04', BW.needOf(-1, '2026-10-12', 3400, '持有', 9, TP).px, Math.round(3400 * (1 - 0.09) * 1.04));
  eq('needOf：没到启动价、没动作 → null', BW.needOf(1, '2026-10-12', 3400, '持有', 5, TP), null);
}

// v101.84 基差：compute() 带出基差，小组件的「why」用同一份 planWhy
{ const PA = require(path.join(ROOT, 'scripts', 'plan_alert.js')), L = JSON.parse(fs.readFileSync(path.join(tmp, 'latest.json'), 'utf8'));
  fs.writeFileSync(path.join(tmp, 'position.json'), JSON.stringify({ flat: true }));
  const A = PA.compute(tmp, { nowMs: mk(10), prices });
  if (L.spotBasis && L.spotBasis.available) {
    eq('基差 = 生意社现货 ÷ 主力合约 − 1', Math.abs(A.basis.v - (L.spotBasis.spot / L.spotBasis.domPrice - 1)) < 1e-12, true);
    eq('sig 里带基差（planWhy 写原因要用）', A.sig.basis, A.basis.v);
  }
  eq('planWhy：被基差拦下时写原因（小组件 why 同一函数）', PA.loadPlan().planWhy({ basisBlocked: true, basis: -0.0123 }).includes('期货高于现货（基差 -1.23%）'), true);
  const L2 = Object.assign({}, L, { spotBasis: { available: false, reason: '断网' } }); fs.writeFileSync(path.join(tmp, 'latest.json'), JSON.stringify(L2));
  const A2 = PA.compute(tmp, { nowMs: mk(10), prices });
  eq('没有基差 → 不过滤（basisOK 不出现），信号和以前一样', [A2.basis.v, A2.sig.basisOK, A2.side], [null, undefined, A.sig.basisOK === false && A.sig.basisBlocked ? A2.side : A.side]);
  fs.writeFileSync(path.join(tmp, 'latest.json'), JSON.stringify(L)); }

// 数据缺失：没有 latest.json → gate 不通过，状态 nodata（不能硬给观望）
fs.unlinkSync(path.join(tmp, 'latest.json'));
w = run({ flat: true });
eq('缺外资数据 → 数据不足', w.signal.state, 'nodata');
eq('数据不足时带原因', w.signal.why.length > 0, true);
eq('数据不足时不给打勾表（外资数据缺失时条件不可信）', [w.signal.chk, w.signal.lv], [null, 'bad']);


// 4 橡胶部分：account.json 的未平仓 ruTrades → ru.position；3月出反弹信号/持仓状态；小组件里的止损% 和 cockpit/rubber.js 一致
{
  const src = fs.readFileSync(path.join(ROOT, 'cockpit', 'rubber.js'), 'utf8'); const m = /STOP:\s*([\d.]+)/.exec(src);
  eq('橡胶止损% 与 rubber.js 的 RUP.STOP 一致', BW.RA_STOP, +m[1]);
  ['ru_live.json', 'ru_ind_auto.json', 'ru_policy.json'].forEach(cp);
  const nowMar = Date.UTC(2026, 2, 12, 5, 0, 0);
  fs.writeFileSync(path.join(tmp, 'account.json'), JSON.stringify({ init: 1e6, ruTrades: [{ id: 'a', side: -1, lots: 3, entryD: '2026-03-04', entryPx: 17200, contract: 'RU2605' }] }));
  const r1 = BW.buildRu(tmp, nowMar);
  eq('有未平仓橡胶单 → ru.position 带手数/开仓价/止损价', [r1.position.lots, r1.position.entryPx, r1.position.stop, r1.position.side], [3, 17200, 18060, -1]);
  eq('有橡胶持仓 → act 是 hold 或 exit，不是 wait/go', ['hold', 'exit'].includes(r1.act), true);
  fs.writeFileSync(path.join(tmp, 'account.json'), JSON.stringify({ init: 1e6, ruTrades: [{ id: 'a', side: -1, lots: 3, entryD: '2026-03-04', entryPx: 17200, exitD: '2026-03-10', exitPx: 17000 }] }));
  eq('已平仓的单不算持仓', BW.buildRu(tmp, nowMar).position, null);
  fs.unlinkSync(path.join(tmp, 'account.json'));
  eq('没有 account.json 也不报错，持仓为空', BW.buildRu(tmp, nowMar).position, null);
  eq('10月不在3月窗口 → act=wait（不出信号）', BW.buildRu(tmp, mk(10)).act, 'wait');
  fs.unlinkSync(path.join(tmp, 'ru_live.json')); const ro = BW.buildRu(tmp, mk(10));
  eq('橡胶价格就是 ru_hist 最后一根（缺 ru_live 也能出）', ro && ro.price != null, true);
  eq('widget.json 版本=4，含 ru', [BW.build(tmp, { nowMs: mk(10) }).v, 'ru' in BW.build(tmp, { nowMs: mk(10) })], [4, true]);
}
fs.rmSync(tmp, { recursive: true, force: true });
console.log(`\n结果：${pass}项通过，${fail}项失败`); process.exit(fail ? 1 : 0);
