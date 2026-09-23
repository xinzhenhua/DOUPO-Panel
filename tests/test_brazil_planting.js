const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：parsePastedData正确区分"本期"和"去年同期"两个关键字 =====================
// ★这两个关键字互为子串关系的风险要专门验证——"巴西大豆去年同期播种率"不应该被
//   "巴西大豆播种率"这个更短的m_brplant关键字提前截胡。
const pasted1 = parsePastedData(`
巴西大豆本期播种率：8.2% (2026年10月4日，CONAB)
巴西大豆去年同期播种率：5.1% (2025年10月5日，CONAB)
`);
check('★本期播种率应该被正确解析为8.2(数字类型)', pasted1.m_brplant && pasted1.m_brplant.value === 8.2);
check('★去年同期播种率应该被正确解析为5.1，不被"本期"那个pattern误截胡', pasted1.m_brplantyoy && pasted1.m_brplantyoy.value === 5.1);
check('两者日期应该分别正确识别(2026 vs 2025)', pasted1.m_brplant.date === '2026-10-04' && pasted1.m_brplantyoy.date === '2025-10-05');

// 反过来试：去年同期这一行放在前面，确认顺序不影响结果
const pasted2 = parsePastedData(`
巴西大豆去年同期播种率：5.1%
巴西大豆本期播种率：8.2%
`);
check('调换行顺序后，去年同期依然应该正确解析(不受顺序影响)', pasted2.m_brplantyoy && pasted2.m_brplantyoy.value === 5.1);
check('调换行顺序后，本期依然应该正确解析', pasted2.m_brplant && pasted2.m_brplant.value === 8.2);

// ===================== 测试2：评分逻辑——只在jan合约生效，用同比差值不用固定阈值 =====================
function setupBrazilTest(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry','m_rmspread'].forEach(id=>{
    makeEl(id).value = '';
  });
  window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null;
  window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
  window._plantingSignal=null; window._brlSignal=null; window._harvestSignal=null;
}

window._selectedContract = 'jan';
setupBrazilTest();
makeEl('m_brplant').value = '5';
makeEl('m_brplantyoy').value = '9'; // 本期比去年同期慢4个百分点(超过±3阈值)
makeEl('alertContent');
updateOverallAlert();
check('★jan合约下，播种比去年同期慢4个百分点(超阈值)，应该判定偏多', window._fundamentalDirection === '偏多' || makeEl('alertContent').innerHTML.includes('+'));

setupBrazilTest();
makeEl('m_brplant').value = '12';
makeEl('m_brplantyoy').value = '8'; // 本期比去年同期快4个百分点(超过±3阈值)
updateOverallAlert();
check('★jan合约下，播种比去年同期快4个百分点(超阈值)，应该出现"偏空"文字', makeEl('alertContent').innerHTML.includes('偏空'));

setupBrazilTest();
makeEl('m_brplant').value = '8.5';
makeEl('m_brplantyoy').value = '8'; // 差距0.5，未超过±3阈值
updateOverallAlert();
check('★差距在±3个百分点以内时应该判定中性，不强行判方向', makeEl('alertContent').innerHTML.includes('基本持平'));

// ★关键验证：切换到sep/may合约时，即使填了巴西播种数据，也不应该影响评分(只在jan生效)
window._selectedContract = 'sep';
setupBrazilTest();
makeEl('m_brplant').value = '5';
makeEl('m_brplantyoy').value = '9'; // 跟前面bull场景相同的数字
updateOverallAlert();
check('★sep合约下，巴西播种数据不应该被计入评分(这项只跟1月合约窗口期相关)', !makeEl('alertContent').innerHTML.includes('巴西大豆播种率'));

window._selectedContract = 'may';
setupBrazilTest();
makeEl('m_brplant').value = '5';
makeEl('m_brplantyoy').value = '9';
updateOverallAlert();
check('★may合约下，巴西播种数据同样不应该被计入评分', !makeEl('alertContent').innerHTML.includes('巴西大豆播种率'));

// ===================== 测试3：只填一个字段(缺另一个)时不应该硬算，也不应该报错 =====================
window._selectedContract = 'jan';
setupBrazilTest();
makeEl('m_brplant').value = '8.2';
// 不填m_brplantyoy
try {
  updateOverallAlert();
  check('★只填本期不填去年同期时不应该报错(信息不足，不强行判断)', !makeEl('alertContent').innerHTML.includes('巴西大豆播种率8.2%比去年同期'));
} catch(e) {
  check('★只填本期不填去年同期时不应该报错', false);
}

H.printSummary();
