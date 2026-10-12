(function () {
'use strict';
const L = window.CockpitLogic, D = window.__DATA__, K = L.K;
const $ = (s, r) => (r || document).querySelector(s), $$ = (s, r) => [...(r || document).querySelectorAll(s)];
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const MINUS = '\u2212';
const sg = (n, d) => n == null || isNaN(n) ? '—' : (n > 0 ? '+' : n < 0 ? MINUS : '') + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: d == null ? 0 : d });
const ab = n => n == null || isNaN(n) ? '—' : Math.abs(Math.round(n)).toLocaleString('en-US');
const pc = (r, d) => r == null ? '—' : (r > 0 ? '+' : r < 0 ? MINUS : '') + Math.abs(r * 100).toFixed(d == null ? 1 : d) + '%';
const BJ = ms => new Date(ms + 8 * 3600e3);
const mmdd = ms => { const d = BJ(ms); return String(d.getUTCMonth() + 1).padStart(2, '0') + '-' + String(d.getUTCDate()).padStart(2, '0'); };
const hhmm = ms => { const d = BJ(ms); return String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0'); };
const lampSvg = lv => `<svg class="lamp ${lv}" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/>${lv === 'warn' ? '<path d="M8 4.6v4M8 10.6v.9"/>' : ''}</svg>`;
const LW = { ok: '正常', note: '留意', warn: '警示', na: '无数据' };
const CM = { sep: { name: '9月合约', win: '4–7月' }, may: { name: '5月合约', win: '12–3月' }, jan: { name: '1月合约', win: '8–11月' } };
const autoKey = () => { const m = BJ(D.snapshotMs).getUTCMonth() + 1; for (const k of ['sep', 'may', 'jan']) if (D.ctx[k].recommendedMonths.includes(m)) return k; return 'sep'; };
const S = { mode: 'trade', view: 'px', seaKind: 'spot', key: autoKey(), auto: true, span: 'mid', range: 80, ex: false, themePref: 'auto' };
const C = () => D.contracts[S.key];
const closed = () => D.closure && D.closure.state === 'in';

/* ---------- 数据：最新的真实资金面(CFTC来自156周序列；高盛等来自龙虎榜) ---------- */
const SER = D.series;
function capital() {
  const cf = L.cftcStats(SER.cftc.pts), m = D.capital && D.capital.members, gs = m && m['高盛期货'];
  const gsNet = gs && gs.net != null ? gs.net : null, gsChg = gs && gs.change != null ? gs.change : null;
  return { cf, gs, gsNet, gsChg, verdict: (D.capital && D.capital.verdict) || null, state: L.capitalState(gsNet, gsChg, cf ? cf.percentile : null) };
}
/* ---------- v101.19：价格位置(近260日分位，新合约用后端按比例换算补齐) / 彩带 / 铁底铁顶 / 成本锚 ---------- */
const RB = { low: '#0E9AA7', mid: '#C99A1C', high: '#E8710A', unknown: 'var(--ink3)' };
function posExt() { const e = D.pricePosition && D.pricePosition[S.key], bars = C().kline || []; return e && Array.isArray(e.closes) && e.symbol === C().symbol && e.closes.length >= bars.length ? e : null; }
function bandOf(win) { if (win.length < 200) return 'unknown'; const last = win[win.length - 1], p = win.filter(c => c <= last).length / win.length * 100; return p <= 20 ? 'low' : p >= 80 ? 'high' : 'mid'; }
function histCloses(uptoDate) { const h = D.hist; if (!h) return null; let n = h.d.length; if (uptoDate) { const k = h.d.indexOf(uptoDate); if (k < 0) return null; n = k + 1; } return h.c.slice(0, n); }
function posBand() {
  const bars = C().kline || [], hc = histCloses(), cs = (hc || bars.map(b => b.c)).slice(-260);
  if (cs.length < 200) return { band: 'unknown', n: cs.length, ext: 0 };
  const last = cs[cs.length - 1], pct = Math.round(cs.filter(c => c <= last).length / cs.length * 1000) / 10, sorted = cs.slice().sort((a, b) => a - b), n = cs.length;
  const ten = (hc || []).slice(-2520), ts = ten.slice().sort((a, b) => a - b);
  return { band: pct <= 20 ? 'low' : pct >= 80 ? 'high' : 'mid', pct, n, ext: 0, p20: sorted[Math.ceil(.2 * n) - 1], p80: sorted[Math.ceil(.8 * n) - 1], t80: ts.length >= 1000 ? ts[Math.ceil(.8 * ts.length) - 1] : null };
}
function ribbonBandsProto() {
  const bars = C().kline || [];
  return bars.map(b => { const cs = histCloses(b.d); return cs ? bandOf(cs.slice(-260)) : 'unknown'; });
}
const BANDNAME = { low: '低位带（≤20%分位）', mid: '中间带', high: '高位带（≥80%分位）' };
function posBlockHtml() {
  const p = posBand();
  if (p.band === 'unknown') return `<div class="rng"><div class="l1"><span>近260日价格位置</span><span><b>数据不足</b>（只有 ${p.n} 根，需 ≥200）</span></div></div>`;
  const note = p.band === 'low' ? '历史检验：低位带之后表现略好于基准，温和支持，样本有限。' : p.band === 'high' ? '历史检验：高位带没有“之后会跌”的证据，只说明价格贵。' : '';
  return `<div class="rng"><div class="l1"><span>近${p.n}日价格位置（主力连续价）</span><span><b>${p.pct}%分位</b>　${BANDNAME[p.band]}</span></div><div class="rtrack"><i style="left:${p.pct}%"></i></div><div class="l2"><span>260天铁底(20%) ${ab(p.p20)}</span><span>260天铁顶(80%) ${ab(p.p80)}</span></div>${note ? `<div class="l2" style="margin-top:2px"><span>${note}</span></div>` : ''}</div>`;
}
function costBlockHtml() {
  const ca = D.costAnchor; if (!ca || !ca.available) return `<div class="rng"><div class="l1"><span>成本锚</span><span class="dim">${esc((ca && ca.reason) || '暂无数据')}</span></div></div>`;
  const c = ca.contracts && ca.contracts[S.key]; if (!c) return `<div class="rng"><div class="l1"><span>成本锚</span><span class="dim">这个合约暂无数据</span></div></div>`;
  const row = o => { const r = c[o], lab = o === 'brazil' ? '巴西豆' : '美豆', tag = c.primary === o ? '（主要）' : c.primary ? '（参考）' : '';
    if (!r || !r.available) return `<div class="l2"><span>${lab}${tag}</span><span>${esc((r && r.reason) || '—')}</span></div>`;
    const w = r.position === 'below' ? '低于' : r.position === 'above' ? '高于' : '处在';
    return `<div class="l2"><span>${lab}${tag} 理论成本 ${ab(r.mealCostLow)}~${ab(r.mealCostHigh)}（中值 ${ab(r.mealCost)}）</span><span>盘面${w}区间，差 ${sg(r.gap)}（${sg(r.gapPct, 1)}%）</span></div>`; };
  return `<div class="rng" title="升贴水无历史、无法回测；增值税9%、港杂100元/吨为经验值，未核实。成本参照，不是买卖信号。"><div class="l1"><span>成本锚（CBOT ${esc(c.cbotSymbol)}${c.zsExact ? '' : ' ⚠️退回近月'}）</span><span class="dim">升贴水未核实</span></div>${row('us')}${row('brazil')}</div>`;
}

/* ======================= v101.19c：驾驶舱新增视图（结论优先，说明收进“?”） ======================= */
const VIEWS = [['px', '价格持仓'], ['pos', '价格位置'], ['sea', '同期规律'], ['cost', '成本锚']];
function viewTabs() { return `<div class="seg vtabs" role="group" aria-label="切换视图">${VIEWS.map(([k, n]) => `<button data-view="${k}" aria-pressed="${(S.view || 'px') === k}">${n}</button>`).join('')}</div>`; }
function viewHdr(title, about) { return `<div class="ch-h"><span class="t">${title}</span><button class="q" data-about="${about}" aria-label="这页怎么看">?</button></div>${viewTabs()}`; }
const fmtD = n => Math.round(n).toLocaleString('en-US');
const quant = (sorted, q) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(q * sorted.length) - 1))];
function histRows() { const h = D.hist; return h ? h.d.map((d, i) => ({ d, c: h.c[i] })) : []; }
function beOf(key) { const cr = D.crush && D.crush[key]; return cr && cr.available && cr.beanPrice != null ? (cr.beanPrice + 150 - cr.oilPrice * .185) / .785 : null; }
const rngBar = (label, pct, tag, lo, hi) => `<div class="rng"><div class="l1"><span>${label}</span><span><b>${pct.toFixed(1)}%分位</b>　${tag}</span></div><div class="rtrack"><i style="left:${pct}%"></i></div><div class="l2"><span>${lo}</span><span>${hi}</span></div></div>`;

/* ---- 价格位置 ---- */
function viewPos() {
  const rows = histRows(); if (rows.length < 400) return viewHdr('价格位置', 'pos') + `<div class="dim2" style="padding:20px 0">缺少历史价格数据。</div>`;
  const box = $('#chart'), W = Math.max(300, Math.min(760, (box.clientWidth || 600) - 40)), H = Math.round(W * .5), ml = 4, mr = 84, mt = 8, mb = 20, N = Math.min(rows.length - 259, 756);
  const start = rows.length - N, cs = rows.map(r => r.c);
  const band = i => { const win = cs.slice(i - 259, i + 1), s = win.slice().sort((a, b) => a - b); return { p20: quant(s, .2), p80: quant(s, .8), pct: win.filter(v => v <= cs[i]).length / win.length * 100 }; };
  const B = []; for (let i = start; i < rows.length; i++) B.push(band(i));
  const lo = Math.min(...cs.slice(start), ...B.map(b => b.p20)) - 40, hi = Math.max(...cs.slice(start), ...B.map(b => b.p80)) + 40;
  const x = k => ml + k / (N - 1) * (W - ml - mr), y = v => mt + (hi - v) / (hi - lo) * (H - mt - mb);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" style="display:block;max-width:100%" role="img" aria-label="近三年价格与铁底铁顶带">`;
  const up = B.map((b, k) => `${x(k)},${y(b.p80)}`).join(' '), dn = B.map((b, k) => `${x(N - 1 - k)},${y(B[N - 1 - k].p20)}`).join(' ');
  s += `<polygon points="${up} ${dn}" fill="var(--focusS)"/><polyline points="${up}" fill="none" stroke="${RB.high}" stroke-width="1" stroke-dasharray="3 3"/><polyline points="${B.map((b, k) => `${x(k)},${y(b.p20)}`).join(' ')}" fill="none" stroke="${RB.low}" stroke-width="1" stroke-dasharray="3 3"/>`;
  for (let k = 1; k < N; k++) { const col = B[k].pct <= 20 ? RB.low : B[k].pct >= 80 ? RB.high : 'var(--ink2)'; s += `<line x1="${x(k - 1)}" y1="${y(cs[start + k - 1])}" x2="${x(k)}" y2="${y(cs[start + k])}" stroke="${col}" stroke-width="1.5"/>`; }
  let lastY = ''; for (let k = 0; k < N; k++) { const yr = rows[start + k].d.slice(0, 4); if (yr !== lastY) { lastY = yr; s += `<text x="${x(k)}" y="${H - 5}" class="lv" style="fill:var(--ink3);font-size:11px">${yr}</text>`; } }
  const L1 = B[N - 1], last = cs[cs.length - 1];
  s += `<text class="lv" x="${W - mr + 4}" y="${y(L1.p80) + 4}" style="fill:${RB.high};font-size:11px">260天铁顶 ${fmtD(L1.p80)}</text><text class="lv" x="${W - mr + 4}" y="${y(L1.p20) + 4}" style="fill:${RB.low};font-size:11px">260天铁底 ${fmtD(L1.p20)}</text><circle cx="${x(N - 1)}" cy="${y(last)}" r="3.5" fill="var(--ink)"/><text class="lv" x="${W - mr + 4}" y="${y(last) + 4}" style="fill:var(--ink);font-weight:600;font-size:12px">${fmtD(last)}</text></svg>`;
  const ten = cs.slice(-2520), pct10 = ten.filter(v => v <= last).length / ten.length * 100, cur = band(rows.length - 1);
  const tag = p => p >= 80 ? '高位带' : p <= 20 ? '低位带' : '中间带';
  const word = cur.pct >= 80 ? `高于260天铁顶 ${fmtD(cur.p80)}，近一年最贵的 20% 里` : cur.pct <= 20 ? `低于260天铁底 ${fmtD(cur.p20)}，近一年最便宜的 20% 里` : `在260天铁底 ${fmtD(cur.p20)} 和铁顶 ${fmtD(cur.p80)} 之间`;
  return viewHdr('价格位置 · 主力连续价', 'pos') + `<div class="hl">现价 <b>${fmtD(last)}</b>：${word}</div>${s}
    ${rngBar('近260日', cur.pct, tag(cur.pct), `260天铁底 ${fmtD(cur.p20)}`, `260天铁顶 ${fmtD(cur.p80)}`)}
    ${rngBar(`近${Math.round(ten.length / 252)}年`, pct10, tag(pct10), `10年铁底 ${fmtD(quant(ten.slice().sort((a, b) => a - b), .2))}`, `10年铁顶 ${fmtD(quant(ten.slice().sort((a, b) => a - b), .8))}`)}`;
}

/* ---- 同期规律：结论 + 12个月上涨概率 ---- */
function trendBlock() {
  const r = D.sea && D.sea.recent; if (!r) return '';
  const col = v => v > 0 ? 'var(--bull)' : v < 0 ? 'var(--bear)' : 'var(--ink2)';
  const pc = v => v == null ? '<td class="n dim">—</td>' : `<td class="n" style="color:${col(v)}">${v > 0 ? '+' : ''}${v}%</td>`;
  const yc = v => v == null ? '<td class="n dim">—</td>' : `<td class="n" style="color:${col(v)}">${v > 0 ? '+' : ''}${Math.round(v)}</td>`;
  const b = r.basis, last = D.sea.meta && D.sea.meta.lastDate, am = D.sea.meta && D.sea.meta.autoMerge;
  return `<table class="tb3x" style="margin:10px 0 4px"><thead><tr><th>近期趋势</th><th>最新</th><th>1周</th><th>1月</th><th>3月</th></tr></thead><tbody>
    <tr><td>现货价</td><td class="n">${fmtD(r.spot.last)}</td>${pc(r.spot.w1)}${pc(r.spot.m1)}${pc(r.spot.q1)}</tr>
    <tr><td>期货价</td><td class="n">${r.futures.last == null ? '—' : fmtD(r.futures.last)}</td>${pc(r.futures.w1)}${pc(r.futures.m1)}${pc(r.futures.q1)}</tr>
    <tr><td>基差(现货−期货)</td><td class="n">${b.last == null ? '—' : (b.last > 0 ? '+' : '') + Math.round(b.last)}</td>${yc(b.w1)}${yc(b.m1)}${yc(b.q1)}</tr></tbody></table>
    <div class="mleg"><span>基差处在近一年 ${b.pct == null ? '—' : b.pct + '%'} 分位（越高=现货越强于期货）；基差栏是元/吨的变化</span><span>数据到 ${last || '—'}${am && am.autoRows ? '，含自动累积' : '，自动累积尚未开始'}</span></div>`;
}
function viewSea() {
  const sea = D.sea, m = BJ(D.snapshotMs).getUTCMonth() + 1, kind = S.seaKind || 'spot', K = kind === 'spot' ? 'spot' : 'futures', G = kind === 'spot' ? 'gradeSpot' : 'gradeFutures';
  const tog = `<div class="ch-r" style="justify-content:flex-start"><div class="seg" role="group" aria-label="现货或期货">${[['spot', '现货价格'], ['fut', '期货价格']].map(([k, n]) => `<button data-sea="${k}" aria-pressed="${kind === k}">${n}</button>`).join('')}</div></div>`;
  if (!sea || !sea.months) return viewHdr('同期规律', 'sea') + `<div class="dim2" style="padding:20px 0">缺少季节性数据。</div>`;
  const ms = sea.months.find(z => z.month === m), f = ms && ms[K], g = ms && ms[G], ex = kind === 'fut' && ms && ms.excursion; if (!f) return viewHdr('同期规律', 'sea') + tog + `<div class="dim2">暂无数据</div>`;
  const sgn = v => (v > 0 ? '+' : '') + v + '%', upN = Math.round(f.upPct / 100 * f.n), dirTxt = f.mean >= 0 ? '偏涨' : '偏跌';
  const verdict = g.label === '不稳' ? '方向不稳定，没有可用的季节规律' : g.label === '一般' ? '前后两半同向，但胜率或显著性不够强，只能参考' : `历史上较稳定${dirTxt}`;
  const op = l => l === '不稳' ? .42 : l === '一般' ? .7 : 1;
  const cols = sea.months.map(z => { const zz = z[K], u = zz.upPct, now = z.month === m, col = u > 50 ? 'var(--bull)' : u < 50 ? 'var(--bear)' : 'var(--ink3)';
    return `<div class="mc${now ? ' now' : ''}"><span class="mv">${Math.round(u)}</span><div class="mb"><i style="height:${u}%;background:${col};opacity:${op(z[G].label)}"></i></div><span class="mm">${z.month}月</span><span class="mr" style="color:${zz.mean >= 0 ? 'var(--bull)' : 'var(--bear)'}">${zz.mean > 0.049 ? "+" : ""}${(Math.abs(zz.mean) < .05 ? 0 : zz.mean).toFixed(1)}</span></div>`; }).join('');
  const stable = sea.months.filter(z => z[G].label === '较稳').map(z => `${z.month}月${z[K].mean >= 0 ? '涨' : '跌'}`);
  return viewHdr('同期规律 · 各月上涨概率', 'sea') + tog + `<div class="hl"><b>${m}月</b>${kind === 'spot' ? '现货' : '期货'}：近 ${f.n} 年 <b>${upN} 年上涨（${Math.round(f.upPct)}%）</b>，平均 ${sgn(f.mean)}，中位 ${sgn(f.median)}<br><span style="color:${g.label === '不稳' ? 'var(--ink3)' : 'var(--amber)'}">稳定性：${esc(g.label)} → ${verdict}</span>${stable.length ? `<br><span style="color:var(--ink2);font-size:13px">较稳的月份：${stable.join('、')}</span>` : ''}</div>
    <div class="mbars">${cols}<div class="m50"></div></div>
    <div class="mleg"><span>柱子=该月上涨年份占比(%)，虚线=50%</span><span>下方数字=平均涨跌(%)；越淡=越不稳</span></div>
    ${trendBlock()}
    ${ex ? `<div class="rng"><div class="l1"><span>${m}月内最大波动（平均）</span><span><b class="bull">冲高 +${ex.upMean.toFixed(1)}%</b>　<b class="bear">回撤 ${ex.dnMean.toFixed(1)}%</b></span></div></div>` : ''}`;
}

/* ---- 成本锚：结论 + 一把标尺 ---- */
function viewCost() {
  const key = S.key, cr = D.crush && D.crush[key], ca = D.costAnchor && D.costAnchor.available && D.costAnchor.contracts && D.costAnchor.contracts[key];
  if (!cr || !cr.available) return viewHdr('成本锚', 'cost') + `<div class="dim2" style="padding:20px 0">这个合约暂无榨利数据。</div>`;
  const be = beOf(key), meal = cr.mealPrice, gap = meal - be, gp = gap / be * 100;
  const verdict = Math.abs(gap) < 40 ? '压榨不赚不亏，成本没给方向' : gap > 0 ? '压榨有利润，油厂倾向多开机，上方有压力' : '压榨亏损，油厂倾向减产，下方有支撑';
  const bands = []; if (ca) ['brazil', 'us'].forEach(o => { const r = ca[o]; if (r && r.available) bands.push({ name: (o === 'brazil' ? '巴西豆' : '美豆') + '进口成本', lo: r.mealCostLow, hi: r.mealCostHigh, mid: r.mealCost, main: ca.primary === o }); });
  const all = [meal, be].concat(bands.flatMap(b => [b.lo, b.hi])), mn = Math.min(...all) - 80, mx = Math.max(...all) + 80, p = v => ((v - mn) / (mx - mn) * 100).toFixed(2);
  const row = (name, val, inner) => `<div class="cr"><div class="cl2"><span>${name}</span><b>${val}</b></div><div class="ct">${inner}</div></div>`;
  let rowsH = row('盘面豆粕', fmtD(meal), `<i class="dot" style="left:${p(meal)}%;background:var(--ink)"></i>`) + row('盈亏平衡价', fmtD(be), `<i class="dot" style="left:${p(be)}%;background:${BEC}"></i>`);
  bands.forEach(b => { const rich = b.lo > meal; rowsH += row(b.name + (b.main ? '（主要）' : ''), `${fmtD(b.lo)}~${fmtD(b.hi)}${rich ? '　<span class="dim">比盘面贵</span>' : ''}`, `<i class="bandx" style="left:${p(b.lo)}%;width:${Math.max(1, p(b.hi) - p(b.lo))}%;background:${rich ? 'var(--ink3)' : 'var(--amber)'}"></i>`); });
  const tbl = ['sep', 'may', 'jan'].map(k => { const c = D.crush && D.crush[k]; if (!c || !c.available) return ''; const b = beOf(k), g = c.mealPrice - b; return `<tr${k === key ? ' style="font-weight:600"' : ''}><td>${CM[k].name}</td><td class="n">${fmtD(c.mealPrice)}</td><td class="n">${fmtD(b)}</td><td class="n" style="color:${g > 0 ? 'var(--bull)' : 'var(--bear)'}">${g > 0 ? '+' : '−'}${fmtD(Math.abs(g))}</td></tr>`; }).join('');
  return viewHdr(`${esc(CM[key].name)} · 豆粕成本锚（元/吨）`, 'cost') + `<div class="hl">盘面 <b>${fmtD(meal)}</b>，盈亏平衡价 <b>${fmtD(be)}</b>：${gap >= 0 ? '高' : '低'} ${fmtD(Math.abs(gap))}（${gp > 0 ? '+' : ''}${gp.toFixed(1)}%）<br><span style="color:var(--ink2)">${verdict}</span></div>
    <div class="ruler"><i class="vline" style="left:${p(meal)}%"></i>${rowsH}</div>
    <table class="tb3x" style="margin-top:10px"><thead><tr><th>合约</th><th>盘面</th><th>平衡价</th><th>差</th></tr></thead><tbody>${tbl}</tbody></table>`;
}

/* ---- 交易计划：规则 + 信号 + 仓位计算器 + 回测摘要（v101.25） ---- */
/* PLAN_BEGIN —— 交易计划纯函数（v101.25）：和回测同一口径，不碰 DOM，便于单测 */
const TPLAN = {
  TIERS: [[5000000, .6], [15000000, .4], [50000000, .25], [Infinity, .15]],   // [权益上限(元), 占用]：<500万 60%；<1500万 40%；<5000万 25%；其余 15%
  STOP: 4, TRAIL: 4, ACT: 8,          // 止损4%；移动止盈：持仓期间最高浮盈≥8% 之后，从持仓最高(低)价回落≥4% 平仓（回测验证过的等价写法）
  LO: 50, DELEV: -20000,              // 低位：近260日分位≤50；任一外资席位5日变化≤-2万手=去杠杆（看单个席位，不看合计：席位之间可能互相对冲）
  BT_MARGIN: .10, TON: 10             // 回测保证金10%；每手10吨
};
function planTier(E) { for (const [lim, u] of TPLAN.TIERS) if (E < lim) return u; return TPLAN.TIERS[TPLAN.TIERS.length - 1][1]; }
function planPct(cs, w) { w = w || 260; const win = cs.slice(-w); if (win.length < 200) return null; const last = cs[cs.length - 1]; return win.filter(v => v <= last).length / win.length * 100; }
function planMA(cs, n) { if (cs.length < n) return null; let s = 0; for (let i = cs.length - n; i < cs.length; i++) s += cs[i]; return s / n; }
function planConfirm(cs) { const n = cs.length; if (n < 11) return false; return cs[n - 1] > cs[n - 6] && cs[n - 1] > Math.min(...cs.slice(n - 11, n - 1)) * 1.01; }
/* 外资5日：摩根大通/高盛/瑞银 各自的 change5.change。v101.33 起信号看「最弱席位」(min)，不再看三家之和(sum，只作参考显示)：
   席位之间可能对冲(如摩根+8,143 对高盛−15,392)，合计会把单个席位的撤退抵消掉。缺的席位不参与(回测里缺数据日按0，等价于不触发) */
function planForeign(members) {
  const used = [], missing = [], approx = [], parts = []; let sum = 0, lastD = null;
  Object.keys(members || {}).forEach(k => { const m = members[k]; if (!m || !m.foreign) return;
    const c5 = m.history && m.history.change5; if (c5 && typeof c5.change === 'number') { sum += c5.change; used.push(k); parts.push({ k, v: c5.change, approx: !!c5.approx, bridged: !!c5.bridged, basis: c5.basis || '' }); if (c5.approx) approx.push(k); if (c5.to && (!lastD || c5.to > lastD)) lastD = c5.to; } else missing.push(k); });
  const w = parts.length ? parts.reduce((a, q) => q.v < a.v ? q : a) : null;
  return { sum, used, missing, approx, parts, lastD, min: w ? w.v : 0, minK: w ? w.k : '' };
}
function planSignals(cs, fsum) {
  const n = cs.length, last = cs[n - 1], pct = planPct(cs), ma20 = planMA(cs, 20), ma60 = planMA(cs, 60), conf = planConfirm(cs), delev = fsum <= TPLAN.DELEV;
  const lowOK = pct != null && pct <= TPLAN.LO;
  const trendDn = ma20 != null && ma60 != null && last < ma20 && ma20 < ma60 && n >= 6 && last < cs[n - 6];
  return { pct, ma20, ma60, confirm: conf, delev, lowOK, trendDn, longOK: lowOK && conf && !delev, shortOK: delev && trendDn };
}
/* mode='real'：手数按你填的实际保证金算（占用=你说的资金占比）；mode='bt'：按回测的10%保证金/名义杠杆算（保证金高于10%时实际占用会更高）*/
function planSize(o) {
  const E = o.equity, m = o.margin, px = o.price, side = o.side >= 0 ? 1 : -1, u = planTier(E), den = o.mode === 'bt' ? TPLAN.BT_MARGIN : m;
  const lots = Math.floor(E * u / (TPLAN.TON * px * den));
  if (!(lots >= 1)) return { u, lots: 0 };
  const L = lots * TPLAN.TON, notional = L * px, margin = notional * m;
  const stopPx = px * (1 - side * TPLAN.STOP / 100), lossStop = notional * TPLAN.STOP / 100, actPx = px * (1 + side * TPLAN.ACT / 100);
  const liqPx = side > 0 ? (L * px - E) / (L * (1 - m)) : (E + L * px) / (L * (1 + m));       // 风险度(保证金/权益)=100% 的价格
  const eqAtStop = E - lossStop, riskAtStop = margin * (stopPx / px) / eqAtStop;
  return { u, lots, notional, margin, usage: margin / E, leverage: notional / E, stopPx, lossStop, lossPct: lossStop / E, actPx, liqPx,
           liqGapPct: Math.abs(liqPx - stopPx) / px * 100, riskAtStop, riskNow: margin / E };
}
function planManage(o) {   // o: {side, entry, peak, last, ma20, fsum=最弱席位5日变化(多单离场用), fall=三家合计5日变化(空单离场用；不传则用fsum)}
  const side = o.side >= 0 ? 1 : -1, r = side * (o.last / o.entry - 1) * 100;
  const stop = r <= -TPLAN.STOP;
  const peakR = side * (o.peak / o.entry - 1) * 100;      // 持仓期间出现过的最高浮盈
  const trail = peakR >= TPLAN.ACT && (side > 0 ? o.last <= o.peak * (1 - TPLAN.TRAIL / 100) : o.last >= o.peak * (1 + TPLAN.TRAIL / 100));
  const delevOut = side > 0 && o.fsum <= TPLAN.DELEV;
  const shortOut = side < 0 && ((o.fall != null ? o.fall : o.fsum) >= 0 || (o.ma20 != null && o.last > o.ma20));
  const action = stop ? '止损' : trail ? '移动止盈' : delevOut ? '外资去杠杆·平多' : shortOut ? '空单离场' : '持有';
  return { r, peakR, stop, trail, delevOut, shortOut, action };
}
/* ---- 账户与持仓（v101.26）：权益、手续费、持仓最高/最低价全部由交易记录和价格数据算出 ---- */
function planWhy(sg) {
  if (sg.longOK) return '低位 + 反弹确认 + 外资没有去杠杆';
  if (sg.shortOK) return '外资去杠杆 + 价格趋势向下';
  if (sg.delev) return '外资在去杠杆，但价格趋势还没向下：不做多，也不做空';
  if (sg.pct == null) return '历史价格不足，暂时算不出价格分位';
  if (!sg.lowOK) return '价格分位 ' + sg.pct.toFixed(0) + '%，不在低位（需 ≤' + TPLAN.LO + '%）';
  return '价格在低位，但还没出现反弹确认';
}
/* 信号数据闸门：外资5日数据一个席位都没有、或价格数据太久没更新时，信号不可信（外资缺数据在回测里按0算=去杠杆过滤失效） */
function planGate(used, lastD, today, opt) {
  opt = opt || {};
  const reasons = [], warn = [], gapOf = d => Math.round((Date.parse(today) - Date.parse(d)) / 86400000);
  if (!used || !used.length) reasons.push('外资席位5日数据缺失（去杠杆过滤失效）');
  else if (opt.fD) { const g = gapOf(opt.fD); if (g > 7) reasons.push('外资席位数据已 ' + g + ' 天没更新（最新 ' + opt.fD + '）'); else if (g > 4) warn.push('外资席位数据最新 ' + opt.fD); }
  if (!lastD) reasons.push('没有价格数据');
  else { const gap = gapOf(lastD); if (gap > 7) reasons.push('价格数据已 ' + gap + ' 天没更新（最新 ' + lastD + '）'); else if (gap > 4) warn.push('价格数据最新 ' + lastD); }
  if (opt.adj === false) reasons.push('缺换月调整价文件 data/main_adj.json');
  const miss = opt.missing || [], ap = opt.approx || [];
  if (ap.length) warn.push(ap.join('、') + '为估算值（只进了一边前20，混有第20名的变动）');
  const level = reasons.length ? 'bad' : (miss.length || warn.length) ? 'part' : 'ok';
  return { ok: !reasons.length, level, reasons, warn, missing: miss, approx: ap };
}
/* 信号旁的「数据状态」一句话：让人一眼看出数据够不够 */
function planPartsText(parts) {   // 「高盛 −15,392(多单) · 摩根大通 +8,143 = −7,249」：每个席位的5日变化都写出来
  const sgn = n => (n >= 0 ? '+' : '−') + Math.abs(Math.round(n)).toLocaleString('en-US');
  if (!parts || !parts.length) return '';
  const one = q => q.k.replace('期货', '') + ' ' + sgn(q.v) + (q.basis === 'long' ? '(多单)' : q.basis === 'short' ? '(空单)' : q.approx ? '(估)' : '');
  const w = parts.reduce((a, q) => q.v < a.v ? q : a);
  return parts.map(one).join(' · ') + (parts.length > 1 ? ' → 最弱 ' + w.k.replace('期货', '') + ' ' + sgn(w.v) : '');
}
function planDataLine(g, used, lastD, fD, adjOn, parts) {
  const pt = planPartsText(parts), seats = (pt || (used && used.length ? used.join('+') : '无')) + (fD ? '（' + fD.slice(5) + '）' : ''), px = lastD ? '价格 ' + lastD.slice(5) + (adjOn === true ? '(换月调整)' : adjOn === false ? '(原始主连)' : '') : '价格无数据';
  if (g.level === 'bad') return { cls: 'bad', t: '✗ 数据不足 · ' + g.reasons.join('；') + ' · ' + px };
  if (g.level === 'part') return { cls: 'part', t: '⚠ 数据基本够用 · ' + [g.missing.length ? g.missing.join('、') + '缺数据按0算' : '', g.warn.join('；')].filter(Boolean).join('；') + ' · 外资 ' + seats + ' · ' + px };
  return { cls: 'ok', t: '✓ 数据齐全 · 外资 ' + seats + ' · ' + px };
}
function planNum(x) { return x != null && x !== '' && isFinite(+x); }
/* 一笔交易的手续费：开仓一半 + 平仓一半（每手来回 perLot 元）；记录时填了实际金额（feeO/feeC）就用实际的 */
function planFee(t, perLot) {
  const half = t.lots * (perLot || 0) / 2;
  return (planNum(t.feeO) ? +t.feeO : half) + (t.exitD ? (planNum(t.feeC) ? +t.feeC : half) : 0);
}
function planPnl(t, px) { return (t.side >= 0 ? 1 : -1) * (px - t.entryPx) * t.lots * TPLAN.TON; }
function planOpen(trades) { for (let i = (trades || []).length - 1; i >= 0; i--) if (!trades[i].exitD) return trades[i]; return null; }
/* 持仓期间的最高/最低价：从主连日线 h={d:[],c:[]} 里取「开仓日起」的收盘价（和回测同口径）。
   开仓价和当天主连收盘差>2%（多半是非主力合约）时，按开仓日收盘折算，保证涨跌幅准确；返回 k=折算系数 */
function planHold(h, t) {
  const side = t.side >= 0 ? 1 : -1, n = h && h.d ? h.d.length : 0;
  let i0 = -1; for (let i = 0; i < n; i++) if (h.d[i] >= t.entryD) { i0 = i; break; }
  if (i0 < 0) return { peak: t.entryPx, worst: t.entryPx, last: t.entryPx, lastD: null, days: 0, k: 1, scaled: false, covered: false };
  const ratio = t.entryPx / h.c[i0], scaled = Math.abs(ratio - 1) > .02, k = scaled ? ratio : 1;
  let mx = -Infinity, mn = Infinity;
  for (let i = i0; i < n; i++) { if (h.c[i] > mx) mx = h.c[i]; if (h.c[i] < mn) mn = h.c[i]; }
  mx *= k; mn *= k;
  return { peak: side > 0 ? Math.max(mx, t.entryPx) : Math.min(mn, t.entryPx), worst: side > 0 ? Math.min(mn, t.entryPx) : Math.max(mx, t.entryPx),
           last: h.c[n - 1] * k, lastD: h.d[n - 1], days: n - 1 - i0, k, scaled, covered: true };
}
/* 权益 = 初始资金 + 出入金 + 已平仓盈亏 + 持仓浮盈亏 − 全部手续费 */
function planEquity(a, openLast) {
  const per = +a.fee || 0; let realized = 0, floating = 0, fees = 0, flows = 0;
  (a.flows || []).forEach(f => { flows += +f.amt || 0; });
  (a.trades || []).forEach(t => { fees += planFee(t, per); if (t.exitD) realized += planPnl(t, t.exitPx); else floating += planPnl(t, openLast != null ? openLast : t.entryPx); });
  return { init: +a.init || 0, flows, realized, floating, fees, equity: (+a.init || 0) + flows + realized + floating - fees };
}
function planStats(a) {
  const per = +a.fee || 0, cl = (a.trades || []).filter(t => t.exitD).map(t => { const net = planPnl(t, t.exitPx) - planFee(t, per); return { t, net, ret: (t.side >= 0 ? 1 : -1) * (t.exitPx / t.entryPx - 1) * 100 }; });
  const wins = cl.filter(x => x.net > 0).length;
  return { n: cl.length, wins, net: cl.reduce((s, x) => s + x.net, 0), rows: cl };
}
/* PLAN_END */

function planState() { let s = {}; try { s = JSON.parse(localStorage.getItem('cockpit-plan') || '{}') || {}; } catch (_) {} return s; }   // v101.25 旧版手填，只用来迁移
let ACCT = null, PMSG = null;
function acctNorm(a) {
  a.flows = Array.isArray(a.flows) ? a.flows : []; a.trades = Array.isArray(a.trades) ? a.trades : [];
  if (!(+a.init >= 0)) a.init = 500000; if (!(+a.margin > 0 && +a.margin < 100)) a.margin = 10; if (!(+a.fee >= 0)) a.fee = 23; if (a.mode !== 'bt') a.mode = 'real';
  return a;
}
function acctLoad() {
  let a = null; try { a = JSON.parse(localStorage.getItem('cockpit-acct') || 'null'); } catch (_) {}
  if (!a || typeof a !== 'object') { const o = planState(); a = { init: parseFloat(o.eq) > 0 ? parseFloat(o.eq) : 500000, margin: parseFloat(o.m) > 0 ? parseFloat(o.m) : 10, fee: 23, mode: o.mode === 'bt' ? 'bt' : 'real' }; }
  return acctNorm(a);
}
function acctGet() { if (!ACCT) ACCT = acctLoad(); return ACCT; }
function acctSave() { try { localStorage.setItem('cockpit-acct', JSON.stringify(ACCT)); return true; } catch (_) { return false; } }
function planCloses() { if (D.adj && D.adj.c.length >= 200) return D.adj.c; const hc = histCloses(); if (hc && hc.length >= 200) return hc; return (C().kline || []).map(b => b.c); }
function planLastPx() { const b = (C().kline || []).slice(-1)[0]; if (b && b.c) return b.c; const hc = histCloses(); return hc && hc.length ? hc[hc.length - 1] : 3000; }
const todayBJ = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
const sdName = s => s > 0 ? '多' : '空';
const yuan = n => (n >= 0 ? '+' : '−') + fmtD(Math.abs(n));
const pc1 = x => (x * 100).toFixed(1) + '%';
/* 一次算好：信号、持仓、自动判定、权益、建议手数。首页信号条和计划页共用，保证两处结论一致 */
function planSnap() {
  const A = acctGet(), cs = planCloses(), F = planForeign(D.capital && D.capital.members), sig = planSignals(cs, F.min);
  const px = cs.length ? cs[cs.length - 1] : planLastPx(), h = D.adj ? D.adj : D.hist && D.hist.d && D.hist.d.length ? D.hist : { d: [], c: [] };
  const pos = planOpen(A.trades); let hold = null, mg = null;
  if (pos) { hold = planHold(h, pos); mg = planManage({ side: pos.side, entry: pos.entryPx, peak: hold.peak, last: hold.last, ma20: sig.ma20 == null ? null : sig.ma20 * hold.k, fsum: F.min, fall: F.sum }); }
  const E = planEquity(A, hold ? hold.last : null), base = planEquity({ init: A.init, flows: A.flows, fee: A.fee, trades: A.trades.filter(t => t.exitD) }, null);
  const hl = h.d.length ? h.d[h.d.length - 1] : ((C().kline || []).slice(-1)[0] || {}).d || null, adjOn = !!D.adj, gate = planGate(F.used, hl, todayBJ(), { missing: F.missing, approx: F.approx, fD: F.lastD, adj: adjOn }), dl = planDataLine(gate, F.used, hl, F.lastD, adjOn, F.parts);
  const side = gate.ok ? (sig.longOK ? 1 : sig.shortOK ? -1 : 0) : 0;
  const size = !pos && side && base.equity > 0 ? planSize({ equity: base.equity, margin: A.margin / 100, price: px, side, mode: A.mode }) : null;
  return { A, cs, F, sig, px, pos, hold, mg, E, base, side, size, gate, dl };
}
/* 决策快照：开/平仓时存下当时的各面结论，以后用自己的实盘检验基本面有没有用 */
function planSnapshotNow(s) {
  const o = { d: todayBJ(), px: Math.round(s.px), pct: s.sig.pct == null ? null : Math.round(s.sig.pct), confirm: s.sig.confirm, delev: s.sig.delev, trendDn: s.sig.trendDn, fsum: Math.round(s.F.min), fsumAll: Math.round(s.F.sum), fsumK: s.F.minK, gateOk: s.gate.ok };
  try { const f = fundamentals(), c = C(); o.fund = f.dir || null; o.fundRatio = f.ratio == null ? null : +(+f.ratio).toFixed(2); o.tech = c.tech || null; o.struct = c.structure && !c.structure.thin ? c.structure.direction || null : null; const cp = capital(); o.cap = cp.verdict && cp.verdict.short ? cp.verdict.short : null; o.regime = regimeNow().label; } catch (_) {}
  return o;
}
/* ---- 首页：交易信号条 ---- */
/* 交易计划面板：空仓时默认收起（首页信号格已经是结论），有持仓时默认展开；点信号格/「计划」按钮手动开关，记平仓后恢复自动 */
function planShown() { if (S.planShow === true || S.planShow === false) return S.planShow; return !!planOpen(acctGet().trades); }
function applyPlanVis() {
  const off = !planShown(), had = document.body.classList.contains('plan-off'); document.body.classList.toggle('plan-off', off);
  const b = $('#planBtn'); if (b) b.setAttribute('aria-pressed', String(!off));
  if (off !== had) drawChart();
}
function renderSig() {
  const el = $('#sigbar'); if (!el) return;
  const s = planSnap(), sg = s.sig, F = s.F, f2 = n => (n >= 0 ? '+' : '−') + Math.abs(Math.round(n)).toLocaleString('en-US'), chip = (ok, t) => `<span class="sc ${ok ? 'y' : 'n'}">${ok ? '✓' : '✗'} ${t}</span>`;
  const blocked = !s.gate.ok, cls = blocked ? 'gate' : s.side > 0 ? 'long' : s.side < 0 ? 'short' : 'wait', head = blocked ? '数据不足，信号不可信' : s.side > 0 ? '做多信号' : s.side < 0 ? '做空信号' : '无入场信号';
  let sub; if (blocked) sub = s.gate.reasons.join('；'); else if (s.pos) sub = s.side ? `已有${sdName(s.pos.side)}单，不加仓` : planWhy(sg); else if (s.size) sub = `建议 ${fmtD(s.size.lots)} 手 · 限价 ${s.side > 0 ? '≤' : '≥'} ${fmtD(s.px)} · 止损价 ${fmtD(s.size.stopPx)} · 占用 ${pc1(s.size.usage)}`; else if (s.side) sub = '权益不够开 1 手'; else sub = planWhy(sg);
  const dsl = `<div class="dsl ${s.dl.cls}" id="dataLine">${esc(s.dl.t)}</div>`;
  let left, right;
  if (!s.pos) {
    left = `<button class="sg ${cls}" data-goplan="1" aria-label="入场信号：${head}。${esc(sub)}。点击查看交易计划"><div class="cl">入场信号（收盘后看一次）· 现价 ${fmtD(s.px)}</div><div class="hd">${head}</div><div class="sb">${esc(sub)}</div>
    <div class="scs${blocked ? ' dim' : ''}">${chip(sg.lowOK, '低位' + (sg.pct == null ? '' : ' ' + sg.pct.toFixed(0) + '%'))}${chip(sg.confirm, '反弹确认')}${chip(!sg.delev, '外资未去杠杆')}<span class="sc sep">空</span>${chip(sg.delev, '外资去杠杆')}${chip(sg.trendDn, '趋势向下')}<span class="sc sep">外资5日 ${F.used.length ? '最弱 ' + F.minK.replace('期货', '') + ' ' + f2(F.min) + ' 手' : '无数据'}</span></div>${dsl}</button>`;
    right = `<button class="sg" data-goplan="1" aria-label="持仓：空仓。点击打开交易计划"><div class="cl">持仓</div><div class="hd">空仓</div><div class="sb">账户权益 ${fmtD(s.E.equity)} 元（自动）${s.side && s.size ? '<br>成交后点这里「记录开仓」' : ''}</div></button>`;
  } else {
    const m = s.mg, ho = s.hold, t = s.pos, sd = t.side > 0, out = m.action !== '持有', fl = planPnl(t, ho.last), noF = !F.used.length;
    const stopPx = t.entryPx * (1 - (sd ? 1 : -1) * TPLAN.STOP / 100), stopGap = Math.abs((stopPx / ho.last - 1) * 100);
    const why = !out ? '没有触发止损、移动止盈或外资离场' : m.action === '止损' ? `浮亏 ${(-m.r).toFixed(1)}%，已到 ${TPLAN.STOP}% 止损` : m.action === '移动止盈' ? `最高浮盈 ${m.peakR.toFixed(1)}% 后回落已到 ${TPLAN.TRAIL}%` : m.action === '外资去杠杆·平多' ? `${F.minK} 5日 ${f2(F.min)} 手，≤ ${f2(TPLAN.DELEV)}` : `外资三家合计5日 ${f2(F.sum)} 手（≥0），或价格站上MA20`;
    const trailTxt = m.peakR >= TPLAN.ACT ? '移动止盈已启动' : `移动止盈未启动（最高浮盈 ${m.peakR.toFixed(1)}%<${TPLAN.ACT}%）`;
    const fch = sd ? chip(!m.delevOut, m.delevOut ? '外资去杠杆' : '外资未去杠杆') : chip(!(F.used.length && F.sum >= 0), '外资合计 ' + (F.used.length ? f2(F.sum) : '无数据') + (F.sum >= 0 && F.used.length ? '（回正）' : '，未回正')) + (sg.ma20 != null ? chip(!(ho.last > sg.ma20 * ho.k), '未站上MA20') : '');
    left = `<button class="sg pos ${out ? 'exit' : 'hold'}" data-goplan="1" aria-label="持仓信号：${out ? '该平仓：' + m.action : '继续持有'}。${esc(why)}。点击打开交易计划"><div class="cl">持仓信号（收盘后看一次）· 现价 ${fmtD(ho.last)}</div><div class="hd">${out ? '该平仓 · ' + esc(m.action) : '继续持有'}</div><div class="sb">${esc(why)}${s.side && !blocked ? '<br>入场信号仍成立，已有持仓不加仓' : ''}</div>
    <div class="scs">${chip(!m.stop, '止损价 ' + fmtD(stopPx) + '（距 ' + stopGap.toFixed(1) + '%）')}${chip(!m.trail, trailTxt)}${fch}</div>${dsl}</button>`;
    const up = fl >= 0;
    right = `<button class="sg pos ${out ? 'exit' : 'hold'}" data-goplan="1" aria-label="持仓：${sdName(t.side)}${t.lots}手，浮盈亏 ${yuan(fl)} 元。点击打开交易计划"><div class="cl">持仓 ${sdName(t.side)}${fmtD(t.lots)}手 @${fmtD(t.entryPx)} · ${esc(t.entryD.slice(5))}</div><div class="hd" style="color:${up ? 'var(--bull)' : 'var(--bear)'}">${yuan(fl)} 元</div>
      <div class="sb">浮盈亏 ${m.r >= 0 ? '+' : ''}${m.r.toFixed(1)}% · 最高浮盈 ${m.peakR.toFixed(1)}%<br>权益 ${fmtD(s.E.equity)} 元${noF ? '<br>⚠️ 外资数据缺失，外资离场判断暂不可用' : ''}</div></button>`;
  }
  el.innerHTML = `<div class="sgw">${left}${qb(s.pos ? 'plpos' : 'plsig')}</div>` + right;
  applyPlanVis();
}
/* ---- 交易计划页 ---- */
function sizeHtml(z, side, m, mode, eq, px) {
  const sd = sdName(side);
  let h = `<table class="tb3x tbpl"><tbody>
    <tr><td><b>建议入场价（${sd}，挂限价单）</b></td><td class="n"><b>${side > 0 ? '≤ ' : '≥ '}${fmtD(px)}</b>（信号日收盘价；下一个交易日有效，没成交就作废；跳空${side > 0 ? '低开' : '高开'}按开盘价成交）</td></tr>
    <tr><td>权益所在阶梯 → 占用</td><td class="n">${fmtD(eq)} 元 → ${Math.round(z.u * 100)}%</td></tr>
    <tr><td><b>开仓手数（${sd}）</b></td><td class="n"><b>${fmtD(z.lots)} 手</b>（名义 ${fmtD(z.notional)} 元 · ${z.leverage.toFixed(1)} 倍）</td></tr>
    <tr><td>占用保证金（按 ${(m * 100).toFixed(1)}%）</td><td class="n">${fmtD(z.margin)} 元（占权益 ${pc1(z.usage)}）</td></tr>
    <tr><td>止损价（${TPLAN.STOP}%）</td><td class="n">${fmtD(z.stopPx)}　亏 ${fmtD(z.lossStop)} 元（权益 ${pc1(z.lossPct)}）</td></tr>
    <tr><td>移动止盈启动价（最高浮盈 ${TPLAN.ACT}%）</td><td class="n">${fmtD(z.actPx)}；之后从持仓${side > 0 ? '最高' : '最低'}价回落 ${TPLAN.TRAIL}% 平仓</td></tr>
    <tr><td>风险度到 100%（追保/强平线）的价格</td><td class="n">${fmtD(z.liqPx)}（距止损价 ${z.liqGapPct.toFixed(1)}%）</td></tr>
    <tr><td>止损触发时的风险度</td><td class="n">${pc1(z.riskAtStop)}</td></tr></tbody></table>`;
  if (z.riskAtStop >= .8) h += `<div class="plw">⚠️ 止损价处风险度已到 ${pc1(z.riskAtStop)}，离 100% 追保线很近：盘中跳空、涨停/跌停来不及止损就可能被追保或强平。建议用「按我的实际保证金占用」口径，或把占用降下来。</div>`;
  else if (z.liqGapPct < 2) h += `<div class="plw">⚠️ 追保线只比止损价远 ${z.liqGapPct.toFixed(1)}%，一个跳空就可能越过止损。</div>`;
  if (mode === 'bt' && m > TPLAN.BT_MARGIN + 1e-9) h += `<div class="plw">你选了按回测杠杆：手数按10%保证金算，实际占用 ${pc1(z.usage)}（比资金占比 ${Math.round(z.u * 100)}% 更高）。</div>`;
  return h;
}
/* 离场提醒读的是仓库里的 data/position.json，不是浏览器里的账：到 Actions →「记录持仓」手动填一次 */
function syncActionsUrl() { const m = location.hostname.match(/^([^.]+)\.github\.io$/), r = location.pathname.split('/')[1]; return m && r ? `https://github.com/${m[1]}/${r}/actions/workflows/record-position.yml` : null; }
function syncHtml(pos) {
  const u = syncActionsUrl(), ex = pos ? `动作 <b>open</b> · 方向 <b>${pos.side > 0 ? '多' : '空'}</b> · 手数 <b>${pos.lots}</b> · 日期 <b>${esc(pos.entryD)}</b> · 成交均价 <b>${fmtD(pos.entryPx)}</b>` : '动作 <b>open</b> · 方向 多/空 · 手数 · 开仓日期 · 成交均价';
  return `<details id="pf-sync"><summary>同步持仓到提醒</summary><div class="plh">想收到「该平仓」提醒就要做这一步。页面里记的账只存在这台设备的浏览器里，服务器上的提醒不知道你有没有仓位。开仓后到 GitHub 点一次，平仓后再点一次（一年大约十次）：</div>
   <div class="plh">${u ? `<a href="${esc(u)}" target="_blank" rel="noopener">GitHub → Actions → 记录持仓 → Run workflow</a>` : 'GitHub → Actions → 记录持仓 → Run workflow'}，填：${ex}；平仓后填 动作 <b>close</b>。</div>
   <div class="plh">不同步也能用：入场提醒不需要持仓；离场判断页面首页每天仍会显示「继续持有 / 该平仓」。</div></details>`;
}
const qb = k => `<button class="q" data-about="${k}" aria-label="说明">?</button>`;
function planBodyHtml(s) {
  const A = s.A, sg = s.sig, F = s.F, f2 = n => (n >= 0 ? '+' : '−') + Math.abs(Math.round(n)).toLocaleString('en-US'), pct1 = x => x == null ? '—' : x.toFixed(0) + '%';
  const fwk = F => F.parts.length ? esc(F.minK.replace('期货', '')) + ' ' + f2(F.min) : '—', mk = (ok, y, n) => `<td class="${ok ? 'ok' : 'no'}">${ok ? '✓ ' + y : '✗ ' + n}</td>`, inp = (id, v, ph, extra) => `<input id="${id}" inputmode="decimal" value="${esc(v)}" placeholder="${esc(ph || '')}" ${extra || ''}>`;
  const sel = (id, cur, opts, extra) => `<select id="${id}" ${extra || ''}>${opts.map(([k, n]) => `<option value="${k}"${String(cur) === String(k) ? ' selected' : ''}>${n}</option>`).join('')}</select>`;
  const head = !s.gate.ok ? '数据不足，信号不可信' : s.side > 0 ? '满足做多入场条件' : s.side < 0 ? '满足做空入场条件' : '没有入场信号，观望';
  const pmsg = PMSG ? `<div class="plw pmsg" role="status">${esc(PMSG)}</div>` : '';
  let h = '';
  /* ① 今日信号（页面分块：ps1..ps5，电脑端排成两列一屏放下） */
  h += `<div class="plt">今日入场信号 ${qb('plsig')}</div><div class="hl plhead"><b>${head}</b><br><span style="color:var(--ink2)">${esc(!s.gate.ok ? s.gate.reasons.join('；') + '。先别按这个信号操作' : planWhy(sg))}${s.pos && s.side ? '。你已有持仓，不加仓' : ''}</span>${s.gate.warn.length ? '<br><span class="plh">' + esc(s.gate.warn.join('；')) + '</span>' : ''}</div>
  <table class="tb3x tbpl"><tbody>
   <tr><td>做多①价格低位（260日分位 ≤ ${TPLAN.LO}%）</td><td class="n">${pct1(sg.pct)}</td>${mk(sg.lowOK, '满足', '不满足')}</tr>
   <tr><td>做多②反弹确认（高于5日前，且高出前10日最低价1%）</td><td class="n">—</td>${mk(sg.confirm, '满足', '不满足')}</tr>
   <tr><td>做多③外资没有去杠杆（任一席位5日变化 > ${f2(TPLAN.DELEV)} 手）</td><td class="n">${fwk(F)}</td>${mk(!sg.delev, '满足', '外资去杠杆')}</tr>
   <tr><td>做空①外资去杠杆（任一席位5日变化 ≤ ${f2(TPLAN.DELEV)} 手）</td><td class="n">${fwk(F)}</td>${mk(sg.delev, '满足', '不满足')}</tr>
   <tr><td>做空②价格 < MA20 < MA60，且低于5日前</td><td class="n">${sg.ma20 == null ? '—' : fmtD(sg.ma20) + ' / ' + fmtD(sg.ma60)}</td>${mk(sg.trendDn, '满足', '不满足')}</tr>
  </tbody></table>
  <div class="dsl ${s.dl.cls}">${esc(s.dl.t)}</div>`;
  if (!s.pos && s.side) h += s.size ? `<div class="plt">建议这样开仓（权益 ${fmtD(s.base.equity)} 元，自动算）</div>` + sizeHtml(s.size, s.side, A.margin / 100, A.mode, s.base.equity, s.px) : `<div class="plw">权益 ${fmtD(s.base.equity)} 元不够开 1 手（1手保证金约 ${fmtD(s.px * TPLAN.TON * A.margin / 100)} 元）。</div>`;
  /* ② 持仓管理 */
  h += `\u0001<div class="plt">持仓管理 ${qb('plpos')}</div>`;
  if (!s.pos) {
    const ds = s.side || 1, lots = s.size ? s.size.lots : '';
    h += `<div class="plf">
      <label>开仓日期${inp('pf-od', todayBJ(), 'YYYY-MM-DD')}</label>
      <label>方向${sel('pf-os', ds, [[1, '做多'], [-1, '做空']])}</label>
      <label>手数${inp('pf-ol', lots, '手')}</label>
      <label>成交均价（元/吨）${inp('pf-op', Math.round(s.px), '')}</label>
      <label>开仓手续费（元，留空=每手${fmtD(A.fee)}元的一半）${inp('pf-of', '', '留空自动')}</label></div>
      <button class="pbtn" data-act="open">记录开仓</button>`;
  } else {
    const t = s.pos, m = s.mg, ho = s.hold, out = m.action !== '持有', fl = planPnl(t, ho.last), sd = t.side > 0, usage = t.lots * TPLAN.TON * ho.last * (A.margin / 100) / (s.E.equity > 0 ? s.E.equity : 1);
    const why2 = !out ? '没有触发止损、移动止盈或外资离场。' : m.action === '止损' ? `浮亏 ${(-m.r).toFixed(1)}%，已到 ${TPLAN.STOP}% 止损。` : m.action === '移动止盈' ? `持仓期间最高浮盈 ${m.peakR.toFixed(1)}%（≥${TPLAN.ACT}%），且从${sd ? '最高' : '最低'}价回落已到 ${TPLAN.TRAIL}%。` : m.action === '外资去杠杆·平多' ? `${esc(s.F.minK)} 5日变化 ${f2(s.F.min)} 手，≤ ${f2(TPLAN.DELEV)}。` : `外资三家合计5日变化 ${f2(s.F.sum)} 手（≥0），或价格已站上MA20。`;
    const trigPx = sd ? ho.peak * (1 - TPLAN.TRAIL / 100) : ho.peak * (1 + TPLAN.TRAIL / 100), stopPx = t.entryPx * (1 - (sd ? 1 : -1) * TPLAN.STOP / 100), actPx = t.entryPx * (1 + (sd ? 1 : -1) * TPLAN.ACT / 100);
    const trailTxt = m.peakR >= TPLAN.ACT ? `已启动：${sd ? '跌破' : '涨过'} ${fmtD(trigPx)} 平仓（距现价 ${Math.abs((trigPx / ho.last - 1) * 100).toFixed(1)}%）` : `未启动（最高浮盈 ${m.peakR.toFixed(1)}% < ${TPLAN.ACT}%）；价格到 ${fmtD(actPx)} 后启动`;
    h += `<div class="hl vd ${out ? 'exit' : 'hold'}"><b>${out ? '该平仓：' + esc(m.action) : '继续持有'}</b>　浮盈亏 ${m.r >= 0 ? '+' : ''}${m.r.toFixed(1)}%（${yuan(fl)} 元）<br><span style="color:var(--ink2)">${esc(why2)}</span></div>
    <table class="tb3x tbpl tb2c"><tbody>
     <tr><td>持仓</td><td class="n">${sdName(t.side)}单 ${fmtD(t.lots)} 手 · ${esc(t.entryD)} @ ${fmtD(t.entryPx)} · 已持有 ${ho.days} 个交易日</td></tr>
     <tr><td>现价（主力连续，截至${ho.lastD ? esc(ho.lastD.slice(5)) : '开仓日'}）</td><td class="n">${fmtD(ho.last)}</td></tr>
     <tr><td>持仓期间${sd ? '最高' : '最低'}价（自动）</td><td class="n">${fmtD(ho.peak)}（最高浮盈 ${m.peakR.toFixed(1)}%）</td></tr>
     <tr><td>持仓期间${sd ? '最低' : '最高'}价（自动）</td><td class="n">${fmtD(ho.worst)}</td></tr>
     <tr><td>止损价（${TPLAN.STOP}%）</td><td class="n">${fmtD(stopPx)}（距现价 ${Math.abs((stopPx / ho.last - 1) * 100).toFixed(1)}%）</td></tr>
     <tr><td>移动止盈</td><td class="n">${trailTxt}</td></tr>
     <tr><td>${sd ? '外资最弱席位5日变化 · 任一席位 ≤ −2万则平多' : '外资三家合计5日变化 · ≥0 或站上MA20 则离场'}</td><td class="n">${sd ? (s.F.parts.length ? esc(s.F.minK.replace('期货', '')) + ' ' : '') + f2(s.F.min) : f2(s.F.sum)} 手${!sd && s.sig.ma20 != null ? ' · MA20 ' + fmtD(s.sig.ma20 * ho.k) : ''}</td></tr>
     <tr><td>当前风险度（保证金/权益）</td><td class="n">${pc1(usage)}</td></tr></tbody></table>
    ${ho.scaled ? `<div class="plh">你的开仓价和开仓日主连收盘差超过2%（可能是非主力合约），最高/最低价和现价已按开仓日主连收盘折算，涨跌幅准确。</div>` : ''}${ho.covered ? '' : `<div class="plh">开仓日期晚于已有价格数据，最高/最低价暂按开仓价，数据更新后自动补上。</div>`}
    <div class="plt" style="margin-top:6px">${out ? '已平仓？记一笔' : '手动平仓（系统没让走，你自己要走时）'}</div><div class="plf">
      <label>平仓日期${inp('pf-cd', todayBJ(), 'YYYY-MM-DD')}</label>
      <label>成交均价（元/吨）${inp('pf-cp', Math.round(ho.last), '')}</label>
      <label>平仓手续费（元，留空=每手${fmtD(A.fee)}元的一半）${inp('pf-cf', '', '留空自动')}</label></div>
      <button class="pbtn${out ? ' warn' : ''}" data-act="close">记录平仓</button>`;
  }
  /* ③ 账户权益 */
  const E = s.E, st = planStats(A);
  h += `\u0001<div class="plt">账户权益（自动）${qb('placct')}</div><div class="hl"><b>${fmtD(E.equity)} 元</b>　<span style="color:var(--ink2)">= 初始 ${fmtD(E.init)} ${yuan(E.flows)}出入金 ${yuan(E.realized)}已平仓 ${yuan(E.floating)}持仓浮动 −${fmtD(E.fees)}手续费</span></div>
   <div class="plh">${st.n ? `已平仓 ${st.n} 笔，胜 ${st.wins} 笔（${(st.wins / st.n * 100).toFixed(0)}%），净盈亏 ${yuan(st.net)} 元（已扣手续费）。` : '还没有已平仓记录。'}</div>
   <details id="pf-set"><summary>账户设置 · 出入金 · 对账校准</summary><div class="plf">
    <label>初始资金（元）${inp('pf-init', A.init, '', 'data-set="init"')}</label>
    <label>期货公司保证金比例（%）${inp('pf-m', A.margin, '', 'data-set="margin"')}</label>
    <label>每手手续费，来回（元）${inp('pf-fee', A.fee, '', 'data-set="fee"')}</label>
    <label>手数口径${sel('pf-mode', A.mode, [['real', '按我的实际保证金占用'], ['bt', '按回测杠杆（10%保证金）']], 'data-set="mode"')}</label></div>
   <div class="plf">
    <label>出入金日期${inp('pf-fd', todayBJ(), 'YYYY-MM-DD')}</label>
    <label>金额（入金填正数，出金填负数）${inp('pf-fa', '', '如 200000 或 -50000')}</label>
    <label>备注${inp('pf-fn', '', '如 年度追加')}</label></div>
   <button class="pbtn" data-act="flow">记录出入金</button>
   <div class="plf" style="margin-top:8px"><label>期货公司账户实际权益（元）${inp('pf-ca', '', '对账后填，系统记一笔差额')}</label></div>
   <button class="pbtn" data-act="calib">按实际权益校准</button></details>`;
  /* ④ 交易记录 */
  h += `\u0001<div class="plt">交易记录</div>`;
  if (!A.trades.length) h += `<div class="plh">暂无记录。</div>`;
  else h += `<div style="overflow-x:auto"><table class="tb3x tbcv"><thead><tr><th>开仓</th><th>方向</th><th>手数</th><th>开仓价</th><th>平仓</th><th>平仓价</th><th>手续费</th><th>净盈亏</th><th>价格涨跌</th><th>开仓时：基本面 · 外资5日</th><th></th></tr></thead><tbody>${A.trades.slice().reverse().map(t => {
      const cl = !!t.exitD, fee = planFee(t, A.fee), net = cl ? planPnl(t, t.exitPx) - fee : null, ret = cl ? (t.side >= 0 ? 1 : -1) * (t.exitPx / t.entryPx - 1) * 100 : null;
      return `<tr><td>${esc(t.entryD)}</td><td>${sdName(t.side)}</td><td class="n">${fmtD(t.lots)}</td><td class="n">${fmtD(t.entryPx)}</td><td>${cl ? esc(t.exitD) : '持仓中'}</td><td class="n">${cl ? fmtD(t.exitPx) : '—'}</td><td class="n">${fmtD(fee)}</td><td class="n" style="color:${net == null ? 'inherit' : net >= 0 ? 'var(--bull)' : 'var(--bear)'}">${net == null ? '—' : yuan(net)}</td><td class="n">${ret == null ? '—' : (ret >= 0 ? '+' : '') + ret.toFixed(1) + '%'}</td><td>${t.snap ? esc((t.snap.fund || '—') + ' · ' + (t.snap.fsum >= 0 ? '+' : '') + t.snap.fsum) : '—'}</td><td><button class="xbtn" data-act="delt" data-id="${esc(t.id)}" aria-label="删除这笔记录">×</button></td></tr>`; }).join('')}</tbody></table></div>`;
  if (A.flows.length) h += `<details id="pf-fl"><summary>出入金记录（${A.flows.length} 笔）</summary><table class="tb3x tbcv"><tbody>${A.flows.map((f, i) => `<tr><td>${esc(f.d)}</td><td class="n">${yuan(+f.amt)}</td><td>${esc(f.note || '')}</td><td><button class="xbtn" data-act="delf" data-i="${i}" aria-label="删除这笔出入金">×</button></td></tr>`).join('')}</tbody></table></details>`;
  h += `<div class="plh" style="margin-top:8px">记录只存本机浏览器。<button class="lnk" data-act="backup">备份下载</button> · <button class="lnk" data-act="csv">导出CSV（含决策快照）</button> · <label class="lnk">恢复备份<input id="pf-file" type="file" accept=".json,application/json" hidden></label></div>`;
  /* 折叠：阶梯、回测摘要 */
  h += `\u0001${syncHtml(s.pos)}<details id="pf-mo"><summary>历史开仓月份</summary><div class="plh">背景参考：信号出现的频率有参考，盈亏没有。</div>${monthHtml()}</details><details id="pf-lad"><summary>仓位阶梯</summary><div class="plh">权益越大，占用越低。</div>${ladderHtml(s.base.equity)}</details><details id="pf-bt"><summary>回测摘要</summary><div class="plh">样本内结果，仅供参考。</div>${planBtHtml()}</details>`;
  const q = h.split('\u0001');   // [入场信号, 持仓管理, 账户权益, 交易记录, 折叠项]：电脑端两列排版时按 入场/账户/记录 | 持仓 的顺序放，高度才平衡
  return pmsg + `<div class="plgrid"><div class="ps ps1">${s.pos ? `<details id="pf-sig"><summary>入场信号条件（已有持仓，不加仓）</summary>${q[0]}</details>` : q[0]}</div><div class="ps ps3">${q[2]}</div><div class="ps ps4">${q[3]}</div><div class="ps ps2">${q[1]}</div><div class="ps ps5">${q[4]}</div></div>`;
}
function tradeShell() { const t = $('#tradePanel'); if (t && !$('#planBody')) t.innerHTML = `<div class="ch-h"><span class="t">交易计划 · 持仓与账户</span><button class="q" data-about="plan" aria-label="这页怎么用">?</button></div><div id="planForm"><div id="planBody"></div></div>`; }
function planBtHtml() {
  return `<div class="plw">⚠️ 回测数字取决于「怎么成交、用什么价、外资数据什么时候知道」：同一套规则，5年终值中位数可以在 317万~895万 之间。下面把几种做法并排放，别只看最好的那个。</div>
  <table class="tb3x tbpl"><thead><tr><th>做法（50万起、盈利再投、44个5年滚动窗口）</th><th>终值中位 · 差10% · 最差</th></tr></thead><tbody>
    <tr><td>收盘价成交 + 当天龙虎榜（做不到：龙虎榜收盘后才公布）</td><td class="n">895万 · 396万 · 245万</td></tr>
    <tr><td>14:58 下单（收盘价±2分钟波动模拟）+ 只能用前一天龙虎榜</td><td class="n">754万 · 317万 · 221万</td></tr>
    <tr><td><b>★ 收盘后看信号，次日开盘价成交（本页的流程）</b></td><td class="n"><b>735万 · 379万 · 237万</b></td></tr>
    <tr><td>次日挂限价单=信号日收盘价（没成交就作废；95% 的信号能成交）</td><td class="n">830万 · 385万 · 241万</td></tr>
    <tr><td>次日挂限价单=收盘价回调 0.3%（成交率 83%）/ 0.5%（58%）</td><td class="n">1022万 · 395万 · 247万 / 919万 · 409万 · 257万</td></tr>
    <tr><td>次日挂限价单=收盘价回调 1%（成交率 22%）/ 1.5%</td><td class="n">337万 · 160万 · 156万 / 146万 · 96万 · 94万</td></tr>
    <tr><td>信号用原始主连（换月日有价差跳空；本页早期版本的做法），次日开盘成交</td><td class="n">317万 · 113万 · 45万</td></tr>
  </tbody></table>
  <div class="plh">结论：14:58 抢跑并不比次日开盘明显好（模拟范围 703~803万 与 735万 重叠），却要盯盘、龙虎榜还没出；所以只在收盘后看一次。入场价见上面的限价单几行：挂在收盘价没问题（不比开盘市价差），回调挂得越深越容易错过——回调 1% 就掉到 337万（夏普 0.89），中间 0.3~0.5% 好看是 43 笔里个别单的路径，不当规则。信号和盈亏必须用「换月调整价」（本页已改），否则会多出换月假信号。</div>
  <table class="tb3x tbpl"><tbody>
    <tr><td>★口径：年化 · 夏普（全程）</td><td class="n">+54% · 1.09</td></tr>
    <tr><td>5年内最大回撤</td><td class="n">中位 −48% · 最差 −54%</td></tr>
    <tr><td>交易笔数</td><td class="n">8.7年共43笔（多27/空16），年均约5笔；持仓中位14个自然日</td></tr>
    <tr><td>胜率</td><td class="n">49%（多头52% · 空头44%）</td></tr>
    <tr><td>盈亏比（平均盈÷平均亏）</td><td class="n">3.56（平均盈 +7.0% · 平均亏 −2.0%，价格涨跌幅）</td></tr>
    <tr><td>手续费+滑点敏感</td><td class="n">每手来回23元：中位735万；63元：618万；103元：466万</td></tr>
  </tbody></table>
  <div class="plh">2017-12~2026-10，只有43笔交易，窗口高度重叠（独立样本约2个），参数在同一段数据里选出，样本外要打折；外资数据2022年起才有，之前的交易全是多单；不含涨跌停无法成交、盘中跳空和大资金冲击成本。</div>`;
}
/* ---- 历史开仓月份（回测：次日开盘成交口径，2018-01~2026-06，43笔）——背景参考，不是交易规则 ---- */
const MSTAT = {"period":"2018-01~2026-06","n":43,"rows":[{"m":1,"n":10,"l":8,"s":2,"w":4,"a":4.2,"y":["2018","2019","2020","2022","2024","2025","2026"]},{"m":2,"n":7,"l":4,"s":3,"w":3,"a":2.3,"y":["2024","2026"]},{"m":3,"n":2,"l":2,"s":0,"w":1,"a":5.0,"y":["2019","2025"]},{"m":4,"n":1,"l":1,"s":0,"w":1,"a":22.5,"y":["2023"]},{"m":5,"n":2,"l":1,"s":1,"w":0,"a":-0.7,"y":["2025"]},{"m":6,"n":1,"l":0,"s":1,"w":1,"a":0.8,"y":["2026"]},{"m":7,"n":2,"l":1,"s":1,"w":1,"a":1.2,"y":["2024"]},{"m":8,"n":2,"l":1,"s":1,"w":2,"a":3.0,"y":["2024"]},{"m":9,"n":4,"l":2,"s":2,"w":1,"a":-1.7,"y":["2024","2025"]},{"m":10,"n":5,"l":3,"s":2,"w":2,"a":0.2,"y":["2021","2024","2025"]},{"m":11,"n":2,"l":1,"s":1,"w":2,"a":2.8,"y":["2021","2024"]},{"m":12,"n":5,"l":3,"s":2,"w":3,"a":1.4,"y":["2023","2024","2025"]}],"note":"样本小、每月只有个位数笔数，仅作背景。"};
function monthHtml() {
  const R = MSTAT.rows, N = MSTAT.n, mx = Math.max(...R.map(r => r.n)), cur = +todayBJ().slice(5, 7);
  const kind = r => { const x = r.n / N * 12; return x >= 1.8 ? '高发' : x <= 0.6 ? '少发' : '平常'; };
  return `<div class="plh">回测里一共 ${N} 笔开仓（${MSTAT.period}，次日开盘价成交）。看两件事：<b>哪些月份信号更常出现</b>，以及<b>哪些月份开的仓更赚钱</b>。</div>
  <table class="tb3x tbcv tbmo"><thead><tr><th>开仓月</th><th>笔数</th><th>多/空</th><th>胜率</th><th>平均每笔</th><th>出现在几年</th></tr></thead><tbody>${R.map(r => `<tr${r.m === cur ? ' class="cur"' : ''}><td>${r.m}月${r.m === cur ? '（本月）' : ''}<span class="mk ${kind(r)}">${kind(r)}</span></td><td class="n"><span class="mb" style="width:${Math.round(r.n / mx * 60)}px"></span>${r.n}</td><td class="n">${r.l}/${r.s}</td><td class="n">${r.n ? Math.round(r.w / r.n * 100) + '%' : '—'}</td><td class="n">${r.a == null ? '—' : (r.a >= 0 ? '+' : '−') + Math.abs(r.a).toFixed(1) + '%'}</td><td class="n" title="${esc(r.y.join('、'))}">${r.y.length}</td></tr>`).join('')}</tbody></table>
  <div class="plt" style="margin-top:10px">这个规律有多重要？</div>
  <table class="tb3x tbpl"><tbody>
   <tr><td><b>信号出现的频率</b><br><span class="stars">★★★☆☆</span></td><td>有参考价值。1、2月合计 17 笔，占 40%（随机期望约 17%，不是巧合）；1月在 9 个年份里有 7 年出现过信号。<b>怎么用：</b>这两个月提醒要开着、每天的数据别断，别一两周没看就以为「没信号」。</td></tr>
   <tr><td><b>开仓的盈亏</b><br><span class="stars">★☆☆☆☆</span></td><td>基本没有参考价值。各月平均每笔收益的差别，把月份随机打乱重算有 70% 的概率出现同样大的差距（统计上分不出来）；月份样本只有 1~10 笔，1月的好成绩主要来自 3 笔大赢单（2018、2020、2022）。<b>怎么用：</b>不要因为「这个月历史上好」而加仓，也不要因为「这个月历史上差」而放弃一个合格的信号。</td></tr>
   <tr><td><b>原因</b></td><td>没有验证。回测只能说「过去信号常出现在年初」，没有检验是什么原因；规则本身并不看月份。</td></tr>
  </tbody></table>
  <div class="plh">「高发/平常/少发」按该月笔数相对平均（每月 ${(N / 12).toFixed(1)} 笔）划分：≥1.8 倍高发，≤0.6 倍少发。${MSTAT.note}</div>`;
}
function monthHint() { const r = MSTAT.rows[+todayBJ().slice(5, 7) - 1], x = r.n / MSTAT.n * 12, k = x >= 1.8 ? '高发月：历史上信号较常出现，提醒保持开启' : x <= 0.6 ? '少发月：历史上很少出信号' : '平常月份'; return `本月（${r.m}月）历史开仓 ${r.n} 笔（占 ${(r.n / MSTAT.n * 100).toFixed(0)}%）· ${k}`; }
function planFormSnap() { const keep = {}; $$('#planBody [id^="pf-"]').forEach(e => { if (e.dataset.t) keep[e.id] = e.value; }); return { keep, opened: $$('#planBody details[open]').map(e => e.id) }; }
let PLAN_BUSY = false;   // 正在重绘时不再重入：浏览器在拆掉有焦点的输入框时会同步触发 change/blur，里面又会调用重绘
function planUpdate(reset, snap) {
  const box = $('#planBody'); if (!box || PLAN_BUSY) return;
  PLAN_BUSY = true;
  try {
    const sn = reset ? { keep: {}, opened: planFormSnap().opened } : (snap || planFormSnap());
    box.innerHTML = planBodyHtml(planSnap());
    Object.keys(sn.keep).forEach(id => { const e = document.getElementById(id); if (e) { e.value = sn.keep[id]; e.dataset.t = '1'; } });
    sn.opened.forEach(id => { const e = document.getElementById(id); if (e) e.open = true; });
  } finally { PLAN_BUSY = false; }
}
function planAfter(msg) { PMSG = msg || null; planUpdate(true); renderSig(); drawChart(); }
const okDate = d => /^\d{4}-\d{2}-\d{2}$/.test(d) && isFinite(Date.parse(d));
function planAct(act, el) {
  const A = acctGet(), v = id => { const e = document.getElementById(id); return e ? String(e.value).trim() : ''; }, nm = id => { const x = parseFloat(v(id).replace(/,/g, '')); return isFinite(x) ? x : NaN; };
  const save = msg => { if (!acctSave()) msg += '（⚠️ 浏览器不让保存，刷新会丢，请先点「备份下载」）'; planAfter(msg); };
  if (act === 'open') {
    const side = parseInt(v('pf-os'), 10) >= 0 ? 1 : -1, lots = Math.round(nm('pf-ol')), px = nm('pf-op'), d = v('pf-od'), fee = v('pf-of');
    if (planOpen(A.trades)) return planAfter('已经有一笔持仓，先记平仓。');
    if (!okDate(d) || !(lots >= 1) || !(px > 0)) return planAfter('开仓没记：日期要写成 2026-10-12，手数≥1，价格>0。');
    if (fee !== '' && !(parseFloat(fee) >= 0)) return planAfter('开仓没记：手续费要么留空，要么填数字。');
    A.trades.push({ id: String(Date.now()), side, lots, entryD: d, entryPx: px, feeO: fee === '' ? null : parseFloat(fee), snap: planSnapshotNow(planSnap()) });
    return save(`已记录开仓：${sdName(side)} ${lots} 手 @ ${fmtD(px)}。之后的最高/最低价、浮盈亏、离场判断都自动算。`);
  }
  if (act === 'close') {
    const t = planOpen(A.trades), px = nm('pf-cp'), d = v('pf-cd'), fee = v('pf-cf');
    if (!t) return planAfter('当前没有持仓。');
    if (!okDate(d) || d < t.entryD || !(px > 0)) return planAfter('平仓没记：日期要写成 2026-10-12 且不早于开仓日，价格>0。');
    if (fee !== '' && !(parseFloat(fee) >= 0)) return planAfter('平仓没记：手续费要么留空，要么填数字。');
    t.exitD = d; t.exitPx = px; t.feeC = fee === '' ? null : parseFloat(fee); t.snapX = planSnapshotNow(planSnap());
    const net = planPnl(t, px) - planFee(t, A.fee);
    S.planShow = undefined;   // 平仓后回到自动：空仓就把交易计划收起来
    return save(`已记录平仓：净盈亏 ${yuan(net)} 元（已扣手续费），权益已更新。`);
  }
  if (act === 'flow') {
    const amt = nm('pf-fa'), d = v('pf-fd');
    if (!okDate(d) || !isFinite(amt) || amt === 0) return planAfter('出入金没记：日期要写成 2026-10-12，金额不能为0（入金正数，出金负数）。');
    A.flows.push({ d, amt, note: v('pf-fn') }); return save(`已记录${amt > 0 ? '入金' : '出金'} ${fmtD(Math.abs(amt))} 元。`);
  }
  if (act === 'calib') {
    const actual = nm('pf-ca'); if (!(actual > 0)) return planAfter('校准没做：请填期货公司账户的实际权益。');
    const diff = actual - planSnap().E.equity; if (Math.abs(diff) < 1) return planAfter('系统权益和你填的一致，不用校准。');
    A.flows.push({ d: todayBJ(), amt: Math.round(diff), note: '按期货公司权益校准' }); return save(`已校准：记了一笔 ${yuan(Math.round(diff))} 元的差额，权益现在 ${fmtD(actual)} 元。`);
  }
  if (act === 'delt') { if (!window.confirm('删除这笔交易记录？权益会重新计算。')) return; A.trades = A.trades.filter(t => String(t.id) !== el.dataset.id); return save('已删除一笔交易记录。'); }
  if (act === 'delf') { if (!window.confirm('删除这笔出入金记录？权益会重新计算。')) return; A.flows.splice(+el.dataset.i, 1); return save('已删除一笔出入金记录。'); }
  if (act === 'csv') {
    const per = A.fee, hdr = ['开仓日','方向','手数','开仓价','平仓日','平仓价','手续费','净盈亏','价格涨跌%','开仓基本面','开仓基本面分','开仓技术面','开仓结构','开仓资金面','开仓市场状态','开仓价格分位','反弹确认','外资去杠杆','外资5日','趋势向下','平仓基本面','平仓外资5日'];
    const rows = A.trades.map(t => { const cl = !!t.exitD, sn = t.snap || {}, sx = t.snapX || {}, fee = planFee(t, per), net = cl ? planPnl(t, t.exitPx) - fee : '', ret = cl ? ((t.side >= 0 ? 1 : -1) * (t.exitPx / t.entryPx - 1) * 100).toFixed(2) : '';
      return [t.entryD, t.side > 0 ? '多' : '空', t.lots, t.entryPx, t.exitD || '', t.exitPx || '', fee, net, ret, sn.fund || '', sn.fundRatio == null ? '' : sn.fundRatio, sn.tech || '', sn.struct || '', sn.cap || '', sn.regime || '', sn.pct == null ? '' : sn.pct, sn.confirm == null ? '' : sn.confirm, sn.delev == null ? '' : sn.delev, sn.fsum == null ? '' : sn.fsum, sn.trendDn == null ? '' : sn.trendDn, sx.fund || '', sx.fsum == null ? '' : sx.fsum]; });
    const csv = '\ufeff' + [hdr].concat(rows).map(r => r.map(x => '"' + String(x).replace(/"/g, '""') + '"').join(',')).join('\r\n');
    try { const b = new Blob([csv], { type: 'text/csv;charset=utf-8' }), a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'cockpit-trades-' + todayBJ() + '.csv'; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); } catch (_) { planAfter('这个浏览器不支持下载。'); } return;
  }
  if (act === 'backup') {
    try { const b = new Blob([JSON.stringify(A, null, 1)], { type: 'application/json' }), a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'cockpit-account-' + todayBJ() + '.json'; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }
    catch (_) { planAfter('这个浏览器不支持下载备份。'); } return;
  }
}
function planSetting(el) {
  const A = acctGet(), k = el.dataset.set, x = parseFloat(String(el.value).replace(/,/g, ''));
  if (k === 'mode') A.mode = el.value === 'bt' ? 'bt' : 'real';
  else if (k === 'init' && x >= 0) A.init = x; else if (k === 'margin' && x > 0 && x < 100) A.margin = x; else if (k === 'fee' && x >= 0) A.fee = x;
  else return planAfter('这一项没改：请填合理的数字。');
  planAfter(acctSave() ? null : '⚠️ 浏览器不让保存，刷新会丢。');
}
function planRestore(file) {
  const fr = new FileReader();
  fr.onload = () => { try { const a = JSON.parse(fr.result); if (!a || !Array.isArray(a.trades) || !Array.isArray(a.flows)) throw 0; ACCT = acctNorm(a); acctSave(); planAfter(`已恢复：${a.trades.length} 笔交易、${a.flows.length} 笔出入金。`); } catch (_) { planAfter('恢复失败：这不是本页导出的备份文件。'); } };
  fr.readAsText(file);
}
function ladderHtml(eq) {
  const rows = [['< 500 万', .6, 0, 5e6], ['500 ~ 1500 万', .4, 5e6, 1.5e7], ['1500 ~ 5000 万', .25, 1.5e7, 5e7], ['≥ 5000 万', .15, 5e7, Infinity]];
  return `<table class="tb3x tbpl"><thead><tr><th>权益</th><th>占用（保证金/权益）</th><th>回测口径名义杠杆</th></tr></thead><tbody>${rows.map(([n, u, a, b]) => `<tr${eq >= a && eq < b ? ' class="cur"' : ''}><td>${n}${eq >= a && eq < b ? '　← 现在' : ''}</td><td class="n">${Math.round(u * 100)}%</td><td class="n">${(u / TPLAN.BT_MARGIN).toFixed(1)} 倍</td></tr>`).join('')}</tbody></table>`;
}
function renderView() { const v = S.view; $('#chart').innerHTML = v === 'pos' ? viewPos() : v === 'sea' ? viewSea() : viewCost(); }

const BEC = '#8b7cf6';
const lampOfLevel = lv => ({ red: 'warn', yellow: 'note', green: 'ok', gray: 'na' }[lv] || 'na');

/* ---------- 基本面：用每日系统记录的最新一天(与线上一致)，趋势用这些记录 ---------- */
function fundamentals() {
  const rec = D.systems[S.key] || [], last = rec[rec.length - 1];
  const dims = C().dims;
  return { rec, last, dir: last ? last.dir : null, ratio: last ? last.v : null, n: last ? last.n : null,
    sup: dims && dims.supply ? dims.supply.ratio : null, dem: dims && dims.demand ? dims.demand.ratio : null };
}

/* ---------- 量价：沿用页面自己的 vpAt 逐日结果 ---------- */
function vpInfo() {
  const c = C(), seq = c.vpSeq || [];
  return { seq, last: seq[seq.length - 1], status: c.vp && c.vp.status, reason: c.vp && c.vp.reason, meaning: c.vpMeaning || {} };
}
const vpClass = r => !r || r.gate ? 'na' : r.quad === '增仓上涨' ? 'sb' : r.quad === '增仓下跌' ? 'sx' : r.quad === '减仓上涨' ? 'wb' : r.quad === '减仓下跌' ? 'wx' : '';

/* ---------- 价格统计 ---------- */
function priceStats() {
  const b = C().kline || []; if (b.length < 2) return null;
  const last = b[b.length - 1], prev = b[b.length - 2], s = { last, prev, chg: last.c / prev.c - 1, n: b.length };
  if (b.length >= 20) { const w = b.slice(-20); s.hi = Math.max(...w.map(x => x.h)); s.lo = Math.min(...w.map(x => x.l)); s.pos = (last.c - s.lo) / ((s.hi - s.lo) || 1); s.ma20 = w.reduce((a, x) => a + x.c, 0) / 20; }
  return s;
}
function trendOfBars(key, pol) {
  const b = C().kline || [];
  const pts = b.map(x => ({ d: x.d, v: key === 'oi' ? x.oi : x.c }));
  return L.trend(pts, { freq: 'daily', pol });
}
function regimeNow() {
  const b = (C().kline || []).map(x => ({ h: x.h, l: x.l, c: x.c, oi: x.oi }));
  const f = fundamentals(), cap = capital();
  return L.regime(b, { capitalCode: cap.state.code, fundRatio: f.ratio });
}

/* ---------- 趋势墙的格子定义 ---------- */
const SIGMAP = {  // 格子 → 当前信号(取自页面的指标徽标或投票)
  stock: i => ind('stock'), stu: i => ind('stu'), crush: i => ind('crush'), arrival: i => ind('arrival'), import: i => ind('import'),
  feed: i => ind('feed'), hog: i => ind('hogratio'), poultry: i => ind('poultry'), rm: i => ind('rmspread'), basis: i => ind('basis'),
  ustu: () => vote(/库存消费比/), margin: () => vote(/压榨毛利/), esr: () => vote(/出口销售/), spread: () => vote(/月差/)
};
function ind(k) { const it = D.indicators.find(x => x.key === k); if (!it || !it.badge) return null; return /偏多/.test(it.badge) ? 1 : /偏空/.test(it.badge) ? -1 : /不计分|暂不计分/.test(it.badge) ? null : 0; }
function vote(re) { const v = C().votes.find(x => re.test(x.label)); return v ? (v.signal === 1 || v.signal === -1 || v.signal === 0 ? v.signal : null) : null; }
function tiles() {
  const k = S.key, out = [];
  const add = (id, base, extra) => { const s = SER[base]; if (!s) return; out.push({ id, ...s, ...extra, sig: (SIGMAP[id.replace(/_.*/, '')] || (() => null))() }); };
  add('stock', 'stock'); add('stu', 'stu'); add('ustu', 'ustu'); add('margin', 'margin_' + k); add('crush', 'crush'); add('arrival', 'arrival'); add('import', 'import');
  add('feed', 'feed'); add('hog', 'hog'); add('esr', 'esr'); add('poultry', 'poultry'); add('rm', 'rm');
  add('basis', 'basis'); add('spread', 'spread_' + k);
  add('cftc', 'cftc'); add('gs', 'gs'); add('zl', 'zl');
  out.forEach(t => { t.tr = L.trend(t.pts, { freq: t.freq, pol: t.pol }); });
  return out;
}
const WIN = { daily: { short: 20, mid: 60, long: 120 }, weekly: { short: 13, mid: 26, long: 104 }, monthly: { short: 6, mid: 12, long: 24 }, yearly: { short: 3, mid: 5, long: 10 }, 'seasonal-daily': { short: 20, mid: 40, long: 80 } };
function windowPts(t) {
  let p = t.pts;
  if (t.freq === 'seasonal-daily') p = L.currentRun(p, 10);
  const n = (WIN[t.freq] || WIN.daily)[S.span];
  return p.slice(-n);
}
function sparkSvg(pts, color, W, H, anim, dl) {
  if (!pts || pts.length < 2) return '';
  const vs = pts.map(p => p.v), lo = Math.min(...vs), hi = Math.max(...vs), r = (hi - lo) || 1, pad = 4;
  const x = i => pad + i / (pts.length - 1) * (W - 2 * pad), y = v => pad + (hi - v) / r * (H - 2 * pad);
  const d = pts.map((p, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(p.v).toFixed(1)).join('');
  const len = Math.round(pts.reduce((a, p, i) => i ? a + Math.hypot(x(i) - x(i - 1), y(p.v) - y(pts[i - 1].v)) : 0, 0)) + 4;
  const area = d + `L${x(pts.length - 1).toFixed(1)} ${H}L${x(0).toFixed(1)} ${H}Z`;
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true"><path class="ar" d="${area}" fill="${color}" opacity=".10"/><path class="ln ${anim ? 'draw' : ''}" d="${d}" stroke="${color}" style="--len:${len};--dl:${dl || 0}ms" vector-effect="non-scaling-stroke"/><path d="M${x(pts.length - 1).toFixed(1)} ${y(vs[vs.length - 1]).toFixed(1)}h.01" stroke="${color}" stroke-width="7" stroke-linecap="round" fill="none" vector-effect="non-scaling-stroke"/></svg>`;
}
const colorOf = m => m > 0 ? 'var(--bull)' : m < 0 ? 'var(--bear)' : 'var(--ink2)';
const arrow = d => d === 1 ? '↑' : d === -1 ? '↓' : d === 0 ? '→' : '';
function chipHtml(t, c) {
  if (!c.ok) return `<div class="chip na"><div class="l">${c.label}</div><div class="a">—</div></div>`;
  if (c.dir === 0) return `<div class="chip"><div class="l">${c.label}</div><div class="a" style="color:var(--ink2)">→持平</div></div>`;
  const f = L.fmtChange(c.change, c.pct, t.show, t.unit);
  return `<div class="chip" title="${esc(c.from.d)}：${esc(L.fmtNum(c.from.v, t.unit))} → ${esc(L.fmtNum(c.to.v, t.unit))}"><div class="l">${c.label}</div><div class="a" style="color:${colorOf(c.meaning)}">${arrow(c.dir)}${f.text}</div></div>`;
}
const BADGE = { up: ['同升', 'up'], down: ['同降', 'down'], pullback: ['回落', 'm'], rebound: ['反弹', 'm'] };
// 徽标的颜色跟"对价格的多空含义"走，不是跟数值升降走：库存同升是偏空(绿)，所以徽标是绿色，不能在绿格子上盖红徽标。含义为0(如CFTC，不是多空信号)用灰色。
const badgeCls = (tr) => { if (!tr.badge) return ''; if (tr.badge === 'pullback' || tr.badge === 'rebound') return 'm'; const m = (tr.chips.find(c => c.ok && c.meaning !== 0) || {}).meaning || 0; return m > 0 ? 'up' : m < 0 ? 'down' : 'm'; };      // 完整含义(三个周期都升/降；长期涨而最近一周跌=回落)在说明里
function tileHtml(t, i, anim) {
  const tr = t.tr, last = tr.last, pts = windowPts(t), sigC = t.sig === 1 ? 'sb' : t.sig === -1 ? 'sx' : '';
  const cons = tr.chips.filter(c => c.ok && c.meaning !== 0).map(c => c.meaning);
  const tint = tr.badge === 'up' || tr.badge === 'down' ? (tr.chips[0].meaning > 0 ? 'tb3' : tr.chips[0].meaning < 0 ? 'tx3' : '') : (cons.length && cons.every(m => m === cons[0]) ? (cons[0] > 0 ? 'tb2' : 'tx2') : '');
  const lineMeaning = (tr.chips.find(c => c.ok) || {}).meaning || 0;
  let sk;
  if (tr.n >= 3) sk = `<div class="sk">${sparkSvg(pts, colorOf(lineMeaning) === 'var(--ink2)' ? 'var(--ink2)' : colorOf(lineMeaning), 120, 40, anim, i * 40)}</div>`;
  else sk = `<div class="sk"><div class="na">${tr.n === 0 ? '暂无数据' : '历史累积中，已' + tr.n + '个点'}</div></div>`;
  const bd = tr.badge ? `<span class="bd ${badgeCls(tr)}" title="${tr.badge === 'up' ? '三个周期都在上升' : tr.badge === 'down' ? '三个周期都在下降' : tr.badge === 'pullback' ? '长期在涨，但最近一周回落' : '长期在跌，但最近一周反弹'}">${BADGE[tr.badge][0]}</span>` : '';
  const val = last ? L.fmtNum(last.v, t.unit) : '—';
  const g = { 供给: '供', 需求: '需', 结构: '价', 资金: '资' }[t.g] || '';
  return `<button class="tile ${sigC} ${tint}" data-tile="${t.id}" aria-label="${esc(t.name)}，最新${esc(val)}${esc(t.unit)}，点击看详情">
    <div class="t1"><span class="n" title="${esc(t.name)}">${esc(t.short && t.name.length > 7 ? t.short : t.name)}</span>${bd}</div>
    <div class="t2"><span class="v">${val}</span><span class="u">${esc(t.unit && t.unit !== '手' ? t.unit : (t.unit === '手' && Math.abs(last ? last.v : 0) >= 1e4 ? '' : t.unit))}</span></div>
    ${sk}
    <div class="chips">${tr.chips.map(c => chipHtml(t, c)).join('')}</div></button>`;
}

/* ---------- 渲染：状态带 ---------- */
function renderBand() {
  const rg = regimeNow(), f = fundamentals(), cap = capital(), ps = priceStats(), vp = vpInfo(), c = C();
  const cls = { trend_up: 'trend_up', trend_down: 'trend_down', capital: 'capital', range: 'range', unclear: 'unclear', na: 'na' }[rg.code];
  const seq = vp.seq.slice(-5);
  const SH = { '增仓上涨': '增涨', '增仓下跌': '增跌', '减仓上涨': '减涨', '减仓下跌': '减跌', '增仓横盘': '增平', '减仓横盘': '减平', '持仓平稳上涨': '平涨', '持仓平稳下跌': '平跌', '价格持仓均平稳': '平' };
  const cnt = {}; seq.forEach(r => { if (r && !r.gate && r.quad) cnt[r.quad] = (cnt[r.quad] || 0) + 1; });
  const top = Object.entries(cnt).sort((a, b) => b[1] - a[1])[0];
  const sumTxt = vp.last && !vp.last.gate ? (top && top[1] >= 2 ? `近5天${top[1]}天${top[0]}` : '近5天没有一致的量价') : '量价不可用';
  const seqHtml = vp.status === 'insufficient' ? `<div class="seq"><span>K线不足，量价不可用</span></div>` :
    `<div class="seq">${seq.map(r => `<i class="${vpClass(r)}" title="${esc(r.d.slice(5))} ${esc(r.quad || r.gate || '')}">${r && !r.gate ? (SH[r.quad] || '') : ''}</i>`).join('')}</div><div class="sub" style="margin-top:2px">${esc(vp.last && !vp.last.gate ? '今天' + vp.last.quad : '')}，${esc(sumTxt)}</div>`;
  const fdir = f.dir == null ? '数据不足' : f.dir === '中性' ? '信号混合' : f.dir;
  const sparkPts = f.rec.map(r => ({ d: r.d, v: r.v }));
  const fspark = sparkPts.length >= 2 ? sparkSvg(sparkPts, f.ratio < 0 ? 'var(--bear)' : f.ratio > 0 ? 'var(--bull)' : 'var(--ink2)', 92, 34, true, 0).replace('<svg ', '<svg class="sp" ') : '';
  const frTrend = L.describeRun(f.rec.map(r => ({ d: r.d, v: r.v }))).text;      // 具体、可核对：从哪到哪、中间到过什么、最近几天持平
  const capTop = cap.verdict && cap.verdict.short ? cap.verdict.short : cap.state.label.replace(/[（(].*$/, '');
  $('#band').innerHTML = `
    <div class="cell regime ${cls}"><div class="cl">市场状态<button class="q" data-about="regime" aria-label="这一块怎么判断">?</button></div>
      <div class="big">${esc(rg.label)}</div><div class="sub">${esc(rg.reason)}</div></div>
    <div class="cell pv"><div class="cl">${esc(c.symbol)} 价格与量价<button class="q" data-about="vp" aria-label="量价怎么看">?</button></div>
      <div class="px"><span class="p">${ps ? ab(ps.last.c) : '—'}</span><span class="c ${ps && ps.chg > 0 ? 'bull' : ps && ps.chg < 0 ? 'bear' : ''}">${ps ? pc(ps.chg, 2) : ''}</span></div>${seqHtml}</div>
    <div class="cell half"><div class="cl">基本面<button class="q" data-about="fund" aria-label="基本面怎么算">?</button></div>
      <div class="fund"><div><div class="big" style="color:${f.dir === '偏空' ? 'var(--bear)' : f.dir === '偏多' ? 'var(--bull)' : 'var(--ink)'}">${fdir}<small class="num">${f.ratio == null ? '' : pc(f.ratio, 0)}</small></div></div>${fspark}</div>
      <div class="sub">${esc(frTrend)}</div></div>
    <div class="cell half"><div class="cl">资金面<button class="q" data-about="capital" aria-label="资金面怎么看">?</button></div>
      <div class="big cap-top" style="font-size:clamp(20px,3.1vh,28px)">${esc(capTop)}</div>
      <div class="sub">${cap.verdict && cap.verdict.label ? esc(cap.verdict.label) + '。' : (cap.gsNet == null ? '高盛未进榜' : '高盛' + (cap.gsNet > 0 ? '净多' : '净空') + ab(cap.gsNet) + '手') + '，'}CFTC ${cap.cf ? '近' + cap.cf.weeks + '周' + Math.round(cap.cf.percentile) + '%分位，连续' + cap.cf.streak + '周' + (cap.cf.dir === 'up' ? '增加' : '减少') : '暂无'}</div></div>`;
  $('#sess').className = 'sess' + (closed() ? '' : ' open');
  $('#sess').innerHTML = closed() ? `<i></i>休市中<span>${mmdd(D.closure.reopenMs)} ${hhmm(D.closure.reopenMs)} 恢复</span>` : `<i></i>交易时段`;
}

/* ---------- 渲染：检查条 ---------- */
function checks() {
  const f = fundamentals(), cap = capital(), ps = priceStats(), c = C(), h = D.health, out = [];
  const fd = f.dir && f.dir !== '中性' ? f.dir : null, td = c.tech && c.tech !== '中性' ? c.tech : null;
  const st = c.structure && !c.structure.thin && c.structure.direction && c.structure.direction !== '中性' ? c.structure.direction : null;
  const set = [fd, td, st].filter(Boolean);
  let lv = 'note', tx = '未形成一致';
  if (set.length >= 2 && new Set(set).size > 1) { lv = 'warn'; tx = '三方背离'; } else if (set.length === 3) { lv = 'ok'; tx = '三方一致'; } else if (set.length === 0) tx = '都没有方向';
  let el, et, eb;
  if (closed()) { el = 'note'; et = '休市中'; eb = `<p>${esc(D.closure.closure.name)}休市，${D.closure.closure.from} 至 ${D.closure.closure.to}，${mmdd(D.closure.reopenMs)} ${hhmm(D.closure.reopenMs)} 恢复交易。</p>`; }
  else { const nx = D.events.filter(e => e.kind === 'usda' && e.ms - D.snapshotMs < 48 * 3600e3); el = nx.length ? 'note' : 'ok'; const mj = D.events.filter(e => (e.kind === 'usda' || e.kind === 'closure' || e.kind === 'reopen') && e.ms > D.snapshotMs), nm = mj[0]; et = nx.length ? nx[0].title : '48小时内无重大事件' + (nm ? ' · 下一个 ' + nm.label.slice(0, 5) : ''); eb = '<p>重大事件指 USDA 月度供需报告、季度库存、休市（北京时间）。</p>' + (mj.length ? '<h3>接下来的重大事件</h3>' + mj.map(evRow).join('') : '<p class="dim2">未来45天里日历里没有重大事件。</p>') + '<h3>近14天的周度数据（不算重大）</h3>' + (D.events.filter(e => e.kind === 'weekly' && e.ms - D.snapshotMs < 14 * 86400e3).map(evRow).join('') || '<p class="dim2">没有。</p>'); }
  out.push({ k: 'evt', t: '事件', lv: el, tx: et, body: eb });
  const nx = D.events.find(e => e.ms > D.snapshotMs && !(closed() && e.kind === 'reopen')) || D.events[0];
  const hl = !h ? 'na' : h.sync.state !== 'ok' ? (h.sync.state === 'degraded' ? 'note' : 'warn') : (h.bad > 0 || h.warn > 0 ? 'note' : 'ok');
  out.push({ k: 'hlth', t: '数据', lv: hl, tx: !h ? '无' : h.bad > 0 ? h.bad + '项不可用' : h.warn > 0 ? h.warn + '项降权' : '全部正常', body: h ? `<p>${esc(h.sync.label)}</p><p>不可用 ${h.bad} 项，降权或手动 ${h.warn} 项，缺席投票 ${h.missing.length} 项${h.missing.length ? '：' + esc(h.missing.join('、')) : ''}。</p>` : '' });
  const pb = posBand();
  out.push({ k: 'pos', t: '价格位置', lv: pb.band === 'unknown' ? (!ps || ps.pos == null ? 'na' : (ps.pos >= .9 || ps.pos <= .1) ? 'note' : 'ok') : (pb.band === 'mid' ? 'ok' : 'note'), tx: pb.band === 'unknown' ? (!ps || ps.pos == null ? 'K线不足' : ps.pos >= .8 ? '靠近近期高点' : ps.pos <= .2 ? '靠近近期低点' : '在近期区间中部') : pb.pct + '%分位·' + BANDNAME[pb.band].replace(/（.*$/, ''),
    body: pb.band === 'unknown' ? '<p>近260日历史不足200根，暂不下结论。</p>' : `<p>最新收盘在近 ${pb.n} 个交易日里处于 <b>${pb.pct}%</b> 分位（${BANDNAME[pb.band]}）。铁底(20%分位价) ${ab(pb.p20)}，铁顶(80%分位价) ${ab(pb.p80)}。${pb.ext ? `前 ${pb.ext} 日是用其他合约按重叠日比例换算的，不是本合约原始成交价。` : ''}</p><p>历史检验：低位带之后略好于基准（温和支持）；高位带没有“之后会跌”的证据。这只描述价格贵不贵，不是买卖信号。</p>` });
  return out;
}
const evRow = e => `<div class="cd"><span></span><span>${esc(e.title)}</span><span class="s">${esc(e.label)}</span></div>`;
function renderChecks() {
  const chs = checks();
  $('#checks').innerHTML = chs.map(x => `<button class="lp" data-lamp="${x.k}" aria-label="${esc(x.t)}：${LW[x.lv]}，${esc(x.tx)}">${lampSvg(x.lv)}<span class="k">${esc(x.t)}</span><span class="v">${esc(x.tx)}</span></button>`).join('') +
''
}

/* ---------- 渲染：左侧价格图 ---------- */
function trendRow(tr, name, unit) {
  const cell = c => !c.ok ? `<span class="pc na"><i>${c.label}</i><b>—</b></span>` : c.dir === 0 ? `<span class="pc"><i>${c.label}</i><b style="color:var(--ink2)">→持平</b></span>` : `<span class="pc"><i>${c.label}</i><b style="color:${colorOf(c.meaning)}">${arrow(c.dir)}${L.fmtChange(c.change, c.pct, 'pct', unit).text}</b></span>`;
  return `<div class="pr2"><span class="pnm">${name}</span>${tr.chips.map(cell).join('')}</div>`;
}
function renderChart() {
  if (S.view && S.view !== 'px') { renderView(); return; }
  const c = C(), ps = priceStats(), tp = trendOfBars('c', 1), to = trendOfBars('oi', 0);
  if (!ps) { $('#chart').innerHTML = `<div class="ch-h"><span class="t">价格与持仓</span></div><div class="dim2" style="padding:20px 0">${esc(c.symbol || '这个合约')}暂无 K 线数据。</div>`; return; }
  const posTxt = ps.pos == null ? '' : ps.pos >= .8 ? '靠近近期高点' : ps.pos <= .2 ? '靠近近期低点' : '在近期区间中部';
  $('#chart').innerHTML = `
    <div class="ch-h"><span class="t">${esc(c.symbol)} 价格与持仓</span><button class="q" data-about="price" aria-label="图怎么看">?</button></div>${viewTabs()}
    <div class="ch-r"><div class="seg" role="group" aria-label="显示多少天">${[40, 80, 120].map(n => `<button data-range="${n}" aria-pressed="${S.range === n}">${n}日</button>`).join('')}</div></div>
    <div class="why">红色是涨，绿色是跌；细线是20日均线，颜色是价格位置（青=低位带、黄=中间、橙=高位带、灰=历史不足200根）；虚线是铁底/铁顶；下方的柱子是持仓量。把鼠标放上去或用手指划过，可以看每一天。</div>
    <div class="ptr">${trendRow(tp, '价格', '')}${trendRow(to, '持仓', '手')}</div>
    <div class="kl" id="kl"></div>
    ${ps.pos == null ? `<div class="dim2" style="margin-top:8px;font-size:13px">只有 ${ps.n} 根K线（临近到期），区间位置不可靠。</div>` : `<div class="rng"><div class="l1"><span>最近20个交易日的高低之间</span><span><b>${posTxt}</b>（${Math.round(ps.pos * 100)}%）</span></div><div class="rtrack"><i style="left:${ps.pos * 100}%"></i></div><div class="l2"><span>低点 ${ab(ps.lo)}</span><span>高点 ${ab(ps.hi)}</span></div></div>`}`;
  $('#chart').insertAdjacentHTML('beforeend', posBlockHtml());
  drawChart();
}
function planChartLines() {   // 持仓时在K线上画开仓价、止损价、移动止盈触发价
  try { const t = planOpen(acctGet().trades); if (!t) return []; const s = planSnap(), sd = t.side > 0 ? 1 : -1, L = [{ v: t.entryPx, n: '开仓', c: 'var(--ink)' }, { v: t.entryPx * (1 - sd * TPLAN.STOP / 100), n: '止损', c: 'var(--amber)' }];
    if (s.mg && s.mg.peakR >= TPLAN.ACT) L.push({ v: s.hold.peak * (1 - sd * TPLAN.TRAIL / 100), n: '移动止盈', c: 'var(--amber)' }); return L; } catch (_) { return []; }
}
function drawChart() {
  const box = $('#kl'); if (!box) return;
  const bars = C().kline || [], N = Math.min(S.range, bars.length), b = bars.slice(-N), off = bars.length - N;
  const W = box.clientWidth || 560, H = box.clientHeight || 220, mr = 98, ml = 4, step = (W - mr - ml) / N, cw = Math.max(1.4, step * .62);
  const volH = Math.max(30, H * .2), pH = H - volH - 6;
  const ois = b.map(x => x.oi), oHi = Math.max(...ois), oLo = Math.min(...ois);
  let hi = Math.max(...b.map(x => x.h)), lo = Math.min(...b.map(x => x.l)); { const bv = beOf(S.key); if (bv != null && bv > lo * .93 && bv < hi * 1.07) { hi = Math.max(hi, bv); lo = Math.min(lo, bv); } const t8 = posBand().t80; if (t8 != null && t8 > lo * .93 && t8 < hi * 1.07) { hi = Math.max(hi, t8); lo = Math.min(lo, t8); } } const PL = planChartLines().filter(l => l.v > lo * .93 && l.v < hi * 1.07); PL.forEach(l => { hi = Math.max(hi, l.v); lo = Math.min(lo, l.v); }); const pad = (hi - lo) * .06 || 1; hi += pad; lo -= pad;
  const y = v => 6 + (hi - v) / (hi - lo) * (pH - 6), x = i => ml + i * step + step / 2;
  const yo = v => pH + 6 + (1 - (v - oLo) / ((oHi - oLo) || 1)) * (volH - 8);
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(C().symbol)}日K线和持仓量">`;
  const ps = priceStats();
  if (ps && ps.hi != null) [[ps.hi, '近20日高'], [ps.lo, '近20日低']].forEach(([v]) => { if (v <= hi && v >= lo) s += `<line x1="${ml}" x2="${W - mr}" y1="${y(v)}" y2="${y(v)}" stroke="var(--ink3)" stroke-dasharray="4 4"/><text class="lv" x="${W - mr + 5}" y="${y(v) + 4}">${ab(v)}</text>`; });
  const beV = beOf(S.key);
  if (beV != null && beV <= hi && beV >= lo) s += `<line x1="${ml}" x2="${W - mr}" y1="${y(beV)}" y2="${y(beV)}" stroke="${BEC}" stroke-dasharray="6 3" stroke-width="1.4"/><text class="lv" x="${W - mr + 5}" y="${y(beV) + 4}" style="fill:${BEC}">平衡 ${ab(beV)}</text>`;
  PL.forEach(l => { s += `<line x1="${ml}" x2="${W - mr}" y1="${y(l.v)}" y2="${y(l.v)}" stroke="${l.c}" stroke-dasharray="3 3" stroke-width="1.5"/><text class="lv" x="${W - mr + 5}" y="${y(l.v) + 4}" style="fill:${l.c}">${l.n} ${ab(l.v)}</text>`; });
  const pbd = posBand(), rbs = ribbonBandsProto();
  if (bars.length >= 20) { let prev = null; for (let i = 0; i < N; i++) { const gi = off + i; if (gi < 19) continue; const v = y(bars.slice(gi - 19, gi + 1).reduce((a, z) => a + z.c, 0) / 20), cur = [x(i), v]; if (prev) s += `<line x1="${prev[0]}" y1="${prev[1]}" x2="${cur[0]}" y2="${cur[1]}" stroke="${RB[rbs[gi]] || RB.unknown}" stroke-width="1.8"/>`; prev = cur; } }
  if (pbd.p20 != null) [[pbd.p80, '260天铁顶', RB.high], [pbd.p20, '260天铁底', RB.low], ...(pbd.t80 != null ? [[pbd.t80, '10年铁顶', '#e05d9b']] : [])].forEach(([v, nm, col]) => { if (v <= hi && v >= lo) s += `<line x1="${ml}" x2="${W - mr}" y1="${y(v)}" y2="${y(v)}" stroke="${col}" stroke-dasharray="2 4" stroke-width="1.2"/><text class="lv" x="${W - mr + 5}" y="${y(v) + 4}" style="fill:${col}">${nm} ${ab(v)}</text>`; });
  b.forEach((z, i) => { const up = z.c >= z.o, col = up ? 'var(--bull)' : 'var(--bear)', xx = x(i); s += `<line x1="${xx}" x2="${xx}" y1="${y(z.h)}" y2="${y(z.l)}" stroke="${col}" stroke-width="1"/><rect class="cd" x="${xx - cw / 2}" y="${Math.min(y(z.o), y(z.c))}" width="${cw}" height="${Math.max(1, Math.abs(y(z.o) - y(z.c)))}" fill="${col}"/>`; });
  const oiPts = b.map((z, i) => x(i) + ',' + yo(z.oi)).join(' ');
  s += `<line x1="${ml}" x2="${W - mr}" y1="${pH + 3}" y2="${pH + 3}" stroke="var(--line)"/><polyline points="${oiPts}" fill="none" stroke="var(--focus)" stroke-width="1.5"/><text class="lv" x="${W - mr + 5}" y="${yo(b[b.length - 1].oi) + 4}" style="fill:var(--focus)">${(b[b.length - 1].oi / 1e4).toFixed(0)}万</text>`;
  s += `<line id="xh" x1="0" x2="0" y1="0" y2="${H}" stroke="var(--focus)" style="display:none"/><rect id="hit" x="0" y="0" width="${W}" height="${H}" fill="transparent"/></svg><div class="tip" id="tip" style="display:none"></div>`;
  box.innerHTML = s;
  const hit = $('#hit'), xh = $('#xh'), tip = $('#tip');
  const mv = e => { const r = box.getBoundingClientRect(), cx = (e.touches ? e.touches[0].clientX : e.clientX) - r.left; let i = Math.floor((cx / (r.width || W) * W - ml) / step); i = Math.max(0, Math.min(N - 1, i)); const z = b[i]; xh.setAttribute('x1', x(i)); xh.setAttribute('x2', x(i)); xh.style.display = ''; tip.style.display = ''; tip.textContent = `${z.d.slice(5)}  收 ${ab(z.c)}  高 ${ab(z.h)}  低 ${ab(z.l)}  持仓 ${(z.oi / 1e4).toFixed(1)}万`; };
  const out = () => { xh.style.display = 'none'; tip.style.display = 'none'; };
  hit.addEventListener('pointermove', mv); hit.addEventListener('pointerleave', out); hit.addEventListener('pointerdown', mv);
}

/* ---------- 渲染：趋势墙(布局由 planGrid 在运行时按真实尺寸决定) ---------- */
let TILES = [], GRID = null, PLAN = null, SUMS = [];
function pendHtml(list, spanStyle, si, title, merged, cellH) {
  const row = t => {
    const val = t.tr.last ? esc(L.fmtNum(t.tr.last.v, t.unit).replace(' 万手', '万')) : '—';
    const tail = t.tr.n >= 3 ? t.tr.chips.map(c => !c.ok ? '<b class="na">—</b>' : c.dir === 0 ? '<b>→</b>' : `<b style="color:${colorOf(c.meaning)}">${arrow(c.dir)}${L.fmtChange(c.change, c.pct, t.show, t.unit).text}</b>`).join('') : `<span class="pc">${t.tr.n}点</span>`;
    return `<div class="pr${t.tr.n >= 3 ? ' tr3' : ''}"><span class="pn" title="${esc(t.name)}">${esc(t.tiny || t.short || t.name)}</span><span class="pv num">${val}</span>${t.tr.n >= 3 ? `<span class="pa">${tail}</span>` : tail}</div>`;
  };
  return `<button class="tile pend" data-pend="1" data-sum="${si == null ? '' : si}"${spanStyle || ''} aria-label="${list.length}个指标：${esc(title || '历史累积中')}，点击查看"><div class="t1"><span class="n">${esc(title || '历史累积中')}${merged && merged.length ? `<small>（含${esc(merged.join('、'))}）</small>` : ''}</span></div><div class="pl">${(cellH ? (() => { const f = L.fitSummary(list, cellH); return f.shown.map(row).join('') + (f.hidden > 0 ? `<div class="pr more-n"><span class="pn">还有${f.hidden}项，点开看</span></div>` : ''); })() : list.map(row).join(''))}</div></button>`;
}
function renderWall(anim) {
  TILES = tiles();
  const nm = { short: '短', mid: '中', long: '长' };
  $('#wall').innerHTML = `<div class="wh"><span class="t">趋势墙</span><div class="seg" role="group" aria-label="曲线显示多久">${['short', 'mid', 'long'].map(k => `<button data-span="${k}" aria-pressed="${S.span === k}">${nm[k]}</button>`).join('')}</div>
      <button class="q" data-about="wall" aria-label="趋势墙怎么看">?</button><span class="hint">左边条：现在的信号。曲线和箭头：最近的趋势。颜色：对多空的意义</span></div>
    <div class="why" style="padding:6px 20px">每一格是一个指标。箭头是数值是升还是降，颜色说明这对价格意味着什么（库存上升对价格是偏空，所以是绿色；猪粮比上升是偏多，所以是红色）。三个周期方向一致的格子底色更深。</div>
    <div class="tiles" id="tiles"></div>`;
  layoutWall(anim);
}
function layoutWall(anim) {
  const box = $('#tiles'); if (!box) return;
  const narrow = matchMedia('(max-width:899px)').matches;
  const blocks = L.groupByBlock(TILES, 3);
  SUMS = [];
  if (narrow) {      // 手机：分节标题(供给/需求/结构与资金) + 该块的趋势格 + 该块的"历史累积中"汇总块
    box.className = 'tiles'; box.style.cssText = '';
    let html = '', k = 0;
    blocks.forEach(b => {
      html += `<div class="bh"><span>${esc(b.name)}</span><i>${b.trending.length + b.pending.length}项</i></div>` + b.trending.map(t => tileHtml(t, k++, anim)).join('');
      if (b.pending.length) { SUMS.push({ items: b.pending, title: '历史累积中' }); html += pendHtml(b.pending, '', SUMS.length - 1, '历史累积中'); }
    });
    box.innerHTML = html; GRID = { cols: 1, more: 0 }; return;
  }
  const W = box.clientWidth, H = box.clientHeight;
  const plan = L.planBlocks(W, H, blocks.map(b => ({ key: b.key, trending: b.trending.length, pending: b.pending.length })));
  PLAN = plan;
  box.className = 'tiles blocks'; box.style.cssText = '';
  if (plan.empty) { box.innerHTML = '<div class="empty" style="padding:14px">窗口太矮，放不下趋势墙，请把窗口拉高一点或用“证据”页签查看。</div>'; return; }
  let html = '', k = 0;
  blocks.forEach((b, bi) => {
    const pb = plan.blocks[bi]; if (pb.dropped) return;
    // 汇总格里的内容：这个块被折叠的趋势格 + 这个块的累积中指标 (+ 被并进来的后面的块的全部指标)
    const items = b.trending.slice(pb.showTrend).concat(b.pending);
    const merged = []; plan.blocks.forEach((q, qi) => { if (q.dropped && q.mergeInto === bi) { merged.push(blocks[qi].name); items.push(...blocks[qi].trending, ...blocks[qi].pending); } });
    const shown = b.trending.slice(0, pb.showTrend), cells = shown.length + (pb.summary ? 1 : 0), span = L.lastSpan(cells, plan.cols);
    let cellsHtml = shown.map(t => tileHtml(t, k++, anim)).join('');
    if (pb.summary) {
      const title = b.trending.length > pb.showTrend || merged.length ? '其余指标' : '历史累积中';
      SUMS.push({ items, title: title + (merged.length ? '（含' + merged.join('、') + '）' : '') }); const si = SUMS.length - 1;
      cellsHtml += pendHtml(items, span > 1 ? ` style="grid-column:span ${span}"` : '', si, title, merged, Math.floor(plan.tileH * pb.rows - 2));
    } else if (shown.length && span > 1) cellsHtml = cellsHtml.replace(/(<button class="tile[^"]*" data-tile="[^"]*")(?![\s\S]*<button class="tile)/, `$1 style="grid-column:span ${span}"`);
    html += `<div class="blk" style="flex:${pb.rows} 1 0"><div class="rail" title="${esc(b.name)}"><span>${esc(b.name + (merged.length ? '+' + merged.join('+') : ''))}</span></div><div class="bg" style="grid-template-columns:repeat(${plan.cols},minmax(0,1fr));grid-template-rows:repeat(${pb.rows},minmax(0,1fr))">${cellsHtml}</div></div>`;
  });
  box.innerHTML = html; GRID = { cols: plan.cols, more: plan.blocks.reduce((a, b) => a + (b.folded || 0), 0) };
}

/* ---------- 抽屉 ---------- */
let lastFocus = null;
function openSheet(title, html, tabs, active) {
  lastFocus = document.activeElement; $('#shT').textContent = title;
  const tb = $('#shTabs'); if (tabs) { tb.style.display = ''; tb.innerHTML = tabs.map(t => `<button role="tab" data-tab="${t[0]}" aria-selected="${t[0] === active}">${t[1]}</button>`).join(''); } else { tb.style.display = 'none'; tb.innerHTML = ''; }
  $('#shB').innerHTML = html; $('#shB').scrollTop = 0; $('#sheet').classList.add('on'); $('#sheet').setAttribute('aria-hidden', 'false'); $('#scrim').classList.add('on');
  setTimeout(() => $('#shX').focus(), 30);
}
function closeSheet() { $('#sheet').classList.remove('on'); $('#sheet').setAttribute('aria-hidden', 'true'); $('#scrim').classList.remove('on'); if (lastFocus && lastFocus.focus) lastFocus.focus(); }
const TABS = [['drivers', '驱动'], ['supply', '供给'], ['demand', '需求'], ['capital', '资金'], ['data', '数据'], ['input', '录入']];
const short = l => { const M = [[/南美.*天气/, '南美天气与产量'], [/作物生长状况/, '美国作物生长'], [/库存消费比/, '美豆库消比'], [/国内豆粕供应松紧/, '国内供应松紧'], [/到港/, '到港与进口'], [/压榨毛利/, '压榨毛利'], [/人民币/, '人民币汇率'], [/雷亚尔/, '巴西雷亚尔'], [/收获进度/, '美豆收获进度'], [/美豆播种/, '美豆播种进度'], [/巴西.*播种/, '巴西播种进度'], [/出口销售/, '美豆出口销售'], [/现货基差/, '现货基差'], [/量价/, '量价关系'], [/月差/, '月差'], [/猪粮比/, '猪粮比'], [/饲料/, '饲料库存天数'], [/肉鸡/, '肉鸡利润'], [/豆菜粕/, '豆菜粕价差']]; for (const [r, t] of M) if (r.test(l)) return t; return l.replace(/[（(].*?[）)]/g, '').replace(/\s*×[\d.]+/, '').trim(); };
function voteRow(v) {
  const sig = v.signal === 1 ? ['偏多', 'bull'] : v.signal === -1 ? ['偏空', 'bear'] : v.signal === 0 ? ['中性', 'mid'] : ['无信号', 'mid'];
  const w = v.weight !== v.baseWeight ? `权重 ${Math.round(v.weight * 100) / 100}（基础 ${v.baseWeight} × 数据质量 ${v.q}${v.qwhy ? '，' + esc(v.qwhy) : ''}）` : `权重 ${v.weight}`;
  return `<div class="cd"><span></span><span><span class="chipx ${sig[1]}">${sig[0]}</span><b style="font-weight:500">${esc(short(v.label))}</b> <span class="dim" style="font-size:12px">${w}</span></span><span class="s">${esc(v.note || '没有记录理由')}</span></div>`;
}
function coverageHtml() {
  const cv = D.capitalCoverage; if (!cv || !cv.seats) return '';
  const names = ['高盛期货', '摩根大通', '瑞银期货', '中粮期货', '国投期货'].filter(n => cv.seats[n]);
  const row = n => { const c = cv.seats[n], tot = c.exact + c.estimated + c.absent, use = tot ? (c.exact + c.estimated) / tot : 0, ex = tot ? c.exact / tot : 0, lv = ex >= .8 ? 'ok' : use >= .5 ? 'note' : 'warn';
    return `<tr><td>${n.replace('期货', '')}</td><td class="n">${c.exact}</td><td class="n">${c.estimated}</td><td class="n">${c.absent}</td><td class="n ${lv === 'warn' ? 'no' : ''}">${Math.round(use * 100)}%</td></tr>`; };
  const weak = names.filter(n => { const c = cv.seats[n], tot = c.exact + c.estimated + c.absent; return tot && c.exact / tot < .5; }).map(n => n.replace('期货', ''));
  return `<h3>席位历史覆盖（${esc(cv.firstDay || '—')} ~ ${esc(cv.lastDay || '—')}，${cv.files || '—'} 个交易日）</h3>
    <table class="tb3x tbcv"><thead><tr><th>席位</th><th>精确</th><th>下限估计</th><th>没进榜</th><th>有数据</th></tr></thead><tbody>${names.map(row).join('')}</tbody></table>
    <p class="dim2" style="margin-top:8px"><b>精确</b>：买卖两边都进了前20，净持仓是真值。<b>下限估计</b>：只进了一边前20，另一边用第20名顶替，净持仓是下限。<b>没进榜</b>：两边都没进前20，不记0。</p>
    ${weak.length ? `<p class="dim2">${esc(weak.join('、'))}大部分日子精确值缺失：趋势判断样本少、外资5日净变化里这几家常缺席（页面会写「按0算」），外资提示主要靠覆盖好的席位，别把这几家的历史曲线当完整序列读。</p>` : ''}`;
}
function tabBody(k) {
  const c = C();
  if (k === 'drivers') { const f = fundamentals(); return `<h3>基本面净倾向 ${f.ratio == null ? '—' : pc(f.ratio, 0)}，${esc(f.dir || '—')}，${f.n || '—'} 项有效</h3><p>下面是各个指标当前的投票（供给和需求计入净倾向；市场结构不计入）。<b>明细按手上的 latest.json 重算，可能和线上最新的净倾向有几个点的差别。</b></p>` + c.votes.map(voteRow).join(''); }
  if (k === 'supply' || k === 'demand') { const side = k; const d = c.dims && c.dims[side]; return `<p>${d ? `这一侧净倾向 <b class="num">${pc(d.ratio, 0)}</b>，${d.n} 项有信号，共 ${d.total} 项。` : ''}</p>` + c.votes.filter(v => v.side === side).sort((a, b) => b.weight - a.weight).map(voteRow).join(''); }
  if (k === 'capital') {
    const cap = capital(), m = D.capital && D.capital.members || {}, rows = ['高盛期货', '摩根大通', '瑞银期货', '中粮期货', '国投期货'];
    const vd = cap.verdict;
    return (vd ? `<h3>${esc(vd.label)}</h3>` + (vd.lines || []).map(l => `<p>${esc(l)}</p>`).join('') + `<h3>历史检验与局限</h3><ul>` + (vd.evidence || []).map(l => `<li>${esc(l)}</li>`).join('') + `<li>水平判断(高盛≥12万手且CFTC≥90分位=拥挤)：${esc(cap.state.label)}；阈值来自参考文档，未回测。</li></ul>` : `<h3>${esc(cap.state.label)}</h3><p>高盛净多 ≥ 12 万手算高位，CFTC 近 156 周分位 ≥ 90 算拥挤。阈值来自参考文档，暂定，未回测。</p>`) + `
      <h3>龙虎榜（${esc(D.capital ? D.capital.date : '—')}，主力合约 ${esc(D.capital && D.capital.mainContract ? D.capital.mainContract.symbol : '—')}）</h3>
      <table class="tb3x"><thead><tr><th>席位</th><th>净持仓（手）</th><th>当日净持仓变化</th></tr></thead><tbody>${rows.map(n => { const x = m[n]; if (!x || x.net == null) return `<tr><td>${n.replace('期货', '')}</td><td colspan="2" class="dim">未进榜（不等于0）</td></tr>`; const mean = x.change > 0 ? (x.net < 0 ? '净空减少' : '净多增加') : x.change < 0 ? (x.net < 0 ? '净空增加' : '净多减少') : ''; return `<tr><td>${n.replace('期货', '')}</td><td class="n">${x.net > 0 ? '净多 ' : '净空 '}${ab(x.net)}</td><td class="n">${sg(x.change)}${mean ? '（' + mean + '）' : ''}</td></tr>`; }).join('')}</tbody></table>
      ${coverageHtml()}
      <h3>要小心</h3><ul><li>龙虎榜是收盘后才发布的前一日数据（T+1）；席位历史按仓库里的龙虎榜文件回填（高盛/瑞银只进一边前20时是下限估计，两边都没进前20记「没进榜」而不是0），之后每天线上累积。</li><li>高盛席位是“代客”集合持仓，不是高盛自营。</li><li>CFTC 是 CBOT 豆粕（美国市场）的管理基金，不是大商所，与国内高盛是否共振没有验证过。</li></ul>`;
  }
  if (k === 'data') {
    const h = D.health, ico = { ok: 'ok', degraded: 'note', pending: 'na', event: 'na', nodata: 'warn' };
    const rows = (h && h.rows || []).filter(r => r.kind === 'indicator');
    const mx = Math.max(...Object.values(SER).filter(s => !s.ctx).map(s => s.pts.length));
    const chk = L.selfCheck({ series: SER, cftcHasHistoryField: !!(D.cftc && 'history' in D.cftc), scoring: D.scoring, basisSame: D.basisSame, now: D.snapshotMs, latestDate: Date.parse(D.generatedAt || '') || null });
    const ST = { ok: ['ok', '通过'], todo: ['warn', '需要你做'], wait: ['note', '累积中'], note: ['note', '留意'], unknown: ['na', '这里查不了'] };
    const selfHtml = `<h3>部署自检（每一项都由数据判定）</h3>` + chk.map(x => `<div class="cd">${lampSvg(ST[x.status][0])}<span><b style="font-weight:500">${esc(x.title)}</b> <span class="dim" style="font-size:12px">${ST[x.status][1]}</span></span><span class="s">${esc(x.detail)}</span>${x.action ? `<span class="s" style="color:var(--ink);font-weight:500">你要做：${esc(x.action)}</span>` : ''}</div>`).join('');
    return selfHtml + `<h3>同步</h3><p>${esc(h.sync.label)}</p><p>缺席的投票：${esc(h.missing.join('、') || '无')}。</p>
      <h3>历史累积情况（趋势墙每一格有多少个点）</h3>${Object.entries(SER).filter(([, s]) => !s.ctx || s.ctx === S.key).map(([id, s]) => { const n = s.freq === 'seasonal-daily' ? L.currentRun(s.pts, 10).length : s.pts.length; return `<div class="cd">${lampSvg(n >= 8 ? 'ok' : n >= 2 ? 'note' : 'warn')}<span>${esc(s.name)}<span class="dim">，${s.freq === 'seasonal-daily' ? '当前窗口' : s.freq}</span></span><span class="s">${n} 个点，最新 ${esc(s.pts[s.pts.length - 1].d)}${n < 3 ? '，趋势还画不出来' : ''}</span></div>`; }).join('')}
      <h3>每个指标的新鲜度</h3>${rows.map(r => `<div class="cd">${lampSvg(ico[r.state] || 'na')}<span><b style="font-weight:500">${esc(r.name)}</b>，${esc(r.label)}</span><span class="s">${esc((r.detail || '').slice(0, 110))}</span></div>`).join('')}
      <h3>数据时间与来源</h3><p>趋势墙和基本面净倾向来自 data/history（序列到 ${D.seriesAsOf ? D.seriesAsOf.history.slice(5) : '—'}，每日系统记录到 ${D.seriesAsOf ? D.seriesAsOf.systems.slice(5) : '—'}）；投票明细、徽标、龙虎榜、健康度来自 data/latest.json（${(D.generatedAt || '').slice(5, 16).replace('T', ' ')} UTC），由后台的评分引擎（engine.html，即原来的完整页面）算出，评分逻辑只有这一份；汇率、天气等指标由引擎在打开页面时联网取。页面每 10 分钟自动重取一次，切回标签页时如果数据超过 10 分钟也会重取。每日系统记录里 v100 起的值是“供需均衡”之后的口径，和 v99 及更早的值不是同一把尺子，趋势只看同口径的相邻几天。</p>`;
  }
  if (k === 'input') return `<p>这些是手动输入。自动抓取到的值已经填在里面；改某一项并按回车或点到别处，<b>那一项就按你的值重新计分</b>（评分引擎会记住，下次打开仍然有效）；清空则恢复自动值。完整的粘贴录入、截图识别等功能在 <a href="engine.html" target="_blank" rel="noopener">旧版完整页面</a>。</p>` + D.indicators.map(i => `<div class="inp" data-key="${esc(i.key)}"><span>${esc(i.title)}<span class="dim"> ${esc(i.unit || '')}</span></span><input inputmode="decimal" value="${esc(i.input || '')}" data-orig="${esc(i.input || '')}" aria-label="${esc(i.title)}"><span class="s">${esc(i.source || '')}，${esc(i.freq || '')}，${esc(i.badge || '')}${i.noVote ? '，不计分' : ''}</span></div>`).join('');
  return '';
}
function openTab(k) { const t = TABS.find(x => x[0] === k); openSheet('证据：' + t[1], tabBody(k), TABS, k); }
function tileSeatNote(t) {   // 研究页的高盛(净持仓、按自然日对比)和交易计划的外资5日(近5个交易日、只算真实一边)口径不同：把后者的数字摆在这里对照
  const nm = { gs: '高盛期货' }[t.id], m = nm && D.capital && D.capital.members && D.capital.members[nm], c5 = m && m.history && m.history.change5;
  if (!c5 || typeof c5.change !== 'number') return '';
  const how = c5.basis === 'long' ? '只算多单的真实变化' : c5.basis === 'short' ? '只算空单的真实变化' : c5.approx ? '估算(净持仓差)' : '净持仓变化';
  return `<p class="dim2" style="margin-top:10px"><b>交易计划用的口径</b>：近5个交易日（${esc(String(c5.from).slice(5))} → ${esc(String(c5.to).slice(5))}），${how}，<b>${sg(c5.change)}</b> 手。上表是净持仓(多−空；空单常是第20名顶替的下限估计)按自然日(1周/1月/3月)对比，起点和口径都不同，所以数字不同，不是数据错了。</p>`;
}
function openTile(id) {
  const t = TILES.find(x => x.id === id); if (!t) return;
  const tr = t.tr, pts = t.freq === 'seasonal-daily' ? L.currentRun(t.pts, 10) : t.pts.slice(-(WIN[t.freq] || WIN.daily).long);
  const svg = pts.length >= 2 ? sparkSvg(pts, 'var(--ink)', 520, 210, false, 0).replace('stroke-width:1.9', '') : '';
  const row = c => !c.ok ? `<tr><td>${c.label}</td><td colspan="3" class="dim">没有可比的点（容差内找不到${c.label}前的数据）</td></tr>` : `<tr><td>${c.label}</td><td class="n">${esc(c.from.d)}：${L.fmtNum(c.from.v, t.unit)}</td><td class="n" style="color:${colorOf(c.meaning)}">${arrow(c.dir)} ${sg(c.change, Math.abs(c.change) < 10 ? 2 : 0)}${c.pct != null ? '（' + pc(c.pct, 1) + '）' : ''}</td><td>${c.meaning > 0 ? '偏多' : c.meaning < 0 ? '偏空' : '—'}</td></tr>`;
  openSheet(t.name, `<div class="dbig">${svg || '<div class="dim2">历史累积中，画不出趋势。</div>'}</div>
    <p>最新 <b class="num">${last(t)}</b> ${esc(t.unit)}，${esc(tr.last ? tr.last.d : '—')}，频率 ${esc(t.freq === 'seasonal-daily' ? '日度(只在建议交易窗口内有数据)' : t.freq)}，共 ${pts.length} 个点。</p>
    <table class="tb3x"><thead><tr><th>周期</th><th>对比的点</th><th>变化</th><th>对价格</th></tr></thead><tbody>${tr.chips.map(row).join('')}</tbody></table>
    ${tileSeatNote(t)}
    <p class="dim2" style="margin-top:12px">${t.pol === 0 ? '这个指标升降本身不直接对应多空（反映的是拥挤程度）。' : t.pol > 0 ? '数值上升对价格偏多，下降偏空。' : '数值上升对价格偏空，下降偏多。'}${t.note ? ' ' + esc(t.note) + '。' : ''}</p>`);
}
const last = t => { const p = t.tr.last; return p ? L.fmtNum(p.v, t.unit) : '—'; };
function openLamp(k) { const x = checks().find(y => y.k === k); openSheet(x.t + '：' + x.tx, `<p><span class="chipx ${x.lv === 'warn' ? 'bull' : 'mid'}">${LW[x.lv]}</span></p>${x.body}`); }
function openMore(si) { const sm = SUMS[+si] || SUMS[0] || { items: [], title: '其余指标' }; openSheet(sm.title, sm.items.map(t => `<div class="cd"><span></span><span><b style="font-weight:500">${esc(t.name)}</b> <span class="num">${last(t)}</span> ${esc(t.unit)}</span><span class="s">${t.tr.chips.filter(c => c.ok).map(c => c.label + arrow(c.dir) + (c.dir === 0 ? '持平' : L.fmtChange(c.change, c.pct, t.show, t.unit).text)).join('　') || '历史累积中，已' + t.tr.n + '个点'}</span></div>`).join('') || '<p>没有。</p>'); }
const ABOUT = {
  regime: ['市场状态怎么判断', `<p>用选中合约的日K线判断，不看资金面以外的任何主观因素。</p><ul><li><b>震荡市</b>：趋势强度 ADX 低于 20，价格来回波动。</li><li><b>趋势市 · 上行/下行</b>：ADX 不低于 25，并且上升力量（+DI）和下降力量（−DI）差距至少 5，价格也在 20 日均线的同一侧。</li><li><b>方向待定</b>：ADX 在 20 到 25 之间，或 ADX 够高但上升下降的力量差不多、方向不清。</li><li><b>资金市迹象</b>：外资多头拥挤，且价格在涨（突破前 20 日高点，或强趋势且方向清楚地向上），且基本面没有明显偏多（净倾向低于 +22%）。三条同时满足才算。</li></ul><p>ADX、+DI、−DI 用通用的 Wilder 方法（14 日），已经和行业通用的 TA-Lib 逐点对拍过。<b>25 和 20 是教科书上的通用阈值，没有针对豆粕标定；资金市的条件来自参考文档，没有回测。</b>所以它描述的是“现在盘面的样子”，不是预测。</p><p>文档里“美豆不涨豆粕涨”这一条目前判断不了：CBOT 豆粕只有一个最新价，没有历史序列。点“资金”页签可以看具体的龙虎榜和 CFTC。</p>`],
  vp: ['量价怎么看', `<p>量价关系看最近 5 个交易日的价格变化和持仓量变化，沿用现有页面的同一套算法，不另造。</p><ul><li><b>增仓上涨</b>：新多头进场，上涨有增量资金确认，偏多。</li><li><b>增仓下跌</b>：新空头进场，下跌有增量资金确认，偏空。</li><li><b>减仓上涨</b>：更多是空头回补，上涨缺乏新资金确认，不判方向。</li><li><b>减仓下跌</b>：多头离场为主，下跌缺乏新空头，动能在衰减，不判方向。</li></ul><p>顶部那排小方块是最近 5 天，从左到右从旧到新：深红增仓上涨，深绿增仓下跌，浅红减仓上涨，浅绿减仓下跌，灰色没有明显变化。</p><p>持仓量在合约临近交割时会机械地下降，所以现有算法设了三道门槛（持仓不低于 50 万手、不低于近 120 日峰值的 60%、距合约月至少 45 天），没过就不计分。</p>`],
  fund: ['基本面怎么算', `<p>每个供需指标投一票（红偏多、绿偏空），按权重加权得到“净倾向”。净倾向进入 ±22% 的区间才算有方向，否则是“信号混合”。权重含天气开关和数据质量折扣。</p><p>市场结构（基差、月差、量价）来自价格本身，不计入这个净倾向。</p><p>这里的方向和数字取自每日系统记录的最新一天，和线上页面一致；小曲线是最近每天的记录。</p>`],
  capital: ['资金面怎么看', `<p>龙虎榜是收盘后才发布的前一日数据；固定看主力合约（净空头榜持仓合计最大的合约），不跟你选的合约走，因为非主力合约几乎没人持仓。</p><p>高盛净多 ≥ 12 万手算高位；CFTC 管理基金净多的近 156 周分位 ≥ 90 算拥挤；两者都满足是“外资多头拥挤”。高盛当日净多减少 ≥ 2 万手，优先显示“撤退预警”。数据缺失时写“数据不足”，不写中性。阈值来自参考文档，暂定，未回测。</p>`],
  price: ['图怎么看', `<p>红涨绿跌的 K 线，细线是 20 日均线，虚线是最近 20 个交易日的最高和最低。图下方金色的线是持仓量。</p><p>“最近 20 个交易日的高低之间”这条带：把近 20 天的最低价当作 0%，最高价当作 100%，今天的收盘价落在中间哪个位置。越靠右越贴近近期高点，越靠左越贴近近期低点。</p>`],
  wall: ['趋势墙怎么看', `<p>每一格是一个指标。<b>曲线</b>是最近一段时间的走势，<b>箭头</b>是数值升还是降，<b>颜色</b>是这个变化对价格意味着什么（库存升是偏空，所以是绿色）。左边的竖条是它现在的信号。</p><p>三个周期（周、月、季）都同向的格子会有“同升/同降”的标记和更深的底色；长期涨、最近一周跌是“回落”，长期跌、最近一周涨是“反弹”。</p><p>周期按日历时间算，缺了几周也不会算错；周度出口销售波动很大，用 4 周均值；压榨毛利和月差只在建议交易窗口内有数据，只看当前这一段。</p><p>右上角“短/中/长”切换曲线显示多久。有的指标历史还在累积，会写“历史累积中”，不会画假线。</p>`]
};
ABOUT.price[1] += `<p><b>紫色虚线 = 盈亏平衡价</b>：用豆二、豆油盘面价和压榨费150元算出来的“油厂压榨不亏的豆粕价”。盘面在它上方，油厂有利润；跌到它下方，油厂亏损，会减产，所以它常被当作底部参照。它不是买卖信号，盘面可以长期低于它。</p>`;
ABOUT.pos = ['价格位置怎么看', `<p>阴影带是每一天往回看 260 个交易日的 <b>20%～80% 分位价</b>：下沿“铁底”（有 20% 的日子比它便宜），上沿“铁顶”（80% 的日子比它便宜）。<b>它们不是历史最高/最低价</b>，会随最近一年的价格走，价格涨起来铁顶也会跟着抬。</p><p>线的颜色：青=在铁底以下，橙=在铁顶以上，灰=中间。下面两条横带是现价在近260日、近10年里的百分位。</p><p>历史检验：低位带之后表现略好于基准，只是温和支持；高位带之后<b>没有“会跌”的证据</b>。它只说明现在贵不贵，不是买卖信号。价格用主力连续价，换月缺口没修正。</p>`];
ABOUT.sea = ['同期规律怎么看', `<p>每根柱子是该月份在历年里“上涨的年份占比”。默认看现货价格，可切到期货（换月修正后的月度涨跌）。下方数字是历年平均涨跌。</p><p>稳定性分三档：前后两半样本方向相反=不稳；同向但胜率或显著性不够=一般；同向且胜率、显著性都够=较稳。柱子越淡越不稳。</p><p>季节性只描述“历史上通常怎样”，不预测今年，样本只有9~10年。</p>`];
ABOUT.cost = ['成本锚怎么看', `<p>所有数字都是<b>豆粕价格（元/吨）</b>：豆的成本按出粕率78.5%，扣掉豆油副产品（出油率18.5%）和压榨费150元换算而来。</p><ul><li><b>盈亏平衡价</b>：只用豆二、豆油盘面价算，最可靠。盘面高于它=压榨有利润；低于它=亏损、油厂减产，下方有支撑。</li><li><b>进口成本带</b>：用CBOT大豆+升贴水（±50美分）+关税+增值税9%+港杂100元推算。美豆关税13%，成本偏高，说明盘面是按更便宜的巴西豆定价的。</li><li>升贴水是4月快照，没有历史、无法回测；增值税、港杂是经验值未核实，所以进口成本带只当参考。</li></ul><p>成本锚是估值参照，<b>不是买卖信号</b>。</p>`];
ABOUT.plan = ['交易计划怎么用', `<p>页面分「交易」和「研究」两个模式（右上角切换，记住你的选择）：交易模式只留入场信号、持仓管理、账户权益、交易记录和K线；基本面趋势墙、市场状态、成本锚、证据页在研究模式。顶部「入场信号」和「持仓管理」两格就是结论。<b>系统不会替你下单</b>，它只做三件事：告诉你今天有没有入场信号、该开几手；你成交后记一笔，之后开仓价、持仓最高/最低价、浮盈亏、权益全部自动算；每天自动判定持仓该走还是继续拿。</p>
<h3>完整交易逻辑（回测和页面是同一套）</h3>
<ul><li><b>价格</b>：用「换月调整的主力连续价」（只做主力合约，主力按持仓量在1/5/9月之间轮换，换月日沿用前一天涨跌幅，不吃价差跳空）。信号和持仓涨跌都用它，收盘后看一次，操作在<b>下一个交易日</b>（入场挂限价单，平仓开盘市价）。</li>
<li><b>外资</b> = 摩根大通、高盛期货、瑞银期货，各自「近5个交易日」持仓变化。龙虎榜每边只公布前20名：席位只有一边进前20时，只用进榜那一边的真实变化，不把顶替的第20名算进去；拿不到的席位不参与（回测里缺数据日按0）。</li>
<li><b>外资去杠杆</b>：<b>任一</b>席位5日变化 ≤ −2万手（看单个席位，不看合计：席位之间会对冲，例如摩根加仓、高盛减仓）。</li>
<li><b>做多</b>（三条同时满足）：①价格在近260日 ≤50% 分位；②反弹确认：今天收盘高于5日前，且比前10日最低价高1%以上；③外资没有去杠杆。</li>
<li><b>做空</b>（三条同时满足）：①外资去杠杆（任一席位5日变化 ≤ −2万手）；②价格 < MA20 < MA60；③价格低于5日前。空头只在外资去杠杆时才做。</li>
<li><b>平多</b>（任一触发）：亏4%止损；持仓期间最高浮盈到过 ≥8% 后，从最高价回落4%；外资去杠杆（任一席位 ≤ −2万手）。</li>
<li><b>平空</b>（任一触发）：亏4%止损；持仓期间最高浮盈到过 ≥8% 后，从最低价反弹4%；外资<b>三家合计</b>5日变化 ≥0（外资回正）；价格站上MA20。</li>
<li><b>入场价（挂条件单用）</b>：信号出现后，下一个交易日挂<b>限价单</b>：做多 ≤ 信号日收盘价、做空 ≥ 信号日收盘价，当日有效，没成交就作废、不追（第二天信号还在会重新给价）。跳空低开（做空是高开）时按开盘价成交，等于不追高。回测（收盘价限价）：5年终值中位 830万 / 夏普 1.11，95% 的信号能成交，不比开盘市价（735万）差。想挂得更低（回调）：回调 0.3%~0.5% 回测更好看但只是少数单的路径，回调 1% 成交率只剩 22%、终值掉到 337万——<b>不建议为了便宜去等回调</b>。止损价按<b>实际成交价</b>×(1∓4%)重新算，页面给的止损价是按收盘价算的参考。</li>
<li><b>已有持仓时</b>不加仓；同一时间只持一个方向。</li>
<li><b>占用阶梯</b>：权益<500万 60%；500~1500万 40%；1500~5000万 25%；其后 15%（页面底部可展开）。手数 = 权益×占用 ÷（每吨×10吨×保证金）。没有账户回撤熔断。</li>
<li><b>平空为什么看合计、去杠杆却看单个席位</b>：回测里两种平空口径几乎一样（14笔空单里13笔完全相同，只差一笔 +1.2%），不是证明出来的优劣，按回测验证过的口径写。</li></ul>
<p><b>权益怎么算</b>：初始资金 + 出入金 + 已平仓盈亏 + 持仓浮动盈亏 − 手续费。要追加资金（比如每年加20万）就记一笔入金；和期货公司账户对不上时用「按实际权益校准」，系统会记一笔差额。</p>
<p><b>最高/最低价怎么来</b>：用主力连续日线收盘价，从你的开仓日取到最新一天，和回测同口径（盘中最高价不计）。你的开仓价和主连差超过2%时按开仓日折算。信号和离场判断都只在收盘后看一次。</p>
<p><b>手续费</b>：按「每手来回多少元」估算，开仓/平仓各一半；回测用 23 元（含滑点估计），63、103 元是敏感性。记录时填了实际金额就用实际的。</p>
<p><b>保证金比例</b>：回测按10%。填期货公司实际比例后，「按我的实际保证金占用」按它算手数；「按回测杠杆」手数不变，实际占用会更高、风险度更接近追保线。风险度到100%的价格是追保/强平的大致位置，以你的期货公司为准。</p>
<p><b>移动止盈为什么是「最高浮盈 ≥8% 后回落4%」</b>：按「最高浮盈到过4%就开始跟踪」回测，反而更差——小利润的单子被早早洗出；「≥8%后回落4%」和原先回测的写法等价。回落幅度不要收紧。</p>
<p><b>数据不足时</b>：外资5日数据一个席位都没取到、或价格数据超过7天没更新，信号格会显示「数据不足，信号不可信」，不给开仓建议（回测里缺外资数据按0算，等于去杠杆过滤失效）。</p>
<p><b>决策快照</b>：每次记开仓/平仓，会同时存下当时的基本面方向、技术面、资金面、市场状态和信号条件；交易记录里能看到开仓时的基本面和外资，「导出CSV」带全部快照字段。基本面目前没有被回测证明有用（见项目文档），快照是为了以后用你自己的实盘去检验它。</p>
<p><b>首页随持仓状态变化</b>：空仓时，左格是入场信号（做多/做空、建议手数、限价、止损价），交易计划面板默认收起，点信号格或右上角「计划」展开（成交后在里面「记录开仓」）。有持仓时，左格变成「持仓信号」（继续持有 / 该平仓 + 原因 + 止损价、移动止盈、外资三项状态），右格显示浮盈亏金额，交易计划面板自动展开；记录平仓后恢复空仓界面。同一时间只持一笔：回测一共 43 笔，持仓期间约 28% 的交易日里「入场信号」仍然成立（页面会写「入场信号仍成立，已有持仓不加仓」），这些信号不开第二笔；反向信号只有 18 个持仓日，而且都要先触发离场才会再看。</p>
<p><b>提醒（邮件 + 微信）</b>：每天夜盘收盘后的那次同步会用同一套逻辑检查：出现新的入场信号、你的持仓该平了、数据不足，就发提醒——GitHub Issue（自动发邮件）、Server酱 / PushPlus（微信）、SMTP 邮件，哪个配了密钥发哪个。入场信号只在「从无到有」时发一次；离场提醒在你平仓并「记录持仓」之前每个交易日提醒一次。提醒里的操作都是<b>下一个交易日开盘</b>。</p>
<p><b>为什么不是14:58下单</b>：回测对比过。龙虎榜收盘后才公布，14:58 只能用前一天的外资数据，加上价格波动，5年终值中位 754万；收盘后看、次日开盘成交 735万，差别在噪声之内，却要盯盘。所以只在收盘后看一次。</p>
<p><b>历史开仓月份</b>：交易计划页底部「历史开仓月份」。信号出现频率有一定参考（1、2月最多，★★★☆☆），盈亏没有参考（★☆☆☆☆），不要因为月份加仓或放弃信号。</p>
<p><b>价格口径</b>：信号、持仓涨跌用「换月调整价」（data/main_adj.json），原始主连在换月日会跳一个合约价差，拿它算会多出假信号（同样次日开盘成交，回测对比：317万 vs 735万）。缺这个文件时信号格会写明并作废信号。</p>
<p><b>记录存在哪</b>：只存在这台设备的浏览器里，换设备或清缓存会丢，所以页面底部有「备份下载 / 恢复备份」。</p>
<p><b>局限</b>：39笔交易、样本内；外资信号只有2022年以后；不含涨跌停无法成交、大资金冲击成本和持仓限额。</p>`];
function sigHelp() {
  const s = planSnap(), F = s.F, f2 = n => (n >= 0 ? '+' : '−') + Math.abs(Math.round(n)).toLocaleString('en-US');
  const bs = q => q.basis === 'long' ? '只算多单(空单只在第20名外，不计)' : q.basis === 'short' ? '只算空单(多单只在第20名外，不计)' : q.approx ? '估算(拿不到多空明细，用净持仓差，混有第20名的变动)' : '净持仓变化(买卖两边都在前20，真值)';
  return `<h3>外资去杠杆：看单个席位，任一席位「近5个交易日」变化 ≤ −2万手</h3><ul>${F.parts.map(q => `<li><b>${esc(q.k)}</b> ${f2(q.v)} 手：${bs(q)}</li>`).join('')}${F.missing.map(k => `<li><b>${esc(k)}</b>：暂无5日数据，按0算（回测里缺数据的日子也按0）</li>`).join('')}</ul>
   <p>${F.parts.length ? '最弱席位 <b>' + esc(F.minK) + ' ' + f2(F.min) + '</b> 手（三家合计 ' + f2(F.sum) + ' 手，仅供参考）；最弱的一家 ≤ −20,000 手就算「外资去杠杆」。' : '没有可用的外资数据。'}</p>
   <p>为什么不用三家合计：席位之间可能对冲(比如摩根加仓、高盛减仓)，合计会把单个席位的撤退抵消掉。回测里两种口径几乎一样(历史上外资信号基本就是摩根大通)，这里按单个席位判断。</p><p>龙虎榜每边只公布前20名。一个席位只有一边进了前20时，另一边用第20名顶替，那个数字的变动和该席位无关，所以信号只用进榜那一边的真实变化。</p>
   <h3>和研究页「高盛净持仓」为什么对不上</h3><p>研究页画的是<b>净持仓(多−空)</b>，空单常常是第20名顶替的下限估计，周期是「1周/1月」按自然日找对比点；这里是<b>近5个交易日</b>、只用真实一边。起点日期和口径都不同，数字就不同。研究页高盛的明细里有这一行对照。</p>
   <h3>价格口径</h3><p>价格用「换月调整的主力连续价」(与回测同一口径)，现价 ${fmtD(s.px)}。信号收盘后看一次即可，龙虎榜收盘后才发布，所以数据日是前一个交易日。</p>
   <h3>完整规则</h3><p>入场、离场、仓位的全部逻辑见右上角「说明」→「交易计划怎么用」。</p><h3>本月</h3><p>${esc(monthHint())}</p>`;
}
const HELP = {
  plsig: ['入场信号：数据和口径说明', sigHelp],
  plpos: ['持仓管理怎么用', () => '<p><b>离场规则</b>：多单——亏4%止损；最高浮盈到过 ≥8% 后从最高价回落4%；外资去杠杆（任一席位5日变化 ≤ −2万手）。空单——亏4%止损；最高浮盈到过 ≥8% 后从最低价反弹4%；外资三家合计5日变化 ≥0；价格站上MA20。完整交易逻辑见右上角「说明」。</p><p>当前空仓时，成交后在这里记一笔，之后开仓价、持仓期间最高/最低价、浮盈亏、该不该走都自动算。持仓中，这里显示止损价、移动止盈、外资离场条件。</p><p>想收到「该平仓」提醒，要把持仓同步到仓库：见下方「同步持仓到提醒系统」。</p>'],
  placct: ['账户权益说明', () => '<p>权益 = 初始资金 ± 出入金 + 已平仓盈亏 + 持仓浮动 − 手续费。手续费按每手来回估算，开仓/平仓各记一半，记录时填了实际金额就用实际的。现价用主力连续收盘价，和期货公司结算价会有小差别，需要时用「账户设置」里的校准。</p><p>回测每手来回按 23 元（含滑点估计）；回测摘要里 63、103 元是敏感性测试。保证金比例填期货公司实际收的（交易所10% + 加收），回测按10%。</p>'],
};
function openAbout(k) {
  if (HELP[k]) { openSheet(HELP[k][0], HELP[k][1]()); return; }
  if (['pos', 'sea', 'cost', 'plan'].includes(k)) { openSheet(ABOUT[k][0], ABOUT[k][1]); return; }
  const keys = ['regime', 'vp', 'fund', 'capital', 'price', 'wall'], order = k ? [k, ...keys.filter(x => x !== k)] : keys;
  const extra = `<h3>合约自动切换</h3><p>按你定的建议交易窗口自动选：9月合约 4–7月，1月合约 8–11月，5月合约 12–3月，全年没有空档。点头部的合约标签可以手动看别的合约；每日记录仍然记三个合约，不受影响。</p><h3>主题</h3><p>默认按本地时间自动切换：06:30 到 18:30 是日间，其余是夜间。点“主题”可以固定成日间、夜间或回到自动。</p><h3>数据口径提醒</h3><ul><li>豆菜粕价差 2026-06 起换成三城市单值，旧阈值不适用，新口径暂不计分。</li><li>开机率历史不足时回退固定阈值。</li><li>国储拍卖、能繁母猪只展示，不计分。</li></ul>`;
  openSheet('说明：怎么读这页', order.map(x => `<h3 style="font-size:15px">${ABOUT[x][0]}</h3>${ABOUT[x][1]}`).join('') + extra);
}
function openEvents() { openSheet('未来 14 天的事件', `<table class="tb3x"><tbody>${D.events.map(e => `<tr><td class="n">${esc(e.label)}</td><td>${esc(e.title)}</td></tr>`).join('')}</tbody></table><p class="dim2" style="margin-top:12px">北京时间，休市和恢复交易以大商所公告为准。</p>`); }

/* ---------- 头部与主题 ---------- */
function renderHeader() {
  const k = S.key, c = C();
  $('#cSym').textContent = c.symbol || '—'; $('#cName').textContent = CM[k].name; $('#cMode').textContent = S.auto ? '自动' : '手动查看';
  const h = D.health, sync = h ? (h.sync.label.match(/\((.*?)\)/) || [])[1] : '';
  $('#sync').className = 'sync' + (h && h.sync.state !== 'ok' ? ' note' : '');
  $('#sync').innerHTML = `<i></i><span class="tx">数据 ${esc(sync || '—')}</span>`;
  const gm = Date.parse(D.generatedAt || ''), hh = isFinite(gm) ? new Date(gm + 8 * 3600e3).toISOString().slice(5, 16).replace('T', ' ') : '—';
  $('#dockNote').textContent = '数据生成 ' + hh + '（北京） · 历史到 ' + (D.seriesAsOf && D.seriesAsOf.history ? D.seriesAsOf.history.slice(5) : '—') + ' · 每10分钟自动刷新';
  $('#cPop').innerHTML = ['sep', 'may', 'jan'].map(x => `<button role="menuitem" data-ck="${x}" aria-current="${x === S.key}"><span class="t">${CM[x].name}（${esc(D.contracts[x].symbol || '')}）</span><span class="tag">${x === autoKey() ? '建议' : ''}</span><span class="s">建议交易窗口 ${CM[x].win}</span></button>`).join('') + `<div class="ft">${S.auto ? '现在按日期自动选择。' : '你正在手动查看。'}${S.auto ? '' : '<button data-ck="auto" style="display:inline;width:auto;padding:0 0 0 6px;color:var(--focus);font-weight:500">回到自动</button>'}<br>每日记录仍会记三个合约，不受这里影响。</div>`;
}
function applyTheme() {
  const th = L.themeFor(new Date(), S.themePref);
  document.documentElement.setAttribute('data-theme', th);
  const b = $('#thBtn'); if (b) b.textContent = S.themePref === 'auto' ? '主题：自动' : S.themePref === 'day' ? '主题：日间' : '主题：夜间';
}
function setMode(m, noSave) {
  S.mode = m === 'research' ? 'research' : 'trade'; document.body.classList.toggle('mode-trade', S.mode === 'trade'); document.body.classList.toggle('mode-research', S.mode === 'research');
  $$('[data-mode]').forEach(b => b.setAttribute('aria-pressed', b.dataset.mode === S.mode));
  if (!noSave) { try { localStorage.setItem('cockpit-mode', S.mode); } catch (_) {} }
  if (S.mode === 'research') { renderWall(false); layoutWall(false); } drawChart();
}
function renderAll(anim) { renderHeader(); renderBand(); renderSig(); renderChecks(); renderChart(); renderWall(anim); tradeShell(); planUpdate(); }

/* ---------- 事件 ---------- */
document.addEventListener('click', e => {
  const t = e.target.closest('button,[data-tile]'), pop = $('#cPop'), cb = $('#cBtn');
  if (!e.target.closest('#cPop') && !e.target.closest('#cBtn')) { pop.classList.remove('on'); cb.setAttribute('aria-expanded', 'false'); }
  if (!t) return;
  if (t.id === 'cBtn') { const on = pop.classList.toggle('on'); cb.setAttribute('aria-expanded', on); return; }
  if (t.dataset.ck) { if (t.dataset.ck === 'auto') { S.auto = true; S.key = autoKey(); } else { S.key = t.dataset.ck; S.auto = S.key === autoKey(); } pop.classList.remove('on'); cb.setAttribute('aria-expanded', 'false'); renderAll(true); return; }
  if (t.id === 'exBtn') { S.ex = !S.ex; document.body.classList.toggle('ex', S.ex); t.setAttribute('aria-pressed', S.ex); layoutWall(false); return; }
  if (t.id === 'thBtn') { S.themePref = { auto: 'day', day: 'night', night: 'auto' }[S.themePref]; applyTheme(); try { localStorage.setItem('cockpit-theme', S.themePref); } catch (_) {} return; }
  if (t.id === 'abBtn') { openAbout(); return; }
  if (t.id === 'planBtn') { S.planShow = !planShown(); applyPlanVis(); return; }
  if (t.dataset.about) { openAbout(t.dataset.about); return; }
  if (t.id === 'shX') { closeSheet(); return; }
  if (t.dataset.tile) { openTile(t.dataset.tile); return; }
  if (t.dataset.more || t.dataset.pend) { openMore(t.dataset.sum); return; }
  if (t.dataset.lamp) { openLamp(t.dataset.lamp); return; }
  if (t.dataset.sea) { S.seaKind = t.dataset.sea; renderChart(); return; }
  if (t.dataset.mode) { setMode(t.dataset.mode); return; }
  if (t.dataset.goplan) { setMode('trade'); S.planShow = true; applyPlanVis(); const tp = $('#tradePanel'); if (tp && tp.scrollIntoView && window.innerWidth < 900) tp.scrollIntoView({ block: 'start' }); return; }
  if (t.dataset.act) { planAct(t.dataset.act, t); return; }
  if (t.dataset.view) { S.view = t.dataset.view; renderChart(); return; }
  if (t.dataset.range) { S.range = +t.dataset.range; $$('[data-range]').forEach(b => b.setAttribute('aria-pressed', +b.dataset.range === S.range)); drawChart(); return; }
  if (t.dataset.span) { S.span = t.dataset.span; $$('[data-span]').forEach(b => b.setAttribute('aria-pressed', b.dataset.span === S.span)); layoutWall(true); return; }
  if (t.dataset.tab) { openTab(t.dataset.tab); return; }
});
$('#scrim').addEventListener('click', closeSheet);
document.addEventListener('keydown', e => {
  if (e.target.matches && e.target.matches('input,textarea')) return;
  if (e.key === 'Escape') { closeSheet(); $('#cPop').classList.remove('on'); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === 'e' || e.key === 'E') $('#exBtn').click(); else if (e.key === '?') openAbout(); else if (/^[1-6]$/.test(e.key)) openTab(TABS[+e.key - 1][0]);
});
document.addEventListener('input', e => { if (e.target.id && e.target.id.startsWith('pf-')) e.target.dataset.t = '1'; });
document.addEventListener('change', e => { const t = e.target; if (t.id === 'pf-file') { if (t.files && t.files[0]) planRestore(t.files[0]); t.value = ''; } else if (t.dataset && t.dataset.set) planSetting(t); });
document.addEventListener('change', e => { const r = e.target.closest && e.target.closest('.inp'); if (!r || !window.CockpitData || !window.CockpitData.manualEdit) return; const s = $('.s', r); if (s) s.textContent = '重新计分中…'; window.CockpitData.manualEdit(r.dataset.key, e.target.value.trim()).then(ok => { if (!ok && s) s.textContent = '没有写进评分引擎（引擎还没就绪）'; }); });
document.addEventListener('input', e => { const r = e.target.closest && e.target.closest('.inp'); if (!r) return; r.classList.toggle('ov', e.target.value !== e.target.dataset.orig); });
let rz; const relayout = () => { clearTimeout(rz); rz = setTimeout(() => { drawChart(); layoutWall(false); }, 100); };
window.addEventListener('resize', relayout);
if (typeof ResizeObserver === 'function') { const ro = new ResizeObserver(relayout); ro.observe($('#tiles') || document.body); ro.observe($('#chart')); }
setInterval(applyTheme, 60000);
try { const t = localStorage.getItem('cockpit-theme'); if (t === 'day' || t === 'night' || t === 'auto') S.themePref = t; } catch (_) {}
try { const m = localStorage.getItem('cockpit-mode'); if (m === 'research' || m === 'trade') S.mode = m; } catch (_) {}
setMode(S.mode, true); applyTheme(); renderAll(true); setMode(S.mode, true);
function refreshed() {   // 后台重取数据后调用：不打断正在输入的表单
  if (S.auto) S.key = autoKey();
  const ae = document.activeElement, typing = ae && ae.closest && ae.closest('#planForm, .inp');
  if (typing) { renderHeader(); renderBand(); renderSig(); renderChecks(); renderWall(false); }
  else renderAll(false);
}
window.__cockpit = { S, L, planSnap, renderAll, refreshed, openTab, openTile, openAbout, closeSheet, layoutWall, checks, regimeNow, capital, fundamentals, tiles, applyTheme, get GRID() { return GRID; } };
})();

