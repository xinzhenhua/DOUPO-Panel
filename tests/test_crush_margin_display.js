const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：数据不可用时的降级显示 =====================
makeEl('crushBadge'); makeEl('crushContent');
renderCrushMargin({available: false, reason: '豆油Y2609接口调用失败'}, new Date().toISOString());
check('★数据不可用时应该显示具体原因(点名哪个合约缺失)', makeEl('crushContent').innerHTML.includes('豆油Y2609'));

renderCrushMargin(null, new Date().toISOString());
check('传null不应该报错，应该有兜底文字', makeEl('crushContent').innerHTML.includes('未知原因'));

// ===================== 测试2：毛利为正(bear，供给宽松) =====================
makeEl('crushBadge'); makeEl('crushContent');
const positiveMargin = {
  available: true, contractMonth: 9,
  mealSymbol: 'M2609', mealPrice: 3400, oilSymbol: 'Y2609', oilPrice: 8500,
  beanSymbol: 'B2609', beanPrice: 4000, grossMargin: 241.5,
  yieldMeal: 0.785, yieldOil: 0.185, source: '测试',
};
renderCrushMargin(positiveMargin, new Date().toISOString());
check('★毛利为正时应该是bear样式(供给端更宽松→偏空参考)', makeEl('crushContent').innerHTML.includes('alert-box bear'));
check('★应该明确标注"未扣加工费"，不能让人误以为是精确净利润', makeEl('crushContent').innerHTML.includes('未扣加工费'));
check('★应该明确标注"仅供参考不计入综合评分"', makeEl('crushContent').innerHTML.includes('不计入综合评分'));
check('三个合约的价格明细都应该显示', makeEl('crushContent').innerHTML.includes('3400') && makeEl('crushContent').innerHTML.includes('8500') && makeEl('crushContent').innerHTML.includes('4000'));

// ===================== 测试3：毛利为负(bull，挺价惜售) =====================
makeEl('crushBadge'); makeEl('crushContent');
renderCrushMargin({...positiveMargin, grossMargin: -150}, new Date().toISOString());
check('★毛利为负时应该是bull样式(挺价惜售动力强→偏多参考)', makeEl('crushContent').innerHTML.includes('alert-box bull'));
check('★应该提示"挺价惜售"相关文字', makeEl('crushContent').innerHTML.includes('挺价') || makeEl('crushContent').innerHTML.includes('惜售'));

// ===================== 测试4：公式说明应该正确显示系数百分比 =====================
check('★公式说明里应该正确显示78.5%出粕率', makeEl('crushContent').innerHTML.includes('78.5%'));
check('★公式说明里应该正确显示18.5%出油率', makeEl('crushContent').innerHTML.includes('18.5%'));

// ===================== 测试5：refreshCrushMarginForContract按合约切换正确读取 =====================
makeEl('crushBadge'); makeEl('crushContent');
window._syncedData = {
  generatedAt: new Date().toISOString(),
  crushMargins: {
    sep: {available: true, mealSymbol:'M2609', mealPrice:3400, oilSymbol:'Y2609', oilPrice:8500, beanSymbol:'B2609', beanPrice:4000, grossMargin: 100, yieldMeal:0.785, yieldOil:0.185, source:'测试'},
    may: {available: true, mealSymbol:'M2705', mealPrice:3300, oilSymbol:'Y2705', oilPrice:8300, beanSymbol:'B2705', beanPrice:3900, grossMargin: -50, yieldMeal:0.785, yieldOil:0.185, source:'测试'},
    jan: {available: false, reason: '测试用不可用'},
  },
};
refreshCrushMarginForContract('sep');
check('★切换到sep合约时应该显示sep对应的豆粕合约代码(M2609)', makeEl('crushContent').innerHTML.includes('M2609'));
refreshCrushMarginForContract('may');
check('★切换到may合约时应该显示may对应的豆粕合约代码(M2705)，不是残留sep的', makeEl('crushContent').innerHTML.includes('M2705') && !makeEl('crushContent').innerHTML.includes('M2609'));
refreshCrushMarginForContract('jan');
check('★切换到jan合约(数据不可用)时应该正确显示不可用原因', makeEl('crushContent').innerHTML.includes('测试用不可用'));

// window._syncedData还没有(数据没同步回来)时不应该报错
delete window._syncedData;
try {
  refreshCrushMarginForContract('sep');
  check('★window._syncedData为空时不应该报错(数据还没同步回来的情况)', true);
} catch(e) {
  check('★window._syncedData为空时不应该报错(数据还没同步回来的情况)', false);
}

H.printSummary();
