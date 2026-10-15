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
  /* 价格序列接上「刚收盘的日线」：main_adj.json 来自生意社 + 夜里 23:05 才累积一次的文件，一天只更新一次；而新浪日线在收盘后不久就有当天收盘价。
   这里把 adj 之后新出现的、已收盘的日线（同一个合约，按两边同一天的收盘比折到调整价水平）接在后面，信号和浮盈当天收盘后就能更新。
   bars: [{d,c}]；sym: 这些日线属于哪个合约；nowMs: 现在。当天的K线只有过了 15:01 才算已收盘；比今天还晚的（夜盘占位）一律不接。 */
  /* 日线晚上才出：用 15:00 那根 15 分钟/小时线的收盘价当"临时收盘价"（日线出来后以日线为准） */
  CL.provDaily = function () {
    const m = {};
    for (const arr of arguments) (arr || []).forEach(b => { const dt = String((b && b.datetime) || ''); if (b && b.close != null && /\s15:00(:00)?$/.test(dt)) m[dt.slice(0, 10)] = +b.close; });
    return Object.keys(m).sort().map(d => ({ d, c: m[d] }));
  };
  CL.extendAdj = function (adj, bars, sym, nowMs) {
    if (!adj || !adj.d || !adj.d.length || !bars || !bars.length) return adj;
    const n0 = adj.d.length, lastD = adj.d[n0 - 1], kEnd = adj.k && adj.k[n0 - 1] ? String(adj.k[n0 - 1]).toLowerCase() : '';
    if (sym && kEnd && String(sym).toLowerCase() !== kEnd) return adj;   // 不是 adj 当前这个合约（换月了）就不接，免得价差混进来
    const bj = new Date(nowMs + 8 * 3600e3), today = bj.toISOString().slice(0, 10), mins = bj.getUTCHours() * 60 + bj.getUTCMinutes();
    const map = {}; bars.forEach(b => { const d = String(b.d || b.date || '').slice(0, 10), c = +(b.c != null ? b.c : b.close); if (d && c > 0) map[d] = c; });
    const base = map[lastD], r = base > 0 ? adj.c[n0 - 1] / base : 1, nd = [], nc = [];
    Object.keys(map).sort().forEach(d => { if (d > lastD && (d < today || (d === today && mins >= 15 * 60 + 1))) { nd.push(d); nc.push(map[d] * r); } });
    if (!nd.length) return adj;
    return Object.assign({}, adj, { d: adj.d.concat(nd), c: adj.c.concat(nc), k: adj.k ? adj.k.concat(nd.map(() => adj.k[n0 - 1])) : adj.k, extended: nd.length });
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
  /* 新浪 15 分钟线（浏览器直连，JSONP）：不用等 GitHub 定时任务；失败就静默回退到 prices.json */
  CL.parseSinaMin = function (arr) {
    if (!Array.isArray(arr)) return [];
    return arr.map(x => x && ({ datetime: String(x.d || '').slice(0, 19), open: +x.o, high: +x.h, low: +x.l, close: +x.c, volume: x.v == null ? null : +x.v, hold: x.p == null ? null : +x.p })).filter(b => b && b.datetime && b.close > 0);
  };
  /* 东方财富 15 分钟线（备用源，浏览器 JSONP 直连）：data.klines 每行 "时间,开,收,高,低,量,额"。注意开收顺序和新浪不同 */
  CL.parseEmKlines = function (o) {
    const k = o && o.data && Array.isArray(o.data.klines) ? o.data.klines : null; if (!k) return [];
    return k.map(r => { const f = String(r).split(','); if (f.length < 6) return null; return { datetime: (f[0].length === 16 ? f[0] + ':00' : f[0]).slice(0, 19), open: +f[1], close: +f[2], high: +f[3], low: +f[4], volume: +f[5], hold: null }; }).filter(b => b && b.datetime && isFinite(b.open) && b.close > 0 && b.high > 0 && b.low > 0);
  };
  CL.emUrl = function (sym, cb) { return 'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=114.' + encodeURIComponent(String(sym).toLowerCase()) + '&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57&klt=15&fqt=0&end=20500101&lmt=300&cb=' + cb; };
  CL.priceCheck = function (a, b, tol) {   // 两个源最新一根 15 分钟线的收盘价是否对得上：取两边共有的最新一根时间比较
    tol = tol == null ? 0.005 : tol; if (!a || !a.length || !b || !b.length) return { ok: null, text: '只有一个价格源可用，没法互相核对' };
    const mb = {}; b.forEach(x => { mb[x.datetime] = x; }); let hit = null; for (let i = a.length - 1; i >= 0; i--) if (mb[a[i].datetime]) { hit = [a[i], mb[a[i].datetime]]; break; }
    if (!hit) return { ok: null, text: '两个价格源没有同一时间的K线可比' };
    const d = Math.abs(hit[0].close / hit[1].close - 1); return { ok: d <= tol, diff: d, dt: hit[0].datetime, text: `新浪 ${hit[0].close} · 东方财富 ${hit[1].close}（${hit[0].datetime.slice(5, 16)}，差 ${(d * 100).toFixed(2)}%）` };
  };
  CL.mergeSina = function (p, sx) {   // sx: {sep|may|jan: {symbol, bars}}；比 prices.json 新的 15 分钟线并进去
    const PK = { sep: 'M09', may: 'M05', jan: 'M01' }, out = JSON.parse(JSON.stringify(p || { contracts: {} })); out.contracts = out.contracts || {}; let n = 0;
    for (const c of Object.keys(PK)) {
      const x = sx && sx[c]; if (!x || !x.bars || !x.bars.length) continue;
      const cur = out.contracts[PK[c]] || { symbol: x.symbol, bars: [], daily: [] }, old = (cur.bars || []).filter(b => b && b.datetime);
      if (cur.symbol && x.symbol && String(cur.symbol).toLowerCase() !== String(x.symbol).toLowerCase()) continue;
      const first = x.bars[0].datetime, lastOld = old.length ? old[old.length - 1].datetime : '';
      if (x.bars[x.bars.length - 1].datetime <= lastOld && old.length) continue;   // 没有更新的就不动
      cur.symbol = cur.symbol || x.symbol; cur.bars = old.filter(b => b.datetime < first).concat(x.bars); out.contracts[PK[c]] = cur; n++;
    }
    out._sina = n; return out;
  };
  /* 实时价条（v101.57）：新浪 1 分钟线最后一根的收盘价 = 最新成交价；默认每 3 秒取一次，失败逐级放慢 */
  CL.tickUrl = function (sym, cb) { return 'https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20' + cb + '=/InnerFuturesNewService.getFewMinLine?symbol=' + encodeURIComponent(String(sym).toUpperCase()) + '&type=1'; };
  /* 新浪逐笔报价(hq.sinajs.cn)：比1分钟线快得多。返回 var hq_str_nf_M2601="名称,时间HHMMSS,开,高,低,昨收,买价,卖价,最新价,结算,昨结,买量,卖量,持仓,成交量,...,日期"
     字段位置按新浪期货约定：[1]时间 [8]最新价 [13]持仓 [14]成交量；日期取字段里的 yyyy-mm-dd，没有就用北京时间今天 */
  CL.hqUrl = function (sym) { return 'https://hq.sinajs.cn/list=nf_' + encodeURIComponent(String(sym).toUpperCase()) + '&_=' + Date.now(); };
  CL.parseSinaHq = function (str, nowMs) {
    if (typeof str !== 'string' || str.length < 20) return null;
    const f = str.split(','); if (f.length < 15) return null;
    const c = parseFloat(f[8]), tm = String(f[1] || '').replace(/\D/g, ''); if (!(c > 0) || tm.length !== 6) return null;
    const hh = tm.slice(0, 2), mm = tm.slice(2, 4), ss = tm.slice(4); if (+hh > 23 || +mm > 59 || +ss > 59) return null;
    let d = null; for (let i = 15; i < f.length; i++) { if (/^\d{4}-\d{2}-\d{2}$/.test(f[i])) { d = f[i]; break; } }
    if (!d) { const b = new Date((nowMs || Date.now()) + 8 * 3600 * 1000), z = n => String(n).padStart(2, '0'); d = b.getUTCFullYear() + '-' + z(b.getUTCMonth() + 1) + '-' + z(b.getUTCDate()); }
    return { dt: d + ' ' + hh + ':' + mm + ':' + ss, c, v: parseFloat(f[14]) || 0, src: 'hq' };
  };
  CL.parseSinaTick = function (arr) { const b = CL.parseSinaMin(arr); if (!b.length) return null; const x = b[b.length - 1]; return { dt: x.datetime, c: x.close, v: x.volume, src: 'min' }; };
  CL.tickBase = function () { let v = 3000; try { const o = +(window.__TICK_MS || localStorage.getItem('cockpit-tick-ms')); if (o >= 500 && o <= 60000) v = o; } catch (_) {} return v; };   // 默认3秒；想调快/调慢：控制台 localStorage.setItem('cockpit-tick-ms','1500')
  CL.tickDelay = function (fails, base) { base = base || CL.tickBase(); return fails <= 0 ? base : fails < 3 ? Math.max(base * 2, 5000) : fails < 6 ? 15000 : 30000; };
  CL.tradingNow = function (nowMs) {   // 北京时间：日盘 09:00–15:10、夜盘 21:00–23:10（周日夜盘到周一凌晨不算：豆粕夜盘只到23:00）
    const b = new Date(nowMs + 8 * 3600e3), dow = b.getUTCDay(), m = b.getUTCHours() * 60 + b.getUTCMinutes();
    return (dow >= 1 && dow <= 5 && m >= 540 && m <= 15 * 60 + 10) || (dow >= 1 && dow <= 5 && m >= 21 * 60 && m <= 23 * 60 + 10);
  };
  /* 盘中价：prices.json(每15分钟) 和 latest.json 里的15分钟/小时线，谁新用谁；日线只到上一个收盘，信号用日线，盘中价只作参考 */
  CL.livePrices = function (L, prices) {
    L = L || {};
    const live = {}, m15 = {}, rawM15 = {}, rawH = {};   // 盘中：15分钟线优先、小时线兜底；日线只到上一个收盘，信号用日线，盘中价只作参考
    const HR = { sep: 'dceM09Hourly', may: 'dceM05Hourly', jan: 'dceM01Hourly' }, MR = { sep: 'dceM09Min15', may: 'dceM05Min15', jan: 'dceM01Min15' };
    const PK = { sep: 'M09', may: 'M05', jan: 'M01' }, PR = (prices && prices.contracts) || {};
    for (const c of KEYS) { try {
      const pb = ((PR[PK[c]] || {}).bars || []).filter(b => b && b.close != null), mb0 = ((L[MR[c]] || {}).bars || []).filter(b => b && b.close != null), mb = pb.length && (!mb0.length || String(pb[pb.length - 1].datetime) >= String(mb0[mb0.length - 1].datetime)) ? pb : mb0;
      const hb = ((L[HR[c]] || {}).bars || []).filter(b => b && b.close != null), lb = (mb.length ? mb : hb).slice(-1)[0];
      if (mb.length) m15[c] = mb.map(b => ({ d: String(b.datetime || '').slice(5, 16), o: b.open, h: b.high, l: b.low, c: b.close, v: b.volume, oi: b.hold }));
      rawM15[c] = ((L[MR[c]] || {}).bars || []); rawH[c] = hb;
      if (lb) live[c] = { dt: String(lb.datetime || '').slice(0, 16), c: +lb.close, src: mb.length ? '15分钟' : '小时' };
    } catch (_) { /* 没有盘中数据就不显示 */ } }
    return { live, m15, rawM15, rawH };
  };
  /* 把 D.adjBase 接上 K线/prices.json 里刚收盘的日线，结果放进 D.adj（每次从 adjBase 重算，可反复调用） */
  CL.extendFromSources = function (D, prices, now) {
    if (!D.adjBase) return;
    const PKd = { sep: 'M09', may: 'M05', jan: 'M01' }, PRd = (prices && prices.contracts) || {}; let out = D.adjBase;
    for (const c of ['sep', 'may', 'jan']) { try {
      const ct = D.contracts && D.contracts[c]; if (!ct || !ct.symbol) continue;
      const pc = PRd[PKd[c]] || {}, same = pc.symbol && String(pc.symbol).toLowerCase() === String(ct.symbol).toLowerCase(), extra = same ? (pc.daily || []).map(b => ({ d: b.date, c: b.close })) : [];
      const prov = CL.provDaily((D.rawM15 || {})[c], (D.rawH || {})[c], same ? pc.bars : null);
      const nx = CL.extendAdj(D.adjBase, prov.concat((ct.kline || []).map(b => ({ d: b.d, c: b.c })), extra), ct.symbol, now); if (nx !== D.adjBase) { out = nx; break; }
    } catch (_) { /* 接不上就用原来的 */ } }
    D.adj = out;
  };
  /* 把所有来源装成驾驶舱的 D。in: {state, latest, H, seasonal, histCsv, now, STATIC} */
  CL.assemble = function (inp) {
    const S = inp.state, L = inp.latest || {}, H = inp.H || {}, ST = inp.STATIC, now = inp.now;
    const D = { polarity: ST.polarity, ctx: ST.ctx, contracts: {} };
    { const lp = CL.livePrices(L, inp.prices); D.live = lp.live; D.m15 = lp.m15; D.rawM15 = lp.rawM15; D.rawH = lp.rawH; }
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
    D.adjBase = D.adj; CL.extendFromSources(D, inp.prices, now);
    D.sea = inp.seasonal || null;
    D.crush = CL.crushFrom(L);
    D.capitalCoverage = CL.coverageFrom(inp.report);
    return D;
  };
  /* 把 src 的内容就地灌进 dst（界面代码里持有 D 和 D.series 的引用，刷新时不能换对象） */
  CL.LIVE_KEYS = ['ticks', 'priceCheck', 'priceSrc', 'tickStat'];   // 浏览器自己维护的实时字段：整体重算时不能被清掉（否则实时价/价格源会每5分钟消失一次）
  CL.fill = function (dst, src) { for (const k of Object.keys(dst)) if (!(k in src) && !CL.LIVE_KEYS.includes(k)) delete dst[k]; for (const k of Object.keys(src)) dst[k] = src[k]; return dst; };

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
    timers.push(setInterval(() => { if (!doc.hidden) cycle(false); }, 5 * 60 * 1000));
    /* 每1分钟：读 prices.json（几十KB）+ 交易时段直连新浪15分钟线，有新价就更新盘中价和收盘价，不重载评分引擎 */
    const sinaOne = (sym) => new Promise(res => {
      try {
        const cb = '__sx' + Math.random().toString(36).slice(2), sc = doc.createElement('script'); let done = false;
        const fin = v => { if (done) return; done = true; clearTimeout(tm); try { delete window[cb]; } catch (_) { window[cb] = undefined; } try { sc.remove(); } catch (_) {} res(v); };
        const tm = setTimeout(() => fin(null), 8000);
        sc.onload = () => fin(CL.parseSinaMin(window[cb])); sc.onerror = () => fin(null);
        sc.src = 'https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20' + cb + '=/InnerFuturesNewService.getFewMinLine?symbol=' + encodeURIComponent(String(sym).toUpperCase()) + '&type=15';
        doc.head.appendChild(sc);
      } catch (_) { res(null); }
    });
    const emOne = (sym) => new Promise(res => {   // 东方财富备用源：JSONP，回调直接给对象
      try {
        const cb = '__em' + Math.random().toString(36).slice(2), sc = doc.createElement('script'); let done = false, tm = null;
        const fin = v => { if (done) return; done = true; clearTimeout(tm); try { delete window[cb]; } catch (_) { window[cb] = undefined; } try { sc.remove(); } catch (_) {} res(v); };
        tm = setTimeout(() => fin(null), 8000); window[cb] = o => fin(CL.parseEmKlines(o)); sc.onerror = () => fin(null);
        sc.src = CL.emUrl(sym, cb); doc.head.appendChild(sc);
      } catch (_) { res(null); }
    });
    let pcN = 0;
    CL.refreshPrices = async function () {
      try {
        if (!D || !lastSide) return;
        let p = null; try { p = await jget('data/prices.json'); } catch (_) { p = lastSide.prices || null; }
        if (!window.__NO_SINA && CL.tradingNow(Date.now())) {
          const sx = {}, ks = ['sep', 'may', 'jan'], used = {}, check = (pcN++ % 5 === 0);   // 每5分钟让两个源互相核对一次
          const rs = await Promise.all(ks.map(async c => { const sym = D.contracts && D.contracts[c] && D.contracts[c].symbol; if (!sym) return null;
            let r = await sinaOne(sym), em = null; used[c] = 'sina';
            if (!r || !r.length || check) { em = window.__NO_EM ? null : await emOne(sym); }
            if ((!r || !r.length) && em && em.length) { r = em; used[c] = 'em'; }
            else if (check && r && r.length && em && em.length) { const ck = CL.priceCheck(r, em); if (c === (window.__cockpit && window.__cockpit.S ? window.__cockpit.S.key : 'sep') || ck.ok === false) D.priceCheck = Object.assign(ck, { at: Date.now(), key: c }); }
            return r; }));
          ks.forEach((c, i) => { if (rs[i] && rs[i].length) sx[c] = { symbol: D.contracts[c].symbol, bars: rs[i] }; });
          D.priceSrc = { used, at: Date.now() };
          if (Object.keys(sx).length) p = CL.mergeSina(p || { contracts: {} }, sx);
        }
        if (!p) return;
        const key = (p.updatedAt || '') + '|' + ['M09', 'M05', 'M01'].map(k => { const b = ((p.contracts || {})[k] || {}).bars || []; return b.length ? b[b.length - 1].datetime + ':' + b[b.length - 1].close : ''; }).join(',');
        if (lastSide.pkey === key) return; lastSide.pkey = key;
        lastSide.prices = p; const lp = CL.livePrices(lastSide.latest, p); D.live = lp.live; D.m15 = lp.m15; D.rawM15 = lp.rawM15; D.rawH = lp.rawH; CL.extendFromSources(D, p, Date.now()); if (window.__cockpit && window.__cockpit.refreshed) window.__cockpit.refreshed();
      } catch (e) { /* 没有或读失败：保持原样 */ }
    };
    timers.push(setInterval(() => { if (!doc.hidden) CL.refreshPrices(); }, 60 * 1000));
    /* 实时价条：只在交易时段+页面可见时，每3秒取当前合约的最新价；失败逐级放慢（被新浪限流时自动退让） */
    const tickMin = (sym) => new Promise(res => {
      try {
        const cb = '__tk' + Math.random().toString(36).slice(2), sc = doc.createElement('script'); let done = false;
        const fin = v => { if (done) return; done = true; clearTimeout(tm); try { delete window[cb]; } catch (_) { window[cb] = undefined; } try { sc.remove(); } catch (_) {} res(v); };
        const tm = setTimeout(() => fin({ err: '超时(5秒没回)' }), 5000);
        sc.onload = () => { const t = CL.parseSinaTick(window[cb]); fin(t || { err: '新浪返回空数据' }); }; sc.onerror = () => fin({ err: '请求被拒绝/网络错误(可能被新浪限流)' });
        sc.src = CL.tickUrl(sym, cb); doc.head.appendChild(sc);
      } catch (_) { res({ err: '页面脚本异常' }); }
    });
    const tickHq = (sym) => new Promise(res => {   // 逐笔报价：脚本执行后全局变量 hq_str_nf_XXX 里就是报价串
      try {
        const vn = 'hq_str_nf_' + String(sym).toUpperCase(), sc = doc.createElement('script'); let done = false;
        const fin = v => { if (done) return; done = true; clearTimeout(tm); try { delete window[vn]; } catch (_) { window[vn] = undefined; } try { sc.remove(); } catch (_) {} res(v); };
        const tm = setTimeout(() => fin({ err: '逐笔报价超时(5秒没回)' }), 5000);
        sc.charset = 'gbk'; try { sc.referrerPolicy = 'no-referrer'; } catch (_) {}
        sc.onload = () => { const t = CL.parseSinaHq(window[vn]); fin(t || { err: '逐笔报价返回空/格式不符' }); }; sc.onerror = () => fin({ err: '逐笔报价被拒绝/网络错误' });
        sc.src = CL.hqUrl(sym); doc.head.appendChild(sc);
      } catch (_) { res({ err: '逐笔报价脚本异常' }); }
    });
    let hqBad = 0, hqSkipUntil = 0;   // 逐笔报价连续失败3次就停用5分钟，期间只用1分钟线，之后再试
    const tickOne = async (sym) => {
      if (!window.__NO_HQ && Date.now() >= hqSkipUntil) {
        const r = await tickHq(sym);
        if (r && !r.err) { hqBad = 0; return r; }
        if (++hqBad >= 3) { hqSkipUntil = Date.now() + 5 * 60000; hqBad = 0; }
        const m = await tickMin(sym); if (m && !m.err) m.hqErr = r && r.err; return m;
      }
      return tickMin(sym);
    };
    let tkFails = 0;
    CL.tickOnce = async function () {
      try {
        if (!D || doc.hidden || window.__NO_SINA) return null;
        const key = window.__cockpit && window.__cockpit.S ? window.__cockpit.S.key : 'sep', sym = D.contracts && D.contracts[key] && D.contracts[key].symbol; if (!sym) return null;
        // 不在交易时段：每个时段结束那一刻的最后成交价就是该时段的收盘价，保留下来（不清掉）；页面刚打开、手里没有时取一次，之后每分钟核对一次
        if (!CL.tradingNow(Date.now())) { const t = D.ticks && D.ticks[key]; if (t && Date.now() - t.at < 60000) return null; }
        const t0 = Date.now(), r = await tickOne(sym), st = D.tickStat = D.tickStat || { ok: 0, fail: 0, since: Date.now(), chg: [] };
        if (!r || r.err) { tkFails++; st.fail++; st.err = r && r.err || '未知'; st.errAt = Date.now(); st.delay = CL.tickDelay(tkFails); return null; }
        st.ok++; st.src = r.src; st.hqErr = r.hqErr || null; st.ms = Date.now() - t0; st.delay = CL.tickDelay(0); { const o = D.ticks && D.ticks[key]; if (!o || o.c !== r.c || o.dt !== r.dt) { st.chg.push(Date.now()); st.chg = st.chg.filter(x => Date.now() - x < 60000); } }
        tkFails = 0; D.ticks = D.ticks || {}; const old = D.ticks[key] || null;
        D.ticks[key] = { key, sym, c: r.c, dt: r.dt, at: Date.now(), dir: old ? (r.c > old.c ? 1 : r.c < old.c ? -1 : old.dir || 0) : 0, flash: !!(old && old.c !== r.c) };
        if (window.__cockpit && window.__cockpit.tickPaint) window.__cockpit.tickPaint();
        return r;
      } catch (_) { tkFails++; return null; }
    };
    (function tickLoop() { const t0 = Date.now(); CL.tickOnce().finally(() => { setTimeout(tickLoop, CL.tradingNow(Date.now()) ? Math.max(0, CL.tickDelay(tkFails) - (tkFails ? 0 : Date.now() - t0)) : (tkFails ? 30000 : 15000)); }); })();   // 正常时按“发出请求到下一次发出”间隔3秒（默认）（请求耗时算在里面）

    doc.addEventListener('visibilitychange', () => { if (!doc.hidden && D && Date.now() - D.snapshotMs > 5 * 60 * 1000) cycle(false); else if (!doc.hidden && D) CL.refreshPrices(); });
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = CL; else root.CockpitData = CL;
})(typeof window !== 'undefined' ? window : globalThis);
