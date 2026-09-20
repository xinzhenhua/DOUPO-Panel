const H = require('./test_helpers');
const { makeEl, check } = H;

eval(H.loadDashboardJs());

// ===================== 测试1：computeMASeriesData纯逻辑运算 =====================
const bars = Array.from({length: 30}, (_, i) => ({
  date: `2026-01-${String(i+1).padStart(2,'0')}`, close: 100+i, open: 99+i, high: 101+i, low: 98+i,
}));

const ma5 = computeMASeriesData(bars, 5);
check('MA5应该从第5根开始有值(前4根数据不够，不该出现)', ma5.length === bars.length - 4);
check('MA5第一个值应该是前5根收盘价的平均(102,101,100,99,98的平均=100)', 
  Math.abs(ma5[0].value - (bars.slice(0,5).reduce((s,b)=>s+b.close,0)/5)) < 0.001);
check('MA5数据格式应该是{time, value}(Lightweight Charts要求的格式)', 
  ma5[0].hasOwnProperty('time') && ma5[0].hasOwnProperty('value'));
check('MA5的time字段应该对应正确的日期(第5根bar的日期)', ma5[0].time === bars[4].date);

const ma20 = computeMASeriesData(bars, 20);
check('MA20应该从第20根开始有值', ma20.length === bars.length - 19);

const ma40 = computeMASeriesData(bars, 40);
check('MA40用period=40也应该能正确算(哪怕当前测试数据只有30根，此时结果应为空数组而不报错)', Array.isArray(ma40));

// 验证renderCandlestickChart函数源码里确实配置了MA40(直接检查源码字符串，
// 因为maConfigs是函数内部局部变量，没法从外部直接访问)
const rawHtml = require('fs').readFileSync(require('path').join(__dirname, '..', 'index.html'), 'utf8');
check('★用户要求补充：源码里应该包含MA40这个均线配置', rawHtml.includes("period:40") && rawHtml.includes("label:'MA40'"));

// 数据不够时的边界情况(比如只有10根数据，算MA20)
const shortBars = bars.slice(0, 10);
const ma20Short = computeMASeriesData(shortBars, 20);
check('数据不够period长度时，应该返回空数组(不是报错或返回错误值)', ma20Short.length === 0);

// ===================== 测试2：图表库未加载时应优雅降级，不崩溃 =====================
// (在Node测试环境里，LightweightCharts本来就是undefined，这正好模拟"库加载失败"的真实场景)
check('测试环境确认：LightweightCharts应为undefined(模拟库加载失败/网络问题)', typeof LightweightCharts === 'undefined');

makeEl('klineBadge'); makeEl('klineContent'); makeEl('klineChartContainer'); makeEl('klineHourlyChartContainer');
const dailyData = {
  available: true, symbol: 'M2609', totalBarsReturned: 30, bars,
  source: '新浪财经(经akshare库获取)',
};

let didThrow = false;
try{
  renderKline(dailyData, {available:false, reason:'测试'}, new Date().toISOString());
} catch(e){
  didThrow = true;
  console.log('意外抛出异常:', e.message);
}
check('★关键验证：图表库未加载时，renderKline不应该抛出异常导致整个页面崩溃', !didThrow);
check('至少应该正常生成基础的统计信息HTML(不依赖图表库的部分)', makeEl('klineContent').innerHTML.includes('M2609'));

// renderKline内部用setTimeout(fn, 0)延迟创建图表(要等DOM先插入)，这里也用setTimeout排在后面确保它先执行完
setTimeout(()=>{
  check('图表库缺失时，图表容器应该显示"加载失败"提示(不是空白或卡在loading)', 
    makeEl('klineChartContainer').innerHTML.includes('图表库加载失败'));
  H.printSummary();
}, 10);
