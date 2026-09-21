const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：KDJ精确验证(用Python独立计算的基准值) =====================
const closes = [10,11,9,12,13,11,14,15,13,16,17,15,18];
const highs = closes.map(c=>c+1);
const lows = closes.map(c=>c-1);
const kdjBars = closes.map((c,i)=>({date:`2026-01-${String(i+1).padStart(2,'0')}`, close:c, high:highs[i], low:lows[i]}));
const {k, d, j} = computeKDJ(kdjBars, 9, 3, 3);

const pythonReference = {
  8:  [54.1667, 51.3889, 59.7222],
  9:  [65.7407, 56.1728, 84.8765],
  10: [73.8272, 62.0576, 97.3663],
  11: [70.0514, 64.7222, 80.7099],
  12: [76.3306, 68.5917, 91.8084],
};
for(const [idxStr, [expK, expD, expJ]] of Object.entries(pythonReference)){
  const idx = Number(idxStr);
  check(`★KDJ第${idx}个值精确验证(K)：跟Python基准值${expK}完全一致`, Math.abs(k[idx]-expK) < 0.001);
  check(`★KDJ第${idx}个值精确验证(D)：跟Python基准值${expD}完全一致`, Math.abs(d[idx]-expD) < 0.001);
  check(`★KDJ第${idx}个值精确验证(J)：跟Python基准值${expJ}完全一致`, Math.abs(j[idx]-expJ) < 0.001);
}
check('KDJ前period-1个(数据不够9根)应该是null', k.slice(0,8).every(v=>v===null));

// 数据不够period长度时，不应该报错，应该整段返回null
const shortKdjBars = kdjBars.slice(0,5);
const shortKdj = computeKDJ(shortKdjBars, 9, 3, 3);
check('数据不够9根时，KDJ应该整段是null(不报错)', shortKdj.k.every(v=>v===null));

// J值可能超出0-100范围，这是正常的(不是bug)
check('J值应该允许超出0-100范围(这是KDJ公式3K-2D的正常特性)', j[10] > 90); // 已经用Python基准验证过97.3663

// ===================== 测试2：findLatestLineCross通用交叉侦测函数 =====================
// 构造一个明确的上穿场景：lineA从低于lineB变成高于lineB
const crossBars2 = Array.from({length:10}, (_,i)=>({date:`2026-01-${String(i+1).padStart(2,'0')}`}));
const lineA = [10, 20, 30, 40, 60, 70, null, null, null, null]; // 第4个索引(60)开始超过lineB
const lineB = [50, 50, 50, 50, 50, 50, null, null, null, null];
const genericCross = findLatestLineCross(lineA, lineB, crossBars2);
check('★通用交叉函数：应该正确侦测到金叉(lineA从40<50变成60>50，在索引4发生)', 
  genericCross !== null && genericCross.type === 'golden' && genericCross.date === '2026-01-05');

// ===================== 测试3：findLatestMacdCross向后兼容(重构后行为不变) =====================
const barsCrossUp = [];
for(let i=0;i<40;i++) barsCrossUp.push({date:`2026-01-${String(i%28+1).padStart(2,'0')}`, close: 3000 - i*3});
for(let i=0;i<30;i++) barsCrossUp.push({date:`2026-02-${String(i%28+1).padStart(2,'0')}`, close: 2880 + i*8});
const {dif, dea} = computeMACD(barsCrossUp);
const macdCross = findLatestMacdCross(dif, dea, barsCrossUp);
check('★findLatestMacdCross重构成调用通用函数后，行为应该保持不变(先跌后涨→金叉)', macdCross !== null && macdCross.type === 'golden');

// ===================== 测试4：KDJ金叉/死叉侦测(复用通用函数) =====================
// 40根下跌+35根上涨：足够让KDJ(只需要9根warmup，比MACD的35根宽松很多)有充分观察空间看到交叉
const kdjCrossBars = [];
for(let i=0;i<40;i++) kdjCrossBars.push({date:`2026-01-${String(i%28+1).padStart(2,'0')}`, open:3200-i*4, close:3195-i*4, high:3205-i*4, low:3190-i*4});
for(let i=0;i<35;i++) kdjCrossBars.push({date:`2026-03-${String(i%28+1).padStart(2,'0')}`, open:3040+i*10, close:3045+i*10, high:3055+i*10, low:3035+i*10});
const {k:k2, d:d2} = computeKDJ(kdjCrossBars, 9, 3, 3);
const kdjCross = findLatestLineCross(k2, d2, kdjCrossBars);
check('★先跌后涨的价格序列，KDJ的K/D也应该能侦测到金叉', kdjCross !== null && kdjCross.type === 'golden');

// ===================== 测试5：KDJ整合进共振摘要(第6个因子) =====================
const {dif:dif2, dea:dea2, histogram:hist2} = computeMACD(kdjCrossBars);
const rsi2 = computeRSI(kdjCrossBars, 14);
const summaryWithKdj = computeConfluenceSummary(kdjCrossBars, dif2, dea2, hist2, rsi2, k2, d2);
check('★共振摘要传入KDJ数据后，应该包含6个因子(比之前的5个多了KDJ)', summaryWithKdj.factors.length === 6);
check('★KDJ因子应该存在且方向判断正确(K>D时偏多)', summaryWithKdj.factors.find(f=>f.name==='KDJ').direction === 'bullish');

// 不传KDJ参数时，应该保持向后兼容(还是5个因子，不报错)
const summaryWithoutKdj = computeConfluenceSummary(kdjCrossBars, dif2, dea2, hist2, rsi2);
check('不传KDJ参数时应该向后兼容，只有5个因子(不报错)', summaryWithoutKdj.factors.length === 5);

// ===================== 测试6：renderKline整合——KDJ详情区块应该出现 =====================
global.LightweightCharts = { createChart(){ return { addSeries(){return{setData(){}};}, timeScale(){return{fitContent(){},subscribeVisibleLogicalRangeChange(){},setVisibleLogicalRange(){}};}, applyOptions(){}, remove(){} }; }, CandlestickSeries:{}, LineSeries:{}, HistogramSeries:{} };
global.ResizeObserver = class { observe(){} };
makeEl('klineBadge'); makeEl('klineContent');
['klineChartContainer','klineVolumeContainer'].forEach(id=>{ const el=makeEl(id); el.clientWidth=700; el.clientHeight=200; });
makeEl('klineCardTitle');
const dailyDataForKdj = {available:true, symbol:'M2609', totalBarsReturned:kdjCrossBars.length, bars:kdjCrossBars, source:'测试'};
renderKline(dailyDataForKdj, {available:false, reason:'测试'}, new Date().toISOString());
check('★renderKline输出应该包含"KDJ(9,3,3)详情"这个板块', makeEl('klineContent').innerHTML.includes('KDJ(9,3,3)详情'));
check('renderKline输出的共振摘要里应该出现KDJ这个因子', makeEl('klineContent').innerHTML.includes('KDJ'));

H.printSummary();
