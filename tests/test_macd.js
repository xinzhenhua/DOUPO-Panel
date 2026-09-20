const H = require('./test_helpers');
const { makeEl, check } = H;

eval(H.loadDashboardJs());

// ===================== 测试1：EMA计算正确性(用手算验证) =====================
// values=[10,11,12,13,14,15,16,17,18,19,20], period=5
// 种子(前5个简单平均) = (10+11+12+13+14)/5 = 12
// k = 2/(5+1) = 0.333...
// ema[5] = 15*k + 12*(1-k) = 15*0.3333+12*0.6667 = 5+8.0004 = 13.0004
const values1 = [10,11,12,13,14,15,16,17,18,19,20];
const ema5 = computeEMA(values1, 5);
check('EMA前period-1个应该是null(数据不够)', ema5[0]===null && ema5[1]===null && ema5[2]===null && ema5[3]===null);
check('EMA种子值(第5个)应该是前5个简单平均=12', Math.abs(ema5[4]-12) < 0.001);
const k = 2/6;
const expectedEma5 = 15*k + 12*(1-k);
check(`EMA第6个值应该是15*k+12*(1-k)≈${expectedEma5.toFixed(4)}`, Math.abs(ema5[5]-expectedEma5) < 0.001);

// ===================== 测试2：MACD计算(DIF/DEA/柱状图) =====================
// 用60根递增数据(模拟稳定上涨趋势)，验证MACD各字段结构正确
const bars60 = Array.from({length:60}, (_,i)=>({date:`2026-01-${String(i%28+1).padStart(2,'0')}`, close:2900+i*2}));
const {dif, dea, histogram} = computeMACD(bars60);
check('MACD应返回dif/dea/histogram三个等长数组', dif.length===60 && dea.length===60 && histogram.length===60);
check('DIF前25个(EMA26算不出来之前)应该是null', dif[24]===null && dif[25]!==null);
check('持续上涨趋势下，DIF应该是正值(快线在慢线上方)', dif[dif.length-1] > 0);
check('柱状图=（DIF-DEA)×2，应该正确按中国习惯乘以2', 
  Math.abs(histogram[histogram.length-1] - (dif[dif.length-1]-dea[dea.length-1])*2) < 0.0001);

// ===================== 测试3：金叉/死叉侦测 =====================
// 构造一个先跌后涨的价格序列，制造一次明确的金叉
const barsCrossUp = [];
for(let i=0;i<40;i++) barsCrossUp.push({date:`2026-01-${String(i%28+1).padStart(2,'0')}`, close: 3000 - i*3}); // 持续下跌
for(let i=0;i<30;i++) barsCrossUp.push({date:`2026-02-${String(i%28+1).padStart(2,'0')}`, close: 2880 + i*8}); // 之后持续上涨
const macdCrossUp = computeMACD(barsCrossUp);
const cross = findLatestMacdCross(macdCrossUp.dif, macdCrossUp.dea, barsCrossUp);
check('先跌后涨的价格序列，应该能侦测到金叉(DIF上穿DEA)', cross!==null && cross.type==='golden');
check('金叉侦测结果应包含date和daysAgo字段', cross && cross.hasOwnProperty('date') && cross.hasOwnProperty('daysAgo'));

// 构造一个先涨后跌的序列，制造死叉
const barsCrossDown = [];
for(let i=0;i<40;i++) barsCrossDown.push({date:`2026-01-${String(i%28+1).padStart(2,'0')}`, close: 2900 + i*3}); // 持续上涨
for(let i=0;i<30;i++) barsCrossDown.push({date:`2026-02-${String(i%28+1).padStart(2,'0')}`, close: 3020 - i*8}); // 之后持续下跌
const macdCrossDown = computeMACD(barsCrossDown);
const cross2 = findLatestMacdCross(macdCrossDown.dif, macdCrossDown.dea, barsCrossDown);
check('先涨后跌的价格序列，应该能侦测到死叉(DIF下穿DEA)', cross2!==null && cross2.type==='death');

// 数据不够(没有明确交叉)的情况不应该报错
const shortBars = bars60.slice(0, 20);
const macdShort = computeMACD(shortBars);
const crossNone = findLatestMacdCross(macdShort.dif, macdShort.dea, shortBars);
check('数据不够、DIF/DEA大部分是null时，应该返回null而不是报错', crossNone === null);

// ===================== 测试4：renderKline集成MACD后的显示效果 =====================
makeEl('klineBadge'); makeEl('klineContent'); makeEl('klineChartContainer');
makeEl('klineMacdContainer'); makeEl('klineHourlyChartContainer');
const dailyDataWithCross = {
  available: true, symbol: 'M2609', totalBarsReturned: barsCrossUp.length, bars: barsCrossUp,
  source: '新浪财经(经akshare库获取)',
};
renderKline(dailyDataWithCross, {available:false, reason:'测试'}, new Date().toISOString());
check('renderKline应该包含MACD相关文字标注', makeEl('klineContent').innerHTML.includes('MACD'));
check('renderKline应该包含金叉/死叉的文字总结(不只是图，还有可读的结论)', 
  makeEl('klineContent').innerHTML.includes('金叉') || makeEl('klineContent').innerHTML.includes('死叉') || makeEl('klineContent').innerHTML.includes('数据不足'));
check('应该包含MACD图表容器', makeEl('klineContent').innerHTML.includes('klineMacdContainer'));

// ===================== 测试5：小时线时区转换bug修复(用Python算出的正确UNIX时间戳核对) =====================
// 北京时间2026-07-13 14:15:00 → 用Python datetime精确算出的正确值是1783923300
const ts = beijingDatetimeToUnixSeconds('2026-07-13 14:15:00');
check('★核心验证：北京时间转UNIX时间戳，跟Python精确计算的基准值(1783923300)完全一致', ts === 1783923300);
check('返回值应该是数字(不是字符串)，Lightweight Charts需要数字类型的时间戳', typeof ts === 'number');

// 反向验证：转换回来应该还是原来的北京时间
const backToDate = new Date(ts * 1000);
const backToBeijingHour = (backToDate.getUTCHours() + 8) % 24; // UTC+8换算回北京时间的小时数
check('反向验证：转换后的UTC时间戳，加8小时换算回北京时间，小时数应该还是14', backToBeijingHour === 14);

H.printSummary();
