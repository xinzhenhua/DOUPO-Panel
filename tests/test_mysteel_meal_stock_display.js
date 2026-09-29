const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

function resetStockFields(){
  makeEl('m_stock').value = '';
  makeEl('ai_stock');
  makeEl('ind_stock');
}

// ===================== 测试1：欄位是空的时自动填入 =====================
resetStockFields();
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelMealStock: {available: true, value: 65.32, date: '2026-09-19', source: 'Mysteel文章'},
};
refreshMysteelMealStock();
check('★欄位是空的时应该自动填入数值', makeEl('m_stock').value == '65.32');
check('★提示区应该显示自动抓取字样和数值', makeEl('ai_stock').innerHTML.includes('自动抓取') && makeEl('ai_stock').innerHTML.includes('65.32万吨'));

// ===================== 测试2：抓取成功时直接覆盖已有值 =====================
resetStockFields();
makeEl('m_stock').value = '80';
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelMealStock: {available: true, value: 65.32, date: '2026-09-19'},
};
refreshMysteelMealStock();
check('★抓取成功时应直接覆盖已有值(80→65.32)', makeEl('m_stock').value == '65.32');
check('提示区应该显示抓取到的值', makeEl('ai_stock').innerHTML.includes('65.32'));

// ===================== 测试3：★失败时应该显示明确原因+debug信息(不是这次才补的教训，直接从一开始就做对) =====================
resetStockFields();
makeEl('ai_stock').className = 'ai-suggest unavailable';
makeEl('ai_stock').innerHTML = '💡 尚未粘贴数据';
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelMealStock: {available: false, reason: '搜索结果为空(测试)', debug: {totalItemsChecked: 0}},
};
refreshMysteelMealStock();
check('★失败时应该替换掉默认的"尚未粘贴数据"文字', !makeEl('ai_stock').innerHTML.includes('尚未粘贴数据'));
check('★失败时应该显示明确的失败原因', makeEl('ai_stock').innerHTML.includes('自动抓取失败') && makeEl('ai_stock').innerHTML.includes('搜索结果为空(测试)'));

// 失败时：保存过的手动值保留，详情里如实说明失败
resetStockFields();
makeEl('m_stock').value = '80';
window._syncedData = {generatedAt: new Date().toISOString(), mysteelMealStock: {available: false, reason: '这次失败了'}};
refreshMysteelMealStock();
check('★失败时不清空保存过的手动值', makeEl('m_stock').value === '80');
check('★失败时如实显示失败原因', makeEl('ai_stock').innerHTML.includes('这次失败了'));

// ===================== 测试4：window._syncedData为空时不报错 =====================
delete window._syncedData;
try {
  refreshMysteelMealStock();
  check('★window._syncedData为空时不应该报错', true);
} catch(e) {
  check('★window._syncedData为空时不应该报错', false);
}


// ===================== 第N周标注(新版后端"全国主要区域大豆及豆粕库存统计"每周一期) =====================
resetStockFields();
window._syncedData = {generatedAt: new Date().toISOString(), mysteelMealStock: {available: true, value: 117.32, date: '2026-09-21', weekLabel: '2026年第38周'}};
refreshMysteelMealStock();
check('★提示区应该标出是第几周的库存统计(2026年第38周)', makeEl('ai_stock').innerHTML.includes('2026年第38周'));
check('提示区应该显示文章发布日期', makeEl('ai_stock').innerHTML.includes('2026-09-21'));
resetStockFields();
window._syncedData = {generatedAt: new Date().toISOString(), mysteelMealStock: {available: true, value: 117.32, date: '2026-09-21', weekLabel: null}};
refreshMysteelMealStock();
check('★没有weekLabel时不应该出现null/undefined', !makeEl('ai_stock').innerHTML.includes('null') && !makeEl('ai_stock').innerHTML.includes('undefined'));

H.printSummary();
