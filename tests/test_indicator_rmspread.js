const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());
H.setMockedMonth(5);   // 固定5月：9月合约作物票在"参与"档(×1)，票数不随真实日期变化(季节档位见test_seasonal.js)
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

// ===================== 测试3：票数审计(豆菜粕价差正确并入) =====================
resetFields();
elements['m_crush'].value='35'; elements['m_stock'].value='40'; elements['m_basis'].value='10';
elements['m_arrival'].value='700'; elements['m_hogratio'].value='8'; elements['m_sows'].value='3600';
elements['m_import'].value='700'; elements['m_poultry'].value='2'; elements['m_rmspread'].value='350';
window._weatherRisk='high'; window._droughtSignal=1; window._noaaOutlookSignal=1; window._soyCondSignal=1;
window._esrSignal=1; window._fxSignal=1; window._psdSignal=1;
updateOverallAlert();
// 供应5票+需求6票(出口销售、基差、猪粮比、能繁、肉鸡、豆菜粕价差)
// 手算：10个有效投票，天气开关打开：作物×2，其余9票×0.5 → 2+4.5=+6.5
check('★票数审计：顶部9个供需票全偏多(原10个含基差)；作物4个子信号全偏多→天气开关：作物×2，其余8票×0.5 = 总分+6',
  elements['alertContent'].innerHTML.includes('基本面偏多 +6（'));
const posCount = (elements['alertContent'].innerHTML.match(/sd-pos/g)||[]).length;
check('★供需表格应精确显示9个偏多格子(原10个，基差移到"市场结构"卡)', posCount === 9);
check('供需表格需求侧应显示"豆菜粕价差"这个新标签', elements['alertContent'].innerHTML.includes('豆菜粕价差'));


H.printSummary();
