/* 豆粕驾驶舱：纯计算模块(浏览器和Node通用)。所有"趋势/状态/布局/主题"的判断都在这里，界面只负责画。
 * 每个函数都有对应的测试(tests_logic.js)；ADX用TA-Lib做外部参考对拍。 */
(function (root) {
  'use strict';
  const L = {};
  const DAY = 86400000;

  /* ---------- 常量(与正式页面一致或来自参考文档，暂定未回测的都标了) ---------- */
  L.K = {
    DIR: 0.22,            // 基本面净倾向阈值，与正式页面 DIRECTION_RATIO 一致
    GS_HIGH: 120000,      // 高盛净多≥12万手=高位(参考文档，暂定，未回测)
    GS_RETREAT: -20000,   // 高盛单日净多变化≤-2万手=撤退预警(参考文档，暂定)
    CFTC_PCT: 90,         // CFTC近156周分位≥90=拥挤(参考文档，暂定)
    ADX_N: 14, ADX_TREND: 25, ADX_RANGE: 20,   // Wilder的通用约定：≥25趋势，<20震荡(教科书值，没有针对豆粕标定)
    DONCHIAN: 20,         // 突破判断：收盘价是否越过前20根的最高/最低
    DI_GAP: 5,            // +DI与−DI至少差5点才算方向清楚(真实1月合约 ADX=28.7 但+DI只比−DI高1.4，方向不可信——用真实数据发现的)
    FLAT_EPS: 0.004       // 趋势"持平"阈值：变化小于该序列典型水平的0.4%
  };

  /* ---------- 日期 ---------- */
  // 'YYYY-MM-DD' → UTC毫秒；'YYYY-MM' → 当月15日；'YYYY' → 当年7月1日(年度数据)
  L.parseDate = function (d) {
    const s = String(d);
    let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    if (m) return Date.UTC(+m[1], +m[2] - 1, +m[3]);
    m = /^(\d{4})-(\d{2})$/.exec(s);
    if (m) return Date.UTC(+m[1], +m[2] - 1, 15);
    m = /^(\d{4})$/.exec(s);
    if (m) return Date.UTC(+m[1], 6, 1);
    return NaN;
  };

  const median = a => { const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  L.median = median;

  /* ---------- 趋势：按日历时间(不是按第几个点)，缺周/缺日也不会算错 ---------- */
  // 频率→三个对比跨度(日历天)与标签。短/中/长=约1周/1月/1季；月度数据最短1月，年度数据按年。
  L.SPECS = {
    daily:   { spans: [7, 30, 91],       labels: ['1周', '1月', '3月'],   tol: [3, 8, 14] },
    weekly:  { spans: [7, 28, 91],       labels: ['1周', '4周', '13周'],  tol: [3, 6, 14] },
    monthly: { spans: [30, 91, 182],     labels: ['1月', '3月', '6月'],   tol: [16, 20, 25] },
    yearly:  { spans: [365, 1095, 1825], labels: ['1年', '3年', '5年'],   tol: [90, 120, 150] }
  };
  L.specFor = function (freq) {
    if (freq === 'seasonal-daily') return L.SPECS.daily;
    if (freq === 'irregular' || freq === 'quarterly') return L.SPECS.monthly;
    return L.SPECS[freq] || L.SPECS.daily;
  };

  // 找到最接近 target(ms) 且在容差内的点；没有就返回 null
  L.pointNear = function (pts, target, tolDays) {
    let best = null, bd = Infinity;
    for (const p of pts) {
      const t = L.parseDate(p.d); if (isNaN(t)) continue;
      const dd = Math.abs(t - target);
      if (dd < bd) { bd = dd; best = p; }
    }
    return best && bd <= tolDays * DAY ? best : null;
  };

  // 相邻点间隔超过 maxGapDays 就视为新的一段；返回最后一段(季节性序列只在建议窗口内有数据，跨年的点不能连起来看趋势)
  L.currentRun = function (pts, maxGapDays) {
    maxGapDays = maxGapDays || 10;
    if (!pts || !pts.length) return [];
    let start = pts.length - 1;
    while (start > 0 && (L.parseDate(pts[start].d) - L.parseDate(pts[start - 1].d)) <= maxGapDays * DAY) start--;
    return pts.slice(start);
  };

  L.movingAvg = function (pts, k) {
    return pts.map((p, i) => i < k - 1 ? null : { d: p.d, v: pts.slice(i - k + 1, i + 1).reduce((a, x) => a + x.v, 0) / k }).filter(Boolean);
  };

  // 单个跨度的变化：返回 {from,to,change,pct,dir} 或 null
  L.spanChange = function (pts, spanDays, tolDays, scale) {
    if (!pts || pts.length < 2) return null;
    const last = pts[pts.length - 1], tl = L.parseDate(last.d);
    const ref = L.pointNear(pts.slice(0, -1), tl - spanDays * DAY, tolDays);
    if (!ref) return null;
    const change = last.v - ref.v;
    const eps = L.K.FLAT_EPS * (scale || Math.abs(ref.v) || 1);
    const dir = Math.abs(change) < eps ? 0 : change > 0 ? 1 : -1;
    const pct = Math.abs(ref.v) > 1e-9 ? change / Math.abs(ref.v) : null;
    return { from: ref, to: last, change, pct, dir };
  };

  // 三个周期的趋势。opts: {pol(数值升高对多空的影响 +1/-1/0), freq}
  L.trend = function (pts, opts) {
    opts = opts || {};
    const spec = L.specFor(opts.freq);
    let data = pts || [];
    if (opts.freq === 'seasonal-daily') data = L.currentRun(data, 10);
    const recent = data.slice(-60).map(p => Math.abs(p.v));
    const scale = recent.length ? median(recent) : 1;
    const chips = spec.spans.map((sp, i) => {
      const c = L.spanChange(data, sp, spec.tol[i], scale);
      return { label: spec.labels[i], span: sp, ...(c ? c : { from: null, to: null, change: null, pct: null, dir: null }), ok: !!c };
    });
    const pol = opts.pol == null ? 0 : opts.pol;
    chips.forEach(c => { c.meaning = (!c.ok || c.dir === 0 || pol === 0) ? 0 : c.dir * pol; });   // +1偏多(红) -1偏空(绿) 0中性
    const dirs = chips.filter(c => c.ok).map(c => c.dir);
    let badge = null;
    if (dirs.length >= 2 && dirs.every(d => d === 1)) badge = 'up';
    else if (dirs.length >= 2 && dirs.every(d => d === -1)) badge = 'down';
    else if (chips[0].ok && chips[1].ok && chips[2].ok && chips[1].dir === chips[2].dir && chips[1].dir !== 0 && chips[0].dir === -chips[1].dir) badge = chips[1].dir === 1 ? 'pullback' : 'rebound';
    return { chips, badge, n: data.length, spec, last: data.length ? data[data.length - 1] : null };
  };

  /* ---------- ADX(Wilder)，实现与TA-Lib一致 ---------- */
  L.adx = function (bars, n) {
    n = n || L.K.ADX_N;
    const N = bars.length;
    if (N < 2 * n + 1) return null;
    const tr = [], pdm = [], mdm = [];
    for (let i = 1; i < N; i++) {
      const up = bars[i].h - bars[i - 1].h, dn = bars[i - 1].l - bars[i].l;
      pdm.push(up > dn && up > 0 ? up : 0);
      mdm.push(dn > up && dn > 0 ? dn : 0);
      tr.push(Math.max(bars[i].h - bars[i].l, Math.abs(bars[i].h - bars[i - 1].c), Math.abs(bars[i].l - bars[i - 1].c)));
    }
    // 与TA-Lib一致：种子只累计前 n-1 个差分，之后每一个差分(含第n个)都做一次 Wilder 平滑 s = s - s/n + x。
    // (上一版多累计了1个，+DI起点差0.12、ADX序列最大差0.86，被TA-Lib对拍测试发现；改后最大差1e-14)
    let sTR = 0, sP = 0, sM = 0;
    for (let i = 0; i < n - 1; i++) { sTR += tr[i]; sP += pdm[i]; sM += mdm[i]; }
    const dx = [], pdi = [], mdi = [];
    for (let i = n - 1; i < tr.length; i++) {
      sTR = sTR - sTR / n + tr[i]; sP = sP - sP / n + pdm[i]; sM = sM - sM / n + mdm[i];
      const p = sTR ? 100 * sP / sTR : 0, m = sTR ? 100 * sM / sTR : 0;
      pdi.push(p); mdi.push(m); dx.push(p + m ? 100 * Math.abs(p - m) / (p + m) : 0);
    }
    let a = 0;
    for (let i = 0; i < n; i++) a += dx[i];
    a /= n;
    const series = [a];
    for (let i = n; i < dx.length; i++) { a = (a * (n - 1) + dx[i]) / n; series.push(a); }
    return { adx: a, pdi: pdi[pdi.length - 1], mdi: mdi[mdi.length - 1], series, pdiSeries: pdi, mdiSeries: mdi };
  };

  /* ---------- 资金面状态：与后端 fetch_data._capital_state 逐字一致(见 tests_logic.js 的对拍) ---------- */
  L.capitalState = function (gsNet, gsChange, cftcPct) {
    const K = L.K;
    if (gsNet == null) gsChange = null;      // 高盛不在榜时不存在"当日变化"(与后端 _capital_state 一致：gs 为空则 change 也为空)——对拍发现JS端漏了
    const gsHigh = gsNet != null && gsNet >= K.GS_HIGH, crowded = cftcPct != null && cftcPct >= K.CFTC_PCT;
    const fmt = n => Math.abs(Math.round(n)).toLocaleString('en-US');
    if (gsChange != null && gsChange <= K.GS_RETREAT) return { code: 'retreat', level: 'yellow', label: '外资撤退预警：高盛当日减仓' + fmt(gsChange) + '手' };
    if (gsHigh && crowded) return { code: 'crowded', level: 'red', label: '外资多头拥挤' };
    if (gsHigh) return { code: 'elevated', level: 'yellow', label: '外资多头高位(高盛净多头在高位，CFTC未到拥挤)' };
    if (crowded) return { code: 'elevated', level: 'yellow', label: '外资多头高位(依据：CFTC管理基金净多到顶；高盛未进榜或不在高位)' };
    if (gsNet == null && cftcPct == null) return { code: 'unknown', level: 'gray', label: '外资状态：数据不足' };
    if (gsNet == null || cftcPct == null) return { code: 'unknown', level: 'gray', label: "外资状态：数据不足(高盛或CFTC缺一项，不下'中性'结论)" };
    return { code: 'neutral', level: 'green', label: '外资中性(高盛净多头不在高位，CFTC不拥挤)' };
  };

  // CFTC周序列统计：口径与来源 fetch_cftc_managed_money 一致(分位=历史里<=当前的占比，含并列；连续周数=从最新往回同向变化的周数)
  L.cftcStats = function (pts) {
    if (!pts || pts.length < 2) return null;
    const v = pts.map(p => p.v), last = v[v.length - 1];
    const pct = Math.round(v.filter(x => x <= last).length / v.length * 1000) / 10;
    let streak = 0, dir = null;
    for (let i = v.length - 1; i > 0; i--) {
      const d = v[i] - v[i - 1], s = d > 0 ? 'up' : d < 0 ? 'down' : null;
      if (s === null) break;
      if (dir === null) { dir = s; streak = 1; } else if (s === dir) streak++; else break;
    }
    return { net: last, change: last - v[v.length - 2], streak, dir, percentile: pct, weeks: v.length, date: pts[pts.length - 1].d };
  };

  /* ---------- 市场状态：震荡 / 趋势 / 资金市迹象 / 方向待定 ---------- */
  // bars: [{h,l,c,oi}]；ctx: {capitalCode, fundRatio}
  // 市场状态分两步：①从K线算指标(ADX、突破、均线、持仓变化) ②classify按指标和资金/基本面判定。拆开是为了测试能直接给定指标逐道验证每个防线。
  L.indicators = function (bars) {
    const K = L.K, N = bars.length;
    const a = L.adx(bars, K.ADX_N);
    if (!a || N < K.DONCHIAN + 2) return null;
    const last = bars[N - 1].c;
    const prior = bars.slice(N - 1 - K.DONCHIAN, N - 1);                   // 前20根，不含今天
    const hi = Math.max(...prior.map(x => x.h)), lo = Math.min(...prior.map(x => x.l));
    const ma20 = bars.slice(N - 20).reduce((x, y) => x + y.c, 0) / 20;
    const oi5 = N > 5 && bars[N - 6].oi ? bars[N - 1].oi / bars[N - 6].oi - 1 : null;
    return { adx: a.adx, pdi: a.pdi, mdi: a.mdi, last, hi, lo, ma20, oi5, breakout: last > hi ? 'up' : last < lo ? 'down' : null, raw: a };
  };

  L.classify = function (ind, ctx) {
    ctx = ctx || {};
    const K = L.K;
    if (!ind) return { code: 'na', label: '数据不足', reason: 'K线不够，判断不了震荡还是趋势', conds: [], met: 0, of: 0 };
    const { adx, pdi, mdi, last, hi, lo, ma20, oi5, breakout } = ind;
    const strong = adx >= K.ADX_TREND, weak = adx < K.ADX_RANGE;
    // 趋势方向要同时满足：①+DI与−DI差距够大(否则方向不可信) ②收盘价在20日均线的同一侧(价格自己也认这个方向)。ADX只回答"有没有趋势"，不回答"往哪边"。
    const gap = Math.abs(pdi - mdi), diDir = pdi > mdi ? 'up' : 'down';
    const sideOk = diDir === 'up' ? last > ma20 : last < ma20;
    const clear = gap >= K.DI_GAP && sideOk;
    const dir = diDir;
    const crowded = ctx.capitalCode === 'crowded';
    const priceUp = (strong && clear && dir === 'up') || breakout === 'up';       // 资金市要求价格真的在涨：突破前高，或强趋势且方向清楚地向上
    const fundNotBull = ctx.fundRatio == null ? null : ctx.fundRatio < K.DIR;
    const conds = [
      { k: 'adx', text: '趋势强度 ADX ' + adx.toFixed(1) + '（≥' + K.ADX_TREND + ' 算趋势，<' + K.ADX_RANGE + ' 算震荡）', met: strong },
      { k: 'dir', text: '上升力量 +DI ' + pdi.toFixed(1) + ' / 下降力量 −DI ' + mdi.toFixed(1) + (gap < K.DI_GAP ? '（差距不足 ' + K.DI_GAP + '，方向不清）' : ''), met: strong ? clear : null },
      { k: 'ma', text: '收盘价 ' + last + ' 在20日均线 ' + ma20.toFixed(0) + (last > ma20 ? ' 上方' : ' 下方'), met: null },
      { k: 'brk', text: '收盘价 ' + last + (breakout === 'up' ? ' 突破前' + K.DONCHIAN + '日最高 ' + hi : breakout === 'down' ? ' 跌破前' + K.DONCHIAN + '日最低 ' + lo : ' 在前' + K.DONCHIAN + '日区间 ' + lo + '~' + hi + ' 之内'), met: breakout !== null },
      { k: 'oi', text: oi5 == null ? '持仓量变化不可用' : '近5日持仓量 ' + (oi5 >= 0 ? '+' : '−') + Math.abs(oi5 * 100).toFixed(1) + '%', met: oi5 == null ? null : oi5 > 0 },
      { k: 'cap', text: '外资多头拥挤', met: crowded },
      { k: 'fund', text: ctx.fundRatio == null ? '基本面净倾向不可用' : '基本面没有明显偏多（净倾向 ' + (ctx.fundRatio * 100).toFixed(0) + '%，偏多线 +' + K.DIR * 100 + '%）', met: fundNotBull }
    ];
    let code, label, reason;
    if (crowded && priceUp && fundNotBull === true) {
      code = 'capital'; label = '资金市迹象'; reason = '外资拥挤，价格在涨，基本面没跟上';
    } else if (strong && !clear) {
      code = 'unclear'; label = '方向待定'; reason = '趋势强度够，但上升和下降的力量差不多，方向不清';
    } else if (strong) {
      code = 'trend_' + dir; label = dir === 'up' ? '趋势市 · 上行' : '趋势市 · 下行';
      reason = dir === 'up' ? '价格持续上行' + (oi5 != null && oi5 > 0 ? '，新资金在进场' : '') : '价格持续下行' + (oi5 != null && oi5 < 0 ? '，但持仓在减少，空头也没有加码' : oi5 != null && oi5 > 0 ? '，新空头在进场' : '');
    } else if (weak) {
      code = 'range'; label = '震荡市'; reason = '价格来回波动，没有明显方向';
    } else {
      code = 'unclear'; label = '方向待定'; reason = '介于震荡和趋势之间，趋势在形成或在衰减';
    }
    const used = conds.filter(c => c.met !== null);
    return { code, label, reason, conds, met: used.filter(c => c.met).length, of: used.length, adx: { adx, pdi, mdi }, breakout, hi, lo, oi5, crowded, priceUp, fundNotBull, ma20, clear };
  };

  L.regime = function (bars, ctx) { return L.classify(L.indicators(bars), ctx); };

  /* ---------- 布局规划：保证趋势墙放得下，放不下的折进"更多"，不靠滚动条兜底 ---------- */
  L.GRID_ASPECT = 1.5;      // 格子理想宽高比(宽:高)
  L.GRID_MIN = { minW: 150, minH: 134, maxCols: 6 };      // 实测值，测试和实现共用这一份
  L.planGrid = function (W, H, n, o) {
    // minH=134：真浏览器实测一个格子的最小内容高度≈128px(名称20+数值31+曲线22+周期31+上下内边距18+行距6)，留余量。minW=150：数值+单位+三个周期不换行所需宽度。
    o = Object.assign({}, L.GRID_MIN, o || {});
    const maxC = Math.max(1, Math.min(o.maxCols, Math.floor(W / o.minW)));
    let best = null;
    for (let c = maxC; c >= 1; c--) {
      const rows = Math.ceil(n / c);
      if (rows * o.minH <= H) {      // rows>=1，所以这个条件已蕴含 H>=minH，不需要再写一遍(变异检查发现的冗余条件)
        // 打分 = 面积 × 宽高比惩罚。只比面积会偏爱"少浪费一格"的窄长版式(13格在2560×1440上选出2列×7行，每格又宽又扁)；
        // 目标宽高比约1.5:1，偏离越远惩罚越大。
        const tw = W / c, th = H / rows, area = tw * th, lr = Math.log(tw / th / L.GRID_ASPECT);
        const score = area * Math.exp(-lr * lr);
        if (!best || score > best.score + 1e-9) best = { cols: c, rows, area, score };
      }
    }
    if (best) return { cols: best.cols, rows: best.rows, show: n, more: 0, tileW: W / best.cols, tileH: H / best.rows };
    const cols = maxC, rows = Math.max(1, Math.floor(H / o.minH));
    const cap = (H >= o.minH ? cols * rows : 0), show = Math.max(0, Math.min(n, cap - 1));      // 高度连一行都放不下：一块都不显示，全部折进"更多"
    return { cols, rows, show, more: n - show, tileW: W / cols, tileH: H / rows };
  };

  /* ---------- 趋势墙分组：有趋势的各占一格，历史累积中的合并成一格 ---------- */
  // 趋势至少要3个点才画得出来(1~2个点连一条线都谈不上)。把"历史累积中"的指标合并成一个汇总格，
  // 不让它们各占一整格的面积(真实数据里17个指标有9个只有1~8个点)；顺序保持原顺序，不丢任何指标。
  L.groupTiles = function (tiles, minPts) {
    if (minPts == null) throw new Error('groupTiles 必须显式传入 minPts(阈值只在调用处定义一次，没有默认值可以悄悄偏离)');
    const main = [], pending = [];
    for (const t of tiles || []) ((t.tr && t.tr.n >= minPts) ? main : pending).push(t);
    return { main, pending };
  };
  L.gridCount = function (g) { return g.main.length + (g.pending.length ? 1 : 0); };

  /* ---------- 部署自检清单 ---------- */
  // 把"部署后需要你手工核对的事"变成页面里的一页：每项由数据判定。读不到服务器文件/真机排版的项明说"查不了"，不假装通过。
  // status: ok 通过 / todo 需要你做(必须带action) / wait 在累积中，不是失败 / note 留意 / unknown 这里查不了
  L.selfCheck = function (o) {
    const n = k => { const s = o.series && o.series[k]; return !s ? 0 : (s.nTotal != null ? s.nTotal : (s.pts ? s.pts.length : 0)); }, items = [];      // nTotal=文件里的真实点数(页面里为了瘦身只带了最近一段)
    const cf = n('cftc');
    items.push({ key: 'cftc156', title: 'CFTC 历史已回填', status: cf >= 100 ? 'ok' : 'todo', detail: 'cftc_mm_net 现有 ' + cf + ' 个点（来源一次返回约 156 周）', action: cf >= 100 ? '' : '部署最新版后等下一次自动更新；若仍只有1个点，说明真实抓取没带回明细，把 data/history/cftc_mm_net.json 发我' });
    const bf = ['crush', 'arrival', 'import'].map(k => [k, n(k)]), lowBf = bf.filter(x => x[1] < 8);
    items.push({ key: 'backfill', title: '开机率、到港预报、进口量的历史回填', status: lowBf.length ? 'todo' : 'ok', detail: bf.map(x => x[0] + ' ' + x[1] + '点').join('，'), action: lowBf.length ? '在 Actions → 回填历史数据，only 填 soy_import,arrival,crush_rate，只点一次；跑完把 data/history/_backfill_report.json 发我' : '' });
    const caps = ['gs', 'zl'].map(k => n(k)), maxCap = Math.max(...caps);
    items.push({ key: 'capital', title: '龙虎榜席位历史在累积', status: maxCap >= 8 ? 'ok' : 'wait', detail: '高盛、中粮各 ' + caps.join('、') + ' 个点。9月的21个交易日已用你给的大商所文件回填（高盛/瑞银是下限估计），之后每个交易日应加 1', action: '' });
    items.push({ key: 'hist-field', title: 'latest.json 里没有留下 CFTC 的 156 周明细', status: o.cftcHasHistoryField ? 'todo' : 'ok', detail: o.cftcHasHistoryField ? '最新的 latest.json 里 cftcManagedMoney 仍带 history 字段（每次多约 12KB）' : '已确认没有 history 字段', action: o.cftcHasHistoryField ? '确认已部署 v101，它会在记录后删掉这个字段' : '' });
    items.push({ key: 'scoring', title: '评分规则版本', status: o.scoring === 'v100' ? 'ok' : 'todo', detail: '当前 ' + (o.scoring || '未知') + '（期望 v100：现货基差按当前合约分位 + 供需各算净倾向再50/50合成）', action: o.scoring === 'v100' ? '' : '推送最新版后再看' });
    let sync = { status: 'unknown', detail: '没有同步时间' };
    if (o.now != null && o.latestDate != null) { const days = Math.floor((o.now - o.latestDate) / 86400000); sync = { status: days >= 3 ? 'note' : 'ok', detail: 'latest.json 距今 ' + days + ' 天' + (days >= 3 ? '（休市期间这是正常的；交易日里超过 2 天才需要查看门狗）' : '') }; }
    const pn = n('poultry'), hg = n('hog'), bs = o.basisSame || {};
    items.push({ key: 'poultry-ndrc', title: '肉鸡预期盈利（发改委×卓创）历史', status: pn >= 50 ? 'ok' : pn >= 3 ? 'wait' : 'todo', detail: 'poultry_ndrc 现有 ' + pn + ' 个周（2024-06 起）；发改委缺失/过期时 Mysteel 白羽肉鸡养殖利润顶替同一票位，票权×0.5', action: pn >= 3 ? '' : '在 Actions → 回填历史数据，only 填 poultry_ndrc' });
    items.push({ key: 'hog-ratio', title: '猪粮比历史', status: hg >= 100 ? 'ok' : hg >= 3 ? 'wait' : 'todo', detail: 'hog_ratio 现有 ' + hg + ' 个点', action: hg >= 3 ? '' : '在 Actions → 回填历史数据，only 填 hog_ratio' });
    items.push({ key: 'basis-same', title: '现货基差：当前合约内的样本', status: bs.n >= bs.min ? 'ok' : 'wait', detail: '当前主力 ' + String(bs.contract || '—').toUpperCase() + ' 已有 ' + (bs.n == null ? '—' : bs.n) + ' 个交易日（≥' + (bs.min || 20) + ' 才计分；换月后约一个月内这一票会缺席，这是有意的）', action: '' });
    items.push({ key: 'sync', title: '数据同步', ...sync, action: '' });
    items.push({ key: 'watchdog', title: '同步看门狗最近一次运行', status: 'unknown', detail: '需要读 GitHub 的工作流状态，这个页面查不了', action: '' });
    items.push({ key: 'device', title: '真机排版（手机、电脑、深浅色）', status: 'unknown', detail: '我在 Chromium 里实测过七个电脑尺寸和三个手机尺寸，但没有在你的真实设备上看过', action: '' });
    return items;
  };

  /* ---------- 趋势墙分块：供给 / 需求 / 结构与资金，各占一行(或几行) ---------- */
  L.BLOCKS = [{ key: 'supply', name: '供给', groups: ['供给'] }, { key: 'demand', name: '需求', groups: ['需求'] }, { key: 'struct', name: '结构与资金', groups: ['结构', '资金'] }];
  // tiles: 带 g(供给/需求/结构/资金) 和 tr.n 的格子。返回[{key,name,trending:[...],pending:[...]}]，空块不返回，顺序固定，不认识的分组并入最后一块(不丢)。
  L.groupByBlock = function (tiles, minPts) {
    minPts = minPts == null ? 3 : minPts;
    const out = L.BLOCKS.map(b => ({ key: b.key, name: b.name, trending: [], pending: [] }));
    for (const t of tiles || []) {
      let k = L.BLOCKS.findIndex(b => b.groups.includes(t.g));
      if (k < 0) k = out.length - 1;
      ((t.tr && t.tr.n >= minPts) ? out[k].trending : out[k].pending).push(t);
    }
    return out.filter(b => b.trending.length + b.pending.length > 0);
  };
  // 一行里 cells 个格子排 c 列：最后一个格子可以撑满该行剩余的列，返回它能跨几列(含自己)
  L.lastSpan = function (cells, c) { return cells <= 0 ? 0 : c - ((cells - 1) % c); };

  L.GRID_MIN.maxColsBlocks = 8;      // 块布局的最大列数(供给7格可以排一行)
  /* planBlocks(W,H,blocks)：blocks=[{key,trending:数量,pending:数量}]。
   * 规则：①每个可见块至少一行；②块里"趋势格+(有累积中的指标则1个汇总格)"放得下就全显示；③放不下：优先级最低(列表末尾)的趋势格并进这个块自己的汇总格，
   *      汇总格里仍显示名称/最新值/三期箭头；④连每块一行都放不下：最后几块整块并进前一个可见块的汇总格(dropped+mergeInto)；⑤不靠滚动条。
   * 在所有列数方案里：优先"全部显示"，其次"显示的趋势格最多"，再按 面积×宽高比惩罚 打分。 */
  L.planBlocks = function (W, H, blocks, o) {
    o = Object.assign({ rail: 22 }, L.GRID_MIN, o || {});
    const usable = Math.max(0, W - o.rail), R = Math.floor(H / o.minH);
    const live = blocks.map((b, i) => ({ i, key: b.key, tr: b.trending | 0, pe: b.pending | 0 })).filter(b => b.tr + b.pe > 0);
    if (R < 1 || !live.length) return { empty: true, cols: 1, rowsTotal: 0, blocks: blocks.map(b => ({ key: b.key, rows: 0, showTrend: 0, folded: 0, summary: false, dropped: true, mergeInto: null })), full: false, tileW: usable, tileH: H };
    const maxC = Math.max(1, Math.min(o.maxColsBlocks, Math.floor(usable / o.minW)));
    let best = null;
    for (let c = maxC; c >= 1; c--) {
      const need = b => b.tr + (b.pe > 0 ? 1 : 0);
      const fullRows = live.map(b => Math.ceil(need(b) / c)), Tfull = fullRows.reduce((a, b) => a + b, 0);
      let rows, vis, full;
      if (Tfull <= R) { rows = fullRows.slice(); vis = live.length; full = true; }
      else {
        full = false; vis = Math.min(R, live.length); rows = live.map((b, k) => k < vis ? 1 : 0);
        const eff = k => { let tr = live[k].tr, pe = live[k].pe; if (k === vis - 1) for (let d = vis; d < live.length; d++) { tr += live[d].tr; pe += live[d].pe; } return { tr, pe }; };
        let spare = R - vis;
        while (spare > 0) {
          let pick = -1, gap = 0;
          for (let k = 0; k < vis; k++) { const e = eff(k), g = e.tr + (e.pe > 0 ? 1 : 0) - c * rows[k]; if (g > gap) { gap = g; pick = k; } }
          if (pick < 0) break;
          rows[pick]++; spare--;
        }
      }
      const T = rows.reduce((a, b) => a + b, 0);
      const outBlocks = blocks.map(b => ({ key: b.key, rows: 0, showTrend: 0, folded: 0, summary: false, dropped: false, mergeInto: null }));
      let shown = 0;
      live.forEach((b, k) => {
        const ob = outBlocks[b.i];
        if (k >= vis) { ob.dropped = true; ob.mergeInto = live[vis - 1].i; return; }
        let tr = b.tr, pe = b.pe;
        if (k === vis - 1) for (let d = vis; d < live.length; d++) { tr += live[d].tr; pe += live[d].pe; }
        const cap = c * rows[k];
        let st, sum;
        if (tr + (pe > 0 ? 1 : 0) <= cap) { st = tr; sum = pe > 0; } else { st = Math.max(0, cap - 1); sum = true; }
        ob.rows = rows[k]; ob.showTrend = st; ob.folded = tr - st; ob.summary = sum; shown += st;
      });
      blocks.forEach((b, i) => { if (!live.some(x => x.i === i)) { outBlocks[i].dropped = true; } });
      const tw = usable / c, th = H / T, area = tw * th, lr = Math.log(tw / th / L.GRID_ASPECT), score = area * Math.exp(-lr * lr);
      const cand = { cols: c, rowsTotal: T, blocks: outBlocks, full, shown, score, tileW: tw, tileH: th, empty: false };
      // 比较顺序：①全部显示优先 ②总行数少优先(用户要的是"每块各占一行"，所以行数最少=每块恰好一行；只比"面积×宽高比"会选出4列、供给被迫排两行的方案——测试发现) ③显示的趋势格多 ④面积×宽高比
      const better = !best || (cand.full !== best.full ? cand.full : (cand.full && cand.rowsTotal !== best.rowsTotal) ? cand.rowsTotal < best.rowsTotal : cand.shown !== best.shown ? cand.shown > best.shown : cand.score > best.score + 1e-9);
      if (better) best = cand;
    }
    return best;
  };

  /* ---------- 汇总格装不下时不默默裁掉 ---------- */
  // 汇总格里每个指标一行：有趋势的(两行：名称+数值、三期箭头)约34px，累积中的(一行)约17px；格子的标题占约36px；"还有N项"提示占约17px。
  // 按高度算最多放几行：趋势行排前面(信息量大)，放不下的计入 hidden，并留出提示那一行。返回 {shown, hidden, usedHeight}。
  L.SUM_ROW = { trend: 34, pending: 17, title: 36, note: 17 };
  L.fitSummary = function (items, cellH) {
    const R = L.SUM_ROW, avail = cellH - R.title;
    const sorted = (items || []).slice().sort((a, b) => ((b.tr && b.tr.n >= 3) ? 1 : 0) - ((a.tr && a.tr.n >= 3) ? 1 : 0));
    const hgt = t => (t.tr && t.tr.n >= 3) ? R.trend : R.pending;
    let used = 0; const shown = [];
    for (let i = 0; i < sorted.length; i++) {
      const h = hgt(sorted[i]), remain = sorted.length - i - 1;
      const need = used + h + (remain > 0 ? 0 : 0);
      if (need > avail) break;
      shown.push(sorted[i]); used = need;
    }
    let hidden = sorted.length - shown.length;
    if (hidden > 0) {      // 要写"还有N项"：给提示留一行，必要时再收回最后一个已放的行
      while (shown.length && used + R.note > avail) { used -= hgt(shown.pop()); hidden++; }
      used += R.note;
      if (used > avail) { used = 0; }      // 连提示都放不下：什么都不显示
    }
    return { shown, hidden, usedHeight: used };
  };

  /* ---------- 日夜主题：自动按本地时间，也可手动 ---------- */
  L.themeFor = function (date, pref) {
    if (pref === 'day' || pref === 'night') return pref;
    const m = date.getHours() * 60 + date.getMinutes();
    return m >= 6 * 60 + 30 && m < 18 * 60 + 30 ? 'day' : 'night';
  };

  /* ---------- 序列走势的一句话(具体、可核对) ---------- */
  // 输入按时间升序的 [{d,v}]，返回 {text, first, last, hi, lo, flatDays}。
  // flatDays=末尾连续"几乎没变"(变化<0.5个百分点即0.005)的天数；先说从哪到哪，再说最近是否持平，最后是否出现过更高/更低。
  L.describeRun = function (pts, eps) {
    eps = eps == null ? 0.005 : eps;
    if (!pts || pts.length < 2) return { text: '历史累积中', first: null, last: null, hi: null, lo: null, flatDays: 0 };
    const v = pts.map(p => p.v), first = v[0], last = v[v.length - 1], hi = Math.max(...v), lo = Math.min(...v);
    let flat = 1; for (let i = v.length - 1; i > 0 && Math.abs(v[i] - v[i - 1]) <= eps; i--) flat++;      // 数点不数间隔：最后连续3个相同的值=持平了3天
    if (flat < 2) flat = 0;
    const pc = x => (x > 0 ? '+' : x < 0 ? '\u2212' : '') + Math.abs(Math.round(x * 100)) + '%';
    let t = '近' + pts.length + '天从' + pc(first) + (Math.abs(last - first) <= eps ? '基本持平' : (last > first ? '回升到' : '走低到') + pc(last));
    const hiIdx = v.indexOf(hi), loIdx = v.indexOf(lo);
    // 两个信息可以同时说：中间是否到过更高/更低(不含两端)，以及最近是否持平
    if (hi > Math.max(first, last) + eps && hiIdx !== 0 && hiIdx !== v.length - 1) t += '，中间到过' + pc(hi);
    else if (lo < Math.min(first, last) - eps && loIdx !== 0 && loIdx !== v.length - 1) t += '，中间到过' + pc(lo);
    if (flat >= 2) t += '，最近' + flat + '天持平';
    return { text: t, first, last, hi, lo, flatDays: flat };
  };

  /* ---------- 展示辅助 ---------- */
  // 变化量的人话表示：百分比在基数很小时失真(CFTC 13周前4,740手→207,578手=+4279%)，超过±500%改用"约N倍"，基数≈0或百分比不可算时用绝对变化。
  // 返回 {text, kind:'pct'|'times'|'abs'}；text不带正负号(方向用箭头和颜色表达)。
  L.fmtChange = function (change, pct, show, unit) {
    const abs = Math.abs(change);
    const num = n => Math.abs(n) >= 1e4 && unit === '手' ? (Math.abs(n) / 1e4).toFixed(1) + '万' : Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: Math.abs(n) < 10 ? 2 : Math.abs(n) < 100 ? 1 : 0 });
    if (show === 'pct' && pct != null) {
      const a = Math.abs(pct);
      if (a > 5) { const x = 1 + a; return { text: (x >= 10 ? Math.round(x) : x.toFixed(1)) + '倍', kind: 'times', approx: true }; }      // 不写"约"：窄格子里 "↑约44倍" 放不下；它本来就是近似值，approx 标记留给详情/悬停去解释       // 涨a=变成原来的(1+a)倍；pct<0时a不会>5(最多-100%)，所以这里只会是上涨
      return { text: (a * 100).toFixed(a < 0.1 ? 1 : 0) + '%', kind: 'pct' };
    }
    return { text: num(abs), kind: 'abs' };
  };

  L.fmtNum = function (v, unit) {
    if (v == null || isNaN(v)) return '—';
    const a = Math.abs(v);
    if (unit === '手' && a >= 1e4) return (v / 1e4).toFixed(a >= 1e5 ? 1 : 2) + ' 万手';
    const d = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 10 ? 1 : 2;
    return v.toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: 0 });
  };


  /* ---------- 本金追加计算器（金额单位：万元）----------
   * 预算档位：cur=本地策略 v102.22（<500万 55%、<1500万 40%、<5000万 25%、其后15%）；v45=v102.20（<500万 45%）；flat=全程55%；old=旧阶梯（<500万 60%）。
   * 月收益 = 年化 × 档位折算，再按月复利。55%档按填的年化；45%档用回测实测比例 48/52，60%档 55/52；其余档按 档位/55% 线性缩小（简化，不是回测结果）。
   * 追加：第2年起每年年初到账；回撤：第 ddy 年末一次性亏 ddp%。 */
  L.CALC_LADDERS = {
    cur: [[500, .55], [1500, .40], [5000, .25], [Infinity, .15]],
    v45: [[500, .45], [1500, .40], [5000, .25], [Infinity, .15]],
    flat: [[Infinity, .55]],
    old: [[500, .60], [1500, .40], [5000, .25], [Infinity, .15]]
  };
  L.calcTier = function (E, mode) {
    const t = L.CALC_LADDERS[mode] || L.CALC_LADDERS.cur;
    for (let i = 0; i < t.length; i++) if (E < t[i][0]) return t[i][1];
    return t[t.length - 1][1];
  };
  L.calcFactor = function (tier) { return tier === .60 ? 55 / 52 : tier === .45 ? 48 / 52 : tier / .55; };
  // P: {start, add, ladder, ddy, ddp}；r: 年化(0.36)；years: 整数。返回 {eq:每月末权益(含第0月), yearly:[...], final, invested}
  L.calcSim = function (P, r, years) {
    let E = P.start, inv = P.start, startY = E, addY = 0, tierY = L.calcTier(E, P.ladder);
    const eq = [E], yearly = [];
    for (let m = 1; m <= years * 12; m++) {
      if ((m - 1) % 12 === 0) { addY = 0; if (m > 1) { E += P.add; inv += P.add; addY = P.add; } startY = E; tierY = L.calcTier(E, P.ladder); }
      E *= Math.pow(1 + r * L.calcFactor(L.calcTier(E, P.ladder)), 1 / 12);
      if (m % 12 === 0) {
        const yr = m / 12, endBefore = E, dd = !!(P.ddy > 0 && yr === P.ddy);
        if (dd) E *= (1 - P.ddp / 100);
        yearly.push({ year: yr, add: addY, start: startY, endBefore, end: E, invested: inv, tier: tierY, dd });
      }
      eq.push(E);
    }
    return { eq, yearly, final: E, invested: inv };
  };
  // 第一次达到 goal 的月数（含第0月）；maxYears 内没到返回 null
  L.calcMonthsTo = function (P, r, goal, maxYears) {
    const s = L.calcSim(P, r, maxYears);
    for (let m = 0; m < s.eq.length; m++) if (s.eq[m] >= goal) return m;
    return null;
  };
  // 要在 years 年内到 goal，每年需追加多少（二分；本金够了返回0）
  L.calcNeedAdd = function (P, r, goal, years) {
    if (L.calcSim(Object.assign({}, P, { add: 0 }), r, years).final >= goal) return 0;
    let lo = 0, hi = 1e6;
    for (let i = 0; i < 70; i++) { const mid = (lo + hi) / 2; if (L.calcSim(Object.assign({}, P, { add: mid }), r, years).final < goal) lo = mid; else hi = mid; }
    return hi;
  };
  // 金额(万元)→文本
  L.calcFmt = function (w) {
    if (w == null || !isFinite(w)) return '—';
    const a = Math.abs(w);
    if (a >= 10000) return (w / 10000).toFixed(a >= 100000 ? 1 : 2) + ' 亿';
    if (a >= 1000) return Math.round(w).toLocaleString('en-US') + ' 万';
    if (a >= 100) return w.toFixed(0) + ' 万';
    return w.toFixed(1) + ' 万';
  };
  L.calcYm = function (m) { if (m == null) return '—'; const y = Math.floor(m / 12), r = m % 12; return (y ? y + ' 年' : '') + (r || !y ? (y ? ' ' : '') + r + ' 个月' : ''); };

  if (typeof module !== 'undefined' && module.exports) module.exports = L; else root.CockpitLogic = L;
})(typeof window !== 'undefined' ? window : globalThis);

