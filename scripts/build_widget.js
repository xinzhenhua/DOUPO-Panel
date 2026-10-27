#!/usr/bin/env node
/* iOS 小组件数据（v101.82；v3 起加逐条入场条件 chk / 外资离去杠杆线 fx / 数据等级 lv；v4 加基本面综合 fund）：把「当前交易合约的价格 + 入场/离场信号 + 持仓」压成一个很小的 data/widget.json，给手机桌面小组件读。
 * 逻辑只有一份：信号直接调 scripts/plan_alert.js 的 compute()（它又用页面同一份 PLAN 纯函数），小组件和驾驶舱不可能算出两个结论。
 *   node scripts/build_widget.js --data data --out data/widget.json [--now 2026-10-16T05:00:00Z]
 * 交易合约 = 驾驶舱 autoKey() 的同一规则：北京时间当前月份 ∈ recommendedMonths（4-7→5月合约，12-3→1月合约，8-11→9月… 以 cockpit/static.json 为准）。 */
'use strict';
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, '..');
const PA = require('./plan_alert.js');
const RA = require('./ru_alert.js');

const readJson = p => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (_) { return null; } };
const bj = ms => new Date(ms + 8 * 3600e3);
const PK = { sep: 'M09', may: 'M05', jan: 'M01' };
const NAME = { sep: '9月合约', may: '5月合约', jan: '1月合约' };

/* 和 cockpit/ui.js 的 autoKey 同一规则 */
function autoKey(ctx, nowMs) {
  const m = bj(nowMs).getUTCMonth() + 1;
  for (const k of ['sep', 'may', 'jan']) if (((ctx[k] || {}).recommendedMonths || []).includes(m)) return k;
  return 'sep';
}

/* 前收盘（和驾驶舱同口径：收盘价，不是结算价）。
 * 夜盘（21:00–23:00）属于「下一个交易日」，所以夜盘里的前收盘 = 同一个日历日的日盘收盘；
 * 日盘里的前收盘 = 更早一个交易日的收盘。
 * 日线里还没有当天（收盘后任务还没刷新）时，用 15 分钟线里当天日盘最后一根的收盘价顶上，不能退回到前天的收盘（会差出一整天的涨跌）。 */
function prevCloseOf(pc, bar) {
  const dt = String(bar.datetime), day = dt.slice(0, 10), hh = +dt.slice(11, 13), night = hh >= 21;
  const d = (pc.daily || []).filter(b => b && b.close != null && (night ? String(b.date) <= day : String(b.date) < day));
  const last = d.length ? d[d.length - 1] : null;
  if (!night) return last ? +last.close : null;
  if (last && String(last.date) === day) return +last.close;
  const dayBars = (pc.bars || []).filter(b => b && b.close != null && String(b.datetime).slice(0, 10) === day && +String(b.datetime).slice(11, 13) < 21);
  if (dayBars.length && +String(dayBars[dayBars.length - 1].datetime).slice(11, 13) >= 14) return +dayBars[dayBars.length - 1].close;   // 日盘最后一根在14点以后才算收完
  return last ? +last.close : null;
}

function build(dataDir, opts) {
  opts = opts || {};
  const nowMs = opts.nowMs || Date.now();
  const stat = readJson(path.join(ROOT, 'cockpit', 'static.json')) || {};
  const key = autoKey(stat.ctx || {}, nowMs);
  const prices = readJson(path.join(dataDir, 'prices.json')) || {};
  const pc = (prices.contracts || {})[PK[key]] || {};
  const bars = (pc.bars || []).filter(b => b && b.close != null);
  const lb = bars.length ? bars[bars.length - 1] : null;
  const lastBarDate = lb ? String(lb.datetime).slice(0, 10) : null;
  const prev = lb ? prevCloseOf(pc, lb) : null;

  const A = PA.compute(dataDir, { nowMs, position: readJson(path.join(dataDir, 'position.json')), prices });
  const TP = PA.loadPlan().TPLAN;

  /* 一句话状态：数据不足 > 持仓(离场/持有) > 入场信号 > 观望 */
  let state, label;
  if (!A.gate.ok) { state = 'nodata'; label = '数据不足'; }
  else if (A.position && A.manage) {
    state = A.manage.action === '持有' ? 'hold' : 'exit';
    label = A.manage.action === '持有' ? '持有' : '该平：' + A.manage.action;
  } else if (A.side !== 0) { state = A.side > 0 ? 'long' : 'short'; label = A.side > 0 ? '做多入场' : '做空入场'; }
  else { state = 'wait'; label = '观望'; }

  let pos = null;
  if (A.position) {
    const p = A.position, sg = p.side, r = A.manage ? A.manage.r : null, peakR = A.manage ? A.manage.peakR : 0;
    const on = peakR >= TP.ACT, peak = p.entryPx * (1 + sg * peakR / 100);
    const pj = readJson(path.join(dataDir, 'position.json')) || {};
    pos = { side: sg, lots: p.lots, entryPx: p.entryPx, entryD: p.entryD, contract: pj.contract || null,
            r, peakR, action: A.manage ? A.manage.action : null,
            stop: Math.round(p.entryPx * (1 - sg * TP.STOP / 100)),
            trail: on ? Math.round(peak * (1 - sg * TP.TRAIL / 100)) : null };
  }

  const why = A.gate.ok ? PA.loadPlan().planWhy(A.sig) : (A.gate.reasons || []).join('；');
  const chk = A.gate.ok ? buildChecks(A, TP) : null;
  const fxPart = (A.foreign || []).length ? A.foreign.reduce((a, q) => q.v < a.v ? q : a) : null;
  const warn1 = (A.gate.warn || [])[0] || null;
  return {
    v: 4,
    updatedAt: new Date(nowMs).toISOString(),
    contract: { key, name: NAME[key], symbol: pc.symbol || null },
    fund: readFund(dataDir, key),
    price: lb ? { c: +lb.close, dt: String(lb.datetime).slice(0, 16), prev } : null,
    signal: { state, label, why, priceDate: A.priceDate, ref: A.px == null ? null : Math.round(A.px),
              en: A.side !== 0 && A.px != null ? (e => ({ lim: e.lim, stop: e.stop, act: e.act, trail: e.trailAtAct, pct: TP.LIM.pct, fill: TP.LIM.fill, tr: TP.TRAIL }))(PA.loadPlan().planEntry(A.px, A.side)) : null,   // v102.14 入场建议：限价(收盘价回调0.3%)、止损(从限价算)、移动止盈启动价/初始移动止损
              stop: A.side !== 0 && A.px != null ? PA.loadPlan().planEntry(A.px, A.side).stop : null,
              pct: A.sig.pct == null ? null : Math.round(A.sig.pct), fsum: A.fsum, delev: !!A.sig.delev,
              gateOk: A.gate.ok,
              lv: A.gate.level || (A.gate.ok ? 'ok' : 'bad'),               // 数据等级 ok/part/bad：小组件锁屏的状态点用
              warn: warn1 ? String(warn1).slice(0, 40) : null,
              fx: fxPart ? { v: Math.round(fxPart.v), k: String(fxPart.k).replace('期货', ''), line: TP.DELEV } : null,   // 最弱外资席位5日变化 + 去杠杆线
              chk },
    position: pos,
    ru: opts.noRu ? null : buildRu(dataDir, nowMs)
  };
}

/* 基本面（只取「综合」及其变动）：data/history/systems_<合约>.json 每个自然日一条（Actions 每小时用驾驶舱同一份评分引擎记录），
 * 按交易日去重后取：comp 综合方向、cp 综合倾向%（−100~+100）、conf 置信度、
 * c1 较上一个交易日的变化（百分点）、c5 较 5 个交易日前的变化、pd 上一交易日的方向。
 * 文件缺失/没有综合倾向 → null，小组件就不画这块。 */
function readFund(dataDir, key) {
  const hist = readJson(path.join(dataDir, 'history', 'systems_' + key + '.json'), null), pts = hist && hist.points;
  if (!pts || !pts.length) return null;
  const byDay = new Map();   // 交易日 → 当天最后一条（周末/节假日重复记录的合并掉）
  for (const q of pts) { const x = q.x || {}; if (x.compRatio == null) continue; byDay.set(x.priceDate || q.d, { d: q.d, dir: x.compDir || null, cp: Math.round(x.compRatio * 100), conf: x.confidence || null }); }
  const arr = [...byDay.values()]; if (!arr.length) return null;
  const cur = arr[arr.length - 1], at = k => arr.length > k ? arr[arr.length - 1 - k] : null, p1 = at(1), p5 = at(5);
  return { d: cur.d, comp: cur.dir, cp: cur.cp, conf: cur.conf, c1: p1 ? cur.cp - p1.cp : null, c5: p5 ? cur.cp - p5.cp : null, pd: p1 ? p1.dir : null };
}

/* 逐条入场条件（和页面「条件表」同一批：做多 4 条、做空 3 条）。每项 [ok, 值]：ok = 1 满足 / 0 不满足 / null 没数据（基差缺失时按原规则不过滤）。
 * 标签文字放在小组件脚本里（省 widget.json 体积）；顺序必须和脚本里的 CHK_LONG / CHK_SHORT 一致。 */
function buildChecks(A, TP) {
  const s = A.sig, pct = s.pct == null ? null : Math.round(s.pct);
  const hasB = A.basis && A.basis.v != null, bv = hasB ? +(A.basis.v * 100).toFixed(2) : null;
  return {
    L: [[s.lowOK ? 1 : 0, pct], [s.confirm ? 1 : 0, null], [s.delev ? 0 : 1, null], [hasB ? (A.basis.v >= TP.BASIS_MIN ? 1 : 0) : null, bv]],
    S: [[s.delev ? 1 : 0, null], [s.below20 ? 1 : 0, null], [s.highOK ? 1 : 0, pct]]
  };
}

/* 橡胶：价格取 ru_live.json 最后两根收盘；持仓取 account.json 里没平仓的 ruTrades；状态来自 cockpit/rubber.js 的 ruPlan（和页面同一份）。
 * 天气拦单只在驾驶舱页面里判断（小组件每5分钟生成，不去取天气），所以这里「做空信号」不含天气这一条。 */
function buildRu(dataDir, nowMs) {
  const S = RA.loadSeries(dataDir); if (!S) return null;
  const today = bj(nowMs).toISOString().slice(0, 10), n = S.d.length;
  const acct = readJson(path.join(dataDir, 'account.json')) || {}, t = (acct.ruTrades || []).find(x => x && !x.exitD) || null;
  const pos = t ? { px: +t.entryPx, lots: +t.lots, d: t.entryD, contract: t.contract || '' } : null;
  const ind = readJson(path.join(dataDir, 'ru_ind_auto.json'), {}), pol = readJson(path.join(dataDir, 'ru_policy.json'), {});
  const pl = RA.plan(S, today, pos, ind, pol), real = S.r[n - 1] != null ? S.r[n - 1] : null, prev = n > 1 && S.r[n - 2] != null ? S.r[n - 2] : null;
  const dom = pl.dom || null;
  const act = pl.st === 'go' ? 'go' : pl.st === 'exit' || pl.st === 'holdwx' ? 'exit' : pl.pos ? 'hold' : 'wait';
  return {
    symbol: dom, price: real == null ? null : { c: real, prev, d: S.d[n - 1] },
    state: pl.st, act, head: pl.head, sub: pl.sub,
    order: pl.order ? { lim: pl.order.lim, stop: pl.order.stop } : null,
    position: pos ? { side: -1, lots: pos.lots, entryPx: pos.px, entryD: pos.d, contract: pos.contract || null, r: pl.pos && pl.pos.r != null ? +pl.pos.r.toFixed(2) : null, stop: Math.round(pos.px * (1 + RA_STOP / 100)), action: act === 'exit' ? '该平' : '持有' } : null
  };
}
const RA_STOP = 5;   // = cockpit/rubber.js RUP.STOP；test_build_widget 里有一条断言核对两处一致

function main(argv) {
  const a = {}; for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) a[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  const dataDir = a.data || 'data', out = a.out || path.join(dataDir, 'widget.json');
  const o = build(dataDir, { nowMs: a.now ? Date.parse(a.now) : undefined });
  const tmp = out + '.tmp'; fs.writeFileSync(tmp, JSON.stringify(o)); fs.renameSync(tmp, out);   // 先写临时文件再改名：读的人不会读到半截
  console.error(`[小组件] ${o.contract.symbol} ${o.price ? o.price.c : '—'} · ${o.signal.label} · ${out}`);
}
if (require.main === module) main(process.argv.slice(2));
module.exports = { build, autoKey, prevCloseOf, buildRu, buildChecks, readFund, RA_STOP };
