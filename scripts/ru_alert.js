/* 橡胶3月做空提醒（v102.0）：输出和 plan_alert.js 同格式的 {priceDate,gate,side,events}，交给 notify_alert.py（独立 state：data/ru_alert_state.json）。
 * 规则/计划全部来自 cockpit/rubber.js 的纯函数（和页面同一份）。服务器不知道你的空单和手动判断，所以：
 *   准备期(2/10) → 3/1窗口开始 → 出信号(挂单价/止损价) → 信号被天气拦住 → 天气转坏(持仓者考虑离场) → 3月最后交易日平仓提醒。
 * 用法：node scripts/ru_alert.js [--data data] [--out f] [--today YYYY-MM-DD] [--nowx] */
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..');
const src = fs.readFileSync(path.join(root, 'cockpit', 'rubber.js'), 'utf8');
const a = src.indexOf('/* RU_BEGIN */'), b = src.indexOf('/* RU_END */');
const P = new Function(src.slice(a, b) + '\nreturn {RUP,RUREG,ruPlan,ruDemandSurge,ruPolicyAlert,ruResonance,ruRegionWx,ruWxVerdict,ruLastWeekdayOfMarch};')();
const readJson = (p, d) => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (_) { return d; } };

function loadSeries(dataDir) {
  const S = readJson(path.join(root, 'cockpit', 'ru_hist.json'), null); if (!S) return null;
  S.m = S.m || []; const j = readJson(path.join(dataDir, 'ru_live.json'), null);
  if (j && j.d && j.d.length) {   // 与页面 mergeLive 同一公式
    const n = S.d.length, f = S.c[n - 1] / S.r[n - 1];
    for (let i = 0; i < j.d.length; i++) { if (j.d[i] <= S.d[S.d.length - 1]) continue; S.d.push(j.d[i]); S.o.push(j.o[i] * f); S.h.push(j.h[i] * f); S.l.push(j.l[i] * f); S.c.push(j.c[i] * f); S.r.push(j.c[i]); S.m.push(j.m && j.m[i] ? String(j.m[i]).replace(/^RU/, '') : S.m[S.m.length - 1]); }
  }
  return S;
}
async function jget(u) { const r = await fetch(u); if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }
async function fetchWx(today) {
  const y0 = +today.slice(0, 4), years = [y0 - 5, y0 - 4, y0 - 3, y0 - 2, y0 - 1];
  return Promise.all(P.RUREG.map(async g => {
    try {
      const base = 'latitude=' + g.lat + '&longitude=' + g.lon + '&timezone=' + encodeURIComponent(g.tz);
      const [fc, hs] = await Promise.all([
        jget('https://api.open-meteo.com/v1/forecast?' + base + '&daily=precipitation_sum,temperature_2m_max&past_days=35&forecast_days=7'),
        jget('https://archive-api.open-meteo.com/v1/archive?' + base + '&start_date=' + years[0] + '-01-01&end_date=' + years[4] + '-12-31&daily=precipitation_sum,temperature_2m_max')]);
      const r = P.ruRegionWx({ d: fc.daily.time, p: fc.daily.precipitation_sum, tx: fc.daily.temperature_2m_max }, { d: hs.daily.time, p: hs.daily.precipitation_sum, tx: hs.daily.temperature_2m_max }, today, years, g.kind);
      return Object.assign({ k: g.k, n: g.n, core: g.core, kind: g.kind, pri: g.pri }, r);
    } catch (e) { return { k: g.k, n: g.n, core: g.core, kind: g.kind, pri: g.pri, err: String(e && e.message || e) }; }
  }));
}
function bjToday(nowMs) { return new Date((nowMs != null ? nowMs : Date.now()) + 8 * 3600e3).toISOString().slice(0, 10); }

/* 纯计算：wx 可注入（测试用）。返回 {priceDate,gate,side,plan,events} */
function compute(S, today, wx, ind, pol) {
  const y = today.slice(0, 4), ev = [], mmdd = today.slice(5), L = S.d[S.d.length - 1];
  const pl = P.ruPlan(S, today, wx, null, { surge: P.ruDemandSurge(ind, today), policy: P.ruPolicyAlert(pol, today, null), reson: P.ruResonance(ind, today) }), yE = P.ruLastWeekdayOfMarch(+y);
  const inMar = +today.slice(5, 7) === 3 && today <= yE;
  if (pl.pre) ev.push({ type: 'ru', key: 'ru|' + y + '|pre', title: '【橡胶】3月季节窗口 ' + pl.daysTo + ' 天后开始（准备期）', body: '橡胶只在3月做空：3/1起，收盘站上5日线(反弹)且主产区天气正常，才在次日挂限价空单(≥收盘+0.3%)。\n现在不动，先看页面「橡胶」里的天气和开割进度；开割延迟/需求走强就手动录入，页面会自动暂缓。' });
  if (inMar && L >= y + '-03-01') ev.push({ type: 'ru', key: 'ru|' + y + '|open', title: '【橡胶】3月窗口开始', body: '规则：收盘站上MA5才出信号；5%止损；' + yE + ' 收盘无条件平仓；止损后今年不再开。\n最新价格日 ' + L + '。' });
  if (pl.st === 'go' && pl.order) {
    const o = pl.order;
    ev.push({ type: 'ru', key: 'ru|' + y + '|go|' + L, title: '【橡胶】做空信号：明日挂限价 ≥' + o.lim + '（' + (o.contract || '主力') + '）', body: '价格日 ' + L + ' 收盘站上MA5（反弹），' + (wx && wx.text ? wx.text : '天气未知') + '。\n挂单：次日限价卖出 ≥ ' + o.lim + '（收盘+0.3%，取整到5元）；没成交就作废，不追。\n成交后止损 ' + o.stop + '（5%），参考目标 ' + o.ref + '（历史平均跌幅5.8%，不设止盈）。\n到 ' + yE + ' 收盘平仓。手数用页面里的仓位计算。\n⚠开割进度/需求是手动项：若已知开割延迟或下游需求超预期，请先在页面录入再决定。' });
  }
  if (pl.st === 'blocked') {
    const reb = pl.reb;
    if (reb) ev.push({ type: 'ru', key: 'ru|' + y + '|blk|' + L, title: '【橡胶】反弹信号被拦下：暂缓做空', body: pl.bad.join('；') + '\n价格已站上MA5，但过滤条件不满足，不开仓。' });
  }
  if (inMar && wx && wx.level === 'block') ev.push({ type: 'ru', key: 'ru|' + y + '|wxb|' + today, title: '【橡胶】主产区天气异常：持有空单者考虑离场', body: wx.text + '\n你的规则：开割后天气持续异常，空头逻辑被破坏。（如果你没有橡胶空单，忽略本条）' });
  if (today === yE) ev.push({ type: 'ru', key: 'ru|' + y + '|exit', title: '【橡胶】今天是3月最后交易日：持有空单收盘前平仓', body: '季节窗口结束，不留到4月（开割后供应利空已兑现，历史上没有优势）。如果换过月，别忘了平的是你实际持有的那个合约。' });
  if (mmdd > '03-31' && mmdd <= '04-03') ev.push({ type: 'ru', key: 'ru|' + y + '|late', title: '【橡胶】3月已过：如还有橡胶空单请立即平仓', body: '规则是3月最后一个交易日平仓，不留到4月。' });
  return { priceDate: L, gate: { ok: true }, side: 0, plan: { st: pl.st, head: pl.head }, events: ev };
}
async function main(argv) {
  const o = {}; for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) o[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  const S = loadSeries(o.data || 'data'); if (!S) { console.error('[橡胶提醒] 找不到快照'); return; }
  const today = o.today || bjToday(); let wx = null;
  if (!o.nowx && +today.slice(5, 7) === 3) { try { wx = P.ruWxVerdict(await fetchWx(today)); } catch (_) { } }
  const out = compute(S, today, wx, readJson(path.join(o.data || 'data', 'ru_ind_auto.json'), {}), readJson(path.join(o.data || 'data', 'ru_policy.json'), {})), txt = JSON.stringify(out, null, 1);
  if (o.out) fs.writeFileSync(o.out, txt); else console.log(txt);
  console.error(`[橡胶提醒] ${today} · 价格日 ${out.priceDate} · ${out.plan.st} · 事件 ${out.events.length}`);
}
if (require.main === module) main(process.argv.slice(2));
/* 小组件用：只要 ruPlan 的结果（可带持仓 pos={px,contract}）。天气拿不到就当未知，不拦单（天气拦单以驾驶舱页面为准） */
function plan(S, today, pos, ind, pol) {
  const wx = null;
  return P.ruPlan(S, today, wx, pos || null, { surge: P.ruDemandSurge(ind || {}, today), policy: P.ruPolicyAlert(pol || {}, today, pos ? pos.d : null), reson: P.ruResonance(ind || {}, today) });
}
module.exports = { compute, loadSeries, plan };
