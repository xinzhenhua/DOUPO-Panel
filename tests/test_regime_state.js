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
check('★资金市清单/休息灯函数已移除', R.capitalChecklist === undefined && R.restLamp === undefined);

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

// ---- 4. 用后端补齐的序列算百分位(新合约历史不够时) ----
// 本合约只有150根(<200不下结论)；后端pricePosition给了260根(前110根是换算的)，最后一个点用页面当前K线
window._dailySymbol = 'M2701';
const own150 = mk(150, i=>({close:i+111}));                      // 111..260
const extCloses = mk(260, i=>i+1);                                // 1..260
let pe = R.pricePercentileBand(own150, {symbol:'M2701', closes:extCloses, ownCount:150, extendedCount:110});
check('★补齐后能算：最新260在1..260里是100%分位, 其中110日为换算', pe.pct === 100 && pe.n === 260 && pe.extN === 110 && pe.band === 'high');
pe = R.pricePercentileBand(own150, {symbol:'M2705', closes:extCloses, ownCount:150, extendedCount:110});
check('★序列属于别的合约(symbol对不上)就不用，仍然"数据不足"', pe.band === 'unknown' && pe.n === 150);
const own150b = own150.slice(0, 149).concat([{close:50.5}]);       // 页面最新收盘50.5：≤50.5的有1..50共50个+自己=51 → 51/260=19.6%
pe = R.pricePercentileBand(own150b, {symbol:'M2701', closes:extCloses, ownCount:150, extendedCount:110});
check('★最后一点用页面当前收盘(50.5)而不是序列里的260 → 19.6%分位, low带', pe.pct === 19.6 && pe.band === 'low');

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
window._dailySymbol = 'M2701';
window._dailyBars = mk(260, i=>({date:`d${i}`, open:3000+i, high:3010+i, low:2990+i, close:3000+i, hold:10000+i}));
const mkB = (bean, cost, lo, hi, gap, pct, pos, tariff, prem)=>({available:true, beanCost:bean, mealCost:cost, mealCostLow:lo, mealCostHigh:hi, gap, gapPct:pct, position:pos, mealPrice:3400, zsCents:1300, fx:6.8, params:{premium_cents:prem, premium_step:50, tariff, vat:0.09, port_fee:100, crush_fee:150, asof:'2026-10-10', premium_confirmed:false, ship:'测试船期', note:'测试说明'}});
window._selectedContract = 'jan';
window._syncedData = {costAnchor:{available:true, fx:6.8, contracts:{
  jan:{cbotSymbol:'ZSX26.CBT', zsCents:1300, zsDate:'2026-10-09', zsExact:true, zsNote:'', mealSymbol:'M2701', primary:'us', brazil:mkB(4434,3954.1,3775.4,4132.8,-554.1,-14,'below',0.03,240), us:mkB(4793,4410,4230,4590,-1010,-22.9,'below',0.13,280)},
  may:{cbotSymbol:'ZS=F', zsCents:1295, zsDate:'2026-10-09', zsExact:false, zsNote:'取不到对应月份的CBOT合约，退回近月连续合约，基准合约可能和升贴水不一致', mealSymbol:'M2705', primary:'brazil', brazil:mkB(4400,3900,3720,4080,-600,-15,'below',0.03,119), us:{available:false, reason:'测试：美豆缺价'}},
  sep:{cbotSymbol:'ZSN27.CBT', zsCents:1300, zsDate:'2026-10-09', zsExact:true, zsNote:'', mealSymbol:'M2709', primary:null, brazil:mkB(4300,3800,3700,3900,-400,-10,'below',0.03,165), us:mkB(4600,4100,4000,4200,-700,-17,'below',0.13,268)}}}};
R.render();
const html = makeEl('regimeContent').innerHTML, T = html.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');
check('价格位置排在行情判断(ADX)前面', T.indexOf('价格位置') >= 0 && T.indexOf('价格位置') < T.indexOf('ADX'));
check('渲染含行情判断与ADX数值', /行情判断/.test(T) && /ADX/.test(T));
check('明说没有前向优势', /没有[^。]{0,30}(前向|预测)/.test(T));
check('今日K线未收盘提示', /未收盘/.test(T));
check('★资金市清单和休息灯已移除', !/资金市清单|休息灯|🛑/.test(T));
check('成本锚(1月)：美豆为主要来源，展示4,410/4,230/4,590，关税13%；巴西豆标参考', ['4,410','4,230','4,590','关税13%','关税3%'].every(s=>T.includes(s)) && /美豆 【该合约主要来源】/.test(T) && /巴西豆 【参考】/.test(T));
check('成本锚声明升贴水未经核实/无法回测', /升贴水未经核实/.test(T) && /无法回测/.test(T));
check('展示CBOT基准合约ZSX26且精确取到时不报警', T.includes('ZSX26.CBT') && !/基准合约可能/.test(T));
window._selectedContract = 'may'; R.render();
const T2 = makeEl('regimeContent').innerHTML.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');
check('★5月合约：巴西豆为主要来源，M2705数字3,900，不再显示1月的4,410；退回近月时有⚠️', T2.includes('M2705') && T2.includes('3,900') && !T2.includes('4,410') && /巴西豆 【该合约主要来源】/.test(T2) && /基准合约可能/.test(T2));
check('某一豆源不可用时单独说明，不影响另一个', /美豆 【参考】 ：测试：美豆缺价/.test(T2));
window._selectedContract = 'sep'; R.render();
const T3 = makeEl('regimeContent').innerHTML.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');
check('★9月合约：巴西豆和美豆都算，且都不标"主要"或"参考"', T3.includes('ZSN27.CBT') && T3.includes('4,100') && T3.includes('3,800') && !/【该合约主要来源】|【参考】/.test(T3));
window._selectedContract = 'foo'; R.render();
check('所选合约无数据 → 明说暂无，不拿别的合约凑', /当前所选合约\(foo\)暂无数据/.test(makeEl('regimeContent').innerHTML));
window._selectedContract = 'jan';
H.printSummary();
