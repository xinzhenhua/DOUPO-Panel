const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());
window._selectedContract = 'sep';

function resetFields(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry','m_rmspread','m_reserve'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import','ind_poultry','ind_rmspread','ind_reserve'].forEach(id=>elements[id]=makeEl(id));
  elements['alertContent'] = makeEl('alertContent');
}

// ===================== 测试1：粘贴解析能识别新指标 =====================
const example = `最近一次国储进口大豆拍卖量(万吨) 54.3万吨 2026年9月22日 国家粮食交易中心`;
const parsed = parsePastedData(example);
check('★应该正确识别国储拍卖量这个新指标', !!parsed.m_reserve);
check('★数值应该正确解析为54.3(不是被"国储进口大豆拍卖量"这个更长的关键字漏掉)', parsed.m_reserve && parsed.m_reserve.value === 54.3);

// ===================== 测试2：规模较大(>=40万吨)时应判定偏空 =====================
resetFields();
elements['m_reserve'].value = '54.3'; // 真实查证过的规模(文华财经文章里的实际数字)
updateOverallAlert();
check('★拍卖54.3万吨(超过40万吨门槛)应判定偏空', elements['alertContent'].innerHTML.includes('sd-cell sd-neg">国储拍卖'));

// ===================== 测试3：规模较小时应判定中性(不是偏多) =====================
resetFields();
elements['m_reserve'].value = '5'; // 小规模拍卖
updateOverallAlert();
check('★小规模拍卖(5万吨，未超过40万吨门槛)应判定中性，不是偏多', elements['alertContent'].innerHTML.includes('sd-cell sd-neutral">国储拍卖'));

// ===================== 测试4：没有拍卖(0)时应判定中性，不是偏多 =====================
resetFields();
elements['m_reserve'].value = '0';
updateOverallAlert();
check('★没有拍卖(0万吨)应判定中性——"没有额外空头催化"不等于"看多"，不能判成偏多', elements['alertContent'].innerHTML.includes('sd-cell sd-neutral">国储拍卖'));
check('★文字说明应该提到"无新增供给压力"', elements['alertContent'].innerHTML.includes('无新增供给压力'));

// ===================== 测试5：没有填写时不应该报错，且不计入评分 =====================
resetFields();
try {
  updateOverallAlert();
  check('★不填这一项时不应该报错', true);
} catch(e) {
  check('★不填这一项时不应该报错', false);
}

// ===================== 测试6：供需表格应该显示新标签 =====================
resetFields();
elements['m_reserve'].value = '60';
updateOverallAlert();
check('供需表格供给侧应显示"国储拍卖"这个新标签', elements['alertContent'].innerHTML.includes('国储拍卖'));

H.printSummary();
