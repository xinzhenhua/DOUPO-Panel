// ============================================================================
// 每天记录两个系统的方向：无头快照脚本(scripts/snapshot_systems.js)
// 依赖 jsdom：没装就跳过(工作流里会 npm install jsdom)。本地运行：NODE_PATH=<含jsdom的node_modules> node tests/test_snapshot.js
// ============================================================================
const fs = require('fs'), os = require('os'), path = require('path'), cp = require('child_process');
let JSDOM_OK = true;
try { require('jsdom'); } catch (e) { JSDOM_OK = false; }
if (!JSDOM_OK) { console.log('⏭️ 未安装jsdom，跳过快照脚本测试(工作流里会安装)'); console.log('结果：0项通过，0项失败(跳过)'); process.exit(0); }

const H = require('./test_helpers');
const { check } = H;
const { runSnapshot, beijingDate, latestPrice } = require('../scripts/snapshot_systems.js');
const ROOT = path.join(__dirname, '..');
const HTML = path.join(ROOT, 'index.html');
const REAL_LATEST = path.join(ROOT, 'data', 'latest.json');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'snap_'));
const bj = (y,m,d,h,mi)=> Date.UTC(y, m-1, d, h||0, mi||0) - 8*3600*1000;
const NOW = bj(2026, 9, 30, 10, 0);                              // 周三 10:00 北京时间
const dAgo = n => new Date(NOW - n*86400000 + 8*3600000).toISOString().slice(0,10);

// ---------- 夹具：真实仓库的latest.json(含M2609真实日K线) + 补齐Mysteel/USDA等字段(数值来自之前的冒烟场景) ----------
function buildLatest(){
  const L = JSON.parse(fs.readFileSync(REAL_LATEST, 'utf8'));
  L.generatedAt = new Date(NOW - 3600000).toISOString();
  L.exportSales = {available:true, commodity:'Soybeans(大豆)', weekEnding:dAgo(12), marketYearUsed:2026, dataAgeDays:12, isStale:false, netSalesMT:1200000, prevNetSalesMT:800000, avg4wNetSalesMT:700000, vs4wAvgPct:71.4, wowChangePct:50, shipmentsMT:900000, chinaNetSalesMT:450000, total4wSumMT:3000000, source:'x'};
  L.supplyDemand = {available:true, commodity:'Oilseed, Soybean', marketYear:2026, marketYearLabel:'2026/27', wasdeVintage:'2026年09月版', endingStocks:8436, production:120700, domesticConsumption:61000, exports:62000, totalUse:123000, stocksToUsePct:6.9, unit:'千公吨', source:'x'};
  L.mysteelCrushRate = {available:true, value:69.98, date:dAgo(2)};
  L.mysteelMealStock = {available:true, value:117.3, date:dAgo(4), weekLabel:'第38周'};
  L.mysteelBasis = {available:true, value:-100, city:'日照', date:dAgo(1), usedFallback:false};
  L.mysteelArrivalForecast = {available:true, value:1100, forecastYear:2026, forecastMonth:10, date:dAgo(3)};
  L.mysteelSoyImport = {available:true, value:1214.14, monthLabel:'2026年8月', date:dAgo(20)};
  L.mysteelMealStu = {available:true, value:16.04, month:'2026-09', monthLabel:'2026年9月', isForecast:true, usedFallbackMonth:false, method:'stated', methodLabel:'文章明示', recordSource:'body', stockWan:125, consumptionWan:779, productionWan:795, next:null, trend:null, weeklyCheck:null, date:dAgo(2), articleAgeDays:2, articleTitle:'x', festival:{name:null, level:null, disturbed:false}};
  L.mysteelReserveAuction = {available:true, value:54.3, auctionDate:dAgo(2), soldWan:19.2, soldRate:37.3, date:dAgo(1)};
  L.hogRatio = {available:true, value:5.6, date:dAgo(1)};
  L.sowInventory = {available:true, value:3980, quarterLabel:'2026年二季度末', date:dAgo(60)};
  L.mysteelPoultryProfit = {available:true, value:-0.4, date:dAgo(5)};
  L.mysteelRmSpread = {available:true, value:550, formatUsed:'区间中点', rangeLow:500, rangeHigh:600, date:dAgo(6)};
  return L;
}
const LATEST_FULL = path.join(tmp, 'latest_full.json');
fs.writeFileSync(LATEST_FULL, JSON.stringify(buildLatest()));

// ---------- 联网桩：天气/汇率返回合法JSON(保证加载成功)；可以让指定URL失败/永不返回 ----------
const ok = (obj)=>({ok:true, status:200, json: async()=>obj});
function netStub(opts){
  opts = opts || {};
  return async (url)=>{
    const u = String(url);
    if(opts.hang) return new Promise(()=>{});
    if(opts.failMatch && u.includes(opts.failMatch)) return {ok:false, status:429, json: async()=>({})};
    if(u.includes('open-meteo')) return ok({daily:{precipitation_sum:[0,0,0,0,0,0,0], temperature_2m_max:[34,34,34,34,34,34,34]}});
    if(u.includes('frankfurter') && u.includes('..')) return ok({rates:{'2026-09-26':{CNY:7.1, BRL:5.4}, '2026-09-29':{CNY:7.2, BRL:5.5}}});
    if(u.includes('frankfurter')) return ok({date:'2026-09-29', rates:{CNY:7.2, BRL:5.5}});
    return {ok:false, status:404, json: async()=>({})};
  };
}
const rejectAll = async (u)=>{ throw new Error('沙盒无网络'); };
const run = (o)=>runSnapshot(Object.assign({htmlPath: HTML, latestPath: LATEST_FULL, nowMs: NOW, fetchImpl: netStub(), waitMs: 8000, jsdom: require('jsdom')}, o||{}));
const byC = (s, c)=>s.contracts.find(x=>x.contract===c);

(async ()=>{
  // ===================== 1. 纯函数 =====================
  check('北京时间日期：UTC 2026-09-30 16:30 = 北京10-01 00:30', beijingDate(Date.UTC(2026,8,30,16,30)) === '2026-10-01' && beijingDate(Date.UTC(2026,8,30,15,59)) === '2026-09-30');
  const L = buildLatest();
  check('★最新价格：sep取M2609日K线最后一根(真实数据：2026-09-14收盘3319)', JSON.stringify(latestPrice(L,'sep')) === JSON.stringify({symbol:'M2609', close:3319, priceDate:'2026-09-14'}));
  check('没有K线的合约(旧版latest.json没有M05/M01)：价格字段为null，不报错', JSON.stringify(latestPrice(L,'may')) === JSON.stringify({symbol:null, close:null, priceDate:null}) && latestPrice(null,'sep').close === null);
  check('K线不可用(available=false)：价格null', latestPrice({dceM09Daily:{available:false, bars:[{close:1,date:'2026-01-01'}]}}, 'sep').close === null);

  // ===================== 2. 真实仓库数据 + 没有网络：不崩溃，如实记录 =====================
  let s = await run({latestPath: REAL_LATEST, fetchImpl: rejectAll, waitMs: 6000});
  check('★没有网络+旧版latest.json：不崩溃，3个合约都有结果', s.contracts.length === 3 && s.contracts.every(c=>!c.error));
  check('★联网失败如实记录(天气×12+南美天气+汇率)，带URL和原因', s.fetchFailures.length >= 10 && s.fetchFailures.some(f=>f.includes('open-meteo') && f.includes('沙盒无网络')) && s.fetchFailures.some(f=>f.includes('frankfurter')));
  check('★数据太少时基本面方向为null(数据不足)，不硬给一个方向；缺席的投票都列出来', byC(s,'sep').fund === null && byC(s,'sep').missing.length >= 8);
  check('快照带评分规则版本号=页面里的SCORING_VERSION(v96)', s.scoringVersion === 'v96' && /const SCORING_VERSION = 'v96'/.test(fs.readFileSync(HTML,'utf8')));
  check('日期=北京日期；2026-09-30周三是交易日', s.date === '2026-09-30' && s.tradingDay === true);
  check('sep的价格字段来自真实日K线', byC(s,'sep').symbol === 'M2609' && byC(s,'sep').close === 3319 && byC(s,'sep').priceDate === '2026-09-14');
  // ===================== 2b. ★inWindow：是否在该合约的推荐交易窗口内(9月合约4-7月、5月合约12-3月、1月合约8-11月) =====================
  check('★页面导出各合约的推荐交易月份(与回填用的窗口一致)', JSON.stringify(await (async()=>{ const {JSDOM}=require('jsdom'); const dom = new JSDOM(fs.readFileSync(HTML,'utf8').replace(/<script[^>]+src="https?:[^"]*"[^>]*><\/script>/g,''), {runScripts:'dangerously', url:'http://localhost/', beforeParse(w){ w.fetch = async()=>({ok:false}); }}); const r = dom.window._contractRecommended; dom.window.close(); return r; })()) === JSON.stringify({sep:[4,5,6,7], may:[12,1,2,3], jan:[8,9,10,11]}));
  check('★9月30日(北京9月)：sep窗口外(false)、may窗口外(false)、jan窗口内(true)——现在该交易的是1月合约', byC(s,'sep').inWindow === false && byC(s,'may').inWindow === false && byC(s,'jan').inWindow === true);
  const at = async (y,m)=> (await run({nowMs: bj(y,m,15,10,0), fetchImpl: rejectAll, waitMs: 2500}));
  const w6 = await at(2026,6), w1 = await at(2027,1), w12 = await at(2026,12);
  check('★6月：sep窗口内、may/jan窗口外', byC(w6,'sep').inWindow === true && byC(w6,'may').inWindow === false && byC(w6,'jan').inWindow === false);
  check('★1月：may窗口内(12-3月跨年)、sep/jan窗口外', byC(w1,'may').inWindow === true && byC(w1,'sep').inWindow === false && byC(w1,'jan').inWindow === false);
  check('12月：may窗口内(12月起)', byC(w12,'may').inWindow === true);
  // 月初凌晨：北京已经是新的一个月，UTC还是上个月——必须按北京月份算
  check('★月初凌晨边界：北京8月1日00:30(=UTC 7月31日16:30)：sep已经出窗口(北京月份=8)，不能按UTC月份(7)算成窗口内', byC(await run({nowMs: bj(2026,8,1,0,30), fetchImpl: rejectAll, waitMs: 2500}),'sep').inWindow === false);
  check('★月初凌晨边界：北京4月1日00:30(=UTC 3月31日16:30)：sep已经进窗口(北京月份=4)', byC(await run({nowMs: bj(2026,4,1,0,30), fetchImpl: rejectAll, waitMs: 2500}),'sep').inWindow === true);
  check('★窗口边界：7月31日北京时间(sep最后一个月)在窗口内，8月1日就不在', byC(await run({nowMs: bj(2026,7,31,10,0), fetchImpl: rejectAll, waitMs: 2500}),'sep').inWindow === true && byC(await run({nowMs: bj(2026,8,1,10,0), fetchImpl: rejectAll, waitMs: 2500}),'sep').inWindow === false);

  // ===================== 3. 交易日标记：周末/国庆休市 =====================
  check('★2026-10-03(周六)：tradingDay=false', (await run({nowMs: bj(2026,10,3,10,0), fetchImpl: rejectAll, waitMs: 3000})).tradingDay === false);
  check('★2026-10-05(周一但国庆休市)：tradingDay=false', (await run({nowMs: bj(2026,10,5,10,0), fetchImpl: rejectAll, waitMs: 3000})).tradingDay === false);
  check('2026-10-08(恢复交易)：tradingDay=true', (await run({nowMs: bj(2026,10,8,10,0), fetchImpl: rejectAll, waitMs: 3000})).tradingDay === true);

  // ===================== 4. 数据齐全+联网桩：拿到两个系统的方向 =====================
  s = await run();
  const sep = byC(s,'sep');
  check('★数据齐全：sep有基本面(仅供需票)方向，票数≥5', sep.fund && ['偏多','偏空','中性'].includes(sep.fund.direction) && sep.fund.n >= 5 && typeof sep.fund.ratio === 'number');
  check('综合预警也有(数值)：方向/净倾向/票数', sep.composite && typeof sep.composite.ratio === 'number' && sep.composite.n >= sep.fund.n && sep.composite.total >= sep.composite.n);
  check('市场结构有结构(items是数组，direction/ratio/n/thin字段齐全)', sep.structure && Array.isArray(sep.structure.items) && 'direction' in sep.structure && 'ratio' in sep.structure && 'n' in sep.structure && 'thin' in sep.structure);
  check('联网桩全部成功：没有联网失败，没有等待超时', s.fetchFailures.length === 0 && s.timedOut === false);
  check('质量分/置信度/缺席投票/技术面方向/外资状态都被记录', typeof sep.quality === 'number' && Array.isArray(sep.missing) && 'confidence' in sep && 'tech' in sep && 'foreign' in sep && 'vpStatus' in sep);
  check('★三个合约分别计算(切换合约后各自算)：may/jan的结果独立存在', byC(s,'may') && byC(s,'jan') && byC(s,'may').contract === 'may' && byC(s,'jan').contract === 'jan');
  // 三个合约的投票清单不同(9月看美国作物、5月看南美+播种+雷亚尔、1月看收获进度+巴西播种)——这是"真的切换了合约再算"的证据
  const tot = c => byC(s,c).composite.total;
  check('★三个合约各自重算(而不是三次读到同一个结果)：总投票数不同(sep 12 / may 14 / jan 15)', tot('sep') === 12 && tot('may') === 14 && tot('jan') === 15);
  check('★合约专属的投票只出现在对应合约的缺席清单里：jan缺"美豆收获进度/巴西大豆播种进度"，sep没有这两项', byC(s,'jan').missing.some(x=>x.includes('美豆收获进度')) && byC(s,'jan').missing.some(x=>x.includes('巴西大豆播种进度')) && !byC(s,'sep').missing.some(x=>x.includes('美豆收获进度')));
  check('★快照是纯JSON：可序列化再反序列化(没有循环引用/函数)', JSON.stringify(JSON.parse(JSON.stringify(s))) === JSON.stringify(s));

  // ===================== 5. 可控场景：基本面偏多 + 市场结构偏空 =====================
  const prepBullFundBearStruct = (w, c)=>{
    w._weatherRisk='high'; w._droughtSignal=1; w._noaaOutlookSignal=1; w._soyCondSignal=1; w._psdSignal=1; w._fxSignal=1; w._esrSignal=0;
    const set = (id,v)=>{ w.document.getElementById(id).value = String(v); };
    set('m_stu',9); set('m_arrival',700); set('m_import',700); set('m_hogratio',8); set('m_poultry',2); set('m_crush',50); set('m_stock',70); set('m_rmspread',550);
    set('m_basis',-100); w._spreadSignal=-1; w._spreadQuality={m:1,why:''}; w._vpSignal=-1; w._vpQuality={m:1,why:''};
    for(const k of Object.keys(w._indState)) { delete w._indState[k].stale; delete w._indState[k].late; }
  };
  s = await run({prepare: prepBullFundBearStruct});
  const b = byC(s,'sep');
  check('★可控场景：基本面(仅供需)偏多、市场结构(基差+月差+量价)偏空——两个系统背离', b.fund.direction === '偏多' && b.structure.direction === '偏空' && b.structure.n === 3 && b.structure.thin === false);
  check('★综合预警被市场结构拉低：综合净倾向 < 纯基本面净倾向(这正是要分开记录的原因)', b.composite.ratio < b.fund.ratio);
  check('市场结构明细：3项都偏空', b.structure.items.length === 3 && b.structure.items.every(x=>x.signal === -1));
  const prepThin = (w, c)=>{ prepBullFundBearStruct(w, c); w._spreadSignal = undefined; w._vpSignal = undefined; };
  s = await run({prepare: prepThin});
  check('市场结构只有基差1项：thin=true被记录(分析时应排除)', byC(s,'sep').structure.n === 1 && byC(s,'sep').structure.thin === true);

  // ===================== 6. 联网部分失败 / 超时 =====================
  s = await run({fetchImpl: netStub({failMatch: 'frankfurter'})});
  check('★汇率接口被限流(429)：记录失败，仍然给出结果(不崩溃)', s.fetchFailures.some(f=>f.includes('frankfurter') && f.includes('429')) && byC(s,'sep').fund !== undefined);
  const t0 = Date.now();
  s = await run({fetchImpl: netStub({hang:true}), waitMs: 2500});
  check('★联网永不返回：到最长等待时间就放弃，timedOut=true，不会卡住整个工作流', s.timedOut === true && Date.now() - t0 < 12000 && s.contracts.length === 3);

  // ===================== 7. 失败路径 =====================
  let rejected = false; try { await run({htmlPath: path.join(tmp, '不存在.html')}); } catch (e) { rejected = true; }
  check('★页面文件不存在：抛异常(CLI以非0退出，工作流里continue-on-error)，而不是悄悄记录一份空数据', rejected);
  rejected = false; try { await run({latestPath: path.join(tmp, '不存在.json')}); } catch (e) { rejected = true; }
  check('latest.json不存在：抛异常', rejected);

  // ===================== 8. 命令行 =====================
  const out = path.join(tmp, 'sub', 'snap.json');
  const r = cp.spawnSync('node', [path.join(ROOT,'scripts','snapshot_systems.js'), '--html', HTML, '--latest', LATEST_FULL, '--out', out, '--wait', '2500'], {encoding:'utf8', env: process.env});
  check('★命令行：退出码0，自动创建输出目录，写出JSON', r.status === 0 && fs.existsSync(out));
  const cli = JSON.parse(fs.readFileSync(out, 'utf8'));
  check('命令行输出包含评分规则版本、3个合约、日期；stdout有一行摘要', cli.scoringVersion === 'v96' && cli.contracts.length === 3 && /^\d{4}-\d{2}-\d{2}$/.test(cli.date) && r.stdout.includes('[快照]'));
  const r2 = cp.spawnSync('node', [path.join(ROOT,'scripts','snapshot_systems.js')], {encoding:'utf8'});
  check('缺参数：退出码2并打印用法', r2.status === 2 && r2.stderr.includes('用法'));
  const r3 = cp.spawnSync('node', [path.join(ROOT,'scripts','snapshot_systems.js'), '--html', path.join(tmp,'无.html'), '--latest', LATEST_FULL, '--out', path.join(tmp,'x.json')], {encoding:'utf8'});
  check('页面文件不存在：退出码1', r3.status === 1 && r3.stderr.includes('快照失败'));

  fs.rmSync(tmp, {recursive:true, force:true});
  H.printSummary();
})().catch(e=>{ console.error('测试脚本自身出错', e); process.exit(1); });
