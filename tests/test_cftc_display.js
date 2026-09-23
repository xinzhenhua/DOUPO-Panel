const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：数据不可用时的降级显示 =====================
makeEl('cftcBadge'); makeEl('cftcContent');
window._cftcNetChange = 999; // 先设一个脏值，确认renderCftc会正确重置它
renderCftc({available: false, reason: '接口暂时无响应'}, new Date().toISOString());
check('★数据不可用时应该显示原因', makeEl('cftcContent').innerHTML.includes('接口暂时无响应'));
check('★数据不可用时window._cftcNetChange应该被重置为null，不留着上次的脏值', window._cftcNetChange === null);

renderCftc(null, new Date().toISOString());
check('传null也不应该报错，应该正常显示"未知原因"兜底', makeEl('cftcContent').innerHTML.includes('未知原因'));

// ===================== 测试2：净多头增仓(bull) =====================
makeEl('cftcBadge'); makeEl('cftcContent');
const bullData = {
  available: true, marketName: 'SOYBEAN MEAL - CHICAGO BOARD OF TRADE', reportDate: '2026-09-16',
  longPositions: 115467, shortPositions: 37899, netPosition: 77568,
  longChange: 6950, shortChange: -11514, netChange: 18464,
  source: '测试',
};
renderCftc(bullData, new Date().toISOString());
check('★净多头增仓时应该是bull样式', makeEl('cftcContent').innerHTML.includes('alert-box bull'));
check('★应该提示"增仓"/"看多信号"', makeEl('cftcContent').innerHTML.includes('增仓') && makeEl('cftcContent').innerHTML.includes('看多'));
check('★净持仓数字应该正确显示(77,568，带千分位)', makeEl('cftcContent').innerHTML.includes('77,568'));
check('★多头/空头持仓明细都应该显示', makeEl('cftcContent').innerHTML.includes('115,467') && makeEl('cftcContent').innerHTML.includes('37,899'));
check('★window._cftcNetChange应该正确写入18464', window._cftcNetChange === 18464);

// ===================== 测试3：净多头减仓(bear) =====================
makeEl('cftcBadge'); makeEl('cftcContent');
const bearData = {...bullData, netChange: -15000};
renderCftc(bearData, new Date().toISOString());
check('★净多头减仓时应该是bear样式', makeEl('cftcContent').innerHTML.includes('alert-box bear'));
check('★应该提示"减仓"/"看空"/"撤退"信号', makeEl('cftcContent').innerHTML.includes('减仓') && (makeEl('cftcContent').innerHTML.includes('看空') || makeEl('cftcContent').innerHTML.includes('撤退')));
check('window._cftcNetChange应该正确写入-15000', window._cftcNetChange === -15000);

// ===================== 测试4：净变化为0(neutral) =====================
makeEl('cftcBadge'); makeEl('cftcContent');
renderCftc({...bullData, netChange: 0}, new Date().toISOString());
check('净变化为0时应该是neutral样式，不强行判定方向', makeEl('cftcContent').innerHTML.includes('alert-box neutral'));

H.printSummary();
