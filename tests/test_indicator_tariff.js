const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());
window._selectedContract = 'sep';

// ===================== 测试1：粘贴解析能识别关税这个新指标 =====================
const example = `对美豆进口关税(%) 13% 2026年9月 中美经贸磋商`;
const parsed = parsePastedData(example);
check('★应该正确识别对美豆进口关税这个新指标', !!parsed.m_tariff);
check('★数值应该正确解析为13', parsed.m_tariff && parsed.m_tariff.value === 13);

// ===================== 测试2：★核心设计验证——关税不应该影响综合评分 =====================
function resetAllFields(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry','m_rmspread','m_reserve','m_tariff'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  elements['alertContent'] = makeEl('alertContent');
}

resetAllFields();
elements['m_hogratio'].value = '8'; // 随便填一个会计分的指标，确保评分逻辑本身在跑
updateOverallAlert();
const scoreWithoutTariff = elements['alertContent'].innerHTML.match(/([+-]?\d+)分/);

resetAllFields();
elements['m_hogratio'].value = '8'; // 同样的指标
elements['m_tariff'].value = '13';  // ★额外填一个关税值，其他完全不变
updateOverallAlert();
const scoreWithTariff = elements['alertContent'].innerHTML.match(/([+-]?\d+)分/);

check('★关键测试：填不填关税，综合评分的分数应该完全一样(关税不计入评分)', 
  scoreWithoutTariff && scoreWithTariff && scoreWithoutTariff[1] === scoreWithTariff[1]);

// 换几个不同的关税数值，反复验证分数都不变(不是恰好这一个值没触发，而是这项彻底不参与计分)
[0, 13, 25, 50, -5].forEach(tariffVal => {
  resetAllFields();
  elements['m_hogratio'].value = '8';
  elements['m_tariff'].value = String(tariffVal);
  updateOverallAlert();
  const score = elements['alertContent'].innerHTML.match(/([+-]?\d+)分/);
  check(`★关税填${tariffVal}时分数应该跟不填时一样(不参与计分)`, score && scoreWithoutTariff && score[1] === scoreWithoutTariff[1]);
});

// ===================== 测试3：renderCrushMargin正确显示关税提示(仅供参考) =====================
makeEl('crushBadge'); makeEl('crushContent');
const marginData = {
  available: true, mealSymbol:'M2609', mealPrice:3400, oilSymbol:'Y2609', oilPrice:8500,
  beanSymbol:'B2609', beanPrice:4000, grossMargin: 100, yieldMeal:0.785, yieldOil:0.185, source:'测试',
};
elements['m_tariff'] = makeEl('m_tariff');
elements['m_tariff'].value = '13';
renderCrushMargin(marginData, new Date().toISOString());
check('★压榨利润卡片应该显示关税提示(13%)', makeEl('crushContent').innerHTML.includes('13%'));
check('★关税提示应该明确标注"仅供参考"', makeEl('crushContent').innerHTML.includes('仅供参考'));
check('★应该说明豆二盘面价格已包含关税成本，不重复计入公式', makeEl('crushContent').innerHTML.includes('不重复计入公式'));

// 没填关税时不应该显示这个提示区块，也不应该报错
elements['m_tariff'].value = '';
renderCrushMargin(marginData, new Date().toISOString());
check('★没填关税时不应该显示关税提示区块', !makeEl('crushContent').innerHTML.includes('当前对美豆进口关税'));

H.printSummary();
