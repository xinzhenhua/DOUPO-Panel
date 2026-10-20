// 豆粕 + 橡胶驾驶舱 · iOS 桌面小组件（Scriptable 脚本，v102.8）
// 使用：App Store 装免费的 Scriptable → 新建脚本 → 把本文件全部内容粘进去 → 桌面长按添加 Scriptable 小组件 → 编辑小组件选这个脚本。
// 小/中/大尺寸 + 锁屏三种尺寸都支持。点小组件会打开驾驶舱网页。
// 数据：价格 = 东方财富实时报价（失败换新浪，再失败用仓库里 15 分钟线）；信号/持仓 = 仓库 data/widget.json（每 5 分钟由 Actions 生成，和驾驶舱同一份逻辑）。
// 注意：iOS 自己决定小组件多久刷新一次（通常 5–15 分钟，省电时更慢），不是逐秒跳动；想看最新价，点开小组件或在 Scriptable 里直接运行脚本。

// ===== 只需要改这里 =====
const GH_USER = "xinzhenhua";          // GitHub 用户名
const GH_REPO = "DOUPO-Panel";         // 仓库名
const GH_BRANCH = "main";              // 分支名
const SITE = `https://${GH_USER.toLowerCase()}.github.io/${GH_REPO}/`;   // 驾驶舱网址（GitHub Pages）
// =======================

const JSON_URLS = [
  `${SITE}data/widget.json`,
  `https://raw.githubusercontent.com/${GH_USER}/${GH_REPO}/${GH_BRANCH}/data/widget.json`,
];
const CACHE_NAME = "doupo-widget-cache.json";

// ---------- 小工具 ----------
const bj = (ms) => new Date(ms + 8 * 3600e3);
const z2 = (n) => String(n).padStart(2, "0");
const hhmm = (ms) => { const b = bj(ms); return z2(b.getUTCHours()) + ":" + z2(b.getUTCMinutes()); };
const f0 = (n) => (n == null || isNaN(n) ? "—" : Math.round(n).toLocaleString("en-US"));
const sgn = (n, d) => (n >= 0 ? "+" : "−") + Math.abs(n).toFixed(d == null ? 1 : d);
const sgnInt = (n) => (n >= 0 ? "+" : "−") + Math.abs(Math.round(n)).toLocaleString("en-US");

// 大商所交易时段（北京时间，周一至周五；节假日无法判断，靠"报价时间太旧"兜底）
function tradingNow(ms) {
  const b = bj(ms), dow = b.getUTCDay(), m = b.getUTCHours() * 60 + b.getUTCMinutes();
  if (dow === 0 || dow === 6) return false;
  return (m >= 540 && m < 615) || (m >= 630 && m < 690) || (m >= 810 && m < 900) || (m >= 1260 && m < 1380);   // 日盘 9:00-10:15、10:30-11:30、13:30-15:00；夜盘 21:00-23:00
}

function dyn(light, dark) {
  try { return Color.dynamic(new Color(light), new Color(dark)); } catch (_) { return new Color(light); }
}
// 中国习惯：涨红跌绿
const C = {
  bg: dyn("#FFFFFF", "#15171C"),
  text: dyn("#111318", "#F2F3F5"),
  sub: dyn("#6B7280", "#9AA0AA"),
  up: dyn("#D93025", "#FF5A4F"),
  down: dyn("#0E9F5B", "#34D18B"),
  warn: dyn("#C26A00", "#FFB34D"),
  info: dyn("#1A5FD0", "#6AA2FF"),
  gray: dyn("#8A8F98", "#7C828C"),
};

async function loadCache() {
  try { const fm = FileManager.local(), p = fm.joinPath(fm.documentsDirectory(), CACHE_NAME); if (fm.fileExists(p)) return JSON.parse(fm.readString(p)); } catch (_) {}
  return null;
}
function saveCache(o) {
  try { const fm = FileManager.local(), p = fm.joinPath(fm.documentsDirectory(), CACHE_NAME); fm.writeString(p, JSON.stringify(o)); } catch (_) {}
}

async function fetchWidgetJson() {
  for (const u of JSON_URLS) {
    try {
      const r = new Request(u + "?_=" + Date.now()); r.timeoutInterval = 8;
      const j = await r.loadJSON();
      if (j && j.v >= 1 && j.contract) return j;
    } catch (_) {}
  }
  return null;
}

// ---------- 实时价 ----------
async function liveEastmoney(sym) {
  const r = new Request(`https://push2.eastmoney.com/api/qt/stock/get?secid=114.${encodeURIComponent(sym.toLowerCase())}&fields=f43,f57,f86&fltt=2&invt=2&_=${Date.now()}`);
  r.timeoutInterval = 6;
  const j = await r.loadJSON(), d = j && j.data; if (!d) return null;
  const c = parseFloat(d.f43), ts = Number(d.f86); if (!(c > 0) || !(ts > 1e9)) return null;
  return { c, ms: ts * 1000, src: "东财" };
}
async function liveSina(sym) {
  const r = new Request(`https://hq.sinajs.cn/list=nf_${encodeURIComponent(sym.toUpperCase())}&_=${Date.now()}`);
  r.timeoutInterval = 6; r.headers = { Referer: "https://finance.sina.com.cn/" };
  const raw = (await r.load()).toRawString(), f = String(raw).split(",");
  if (f.length < 15) return null;
  const c = parseFloat(f[8]), tm = String(f[1] || "").replace(/\D/g, ""); if (!(c > 0) || tm.length !== 6) return null;
  const nowB = bj(Date.now()); let dd = null; for (let i = 15; i < f.length; i++) if (/^\d{4}-\d{2}-\d{2}$/.test(f[i])) { dd = f[i]; break; }
  if (!dd) dd = nowB.getUTCFullYear() + "-" + z2(nowB.getUTCMonth() + 1) + "-" + z2(nowB.getUTCDate());
  const ms = Date.parse(dd + "T" + tm.slice(0, 2) + ":" + tm.slice(2, 4) + ":" + tm.slice(4) + "+08:00");
  return { c, ms: isNaN(ms) ? Date.now() : ms, src: "新浪" };
}
async function getLive(sym) {
  for (const f of [liveEastmoney, liveSina]) { try { const t = await f(sym); if (t) return t; } catch (_) {} }
  return null;
}

// ---------- 把数据整理成一份"要显示的东西" ----------
async function loadData() {
  let data = await fetchWidgetJson(), stale = false;
  if (data) saveCache(data); else { data = await loadCache(); stale = true; }
  return data ? { data, stale } : null;
}
async function gather(D) {
  const data = D.data, stale = D.stale;
  const sym = data.contract.symbol;
  const live = sym ? await getLive(sym) : null;
  const now = Date.now();
  let px = null, pxMs = null, src = "";
  if (live) { px = live.c; pxMs = live.ms; src = live.src; }
  else if (data.price) { px = data.price.c; pxMs = Date.parse(data.price.dt.replace(" ", "T") + ":00+08:00"); src = "15分钟线"; }
  const prev = data.price ? data.price.prev : null;
  const chg = px != null && prev ? px - prev : null, chgPct = chg != null ? chg / prev * 100 : null;
  const open = tradingNow(now), tickAge = pxMs ? (now - pxMs) / 60000 : null;
  const quoteOld = tickAge != null && tickAge > 15;     // 交易时段里报价超过 15 分钟没动：多半是休市/节假日/取价失败
  const dataAge = data.updatedAt ? (now - Date.parse(data.updatedAt)) / 60000 : null;
  const sigOld = open && dataAge != null && dataAge > 45;  // 信号文件超过 45 分钟没更新：Actions 可能没跑
  // 持仓浮动盈亏：合约一致才用实时价算，否则用 Actions 算的
  let pnl = null;
  const p = data.position;
  if (p) {
    const same = !p.contract || String(p.contract).toLowerCase() === String(sym || "").toLowerCase();
    const r = same && px != null ? p.side * (px / p.entryPx - 1) * 100 : p.r;
    pnl = { r, amt: same && px != null ? p.side * (px - p.entryPx) * p.lots * 10 : null };
  }
  return { name: "豆粕", kind: "soy", data, sym, px, pxMs, src, chg, chgPct, open, quoteOld, sigOld, stale, pnl, now };
}

// ---------- 橡胶：整理成和豆粕同样的结构，复用同一套画法 ----------
async function liveRu(sym) {   // 上期所 RU：东财 113.ruXXXX，失败换新浪 nf_RUXXXX
  const s = String(sym || "").toLowerCase(); if (!s) return null;
  try {
    const r = new Request(`https://push2.eastmoney.com/api/qt/stock/get?secid=113.${encodeURIComponent(s)}&fields=f43,f57,f86&fltt=2&invt=2&_=${Date.now()}`); r.timeoutInterval = 6;
    const j = await r.loadJSON(), d = j && j.data, c = d ? parseFloat(d.f43) : NaN, ts = d ? Number(d.f86) : 0;
    if (c > 0 && ts > 1e9) return { c, ms: ts * 1000, src: "东财" };
  } catch (_) {}
  try { return await liveSina(s.toUpperCase()); } catch (_) {}
  return null;
}
async function gatherRu(D) {
  const ru = D.data.ru; if (!ru) return null;
  const live = ru.symbol ? await liveRu(ru.symbol) : null, now = Date.now();
  let px = null, pxMs = null, src = "";
  if (live) { px = live.c; pxMs = live.ms; src = live.src; }
  else if (ru.price) { px = ru.price.c; pxMs = Date.parse(ru.price.d + "T15:00:00+08:00"); src = "日线"; }
  const prev = ru.price ? ru.price.prev : null;
  // live 的前收：交易时段里 live 价比日线最后一根新，涨跌用「实时价 − 日线最后收盘」近似；没有实时价就用最近两根日线
  const base = live && ru.price ? ru.price.c : prev;
  const chg = px != null && base ? px - base : null, chgPct = chg != null ? chg / base * 100 : null;
  const open = tradingNow(now), tickAge = pxMs ? (now - pxMs) / 60000 : null, quoteOld = live ? (tickAge != null && tickAge > 15) : false;
  const p = ru.position; let pnl = null;
  if (p) pnl = { r: px != null ? p.side * (px / p.entryPx - 1) * 100 : p.r, amt: px != null ? p.side * (px - p.entryPx) * p.lots * 10 : null };
  const st = ru.act === "go" ? "short" : ru.act === "exit" || ru.act === "hold" ? (ru.act === "exit" ? "exit" : "hold") : "wait";
  const label = ru.act === "go" ? "做空入场" : ru.state === "blocked" ? "暂缓做空" : ru.act === "exit" ? "该平：" + (ru.head || "") : ru.act === "hold" ? "持有" : (ru.head || "观望").split("：")[0];
  const data = { signal: { state: st, label, why: ru.sub || "", ref: ru.order ? ru.order.lim : null, stop: ru.order ? ru.order.stop : null, pct: null, fsum: null, delev: false, priceDate: ru.price ? ru.price.d : null }, position: p ? { side: p.side, lots: p.lots, entryPx: p.entryPx, entryD: p.entryD, stop: p.stop, trail: null, action: p.action } : null, contract: { name: "3月季节做空" }, updatedAt: D.data.updatedAt };
  return { name: "橡胶", kind: "ru", data, sym: ru.symbol, px, pxMs, src, chg, chgPct, open, quoteOld, sigOld: false, stale: D.stale, pnl, now };
}

// ---------- 选显示哪个品种 ----------
// 规则：① 有「要处理」的（入场信号、该平）优先弹出；② 否则有持仓的优先；③ 都没有 → 豆粕。
// 同一档里有两个（同时有信号 / 同时持仓）→ 按时间轮换（每 5 分钟换一个，widget 每次刷新就换一次）。
function attention(g) {
  const s = g.data.signal, p = g.data.position;
  if (s.state === "long" || s.state === "short") return 2;   // 入场信号
  if (p && s.state === "exit") return 2;                     // 该平
  if (p) return 1;                                           // 持仓
  return 0;
}
function pickItems(items, now) {
  const lv = items.map(attention), top = Math.max(...lv);
  const cand = items.filter((_, i) => lv[i] === top);
  if (top === 0) return { show: items[0], others: items.slice(1), rotating: false };   // 都没信号没持仓：豆粕
  const show = cand[Math.floor(now / 300000) % cand.length];
  return { show, others: items.filter(x => x !== show), rotating: cand.length > 1 };
}
function brief(g) {   // 另一个品种的一句话
  const s = g.data.signal, p = g.data.position;
  if (p && g.pnl) return `${g.name}${p.side > 0 ? "多" : "空"}${p.lots}手${g.pnl.r == null ? "" : " " + sgn(g.pnl.r) + "%"}${s.state === "exit" ? "·该平" : ""}`;
  return `${g.name}：${s.label}`;
}

function sigColor(state) {
  return { long: C.up, short: C.down, exit: C.warn, hold: C.info, nodata: C.gray, wait: C.gray }[state] || C.gray;
}
function priceColor(chg) { return chg == null || chg === 0 ? C.text : chg > 0 ? C.up : C.down; }

// 状态小标签："实时 14:22 东财" / "休市 · 收盘价" / "报价较旧"
function pxTag(g) {
  if (g.px == null) return "无报价";
  const t = g.pxMs ? hhmm(g.pxMs) : "";
  if (g.stale) return `离线缓存 ${t}`;
  if (g.quoteOld || !g.open) return `${g.open ? "报价较旧" : "休市"} ${t}`;
  return `${t} ${g.src}`;
}
function sigLine(g) {
  const s = g.data.signal, p = g.data.position;
  if (p && g.pnl) {
    const sd = p.side > 0 ? "多" : "空", r = g.pnl.r;
    return `${sd}${p.lots}手 ${r == null ? "" : sgn(r) + "%"}${g.pnl.amt != null ? " " + sgnInt(g.pnl.amt) + "元" : ""}`;
  }
  return s.label;
}

// ---------- 画 ----------
function addTxt(parent, text, size, color, bold, opts) {
  const t = parent.addText(String(text));
  t.font = bold ? Font.boldSystemFont(size) : Font.systemFont(size);
  t.textColor = color; t.lineLimit = (opts && opts.lines) || 1; t.minimumScaleFactor = 0.6;
  return t;
}
function priceText(parent, g, size) {
  const t = parent.addText(g.px == null ? "—" : f0(g.px));
  t.font = Font.boldMonospacedSystemFont ? Font.boldMonospacedSystemFont(size) : Font.boldSystemFont(size);
  t.textColor = priceColor(g.chg); t.minimumScaleFactor = 0.6; t.lineLimit = 1;
  return t;
}
function chgText(g) { return g.chg == null ? "" : `${sgnInt(g.chg)}  ${sgn(g.chgPct, 2)}%`; }

function buildHome(g, family) {
  const w = new ListWidget(); w.backgroundColor = C.bg; w.url = SITE;
  w.setPadding(12, 14, 12, 14);
  const s = g.data.signal, p = g.data.position;
  const big = family === "large", small = family === "small";

  const head = w.addStack(); head.centerAlignContent();
  addTxt(head, `${g.name} ${g.sym || ""}`, small ? 12 : 13, C.sub, true);
  head.addSpacer();
  addTxt(head, pxTag(g), 10, g.quoteOld || g.stale ? C.warn : C.sub, false);

  w.addSpacer(small ? 2 : 4);
  priceText(w, g, small ? 30 : 36);
  addTxt(w, chgText(g), small ? 12 : 14, priceColor(g.chg), true);

  w.addSpacer(small ? 6 : 8);
  // 信号条
  const bar = w.addStack(); bar.centerAlignContent(); bar.cornerRadius = 8; bar.setPadding(5, 9, 5, 9);
  bar.backgroundColor = dyn(sigColorHex(s.state, false), sigColorHex(s.state, true));
  addTxt(bar, p && g.pnl ? (g.data.position.action === "持有" ? "持仓" : "该平") : s.label, small ? 13 : 15, new Color("#FFFFFF"), true);
  bar.addSpacer(6);
  if (!small) addTxt(bar, p ? sigLine(g) : (s.ref != null ? `参考价 ${f0(s.ref)}` : ""), 12, new Color("#FFFFFF"), false);
  if (small && p) { w.addSpacer(3); addTxt(w, sigLine(g), 12, C.text, true); }

  if (!small) {
    w.addSpacer(6);
    if (p) {
      const lines = [`开仓 ${f0(p.entryPx)}（${p.entryD.slice(5)}）`, p.trail != null ? `移动止损 ${f0(p.trail)}` : `止损 ${f0(p.stop)}`];
      addTxt(w, lines.join("  ·  "), 12, C.sub, false);
    } else {
      addTxt(w, s.why || "", 12, C.sub, false, { lines: big ? 3 : 2 });
      if (s.state === "long" || s.state === "short") addTxt(w, `建议限价 ${s.state === "long" ? "≤" : "≥"} ${f0(s.ref)}，止损 ${f0(s.stop)}`, 12, C.text, true);
    }
  }
  if (big && g.kind === "soy") {
    w.addSpacer(8);
    addTxt(w, `价格分位 ${s.pct == null ? "—" : s.pct + "%"}   外资最弱席位5日 ${s.fsum == null ? "—" : sgnInt(s.fsum)} 手${s.delev ? "（去杠杆）" : ""}`, 12, C.sub, false);
    addTxt(w, `信号数据日 ${s.priceDate || "—"}  ·  合约 ${g.data.contract.name}`, 11, C.sub, false);
  }
  if (g.other && g.other.length && !small) { w.addSpacer(4); addTxt(w, "另：" + g.other.map(brief).join(" · ") + (g.rotating ? "（轮换中）" : ""), 11, C.info, false); }
  if (g.sigOld) { w.addSpacer(4); addTxt(w, "⚠ 信号文件超过45分钟没更新，检查 Actions", 10, C.warn, false); }

  w.addSpacer();
  addTxt(w, `刷新 ${hhmm(g.now)} · 仅供参考，操作以驾驶舱为准`, 9, C.gray, false);
  return w;
}

function sigColorHex(state, dark) {
  const m = { long: ["#D93025", "#C9372C"], short: ["#0E9F5B", "#12844F"], exit: ["#C26A00", "#B25F00"], hold: ["#1A5FD0", "#2B5BB5"], nodata: ["#8A8F98", "#5E636C"], wait: ["#8A8F98", "#5E636C"] };
  return (m[state] || m.wait)[dark ? 1 : 0];
}

function buildLock(g, family) {
  const w = new ListWidget(); w.url = SITE;
  const s = g.data.signal, p = g.data.position, tag = p ? (p.action === "持有" ? "持" : "平") : s.state === "long" ? "多" : s.state === "short" ? "空" : s.state === "nodata" ? "缺" : "观";
  if (family === "accessoryInline") {
    addTxt(w, `${g.name} ${f0(g.px)} ${g.chgPct == null ? "" : sgn(g.chgPct, 1) + "%"} ${p ? sigLine(g) : s.label}`, 12, Color.white(), false);
  } else if (family === "accessoryCircular") {
    w.addAccessoryWidgetBackground = true;
    const st = w.addStack(); st.layoutVertically(); st.centerAlignContent();
    addTxt(st, f0(g.px), 14, Color.white(), true);
    addTxt(st, tag, 12, Color.white(), true);
  } else {   // accessoryRectangular
    addTxt(w, `${g.name} ${g.sym || ""}  ${f0(g.px)}`, 14, Color.white(), true);
    addTxt(w, `${chgText(g)}`, 12, Color.white(), false);
    addTxt(w, p ? sigLine(g) : s.label + (s.state === "long" || s.state === "short" ? ` ${f0(s.ref)}` : ""), 12, Color.white(), true);
  }
  return w;
}

function buildError() {
  const w = new ListWidget(); w.backgroundColor = C.bg; w.url = SITE;
  addTxt(w, "豆粕", 14, C.sub, true);
  addTxt(w, "取不到数据", 16, C.warn, true);
  addTxt(w, "检查网络，或确认 GH_USER / GH_REPO 填对、仓库已开 Pages 且 data/widget.json 存在", 11, C.sub, false, { lines: 4 });
  return w;
}

// ---------- 入口 ----------
const D = await loadData();
let g = null;
if (D) {
  const soy = await gather(D), ru = await gatherRu(D), items = [soy, ru].filter(Boolean), pk = pickItems(items, Date.now());
  g = pk.show; g.other = pk.others; g.rotating = pk.rotating;
}
const family = config.widgetFamily || "medium";
let widget;
if (!g) widget = buildError();
else if (String(family).startsWith("accessory")) widget = buildLock(g, family);
else widget = buildHome(g, family);

// 交易时段 5 分钟后再刷；休市 30 分钟（iOS 实际不一定按这个来）
widget.refreshAfterDate = new Date(Date.now() + (g && g.open ? 5 : 30) * 60e3);

if (config.runsInWidget) Script.setWidget(widget);
else if (String(family).startsWith("accessory")) await widget.presentAccessoryRectangular();
else if (family === "small") await widget.presentSmall();
else if (family === "large") await widget.presentLarge();
else await widget.presentMedium();
Script.complete();
