const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：数据不可用时的降级显示 =====================
makeEl('brPlantBadge'); makeEl('brPlantContent');
window._brazilPlantingSignal = 999; // 先设一个脏值，确认会被正确重置
renderBrazilPlanting({available: false, reason: 'CONAB接口调用失败: ConnectionError'}, new Date().toISOString());
check('★数据不可用时应该显示具体原因', makeEl('brPlantContent').innerHTML.includes('CONAB接口调用失败'));
check('★数据不可用时window._brazilPlantingSignal应该被重置为null，不留着脏值', window._brazilPlantingSignal === null);

renderBrazilPlanting(null, new Date().toISOString());
check('传null不应该报错，应该有兜底文字', makeEl('brPlantContent').innerHTML.includes('未知原因'));

// ===================== 测试2：播种慢于去年同期(bull，偏多) =====================
makeEl('brPlantBadge'); makeEl('brPlantContent');
const slowerData = {
  available: true, safra: '2026/27', weekLabel: '2026-10-04',
  pctCurrent: 5.0, pctYearAgo: 9.0, pctPrevWeek: 3.0, pctFiveYearAvg: 8.5,
  source: '测试',
};
renderBrazilPlanting(slowerData, new Date().toISOString());
check('★播种慢于去年同期(差距超过3个百分点)应该是bull样式', makeEl('brPlantContent').innerHTML.includes('alert-box bull'));
check('★应该显示"偏多信号"文字', makeEl('brPlantContent').innerHTML.includes('偏多信号'));
check('★window._brazilPlantingSignal应该正确写入1', window._brazilPlantingSignal === 1);
check('详情区应该显示本期/去年同期/上周/五年均值四项数据', 
  makeEl('brPlantContent').innerHTML.includes('5%') || makeEl('brPlantContent').innerHTML.includes('5.0%'));
check('应该显示去年同期数值(9%)', makeEl('brPlantContent').innerHTML.includes('9%') || makeEl('brPlantContent').innerHTML.includes('9.0%'));
check('应该显示近五年均值(8.5%)', makeEl('brPlantContent').innerHTML.includes('8.5%'));

// ===================== 测试3：播种快于去年同期(bear，偏空) =====================
makeEl('brPlantBadge'); makeEl('brPlantContent');
const fasterData = {...slowerData, pctCurrent: 12.0, pctYearAgo: 8.0};
renderBrazilPlanting(fasterData, new Date().toISOString());
check('★播种快于去年同期(差距超过3个百分点)应该是bear样式', makeEl('brPlantContent').innerHTML.includes('alert-box bear'));
check('★应该显示"偏空信号"文字', makeEl('brPlantContent').innerHTML.includes('偏空信号'));
check('★window._brazilPlantingSignal应该正确写入-1', window._brazilPlantingSignal === -1);

// ===================== 测试4：差距在±3个百分点以内(中性) =====================
makeEl('brPlantBadge'); makeEl('brPlantContent');
renderBrazilPlanting({...slowerData, pctCurrent: 8.5, pctYearAgo: 8.0}, new Date().toISOString());
check('★差距在±3个百分点以内应该判定中性', window._brazilPlantingSignal === 0);
check('应该显示"基本持平"文字', makeEl('brPlantContent').innerHTML.includes('基本持平'));

// ===================== 测试5：去年同期数据缺失时不应该硬判断方向 =====================
makeEl('brPlantBadge'); makeEl('brPlantContent');
renderBrazilPlanting({...slowerData, pctYearAgo: null}, new Date().toISOString());
check('★去年同期数据缺失时，signal应该保持null，不强行判断方向', window._brazilPlantingSignal === null);

// ===================== 测试6：refreshBrazilPlantingDisplay从window._syncedData正确读取 =====================
makeEl('brPlantBadge'); makeEl('brPlantContent');
window._syncedData = {
  generatedAt: new Date().toISOString(),
  brazilPlantingProgress: {available: true, safra: '2026/27', weekLabel: '2026-10-04',
    pctCurrent: 6.0, pctYearAgo: 10.0, pctPrevWeek: 4.0, pctFiveYearAvg: 9.0, source: '测试'},
};
refreshBrazilPlantingDisplay();
check('★refreshBrazilPlantingDisplay应该正确从window._syncedData读取数据并渲染', window._brazilPlantingSignal === 1);

// window._syncedData还没有时不应该报错
delete window._syncedData;
try {
  refreshBrazilPlantingDisplay();
  check('★window._syncedData为空时不应该报错(数据还没同步回来的情况)', true);
} catch(e) {
  check('★window._syncedData为空时不应该报错(数据还没同步回来的情况)', false);
}

H.printSummary();
