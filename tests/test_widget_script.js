// widget/豆粕小组件.js（Scriptable 脚本）：用假的 Scriptable 环境跑一遍，核对「显示哪个品种」的规则。不联网。
const fs = require('fs'), path = require('path'), vm = require('vm');
const SRC = fs.readFileSync(path.join(__dirname, '..', 'widget', '豆粕小组件.js'), 'utf8');
let pass = 0, fail = 0; const eq = (n, x, y) => { const ok = JSON.stringify(x) === JSON.stringify(y); ok ? pass++ : (fail++, console.log('❌', n, '期望', y, '实际', x)); if (ok) console.log('✅', n); };
const bjNow = Date.parse('2026-03-12T05:00:00Z');
const soy = (o) => Object.assign({ v: 2, updatedAt: new Date(bjNow).toISOString(), contract: { key: 'jan', name: '1月合约', symbol: 'M2701' }, price: { c: 3267, dt: '2026-03-12 15:00', prev: 3287 }, signal: { state: 'wait', label: '观望', why: 'x', priceDate: '2026-03-12', ref: 3267, stop: null, pct: 87, fsum: 0, delev: false, gateOk: true }, position: null }, o || {});
const ruO = (o) => Object.assign({ symbol: 'RU2705', price: { c: 17000, prev: 16900, d: '2026-03-12' }, state: 'wait', act: 'wait', head: '等反弹：x', sub: 's', order: null, position: null }, o || {});
async function run(data, family, nowMs) {
  const texts = []; let widgetSet = null;
  class Col { constructor(h) { this.h = h; } static dynamic(a) { return a; } static white() { return new Col('#fff'); } }
  const mkStack = () => ({ addText(t) { texts.push(String(t)); return { font: null, textColor: null, lineLimit: 1, minimumScaleFactor: 1 }; }, addSpacer() {}, addStack() { return mkStack(); }, centerAlignContent() {}, layoutVertically() {}, setPadding() {} });
  class LW { constructor() { Object.assign(this, mkStack()); } }
  const Req = class { constructor(u) { this.u = u; } async loadJSON() { if (/widget\.json/.test(this.u)) return data; throw new Error('offline'); } async load() { throw new Error('offline'); } };
  const ctx = { Request: Req, ListWidget: LW, Color: Col, Font: { boldSystemFont: () => 1, systemFont: () => 1, boldMonospacedSystemFont: () => 1 }, FileManager: { local: () => ({ documentsDirectory: () => '/tmp', joinPath: (a, b) => a + '/' + b, fileExists: () => false, readString: () => '', writeString: () => {} }) },
    config: { widgetFamily: family, runsInWidget: true }, Script: { setWidget: w => { widgetSet = w; }, complete() {} }, console, Date: class extends Date { constructor(...a) { a.length ? super(...a) : super(nowMs); } static now() { return nowMs; } }, Math, JSON, Promise, String, Number, isNaN, parseFloat, encodeURIComponent, Object, Array };
  await vm.runInNewContext('(async()=>{' + SRC + '\n})()', ctx);
  return texts;
}
(async () => {
  const has = (t, k) => t.some(x => x.includes(k));
  let t = await run({ ...soy(), ru: ruO() }, 'medium', bjNow);
  eq('都没信号没持仓 → 显示豆粕', [has(t, '豆粕'), has(t, '橡胶 RU')], [true, false]);
  t = await run({ ...soy(), ru: ruO({ state: 'go', act: 'go', head: '做空信号', order: { lim: 17100, stop: 17955 } }) }, 'medium', bjNow);
  eq('橡胶有入场信号 → 弹出橡胶，且写建议限价', [has(t, '橡胶 RU2705'), has(t, '建议限价 ≥ 17,100')], [true, true]);
  t = await run({ ...soy(), ru: ruO({ state: 'hold', act: 'hold', head: '持有空单', position: { side: -1, lots: 3, entryPx: 17200, entryD: '2026-03-04', contract: null, r: 1, stop: 18060, action: '持有' } }) }, 'medium', bjNow);
  eq('橡胶持仓、豆粕空仓 → 显示橡胶，并提示另一个', [has(t, '橡胶 RU2705'), has(t, '另：豆粕：观望')], [true, true]);
  const soyHold = soy({ signal: { state: 'hold', label: '持有', why: '', ref: 3267, stop: null, pct: 50, fsum: 0, delev: false, gateOk: true, priceDate: '2026-03-12' }, position: { side: 1, lots: 2, entryPx: 3200, entryD: '2026-03-01', contract: 'M2701', r: 2, peakR: 2, action: '持有', stop: 3100, trail: null } });
  t = await run({ ...soyHold, ru: ruO() }, 'medium', bjNow);
  eq('豆粕持仓、橡胶无 → 显示豆粕持仓', [has(t, '豆粕 M2701'), has(t, '另：橡胶')], [true, true]);
  const ruHold = ruO({ state: 'hold', act: 'hold', position: { side: -1, lots: 3, entryPx: 17200, entryD: '2026-03-04', contract: null, r: 1, stop: 18060, action: '持有' } });
  const a = await run({ ...soyHold, ru: ruHold }, 'medium', bjNow), b = await run({ ...soyHold, ru: ruHold }, 'medium', bjNow + 300000);
  eq('同时持仓 → 轮换：相邻5分钟显示不同品种', [has(a, '豆粕 M2701') !== has(b, '豆粕 M2701'), has(a, '轮换中')], [true, true]);
  t = await run({ ...soyHold, ru: ruO({ state: 'go', act: 'go', order: { lim: 17100, stop: 17955 } }) }, 'medium', bjNow);
  eq('豆粕持仓 + 橡胶出入场信号 → 信号弹出（橡胶），另一行写豆粕持仓', [has(t, '橡胶 RU2705'), has(t, '另：豆粕多2手')], [true, true]);
  const soyLong = soy({ signal: { state: 'long', label: '做多入场', why: 'w', ref: 3300, stop: 3200, pct: 20, fsum: 100, delev: false, gateOk: true, priceDate: '2026-03-12' } });
  const c = await run({ ...soyLong, ru: ruO({ state: 'go', act: 'go', order: { lim: 17100, stop: 17955 } }) }, 'medium', bjNow), d = await run({ ...soyLong, ru: ruO({ state: 'go', act: 'go', order: { lim: 17100, stop: 17955 } }) }, 'medium', bjNow + 300000);
  eq('同时有信号 → 轮换', has(c, '橡胶 RU2705') !== has(d, '橡胶 RU2705'), true);
  t = await run({ ...soy(), ru: ruO({ state: 'exit', act: 'exit', head: '止损：平空单', position: { side: -1, lots: 1, entryPx: 17200, entryD: '2026-03-04', contract: null, r: -5, stop: 18060, action: '该平' } }) }, 'small', bjNow);
  eq('橡胶该平 → 弹出橡胶（小尺寸）', has(t, '橡胶 RU2705'), true);
  t = await run(soy(), 'medium', bjNow);
  eq('旧版 widget.json（v1，没有 ru）→ 只显示豆粕，不报错', [has(t, '豆粕 M2701'), has(t, '另：')], [true, false]);
  t = await run({ ...soy(), ru: ruO() }, 'accessoryRectangular', bjNow);
  eq('锁屏矩形小组件能画', has(t, '豆粕'), true);
  console.log(`\n结果：${pass}项通过，${fail}项失败`); process.exit(fail ? 1 : 0);
})();
