const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== ★核心bug修复验证 =====================
// 之前的问题：抓取失败时四个函式直接return，完全不碰ai_xxx这个区域，
// 导致renderParsedInfo设置的"💡 尚未粘贴数据"默认文字一直留着，
// 让用户误以为自动抓取根本没有尝试过（这正是用户反馈"前台没有任何变化"的根因）。

function testOneIndicator(name, refreshFn, badgeId, dataKey){
  // 场景1：区域处于renderParsedInfo设置的默认"尚未粘贴数据"状态，抓取失败时
  // 应该主动替换成明确的失败原因，不能让默认文字继续误导用户
  const badge = makeEl(badgeId);
  badge.className = 'ai-suggest unavailable';
  badge.innerHTML = '💡 尚未粘贴数据，或者粘贴的文本里没有识别到这一项';
  window._syncedData = {generatedAt: new Date().toISOString(), [dataKey]: {available: false, reason: '搜索结果为空(测试)'}};
  refreshFn();
  check(`★${name}: 失败时应该替换掉"尚未粘贴数据"这句误导性默认文字`, !badge.innerHTML.includes('尚未粘贴数据'));
  check(`★${name}: 失败时应该显示明确的失败原因`, badge.innerHTML.includes('自动抓取失败') && badge.innerHTML.includes('搜索结果为空(测试)'));

  // 场景2：区域已经是fresh状态(比如用户刚手动贴过、或者之前自动抓取成功过)，
  // 这次抓取失败时不应该覆盖掉这个已有的真实内容
  const badge2 = makeEl(badgeId);
  badge2.className = 'ai-suggest fresh';
  badge2.innerHTML = '📋 解析到：<b>某个之前的真实值</b>';
  window._syncedData = {generatedAt: new Date().toISOString(), [dataKey]: {available: false, reason: '这次失败了'}};
  refreshFn();
  check(`${name}: 区域已有真实内容(fresh状态)时，失败不应该覆盖掉它`, badge2.innerHTML.includes('某个之前的真实值'));
}

testOneIndicator('开机率', refreshMysteelCrushRate, 'ai_crush', 'mysteelCrushRate');
testOneIndicator('养殖利润', refreshMysteelPoultryProfit, 'ai_poultry', 'mysteelPoultryProfit');
testOneIndicator('豆菜粕价差', refreshMysteelRmSpread, 'ai_rmspread', 'mysteelRmSpread');
testOneIndicator('到港预报', refreshMysteelArrivalForecast, 'ai_arrival', 'mysteelArrivalForecast');

H.printSummary();
