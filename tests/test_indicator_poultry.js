const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());
H.setMockedMonth(5);   // 固定5月：9月合约作物票在"参与"档(×1)，票数不随真实日期变化(季节档位见test_seasonal.js)
// ★脚本eval时会自动按"今天"的真实日期跑一次selectContract(getDefaultContractByDate())，
//   这个测试假设的是9月合约(sep)语境下的评分规则，明确覆盖一次，
//   不要让测试结果跟着"今天实际是几月"变来变去。
window._selectedContract = 'sep';


// ===================== 测试2：评分阈值验证(用查证过的真实数据区间) =====================
function resetFields(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import','ind_poultry'].forEach(id=>elements[id]=makeEl(id));
  elements['alertContent'] = makeEl('alertContent');
}

resetFields();
elements['m_poultry'].value = '1.73'; // 查到的真实数据：2023年案例，>1.5阈值
updateOverallAlert();
check('盈利1.73元/只(>1.5阈值，真实历史数据)应判定偏多', elements['alertContent'].innerHTML.includes('sd-cell sd-pos">肉鸡养殖利润'));

resetFields();
elements['m_poultry'].value = '0.71'; // 查到的真实数据：2022年案例，介于0-1.5之间
updateOverallAlert();
check('盈利0.71元/只(0-1.5之间，真实历史数据)应判定中性', elements['alertContent'].innerHTML.includes('sd-cell sd-neutral">肉鸡养殖利润'));

resetFields();
elements['m_poultry'].value = '-4'; // 亏损场景
updateOverallAlert();
check('亏损-4元/只(<0)应判定偏空', elements['alertContent'].innerHTML.includes('sd-cell sd-neg">肉鸡养殖利润'));

// ===================== 测试3：票数审计(肉鸡指标正确并入) =====================
resetFields();
elements['m_crush'].value='35'; elements['m_stock'].value='40'; H.setBasis('10');
elements['m_arrival'].value='700'; elements['m_hogratio'].value='8'; elements['m_sows'].value='3600';
elements['m_import'].value='700'; elements['m_poultry'].value='2';
window._weatherRisk='high'; window._droughtSignal=1; window._noaaOutlookSignal=1; window._soyCondSignal=1;
window._esrSignal=1; window._fxSignal=1; window._psdSignal=1;
updateOverallAlert();
// 供应5票(作物、库存消费比、供应松紧、到港/进口、汇率)+需求5票(出口销售、基差、猪粮比、能繁、肉鸡)
// 手算：9个有效投票(能繁已移出评分)，天气开关打开：作物×2，其余8票×0.5 → 2+4=+6
check('★票数审计：顶部8个供需票全偏多(原9个含基差)；作物4个子信号全偏多→天气开关：作物×2，其余7票×0.5 = 总分+5.5',
  elements['alertContent'].innerHTML.includes('基本面偏多 +5.5（'));
const posCount = (elements['alertContent'].innerHTML.match(/sd-pos/g)||[]).length;
check('★供需表格应精确显示8个偏多格子(原9个，基差移到"市场结构"卡)', posCount === 8);
check('供需表格需求侧应显示"肉鸡养殖利润"这个新标签', elements['alertContent'].innerHTML.includes('肉鸡养殖利润'));

H.printSummary();
