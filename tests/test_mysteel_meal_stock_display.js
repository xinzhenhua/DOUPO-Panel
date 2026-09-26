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

// ===================== 测试2：欄位已有值时不强制覆盖 =====================
resetStockFields();
makeEl('m_stock').value = '80';
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelMealStock: {available: true, value: 65.32, date: '2026-09-19'},
};
refreshMysteelMealStock();
check('★欄位已有值时不应该被覆盖', makeEl('m_stock').value === '80');
check('提示区依然应该显示抓取到的值供参考', makeEl('ai_stock').innerHTML.includes('65.32'));

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

// 已有真实内容时失败不应该覆盖
resetStockFields();
makeEl('ai_stock').className = 'ai-suggest fresh';
makeEl('ai_stock').innerHTML = '📋 之前的真实结果';
window._syncedData = {generatedAt: new Date().toISOString(), mysteelMealStock: {available: false, reason: '这次失败了'}};
refreshMysteelMealStock();
check('★区域已有真实内容时，失败不应该覆盖掉它', makeEl('ai_stock').innerHTML.includes('之前的真实结果'));

// ===================== 测试4：window._syncedData为空时不报错 =====================
delete window._syncedData;
try {
  refreshMysteelMealStock();
  check('★window._syncedData为空时不应该报错', true);
} catch(e) {
  check('★window._syncedData为空时不应该报错', false);
}

H.printSummary();
