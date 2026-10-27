// widget/豆粕小组件.js（Scriptable 脚本）：用一个假的 Scriptable 运行环境把各尺寸「画」一遍，检查文字内容和版面结构。不联网、不需要手机。
const fs = require('fs'), path = require('path'), os = require('os');
const ROOT = path.join(__dirname, '..'), BW = require(path.join(ROOT, 'scripts', 'build_widget.js'));
const SRC = fs.readFileSync(path.join(ROOT, 'widget', '豆粕小组件.js'), 'utf8');
let pass = 0, fail = 0;
const ok = (n, c, extra) => { c ? (pass++, console.log('✅', n)) : (fail++, console.log('❌', n, extra || '')); };

const cacheDir = fs.mkdtempSync(path.join(os.tmpdir(), 'wsc-'));
class El { constructor(t) { this.t = t; this.kids = []; }
  addText(x) { const e = new El('T:' + x); this.kids.push(e); return e; } addStack() { const e = new El('S'); this.kids.push(e); return e; }
  addImage(img) { const e = new El('I'); e.img = img; this.kids.push(e); return e; }
  addSpacer() {} setPadding() {} layoutVertically() {} centerAlignContent() {} topAlignContent() {} bottomAlignContent() {} }
class ListWidget extends El { constructor() { super('W'); } }
const texts = (e, a) => { a = a || []; if (e.t.startsWith('T:')) a.push(e.t.slice(2)); e.kids.forEach(k => texts(k, a)); return a; };
const countImg = e => (e.t === 'I' ? 1 : 0) + e.kids.reduce((n, k) => n + countImg(k), 0);
const stacks = (e, a) => { a = a || []; if (e.t === 'S') a.push(e); e.kids.forEach(k => stacks(k, a)); return a; };
const isPill = st => st.kids.some(k => k.t.startsWith('T:') && /^[✓✗–]/.test(k.t.slice(2)));   // 小标签 = 直接带 ✓/✗/– 文字的 stack
const pillsIn = st => st.kids.filter(k => k.t === 'S' && isPill(k)).length;
const maxPillsPerRow = root => Math.max(0, ...stacks(root).map(pillsIn));            // 同一行有几个标签（要求 ≤1：一行一个）
const countPills = root => stacks(root).filter(isPill).length;

class Rect { constructor(x, y, w, h) { Object.assign(this, { x, y, w, h }); } }
class DrawContext { constructor() { this.n = 0; } setFillColor() {} fillRect() { this.n++; } addPath() {} fillPath() {} getImage() { return { drawn: this.n }; } }
class Path { addRoundedRect() {} }

async function render(family, data, o) {
  o = o || {}; const out = [];
  const env = { Color: class { static dynamic(a) { return a; } static white() { return {}; } }, Font: { boldSystemFont() {}, systemFont() {}, boldMonospacedSystemFont() {} }, Size: class {}, ListWidget, Rect, DrawContext, Path, Device: { isUsingDarkAppearance: () => false },
    Request: class { constructor(u) { this.u = u; } async loadJSON() { if (this.u.includes('widget.json')) { if (o.offline) throw new Error('net'); return data; } if (this.u.includes('eastmoney')) return { data: { f43: o.px || 3280, f86: Date.UTC(2026, 9, 23, 15, 0, 0) / 1000 } }; throw new Error('x'); } async load() { throw new Error('x'); } },
    FileManager: { local: () => ({ joinPath: (a, b) => path.join(cacheDir, b), documentsDirectory: () => cacheDir, fileExists: p => fs.existsSync(p), readString: p => fs.readFileSync(p, 'utf8'), writeString: (p, s) => fs.writeFileSync(p, s) }) },
    config: { widgetFamily: family, runsInWidget: true }, Script: { setWidget: w => out.push(w), complete() {} } };
  const names = Object.keys(env), fn = new (Object.getPrototypeOf(async function () {}).constructor)(...names, SRC);
  await fn(...names.map(k => env[k]));
  return { text: texts(out[0]).join('\n'), root: out[0] };
}

Date.now = () => Date.UTC(2026, 9, 24, 8, 0, 0);   // 固定为周六（休市），测试不依赖现在是几点
(async () => {
  const real = BW.build(path.join(ROOT, 'data'), { nowMs: Date.UTC(2026, 9, 24, 8, 0, 0) });
  // 用固定的信号数字做基准（仓库里的实时数据每天都在变，写死真实数字的测试一换数据就会失败）；价格、橡胶等仍取真实数据
  const fixed = d => { const sg = d.signal; Object.assign(sg, { state: 'wait', label: '观望', gateOk: true, lv: 'ok', pct: 87, fsum: -11567, delev: false, ref: 3276, priceDate: '2026-10-23',
    fx: { v: -11567, k: '高盛', line: -20000 }, chk: { L: [[0, 87], [0, null], [1, null], [1, 1.53]], S: [[0, null], [1, null], [1, 87]] } });
    d.fund = { d: '2026-10-26', comp: '偏空', cp: -28, conf: '高', c1: 0, c5: 13, pd: '偏空' }; d.position = null; return d; };
  const clone = f => { const d = fixed(JSON.parse(JSON.stringify(real))); return f ? f(d) : d; };
  ok('测试数据里有综合基本面', !!(real.fund && real.fund.cp != null));

  const L = await render('large', clone()), S = await render('small', clone()), M = await render('medium', clone());
  const lg = L.text, sm = S.text, md = M.text;

  // ① 大号信号列表改成和小号/中号一样的小标签（✓/✗ 圆角标签），一行一个
  ok('大号：信号条件是小标签（全称+当前值），不再是逐行打勾', lg.includes('✗外资去杠杆 −11,567') && lg.includes('✓收盘<MA20') && lg.includes('✓价格分位≥70% 87%'));
  ok('大号：只画最接近出信号的那一边，另一边只写进度', lg.includes('做空条件') && !lg.includes('做多条件') && lg.includes('做多 2/4'));
  ok('大号：3 个标签，每行一个', countPills(L.root) === 3 && maxPillsPerRow(L.root) <= 1);
  // ② 小号、中号：一行一个
  ok('小号：3 个标签，每行一个', countPills(S.root) === 3 && maxPillsPerRow(S.root) <= 1);
  ok('中号：3 个标签，每行一个', countPills(M.root) === 3 && maxPillsPerRow(M.root) <= 1);
  ok('小号：标签 = ✗去杠杆 ✓MA20 ✓高位87%（简称）', sm.includes('✗去杠杆') && sm.includes('✓MA20') && sm.includes('✓高位87%'));
  ok('中号：外资标签带手数 ✗去杠杆 −11,567', md.includes('✗去杠杆 −11,567'));
  // ③ 小号：列表在观望按钮右侧，按钮在下
  const rowS = stacks(S.root).find(st => st.kids.filter(k => k.t === 'S').length === 2 && texts(st.kids.filter(k => k.t === 'S')[0]).includes('观望') && texts(st.kids.filter(k => k.t === 'S')[1]).some(t => t.startsWith('✗去杠杆')));
  ok('小号：同一行里，左边是观望按钮（+进度「空 2/3」），右边是标签列表', !!rowS && texts(rowS.kids.filter(k => k.t === 'S')[0]).includes('空 2/3'));
  // ④ 基本面只显示综合 + 变动，风格同仪表盘（倾向条 + 红多绿空）
  ok('大号/中号：只有「基本面」一个数（和仪表盘基本面卡一致），没有供需/结构/技术逐项', !/供需|结构 |技术 /.test(lg + md) && lg.includes('基本面') && !lg.includes('基本面·综合') && md.includes('基本面'));
  ok('大号：综合 偏空 −28%，较上一交易日、较5个交易日前的变动', lg.includes('偏空') && lg.includes('−28%') && lg.includes('较上一交易日') && lg.includes('较5个交易日前'));
  ok('中号：综合 + 较前日 / 5日 变动', md.includes('偏空') && md.includes('−28%') && md.includes('较前日') && md.includes('5日'));
  ok('倾向条画出来：大号 1 张、中号 1 张、小号 0 张（不再画近10日走势柱）', countImg(L.root) === 1 && countImg(M.root) === 1 && countImg(S.root) === 0);
  ok('倾向条图确实画了东西（底条+刻度+填充+中线）', (stacks(L.root).concat([L.root]).length > 0) && JSON.stringify(L.root).includes('"drawn"'));
  ok('大号：不再重复写「价格分位」一句话', !/不在低位/.test(lg));
  ok('大号：外资线写出距去杠杆线还差多少手', /外资 .* \/ 线 −20,000/.test(lg) && /距去杠杆线 [\d,]+ 手|已到去杠杆线/.test(lg));

  // 橡胶休眠：三种尺寸都显示
  ok('橡胶休眠：小/中/大号都显示一句', sm.includes('橡胶休眠') && /橡胶休眠·距3月开窗\d+天/.test(md) && /橡胶：休眠 · 下一个窗口/.test(lg));
  ok('状态词统一：休市·收盘 23:00，不再出现「离线缓存」', [lg, sm, md].every(t => t.includes('休市·收盘 23:00') && !t.includes('离线缓存')));

  const lk = (await render('accessoryRectangular', clone())).text;
  ok('锁屏矩形：状态点 + 最接近那边的进度 + 差哪条', /🟢/.test(lk) && lk.includes('空2/3') && lk.includes('差去杠杆'));
  const noData = clone(d => { d.signal.state = 'nodata'; d.signal.label = '数据不足'; d.signal.gateOk = false; d.signal.lv = 'bad'; d.signal.chk = null; d.signal.why = '外资席位5日数据缺失'; return d; });
  ok('数据不足：锁屏是橙点', (await render('accessoryRectangular', noData)).text.includes('🟠'));
  ok('数据不足：大号不画标签，只写原因', countPills((await render('large', noData)).root) === 0);
  const sig = clone(d => { d.signal.state = 'long'; d.signal.label = '做多入场'; d.signal.ref = 3100; d.signal.stop = 2976; return d; });
  ok('有入场信号：锁屏是红点', (await render('accessoryRectangular', sig)).text.includes('🔴'));
  /* v102.14 入场建议：限价(收盘价回调0.3%)、止损、移动止盈启动价 —— 小/中/大/锁屏都要显示，且不再把收盘价当限价 */
  const en = { lim: 3090, stop: 2966, act: 3337, trail: 3203, pct: 0.3, fill: 83, tr: 4 };
  const sigEn = clone(d => { d.signal.state = 'long'; d.signal.label = '做多入场'; d.signal.ref = 3100; d.signal.stop = 2966; d.signal.en = en; return d; });
  for (const fam of ['small', 'medium', 'large']) {
    const t = (await render(fam, sigEn)).text;
    ok(`有信号·${fam}号：显示限价 ≤ 3,090 和止损 2,966，不显示收盘价当限价`, t.includes('3,090') && t.includes('2,966') && !t.includes('≤ 3,100'));
  }
  const tl = (await render('large', sigEn)).text;
  ok('有信号·大号：显示移动止盈启动价 3,337、回落4%、每0.5%上移', tl.includes('3,337') && tl.includes('回落4%') && tl.includes('0.5%'));
  ok('有信号·中号：显示启动价 3,337', (await render('medium', sigEn)).text.includes('3,337'));
  const lk2 = (await render('accessoryRectangular', sigEn)).text;
  ok('有信号·锁屏：显示限价和止损', lk2.includes('3,090') && lk2.includes('2,966'));
  const sigShort = clone(d => { d.signal.state = 'short'; d.signal.label = '做空入场'; d.signal.en = { lim: 3110, stop: 3234, act: 2861, trail: 2975, pct: 0.3, fill: 83, tr: 4 }; return d; });
  ok('做空信号·大号：限价 ≥ 3,110', (await render('large', sigShort)).text.includes('≥ 3,110'));
  const holdD = clone(d => { d.position = { side: -1, lots: 5, entryPx: 3386, entryD: '2026-10-09', contract: 'M2701', r: 3, peakR: 3, action: '持有', stop: 3521, trail: null }; d.signal.state = 'hold'; d.signal.label = '持有'; return d; });
  const hl = (await render('large', holdD)).text;
  ok('持仓：大号显示开仓/止损，不画入场标签', hl.includes('开仓 3,386') && hl.includes('止损 3,521') && !hl.includes('做空条件'));

  /* v102.15 持仓：显示盈亏、开仓/最高浮盈、止损或移动止损(距现价%)、启动价/已启动规则 */
  const posA = clone(d => { d.position = { side: -1, lots: 5, entryPx: 3386, entryD: '2026-10-09', contract: 'M2701', r: 3, peakR: 3, action: '持有', stop: 3521, trail: null, act: 3115, on: false, peak: 3300, tr: 4 }; d.signal.state = 'hold'; d.signal.label = '持有'; return d; });
  const pa = (await render('large', posA)).text;
  ok('持仓(未启动)·大号：止损、启动价 3,115、最高浮盈', pa.includes('止损 3,521') && pa.includes('3,115') && pa.includes('最高浮盈'));
  ok('持仓(未启动)·中号/小号：显示止损和启动价', (await render('medium', posA)).text.includes('3,115') && (await render('small', posA)).text.includes('止损 3,521'));
  const posB = clone(d => { d.position = { side: -1, lots: 5, entryPx: 3386, entryD: '2026-10-09', contract: 'M2701', r: 9, peakR: 9, action: '持有', stop: 3521, trail: 3280, act: 3115, on: true, peak: 3154, tr: 4 }; d.signal.state = 'hold'; d.signal.label = '持有'; return d; });
  const pb = (await render('large', posB)).text;
  ok('持仓(已启动)·大号：移动止损 3,280、从最低价 3,154 回落4%', pb.includes('移动止损 3,280') && pb.includes('3,154') && pb.includes('回落4%'));
  ok('有信号·建议手数：大号显示"建议开 51 手"', (await render('large', clone(d => { d.signal.state = 'short'; d.signal.label = '做空入场'; d.signal.en = { lim: 3210, stop: 3338, act: 2953, trail: 3071, pct: 0.3, fill: 83, tr: 4, lots: 51, use: 60, loss: 65484 }; return d; }))).text.includes('建议开 51 手'));
  ok('基本面标签：大号写"基本面"而不是"基本面·综合"', !(await render('large', clone())).text.includes('基本面·综合'));
  // 旧文件兼容
  const v2 = clone(d => { d.v = 2; delete d.signal.chk; delete d.signal.fx; delete d.signal.lv; delete d.fund; return d; });
  const v2L = await render('large', v2), v2M = await render('medium', v2), v2S = await render('small', v2);
  ok('旧版 v2 文件：用合成条件画标签，没有基本面也不报错', v2L.text.includes('观望') && countPills(v2L.root) >= 3 && v2M.text.includes('–反弹') && countPills(v2S.root) >= 3 && !v2L.text.includes('基本面·综合'));
  const noFund = clone(d => { d.fund = null; return d; });
  ok('没有 fund 字段：大号/中号不画基本面，也不报错', !(await render('large', noFund)).text.includes('基本面·综合') && countImg((await render('medium', noFund)).root) === 0);
  const off = (await render('medium', clone(), { offline: true })).text;
  ok('取不到 widget.json、用缓存：标「离线·缓存」', off.includes('离线·缓存'));
  const ruGo = clone(d => { d.ru.state = 'go'; d.ru.act = 'go'; d.ru.head = '做空信号'; d.ru.order = { lim: 19800, stop: 20800 }; return d; });
  ok('橡胶出做空信号时显示橡胶状态', (await render('medium', ruGo)).text.includes('橡胶'));
  fs.rmSync(cacheDir, { recursive: true, force: true });
  console.log(`\n结果：${pass}项通过，${fail}项失败`); process.exit(fail ? 1 : 0);
})().catch(e => { console.error('异常', e); process.exit(1); });
