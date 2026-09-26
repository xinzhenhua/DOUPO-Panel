const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

function resetRmSpreadFields(){
  makeEl('m_rmspread').value = '';
  makeEl('ai_rmspread');
  makeEl('ind_rmspread');
}

// ===================== 测试1：区间中点格式 =====================
resetRmSpreadFields();
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelRmSpread: {available: true, value: 500, formatUsed: '区间中点', rangeLow: 480, rangeHigh: 520, date: '2026-07-09', source: 'Mysteel文章'},
};
refreshMysteelRmSpread();
check('★区间格式时应该自动填入中点值', makeEl('m_rmspread').value == '500');
check('★提示区应该显示"中点"字样(实际格式是"区间480-520元/吨的中点"，"区间"和"中点"被数字隔开)', makeEl('ai_rmspread').innerHTML.includes('中点'));
check('★提示区应该显示原始区间范围(480-520)，方便核对', makeEl('ai_rmspread').innerHTML.includes('480-520元/吨的中点'));

// ===================== 测试2：多城市单值平均格式 =====================
resetRmSpreadFields();
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelRmSpread: {available: true, value: 753.3, formatUsed: '多城市单值平均', citySamples: [740, 710, 810], date: '2026-08-28', source: 'Mysteel文章'},
};
refreshMysteelRmSpread();
check('★多城市格式时应该自动填入平均值', makeEl('m_rmspread').value == '753.3');
check('★提示区应该显示"3个城市"字样', makeEl('ai_rmspread').innerHTML.includes('3个城市'));
check('★提示区应该显示各城市原始数值(740/710/810)，方便核对平均值怎么算出来的', makeEl('ai_rmspread').innerHTML.includes('740/710/810'));

// ===================== 测试3：欄位已有值时不强制覆盖 =====================
resetRmSpreadFields();
makeEl('m_rmspread').value = '600';
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelRmSpread: {available: true, value: 500, formatUsed: '区间中点', rangeLow: 480, rangeHigh: 520, date: '2026-07-09'},
};
refreshMysteelRmSpread();
check('★欄位已有值时不应该被覆盖', makeEl('m_rmspread').value === '600');
check('提示区依然应该显示抓取到的值供参考', makeEl('ai_rmspread').innerHTML.includes('500'));

// ===================== 测试4：抓取失败/无数据时不报错 =====================
resetRmSpreadFields();
window._syncedData = {generatedAt: new Date().toISOString(), mysteelRmSpread: {available: false, reason: '搜索结果为空'}};
try {
  refreshMysteelRmSpread();
  check('★抓取失败时不应该报错', true);
} catch(e) {
  check('★抓取失败时不应该报错', false);
}

delete window._syncedData;
try {
  refreshMysteelRmSpread();
  check('★window._syncedData为空时不应该报错', true);
} catch(e) {
  check('★window._syncedData为空时不应该报错', false);
}

H.printSummary();
