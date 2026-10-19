/* 橡胶(RU) 3月季节性做空 —— 期货组合页的第二个品种（v102.0）
 * 规则来自 Ted 给的基本面文字 + 回测：只在3月做、只做空；收盘站上MA5（反弹）才挂单（不追空）；
 * 次日限价卖出 ≥ 收盘价+0.3%；5%止损；3月最后一个交易日收盘平仓；不设止盈（回测里止盈更差）；
 * 天气筛选（泰国南部/东北、越南东南、云南、海南，Open-Meteo）：严重异常不做空。天气条件没有历史回测，只作为 Ted 要求的过滤。
 * 纯函数放在 RU_BEGIN..RU_END 之间，tests/test_rubber.js 按标记抽出来测。 */
/* RU_BEGIN */
const RUP = { STOP: 5, LIM: 0.3, MA: 5, COST: 3e-4, TON: 10, TICK: 5, MON: 3, PRE_FROM: '02-10', AVG_DROP: 5.8, RISK: 2, MARGIN: 12, USE_CAP: 30 };
const RUREG = [
  { k: 'ths', n: '泰国南部（合艾）', lat: 7.0, lon: 100.47, tz: 'Asia/Bangkok', core: true },
  { k: 'the', n: '泰国东北（乌隆）', lat: 17.4, lon: 102.8, tz: 'Asia/Bangkok', core: false },
  { k: 'vn', n: '越南东南（平福）', lat: 11.75, lon: 106.9, tz: 'Asia/Ho_Chi_Minh', core: false },
  { k: 'yn', n: '云南（西双版纳）', lat: 22.0, lon: 100.8, tz: 'Asia/Shanghai', core: true },
  { k: 'hn', n: '海南（儋州）', lat: 19.5, lon: 109.6, tz: 'Asia/Shanghai', core: false }
];
function ruMA(c, i, n) { if (i < n - 1) return null; let s = 0; for (let k = i - n + 1; k <= i; k++) s += c[k]; return s / n; }
function ruAddDays(d, n) { const t = new Date(d + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); }
function ruLastWeekdayOfMarch(y) { let d = y + '-03-31'; for (;;) { const w = new Date(d + 'T00:00:00Z').getUTCDay(); if (w !== 0 && w !== 6) return d; d = ruAddDays(d, -1); } }
function ruTickUp(x) { return Math.ceil(x / RUP.TICK - 1e-9) * RUP.TICK; }
/* 历史上每年3月按同一条规则会怎样（用换月调整价）：首个「收盘≥MA5」的3月交易日出信号，次日限价卖出≥收盘×1.003，成交价=max(限价,次日开盘)；5%止损按盘中最高价；否则3月最后一天收盘平仓 */
function ruSimYear(S, y) {
  const idx = []; for (let i = 0; i < S.d.length; i++) if (S.d[i].slice(0, 7) === y + '-03') idx.push(i);
  if (idx.length < 10) return null;
  const last = idx[idx.length - 1]; let ent = null, ei = -1, sig = null;
  for (let k = 0; k < idx.length - 1; k++) {
    const i = idx[k], m = ruMA(S.c, i, RUP.MA);
    if (m != null && S.c[i] >= m) { const nd = idx[k + 1], lim = S.c[i] * (1 + RUP.LIM / 100); if (S.h[nd] >= lim) { ent = Math.max(lim, S.o[nd]); ei = k + 1; sig = S.d[i]; break; } }
  }
  if (ent == null) return { y, trade: false };
  let out = null, why = '月底平仓', ed = S.d[last];
  for (let k = ei; k < idx.length; k++) { const i = idx[k]; if (S.h[i] >= ent * (1 + RUP.STOP / 100)) { out = -RUP.STOP / 100; why = '止损'; ed = S.d[i]; break; } }
  if (out == null) out = -(S.c[last] / ent - 1);
  return { y, trade: true, sig, entD: S.d[idx[ei === -1 ? 0 : ei]], exitD: ed, why, ret: out - 2 * RUP.COST };
}
function ruHistory(S) { const y0 = +S.d[0].slice(0, 4), y1 = +S.d[S.d.length - 1].slice(0, 4), a = []; for (let y = y0; y <= y1; y++) { const r = ruSimYear(S, y); if (r) a.push(r); } return a; }
function ruStats(H) {
  const t = H.filter(x => x.trade), n = t.length; if (!n) return null;
  const m = t.reduce((a, x) => a + x.ret, 0) / n, sd = Math.sqrt(t.reduce((a, x) => a + (x.ret - m) * (x.ret - m), 0) / Math.max(1, n - 1));
  return { n, years: H.length, mean: m * 100, win: t.filter(x => x.ret > 0).length / n * 100, worst: Math.min(...t.map(x => x.ret)) * 100, best: Math.max(...t.map(x => x.ret)) * 100, t: sd > 0 ? m / sd * Math.sqrt(n) : 0 };
}
/* 天气：一个区域的指标。fc={d[],p[],tx[]}（含过去30天+未来7天），hist={d[],p[],tx[]}（过去几年），today 北京日期 */
function ruRegionWx(fc, hist, today, years) {
  const d0 = ruAddDays(today, -29), past = [], fut = [];
  for (let i = 0; i < fc.d.length; i++) { if (fc.d[i] <= today) { if (fc.d[i] >= d0) past.push(i); } else if (fc.d[i] <= ruAddDays(today, 7)) fut.push(i); }
  const num = v => (v == null || isNaN(v) ? 0 : +v), p30 = past.reduce((a, i) => a + num(fc.p[i]), 0), p7 = past.slice(-7).reduce((a, i) => a + num(fc.p[i]), 0);
  const tx7 = past.slice(-7).map(i => fc.tx[i]).filter(v => v != null), t7 = tx7.length ? tx7.reduce((a, b) => a + b, 0) / tx7.length : null, f7 = fut.reduce((a, i) => a + num(fc.p[i]), 0);
  const norms = [], tnorm = []; const y0 = +today.slice(0, 4);
  (years || []).forEach(yy => { const sh = yy - y0, a = ruAddDays(today, 0).replace(/^\d{4}/, String(yy)), s = ruAddDays(a, -29); let sum = 0, cnt = 0, ts = [], tc = 0; for (let i = 0; i < hist.d.length; i++) { const d = hist.d[i]; if (d >= s && d <= a) { sum += num(hist.p[i]); cnt++; if (d >= ruAddDays(a, -6) && hist.tx[i] != null) ts.push(hist.tx[i]); } } if (cnt >= 25) norms.push(sum); if (ts.length >= 5) tnorm.push(ts.reduce((x, y) => x + y, 0) / ts.length); });
  const n30 = norms.length ? norms.reduce((a, b) => a + b, 0) / norms.length : null, tn = tnorm.length ? tnorm.reduce((a, b) => a + b, 0) / tnorm.length : null;
  let sev = 0; const msgs = [];
  if (n30 != null && n30 >= 20) {
    const ratio = p30 / n30, diff = p30 - n30;
    if (ratio < 0.25 && diff <= -30) { sev = Math.max(sev, 2); msgs.push('严重偏旱'); } else if (ratio < 0.5 && diff <= -30) { sev = Math.max(sev, 1); msgs.push('偏旱'); }
    else if (ratio > 3 && diff >= 100) { sev = Math.max(sev, 2); msgs.push('严重偏涝'); } else if (ratio > 2 && diff >= 60) { sev = Math.max(sev, 1); msgs.push('偏涝'); }
  }
  if (t7 != null && tn != null && t7 - tn >= 3.5) { sev = Math.max(sev, 1); msgs.push('高温'); }
  return { p30, p7, f7, n30, ratio: n30 ? p30 / n30 : null, t7, tn, sev, msg: msgs.join('、') || '正常' };
}
/* 汇总：核心产区（泰国南部、云南）严重异常，或各区「注意」累计≥3 → 暂缓做空；有注意 → 提示；取不到 → 不拦 */
function ruWxVerdict(rs) {
  const ok = rs.filter(r => r && !r.err);
  if (!ok.length) return { level: 'unknown', text: '天气数据没取到：不用天气过滤' };
  const blk = ok.filter(r => r.core && r.sev >= 2), sum = ok.reduce((a, r) => a + r.sev, 0), warn = ok.filter(r => r.sev >= 1);
  if (blk.length || sum >= 3) return { level: 'block', text: '主产区天气异常：' + (blk.length ? blk.map(r => r.n + ' ' + r.msg).join('、') : warn.map(r => r.n + ' ' + r.msg).join('、')) + '，暂缓做空' };
  if (warn.length) return { level: 'warn', text: '有产区轻度异常：' + warn.map(r => r.n + ' ' + r.msg).join('、') + '（不拦，留意）' };
  return { level: 'ok', text: '主产区天气正常' };
}
/* 当前该做什么。S 序列（含 r 真实收盘），today 北京日期，wx 天气结论，pos 记录的空单 {d,px,lots}|null */
function ruPlan(S, today, wx, pos, man) {
  const n = S.d.length, L = S.d[n - 1], y = +today.slice(0, 4), mmdd = today.slice(5), real = S.r[n - 1] != null ? S.r[n - 1] : null, scale = real ? S.c[n - 1] / real : null;
  const inMar = +today.slice(5, 7) === RUP.MON, pre = mmdd >= RUP.PRE_FROM && mmdd < '03-01', yE = ruLastWeekdayOfMarch(y);
  const dom = S.m && S.m[n - 1] ? 'RU' + S.m[n - 1] : null, yy = String(y).slice(2), bad = [];
  if (wx && wx.level === 'block') bad.push(wx.text);
  if (man && man.st === 'delay') bad.push('手动录入：开割延迟（干旱/洪涝）');
  if (man && man.demand) bad.push('手动录入：需求超预期走强（轮胎开工率回升）');
  const o = { today, last: L, real, dom, bad, inMar, pre, exitD: yE, wx, st: 'sleep', head: '', sub: '', chips: [], order: null, mar05: 'RU' + yy + '05', mar09: 'RU' + yy + '09' };
  const nextWin = (mmdd >= '04-01' ? (y + 1) : y) + '-03-01'; o.nextWin = nextWin; o.daysTo = Math.round((new Date(nextWin + 'T00:00:00Z') - new Date(today + 'T00:00:00Z')) / 864e5);
  const ma = ruMA(S.c, n - 1, RUP.MA), reb = ma != null && S.c[n - 1] >= ma; o.reb = reb; o.ma = ma != null && scale ? ma / scale : null;
  const stale = inMar && L < ruAddDays(today, -4); o.stale = stale;
  if (pos) {
    const r = real && pos.px ? -(real / pos.px - 1) * 100 : null; o.pos = { r, stop: pos.px * (1 + RUP.STOP / 100), stopGap: real && pos.px ? (pos.px * (1 + RUP.STOP / 100) / real - 1) * 100 : null };
    const exitDue = today >= yE || !inMar, stopHit = real != null && real >= o.pos.stop;
    if (stopHit) { o.st = 'exit'; o.head = '止损：平空单'; o.sub = '现价 ' + Math.round(real) + ' 已到止损价 ' + Math.round(o.pos.stop) + '（' + RUP.STOP + '%）'; }
    else if (exitDue) { o.st = 'exit'; o.head = today > yE ? '3月已过：平空单' : '今天是3月最后一个交易日：收盘前平空单'; o.sub = '季节窗口结束，不留到4月（开割后供应利空已兑现，没有历史优势）'; }
    else if (bad.length) { o.st = 'holdwx'; o.head = '持有空单·出现离场条件，考虑离场'; o.sub = bad.join('；') + '。你的规则：开割后天气持续异常、或需求超预期强劲回升，空头逻辑被破坏，应止盈或止损离场'; }
    else { o.st = 'hold'; o.head = '持有空单'; o.sub = '到 ' + yE + ' 收盘平仓；止损 ' + Math.round(o.pos.stop); }
    o.roll = !!(pos.contract && dom && pos.contract !== dom);
    return o;
  }
  if (!inMar) {
    if (pre) { o.st = 'pre'; o.head = '准备期：3月季节窗口 ' + o.daysTo + ' 天后开始'; o.sub = '3月1日起，价格收盘站上5日均线（反弹）且天气正常，才挂单做空；现在不动'; }
    else { o.st = 'sleep'; o.head = '休眠：只在3月做'; o.sub = '下一个窗口 ' + nextWin + '（还有 ' + o.daysTo + ' 天）。2月10日起进入准备期'; }
    return o;
  }
  if (stale) { o.st = 'stale'; o.head = '价格数据没更新到3月'; o.sub = '最新一根是 ' + L + '，需要 Actions 更新橡胶价格后才出信号'; return o; }
  if (today > yE) { o.st = 'sleep'; o.head = '3月窗口已结束'; o.sub = '下一个窗口 ' + nextWin; return o; }
  if (L.slice(0, 7) !== today.slice(0, 7)) { o.st = 'pre'; o.head = '3月窗口开始：等第一个3月收盘'; o.sub = '信号只看3月内的收盘；最新价格是 ' + L + '，等3月的第一根日线'; return o; }
  if (man && man.stopY === y) { o.st = 'done'; o.head = '今年3月已止损，不再开仓'; o.sub = '回测每年只做一次，止损后再开没有验证过；下一个窗口 ' + nextWin; return o; }
  if (bad.length) { o.st = 'blocked'; o.head = '暂缓做空'; o.sub = bad.join('；'); return o; }
  if (!reb) { o.st = 'wait'; o.head = '等反弹：收盘还在5日线下，不追空'; o.sub = '收盘 ' + (real ? Math.round(real) : '—') + (o.ma ? ' 低于 MA5 ' + Math.round(o.ma) : '') + '；逢反弹站上5日线再挂空单'; return o; }
  const lim = real ? ruTickUp(real * (1 + RUP.LIM / 100)) : null;
  o.st = 'go'; o.head = '做空信号：明日挂限价 ' + (lim ? '≥ ' + lim : ''); o.sub = '收盘站上MA5（反弹），天气' + (wx && wx.level === 'warn' ? '轻度异常' : wx && wx.level === 'ok' ? '正常' : '未知') + '；次日有效，没成交就作废，不追';
  o.order = { contract: dom, lim, stop: lim ? Math.round(lim * (1 + RUP.STOP / 100)) : null, ref: lim ? Math.round(lim * (1 - RUP.AVG_DROP / 100)) : null };
  return o;
}
/* 手数：单笔风险% 与 保证金占用上限 取小 */
function ruSize(eq, px, riskPct, margin) {
  if (!(eq > 0) || !(px > 0)) return { lots: 0 };
  const perLot = px * RUP.TON * RUP.STOP / 100, byRisk = Math.floor(eq * riskPct / 100 / perLot), byMargin = Math.floor(eq * RUP.USE_CAP / 100 / (px * RUP.TON * margin / 100));
  const lots = Math.max(0, Math.min(byRisk, byMargin)); return { lots, byRisk, byMargin, perLot, margin: lots * px * RUP.TON * margin / 100, loss: lots * perLot };
}
/* RU_END */
(function () {
  'use strict';
  const $ = s => document.querySelector(s), RU = window.__RU__;
  if (!RU || !$('#ruApp')) return;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const todayBJ = () => window.__RU_TODAY || new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
  const lsGet = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (_) { return d; } };
  const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} };
  const f0 = x => x == null || isNaN(x) ? '—' : Math.round(x).toLocaleString('en-US'), p1 = x => x == null || isNaN(x) ? '—' : (x >= 0 ? '+' : '') + x.toFixed(1) + '%';
  let S = { d: RU.d.slice(), o: RU.o.slice(), h: RU.h.slice(), l: RU.l.slice(), c: RU.c.slice(), r: RU.r.slice(), m: (RU.m || []).slice() }, WX = { rs: null, v: null, at: null, busy: false }, VIEW = lsGet('fut-view', 'meal');
  const OPT = { eq: lsGet('ru-eq', 500000), risk: lsGet('ru-risk', RUP.RISK), margin: lsGet('ru-margin', RUP.MARGIN), pos: lsGet('ru-pos', null), stopY: lsGet('ru-stopY', null), man: lsGet('ru-man', { st: '', note: '', qg: '', bg: '', stk: '', demand: false, d: '' }) };
  /* 接上 data/ru_live.json（Actions 追加的最新真实日线 {d,o,h,l,c}）：按快照最后一天的 调整价/真实价 比例换算 */
  function mergeLive(j) {
    if (!j || !j.d || !j.d.length) return; const n = S.d.length, f = S.c[n - 1] / S.r[n - 1];
    for (let i = 0; i < j.d.length; i++) { if (j.d[i] <= S.d[S.d.length - 1]) continue; S.d.push(j.d[i]); S.o.push(j.o[i] * f); S.h.push(j.h[i] * f); S.l.push(j.l[i] * f); S.c.push(j.c[i] * f); S.r.push(j.c[i]); S.m.push(j.m && j.m[i] ? String(j.m[i]).replace(/^RU/, '') : S.m[S.m.length - 1]); }
  }
  async function loadLive() { try { const r = await fetch('data/ru_live.json?_=' + Date.now(), { cache: 'no-store' }); if (r.ok) mergeLive(await r.json()); } catch (_) {} }
  /* ---- 天气（浏览器直连 Open-Meteo，免密钥；每6小时缓存一次） ---- */
  async function jget(u) { const r = await fetch(u); if (!r.ok) throw new Error(r.status); return r.json(); }
  async function loadWx(force) {
    const today = todayBJ(); if (window.__RU_WX_MOCK) { WX.rs = window.__RU_WX_MOCK; WX.v = ruWxVerdict(WX.rs); WX.at = Date.now(); return; }
    const c = lsGet('ru-wx', null); if (!force && c && c.today === today && Date.now() - c.at < 6 * 3600e3) { WX.rs = c.rs; WX.v = ruWxVerdict(c.rs); WX.at = c.at; return; }
    WX.busy = true; paint();
    const y0 = +today.slice(0, 4), years = [y0 - 5, y0 - 4, y0 - 3, y0 - 2, y0 - 1];
    const rs = await Promise.all(RUREG.map(async g => {
      try {
        const tz = encodeURIComponent(g.tz), base = 'latitude=' + g.lat + '&longitude=' + g.lon + '&timezone=' + tz;
        const [fc, hs] = await Promise.all([
          jget('https://api.open-meteo.com/v1/forecast?' + base + '&daily=precipitation_sum,temperature_2m_max&past_days=35&forecast_days=7'),
          jget('https://archive-api.open-meteo.com/v1/archive?' + base + '&start_date=' + years[0] + '-01-01&end_date=' + years[4] + '-12-31&daily=precipitation_sum,temperature_2m_max')]);
        const r = ruRegionWx({ d: fc.daily.time, p: fc.daily.precipitation_sum, tx: fc.daily.temperature_2m_max }, { d: hs.daily.time, p: hs.daily.precipitation_sum, tx: hs.daily.temperature_2m_max }, today, years);
        return Object.assign({ k: g.k, n: g.n, core: g.core }, r);
      } catch (e) { return { k: g.k, n: g.n, core: g.core, err: String(e && e.message || e) }; }
    }));
    WX.busy = false; WX.rs = rs; WX.v = ruWxVerdict(rs); WX.at = Date.now(); if (rs.some(r => !r.err)) lsSet('ru-wx', { today, at: WX.at, rs });
  }
  /* ---- 渲染 ---- */
  const chip = (ok, t) => '<span class="sc ' + (ok == null ? '' : ok ? 'ok' : 'no') + '">' + (ok == null ? '' : ok ? '✓ ' : '✗ ') + esc(t) + '</span>';
  function planNow() { return ruPlan(S, todayBJ(), WX.v, OPT.pos && OPT.pos.px ? OPT.pos : null, Object.assign({}, OPT.man, { stopY: OPT.stopY })); }
  function wxHtml() {
    if (WX.busy) return '<p class="dim">正在取天气…</p>';
    if (!WX.rs) return '<p class="dim">还没取天气。</p>';
    const v = WX.v, tone = v.level === 'block' ? 'bad' : v.level === 'warn' ? 'warn' : v.level === 'ok' ? 'good' : '';
    let h = '<div class="ruwx ' + tone + '"><b>' + esc(v.text) + '</b></div><table class="rutb"><thead><tr><th>产区</th><th>近30天降水</th><th>近7天最高温</th><th>未来7天降水预报</th><th>判断</th></tr></thead><tbody>';
    WX.rs.forEach(r => { h += r.err ? '<tr><td>' + esc(r.n) + '</td><td colspan="4" class="dim">没取到（' + esc(r.err) + '）</td></tr>' : '<tr class="' + (r.sev >= 2 ? 'bad' : r.sev ? 'warn' : '') + '"><td>' + esc(r.n) + (r.core ? ' <small class="dim">核心</small>' : '') + '</td><td>' + f0(r.p30) + ' mm' + (r.n30 != null ? '<br><small class="dim">近5年同期均值 ' + f0(r.n30) + '（' + (r.ratio * 100).toFixed(0) + '%）</small>' : '') + '</td><td>' + (r.t7 == null ? '—' : r.t7.toFixed(1) + '℃') + (r.tn != null ? '<br><small class="dim">常年 ' + r.tn.toFixed(1) + '℃</small>' : '') + '</td><td>' + f0(r.f7) + ' mm</td><td>' + esc(r.msg) + '</td></tr>'; });
    return h + '</tbody></table><p class="dim ruft">数据：Open-Meteo（再分析+预报模型，不是气象站实测）。判定：近30天降水不到同期均值的 25%（且少30mm以上）=严重偏旱，不到50%=偏旱；超过300%（且多100mm以上）=严重偏涝，超过200%=偏涝；近7天最高温比常年高3.5℃以上=高温。泰国南部或云南严重异常，或各区「注意」累计≥3，就暂缓做空。<b>这些阈值是按你的文字设的，没有历史天气回测。</b>更新于 ' + (WX.at ? new Date(WX.at + 8 * 3600e3).toISOString().slice(5, 16).replace('T', ' ') : '—') + ' <button class="lnk" data-ru="wxre">重新取</button></p>';
  }
  function ruHtml() {
    const P = planNow(), eqLots = P.order && P.real ? ruSize(OPT.eq, P.order.lim, OPT.risk, OPT.margin) : null, H = ruHistory(S), ST = ruStats(H);
    const tone = { go: 'short', exit: 'short', holdwx: 'short', hold: 'wait', blocked: 'wait', wait: 'wait', pre: 'wait', sleep: 'wait', stale: 'wait' }[P.st] || 'wait';
    let h = '<div class="rusg ' + (P.st === 'go' || P.st === 'exit' ? 'go' : '') + '"><div class="cl">橡胶 RU · 3月季节性做空 · 价格截至 ' + esc(P.last) + (P.real ? ' · 收盘 ' + f0(P.real) : '') + '</div><div class="hd ' + tone + '">' + esc(P.head) + '</div><div class="sb">' + esc(P.sub) + '</div><div class="scs">'
      + chip(P.inMar ? true : null, P.inMar ? '3月窗口' : '不在3月窗口') + (P.inMar || P.pre ? chip(P.reb, '收盘≥MA5（反弹）' + (P.ma ? ' ' + f0(P.ma) : '')) : '') + (WX.v ? chip(WX.v.level === 'unknown' ? null : WX.v.level !== 'block', '天气' + ({ ok: '正常', warn: '轻度异常', block: '异常', unknown: '未知' })[WX.v.level]) : '') + chip(null, '止损 ' + RUP.STOP + '% · 月底平仓 · 不设止盈') + '</div></div>';
    if (P.order) {
      h += '<h3>建议价格</h3><table class="rutb"><tbody><tr><td><b>做哪个合约</b></td><td class="n"><b>' + esc(P.dom || '当前主力') + '</b>（当前主力；3月下旬主力常从 ' + esc(P.mar05) + ' 换到 ' + esc(P.mar09) + '，见下面「换合约」）</td></tr><tr><td>最近收盘（真实主连）</td><td class="n">' + f0(P.real) + '</td></tr><tr><td><b>明日挂限价卖出（空）</b></td><td class="n"><b>≥ ' + f0(P.order.lim) + '</b>（收盘价反弹 ' + RUP.LIM + '%；当日有效，没成交作废，不追）</td></tr><tr><td>止损价（' + RUP.STOP + '%）</td><td class="n">' + f0(P.order.stop) + '</td></tr><tr><td>离场</td><td class="n">' + esc(P.exitD) + ' 收盘（3月最后一个交易日）</td></tr><tr><td>参考目标（历史3月平均跌 ' + RUP.AVG_DROP + '%）</td><td class="n">' + f0(P.order.ref) + '（仅参考，不设止盈：回测里加止盈更差）</td></tr></tbody></table>';
      h += '<h3>建议手数（轻仓、分批）</h3><div class="ruin"><label>账户权益(元)<input id="ruEq" inputmode="numeric" value="' + OPT.eq + '"></label><label>单笔最多亏(权益%)<input id="ruRisk" inputmode="decimal" value="' + OPT.risk + '"></label><label>保证金率(%)<input id="ruMg" inputmode="decimal" value="' + OPT.margin + '"></label></div>'
        + '<p>' + (eqLots.lots >= 1 ? '总共 <b>' + eqLots.lots + ' 手</b>（按止损亏 ' + f0(eqLots.loss) + ' 元≈权益 ' + (eqLots.loss / OPT.eq * 100).toFixed(1) + '%；占用保证金约 ' + f0(eqLots.margin) + ' 元）。' + (eqLots.lots >= 2 ? '建议分两批：首批 ' + Math.ceil(eqLots.lots / 2) + ' 手，下一个仍站上MA5的反弹日再挂 ' + Math.floor(eqLots.lots / 2) + ' 手（分批是你文字里的建议，没有单独回测）。' : '') : '按这个风险预算开不了1手（1手止损约亏 ' + f0(eqLots.perLot) + ' 元）。') + '</p>';
    }
    h += '<h3>天气（做空筛选）</h3>' + wxHtml();
    h += '<h3>手动录入：开割进度与需求（暂时没有自动数据）</h3>' + manHtml(P);
    h += '<h3>我的橡胶空单</h3>' + posHtml(P);
    h += '<h3>提醒</h3>' + remindHtml(P);
    h += '<h3>历史：每年3月按这条规则</h3>' + histHtml(H, ST);
    h += '<details class="ruabout"><summary>规则依据与局限</summary>' + aboutHtml() + '</details>';
    return h;
  }
  function manHtml(P) {
    const m = OPT.man, age = m.d ? Math.round((new Date(todayBJ() + 'T00:00:00Z') - new Date(m.d + 'T00:00:00Z')) / 864e5) : null, old = (P.inMar || P.pre) && (age == null || age > 14);
    const sel = [['', '没录入'], ['stop', '还在停割'], ['trial', '部分产区试割'], ['ok', '正常开割'], ['delay', '延迟开割（干旱/洪涝）']].map(x => '<option value="' + x[0] + '"' + (m.st === x[0] ? ' selected' : '') + '>' + x[1] + '</option>').join('');
    return (old ? '<div class="ruwx warn"><b>' + (age == null ? '还没录入过' : '已 ' + age + ' 天没更新') + '：</b>3月里请每周看一次泰国/越南/云南的开割进度和轮胎开工率，录在这里（来源：隆众、卓创、云南/海南农垦消息、泰国橡胶局）。</div>' : '')
      + '<div class="ruin"><label>开割进度<select id="ruMs">' + sel + '</select></label><label>备注（哪个产区、什么情况）<input id="ruMn" value="' + esc(m.note) + '"></label></div>'
      + '<div class="ruin"><label>全钢胎开工率(%)<input id="ruMq" inputmode="decimal" value="' + esc(m.qg) + '"></label><label>半钢胎开工率(%)<input id="ruMb" inputmode="decimal" value="' + esc(m.bg) + '"></label><label>社会库存(万吨)<input id="ruMk" inputmode="decimal" value="' + esc(m.stk) + '"></label></div>'
      + '<label class="ruck"><input type="checkbox" id="ruMd"' + (m.demand ? ' checked' : '') + '> 需求超预期强劲回升（你判断开工率明显高于预期）→ 暂缓做空；持仓则考虑离场</label>'
      + '<p class="dim">录入日期：' + esc(m.d || '—') + '。只记在这台设备上。选「延迟开割」或勾「需求超预期走强」，和天气严重异常一样会拦住新的做空、并提示持仓离场；开工率和库存数字只做记录，系统不拿它们算信号（没有历史数据可回测）。</p>';
  }
  function posHtml(P) {
    const pos = OPT.pos;
    if (pos && pos.px) return (P.roll ? '<div class="ruwx warn"><b>主力已换到 ' + esc(P.dom) + '，你的单子在 ' + esc(pos.contract) + '</b>：不用换，拿到月底平仓就行；下面的浮盈、止损线按主连价格估算，和你的合约有价差，实际以你软件里的 ' + esc(pos.contract) + ' 价格为准。</div>' : '') + '<p>空 ' + esc(pos.contract || '') + ' ' + esc(pos.lots || '') + ' 手 @ ' + f0(pos.px) + '（' + esc(pos.d || '') + '）' + (P.pos ? '：浮盈 <b class="' + (P.pos.r >= 0 ? 'bear' : 'bull') + '">' + p1(P.pos.r) + '</b>，止损价 ' + f0(P.pos.stop) + '（距现价 ' + (P.pos.stopGap == null ? '—' : P.pos.stopGap.toFixed(1) + '%') + '），到 ' + esc(P.exitD) + ' 收盘平仓' : '') + ' <button class="lnk" data-ru="close">已平仓，清除</button> <button class="lnk" data-ru="stopped">止损平仓（今年不再开）</button></p>';
    return '<div class="ruin"><label>开仓日<input id="ruPd" placeholder="YYYY-MM-DD"></label><label>成交价<input id="ruPp" inputmode="decimal"></label><label>手数<input id="ruPl" inputmode="numeric"></label><label>合约<input id="ruPc" placeholder="' + esc(P.dom || 'RU2705') + '"></label><button class="tb" data-ru="open" style="border:1px solid var(--line)">记一笔空单</button></div><p class="dim">只记在这台设备上，用来算浮盈、止损线和离场提醒。</p>';
  }
  function remindHtml(P) {
    const y = +todayBJ().slice(0, 4), yy = P.nextWin ? +P.nextWin.slice(0, 4) : y, L = [['02-10', '准备期开始：开始看天气和价格'], ['03-01', '窗口开始：每个收盘后看一次；收盘站上MA5且天气正常 → 次日挂限价空'], ['(每周)', '3月里每周录一次开割进度和轮胎开工率（上面手动录入）'], ['(每天)', '持仓时：止损价（+' + RUP.STOP + '%）、天气转异常、开割延迟、需求走强 → 考虑离场'], [ruLastWeekdayOfMarch(yy).slice(5), '3月最后一个交易日：收盘前平仓']];
    let h = '<ul class="rurm">' + L.map(x => '<li><b>' + esc(x[0]) + '</b> ' + esc(x[1]) + '</li>').join('') + '</ul>';
    const alert = P.st === 'go' || P.st === 'exit' || P.st === 'holdwx' || P.st === 'blocked';
    h += '<p class="' + (alert ? 'ruhot' : 'dim') + '">' + (alert ? '👉 今天要处理：' + esc(P.head) : '今天没有要处理的事。') + '</p><p class="dim">手机推送提醒（窗口开始、出信号、止损/离场、天气异常）随整包上线时接入现有的推送。</p>';
    return h;
  }
  function histHtml(H, ST) {
    if (!H.length) return '<p class="dim">没有历史数据。</p>';
    let h = (ST ? '<p>' + ST.years + ' 个3月里 ' + ST.n + ' 年出信号成交：平均 <b>' + p1(ST.mean) + '</b>，胜率 ' + ST.win.toFixed(0) + '%，最好 ' + p1(ST.best) + '，最差 ' + p1(ST.worst) + '（t=' + ST.t.toFixed(1) + '）。<span class="dim">按12个月一起做多重检验校正后仍不算显著（p≈0.1），主要靠基本面逻辑支撑；一年只有一笔，样本很小。</span></p>' : '')
      + '<table class="rutb"><thead><tr><th>年</th><th>信号日</th><th>成交日</th><th>离场</th><th>结果</th></tr></thead><tbody>';
    H.slice().reverse().forEach(x => { h += x.trade ? '<tr><td>' + x.y + '</td><td>' + esc(x.sig.slice(5)) + '</td><td>' + esc(x.entD.slice(5)) + '</td><td>' + esc(x.exitD.slice(5)) + ' ' + esc(x.why) + '</td><td class="n ' + (x.ret >= 0 ? 'bear' : 'bull') + '">' + p1(x.ret * 100) + '</td></tr>' : '<tr><td>' + x.y + '</td><td colspan="4" class="dim">没出信号/没成交</td></tr>'; });
    return h + '</tbody></table>';
  }
  function aboutHtml() {
    return '<p><b>逻辑</b>：天然橡胶11月到次年2-3月停割，3月中下旬起泰国北部、越南先试割，4月规模开割。3月是「停割利多出尽 + 开割供应增量预期」的兑现窗口，交易的是开割预期，不是开割现实。</p><p><b>回测</b>：2013–2026 年3月做空，平均约 +5.7%/年，14年里11年赚（79%）；前半段（2013-19）+5.6%、后半段（2020-26）+5.8%，20号胶同向（2020–26 年3月7年6年跌）。3月是12个月里最强的，但多重检验后仍不显著。</p><p><b>入场</b>：不追空。3月内收盘站上5日均线（反弹）才出信号，次日限价卖出≥收盘价+0.3%。三种「逢反弹」写法（站上MA5/MA10、距低点反弹1.5%、贴近前10日高点）回测平均都在 +4.1%~+5.7%，差别在噪声内，按你的文字取最简单的MA5。</p><p><b>离场</b>：5%止损（盘中最高价触及）；3月最后一个交易日收盘平仓。止盈6%/8%回测更差（砍掉大跌里的盈利），所以不设止盈；「参考目标」只是历史平均跌幅。</p><p><b>天气</b>：你的文字里「主产区天气正常」是做空前提。这里用降水异常和高温做判定，没有历史天气数据，所以<b>没回测过这个过滤</b>，只作为风险开关。</p><p><b>没有做的</b>：开割进度、轮胎开工率、库存、青岛保税区库存没有自动数据（库存接口取数失败），暂时是手动录入，只有「延迟开割」「需求超预期走强」两个开关会影响信号；多NR空RU套利（没有价差回测）。</p><p><b>换合约</b>：回测用的是主力连续价格，3月一般是 5 月合约（RU05），3月下旬（约19~30日）主力常换到 9 月合约。已经持有的单子不用换：拿着原合约到月底平仓（它仍有足够成交量）。想换也行：同一天先平旧合约、再空新主力合约，回测的连续价格就是这么算的，实际多付两次手续费和滑点。新开仓一律做当时的主力合约。止损后当月不再重新开仓（回测里每年只做一次，止损后再开没有验证）。</p><p><b>限制</b>：每年最多一笔；单品种一个月的结果不能当系统策略，仓位要小。</p>';
  }
  function overviewHtml() {
    let meal = '<div class="ov-c" data-v="meal"><h4>豆粕 M</h4><p class="dim">没取到</p></div>';
    try {
      const s = window.__cockpit && window.__cockpit.planSnap && window.__cockpit.planSnap();
      if (s) { const t = s.pos ? (s.pos.side > 0 ? '持有多单' : '持有空单') + (s.mg ? ' · ' + s.mg.action : '') : s.side > 0 ? '做多入场信号' : s.side < 0 ? '做空入场信号' : '空仓 · 无信号'; meal = '<div class="ov-c" data-v="meal"><h4>豆粕 M · 全年规则</h4><div class="hd">' + esc(t) + '</div><p class="dim">收盘 ' + f0(s.px) + '　点此进入豆粕页</p></div>'; }
    } catch (_) {}
    const P = planNow(), ru = '<div class="ov-c" data-v="ru"><h4>橡胶 RU · 仅3月做空</h4><div class="hd">' + esc(P.head) + '</div><p class="dim">' + esc(P.sub) + '　点此进入橡胶页</p></div>';
    return '<div class="ovg">' + meal + ru + '</div><p class="dim ovn">组合思路：每个品种只在自己有逻辑的窗口里做，互不重叠，分散风险。目前接入：豆粕（全年）、橡胶（3月）。新品种要先有因果逻辑，再回测，再接入。</p>';
  }
  function paint() {
    const app = $('#ruApp'); if (!app) return;
    try { const ae = document.activeElement; if (ae && app.contains(ae) && ae.blur) ae.blur(); } catch (_) {}   // 先让输入框失焦（触发它的 change），再重画，避免重画过程中 blur 嵌套
    document.body.classList.toggle('v-ru', VIEW === 'ru'); document.body.classList.toggle('v-all', VIEW === 'all');
    document.querySelectorAll('#vSeg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.v === VIEW)));
    if (VIEW === 'meal') { app.innerHTML = ''; return; }
    app.innerHTML = '<div class="ruin2">' + (VIEW === 'all' ? overviewHtml() : ruHtml()) + '</div>';
  }
  function setView(v) { VIEW = v; lsSet('fut-view', v); if (v !== 'meal' && !WX.rs && !WX.busy) loadWx().then(paint); paint(); try { window.scrollTo(0, 0); } catch (_) {} if (v === 'meal') { try { window.dispatchEvent(new Event('resize')); } catch (_) {} } }
  document.addEventListener('click', e => {
    const b = e.target.closest('#vSeg button'); if (b) return setView(b.dataset.v);
    const oc = e.target.closest('.ov-c'); if (oc) return setView(oc.dataset.v);
    const t = e.target.closest('[data-ru]'); if (!t) return; const a = t.dataset.ru;
    if (a === 'wxre') { WX.rs = null; loadWx(true).then(paint); paint(); }
    if (a === 'stopped') { OPT.stopY = +todayBJ().slice(0, 4); lsSet('ru-stopY', OPT.stopY); OPT.pos = null; lsSet('ru-pos', null); paint(); }
    if (a === 'close') { OPT.pos = null; lsSet('ru-pos', null); paint(); }
    if (a === 'open') { const d = ($('#ruPd').value || todayBJ()).trim(), px = +$('#ruPp').value, lots = +$('#ruPl').value; if (!(px > 0)) return; const pc = ($('#ruPc').value || '').trim().toUpperCase() || (planNow().dom || ''); OPT.pos = { d, px, lots: lots > 0 ? lots : null, contract: pc }; lsSet('ru-pos', OPT.pos); paint(); }
  });
  document.addEventListener('change', e => {
    const id = e.target && e.target.id;
    if (id === 'ruMs' || id === 'ruMn' || id === 'ruMq' || id === 'ruMb' || id === 'ruMk' || id === 'ruMd') {
      const g = k => { const x = $('#' + k); return x ? (x.type === 'checkbox' ? x.checked : x.value.trim()) : ''; };
      OPT.man = { st: g('ruMs'), note: g('ruMn').slice(0, 80), qg: g('ruMq'), bg: g('ruMb'), stk: g('ruMk'), demand: !!g('ruMd'), d: todayBJ() }; lsSet('ru-man', OPT.man); return paint();
    }
    const m = { ruEq: ['eq', 'ru-eq'], ruRisk: ['risk', 'ru-risk'], ruMg: ['margin', 'ru-margin'] }[e.target && e.target.id]; if (!m) return;
    const v = +e.target.value; if (!(v > 0)) return; OPT[m[0]] = v; lsSet(m[1], v); paint();
  });
  window.__ru = { plan: planNow, paint, setView, loadWx, S: () => S, view: () => VIEW, history: () => ruHistory(S), size: ruSize };
  loadLive().then(() => { paint(); if (VIEW !== 'meal') loadWx().then(paint); });
  paint();
})();
