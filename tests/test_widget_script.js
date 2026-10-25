// widget/豆粕小组件.js（Scriptable 脚本）：用一个假的 Scriptable 运行环境把各尺寸「画」一遍，检查文字内容。不联网、不需要手机。
const fs = require('fs'), path = require('path'), os = require('os');
const ROOT = path.join(__dirname, '..'), BW = require(path.join(ROOT, 'scripts', 'build_widget.js'));
const SRC = fs.readFileSync(path.join(ROOT, 'widget', '豆粕小组件.js'), 'utf8');
let pass = 0, fail = 0;
const ok = (n, c, extra) => { c ? (pass++, console.log('✅', n)) : (fail++, console.log('❌', n, extra || '')); };

const cacheDir = fs.mkdtempSync(path.join(os.tmpdir(), 'wsc-'));
class El { constructor(t) { this.t = t; this.kids = []; } addText(x) { const e = new El('T:' + x); this.kids.push(e); return e; } addStack() { const e = new El('S'); this.kids.push(e); return e; }
  addSpacer() {} setPadding() {} layoutVertically() {} centerAlignContent() {} topAlignContent() {} }
class ListWidget extends El { constructor() { super('W'); } }
const texts = (e, a) => { a = a || []; if (e.t.startsWith('T:')) a.push(e.t.slice(2)); e.kids.forEach(k => texts(k, a)); return a; };

async function render(family, data, o) {
  o = o || {}; const out = [];
  const env = { Color: class { static dynamic(a) { return a; } static white() { return {}; } }, Font: { boldSystemFont() {}, systemFont() {}, boldMonospacedSystemFont() {} }, Size: class {}, ListWidget,
    Request: class { constructor(u) { this.u = u; } async loadJSON() { if (this.u.includes('widget.json')) { if (o.offline) throw new Error('net'); return data; } if (this.u.includes('eastmoney')) return { data: { f43: o.px || 3280, f86: o.ts || Date.UTC(2026, 9, 23, 15, 0, 0) / 1000 } }; throw new Error('x'); } async load() { throw new Error('x'); } },
    FileManager: { local: () => ({ joinPath: (a, b) => path.join(cacheDir, b), documentsDirectory: () => cacheDir, fileExists: p => fs.existsSync(p), readString: p => fs.readFileSync(p, 'utf8'), writeString: (p, s) => fs.writeFileSync(p, s) }) },
    config: { widgetFamily: family, runsInWidget: true }, Script: { setWidget: w => out.push(w), complete() {} } };
  const names = Object.keys(env), fn = new (Object.getPrototypeOf(async function () {}).constructor)(...names, SRC);
  await fn(...names.map(k => env[k]));
  return texts(out[0]).join('\n');
}

const REAL_NOW = Date.now;
Date.now = () => Date.UTC(2026, 9, 24, 8, 0, 0);   // 固定为周六（休市），测试不依赖现在是几点
(async () => {
  const real = BW.build(path.join(ROOT, 'data'), { nowMs: Date.UTC(2026, 9, 24, 8, 0, 0) });   // 真实数据：10月 → 1月合约
  const clone = f => { const d = JSON.parse(JSON.stringify(real)); return f ? f(d) : d; };

  const lg = await render('large', clone());
  ok('大号：做多4条 + 做空3条逐条打勾', lg.includes('做多条件') && lg.includes('做空条件') && lg.includes('价格分位 ≤50%') && lg.includes('价格分位 ≥70%') && /[✓✗]/.test(lg));
  ok('大号：「价格分位」那句原因不再重复（旧版同一句出现两次）', !/不在低位/.test(lg));
  ok('大号：外资线写出离去杠杆线还差多少手', /外资 .* \/ 线 −20,000/.test(lg) && /距去杠杆线 [\d,]+ 手|已到去杠杆线/.test(lg));
  const sm = await render('small', clone());
  ok('小号：补一句为什么观望', sm.includes('观望') && /分位\d+% 不在低位/.test(sm));
  const md = await render('medium', clone());
  ok('中号：右侧打勾 + 外资线', /(做多|做空)条件/.test(md) && /外资 .* \/ 线/.test(md));
  ok('状态词统一：休市写「休市·收盘」，不再出现「离线缓存」', [lg, sm, md].every(t => t.includes('休市·收盘 23:00') && !t.includes('离线缓存')));
  const lk = await render('accessoryRectangular', clone());
  ok('锁屏矩形：带状态点和分位', /🟢|🟠|🔴|🔵/.test(lk) && lk.includes('分位'));
  ok('橡胶休眠时三种桌面尺寸都不占位', ![lg, sm, md].some(t => t.includes('橡胶')));

  const noData = clone(d => { d.signal.state = 'nodata'; d.signal.label = '数据不足'; d.signal.gateOk = false; d.signal.lv = 'bad'; d.signal.chk = null; d.signal.why = '外资席位5日数据缺失'; return d; });
  ok('数据不足：锁屏是橙点', (await render('accessoryRectangular', noData)).includes('🟠'));
  ok('数据不足：大号不画打勾表，只写原因', !(await render('large', noData)).includes('做多条件'));
  const sig = clone(d => { d.signal.state = 'long'; d.signal.label = '做多入场'; d.signal.ref = 3100; d.signal.stop = 2976; return d; });
  ok('有入场信号：锁屏是红点', (await render('accessoryRectangular', sig)).includes('🔴'));
  const holdD = clone(d => { d.position = { side: -1, lots: 5, entryPx: 3386, entryD: '2026-10-09', contract: 'M2701', r: 3, peakR: 3, action: '持有', stop: 3521, trail: null }; d.signal.state = 'hold'; d.signal.label = '持有'; return d; });
  const hl = await render('large', holdD);
  ok('持仓：大号显示开仓/止损，不画入场打勾表', hl.includes('开仓 3,386') && hl.includes('止损 3,521') && !hl.includes('做多条件'));
  const v2 = clone(d => { d.v = 2; delete d.signal.chk; delete d.signal.fx; delete d.signal.lv; return d; });
  const v2t = await render('large', v2);
  ok('旧版 v2 文件也画打勾表：分位/外资两条真实，其余标「待更新」，外资线用合计', v2t.includes('观望') && v2t.includes('做多条件') && v2t.includes('待更新') && /外资 合计 .* \/ 线 −20,000/.test(v2t));
const v2m = await render('medium', v2);
ok('旧版 v2 文件中号也有打勾表（不是一大片空白）', /(做多|做空)条件/.test(v2m) && v2m.includes('待更新'));
  const off = await render('medium', clone(), { offline: true });
  ok('取不到 widget.json、用缓存：标「离线·缓存」', off.includes('离线·缓存'));
  const ruGo = clone(d => { d.ru.state = 'go'; d.ru.act = 'go'; d.ru.head = '做空信号'; d.ru.order = { lim: 19800, stop: 20800 }; return d; });
  ok('橡胶出做空信号时弹出橡胶', (await render('medium', ruGo)).includes('橡胶'));
  fs.rmSync(cacheDir, { recursive: true, force: true });
  console.log(`\n结果：${pass}项通过，${fail}项失败`); process.exit(fail ? 1 : 0);
})().catch(e => { console.error('异常', e); process.exit(1); });
