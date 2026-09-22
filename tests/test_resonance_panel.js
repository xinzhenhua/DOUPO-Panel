global.LightweightCharts = { createChart(){ return { addSeries(){return{setData(){}};}, timeScale(){return{fitContent(){},subscribeVisibleLogicalRangeChange(){},setVisibleLogicalRange(){}};}, applyOptions(){}, remove(){} }; }, CandlestickSeries:{}, LineSeries:{}, HistogramSeries:{} };
global.ResizeObserver = class { observe(){} };

const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：computeForeignCapitalActivity =====================
check('★数据不可用时应该返回unavailable状态', computeForeignCapitalActivity(null).status === 'unavailable');
check('★available:false时也应该返回unavailable状态', computeForeignCapitalActivity({available:false}).status === 'unavailable');

const quietData = {available:true, tables:{netLong:[{rank:1,name:'国泰君安',value:1000,change:50,isForeign:false}]}};
const quietResult = computeForeignCapitalActivity(quietData);
check('★没有外资记录时应该返回quiet状态', quietResult.status === 'quiet');
check('quiet状态下entries应该是空数组', Array.isArray(quietResult.entries) && quietResult.entries.length===0);

const activeData = {available:true, tables:{
  netLong: [{rank:1,name:'国泰君安',value:5000,change:100,isForeign:false}],
  netShort: [{rank:2,name:'高盛期货',value:3000,change:-800,isForeign:true}],
  longUp: [{rank:5,name:'摩根士丹利期货',value:2000,change:200,isForeign:true}],
}};
const activeResult = computeForeignCapitalActivity(activeData);
check('★有外资记录时应该返回active状态', activeResult.status === 'active');
check('★应该找出变化幅度绝对值最大的一条(高盛-800 > 大摩+200)', activeResult.label.includes('高盛期货'));
check('★isGoldman字段应该正确标注', activeResult.isGoldman === true);
check('entries应该收集全部外资记录(高盛+大摩两条)，不是只有最显著那条', activeResult.entries.length === 2);

const activeNonGoldman = {available:true, tables:{
  longDown: [{rank:1,name:'瑞银期货',value:1500,change:-900,isForeign:true}],
}};
const nonGoldmanResult = computeForeignCapitalActivity(activeNonGoldman);
check('★非高盛外资活跃时isGoldman应该是false', nonGoldmanResult.isGoldman === false);

// ===================== 测试2：computeResonanceStatus =====================
const goldmanActive = {status:'active', isGoldman:true, label:'高盛期货出现在净空头榜(-800手)'};
const nonGoldmanActive = {status:'active', isGoldman:false, label:'瑞银期货出现在多头减仓榜(-900手)'};
const quiet = {status:'quiet', label:'本次未侦测到已确认外资机构进入前20名榜单'};
const unavailable = {status:'unavailable', label:'外资持仓数据暂不可用'};

const r1 = computeResonanceStatus('偏多', '偏多', goldmanActive);
check('★高盛活跃时应该是warn样式，不管技术面基本面是否同向', r1.cls === 'warn');
check('★高盛活跃时标题应该明确提到高盛', r1.title.includes('高盛'));

const r2 = computeResonanceStatus('偏多', '偏多', nonGoldmanActive);
check('非高盛外资活跃也应该是warn样式', r2.cls === 'warn');
check('非高盛外资活跃的说明文字应该提示可能是对冲/客户盘', r2.detail.includes('对冲') || r2.detail.includes('客户'));

const r3 = computeResonanceStatus('偏多', '偏多', quiet);
check('★技术面基本面同向(偏多)+外资平静，应该是bull样式', r3.cls === 'bull');
check('同向偏多的标题应该体现出"技术面与基本面同向"', r3.title.includes('技术面') && r3.title.includes('基本面'));

const r4 = computeResonanceStatus('偏空', '偏空', quiet);
check('★技术面基本面同向(偏空)+外资平静，应该是bear样式', r4.cls === 'bear');

const r5 = computeResonanceStatus('偏多', '偏空', quiet);
check('★技术面与基本面方向不一致时应该是neutral样式', r5.cls === 'neutral');
check('方向不一致的标题应该同时体现两边的方向', r5.title.includes('偏多') && r5.title.includes('偏空'));

const r6 = computeResonanceStatus(null, '偏多', quiet);
check('★技术面数据缺失时应该提示数据不足，而不是误判成方向不一致', r6.title.includes('数据不足'));

const r7 = computeResonanceStatus('偏多', null, quiet);
check('★基本面数据缺失时也应该提示数据不足', r7.title.includes('数据不足'));

const r8 = computeResonanceStatus('中性', '中性', quiet);
check('两边都是中性时不应该被误判成"同向"(中性不算方向一致的共振)', r8.cls !== 'bull' && r8.cls !== 'bear');

// 外资数据不可用时，不应该报错，应该用neutral兜底且提示外资数据不可用
const r9 = computeResonanceStatus('偏多', '偏多', unavailable);
check('★外资数据不可用时不应该报错，应该正常给出同向判断并注明外资数据缺失', r9.cls === 'bull' && r9.detail.includes('外资数据暂不可用'));

// ===================== 测试3：renderResonancePanel读取window状态并渲染 =====================
makeEl('resonanceContent');
window._technicalDirection = '偏多';
window._fundamentalDirection = '偏多';
window._foreignActivity = quiet;
renderResonancePanel();
check('★renderResonancePanel应该把三方状态都写进HTML里', 
  makeEl('resonanceContent').innerHTML.includes('技术面：偏多') &&
  makeEl('resonanceContent').innerHTML.includes('基本面：偏多') &&
  makeEl('resonanceContent').innerHTML.includes('外资动向'));
check('renderResonancePanel应该带alert-box样式类', makeEl('resonanceContent').innerHTML.includes('alert-box bull'));

// 三方状态还没任何一方算完时(初始状态)，不应该报错
delete window._technicalDirection;
delete window._fundamentalDirection;
delete window._foreignActivity;
makeEl('resonanceContent');
renderResonancePanel();
check('★三方状态都还没算出来时(页面刚加载)，不应该报错，应该显示加载中/数据不足', 
  makeEl('resonanceContent').innerHTML.includes('加载中') || makeEl('resonanceContent').innerHTML.includes('数据不足'));

// resonanceContent容器不存在时(理论上不该发生，但防御一下)，不应该报错
const originalGetElementById = document.getElementById;
document.getElementById = (id) => id==='resonanceContent' ? null : originalGetElementById(id);
try {
  renderResonancePanel();
  check('★resonanceContent容器不存在时不应该抛异常', true);
} catch(e) {
  check('★resonanceContent容器不存在时不应该抛异常', false);
} finally {
  document.getElementById = originalGetElementById;
}

// ===================== 测试4：renderKline整合——技术面方向和外资活跃度应该正确写入window =====================
global.LightweightCharts = { createChart(){ return { addSeries(){return{setData(){}};}, timeScale(){return{fitContent(){},subscribeVisibleLogicalRangeChange(){},setVisibleLogicalRange(){}};}, applyOptions(){}, remove(){} }; }, CandlestickSeries:{}, LineSeries:{}, HistogramSeries:{} };
global.ResizeObserver = class { observe(){} };
makeEl('klineBadge'); makeEl('klineContent'); makeEl('resonanceContent');
['klineChartContainer','klineVolumeContainer'].forEach(id=>{ const el=makeEl(id); el.clientWidth=700; el.clientHeight=200; });
makeEl('klineCardTitle');

// 构造一段明确上涨趋势的K线数据，让技术面因子大概率偏多，便于断言方向
const bars = [];
for(let i=0;i<80;i++){
  const base = 2800 + i*3;
  bars.push({date:`2026-0${(i%9)+1}-0${(i%9)+1}`, open:base, high:base+15, low:base-10, close:base+10, volume:1000, hold:50000});
}
const dailyData = {available:true, symbol:'M2701', totalBarsReturned:bars.length, bars, source:'测试'};
const posData = {available:true, date:'2026-09-19', tables:{netLong:[{rank:1,name:'高盛期货',value:5000,change:600,isForeign:true}]}, source:'测试'};

renderKline(dailyData, {available:false, reason:'测试'}, new Date().toISOString(), posData);
check('★renderKline应该把技术面方向写入window._technicalDirection', ['偏多','偏空','中性'].includes(window._technicalDirection));
check('★持续上涨的K线数据，技术面方向大概率应该是偏多', window._technicalDirection === '偏多');
check('★renderKline应该把外资活跃度写入window._foreignActivity(高盛出现)', window._foreignActivity && window._foreignActivity.status==='active' && window._foreignActivity.isGoldman===true);
check('renderKline执行完应该已经刷新了共振面板', makeEl('resonanceContent').innerHTML.includes('技术面'));

// ===================== 测试5：updateOverallAlert整合——基本面方向应该正确写入window =====================
window._selectedContract = 'sep';
function resetManualFieldsForResonance(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import'].forEach(id=>{
    const el = makeEl(id); el.value='';
  });
}
resetManualFieldsForResonance();
makeEl('m_crush').value='35'; makeEl('m_stock').value='40'; makeEl('m_basis').value='10';
makeEl('m_arrival').value='700'; makeEl('m_hogratio').value='8'; makeEl('m_sows').value='3600';
makeEl('m_import').value='700';
window._weatherRisk = 'high'; window._droughtSignal = 1; window._noaaOutlookSignal = 1; window._soyCondSignal = 1;
window._esrSignal = 1; window._fxSignal = 1; window._psdSignal = 1;
makeEl('alertContent');
updateOverallAlert();
check('★评分偏多时(11个信号全偏多)，updateOverallAlert应该把window._fundamentalDirection设为偏多', window._fundamentalDirection === '偏多');

// 完全没填任何手动数据+没有天气信号时，应该是数据不足的早退路径，此时方向应该明确置空
resetManualFieldsForResonance();
window._weatherRisk = null; window._droughtSignal = null; window._noaaOutlookSignal = null; window._soyCondSignal = null;
window._esrSignal = null; window._fxSignal = null; window._psdSignal = null;
makeEl('alertContent');
updateOverallAlert();
check('★完全没有数据时(早退路径)，window._fundamentalDirection应该被明确置空，而不是留着上次的旧值', window._fundamentalDirection === null);

H.printSummary();
