// 用假图表库验证图表创建/销毁行为
let createChartCallCount = 0;
let removeCallCount = 0;
let lastCreatedContainerIds = [];
global.LightweightCharts = {
  createChart(container){
    createChartCallCount++;
    lastCreatedContainerIds.push(container.id);
    return {
      addSeries(){ return { setData(){} }; },
      timeScale(){ return { fitContent(){}, subscribeVisibleLogicalRangeChange(){}, setVisibleLogicalRange(){} }; },
      applyOptions(){},
      remove(){ removeCallCount++; },
    };
  },
  CandlestickSeries: {}, LineSeries: {}, HistogramSeries: {},
};
global.ResizeObserver = class { observe(){} };

const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：getDefaultContractByDate()逐月核对 =====================
// 直接复用CONTRACT_CONTEXT.recommendedMonths，逐月核对不应该有空隙或重叠
const monthToExpected = {
  1:'may', 2:'may', 3:'may', 4:'sep', 5:'sep', 6:'sep', 7:'sep',
  8:'jan', 9:'jan', 10:'jan', 11:'jan', 12:'may',
};
let allMonthsCorrect = true;
for(const [month, expected] of Object.entries(monthToExpected)){
  const testDate = new Date(2026, Number(month)-1, 15);
  const result = getDefaultContractByDate(testDate);
  if(result !== expected){
    allMonthsCorrect = false;
    console.log(`  ❌ ${month}月期望${expected}实际得到${result}`);
  }
}
check('★getDefaultContractByDate()：12个月逐一核对，全部命中期望的合约(无空隙无重叠)', allMonthsCorrect);

// ★用户举的具体例子：2026年8月，应该建议1月合约(实际数据是2027年1月M2701，但这里测的是选哪个key，
//   具体年份由get_current_contract_code在后端已经验证过)
const augustDate = new Date(2026, 7, 20); // 8月20日
check('★用户举例场景：8月应该自动选中jan(对应实际抓取的是2027年1月合约)', getDefaultContractByDate(augustDate) === 'jan');

// ===================== 测试2：refreshKlineForContract()按合约取正确的数据key =====================
makeEl('klineBadge'); makeEl('klineContent');
['klineChartContainer','klineVolumeContainer','klineMacdContainer','klineRsiContainer'].forEach(id=>{
  const el = makeEl(id); el.clientWidth=700; el.clientHeight=200;
});
makeEl('klineHourlyDetails').open = false;
makeEl('klineCardTitle');

const makeBars = (basePrice)=>Array.from({length:40}, (_,i)=>({
  date:`2026-0${(i%9)+1}-0${(i%9)+1}`, open:basePrice+i, high:basePrice+i+5, low:basePrice+i-5, close:basePrice+i+2,
  volume:1000+i, hold:50000+i, settle:basePrice+i+1,
}));

window._syncedData = {
  generatedAt: new Date().toISOString(),
  dceM09Daily: {available:true, symbol:'M2609', totalBarsReturned:40, bars:makeBars(3300), source:'测试'},
  dceM09Hourly: {available:false, reason:'测试无小时线'},
  dceM05Daily: {available:true, symbol:'M2705', totalBarsReturned:40, bars:makeBars(3500), source:'测试'},
  dceM05Hourly: {available:false, reason:'测试无小时线'},
  dceM01Daily: {available:true, symbol:'M2701', totalBarsReturned:40, bars:makeBars(3400), source:'测试'},
  dceM01Hourly: {available:false, reason:'测试无小时线'},
};

setTimeout(()=>{
  createChartCallCount = 0; lastCreatedContainerIds = [];
  refreshKlineForContract('may');
  setTimeout(()=>{
    check('★切到may合约时，卡片标题应该显示M2705(5月合约的symbol)', makeEl('klineCardTitle').textContent.includes('M2705'));

    refreshKlineForContract('jan');
    setTimeout(()=>{
      check('★切到jan合约时，卡片标题应该显示M2701(1月合约的symbol)，不是上一个合约的M2705', makeEl('klineCardTitle').textContent.includes('M2701'));

      // ===================== 测试3：切换合约时正确清理旧图表实例(防内存泄漏) =====================
      const removeCountBeforeSwitch = removeCallCount;
      refreshKlineForContract('sep');
      // renderKline内部会同步调用destroyKlineCharts()（在setTimeout排队图表创建之前），
      // 所以不需要等下一个setTimeout，此刻就该已经调用了remove()清理上一轮(jan)的图表实例。
      // ★这次UI精简后MACD/RSI改成收起状态延迟加载了，这个测试流程里从没打开过它们的details，
      //   所以只有main+volume这2个会被创建/清理(不再是4个)。
      check('★切换合约前应该销毁上一次的图表实例(main+volume共2个，MACD/RSI这次测试流程里没打开过)，避免内存泄漏堆积',
        removeCallCount === removeCountBeforeSwitch + 2);

      setTimeout(()=>{
        check('切到sep合约后标题正确显示M2609', makeEl('klineCardTitle').textContent.includes('M2609'));

        // ===================== 测试4：切到没有数据的合约，标题应重置且不残留旧图表 =====================
        const removeCountBeforeNoData = removeCallCount;
        window._syncedData.dceM05Daily = {available:false, reason:'测试：模拟这个合约暂时没数据'};
        refreshKlineForContract('may');
        check('★切到没数据的合约，也应该先销毁上一个合约(sep)的图表实例，不留孤儿对象',
          removeCallCount === removeCountBeforeNoData + 2);
        check('切到没数据的合约，标题应该重置为通用文案，不残留上一个合约的symbol',
          makeEl('klineCardTitle').textContent === '日K线');

        H.printSummary();
      }, 10);
    }, 10);
  }, 10);
}, 10);
