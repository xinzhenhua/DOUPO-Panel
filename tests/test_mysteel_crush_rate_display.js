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
check('★欄位已有值时不应该被强制覆盖(保留用户自己填的55.5)', makeEl('m_crush').value === '55.5');
check('★但提示区依然应该显示抓取到的新值，方便用户对比', makeEl('ai_crush').innerHTML.includes('69.98'));
check('提示区应该有"采用"按钮，让用户自己选择要不要换成新值', makeEl('ai_crush').innerHTML.includes('采用'));

// ===================== 测试3：抓取失败时不报错，也不覆盖既有提示内容 =====================
resetCrushFields();
makeEl('ai_crush').innerHTML = '之前贴过的解析结果';
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
check('★抓取失败时不应该覆盖掉之前贴过的解析结果', makeEl('ai_crush').innerHTML === '之前贴过的解析结果');

// ===================== 测试4：window._syncedData还没同步回来时不应该报错 =====================
delete window._syncedData;
try {
  refreshMysteelCrushRate();
  check('★window._syncedData为空时不应该报错', true);
} catch(e) {
  check('★window._syncedData为空时不应该报错', false);
}

H.printSummary();
