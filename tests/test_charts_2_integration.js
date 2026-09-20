const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


// ===================== 集成测试1：干旱监测应该包含条形图 =====================
elements['droughtBadge'] = makeEl('droughtBadge');
elements['droughtContent'] = makeEl('droughtContent');
const mockByState = {};
['IA','IL','MN','IN','NE','OH','MO','SD','ND','KS','MI','WI'].forEach((st,i)=>{
  mockByState[st] = {available:true, anomalous:false, d0:10,d1:5,d2:i*2,d3:0,d4:0, severeOrWorsePct:i*2, validDate:'2026-07-07T00:00:00'};
});
renderDrought({available:true, anomalous:false, byState:mockByState, avgSevereOrWorsePct:8.0, simpleSevereOrWorsePct:11.0}, new Date().toISOString());
check('干旱监测渲染结果应该包含<svg>条形图', elements['droughtContent'].innerHTML.includes('<svg'));
check('干旱监测的条形图应该在alert-box之后(先看结论再看图)', elements['droughtContent'].innerHTML.indexOf('alert-box') < elements['droughtContent'].innerHTML.indexOf('<svg'));

// ===================== 集成测试2：NOAA展望应该包含条形图 =====================
elements['noaaOutlookBadge'] = makeEl('noaaOutlookBadge');
elements['noaaOutlookContent'] = makeEl('noaaOutlookContent');
const mockNoaaByState = {};
['IA','IL','MN','IN','NE','OH','MO','SD','ND','KS','MI','WI'].forEach((st,i)=>{
  mockNoaaByState[st] = {available:true, worseningCount:i, totalPoints:8, worseningPct:i*10, dominantOutlook:'No_Drought', dominantOutlookLabel:'预计无旱', targetPeriod:'Jul 2026'};
});
renderNoaaOutlook({available:true, byState:mockNoaaByState, avgWorseningPct:15.0, simpleWorseningPct:18.0, overallSignal:0}, new Date().toISOString());
check('NOAA展望渲染结果应该包含<svg>条形图', elements['noaaOutlookContent'].innerHTML.includes('<svg'));

// ===================== 集成测试3：综合预警应该包含仪表盘+状态点图 =====================
['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import'].forEach(id=>{
  elements[id] = makeEl(id);
  elements[id].value = '';
});
elements['m_crush'].value = '35'; // <40，触发偏多
elements['ind_crush']=makeEl('ind_crush');elements['ind_stock']=makeEl('ind_stock');
elements['ind_basis']=makeEl('ind_basis');elements['ind_arrival']=makeEl('ind_arrival');
elements['ind_hogratio']=makeEl('ind_hogratio');elements['ind_sows']=makeEl('ind_sows');
elements['ind_import']=makeEl('ind_import');
elements['alertContent'] = makeEl('alertContent');
window._weatherRisk = 'high'; // 触发至少一个信号，避免"数据不足"分支
updateOverallAlert();
check('综合预警应该包含仪表盘(gauge的特征：包含"偏空"和"偏多"标签)', elements['alertContent'].innerHTML.includes('偏空') && elements['alertContent'].innerHTML.includes('偏多'));
check('综合预警应该包含供需二栏表格(取代已移除的状态点图)', elements['alertContent'].innerHTML.includes('<table') && elements['alertContent'].innerHTML.includes('供应') && elements['alertContent'].innerHTML.includes('需求'));
check('综合预警应该包含仪表盘的<svg>(现在只有1个图，点图已移除)', (elements['alertContent'].innerHTML.match(/<svg/g)||[]).length === 1);
check('仪表盘应该在alert-box结论之前(先看仪表盘全局印象，再看文字明细)', elements['alertContent'].innerHTML.indexOf('<svg') < elements['alertContent'].innerHTML.indexOf('alert-box'));


H.printSummary();
