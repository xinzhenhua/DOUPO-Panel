// ============================================================================
// 春节感知(国内库消比)：春节扰动月不判方向/不投票、票权规则、同类月份分位、样本不连续时不给分位
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
window._selectedContract = 'sep';
H.setMockedMonth(2);
const AUTO = window._autoIndicators;
const dayStr = n => new Date(Date.now() - n*86400000).toISOString().slice(0,10);
const KEYS = AUTO.map(c=>c.key);
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); window._indState[k] = {}; });
  makeEl('alertContent');
  window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null;
  window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
}
function neutralBase(){
  reset();
  const v = {crush:50, stock:70, basis:0, arrival:900, import:900, hogratio:6, sows:3750, poultry:1, rmspread:550, reserve:0};
  Object.keys(v).forEach(k=>makeEl('m_'+k).value = String(v[k]));
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0;
  window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
}
const html = ()=>makeEl('alertContent').innerHTML;
const cell = ()=> (html().match(/sd-cell (sd-\w+)">国内豆粕供应松紧( ×2)?/)||[]);
const stu = (o)=>Object.assign({available:true, value:20.95, month:'2026-02', monthLabel:'2026年2月', isForecast:false, usedFallbackMonth:false,
  method:'stated', methodLabel:'文章明示', recordSource:'body', stockWan:93, consumptionWan:444, productionWan:500, next:null, trend:null, weeklyCheck:null,
  date:dayStr(3), articleAgeDays:3, articleTitle:'x',
  festival:{festivalDate:'2026-02-17', coreDays:22, disturbed:true, phase:'假期停摆', bias:'养殖/饲料/贸易停摆，月消费骤降，库消比容易被机械抬高'}}, o||{});

// ===================== 1. 春节扰动月：显示但不判方向、不投票 =====================
neutralBase();
window._syncedData = {mysteelMealStu: stu()};
refreshMysteelMealStu();
check('★春节扰动月：库消比数值照常填入(20.95%，方便查看)', makeEl('m_stu').value == '20.95');
check('★徽标：春节扰动期·不计分', makeEl('badge_stu').textContent.includes('春节扰动期') && makeEl('badge_stu').textContent.includes('不计分'));
let ai = makeEl('ai_stu').innerHTML;
check('★详情：说明春节日期、核心窗口天数、阶段、对库消比的影响，以及为什么不判方向', ai.includes('春节扰动月') && ai.includes('2026-02-17') && ai.includes('22天') && ai.includes('假期停摆') && ai.includes('月消费骤降') && ai.includes('不据此判偏多偏空'));
check('★结论框：不是偏空(20.95%虽然≥16%)，而是中性色+"不判方向"', makeEl('alert_stu').innerHTML.includes('alert-box neutral') && makeEl('alert_stu').innerHTML.includes('春节扰动期') && !makeEl('alert_stu').innerHTML.includes('alert-box bear') && makeEl('alert_stu').innerHTML.includes('不参与综合评分'));
updateOverallAlert();
check('★综合评分里不投票：20.95%没有把这一组拉向偏空(全中性基线仍是"信号混合")，国内供应松紧回退到库存+开机率，只算1票(没有×2)',
  html().includes('信号混合 0（') && cell()[1]==='sd-neutral' && !cell()[2]);
check('详细理由里写明春节扰动月未计入评分', html().includes('春节扰动月，未计入评分'));

// 对照：同样20.95%，不在春节扰动月 → 正常判偏空、投2票
neutralBase();
window._syncedData = {mysteelMealStu: stu({festival:{festivalDate:'2026-02-17', coreDays:0, disturbed:false, phase:null, bias:null}, month:'2026-08', monthLabel:'2026年8月'})};
refreshMysteelMealStu();
updateOverallAlert();
check('★对照：同样20.95%但不是春节扰动月 → 判偏空，国内供应松紧偏空且票权×2', makeEl('alert_stu').innerHTML.includes('alert-box bear') && cell()[1]==='sd-neg' && cell()[2]===' ×2' && makeEl('badge_stu').textContent.includes('自动'));

// 没有festival字段(latest.json还是旧版)：按平常月处理，不报错
neutralBase();
const noFest = stu(); delete noFest.festival;
window._syncedData = {mysteelMealStu: noFest};
let ok = true; try{ refreshMysteelMealStu(); updateOverallAlert(); }catch(e){ ok=false; }
check('没有festival字段时不报错，按平常月处理', ok && makeEl('alert_stu').innerHTML.includes('alert-box bear'));

// 下月是春节扰动月：提示
neutralBase();
window._syncedData = {mysteelMealStu: stu({value:12, month:'2026-01', monthLabel:'2026年1月', festival:{festivalDate:'2026-02-17', coreDays:0, disturbed:false, phase:null},
  next:{month:'2026-02', monthLabel:'2026年2月', value:20, festival:{festivalDate:'2026-02-17', coreDays:22, disturbed:true, phase:'假期停摆'}}})};
refreshMysteelMealStu();
check('★下月是春节扰动月：当月正常判断，同时提示下月不按固定阈值', makeEl('ai_stu').innerHTML.includes('下月(2026年2月)是春节扰动月') && makeEl('alert_stu').innerHTML.includes('alert-box neutral'));

// 手动修正：用户自己填值，视为自己负责，恢复计分
neutralBase();
window._syncedData = {mysteelMealStu: stu()};
refreshMysteelMealStu();
makeEl('m_stu').value = '13';
onManualEdit('stu');
updateOverallAlert();
check('★春节扰动月里用户手动修正了值 → 恢复计分(中性区间13%)，且票权×2回来', window._indState.stu.suppressed === '' && cell()[1]==='sd-neutral' && cell()[2]===' ×2');

// 刷新页面：手动值不会因为春节标记而被丢掉/残留suppressed
neutralBase();
window._syncedData = {mysteelMealStu: stu()};
refreshMysteelMealStu();
window._syncedData = {mysteelMealStu: stu({festival:{festivalDate:'2026-02-17', coreDays:0, disturbed:false, phase:null}})};
refreshMysteelMealStu();
check('下一次抓取不再是春节扰动月时，suppressed被清除，恢复正常计分', window._indState.stu.suppressed === '' && makeEl('badge_stu').textContent.includes('自动'));

// ===================== 2. 票权规则：库消比参与才×2 =====================
neutralBase(); makeEl('m_stu').value='9'; updateOverallAlert();
check('★库消比参与(9%≤10%偏多)：国内供应松紧偏多，×2', cell()[1]==='sd-pos' && cell()[2]===' ×2');
neutralBase(); makeEl('m_stu').value=''; makeEl('m_stock').value='40'; updateOverallAlert();
check('★库消比没有数据：退回库存+开机率(库存偏多60%→偏多)，只算1票、没有×2', cell()[1]==='sd-pos' && !cell()[2]);
neutralBase(); makeEl('m_stu').value='9'; window._indState.stu = {stale:true, mode:'auto'}; updateOverallAlert();
check('★库消比数据过期：同样退回1票', !cell()[2]);
neutralBase(); makeEl('m_stu').value='9'; makeEl('m_crush').value='70'; window._psdSignal=1; updateOverallAlert();
check('票权×2时净倾向按有效票权算：库消比9%偏多(组内库消比50+开机率偏空30→(50-30)/100=0.2中性)+美豆库消比偏多 → +1÷10.5(2月作物票在背景档×0.5，总票权=10.5)=+9.5%→四舍五入+10%', html().includes('信号混合 +1（净倾向+10%）'));

// ===================== 3. historyBlock：样本不连续 + 同类月份分位 =====================
const hist = (o)=>Object.assign({n:60, minPoints:12, asOf:'2026-09', since:'2021-09', percentile:88.3, min:5.94, max:16.3, median:12.45, seasonal:null, cohort:null, sparse:null}, o||{});
let t = historyBlock(hist({percentile:null, sparse:'样本不连续：跨1553天应有约222期，实际只有70期(31%)'}), {unit:'万吨'});
check('★样本不连续：明确说"暂不给分位"和原因，不是"积累中"也不给百分位', t.includes('暂不给分位') && t.includes('样本不连续') && t.includes('31%') && !t.includes('%</b>('));
check('★样本不连续的提示里说明"补齐后自动恢复"', t.includes('补齐后自动恢复'));
t = historyBlock(hist({cohort:{label:'春节扰动月', n:5, percentile:80, median:15}}), {unit:'%'});
check('★同类月份分位：春节扰动月只跟往年春节月比', t.includes('同类月份</b>(春节扰动月)分位：<b>80%</b>') && t.includes('5个春节扰动月') && t.includes('春节月只跟往年春节月比'));
t = historyBlock(hist({cohort:{label:'平常月', n:15, percentile:55, median:14}}), {unit:'%'});
check('平常月只跟平常月比', t.includes('(平常月)分位：<b>55%</b>') && t.includes('平常月只跟平常月比'));
t = historyBlock(hist({cohort:{label:'春节扰动月', n:3, percentile:null, median:12}}), {unit:'%'});
check('同类月份样本<4个：说明只有N个、暂不给分位', t.includes('目前只有3个，不足4个，暂不给分位'));

t = historyBlock(hist({window:'整体样本不连续，仅用最近2年的连续样本(2024-10-07起)'}), {unit:'万吨'});
check('★仅用近两年样本时，界面如实说明', t.includes('仅用最近2年的连续样本') && t.includes('ℹ️'));
check('没有window字段时不显示该行', !historyBlock(hist(), {unit:'%'}).includes('仅用最近'));

H.clearMockedMonth();
H.printSummary();
