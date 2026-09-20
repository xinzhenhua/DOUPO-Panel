const H = require('./test_helpers');
const { makeEl, check } = H;

// 建一个最小化的LightweightCharts假库，用来验证"延迟初始化"这个行为逻辑本身，
// 而不只是检查代码字符串里有没有写这段逻辑
let createChartCallCount = 0;
let lastCreatedContainerIds = [];
global.LightweightCharts = {
  createChart(container, options){
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

eval(H.loadDashboardJs());

let pass=0, fail=0;
function check2(desc, cond){ if(cond){pass++;console.log('✅',desc);} else {fail++;console.log('❌',desc);} }

const bars = Array.from({length: 60}, (_, i) => ({
  date: `2026-01-${String(i%28+1).padStart(2,'0')}`, close: 2900+i, open: 2899+i, high: 2905+i, low: 2895+i,
}));
const hourlyBars = Array.from({length: 40}, (_, i) => ({
  datetime: `2026-07-${String(i%28+1).padStart(2,'0')} 10:00:00`, close: 3000+i, open: 2999+i, high: 3005+i, low: 2995+i,
}));

makeEl('klineBadge'); makeEl('klineContent');
const chartContainer = makeEl('klineChartContainer'); chartContainer.clientWidth = 700; chartContainer.clientHeight = 320;
const macdContainer = makeEl('klineMacdContainer'); macdContainer.clientWidth = 700; macdContainer.clientHeight = 130;
// 关键：模拟一个"收起状态"的details容器，clientWidth/Height都是0(真实浏览器里collapsed details内容就是这样)
const hourlyContainer = makeEl('klineHourlyChartContainer'); hourlyContainer.clientWidth = 0; hourlyContainer.clientHeight = 0;
const hourlyMacdContainer = makeEl('klineHourlyMacdContainer'); hourlyMacdContainer.clientWidth = 0; hourlyMacdContainer.clientHeight = 0;
makeEl('klineHourlyMacdCross');
const hourlyDetails = makeEl('klineHourlyDetails'); hourlyDetails.open = false; // 默认收起

const dailyData = { available: true, symbol: 'M2609', totalBarsReturned: 60, bars, source: 'test' };
const hourlyData = { available: true, symbol: 'M2609', totalBarsReturned: 40, bars: hourlyBars, source: 'test' };

renderKline(dailyData, hourlyData, new Date().toISOString());

// renderKline内部用setTimeout(fn,0)才真正创建图表，这里手动排在后面执行，模拟浏览器的下一个事件循环
setTimeout(()=>{
  check2('★核心验证：details收起状态下，页面加载完成时不应该立刻创建小时线图表(避免0宽高bug)',
    !lastCreatedContainerIds.includes('klineHourlyChartContainer'));
  check2('主K线图和成交量图应该正常创建(它们不在collapsed容器里，应该立刻初始化)',
    lastCreatedContainerIds.includes('klineChartContainer') && lastCreatedContainerIds.includes('klineVolumeContainer'));
  check2('★这次UI精简后，日线MACD也改成收起状态延迟加载了，不应该立刻创建',
    !lastCreatedContainerIds.includes('klineMacdContainer'));
  check2('details元素应该被绑定了ontoggle处理函数', typeof hourlyDetails.ontoggle === 'function');

  const countBeforeToggle = createChartCallCount;

  // 模拟用户点开details(浏览器会触发toggle事件，我们直接调用绑定的处理函数模拟这个过程)
  hourlyDetails.open = true;
  hourlyContainer.clientWidth = 700; hourlyContainer.clientHeight = 280; // 展开后容器恢复正常尺寸
  hourlyDetails.ontoggle();

  check2('★用户点开details后，小时线图表应该被创建(延迟初始化生效)',
    lastCreatedContainerIds.includes('klineHourlyChartContainer'));
  check2('图表创建次数应该刚好+2(小时K线+小时MACD)', createChartCallCount === countBeforeToggle + 2);

  // 再次触发toggle(比如用户收起又展开)，不应该重复创建图表(避免图表叠加/内存泄漏)
  const countAfterFirstOpen = createChartCallCount;
  hourlyDetails.open = false;
  hourlyDetails.ontoggle();
  hourlyDetails.open = true;
  hourlyDetails.ontoggle();
  check2('★重复展开/收起，不应该重复创建图表(只在第一次真正初始化)', createChartCallCount === countAfterFirstOpen);

  // ===================== 小时线MACD相关验证 =====================
  check2('★小时线MACD：展开details后，小时线MACD图表也应该被创建(不只是K线)',
    lastCreatedContainerIds.includes('klineHourlyMacdContainer'));
  check2('小时线金叉/死叉文字总结应该在图表创建之前就已经算好(不需要等用户展开)',
    makeEl('klineHourlyMacdCross').innerHTML.length > 0);

  console.log('');
  console.log(`结果：${pass}项通过，${fail}项失败`);
  if(fail>0) process.exit(1);
}, 10);
