/* 橡胶(RU) 3月季节性做空 —— 期货组合页的第二个品种（v102.0）
 * 规则来自 Ted 给的基本面文字 + 回测：只在3月做、只做空；收盘站上MA5（反弹）才挂单（不追空）；
 * 次日限价卖出 ≥ 收盘价+0.3%；5%止损；3月最后一个交易日收盘平仓；不设止盈（回测里止盈更差）；
 * 天气筛选（泰国南部/东北、越南东南、云南、海南，Open-Meteo）：严重异常不做空。天气条件没有历史回测，只作为 Ted 要求的过滤。
 * 纯函数放在 RU_BEGIN..RU_END 之间，tests/test_rubber.js 按标记抽出来测。 */
/* RU_BEGIN */
const RUP = { STOP: 5, LIM: 0.3, MA: 5, COST: 3e-4, TON: 10, TICK: 5, MON: 3, PRE_FROM: '02-10', AVG_DROP: 5.8, RISK: 2, MARGIN: 12, USE_CAP: 30 };
const RUREG = [   // 3月只盯"开割预期"能否兑现：第一优先级=泰国北部/东北部、越南东南部（kind:open，干旱高温=开割推迟）；第二优先级=印尼南部巨港（kind:wet，降雨偏多=割胶受阻）。西双版纳(4月才割胶)、泰国南部(割胶尾声)、海南 不看
  { k: 'thn', n: '泰国北部（清莱）', lat: 19.9, lon: 99.83, tz: 'Asia/Bangkok', core: true, kind: 'open', pri: 1 },
  { k: 'the', n: '泰国东北（廊开/乌隆）', lat: 17.4, lon: 102.8, tz: 'Asia/Bangkok', core: true, kind: 'open', pri: 1 },
  { k: 'vn', n: '越南东南（平福/西宁）', lat: 11.75, lon: 106.9, tz: 'Asia/Ho_Chi_Minh', core: true, kind: 'open', pri: 1 },
  { k: 'id', n: '印尼南部（巨港）', lat: -2.99, lon: 104.76, tz: 'Asia/Jakarta', core: false, kind: 'wet', pri: 2 }
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
function ruRegionWx(fc, hist, today, years, kind) {
  const d0 = ruAddDays(today, -29), past = [], fut = [];
  for (let i = 0; i < fc.d.length; i++) { if (fc.d[i] <= today) { if (fc.d[i] >= d0) past.push(i); } else if (fc.d[i] <= ruAddDays(today, 7)) fut.push(i); }
  const num = v => (v == null || isNaN(v) ? 0 : +v), p30 = past.reduce((a, i) => a + num(fc.p[i]), 0), p7 = past.slice(-7).reduce((a, i) => a + num(fc.p[i]), 0);
  const tx7 = past.slice(-7).map(i => fc.tx[i]).filter(v => v != null), t7 = tx7.length ? tx7.reduce((a, b) => a + b, 0) / tx7.length : null, f7 = fut.reduce((a, i) => a + num(fc.p[i]), 0);
  const norms = [], tnorm = []; const y0 = +today.slice(0, 4);
  (years || []).forEach(yy => { const sh = yy - y0, a = ruAddDays(today, 0).replace(/^\d{4}/, String(yy)), s = ruAddDays(a, -29); let sum = 0, cnt = 0, ts = [], tc = 0; for (let i = 0; i < hist.d.length; i++) { const d = hist.d[i]; if (d >= s && d <= a) { sum += num(hist.p[i]); cnt++; if (d >= ruAddDays(a, -6) && hist.tx[i] != null) ts.push(hist.tx[i]); } } if (cnt >= 25) norms.push(sum); if (ts.length >= 5) tnorm.push(ts.reduce((x, y) => x + y, 0) / ts.length); });
  const n30 = norms.length ? norms.reduce((a, b) => a + b, 0) / norms.length : null, tn = tnorm.length ? tnorm.reduce((a, b) => a + b, 0) / tnorm.length : null;
  let sev = 0; const msgs = [], wet = kind === 'wet', hotA = t7 != null && tn != null ? t7 - tn : null;
  /* 你的阈值（只作提示，不单独拦单）：连续一周无有效降雨(7天累计<5mm)且最高温均值≥33℃ → 开割推迟预警。
   * 说明：泰国东北3月平均最高温本来就常在33℃以上，这条绝对阈值几乎每年3月都会触发，所以拦单只看「相对近5年同期」的异常。 */
  const ur = !wet && p7 < 5 && t7 != null && t7 >= 33;
  if (n30 != null && n30 >= 20) {
    const ratio = p30 / n30, diff = p30 - n30;
    if (!wet && ratio < 0.25 && diff <= -30) { sev = Math.max(sev, 2); msgs.push('严重偏旱'); } else if (!wet && ratio < 0.5 && diff <= -30) { sev = Math.max(sev, 1); msgs.push('偏旱'); }
    else if (ratio > 3 && diff >= 100) { sev = Math.max(sev, 2); msgs.push(wet ? '降雨严重偏多' : '严重偏涝'); } else if (ratio > 2 && diff >= 60) { sev = Math.max(sev, 1); msgs.push(wet ? '降雨偏多' : '偏涝'); }
  }
  if (!wet && hotA != null && hotA >= 3.5) { sev = Math.max(sev, 1); msgs.push('高温'); }
  if (!wet && hotA != null && hotA >= 2 && msgs.some(m => /偏旱/.test(m))) { sev = Math.max(sev, 2); if (!msgs.includes('高温')) msgs.push('高温'); }   // 干旱+明显偏热 = 试割不畅，升一级
  return { p30, p7, f7, n30, ratio: n30 ? p30 / n30 : null, t7, tn, sev, ur, msg: msgs.join('、') || (wet ? '降雨正常/偏少（对空头无影响）' : '正常') };
}
/* 汇总：核心产区（泰国北部/东北、越南东南）严重异常，或各区「注意」累计≥3 → 暂缓做空；有注意 → 提示；取不到 → 不拦 */
function ruWxVerdict(rs) {
  const ok = rs.filter(r => r && !r.err);
  if (!ok.length) return { level: 'unknown', text: '天气数据没取到：不用天气过滤' };
  const blk = ok.filter(r => r.core && r.sev >= 2), sum = ok.reduce((a, r) => a + r.sev, 0), warn = ok.filter(r => r.sev >= 1);
  if (blk.length || sum >= 3) return { level: 'block', text: '主产区天气异常：' + (blk.length ? blk.map(r => r.n + ' ' + r.msg).join('、') : warn.map(r => r.n + ' ' + r.msg).join('、')) + '，暂缓做空' };
  if (warn.length) return { level: 'warn', text: '有产区轻度异常：' + warn.map(r => r.n + ' ' + r.msg).join('、') + '（不拦，留意）' };
  return { level: 'ok', text: '主产区天气正常' };
}
/* 需求意外爆发（防3月下旬空头被逼仓）：必须同时满足 ①统计周在当年3月15日之后 ②全钢胎产能利用率≥75% 且较上周上升 ③同比≥+8个点。全部自动，不再手动勾选 */
const RUSURGE = { FROM: '03-15', LEVEL: 75, YOY: 8 };
function ruDemandSurge(ind, today) {
  const ls = (ind && ind.qg) || [], ys = (ind && ind.qgY) || [], y = String(today).slice(0, 4), n = ls.length, o = { on: false, text: '', conds: [] };
  if (!n) { o.text = '全钢胎产能利用率暂无数据'; return o; }
  const last = ls[n - 1], prev = n > 1 ? ls[n - 2] : null, yy = ys.find(p => p.d === last.d);
  const c1 = last.d.slice(0, 4) === y && last.d.slice(5) >= RUSURGE.FROM && last.d.slice(5) <= '03-31', c2 = last.v >= RUSURGE.LEVEL && !!prev && last.v > prev.v, c3 = !!yy && yy.v >= RUSURGE.YOY;
  o.conds = [c1, c2, c3]; o.on = c1 && c2 && c3; o.last = last; o.yoy = yy ? yy.v : null;
  o.text = o.on ? '需求意外爆发：全钢胎产能利用率 ' + last.v + '%（周期止 ' + last.d + '，较上周升、同比 +' + yy.v + ' 点），防空头被逼仓' : '未触发（全钢胎 ' + last.v + '%，同比 ' + (yy ? (yy.v >= 0 ? '+' : '') + yy.v + '点' : '—') + '；需3/15后、≥' + RUSURGE.LEVEL + '%且周升、同比≥+' + RUSURGE.YOY + '点）';
  return o;
}
/* 当前该做什么。S 序列（含 r 真实收盘），today 北京日期，wx 天气结论，pos 记录的空单 {d,px,lots}|null */
function ruPlan(S, today, wx, pos, man) {
  const n = S.d.length, L = S.d[n - 1], y = +today.slice(0, 4), mmdd = today.slice(5), real = S.r[n - 1] != null ? S.r[n - 1] : null, scale = real ? S.c[n - 1] / real : null;
  const inMar = +today.slice(5, 7) === RUP.MON, pre = mmdd >= RUP.PRE_FROM && mmdd < '03-01', yE = ruLastWeekdayOfMarch(y);
  const dom = S.m && S.m[n - 1] ? 'RU' + S.m[n - 1] : null, yy = String(y).slice(2), bad = [];
  if (wx && wx.level === 'block') bad.push(wx.text);
  if (man && man.surge && man.surge.on) bad.push(man.surge.text);
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
/* ---- 基本面指标（库存/产能利用率/产量/进口/青岛）：全部由 Actions 自动抓取隆众周报/月报 → data/ru_ind_auto.json，页面只读，不能录入 ----
 * 每项一个时间序列 [{d,v,(m)}]，d=统计日(周数据)或发布日(月数据，m=统计月份)。
 * m：对价格的含义，+1=偏多、−1=偏空、0=不明显（和豆粕趋势墙同一约定：库存上升对价格偏空）。阈值是常识性的提示线，没有历史回测，不单独拦单。
 * mode：pct=较上期变化%；chg=序列本身就是「较上周变化(百分点)」(青岛出入库率正文只给变化，不给水平)，另算4周累计；
 *       lvl=看同比字段 y（产量/进口：累计同比%；轮胎产能利用率：同比百分点，dmode:'pt' 表示较上期也按百分点算） */
const RUIND = [
  { k: 'prod', n: '全球产量', u: '万吨', g: '供给', mode: 'lvl', y: 'prodY', yu: '%', thr: 2, sign: -1, freq: 'm', src: '隆众：[产量]全球天然橡胶产量月数据统计（ANRPC预测，同比=累计同比）' },
  { k: 'imp', n: '进口量', u: '万吨', g: '供给', mode: 'lvl', y: 'impY', yu: '%', thr: 5, sign: -1, freq: 'm', src: '隆众：[进出口]中国天然橡胶进口量月数据统计（海关终值，预估值已剔除；同比=累计同比）' },
  { k: 'stk', n: '社会总库存', u: '万吨', g: '库存', mode: 'pct', thr: 1, sign: -1, freq: 'w', src: '隆众：中国天然橡胶社会库存周数据分析' },
  { k: 'dark', n: '深色胶库存', u: '万吨', g: '库存', mode: 'pct', thr: 1, sign: -1, freq: 'w', src: '同上（深色胶=轮胎用）；深色+浅色=社会总库存' },
  { k: 'light', n: '浅色胶库存', u: '万吨', g: '库存', mode: 'pct', thr: 1, sign: -1, freq: 'w', src: '同上；正文缺失时由 总库存−深色胶 算出' },
  { k: 'qd', n: '青岛库存', u: '万吨', g: '青岛', mode: 'pct', thr: 1, sign: -1, freq: 'w', src: '隆众：青岛地区天然橡胶样本库存和出入库率周数据（保税+一般贸易合计）' },
  { k: 'qin', n: '青岛入库率变化', u: '点', g: '青岛', mode: 'chg', thr: 2, sign: -1, freq: 'w', src: '同上（一般贸易仓库入库率，较上周变化的百分点）' },
  { k: 'qout', n: '青岛出库率变化', u: '点', g: '青岛', mode: 'chg', thr: 2, sign: 1, freq: 'w', src: '同上（一般贸易仓库出库率，较上周变化的百分点）' },
  { k: 'qg', n: '全钢胎产能利用率', u: '%', g: '需求', mode: 'lvl', y: 'qgY', yu: '点', dmode: 'pt', thr: 3, sign: 1, freq: 'w', src: '隆众：中国轮胎产能利用率周数据统计（样本企业；多空看同比，国庆/春节停工会让环比失真）' },
  { k: 'bg', n: '半钢胎产能利用率', u: '%', g: '需求', mode: 'lvl', y: 'bgY', yu: '点', dmode: 'pt', thr: 3, sign: 1, freq: 'w', src: '同上' }
];
const RUIND_STALE = { w: 10, m: 45 };
function ruDaysBetween(a, b) { return Math.round((new Date(b + 'T00:00:00Z') - new Date(a + 'T00:00:00Z')) / 864e5); }
/* 一项指标的趋势：最新值、较上期、同比、含义、多久没更新 */
function ruIndTrend(df, ind, today) {
  const ls = (ind && ind[df.k]) || [], n = ls.length; if (!n) return { n: 0, def: df, m: 0 };
  const last = ls[n - 1], prev = n > 1 ? ls[n - 2] : null, ys = df.y && ind[df.y] && ind[df.y].length ? ind[df.y] : null, yy = ys ? (ys.find(p => p.d === last.d) || ys[ys.length - 1]) : null;
  let delta = null, m = 0, d4 = null;
  if (df.mode === 'chg') { delta = last.v; if (n >= 4) d4 = ls.slice(-4).reduce((a, p) => a + p.v, 0); m = Math.abs(delta) >= df.thr ? (delta > 0 ? df.sign : -df.sign) : 0; }
  else if (df.mode === 'lvl') { if (yy) m = Math.abs(yy.v) >= df.thr ? (yy.v > 0 ? df.sign : -df.sign) : 0; if (prev) delta = df.dmode === 'pt' ? last.v - prev.v : (last.v / prev.v - 1) * 100; }
  else if (prev) { delta = (last.v / prev.v - 1) * 100; m = Math.abs(delta) >= df.thr ? (delta > 0 ? df.sign : -df.sign) : 0; }
  const age = today ? ruDaysBetween(last.d, today) : 0;
  return { n, def: df, last, prev, delta, d4, yy, m, age, stale: age > RUIND_STALE[df.freq], pts: ls.slice(-24) };
}
/* 综合：偏空/偏多/中性/数据不足 + 提示 */
function ruIndSummary(ind, today) {
  const T = RUIND.map(d => ruIndTrend(d, ind, today)), E = T.filter(t => t.n > 0), bear = E.filter(t => t.m < 0).length, bull = E.filter(t => t.m > 0).length, by = {}; T.forEach(t => { by[t.def.k] = t; });
  const dir = E.length < 3 ? 'na' : bear - bull >= 2 ? '偏空' : bull - bear >= 2 ? '偏多' : '中性', warns = [], goods = [];
  const dk = by.dark; if (dk && dk.delta != null && dk.delta <= -3) warns.push('深色胶库存较上期降 ' + Math.abs(dk.delta).toFixed(1) + '%（意外大幅去库：空头要警惕）');
  ['qg', 'bg'].forEach(k => { const t = by[k]; if (t && t.delta != null && t.delta >= 3 && t.yy && t.yy.v >= 3) warns.push(t.def.n + '较上期升 ' + t.delta.toFixed(1) + ' 个点、且比去年同期高 ' + t.yy.v.toFixed(1) + ' 个点（需求明显强于去年；只有3/15后、≥75%且同比≥+8点才会触发“需求爆发”离场条件）'); });
  if (by.qin && by.qout && by.qin.delta != null && by.qout.delta != null && by.qin.delta >= 5 && by.qout.delta <= -2) goods.push('青岛入库率大升、出库率走低：现货压力在积聚（强化空头逻辑）');
  if (by.stk && by.stk.delta != null && by.stk.delta >= 3) goods.push('社会库存较上期升 ' + by.stk.delta.toFixed(1) + '%（累库，强化空头逻辑）');
  const fresh = E.filter(t => !t.stale).length, last = E.reduce((a, t) => t.last.d > a ? t.last.d : a, '');
  return { T, by, n: E.length, tot: RUIND.length, bear, bull, dir, warns, goods, fresh, last, stale: E.length - fresh };
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
  const CH = { span: 120 };
  /* 指标序列（自动抓取，只读）{k:[{d,v,m?}]} 与 抓取元信息 */
  let AUTO = {}, AUTOINFO = null;
  /* 接上 data/ru_live.json（Actions 追加的最新真实日线 {d,o,h,l,c}）：按快照最后一天的 调整价/真实价 比例换算 */
  function mergeLive(j) {
    if (!j || !j.d || !j.d.length) return; const n = S.d.length, f = S.c[n - 1] / S.r[n - 1];
    for (let i = 0; i < j.d.length; i++) { if (j.d[i] <= S.d[S.d.length - 1]) continue; S.d.push(j.d[i]); S.o.push(j.o[i] * f); S.h.push(j.h[i] * f); S.l.push(j.l[i] * f); S.c.push(j.c[i] * f); S.r.push(j.c[i]); S.m.push(j.m && j.m[i] ? String(j.m[i]).replace(/^RU/, '') : S.m[S.m.length - 1]); }
  }
  const indAll = () => AUTO;
  function setAuto(j) { AUTO = {}; const ks = new Set(RUIND.map(d => d.k).concat(RUIND.map(d => d.y).filter(Boolean))); ks.forEach(k => { if (j && Array.isArray(j[k]) && j[k].length) AUTO[k] = j[k].filter(p => p && /^\d{4}-\d{2}-\d{2}$/.test(p.d) && typeof p.v === 'number' && isFinite(p.v)); }); AUTOINFO = { updated: (j && j.updated) || '', calc: new Set((j && j.calc) || []), warn: (j && j.warn) || [] }; }
  async function loadAuto() { try { const r = await fetch('data/ru_ind_auto.json?_=' + Date.now(), { cache: 'no-store' }); if (r.ok) setAuto(await r.json()); } catch (_) {} }
  async function loadLive() { try { const r = await fetch('data/ru_live.json?_=' + Date.now(), { cache: 'no-store' }); if (r.ok) mergeLive(await r.json()); } catch (_) {} }
  /* ---- 天气（浏览器直连 Open-Meteo，免密钥；每6小时缓存一次） ---- */
  async function jget(u) { const r = await fetch(u); if (!r.ok) throw new Error(r.status); return r.json(); }
  async function loadWx(force) {
    const today = todayBJ(); if (window.__RU_WX_MOCK) { WX.rs = window.__RU_WX_MOCK; WX.v = ruWxVerdict(WX.rs); WX.at = Date.now(); return; }
    const c = lsGet('ru-wx2', null); if (!force && c && c.today === today && Date.now() - c.at < 6 * 3600e3) { WX.rs = c.rs; WX.v = ruWxVerdict(c.rs); WX.at = c.at; return; }
    WX.busy = true; paint();
    const y0 = +today.slice(0, 4), years = [y0 - 5, y0 - 4, y0 - 3, y0 - 2, y0 - 1];
    const rs = await Promise.all(RUREG.map(async g => {
      try {
        const tz = encodeURIComponent(g.tz), base = 'latitude=' + g.lat + '&longitude=' + g.lon + '&timezone=' + tz;
        const [fc, hs] = await Promise.all([
          jget('https://api.open-meteo.com/v1/forecast?' + base + '&daily=precipitation_sum,temperature_2m_max&past_days=35&forecast_days=7'),
          jget('https://archive-api.open-meteo.com/v1/archive?' + base + '&start_date=' + years[0] + '-01-01&end_date=' + years[4] + '-12-31&daily=precipitation_sum,temperature_2m_max')]);
        const r = ruRegionWx({ d: fc.daily.time, p: fc.daily.precipitation_sum, tx: fc.daily.temperature_2m_max }, { d: hs.daily.time, p: hs.daily.precipitation_sum, tx: hs.daily.temperature_2m_max }, today, years, g.kind);
        return Object.assign({ k: g.k, n: g.n, core: g.core, kind: g.kind, pri: g.pri }, r);
      } catch (e) { return { k: g.k, n: g.n, core: g.core, kind: g.kind, pri: g.pri, err: String(e && e.message || e) }; }
    }));
    WX.busy = false; WX.rs = rs; WX.v = ruWxVerdict(rs); WX.at = Date.now(); if (rs.some(r => !r.err)) lsSet('ru-wx2', { today, at: WX.at, rs });
  }
  /* ---- 渲染 ---- */
  const chip = (ok, t, tip) => '<span class="sc ' + (ok == null ? '' : ok ? 'y' : 'n') + '"' + (tip ? ' title="' + esc(tip) + '"' : '') + '>' + (ok == null ? '' : ok ? '✓ ' : '✗ ') + esc(t) + '</span>';
  function planNow() { return ruPlan(S, todayBJ(), WX.v, OPT.pos && OPT.pos.px ? OPT.pos : null, { stopY: OPT.stopY, surge: ruDemandSurge(indAll(), todayBJ()) }); }
  const indNow = () => ruIndSummary(indAll(), todayBJ());
  const ago = n => n <= 0 ? '今天' : n + '天前';
  /* 迷你曲线：和豆粕趋势墙同一种画法（面积+线+末点） */
  function spark(vs, color, W, H) {
    if (!vs || vs.length < 2) return '';
    const lo = Math.min(...vs), hi = Math.max(...vs), r = (hi - lo) || 1, pad = 4, x = i => pad + i / (vs.length - 1) * (W - 2 * pad), y = v => pad + (hi - v) / r * (H - 2 * pad);
    const d = vs.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join('');
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" aria-hidden="true"><path class="ar" d="' + d + 'L' + x(vs.length - 1).toFixed(1) + ' ' + H + 'L' + x(0).toFixed(1) + ' ' + H + 'Z" fill="' + color + '" opacity=".10"/><path class="ln" d="' + d + '" stroke="' + color + '" vector-effect="non-scaling-stroke"/><circle cx="' + x(vs.length - 1).toFixed(1) + '" cy="' + y(vs[vs.length - 1]).toFixed(1) + '" r="2.6" fill="' + color + '"/></svg>';
  }
  const mcolor = m => m > 0 ? 'var(--bull)' : m < 0 ? 'var(--bear)' : 'var(--ink2)';
  const fnum = (v, dp) => v == null || isNaN(v) ? '—' : (+v).toFixed(dp == null ? 1 : dp).replace(/\.0+$/, '');
  /* 指标格（和趋势墙的格子同一套 class） */
  function indTile(t) {
    const df = t.def; if (!t.n) return '<div class="tile pend rutile" data-ik="' + df.k + '"><div class="t1"><span class="n">' + esc(df.n) + '</span></div><div class="sk"><div class="na">暂无数据<br><small>等 Actions 自动抓取</small></div></div></div>';
    const tint = t.m > 0 ? 'tb2' : t.m < 0 ? 'tx2' : '', side = t.m > 0 ? 'sb' : t.m < 0 ? 'sx' : '', bd = t.m ? '<span class="bd ' + (t.m > 0 ? 'up' : 'down') + '">' + (t.m > 0 ? '偏多' : '偏空') + '</span>' : (t.stale ? '<span class="bd m">过期</span>' : '');
    const sg = v => (v >= 0 ? '+' : '') + fnum(v), calc = AUTOINFO && AUTOINFO.calc.has(t.last.d + ':' + df.k);
    let lab = '较上期', chg = '—', l2 = '上期', v2 = t.prev ? fnum(t.prev.v) : '—';
    if (df.mode === 'lvl') { lab = '同比'; chg = t.yy ? sg(t.yy.v) + (df.yu === '%' ? '%' : '点') : '—'; }
    else if (df.mode === 'chg') { chg = t.delta == null ? '—' : (t.delta >= 0 ? '↑' : '↓') + fnum(Math.abs(t.delta), 1) + '点'; l2 = '近4周'; v2 = t.d4 == null ? '—' : sg(t.d4); }
    else chg = t.delta == null ? '—' : (t.delta >= 0 ? '↑' : '↓') + fnum(Math.abs(t.delta), 1) + '%';
    const mm = df.freq === 'm' && t.last.m ? t.last.m.slice(2).replace('-', '/') + '月' : t.last.d.slice(5);
    return '<div class="tile ' + side + ' ' + tint + ' rutile" data-ik="' + df.k + '" title="' + esc(df.src) + '" aria-label="' + esc(df.n) + '，最新' + fnum(t.last.v) + esc(df.u) + '"><div class="t1"><span class="n">' + esc(df.n) + '<small class="dim"> 自动' + (calc ? '*' : '') + '</small></span>' + bd + '</div>'
      + '<div class="t2"><span class="v">' + (df.mode === 'chg' ? sg(t.last.v) : fnum(t.last.v)) + '</span><span class="u">' + esc(df.u) + '</span></div>'
      + '<div class="sk">' + (t.pts.length >= 3 ? spark(t.pts.map(p => p.v), mcolor(t.m), 120, 40) : '<div class="na">只有 ' + t.n + ' 期，满3期画曲线</div>') + '</div>'
      + '<div class="chips"><div class="chip"><div class="l">' + lab + '</div><div class="a" style="color:' + mcolor(t.m) + '">' + esc(chg) + '</div></div><div class="chip"><div class="l">' + l2 + '</div><div class="a">' + v2 + '</div></div><div class="chip' + (t.stale ? ' na' : '') + '"><div class="l">' + (df.freq === 'm' ? '统计月' : '统计日') + '</div><div class="a"' + (t.stale ? ' style="color:var(--amber)"' : '') + '>' + esc(mm) + '</div></div></div></div>';
  }
  /* 天气格 */
  function wxTile(g) {
    const r = (WX.rs || []).find(x => x.k === g.k);
    if (!r) return '<button class="tile pend rutile" data-ik="wx"><div class="t1"><span class="n">' + esc(g.n) + '</span></div><div class="sk"><div class="na">' + (WX.busy ? '正在取天气…' : '还没取天气') + '</div></div></button>';
    if (r.err) return '<button class="tile pend rutile" data-ik="wx"><div class="t1"><span class="n">' + esc(g.n) + '</span></div><div class="sk"><div class="na">没取到<br><small>' + esc(r.err) + '</small></div></div></button>';
    const side = r.sev >= 2 ? 'sb' : '', tint = r.sev >= 2 ? 'tb3' : r.sev ? 'tb2' : '', bd = r.sev >= 2 ? '<span class="bd up">严重</span>' : r.sev ? '<span class="bd up">注意</span>' : r.ur ? '<span class="bd m" title="一周累计降水<5mm 且均温≥33℃（你的阈值，只提示不拦单）">⚑</span>' : '';
    return '<button class="tile wxt ' + side + ' ' + tint + ' rutile" data-ik="wx" aria-label="' + esc(g.n) + '：' + esc(r.msg) + '"><div class="t1"><span class="n">' + esc(g.n) + '</span>' + bd + '</div>'
      + '<div class="t2"><span class="v" style="font-size:clamp(15px,2.2vh,19px)">' + esc(r.msg) + '</span></div>'
      + '<div class="sk"><div class="na" style="text-align:left;justify-content:flex-start;background:none;font-size:11.5px">' + (g.kind === 'wet' ? '看降雨偏多（割胶受阻）' : '看干旱+高温（开割推迟）') + (r.ratio != null ? '<br>30天降水=同期' + (r.ratio * 100).toFixed(0) + '%' : '') + (r.ur ? '<br>⚑ 一周无雨且≥33℃' : '') + '</div></div>'
      + '<div class="chips"><div class="chip"><div class="l">30天降水</div><div class="a">' + f0(r.p30) + 'mm' + (r.ratio != null ? '<span class="wr">·' + (r.ratio * 100).toFixed(0) + '%</span>' : '') + '</div></div><div class="chip"><div class="l">7天均温</div><div class="a">' + (r.t7 == null ? '—' : r.t7.toFixed(1) + '℃') + '</div></div><div class="chip"><div class="l">未来7天雨</div><div class="a">' + f0(r.f7) + 'mm</div></div></div></button>';
  }
  function wallHtml(IS) {
    const gt = g => IS.T.filter(t => t.def.g === g).map(indTile);
    const groups = [['供给', gt('供给')], ['库存', gt('库存')], ['青岛', gt('青岛')], ['需求', gt('需求')], ['天气', RUREG.map(wxTile)]];
    const upd = AUTOINFO && AUTOINFO.updated ? '，抓取于 ' + esc(AUTOINFO.updated) : '';
    let h = '<div class="wh"><span class="t">趋势墙</span><span class="hint">库存/青岛/产能利用率/产量/进口全部由 Actions 自动抓取隆众周报月报' + upd + '；天气自动取。颜色：对价格多空的含义</span></div>'
      + '<div class="why" style="padding:6px 20px">每一格一个指标，页面上不能录入。绿色=对价格偏空（强化空头逻辑），红色=偏多（削弱空头逻辑）。库存上升、进口/产量同比增加偏空；轮胎产能利用率同比走高、去库偏多。产量/进口看累计同比，轮胎产能利用率看同比(百分点)，青岛出入库率是较上周的变化。阈值是常识性的提示线，<b>没有回测，不会单独拦单</b>——只有天气严重异常、或“需求爆发”（3/15后全钢胎产能利用率≥75%且周升、同比≥+8点，自动判断）才会拦住做空。' + (AUTOINFO && AUTOINFO.warn.length ? '<br><span class="dim">抓取提示：' + esc(AUTOINFO.warn.slice(0, 3).join('；')) + '</span>' : '') + '</div><div class="tiles blocks rutiles">';
    groups.forEach(g => { h += '<div class="bh"><span>' + g[0] + '</span><i>' + g[1].length + '项</i></div><div class="blk"><div class="rail"><span>' + g[0] + '</span></div><div class="bg" style="grid-template-columns:repeat(' + g[1].length + ',minmax(0,1fr))">' + g[1].join('') + '</div></div>'; });
    return h + '</div>' + entryHtml(IS);
  }
  /* 数据来源说明 + 需求爆发离场条件（全部自动，没有任何手动录入） */
  function entryHtml(IS) {
    const DS = ruDemandSurge(indAll(), todayBJ());
    return '<details class="ruabout"><summary>数据来源与自动离场条件（点开）</summary><ul class="rurm"><li><b>需求爆发（自动，会拦做空/提示持仓离场）</b>：3月15日之后的统计周，全钢胎产能利用率 ≥' + RUSURGE.LEVEL + '% 且较上周上升、同比 ≥+' + RUSURGE.YOY + ' 个点，三条同时满足。当前：' + esc(DS.text) + '</li><li>库存：「中国天然橡胶社会库存周数据分析」「青岛地区天然橡胶样本库存和出入库率周数据分析」</li><li>产能利用率：「中国轮胎产能利用率周数据统计」（全钢胎/半钢胎）</li><li>产量：「全球天然橡胶产量月数据统计」（ANRPC预测）</li><li>进口：「中国天然橡胶进口量月数据统计」（海关终值，预估已剔除）</li></ul></details>';
  }
  /* 价格图：近N个交易日收盘（按最近真实价换算）+ MA5 + 历年3月窗口底色 + 挂单价/止损线 */
  function chartHtml(P, W, H) {
    const n = S.d.length, N = Math.min(CH.span, n), i0 = n - N, f = S.r[n - 1] / S.c[n - 1], px = i => S.c[i] * f;
    const lines = []; if (P.order && P.order.lim) { lines.push([P.order.lim, '限价 ' + f0(P.order.lim), 'var(--bear)']); lines.push([P.order.stop, '止损 ' + f0(P.order.stop), 'var(--amber)']); }
    if (OPT.pos && OPT.pos.px) { lines.push([OPT.pos.px, '开仓 ' + f0(OPT.pos.px), 'var(--ink)']); lines.push([OPT.pos.px * (1 + RUP.STOP / 100), '止损 ' + f0(OPT.pos.px * (1 + RUP.STOP / 100)), 'var(--amber)']); }
    const vals = []; for (let i = i0; i < n; i++) { vals.push(px(i)); const m = ruMA(S.c, i, RUP.MA); if (m != null) vals.push(m * f); } lines.forEach(l => vals.push(l[0]));
    let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
    const L = 8, R = 56, T = 10, B = 20, x = i => L + (i - i0) / Math.max(1, N - 1) * (W - L - R), y = v => T + (hi - v) / (hi - lo) * (H - T - B);
    let g = '', k = i0; while (k < n) { if (S.d[k].slice(5, 7) === '03') { let e = k; while (e + 1 < n && S.d[e + 1].slice(5, 7) === '03') e++; g += '<rect x="' + x(k).toFixed(1) + '" y="' + T + '" width="' + Math.max(2, x(e) - x(k)).toFixed(1) + '" height="' + (H - T - B) + '" fill="var(--amber)" opacity=".13"/><text x="' + ((x(k) + x(e)) / 2).toFixed(1) + '" y="' + (T + 11) + '" text-anchor="middle" class="lw" fill="var(--amber)">3月</text>'; k = e + 1; } else k++; }
    let c = '', m5 = '', last = -1; for (let i = i0; i < n; i++) { c += (i === i0 ? 'M' : 'L') + x(i).toFixed(1) + ' ' + y(px(i)).toFixed(1); const m = ruMA(S.c, i, RUP.MA); if (m != null) { m5 += (last < 0 ? 'M' : 'L') + x(i).toFixed(1) + ' ' + y(m * f).toFixed(1); last = i; } }
    let ax = '', pm = ''; for (let i = i0; i < n; i++) { const mo = S.d[i].slice(0, 7); if (mo !== pm) { pm = mo; if (i > i0 + 2) ax += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 5) + '" class="lw" text-anchor="middle">' + (S.d[i].slice(5, 7) === '01' ? S.d[i].slice(0, 4) + '-' : '') + (+S.d[i].slice(5, 7)) + '月</text>'; } }
    let ls = ''; lines.forEach(l => { if (l[0] >= lo && l[0] <= hi) ls += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(l[0]).toFixed(1) + '" y2="' + y(l[0]).toFixed(1) + '" stroke="' + l[2] + '" stroke-dasharray="5 4" stroke-width="1.2"/><text x="' + (W - R + 4) + '" y="' + (y(l[0]) + 4).toFixed(1) + '" class="lv" fill="' + l[2] + '">' + esc(l[1]) + '</text>'; });
    const lp = px(n - 1);
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="橡胶主连近' + N + '个交易日收盘价和5日均线">' + g + ax + ls + '<path d="' + m5 + '" fill="none" stroke="var(--amber)" stroke-width="1.3" opacity=".9"/><path d="' + c + '" fill="none" stroke="var(--ink)" stroke-width="1.7" stroke-linejoin="round"/><circle cx="' + x(n - 1).toFixed(1) + '" cy="' + y(lp).toFixed(1) + '" r="3" fill="var(--ink)"/>'
      + (y(lp) - T > 16 ? '<text x="' + (W - R + 4) + '" y="' + T + '" class="lv">' + f0(hi) + '</text>' : '') + '<text x="' + (W - R + 4) + '" y="' + (H - B) + '" class="lv">' + f0(lo) + '</text><text x="' + (W - R + 4) + '" y="' + (y(lp) - 6).toFixed(1) + '" class="lv" fill="var(--ink)" font-weight="600">' + f0(lp) + '</text></svg>';
  }
  function drawChart() { const el = document.getElementById('ruKl'); if (!el) return; const W = Math.max(280, Math.floor(el.clientWidth || 600)), H = W < 520 ? 230 : 260; el.innerHTML = chartHtml(planNow(), W, H); }
  function sigHtml(P, IS, eqLots) {
    const tone = { go: 'short', exit: 'wait', holdwx: 'wait', hold: 'short', blocked: 'wait', wait: 'wait', pre: 'wait', sleep: 'wait', stale: 'wait', done: 'wait' }[P.st] || 'wait', cls = P.st === 'stale' ? 'gate' : tone;
    const DS = ruDemandSurge(indAll(), todayBJ()), wv = WX.v, wxOk = !wv || wv.level === 'unknown' ? null : wv.level !== 'block';
    const chips = chip(P.inMar ? true : null, P.inMar ? '3月窗口' : '不在3月窗口') + (P.inMar || P.pre ? chip(P.reb, '收盘≥MA5（反弹）' + (P.ma ? ' ' + f0(P.ma) : '')) : '')
      + (wv ? chip(wxOk, wv.level === 'block' ? '天气：暂缓' : wv.level === 'warn' ? '天气：轻度异常' : wv.level === 'ok' ? '天气正常' : '天气未取到', wv.text) : '')
      + chip(DS.on ? false : DS.last ? null : null, DS.on ? '需求爆发（自动）' : '需求未爆发', DS.text)
      + '<span class="sc sep">止损 ' + RUP.STOP + '% · 月底平仓 · 不设止盈</span>';
    const sizeLn = P.order && eqLots && eqLots.lots >= 1 ? '<div class="sb">建议总共 <b>' + eqLots.lots + ' 手</b>（止损亏约 ' + f0(eqLots.loss) + ' 元≈权益 ' + (eqLots.loss / OPT.eq * 100).toFixed(1) + '%）' + (eqLots.lots >= 2 ? '，可分2批：先一半，次日再反弹再加' : '') + '</div>' : '';
    const left = '<button class="sg ' + cls + '" data-ru="goplan" aria-label="橡胶入场信号：' + esc(P.head) + '"><div class="cl">橡胶 RU · 3月季节性做空 · 最近收盘（' + esc(P.last.slice(5)) + '）' + (P.real ? ' ' + f0(P.real) : '') + '</div><div class="hd">' + esc(P.head) + '</div><div class="sb">' + esc(P.sub) + '</div>' + sizeLn + '<div class="scs">' + chips + '</div></button>';
    let right;
    if (P.pos && OPT.pos) {
      const up = P.pos.r >= 0;
      right = '<div class="sg pos ' + (P.st === 'exit' || P.st === 'holdwx' ? 'exit' : 'hold') + '"><div class="cl">空 ' + esc(OPT.pos.contract || '') + ' ' + esc(OPT.pos.lots || '') + ' 手 @' + f0(OPT.pos.px) + ' · ' + esc((OPT.pos.d || '').slice(5)) + '</div><div class="hd big" style="color:' + (up ? 'var(--bear)' : 'var(--bull)') + '">' + p1(P.pos.r) + '</div><div class="sb">止损价 ' + f0(P.pos.stop) + '（距现价 ' + (P.pos.stopGap == null ? '—' : P.pos.stopGap.toFixed(1) + '%') + '）<br>到 ' + esc(P.exitD.slice(5)) + ' 收盘平仓</div></div>';
    } else if (P.order) {
      right = '<div class="sg"><div class="cl">建议价格（' + esc(P.dom || '当前主力') + '）</div><div class="hd big">≥ ' + f0(P.order.lim) + '<small> 限价空</small></div><div class="sb">止损 ' + f0(P.order.stop) + '（+' + RUP.STOP + '%）· 参考目标 ' + f0(P.order.ref) + '（历史平均跌 ' + RUP.AVG_DROP + '%，不设止盈）<br>离场 ' + esc(P.exitD) + ' 收盘 · 次日没成交就作废，不追</div></div>';
    } else right = '<div class="sg"><div class="cl">当前主力合约</div><div class="hd big">' + esc(P.dom || '—') + '</div><div class="sb">' + (P.inMar || P.pre ? '3月下旬主力常从 ' + esc(P.mar05) + ' 换到 ' + esc(P.mar09) + '；新开仓做当时主力，已持有的不用换。' : '下一个窗口 ' + esc(P.nextWin) + '（还有 ' + P.daysTo + ' 天）') + '</div></div>';
    return '<section class="sigbar rusig">' + left + right + '</section>';
  }
  function bandHtml(P, IS) {
    const n = S.d.length, f = S.r[n - 1] / S.c[n - 1], chg = n > 1 ? S.c[n - 1] / S.c[n - 2] - 1 : null, c5 = n > 5 ? S.c[n - 1] / S.c[n - 6] - 1 : null;
    const pv = '<div class="cell pv"><div class="cl">RU 主连价格与均线</div><div class="px"><span class="p">' + f0(P.real) + '</span><span class="c ' + (chg > 0 ? 'bull' : chg < 0 ? 'bear' : '') + '">' + (chg == null ? '' : (chg >= 0 ? '+' : '') + (chg * 100).toFixed(2) + '%') + '</span><span class="dim" style="font-size:11.5px;margin-left:6px">' + esc(P.last.slice(5)) + ' 收盘</span></div><div class="sub">近5天 ' + (c5 == null ? '—' : (c5 >= 0 ? '+' : '') + (c5 * 100).toFixed(1) + '%') + ' · MA5 ' + f0(P.ma) + (P.reb ? '（收盘在其上，反弹）' : '（收盘在其下）') + ' · 主力 ' + esc(P.dom || '—') + '</div></div>';
    const fd = IS.dir === 'na' ? '数据不足' : IS.dir, fc = IS.dir === '偏空' ? 'var(--bear)' : IS.dir === '偏多' ? 'var(--bull)' : 'var(--ink)';
    const fs = '<div class="cell half"><div class="cl">基本面（库存·产能利用率·产量·进口）</div><div class="fund"><div><div class="big" style="color:' + fc + '">' + esc(fd) + '<small class="num">' + (IS.n ? '空' + IS.bear + ' 多' + IS.bull : '') + '</small></div></div></div><div class="sub">' + (IS.warns.length ? '⚠ ' + esc(IS.warns[0]) : IS.goods.length ? esc(IS.goods[0]) : IS.n ? '自动 ' + IS.n + '/' + IS.tot + ' 项 · 最近 ' + esc(IS.last.slice(5)) + (IS.stale ? ' · ' + IS.stale + ' 项过期' : '') : '指标数据还没抓到（等 Actions 自动抓取）') + '</div></div>';
    const wv = WX.v, wt = !wv ? (WX.busy ? '正在取…' : '未取') : wv.level === 'block' ? '暂缓做空' : wv.level === 'warn' ? '轻度异常' : wv.level === 'ok' ? '正常' : '没取到', wcol = wv && wv.level === 'block' ? 'var(--bull)' : wv && wv.level === 'warn' ? 'var(--amber)' : 'var(--ink)';
    const wx = '<div class="cell half"><div class="cl">开割天气（泰北·泰东北·越南·印尼巨港）</div><div class="big" style="font-size:clamp(20px,3.1vh,28px);color:' + wcol + '">' + esc(wt) + '</div><div class="sub">' + (wv ? esc(wv.text.replace(/^主产区天气异常：/, '')) : '') + ' <button class="lnk" data-ru="wxre">重新取</button>' + (WX.at ? ' <span class="dim">' + new Date(WX.at + 8 * 3600e3).toISOString().slice(5, 16).replace('T', ' ') + '</span>' : '') + '</div></div>';
    return '<section class="band ruband">' + pv + fs + wx + '</section>';
  }
  function checksHtml(P) {
    const it = (a, b) => '<span class="ruci"><i>' + esc(a) + '</i>' + esc(b) + '</span>';
    return '<nav class="checks rucheck" aria-label="橡胶要点">' + it('主力', P.dom || '—') + it(P.inMar ? '离场日' : '下个窗口', P.inMar ? P.exitD.slice(5) : P.nextWin) + it('止损', RUP.STOP + '% · 盘中最高价触及') + it('入场', '收盘≥MA5，次日限价≥收盘+0.3%') + it('止损后', '当月不再开仓') + it('合约', '新开仓用当时主力，已持有不换') + '</nav>';
  }
  function histBars(H, ST) {
    if (!H.length) return '<p class="dim">没有历史数据。</p>';
    const mx = Math.max(8, ...H.filter(x => x.trade).map(x => Math.abs(x.ret * 100)));
    const bars = H.map(x => x.trade ? '<div class="mc" title="' + x.y + '：信号 ' + esc(x.sig.slice(5)) + '，成交 ' + esc(x.entD.slice(5)) + '，离场 ' + esc(x.exitD.slice(5)) + ' ' + esc(x.why) + '"><span class="mv" style="color:' + (x.ret >= 0 ? 'var(--bear)' : 'var(--bull)') + '">' + (x.ret * 100).toFixed(1) + '</span><div class="mb"><i style="height:' + Math.max(3, Math.abs(x.ret * 100) / mx * 100) + '%;background:' + (x.ret >= 0 ? 'var(--bear)' : 'var(--bull)') + '"></i></div><span class="mm">' + String(x.y).slice(2) + '</span></div>' : '<div class="mc" title="' + x.y + '：没出信号"><span class="mv">—</span><div class="mb"></div><span class="mm">' + String(x.y).slice(2) + '</span></div>').join('');
    return (ST ? '<p class="hl">' + ST.years + ' 个3月里 ' + ST.n + ' 年出信号成交：平均 <b>' + p1(ST.mean) + '</b>，胜率 ' + ST.win.toFixed(0) + '%，最好 ' + p1(ST.best) + '，最差 ' + p1(ST.worst) + '（t=' + ST.t.toFixed(1) + '）。<span class="dim">样本只有 ' + ST.n + ' 年，多重检验后不显著，仓位要小。</span></p>' : '') + '<div class="mbars rubars">' + bars + '</div><div class="mleg"><span>每根柱子=当年3月按这条规则的收益%（含成本）；绿=赚，红=亏</span></div>';
  }
  function remindHtml(P) {
    const yy = P.nextWin ? +P.nextWin.slice(0, 4) : +todayBJ().slice(0, 4), L = [['02-10', '准备期开始：开始看天气和价格'], ['03-01', '窗口开始：每个收盘后看一次；收盘站上MA5且天气正常 → 次日挂限价空'], ['(每周)', '3月里每周看一眼趋势墙的库存、产能利用率（自动更新，无需录入）'], ['(每天)', '持仓时：止损价（+' + RUP.STOP + '%）、天气转异常、开割延迟、需求走强 → 考虑离场'], [ruLastWeekdayOfMarch(yy).slice(5), '3月最后一个交易日：收盘前平仓']];
    const alert = P.st === 'go' || P.st === 'exit' || P.st === 'holdwx' || P.st === 'blocked';
    return '<ul class="rurm">' + L.map(x => '<li><b>' + esc(x[0]) + '</b> ' + esc(x[1]) + '</li>').join('') + '</ul><p class="' + (alert ? 'ruhot' : 'dim') + '">' + (alert ? '👉 今天要处理：' + esc(P.head) : '今天没有要处理的事。') + '</p><p class="dim">手机推送（准备期、窗口开始、出信号含挂单价和止损价、被天气拦住、最后交易日平仓）已随 v102.0 接入现有推送。</p>';
  }
  function wxDetail() {
    if (WX.busy) return '<p class="dim">正在取天气…</p>';
    if (!WX.rs) return '<p class="dim">还没取天气。</p>';
    const v = WX.v; let h = '<table class="rutb"><thead><tr><th>产区</th><th>近30天降水</th><th>近7天最高温</th><th>未来7天降水预报</th><th>判断</th></tr></thead><tbody>';
    WX.rs.forEach(r => { h += r.err ? '<tr><td>' + esc(r.n) + '</td><td colspan="4" class="dim">没取到（' + esc(r.err) + '）</td></tr>' : '<tr class="' + (r.sev >= 2 ? 'bad' : r.sev ? 'warn' : '') + '"><td>' + esc(r.n) + ' <small class="dim">' + (r.pri === 1 ? '第一优先' : '第二优先') + '</small></td><td>' + f0(r.p30) + ' mm' + (r.n30 != null ? '<br><small class="dim">近5年同期均值 ' + f0(r.n30) + '（' + (r.ratio * 100).toFixed(0) + '%）</small>' : '') + '</td><td>' + (r.t7 == null ? '—' : r.t7.toFixed(1) + '℃') + (r.tn != null ? '<br><small class="dim">近5年同期 ' + r.tn.toFixed(1) + '℃</small>' : '') + '</td><td>' + f0(r.f7) + ' mm</td><td>' + esc(r.msg) + (r.ur ? '<br><small>⚑ 一周无雨且均温≥33℃</small>' : '') + '</td></tr>'; });
    return h + '</tbody></table><p class="dim ruft">只看会影响「开割预期能否兑现」的产区：<b>第一优先</b>=泰国北部/东北部、越南东南部（干旱+高温→试割不畅、开割推迟，对空头是扰动）；<b>第二优先</b>=印尼南部巨港（降雨持续偏多→割胶受阻，供应阶段性收紧）。不看：西双版纳（4月才割胶）、泰国南部（割胶尾声）、海南。数据：Open-Meteo（再分析+预报模型，不是气象站实测）。判定：近30天降水不到近5年同期的 25%（且少30mm以上）=严重偏旱，50%=偏旱；偏热（7天均温比近5年同期高2℃）叠加偏旱升一级，单独高3.5℃以上=高温；印尼降雨超过同期200%（多60mm）=偏多、300%（多100mm）=严重偏多。你的阈值「连续一周累计降水<5mm 且均温≥33℃」显示为 ⚑，但<b>不单独拦单</b>：泰国东北3月平均最高温本来就常在33℃以上，这条绝对阈值几乎每年3月都会触发（我这里连不上 Open-Meteo，看上表「近5年同期」一列自己核对）。拦单规则：第一优先产区出现严重异常，或各区「注意」累计≥3。<b>这些阈值没有历史天气回测。</b></p>';
  }
  function ruHtml() {
    const P = planNow(), IS = indNow(), eqLots = P.order && P.real ? ruSize(OPT.eq, P.order.lim, OPT.risk, OPT.margin) : null, H = ruHistory(S), ST = ruStats(H);
    const spans = [[60, '60日'], [120, '120日'], [250, '250日']].map(x => '<button data-ru="span" data-n="' + x[0] + '" aria-pressed="' + (CH.span === x[0]) + '">' + x[1] + '</button>').join('');
    const chartCol = '<section class="chart" aria-label="橡胶价格与历史"><div class="ch-h"><span class="t">RU 主连收盘与5日线</span><div class="seg" role="group" aria-label="显示多久">' + spans + '</div></div><div class="hl">黄底=历年3月窗口；黄线=MA5。收盘站上黄线才是「反弹」，出信号后次日挂限价（见上方建议价格）。</div><div class="rukl" id="ruKl"></div>'
      + '<h3 class="ruh">历年3月按这条规则的结果</h3>' + histBars(H, ST)
      + '<h3 class="ruh">建议手数（轻仓、分批）</h3><div class="ruin"><label>账户权益(元)<input id="ruEq" inputmode="numeric" value="' + OPT.eq + '"></label><label>单笔最多亏(权益%)<input id="ruRisk" inputmode="decimal" value="' + OPT.risk + '"></label><label>保证金率(%)<input id="ruMg" inputmode="decimal" value="' + OPT.margin + '"></label></div><p class="dim">手数=按5%止损亏损不超过权益的 ' + OPT.risk + '%，且保证金占用不超过权益 ' + RUP.USE_CAP + '%，两者取小。' + (eqLots ? (eqLots.lots >= 1 ? '现在价位：' + eqLots.lots + ' 手（止损亏 ' + f0(eqLots.loss) + ' 元，占用保证金约 ' + f0(eqLots.margin) + ' 元）。' : '现在价位按你的风险设置不够1手。') : '出信号后这里给出手数。') + '分2批是建议，没有回测过。</p>'
      + '<h3 class="ruh">我的橡胶空单</h3>' + posHtml(P) + '<h3 class="ruh">提醒</h3>' + remindHtml(P)
      + '<details class="ruabout"><summary>天气明细与口径</summary>' + wxDetail() + '</details>'
      + '<details class="ruabout"><summary>规则依据与局限</summary>' + aboutHtml() + '</details></section>';
    return sigHtml(P, IS, eqLots) + bandHtml(P, IS) + checksHtml(P) + '<main class="main rumain">' + chartCol + '<section class="wall rwall" aria-label="趋势墙">' + wallHtml(IS) + '</section></main>';
  }

  function posHtml(P) {
    const pos = OPT.pos;
    if (pos && pos.px) return (P.roll ? '<div class="ruwx warn"><b>主力已换到 ' + esc(P.dom) + '，你的单子在 ' + esc(pos.contract) + '</b>：不用换，拿到月底平仓就行；下面的浮盈、止损线按主连价格估算，和你的合约有价差，实际以你软件里的 ' + esc(pos.contract) + ' 价格为准。</div>' : '') + '<p>空 ' + esc(pos.contract || '') + ' ' + esc(pos.lots || '') + ' 手 @ ' + f0(pos.px) + '（' + esc(pos.d || '') + '）' + (P.pos ? '：浮盈 <b class="' + (P.pos.r >= 0 ? 'bear' : 'bull') + '">' + p1(P.pos.r) + '</b>，止损价 ' + f0(P.pos.stop) + '（距现价 ' + (P.pos.stopGap == null ? '—' : P.pos.stopGap.toFixed(1) + '%') + '），到 ' + esc(P.exitD) + ' 收盘平仓' : '') + ' <button class="lnk" data-ru="close">已平仓，清除</button> <button class="lnk" data-ru="stopped">止损平仓（今年不再开）</button></p>';
    return '<div class="ruin"><label>开仓日<input id="ruPd" placeholder="YYYY-MM-DD"></label><label>成交价<input id="ruPp" inputmode="decimal"></label><label>手数<input id="ruPl" inputmode="numeric"></label><label>合约<input id="ruPc" placeholder="' + esc(P.dom || 'RU2705') + '"></label><button class="tb" data-ru="open" style="border:1px solid var(--line)">记一笔空单</button></div><p class="dim">只记在这台设备上，用来算浮盈、止损线和离场提醒。</p>';
  }

  function aboutHtml() {
    return '<p><b>逻辑</b>：天然橡胶11月到次年2-3月停割，3月中下旬起泰国北部、越南先试割，4月规模开割。3月是「停割利多出尽 + 开割供应增量预期」的兑现窗口，交易的是开割预期，不是开割现实。</p><p><b>回测</b>：2013–2026 年3月做空，平均约 +5.7%/年，14年里11年赚（79%）；前半段（2013-19）+5.6%、后半段（2020-26）+5.8%，20号胶同向（2020–26 年3月7年6年跌）。3月是12个月里最强的，但多重检验后仍不显著。</p><p><b>入场</b>：不追空。3月内收盘站上5日均线（反弹）才出信号，次日限价卖出≥收盘价+0.3%。三种「逢反弹」写法（站上MA5/MA10、距低点反弹1.5%、贴近前10日高点）回测平均都在 +4.1%~+5.7%，差别在噪声内，按你的文字取最简单的MA5。</p><p><b>离场</b>：5%止损（盘中最高价触及）；3月最后一个交易日收盘平仓。止盈6%/8%回测更差（砍掉大跌里的盈利），所以不设止盈；「参考目标」只是历史平均跌幅。</p><p><b>天气</b>：3月交易的是「开割预期」，所以只看会影响开割节奏的产区：泰国北部/东北部、越南东南部（干旱+高温→试割不畅、开割推迟）和印尼南部巨港（降雨偏多→割胶受阻）。西双版纳4月才割胶、泰国南部在割胶尾声，不看。判定用降水/气温相对近5年同期的异常，<b>没有历史天气回测</b>，只作为风险开关。</p><p><b>指标</b>：库存（社会/深色/浅色）、青岛库存与出入库率、全钢/半钢胎产能利用率、全球产量、进口，全部由 Actions 自动抓取（来源：隆众/Mysteel 周报月报），页面不能录入。它们在趋势墙里显示方向（偏空/偏多），但阈值没有回测，<b>只有天气严重异常和“需求爆发”（3/15后全钢胎产能利用率≥75%、周升、同比≥+8点，自动判断）会拦住信号</b>。没有做：多NR空RU套利（没有价差回测）。</p><p><b>换合约</b>：回测用的是主力连续价格，3月一般是 5 月合约（RU05），3月下旬（约19~30日）主力常换到 9 月合约。已经持有的单子不用换：拿着原合约到月底平仓（它仍有足够成交量）。想换也行：同一天先平旧合约、再空新主力合约，回测的连续价格就是这么算的，实际多付两次手续费和滑点。新开仓一律做当时的主力合约。止损后当月不再重新开仓（回测里每年只做一次，止损后再开没有验证）。</p><p><b>限制</b>：每年最多一笔；单品种一个月的结果不能当系统策略，仓位要小。</p>';
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
    app.innerHTML = VIEW === 'all' ? '<div class="ruin2">' + overviewHtml() + '</div>' : ruHtml();
    if (VIEW === 'ru') drawChart();
  }
  function setView(v) { VIEW = v; lsSet('fut-view', v); if (v !== 'meal' && !WX.rs && !WX.busy) loadWx().then(paint); paint(); try { window.scrollTo(0, 0); const a = $('#ruApp'); if (a) a.scrollTop = 0; } catch (_) {} if (v === 'meal') { try { window.dispatchEvent(new Event('resize')); } catch (_) {} } }
  window.addEventListener('resize', () => { if (VIEW === 'ru') drawChart(); });
  document.addEventListener('click', e => {
    const b = e.target.closest('#vSeg button'); if (b) return setView(b.dataset.v);
    const oc = e.target.closest('.ov-c'); if (oc) return setView(oc.dataset.v);
    const tl = e.target.closest('.rutile[data-ik]');
    if (tl) { if (tl.dataset.ik === 'wx') { const d = [...document.querySelectorAll('.ruabout')].find(x => /天气明细/.test(x.textContent)); if (d) { d.open = true; d.scrollIntoView({ block: 'center' }); } } return; }
    const t = e.target.closest('[data-ru]'); if (!t) return; const a = t.dataset.ru;
    if (a === 'wxre') { WX.rs = null; loadWx(true).then(paint); paint(); }
    if (a === 'span') { CH.span = +t.dataset.n || 120; paint(); }
    if (a === 'goplan') { const d = document.querySelector('.rucheck'); if (d) d.scrollIntoView({ block: 'nearest' }); }
    if (a === 'stopped') { OPT.stopY = +todayBJ().slice(0, 4); lsSet('ru-stopY', OPT.stopY); OPT.pos = null; lsSet('ru-pos', null); paint(); }
    if (a === 'close') { OPT.pos = null; lsSet('ru-pos', null); paint(); }
    if (a === 'open') { const d = ($('#ruPd').value || todayBJ()).trim(), px = +$('#ruPp').value, lots = +$('#ruPl').value; if (!(px > 0)) return; const pc = ($('#ruPc').value || '').trim().toUpperCase() || (planNow().dom || ''); OPT.pos = { d, px, lots: lots > 0 ? lots : null, contract: pc }; lsSet('ru-pos', OPT.pos); paint(); }
  });
  document.addEventListener('change', e => {
    const id = e.target && e.target.id;
    const m = { ruEq: ['eq', 'ru-eq'], ruRisk: ['risk', 'ru-risk'], ruMg: ['margin', 'ru-margin'] }[e.target && e.target.id]; if (!m) return;
    const v = +e.target.value; if (!(v > 0)) return; OPT[m[0]] = v; lsSet(m[1], v); paint();
  });
  window.__ru = { surge: () => ruDemandSurge(indAll(), todayBJ()), plan: planNow, paint, setView, loadWx, S: () => S, view: () => VIEW, history: () => ruHistory(S), size: ruSize, ind: () => indAll(), auto: () => AUTO, loadAuto, indSummary: indNow };
  Promise.all([loadLive(), loadAuto()]).then(() => { paint(); if (VIEW !== 'meal') loadWx().then(paint); });
  paint();
})();
