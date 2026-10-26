// 豆粕 + 橡胶驾驶舱 · iOS 桌面小组件（Scriptable 脚本，v102.13）
// 使用：App Store 装免费的 Scriptable → 新建脚本 → 把本文件全部内容粘进去 → 桌面长按添加 Scriptable 小组件 → 编辑小组件选这个脚本。
// 小/中/大尺寸 + 锁屏三种尺寸都支持。点小组件会打开驾驶舱网页。
// v102.13：大号逐条打勾（做多4条/做空3条）、外资离去杠杆线还有多远、统一状态词（休市/离线）、橡胶休眠时不占位、锁屏状态点（需要 data/widget.json v3，Actions 跑一次后生效；旧文件也能显示，只是没有打勾表）。
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
// 逐条条件的顺序必须和 scripts/build_widget.js 的 buildChecks() 一致：做多 [低位, 反弹, 外资未去杠杆, 基差]，做空 [去杠杆, 收盘<MA20, 高位]

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
  for (const u of JSON_URLS.concat(JSON_URLS)) {   // 两个地址各试两轮：手机刚恢复网络时第一次常失败，不然就误显示「离线」
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
  return { name: "橡胶", kind: "ru", sleep: ru.state === "sleep" && !p, data, sym: ru.symbol, px, pxMs, src, chg, chgPct, open, quoteOld, sigOld: false, stale: D.stale, pnl, now };
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

// 状态小标签（三种尺寸统一）：休市（灰）/ 盘中 HH:MM 来源 / 报价较旧（橙）/ 离线（橙，信号文件没取到，用的是手机里的缓存）
function pxTag(g) {
  if (g.stale) { const u = g.data.updatedAt ? hhmm(Date.parse(g.data.updatedAt)) : "—"; return { t: `离线·缓存 ${u}`, warn: true }; }
  if (g.px == null) return { t: "无报价", warn: true };
  const t = g.pxMs ? hhmm(g.pxMs) : "";
  if (g.quoteOld && g.open) return { t: `报价较旧 ${t}`, warn: true };
  if (!g.open) return { t: `休市·收盘 ${t}`, warn: false };
  return { t: `${t} ${g.src}`, warn: false };
}
function sigLine(g) {
  const s = g.data.signal, p = g.data.position;
  if (p && g.pnl) {
    const sd = p.side > 0 ? "多" : "空", r = g.pnl.r;
    return `${sd}${p.lots}手 ${r == null ? "" : sgn(r) + "%"}${g.pnl.amt != null ? " " + sgnInt(g.pnl.amt) + "元" : ""}`;
  }
  return s.label;
}

// ---------- 小标签（和页面「入场信号」那排标签同款：✓ 满足 / ✗ 不满足）----------
const TAG_L = ["低位", "反弹", "外资", "基差"], TAG_S = ["去杠杆", "MA20", "高位"];                         // 小号/中号简称
const TAG_L_LONG = ["价格分位≤50%", "反弹确认", "外资未去杠杆", "期货不高于现货"], TAG_S_LONG = ["外资去杠杆", "收盘<MA20", "价格分位≥70%"];   // 大号全称
const CH = {
  okBg: dyn("#E6F2EA", "#1F3A2B"), okFg: dyn("#2F7D4F", "#7BD39B"),
  noBg: dyn("#FBF3DD", "#3D3418"), noFg: dyn("#B7860B", "#E5B94B"),
  nuBg: dyn("#EEEFF2", "#2A2D33"), nuFg: dyn("#8A8F98", "#7C828C")
};
// mode: "s" 小号（只带分位值）/ "m" 中号（再带外资手数、基差）/ "l" 大号（全称 + 全部值）
function tagsOf(side, g, mode) {
  const s = g.data.signal, arr = s.chk[side], long = mode === "l", names = side === "L" ? (long ? TAG_L_LONG : TAG_L) : (long ? TAG_S_LONG : TAG_S);
  return arr.map((c, i) => {
    const pct = (side === "L" && i === 0) || (side === "S" && i === 2), fx = (side === "L" && i === 2) || (side === "S" && i === 0), bs = side === "L" && i === 3;
    let val = "";
    if (pct && c[1] != null) val = c[1] + "%";
    else if (mode !== "s" && fx && s.fsum != null) val = sgnInt(s.fsum);
    else if (mode !== "s" && bs && c[0] != null && c[1] != null) val = sgn(c[1], 1) + "%";
    return { ok: c[0], name: names[i], t: names[i] + (val ? (pct && !long ? "" : " ") + val : "") };
  });
}
function closestSide(g) {   // 哪一边更接近出信号（已出信号的那边优先；一样近时看做多）
  const s = g.data.signal; if (s.state === "short") return "S"; if (s.state === "long") return "L";
  const L = s.chk.L, S = s.chk.S;
  return chkCount(S) / S.length > chkCount(L) / L.length ? "S" : "L";
}
function sideInfo(g, side, mode) {
  const arr = g.data.signal.chk[side], n = arr.length;
  return { side, title: side === "L" ? "做多" : "做空", short: side === "L" ? "多" : "空", have: chkCount(arr), n, tags: tagsOf(side, g, mode || "s") };
}
function missingTag(g) {   // 最接近那边「差哪条」，锁屏用
  const si = sideInfo(g, closestSide(g)), m = si.tags.find(t => t.ok === 0);
  return m ? m.name : "";
}
function addTag(parent, tg, size, style) {   // style: "big" 大号 / "tight" 中号（更矮）/ "" 默认
  const big = style === "big", tight = style === "tight";
  const c = parent.addStack(); c.setPadding(big ? 2 : tight ? 0 : 1, big ? 9 : 5, big ? 2 : tight ? 0 : 1, big ? 9 : 5); c.cornerRadius = big ? 10 : 7; c.centerAlignContent();
  c.backgroundColor = tg.ok === 1 ? CH.okBg : tg.ok === 0 ? CH.noBg : CH.nuBg;
  const t = c.addText((tg.ok === 1 ? "✓" : tg.ok === 0 ? "✗" : "–") + tg.t);
  t.font = Font.systemFont(size); t.lineLimit = 1; t.minimumScaleFactor = 0.7;
  t.textColor = tg.ok === 1 ? CH.okFg : tg.ok === 0 ? CH.noFg : CH.nuFg;
}
function addTagRows(parent, tags, size, style) {   // 一行一个
  tags.forEach(tg => { const r = parent.addStack(); r.centerAlignContent(); addTag(r, tg, size, style); parent.addSpacer(style === "big" ? 3 : 1); });
}

// ---------- 基本面 / 橡胶 ----------
function dirColor(d) { return d === "偏多" ? C.up : d === "偏空" ? C.down : C.sub; }   // 和价格一样：红=多、绿=空
function fundOf(g) { const f = g.kind === "soy" ? g.data.fund : null; return f && f.cp != null ? f : null; }
// 仪表盘同款「倾向条」：圆角底条 + 两侧 ±22% 阈值刻度 + 中线；偏多从中线向右填红，偏空向左填绿
function palette() {
  let d = false; try { d = Device.isUsingDarkAppearance(); } catch (e) {}
  return { bull: new Color(d ? "#FF6B63" : "#D03A33"), bear: new Color(d ? "#3ACB93" : "#13915B"), track: new Color(d ? "#2A2D33" : "#E9ECF0"), line: new Color(d ? "#6A707C" : "#9AA1AD"), tick: new Color(d ? "#454A55" : "#CDD2DA") };
}
function newDC(w, h) { const dc = new DrawContext(); dc.size = new Size(w, h); dc.opaque = false; dc.respectScreenScale = true; return dc; }
function compImage(w, h, ratio) {
  const dc = newDC(w, h), P = palette(), r = Math.max(-1, Math.min(1, ratio));
  const bg = new Path(); bg.addRoundedRect(new Rect(0, 0, w, h), h / 2, h / 2); dc.addPath(bg); dc.setFillColor(P.track); dc.fillPath();
  dc.setFillColor(P.tick); [0.5 - 0.11, 0.5 + 0.11].forEach(f => dc.fillRect(new Rect(Math.round(w * f), 2, 1, h - 4)));
  const half = Math.abs(r) * w / 2;
  if (half > 0.5) { dc.setFillColor(r > 0 ? P.bull : P.bear); dc.fillRect(new Rect(r > 0 ? w / 2 : w / 2 - half, 0, half, h)); }
  dc.setFillColor(P.line); dc.fillRect(new Rect(Math.round(w / 2), 0, 1, h));
  return dc.getImage();
}
function sparkImage(vals, w, h) {   // 近 N 个交易日的综合倾向：每天一根柱，中线上红下绿，细线=±22% 方向阈值；纵轴满刻度 ±50%
  const dc = newDC(w, h), P = palette(), n = vals.length, slot = w / Math.max(n, 1), bw = Math.max(3, slot * 0.58), mid = h / 2, R = 50;
  dc.setFillColor(P.tick); [22, -22].forEach(t => dc.fillRect(new Rect(0, Math.round(mid - t / R * (mid - 1)), w, 1)));
  vals.forEach((v, i) => {
    const bh = Math.max(1, Math.min(1, Math.abs(v) / R) * (mid - 1)), x = i * slot + (slot - bw) / 2;
    dc.setFillColor(v >= 0 ? P.bull : P.bear); dc.fillRect(new Rect(x, v >= 0 ? mid - bh : mid, bw, bh));
  });
  dc.setFillColor(P.line); dc.fillRect(new Rect(0, Math.round(mid), w, 1));
  return dc.getImage();
}
function addImg(parent, img, w, h) { const im = parent.addImage(img); im.imageSize = new Size(w, h); return im; }
function addChg(parent, label, v, size) {   // 「较前日 ▲6点」：涨(更偏多)红、跌(更偏空)绿、持平灰
  const h = parent.addStack(); h.centerAlignContent();
  addTxt(h, label + " ", size, C.sub, false);
  addTxt(h, v == null ? "—" : v === 0 ? "持平" : (v > 0 ? "▲" : "▼") + Math.abs(v) + "点", size, v == null || v === 0 ? C.sub : v > 0 ? C.up : C.down, v != null && v !== 0);
}
// 中号：综合一行 + 倾向条 + 变动一行
function addCompMid(parent, g, w) {
  const f = fundOf(g); if (!f) return;
  const h = parent.addStack(); h.centerAlignContent();
  addTxt(h, "综合 ", 10, C.sub, false); addTxt(h, f.comp || "—", 11, dirColor(f.comp), true); h.addSpacer(4); addTxt(h, sgn(f.cp, 0) + "%", 11, dirColor(f.comp), true);
  parent.addSpacer(1); addImg(parent, compImage(w * 2, 16, f.cp / 100), w, 8); parent.addSpacer(1);
  const r = parent.addStack(); r.centerAlignContent(); addChg(r, "较前日", f.c1, 9); r.addSpacer(6); addChg(r, "5日", f.c5, 9);
}
// 大号：标题 + 倾向条 + 变动两项 + 近10个交易日走势柱
function addCompBig(parent, g, w) {
  const f = fundOf(g); if (!f) return;
  const h = parent.addStack(); h.centerAlignContent();
  addTxt(h, "基本面·综合", 13, C.text, true); h.addSpacer(8); addTxt(h, f.comp || "—", 13, dirColor(f.comp), true); h.addSpacer(4); addTxt(h, sgn(f.cp, 0) + "%", 13, dirColor(f.comp), true);
  h.addSpacer(); addTxt(h, `${f.conf ? "置信" + f.conf + " · " : ""}${f.d ? f.d.slice(5) : ""}`, 10, C.sub, false);
  parent.addSpacer(3); addImg(parent, compImage(w * 2, 22, f.cp / 100), w, 11); parent.addSpacer(4);
  const r = parent.addStack(); r.centerAlignContent(); addChg(r, "较上一交易日", f.c1, 11); r.addSpacer(10); addChg(r, "较5个交易日前", f.c5, 11);
  if (f.pd && f.comp && f.pd !== f.comp) { r.addSpacer(8); addTxt(r, `（前日${f.pd}）`, 10, C.warn, false); }
  if (f.h && f.h.length > 1) { parent.addSpacer(4); addImg(parent, sparkImage(f.h, w * 2, 48), w, 24); }
}
// 橡胶：休眠时也显示（用户要求三种尺寸都看得到）。mode: short 小号 / mid 中号 / long 大号
function rubberOf(g) { return g.kind === "soy" ? (g.other || []).find(x => x.kind === "ru") || null : null; }
function rubberText(g, mode) {
  const x = rubberOf(g); if (!x) return null;
  if (!x.sleep) return { t: brief(x), sleep: false };
  const why = x.data.signal.why || "", m = /还有\s*(\d+)\s*天/.exec(why);
  if (mode === "short") return { t: "橡胶休眠", sleep: true };
  if (mode === "mid") return { t: m ? `橡胶休眠·距3月开窗${m[1]}天` : "橡胶休眠", sleep: true };
  return { t: "橡胶：休眠 · " + (why.split("。")[0] || "只在3月做"), sleep: true };
}

// ---------- 逐条条件 ----------
function hasChk(g) {
  if (g.kind !== "soy") return false;
  const s = g.data.signal; if (s.gateOk === false) return false;
  if (s.chk && s.chk.L) return true;
  // 旧版 widget.json（v2）没有逐条条件：用已有的分位、外资去杠杆合成，其余两条标「待更新」（Actions 下次运行后自动变成完整的）
  if (s.pct == null) return false;
  s.chkSynth = true;
  s.chk = { L: [[s.pct <= 50 ? 1 : 0, s.pct], [null, null], [s.delev ? 0 : 1, null], [null, null]], S: [[s.delev ? 1 : 0, null], [null, null], [s.pct >= 70 ? 1 : 0, s.pct]] };
  return true;
}
function chkCount(arr) { return arr.filter(c => c[0] === 1).length + arr.filter(c => c[0] == null).length; }   // 没数据的按「不拦」算满足
// 小号/锁屏用的一句话：差哪一条
function shortWhy(g) {
  const s = g.data.signal;
  if (g.kind !== "soy") return s.why || "";
  if (s.gateOk === false) return "数据不足：" + (s.why || "");
  if (!s.chk || !s.chk.L) return s.why || "";
  const L = s.chk.L;
  if (s.state === "wait" || s.state === "nodata") {
    if (L[0][0] === 0) return `分位${s.pct == null ? "—" : s.pct + "%"} 不在低位（需≤50%）`;
    if (L[1][0] === 0) return "已在低位，等反弹确认";
    if (L[2][0] === 0) return "外资在去杠杆，不做多";
    if (L[3][0] === 0) return "期货高于现货，不做多";
  }
  return s.why || "";
}
// 外资离「去杠杆线」还有多远（做多的拦截条件，也是做空的触发条件）
function fxInfo(g) {
  const sg = g.data.signal; if (g.kind !== "soy") return null;
  const fx = sg.fx || (sg.fsum != null ? { v: sg.fsum, k: "合计", line: -20000 } : null); if (!fx) return null;
  const gap = fx.v - fx.line;   // >0 = 还没到线
  const near = fx.v <= fx.line * 0.7;
  return { text: `外资 ${fx.k} ${sgnInt(fx.v)} / 线 ${sgnInt(fx.line)}`, gap, hit: gap <= 0, near, long: gap <= 0 ? "已到去杠杆线" : `距去杠杆线 ${f0(gap)} 手` };
}
// 锁屏状态点：🟢数据齐·观望 🟠数据缺/过期/离线 🔴有入场或该平 🔵持有
function dotOf(g) {
  const s = g.data.signal;
  if (g.stale || g.sigOld || g.quoteOld && g.open || s.gateOk === false || s.state === "nodata" || (s.lv && s.lv !== "ok")) return "🟠";
  if (s.state === "long" || s.state === "short" || s.state === "exit") return "🔴";
  if (s.state === "hold") return "🔵";
  return "🟢";
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

function addFxLine(parent, g, size, withGap) {
  const f = fxInfo(g); if (!f) return;
  addTxt(parent, f.text + (withGap ? `（${f.long}）` : ""), size, f.hit || f.near ? C.warn : C.sub, false);
}
function addHeader(w, g, small) {
  const head = w.addStack(); head.centerAlignContent();
  addTxt(head, `${g.name} ${g.sym || ""}`, small ? 12 : 13, C.sub, true);
  head.addSpacer();
  const tg = pxTag(g); addTxt(head, tg.t, 10, tg.warn ? C.warn : C.sub, false);
}
function addSignalBar(parent, g, small, extra) {
  const s = g.data.signal, p = g.data.position;
  const bar = parent.addStack(); bar.centerAlignContent(); bar.cornerRadius = 8; bar.setPadding(small ? 4 : 5, 9, small ? 4 : 5, 9);
  bar.backgroundColor = dyn(sigColorHex(s.state, false), sigColorHex(s.state, true));
  addTxt(bar, p && g.pnl ? (p.action === "持有" ? "持仓" : "该平") : s.label, small ? 13 : 15, new Color("#FFFFFF"), true);
  if (extra) { bar.addSpacer(5); addTxt(bar, extra, 11, new Color("#FFFFFF"), false); }
  if (!small) { bar.addSpacer(6); addTxt(bar, p ? sigLine(g) : (s.ref != null ? `参考价 ${f0(s.ref)}` : ""), 12, new Color("#FFFFFF"), false); }
  return bar;
}
function addFooter(w, g, family) {
  const d = g.data.signal.priceDate ? "数据" + g.data.signal.priceDate.slice(5) + " · " : "";
  if (family === "large") { addTxt(w, `${d}刷新 ${hhmm(g.now)} · 仅供参考，操作以驾驶舱为准`, 9, C.gray, false); return; }
  const rb = rubberText(g, family === "small" ? "short" : "mid");
  const line = family === "small" ? `${rb ? rb.t + " · " : ""}刷新 ${hhmm(g.now)}` : `${rb ? rb.t + " · " : ""}${d}刷新 ${hhmm(g.now)}`;
  addTxt(w, line, 9, rb && !rb.sleep ? C.info : C.gray, false);
}
function addPosLines(parent, g, size) {
  const p = g.data.position; if (!p) return;
  addTxt(parent, `开仓 ${f0(p.entryPx)}（${p.entryD.slice(5)}）`, size, C.sub, false);
  addTxt(parent, p.trail != null ? `移动止损 ${f0(p.trail)}` : `止损 ${f0(p.stop)}`, size, C.sub, false);
}
function addOther(w, g) {   // 另一个品种：橡胶休眠（只在3月做）时不占位
  const o = (g.other || []).filter(x => !(x.kind === "ru" && x.sleep));
  if (!o.length) return false;
  addTxt(w, "另：" + o.map(brief).join(" · ") + (g.rotating ? "（轮换中）" : ""), 11, C.info, false); return true;
}

function addTagBlock(parent, si, otherText, size, style) {   // 标题 + 一行一个标签（大号用）
  const h = parent.addStack(); h.centerAlignContent();
  addTxt(h, si.title + "条件", size + 1, C.text, true); h.addSpacer(6); addTxt(h, `${si.have}/${si.n}`, size + 1, si.have === si.n ? C.up : C.sub, true);
  if (otherText) { h.addSpacer(8); addTxt(h, otherText, size - 2, C.gray, false); }
  parent.addSpacer(3); addTagRows(parent, si.tags, size, style);
}

function buildHome(g, family) {
  const w = new ListWidget(); w.backgroundColor = C.bg; w.url = SITE;
  w.setPadding(12, 14, 12, 14);
  const s = g.data.signal, p = g.data.position;
  const small = family === "small", chk = hasChk(g) && !p;
  const sd = chk ? closestSide(g) : null, other = chk ? sideInfo(g, sd === "S" ? "L" : "S") : null;
  const hint = o => o ? `${o.title} ${o.have}/${o.n}` : "";
  const buyAdvice = sz => (s.state === "long" || s.state === "short") ? addTxt(w, `建议限价 ${s.state === "long" ? "≤" : "≥"} ${f0(s.ref)}，止损 ${f0(s.stop)}`, sz, C.text, true) : null;

  addHeader(w, g, small);
  w.addSpacer(small ? 2 : 4);

  if (family === "small") {
    const pr = w.addStack(); pr.bottomAlignContent();
    priceText(pr, g, 28); pr.addSpacer(6);
    addTxt(pr, g.chgPct == null ? "" : sgn(g.chgPct, 2) + "%", 11, priceColor(g.chg), true);
    w.addSpacer(4);
    if (chk) {   // 左：观望按钮（压到下面）+ 进度；右：最接近出信号那边的条件，一行一个
      const si = sideInfo(g, sd, "s");
      const row = w.addStack(); row.topAlignContent();
      const left = row.addStack(); left.layoutVertically(); left.size = new Size(56, 0);
      left.addSpacer(8); addSignalBar(left, g, true); left.addSpacer(2); addTxt(left, `${si.short} ${si.have}/${si.n}`, 10, C.sub, false);
      row.addSpacer(6);
      const right = row.addStack(); right.layoutVertically(); addTagRows(right, si.tags, 10, "");
    } else {
      addSignalBar(w, g, true); w.addSpacer(3);
      if (p && g.pnl) addTxt(w, sigLine(g), 12, C.text, true); else addTxt(w, shortWhy(g), 11, C.sub, false, { lines: 2 });
    }
  } else if (family === "medium") {
    // 左：价格 + 信号条 + 两边进度；右：最接近那边的条件（一行一个）+ 综合倾向条
    const row = w.addStack(); row.topAlignContent();
    const left = row.addStack(); left.layoutVertically(); left.size = new Size(138, 0);
    priceText(left, g, 30); addTxt(left, chgText(g), 13, priceColor(g.chg), true); left.addSpacer(4); addSignalBar(left, g, true);
    if (chk) { left.addSpacer(3); addTxt(left, `${sideInfo(g, sd).title} ${sideInfo(g, sd).have}/${sideInfo(g, sd).n} · ${hint(other)}`, 9, C.sub, false); }
    row.addSpacer(10);
    const right = row.addStack(); right.layoutVertically();
    if (chk) { addTagRows(right, sideInfo(g, sd, "m").tags, 10, "tight"); addCompMid(right, g, 164); }
    else if (p) { addTxt(right, sigLine(g), 13, C.text, true); right.addSpacer(2); addPosLines(right, g, 11); addCompMid(right, g, 164); }
    else { addTxt(right, s.why || shortWhy(g), 11, C.sub, false, { lines: 4 }); right.addSpacer(3); addCompMid(right, g, 164); }
  } else {   // large：用弹性间距把各块均匀撑开
    priceText(w, g, 36);
    addTxt(w, chgText(g), 14, priceColor(g.chg), true);
    w.addSpacer(6);
    addSignalBar(w, g, false);
    w.addSpacer();
    if (p) { addPosLines(w, g, 13); w.addSpacer(); addFxLine(w, g, 12, true); }
    else if (chk) {
      buyAdvice(13); if (s.state === "long" || s.state === "short") w.addSpacer(3);
      addTagBlock(w, sideInfo(g, sd, "l"), hint(other), 11, "big");
      w.addSpacer(); addFxLine(w, g, 12, true);
    } else { addTxt(w, s.why || shortWhy(g), 13, s.state === "nodata" ? C.warn : C.sub, false, { lines: 5 }); buyAdvice(13); }
    w.addSpacer(); addCompBig(w, g, 316);
    w.addSpacer();
    const rb = rubberText(g, "long"); if (rb) addTxt(w, rb.t, 11, rb.sleep ? C.gray : C.info, false);
  }
  if (g.sigOld) { w.addSpacer(3); addTxt(w, "⚠ 信号文件超过45分钟没更新，检查 Actions", 10, C.warn, false); }

  w.addSpacer();
  addFooter(w, g, family);
  return w;
}

function sigColorHex(state, dark) {
  const m = { long: ["#D93025", "#C9372C"], short: ["#0E9F5B", "#12844F"], exit: ["#C26A00", "#B25F00"], hold: ["#1A5FD0", "#2B5BB5"], nodata: ["#8A8F98", "#5E636C"], wait: ["#8A8F98", "#5E636C"] };
  return (m[state] || m.wait)[dark ? 1 : 0];
}

function buildLock(g, family) {
  const w = new ListWidget(); w.url = SITE;
  const s = g.data.signal, p = g.data.position, dot = dotOf(g), tag = p ? (p.action === "持有" ? "持" : "平") : s.state === "long" ? "多" : s.state === "short" ? "空" : s.state === "nodata" ? "缺" : "观";
  if (family === "accessoryInline") {
    addTxt(w, `${dot}${g.name} ${f0(g.px)} ${g.chgPct == null ? "" : sgn(g.chgPct, 1) + "%"} ${p ? sigLine(g) : s.label}`, 12, Color.white(), false);
  } else if (family === "accessoryCircular") {
    w.addAccessoryWidgetBackground = true;
    const st = w.addStack(); st.layoutVertically(); st.centerAlignContent();
    addTxt(st, f0(g.px), 14, Color.white(), true);
    addTxt(st, dot + tag, 12, Color.white(), true);
  } else {   // accessoryRectangular：3 行 —— 价格 / 涨跌+状态 / 状态点+结论+一句原因
    const tg = pxTag(g);
    addTxt(w, `${g.name} ${g.sym || ""}  ${f0(g.px)}`, 14, Color.white(), true);
    addTxt(w, `${chgText(g)}${tg.warn || !g.open ? "  " + tg.t.split(" ")[0] : ""}`, 12, Color.white(), false);
    let l3;
    if (p) l3 = `${dot} ${sigLine(g)}`;
    else if (s.state === "long" || s.state === "short") l3 = `${dot} ${s.label} ${f0(s.ref)}`;
    else if (s.state === "nodata") l3 = `${dot} 数据不足`;
    else if (hasChk(g)) { const si = sideInfo(g, closestSide(g)), ms = missingTag(g); l3 = `${dot} ${s.label} ${si.short}${si.have}/${si.n}${ms ? " 差" + ms : ""}`; }
    else l3 = `${dot} ${s.label}${s.pct != null && g.kind === "soy" ? " · 分位" + s.pct + "%" : ""}`;
    addTxt(w, l3, 12, Color.white(), true);
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
