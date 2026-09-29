const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());
// ★脚本eval时会自动按"今天"的真实日期跑一次selectContract(getDefaultContractByDate())，
//   这个测试假设的是9月合约(sep)语境下的评分规则，明确覆盖一次，
//   不要让测试结果跟着"今天实际是几月"变来变去。
window._selectedContract = 'sep';


function resetManualFields(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import'].forEach(id=>elements[id]=makeEl(id));
  elements['alertContent'] = makeEl('alertContent');
}

// ===================== 严格审计1：全部信号偏多时票数必须精确 =====================
// 9月合约、这次给了值的投票：作物综合、库存消费比、国内豆粕供应松紧(库存+开机率合并)、大豆到港/进口(到港+进口合并)、人民币汇率 = 5票供应；
// 出口销售、现货基差、猪粮比、能繁母猪 = 4票需求。合计9票(国储拍卖/肉鸡/豆菜粕价差没填，不投票)。
resetManualFields();
elements['m_crush'].value='35'; elements['m_stock'].value='40'; elements['m_basis'].value='10';
elements['m_arrival'].value='700'; elements['m_hogratio'].value='8'; elements['m_sows'].value='3600';
elements['m_import'].value='700';

window._weatherRisk = 'high'; window._droughtSignal = 1; window._noaaOutlookSignal = 1; window._soyCondSignal = 1;
window._esrSignal = 1; window._fxSignal = 1; window._psdSignal = 1;
window._cbotSignal = 1;

updateOverallAlert();

check('★严格审计：9个投票全部偏多，其中"国内豆粕供应松紧"票权2 → 总分应精确是+10，净倾向仍是+100%',
  elements['alertContent'].innerHTML.includes('综合偏多 +10（'));
check('★有效指标数应精确显示为9(净倾向=9÷9=+100%)', elements['alertContent'].innerHTML.includes('有效9/') && elements['alertContent'].innerHTML.includes('净倾向+100%'));
check('★验证CBOT确实不参与评分：即使window._cbotSignal=1，总分也不是+11', !elements['alertContent'].innerHTML.includes('+11（'));

const posCount = (elements['alertContent'].innerHTML.match(/sd-pos/g)||[]).length;
check('★严格审计：供需表格里应该恰好有9个"偏多"格子(5供应+4需求)', posCount === 9);
check('★合并后的两个新标签应该出现', elements['alertContent'].innerHTML.includes('国内豆粕供应松紧') && elements['alertContent'].innerHTML.includes('大豆到港/进口'));
check('★合并前的单独标签不应再各占一格', !/sd-cell sd-\w+">(开机率|商业库存|到港预报|进口量)/.test(elements['alertContent'].innerHTML));
check('供需表格应该显示"作物生长状况综合"这个合并后的标签(9月合约默认，标签格式已更新为动态可切换)', elements['alertContent'].innerHTML.includes('作物生长状况综合'));

// ===================== 严格审计2：composite的合成逻辑本身要正确 =====================
resetManualFields();
elements['m_crush'].value='35';
window._weatherRisk = 'high'; window._droughtSignal = 1; window._noaaOutlookSignal = 1; window._soyCondSignal = 0;
window._esrSignal = null; window._fxSignal = null; window._psdSignal = null;
updateOverallAlert();
check('场景A：4个子信号[偏多,偏多,偏多,中性]，平均0.75≥0.5，应合成为偏多',
  (elements['alertContent'].innerHTML.match(/sd-cell sd-pos">作物生长状况/)||[]).length === 1);

resetManualFields();
elements['m_crush'].value='35';
window._weatherRisk = 'high'; window._droughtSignal = 1; window._noaaOutlookSignal = -1; window._soyCondSignal = -1;
window._esrSignal = null; window._fxSignal = null; window._psdSignal = null;
updateOverallAlert();
check('场景B：4个子信号[偏多,偏多,偏空,偏空]方向不一致，平均为0，应合成为中性',
  (elements['alertContent'].innerHTML.match(/sd-cell sd-neutral">作物生长状况/)||[]).length === 1);


H.printSummary();
