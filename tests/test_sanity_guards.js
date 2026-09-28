const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// 每个自动抓取指标：荒谬数值不能自动填入、不能显示"采用"按钮，要显示警告；合理数值不受影响
const cases = [
  {name:'豆粕商业库存(用户遇到的0.7万吨)', fn: refreshMysteelMealStock, ai:'ai_stock', input:'m_stock', key:'mysteelMealStock', bad:{value:0.7, date:'2026-09-28'}, good:{value:117.32, date:'2026-09-21'}},
  {name:'油厂开机率', fn: refreshMysteelCrushRate, ai:'ai_crush', input:'m_crush', key:'mysteelCrushRate', bad:{value:1.14, date:'2026-09-28'}, good:{value:68.84, date:'2026-09-23'}},
  {name:'养殖利润', fn: refreshMysteelPoultryProfit, ai:'ai_poultry', input:'m_poultry', key:'mysteelPoultryProfit', bad:{value:99, date:'2026-09-24'}, good:{value:-4.18, date:'2026-09-24'}},
  {name:'豆菜粕价差', fn: refreshMysteelRmSpread, ai:'ai_rmspread', input:'m_rmspread', key:'mysteelRmSpread', bad:{value:15, formatUsed:'区间中点', rangeLow:10, rangeHigh:20, date:'2026-09-28'}, good:{value:500, formatUsed:'区间中点', rangeLow:480, rangeHigh:520, date:'2026-09-28'}},
  {name:'到港预报', fn: refreshMysteelArrivalForecast, ai:'ai_arrival', input:'m_arrival', key:'mysteelArrivalForecast', bad:{value:30, forecastYear:2026, forecastMonth:10, date:'2026-09-24'}, good:{value:854.1, forecastYear:2026, forecastMonth:10, date:'2026-09-24'}},
  {name:'猪粮比', fn: refreshHogRatio, ai:'ai_hogratio', input:'m_hogratio', key:'hogRatio', bad:{value:42, date:'2026-09-27'}, good:{value:4.4, date:'2026-09-27'}},
  {name:'能繁母猪存栏', fn: refreshSowInventory, ai:'ai_sows', input:'m_sows', key:'sowInventory', bad:{value:20, date:'2026-09-24', quarterLabel:'2026年二季度末'}, good:{value:3780, date:'2026-09-24', quarterLabel:'2026年二季度末'}},
];
for (const c of cases) {
  // 荒谬数值：不填入、无采用按钮、有警告
  makeEl(c.input).value = ''; makeEl(c.ai).className = 'ai-suggest unavailable'; makeEl(c.ai).innerHTML = '💡 尚未粘贴数据'; makeEl('ind_' + c.input.slice(2));
  window._syncedData = {generatedAt: new Date().toISOString(), [c.key]: Object.assign({available: true}, c.bad)};
  c.fn();
  check(`★${c.name}: 荒谬数值(${c.bad.value})不能自动填入输入框`, makeEl(c.input).value === '');
  check(`★${c.name}: 荒谬数值不能显示"采用"按钮`, !makeEl(c.ai).innerHTML.includes('采用'));
  check(`★${c.name}: 应该显示"不合理，已忽略"警告和具体范围`, makeEl(c.ai).innerHTML.includes('不合理') && makeEl(c.ai).innerHTML.includes('超出合理范围'));
  // 合理数值：正常填入
  makeEl(c.input).value = ''; makeEl(c.ai).className = 'ai-suggest unavailable'; makeEl(c.ai).innerHTML = '';
  window._syncedData = {generatedAt: new Date().toISOString(), [c.key]: Object.assign({available: true}, c.good)};
  c.fn();
  check(`${c.name}: 合理数值(${c.good.value})不受影响，正常自动填入`, String(makeEl(c.input).value) === String(c.good.value));
  // 用户已经手动贴过真实内容(fresh)时，不被警告覆盖
  makeEl(c.ai).className = 'ai-suggest fresh'; makeEl(c.ai).innerHTML = '📋 用户手动贴的真实结果'; makeEl(c.input).value = '';
  window._syncedData = {generatedAt: new Date().toISOString(), [c.key]: Object.assign({available: true}, c.bad)};
  c.fn();
  check(`${c.name}: 已有真实内容时，荒谬数值的警告不覆盖它，也不填入`, makeEl(c.ai).innerHTML.includes('用户手动贴的真实结果') && makeEl(c.input).value === '');
}
// 判断函数本身
check('sanityProblem: 合理值返回null', sanityProblem('mealStock', 117.32) === null);
check('sanityProblem: 边界值(10/600)算合理', sanityProblem('mealStock', 10) === null && sanityProblem('mealStock', 600) === null);
check('sanityProblem: 0.7超出范围', sanityProblem('mealStock', 0.7) !== null);
check('sanityProblem: 非数字(NaN/undefined)算无效', sanityProblem('mealStock', NaN) !== null && sanityProblem('mealStock', undefined) !== null);
check('sanityProblem: 未登记的key不拦截(不会误伤)', sanityProblem('不存在的key', 1) === null);
H.printSummary();
