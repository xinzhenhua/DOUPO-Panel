const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


// ===================== 测试1：renderTieredStateRows核心逻辑 =====================
const testRows = {
  IA: '<div>IA核心州</div>', ND: '<div>ND次要州</div>', KS: '<div>KS次要州</div>',
};
const tieredHtml = renderTieredStateRows(testRows, '测试详情');
check('★行为已变更(本轮要求)：核心州内容现在也应该收进details里(不再单独常驻)', tieredHtml.indexOf('IA核心州') > tieredHtml.indexOf('<details'));
check('次要州(ND/KS)内容应该被包在<details>里', tieredHtml.includes('<details') && tieredHtml.includes('ND次要州') && tieredHtml.includes('KS次要州'));
check('details默认应该是收起的(没有open属性)', !tieredHtml.includes('<details open') && !tieredHtml.includes('open>'));

// ===================== 测试2：drought监测的分层显示 =====================
elements['droughtBadge'] = makeEl('droughtBadge');
elements['droughtContent'] = makeEl('droughtContent');
const mockByState = {};
['IA','IL','MN','IN','NE','OH','MO','SD','ND','KS','MI','WI'].forEach(st=>{
  mockByState[st] = {available:true, anomalous:false, d0:10,d1:5,d2:2,d3:0,d4:0, severeOrWorsePct:2, validDate:'2026-07-07T00:00:00'};
});
renderDrought({available:true, anomalous:false, byState:mockByState, avgSevereOrWorsePct:2.0, simpleSevereOrWorsePct:2.0}, new Date().toISOString());
check('★行为已变更(本轮要求)：干旱监测逐州明细现在全部收进details，只有alert-box常驻', elements['droughtContent'].innerHTML.indexOf('alert-box') < elements['droughtContent'].innerHTML.indexOf('<details'));
check('12州干旱监测：次要州(北达科他)应该在details里', elements['droughtContent'].innerHTML.includes('北达科他'));
check('alert-box应该显示"12州加权平均"而不是写死的"八州"或简单平均', elements['droughtContent'].innerHTML.includes('12州加权平均'));

// ===================== 测试3：PSD现在应该有alert-box了 =====================
elements['psdBadge'] = makeEl('psdBadge');
elements['psdContent'] = makeEl('psdContent');
renderPsd({available:true, marketYear:2026, endingStocks:300, production:52000, domesticConsumption:34000, wasdeVintage:'2026年06月版'}, new Date().toISOString());
check('PSD现在应该有alert-box展示结论(之前完全没有)', elements['psdContent'].innerHTML.includes('alert-box'));
check('PSD的alert-box应该带偏多/偏空文字', elements['psdContent'].innerHTML.includes('偏多') || elements['psdContent'].innerHTML.includes('偏空'));
check('PSD详细数据应该被收进details里', elements['psdContent'].innerHTML.includes('<details') && elements['psdContent'].innerHTML.includes('详细数据'));

// ===================== 测试4：CBOT现在应该有alert-box，且方向正确 =====================
elements['cbotBadge'] = makeEl('cbotBadge');
elements['cbotContent'] = makeEl('cbotContent');
renderCbot({available:true, price:310.5, change:5.2, changePct:1.7, asOf:new Date().toISOString(), source:'test'}, new Date().toISOString());
check('CBOT现在应该有alert-box(之前完全没有)', elements['cbotContent'].innerHTML.includes('alert-box'));
check('CBOT上涨(change=5.2>0)应该显示"偏多"而不是之前反过来的"偏空"', elements['cbotContent'].innerHTML.includes('偏多'));
check('window._cbotSignal方向应该正确：chg>0时应为1(不是之前反过来的-1)', window._cbotSignal === 1);
check('CBOT应明确标注"仅供参考，不计入综合评分"', elements['cbotContent'].innerHTML.includes('不计入'));


H.printSummary();
