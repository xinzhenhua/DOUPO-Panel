const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：支撑/压力位 =====================
// 构造30根bar，刻意让第25根(倒数第6根，在最近20根窗口内)是全局最低点，第5根(明确在窗口外)是全局最高点
const srBars = Array.from({length:30}, (_,i)=>({
  date:`2026-01-${String(i+1).padStart(2,'0')}`,
  open:3000, close:3000,
  high: i===5 ? 3500 : (i===25 ? 3050 : 3200), // 第5根(30-20=10之前，明确在窗口外)全局最高3500，不该被最近20根窗口捕捉到
  low: i===25 ? 2800 : 3100, // 第25根(窗口内)是最低点2800
}));
const {support, resistance} = computeSupportResistance(srBars, 20);
check('★支撑位应该是最近20根窗口内的最低点(2800)，不是全局最低点', support === 2800);
check('★压力位应该是最近20根窗口内的最高点，不该被窗口外的3500(第10根)干扰', resistance === 3200);

const emptySR = computeSupportResistance([], 20);
check('空数组不应该报错，应该返回null', emptySR.support === null && emptySR.resistance === null);

// ===================== 测试2：趋势信号(均线排列) =====================
// 严格递增价格序列(每天涨5)：短期均线必然在长期均线上方 → 应该判定多头排列
const bullBars = Array.from({length:70}, (_,i)=>({date:`2026-0${(i%9)+1}-0${(i%9)+1}`, close:2900+i*5}));
const bullTrend = computeTrendSignal(bullBars);
check('★严格递增价格序列，应该判定为多头排列(bullish)', bullTrend.direction === 'bullish');

// 严格递减价格序列 → 应该判定空头排列
const bearBars = Array.from({length:70}, (_,i)=>({date:`2026-0${(i%9)+1}-0${(i%9)+1}`, close:3500-i*5}));
const bearTrend = computeTrendSignal(bearBars);
check('★严格递减价格序列，应该判定为空头排列(bearish)', bearTrend.direction === 'bearish');

// 剧烈震荡(上下交替)，均线不会呈现清晰排列 → 应该判定中性/不明确
const choppyBars = Array.from({length:70}, (_,i)=>({date:`2026-0${(i%9)+1}-0${(i%9)+1}`, close: 3000 + (i%2===0?200:-200) + Math.sin(i)*50}));
const choppyTrend = computeTrendSignal(choppyBars);
check('剧烈震荡序列，应该判定为中性/排列不明确(不应该误判成多头或空头)', choppyTrend.direction === 'neutral');

// 数据太少(不够2条均线可比较)
const tinyBars = Array.from({length:3}, (_,i)=>({date:`2026-01-0${i+1}`, close:3000+i}));
const tinyTrend = computeTrendSignal(tinyBars);
check('数据太少时应该诚实说明"数据不足"，不该硬判断', tinyTrend.label.includes('数据不足'));

// ===================== 测试3：技术面共振摘要——先验证factors数量+计数逻辑 =====================
// 40根下跌+35根上涨：足够让MACD在下跌段就开始有值(35根warmup)，之后能观察到实际的金叉，
// 同时均线排列会转为多头、RSI会走高——这样5个因子都能算出来，不会有缺项
const crossBars = [];
for(let i=0;i<40;i++) crossBars.push({date:`2026-01-${String(i%28+1).padStart(2,'0')}`, open:3200-i*4, close:3195-i*4, high:3205-i*4, low:3190-i*4});
for(let i=0;i<35;i++) crossBars.push({date:`2026-03-${String(i%28+1).padStart(2,'0')}`, open:3040+i*10, close:3045+i*10, high:3055+i*10, low:3035+i*10});
const {dif, dea, histogram} = computeMACD(crossBars);
const rsi = computeRSI(crossBars, 14);
const summary = computeConfluenceSummary(crossBars, dif, dea, histogram, rsi);
check('★共振摘要应包含5个独立因子(趋势/RSI/MACD柱方向/金叉死叉/支撑压力位)', summary.factors.length === 5);
check('★这个场景应该正确侦测到金叉(下跌转上涨)', summary.factors.find(f=>f.name.includes('金叉')).direction === 'bullish');
check('★趋势因子应该判定偏多(后段大涨拉动均线转为多头排列)', summary.factors.find(f=>f.name.includes('趋势')).direction === 'bullish');
check('★偏多计数(bullCount)应该跟factors里实际标记为bullish的数量完全一致(不多不少)',
  summary.bullCount === summary.factors.filter(f=>f.direction==='bullish').length);
check('偏多+偏空+中性的总数应该等于factors总数(计数逻辑没有遗漏或重复)',
  summary.bullCount + summary.bearCount + summary.neutralCount === summary.factors.length);

// 用简单的持续上涨场景单独验证趋势/RSI方向(这个场景MACD histogram会自然收敛到0附近，
// 不适合测试MACD相关因子，但很适合单独验证趋势和RSI这两个因子的方向判断)
const allBullBars = Array.from({length:70}, (_,i)=>({
  date:`2026-0${(i%9)+1}-0${(i%9)+1}`, open:2900+i*5, close:2905+i*5, high:2910+i*5, low:2895+i*5,
}));
const bullMacd = computeMACD(allBullBars);
const bullRsi = computeRSI(allBullBars, 14);
const bullSummary = computeConfluenceSummary(allBullBars, bullMacd.dif, bullMacd.dea, bullMacd.histogram, bullRsi);
check('★持续上涨场景：趋势因子应该判定偏多', bullSummary.factors.find(f=>f.name.includes('趋势')).direction === 'bullish');
check('★持续上涨场景：RSI因子应该判定偏多(RSI应该显著>55)', bullSummary.factors.find(f=>f.name==='RSI(14)').direction === 'bullish');


// 反向验证：持续下跌场景，趋势和RSI因子都应该判定偏空
const allBearBars = Array.from({length:70}, (_,i)=>({
  date:`2026-0${(i%9)+1}-0${(i%9)+1}`, open:3500-i*5, close:3495-i*5, high:3505-i*5, low:3490-i*5,
}));
const bearMacd = computeMACD(allBearBars);
const bearRsi = computeRSI(allBearBars, 14);
const bearSummary = computeConfluenceSummary(allBearBars, bearMacd.dif, bearMacd.dea, bearMacd.histogram, bearRsi);
check('★持续下跌场景：趋势因子应该判定偏空', bearSummary.factors.find(f=>f.name.includes('趋势')).direction === 'bearish');
check('★持续下跌场景：RSI因子应该判定偏空', bearSummary.factors.find(f=>f.name==='RSI(14)').direction === 'bearish');

// 数据不够时(比如刚够RSI但不够MACD)，共振摘要不应该报错，该有的因子有，算不出来的因子就不包含
const shortBars = Array.from({length:20}, (_,i)=>({date:`2026-01-${String(i+1).padStart(2,'0')}`, open:3000, close:3000+i, high:3005+i, low:2995+i}));
const shortMacd = computeMACD(shortBars); // 20根数据不够算MACD(需要至少35根)
const shortRsi = computeRSI(shortBars, 14); // 20根够算RSI(需要至少15根)
const shortSummary = computeConfluenceSummary(shortBars, shortMacd.dif, shortMacd.dea, shortMacd.histogram, shortRsi);
check('数据不够算MACD时，共振摘要不应该报错，应该只包含算得出来的因子(趋势/RSI/支撑压力位，不含MACD相关)',
  !shortSummary.factors.some(f=>f.name.includes('MACD')));

// ===================== 测试4：renderConfluenceSummaryHtml渲染 + renderKline整合 =====================
const htmlOutput = renderConfluenceSummaryHtml(summary);
check('★HTML输出应该包含计数总览("项偏多"这几个字)', htmlOutput.includes('项偏多') && htmlOutput.includes('项偏空') && htmlOutput.includes('项中性'));
check('★HTML输出里每个factor都应该有对应的名称出现', summary.factors.every(f=>htmlOutput.includes(f.name)));
check('HTML输出不应该包含"买入"/"卖出"/"建议"这类结论性词汇(只列因子，不下结论)',
  !htmlOutput.includes('建议买') && !htmlOutput.includes('建议卖') && !htmlOutput.includes('应该买') && !htmlOutput.includes('应该卖'));

// renderKline整合：确认"技术面共振摘要"这个板块真的出现在最终渲染结果里
global.LightweightCharts = { createChart(){ return { addSeries(){return{setData(){}};}, timeScale(){return{fitContent(){},subscribeVisibleLogicalRangeChange(){},setVisibleLogicalRange(){}};}, applyOptions(){}, remove(){} }; }, CandlestickSeries:{}, LineSeries:{}, HistogramSeries:{} };
global.ResizeObserver = class { observe(){} };
makeEl('klineBadge'); makeEl('klineContent');
['klineChartContainer','klineVolumeContainer'].forEach(id=>{ const el=makeEl(id); el.clientWidth=700; el.clientHeight=200; });
const dailyDataForKline = {available:true, symbol:'M2609', totalBarsReturned:crossBars.length, bars:crossBars, source:'测试'};
renderKline(dailyDataForKline, {available:false, reason:'测试'}, new Date().toISOString());
check('★renderKline输出应该包含"技术面共振摘要"这个板块标题', makeEl('klineContent').innerHTML.includes('技术面共振摘要'));
check('renderKline输出应该包含计数总览文字', makeEl('klineContent').innerHTML.includes('项偏多'));

H.printSummary();
