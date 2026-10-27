#!/usr/bin/env node
/* 交易提醒：用页面同一份纯函数（cockpit/ui.js 里 PLAN_BEGIN…PLAN_END）算「入场信号 / 持仓离场 / 数据不足」，输出 JSON 给 notify.py 去发。
 * 逻辑只有一份：页面和提醒不可能算出两个结论。tests/e2e_cockpit.py 里有一致性测试（同一份数据，页面的 planSnap 和这里必须一样）。
 *   node scripts/plan_alert.js --data data --position data/position.json --out /tmp/alert.json [--today 2026-10-12]
 * 输入：data/latest.json（外资席位 5 日变化、spotBasis 生意社基差）、data/raw/seasonal/M0_daily.csv（原始主连）、data/main_adj.json（换月调整价）、data/position.json（可选：你的持仓）。 */
'use strict';
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, '..');
const CL = require(path.join(ROOT, 'cockpit', 'loader.js'));

function loadPlan() {
  const src = fs.readFileSync(path.join(ROOT, 'cockpit', 'ui.js'), 'utf8');
  const a = src.indexOf('/* PLAN_BEGIN'), b = src.indexOf('/* PLAN_END */');
  if (a < 0 || b < 0) throw new Error('ui.js 里找不到 PLAN_BEGIN/PLAN_END 标记');
  return new Function(src.slice(a, b) + '\nreturn {TPLAN,planEntry,planSignals,planBasis,planForeign,planManage,planGate,planHold,planWhy,planTier,planSize};')();
}
const readJson = p => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (_) { return null; } };
const readText = p => { try { return fs.readFileSync(p, 'utf8'); } catch (_) { return ''; } };
const beijingToday = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
const f0 = n => Math.round(n).toLocaleString('en-US'), f2 = n => (n >= 0 ? '+' : '−') + Math.abs(Math.round(n)).toLocaleString('en-US');

/* 持仓文件：{side:1|-1, lots, entryD, entryPx}；flat:true 或缺字段 = 空仓 */
function normPosition(p) {
  if (!p || p.flat) return null;
  const side = +p.side >= 0 ? (+p.side === 0 ? 0 : 1) : -1, lots = +p.lots, px = +p.entryPx, d = String(p.entryD || '').slice(0, 10);
  if (!side || !(lots >= 1) || !(px > 0) || !/^\d{4}-\d{2}-\d{2}$/.test(d)) return null;
  return { side, lots, entryPx: px, entryD: d };
}

function compute(dataDir, opts) {
  opts = opts || {};
  const P = loadPlan(), TP = P.TPLAN, today = opts.today || beijingToday();
  const latest = readJson(path.join(dataDir, 'latest.json')) || {};
  const hist = CL.histFromCsv(readText(path.join(dataDir, 'raw', 'seasonal', 'M0_daily.csv')), '2015-04-03');
  let adj = CL.adjFrom(readJson(path.join(dataDir, 'main_adj.json')), hist);
  if (adj) {   // 和页面同一个逻辑：用刚收盘的日线（latest.json 的日K、prices.json 的 daily）把价格序列接到最新一天
    const nowMs = opts.nowMs || Date.now(), pj = opts.prices || readJson(path.join(dataDir, 'prices.json')) || {};
    const SRC = [['dceM09Daily', 'M09'], ['dceM05Daily', 'M05'], ['dceM01Daily', 'M01']];
    for (const [lk, pk] of SRC) {
      const lb = (latest[lk] || {}), sym = lb.symbol, pc = (pj.contracts || {})[pk] || {};
      const bars = (lb.bars || []).map(b => ({ d: b.date, c: b.close })).concat(pc.symbol && sym && String(pc.symbol).toLowerCase() === String(sym).toLowerCase() ? (pc.daily || []).map(b => ({ d: b.date, c: b.close })) : []);
      const MK = { M09: 'dceM09Min15', M05: 'dceM05Min15', M01: 'dceM01Min15' }, HK = { M09: 'dceM09Hourly', M05: 'dceM05Hourly', M01: 'dceM01Hourly' }, same = pc.symbol && sym && String(pc.symbol).toLowerCase() === String(sym).toLowerCase();
      const prov = CL.provDaily((latest[MK[pk]] || {}).bars, (latest[HK[pk]] || {}).bars, same ? pc.bars : null);
      const nx = CL.extendAdj(adj, prov.concat(bars), sym, nowMs); if (nx !== adj) { adj = nx; break; }
    }
  }
  const h = adj || hist, cs = h.c;
  const F = P.planForeign(latest.marketCapital && latest.marketCapital.members);
  const lastD = h.d.length ? h.d[h.d.length - 1] : null;
  const gate = P.planGate(F.used, lastD, today, { missing: F.missing, approx: F.approx, fD: F.lastD, adj: !!adj });
  const B = P.planBasis(latest.spotBasis, lastD);   // v101.84：做多第④条，取不到 → B.v=null → 原规则
  const sig = cs.length >= 11 ? P.planSignals(cs, F.min, B.v) : { pct: null, ma20: null, ma60: null, confirm: false, delev: false, lowOK: false, trendDn: false, below20: false, highOK: false, longOK: false, shortOK: false };
  const side = gate.ok ? (sig.longOK ? 1 : sig.shortOK ? -1 : 0) : 0;
  const px = cs.length ? cs[cs.length - 1] : null;
  const pos = normPosition(opts.position);
  let hold = null, mg = null;
  if (pos && h.d.length) { hold = P.planHold(h, pos); mg = P.planManage({ side: pos.side, entry: pos.entryPx, peak: hold.peak, last: hold.last, ma20: sig.ma20 == null ? null : sig.ma20 * hold.k, fsum: F.min, fall: F.sum }); }
  const ev = [], sd = pos ? (pos.side > 0 ? '多' : '空') : '';
  const tail = '\n\n（提醒按收盘后的数据算；入场挂限价单、平仓开盘市价，都在下一个交易日。手数、止损价、账户权益请打开驾驶舱看。）';
  if (!gate.ok) ev.push({ type: 'gate', key: 'gate|' + today, title: '【豆粕】数据不足，信号暂停', body: '信号和离场判断暂时不可信：' + gate.reasons.join('；') + '。\n先别按页面上的信号操作，检查 Actions 是否正常运行。' });
  if (side !== 0 && !pos) {
    const en = P.planEntry(px, side);
    ev.push({ type: 'entry', side, key: 'entry|' + lastD + '|' + side, title: '【豆粕】' + (side > 0 ? '做多' : '做空') + '入场信号（数据日 ' + lastD + '）',
      body: P.planWhy(sig) + '。\n价格分位 ' + (sig.pct == null ? '—' : sig.pct.toFixed(0) + '%') + '，外资最弱席位 ' + F.minK + ' 5日 ' + f2(F.min) + ' 手，' + (B.v == null ? '基差无数据（不过滤）' : '基差 ' + (B.v >= 0 ? '+' : '') + (B.v * 100).toFixed(2) + '%（生意社 ' + B.d.slice(5) + '）') + '，收盘参考价 ' + f0(px) + '。\n建议：下一个交易日挂限价单——' + (side > 0 ? '做多 ≤ ' : '做空 ≥ ') + f0(en.lim) + '（信号日收盘价 ' + f0(en.close) + (side > 0 ? ' 回调 ' : ' 反弹 ') + TP.LIM.pct + '%，成交率约 ' + TP.LIM.fill + '%；想更容易成交可挂 ' + f0(en.close) + '，成交率约 ' + TP.LIM.closeFill + '%），当日有效，没成交就作废、不追；' + (side > 0 ? '低开' : '高开') + '跳空按开盘价成交。\n止损价 ' + f0(en.stop) + '（入场价 ' + TP.STOP + '%）；移动止盈启动价 ' + f0(en.act) + '（浮盈 ' + TP.ACT + '%），到了就把固定止损改成移动止损，初始约 ' + f0(en.trailAtAct) + '（从' + (side > 0 ? '最高' : '最低') + '价回落 ' + TP.TRAIL + '%），之后每多赚 0.5% 把止损上移一次，触及平仓。' + tail });
  }
  if (pos && mg && mg.action !== '持有') {
    ev.push({ type: 'exit', key: 'exit|' + lastD + '|' + pos.entryD + '|' + mg.action, title: '【豆粕】持仓该平了：' + mg.action + '（' + sd + pos.lots + '手）',
      body: '你的持仓：' + sd + ' ' + pos.lots + ' 手 @' + f0(pos.entryPx) + '（' + pos.entryD + '）。\n信号：' + mg.action + '。浮盈亏 ' + (mg.r >= 0 ? '+' : '') + mg.r.toFixed(1) + '%，持仓期间最高浮盈 ' + mg.peakR.toFixed(1) + '%，外资最弱席位 ' + F.minK + ' 5日 ' + f2(F.min) + ' 手。\n建议：下一个交易日开盘平仓；平仓后记得在 GitHub Actions 里「记录持仓」点平仓，否则明天还会提醒。' + tail });
  }
  /* v101.42 动态提示：持仓时的止损管理。
   *   ① 价格涨到启动价（浮盈 ACT%）→ 提醒「把固定止损改成移动止损」并给出新的止损价（= 持仓最高价回落 TRAIL%）；
   *   ② 之后每创新高、止损线又上移 0.5%（按开仓价算）→ 提醒「把止损上移到 X」；
   *   ③ 价格离止损价/移动止损线 ≤1% 提醒；盘中价已触及线也提醒（只预警，是否平仓以收盘结论为准）。
   * 最高价取收盘序列和当天15分钟线的最高/最低价的更极端者；线和回测、页面是同一个公式。 */
  if (pos && mg && hold && mg.action === '持有') {
    const sg = pos.side, last = hold.last, k = hold.k || 1, NEAR = 1, f1 = n => Math.round(n * 10) / 10;
    const pr = opts.prices && opts.prices.contracts && opts.prices.contracts[opts.contract || 'M01'], bars = pr && pr.bars ? pr.bars.filter(b => b && b.close != null && String(b.datetime).slice(0, 10) > lastD) : [];
    const lb = bars.length ? bars[bars.length - 1] : null, lp = lb ? +lb.close * k : null;
    let peak = hold.peak; bars.forEach(b => { const x = (sg > 0 ? +(b.high != null ? b.high : b.close) : +(b.low != null ? b.low : b.close)) * k; peak = sg > 0 ? Math.max(peak, x) : Math.min(peak, x); });
    const stopPx = pos.entryPx * (1 - sg * TP.STOP / 100), actPx = pos.entryPx * (1 + sg * TP.ACT / 100), peakR = sg * (peak / pos.entryPx - 1) * 100, on = peakR >= TP.ACT;
    const trig = peak * (1 - sg * TP.TRAIL / 100), trigAct = actPx * (1 - sg * TP.TRAIL / 100), step = pos.entryPx * 0.005, dirw = sg > 0 ? '跌破' : '涨过';
    const head = sd + pos.lots + '手 @' + f0(pos.entryPx), lock = sg * (trig / pos.entryPx - 1) * 100, gap = (v, p) => Math.abs((v / p - 1) * 100);
    const note = '\n（回测按收盘价判断；若你在期货公司挂的是盘中条件单，会比回测更容易被短暂波动洗出，可改成收盘后手动判断。）';
    if (on) {
      ev.push({ type: 'act', key: 'act|' + pos.entryD, title: '【豆粕】已到启动价 ' + f0(actPx) + '：止损改成移动止损（' + head + '）',
        body: '浮盈已到 ' + peakR.toFixed(1) + '%（≥' + TP.ACT + '%），按策略把固定止损改成移动止损。\n建议止损价：' + f0(trig) + '（' + (sg > 0 ? '最高 ' : '最低 ') + f0(peak) + ' 回落 ' + TP.TRAIL + '%，' + (lock >= 0 ? '锁住约 +' : '仍亏约 ') + Math.abs(lock).toFixed(1) + '%）；原固定止损 ' + f0(stopPx) + ' 作废。\n之后每创新高，止损线上移，我再提醒你。' + note });
      const b = sg * (trig - trigAct) / step | 0;   // 比刚启动时又上移了几格（每格 0.5% 开仓价）
      if (b >= 1) ev.push({ type: 'trail', key: 'trail|' + pos.entryD + '|' + b, title: '【豆粕】止损上移到 ' + f0(trig) + '（' + head + '）',
        body: '持仓期间' + (sg > 0 ? '最高 ' : '最低 ') + f0(peak) + '（最高浮盈 ' + peakR.toFixed(1) + '%）。把止损改到 ' + f0(trig) + '，锁住约 ' + (lock >= 0 ? '+' : '') + lock.toFixed(1) + '%。\n现价 ' + f0(lp != null ? lp : last) + '，距止损线 ' + gap(trig, lp != null ? lp : last).toFixed(1) + '%。线只往有利方向走，不会回退。' + note });
    } else if (gap(actPx, lp != null ? lp : last) <= NEAR) {
      ev.push({ type: 'near', key: 'nearact|' + pos.entryD + '|' + (lb ? String(lb.datetime).slice(0, 10) : lastD), title: '【豆粕】快到移动止损启动价 ' + f0(actPx) + '（' + head + '）',
        body: '现价 ' + f0(lp != null ? lp : last) + '，到 ' + f0(actPx) + '（浮盈 ' + TP.ACT + '%）就把固定止损改成移动止损，届时我再给你新的止损价（约 ' + f0(trigAct) + '）。当前止损价 ' + f0(stopPx) + '。' });
    }
    const cur = lp != null ? lp : last, lines = [{ n: '止损价', v: stopPx, id: 'stop' }]; if (on) { lines.length = 0; lines.push({ n: '移动止损线', v: trig, id: 'trail' }); }
    lines.forEach(L => {
      const hit = sg > 0 ? cur <= L.v : cur >= L.v, td = lb ? String(lb.datetime).slice(0, 10) : lastD;
      if (lb && hit) ev.push({ type: 'touch', key: 'touch|' + pos.entryD + '|' + L.id + '|' + td, title: '【豆粕】盘中已' + dirw + L.n + '（' + head + '）',
        body: '盘中价 ' + f0(cur) + '（' + String(lb.datetime).slice(5, 16) + '）已' + dirw + L.n + ' ' + f0(L.v) + '。\n结论按收盘：收盘还在线' + (sg > 0 ? '下' : '上') + '才平仓，系统会在收盘后再提醒。想提前走由你决定。' });
      else if (!hit && gap(L.v, cur) <= NEAR) ev.push({ type: 'near', key: 'near|' + pos.entryD + '|' + L.id + '|' + td, title: '【豆粕】离' + L.n + '只剩 ' + gap(L.v, cur).toFixed(1) + '%（' + head + '）',
        body: L.n + ' ' + f0(L.v) + '，' + (lb ? '盘中价 ' : '收盘价 ') + f0(cur) + '。' });
    });
  }
  return { today, priceDate: lastD, adj: !!adj, px, side, gate: { ok: gate.ok, level: gate.level, reasons: gate.reasons, warn: gate.warn }, fsum: F.min, fsumAll: F.sum, foreign: F.parts,
           sig: { pct: sig.pct, confirm: sig.confirm, delev: sig.delev, lowOK: sig.lowOK, below20: !!sig.below20, highOK: !!sig.highOK, trendDn: sig.trendDn, longOK: sig.longOK, shortOK: sig.shortOK, basisOK: sig.basisOK, basisBlocked: !!sig.basisBlocked, contangoShort: !!sig.contangoShort, basis: sig.basis },
           basis: B,
           position: pos, manage: mg ? { action: mg.action, r: mg.r, peakR: mg.peakR } : null, events: ev };
}

function main(argv) {
  const a = {}; for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) a[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  const dataDir = a.data || 'data', out = compute(dataDir, { today: a.today, nowMs: a.now ? +a.now : undefined, position: readJson(a.position || path.join(dataDir, 'position.json')), prices: readJson(a.prices || path.join(dataDir, 'prices.json')), contract: a.contract });
  const txt = JSON.stringify(out, null, 1);
  if (a.out) fs.writeFileSync(a.out, txt); else console.log(txt);
  console.error(`[提醒] 价格日 ${out.priceDate} · ${out.gate.ok ? '数据可用' : '数据不足'} · 入场信号 ${out.side || '无'} · 持仓 ${out.position ? (out.position.side > 0 ? '多' : '空') + out.position.lots + '手' : '空仓'} · 事件 ${out.events.length} 个`);
}
if (require.main === module) main(process.argv.slice(2));
module.exports = { compute, normPosition, loadPlan };
