const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());
// ★脚本eval时会自动按"今天"的真实日期跑一次selectContract(getDefaultContractByDate())，
//   这个测试假设的是9月合约(sep)语境下的评分规则，明确覆盖一次，
//   不要让测试结果跟着"今天实际是几月"变来变去。
window._selectedContract = 'sep';


function resetFields(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry','m_rmspread'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import','ind_poultry','ind_rmspread'].forEach(id=>elements[id]=makeEl(id));
  elements['alertContent'] = makeEl('alertContent');
}

// ===================== 测试1：粘贴解析能识别新指标 =====================
const example = `豆菜粕价差(元/吨) 550元/吨 2026年7月 我的钢铁网`;
const parsed = parsePastedData(example);
check('应该正确识别豆菜粕价差这个新指标', !!parsed.m_rmspread);
check('数值应该正确解析为550', parsed.m_rmspread && parsed.m_rmspread.value === 550);

// ===================== 测试2：阈值验证(用2026年4月查证过的真实数据区间470-780) =====================
resetFields();
elements['m_rmspread'].value = '350'; // <400阈值
updateOverallAlert();
check('价差350(<400，菜粕不便宜)应判定偏多', elements['alertContent'].innerHTML.includes('sd-cell sd-pos">豆菜粕价差'));

resetFields();
elements['m_rmspread'].value = '550'; // 落在2026年4月真实区间470-780内，属于中性
updateOverallAlert();
check('价差550(真实2026年4月区间内，400-700之间)应判定中性', elements['alertContent'].innerHTML.includes('sd-cell sd-neutral">豆菜粕价差'));

resetFields();
elements['m_rmspread'].value = '750'; // >700阈值
updateOverallAlert();
check('价差750(>700，菜粕明显划算)应判定偏空', elements['alertContent'].innerHTML.includes('sd-cell sd-neg">豆菜粕价差'));

// ===================== 测试3：13票制审计(12票+新指标=13票) =====================
resetFields();
elements['m_crush'].value='35'; elements['m_stock'].value='40'; elements['m_basis'].value='10';
elements['m_arrival'].value='700'; elements['m_hogratio'].value='8'; elements['m_sows'].value='3600';
elements['m_import'].value='700'; elements['m_poultry'].value='2'; elements['m_rmspread'].value='350';
window._weatherRisk='high'; window._droughtSignal=1; window._noaaOutlookSignal=1; window._soyCondSignal=1;
window._esrSignal=1; window._fxSignal=1; window._psdSignal=1;
updateOverallAlert();
check('★13票制审计：全部信号偏多时，总分应精确为+13(新指标正确并入总票数)',
  elements['alertContent'].innerHTML.includes('+13分'));
const posCount = (elements['alertContent'].innerHTML.match(/sd-pos/g)||[]).length;
check('★供需表格应精确显示13个偏多格子', posCount === 13);
check('供需表格需求侧应显示"豆菜粕价差"这个新标签', elements['alertContent'].innerHTML.includes('豆菜粕价差'));


H.printSummary();
