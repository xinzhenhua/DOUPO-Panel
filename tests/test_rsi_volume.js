// 用假图表库，验证图表创建行为(跟之前的模式一致)
let createChartCallCount = 0;
let lastCreatedContainerIds = [];
global.LightweightCharts = {
  createChart(container){
    createChartCallCount++;
    lastCreatedContainerIds.push(container.id);
    return {
      addSeries(){ return { setData(){} }; },
      timeScale(){ return { fitContent(){}, subscribeVisibleLogicalRangeChange(){}, setVisibleLogicalRange(){} }; },
      applyOptions(){},
    };
  },
  CandlestickSeries: {}, LineSeries: {}, HistogramSeries: {},
};
global.ResizeObserver = class { observe(){} };

const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：RSI精确验证(经典Wilder教科书案例，公认基准≈70.46) =====================
const closesWilder = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28];
const barsWilder = closesWilder.map((c,i)=>({date:`2026-01-${String(i+1).padStart(2,'0')}`, close:c}));
const rsiResult = computeRSI(barsWilder, 14);
check('★RSI精确验证：经典Wilder教科书案例，用Python独立计算的基准值(70.4641)完全一致',
  Math.abs(rsiResult[14] - 70.4641) < 0.001);
check('RSI前14个应该是null(数据不够，至少需要period+1根)', rsiResult.slice(0,14).every(v=>v===null));

// 纯上涨序列(无下跌)，RSI应该是100
const barsAllUp = Array.from({length:20},(_,i)=>({date:`2026-01-${String(i+1).padStart(2,'0')}`, close:100+i}));
const rsiAllUp = computeRSI(barsAllUp, 14);
check('纯上涨序列(零下跌)，RSI应该恰好是100', rsiAllUp[14] === 100);

// ===================== 测试2：成交量均线(复用computeMASeriesData但换成volume字段) =====================
const barsWithVolume = Array.from({length:15},(_,i)=>({date:`2026-01-${String(i+1).padStart(2,'0')}`, close:100, volume:1000+i*100}));
const volMa10 = computeMASeriesData(barsWithVolume, 10, b=>b.volume);
check('成交量均线：应该从第10根开始有值', volMa10.length === barsWithVolume.length - 9);
const expectedVolMa10First = barsWithVolume.slice(0,10).reduce((s,b)=>s+b.volume,0)/10;
check('成交量均线第一个值应该是前10根成交量的平均', Math.abs(volMa10[0].value - expectedVolMa10First) < 0.001);
check('不传valueFn时，computeMASeriesData应该保持原有行为(默认用close)，不应该破坏原有的价格均线功能',
  computeMASeriesData(barsWithVolume, 10)[0].value === 100);

// ===================== 测试3：renderKline完整集成(统计列+成交量图+RSI图) =====================
createChartCallCount = 0; lastCreatedContainerIds = [];
makeEl('klineBadge'); makeEl('klineContent');
['klineChartContainer','klineVolumeContainer','klineMacdContainer','klineRsiContainer'].forEach(id=>{
  const el = makeEl(id); el.clientWidth=700; el.clientHeight=200;
});
makeEl('klineHourlyDetails').open = false;

const fullBars = Array.from({length:60}, (_,i)=>({
  date:`2026-0${(i%9)+1}-0${(i%9)+1}`, open:2900+i, high:2920+i, low:2880+i, close:2910+i,
  volume: 100000+i*1000, hold: 1900000+i*500, settle: 2911+i,
}));
const dailyData = { available:true, symbol:'M2609', totalBarsReturned:60, bars:fullBars, source:'test' };
// ★注意：eval加载的dashboard脚本会自动执行loadSyncedData()等初始化函数，
//   这些函数会异步fetch数据(测试环境里fetch会失败/被拒绝)，触发离线降级逻辑，
//   这个降级逻辑也会给klineContent写入内容——如果时机不对，会覆盖掉我们下面
//   显式调用renderKline()设置的内容。用setTimeout延后我们的调用，确保在
//   任何初始化噪音结束之后才执行，这样我们的调用才是最终生效的状态。
setTimeout(()=>{
  createChartCallCount = 0; lastCreatedContainerIds = []; // 重置：避免dashboard自己init流程里可能触发的图表创建被计入
  renderKline(dailyData, {available:false, reason:'test'}, new Date().toISOString());

  setTimeout(()=>{
    check('★统计列应该包含"今开"标签', makeEl('klineContent').innerHTML.includes('今开'));
    check('★统计列应该包含"今高"/"今低"标签', makeEl('klineContent').innerHTML.includes('今高') && makeEl('klineContent').innerHTML.includes('今低'));
    check('★统计列应该包含"昨收"标签', makeEl('klineContent').innerHTML.includes('昨收'));
    check('★统计列应该包含"昨结"标签(之前查过akshare有这个字段但没提取，这次补上了)', makeEl('klineContent').innerHTML.includes('昨结'));
    check('★统计列应该包含"持仓量"标签', makeEl('klineContent').innerHTML.includes('持仓量'));
    check('★统计列应该包含"日增仓"标签', makeEl('klineContent').innerHTML.includes('日增仓'));
    check('日增仓数值应该正确计算(最新持仓-前一日持仓)', makeEl('klineContent').innerHTML.includes('+500'));

    check('★应该包含成交量图表容器', lastCreatedContainerIds.includes('klineVolumeContainer'));
    check('★应该包含RSI图表容器', lastCreatedContainerIds.includes('klineRsiContainer'));
    check('内容应包含当前RSI数值文字总结', makeEl('klineContent').innerHTML.includes('当前RSI'));

    H.printSummary();
  }, 10);
}, 50);
