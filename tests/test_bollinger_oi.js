let createChartCallCount = 0;
let removeCallCount = 0;
const seriesCallLog = []; // 记录每次addSeries的参数，用来检查到底画了哪些线
global.LightweightCharts = {
  createChart(container){
    createChartCallCount++;
    return {
      addSeries(seriesType, opts){
        seriesCallLog.push({containerContext: container.id, opts});
        return { setData(data){ seriesCallLog[seriesCallLog.length-1].data = data; } };
      },
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

// ===================== 测试1：布林带精确验证(用Python独立计算的基准值) =====================
const closesForBB = [...Array(10).fill(100), 101,102,103,104,105,106,107,108,109,110];
const barsForBB = closesForBB.map((c,i)=>({date:`2026-01-${String(i+1).padStart(2,'0')}`, close:c}));
const {middle, upper, lower} = computeBollingerBands(barsForBB, 20, 2);
// Python基准：均值=102.75，标准差=3.418699，上轨=109.587397，下轨=95.912603
check('★布林带中轨精确验证：跟Python基准值102.75完全一致', Math.abs(middle[19]-102.75) < 0.0001);
check('★布林带上轨精确验证：跟Python基准值109.587397完全一致', Math.abs(upper[19]-109.587397) < 0.001);
check('★布林带下轨精确验证：跟Python基准值95.912603完全一致', Math.abs(lower[19]-95.912603) < 0.001);
check('布林带前19个(数据不够20根)应该是null', middle.slice(0,19).every(v=>v===null));

// 数据不够20根时，不应该报错，应该整段返回null
const shortBars = barsForBB.slice(0,10);
const shortBB = computeBollingerBands(shortBars, 20, 2);
check('数据不够period长度时，布林带应该整段是null(不报错)', shortBB.middle.every(v=>v===null));

// ===================== 测试2：renderCandlestickChart的均线/布林带二选一逻辑 =====================
const chartContainer = makeEl('klineChartContainer'); chartContainer.clientWidth=700; chartContainer.clientHeight=320;
const bars60 = Array.from({length:60},(_,i)=>({date:`2026-01-${String(i%28+1).padStart(2,'0')}`, open:2900+i, high:2910+i, low:2890+i, close:2905+i}));

seriesCallLog.length = 0;
renderCandlestickChart('klineChartContainer', bars60, 'ma');
const maLabels = seriesCallLog.filter(c=>c.opts && c.opts.title).map(c=>c.opts.title);
check('★overlayMode=ma时，应该画5条均线(MA5/10/20/40/60)，不应该出现布林带', 
  ['MA5','MA10','MA20','MA40','MA60'].every(l=>maLabels.includes(l)) && !maLabels.some(l=>l.includes('轨')));

seriesCallLog.length = 0;
renderCandlestickChart('klineChartContainer', bars60, 'bollinger');
const bbLabels = seriesCallLog.filter(c=>c.opts && c.opts.title).map(c=>c.opts.title);
check('★overlayMode=bollinger时，应该画3条布林带线(上轨/中轨/下轨)，不应该出现均线', 
  bbLabels.some(l=>l.includes('上轨')) && bbLabels.some(l=>l.includes('中轨')) && bbLabels.some(l=>l.includes('下轨')) && !bbLabels.includes('MA5'));

seriesCallLog.length = 0;
renderCandlestickChart('klineChartContainer', bars60); // 不传overlayMode，应该默认走ma(向后兼容)
const defaultLabels = seriesCallLog.filter(c=>c.opts && c.opts.title).map(c=>c.opts.title);
check('不传overlayMode参数时，应该默认走均线模式(保持向后兼容)', defaultLabels.includes('MA5'));

// ===================== 测试3：成交量图表应该包含持仓量线 =====================
const volContainer = makeEl('klineVolumeContainer'); volContainer.clientWidth=700; volContainer.clientHeight=100;
const barsWithHold = bars60.map((b,i)=>({...b, volume:1000+i, hold:50000+i*10}));
seriesCallLog.length = 0;
renderVolumeChart('klineVolumeContainer', barsWithHold, null);
const volLabels = seriesCallLog.filter(c=>c.opts && c.opts.title).map(c=>c.opts.title);
check('★成交量图表应该包含"持仓量"这条线', volLabels.includes('持仓量'));
const oiCall = seriesCallLog.find(c=>c.opts && c.opts.title === '持仓量');
check('持仓量线应该用独立的左侧坐标轴(priceScaleId:left)，避免跟成交量数量级差异互相挤压',
  oiCall && oiCall.opts.priceScaleId === 'left');
check('持仓量线的数据点数量应该跟输入的bars一致(每根bar都有hold值)', oiCall.data.length === barsWithHold.length);

// hold字段缺失时不应该报错
seriesCallLog.length = 0;
renderVolumeChart('klineVolumeContainer', bars60.map(b=>({...b, volume:1000})), null); // 没有hold字段
const noHoldLabels = seriesCallLog.filter(c=>c.opts && c.opts.title).map(c=>c.opts.title);
check('bars没有hold字段时，不应该画持仓量线(也不应该报错)', !noHoldLabels.includes('持仓量'));

H.printSummary();
