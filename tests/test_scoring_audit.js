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

// ===================== 严格审计1：11个信号全部偏多，score应精确等于11(不是14) =====================
resetManualFields();
elements['m_crush'].value='35'; elements['m_stock'].value='40'; elements['m_basis'].value='10';
elements['m_arrival'].value='700'; elements['m_hogratio'].value='8'; elements['m_sows'].value='3600';
elements['m_import'].value='700';

window._weatherRisk = 'high'; window._droughtSignal = 1; window._noaaOutlookSignal = 1; window._soyCondSignal = 1;
window._esrSignal = 1; window._fxSignal = 1; window._psdSignal = 1;
window._cbotSignal = 1;

updateOverallAlert();

check('★严格审计：11个信号全部偏多时，综合评分应该精确是+11分(4个天气类指标合并成1票后的新总数)',
  elements['alertContent'].innerHTML.includes('+11分'));
check('★不应该再出现旧的+14分(说明合并逻辑生效)', !elements['alertContent'].innerHTML.includes('+14分'));
check('★验证CBOT确实不参与评分：即使window._cbotSignal=1，也不应该让总分变成12分',
  !elements['alertContent'].innerHTML.includes('+12分'));

const posCount = (elements['alertContent'].innerHTML.match(/sd-pos/g)||[]).length;
check('★严格审计：供需表格里应该恰好有11个"偏多"格子(7供应+4需求)', posCount === 11);
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
