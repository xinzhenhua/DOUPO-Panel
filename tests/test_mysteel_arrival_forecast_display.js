const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

function resetArrivalFields(){
  makeEl('m_arrival').value = '';
  makeEl('ai_arrival');
  makeEl('ind_arrival');
}

// ===================== 测试1：标准格式月份正确显示且自动填入 =====================
resetArrivalFields();
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelArrivalForecast: {available: true, forecastYear: 2026, forecastMonth: 6, value: 1073.8, date: '2026-05-27', formatUsed: '标准格式', source: 'Mysteel文章'},
};
refreshMysteelArrivalForecast();
check('★欄位是空的时应该自动填入数值', makeEl('m_arrival').value == '1073.8');
check('★提示区应该明确显示是哪年哪月的预报(2026年6月)', makeEl('ai_arrival').innerHTML.includes('2026年6月到港'));
check('★提示区应该显示数值', makeEl('ai_arrival').innerHTML.includes('1073.8万吨'));

// ===================== 测试2：★核心验证——必须有醒目警告提醒核对月份 =====================
check('★必须包含警告文字，提醒用户核对月份(不能默认这就是"本月")', makeEl('ai_arrival').innerHTML.includes('请核对这是不是你需要的月份'));
check('★警告文字应该说明到港预报的性质(一般是下个月，不一定是当月)', makeEl('ai_arrival').innerHTML.includes('一般发布下个月'));

// ===================== 测试3：级联格式(预测未来3个月，只取最近月)同样正确显示 =====================
resetArrivalFields();
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelArrivalForecast: {available: true, forecastYear: 2026, forecastMonth: 7, value: 1064, date: '2026-06-26', formatUsed: '级联格式(仅取最近月)', source: 'Mysteel文章'},
};
refreshMysteelArrivalForecast();
check('★级联格式时同样应该明确显示对应月份(2026年7月)', makeEl('ai_arrival').innerHTML.includes('2026年7月到港'));
check('★级联格式时同样应该有月份核对警告', makeEl('ai_arrival').innerHTML.includes('请核对这是不是你需要的月份'));

// ===================== 测试4：欄位已有值时不强制覆盖 =====================
resetArrivalFields();
makeEl('m_arrival').value = '900';
window._syncedData = {
  generatedAt: new Date().toISOString(),
  mysteelArrivalForecast: {available: true, forecastYear: 2026, forecastMonth: 6, value: 1073.8, date: '2026-05-27'},
};
refreshMysteelArrivalForecast();
check('★欄位已有值时不应该被覆盖', makeEl('m_arrival').value === '900');
check('提示区依然应该显示抓取到的月份+数值供参考', makeEl('ai_arrival').innerHTML.includes('2026年6月'));

// ===================== 测试5：抓取失败/无数据时不报错 =====================
resetArrivalFields();
window._syncedData = {generatedAt: new Date().toISOString(), mysteelArrivalForecast: {available: false, reason: '搜索结果为空'}};
try {
  refreshMysteelArrivalForecast();
  check('★抓取失败时不应该报错', true);
} catch(e) {
  check('★抓取失败时不应该报错', false);
}

delete window._syncedData;
try {
  refreshMysteelArrivalForecast();
  check('★window._syncedData为空时不应该报错', true);
} catch(e) {
  check('★window._syncedData为空时不应该报错', false);
}

H.printSummary();
