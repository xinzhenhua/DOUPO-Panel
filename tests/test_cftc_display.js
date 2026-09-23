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

// ===================== 测试5：★用户明确要求的3类新信号 =====================
const baseData = {
  available: true, marketName: 'SOYBEAN MEAL - CHICAGO BOARD OF TRADE', reportDate: '2026-09-16',
  longPositions: 115467, shortPositions: 37899, netPosition: 77568,
  longChange: 6950, shortChange: -11514, netChange: 18464, source: '测试',
};

// 信号①：连续增仓(streakWeeks>=3)
makeEl('cftcBadge'); makeEl('cftcContent');
renderCftc({...baseData, streakWeeks: 4, streakDirection: 'up', historyPercentile: null, historyWeeksUsed: 10}, new Date().toISOString());
check('★连续4周增仓时应该显示"净多头持续增加"提示', makeEl('cftcContent').innerHTML.includes('净多头持续增加'));
check('★连续增仓提示应该显示具体周数(4周)', makeEl('cftcContent').innerHTML.includes('连续4周'));
check('连续增仓应该是bull样式', makeEl('cftcContent').innerHTML.includes('净多头持续增加') && (makeEl('cftcContent').innerHTML.match(/alert-box bull/g)||[]).length >= 1);

// 信号①反向：连续减仓
makeEl('cftcBadge'); makeEl('cftcContent');
renderCftc({...baseData, streakWeeks: 5, streakDirection: 'down', historyPercentile: null, historyWeeksUsed: 10}, new Date().toISOString());
check('★连续5周减仓时应该显示"净多头持续下降"提示', makeEl('cftcContent').innerHTML.includes('净多头持续下降'));
check('★应该提示"投机资金离场/看空"', makeEl('cftcContent').innerHTML.includes('离场') || makeEl('cftcContent').innerHTML.includes('看空'));

// 连续周数不足3周时不应该显示这个提示(避免噪音——1-2周的连续没有太大意义)
makeEl('cftcBadge'); makeEl('cftcContent');
renderCftc({...baseData, streakWeeks: 2, streakDirection: 'up', historyPercentile: null, historyWeeksUsed: 10}, new Date().toISOString());
check('★连续周数不足3周(阈值以下)时不应该显示持续增减仓提示', !makeEl('cftcContent').innerHTML.includes('持续增加'));

// 信号②：历史高位(percentile>=90)
makeEl('cftcBadge'); makeEl('cftcContent');
renderCftc({...baseData, streakWeeks: 0, streakDirection: null, historyPercentile: 95, historyWeeksUsed: 156}, new Date().toISOString());
check('★历史百分位95(超过90阈值)时应该显示"历史高位"警示', makeEl('cftcContent').innerHTML.includes('历史高位'));
check('★应该提示"警惕反转"或"过热"相关文字', makeEl('cftcContent').innerHTML.includes('过热') || makeEl('cftcContent').innerHTML.includes('反转'));
check('历史高位警示应该是warn样式(不是简单的bull/bear)', makeEl('cftcContent').innerHTML.includes('alert-box warn'));

// 信号②反向：历史低位(percentile<=10)
makeEl('cftcBadge'); makeEl('cftcContent');
renderCftc({...baseData, streakWeeks: 0, streakDirection: null, historyPercentile: 5, historyWeeksUsed: 156}, new Date().toISOString());
check('★历史百分位5(低于10阈值)时应该显示"历史低位"警示', makeEl('cftcContent').innerHTML.includes('历史低位'));

// 百分位在中间区间(不极端)时不应该显示历史高位/低位提示
makeEl('cftcBadge'); makeEl('cftcContent');
renderCftc({...baseData, streakWeeks: 0, streakDirection: null, historyPercentile: 50, historyWeeksUsed: 156}, new Date().toISOString());
check('★百分位在中间区间(50)时不应该显示历史高位/低位提示', !makeEl('cftcContent').innerHTML.includes('历史高位') && !makeEl('cftcContent').innerHTML.includes('历史低位'));

// 三个信号可以同时出现(连续增仓+历史高位同时成立，这正是最值得留意的组合)
makeEl('cftcBadge'); makeEl('cftcContent');
renderCftc({...baseData, streakWeeks: 6, streakDirection: 'up', historyPercentile: 92, historyWeeksUsed: 156}, new Date().toISOString());
check('★连续增仓+历史高位应该能同时显示，不是互相覆盖', makeEl('cftcContent').innerHTML.includes('净多头持续增加') && makeEl('cftcContent').innerHTML.includes('历史高位'));

// historyPercentile为null(历史数据不足52周)时，详情区不应该显示历史百分位这一行
makeEl('cftcBadge'); makeEl('cftcContent');
renderCftc({...baseData, streakWeeks: 0, streakDirection: null, historyPercentile: null, historyWeeksUsed: 10}, new Date().toISOString());
check('★历史数据不足时详情区不应该出现"历史百分位"这行(避免显示无意义的null)', !makeEl('cftcContent').innerHTML.includes('历史百分位'));

H.printSummary();
