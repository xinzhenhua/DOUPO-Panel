#!/usr/bin/env node
// ============================================================================
// 每天记录两个系统的方向：用 jsdom 无头运行页面(index.html)自己的评分代码，读出结果。
//
// 为什么这样做：两个系统(基本面=仅供需票、市场结构=基差/月差/量价)的方向是在浏览器里(JS)算出来的，而历史是由
//   GitHub Actions 里的 Python 写的。重写一遍评分(一千多行)会让两份代码慢慢不一致；存浏览器localStorage只有你打开页面那天才记得到。
//   所以在 Actions 里把页面本身跑起来——评分逻辑只有一份，记录的就是你在页面上看到的。
//
// 用法：node scripts/snapshot_systems.js --html index.html --latest data/latest.json --out /tmp/systems_snapshot.json [--wait 25000]
// 依赖：jsdom(工作流里 npm install jsdom@30.1.1)。失败时进程以非0退出，但工作流里这一步 continue-on-error，绝不影响数据同步。
//
// ⚠️页面加载时会联网：汇率(frankfurter)、美国/南美天气(Open-Meteo)。从GitHub Actions的共享IP出去偶尔会被限流，
//   天气票一旦缺席，基本面的投票构成就变了，方向可能因为"网络噪声"翻转——所以快照里带上覆盖情况(有效票数、缺了哪些票)和联网失败清单，
//   记录时"同一天覆盖最完整的那次胜出"(见 record_systems.py)。
// ============================================================================
const fs = require('fs');
const path = require('path');

const CONTRACTS = ['sep', 'may', 'jan'];
const clone = x => (x === undefined ? null : JSON.parse(JSON.stringify(x)));

/** 北京时间的日期 'YYYY-MM-DD' */
function beijingDate(ms) {
  const d = new Date(ms + 8 * 3600 * 1000);
  return d.toISOString().slice(0, 10);
}

/** 各合约日K线最新一根(价格)：用于以后算前瞻收益；合约代码变了(移仓/到期滚动)时，跨代码的收益不可比，分析里按symbol过滤。 */
function latestPrice(latest, contract) {
  const key = { sep: 'dceM09Daily', may: 'dceM05Daily', jan: 'dceM01Daily' }[contract];
  const d = latest && latest[key];
  const bars = d && d.available && Array.isArray(d.bars) ? d.bars : [];
  if (!bars.length) return { symbol: null, close: null, priceDate: null };
  const b = bars[bars.length - 1];
  return { symbol: d.symbol || null, close: b.close == null ? null : b.close, priceDate: b.date ? String(b.date).slice(0, 10) : null };
}

/**
 * 运行快照。opts:
 *   htmlPath, latestPath  必填
 *   nowMs        固定"现在"(测试用；默认真实时间)。页面里的新鲜度判断读 window._nowMs
 *   fetchImpl    联网请求的实现(测试里注入)；默认用 Node 自带的 fetch(15秒超时)
 *   waitMs       最长等待页面异步数据(天气/汇率)加载完成的时间，默认25000
 *   prepare      测试接缝：(window, contract)=>{}，在读取每个合约的结果前调用
 *   jsdom        注入(测试用)；默认 require('jsdom')
 */
async function runSnapshot(opts) {
  const { JSDOM, VirtualConsole } = opts.jsdom || require('jsdom');
  const nowMs = opts.nowMs != null ? opts.nowMs : Date.now();
  const waitMs = opts.waitMs != null ? opts.waitMs : 25000;
  const latestText = fs.readFileSync(opts.latestPath, 'utf8');
  const latest = JSON.parse(latestText);
  // 去掉外部脚本(lightweight-charts：只用来画K线图，评分不需要；Actions里拉它也没意义)
  const html = fs.readFileSync(opts.htmlPath, 'utf8').replace(/<script[^>]+src="https?:\/\/[^"]*"[^>]*><\/script>/g, '');

  const failures = [];          // 联网失败清单(哪个URL、什么原因)
  let pending = 0, settledAt = Date.now();
  const realFetch = opts.fetchImpl || (async (url) => {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 15000);
    try { return await fetch(url, { signal: ctl.signal }); } finally { clearTimeout(t); }
  });
  const shim = async (url) => {
    const u = String(url);
    if (u.includes('data/latest.json')) return { ok: true, status: 200, json: async () => JSON.parse(latestText) };
    pending++;
    try {
      const r = await realFetch(u);
      if (!r || r.ok === false) failures.push(`${u.slice(0, 80)} → HTTP ${r && r.status}`);
      return r;
    } catch (e) {
      failures.push(`${u.slice(0, 80)} → ${e && e.message ? e.message : e}`);
      throw e;
    } finally { pending--; settledAt = Date.now(); }
  };

  const pageErrors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => pageErrors.push(String(e && e.message || e).slice(0, 160)));
  const dom = new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/',
    beforeParse(w) {
      w.fetch = shim; w._nowMs = nowMs;
      // ★时间注入要彻底：页面里很多规则(月份相关的投票清单、默认合约、窗口)读的是 new Date()，不是 window._nowMs。
      //   只在显式传了nowMs(测试/回放)时才把页面的Date固定成它；生产(没传)用真实时间，行为不变。
      if (opts.nowMs != null) {
        const RealDate = w.Date;
        class FixedDate extends RealDate {
          constructor(...a) { if (a.length === 0) super(nowMs); else super(...a); }
          static now() { return nowMs; }
        }
        w.Date = FixedDate;
      }
    },
  });
  const w = dom.window;

  // 等页面把异步数据(latest.json、天气、汇率)都加载完：latest已读入 + 没有在途请求 + 安静了0.6秒；或者到最长等待时间
  const started = Date.now();
  await new Promise(resolve => {
    const tick = () => {
      const quiet = pending === 0 && Date.now() - settledAt > 600 && Date.now() - started > 1500;
      if ((w._syncedData && quiet) || Date.now() - started > waitMs) return resolve();
      setTimeout(tick, 150);
    };
    tick();
  });
  const timedOut = !(w._syncedData && pending === 0);

  const out = [];
  for (const c of CONTRACTS) {
    try {
      w.selectContract(c);                 // 切换合约：会重新渲染K线/榨利/月差/量价，并触发评分重算
      if (opts.prepare) opts.prepare(w, c);   // 测试接缝：在读取结果前直接设置window上的信号(生产里不传)
      w.updateOverallAlert();
    } catch (e) {
      out.push({ contract: c, error: String(e && e.message || e).slice(0, 160) });
      continue;
    }
    const q = w._quality || {};
    const monthBJ = parseInt(beijingDate(nowMs).slice(5, 7), 10);
    const rec = w._contractRecommended && w._contractRecommended[c];
    out.push({
      contract: c,
      inWindow: rec ? rec.includes(monthBJ) : null,   // 是否在该合约的推荐交易窗口内(9月合约4-7月、5月合约12-3月、1月合约8-11月)；窗口外价格可能已过期/合约已到期
      fund: clone(w._fundamentalPure),              // {direction, ratio, n}：仅供需票
      structure: clone(w._structureSystem),         // {direction, ratio, n, thin, items}：基差/月差/量价
      composite: clone(w._composite),               // 顶部综合预警
      tech: w._technicalDirection || null,
      foreign: w._foreignActivity ? w._foreignActivity.status : null,
      quality: q.score == null ? null : q.score,
      missing: clone(q.missing) || [],              // 没有数据、因此没参与评分的投票
      confidence: w._fundamentalConfidence || null,
      vpStatus: w._vpStatus || null,
      ...latestPrice(latest, c),
    });
  }
  const tradingDay = (() => {
    try { const d = beijingDate(nowMs).split('-').map(Number); return !!w._eventCal.dceIsTradingDay(d[0], d[1], d[2]); } catch (e) { return null; }
  })();
  const snapshot = {
    date: beijingDate(nowMs),
    scoringVersion: w._scoringVersion || null,
    tradingDay,
    dataGeneratedAt: latest.generatedAt || null,
    timedOut,
    fetchFailures: failures,
    pageErrors: pageErrors.slice(0, 5),
    contracts: out,
  };
  w.close();
  return snapshot;
}

function parseArgs(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) a[argv[i].slice(2)] = argv[i + 1], i++;
  return a;
}

if (require.main === module) {
  const a = parseArgs(process.argv.slice(2));
  if (!a.html || !a.latest || !a.out) { console.error('用法: node scripts/snapshot_systems.js --html index.html --latest data/latest.json --out <文件> [--wait 25000]'); process.exit(2); }
  runSnapshot({ htmlPath: a.html, latestPath: a.latest, waitMs: a.wait ? parseInt(a.wait, 10) : undefined })
    .then(s => {
      fs.mkdirSync(path.dirname(path.resolve(a.out)), { recursive: true });
      fs.writeFileSync(a.out, JSON.stringify(s, null, 2));
      const ok = s.contracts.filter(c => c.fund && c.fund.ratio != null).length;
      console.log(`[快照] ${s.date} 评分规则${s.scoringVersion} 交易日=${s.tradingDay} 合约${ok}/${s.contracts.length}个有基本面方向；联网失败${s.fetchFailures.length}个${s.timedOut ? '；⚠️等待超时' : ''}`);
      s.contracts.forEach(c => console.log(`   ${c.contract}: 基本面=${c.fund ? c.fund.direction : '--'}(${c.fund ? c.fund.n : 0}票) 市场结构=${c.structure ? c.structure.direction : '--'}(${c.structure ? c.structure.n : 0}项) 综合=${c.composite ? c.composite.direction : '--'} 缺票${(c.missing || []).length}个`));
      s.fetchFailures.forEach(f => console.log('   ⚠️联网失败: ' + f));
      process.exit(0);
    })
    .catch(e => { console.error('[快照失败] ' + (e && e.stack || e)); process.exit(1); });
}
module.exports = { runSnapshot, beijingDate, latestPrice, CONTRACTS };
