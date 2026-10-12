#!/usr/bin/env node
/* 交易提醒：用页面同一份纯函数（cockpit/ui.js 里 PLAN_BEGIN…PLAN_END）算「入场信号 / 持仓离场 / 数据不足」，输出 JSON 给 notify.py 去发。
 * 逻辑只有一份：页面和提醒不可能算出两个结论。tests/e2e_cockpit.py 里有一致性测试（同一份数据，页面的 planSnap 和这里必须一样）。
 *   node scripts/plan_alert.js --data data --position data/position.json --out /tmp/alert.json [--today 2026-10-12]
 * 输入：data/latest.json（外资席位 5 日变化）、data/raw/seasonal/M0_daily.csv（原始主连）、data/main_adj.json（换月调整价）、data/position.json（可选：你的持仓）。 */
'use strict';
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, '..');
const CL = require(path.join(ROOT, 'cockpit', 'loader.js'));

function loadPlan() {
  const src = fs.readFileSync(path.join(ROOT, 'cockpit', 'ui.js'), 'utf8');
  const a = src.indexOf('/* PLAN_BEGIN'), b = src.indexOf('/* PLAN_END */');
  if (a < 0 || b < 0) throw new Error('ui.js 里找不到 PLAN_BEGIN/PLAN_END 标记');
  return new Function(src.slice(a, b) + '\nreturn {TPLAN,planSignals,planForeign,planManage,planGate,planHold,planWhy,planTier,planSize};')();
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
  const adj = CL.adjFrom(readJson(path.join(dataDir, 'main_adj.json')), hist);
  const h = adj || hist, cs = h.c;
  const F = P.planForeign(latest.marketCapital && latest.marketCapital.members);
  const lastD = h.d.length ? h.d[h.d.length - 1] : null;
  const gate = P.planGate(F.used, lastD, today, { missing: F.missing, approx: F.approx, fD: F.lastD, adj: !!adj });
  const sig = cs.length >= 11 ? P.planSignals(cs, F.sum) : { pct: null, ma20: null, ma60: null, confirm: false, delev: false, lowOK: false, trendDn: false, longOK: false, shortOK: false };
  const side = gate.ok ? (sig.longOK ? 1 : sig.shortOK ? -1 : 0) : 0;
  const px = cs.length ? cs[cs.length - 1] : null;
  const pos = normPosition(opts.position);
  let hold = null, mg = null;
  if (pos && h.d.length) { hold = P.planHold(h, pos); mg = P.planManage({ side: pos.side, entry: pos.entryPx, peak: hold.peak, last: hold.last, ma20: sig.ma20 == null ? null : sig.ma20 * hold.k, fsum: F.sum }); }
  const ev = [], sd = pos ? (pos.side > 0 ? '多' : '空') : '';
  const tail = '\n\n（提醒按收盘后的数据算；操作在下一个交易日开盘。手数、止损价、账户权益请打开驾驶舱看。）';
  if (!gate.ok) ev.push({ type: 'gate', key: 'gate|' + today, title: '【豆粕】数据不足，信号暂停', body: '信号和离场判断暂时不可信：' + gate.reasons.join('；') + '。\n先别按页面上的信号操作，检查 Actions 是否正常运行。' });
  if (side !== 0 && !pos) {
    const stop = px * (1 - side * TP.STOP / 100);
    ev.push({ type: 'entry', side, key: 'entry|' + lastD + '|' + side, title: '【豆粕】' + (side > 0 ? '做多' : '做空') + '入场信号（数据日 ' + lastD + '）',
      body: P.planWhy(sig) + '。\n价格分位 ' + (sig.pct == null ? '—' : sig.pct.toFixed(0) + '%') + '，外资5日 ' + f2(F.sum) + ' 手，收盘参考价 ' + f0(px) + '。\n建议：下一个交易日开盘价入场；止损 ' + TP.STOP + '%（约 ' + f0(stop) + '）；浮盈 ≥' + TP.ACT + '% 后从' + (side > 0 ? '最高' : '最低') + '价回落 ' + TP.TRAIL + '% 平仓。' + tail });
  }
  if (pos && mg && mg.action !== '持有') {
    ev.push({ type: 'exit', key: 'exit|' + lastD + '|' + pos.entryD + '|' + mg.action, title: '【豆粕】持仓该平了：' + mg.action + '（' + sd + pos.lots + '手）',
      body: '你的持仓：' + sd + ' ' + pos.lots + ' 手 @' + f0(pos.entryPx) + '（' + pos.entryD + '）。\n信号：' + mg.action + '。浮盈亏 ' + (mg.r >= 0 ? '+' : '') + mg.r.toFixed(1) + '%，持仓期间最高浮盈 ' + mg.peakR.toFixed(1) + '%，外资5日 ' + f2(F.sum) + ' 手。\n建议：下一个交易日开盘平仓；平仓后记得在 GitHub Actions 里「记录持仓」点平仓，否则明天还会提醒。' + tail });
  }
  return { today, priceDate: lastD, adj: !!adj, px, side, gate: { ok: gate.ok, level: gate.level, reasons: gate.reasons, warn: gate.warn }, fsum: F.sum, foreign: F.parts,
           sig: { pct: sig.pct, confirm: sig.confirm, delev: sig.delev, lowOK: sig.lowOK, trendDn: sig.trendDn, longOK: sig.longOK, shortOK: sig.shortOK },
           position: pos, manage: mg ? { action: mg.action, r: mg.r, peakR: mg.peakR } : null, events: ev };
}

function main(argv) {
  const a = {}; for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) a[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  const dataDir = a.data || 'data', out = compute(dataDir, { today: a.today, position: readJson(a.position || path.join(dataDir, 'position.json')) });
  const txt = JSON.stringify(out, null, 1);
  if (a.out) fs.writeFileSync(a.out, txt); else console.log(txt);
  console.error(`[提醒] 价格日 ${out.priceDate} · ${out.gate.ok ? '数据可用' : '数据不足'} · 入场信号 ${out.side || '无'} · 持仓 ${out.position ? (out.position.side > 0 ? '多' : '空') + out.position.lots + '手' : '空仓'} · 事件 ${out.events.length} 个`);
}
if (require.main === module) main(process.argv.slice(2));
module.exports = { compute, normPosition, loadPlan };
