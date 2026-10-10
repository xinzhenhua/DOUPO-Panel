// ============================================================================
// v101.19：行情状态(ADX+彩带)、价格百分位带、资金市证据清单、休息灯(可选开关)、成本锚展示。
// 期望值全部手算：见各用例注释。这些只是"描述状态"，历史检验结论(无前向优势)写在页面上。
// ============================================================================
const fs = require('fs'), path = require('path');
const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
const R = window._regime;
check('导出了window._regime', !!R && typeof R.computeADX === 'function');

const mk = (n, f)=>Array.from({length:n}, (_, i)=>f(i));
// ---- 1. ADX ----
// 单边上涨：每天high+1,low+1,range恒为2,close=中点 → +DM=1,-DM=0,TR=2 → +DI=50,-DI=0 → DX恒为100 → ADX=100
const up = mk(60, i=>({high:101+i, low:99+i, close:100+i}));
const adxUp = R.computeADX(up, 14);
check('单边上涨ADX=100', Math.abs(adxUp[adxUp.length-1] - 100) < 1e-6);
check('ADX前27根是null(14根DI种子+13根DX平均,第28根起有值)', adxUp[26] === null && adxUp[27] !== null);
// 完全不动：+DM=-DM=0,TR>0 → DX定义为0，不能除零出NaN
const flat = mk(60, i=>({high:101, low:99, close:100}));
const adxFlat = R.computeADX(flat, 14);
check('横盘不动ADX=0且不是NaN', adxFlat[adxFlat.length-1] === 0);
// 来回震荡：+DM与-DM交替相等 → ADX很低
const zig = mk(80, i=> i%2===0 ? {high:11, low:9, close:10} : {high:12, low:10, close:11});
const adxZig = R.computeADX(zig, 14);
check('来回震荡ADX<10', adxZig[adxZig.length-1] < 10);
check('数据不足返回全null', R.computeADX(up.slice(0,20), 14).every(v=>v===null));

// ---- 2. 行情状态分类(22/28是文档阈值) ----
check('ADX 15 → 震荡', R.classifyRegime(15, 100, 100, 100).code === 'range');
check('ADX 25 → 过渡', R.classifyRegime(25, 100, 100, 100).code === 'transition');
check('ADX 30 + 收盘>MA20>MA60 → 上升趋势', R.classifyRegime(30, 110, 105, 100).code === 'trend_up');
check('ADX 30 + 收盘<MA20<MA60 → 下降趋势', R.classifyRegime(30, 90, 95, 100).code === 'trend_down');
check('ADX 30 但彩带缠绕 → 趋势强但方向不明', R.classifyRegime(30, 100, 105, 100).code === 'trend_mixed');
check('ADX恰好28算趋势、恰好22算过渡(边界)', R.classifyRegime(28, 110, 105, 100).code === 'trend_up' && R.classifyRegime(22, 100,100,100).code === 'transition');
check('ADX 21.9 仍是震荡、27.9 仍是过渡(阈值不能偷偷挪)', R.classifyRegime(21.9, 100,100,100).code === 'range' && R.classifyRegime(27.9, 110,105,100).code === 'transition');
check('ADX为null → unknown', R.classifyRegime(null, 1, 1, 1).code === 'unknown');

// ---- 3. 价格百分位带 ----
// closes 1..250，最新=250 → 250个里≤250的有250个 → 100%
let pb = R.pricePercentileBand(mk(250, i=>({close:i+1})));
check('最新是最高 → 100%分位, high带', pb.pct === 100 && pb.band === 'high');
// closes 1..249 后接最新=49.5：≤49.5的有1..49共49个+最新自己=50 → 50/250=20% → 恰好20算low带
const closes = mk(249, i=>i+1).concat([49.5]);
pb = R.pricePercentileBand(closes.map(c=>({close:c})));
check('恰好20%分位 → low带(铁底区)', pb.pct === 20 && pb.band === 'low');
// 1..249 + 最新=199.5 → 1..199共199个+自己=200 → 80% → high
pb = R.pricePercentileBand(mk(249, i=>i+1).concat([199.5]).map(c=>({close:c})));
check('恰好80% → high带', pb.pct === 80 && pb.band === 'high');
pb = R.pricePercentileBand(mk(249, i=>i+1).concat([124.5]).map(c=>({close:c})));
check('50% → mid带', pb.pct === 50 && pb.band === 'mid');
check('不足200根不下结论', R.pricePercentileBand(mk(150, i=>({close:i+1}))).band === 'unknown');

// ---- 4. 资金市证据清单 ----
// 5日: 价格 100→105(涨) 且 持仓 10000→10800(+8%,增) → 增仓上涨命中; 持仓相对前20日均值: 前20日均10000,最新10800=+8% <20% → 暴增不命中
function bars(price0, price1, hold0, hold1){
  return mk(30, i=>{ const base = i<24 ? price0 : price0 + (price1-price0)*(i-24)/5; const h = i<24 ? hold0 : hold0 + (hold1-hold0)*(i-24)/5;
    return {close:base, high:base+1, low:base-1, hold:h}; });
}
let cl = R.capitalChecklist(bars(100,105,10000,10800), null, {band:'mid', pct:50});
const hit = id=>cl.items.find(x=>x.id===id).hit;
check('增仓上涨命中(5日价↑且持仓↑)', hit('oi_up_price_up') === true);
check('持仓+8%不算暴增', hit('oi_surge') === false);
cl = R.capitalChecklist(bars(100,105,10000,12500), null, {band:'mid', pct:50});   // +25%，≥20%暴增
check('持仓+25%命中暴增(≥20%)', hit('oi_surge') === true);
cl = R.capitalChecklist(bars(100,95,10000,10800), null, {band:'mid', pct:50});    // 价跌仓增 → 不是增仓上涨
check('价格下跌+增仓不算增仓上涨', hit('oi_up_price_up') === false);
cl = R.capitalChecklist(bars(100,105,10000,9000), null, {band:'mid', pct:50});    // 减仓上涨
check('减仓上涨不算增仓上涨', hit('oi_up_price_up') === false);
cl = R.capitalChecklist(bars(100,105,10000,10800), {code:'retreat_from_high'}, {band:'high', pct:90});
check('外资高位撤退+价格高位+增仓上涨 = 3项命中', cl.count === 3 && hit('foreign_retreat') && hit('price_high'));
check('每项都带证据强度标签', cl.items.every(x=>['weak','none'].includes(x.evidence)));
check('未接入的项目被点名且不计数', cl.notWired.length >= 3 && cl.total === cl.items.length);
cl = R.capitalChecklist(bars(100,105,10000,10800), {code:'neutral_flat'}, {band:'mid', pct:50});
check('外资中性不命中', hit('foreign_retreat') === false && hit('foreign_crowded') === false);
cl = R.capitalChecklist([], null, {band:'unknown'});
check('没有K线不崩，计数0', cl.count === 0);

// ---- 5. 休息灯：默认关；开启且≥3项才亮；开关状态不影响清单本身 ----
check('默认关闭', R.restLamp({count:3}, false).on === false);
check('开启且<3项 → 不亮', R.restLamp({count:2}, true).lit === false);
check('开启且=3项 → 亮', R.restLamp({count:3}, true).lit === true && /纪律提示/.test(R.restLamp({count:3}, true).text));
check('亮灯文字声明"未回测"', /未回测|没有回测/.test(R.restLamp({count:3}, true).text));
check('关闭时即使5项也不亮', R.restLamp({count:5}, false).lit === false);

// ---- 6. 收盘定型标记 ----
// 北京时间15:00收盘，日盘交易时段 09:00-15:00(含10:15-10:30休息) ; 夜盘21:00-23:00
const E = window._eventCal;
check('日盘中(10:00)未定型', R.barFinal(E.bjToMs(2026,10,12,10,0), '2026-10-12') === false);
check('15:30已收盘 → 定型', R.barFinal(E.bjToMs(2026,10,12,15,30), '2026-10-12') === true);
check('K线日期早于今天 → 定型', R.barFinal(E.bjToMs(2026,10,12,10,0), '2026-10-09') === true);
check('周末(10-10周六)不判未定型', R.barFinal(E.bjToMs(2026,10,10,10,0), '2026-10-09') === true);

// ---- 7. 页面渲染 ----
['regimeContent'].forEach(makeEl);
window._nowMs = E.bjToMs(2026,10,12,10,0);
window._dailyBars = mk(260, i=>({date:`d${i}`, open:3000+i, high:3010+i, low:2990+i, close:3000+i, hold:10000+i}));
window._syncedData = {costAnchor:{available:true, beanCost:4434, mealCost:3954.1, mealCostLow:3775.4, mealCostHigh:4132.8, gap:-554.1, gapPct:-14, position:'below', mealSymbol:'M2701', mealPrice:3400, zsCents:1295, fx:6.8, params:{premium_cents:250, premium_step:50, tariff:0.03, vat:0.09, port_fee:100, crush_fee:150, asof:'2026-10-10', source_note:'x'}, note:'成本参照，不是回测过的信号'}};
R.render();
const html = makeEl('regimeContent').innerHTML, T = html.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');
check('渲染含行情状态与ADX数值', /行情状态/.test(T) && /ADX/.test(T));
check('渲染含百分位', /百分位/.test(T));
check('明说没有前向优势', /没有[^。]{0,30}(前向|预测)/.test(T));
check('今日K线未收盘提示', /未收盘/.test(T));
check('成本锚展示：理论成本3,954、盘面3,400、区间3,775~4,133', ['3,954','3,400','3,775','4,133'].every(s=>T.includes(s)));
check('成本锚声明参数日期与升贴水不可回测', /2026-10-10/.test(T) && /升贴水/.test(T));
check('渲染含休息灯开关(默认关)', /休息灯/.test(T) && !/🛑/.test(T));
check('渲染含未接入项目', /未接入/.test(T));
// ---- 8. 决策卡顶部：休息灯只在开启且亮时出现 ----
window._restLampOverride = false;
check('开关关：状态区没有🛑', !/🛑/.test(marketStateHtml(true, {direction:'中性', ratio:0})));
window._restLampOverride = true;
window._dailyBars = mk(260, i=>({date:`d${i}`, open:1, high:i+11, low:i+9, close:i+10, hold: i<255 ? 10000 : 10000 + (i-254)*600}));   // 价涨+持仓暴增+高位 = 3项
window._syncedData = {marketCapital:{available:true, state:{level:'yellow', label:'x', thresholdSource:'y'}, verdict:{code:'retreat_from_high', level:'yellow', short:'外资高位撤退中', label:'外资高位撤退中', lines:[], evidence:[]}}};
const sn = R.snapshot();
check('构造的3项全中', sn.cl.count === 4 || sn.cl.count === 3);
check('开关开+命中≥3：状态区出现🛑纪律提示', /🛑/.test(marketStateHtml(true, {direction:'中性', ratio:0})));
window._restLampOverride = null;
H.printSummary();
