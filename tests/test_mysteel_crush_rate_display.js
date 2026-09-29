const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

function resetCrushFields(){
  makeEl('m_crush').value = '';
  makeEl('ai_crush');
  makeEl('ind_crush');
}

// ===================== 测试1：欄位是空的时，应该自动填入 =====================
resetCrushFields();
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelCrushRate: {available: true, value: 69.98, date: '2026-09-22', source: 'Mysteel快讯', rawContent: '测试'},
};
refreshMysteelCrushRate();
check('★欄位是空的时，应该自动填入抓取到的值', makeEl('m_crush').value === '69.98' || makeEl('m_crush').value === 69.98);
check('★提示区应该显示"自动抓取(Mysteel)"字样', makeEl('ai_crush').innerHTML.includes('自动抓取') && makeEl('ai_crush').innerHTML.includes('Mysteel'));
check('提示区应该显示具体数值', makeEl('ai_crush').innerHTML.includes('69.98'));
check('提示区应该显示日期', makeEl('ai_crush').innerHTML.includes('2026-09-22'));

// ===================== 测试2：★欄位已经有值时，不应该强制覆盖，只提示 =====================
resetCrushFields();
makeEl('m_crush').value = '55.5'; // 用户自己手动填过的值
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelCrushRate: {available: true, value: 69.98, date: '2026-09-22', source: 'Mysteel快讯'},
};
refreshMysteelCrushRate();
check('★抓取成功时直接覆盖输入框里已有的值(55.5→69.98)，不再区分"输入框是否为空"', makeEl('m_crush').value == '69.98');
check('提示区应该显示抓取到的值', makeEl('ai_crush').innerHTML.includes('69.98'));
check('★不再有"采用"按钮(自动值直接覆盖)', !makeEl('ai_crush').innerHTML.includes('采用'));

// ===================== 测试3：抓取失败时不报错；输入框里保存过的手动值要保留(不被清空) =====================
resetCrushFields();
makeEl('m_crush').value = '55.5'; // 上次保存的手动修正值
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelCrushRate: {available: false, reason: '搜索结果为空'},
};
try {
  refreshMysteelCrushRate();
  check('★抓取失败时不应该报错', true);
} catch(e) {
  check('★抓取失败时不应该报错', false);
}
check('★抓取失败时不清空输入框里保存过的手动值', makeEl('m_crush').value === '55.5');
check('★抓取失败时详情里应该说明失败原因', makeEl('ai_crush').innerHTML.includes('自动抓取失败') && makeEl('ai_crush').innerHTML.includes('搜索结果为空'));

// ===================== 测试4：window._syncedData还没同步回来时不应该报错 =====================
delete window._syncedData;
try {
  refreshMysteelCrushRate();
  check('★window._syncedData为空时不应该报错', true);
} catch(e) {
  check('★window._syncedData为空时不应该报错', false);
}

H.printSummary();
