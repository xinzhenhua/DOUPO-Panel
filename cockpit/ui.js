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
const LYD = { ma: true, mon: true, vol: true, macd: true, oi: true, h20: false, iron: false, be: false };   // K线图层默认：只留彩带、本月高低、持仓量，其余按需打开（v101.51）
const LYN = [['ma', '20日均线（彩带=价格位置）'], ['mon', '本月高低 + 本月振幅'], ['vol', '成交量（下方柱子）'], ['macd', 'MACD（12,26,9）'], ['oi', '持仓量（成交量栏里的金线）'], ['h20', '近20日高/低'], ['iron', '260天铁顶/底 · 10年铁顶'], ['be', '成本平衡价']];
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
const VIEWS = [['px', '价格持仓'], ['amp', '月振幅'], ['pos', '价格位置'], ['sea', '同期规律'], ['cost', '成本锚']];
let MULTI = false;
function viewTabs() { if (MULTI) return ''; return `<div class="seg vtabs" role="group" aria-label="切换视图">${VIEWS.map(([k, n]) => `<button data-view="${k}" aria-pressed="${(S.view || 'px') === k}">${n}</button>`).join('')}</div>`; }
function viewHdr(title, about) { return `<div class="ch-h"><span class="t">${title}</span><button class="q" data-about="${about}" aria-label="这页怎么看">?</button><button class="q fsbtn" data-full="${about}" aria-label="放大全屏" title="放大全屏">⤢</button></div>${viewTabs()}`; }
const fmtD = n => Math.round(n).toLocaleString('en-US');
const quant = (sorted, q) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(q * sorted.length) - 1))];
function histRows() { const h = D.hist; return h ? h.d.map((d, i) => ({ d, c: h.c[i] })) : []; }
function beOf(key) { const cr = D.crush && D.crush[key]; return cr && cr.available && cr.beanPrice != null ? (cr.beanPrice + 150 - cr.oilPrice * .185) / .785 : null; }
const rngBar = (label, pct, tag, lo, hi) => `<div class="rng"><div class="l1"><span>${label}</span><span><b>${pct.toFixed(1)}%分位</b>　${tag}</span></div><div class="rtrack"><i style="left:${pct}%"></i></div><div class="l2"><span>${lo}</span><span>${hi}</span></div></div>`;

/* ---- 价格位置 ---- */
function viewPos(bx, cap, maxH) {
  const rows = histRows(); if (rows.length < 400) return viewHdr('价格位置', 'pos') + `<div class="dim2" style="padding:20px 0">缺少历史价格数据。</div>`;
  const box = bx || $('#chart'), W = Math.max(260, Math.min(cap || 760, (box.clientWidth || 600) - 24)), H = Math.min(Math.round(W * .5), maxH || 9999), ml = 4, mr = W < 560 ? 104 : 84, mt = 8, mb = 20, N = Math.min(rows.length - 259, 756);
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
const vmoreOpen = k => { const v = (S.vm || {})[k]; return v != null ? v : (innerWidth < 900); };   // 电脑端默认收起「更多明细」，保证一屏放下；手机上本来就能滚动，默认展开
const vmoreHtml = (k, inner) => inner && inner.trim() ? `<details class="vmore" data-vm="${k}"${vmoreOpen(k) ? ' open' : ''}><summary>更多明细</summary>${inner}</details>` : '';
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
  return viewHdr('同期规律 · 各月上涨概率', 'sea') + tog + `<div class="hl"><b>${m}月</b>${kind === 'spot' ? '现货' : '期货'}：近 ${f.n} 年 <b>${upN} 年上涨（${Math.round(f.upPct)}%）</b>，平均 ${sgn(f.mean)}，中位 ${sgn(f.median)}<br><span style="color:${g.label === '不稳' ? 'var(--ink3)' : 'var(--amber)'}">稳定性：${esc(g.label)} → ${verdict}</span>${stable.length ? `<br><span class="stm" style="color:var(--ink2);font-size:13px">较稳的月份：${stable.join('、')}</span>` : ''}</div>
    <div class="mbars">${cols}<div class="m50"></div></div>
    <div class="mleg"><span>柱子=该月上涨年份占比(%)，虚线=50%</span><span>下方数字=平均涨跌(%)；越淡=越不稳</span></div>
    ${vmoreHtml('sea', trendBlock() + (ex ? `<div class="rng"><div class="l1"><span>${m}月内最大波动（平均）</span><span><b class="bull">冲高 +${ex.upMean.toFixed(1)}%</b>　<b class="bear">回撤 ${ex.dnMean.toFixed(1)}%</b></span></div></div>` : ''))}`;
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
    ${vmoreHtml('cost', `<table class="tb3x" style="margin-top:6px"><thead><tr><th>合约</th><th>盘面</th><th>平衡价</th><th>差</th></tr></thead><tbody>${tbl}</tbody></table>`)}`;
}

/* ---- 交易计划：规则 + 信号 + 仓位计算器 + 回测摘要（v101.25） ---- */
/* PLAN_BEGIN —— 交易计划纯函数（v101.25）：和回测同一口径，不碰 DOM，便于单测 */
const TPLAN = {
  TIERS: [[5000000, .6], [15000000, .4], [50000000, .25], [Infinity, .15]],   // [权益上限(元), 占用]：<500万 60%；<1500万 40%；<5000万 25%；其余 15%
  STOP: 4, TRAIL: 4, ACT: 8,          // 止损4%；移动止盈：持仓期间最高浮盈≥8% 之后，从持仓最高(低)价回落≥4% 平仓（回测验证过的等价写法）
  LO: 50, DELEV: -20000,              // 低位：近260日分位≤50；任一外资席位5日变化≤-2万手=去杠杆（看单个席位，不看合计：席位之间可能互相对冲）
  BT_MARGIN: .10, TON: 10,            // 回测保证金10%；每手10吨
  FX_TH: 20000,                       // v101.87 候选规则「外资加杠杆做多」：任一外资席位5日持仓变化 ≥ +2万手（去杠杆的镜像）
  BASIS_MIN: 0, BASIS_AGE: 7          // v101.84 做多多一条：生意社基差(现货÷主力合约−1) ≥ 0；基差数据日和价格日相差超过7天就不用（不过滤，按原规则）
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
  const w = parts.length ? parts.reduce((a, q) => q.v < a.v ? q : a) : null, x = parts.length ? parts.reduce((a, q) => q.v > a.v ? q : a) : null;
  return { sum, used, missing, approx, parts, lastD, min: w ? w.v : 0, minK: w ? w.k : '', max: x ? x.v : null, maxK: x ? x.k : '' };
}
/* v101.84 基差：latest.json 的 spotBasis（生意社现货价、生意社主力合约价，fetch_data.fetch_spot_basis 取）→ 比值 现货÷主力−1（正=现货高于期货）。
   和本地自动交易 local_signal.py、回测同一个口径。取不到/太旧 → v=null，信号按原规则（不过滤），why 写原因。 */
function planBasis(sb, priceD) {
  if (!sb || !sb.available) return { v: null, why: '没有基差数据' + (sb && sb.reason ? '（' + sb.reason + '）' : '') };
  const sp = +sb.spot, fp = +sb.domPrice, d = String(sb.date || '').slice(0, 10);
  if (!(sp > 0 && fp > 0) || !/^\d{4}-\d{2}-\d{2}$/.test(d)) return { v: null, why: '基差数据不完整' };
  const age = priceD ? Math.round((Date.parse(priceD) - Date.parse(d)) / 86400000) : 0;
  if (Math.abs(age) > TPLAN.BASIS_AGE) return { v: null, why: '基差数据日 ' + d + ' 和价格日 ' + priceD + ' 相差 ' + Math.abs(age) + ' 天，太旧不用', d };
  return { v: sp / fp - 1, d, age, spot: sp, fut: fp, dom: sb.domSymbol || '' };
}
/* v101.87 两条候选规则（默认都不启用，网页「入场信号：数据和口径说明」里各有开关）：opt = { contangoShort: 期货升水+趋势向下做空, fxLong: 外资加杠杆直接做多, fmax: 外资席位5日最大变化 }。
   不传 opt（或都为 false）= 和 v101.84 完全一样。启用后候选信号出现就当成入场信号（longOK / shortOK 为真，via 标明来源），离场规则和常规单一样。 */
function planSignals(cs, fsum, basis, opt) {   // basis：planBasis(...).v；不传/null = 原规则（和 v101.81 之前完全一样）
  const n = cs.length, last = cs[n - 1], pct = planPct(cs), ma20 = planMA(cs, 20), ma60 = planMA(cs, 60), conf = planConfirm(cs), delev = fsum <= TPLAN.DELEV;
  const lowOK = pct != null && pct <= TPLAN.LO;
  const trendDn = ma20 != null && ma60 != null && last < ma20 && ma20 < ma60 && n >= 6 && last < cs[n - 6];
  const o = { pct, ma20, ma60, confirm: conf, delev, lowOK, trendDn, longOK: lowOK && conf && !delev, shortOK: delev && trendDn };
  if (typeof basis === 'number' && isFinite(basis)) {
    const ok = basis >= TPLAN.BASIS_MIN;
    Object.assign(o, { basis, basisOK: ok, basisBlocked: o.longOK && !ok, contangoShort: basis < 0 && trendDn && !delev, longOK: o.longOK && ok });
  }
  if (!opt) return o;   // 不传 opt：输出字段和 v101.84 完全一样（plan_alert.js 推送提醒就是这样调的）
  // 候选A 期货升水+趋势向下做空（不要求外资去杠杆）：contangoShort 是「出现」，启用后才当信号
  o.cShortGo = !!(opt && opt.contangoShort) && !!o.contangoShort && !o.shortOK;
  // 候选B 外资加杠杆直接做多：任一席位5日 ≥ +2万手；常规多单没成立、没有席位在去杠杆、基差不<0（取不到基差不拦）——和本地 DOUPO-FX 的 fx_lever_long 同一条
  o.fxMax = opt && typeof opt.fmax === 'number' && isFinite(opt.fmax) ? opt.fmax : null;
  o.fxLever = o.fxMax != null && o.fxMax >= TPLAN.FX_TH;
  o.fxCand = o.fxLever && !o.longOK && !o.delev && o.basisOK !== false;
  o.fxGo = !!(opt && opt.fxLong) && o.fxCand;
  o.via = o.fxGo ? 'fx' : o.cShortGo ? 'contango' : null;
  if (o.fxGo) o.longOK = true;
  if (o.cShortGo) o.shortOK = true;
  return o;
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
  if (sg.fxGo) return '外资加杠杆直接做多（候选规则，你已启用）：' + (sg.fxMax != null ? '任一席位5日 ' + (sg.fxMax >= 0 ? '+' : '') + Math.round(sg.fxMax).toLocaleString('en-US') + ' 手 ≥ +' + TPLAN.FX_TH.toLocaleString('en-US') : '') + '，没有席位在去杠杆' + (sg.basisOK ? '，期货不高于现货' : '');
  if (sg.cShortGo) return '期货高于现货 + 价格趋势向下（候选规则，你已启用）：不要求外资去杠杆';
  if (sg.longOK) return '低位 + 反弹确认 + 外资没有去杠杆' + (sg.basisOK ? ' + 期货不高于现货' : '');
  if (sg.basisBlocked) return '低位 + 反弹确认 + 外资没有去杠杆，但期货高于现货（基差 ' + (sg.basis * 100).toFixed(2) + '%）：按基差过滤不做多';
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
/* 持仓属于哪个合约：开仓时记下当时看的合约代码(t.contract)；没记的老记录算当前自动合约的 */
function planOpenFor(trades, sym, legacySym) { for (let i = (trades || []).length - 1; i >= 0; i--) { const t = trades[i]; if (t.exitD) continue; const c = t.contract || legacySym; if (!sym || !c || String(c).toLowerCase() === String(sym).toLowerCase()) return t; } return null; }
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

/* ---- 实盘记录（v101.50）：每笔交易存下「当时系统怎么看、预计多少」和「事后实际怎样」，攒够了就能检验系统 ---- */
const PLAN_REASONS = [['', '自动（按系统建议动作）'], ['stop', '止损'], ['trail', '移动止盈'], ['foreign', '外资去杠杆/翻转'], ['ma20', '站上MA20'], ['protect', '手动保本/落袋'], ['feel', '主观判断（没触发规则）'], ['other', '其他']];
const planReasonOf = act => act === '止损' ? 'stop' : act === '移动止盈' ? 'trail' : act === '外资去杠杆·平多' || act === '空单离场' ? 'foreign' : 'feel';
const planSlip = (side, ref, px) => (ref > 0 && px > 0) ? (side >= 0 ? 1 : -1) * (px / ref - 1) * 100 : null;   // 开仓滑点：正数=比参考价更不利（多单买高了/空单卖低了）
function planPath(h, t) {   // 持仓期间的日线路径与极值：{days, mfe(最大浮盈%), mae(最大浮亏%，负数), path:[[日期,真实价]...]}；已平仓只算到平仓日
  if (!h || !h.d || !h.d.length) return null;
  const side = t.side >= 0 ? 1 : -1; let n = h.d.length; if (t.exitD) { n = 0; while (n < h.d.length && h.d[n] <= t.exitD) n++; }
  const hh = { d: h.d.slice(0, n), c: h.c.slice(0, n) }, ho = planHold(hh, t); if (!ho.covered) return null;
  const path = []; for (let i = 0; i < n; i++) if (h.d[i] >= t.entryD) path.push([h.d[i], Math.round(h.c[i] * ho.k)]);
  return { days: t.exitD ? path.length - 1 : ho.days, mfe: side * (ho.peak / t.entryPx - 1) * 100, mae: side * (ho.worst / t.entryPx - 1) * 100, path };
}
function planReview(trades, per) {   // 已平仓交易的「预计 vs 实际」汇总
  const cl = (trades || []).filter(t => t.exitD), avg = a => a.length ? a.reduce((p, c) => p + c, 0) / a.length : null;
  const rows = cl.map(t => { const net = planPnl(t, t.exitPx) - planFee(t, per), ret = (t.side >= 0 ? 1 : -1) * (t.exitPx / t.entryPx - 1) * 100, rs = t.res || {}; return { t, net, ret, win: net > 0, src: t.src === 'own' ? 'own' : t.src === 'sys' ? 'sys' : planSrc(t), mfe: rs.mfe, mae: rs.mae, days: rs.days, so: t.slipO, sx: rs.slipX, pw: t.pred && t.pred.win != null ? t.pred.win : null, pev: t.pred && t.pred.ev != null ? t.pred.ev : null, prr: t.pred && t.pred.rr != null ? t.pred.rr : null }; });
  const grp = a => ({ n: a.length, win: a.length ? a.filter(x => x.win).length / a.length : null, ret: avg(a.map(x => x.ret)), net: a.reduce((p, c) => p + c.net, 0) });
  const pr = rows.filter(r => r.pw != null), cap = rows.filter(r => r.win && r.mfe > 0).map(r => r.ret / r.mfe);
  return { n: rows.length, all: grp(rows), sys: grp(rows.filter(r => r.src === 'sys')), own: grp(rows.filter(r => r.src === 'own')), long: grp(rows.filter(r => r.t.side >= 0)), short: grp(rows.filter(r => r.t.side < 0)),
    predN: pr.length, predWin: avg(pr.map(r => r.pw)), predEv: avg(pr.map(r => r.pev)), actWinOfPred: pr.length ? pr.filter(r => r.win).length / pr.length : null, actRetOfPred: avg(pr.map(r => r.ret)),
    slipO: avg(rows.filter(r => r.so != null).map(r => r.so)), slipX: avg(rows.filter(r => r.sx != null).map(r => r.sx)), mfe: avg(rows.filter(r => r.mfe != null).map(r => r.mfe)), mae: avg(rows.filter(r => r.mae != null).map(r => r.mae)), days: avg(rows.filter(r => r.days != null).map(r => r.days)), capture: avg(cap), rows };
}
/* ---- 持仓预期（v101.48）：回测经验值 + 从现在起的价格推演（蒙特卡洛）。不是预测，是把"回测里的平均优势"套到当前持仓上 ---- */
const TBT = {   // 回测（2017-12~2026-10，信号收盘价、止损/移动止盈按收盘判断，40笔）里同方向的统计；脚本见 scratchpad/mp/bt4.py
  long: { n: 26, win: .538, avgWin: 9.1, avgLoss: -2.6, avg: 3.7, days: 29 },
  short: { n: 14, win: .643, avgWin: 2.4, avgLoss: -1.3, avg: 1.0, days: 5 },
  LIM: { pct: 0.3, fill: 83, med: 1022, close: 830, open: 735 },   // 次日限价=收盘价回调0.3%：成交率83%，50万起5年终值中位（见回测摘要）
  SEDGE: .0022,   // 空单有外资翻转模型后需要的每日优势（让推演的胜率≈64%、平均≈+1.0%、持有≈4~5天，对上回测空单的统计；脚本 scratchpad/mp/flipmc.py）
  FLIPH: [.02, .11, .15, .25, .25, .20],   // 外资三家5日合计从「去杠杆」翻回≥0 的每日概率（第1天,第2天…第6天起恒定）：回测期45个空单信号日，翻转的中位天数4~5天（flip.py）
  EDGE: .0009, H: 60, FAN: 20     // 每天顺着持仓方向的平均优势 0.09%（让推演的平均收益≈回测的平均单笔收益）；推演60个交易日，画未来20个交易日
};
function planWilson(k, n) { if (!n) return [0, 1]; const z = 1.645, p = k / n, d = 1 + z * z / n, c = p + z * z / (2 * n), w = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return [Math.max(0, (c - w) / d), Math.min(1, (c + w) / d)]; }
function planRng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function planExpect(o) {   // o: {side,entry,peak,last,closes(真实价，至少20个),rets(日收益，去均值),edge,n,seed}；退出规则同 planManage：止损、移动止盈、空单站上MA20
  const side = o.side >= 0 ? 1 : -1, n = o.n || 1500, H = TBT.H, FAN = TBT.FAN, rets = o.rets || [], R = rets.length, edge = (o.edge == null ? TBT.EDGE : o.edge) * side, rng = planRng(o.seed || 12345), base = (o.closes || []).slice(-30);
  if (R < 50 || base.length < 20) return null;
  const fin = [], fnow = [], days = [], fan = []; for (let d = 0; d < FAN; d++) fan.push([]);
  let st = 0, tr = 0, ma = 0, hz = 0, fl = 0; const FH = TBT.FLIPH, held = o.flipHeld == null ? -1 : o.flipHeld;   // flipHeld>=0：空单按外资翻转概率离场（已持有的天数，之后每天抽一次）
  for (let i = 0; i < n; i++) {
    let px = o.last, pk = o.peak, d = 0, out = null; const ctx = base.slice(-19);
    while (d < H) {
      const j = Math.floor(rng() * (R - 5));
      for (let b = 0; b < 5 && d < H; b++) {
        px *= 1 + rets[j + b] + edge; d++; ctx.push(px); if (ctx.length > 20) ctx.shift();
        if (d <= FAN) fan[d - 1].push(px);
        if (out) continue;
        pk = side > 0 ? Math.max(pk, px) : Math.min(pk, px);
        const r = side * (px / o.entry - 1) * 100, pr = side * (pk / o.entry - 1) * 100;
        if (r <= -TPLAN.STOP) out = ['s', px, d]; else if (pr >= TPLAN.ACT && (side > 0 ? px <= pk * (1 - TPLAN.TRAIL / 100) : px >= pk * (1 + TPLAN.TRAIL / 100))) out = ['t', px, d];
        else if (side < 0 && ctx.length >= 20 && px > ctx.reduce((a, c) => a + c, 0) / 20) out = ['m', px, d];
        else if (side < 0 && held >= 0 && rng() < FH[Math.min(held + d, FH.length) - 1]) out = ['f', px, d];
      }
    }
    if (!out) out = ['h', px, H];
    if (out[0] === 's') st++; else if (out[0] === 't') tr++; else if (out[0] === 'm') ma++; else if (out[0] === 'f') fl++; else hz++;
    fin.push(side * (out[1] / o.entry - 1) * 100); fnow.push(side * (out[1] / o.last - 1) * 100); days.push(out[2]);
  }
  const q = (a, p) => { const b = a.slice().sort((x, y) => x - y); return b[Math.min(b.length - 1, Math.max(0, Math.round(p * (b.length - 1))))]; };
  const gn = fnow.filter(x => x > 0), ls = fnow.filter(x => x < 0), avg = a => a.length ? a.reduce((p, c) => p + c, 0) / a.length : 0, gainNow = avg(gn), lossNow = -avg(ls);
  return { n, gainNow, lossNow, rrNow: lossNow > 0 ? gainNow / lossNow : (gainNow > 0 ? 99 : 0), evNow: avg(fnow), winNow: gn.length / n, win: fin.filter(x => x > 0).length / n, stopP: st / n, trailP: tr / n, maP: ma / n, flipP: fl / n, holdP: hz / n, mean: fin.reduce((a, c) => a + c, 0) / n, p10: q(fin, .1), p50: q(fin, .5), p90: q(fin, .9), medDays: q(days, .5),
    fan: fan.map(a => ({ p10: q(a, .1), p25: q(a, .25), p50: q(a, .5), p75: q(a, .75), p90: q(a, .9) })) };
}

/* 开仓来源：按系统信号开的（sys）还是自己开的、当时系统没给信号（own）。旧记录没有这个字段，用开仓当天存的快照推断 */
function planSrc(t) {
  if (!t) return 'sys'; if (t.src === 'sys' || t.src === 'own') return t.src;
  const sn = t.snap; if (!sn) return 'sys'; if (sn.gateOk === false) return 'own';
  const longOK = sn.pct != null && sn.pct <= TPLAN.LO && !!sn.confirm && !sn.delev && !(typeof sn.basis === 'number' && sn.basis < TPLAN.BASIS_MIN), shortOK = !!sn.delev && !!sn.trendDn;
  if ((sn.via === 'fx' && t.side > 0) || (sn.via === 'contango' && t.side < 0)) return 'sys';   // v101.87 候选规则启用后开的单：按系统信号算
  return (t.side > 0 ? longOK : shortOK) ? 'sys' : 'own';
}
/* 平仓建议：按系统信号开的单，回测只验证过「按规则持有」；自己开的单没有入场优势，建议更紧。rr=从现在起继续持有的预计盈亏比 */
function planAdvice(o) {   // o: {src, side, r(浮盈%), rr, ev(从现在起的期望%), act(planManage.action), against(与系统方向相反), entry}
  const own = o.src === 'own', th = own ? 2 : 1.5, rr = o.rr == null ? null : o.rr, rrT = rr == null ? '—' : (rr >= 10 ? '10+' : rr.toFixed(1)) + ':1', profit = o.r > 0.5, L = [];
  if (o.act && o.act !== '持有') return { lv: 'exit', head: '按规则该平仓：' + o.act, rrT, th, L: ['这是系统的离场规则，不管这单是怎么开的，都按这个走。'] };
  if (own && o.against) return { lv: 'exit', head: '方向和系统相反，建议及时平仓', rrT, th, L: ['这单没有系统信号，而且' + (o.side > 0 ? '外资正在去杠杆' : '外资三家合计已回正') + '——回测里的优势站在另一边。', '不想马上平：至少把止损收紧到开仓价附近。'] };
  if (rr == null) return { lv: 'hold', head: own ? '自主开仓：按止损和移动止盈管理' : '按规则持有', rrT, th, L };
  if (profit && rr < th) {
    L.push('现在平仓 = 落袋 ' + o.r.toFixed(1) + '%；继续拿，平均再赚 ' + o.gain.toFixed(1) + '% / 再亏 ' + o.loss.toFixed(1) + '%，赔率不到 ' + th + ':1。');
    L.push(own ? '自己开的单没有回测优势，赚到的别等回吐：建议保本平仓，或把止损上移到开仓价 ' + o.entryTxt + '。' : '建议把止损上移到开仓价 ' + o.entryTxt + '（保本止损）：回测里浮盈≥3~6%后保本，5年终值中位 927万（基线 895万）、差10% 374万（基线 396万），基本持平，不吃亏；提前直接平仓没有回测支持。');
    return { lv: 'protect', head: '盈亏比 ' + rrT + '，低于 ' + th + ':1：建议保本', rrT, th, L };
  }
  if (!profit && (rr < th || o.ev < 0) && own) return { lv: 'exit', head: '盈亏比 ' + rrT + '，偏低：建议减仓或及时止损', rrT, th, L: ['自己开的单没有回测优势，浮亏时盈亏比还不到 ' + th + ':1，不值得等。'] };
  if (!profit && rr < th) return { lv: 'watch', head: '盈亏比 ' + rrT + '，偏低，但仍按系统规则持有', rrT, th, L: ['这单有系统信号：回测只验证过「按规则持有」，止损 4% 之前不建议自己提前砍。'] };
  return { lv: own ? 'watch' : 'hold', head: own ? '自主开仓：盈亏比 ' + rrT + '，可持有，建议保本止损' : '按规则持有 · 盈亏比 ' + rrT, rrT, th, L };
}
/* ---- 月振幅（v101.51）：每个日历月 (月内最高收盘−最低收盘)/月末收盘；本月没走完时按「同月历史上同样走了n个交易日」比 ---- */
function monthAmpCalc(d, c, curMonth) {   // d: 日期数组(升序), c: 收盘价(换月调整价)；curMonth: 'YYYY-MM'（今天所在月，没走完）
  if (!d || !c || d.length < 200 || d.length !== c.length) return null;
  const mp = new Map(); for (let i = 0; i < d.length; i++) { const k = d[i].slice(0, 7); if (!mp.has(k)) mp.set(k, []); mp.get(k).push(c[i]); }
  const q = (a, p) => { const b = a.slice().sort((x, y) => x - y); return b[Math.min(b.length - 1, Math.max(0, Math.round(p * (b.length - 1))))]; };
  const range = (a, n) => { const w = a.slice(0, n); return (Math.max(...w) - Math.min(...w)) / w[w.length - 1] * 100; };
  const keys = [...mp.keys()], rows = keys.map((k, i) => { const a = mp.get(k); return { m: k, y: +k.slice(0, 4), mo: +k.slice(5, 7), n: a.length, amp: range(a, a.length), part: k >= curMonth, a }; }).filter((r, i) => !(i === 0 && r.n < 10));
  const done = rows.filter(r => !r.part), cur = rows.find(r => r.part) || null, amps = done.map(r => r.amp);
  if (done.length < 24) return null;
  const byMonth = []; for (let mo = 1; mo <= 12; mo++) { const v = done.filter(r => r.mo === mo); if (!v.length) { byMonth.push(null); continue; } const a = v.map(r => r.amp); byMonth.push({ mo, n: v.length, min: Math.min(...a), q25: q(a, .25), med: q(a, .5), q75: q(a, .75), max: Math.max(...a), vals: v.map(r => ({ y: r.y, amp: r.amp })) }); }
  let curInfo = null;
  if (cur) { const same = done.filter(r => r.mo === cur.mo && r.n >= cur.n).map(r => range(r.a, cur.n)), pctN = same.length ? same.filter(x => x <= cur.amp).length / same.length * 100 : null;
    curInfo = { m: cur.m, mo: cur.mo, n: cur.n, amp: cur.amp, pctAll: amps.filter(x => x <= cur.amp).length / amps.length * 100, sameN: same.length, sameMed: same.length ? q(same, .5) : null, pctSameN: pctN, fullMed: byMonth[cur.mo - 1] ? byMonth[cur.mo - 1].med : null }; }
  return { rows: rows.map(r => ({ m: r.m, y: r.y, mo: r.mo, n: r.n, amp: r.amp, part: r.part })), cur: curInfo, med: q(amps, .5), q25: q(amps, .25), q75: q(amps, .75), max: Math.max(...amps), min: Math.min(...amps), nDone: done.length, byMonth };
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
function acctSave(noBump) {
  if (!noBump) { ACCT.rev = (+ACCT.rev || 0) + 1; ACCT.updated = new Date().toISOString(); }
  let ok = true; try { localStorage.setItem('cockpit-acct', JSON.stringify(ACCT)); } catch (_) { ok = false; }
  if (!noBump) cloudQueue();
  return ok;
}
function planCloses() { if (D.adj && D.adj.c.length >= 200) return D.adj.c; const hc = histCloses(); if (hc && hc.length >= 200) return hc; return (C().kline || []).map(b => b.c); }
function planLastPx() { const b = (C().kline || []).slice(-1)[0]; if (b && b.c) return b.c; const hc = histCloses(); return hc && hc.length ? hc[hc.length - 1] : 3000; }
const todayBJ = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
const sdName = s => s > 0 ? '多' : '空';
const yuan = n => (n >= 0 ? '+' : '−') + fmtD(Math.abs(n));
const pc1 = x => (x * 100).toFixed(1) + '%';
/* 一次算好：信号、持仓、自动判定、权益、建议手数。首页信号条和计划页共用，保证两处结论一致 */
function curPos() { const A = acctGet(); return planOpenFor(A.trades, C().symbol, (D.contracts[autoKey()] || {}).symbol); }
/* 某一笔持仓用哪条价格线算：开的就是 adj 那个主力合约 → 换月调整价；否则用它自己那个合约的日K */
function holdSeries(t) {
  const cs = String(t.contract || (D.contracts[autoKey()] || {}).symbol || '').toLowerCase(), ak = D.adj && D.adj.k && D.adj.k.length ? String(D.adj.k[D.adj.k.length - 1] || '').toLowerCase() : '';
  if (D.adj && (!ak || !cs || ak === cs)) return { h: D.adj, own: false };
  for (const k of ['sep', 'may', 'jan']) { const c = D.contracts[k]; if (c && String(c.symbol || '').toLowerCase() === cs && (c.kline || []).length >= 5) return { h: { d: c.kline.map(b => b.d), c: c.kline.map(b => b.c) }, own: true }; }
  return { h: D.adj || (D.hist && D.hist.d && D.hist.d.length ? D.hist : { d: [], c: [] }), own: false };
}
/* 候选规则开关：只存在这台设备的浏览器里（localStorage），默认都关。不影响 GitHub Actions 的推送提醒（那边按常规规则算） */
const PLAN_OPT_KEY = 'cockpit-planopt';
let PLAN_OPT_MEM = null;
function planOptGet() {
  if (PLAN_OPT_MEM) return PLAN_OPT_MEM;
  let o = {}; try { o = JSON.parse(localStorage.getItem(PLAN_OPT_KEY) || '{}') || {}; } catch (_) {}
  PLAN_OPT_MEM = { cs: o.cs === true, fx: o.fx === true }; return PLAN_OPT_MEM;
}
function planOptSet(k, on) {
  const o = Object.assign({}, planOptGet(), { [k]: !!on }); PLAN_OPT_MEM = o;
  try { localStorage.setItem(PLAN_OPT_KEY, JSON.stringify(o)); } catch (_) {}
  return o;
}
function planOptToggle(k) {
  if (k !== 'cs' && k !== 'fx') return;
  planOptSet(k, !planOptGet()[k]); renderSig(); try { planUpdate(true); } catch (_) {}
  const b = $('#shB'); if (b && b.querySelector('[data-opt]')) { const y = b.scrollTop; b.innerHTML = sigHelp(); b.scrollTop = y; }
}
function planSnap() {
  const A = acctGet(), cs = planCloses(), F = planForeign(D.capital && D.capital.members), h = D.adj ? D.adj : D.hist && D.hist.d && D.hist.d.length ? D.hist : { d: [], c: [] };
  const hl = h.d.length ? h.d[h.d.length - 1] : ((C().kline || []).slice(-1)[0] || {}).d || null, B = planBasis(D.spotBasis, hl), O = planOptGet(), sig = planSignals(cs, F.min, B.v, { contangoShort: O.cs, fxLong: O.fx, fmax: F.max });
  const px = cs.length ? cs[cs.length - 1] : planLastPx();
  const any = planOpen(A.trades), pos = curPos(), other = any && !pos ? any : null; let hold = null, mg = null, holdAny = null;
  if (any) { const hs = holdSeries(any), ho = planHold(hs.h, any), ma = hs.own ? (hs.h.c.length >= 20 ? hs.h.c.slice(-20).reduce((a, b) => a + b, 0) / 20 : null) : (sig.ma20 == null ? null : sig.ma20 * ho.k); holdAny = ho;
    if (pos) { hold = ho; mg = planManage({ side: pos.side, entry: pos.entryPx, peak: ho.peak, last: ho.last, ma20: ma, fsum: F.min, fall: F.sum }); } }
  const E = planEquity(A, holdAny ? holdAny.last : null), base = planEquity({ init: A.init, flows: A.flows, fee: A.fee, trades: A.trades.filter(t => t.exitD) }, null);
  const adjOn = !!D.adj, gate = planGate(F.used, hl, todayBJ(), { missing: F.missing, approx: F.approx, fD: F.lastD, adj: adjOn }), dl = planDataLine(gate, F.used, hl, F.lastD, adjOn, F.parts);
  const side = gate.ok ? (sig.longOK ? 1 : sig.shortOK ? -1 : 0) : 0;
  const size = !pos && side && base.equity > 0 ? planSize({ equity: base.equity, margin: A.margin / 100, price: px, side, mode: A.mode }) : null;
  return { A, cs, F, B, sig, px, pos, other, hold, mg, E, base, side, size, gate, dl };
}
/* 决策快照：开/平仓时存下当时的各面结论，以后用自己的实盘检验基本面有没有用 */
function planSnapshotNow(s) {
  const o = { d: todayBJ(), px: Math.round(s.px), pct: s.sig.pct == null ? null : Math.round(s.sig.pct), confirm: s.sig.confirm, delev: s.sig.delev, trendDn: s.sig.trendDn, fsum: Math.round(s.F.min), fsumAll: Math.round(s.F.sum), fsumK: s.F.minK, gateOk: s.gate.ok, basis: s.B && s.B.v != null ? +s.B.v.toFixed(4) : null, via: s.sig.via || null };
  try { const f = fundamentals(), c = C(); o.fund = f.dir || null; o.fundRatio = f.ratio == null ? null : +(+f.ratio).toFixed(2); o.tech = c.tech || null; o.struct = c.structure && !c.structure.thin ? c.structure.direction || null : null; const cp = capital(); o.cap = cp.verdict && cp.verdict.short ? cp.verdict.short : null; } catch (_) {}
  return o;
}
/* ---- 首页：交易信号条 ---- */
/* 交易计划面板：空仓时默认收起（首页信号格已经是结论），有持仓时默认展开；点信号格/「计划」按钮手动开关，记平仓后恢复自动 */
function planShown() { if (S.planShow === true || S.planShow === false) return S.planShow; return !!curPos(); }
function applyPlanVis() {
  const off = !planShown(), had = document.body.classList.contains('plan-off'); document.body.classList.toggle('plan-off', off);
  document.body.classList.toggle('holding', !!curPos());
  const b = $('#planBtn'); if (b) b.setAttribute('aria-pressed', String(!off));
  if (off !== had || MULTI !== multiOn()) renderChart();
}
function lastDayD() { try { const k = (C().kline || []).slice(-1)[0], a = D.adj && D.adj.d && D.adj.d.length ? D.adj.d[D.adj.d.length - 1] : '', kd = k ? k.d : ''; return a > kd ? a : kd; } catch (_) { return ''; } }   // 收盘价最新一天：日线 或 刚收盘接上的临时收盘价
function klineBase() {   // 日K线（latest.json 晚上才更新一次）+ 刚收盘当天的「临时日线」：用当天日盘 15 分钟线拼出开高低收，日线出来后自动以日线为准
  const k = C().kline || [];
  try {
    const kd = k.length ? k[k.length - 1].d : '', day = lastDayD(), m = D.m15 && D.m15[S.key]; if (!kd || !day || day <= kd || !m || !m.length) return k;
    const md = day.slice(5), bs = m.filter(x => x.d.slice(0, 5) === md && x.d.slice(6) >= '09:00' && x.d.slice(6) <= '15:00'); if (!bs.length || bs[bs.length - 1].d.slice(6) !== '15:00') return k;
    return k.concat([{ d: day, o: bs[0].o, h: Math.max(...bs.map(x => x.h)), l: Math.min(...bs.map(x => x.l)), c: bs[bs.length - 1].c, v: bs.reduce((a, x) => a + (x.v || 0), 0), oi: bs[bs.length - 1].oi, prov: true }]);
  } catch (_) { return k; }
}
/* ---- 当天未收盘的日K线（v101.58）：分钟线拼开高低收 + 实时价当收盘，盘中随实时价条每3秒变动 ---- */
function tradeDayOf(dt, yHint) {   // 'YYYY-MM-DD HH:MM…' 或 'MM-DD HH:MM' → 所属交易日：18点以后是夜盘，归下一个交易日（周五夜盘→周一；法定节假日不识别，日线出来后以日线为准）
  const full = dt[4] === '-', y = full ? +dt.slice(0, 4) : yHint, md = full ? dt.slice(5, 10) : dt.slice(0, 5), hm = full ? dt.slice(11, 16) : dt.slice(6, 11);
  const d = new Date(Date.UTC(y, +md.slice(0, 2) - 1, +md.slice(3, 5)));
  if (hm >= '18:00') { do { d.setUTCDate(d.getUTCDate() + 1); } while (d.getUTCDay() === 0 || d.getUTCDay() === 6); }
  else if (d.getUTCDay() === 6) d.setUTCDate(d.getUTCDate() + 2); else if (d.getUTCDay() === 0) d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}
function liveBar(k, m, tk) {   // 纯函数：k=已有日线(含刚收盘的临时日线)，m=15分钟线(d='MM-DD HH:MM')，tk=实时价{dt,c}或null。返回新的一根或null
  const last = k[k.length - 1]; if (!last) return null;
  const y0 = +last.d.slice(0, 4), mo0 = +last.d.slice(5, 7), yOf = md => (+md.slice(0, 2) < mo0 - 6 ? y0 + 1 : y0);
  const bars = (m || []).map(x => ({ x, T: tradeDayOf(x.d, yOf(x.d)) })), tT = tk ? tradeDayOf(tk.dt.slice(0, 16)) : null;
  let T = tT || ''; bars.forEach(z => { if (z.T > T) T = z.T; }); if (!T || T <= last.d) return null;
  const bs = bars.filter(z => z.T === T).map(z => z.x), tkOk = tk && tT === T;
  if (!bs.length && !tkOk) return null;
  let o, h, l, c, v = 0, oi = last.oi;
  if (bs.length) { o = bs[0].o; h = Math.max(...bs.map(x => x.h)); l = Math.min(...bs.map(x => x.l)); c = bs[bs.length - 1].c; v = bs.reduce((a, x) => a + (x.v || 0), 0); oi = bs[bs.length - 1].oi != null ? bs[bs.length - 1].oi : oi; }
  if (tkOk) { if (o == null) { o = h = l = tk.c; } c = tk.c; h = Math.max(h, tk.c); l = Math.min(l, tk.c); }
  const hm = bs.length ? bs[bs.length - 1].d.slice(6, 11) : '', closed = !!(tkOk ? sessOf(tk.dt.slice(11, 16)) === '日盘收' : bs.length && hm === '15:00');
  // 每个交易时段结束时的最新价：没有实时价时，用最后一根分钟线说明是哪个时段收的（早盘10:15、上午11:30、日盘15:00、夜盘23:00）
  const sess = tkOk ? sessOf(tk.dt.slice(11, 16)) : ({ '10:15': '早盘收', '11:30': '上午收', '15:00': '日盘收', '23:00': '夜盘收' })[hm] || null;
  const hmShow = tkOk ? tk.dt.slice(11, 16) : hm;
  return { d: T, o, h, l, c, v, oi, hm: hmShow, sess, prov: !!closed, live: !closed };
}
function sessOf(hm) {   // 最新成交的分钟 → 这是哪个时段收的价（时段结束到下个时段开始之间）；时段内部返回 null
  if (!hm) return null; if (hm >= '10:15' && hm < '10:30') return '早盘收'; if (hm >= '11:30' && hm < '13:30') return '上午收'; if (hm >= '15:00' && hm < '21:00') return '日盘收'; if (hm >= '23:00' || hm < '09:00') return '夜盘收'; return null;
}
function curTick(maxAge) {   // 实时价：交易中保留120秒（新浪偶尔失败不闪回）；时段已结束（休息/收盘）的最后成交价一直保留，它就是该时段的收盘价
  const t = D && D.ticks && D.ticks[S.key]; if (!t) return null;
  return Date.now() - t.at < (maxAge || 120000) || sessOf(t.dt.slice(11, 16)) ? t : null;
}   // 实时价保留120秒：新浪偶尔失败/限流时不会立刻退回收盘价
function klineNow() {
  const k = klineBase();
  try {
    const t = curTick(120000), b = liveBar(k, D.m15 && D.m15[S.key], t);
    return b ? k.concat([b]) : k;
  } catch (_) { return k; }
}
function pxLabel(ps) {   // 价格卡上价格旁边的小字：说明这个价是哪一刻的
  if (!ps) return '';
  const l = ps.last, md = l.d.slice(5);
  if (l.live) return md + ' ' + (l.sess ? l.sess + (l.hm ? ' ' + l.hm : '') : '盘中');
  return md + (l.prov ? ' 日盘收' + (l.hm ? ' ' + l.hm : '') : ' 收盘');
}
function lastBarD() { const d = lastDayD(); return d ? '（' + d.slice(5) + '）' : ''; }
function livePnl(t, ho) {   // 盘中参考浮盈（按最新15分钟/小时价），结论仍按收盘
  try { const lv = D.live && D.live[S.key], kd = lastDayD(); if (!lv || !kd || lv.dt.slice(0, 10) <= kd) return null; const px = lv.c * (ho.k || 1); return { px, fl: planPnl(t, px), r: (t.side >= 0 ? 1 : -1) * (px / t.entryPx - 1) * 100, dt: lv.dt.slice(5), src: lv.src }; } catch (_) { return null; }
}
function liveTxt() {   // 盘中价（小时线），只在比日线新时显示
  try { const lv = D.live && D.live[S.key], kd = lastDayD(); if (!lv || !kd || lv.dt.slice(0, 10) <= kd) return ''; return ` · 盘中 ${fmtD(lv.c)}（${lv.dt.slice(5)}）`; } catch (_) { return ''; }
}
const limPx = s => Math.round(s.px * (1 - s.side * TBT.LIM.pct / 100));
const LIMNOTE = () => `挂回调${TBT.LIM.pct}%：成交率约 ${TBT.LIM.fill}%（没成交就作废、不追），但回测收益更高——5年终值中位 ${TBT.LIM.med.toLocaleString('en-US')}万，高于挂收盘价 ${TBT.LIM.close}万、次日开盘市价 ${TBT.LIM.open}万。`;
/* ---- 数据灯 ↔ 趋势墙 对账（v101.55）：数据灯看“这一次抓取成功没有”，趋势墙看“历史里最新的点”，两边口径不同，对不上时要说清楚 ---- */
const IND_SER = { crush: 'crush', stock: 'stock', stu: 'stu', basis: 'basis', arrival: 'arrival', import: 'import', hogratio: 'hog', poultry: 'poultry', feed: 'feed', rmspread: 'rm' };
const SER_ALLOW = { daily: 6, weekly: 16, monthly: 75 };   // 历史最新点多久以内算“还新”（天）
function serLast(id) {
  const s = D.series && D.series[id]; if (!s || !s.pts || !s.pts.length) return null;
  const p = s.pts[s.pts.length - 1], ds = String(p.d), full = ds.length === 7 ? ds + '-28' : ds.length === 4 ? ds + '-12-28' : ds.slice(0, 10);
  const age = Math.floor((Date.parse(todayBJ() + 'T00:00:00Z') - Date.parse(full + 'T00:00:00Z')) / 864e5);
  return { d: ds, v: p.v, age, freq: s.freq, unit: s.unit, txt: L.fmtNum(p.v, s.unit), fresh: SER_ALLOW[s.freq] == null ? null : age <= SER_ALLOW[s.freq] };
}
function reconcile() {   // 返回 [{row, ser, issue}]：issue = 'hist_fresh'（数据灯说没数据/过期，但历史里有新点）| 'hist_old'（数据灯说正常，但趋势墙最新点很旧）
  const out = []; ((D.health && D.health.rows) || []).forEach(r => {
    if (r.kind !== 'indicator' || !IND_SER[r.key]) return; const ser = serLast(IND_SER[r.key]); if (!ser || ser.fresh == null) return;
    if ((r.state === 'nodata' || r.state === 'stale') && ser.fresh) out.push({ row: r, ser, issue: 'hist_fresh' });
    else if ((r.state === 'ok' || r.state === 'degraded') && !ser.fresh) out.push({ row: r, ser, issue: 'hist_old' });
  }); return out;
}
const reconNote = (r, ser) => ` <span class="dim" style="font-size:12.5px">趋势墙里这一项最近的点：<b>${esc(ser.txt)}</b>（${esc(ser.d)}，距今 ${ser.age} 天）——来自此前成功的抓取；本次没抓到，所以这一票本次没参与评分。</span>`;
const MISSW = [[/豆菜粕/, () => { const i = (D.indicators || []).find(z => z.key === 'rmspread'); return `${i && i.input ? '其实有数据，现在读数 ' + i.input + ' ' + (i.unit || '') + '，' : ''}但 2026-06 起口径换成三城市单值平均（约 800~900），旧阈值 400/700 不适用，会天天误判偏空，所以这一票暂不计分。不是没数据。`; }],
  [/巴西.*播种/, () => '播种进度只在巴西播种季（约 10~12 月）才有 CONAB 数据，每周发布一次；现在如果还是空，多半是这一期还没发布或抓取失败，可在 Actions「更新数据」日志里看。']];
const missWhy = x => { const n = String(x); for (const [r, f] of MISSW) if (r.test(n)) return f(); return '这一票现在没有可用数据。'; };
function healthBody(h) {   // 「数据」灯：把不可用 / 降权 / 手动是哪几项、为什么，逐条写出来
  const rows = (h.rows || []).filter(r => r.votes), li = r => { const rc = reconcile().find(x => x.row === r && x.issue === 'hist_fresh'); return `<li>${esc(r.icon || '')} <b>${esc(r.name)}</b>：${esc(r.label || '')}${r.detail ? '——' + esc(r.detail) : ''}${rc ? '<br>' + reconNote(r, rc.ser) : ''}</li>`; };
  const bad = rows.filter(r => r.state === 'stale' || r.state === 'nodata'), soft = rows.filter(r => r.state === 'degraded' || r.state === 'suppressed'), man = rows.filter(r => r.state === 'manual');
  const sec = (t, a, tip) => a.length ? `<p><b>${t}（${a.length}）</b><span style="color:var(--ink3)"> ${tip}</span></p><ul>${a.map(li).join('')}</ul>` : '';
  const ps = D.priceSrc, pc = D.priceCheck, em = ps ? Object.keys(ps.used || {}).filter(k => ps.used[k] === 'em') : [];
  const pLine0 = !ps ? `<p><b>盘中价格源</b><span style="color:var(--ink3)"> 现在不是交易时段，所以这里还没有内容。开盘后：新浪为主、东方财富备用，每 5 分钟两个源互相核对一次，结果会显示在这一行（“核对：一致/对不上”）。</span></p>` : ps ? `<p><b>盘中价格源</b><span style="color:var(--ink3)"> ${em.length ? '新浪取不到，已改用东方财富备用源（' + em.length + ' 个合约）' : '新浪（浏览器直连）；东方财富作备用'}${pc ? ' · 核对：' + (pc.ok === false ? '⚠️ 对不上，' : pc.ok ? '一致，' : '') + esc(pc.text) : ''}</span></p>` : '';
  const tkS = D.tickStat, tkLine = tkS ? `<p><b>实时价</b><span style="color:var(--ink3)"> 数据源：${({ sse: '东方财富实时推送（数据一变就推过来）', hq: '新浪逐笔报价', em: '东方财富实时价（轮询）', min: '新浪1分钟线（最慢，兜底）' })[tkS.src] || '—'}${tkS.src !== 'sse' && tkS.sseErr ? '；推送：' + esc(tkS.sseErr) : ''}${tkS.src !== 'hq' && tkS.errs ? Object.entries({ hq: '新浪逐笔报价', em: '东方财富', min: '新浪1分钟线' }).filter(([k]) => tkS.errs[k] && k !== tkS.src).map(([k, n]) => '；' + n + '：' + esc(tkS.errs[k])).join('') : ''} · 打开以来：成功 ${tkS.ok} 次 · 失败 ${tkS.fail} 次${tkS.ms != null ? ' · 最近一次耗时 ' + tkS.ms + ' 毫秒' : ''} · ${tkS.sseOn ? '推送中（另每15秒轮询核对一次）' : '当前取价间隔 ' + Math.round((tkS.delay || 3000) / 100) / 10 + ' 秒'} · 近1分钟价格变动 ${(tkS.chg || []).filter(x => Date.now() - x < 60000).length} 次${tkS.err ? ' · 最近一次失败：' + esc(tkS.err) + '（' + Math.round((Date.now() - tkS.errAt) / 1000) + ' 秒前）' : ''}</span></p><p><button class="lnk" data-probe="1">${D.probe && D.probe.busy ? '测试中…（约6秒）' : '测一测各个实时价来源'}</button>${D.probe && D.probe.rows ? '<span style="color:var(--ink3)"> ' + Math.round((Date.now() - D.probe.at) / 1000) + ' 秒前的结果：</span></p><ul>' + D.probe.rows.map(x => `<li><b>${esc(x.name)}</b>：${x.ok ? '✓ 通' : '✗ 不通'}（${x.ms} 毫秒）${esc(x.detail)}</li>`).join('') + '</ul>' : '</p>'}` : '', pLine = pLine0 + tkLine;
  const rcs = reconcile(), rcOld = rcs.filter(x => x.issue === 'hist_old');
  const rcLine = rcOld.length ? `<p><b>对账提醒（${rcOld.length}）</b><span style="color:var(--ink3)"> 数据灯说正常，但趋势墙里的最新点已经很旧：</span></p><ul>${rcOld.map(x => `<li><b>${esc(x.row.name)}</b>：趋势墙最新点 ${esc(x.ser.txt)}（${esc(x.ser.d)}，距今 ${x.ser.age} 天）</li>`).join('')}</ul>` : '';
  return `<p>${esc(h.sync.label)}</p>` + pLine + rcLine + sec('不可用', bad, '数据过期或拿不到，这一票没有参与评分') + sec('降权', soft, '数据偏晚、估算或处在扰动期，这一票的票权被调低') + sec('手动', man, '需要人工填值，没填或没更新，这一票不算自动') +
    (h.missing.length ? `<p><b>没参与评分的投票（${h.missing.length}）</b><span style="color:var(--ink3)"> 原因逐条写在后面：有的是没数据，有的是有数据但暂不计分</span></p><ul>${h.missing.map(x => `<li><b>${esc(String(x).split('(')[0])}</b>：${esc(missWhy(x))}</li>`).join('')}</ul>` : '') +
    (!bad.length && !soft.length && !man.length && !h.missing.length ? '<p>全部指标正常。</p>' : '');
}
/* v101.84：信号条上基差那一格（有数据：✓/✗ 期货≤现货 +2.35%；没有：灰色「基差无数据·不过滤」） */
function basisChip(sg, B) {
  if (typeof sg.basisOK !== 'boolean') return `<span class="sc sep" title="${esc((B && B.why) || '')}">基差无数据·不过滤</span>`;
  const t = (sg.basis >= 0 ? '+' : '') + (sg.basis * 100).toFixed(1) + '%';
  return `<span class="sc ${sg.basisOK ? 'y' : 'n'}" title="生意社 ${esc(B.d || '')}：现货 ${fmtD(B.spot)} / ${esc(B.dom || '主力')} ${fmtD(B.fut)}">${sg.basisOK ? '✓' : '✗'} 期货≤现货 ${t}</span>`;
}
/* 候选规则的信号条小标签：未启用 = 灰色「候选（未启用）」只提示；启用 = 绿色，且已经是入场信号 */
function candChips(sg) {
  const f = n => (n >= 0 ? '+' : '−') + Math.abs(Math.round(n)).toLocaleString('en-US'); let h = '';
  if (sg.cShortGo) h += '<span class="sc y" title="候选规则，你在「入场信号说明」里启用了">✓ 期货升水+趋势向下做空（候选·已启用）</span>';
  else if (sg.contangoShort) h += '<span class="sc sep" title="没有充分验证，默认不启用。要用：点信号格里的「数据和口径说明」，拉到最下面看回测再决定">候选：期货升水+趋势向下做空（未启用）</span>';
  if (sg.fxGo) h += '<span class="sc y" title="候选规则，你在「入场信号说明」里启用了">✓ 外资加杠杆 ' + f(sg.fxMax) + ' 手做多（候选·已启用）</span>';
  else if (sg.fxCand) h += '<span class="sc sep" title="没有充分验证，默认不启用。要用：点信号格里的「数据和口径说明」，拉到最下面看回测再决定">候选：外资加杠杆 ' + f(sg.fxMax) + ' 手做多（未启用）</span>';
  return h;
}
function renderSig() {
  const el = $('#sigbar'); if (!el) return;
  const s = planSnap(), sg = s.sig, F = s.F, f2 = n => (n >= 0 ? '+' : '−') + Math.abs(Math.round(n)).toLocaleString('en-US'), chip = (ok, t) => `<span class="sc ${ok ? 'y' : 'n'}">${ok ? '✓' : '✗'} ${t}</span>`;
  const blocked = !s.gate.ok, cls = blocked ? 'gate' : s.side > 0 ? 'long' : s.side < 0 ? 'short' : 'wait', head = blocked ? '数据不足，信号不可信' : s.side > 0 ? '做多信号' + (sg.fxGo ? '（外资加杠杆·候选）' : '') : s.side < 0 ? '做空信号' + (sg.cShortGo ? '（期货升水·候选）' : '') : '无入场信号';
  let sub; if (blocked) sub = s.gate.reasons.join('；'); else if (s.pos) sub = s.side ? `已有${sdName(s.pos.side)}单，不加仓` : planWhy(sg); else if (s.other) sub = `持仓在 ${s.other.contract || '另一个合约'}，不加仓` + (s.side ? '（这个合约的信号仅供参考）' : ''); else if (s.size) sub = `建议 ${fmtD(s.size.lots)} 手 · 次日限价 ${s.side > 0 ? '≤' : '≥'} ${fmtD(limPx(s))}（收盘价${s.side > 0 ? '回调' : '反弹'}0.3%） · 止损价 ${fmtD(s.size.stopPx)} · 占用 ${pc1(s.size.usage)}`; else if (s.side) sub = '权益不够开 1 手'; else sub = planWhy(sg);
  const dsOpen = !!S.dslOpen, dsIc = { ok: '✓', part: '!', bad: '!' }[s.dl.cls] || '!';
  const dsl = `<span class="dsw ${s.dl.cls}" id="dataLine"><span class="dsb" role="button" tabindex="0" data-dsl="1" aria-expanded="${dsOpen}" aria-label="数据状态：${esc({ ok: '齐全', part: '基本够用', bad: '不足' }[s.dl.cls])}，点开看详情"><i>${dsIc}</i><u>${dsOpen ? '收起' : '数据'}</u></span>${dsOpen ? `<span class="dst">${esc(s.dl.t)}<br><small>判定：缺外资数据/价格或超过7天没更新=不足；4–7天没更新、缺个别席位、席位只有估算值=基本够用；其余=齐全。</small></span>` : ''}</span>`;
  let left, right;
  if (!s.pos) {
    left = `<button class="sg ${cls}" data-goplan="1" aria-label="入场信号：${head}。${esc(sub)}。点击查看交易计划"><div class="cl">入场信号（收盘后看一次）· 最近收盘${lastBarD()} ${fmtD(s.px)}</div><div class="hd">${head}</div><div class="sb">${esc(sub)}</div>${s.size && !blocked ? `<div class="sb sb2">${esc(LIMNOTE())}</div>` : ''}
    <div class="scs${blocked ? ' dim' : ''}">${chip(sg.lowOK, '低位' + (sg.pct == null ? '' : ' ' + sg.pct.toFixed(0) + '%'))}${chip(sg.confirm, '反弹确认')}${chip(!sg.delev, '外资未去杠杆')}${basisChip(sg, s.B)}<span class="sc sep">空</span>${chip(sg.delev, '外资去杠杆')}${chip(sg.trendDn, '趋势向下')}${candChips(sg)}<span class="sc sep">外资5日 ${F.used.length ? '最弱 ' + F.minK.replace('期货', '') + ' ' + f2(F.min) + ' 手' : '无数据'}</span></div>${dsl}</button>`;
    right = s.other ? (() => { const o = s.other, ck = ['sep', 'may', 'jan'].find(k => String((D.contracts[k] || {}).symbol || '').toLowerCase() === String(o.contract || (D.contracts[autoKey()] || {}).symbol || '').toLowerCase()); return `<button class="sg" ${ck ? `data-ck="${ck}"` : 'data-goplan="toggle"'} aria-label="持仓在另一个合约，点击切换过去"><div class="cl">持仓在另一个合约</div><div class="hd">${esc(o.contract || '—')}</div><div class="sb">${sdName(o.side)} ${fmtD(o.lots)} 手 · 点这里切过去看</div></button>`; })() : `<button class="sg" data-goplan="toggle" aria-label="持仓：空仓。点击展开或收起交易计划"><div class="cl">持仓</div><div class="hd">空仓</div><div class="sb">账户权益 ${fmtD(s.E.equity)} 元（自动）${s.side && s.size ? '<br>成交后点这里「记录开仓」' : ''}</div></button>`;
  } else {
    const m = s.mg, ho = s.hold, t = s.pos, sd = t.side > 0, out = m.action !== '持有', fl = planPnl(t, ho.last), noF = !F.used.length;
    const stopPx = t.entryPx * (1 - (sd ? 1 : -1) * TPLAN.STOP / 100), stopGap = Math.abs((stopPx / ho.last - 1) * 100);
    const why = !out ? '没有触发止损、移动止盈或外资离场' : m.action === '止损' ? `浮亏 ${(-m.r).toFixed(1)}%，已到 ${TPLAN.STOP}% 止损` : m.action === '移动止盈' ? `最高浮盈 ${m.peakR.toFixed(1)}% 后回落已到 ${TPLAN.TRAIL}%` : m.action === '外资去杠杆·平多' ? `${F.minK} 5日 ${f2(F.min)} 手，≤ ${f2(TPLAN.DELEV)}` : `外资三家合计5日 ${f2(F.sum)} 手（≥0），或价格站上MA20`;
    const trailTxt = m.peakR >= TPLAN.ACT ? '移动止盈已启动' : `移动止盈未启动（最高浮盈 ${m.peakR.toFixed(1)}%<${TPLAN.ACT}%）`;
    const fch = sd ? chip(!m.delevOut, m.delevOut ? '外资去杠杆' : '外资未去杠杆') : chip(!(F.used.length && F.sum >= 0), '外资合计 ' + (F.used.length ? f2(F.sum) : '无数据') + (F.sum >= 0 && F.used.length ? '（回正）' : '，未回正')) + (sg.ma20 != null ? chip(!(ho.last > sg.ma20 * ho.k), '未站上MA20') : '');
    left = `<button class="sg pos ${out ? 'exit' : 'hold'}" data-goplan="toggle" aria-label="持仓信号：${out ? '该平仓：' + m.action : '继续持有'}。点击展开或收起交易计划"><div class="cl">收盘${lastBarD()} ${fmtD(ho.last)}${liveTxt()}</div><div class="hd">${out ? '该平仓 · ' + esc(m.action) : '继续持有'}</div>${out ? `<div class="sb">${esc(why)}</div>` : ''}
    <div class="scs">${chip(!m.stop, '止损 ' + fmtD(stopPx) + '（距 ' + stopGap.toFixed(1) + '%）')}${chip(!m.trail, m.peakR >= TPLAN.ACT ? '移动止盈已启动' : '移动止盈未启动')}${fch}</div>${blocked ? dsl : ''}</button>`;
    const up = fl >= 0, lp = livePnl(t, ho);
    right = `<div class="sgw rt"><div class="sg pos ${out ? 'exit' : 'hold'}" aria-label="持仓：${sdName(t.side)}${t.lots}手，浮盈亏 ${yuan(fl)} 元"><div class="cl">${sdName(t.side)} ${fmtD(t.lots)} 手 @${fmtD(t.entryPx)} · ${esc(t.entryD.slice(5))}</div><div class="hd big" style="color:${up ? 'var(--bull)' : 'var(--bear)'}">${yuan(fl)} <small>元</small></div>
      <div class="sb">${m.r >= 0 ? '+' : ''}${m.r.toFixed(1)}% · 账户权益 <b>${fmtD(s.E.equity)}</b> 元${lp ? `<br>盘中 ${fmtD(lp.px)}：${yuan(lp.fl)} 元${lp.r <= -TPLAN.STOP ? ' ⚠️已到止损线' : ''}` : ''}</div></div>${qb('placct')}</div>`;
  }
  el.innerHTML = `<div class="sgw">${left}${qb(s.pos ? 'plpos' : 'plsig')}</div>` + right;
  applyPlanVis();
}
/* ---- 交易计划页 ---- */
function sizeHtml(z, side, m, mode, eq, px) {
  const sd = sdName(side);
  let h = `<table class="tb3x tbpl"><tbody>
    <tr><td><b>建议入场价（${sd}，挂限价单）</b></td><td class="n"><b>${side > 0 ? '≤ ' : '≥ '}${fmtD(Math.round(px * (1 - side * TBT.LIM.pct / 100)))}</b>（收盘价${side > 0 ? '回调' : '反弹'}${TBT.LIM.pct}%，成交率约${TBT.LIM.fill}%但收益更高；挂 ${side > 0 ? '≤ ' : '≥ '}${fmtD(px)} 也行（成交率95%）；下一个交易日有效，没成交就作废；跳空${side > 0 ? '低开' : '高开'}按开盘价成交）</td></tr>
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
const qb = k => `<button class="q" data-about="${k}" aria-label="说明">?</button>`;
const PLAN_OPT = () => planOptGet();
/* 候选规则（默认不启用）：规则 + 回测数据 + 启用按钮，放在「入场信号：数据和口径说明」最后。数字出处：项目文档「豆粕策略加三条规则全回测」「外资条件作用」，2026-10-18 */
function shortCmpHtml() {
  return `<h3>做空条件：要同时满足，还是满足一个就行？（回测对比）</h3>
  <p>现在的规则是<b>①外资去杠杆 和 ②价格趋势向下 要同时满足</b>才做空。下面是把条件放宽、改成“满足一个就行”的回测（做多规则都一样，含「基差≥0」；2013–2026，收盘成交；<b>外资数据 2022 年才有，含外资条件的做空只有 2022 年以后的样本</b>）：</p>
  <table class="tb3x" style="font-size:12px"><thead><tr><th>做空触发条件</th><th>笔数</th><th>空单平均/合计</th><th>夏普22-26</th></tr></thead><tbody>
   <tr class="cur"><td>现在：①去杠杆 且 ②趋势向下</td><td class="n">16</td><td class="n">−0.0% / −0.7%</td><td class="n">1.08</td></tr>
   <tr><td>只要①去杠杆（不看趋势）</td><td class="n">56</td><td class="n">+0.1% / +6.7%</td><td class="n">1.17</td></tr>
   <tr><td>①去杠杆 且 仅“收盘&lt;MA20”（放宽趋势）</td><td class="n">32</td><td class="n">+0.2% / +7.3%</td><td class="n">1.20</td></tr>
   <tr><td>只要②趋势向下（不看外资）</td><td class="n">311</td><td class="n">−0.1% / −23.6%</td><td class="n">1.14</td></tr>
   <tr><td>①或②满足一个就做空</td><td class="n">351</td><td class="n">−0.1% / −20.4%</td><td class="n">1.16</td></tr>
   <tr><td>不做空（只做多）</td><td class="n">0</td><td class="n">—</td><td class="n">1.14</td></tr></tbody></table>
  <ul>
   <li><b>只看趋势会亏</b>：2013–2021 年单靠“价格跌就做空”有 238 笔、合计 −30%（2014、2016、2019 年都亏）；2022 年以后才转正（73 笔 +6.4%）。所以要有外资这个条件来筛。</li>
   <li><b>只看外资去杠杆</b>：笔数从 16 笔增到 56 笔，合计由 −0.7% 变 +6.7%，夏普（2022-26）由 1.08 升到 1.17，最大回撤都是 −23%；但 56 笔里有 45 笔入场时价格还没向下，平均只持有约 5 天，2025 年一年就亏 −10.8%。</li>
   <li><b>差别都不显著</b>：和现规则的年化差 +2.15%（95% 区间 −2.5% 到 +6.0%），空单 t 值只有 0.5；“放宽趋势”那条 +2.05%（区间 −1.5% 到 +4.9%）。包含 0，只是几十笔交易的差别。</li>
   <li><b>用事件检验（不看离场规则）</b>：2022 年后，外资去杠杆当天之后 10 个交易日平均 −0.13%（48 次新触发，54% 下跌），对比任意一天平均 +0.55%——有一点点偏空，但很弱；去杠杆且趋势向下 −0.61%（51 天），去杠杆但趋势没向下 −0.37%（100 天）。</li>
   <li><b>结论</b>：保持“同时满足”（最保守、只有 16 笔，基本不赚不赔）。放宽成“只要去杠杆”或“收盘&lt;MA20”看起来略好，但这是从几个写法里挑出来的、样本只有 2022 年后的 3 年多，不够证明。想试的话可以先用上面的候选规则记录实盘，攒够样本再改。</li>
  </ul>`;
}
function candHtml() {
  const O = planOptGet(), btn = (k, on) => `<p><button class="tb" data-opt="${k}" aria-pressed="${on}" style="padding:8px 14px;font-size:14px">${on ? '✓ 已启用 · 点这里关闭' : '启用这条规则'}</button>　<span style="color:var(--ink2)">当前：${on ? '已启用（只对这台设备的网页生效）' : '未启用（默认）'}</span></p>`;
  return `<h3>候选规则（默认都不启用）：先看回测，再决定要不要开</h3>
  <p style="color:var(--ink2)">这两条<b>没有通过「稳健性」检验</b>（样本少、差别只有几笔交易、不显著），所以不在默认规则里。启用后：满足条件时信号条会直接给出做多/做空信号和建议手数；离场规则和常规单完全一样；<b>只影响这台设备上的网页</b>（开关存在浏览器里），GitHub 推送提醒仍按常规规则，已有持仓不受影响。随时可以关。</p>
  <h3>候选A：期货高于现货 + 价格趋势向下 → 做空</h3>
  <p><b>规则</b>：生意社基差 &lt; 0（期货高于现货），且价格 &lt; MA20 &lt; MA60、低于5日前；<b>不要求外资去杠杆</b>。离场同常规空单（亏4%止损 / 最高浮盈≥8%后回落4% / 外资三家合计5日≥0 / 站上MA20）。本地自动交易里对应的开关是 SHORT_CONTANGO=1。</p>
  <table class="tb3x tbpl"><thead><tr><th>回测（2013-2026，收盘成交）</th><th>只加「基差≥0才做多」</th><th>再加本规则</th></tr></thead><tbody>
   <tr><td>夏普 2013-19 / 2020-26 / 2022-26</td><td class="n">0.11 / 0.89 / 1.08</td><td class="n">0.16 / 0.97 / 1.22</td></tr>
   <tr><td>2018 起 50 万终值 · 最大回撤</td><td class="n">1559万 · −59%</td><td class="n">1820万 · −52%</td></tr>
   <tr><td>5年窗口终值中位 / 最差</td><td class="n">670万 / 100万</td><td class="n">790万 / 109万</td></tr>
   <tr><td>交易笔数（其中空单）</td><td class="n">56（16）</td><td class="n">82（42）</td></tr></tbody></table>
  <ul><li>新增的 26 笔空单：平均 +0.46%，胜率 39%，t = 1.2（<b>不显著</b>）；2020 年前 13 笔 +0.20%，2020 年后 16 笔 +0.74%；收益集中在 2024 年。</li>
   <li>相对不加的年化差 +0.93%，block bootstrap 95% 区间 [−0.42%, +2.58%]，<b>包含 0</b>。</li>
   <li>次日开盘成交（更保守）：年化差只剩 +0.42%，最大回撤 −66%，最差 5 年窗口终值只有 63万。</li>
   <li>要求期货高于现货 <b>3% 以上</b>才可空：2022-26 夏普 1.17，终值 1684万（笔数 59，更少更稳，但也更不显著）。</li>
   <li>对照：「价格一跌就做空」（不要求期货升水、也不要求外资）2013-19 是亏的（172 笔均 −0.17%，t = −2.7），所以这条靠的是「期货升水」，不是靠趋势。</li>
   <li><b>判断</b>：边际为正、方向两半都对，但不显著，历史上豆粕期货很少高于现货，样本小；2026 年期货高于现货的天数约一半，以后会更常出现，可以启用后攒实盘记录再定。</li></ul>
  ${btn('cs', O.cs)}
  <h3>候选B：外资加杠杆直接做多</h3>
  <p><b>规则</b>：空仓，常规多单条件不成立，但<b>任一外资席位（摩根大通 / 瑞银 / 高盛）近 5 个交易日持仓变化 ≥ +${TPLAN.FX_TH.toLocaleString('en-US')} 手</b>，同时没有席位在去杠杆、基差不 &lt; 0（取不到基差不拦）→ 做多。离场同常规多单（亏4%止损 / 最高浮盈≥8%后回落4% / 外资去杠杆平多）。本地自动交易里是第 4 个策略 DOUPO-FX（模拟账户 4），在跑同一条规则做 A/B 对照。</p>
  <table class="tb3x tbpl"><thead><tr><th>回测（驾驶舱单做 年化 / 回撤 / 夏普）</th><th>现行规则</th><th>再加本规则</th></tr></thead><tbody>
   <tr><td>2022 年起（外资数据从这年才有）</td><td class="n">+58% / −49% / 1.18</td><td class="n">+83% / −41% / 1.42</td></tr>
   <tr><td>2018 年起</td><td class="n">+45% / −48% / 1.07</td><td class="n">+54% / −48% / 1.16</td></tr>
   <tr><td>与 ZIP 组合（COMBO）2022 起夏普</td><td class="n">1.42</td><td class="n">1.53</td></tr>
   <tr><td>交易笔数</td><td class="n">40</td><td class="n">45（多 6 笔，少 1 笔）</td></tr></tbody></table>
  <ul><li>多出的 6 笔：平均 +3.48%，胜率 83%，t = 1.3（<b>不显著</b>）；其中 2022-06-23 一笔 +14.8% 占了大头，其余 5 笔平均约 +1.2%。</li>
   <li><b>对门槛极敏感</b>：1 万手 → 夏普 0.96（比现行还差）；1.5~2.5 万 → 1.35~1.46；3 万 → 1.09；4 万 → 不触发。2 万是看着结果选的。</li>
   <li><b>越来越弱</b>：外资加杠杆之后 10 个交易日平均涨 +1.75%（37 个独立事件，t = 2.9），但 2022-24 年是 +3.10%，2025-26 年只有 +0.83%；账户收益也集中在 2022-01 ~ 2024-05。</li>
   <li>要求「趋势向上」或「反弹确认」再做多：不再有改善（夏普 1.09 / 1.12），所以它好的地方恰恰是<b>不等确认就进</b>——它是追随外资资金的信号，不是低吸信号，和这套策略的主体逻辑不同。</li>
   <li>外资数据只有约 4.7 年、主要是摩根大通一家，所有差别都是几笔交易的差别。</li>
   <li><b>判断</b>：有道理但没被证明。你说前期资本积累需要这个信号——可以启用，但<b>手数不要因为它加大</b>，并盯着本地 DOUPO-FX 的模拟账户数据：它和 DOUPO 唯一的区别就是这条规则，两账户权益差就是这条规则的真实贡献。</li></ul>
  ${btn('fx', O.fx)}`;
}
function sigTableHtml(s) {
  const sg = s.sig, F = s.F, f2 = n => (n >= 0 ? '+' : '−') + Math.abs(Math.round(n)).toLocaleString('en-US'), pct1 = x => x == null ? '—' : x.toFixed(0) + '%';
  const fwk = F => F.parts.length ? esc(F.minK.replace('期货', '')) + ' ' + f2(F.min) : '—', mk = (ok, y, n) => `<td class="${ok ? 'ok' : 'no'}">${ok ? '✓ ' + y : '✗ ' + n}</td>`;
  return `<h3>今日入场条件（当前值）</h3>  <table class="tb3x tbpl"><tbody>
   <tr><td>做多①价格低位（260日分位 ≤ ${TPLAN.LO}%）</td><td class="n">${pct1(sg.pct)}</td>${mk(sg.lowOK, '满足', '不满足')}</tr>
   <tr><td>做多②反弹确认（高于5日前，且高出前10日最低价1%）</td><td class="n">—</td>${mk(sg.confirm, '满足', '不满足')}</tr>
   <tr><td>做多③外资没有去杠杆（任一席位5日变化 > ${f2(TPLAN.DELEV)} 手）</td><td class="n">${fwk(F)}</td>${mk(!sg.delev, '满足', '外资去杠杆')}</tr>
   <tr><td>做多④期货不高于现货（生意社基差 ≥ 0）</td><td class="n">${typeof sg.basisOK === 'boolean' ? (sg.basis >= 0 ? '+' : '') + (sg.basis * 100).toFixed(2) + '%' : '—'}</td>${typeof sg.basisOK === 'boolean' ? mk(sg.basisOK, '满足', '期货高于现货') : '<td class="ok">无数据·不过滤</td>'}</tr>
   <tr><td>做空①外资去杠杆（任一席位5日变化 ≤ ${f2(TPLAN.DELEV)} 手）<b>·与②同时满足才做空</b></td><td class="n">${fwk(F)}</td>${mk(sg.delev, '满足', '不满足')}</tr>
   <tr><td>做空②价格 < MA20 < MA60，且低于5日前<b>·与①同时满足才做空</b></td><td class="n">${sg.ma20 == null ? '—' : fmtD(sg.ma20) + ' / ' + fmtD(sg.ma60)}</td>${mk(sg.trendDn, '满足', '不满足')}</tr>
   <tr><td>候选A（${PLAN_OPT().cs ? '已启用' : '未启用'}）：期货高于现货 + 趋势向下做空，不要求外资去杠杆</td><td class="n">${typeof sg.basis === 'number' ? (sg.basis >= 0 ? '+' : '') + (sg.basis * 100).toFixed(2) + '%' : '—'}</td><td class="${sg.contangoShort ? (sg.cShortGo ? 'ok' : 'no') : ''}">${sg.contangoShort ? (sg.cShortGo ? '出现 → 已当做空信号' : '出现（未启用，只提示）') : '没有'}<br><button class="tb optb" data-opt="cs" aria-pressed="${PLAN_OPT().cs}">${PLAN_OPT().cs ? '✓ 已启用 · 点此关闭' : '点此启用'}</button></td></tr>
   <tr><td>候选B（${PLAN_OPT().fx ? '已启用' : '未启用'}）：外资加杠杆直接做多（任一席位5日变化 ≥ +${TPLAN.FX_TH.toLocaleString('en-US')} 手）</td><td class="n">${F.max == null ? '—' : esc(F.maxK.replace('期货', '')) + ' ' + f2(F.max)}</td><td class="${sg.fxCand ? (sg.fxGo ? 'ok' : 'no') : ''}">${sg.fxCand ? (sg.fxGo ? '出现 → 已当做多信号' : '出现（未启用，只提示）') : sg.fxLever ? '席位加杠杆，但常规多单已成立/外资去杠杆/期货高于现货' : '没有'}<br><button class="tb optb" data-opt="fx" aria-pressed="${PLAN_OPT().fx}">${PLAN_OPT().fx ? '✓ 已启用 · 点此关闭' : '点此启用'}</button></td></tr>
  </tbody></table>
  <div class="plh">${basisLine(s.B)}</div>
  <div class="dsl ${s.dl.cls}">${esc(s.dl.t)}</div>`;
}
function basisLine(B) {
  if (!B || B.v == null) return '基差：' + esc((B && B.why) || '没有数据') + '。取不到时做多不看这一条（按原规则）。';
  return `基差（生意社 ${esc(B.d)}）：现货 ${fmtD(B.spot)} ÷ ${esc(B.dom || '主力合约')} ${fmtD(B.fut)} − 1 = <b>${(B.v >= 0 ? '+' : '') + (B.v * 100).toFixed(2)}%</b>${B.v < 0 ? '，期货高于现货' : ''}${B.age ? '（比价格日早 ' + B.age + ' 天）' : ''}。生意社现货价偏全国多地综合，比江苏/山东/广东港口价高约 80~90 元。`;
}
const POPH = { set: '', fl: '' };
const REASON_TXT = Object.fromEntries(PLAN_REASONS.filter(r => r[0]).map(r => [r[0], r[1]]));
const sgn1 = v => v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
function tradeDetailRow(t, cl) {   // 每笔交易下面一行小字：来源 / 极值 / 滑点 / 预计 / 原因备注（老记录没有的字段不显示）
  const rs = t.res || (!cl ? (() => { try { const pa = planPath(holdSeries(t).h, t); return pa ? { mfe: pa.mfe, mae: pa.mae } : null; } catch (_) { return null; } })() : null) || {}, pd = t.pred, src = planSrc(t), P = [];
  P.push(src === 'own' ? '自主开仓' : '系统信号');
  if (t.snap) P.push(`开仓时 基本面 ${esc(t.snap.fund || '—')} · 外资5日 ${t.snap.fsum >= 0 ? '+' : ''}${t.snap.fsum}`);
  if (rs.mfe != null) P.push(`${cl ? '' : '至今 '}最大浮盈 <b style="color:var(--bull)">${sgn1(rs.mfe)}</b> · 最大浮亏 <b style="color:var(--bear)">${sgn1(rs.mae)}</b>${rs.days != null ? ' · ' + rs.days + ' 个交易日' : ''}`);
  if (t.slipO != null || rs.slipX != null) P.push(`滑点 开 ${t.slipO != null ? sgn1(t.slipO) : '—'}${cl ? ' / 平 ' + (rs.slipX != null ? sgn1(rs.slipX) : '—') : ''}（正=比信号日收盘价/触发价更不利）`);
  if (pd && pd.win != null) P.push(`开仓时预计：胜率 ${Math.round(pd.win * 100)}%${pd.rr != null ? ' · 盈亏比 ' + (pd.rr >= 10 ? '10+' : pd.rr.toFixed(1)) + ':1' : ''}${pd.ev != null ? ' · 期望 ' + sgn1(pd.ev) : ''}${pd.stopP != null ? ' · 止损概率 ' + Math.round(pd.stopP * 100) + '%' : ''}`);
  const why = [cl && rs.reason ? '平仓：' + (REASON_TXT[rs.reason] || '') : '', t.note ? '开仓备注：' + t.note : '', rs.note ? '平仓备注：' + rs.note : ''].filter(Boolean); if (why.length) P.push(why.map(esc).join(' · '));
  return `<tr class="tdx"><td colspan="10">${P.map((x, i) => i === 0 ? esc(x) : x).join(' ｜ ')}</td></tr>`;
}
function reviewHtml(A) {
  const R = planReview(A.trades, A.fee); if (!R.n) return '';
  const pc = v => v == null ? '—' : Math.round(v * 100) + '%', g = (n, x) => `<tr><td>${n}</td><td class="n">${x.n}</td><td class="n">${pc(x.win)}</td><td class="n">${sgn1(x.ret)}</td><td class="n" style="color:${x.net >= 0 ? 'var(--bull)' : 'var(--bear)'}">${yuan(Math.round(x.net))}</td></tr>`;
  const pv = R.predN ? `预计胜率平均 ${pc(R.predWin)} · 实际 ${pc(R.actWinOfPred)}（${R.predN} 笔有预计）；预计单笔期望 ${sgn1(R.predEv)} · 实际 ${sgn1(R.actRetOfPred)}。` : '这些交易开仓时还没存「预计」，从下一笔开始对照。';
  return `<details class="plx"><summary>实盘复盘（${R.n} 笔已平仓）：系统预计 vs 实际 · 滑点 · 来源</summary>
  <table class="tb3x tbpl"><thead><tr><th>分组</th><th class="n">笔数</th><th class="n">胜率</th><th class="n">平均涨跌</th><th class="n">净盈亏</th></tr></thead><tbody>${g('全部', R.all)}${g('按系统信号开', R.sys)}${g('自主开仓', R.own)}${g('多单', R.long)}${g('空单', R.short)}</tbody></table>
  <div class="plh">${pv}</div>
  <div class="plh">平均滑点：开仓 ${sgn1(R.slipO)}、平仓 ${sgn1(R.slipX)}（正数=比信号日收盘价/触发价更不利）；平均最大浮盈 ${sgn1(R.mfe)}、最大浮亏 ${sgn1(R.mae)}；平均持有 ${R.days == null ? '—' : R.days.toFixed(1)} 个交易日；赚钱的单平均只拿到最大浮盈的 ${R.capture == null ? '—' : Math.round(R.capture * 100)}%。</div>
  <div class="plh">${R.n < 20 ? '样本不足 20 笔，只看趋势，别当结论。' : ''}「按系统信号开」和「自主开仓」分开统计，攒够了就能回答：自己加的单是帮了系统还是拖了后腿。</div></details>`;
}
function planBodyHtml(s) {
  const A = s.A, sg = s.sig, F = s.F, f2 = n => (n >= 0 ? '+' : '−') + Math.abs(Math.round(n)).toLocaleString('en-US'), pct1 = x => x == null ? '—' : x.toFixed(0) + '%';
  const fwk = F => F.parts.length ? esc(F.minK.replace('期货', '')) + ' ' + f2(F.min) : '—', mk = (ok, y, n) => `<td class="${ok ? 'ok' : 'no'}">${ok ? '✓ ' + y : '✗ ' + n}</td>`, inp = (id, v, ph, extra) => `<input id="${id}" inputmode="decimal" value="${esc(v)}" placeholder="${esc(ph || '')}" ${extra || ''}>`;
  const sel = (id, cur, opts, extra) => `<select id="${id}" ${extra || ''}>${opts.map(([k, n]) => `<option value="${k}"${String(cur) === String(k) ? ' selected' : ''}>${n}</option>`).join('')}</select>`;
  const head = !s.gate.ok ? '数据不足，信号不可信' : s.side > 0 ? '满足做多入场条件' : s.side < 0 ? '满足做空入场条件' : '没有入场信号，观望';
  const pmsg = PMSG ? `<div class="plw pmsg" role="status">${esc(PMSG)}</div>` : '';
  let h = '';
  /* ① 今日信号（页面分块：ps1..ps5，电脑端排成两列一屏放下） */
  h += `<div class="plt">今日入场信号 ${qb('plsig')}</div><div class="hl plhead"><b>${head}</b><br><span style="color:var(--ink2)">${esc(!s.gate.ok ? s.gate.reasons.join('；') + '。先别按这个信号操作' : planWhy(sg))}${s.pos && s.side ? '。你已有持仓，不加仓' : ''}</span>${s.gate.warn.length ? '<br><span class="plh">' + esc(s.gate.warn.join('；')) + '</span>' : ''}</div>
`;
  if (!s.pos && !s.other && s.side) h += s.size ? `<div class="plt">建议这样开仓（权益 ${fmtD(s.base.equity)} 元，自动算）</div>` + sizeHtml(s.size, s.side, A.margin / 100, A.mode, s.base.equity, s.px) : `<div class="plw">权益 ${fmtD(s.base.equity)} 元不够开 1 手（1手保证金约 ${fmtD(s.px * TPLAN.TON * A.margin / 100)} 元）。</div>`;
  /* ② 持仓管理 */
  h += `\u0001<div class="plt">持仓管理 ${qb('plpos')}</div>`;
  if (!s.pos && s.other) {
    h += `<div class="plh">你的持仓在 <b>${esc(s.other.contract || '另一个合约')}</b>：${sdName(s.other.side)} ${fmtD(s.other.lots)} 手 @ ${fmtD(s.other.entryPx)}。同一时间只持一笔，先在那个合约里平仓。</div>`;
  } else if (!s.pos) {
    const ds = s.side || 1, lots = s.size ? s.size.lots : '';
    h += `<div class="plf">
      <label>开仓日期${inp('pf-od', todayBJ(), 'YYYY-MM-DD')}</label>
      <label>方向${sel('pf-os', ds, [[1, '做多'], [-1, '做空']])}</label>
      <label>手数${inp('pf-ol', lots, '手')}</label>
      <label>成交均价（元/吨）${inp('pf-op', Math.round(s.px), '')}</label>
      <label>开仓手续费（元，留空=每手${fmtD(A.fee)}元的一半）${inp('pf-of', '', '留空自动')}</label></div>
      <details id="pf-more-o" class="plmore"><summary>备注（可选，会进CSV）</summary><div class="plf"><label>备注${inp('pf-on', '', '如：看了库存报告 / 手动加的')}</label></div></details>
      <button class="pbtn" data-act="open">记录开仓</button>`;
  } else {
    const t = s.pos, m = s.mg, ho = s.hold, out = m.action !== '持有', fl = planPnl(t, ho.last), sd = t.side > 0, usage = t.lots * TPLAN.TON * ho.last * (A.margin / 100) / (s.E.equity > 0 ? s.E.equity : 1);
    const why2 = !out ? '没有触发止损、移动止盈或外资离场。' : m.action === '止损' ? `浮亏 ${(-m.r).toFixed(1)}%，已到 ${TPLAN.STOP}% 止损。` : m.action === '移动止盈' ? `持仓期间最高浮盈 ${m.peakR.toFixed(1)}%（≥${TPLAN.ACT}%），且从${sd ? '最高' : '最低'}价回落已到 ${TPLAN.TRAIL}%。` : m.action === '外资去杠杆·平多' ? `${esc(s.F.minK)} 5日变化 ${f2(s.F.min)} 手，≤ ${f2(TPLAN.DELEV)}。` : `外资三家合计5日变化 ${f2(s.F.sum)} 手（≥0），或价格已站上MA20。`;
    const trigPx = sd ? ho.peak * (1 - TPLAN.TRAIL / 100) : ho.peak * (1 + TPLAN.TRAIL / 100), stopPx = t.entryPx * (1 - (sd ? 1 : -1) * TPLAN.STOP / 100), actPx = t.entryPx * (1 + (sd ? 1 : -1) * TPLAN.ACT / 100);
    const trailTxt = m.peakR >= TPLAN.ACT ? `已启动：${sd ? '跌破' : '涨过'} ${fmtD(trigPx)} 平仓（距现价 ${Math.abs((trigPx / ho.last - 1) * 100).toFixed(1)}%）` : `未启动（最高浮盈 ${m.peakR.toFixed(1)}% < ${TPLAN.ACT}%）；价格到 ${fmtD(actPx)} 后启动`;
    const dist = x => Math.abs((x / ho.last - 1) * 100).toFixed(1) + '%', card = (l, v, sub, tone) => `<div class="hvk${tone ? ' t' + tone : ''}"><i>${l}</i><b>${v}</b>${sub ? `<em>${sub}</em>` : ''}</div>`;
    const rtr = Math.max(0, sd ? (1 - ho.last / ho.peak) * 100 : (ho.last / ho.peak - 1) * 100), stGap = Math.abs((stopPx / ho.last - 1) * 100), fTone = sd ? (s.F.min > 0 ? 'g' : s.F.min > TPLAN.DELEV ? 'a' : 'r') : (s.F.sum < 0 ? 'g' : 'r'), uTone = usage < 0.5 ? 'g' : usage < 0.8 ? 'a' : 'r';
    h += `<div class="hv">${card('现价', fmtD(ho.last), '截至 ' + (ho.lastD ? esc(ho.lastD.slice(5)) : '开仓日'), fl >= 0 ? 'r' : 'g')}${card('止损价', fmtD(stopPx), '距现价 ' + dist(stopPx), stGap < 1 ? 'r' : 'a')}${card('移动止损', m.peakR >= TPLAN.ACT ? fmtD(trigPx) : '未启动', m.peakR >= TPLAN.ACT ? '止损已改到此价 · 距 ' + dist(trigPx) : '到 ' + fmtD(actPx) + ' 改成移动止损', m.peakR >= TPLAN.ACT ? 'g' : '')}${card('回撤', rtr.toFixed(1) + '%', (sd ? '最高 ' : '最低 ') + fmtD(ho.peak) + ' · 最高浮盈 ' + m.peakR.toFixed(1) + '%', m.peakR >= TPLAN.ACT ? (rtr >= TPLAN.TRAIL * 0.75 ? 'r' : 'a') : (rtr > 0 ? 'a' : 'g'))}${card('持有', ho.days + ' 天', '风险度 ' + pc1(usage), uTone)}${card(sd ? '外资最弱席位' : '外资三家合计', (sd ? f2(s.F.min) : f2(s.F.sum)) + ' 手', sd ? esc(s.F.parts.length ? s.F.minK.replace('期货', '') : '5日变化') : '5日变化', fTone)}</div>
    ${ho.covered ? '' : `<div class="plh">开仓日晚于已有价格数据，最高/最低价暂按开仓价，数据更新后自动补上。</div>`}
    <div class="plt hvc">${out ? '已平仓？记一笔' : '平仓'}</div><div class="plf">
      <label>平仓日期${inp('pf-cd', todayBJ(), 'YYYY-MM-DD')}</label>
      <label>成交均价${inp('pf-cp', Math.round(ho.last), '')}</label>
      <label>手续费（留空自动）${inp('pf-cf', '', '留空自动')}</label></div>
      <details id="pf-more-c" class="plmore"><summary>平仓原因 · 备注（可选，会进复盘和CSV）</summary><div class="plf"><label>平仓原因${sel('pf-cr', '', PLAN_REASONS)}</label><label>备注${inp('pf-cn', '', '如：怕回吐提前走')}</label></div></details>
      <button class="pbtn${out ? ' warn' : ''}" data-act="close">记录平仓</button>`;
  }
  /* ③ 账户权益 */
  const E = s.E, st = planStats(A);
  h += `\u0001<div class="plt">账户权益（自动）${qb('placct')}</div><div class="hl"><b>${fmtD(E.equity)} 元</b>　<span style="color:var(--ink2)">= 初始 ${fmtD(E.init)} ${yuan(E.flows)}出入金 ${yuan(E.realized)}已平仓 ${yuan(E.floating)}持仓浮动 −${fmtD(E.fees)}手续费</span></div>
   <div class="plh">${st.n ? `已平仓 ${st.n} 笔，胜 ${st.wins} 笔（${(st.wins / st.n * 100).toFixed(0)}%），净盈亏 ${yuan(st.net)} 元（已扣手续费）。` : '还没有已平仓记录。'} 云端：<span class="cloudmsg">${esc(cloudShort())}</span></div>
`;
  POPH.set = `<div class="pph">账户设置 · 出入金 · 对账校准<button class="xbtn" data-pop="x" aria-label="关闭">×</button></div><div class="plf">
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
   <button class="pbtn" data-act="calib">按实际权益校准</button>
   ${cloudHtml()}${pushHtml()}`;
  /* ④ 交易记录 */
  h += `\u0001<div class="plt">交易记录</div>`;
  if (!A.trades.length) h += `<div class="plh">暂无记录。</div>`;
  else h += `<div style="overflow-x:auto"><table class="tb3x tbcv"><thead><tr><th>开仓</th><th>方向</th><th class="n">手数</th><th class="n">开仓价</th><th>平仓</th><th class="n">平仓价</th><th class="n">手续费</th><th class="n">净盈亏</th><th class="n">价格涨跌</th><th></th></tr></thead><tbody>${A.trades.slice().reverse().map(t => {
      const cl = !!t.exitD, fee = planFee(t, A.fee), net = cl ? planPnl(t, t.exitPx) - fee : null, ret = cl ? (t.side >= 0 ? 1 : -1) * (t.exitPx / t.entryPx - 1) * 100 : null;
      return `<tr><td>${esc(t.entryD)}</td><td>${sdName(t.side)}</td><td class="n">${fmtD(t.lots)}</td><td class="n">${fmtD(t.entryPx)}</td><td>${cl ? esc(t.exitD) : '持仓中'}</td><td class="n">${cl ? fmtD(t.exitPx) : '—'}</td><td class="n">${fmtD(fee)}</td><td class="n" style="color:${net == null ? 'inherit' : net >= 0 ? 'var(--bull)' : 'var(--bear)'}">${net == null ? '—' : yuan(net)}</td><td class="n">${ret == null ? '—' : (ret >= 0 ? '+' : '') + ret.toFixed(1) + '%'}</td><td><button class="xbtn" data-act="delt" data-id="${esc(t.id)}" aria-label="删除这笔记录">×</button></td></tr>${tradeDetailRow(t, cl)}`; }).join('')}</tbody></table></div>${reviewHtml(A)}`;
  POPH.fl = `<div class="pph">出入金记录（${A.flows.length} 笔）<button class="xbtn" data-pop="x" aria-label="关闭">×</button></div>${A.flows.length ? `<table class="tb3x tbcv"><tbody>${A.flows.map((f, i) => `<tr><td>${esc(f.d)}</td><td class="n">${yuan(+f.amt)}</td><td>${esc(f.note || '')}</td><td><button class="xbtn" data-act="delf" data-i="${i}" aria-label="删除这笔出入金">×</button></td></tr>`).join('')}</tbody></table>` : '<div class="plh">暂无出入金记录。</div>'}`;
  POPH.fl += `<div class="plh" style="margin-top:8px">记录只存本机浏览器。<button class="lnk" data-act="backup">备份下载</button> · <button class="lnk" data-act="csv">导出CSV（含决策快照、预计、滑点、路径）</button> · <label class="lnk">恢复备份<input id="pf-file" type="file" accept=".json,application/json" hidden></label></div>`;
  /* 折叠：阶梯、回测摘要 */
  h += `\u0001<details id="pf-mo"><summary>历史开仓月份</summary><div class="plh">背景参考：信号出现的频率有参考，盈亏没有。</div>${monthHtml()}</details><details id="pf-lad"><summary>仓位阶梯</summary><div class="plh">权益越大，占用越低。</div>${ladderHtml(s.base.equity)}</details><details id="pf-bt"><summary>回测摘要</summary><div class="plh">样本内结果，仅供参考。</div>${planBtHtml()}</details><details id="pf-mv"><summary>多品种回测（别的品种能用同一套规则吗？）</summary><div class="plh">结论：不能直接套。</div>${mvHtml()}</details>`;
  const q = h.split('\u0001');   // [入场信号, 持仓管理, 账户权益, 交易记录, 折叠项]：电脑端两列排版时按 入场/账户/记录 | 持仓 的顺序放，高度才平衡
  return pmsg + `<div class="plgrid"><div class="ps ps1">${s.pos ? '' : q[0]}</div><div class="ps ps3">${q[2]}</div><div class="ps ps4">${q[3]}${s.pos ? `<div class="exp">${expectHtml(s)}</div>` : ''}</div><div class="ps ps2">${q[1]}</div><div class="ps ps5">${q[4]}</div></div>`;
}

const EXP_CACHE = {};
function expectCalc(s) {   // 当前持仓的推演（缓存：同一个持仓和同一根价格不重复算）
  const t = s.pos, ho = s.hold; if (!t || !ho) return null;
  const hs = holdSeries(t).h, c = hs && hs.c ? hs.c : []; if (c.length < 300) return null;
  const own = planSrc(t) === 'own', held = t.side < 0 ? hs.d.filter(d => d > t.entryD).length : -1, key = [t.id, t.side, t.entryPx, ho.last, ho.peak, c.length, own, held].join('|'); if (EXP_CACHE.k === key) return EXP_CACHE.v;
  const rets = []; for (let i = Math.max(1, c.length - 1500); i < c.length; i++) rets.push(c[i] / c[i - 1] - 1); const mu = rets.reduce((a, b) => a + b, 0) / rets.length, r0 = rets.map(x => x - mu);
  const closes = c.slice(-30).map(x => x * ho.k), v = planExpect({ side: t.side, entry: t.entryPx, peak: ho.peak, last: ho.last, closes, rets: r0, n: 2000, edge: own ? 0 : (t.side < 0 ? TBT.SEDGE : TBT.EDGE), flipHeld: held >= 0 ? held : null });
  EXP_CACHE.k = key; EXP_CACHE.v = v ? Object.assign(v, { hist: c.slice(-40).map(x => x * ho.k), histD: hs.d.slice(-40) }) : null; return EXP_CACHE.v;
}
function planPred(s) {   // 开仓后立刻存下系统当时的预计（以后和实际对照）
  try { const t = s.pos; if (!t || !s.hold) return null; const x = expectCalc(s), own = planSrc(t) === 'own', bt = t.side > 0 ? TBT.long : TBT.short;
    const r = v => v == null || !isFinite(v) ? null : +(+v).toFixed(3);
    return { src: planSrc(t), win: r(own && x ? x.win : bt.win), ev: r(own && x ? x.mean : bt.avg), rr: x ? r(Math.min(99, x.rrNow)) : null, stopP: x ? r(x.stopP) : null, med: x ? x.medDays : null, flipP: x && t.side < 0 ? r(x.flipP) : null, bt: bt.n }; } catch (_) { return null; }
}
function expectChart(x, t, ho, stopPx, trigPx) {
  const W = 640, Hh = 230, L = 8, Rr = 84, T = 10, B = 18, hist = x.hist, nh = hist.length, nf = x.fan.length, tot = nh + nf - 1;
  const vals = hist.concat(x.fan.map(f => f.p10), x.fan.map(f => f.p90), [t.entryPx, stopPx]); if (trigPx) vals.push(trigPx);
  let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * .06 || 5; lo -= pad; hi += pad;
  const X = i => L + (W - L - Rr) * i / tot, Y = v => T + (Hh - T - B) * (1 - (v - lo) / (hi - lo)), f1 = v => Math.round(v * 10) / 10;
  const line = a => a.map((v, i) => `${i ? 'L' : 'M'}${f1(X(i))},${f1(Y(v))}`).join('');
  const band = (u, l2) => { const up = x.fan.map((f, i) => `${f1(X(nh - 1 + i + 1))},${f1(Y(f[u]))}`), dn = x.fan.map((f, i) => `${f1(X(nh - 1 + i + 1))},${f1(Y(f[l2]))}`).reverse(); return `M${f1(X(nh - 1))},${f1(Y(hist[nh - 1]))}L` + up.join('L') + 'L' + dn.join('L') + 'Z'; };
  const med = [hist[nh - 1]].concat(x.fan.map(f => f.p50)), hl = (v, cls, lab) => `<line x1="${L}" x2="${W - Rr}" y1="${f1(Y(v))}" y2="${f1(Y(v))}" class="${cls}"/><text x="${W - Rr + 4}" y="${f1(Y(v)) + 3.5}" class="${cls}t">${lab} ${fmtD(v)}</text>`;
  return `<svg class="exsv" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="日K线收盘价与未来20个交易日的推演区间">
    <path d="${band('p10', 'p90')}" class="exb2"/><path d="${band('p25', 'p75')}" class="exb1"/>
    ${hl(t.entryPx, 'exl', '开仓')}${hl(stopPx, 'exs', '止损')}${trigPx ? hl(trigPx, 'ext', '移动止损') : ''}
    <path d="${line(hist)}" class="exh"/><path d="${med.map((v, i) => `${i ? 'L' : 'M'}${f1(X(nh - 1 + i))},${f1(Y(v))}`).join('')}" class="exm"/>
    <line x1="${f1(X(nh - 1))}" x2="${f1(X(nh - 1))}" y1="${T}" y2="${Hh - B}" class="exn"/>
    <text x="${f1(X(nh - 1)) - 4}" y="${Hh - 4}" text-anchor="end" class="exa">${esc(String(x.histD[nh - 1] || '').slice(5))} 现在</text><text x="${W - Rr}" y="${Hh - 4}" text-anchor="end" class="exa">+${nf} 个交易日</text>
    <circle cx="${f1(X(nh - 1))}" cy="${f1(Y(hist[nh - 1]))}" r="3.5" class="exd"/></svg>`;
}
function expectHtml(s) {
  const t = s.pos, ho = s.hold, x = expectCalc(s); if (!t || !ho) return '';
  const sd = t.side > 0, src = planSrc(t), own = src === 'own', bt = sd ? TBT.long : TBT.short, not = t.lots * TPLAN.TON * t.entryPx, A = s.A, fee = (+A.fee || 0) * t.lots, yv = v => yuan(Math.round(v)), w = planWilson(Math.round(bt.win * bt.n), bt.n);
  const win = own && x ? x.win : bt.win, exp = (own && x ? x.mean : bt.avg) * not / 100 - fee, loss = -TPLAN.STOP * not / 100 - fee, rrBt = Math.abs(bt.avgWin / bt.avgLoss);
  const gainY = own && x ? x.gainNow : bt.avgWin, lossY = own && x ? x.lossNow : Math.abs(bt.avgLoss);
  const card = (l, v, sub, tone) => `<div class="hvk${tone ? ' t' + tone : ''}"><i>${l}</i><b>${v}</b>${sub ? `<em>${sub}</em>` : ''}</div>`;
  const F = s.F, tail = F.used && F.used.length ? (sd ? F.min > TPLAN.DELEV : F.sum < 0) : null, ma = s.sig && s.sig.ma20 != null ? ho.last < s.sig.ma20 * ho.k : null, against = tail === false;
  const chip = (ok, txt) => ok == null ? '' : `<span class="sc ${ok ? 'y' : 'n'}">${ok ? '✓' : '✗'} ${txt}</span>`;
  const rr = x ? x.rrNow : null, adv = planAdvice({ src, side: t.side, r: s.mg ? s.mg.r : 0, rr, ev: x ? x.evNow : 0, gain: x ? x.gainNow : 0, loss: x ? x.lossNow : 0, act: s.mg ? s.mg.action : '持有', against, entry: t.entryPx, entryTxt: fmtD(t.entryPx) });
  const rrTone = rr == null ? '' : rr >= adv.th ? 'g' : rr >= 1 ? 'a' : 'r';
  const cards = `<div class="hv exc">${card('预计胜率', Math.round(win * 100) + '%', own ? '无入场优势：按随机推演' : `回测同方向 ${bt.n} 笔，90% 区间 ${Math.round(w[0] * 100)}–${Math.round(w[1] * 100)}%`, win >= .55 ? 'g' : win < .45 ? 'a' : '')}${card('预计盈利', yv(exp) + ' 元', `平均赚 ${yv(gainY * not / 100 - fee)} · 平均亏 ${yv(-lossY * not / 100 - fee)}`, exp >= 0 ? 'r' : 'g')}${card('预计盈亏比', rr == null ? '—' : adv.rrT, `继续持有的再赚/再亏 · 回测 ${rrBt.toFixed(1)}:1`, rrTone)}${card('止损亏损', yv(loss) + ' 元', x ? `触发止损概率 ${(x.stopP * 100).toFixed(1)}%` : '到止损价平仓', 'a')}</div>`;
  const stopPx = t.entryPx * (1 - (sd ? 1 : -1) * TPLAN.STOP / 100), trig = s.mg && s.mg.peakR >= TPLAN.ACT ? (sd ? ho.peak * (1 - TPLAN.TRAIL / 100) : ho.peak * (1 + TPLAN.TRAIL / 100)) : null;
  const chart = x ? expectChart(x, t, ho, stopPx, trig) : '<div class="plh">价格历史不足，画不出推演。</div>';
  const out = x && !sd ? `预计持有 约 ${x.medDays} 天 · 外资翻转离场 ${(x.flipP * 100).toFixed(0)}% · 站上MA20 ${(x.maP * 100).toFixed(0)}% · 止损 ${(x.stopP * 100).toFixed(1)}%` : x ? `预计持有 约 ${x.medDays} 天 · ${x.maP > .5 ? `站上MA20离场 ${(x.maP * 100).toFixed(0)}%` : x.trailP > .3 ? `移动止盈离场 ${(x.trailP * 100).toFixed(0)}%` : `到期未离场 ${(x.holdP * 100).toFixed(0)}%`} · 止损 ${(x.stopP * 100).toFixed(1)}%` : '';
  const advH = `<div class="exadv ${adv.lv}"><b>${esc(adv.head)}</b>${adv.L.map(l => `<div>${esc(l)}</div>`).join('')}</div>`;
  return `<div class="plt">预期与建议 · 回测经验，不是预测</div>${advH}<div class="exchips"><button class="lnk exsrc" data-act="src" title="点一下切换：按系统信号开的 / 自己开的（开仓时系统没给信号）">${own ? '自主开仓（没有系统信号）' : '按系统信号开仓'} · 点此切换</button>${chip(tail, sd ? '外资未去杠杆' : '外资合计未回正')}${sd ? '' : chip(ma, '在MA20下方')}<span class="sc">基本面 回测无预测力，不计入</span></div>${cards}
  <div class="exw">${chart}<div class="exleg"><span class="lg1"></span>中位 <span class="lg2"></span>25–75% <span class="lg3"></span>10–90% · ${out}</div></div>
  <div class="plh exn2">推演：${own ? '自己开的单没有入场优势，所以按「无优势」随机推演' : sd ? '每天顺持仓方向的平均优势 0.09%（让平均收益≈回测单笔平均 ' + bt.avg.toFixed(1) + '%）' : '每天顺持仓方向的平均优势 0.22%（加上外资翻转后，胜率≈64%、平均≈+1.0%、持有约4天，对上回测空单）'}，2,000 条路径，沿用同样的止损 / 移动止盈 / ${sd ? '外资去杠杆（多单不计翻转）' : '站上MA20，以及外资三家合计翻回≥0（按历史概率：回测期45个空单信号日里，状态延续的中位天数只有4~5天，每天翻转概率约 ' + Math.round(TBT.FLIPH[1] * 100) + '→' + Math.round(TBT.FLIPH[5] * 100) + '%）'} 规则。盈亏比 = 从现在起平均再赚 ÷ 平均再亏；样本只有 ${bt.n} 笔（空单信号日 45 个、独立约 14 次），误差很大。</div>`;
}
function tradeShell() { const t = $('#tradePanel'); if (t && !$('#planBody')) t.innerHTML = `<div class="ch-h"><span class="t">交易计划 · 持仓与账户</span><button class="tb" id="planHide" aria-label="收起交易计划，回到首页">收起 ✕</button><button class="q" data-about="plan" aria-label="这页怎么用">?</button></div><div id="planForm"><div id="planBody"></div></div>`; }
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
  <div class="plh">结论：14:58 抢跑并不比次日开盘明显好（模拟范围 703~803万 与 735万 重叠），却要盯盘、龙虎榜还没出；所以只在收盘后看一次。入场价见上面的限价单几行：页面建议价用「收盘价回调 0.3%」（成交率 83%，5年终值中位 1022万，高于挂收盘价的 830万），代价是约 17% 的信号会错过（没成交就作废、不追）；挂收盘价也行（成交率 95%，不比开盘市价差）。回调挂得越深越容易错过——回调 1% 就掉到 337万（夏普 0.89）。0.3% 比收盘价好看是 43 笔里少数单的路径，样本小，别当成稳定规律。信号和盈亏必须用「换月调整价」（本页已改），否则会多出换月假信号。</div>
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
/* 多品种回测（v101.50）：同一套价格规则（分位≤50%+反弹确认，止损4%，移动止盈，每个品种单独跑、满仓位阶梯）放到别的大商所品种上。脚本 scratchpad/mp/multi_run.py，2017-12~2026-10，跳空>3%的换月缺口抹平。 */
const MVT = { period: '2017-12~2026-10', rows: [   // [品种, 只做多: 笔数, 胜率%, 平均每笔%, 年化%, 夏普, 前半段笔数/平均, 后半段笔数/平均]
  ['豆粕', 22, 55, 3.5, 38, 0.84, '11笔 +1.6%', '11笔 +5.3%'], ['豆油', 21, 38, 0.7, -5, 0.27, '5笔 +2.4%', '16笔 +0.2%'], ['棕榈油', 21, 38, 0.1, -13, 0.16, '8笔 −0.5%', '13笔 +0.5%'],
  ['菜粕', 32, 44, 1.5, 2, 0.44, '10笔 +2.2%', '22笔 +1.1%'], ['玉米', 20, 35, 0.3, -8, 0.08, '6笔 +4.3%', '14笔 −1.3%'], ['豆一', 24, 38, -0.6, -19, -0.10, '8笔 −1.1%', '16笔 −0.4%']] };
function mvHtml() {
  return `<div class="plh">把本页的价格规则（价格分位≤50% + 反弹确认 + 4%止损 + 移动止盈）原样放到别的品种上，每个品种单独跑（${MVT.period}，只做多：外资席位数据只有豆粕有，做空的外资条件没法套）。</div>
  <table class="tb3x tbpl"><thead><tr><th>品种</th><th class="n">笔数</th><th class="n">胜率</th><th class="n">平均每笔</th><th class="n">年化 · 夏普</th><th>前半段 · 后半段（以2022年为界）</th></tr></thead><tbody>${MVT.rows.map((r, i) => `<tr${i === 0 ? ' class="cur"' : ''}><td>${r[0]}${i === 0 ? '（本页）' : ''}</td><td class="n">${r[1]}</td><td class="n">${r[2]}%</td><td class="n">${r[3] >= 0 ? '+' : '−'}${Math.abs(r[3]).toFixed(1)}%</td><td class="n">${r[4] >= 0 ? '+' : '−'}${Math.abs(r[4])}% · ${r[5].toFixed(2)}</td><td>${r[6]} · ${r[7]}</td></tr>`).join('')}</tbody></table>
  <div class="plh">怎么读：只有豆粕的平均每笔（+3.5%）和胜率（55%）像样，其余五个品种的平均每笔在 −0.6%~+1.5% 之间、胜率 35~44%，年化为负或接近 0；而且前后半段方向常常相反（玉米前半段 +4.3%、后半段 −1.3%）。把五个品种等权做多合起来：年化 +6%、回撤 −64%，不比只做豆粕好；加上豆粕六品种等权年化 +13%（只做多，豆粕单做 +38%），多品种<b>没有</b>带来分散收益，因为这套规则的优势集中在豆粕。</div>
  <div class="plh">所以本页不做多品种：想做别的品种需要它自己的规则和自己的回测。做空方向更差（菜粕、豆一、棕榈油多空同做时年化 −26%~−39%），单靠价格没有空头优势，豆粕的空单靠的是外资席位去杠杆这个过滤。每个品种只有 20~30 笔，误差很大，这是「没发现优势」，不是「证明没有」。</div>`;
}
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
function popRender() { const el = $('#acctPop'); if (!el) return; el.hidden = !S.pop; el.innerHTML = S.pop ? POPH[S.pop] || '' : ''; ['flBtn', 'setBtn'].forEach(id => { const b = $('#' + id); if (b) b.setAttribute('aria-pressed', String(S.pop === (id === 'flBtn' ? 'fl' : 'set'))); }); }
function popSet(k) { S.pop = S.pop === k ? null : k; popRender(); if (S.pop) { const f = $('#acctPop input'); } }
function planFormSnap() { const keep = {}; $$('#planBody [id^="pf-"], #acctPop [id^="pf-"]').forEach(e => { if (e.dataset.t) keep[e.id] = e.value; }); return { keep, opened: $$('#planBody details[open]').map(e => e.id) }; }
let PLAN_BUSY = false;   // 正在重绘时不再重入：浏览器在拆掉有焦点的输入框时会同步触发 change/blur，里面又会调用重绘
function planUpdate(reset, snap) {
  const box = $('#planBody'); if (!box || PLAN_BUSY) return;
  PLAN_BUSY = true;
  try {
    const sn = reset ? { keep: {}, opened: planFormSnap().opened } : (snap || planFormSnap());
    box.innerHTML = planBodyHtml(planSnap()); popRender();
    Object.keys(sn.keep).forEach(id => { const e = document.getElementById(id); if (e) { e.value = sn.keep[id]; e.dataset.t = '1'; } });
    sn.opened.forEach(id => { const e = document.getElementById(id); if (e) e.open = true; });
  } finally { PLAN_BUSY = false; }
}
function planAfter(msg) { PMSG = msg || null; planUpdate(true); renderSig(); drawChart(); }
const okDate = d => /^\d{4}-\d{2}-\d{2}$/.test(d) && isFinite(Date.parse(d));
function planAct(act, el) {
  if (act.startsWith('push-')) return pushAct(act);
  const A = acctGet(), v = id => { const e = document.getElementById(id); return e ? String(e.value).trim() : ''; }, nm = id => { const x = parseFloat(v(id).replace(/,/g, '')); return isFinite(x) ? x : NaN; };
  const save = msg => { if (!acctSave()) msg += '（⚠️ 浏览器不让保存，刷新会丢，请先点「备份下载」）'; planAfter(msg); };
  if (act === 'pat-save' || act === 'pat-clear' || act === 'pat-sync') return cloudAct(act);
  if (act === 'open') {
    const side = parseInt(v('pf-os'), 10) >= 0 ? 1 : -1, lots = Math.round(nm('pf-ol')), px = nm('pf-op'), d = v('pf-od'), fee = v('pf-of');
    { const o = planOpen(A.trades); if (o) return planAfter('已经有一笔持仓' + (o.contract ? '（' + o.contract + '）' : '') + '，先记平仓。'); }
    if (!okDate(d) || !(lots >= 1) || !(px > 0)) return planAfter('开仓没记：日期要写成 2026-10-12，手数≥1，价格>0。');
    if (fee !== '' && !(parseFloat(fee) >= 0)) return planAfter('开仓没记：手续费要么留空，要么填数字。');
    const s0 = planSnap(), nt = v('pf-on').slice(0, 200), nw = { id: String(Date.now()), contract: C().symbol || null, side, lots, entryD: d, entryPx: px, feeO: fee === '' ? null : parseFloat(fee), snap: planSnapshotNow(s0), src: s0.side === side ? 'sys' : 'own',
      refPx: Math.round(s0.px), limPx: s0.side ? limPx({ px: s0.px, side: s0.side }) : null, slipO: (v0 => v0 == null ? null : +v0.toFixed(2))(planSlip(side, s0.px, px)), note: nt || null, rec: 2 };
    A.trades.push(nw); try { nw.pred = planPred(planSnap()); } catch (_) {}
    return save(`已记录开仓：${sdName(side)} ${lots} 手 @ ${fmtD(px)}。之后的最高/最低价、浮盈亏、离场判断都自动算。`);
  }
  if (act === 'src') { const t = curPos(); if (!t) return planAfter('当前没有持仓。'); t.src = planSrc(t) === 'own' ? 'sys' : 'own'; return save('已标记为：' + (t.src === 'own' ? '自主开仓（开仓时系统没给信号）' : '按系统信号开仓') + '。'); }
  if (act === 'close') {
    const t = curPos(), px = nm('pf-cp'), d = v('pf-cd'), fee = v('pf-cf');
    if (!t) return planAfter('当前没有持仓。');
    if (!okDate(d) || d < t.entryD || !(px > 0)) return planAfter('平仓没记：日期要写成 2026-10-12 且不早于开仓日，价格>0。');
    if (fee !== '' && !(parseFloat(fee) >= 0)) return planAfter('平仓没记：手续费要么留空，要么填数字。');
    const s1 = planSnap(), mg1 = s1.mg, rs = v('pf-cr') || planReasonOf(mg1 ? mg1.action : '持有'), sdn = t.side >= 0 ? 1 : -1;
    const refX = mg1 && s1.hold ? (mg1.action === '止损' ? t.entryPx * (1 - sdn * TPLAN.STOP / 100) : mg1.action === '移动止盈' ? (sdn > 0 ? s1.hold.peak * (1 - TPLAN.TRAIL / 100) : s1.hold.peak * (1 + TPLAN.TRAIL / 100)) : s1.hold.last) : null;
    t.exitD = d; t.exitPx = px; t.feeC = fee === '' ? null : parseFloat(fee); t.snapX = planSnapshotNow(s1);
    try { const hs = holdSeries(t), pa = planPath(hs.h, t), sl = planSlip(-sdn, refX, px); t.res = { reason: rs, note: v('pf-cn').slice(0, 200) || null, act: mg1 ? mg1.action : null, refX: refX ? Math.round(refX) : null, slipX: sl == null ? null : +sl.toFixed(2), days: pa ? pa.days : null, mfe: pa ? +pa.mfe.toFixed(2) : null, mae: pa ? +pa.mae.toFixed(2) : null, path: pa ? pa.path : null }; } catch (_) {}
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
    const per = A.fee, hdr = ['开仓日','方向','手数','合约','开仓价','平仓日','平仓价','手续费','净盈亏','价格涨跌%','来源(sys系统/own自主)','信号日收盘价','建议限价','开仓滑点%','开仓备注','预计胜率','预计单笔期望%','预计盈亏比','预计止损概率','预计持有天数','持有交易日','最大浮盈%','最大浮亏%','平仓原因','平仓触发参考价','平仓滑点%','平仓备注','开仓基本面','开仓基本面分','开仓技术面','开仓结构','开仓资金面','开仓市场状态','开仓价格分位','反弹确认','外资去杠杆','外资最弱席位5日','外资三家合计5日','趋势向下','平仓基本面','平仓外资最弱5日','平仓外资合计5日','平仓价格分位','价格路径(日期:收盘价)'];
    const q = v => v == null ? '' : v;
    const rows = A.trades.map(t => { const cl = !!t.exitD, sn = t.snap || {}, sx = t.snapX || {}, rs = t.res || {}, pd = t.pred || {}, fee = planFee(t, per), net = cl ? planPnl(t, t.exitPx) - fee : '', ret = cl ? ((t.side >= 0 ? 1 : -1) * (t.exitPx / t.entryPx - 1) * 100).toFixed(2) : '';
      return [t.entryD, t.side > 0 ? '多' : '空', t.lots, t.contract || '', t.entryPx, t.exitD || '', t.exitPx || '', fee, net, ret, planSrc(t), q(t.refPx), q(t.limPx), q(t.slipO), t.note || '', q(pd.win), q(pd.ev), q(pd.rr), q(pd.stopP), q(pd.med), q(rs.days), q(rs.mfe), q(rs.mae), rs.reason ? REASON_TXT[rs.reason] || rs.reason : '', q(rs.refX), q(rs.slipX), rs.note || '',
        sn.fund || '', q(sn.fundRatio), sn.tech || '', sn.struct || '', sn.cap || '', sn.regime || '', q(sn.pct), q(sn.confirm), q(sn.delev), q(sn.fsum), q(sn.fsumAll), q(sn.trendDn), sx.fund || '', q(sx.fsum), q(sx.fsumAll), q(sx.pct), (rs.path || []).map(x => x[0] + ':' + x[1]).join(' ')]; });
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
function monthAmpNow() {
  const h = D.adj && D.adj.d && D.adj.d.length >= 600 ? D.adj : D.hist; if (!h || !h.c) return null;
  const k = [h.d.length, h.d[h.d.length - 1], todayBJ().slice(0, 7)].join('|'); if (MAMP.k === k) return MAMP.v;
  MAMP.k = k; MAMP.v = monthAmpCalc(h.d, h.c, todayBJ().slice(0, 7)); if (MAMP.v) MAMP.v.raw = h !== D.adj; return MAMP.v;
}
const MAMP = {};
function ampChartHtml(M, nb) {
  const R = M.rows.slice(-(nb || 37)), W = 640, Hh = 112, L = 30, Rr = 8, T = 10, B = 24, n = R.length, mx = Math.max(...R.map(r => r.amp), M.q75 * 1.3), bw = (W - L - Rr) / n, Y = v => T + (Hh - T - B) * (1 - v / mx), f1 = v => Math.round(v * 10) / 10;
  let g = ''; [0, 5, 10, 15, 20].filter(v => v < mx).forEach(v => { g += `<line x1="${L}" x2="${W - Rr}" y1="${f1(Y(v))}" y2="${f1(Y(v))}" class="amg"/><text x="${L - 4}" y="${f1(Y(v)) + 3.5}" class="amt" text-anchor="end">${v}%</text>`; });
  g += `<line x1="${L}" x2="${W - Rr}" y1="${f1(Y(M.med))}" y2="${f1(Y(M.med))}" class="amm"/>`;
  R.forEach((r, i) => { const x0 = L + i * bw + bw * .18, w = bw * .64, y0 = Y(r.amp), cls = r.part ? 'amcur' : r.amp >= M.q75 ? 'amhi' : r.amp <= M.q25 ? 'amlo' : 'amb';
    g += `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(Hh - B - y0)}" class="${cls}"><title>${r.m}  振幅 ${r.amp.toFixed(1)}%${r.part ? '（本月还没走完，已 ' + r.n + ' 个交易日）' : ''}</title></rect>`;
    if (r.mo === 1) g += `<text x="${f1(L + i * bw + bw / 2)}" y="${Hh - 8}" class="amt" text-anchor="middle" style="font-weight:700;fill:var(--ink2)">${r.m.slice(2, 4)}年</text>`; else if (r.mo % 3 === 1 || i === n - 1) g += `<text x="${f1(L + i * bw + bw / 2)}" y="${Hh - 8}" class="amt" text-anchor="middle">${r.mo}月</text>`; });
  return `<div class="amw2"><svg class="amsv" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="逐月振幅柱状图">${g}</svg></div>`;
}
function ampSeasonHtml(M) {
  const W = 640, Hh = 128, L = 30, Rr = 8, T = 8, B = 20, mx = Math.max(...M.byMonth.filter(Boolean).map(b => b.max)) * 1.05, cw = (W - L - Rr) / 12, Y = v => T + (Hh - T - B) * (1 - v / mx), f1 = v => Math.round(v * 10) / 10, yr = +todayBJ().slice(0, 4), cm = M.cur ? M.cur.mo : -1;
  let g = ''; [0, 5, 10, 15, 20].filter(v => v < mx).forEach(v => { g += `<line x1="${L}" x2="${W - Rr}" y1="${f1(Y(v))}" y2="${f1(Y(v))}" class="amg"/><text x="${L - 4}" y="${f1(Y(v)) + 3.5}" class="amt" text-anchor="end">${v}%</text>`; });
  M.byMonth.forEach((b, i) => { if (!b) return; const cx = L + i * cw + cw / 2, isC = b.mo === cm;
    if (isC) g += `<rect x="${f1(L + i * cw)}" y="${T}" width="${f1(cw)}" height="${Hh - T - B}" class="amcol"/>`;
    g += `<line x1="${f1(cx)}" x2="${f1(cx)}" y1="${f1(Y(b.max))}" y2="${f1(Y(b.min))}" class="amw"/><rect x="${f1(cx - cw * .22)}" y="${f1(Y(b.q75))}" width="${f1(cw * .44)}" height="${f1(Y(b.q25) - Y(b.q75))}" class="amx"><title>${b.mo}月：${b.n}年 · 最小 ${b.min.toFixed(1)}% · 中位 ${b.med.toFixed(1)}% · 最大 ${b.max.toFixed(1)}%</title></rect><line x1="${f1(cx - cw * .22)}" x2="${f1(cx + cw * .22)}" y1="${f1(Y(b.med))}" y2="${f1(Y(b.med))}" class="amy"/>`;
    const last = b.vals[b.vals.length - 1]; if (last && last.y >= yr - 1 && !isC) g += `<circle cx="${f1(cx)}" cy="${f1(Y(last.amp))}" r="3" class="amd"><title>${last.y}年${b.mo}月 ${last.amp.toFixed(1)}%</title></circle>`;
    if (isC && M.cur) g += `<circle cx="${f1(cx)}" cy="${f1(Y(M.cur.amp))}" r="4.2" class="amc"><title>本月至今 ${M.cur.amp.toFixed(1)}%</title></circle>`;
    g += `<text x="${f1(cx)}" y="${Hh - 6}" class="amt" text-anchor="middle"${isC ? ' style="fill:var(--ink);font-weight:700"' : ''}>${b.mo}月</text>`; });
  return `<div class="amw2"><svg class="amsv" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="每个日历月的历史振幅区间">${g}</svg></div>`;
}
function viewAmp() {
  const hd = `<div class="ch-h"><span class="t">月振幅</span><button class="q" data-about="amp" aria-label="这页怎么看">?</button></div>${viewTabs()}`, M = monthAmpNow();
  if (!M) return hd + '<div class="dim2" style="padding:20px 0">历史价格不足 2 年，算不出月振幅。</div>';
  const c = M.cur, lv = v => v == null ? null : v >= 75 ? 'wide' : v <= 25 ? 'narrow' : 'mid';
  const L = { wide: ['偏宽', 'var(--bull)', '波动比往年同期大，4% 止损更容易被正常波动碰到（回测里入场时振幅最宽的那三分之一，止损占比偏高，但只有 6 笔，别当规律）。仓位别拉满，仅供参考。'], mid: ['正常', 'var(--ink2)', '波动和往年同期差不多，按计划的仓位和止损做就行。'], narrow: ['偏窄', 'var(--bear)', '波动比往年同期小。止损被误碰的可能小，但行情也可能走不远，别指望大波段。'] };
  const lvl = c ? lv(c.pctSameN) : null, I = lvl ? L[lvl] : null;
  const head = c && I ? `<div class="hl"><b>本月振幅 ${c.amp.toFixed(1)}%</b>（已 ${c.n} 个交易日），和往年同月同样走了 ${c.n} 天相比：<b style="color:${I[1]}">${I[0]}</b>${c.pctSameN == null ? '' : '（比 ' + Math.round(c.pctSameN) + '% 的年份大）'}<br><span style="color:var(--ink2)">${I[2]}</span></div>` : '';
  const more = `<div class="plt">每个日历月历史上的振幅范围（方框=中间一半的年份 · 细线=最小~最大 · 横杠=中位 · 点=去年同月）</div>${ampSeasonHtml(M)}
   <div class="plh">${M.nDone} 个完整月：中位 ${M.med.toFixed(1)}%，中间一半在 ${M.q25.toFixed(1)}%~${M.q75.toFixed(1)}%，最大 ${M.max.toFixed(1)}%。振幅 = 月内最高收盘 − 最低收盘，再除以月末收盘（${M.raw ? '用的是未换月调整的主连价，换月月份会偏大' : '换月调整价，不含换月跳空'}）。</div>`;
  return hd + head + `<div class="plt" style="margin-top:4px">近 2 年逐月振幅（金=本月 · 红=最宽25% · 绿=最窄25% · 虚线=中位 ${M.med.toFixed(1)}%）</div>${ampChartHtml(M, 25)}
   <div class="plh">⚠️ 只说波动大小，<b>不说多空</b>，不是开仓条件：回测里它能预测未来的振幅（相关 +0.25），但对方向和开仓胜率没有可用规律（40 笔按入场振幅分三档，看不出差别）。</div>${vmoreHtml('amp', more)}`;
}
function monthLines(bars) {   // K线上的「本月高低」：本月至今的最高收盘/最低收盘（和月振幅页同一口径）
  if (!bars || !bars.length) return null; const last = bars[bars.length - 1], k = String(last.d || '').slice(0, 7); if (!k) return null;
  const m = bars.filter(z => String(z.d).slice(0, 7) === k); if (m.length < 2) return null; const cs = m.map(z => z.c), mx = Math.max(...cs), mn = Math.min(...cs);
  return { mx, mn, n: m.length, amp: (mx - mn) / last.c * 100, k };
}
const LBGAP = 14;   // 右侧数据标签的最小行距（字号11px，文字框约13px高，必须≥14才不会叠）
function lyLabels(LB, gap, top, bot, xx) {   // 右侧标签防重叠：空间不够放时先按重要性丢掉最次要的标签(铁顶底<近20日高低<本月高低<平衡价<开仓/止损)，剩下的按高度排序、挨得太近的往下推，推出底就整体往上挤
  gap = Math.max(gap || 0, LBGAP); const pr = t => /开仓|止损|移动止盈/.test(t) ? 5 : /平衡/.test(t) ? 4 : /本月|振幅/.test(t) ? 3 : /20日/.test(t) ? 2 : 1;
  let L2 = LB.slice(), cap = Math.max(1, Math.floor((bot - top) / gap) + 1);
  while (L2.length > cap) { let k = 0; for (let i = 1; i < L2.length; i++) if (pr(L2[i].t) <= pr(L2[k].t)) k = i; L2.splice(k, 1); }
  const a = L2.sort((p, q) => p.y - q.y); let prev = -1e9; a.forEach(l => { l.y2 = Math.max(l.y, prev + gap, top); prev = l.y2; });
  for (let i = a.length - 1; i >= 0; i--) { const lim = i === a.length - 1 ? bot : a[i + 1].y2 - gap; if (a[i].y2 > lim) a[i].y2 = lim; }
  return a.map(l => `${Math.abs(l.y2 - l.y) > 2 ? `<line x1="${xx - 4}" x2="${xx - 1}" y1="${l.y}" y2="${l.y2 + 1}" stroke="${l.c}" stroke-width=".8" opacity=".6"/>` : ''}<text class="lv" x="${xx}" y="${l.y2 + 4}" style="fill:${l.c}">${l.t}</text>`).join('');
}
const lyOn = k => !!(S.ly || LYD)[k];
function lyMenuHtml() { return `<span class="lyw"><button class="lnk lybtn" data-lyr="menu" aria-expanded="false" aria-haspopup="true">图层 ▾</button><div class="lym" hidden>${LYN.map(([k, n]) => `<label><input type="checkbox" data-ly="${k}"${lyOn(k) ? ' checked' : ''}> ${n}</label>`).join('')}<div class="lyh">图层越多越看不清；按需打开，选择会记住。</div></div></span>`; }
function renderView() { const v = S.view; $('#chart').innerHTML = v === 'pos' ? viewPos() : v === 'sea' ? viewSea() : v === 'amp' ? viewAmp() : viewCost(); }

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
  const b = klineNow(); if (b.length < 2) return null;
  const last = b[b.length - 1], prev = b[b.length - 2], s = { last, prev, chg: last.c / prev.c - 1, n: b.length };
  if (b.length >= 20) { const w = b.slice(-20); s.hi = Math.max(...w.map(x => x.h)); s.lo = Math.min(...w.map(x => x.l)); s.pos = (last.c - s.lo) / ((s.hi - s.lo) || 1); s.ma20 = w.reduce((a, x) => a + x.c, 0) / 20; }
  return s;
}
function trendOfBars(key, pol) {
  const b = C().kline || [];
  const pts = b.map(x => ({ d: x.d, v: key === 'oi' ? x.oi : x.c }));
  return L.trend(pts, { freq: 'daily', pol });
}

/* ---------- 趋势墙的格子定义 ---------- */
const SIGMAP = {  // 格子 → 当前信号(取自页面的指标徽标或投票)
  stock: i => ind('stock'), stu: i => ind('stu'), crush: i => ind('crush'), arrival: i => ind('arrival'), import: i => ind('import'),
  feed: i => ind('feed'), hog: i => ind('hogratio'), poultry: i => ind('poultry'), rm: i => ind('rmspread'), basis: i => ind('basis'),
  ustu: () => vote(/库存消费比/), bplant: () => vote(/巴西.*播种/), margin: () => vote(/压榨毛利/), esr: () => vote(/出口销售/), spread: () => vote(/月差/)
};
function ind(k) { const it = D.indicators.find(x => x.key === k); if (!it || !it.badge) return null; return /偏多/.test(it.badge) ? 1 : /偏空/.test(it.badge) ? -1 : /不计分|暂不计分/.test(it.badge) ? null : 0; }
function vote(re) { const v = C().votes.find(x => re.test(x.label)); return v ? (v.signal === 1 || v.signal === -1 || v.signal === 0 ? v.signal : null) : null; }
function tiles() {
  const k = S.key, out = [];
  const add = (id, base, extra) => { const s = SER[base]; if (!s) return; out.push({ id, ...s, ...extra, sig: (SIGMAP[id.replace(/_.*/, '')] || (() => null))() }); };
  add('stock', 'stock'); add('stu', 'stu'); add('ustu', 'ustu'); add('margin', 'margin_' + k); add('crush', 'crush'); add('arrival', 'arrival'); add('bplant', 'bplant'); add('import', 'import');
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
function renderSess() {
  const trd = !closed() && !!(window.CockpitData && window.CockpitData.tradingNow && window.CockpitData.tradingNow(Date.now()));
  $('#sess').className = 'sess' + (trd ? ' open' : '');
  $('#sess').innerHTML = closed() ? `<i></i>休市中<span>${mmdd(D.closure.reopenMs)} ${hhmm(D.closure.reopenMs)} 恢复</span>` : trd ? `<i></i>交易时段` : `<i></i>已收盘`;
}
setInterval(() => { try { if (D) renderSess(); } catch (_) {} }, 60000);
function renderBand() {
  const f = fundamentals(), cap = capital(), ps = priceStats(), vp = vpInfo(), c = C();
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
    <div class="cell pv"><div class="cl">${esc(c.symbol)} 价格与量价<button class="q" data-about="vp" aria-label="量价怎么看">?</button></div>
      <div class="px"><span class="p">${ps ? ab(ps.last.c) : '—'}</span><span class="c ${ps && ps.chg > 0 ? 'bull' : ps && ps.chg < 0 ? 'bear' : ''}">${ps ? pc(ps.chg, 2) : ''}</span><span class="dim pxl" style="font-size:11.5px;margin-left:6px"${ps && ps.last.prov ? ' title="今天的收盘价已定；日K线文件晚上才更新，这里先用日盘最后一根15分钟线的收盘价"' : ''}>${esc(pxLabel(ps))}</span></div><div class="tick" id="tick"></div>${seqHtml}</div>
    <div class="cell half"><div class="cl">基本面<button class="q" data-about="fund" aria-label="基本面怎么算">?</button></div>
      <div class="fund"><div><div class="big" style="color:${f.dir === '偏空' ? 'var(--bear)' : f.dir === '偏多' ? 'var(--bull)' : 'var(--ink)'}">${fdir}<small class="num">${f.ratio == null ? '' : pc(f.ratio, 0)}</small></div></div>${fspark}</div>
      <div class="sub">${esc(frTrend)}</div></div>
    <div class="cell half"><div class="cl">资金面<button class="q" data-about="capital" aria-label="资金面怎么看">?</button></div>
      <div class="big cap-top" style="font-size:clamp(20px,3.1vh,28px)">${esc(capTop)}</div>
      <div class="sub">${cap.verdict && cap.verdict.label ? esc(cap.verdict.label) + '。' : (cap.gsNet == null ? '高盛未进榜' : '高盛' + (cap.gsNet > 0 ? '净多' : '净空') + ab(cap.gsNet) + '手') + '，'}CFTC ${cap.cf ? '近' + cap.cf.weeks + '周' + Math.round(cap.cf.percentile) + '%分位，连续' + cap.cf.streak + '周' + (cap.cf.dir === 'up' ? '增加' : '减少') : '暂无'}</div></div>`;
  renderSess(); tickPaint();
}

/* ---------- 实时价条（v101.57）：D.tick 由 loader 每3秒更新；这里只改这一小块 DOM，不重画整页 ---------- */
function tickInfo() {
  const t = curTick(120000); if (!t) return null;
  const ps = priceStats(); if (!ps) return null;
  const kd = lastDayD(), newer = t.dt.slice(0, 10) > kd, base = ps.last.live ? ps.prev.c : newer ? ps.last.c : ps.prev.c;   // 比最近一根日线更新 → 对比最近收盘；否则就是刚收盘当天，对比前一日
  return { c: t.c, d: t.c - base, r: t.c / base - 1, t: t.dt.slice(11, 19), sess: sessOf(t.dt.slice(11, 16)), dir: t.dir, flash: t.flash, lag: Math.round((Date.now() - t.at) / 1000) };
}
function tickPaint() {
  try { pxPaint(); tickChart(); } catch (_) {}
  const el = document.getElementById('tick'); if (!el) return;
  let x = null; try { x = tickInfo(); } catch (_) {}
  if (!x) { el.innerHTML = ''; el.style.display = 'none'; return; }
  const k = x.d > 0 ? 'bull' : x.d < 0 ? 'bear' : '';
  el.style.display = 'flex';
  el.innerHTML = `<span class="tl">${x.sess || '实时'}</span><b class="tp ${k}${x.flash ? ' fl' + (x.dir > 0 ? 'u' : 'd') : ''}">${fmtD(x.c)}</b><span class="${k}">${x.d > 0 ? '▲ +' : x.d < 0 ? '▼ ' + MINUS : ''}${Math.abs(Math.round(x.d))} · ${pc(x.r, 2)}</span><span class="dim">${x.t}${x.lag >= 5 && !x.sess ? ' · ' + x.lag + '秒前' : ''}</span>`;
  if (x.flash) { const t = curTick(); if (t) t.flash = false; }
}
function pxPaint() {   // 实时价到来时只改价格卡上三个字段（不重画整张卡，避免打断点击）
  try {
    const ps = priceStats(), b = $('#band'); if (!ps || !b) return;
    const p = b.querySelector('.px .p'), c = b.querySelector('.px .c'), l = b.querySelector('.px .pxl'); if (!p || !c) return;
    p.textContent = ab(ps.last.c); c.textContent = pc(ps.chg, 2); c.className = 'c ' + (ps.chg > 0 ? 'bull' : ps.chg < 0 ? 'bear' : '');
    if (l) l.textContent = pxLabel(ps);
  } catch (_) {}
}
function tickChart() {   // 实时价到来：K线图重画（手指/鼠标正在图上看数据时不重画，免得提示框消失）
  try { const box = document.getElementById('kl'); if (!box || box.dataset.hov === '1' || S.intra) return; drawChart(); } catch (_) {}
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
  out.push({ k: 'hlth', t: '数据', lv: hl, tx: !h ? '无' : h.bad > 0 ? h.bad + '项不可用' : h.warn > 0 ? h.warn + '项降权' : '全部正常', body: h ? healthBody(h) : '' });
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
/* 电脑端宽屏 + 没有计划面板（空仓）：价格持仓、价格位置、同期规律三张图同屏，不再切换；成本锚不在这里显示（只在窄屏/研究页的切换里保留） */
function multiOn() { return S.mode === 'trade' && !planShown() && window.innerWidth >= 1200; }
function pxHtml(multi) {
  const c = C(), ps = priceStats(), tp = trendOfBars('c', 1), to = trendOfBars('oi', 0);
  if (!ps) return `<div class="ch-h"><span class="t">价格与持仓</span></div><div class="dim2" style="padding:20px 0">${esc(c.symbol || '这个合约')}暂无 K 线数据。</div>`;
  const posTxt = ps.pos == null ? '' : ps.pos >= .8 ? '靠近近期高点' : ps.pos <= .2 ? '靠近近期低点' : '在近期区间中部';
  return `
    <div class="ch-h"><span class="t">${esc(c.symbol)} 价格与持仓</span><button class="q" data-about="price" aria-label="图怎么看">?</button><button class="q fsbtn" data-full="px" aria-label="放大全屏" title="放大全屏">⤢</button></div>${viewTabs()}
    <div class="ch-r">${lyMenuHtml()}<div class="seg" role="group" aria-label="显示多少天">${[40, 80, 120].map(n => `<button data-range="${n}" aria-pressed="${!S.intra && S.range === n}">${n}日</button>`).join('')}${D.m15 && D.m15[S.key] ? `<button data-intra="1" aria-pressed="${!!S.intra}">15分</button>` : ''}</div></div>
    <div class="why">红色是涨，绿色是跌；细线是20日均线，颜色是价格位置（青=低位带、黄=中间、橙=高位带、灰=历史不足200根）；金色虚线框是本月至今的高低（标签里有本月振幅）；下方金线是持仓量。铁顶/铁底、近20日高低、平衡价默认收起，点左上「图层」打开。把鼠标放上去或用手指划过，可以看每一天。</div>
    <div class="ptr">${trendRow(tp, '价格', '')}${trendRow(to, '持仓', '手')}</div>
    <div class="kl" id="kl"></div>
    ${ps.pos == null ? `<div class="dim2" style="margin-top:8px;font-size:13px">只有 ${ps.n} 根K线（临近到期），区间位置不可靠。</div>` : `<div class="rng"><div class="l1"><span>最近20个交易日的高低之间</span><span><b>${posTxt}</b>（${Math.round(ps.pos * 100)}%）</span></div><div class="rtrack"><i style="left:${ps.pos * 100}%"></i></div><div class="l2"><span>低点 ${ab(ps.lo)}</span><span>高点 ${ab(ps.hi)}</span></div></div>`}` + (multi ? '' : posBlockHtml());
}
function renderChart() {
  MULTI = multiOn(); document.body.classList.toggle('multi', MULTI);
  if (MULTI) {
    $('#chart').innerHTML = '<div class="mg"><div class="mgc" id="mg1"></div><div class="mgc" id="mg2"></div><div class="mgc" id="mg3"></div></div>';
    $('#mg1').innerHTML = pxHtml(true); $('#mg2').innerHTML = viewPos($('#mg2')); $('#mg3').innerHTML = viewSea();
    drawChart(); return;
  }
  if (S.view && S.view !== 'px') { renderView(); return; }
  $('#chart').innerHTML = pxHtml(false);
  drawChart();
}
function planChartLines() {   // 持仓时在K线上画开仓价、止损价、移动止盈触发价
  try { const t = curPos(); if (!t) return []; const s = planSnap(), sd = t.side > 0 ? 1 : -1, L = [{ v: t.entryPx, n: '开仓', c: 'var(--ink)' }, { v: t.entryPx * (1 - sd * TPLAN.STOP / 100), n: '止损', c: 'var(--amber)' }];
    if (s.mg && s.mg.peakR >= TPLAN.ACT) L.push({ v: s.hold.peak * (1 - sd * TPLAN.TRAIL / 100), n: '移动止盈', c: 'var(--amber)' }); return L; } catch (_) { return []; }
}
function macdOf(cs, f, sl, sg) {   // 标准 MACD：DIF=EMA12-EMA26，DEA=DIF的EMA9，柱=2×(DIF-DEA)（国内行情软件口径）。从第一根开始递推，取全部历史再截取显示段
  f = f || 12; sl = sl || 26; sg = sg || 9; const kf = 2 / (f + 1), ks = 2 / (sl + 1), kg = 2 / (sg + 1); let ef = null, es = null, de = null; const dif = [], dea = [], bar = [];
  for (let i = 0; i < cs.length; i++) { const c = cs[i]; ef = ef == null ? c : ef + kf * (c - ef); es = es == null ? c : es + ks * (c - es); const d = ef - es; de = de == null ? d : de + kg * (d - de); dif.push(d); dea.push(de); bar.push(2 * (d - de)); }
  return { dif, dea, bar };
}
function drawChart(box0) {
  const box = box0 || $('#kl'); if (!box) return;
  const intra = !!(S.intra && D.m15 && D.m15[S.key]), bars = intra ? D.m15[S.key] : klineNow(), N = Math.min(intra ? 120 : S.range, bars.length), b = bars.slice(-N), off = bars.length - N;
  const W = box.clientWidth || 560, H = box.clientHeight || 220, mr = 98, ml = 4, step = (W - mr - ml) / N, cw = Math.max(1.4, step * .62);
  const oiOn = lyOn('oi') && b.every(x => x.oi != null), volOn = lyOn('vol'), macdOn = lyOn('macd') && bars.length >= 30, pnl = oiOn || volOn;
  const volH = pnl ? Math.max(30, H * .17) : 0, macdH = macdOn ? Math.max(52, H * .22) : 0, pH = H - volH - macdH - (pnl || macdOn ? 6 : 2);
  const ois = oiOn ? b.map(x => x.oi) : [0, 1], oHi = Math.max(...ois), oLo = Math.min(...ois), vmax = volOn ? Math.max(1, ...b.map(x => x.v || 0)) : 1;
  let hi = Math.max(...b.map(x => x.h)), lo = Math.min(...b.map(x => x.l)); { const bv = lyOn('be') ? beOf(S.key) : null; if (bv != null && bv > lo * .93 && bv < hi * 1.07) { hi = Math.max(hi, bv); lo = Math.min(lo, bv); } const t8 = lyOn('iron') ? posBand().t80 : null; if (t8 != null && t8 > lo * .93 && t8 < hi * 1.07) { hi = Math.max(hi, t8); lo = Math.min(lo, t8); } } const PL = planChartLines().filter(l => l.v > lo * .93 && l.v < hi * 1.07); PL.forEach(l => { hi = Math.max(hi, l.v); lo = Math.min(lo, l.v); }); const pad = (hi - lo) * .06 || 1; hi += pad; lo -= pad;
  const y = v => 6 + (hi - v) / (hi - lo) * (pH - 6), x = i => ml + i * step + step / 2;
  const yo = v => pH + 6 + (1 - (v - oLo) / ((oHi - oLo) || 1)) * (volH - 8);
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(C().symbol)}${intra ? '15分钟' : '日'}K线${oiOn ? '和持仓量' : ''}">`;
  const LB = [];
  const ps = intra ? null : priceStats();
  if (lyOn('h20') && ps && ps.hi != null) [[ps.hi, '20日高'], [ps.lo, '20日低']].forEach(([v, nm]) => { if (v <= hi && v >= lo) { s += `<line x1="${ml}" x2="${W - mr}" y1="${y(v)}" y2="${y(v)}" stroke="var(--ink3)" stroke-dasharray="4 4"/>`; LB.push({ y: y(v), c: 'var(--ink3)', t: nm + ' ' + ab(v) }); } });
  const beV = intra || !lyOn('be') ? null : beOf(S.key);
  if (beV != null && beV <= hi && beV >= lo) { s += `<line x1="${ml}" x2="${W - mr}" y1="${y(beV)}" y2="${y(beV)}" stroke="${BEC}" stroke-dasharray="6 3" stroke-width="1.4"/>`; LB.push({ y: y(beV), c: BEC, t: '平衡 ' + ab(beV) }); }
  const ML = !intra && lyOn('mon') ? monthLines(bars) : null;
  if (ML && ML.mx <= hi && ML.mn >= lo) { const mc = 'var(--focus)'; s += `<rect x="${ml}" y="${y(ML.mx)}" width="${W - mr - ml}" height="${Math.max(1, y(ML.mn) - y(ML.mx))}" fill="${mc}" opacity=".07"/><line x1="${ml}" x2="${W - mr}" y1="${y(ML.mx)}" y2="${y(ML.mx)}" stroke="${mc}" stroke-dasharray="5 3" stroke-width="1"/><line x1="${ml}" x2="${W - mr}" y1="${y(ML.mn)}" y2="${y(ML.mn)}" stroke="${mc}" stroke-dasharray="5 3" stroke-width="1"/>`; LB.push({ y: y(ML.mx), c: mc, t: '本月高 ' + ab(ML.mx) }); LB.push({ y: (y(ML.mx) + y(ML.mn)) / 2, c: mc, t: '振幅 ' + ML.amp.toFixed(1) + '%' }); LB.push({ y: y(ML.mn), c: mc, t: '本月低 ' + ab(ML.mn) }); }
  PL.forEach(l => { s += `<line x1="${ml}" x2="${W - mr}" y1="${y(l.v)}" y2="${y(l.v)}" stroke="${l.c}" stroke-dasharray="3 3" stroke-width="1.5"/>`; LB.push({ y: y(l.v), c: l.c, t: l.n + ' ' + ab(l.v) }); });
  const pbd = posBand(), rbs = ribbonBandsProto();
  if (!intra && lyOn('ma') && bars.length >= 20) { let prev = null; for (let i = 0; i < N; i++) { const gi = off + i; if (gi < 19) continue; const v = y(bars.slice(gi - 19, gi + 1).reduce((a, z) => a + z.c, 0) / 20), cur = [x(i), v]; if (prev) s += `<line x1="${prev[0]}" y1="${prev[1]}" x2="${cur[0]}" y2="${cur[1]}" stroke="${RB[rbs[gi]] || RB.unknown}" stroke-width="1.8"/>`; prev = cur; } }
  if (!intra && lyOn('iron') && pbd.p20 != null) [[pbd.p80, '260天铁顶', RB.high], [pbd.p20, '260天铁底', RB.low], ...(pbd.t80 != null ? [[pbd.t80, '10年铁顶', '#e05d9b']] : [])].forEach(([v, nm, col]) => { if (v <= hi && v >= lo) { s += `<line x1="${ml}" x2="${W - mr}" y1="${y(v)}" y2="${y(v)}" stroke="${col}" stroke-dasharray="2 4" stroke-width="1.2"/>`; LB.push({ y: y(v), c: col, t: nm + ' ' + ab(v) }); } });
  b.forEach((z, i) => { const up = z.c >= z.o, col = up ? 'var(--bull)' : 'var(--bear)', xx = x(i); s += `<line x1="${xx}" x2="${xx}" y1="${y(z.h)}" y2="${y(z.l)}" stroke="${col}" stroke-width="1"/><rect class="cd" x="${xx - cw / 2}" y="${Math.min(y(z.o), y(z.c))}" width="${cw}" height="${Math.max(1, Math.abs(y(z.o) - y(z.c)))}" fill="${col}"/>`; });
  const PLB = [];   // 下方量/持仓区的右侧标签：统一过 lyLabels 防重叠
  if (pnl) {
    const base = pH + volH - 2, vh = volH - 10;
    s += `<line x1="${ml}" x2="${W - mr}" y1="${pH + 3}" y2="${pH + 3}" stroke="var(--line)"/>`;
    if (volOn) { b.forEach((z, i) => { const hh = Math.max(.5, (z.v || 0) / vmax * vh); s += `<rect x="${x(i) - cw / 2}" y="${base - hh}" width="${cw}" height="${hh}" fill="${z.c >= z.o ? 'var(--bull)' : 'var(--bear)'}" opacity=".55"/>`; });
      const lv = b[b.length - 1].v || 0; PLB.push({ y: pH + 12, c: 'var(--ink2)', t: '成交量 ' + (lv >= 1e4 ? (lv / 1e4).toFixed(1) + '万' : Math.round(lv)) }); }
    if (oiOn) { const oiPts = b.map((z, i) => x(i) + ',' + yo(z.oi)).join(' ');
      s += `<polyline points="${oiPts}" fill="none" stroke="var(--focus)" stroke-width="1.5"/>`; PLB.push({ y: yo(b[b.length - 1].oi), c: 'var(--focus)', t: '持仓 ' + (b[b.length - 1].oi / 1e4).toFixed(1) + '万' }); }
  }
  if (PLB.length) s += lyLabels(PLB, LBGAP, pH + 9, pH + volH - 3, W - mr + 5);
  let MC = null;
  if (macdOn) {
    MC = macdOf(bars.map(z => z.c)); const mT = pH + volH + 8, mH = macdH - 12, sl = a => a.slice(off), dif = sl(MC.dif), dea = sl(MC.dea), hs = sl(MC.bar);
    const R = Math.max(1e-9, ...dif.map(Math.abs), ...dea.map(Math.abs), ...hs.map(Math.abs)) * 1.08, ym = v => mT + (1 - (v + R) / (2 * R)) * mH;
    s += `<line x1="${ml}" x2="${W - mr}" y1="${pH + volH + 3}" y2="${pH + volH + 3}" stroke="var(--line)"/><line x1="${ml}" x2="${W - mr}" y1="${ym(0)}" y2="${ym(0)}" stroke="var(--line)" stroke-dasharray="3 3"/>`;
    hs.forEach((v, i) => { const y0 = ym(0), y1 = ym(v); s += `<rect x="${x(i) - cw * .4}" y="${Math.min(y0, y1)}" width="${cw * .8}" height="${Math.max(.5, Math.abs(y1 - y0))}" fill="${v >= 0 ? 'var(--bull)' : 'var(--bear)'}" opacity=".75"/>`; });
    s += `<polyline points="${dif.map((v, i) => x(i) + ',' + ym(v)).join(' ')}" fill="none" stroke="var(--ink)" stroke-width="1.3"/><polyline points="${dea.map((v, i) => x(i) + ',' + ym(v)).join(' ')}" fill="none" stroke="var(--amber)" stroke-width="1.3"/>`;
    const f1 = v => v.toFixed(Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2);
    s += `<text class="lw" x="${W - mr + 5}" y="${mT + 8}">MACD ${f1(hs[hs.length - 1])}</text><text class="lw" x="${W - mr + 5}" y="${mT + 8 + LBGAP}" style="fill:var(--ink)">DIF ${f1(dif[dif.length - 1])}</text><text class="lw" x="${W - mr + 5}" y="${mT + 8 + 2 * LBGAP}" style="fill:var(--amber)">DEA ${f1(dea[dea.length - 1])}</text>`;
    MC = { dif, dea, hs };
  }
  s += lyLabels(LB, LBGAP, 8, pH - 2, W - mr + 5);
  s += `<line id="xh" x1="0" x2="0" y1="0" y2="${H}" stroke="var(--focus)" style="display:none"/><rect id="hit" x="0" y="0" width="${W}" height="${H}" fill="transparent"/></svg><div class="tip" id="tip" style="display:none"></div>`;
  box.innerHTML = s;
  const hit = box.querySelector('#hit'), xh = box.querySelector('#xh'), tip = box.querySelector('#tip');
  const mv = e => { const r = box.getBoundingClientRect(), cx = (e.touches ? e.touches[0].clientX : e.clientX) - r.left; let i = Math.floor((cx / (r.width || W) * W - ml) / step); i = Math.max(0, Math.min(N - 1, i)); const z = b[i]; xh.setAttribute('x1', x(i)); xh.setAttribute('x2', x(i)); xh.style.display = ''; tip.style.display = ''; tip.textContent = `${z.d.slice(5)}  收 ${ab(z.c)}  高 ${ab(z.h)}  低 ${ab(z.l)}  ${volOn && z.v != null ? '  量 ' + (z.v >= 1e4 ? (z.v / 1e4).toFixed(1) + '万' : Math.round(z.v)) : ''}${oiOn ? '  持仓 ' + (z.oi / 1e4).toFixed(1) + '万' : ''}${MC ? '  MACD ' + MC.hs[i].toFixed(1) : ''}${z.live ? '  （盘中）' : ''}`; };
  const out = () => { xh.style.display = 'none'; tip.style.display = 'none'; box.dataset.hov = ''; };
  const mvh = e => { box.dataset.hov = '1'; mv(e); };
  hit.addEventListener('pointermove', mvh); hit.addEventListener('pointerleave', out); hit.addEventListener('pointerdown', mvh);
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
    return selfHtml + `<h3>同步</h3><p>${esc(h.sync.label)}</p><p>没参与评分的投票：${h.missing.length ? h.missing.map(x => esc(String(x).split('(')[0]) + '（' + esc(missWhy(x)) + '）').join('；') : '无'}。</p>
      <h3>历史累积情况（趋势墙每一格有多少个点）</h3>${Object.entries(SER).filter(([, s]) => !s.ctx || s.ctx === S.key).map(([id, s]) => { const n = s.freq === 'seasonal-daily' ? L.currentRun(s.pts, 10).length : s.pts.length; return `<div class="cd">${lampSvg(n >= 8 ? 'ok' : n >= 2 ? 'note' : 'warn')}<span>${esc(s.name)}<span class="dim">，${s.freq === 'seasonal-daily' ? '当前窗口' : s.freq}</span></span><span class="s">${n} 个点${s.pts.length ? '，最新 ' + esc(s.pts[s.pts.length - 1].d) : '（非播种季或还没抓到）'}${n < 3 ? '，趋势还画不出来' : ''}</span></div>`; }).join('')}
      <h3>每个指标的新鲜度</h3>${rows.map(r => `<div class="cd">${lampSvg(ico[r.state] || 'na')}<span><b style="font-weight:500">${esc(r.name)}</b>，${esc(r.label)}</span><span class="s">${esc((r.detail || '').slice(0, 110))}${(() => { const sr = IND_SER[r.key] && serLast(IND_SER[r.key]); return sr ? ' · 趋势墙最新点 ' + esc(sr.txt) + '（' + esc(sr.d) + '）' : ''; })()}</span></div>`).join('')}
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
function ageTxt(d) {   // “（今天）/（3 天前）”：展开页里每个指标都带上数据日期距今多久
  if (!d) return ''; const ds = String(d), full = ds.length === 7 ? ds + '-28' : ds.length === 4 ? ds + '-12-28' : ds.slice(0, 10), a = Math.floor((Date.parse(todayBJ() + 'T00:00:00Z') - Date.parse(full + 'T00:00:00Z')) / 864e5);
  if (!isFinite(a)) return ''; return ds.length < 10 ? '（按月/年记录）' : a <= 0 ? '（今天）' : '（' + a + ' 天前）';
}
function openTile(id) {
  const t = TILES.find(x => x.id === id); if (!t) return;
  const tr = t.tr, pts = t.freq === 'seasonal-daily' ? L.currentRun(t.pts, 10) : t.pts.slice(-(WIN[t.freq] || WIN.daily).long);
  const svg = pts.length >= 2 ? sparkSvg(pts, 'var(--ink)', 520, 210, false, 0).replace('stroke-width:1.9', '') : '';
  const row = c => !c.ok ? `<tr><td>${c.label}</td><td colspan="3" class="dim">没有可比的点（容差内找不到${c.label}前的数据）</td></tr>` : `<tr><td>${c.label}</td><td class="n">${esc(c.from.d)}：${L.fmtNum(c.from.v, t.unit)}</td><td class="n" style="color:${colorOf(c.meaning)}">${arrow(c.dir)} ${sg(c.change, Math.abs(c.change) < 10 ? 2 : 0)}${c.pct != null ? '（' + pc(c.pct, 1) + '）' : ''}</td><td>${c.meaning > 0 ? '偏多' : c.meaning < 0 ? '偏空' : '—'}</td></tr>`;
  openSheet(t.name, `<div class="dbig">${svg || '<div class="dim2">历史累积中，画不出趋势。</div>'}</div>
    <p>最新 <b class="num">${last(t)}</b> ${esc(t.unit)}，<b>数据日期 ${esc(tr.last ? tr.last.d : '—')}</b>${esc(ageTxt(tr.last && tr.last.d))}，频率 ${esc(t.freq === 'seasonal-daily' ? '日度(只在建议交易窗口内有数据)' : t.freq)}，共 ${pts.length} 个点。</p>
    <table class="tb3x"><thead><tr><th>周期</th><th>对比的点</th><th>变化</th><th>对价格</th></tr></thead><tbody>${tr.chips.map(row).join('')}</tbody></table>
    ${tileSeatNote(t)}
    <p class="dim2" style="margin-top:12px">${t.pol === 0 ? '这个指标升降本身不直接对应多空（反映的是拥挤程度）。' : t.pol > 0 ? '数值上升对价格偏多，下降偏空。' : '数值上升对价格偏空，下降偏多。'}${t.note ? ' ' + esc(t.note) + '。' : ''}</p>`);
}
const last = t => { const p = t.tr.last; return p ? L.fmtNum(p.v, t.unit) : '—'; };
function openLamp(k) { const x = checks().find(y => y.k === k); openSheet(x.t + '：' + x.tx, `<p><span class="chipx ${x.lv === 'warn' ? 'bull' : 'mid'}">${LW[x.lv]}</span></p>${x.body}`); }
function openMore(si) { const sm = SUMS[+si] || SUMS[0] || { items: [], title: '其余指标' }; openSheet(sm.title, sm.items.map(t => `<div class="cd"><span></span><span><b style="font-weight:500">${esc(t.name)}</b> <span class="num">${last(t)}</span> ${esc(t.unit)}　<span class="dim">数据日期 ${esc(t.tr.last ? t.tr.last.d : '—')}${esc(ageTxt(t.tr.last && t.tr.last.d))}</span></span><span class="s">${t.tr.chips.filter(c => c.ok).map(c => c.label + arrow(c.dir) + (c.dir === 0 ? '持平' : L.fmtChange(c.change, c.pct, t.show, t.unit).text)).join('　') || '历史累积中，已' + t.tr.n + '个点'}</span></div>`).join('') || '<p>没有。</p>'); }
const ABOUT = {
  vp: ['量价怎么看', `<p>量价关系看最近 5 个交易日的价格变化和持仓量变化，沿用现有页面的同一套算法，不另造。</p><ul><li><b>增仓上涨</b>：新多头进场，上涨有增量资金确认，偏多。</li><li><b>增仓下跌</b>：新空头进场，下跌有增量资金确认，偏空。</li><li><b>减仓上涨</b>：更多是空头回补，上涨缺乏新资金确认，不判方向。</li><li><b>减仓下跌</b>：多头离场为主，下跌缺乏新空头，动能在衰减，不判方向。</li></ul><p>顶部那排小方块是最近 5 天，从左到右从旧到新：深红增仓上涨，深绿增仓下跌，浅红减仓上涨，浅绿减仓下跌，灰色没有明显变化。</p><p>持仓量在合约临近交割时会机械地下降，所以现有算法设了三道门槛（持仓不低于 50 万手、不低于近 120 日峰值的 60%、距合约月至少 45 天），没过就不计分。</p>`],
  fund: ['基本面怎么算', `<p>每个供需指标投一票（红偏多、绿偏空），按权重加权得到“净倾向”。净倾向进入 ±22% 的区间才算有方向，否则是“信号混合”。权重含天气开关和数据质量折扣。</p><p>市场结构（基差、月差、量价）来自价格本身，不计入这个净倾向。</p><p>这里的方向和数字取自每日系统记录的最新一天，和线上页面一致；小曲线是最近每天的记录。</p>`],
  capital: ['资金面怎么看', `<p>龙虎榜是收盘后才发布的前一日数据；固定看主力合约（净空头榜持仓合计最大的合约），不跟你选的合约走，因为非主力合约几乎没人持仓。</p><p>高盛净多 ≥ 12 万手算高位；CFTC 管理基金净多的近 156 周分位 ≥ 90 算拥挤；两者都满足是“外资多头拥挤”。高盛当日净多减少 ≥ 2 万手，优先显示“撤退预警”。数据缺失时写“数据不足”，不写中性。</p><p><b>这些阈值没法回测，并且能检验的部分不支持“撤退=看空、拥挤=风险”：</b>高盛只有 2026-04 起 113 天数据（净多≥12万只出现过 1 段）；CFTC 只有 157 周（≥90 分位只有 2 段独立事件）。能用的替身是摩根大通（2022 起 1025 天）：单日净减仓 ≤ −2万手有 11 次，之后 5/10 日平均 +0.67%/+1.56%（高于基准 +0.28%/+0.58%），没有下跌；净多高位（≥80 分位）9 次，之后 10 日 +2.5%。样本都很小，结论只有一条：<b>历史没有支持把外资撤退当看空信号</b>，所以页面只把它们当“描述外资在做什么”，不进入开平仓规则（规则里用的只有外资 5 日变化 ≤ −2万 这一条，已回测）。</p>`],
  amp: ['月振幅怎么看', `<p><b>振幅</b> = 月内最高收盘价 − 最低收盘价，再除以月末收盘价，用换月调整价算（不含换月跳空）。</p><ul><li><b>最上面一行</b>：本月振幅，和「往年同月、同样走了 n 个交易日」比，分成偏宽 / 正常 / 偏窄（本月没走完，所以不能拿整月去比）。</li><li><b>柱状图</b>：最近 2 年逐月振幅。金色是本月，红色是历史最宽的 25%，绿色是最窄的 25%，虚线是中位数。</li><li><b>更多明细</b>（点开）：把历史上同一个日历月放在一起（比如所有的 10 月）看波动范围。</li></ul><p>K线上的金色虚线框就是本月至今的最高/最低收盘。</p><p><b>怎么用</b>：只用来掂量「4% 止损会不会被正常波动碰到」和仓位大小，<b>不决定做多还是做空</b>。回测里近20日振幅能预测未来20日振幅（相关 +0.25，前后半段一致），但对方向、对开仓胜率都没有可用的规律；各月份之间的差别只有 10 年左右的样本，只当背景参考。</p>`],
  price: ['图怎么看', `<p>红涨绿跌的 K 线，细线是 20 日均线，虚线是最近 20 个交易日的最高和最低。图下方金色的线是持仓量。</p><p>“最近 20 个交易日的高低之间”这条带：把近 20 天的最低价当作 0%，最高价当作 100%，今天的收盘价落在中间哪个位置。越靠右越贴近近期高点，越靠左越贴近近期低点。</p>`],
  wall: ['趋势墙怎么看', `<p>每一格是一个指标。<b>曲线</b>是最近一段时间的走势，<b>箭头</b>是数值升还是降，<b>颜色</b>是这个变化对价格意味着什么（库存升是偏空，所以是绿色）。左边的竖条是它现在的信号。</p><p>三个周期（周、月、季）都同向的格子会有“同升/同降”的标记和更深的底色；长期涨、最近一周跌是“回落”，长期跌、最近一周涨是“反弹”。</p><p>周期按日历时间算，缺了几周也不会算错；周度出口销售波动很大，用 4 周均值；压榨毛利和月差只在建议交易窗口内有数据，只看当前这一段。</p><p>右上角“短/中/长”切换曲线显示多久。有的指标历史还在累积，会写“历史累积中”，不会画假线。</p>`]
};
ABOUT.price[1] += `<p><b>紫色虚线 = 盈亏平衡价</b>：用豆二、豆油盘面价和压榨费150元算出来的“油厂压榨不亏的豆粕价”。盘面在它上方，油厂有利润；跌到它下方，油厂亏损，会减产，所以它常被当作底部参照。它不是买卖信号，盘面可以长期低于它。</p>`;
ABOUT.pos = ['价格位置怎么看', `<p>阴影带是每一天往回看 260 个交易日的 <b>20%～80% 分位价</b>：下沿“铁底”（有 20% 的日子比它便宜），上沿“铁顶”（80% 的日子比它便宜）。<b>它们不是历史最高/最低价</b>，会随最近一年的价格走，价格涨起来铁顶也会跟着抬。</p><p>线的颜色：青=在铁底以下，橙=在铁顶以上，灰=中间。下面两条横带是现价在近260日、近10年里的百分位。</p><p>历史检验：低位带之后表现略好于基准，只是温和支持；高位带之后<b>没有“会跌”的证据</b>。它只说明现在贵不贵，不是买卖信号。价格用主力连续价，换月缺口没修正。</p>`];
ABOUT.sea = ['同期规律怎么看', `<p>每根柱子是该月份在历年里“上涨的年份占比”。默认看现货价格，可切到期货（换月修正后的月度涨跌）。下方数字是历年平均涨跌。</p><p>稳定性分三档：前后两半样本方向相反=不稳；同向但胜率或显著性不够=一般；同向且胜率、显著性都够=较稳。柱子越淡越不稳。</p><p>季节性只描述“历史上通常怎样”，不预测今年，样本只有9~10年。</p>`];
ABOUT.cost = ['成本锚怎么看', `<p>所有数字都是<b>豆粕价格（元/吨）</b>：豆的成本按出粕率78.5%，扣掉豆油副产品（出油率18.5%）和压榨费150元换算而来。</p><ul><li><b>盈亏平衡价</b>：只用豆二、豆油盘面价算，最可靠。盘面高于它=压榨有利润；低于它=亏损、油厂减产，下方有支撑。</li><li><b>进口成本带</b>：用CBOT大豆+升贴水（±50美分）+关税+增值税9%+港杂100元推算。美豆关税13%，成本偏高，说明盘面是按更便宜的巴西豆定价的。</li><li>升贴水是4月快照，没有历史、无法回测；增值税、港杂是经验值未核实，所以进口成本带只当参考。</li></ul><p>成本锚是估值参照，<b>不是买卖信号</b>。</p>`];
ABOUT.plan = ['交易计划怎么用', `<p>页面分「交易」和「研究」两个模式（右上角切换；空仓默认先看研究页，有持仓默认进交易页）：交易模式只留入场信号、持仓管理、账户权益、交易记录和K线；基本面趋势墙、市场状态、成本锚、证据页在研究模式。顶部「入场信号」和「持仓管理」两格就是结论。<b>系统不会替你下单</b>，它只做三件事：告诉你今天有没有入场信号、该开几手；你成交后记一笔，之后开仓价、持仓最高/最低价、浮盈亏、权益全部自动算；每天自动判定持仓该走还是继续拿。</p>
<h3>完整交易逻辑（回测和页面是同一套）</h3>
<ul><li><b>价格</b>：用「换月调整的主力连续价」（只做主力合约，主力按持仓量在1/5/9月之间轮换，换月日沿用前一天涨跌幅，不吃价差跳空）。信号和持仓涨跌都用它，收盘后看一次，操作在<b>下一个交易日</b>（入场挂限价单，平仓开盘市价）。</li>
<li><b>外资</b> = 摩根大通、高盛期货、瑞银期货，各自「近5个交易日」持仓变化。龙虎榜每边只公布前20名：席位只有一边进前20时，只用进榜那一边的真实变化，不把顶替的第20名算进去；拿不到的席位不参与（回测里缺数据日按0）。</li>
<li><b>外资去杠杆</b>：<b>任一</b>席位5日变化 ≤ −2万手（看单个席位，不看合计：席位之间会对冲，例如摩根加仓、高盛减仓）。</li>
<li><b>做多</b>（四条同时满足）：①价格在近260日 ≤50% 分位；②反弹确认：今天收盘高于5日前，且比前10日最低价高1%以上；③外资没有去杠杆；④期货不高于现货（生意社基差 ≥ 0，v101.84 加）。</li>
<li><b>基差（v101.84）</b>：生意社豆粕现货价 ÷ 生意社主力合约价 − 1，和回测、本地自动交易同一个源。全品种回测里期货明显高于现货时做多平均是亏的；豆粕自己历史上只过滤 2 笔（回测夏普 1.10→1.12，回撤不变），但 2026 年期货高于现货的天数约一半，以后会常起作用。<b>取不到或数据日和价格日相差 7 天以上时这一条不起作用</b>，按原来三条判断。「期货升水+趋势向下」做空、「外资加杠杆直接做多」是两条候选规则，没有通过稳健性检验，默认不启用：信号条和条件表里只提示「候选（未启用）」，不作为信号、不发提醒；想用的话在「入场信号：数据和口径说明」最后看回测数据，再点「启用」开关（只对这台设备的网页生效）。</li>
<li><b>做空</b>（三条同时满足）：①外资去杠杆（任一席位5日变化 ≤ −2万手）；②价格 < MA20 < MA60；③价格低于5日前。空头只在外资去杠杆时才做。</li>
<li><b>平多</b>（任一触发）：亏4%止损；持仓期间最高浮盈到过 ≥8% 后，从最高价回落4%；外资去杠杆（任一席位 ≤ −2万手）。</li>
<li><b>平空</b>（任一触发）：亏4%止损；持仓期间最高浮盈到过 ≥8% 后，从最低价反弹4%；外资<b>三家合计</b>5日变化 ≥0（外资回正）；价格站上MA20。</li>
<li><b>入场价（挂条件单用）</b>：信号出现后，下一个交易日挂<b>限价单</b>：做多 ≤ 信号日收盘价、做空 ≥ 信号日收盘价，当日有效，没成交就作废、不追（第二天信号还在会重新给价）。跳空低开（做空是高开）时按开盘价成交，等于不追高。回测（收盘价限价）：5年终值中位 830万 / 夏普 1.11，95% 的信号能成交，不比开盘市价（735万）差。页面建议价是<b>收盘价回调 0.3%</b>（做空是反弹 0.3%）：成交率约 83%，没成交就作废，回测 5年终值中位 1022万，高于挂收盘价的 830万——但这是少数单的路径、样本小；想求稳就挂收盘价。回调 0.5% 成交率 58%（919万），回调 1% 成交率只剩 22%、终值掉到 337万——<b>回调不要挂得更深</b>。止损价按<b>实际成交价</b>×(1∓4%)重新算，页面给的止损价是按收盘价算的参考。</li>
<li><b>已有持仓时</b>不加仓；同一时间只持一个方向。</li>
<li><b>占用阶梯</b>：权益<500万 60%；500~1500万 40%；1500~5000万 25%；其后 15%（页面底部可展开）。手数 = 权益×占用 ÷（每吨×10吨×保证金）。没有账户回撤熔断。</li>
<li><b>平空为什么看合计、去杠杆却看单个席位</b>：回测里两种平空口径几乎一样（14笔空单里13笔完全相同，只差一笔 +1.2%），不是证明出来的优劣，按回测验证过的口径写。</li></ul>
<p><b>权益怎么算</b>：初始资金 + 出入金 + 已平仓盈亏 + 持仓浮动盈亏 − 手续费。要追加资金（比如每年加20万）就记一笔入金；和期货公司账户对不上时用「按实际权益校准」，系统会记一笔差额。</p>
<p><b>最高/最低价怎么来</b>：用主力连续日线收盘价，从你的开仓日取到最新一天，和回测同口径（盘中最高价不计）。你的开仓价和主连差超过2%时按开仓日折算。信号和离场判断都只在收盘后看一次。</p>
<p><b>手续费</b>：按「每手来回多少元」估算，开仓/平仓各一半；回测用 23 元（含滑点估计），63、103 元是敏感性。记录时填了实际金额就用实际的。</p>
<p><b>保证金比例</b>：回测按10%。填期货公司实际比例后，「按我的实际保证金占用」按它算手数；「按回测杠杆」手数不变，实际占用会更高、风险度更接近追保线。风险度到100%的价格是追保/强平的大致位置，以你的期货公司为准。</p>
<p><b>移动止盈为什么是「最高浮盈 ≥8% 后回落4%」</b>：按「最高浮盈到过4%就开始跟踪」回测，反而更差——小利润的单子被早早洗出；「≥8%后回落4%」和原先回测的写法等价。回落幅度不要收紧。</p>
<p><b>数据不足时</b>：外资5日数据一个席位都没取到、或价格数据超过7天没更新，信号格会显示「数据不足，信号不可信」，不给开仓建议（回测里缺外资数据按0算，等于去杠杆过滤失效）。</p>
<p><b>决策快照</b>：每次记开仓/平仓，会同时存下当时的基本面方向、技术面、资金面和信号条件；交易记录里能看到开仓时的基本面和外资，「导出CSV」带全部快照字段。基本面目前没有被回测证明有用（见项目文档），快照是为了以后用你自己的实盘去检验它。</p>
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
  return sigTableHtml(s) + `<h3>外资去杠杆：看单个席位，任一席位「近5个交易日」变化 ≤ −2万手</h3><ul>${F.parts.map(q => `<li><b>${esc(q.k)}</b> ${f2(q.v)} 手：${bs(q)}</li>`).join('')}${F.missing.map(k => `<li><b>${esc(k)}</b>：暂无5日数据，按0算（回测里缺数据的日子也按0）</li>`).join('')}</ul>
   <p>${F.parts.length ? '最弱席位 <b>' + esc(F.minK) + ' ' + f2(F.min) + '</b> 手（三家合计 ' + f2(F.sum) + ' 手，仅供参考）；最弱的一家 ≤ −20,000 手就算「外资去杠杆」。' : '没有可用的外资数据。'}</p>
   <p>为什么不用三家合计：席位之间可能对冲(比如摩根加仓、高盛减仓)，合计会把单个席位的撤退抵消掉。回测里两种口径几乎一样(历史上外资信号基本就是摩根大通)，这里按单个席位判断。</p><p>龙虎榜每边只公布前20名。一个席位只有一边进了前20时，另一边用第20名顶替，那个数字的变动和该席位无关，所以信号只用进榜那一边的真实变化。</p>
   <h3>和研究页「高盛净持仓」为什么对不上</h3><p>研究页画的是<b>净持仓(多−空)</b>，空单常常是第20名顶替的下限估计，周期是「1周/1月」按自然日找对比点；这里是<b>近5个交易日</b>、只用真实一边。起点日期和口径都不同，数字就不同。研究页高盛的明细里有这一行对照。</p>
   <h3>基差（做多第④条）</h3><p>${basisLine(s.B)}</p>
   <h3>价格口径</h3><p>价格用「换月调整的主力连续价」(与回测同一口径)，现价 ${fmtD(s.px)}。信号收盘后看一次即可，龙虎榜收盘后才发布，所以数据日是前一个交易日。</p>
   <h3>完整规则</h3><p>入场、离场、仓位的全部逻辑见右上角「说明」→「交易计划怎么用」。</p><h3>本月</h3><p>${esc(monthHint())}</p>${shortCmpHtml()}${candHtml()}`;
}
const HELP = {
  plsig: ['入场信号：数据和口径说明', sigHelp],
  plpos: ['持仓管理怎么用', () => '<p><b>微信动态提示</b>（持仓时，交易时段每15分钟检查一次）：价格涨到启动价（浮盈 8%）→ 提醒把固定止损改成移动止损，并给新的止损价；之后每创新高、止损线上移 0.5% 就提醒一次；价格离止损线 ≤1%、或盘中已触及线也提醒。回测按收盘价判断，盘中只做预警。</p><p><b>离场规则</b>：多单——亏4%止损；最高浮盈到过 ≥8% 后从最高价回落4%；外资去杠杆（任一席位5日变化 ≤ −2万手）。空单——亏4%止损；最高浮盈到过 ≥8% 后从最低价反弹4%；外资三家合计5日变化 ≥0；价格站上MA20。完整交易逻辑见右上角「说明」。</p><p>当前空仓时，成交后在这里记一笔，之后开仓价、持仓期间最高/最低价、浮盈亏、该不该走都自动算。持仓中，这里显示止损价、移动止盈、外资离场条件。</p><p>想收到「该平仓」提醒，要把持仓同步到仓库：见下方「同步持仓到提醒系统」。</p>'],
  placct: ['账户权益说明', () => '<p>权益 = 初始资金 ± 出入金 + 已平仓盈亏 + 持仓浮动 − 手续费。手续费按每手来回估算，开仓/平仓各记一半，记录时填了实际金额就用实际的。现价用主力连续收盘价，和期货公司结算价会有小差别，需要时用「账户设置」里的校准。</p><p>回测每手来回按 23 元（含滑点估计）；回测摘要里 63、103 元是敏感性测试。保证金比例填期货公司实际收的（交易所10% + 加收），回测按10%。</p>'],
};
function openAbout(k) {
  if (HELP[k]) { openSheet(HELP[k][0], HELP[k][1]()); return; }
  if (['pos', 'sea', 'cost', 'plan', 'amp'].includes(k)) { openSheet(ABOUT[k][0], ABOUT[k][1]); return; }
  const keys = ['vp', 'fund', 'capital', 'price', 'wall'], order = k ? [k, ...keys.filter(x => x !== k)] : keys;
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
  $('#dockNote').textContent = '数据生成 ' + hh + '（北京） · 历史到 ' + (D.seriesAsOf && D.seriesAsOf.history ? D.seriesAsOf.history.slice(5) : '—') + ' · 每5分钟自动刷新（价格每1分钟）';
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
  if (S.mode === 'research') { renderWall(false); layoutWall(false); } if (MULTI !== multiOn()) renderChart(); else drawChart();
}
/* ======================= v101.39：账户云端同步（data/account.json，页面直接用 GitHub 令牌读写） =======================
   账以 data/account.json 为准；每次记账 1.5 秒后自动上传，同时把当前持仓写成 data/position.json（离场提醒读它）。
   令牌只存本机浏览器（localStorage），权限只给这个仓库的 Contents 读写。没填令牌 = 只读：能看到云端的账，改动不上传。 */
const CLOUD = { msg: '', sha: null, timer: null, busy: false, at: '' };
const ghCfg = () => { let o = {}; try { o = JSON.parse(localStorage.getItem('cockpit-gh') || '{}') || {}; } catch (_) {} const m = location.hostname.match(/^([^.]+)\.github\.io$/), r = location.pathname.split('/')[1]; return { owner: o.owner || (m ? m[1] : ''), repo: o.repo || r || '' }; };
const patGet = () => { try { return localStorage.getItem('cockpit-pat') || ''; } catch (_) { return ''; } };
const b64e = t => btoa(unescape(encodeURIComponent(t))), b64d = t => decodeURIComponent(escape(atob(String(t).replace(/\n/g, ''))));
const cloudT = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(11, 16);
function ghApi(method, path, body) { const g = ghCfg(); return fetch(`https://api.github.com/repos/${g.owner}/${g.repo}/contents/${path}`, { method, headers: { Authorization: 'Bearer ' + patGet(), Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined, cache: 'no-store' }); }
function ghErr(status) { return 'HTTP ' + status + (status === 401 ? '（令牌无效或已过期）' : status === 403 || status === 404 ? '（令牌权限不够，或仓库名不对）' : ''); }
function cloudShort() { if (!patGet()) return '未连接（账只在本机）'; return CLOUD.msg || '已连接'; }
function syncDotUpdate() {   // 页面顶部：绿点=云端已同步，黄点=上传/读取中，红点=没同步（没填令牌或失败）
  const d = $('#syncDot'); if (!d) return; const has = !!patGet(), m = CLOUD.msg || '';
  const st = has && m.startsWith('已同步') ? 'ok' : has && /中…$|待上传/.test(m) ? 'wait' : 'bad';
  d.className = 'sdot ' + (st === 'bad' ? '' : st); d.innerHTML = `<i></i>${st === 'ok' ? '持仓已同步' : st === 'wait' ? '同步中…' : '未同步'}`;
  d.title = has ? (m || '云端：已连接，等待同步') : '没填令牌：账只存在这台设备。点这里去填';
}
function cloudSet(m) { CLOUD.msg = m; $$('.cloudmsg').forEach(e => { e.textContent = cloudShort(); }); syncDotUpdate(); }
function acctHasData(A) { return !!(A.trades.length || A.flows.length || +A.init !== 500000); }
function adoptAcct(a, note) {
  ACCT = acctNorm(a); acctSave(true); PMSG = null; planUpdate(true); renderSig(); drawChart(); cloudSet('已同步 ' + cloudT() + (note || ''));
}
async function cloudFetch() {
  const r = await ghApi('GET', 'data/account.json');
  if (r.status === 404) { CLOUD.sha = null; return { ok: true, acct: null }; }
  if (!r.ok) return { ok: false, status: r.status };
  const j = await r.json(); CLOUD.sha = j.sha; let a = null; try { a = JSON.parse(b64d(j.content)); } catch (_) {}
  return { ok: true, acct: a && Array.isArray(a.trades) && Array.isArray(a.flows) ? a : null };
}
function posPayload() { const t = planOpen(acctGet().trades); return t ? { side: t.side >= 0 ? 1 : -1, lots: t.lots, entryD: t.entryD, entryPx: t.entryPx, contract: t.contract || (D.contracts[autoKey()] || {}).symbol || null } : { flat: true }; }
async function cloudPushPos() {
  const want = posPayload(); let sha, cur = null;
  const r = await ghApi('GET', 'data/position.json');
  if (r.ok) { const j = await r.json(); sha = j.sha; try { cur = JSON.parse(b64d(j.content)); } catch (_) {} } else if (r.status !== 404) throw new Error('持仓文件 ' + ghErr(r.status));
  if (cur) { const c = Object.assign({}, cur); delete c.updated; if (JSON.stringify(c) === JSON.stringify(want)) return; }
  const w = await ghApi('PUT', 'data/position.json', { message: '持仓 ' + todayBJ(), content: b64e(JSON.stringify(Object.assign({}, want, { updated: new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC' }), null, 1)), sha });
  if (!w.ok) throw new Error('持仓文件 ' + ghErr(w.status));
}
async function cloudPush(retried) {
  if (!patGet() || !ghCfg().owner || CLOUD.busy) { if (CLOUD.busy) CLOUD.again = true; return; }
  CLOUD.busy = true; cloudSet('上传中…');
  try {
    const A = acctGet(), r = await ghApi('PUT', 'data/account.json', { message: `账户 rev${A.rev || 0} ${todayBJ()}`, content: b64e(JSON.stringify(A, null, 1)), sha: CLOUD.sha || undefined });
    if (r.status === 409 || r.status === 422) {
      const g = await cloudFetch(); CLOUD.busy = false;
      if (g.ok && g.acct && (+g.acct.rev || 0) > (+A.rev || 0)) { adoptAcct(g.acct, '（云端有更新的账，已改用云端）'); return; }
      if (g.ok && !retried) return cloudPush(true);
      throw new Error('冲突，稍后重试');
    }
    if (!r.ok) throw new Error(ghErr(r.status));
    CLOUD.sha = (await r.json()).content.sha; await cloudPushPos(); cloudSet('已同步 ' + cloudT());
  } catch (e) { cloudSet('同步失败：' + (e.message || e) + '；账已存在本机，改动后会重试'); }
  finally { CLOUD.busy = false; if (CLOUD.again) { CLOUD.again = false; cloudQueue(); } }
}
function cloudQueue() { if (!patGet()) return; clearTimeout(CLOUD.timer); cloudSet('待上传…'); CLOUD.timer = setTimeout(() => { CLOUD.timer = null; cloudPush(); }, 1500); }
async function cloudPull() {
  try {
    const A = acctGet();
    if (patGet()) {
      cloudSet('读取中…'); const g = await cloudFetch();
      if (!g.ok) return cloudSet('读取失败：' + ghErr(g.status));
      if (!g.acct) { if (acctHasData(A)) { A.rev = Math.max(+A.rev || 0, 1); acctSave(true); return cloudPush(); } return cloudSet('云端还没有账，记第一笔后会自动上传'); }
      const rr = +g.acct.rev || 0, lr = +A.rev || 0;
      if (rr > lr) adoptAcct(g.acct); else if (lr > rr) await cloudPush(); else cloudSet('已同步 ' + cloudT());
    } else {
      const r = await fetch('data/account.json?t=' + Date.now(), { cache: 'no-store' });
      if (r.ok) { const a = await r.json(); if (a && Array.isArray(a.trades) && Array.isArray(a.flows) && (+a.rev || 0) > (+A.rev || 0)) adoptAcct(a, '（只读：没填令牌，这里的改动不会上传）'); }
    }
  } catch (e) { cloudSet('读取失败：' + (e.message || e)); }
}
function cloudAct(act) {
  const v = id => { const e = document.getElementById(id); return e ? String(e.value).trim() : ''; };
  if (act === 'pat-save') {
    const tk = v('pf-pat'), rp = v('pf-repo').split('/');
    try {
      if (tk) { if (!/^(github_pat_|ghp_)[A-Za-z0-9_]+$/.test(tk)) return planAfter('令牌格式不对：应该以 github_pat_ 开头，整串复制。'); localStorage.setItem('cockpit-pat', tk); }
      if (rp.length === 2 && rp[0] && rp[1]) localStorage.setItem('cockpit-gh', JSON.stringify({ owner: rp[0], repo: rp[1] }));
    } catch (_) { return planAfter('浏览器不让保存令牌（隐私模式？）。'); }
    if (!patGet()) return planAfter('先粘贴令牌。');
    planAfter('令牌已保存在这台设备，正在连接云端…'); cloudPull(); return;
  }
  if (act === 'pat-clear') { try { localStorage.removeItem('cockpit-pat'); } catch (_) {} CLOUD.sha = null; CLOUD.msg = ''; return planAfter('令牌已从这台设备删除。账还在本机和云端；之后的改动不再上传（建议同时去 GitHub 把这个令牌 Delete）。'); }
  if (act === 'pat-sync') { cloudPull(); }
}
function cloudHtml() {
  const g = ghCfg(), has = !!patGet();
  return `<div class="plt" style="margin-top:8px">云端同步（账存进你的 GitHub 仓库）</div>
   <div class="plh">状态：<b class="cloudmsg">${esc(cloudShort())}</b>。账记在 <code>data/account.json</code>，当前持仓自动同步到 <code>data/position.json</code>（离场提醒读它），不用再去 Actions 手填。⚠️ 仓库公开的话，这两个文件任何人都能看到。</div>
   <div class="plf"><label>GitHub 令牌（只存在这台设备的浏览器）<input id="pf-pat" type="password" autocomplete="off" placeholder="${has ? '已保存；要换就粘贴新的' : 'github_pat_…'}"></label>
    <label>仓库（所有者/仓库名）<input id="pf-repo" value="${esc(g.owner + '/' + g.repo)}"></label></div>
   <button class="pbtn" data-act="pat-save">保存并同步</button>${has ? ' <button class="lnk" data-act="pat-sync">立即同步</button> · <button class="lnk" data-act="pat-clear">清除令牌</button>' : ''}`;
}
/* ---- 网页推送（v101.50）：提醒不止发到微信/邮件，也能弹到手机/电脑的系统通知。
   流程：①设置里「生成推送密钥」（浏览器里生成；私钥你复制到 GitHub Secrets 的 VAPID_PRIVATE_KEY，公钥自动存进仓库 data/push_vapid.json）
        ②每台设备点「开启本设备推送」（授权通知 + 订阅，订阅信息存进 data/push_subs.json）
        ③之后 GitHub Actions 发提醒时会同时推到这些设备（notify_alert.py 的 webpush 渠道，加密在 webpush_send.py）。
   iPhone：iOS 16.4+，且必须先「添加到主屏幕」再从主屏幕图标打开才能开启。 */
const PUSH = { pub: null, priv: null, msg: '', busy: false };
const pushSupported = () => { try { return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window; } catch (_) { return false; } };
const pushOn = () => { try { return localStorage.getItem('cockpit-push') === '1'; } catch (_) { return false; } };
const pushIos = () => /iPhone|iPad|iPod/.test(navigator.userAgent || '') && !(window.navigator.standalone || (window.matchMedia && matchMedia('(display-mode: standalone)').matches));
const u8FromB64u = t => { const p = String(t).replace(/-/g, '+').replace(/_/g, '/'), b = atob(p + '='.repeat((4 - p.length % 4) % 4)); return Uint8Array.from(b, c => c.charCodeAt(0)); };
const b64uFromU8 = a => btoa(String.fromCharCode(...a)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
async function pushPubLoad() { try { const r = await fetch('data/push_vapid.json?_=' + Date.now(), { cache: 'no-store' }); if (r.ok) { const j = await r.json(); PUSH.pub = j && j.publicKey ? String(j.publicKey) : null; } } catch (_) {} pushRefresh(); }
const pushRefresh = () => { try { planUpdate(false); } catch (_) { popRender(); } };   // 浮层内容是随计划页一起生成的，状态变了要整体重绘
function pushSet(m) { PUSH.msg = m; PUSH.busy = false; pushRefresh(); }
async function ghMerge(path, mutate, msg) {   // 读-改-写一个云端JSON文件（冲突重试一次）
  for (let k = 0; k < 2; k++) {
    const r = await ghApi('GET', path); let sha, cur = {};
    if (r.ok) { const j = await r.json(); sha = j.sha; try { cur = JSON.parse(b64d(j.content)) || {}; } catch (_) {} } else if (r.status !== 404) throw new Error(path + ' ' + ghErr(r.status));
    const w = await ghApi('PUT', path, { message: msg, content: b64e(JSON.stringify(mutate(cur), null, 1)), sha });
    if (w.ok) return true; if (w.status !== 409 && w.status !== 422) throw new Error(path + ' ' + ghErr(w.status));
  }
  throw new Error(path + ' 保存冲突，稍后再试');
}
function pushHtml() {
  const sup = pushSupported(), perm = sup ? Notification.permission : 'unsupported', on = pushOn(), has = !!patGet();
  let st, btn = '';
  if (!sup) st = pushIos() ? 'iPhone/iPad：请先用 Safari「分享 → 添加到主屏幕」，再从主屏幕图标打开本页（需要 iOS 16.4 以上），然后回到这里开启。' : '这个浏览器不支持网页推送（电脑建议 Chrome / Edge / Firefox，手机建议 Chrome / Safari 主屏幕应用）。';
  else if (!has) st = '需要先在上面「云端同步」填好 GitHub 令牌：密钥、订阅都存进你的仓库。';
  else if (!PUSH.pub) { st = '第 1 步（只做一次）：生成推送密钥。'; btn = '<button class="pbtn" data-act="push-gen">生成推送密钥</button>'; }
  else if (perm === 'denied') st = '浏览器已拒绝本站的通知权限：点地址栏左边的图标 → 网站设置 → 通知 → 允许，然后刷新本页。';
  else if (!on) { st = '密钥已配好。第 2 步（每台设备各做一次）：开启本设备推送。'; btn = '<button class="pbtn" data-act="push-on">开启本设备推送</button>'; }
  else { st = '本设备已开启：有入场信号、该平仓、止损线逼近时会弹系统通知。'; btn = '<button class="pbtn" data-act="push-test">发本机测试通知</button> <button class="lnk" data-act="push-off">关闭本设备推送</button>'; }
  const priv = PUSH.priv ? `<div class="plw">⚠️ 私钥只显示这一次：复制它 → GitHub 仓库 Settings → Secrets and variables → Actions → New repository secret，名字填 <b>VAPID_PRIVATE_KEY</b>（已存在就点它右边的铅笔「Update」改成新私钥，不要再新建）。不要发给别人。公钥已自动存进仓库。<textarea readonly rows="2" style="width:100%;margin-top:4px" onclick="this.select()">${esc(PUSH.priv)}</textarea></div>` : '';
  return `<div class="plt" style="margin-top:8px">网页推送（手机/电脑系统通知，页面关着也能收到）</div><div class="plh">${esc(st)}${PUSH.msg ? ' <b>' + esc(PUSH.msg) + '</b>' : ''}</div>${priv}${btn}${PUSH.pub && has && !PUSH.priv ? ' <button class="lnk" data-act="push-regen">重新生成密钥</button>' : ''}<div class="plh">服务端发送在 GitHub Actions 里跑（信号/平仓/止损线提醒同时推到这里）。设好后到 Actions → 测试提醒 点 Run workflow，能收到测试通知才算通。</div>`;
}
async function pushAct(act) {
  if (PUSH.busy) return; PUSH.busy = true; PUSH.msg = '处理中…'; pushRefresh();
  try {
    if (act === 'push-gen' || act === 'push-regen') {
      const force = act === 'push-regen';
      if (!force) { const r0 = await ghApi('GET', 'data/push_vapid.json'); if (r0.ok) { try { const j0 = JSON.parse(b64d((await r0.json()).content)); if (j0 && j0.publicKey) { PUSH.pub = String(j0.publicKey); return pushSet('云端已经有推送密钥了（别的设备生成过），不要重复生成。直接点「开启本设备推送」。'); } } catch (_) {} } }
      else if (!confirm('重新生成会让旧私钥和所有已登记设备失效：需要在 Secrets 里把 VAPID_PRIVATE_KEY 改成新私钥，并且每台设备重新开启推送。确定吗？')) return pushSet('已取消。');
      const k = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']), jw = await crypto.subtle.exportKey('jwk', k.privateKey);
      const pub = b64uFromU8(Uint8Array.from([4, ...u8FromB64u(jw.x), ...u8FromB64u(jw.y)]));
      await ghMerge('data/push_vapid.json', () => ({ publicKey: pub, created: todayBJ() }), '推送公钥 ' + todayBJ());
      if (force) { try { await ghMerge('data/push_subs.json', () => ({ subs: [], updated: todayBJ() }), '换密钥，清空旧设备 ' + todayBJ()); } catch (_) {} try { localStorage.removeItem('cockpit-push'); } catch (_) {} }
      PUSH.pub = pub; PUSH.priv = jw.d; return pushSet('已生成。请马上复制私钥。');
    }
    if (act === 'push-on') {
      if (!PUSH.pub) return pushSet('还没有推送密钥，先生成。');
      try { const r1 = await ghApi('GET', 'data/push_vapid.json'); if (r1.ok) { const j1 = JSON.parse(b64d((await r1.json()).content)); if (j1 && j1.publicKey) PUSH.pub = String(j1.publicKey); } } catch (_) {}   // 以仓库里最新的公钥为准，不用网页缓存
      const perm = await Notification.requestPermission(); if (perm !== 'granted') return pushSet('没有拿到通知权限（' + perm + '）。');
      const reg = await navigator.serviceWorker.register('sw.js'); await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription(); if (sub) { const cur = sub.options && sub.options.applicationServerKey ? b64uFromU8(new Uint8Array(sub.options.applicationServerKey)) : null; if (cur && cur !== PUSH.pub) { await sub.unsubscribe(); sub = null; } }
      sub = sub || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: u8FromB64u(PUSH.pub) });
      const j = sub.toJSON(); await ghMerge('data/push_subs.json', c => { const a = (c.subs || []).filter(x => x.endpoint !== j.endpoint); a.push({ endpoint: j.endpoint, keys: j.keys, pub: PUSH.pub, ua: (navigator.userAgent || '').slice(0, 80), added: todayBJ() }); return { subs: a, updated: todayBJ() }; }, '登记推送设备 ' + todayBJ());
      try { localStorage.setItem('cockpit-push', '1'); } catch (_) {} return pushSet('已开启并登记到云端。');
    }
    if (act === 'push-test') { const reg = await navigator.serviceWorker.ready; await reg.showNotification('豆粕驾驶舱 · 测试通知', { body: '看到这条说明本设备的通知权限没问题。服务端推送请用 Actions →「测试提醒」验证。', tag: 'doupo-test', icon: 'icon-192.png' }); return pushSet('已发出本机测试通知。'); }
    if (act === 'push-off') {
      const reg = await navigator.serviceWorker.getRegistration('sw.js'), sub = reg && await reg.pushManager.getSubscription(), ep = sub && sub.endpoint;
      if (sub) await sub.unsubscribe(); try { localStorage.removeItem('cockpit-push'); } catch (_) {}
      if (ep && patGet()) { try { await ghMerge('data/push_subs.json', c => ({ subs: (c.subs || []).filter(x => x.endpoint !== ep), updated: todayBJ() }), '移除推送设备 ' + todayBJ()); } catch (_) {} }
      return pushSet('已关闭本设备推送。');
    }
  } catch (e) { pushSet('失败：' + String((e && e.message) || e).slice(0, 120)); }
}
setTimeout(pushPubLoad, 1500);

/* ---- 放大全屏：每张图右上角 ⤢，Esc 或点「关闭」退出 ---- */
const FULL = { kind: null };
const FULLT = { px: '价格与持仓', price: '价格与持仓', pos: '价格位置', sea: '同期规律', cost: '成本锚' };
function fullBody() { return $('#fsB'); }
function renderFull() {
  const k = FULL.kind; if (!k) return; const b = fullBody(); if (!b) return; const was = MULTI; MULTI = true;   // 全屏里不要切换按钮
  try {
    if (k === 'px' || k === 'price') {
      b.innerHTML = `<div class="ch-r" style="justify-content:flex-start"><div class="seg" role="group" aria-label="周期">${[40, 80, 120].map(n => `<button data-range="${n}" aria-pressed="${!S.intra && S.range === n}">${n}日</button>`).join('')}${D.m15 && D.m15[S.key] ? `<button data-intra="1" aria-pressed="${!!S.intra}">15分</button>` : ''}</div></div><div class="kl" id="klF" style="flex:1 1 auto;min-height:320px"></div>`;
      drawChart(b.querySelector('#klF'));
    } else if (k === 'pos') { b.innerHTML = viewPos(b, 1500, Math.max(260, b.clientHeight - 150)); }
    else if (k === 'sea') b.innerHTML = viewSea();
    else b.innerHTML = viewCost();
    b.querySelectorAll('.fsbtn,.ch-h .q').forEach(e => e.remove());
  } finally { MULTI = was; }
}
function openFull(k) {
  if (!FULLT[k]) return; FULL.kind = k === 'price' ? 'px' : k;
  let o = $('#fsv'); if (!o) { o = document.createElement('div'); o.id = 'fsv'; o.setAttribute('role', 'dialog'); o.setAttribute('aria-modal', 'true'); document.body.appendChild(o); }
  o.innerHTML = `<div class="fsh"><span class="t">${esc(C().symbol || '')} ${FULLT[k]}</span><button class="tb" id="fsX" aria-label="关闭全屏">关闭 ✕</button></div><div class="fsb2" id="fsB"></div>`;
  o.classList.add('on'); document.body.classList.add('fs-on'); renderFull();
}
function closeFull() { const o = $('#fsv'); if (o) o.classList.remove('on'); document.body.classList.remove('fs-on'); FULL.kind = null; }
function renderAll(anim) { renderHeader(); renderBand(); renderSig(); renderChecks(); renderChart(); renderWall(anim); tradeShell(); planUpdate(); }

/* ---------- 事件 ---------- */
document.addEventListener('toggle', e => { const d = e.target; if (d && d.classList && d.classList.contains('vmore')) { S.vm = S.vm || {}; S.vm[d.dataset.vm] = d.open; } }, true);
document.addEventListener('click', e => {
  const dz = e.target.closest('[data-dsl]'); if (dz) { e.preventDefault(); e.stopPropagation(); S.dslOpen = !S.dslOpen; renderSig(); return; }
  if (!e.target.closest('.lyw')) $$('.lym').forEach(m => { m.hidden = true; });
  const pbn = e.target.closest('[data-probe]'); if (pbn) { const rf = () => { const b = document.getElementById('shB'); if (b && b.querySelector('[data-probe]')) openLamp('hlth'); }; if (D.probe && D.probe.busy) return; D.probe = { busy: true, rows: null, at: Date.now() }; rf(); (window.CockpitData && window.CockpitData.probeTicks ? window.CockpitData.probeTicks() : Promise.resolve([{ name: '实时价', ok: false, ms: 0, detail: '页面还没准备好' }])).then(rows => { D.probe = { busy: false, rows, at: Date.now() }; rf(); }).catch(() => { D.probe = null; rf(); }); return; }
  const lb = e.target.closest('[data-lyr]'); if (lb) { const m = lb.parentElement.querySelector('.lym'); m.hidden = !m.hidden; lb.setAttribute('aria-expanded', String(!m.hidden)); return; }
  const t = e.target.closest('button,[data-tile]'), pop = $('#cPop'), cb = $('#cBtn');
  if (!e.target.closest('#cPop') && !e.target.closest('#cBtn')) { pop.classList.remove('on'); cb.setAttribute('aria-expanded', 'false'); }
  if (!t) return;
  if (t.id === 'cBtn') { const on = pop.classList.toggle('on'); cb.setAttribute('aria-expanded', on); return; }
  if (t.dataset.ck) { if (t.dataset.ck === 'auto') { S.auto = true; S.key = autoKey(); } else { S.key = t.dataset.ck; S.auto = S.key === autoKey(); } pop.classList.remove('on'); cb.setAttribute('aria-expanded', 'false'); renderAll(true); return; }
  if (t.id === 'exBtn') { S.ex = !S.ex; document.body.classList.toggle('ex', S.ex); t.setAttribute('aria-pressed', S.ex); layoutWall(false); return; }
  if (t.id === 'thBtn') { S.themePref = { auto: 'day', day: 'night', night: 'auto' }[S.themePref]; applyTheme(); try { localStorage.setItem('cockpit-theme', S.themePref); } catch (_) {} return; }
  if (t.id === 'syncDot') { S.pop = 'set'; popRender(); return; }
  if (t.id === 'flBtn' || t.id === 'setBtn') { popSet(t.id === 'flBtn' ? 'fl' : 'set'); return; }
  if (t.dataset.pop) { S.pop = null; popRender(); return; }
  if (t.id === 'fsX') { closeFull(); return; }
  if (t.dataset.full) { openFull(t.dataset.full); return; }
  if (t.id === 'abBtn') { openAbout(); return; }
  if (t.id === 'planBtn' || t.id === 'planHide') { S.planShow = !planShown(); applyPlanVis(); return; }
  if (t.dataset.opt) { planOptToggle(t.dataset.opt); return; }
  if (t.dataset.about) { openAbout(t.dataset.about); return; }
  if (t.id === 'shX') { closeSheet(); return; }
  if (t.dataset.tile) { openTile(t.dataset.tile); return; }
  if (t.dataset.more || t.dataset.pend) { openMore(t.dataset.sum); return; }
  if (t.dataset.lamp) { openLamp(t.dataset.lamp); return; }
  if (t.dataset.sea) { S.seaKind = t.dataset.sea; renderChart(); return; }
  if (t.dataset.mode) { setMode(t.dataset.mode); return; }
  if (t.dataset.goplan) { setMode('trade'); S.planShow = t.dataset.goplan === 'toggle' ? !planShown() : true; applyPlanVis(); const tp = $('#tradePanel'); if (tp && tp.scrollIntoView && window.innerWidth < 900) tp.scrollIntoView({ block: 'start' }); return; }
  if (t.dataset.act) { planAct(t.dataset.act, t); return; }
  if (t.dataset.view) { S.view = t.dataset.view; renderChart(); return; }
  if (t.dataset.intra) { S.intra = true; $$('[data-range]').forEach(b => b.setAttribute('aria-pressed', 'false')); $$('[data-intra]').forEach(b => b.setAttribute('aria-pressed', 'true')); drawChart(); if (FULL.kind) renderFull(); return; }
  if (t.dataset.range) { S.intra = false; $$('[data-intra]').forEach(b => b.setAttribute('aria-pressed', 'false')); S.range = +t.dataset.range; $$('[data-range]').forEach(b => b.setAttribute('aria-pressed', +b.dataset.range === S.range)); drawChart(); if (FULL.kind) renderFull(); return; }
  if (t.dataset.span) { S.span = t.dataset.span; $$('[data-span]').forEach(b => b.setAttribute('aria-pressed', b.dataset.span === S.span)); layoutWall(true); return; }
  if (t.dataset.tab) { openTab(t.dataset.tab); return; }
});
document.addEventListener('change', e => { const el = e.target.closest && e.target.closest('[data-ly]'); if (!el) return; S.ly = Object.assign({}, S.ly || LYD, { [el.dataset.ly]: el.checked }); try { localStorage.setItem('cockpit-ly', JSON.stringify(S.ly)); } catch (_) {} $$('[data-ly="' + el.dataset.ly + '"]').forEach(x => { x.checked = el.checked; }); drawChart(); if (MULTI) $$('#mg1 #kl').forEach(k => drawChart(k)); });
$('#scrim').addEventListener('click', closeSheet);
document.addEventListener('keydown', e => {
  if (e.target.matches && e.target.matches('input,textarea')) return;
  if (e.key === 'Escape' && FULL.kind) { closeFull(); return; }
  if (e.key === 'Escape' && S.pop) { S.pop = null; popRender(); return; }
  if (e.key === 'Escape') { const sheetOn = $('#sheet').classList.contains('on'); closeSheet(); $('#cPop').classList.remove('on'); if (!sheetOn && S.mode === 'trade' && planShown() && !curPos()) { S.planShow = false; applyPlanVis(); } return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === 'e' || e.key === 'E') $('#exBtn').click(); else if (e.key === '?') openAbout(); else if (/^[1-6]$/.test(e.key)) openTab(TABS[+e.key - 1][0]);
});
document.addEventListener('input', e => { if (e.target.id && e.target.id.startsWith('pf-')) e.target.dataset.t = '1'; });
document.addEventListener('change', e => { const t = e.target; if (t.id === 'pf-file') { if (t.files && t.files[0]) planRestore(t.files[0]); t.value = ''; } else if (t.dataset && t.dataset.set) planSetting(t); });
document.addEventListener('change', e => { const r = e.target.closest && e.target.closest('.inp'); if (!r || !window.CockpitData || !window.CockpitData.manualEdit) return; const s = $('.s', r); if (s) s.textContent = '重新计分中…'; window.CockpitData.manualEdit(r.dataset.key, e.target.value.trim()).then(ok => { if (!ok && s) s.textContent = '没有写进评分引擎（引擎还没就绪）'; }); });
document.addEventListener('input', e => { const r = e.target.closest && e.target.closest('.inp'); if (!r) return; r.classList.toggle('ov', e.target.value !== e.target.dataset.orig); });
let rz; const relayout = () => { clearTimeout(rz); rz = setTimeout(() => { if (MULTI !== multiOn()) renderChart(); else drawChart(); layoutWall(false); }, 100); };
window.addEventListener('resize', relayout); window.addEventListener('resize', () => { if (FULL.kind) renderFull(); });
if (typeof ResizeObserver === 'function') { const ro = new ResizeObserver(relayout); ro.observe($('#tiles') || document.body); ro.observe($('#chart')); }
setInterval(applyTheme, 60000);
try { const l = JSON.parse(localStorage.getItem('cockpit-ly') || 'null'); if (l && typeof l === 'object') S.ly = Object.assign({}, LYD, l); } catch (_) {}
try { const t = localStorage.getItem('cockpit-theme'); if (t === 'day' || t === 'night' || t === 'auto') S.themePref = t; } catch (_) {}
S.mode = curPos() ? 'trade' : 'research';   // 空仓默认先看研究页；有持仓默认看交易页
setMode(S.mode, true); applyTheme(); renderAll(true); setMode(S.mode, true);
setInterval(() => { const ae = document.activeElement; if (!document.hidden && patGet() && !CLOUD.busy && !CLOUD.timer && !(ae && ae.matches && ae.matches('input,select,textarea') && ae.closest('#planForm'))) cloudPull(); }, window.__CLOUD_POLL_MS || 2 * 60 * 1000);   // 页面开着：每2分钟拉一次云端（有人在填表单时不拉）
syncDotUpdate(); cloudPull(); document.addEventListener('visibilitychange', () => { if (!document.hidden && !CLOUD.busy && !CLOUD.timer) cloudPull(); });
function refreshed() {   // 后台重取数据后调用：不打断正在输入的表单
  if (S.auto) S.key = autoKey();
  const ae = document.activeElement, typing = ae && ae.closest && ae.closest('#planForm, .inp');
  if (typing) { renderHeader(); renderBand(); renderSig(); renderChecks(); renderWall(false); }
  else renderAll(false);
}
window.__cockpit = { curTick, sessOf, pxLabel, tickPaint, tickInfo, liveBar, tradeDayOf, macdOf, S, L, reconcile, serLast, ageTxt, missWhy, openLamp, openMore, openTile, klineNow, priceStats, renderBand, planSnap, renderAll, refreshed, openTab, openTile, openAbout, closeSheet, layoutWall, checks, capital, fundamentals, tiles, applyTheme, get GRID() { return GRID; } };
})();

