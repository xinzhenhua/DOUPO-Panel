const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：数据不可用时的降级显示 =====================
makeEl('crushBadge'); makeEl('crushContent');
renderCrushMargin({available: false, reason: '豆油Y2609接口调用失败'}, new Date().toISOString());
check('★数据不可用时应该显示具体原因(点名哪个合约缺失)', makeEl('crushContent').innerHTML.includes('豆油Y2609'));

renderCrushMargin(null, new Date().toISOString());
check('传null不应该报错，应该有兜底文字', makeEl('crushContent').innerHTML.includes('未知原因'));

// ===================== 测试2：★榨利的绝对数没有意义——毛利为正/为负都不能据此判方向 =====================
// 旧规则"毛利>0就偏空、<0就偏多"：这里算的是毛利(没扣加工费)，几乎永远为正，等于永远偏空。v90起改成"跟历史同期比的分位"。
makeEl('crushBadge'); makeEl('crushContent');
const positiveMargin = {
  available: true, contractMonth: 9, date: new Date().toISOString().slice(0,10),
  mealSymbol: 'M2609', mealPrice: 3400, oilSymbol: 'Y2609', oilPrice: 8500,
  beanSymbol: 'B2609', beanPrice: 4000, grossMargin: 241.5,
  yieldMeal: 0.785, yieldOil: 0.185, source: '测试',
};
renderCrushMargin(positiveMargin, new Date().toISOString());
check('★回归：毛利为正(+241.5)、没有历史分位时，不再判"偏空"(不是bear样式)', !makeEl('crushContent').innerHTML.includes('alert-box bear') && makeEl('crushContent').innerHTML.includes('alert-box neutral'));
check('★没有历史分位时说明"历史同期样本积累中，暂不计分"，并写明"毛利的绝对数没有意义"', makeEl('crushContent').innerHTML.includes('样本积累中') && makeEl('crushContent').innerHTML.includes('绝对数没有意义'));
check('★应该明确标注"未扣加工费"，不能让人误以为是精确净利润', makeEl('crushContent').innerHTML.includes('未扣加工费'));
check('★卡片写明"暂不计入综合评分"', makeEl('crushContent').innerHTML.includes('暂不计入综合评分'));
check('三个合约的价格明细都应该显示', makeEl('crushContent').innerHTML.includes('3400') && makeEl('crushContent').innerHTML.includes('8500') && makeEl('crushContent').innerHTML.includes('4000'));
check('★window._crushSignal=null(渲染过但没有信号)，状态=pending', window._crushSignal === null && window._crushStatus === 'pending');

makeEl('crushBadge'); makeEl('crushContent');
renderCrushMargin({...positiveMargin, grossMargin: -150}, new Date().toISOString());
check('★回归：毛利为负(-150)、没有历史分位时，同样不判方向(不是bull样式)', !makeEl('crushContent').innerHTML.includes('alert-box bull') && window._crushSignal === null);

// ===================== 测试3：有历史同期分位 → 判方向 =====================
const withSeasonal = (pct, n)=>({...positiveMargin, history:{n:800, minPoints:12, since:'2018-04-02', percentile:pct, min:-200, max:600, median:150, sparse:null, window:null, cohort:null, seasonal:{month:7, n:n===undefined?160:n, percentile:pct, median:150}}});
renderCrushMargin(withSeasonal(85), new Date().toISOString());
check('★历史同期分位85%(≥80)：偏空(bear)，写明"油厂压榨动力强，豆粕供应将增加"', window._crushSignal === -1 && makeEl('crushContent').innerHTML.includes('alert-box bear') && makeEl('crushContent').innerHTML.includes('压榨动力强') && makeEl('crushContent').innerHTML.includes('85%分位'));
check('★写明"参与综合评分"', makeEl('crushContent').innerHTML.includes('参与综合评分') && window._crushStatus === 'ok');
renderCrushMargin(withSeasonal(10), new Date().toISOString());
check('★历史同期分位10%(≤20)：偏多(bull)，写明"可能降负荷，豆粕供应收缩"', window._crushSignal === 1 && makeEl('crushContent').innerHTML.includes('alert-box bull') && makeEl('crushContent').innerHTML.includes('降负荷'));
renderCrushMargin(withSeasonal(50), new Date().toISOString());
check('分位50%：中性(常态区间)', window._crushSignal === 0 && makeEl('crushContent').innerHTML.includes('常态区间'));
check('边界：80%偏空、20%偏多、79.9%/20.1%中性', crushSignalFrom(withSeasonal(80)) === -1 && crushSignalFrom(withSeasonal(20)) === 1 && crushSignalFrom(withSeasonal(79.9)) === 0 && crushSignalFrom(withSeasonal(20.1)) === 0);
check('★同月样本不足20个 → 不判(null)，即使分位是95%', crushSignalFrom(withSeasonal(95, 19)) === null && crushSignalFrom(withSeasonal(95, 20)) === -1);
check('没有history/seasonal字段 → null', crushSignalFrom(positiveMargin) === null && crushSignalFrom({...positiveMargin, history:{n:5, seasonal:null}}) === null && crushSignalFrom(null) === null);
check('★方向：榨利越高越偏空(pol=-1)——历史分位高时"绝对阈值判偏空"的一致性提示不会误触发', makeEl('crushContent').innerHTML.includes('历史分位'));

// 新鲜度：日频按交易日
window._nowMs = null;
const dayAgo = n=>new Date(Date.now()-n*86400000).toISOString().slice(0,10);
renderCrushMargin({...withSeasonal(90), date: dayAgo(30)}, new Date().toISOString());
check('★盘面数据30天前(错过很多交易日)：过期，不判方向、不投票，写明原因', window._crushSignal === null && window._crushStatus === 'stale' && makeEl('crushContent').innerHTML.includes('已过期') && makeEl('crushContent').innerHTML.includes('不参与评分'));
renderCrushMargin({...withSeasonal(90), date: undefined}, new Date().toISOString());
check('数据日期未知：当作正常(不因为缺日期就排除)，仍判方向', window._crushSignal === -1);
// 晚了一期→质量×0.5：固定"现在"再测(不依赖运行当天是星期几)
const Ev = window._eventCal;
window._nowMs = Ev.bjToMs(2026,9,30,10,0);
renderCrushMargin({...withSeasonal(90), date:'2026-09-25'}, new Date().toISOString());     // 周五数据，周三10点：错过周一、周二2个交易日 → 晚了一期
check('★盘面数据晚了一期(错过2个交易日)：信号仍在，质量乘数×0.5', window._crushSignal === -1 && window._crushQuality.m === 0.5 && window._crushQuality.why.includes('晚了一期'));
renderCrushMargin({...withSeasonal(90), date:'2026-09-29'}, new Date().toISOString());
check('数据日期昨天：正常，乘数1', window._crushQuality.m === 1);
window._nowMs = null;

// ===================== 测试3b：进综合评分 =====================
const AUTO = window._autoIndicators;
function resetScore(){
  AUTO.forEach(c=>{ makeEl(c.inputId).value=''; makeEl('ind_'+c.key); makeEl('alert_'+c.key); });
  window._indState = {}; makeEl('alertContent');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
  window._selectedContract='sep'; H.setMockedMonth(5);
  const fill = {crush:'50', stock:'70', basis:'0', arrival:'900', import:'900', hogratio:'6', poultry:'1', rmspread:'550'};
  Object.keys(fill).forEach(k=>makeEl('m_'+k).value = fill[k]);
}
const cellOf = ()=> (makeEl('alertContent').innerHTML.match(/sd-cell (sd-\w+)">盘面压榨毛利[^<]*/)||[]);
resetScore(); window._crushSignal = undefined; updateOverallAlert();
check('★还没渲染过榨利卡片(undefined)：这一票不在投票清单里(供需表格里没有)', !/sd-cell[^>]*>盘面压榨毛利/.test(makeEl('alertContent').innerHTML));
resetScore(); window._crushSignal = null; window._crushQuality = null; updateOverallAlert();
check('★渲染过但没有信号(null，历史样本积累中)：这一票在清单里但没数据——作为"缺席的投票"如实列出', /sd-cell sd-empty">盘面压榨毛利/.test(makeEl('alertContent').innerHTML) && window._quality.missing.some(x=>x.includes('盘面压榨毛利')));
resetScore(); window._crushSignal = -1; window._crushQuality = {m:1, why:''}; updateOverallAlert();
check('★榨利偏空：供需表格里"盘面压榨毛利"是偏空格(▼)，属于供给侧', cellOf()[1] === 'sd-neg' && makeEl('alertContent').innerHTML.includes('盘面压榨毛利(供给响应) ▼'));
check('★属于"国内供应链"分组(与国内供应松紧、到港进口同组)', voteGroup('盘面压榨毛利(供给响应)') === 'domestic');
check('详细理由里写明偏空原因', makeEl('alertContent').innerHTML.includes('油厂压榨动力强，豆粕供应将增加'));
resetScore(); window._crushSignal = 1; window._crushQuality = {m:1, why:''}; updateOverallAlert();
check('榨利偏多：偏多格(▲)', cellOf()[1] === 'sd-pos');
resetScore(); window._crushSignal = -1; window._crushQuality = {m:0.5, why:'盘面数据晚了一期'}; updateOverallAlert();
check('★榨利数据晚了一期：票权×0.5，质量分里点名', window._quality.lowItems.some(x=>x.label.includes('盘面压榨毛利') && x.q === 0.5));
// 对总分的影响：一个偏空票让净倾向下降
resetScore(); window._crushSignal = 0; updateOverallAlert();
const neutralRatio = window._dimensions.supply.ratio;
resetScore(); window._crushSignal = -1; window._crushQuality = {m:1, why:''}; updateOverallAlert();
check('★榨利偏空 → 供给端净倾向比中性时更低(1票偏空)', window._dimensions.supply.ratio < neutralRatio);
H.clearMockedMonth(); window._crushSignal = undefined; window._selectedContract = 'sep';

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
