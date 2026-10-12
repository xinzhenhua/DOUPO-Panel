/* 豆粕驾驶舱：取数与装配(浏览器和Node通用的纯函数 + 浏览器里的启动流程)。
 * 数据来源（全部自动，页面每次打开/定时刷新都会重新取）：
 *   1. engine.html（旧版评分引擎）在后台隐藏 iframe 里运行：自己取 data/latest.json、汇率、天气等，算出逐票投票/徽标/健康度/事件日历；
 *      这里只"读"它的结果，不重复实现评分——评分逻辑只有一份。
 *   2. data/history/*.json：每个指标的历史序列（趋势墙、净倾向走势、系统记录）。
 *   3. data/seasonal.json：同期规律；data/raw/seasonal/M0_daily.csv：豆粕主连日线（价格分位、交易计划）。
 * 纯函数部分有单元测试（tests/test_cockpit_loader.js），启动流程由端到端测试覆盖（tests/e2e_cockpit.py）。 */
(function (root) {
  'use strict';
  const CL = {};
  const KEYS = ['sep', 'may', 'jan'];
  const BARS = { sep: 'dceM09Daily', may: 'dceM05Daily', jan: 'dceM01Daily' };

  /* ---------- 纯函数 ---------- */
  CL.parseCsv = function (text) {
    const lines = String(text || '').replace(/^﻿/, '').split(/\r?\n/).filter(l => l.trim());
    if (lines.length < 2) return [];
    const head = lines[0].split(',').map(s => s.trim());
    return lines.slice(1).map(l => { const c = l.split(','), o = {}; head.forEach((h, i) => { o[h] = c[i] == null ? '' : c[i].trim(); }); return o; });
  };
  /* 主连日线 CSV → {d:[],c:[]}；只留收盘价为正数的行，日期升序去重 */
  CL.histFromCsv = function (text, from) {
    const rows = CL.parseCsv(text), seen = new Map();
    for (const r of rows) { const c = parseFloat(r.close); if (!r.date || !(c > 0)) continue; if (from && r.date < from) continue; seen.set(r.date, c); }
    const d = [...seen.keys()].sort();
    return { d, c: d.map(k => seen.get(k)) };
  };
  /* 换月调整后的主力连续价 data/main_adj.json {d,i,k} → {d,c,k}：按「最后一个与原始主连共有的日期」折算成价格水平（i 本身以100为基准）。
   交易信号（价格分位/均线/反弹确认）和持仓涨跌必须用它：原始主连在换月日会跳一个合约价差（豆粕可到 7%），回测用的就是调整后的。 */
  CL.adjFrom = function (j, hist) {
    if (!j || !Array.isArray(j.d) || !Array.isArray(j.i) || j.d.length !== j.i.length) return null;
    const d = [], v = [], k = [];
    for (let n = 0; n < j.d.length; n++) { const x = +j.i[n]; if (j.d[n] && x > 0 && isFinite(x)) { d.push(String(j.d[n]).slice(0, 10)); v.push(x); k.push(j.k ? j.k[n] : null); } }
    if (d.length < 200) return null;
    let scale = 1;
    if (hist && hist.d && hist.d.length) { const m = new Map(hist.d.map((x, n) => [x, hist.c[n]])); for (let n = d.length - 1; n >= 0; n--) if (m.has(d[n])) { scale = m.get(d[n]) / v[n]; break; } }
    return { d, c: v.map(x => x * scale), k };
  };
  const pt = p => ({ d: p.d, v: p.v });
  const tail = (a, n) => (n ? a.slice(-n) : a);
  /* 当前窗口内的连续一段：series 里按"推荐月份"截取最近一段（跨度超过 gapDays 视为另一个窗口） */
  CL.windowRun = function (pts, months, gapDays) {
    gapDays = gapDays || 45;
    const mo = d => +String(d).slice(5, 7), ms = d => Date.parse(String(d).slice(0, 10) + 'T00:00:00Z');
    let j = -1; for (let i = pts.length - 1; i >= 0; i--) if (months.includes(mo(pts[i].d))) { j = i; break; }
    if (j < 0) return [];
    let k = j; while (k > 0 && months.includes(mo(pts[k - 1].d)) && ms(pts[k].d) - ms(pts[k - 1].d) <= gapDays * 86400e3) k--;
    return pts.slice(k, j + 1);
  };
  /* 把 history 文件装成趋势墙用的 series。H: {文件名: points[]}；meta: static.json 里的 series 骨架 */
  CL.buildSeries = function (meta, H, ctx) {
    const out = {}, get = n => (H[n] && H[n].length ? H[n] : null);
    for (const k of Object.keys(meta)) out[k] = Object.assign({}, meta[k], { pts: [], nTotal: 0 });
    const put = (key, pts, total) => { if (!out[key] || !pts) return; out[key].pts = pts; out[key].nTotal = total == null ? pts.length : total; };
    const plain = (key, file, cap) => { const a = get(file); if (a) put(key, tail(a.map(pt), cap), a.length); };
    plain('stock', 'meal_stock', 160); plain('stu', 'meal_stu'); plain('ustu', 'us_stocks_to_use', 10); plain('crush', 'crush_rate', 140);
    plain('arrival', 'arrival_forecast'); plain('import', 'soy_import', 40); plain('feed', 'feed_days', 160); plain('hog', 'hog_ratio');
    plain('poultry', 'poultry_ndrc'); plain('rm', 'rm_spread'); plain('cftc', 'cftc_mm_net'); plain('gs', 'capital_gs_net'); plain('zl', 'capital_zl_net');
    const esr = get('esr_net_sales');
    if (esr) { const v = esr.map(p => p.v), e4 = []; for (let k = 3; k < esr.length; k++) e4.push({ d: esr[k].d, v: Math.round((v[k - 3] + v[k - 2] + v[k - 1] + v[k]) / 4 / 1e4 * 1e4) / 1e4 }); put('esr', tail(e4, 160), e4.length); }
    const sb = get('spot_basis');
    if (sb) {
      put('basis', tail(sb.map(pt), 160), sb.length);
      const dom = String(((sb[sb.length - 1].x || {}).dom) || '').toLowerCase();
      if (dom) out.basis.note = '分位只在当前主力合约(' + dom.toUpperCase() + ')自己的历史里算——换月造成的断层不混进来；该合约样本<20个交易日不计分';
    }
    for (const c of KEYS) for (const [a, f] of [['margin', 'crush_margin_'], ['spread', 'term_spread_']]) {
      const all = get(f + c); if (!all) continue;
      put(a + '_' + c, CL.windowRun(all.map(pt), ctx[c].recommendedMonths), all.length);
    }
    return out;
  };
  CL.buildSystems = function (H) {
    const out = {};
    for (const c of KEYS) out[c] = (H['systems_' + c] || []).filter(p => p.x).map(p => ({ d: p.d, v: p.v, dir: p.x.fundDir, n: p.x.fundN }));
    return out;
  };
  CL.basisSame = function (H) {
    const sb = H.spot_basis || []; if (!sb.length) return { contract: '', n: 0, min: 20 };
    const dom = String(((sb[sb.length - 1].x || {}).dom) || '').toLowerCase(), last = sb[sb.length - 1].d;
    return { contract: dom, n: sb.filter(p => String((p.x || {}).dom || '').toLowerCase() === dom && p.d !== last).length, min: 20 };
  };
  /* 龙虎榜席位历史覆盖：取自 data/history/_backfill_report.json 里 key=capital_rank 那一项（每小时补齐时写入）；没有就返回 null */
  CL.coverageFrom = function (rep) {
    const e = rep && Array.isArray(rep.series) ? rep.series.find(s => s && s.key === 'capital_rank' && s.coverage && !s.error) : null;
    if (!e) return null;
    const seats = {};
    for (const n of Object.keys(e.coverage)) { const c = e.coverage[n] || {}; seats[n] = { exact: +c.exact || 0, estimated: +c.estimated || 0, absent: +c.absent || 0 }; }
    return { firstDay: e.firstDay || null, lastDay: e.lastDay || null, files: e.files || null, runAt: e.runAt || rep.generatedAt || null, seats };
  };
  CL.crushFrom = function (latest) {
    const out = {}, cm = (latest && latest.crushMargins) || {};
    for (const c of KEYS) { const x = cm[c]; out[c] = x ? { available: !!x.available, mealSymbol: x.mealSymbol, mealPrice: x.mealPrice, oilPrice: x.oilPrice, beanPrice: x.beanPrice, date: x.date } : { available: false }; }
    return out;
  };
  /* 读 engine 窗口的结果（与 CI 里每小时记录系统方向的 jsdom 脚本读的是同一批变量） */
  CL.engineState = function (w, nowMs) {
    const clone = x => (x === undefined ? null : JSON.parse(JSON.stringify(x)));
    const out = { scoringVersion: w._scoringVersion, contracts: {} };
    const prev = w._selectedContract;
    for (const c of KEYS) {
      w.selectContract(c); w.updateOverallAlert();
      const sd = w._syncedData || {}, sym = (sd[BARS[c]] || {}).symbol, bars = (sd[BARS[c]] || {}).bars || [];
      let vpSeq = [];
      try {
        const st = w.vpContractStartMs(sym);
        for (let i = Math.max(0, bars.length - 10); i < bars.length; i++) {
          const r = w.vpAt(bars, i, st);
          const quad = r.odir === 1 ? (r.pdir === 1 ? '增仓上涨' : r.pdir === -1 ? '增仓下跌' : '增仓横盘') : r.odir === -1 ? (r.pdir === 1 ? '减仓上涨' : r.pdir === -1 ? '减仓下跌' : '减仓横盘') : (r.pdir === 1 ? '持仓平稳上涨' : r.pdir === -1 ? '持仓平稳下跌' : '价格持仓均平稳');
          vpSeq.push({ d: String(bars[i].date).slice(0, 10), gate: r.gate || null, pc: r.pc, oc: r.oc, pdir: r.pdir, odir: r.odir, signal: r.signal, volRatio: r.volRatio, quad });
        }
      } catch (e) { vpSeq = []; }
      out.contracts[c] = {
        symbol: sym, votes: clone(w._votesDump) || [], pure: clone(w._fundamentalPure), structure: clone(w._structureSystem), composite: clone(w._composite),
        tech: w._technicalDirection || null, confidence: w._fundamentalConfidence || null, dims: clone(w._dimensions), vpStatus: w._vpStatus, vpReason: w._vpReason,
        bars: clone(bars), vpSeq, health: clone(w.computeDataHealth ? w.computeDataHealth(nowMs) : null),
      };
    }
    out.indicators = (w._autoIndicators || []).map(cfg => { const inp = w.document.getElementById(cfg.inputId), bd = w.document.getElementById('ind_' + cfg.key); return { key: cfg.key, inputId: cfg.inputId, title: cfg.title, freq: cfg.freq || null, source: cfg.sourceName || null, noVote: cfg.noVote || null, unit: cfg.unit || null, input: inp ? inp.value : null, badge: bd ? bd.textContent : null }; });
    out.events = clone(w._eventCal.buildEventList(nowMs, nowMs + 45 * 86400000));
    out.closure = clone(w._eventCal.closureStatus(nowMs, 3));
    if (prev && prev !== KEYS[KEYS.length - 1]) { try { w.selectContract(prev); w.updateOverallAlert(); } catch (e) { /* 还原失败不影响读数 */ } }
    return out;
  };
  /* 盘中价：prices.json(每15分钟) 和 latest.json 里的15分钟/小时线，谁新用谁；日线只到上一个收盘，信号用日线，盘中价只作参考 */
  CL.livePrices = function (L, prices) {
    L = L || {};
    const live = {}, m15 = {};   // 盘中：15分钟线优先、小时线兜底；日线只到上一个收盘，信号用日线，盘中价只作参考
    const HR = { sep: 'dceM09Hourly', may: 'dceM05Hourly', jan: 'dceM01Hourly' }, MR = { sep: 'dceM09Min15', may: 'dceM05Min15', jan: 'dceM01Min15' };
    const PK = { sep: 'M09', may: 'M05', jan: 'M01' }, PR = (prices && prices.contracts) || {};
    for (const c of KEYS) { try {
      const pb = ((PR[PK[c]] || {}).bars || []).filter(b => b && b.close != null), mb0 = ((L[MR[c]] || {}).bars || []).filter(b => b && b.close != null), mb = pb.length && (!mb0.length || String(pb[pb.length - 1].datetime) >= String(mb0[mb0.length - 1].datetime)) ? pb : mb0;
      const hb = ((L[HR[c]] || {}).bars || []).filter(b => b && b.close != null), lb = (mb.length ? mb : hb).slice(-1)[0];
      if (mb.length) m15[c] = mb.map(b => ({ d: String(b.datetime || '').slice(5, 16), o: b.open, h: b.high, l: b.low, c: b.close, v: b.volume, oi: b.hold }));
      if (lb) live[c] = { dt: String(lb.datetime || '').slice(0, 16), c: +lb.close, src: mb.length ? '15分钟' : '小时' };
    } catch (_) { /* 没有盘中数据就不显示 */ } }
    return { live, m15 };
  };
  /* 把所有来源装成驾驶舱的 D。in: {state, latest, H, seasonal, histCsv, now, STATIC} */
  CL.assemble = function (inp) {
    const S = inp.state, L = inp.latest || {}, H = inp.H || {}, ST = inp.STATIC, now = inp.now;
    const D = { polarity: ST.polarity, ctx: ST.ctx, contracts: {} };
    { const lp = CL.livePrices(L, inp.prices); D.live = lp.live; D.m15 = lp.m15; }
    for (const c of KEYS) {
      const s = S.contracts[c];
      D.contracts[c] = {
        symbol: s.symbol,
        votes: s.votes.map(v => { const o = {}; for (const k of ['label', 'side', 'signal', 'weight', 'baseWeight', 'q', 'qwhy', 'note']) o[k] = v[k]; return o; }),
        pure: s.pure, confidence: s.confidence || '',
        structure: s.structure ? { n: s.structure.n, direction: s.structure.direction, ratio: s.structure.ratio, thin: s.structure.thin } : null,
        tech: s.tech, dims: s.dims,
        vp: { status: s.vpStatus, reason: s.vpReason || null, signal: (() => { const v = s.votes.find(x => String(x.label).startsWith('量价关系')); return v && v.signal !== undefined ? v.signal : null; })() },
        kline: s.bars.slice(-160).map(b => ({ d: String(b.date).slice(0, 10), o: b.open, h: b.high, l: b.low, c: b.close, v: b.volume, oi: b.hold })),
        vpSeq: s.vpSeq,
      };
    }
    D.snapshotMs = now;
    D.indicators = S.indicators.map(x => ({ key: x.key, inputId: x.inputId, title: x.title, freq: x.freq, source: x.source, noVote: x.noVote, unit: x.unit, input: x.input, badge: x.badge }));
    D.events = S.events.map(e => ({ kind: e.kind, label: e.label, title: e.title, ms: e.ms }));
    D.closure = S.closure;
    const bj = new Date(now + 8 * 3600e3), month = bj.getUTCMonth() + 1;
    const auto = KEYS.find(k => ST.ctx[k].recommendedMonths.includes(month)) || 'sep';
    const h = S.contracts[auto].health || {};
    D.health = { level: h.level, sync: h.sync, bad: h.bad, warn: h.warn, missing: h.missing, rows: h.rows };
    D.capital = L.marketCapital || null; D.cftc = L.cftcManagedMoney || null;
    D.scoring = S.scoringVersion || '';
    D.series = CL.buildSeries(ST.series, H, ST.ctx);
    D.systems = CL.buildSystems(H);
    D.generatedAt = L.generatedAt || '';
    D.cftcRawHasHistory = !!(L.cftcManagedMoney && 'history' in L.cftcManagedMoney);
    D.basisSame = CL.basisSame(H);
    const last = a => (a && a.length ? a[a.length - 1].d : '');
    D.seriesAsOf = { history: last(H.hog_ratio) || last(H.meal_stock) || '', systems: last(D.systems.sep) };
    D.pricePosition = L.pricePosition || {}; D.costAnchor = L.costAnchor || null;
    D.hist = inp.histCsv ? CL.histFromCsv(inp.histCsv, '2015-04-03') : { d: [], c: [] };
    D.adj = CL.adjFrom(inp.adj, D.hist);
    D.sea = inp.seasonal || null;
    D.crush = CL.crushFrom(L);
    D.capitalCoverage = CL.coverageFrom(inp.report);
    return D;
  };
  /* 把 src 的内容就地灌进 dst（界面代码里持有 D 和 D.series 的引用，刷新时不能换对象） */
  CL.fill = function (dst, src) { for (const k of Object.keys(dst)) if (!(k in src)) delete dst[k]; for (const k of Object.keys(src)) dst[k] = src[k]; return dst; };

  /* ---------- 浏览器启动流程 ---------- */
  CL.boot = function (opts) {
    const doc = document, STATIC = opts.STATIC, runUI = opts.runUI, status = opts.status;
    const base = './', ts = () => '?t=' + Date.now();
    const jget = async (u) => { const r = await fetch(base + u + ts(), { cache: 'no-store' }); if (!r.ok) throw new Error(u + ' HTTP ' + r.status); return r.json(); };
    const tget = async (u) => { const r = await fetch(base + u + ts(), { cache: 'no-store' }); if (!r.ok) throw new Error(u + ' HTTP ' + r.status); return r.text(); };
    const HFILES = ['meal_stock', 'meal_stu', 'us_stocks_to_use', 'crush_rate', 'arrival_forecast', 'soy_import', 'feed_days', 'hog_ratio', 'poultry_ndrc', 'rm_spread', 'esr_net_sales', 'spot_basis', 'cftc_mm_net', 'capital_gs_net', 'capital_zl_net',
      'crush_margin_sep', 'crush_margin_may', 'crush_margin_jan', 'term_spread_sep', 'term_spread_may', 'term_spread_jan', 'systems_sep', 'systems_may', 'systems_jan'];
    let frame = null, D = null, timers = [], fails = [], lastSide = null;
    function loadFrame() {
      return new Promise((res, rej) => {
        if (frame) frame.remove();
        frame = doc.createElement('iframe'); frame.id = 'engineFrame'; frame.setAttribute('aria-hidden', 'true'); frame.tabIndex = -1; frame.title = '评分引擎';
        frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:1280px;height:900px;border:0;visibility:hidden;pointer-events:none';
        frame.onload = () => res(frame.contentWindow); frame.onerror = () => rej(new Error('engine.html 加载失败'));
        frame.src = base + 'engine.html' + ts(); doc.body.appendChild(frame);
      });
    }
    async function fetchSide() {
      fails = [];
      const H = {};
      await Promise.all(HFILES.map(async n => { try { const j = await jget('data/history/' + n + '.json'); H[n] = j.points || []; } catch (e) { fails.push(n); } }));
      let latest = null, seasonal = null, histCsv = '', report = null, adj = null, prices = null;
      try { latest = await jget('data/latest.json'); } catch (e) { fails.push('latest.json'); }
      try { seasonal = await jget('data/seasonal.json'); } catch (e) { fails.push('seasonal.json'); }
      try { histCsv = await tget('data/raw/seasonal/M0_daily.csv'); } catch (e) { fails.push('M0_daily.csv'); }
      try { adj = await jget('data/main_adj.json'); } catch (e) { /* 可选文件：没有就退回原始主连，并在交易信号的数据状态里明说 */ }
      try { report = await jget('data/history/_backfill_report.json'); } catch (e) { /* 可选文件：没有就不显示覆盖表，不算缺文件 */ }
      try { prices = await jget('data/prices.json'); } catch (e) { /* 可选文件：没有就用基本面更新里的小时线/15分钟线 */ }
      lastSide = { H, latest, seasonal, histCsv, report, adj, prices };
      return lastSide;
    }
    async function waitReady(w, maxMs) {
      const t0 = Date.now();
      while (Date.now() - t0 < maxMs) { if (w._syncedData && w._eventCal && typeof w.selectContract === 'function') return true; await new Promise(r => setTimeout(r, 200)); }
      return false;
    }
    async function build() {
      const w = frame.contentWindow, now = Date.now();
      const state = CL.engineState(w, now);
      return { state, now };
    }
    async function cycle(first) {
      try {
        status(first ? '正在启动评分引擎并读取数据…' : null);
        const [w, side] = await Promise.all([loadFrame(), fetchSide()]);
        if (!(await waitReady(w, 30000))) throw new Error('评分引擎没有拿到 data/latest.json（引擎页同步失败）');
        await new Promise(r => setTimeout(r, first ? 2500 : 1500));   // 让引擎里的异步指标（汇率/天气/龙虎榜）落定
        const { state, now } = await build();
        const nd = CL.assemble({ state, latest: side.latest, H: side.H, seasonal: side.seasonal, histCsv: side.histCsv, report: side.report, adj: side.adj, prices: side.prices, now, STATIC });
        if (!D) { D = nd; window.__DATA__ = D; runUI(); }
        else { const ser = D.series, con = D.contracts; CL.fill(ser, nd.series); delete nd.series; CL.fill(con, nd.contracts); delete nd.contracts; CL.fill(D, nd); D.series = ser; D.contracts = con; if (window.__cockpit) window.__cockpit.refreshed(); }
        status('', fails);
        if (first) { timers.push(setTimeout(() => cycleLight(), 9000), setTimeout(() => cycleLight(), 24000)); }
      } catch (e) { status('error', fails, e); }
    }
    /* 只重新读引擎（不重载 iframe）：用来吃进启动后才返回的汇率/天气等异步指标 */
    async function cycleLight() {
      try { if (!frame || !D) return; const { state, now } = await build(); const side = lastSide || await fetchSide(); const nd = CL.assemble({ state, latest: side.latest, H: side.H, seasonal: side.seasonal, histCsv: side.histCsv, report: side.report, adj: side.adj, prices: side.prices, now, STATIC }); const ser = D.series, con = D.contracts; CL.fill(ser, nd.series); delete nd.series; CL.fill(con, nd.contracts); delete nd.contracts; CL.fill(D, nd); D.series = ser; D.contracts = con; if (window.__cockpit) window.__cockpit.refreshed(); } catch (e) { /* 静默：下一轮再试 */ }
    }
    CL.manualEdit = async function (key, value) {
      const w = frame && frame.contentWindow; if (!w) return false;
      const cfg = (w._autoIndicators || []).find(c => c.key === key); if (!cfg) return false;
      const el = w.document.getElementById(cfg.inputId); if (!el) return false;
      el.value = value; w.onManualEdit(key);
      if (value === '') await cycle(false);        // 清空=恢复自动：重载引擎，让它把自动值重新填回输入框
      else await cycleLight();
      return true;
    };
    CL.reload = () => cycle(false);
    cycle(true);
    timers.push(setInterval(() => { if (!doc.hidden) cycle(false); }, 10 * 60 * 1000));
    /* 每3分钟只读 prices.json（几十KB）：有新的15分钟价就更新盘中价，不重载评分引擎 */
    CL.refreshPrices = async function () {
      try {
        if (!D || !lastSide) return; const p = await jget('data/prices.json'); if (!p || (lastSide.prices && lastSide.prices.updatedAt === p.updatedAt)) return;
        lastSide.prices = p; const lp = CL.livePrices(lastSide.latest, p); D.live = lp.live; D.m15 = lp.m15; if (window.__cockpit && window.__cockpit.refreshed) window.__cockpit.refreshed();
      } catch (e) { /* 没有或读失败：保持原样 */ }
    };
    timers.push(setInterval(() => { if (!doc.hidden) CL.refreshPrices(); }, 3 * 60 * 1000));
    doc.addEventListener('visibilitychange', () => { if (!doc.hidden && D && Date.now() - D.snapshotMs > 10 * 60 * 1000) cycle(false); });
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = CL; else root.CockpitData = CL;
})(typeof window !== 'undefined' ? window : globalThis);
