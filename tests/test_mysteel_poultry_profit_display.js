const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

function resetPoultryFields(){
  makeEl('m_poultry').value = '';
  makeEl('ai_poultry');
  makeEl('ind_poultry');
}

// ===================== 测试1：欄位是空的时，正数(盈利)自动填入 =====================
resetPoultryFields();
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelPoultryProfit: {available: true, value: 0.56, date: '2026-09-24', source: 'Mysteel文章'},
};
refreshMysteelPoultryProfit();
check('★盈利时应该自动填入正值', makeEl('m_poultry').value == '0.56');
check('★提示区应该显示正数带+号', makeEl('ai_poultry').innerHTML.includes('+0.56元/只'));

// ===================== 测试2：★核心验证——负数(亏损)时的显示，不能漏掉负号 =====================
resetPoultryFields();
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelPoultryProfit: {available: true, value: -4.18, date: '2026-09-24', source: 'Mysteel文章'},
};
refreshMysteelPoultryProfit();
check('★亏损时应该自动填入负值(不是绝对值)', makeEl('m_poultry').value == '-4.18');
check('★提示区应该正确显示负号，不应该多此一举加"+"号', makeEl('ai_poultry').innerHTML.includes('-4.18元/只') && !makeEl('ai_poultry').innerHTML.includes('+-4.18'));
check('★采用按钮传入的值也应该是负数', makeEl('ai_poultry').innerHTML.includes("useAiValue('m_poultry', -4.18)"));

// ===================== 测试3：欄位已有值时不强制覆盖(负值场景) =====================
resetPoultryFields();
makeEl('m_poultry').value = '1.5'; // 用户自己填的
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelPoultryProfit: {available: true, value: -2.23, date: '2026-09-24'},
};
refreshMysteelPoultryProfit();
check('★欄位已有值时不应该被覆盖', makeEl('m_poultry').value === '1.5');
check('提示区依然应该显示抓取到的负值供参考', makeEl('ai_poultry').innerHTML.includes('-2.23元/只'));

// ===================== 测试4：抓取失败时不报错 =====================
resetPoultryFields();
window._syncedData = {generatedAt: new Date().toISOString(), mysteelPoultryProfit: {available: false, reason: '搜索结果为空'}};
try {
  refreshMysteelPoultryProfit();
  check('★抓取失败时不应该报错', true);
} catch(e) {
  check('★抓取失败时不应该报错', false);
}

// ===================== 测试5：window._syncedData为空时不报错 =====================
delete window._syncedData;
try {
  refreshMysteelPoultryProfit();
  check('★window._syncedData为空时不应该报错', true);
} catch(e) {
  check('★window._syncedData为空时不应该报错', false);
}

H.printSummary();
