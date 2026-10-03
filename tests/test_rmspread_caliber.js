// ============================================================================
// 豆菜粕价差：新口径(多城市单值平均，2026-06起约800~900)读数不再按旧阈值(<400偏多、>700偏空)计分
// 依据：旧阈值按"沿海地区价差区间中点"(300~760，均值<700)标定；新口径真实读数823.3永远>700，会天天误判偏空。
// 新口径只有约3.5个月历史，没法重新标定 → 暂不计分(显示事实+继续累积历史)。旧口径/手填值照常。
// ============================================================================
const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
const E = window._eventCal;
const AUTO = window._autoIndicators;
const KEYS = AUTO.map(c=>c.key);
const html = k=>makeEl('ai_'+k).innerHTML;
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); });
  window._indState = {}; makeEl('alertContent'); makeEl('structureContent');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
  window._selectedContract='sep';
}
const NOW = E.bjToMs(2026,10,1,10,0);
// 真实读数(latest.json 2026-09-30)：广东800/广西790/南通880，平均823.3，formatUsed='多城市单值平均'
const CITY = {available:true, value:823.3, citySamples:[800,790,880], date:'2026-09-30', formatUsed:'多城市单值平均', rawContent:'x', source:'Mysteel文章(豆菜粕价差)', sourceUrl:'x'};
// 旧口径：沿海地区区间320-440的中点380
const RANGE = {available:true, value:380, rangeLow:320, rangeHigh:440, date:'2026-05-29', formatUsed:'区间中点', rawContent:'x', source:'Mysteel文章(豆菜粕价差)', sourceUrl:'x'};
function load(rm, nowMs){
  reset(); window._nowMs = nowMs || NOW;
  window._syncedData = {generatedAt:new Date(window._nowMs).toISOString(), mysteelRmSpread: rm};
  refreshMysteelRmSpread();
  return window._indState.rmspread;
}
const rule = window._manualRules.rmspread;

// ===================== 1. 新口径：不计分 =====================
let st = load(CITY);
check('★真实读数823.3(三城市单值平均)：规则返回[null,…]——不再天天判偏空(旧阈值>700会判-1)', rule(823.3)[0] === null && st.caliber === 'cities');
check('★原因写明：口径变了、旧阈值按区间中点标定、新读数约800~900永远>700、累积够历史后改用分位', rule(823.3)[1].includes('口径') && rule(823.3)[1].includes('400/700') && rule(823.3)[1].includes('永远>700') && rule(823.3)[1].includes('分位'));
updateOverallAlert();
check('★评分里没有豆菜粕价差这一票：出现在"缺席的投票"里', window._quality.missing.includes('豆菜粕价差'));
check('★卡片结论框写明"口径变了，暂不计分"，不是"历史样本积累中"(那是饲料库存天数的原因)', makeEl('alert_rmspread').innerHTML.includes('口径') && !makeEl('alert_rmspread').innerHTML.includes('历史样本积累中'));

// ===================== 2. 旧口径/手填：照常(旧规则) =====================
st = load(RANGE);
check('旧口径(区间320-440的中点380)：照常按旧阈值——<400偏多(+1)', st.caliber === 'range' && rule(380)[0] === 1);
check('旧口径的其它值：550中性(0)、750偏空(-1)——旧规则行为完全不变', rule(550)[0] === 0 && rule(750)[0] === -1 && rule(400)[0] === 0 && rule(700)[0] === 0 && rule(399.9)[0] === 1 && rule(700.1)[0] === -1);
st = load(CITY);
makeEl('m_rmspread').value = '550'; onManualEdit('rmspread');
check('★用户手填550(视为按旧口径自己负责)：照常计分，不再被新口径抑制——caliber清空', window._indState.rmspread.caliber === '' && rule(550)[0] === 0 && rule(750)[0] === -1);
reset(); window._indState.rmspread = {};
check('没有任何抓取状态(纯手填场景)：旧规则照常(所有现有的手填测试都靠这个)', rule(300)[0] === 1 && rule(550)[0] === 0 && rule(800)[0] === -1);

// ===================== 3. 进总分：影响手算 =====================
// 用真实场景：需求侧里豆菜粕价差从"-1票"变成"缺席"。构造5个需求票全中性+豆菜粕新口径823.3：
//   旧行为：豆菜粕价差判偏空(-1)，需求侧净倾向被拉低；新行为：这一票缺席，不影响
function scenario(withCity){
  reset(); window._nowMs = NOW;
  window._psdSignal = 1; window._fxSignal = 1; makeEl('m_hogratio').value = '6'; makeEl('m_poultry').value = '1'; makeEl('m_stu').value = '12';
  if(withCity){ window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelRmSpread: CITY}; refreshMysteelRmSpread(); }
  else { makeEl('m_rmspread').value = '823.3'; window._indState.rmspread = {}; }
  updateOverallAlert();
  return {demand: window._dimensions.demand, html: makeEl('alertContent').innerHTML, missing: window._quality.missing.slice()};
}
const newB = scenario(true), oldB = scenario(false);
check('★同样的823.3：新口径下需求侧少一个投票(缺席)，旧规则(手填无口径信息)下多一个偏空票——需求侧有效票数差1', newB.demand.n === oldB.demand.n - 1);
check('★新口径下需求侧净倾向不再被这一票压低：新≥旧(旧规则多了一票-1)', newB.demand.ratio >= oldB.demand.ratio && oldB.demand.ratio < newB.demand.ratio);
check('评分规则版本v99', window._scoringVersion === 'v99');
H.printSummary();
