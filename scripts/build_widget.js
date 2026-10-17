#!/usr/bin/env node
/* iOS 小组件数据（v101.82）：把「当前交易合约的价格 + 入场/离场信号 + 持仓」压成一个很小的 data/widget.json，给手机桌面小组件读。
 * 逻辑只有一份：信号直接调 scripts/plan_alert.js 的 compute()（它又用页面同一份 PLAN 纯函数），小组件和驾驶舱不可能算出两个结论。
 *   node scripts/build_widget.js --data data --out data/widget.json [--now 2026-10-16T05:00:00Z]
 * 交易合约 = 驾驶舱 autoKey() 的同一规则：北京时间当前月份 ∈ recommendedMonths（4-7→5月合约，12-3→1月合约，8-11→9月… 以 cockpit/static.json 为准）。 */
'use strict';
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, '..');
const PA = require('./plan_alert.js');

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

/* 前收盘 = 日线里日期早于「最新分钟线所在日」的最后一根；盘中未收完的当天日线不能当前收 */
function prevCloseOf(pc, lastBarDate) {
  const d = (pc.daily || []).filter(b => b && b.close != null && String(b.date) < lastBarDate);
  return d.length ? +d[d.length - 1].close : null;
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
  const prev = lb ? prevCloseOf(pc, lastBarDate) : null;

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
  return {
    v: 1,
    updatedAt: new Date(nowMs).toISOString(),
    contract: { key, name: NAME[key], symbol: pc.symbol || null },
    price: lb ? { c: +lb.close, dt: String(lb.datetime).slice(0, 16), prev } : null,
    signal: { state, label, why, priceDate: A.priceDate, ref: A.px == null ? null : Math.round(A.px),
              stop: A.side !== 0 && A.px != null ? Math.round(A.px * (1 - A.side * TP.STOP / 100)) : null,
              pct: A.sig.pct == null ? null : Math.round(A.sig.pct), fsum: A.fsum, delev: !!A.sig.delev,
              gateOk: A.gate.ok },
    position: pos
  };
}

function main(argv) {
  const a = {}; for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) a[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  const dataDir = a.data || 'data', out = a.out || path.join(dataDir, 'widget.json');
  const o = build(dataDir, { nowMs: a.now ? Date.parse(a.now) : undefined });
  const tmp = out + '.tmp'; fs.writeFileSync(tmp, JSON.stringify(o)); fs.renameSync(tmp, out);   // 先写临时文件再改名：读的人不会读到半截
  console.error(`[小组件] ${o.contract.symbol} ${o.price ? o.price.c : '—'} · ${o.signal.label} · ${out}`);
}
if (require.main === module) main(process.argv.slice(2));
module.exports = { build, autoKey, prevCloseOf };
