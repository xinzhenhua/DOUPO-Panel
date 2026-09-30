// ============================================================================
// 历史分位展示：historyBlock + 各指标卡片/ESR/PSD详情里的接入
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
window._selectedContract = 'sep';
const dayStr = n => new Date(Date.now() - n*86400000).toISOString().slice(0,10);
const hist = (o)=>Object.assign({n:60, minPoints:12, asOf:'2026-09', since:'2021-09', percentile:88.3, min:5.94, max:16.3, median:12.45, seasonal:null}, o||{});

// ===================== 1. historyBlock =====================
check('没有history字段(latest.json还是旧版)：什么都不显示，不出现undefined', historyBlock(undefined)==='' && historyBlock(null)==='' && historyBlock({})==='');
let t = historyBlock(hist({percentile:null, n:5, since:'2026-05', min:10, max:12}), {unit:'%'});
check('★样本不足：显示"历史积累中"、已有期数、起点，不给百分位', t.includes('历史积累中') && t.includes('已有5期') && t.includes('自2026-05') && t.includes('满12期') && !t.includes('<b>'));
check('样本不足但有区间时给出目前区间', t.includes('目前区间10～12%'));
t = historyBlock(hist({percentile:null, n:0, since:null, min:null, max:null}));
check('一个点都没有：只说积累中，不出现null/undefined/NaN', t.includes('已有0期') && !/null|undefined|NaN/.test(t));
t = historyBlock(hist(), {unit:'%'});
check('★有分位：显示百分位+区间标签+期数+起点+最小/最大/中位', t.includes('<b>88.3%</b>(偏高)') && t.includes('共60期(2021-09起)') && t.includes('最低5.94～最高16.3%') && t.includes('中位12.45%'));
check('分位区间标签：<20偏低，>80偏高，其余中等', historyBlock(hist({percentile:12})).includes('(偏低)') && historyBlock(hist({percentile:50})).includes('(中等)') && historyBlock(hist({percentile:81})).includes('(偏高)') && historyBlock(hist({percentile:80})).includes('(中等)'));
t = historyBlock(hist({seasonal:{month:9, n:5, percentile:92.5, median:11.2}}), {unit:'%'});
check('★同月分位：显示月份、往年同月个数和中位', t.includes('同月(9月)分位：<b>92.5%</b>') && t.includes('5个往年同月') && t.includes('中位11.2%'));
check('同月样本不足(percentile=null)时不显示同月分位', !historyBlock(hist({seasonal:{month:9, n:2, percentile:null, median:null}})).includes('同月'));
check('大数字用千分位(出口吨数)', historyBlock(hist({min:400000, max:9000000, median:1200000}), {unit:'吨'}).includes('最低400,000～最高9,000,000吨'));
check('basis字段(出口净销售用近4周合计)写进标签', historyBlock(hist({basis:'近4周净销售合计'})).includes('近4周净销售合计，共60期'));

// 一致性提示：pol=-1(数值越高越偏空，如库消比)
check('★偏空信号 + 历史分位高(88%)：一致，不提示', !historyBlock(hist({percentile:88}), {pol:-1, dir:-1}).includes('⚠️'));
t = historyBlock(hist({percentile:35}), {pol:-1, dir:-1});
check('★偏空信号 + 历史分位只有35%：提示"阈值可能偏松"，并写出分位', t.includes('⚠️') && t.includes('判<b>偏空</b>') && t.includes('35%') && t.includes('校准'));
check('★偏多信号(库消比低) + 历史分位高(70%)：提示不一致', historyBlock(hist({percentile:70}), {pol:-1, dir:1}).includes('判<b>偏多</b>'));
check('偏多信号 + 历史分位低(15%)：一致，不提示', !historyBlock(hist({percentile:15}), {pol:-1, dir:1}).includes('⚠️'));
check('★pol=+1(数值越高越偏多，如基差)：偏多信号 + 分位高 → 一致；偏多信号 + 分位20% → 不一致', !historyBlock(hist({percentile:80}), {pol:1, dir:1}).includes('⚠️') && historyBlock(hist({percentile:20}), {pol:1, dir:1}).includes('⚠️'));
check('★中性区间但历史分位已到95%(极端)：提示阈值可能偏宽', historyBlock(hist({percentile:95}), {pol:-1, dir:0}).includes('ℹ️') && historyBlock(hist({percentile:5}), {pol:-1, dir:0}).includes('ℹ️'));
check('中性区间且分位居中：不提示', !/⚠️|ℹ️/.test(historyBlock(hist({percentile:50}), {pol:-1, dir:0})));
check('样本不足时不做一致性判断(没有分位可比)', !historyBlock(hist({percentile:null}), {pol:-1, dir:-1}).includes('⚠️'));
check('没传pol/dir时不做一致性判断', !/⚠️|ℹ️/.test(historyBlock(hist({percentile:5}), {})));

// ===================== 2. 指标卡片详情接入 =====================
const AUTO = window._autoIndicators;
function resetKey(key){ const c = window._autoByKey[key]; makeEl(c.inputId).value=''; makeEl('ai_'+key).innerHTML=''; makeEl('badge_'+key); makeEl('alert_'+key); makeEl('ind_'+key); makeEl('alertContent'); window._indState[key] = {}; }
resetKey('stu');
window._syncedData = {mysteelMealStu:{available:true, value:16.04, monthLabel:'2026年9月', isForecast:true, method:'stated', methodLabel:'文章明示', recordSource:'body',
  stockWan:125, consumptionWan:779, productionWan:795, next:null, trend:null, weeklyCheck:null, date:dayStr(29), articleAgeDays:29, articleTitle:'x',
  history: hist({percentile:91.2, seasonal:{month:9, n:5, percentile:80, median:14}})}};
refreshMysteelMealStu();
let ai = makeEl('ai_stu').innerHTML;
check('★库消比卡片详情里显示历史分位和同月分位', ai.includes('历史分位：<b>91.2%</b>') && ai.includes('同月(9月)分位'));
check('★库消比16.04%判偏空、历史分位91%：一致，无提示', !ai.includes('⚠️ 绝对阈值'));

// 不一致：库消比14.5%判偏空，但历史分位只有40%
resetKey('stu');
window._syncedData.mysteelMealStu = Object.assign({}, window._syncedData.mysteelMealStu, {value:14.5, history:hist({percentile:40})});
refreshMysteelMealStu();
check('★库消比14.5%(≥14判偏空)但历史分位40%：详情里提示阈值可能偏松', makeEl('ai_stu').innerHTML.includes('绝对阈值判<b>偏空</b>') && makeEl('ai_stu').innerHTML.includes('40%'));

// 基差(pol=+1)：-100判偏空，历史分位若只有60%(即基差并不算低)也应提示
resetKey('basis');
window._syncedData = {mysteelBasis:{available:true, value:-100, city:'日照', date:dayStr(1), usedFallback:false, history:hist({percentile:60, n:400})}};
refreshMysteelBasis();
check('★基差(数值越高越偏多)：-100判偏空但历史分位60%(不算低)，提示不一致', makeEl('ai_basis').innerHTML.includes('绝对阈值判<b>偏空</b>'));

// 没有history字段：卡片照常，不出现undefined
resetKey('crush');
window._syncedData = {mysteelCrushRate:{available:true, value:69.98, date:dayStr(2)}};
refreshMysteelCrushRate();
check('没有history字段时卡片照常显示，无undefined', makeEl('ai_crush').innerHTML.includes('69.98%') && !makeEl('ai_crush').innerHTML.includes('undefined') && !makeEl('ai_crush').innerHTML.includes('历史分位'));
// 刚开始积累
resetKey('crush');
window._syncedData = {mysteelCrushRate:{available:true, value:69.98, date:dayStr(2), history:hist({percentile:null, n:3, since:'2026-09-15', min:65, max:70})}};
refreshMysteelCrushRate();
check('★刚开始积累(3期)：详情里显示"历史积累中"', makeEl('ai_crush').innerHTML.includes('历史积累中') && makeEl('ai_crush').innerHTML.includes('已有3期'));
// 历史分位不影响评分：同样的值有没有history，投票结果一样
resetKey('crush');
window._syncedData = {mysteelCrushRate:{available:true, value:69.98, date:dayStr(2), history:hist({percentile:5})}};
refreshMysteelCrushRate();
check('★历史分位只展示，不改变信号(开机率69.98%仍判偏空，即使分位只有5%)', makeEl('alert_crush').innerHTML.includes('alert-box bear'));

// ===================== 3. PSD / ESR 详情 =====================
elements['psdBadge']=makeEl('psdBadge'); elements['psdContent']=makeEl('psdContent'); elements['esrBadge']=makeEl('esrBadge'); elements['esrContent']=makeEl('esrContent');
const psd = {available:true, commodity:'Oilseed, Soybean', marketYear:2026, marketYearLabel:'2026/27', wasdeVintage:'2026年09月版', endingStocks:8436, production:120700, domesticConsumption:61000, exports:62000, totalUse:123000, stocksToUsePct:6.9, unit:'千公吨',
  history: hist({n:20, minPoints:12, since:'2006', percentile:55, min:2.6, max:24.4, median:8.1})};
renderPsd(psd, new Date().toISOString());
check('★PSD详情：历史位置(按市场年度)', makeEl('psdContent').innerHTML.includes('历史分位(按市场年度)：<b>55%</b>') && makeEl('psdContent').innerHTML.includes('共20期(2006起)'));
renderPsd(Object.assign({}, psd, {stocksToUsePct:4.0, history:hist({percentile:55, n:20})}), new Date().toISOString());
check('★美豆库消比4%判偏多(<5%)但历史分位55%(高于一半年份)：提示不一致——正是要校准的5%/10%暂定阈值', makeEl('psdContent').innerHTML.includes('绝对阈值判<b>偏多</b>'));
renderPsd(Object.assign({}, psd, {history:undefined}), new Date().toISOString());
check('PSD没有history字段时不显示"历史位置"行', !makeEl('psdContent').innerHTML.includes('历史位置'));

const esr = {available:true, commodity:'Soybeans(大豆)', weekEnding:'2026-09-24', marketYearUsed:2026, dataAgeDays:5, isStale:false, netSalesMT:1200000, prevNetSalesMT:800000, avg4wNetSalesMT:700000,
  vs4wAvgPct:71.4, wowChangePct:50, shipmentsMT:900000, chinaNetSalesMT:450000, source:'x',
  history: hist({n:300, since:'2018-01-04', percentile:93, min:400000, max:9000000, median:2500000, basis:'近4周净销售合计', seasonal:{month:9, n:8, percentile:70, median:2000000}})};
renderEsr(esr, new Date().toISOString());
let e = makeEl('esrContent').innerHTML;
check('★ESR详情：近4周合计的历史分位+同月分位', e.includes('近4周净销售合计，共300期') && e.includes('<b>93%</b>') && e.includes('同月(9月)分位') && e.includes('1,200,000') === true);
renderEsr(Object.assign({}, esr, {history:undefined}), new Date().toISOString());
check('ESR没有history字段时不报错、不显示历史位置', !makeEl('esrContent').innerHTML.includes('历史位置') && !makeEl('esrContent').innerHTML.includes('undefined'));

H.printSummary();
