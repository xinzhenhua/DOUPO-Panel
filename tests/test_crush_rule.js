// ============================================================================
// 油厂开机率评分规则重做(v98)：滚动365天分位(去掉春节窗口)；历史不足时回退固定阈值(旧规则)
// 分位点取自用户真实采样(2024-12~2026-09，去掉春节窗口后120个读数)：p20=52.6、中位61.6、p80=66.7
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
// 21个分位点(0%,5%,...,100%)：真实分布的形状(p0=25.15是2025-04关税战低谷；p20=q[4]=52.6；p50=q[10]=61.6；p80=q[16]=66.7)
const Q = [25.15,38.5,43.5,49.0,52.6,53.7,56.0,58.2,60.1,61.0,61.6,62.6,63.8,65.0,66.0,66.4,66.7,67.5,68.2,69.3,73.27];
const trailing = (o)=>Object.assign({n:235, windowDays:365, minN:120, asOf:'2026-09-29', since:'2025-09-29', median:61.6, percentile:48.0, quantiles:Q, enough:true}, o||{});
const crushData = (value, date, o)=>Object.assign({available:true, value, date, festival:null, rawContent:'x', source:'Mysteel快讯', sourceUrl:'x',
  history:{n:350, minPoints:12, asOf:date, since:'2024-12-13', percentile:50, seasonal:null, trailing:trailing()}}, o||{});
const NOW = E.bjToMs(2026,9,30,10,0);
function load(value, date, o, nowMs){
  reset(); window._nowMs = nowMs || NOW;
  window._syncedData = {generatedAt:new Date(window._nowMs).toISOString(), mysteelCrushRate: crushData(value, date, o)};
  refreshMysteelCrushRate();
  return window._indState.crush;
}
const rule = window._manualRules.crush;
function ruleWith(tr, v){ reset(); window._indState.crush = {history: tr === undefined ? undefined : {trailing: tr}}; return rule(v); }

// ===================== 1. 新规则(有足够历史) =====================
let r = ruleWith(trailing(), 60.95);
check('★今天的60.95%：旧规则(>60)判偏空，新规则按近365天分位(约48%)判中性(0)——这是重做的核心', r[0] === 0 && r[1].includes('60.95%') && r[1].includes('近365天') && r[1].includes('235个读数') && r[1].includes('常态区间52.6~66.7%'));
r = ruleWith(trailing(), 68.2);
check('★68.2%(≥p80=66.7)：偏空，写明"油厂开工强、豆粕供应充足"和≥66.7', r[0] === -1 && r[1].includes('偏空') && r[1].includes('66.7') && r[1].includes('供应充足'));
r = ruleWith(trailing(), 50.0);
check('★50.0%(≤p20=52.6)：偏多，写明"开工弱、豆粕供应偏紧"', r[0] === 1 && r[1].includes('偏多') && r[1].includes('52.6') && r[1].includes('偏紧'));
check('边界：恰好=p80(66.7)→偏空；恰好=p20(52.6)→偏多；比p80低0.1(66.6)→中性；比p20高0.1(52.7)→中性', ruleWith(trailing(), 66.7)[0] === -1 && ruleWith(trailing(), 52.6)[0] === 1 && ruleWith(trailing(), 66.6)[0] === 0 && ruleWith(trailing(), 52.7)[0] === 0);
r = ruleWith(trailing(), 35.0);
check('★旧规则的盲区：35%旧规则判偏多(<40)，新规则下也是偏多(远低于p20)；而旧规则判偏空的62%/64%，新规则判中性', r[0] === 1 && ruleWith(trailing(), 62.0)[0] === 0 && ruleWith(trailing(), 64.0)[0] === 0);
r = ruleWith(trailing(), 73.0);
check('极端高值(>p100附近)：仍是偏空，分位写成接近100%', r[0] === -1 && /9\d(\.\d)?%分位|100%分位/.test(r[1]));

// ===================== 2. 对任意值(含手填)按分位点表算位置 =====================
const pf = window._pctFromQuantiles;
check('★分位点→百分位：等于分位点本身时给出对应百分位(q[4]=52.6→20、q[10]=61.6→50、q[16]=66.7→80)；两点之间线性插值', Math.abs(pf(52.6, Q)-20)<0.01 && Math.abs(pf(61.6, Q)-50)<0.01 && Math.abs(pf(66.7, Q)-80)<0.01 && Math.abs(pf((52.6+53.7)/2, Q)-22.5)<0.01);
check('超出范围：低于p0→0，高于p100→100', pf(10, Q) === 0 && pf(99, Q) === 100);
check('分位点有并列(平段)时不除零：[60,60,60,...]', Number.isFinite(pf(60, new Array(21).fill(60))) && Number.isFinite(pf(59, new Array(21).fill(60))));

// ===================== 3. 手填的值也按分位算(不是沿用自动值的分位) =====================
const stA = load(60.95, '2026-09-29');
check('前置：自动读数60.95%按分位判中性', window._manualRules.crush(60.95)[0] === 0);
makeEl('m_crush').value = '68.5'; onManualEdit('crush');
check('★用户手填68.5%：按68.5%自己的位置判偏空(≥p80)，不是沿用自动值60.95%的中性——历史挂在状态里，规则对传入的值重新算', window._manualRules.crush(68.5)[0] === -1 && window._indState.crush.history.trailing.enough === true);
makeEl('m_crush').value = '45'; onManualEdit('crush');
check('手填45%：偏多(≤p20)', window._manualRules.crush(45)[0] === 1);

// ===================== 4. 历史不足：回退固定阈值(旧规则)，保持原行为 =====================
for (const [label, tr] of [['没有history', undefined], ['trailing为null', null], ['样本不足(enough=false)', trailing({enough:false, n:97})], ['没有分位点表', trailing({quantiles:null})], ['分位点表长度不对', trailing({quantiles:[1,2,3]})]]){
  const a = ruleWith(tr, 35), b = ruleWith(tr, 70), c = ruleWith(tr, 50);
  check(`★回退旧规则(${label})：35%→偏多、70%→偏空、50%→中性，文字与旧规则完全一致`, a[0] === 1 && a[1] === '开机率35%（&lt;40%）→ 偏多' && b[0] === -1 && b[1] === '开机率70%（&gt;60%）→ 偏空' && c[0] === 0 && c[1] === '开机率50%（中性区间）');
}
check('★退化的分位点表(p80<=p20，如全部相同)：不用来计分，回退旧规则', ruleWith(trailing({quantiles:new Array(21).fill(60)}), 70)[0] === -1 && ruleWith(trailing({quantiles:new Array(21).fill(60)}), 70)[1].includes('&gt;60%'));


// ===================== 4b. 变异检查补的边界(原测试的盲区) =====================
// 分位点表长度必须恰好是21：长度错但q[4]、q[16]都有值的表(20个或22个点)不能被拿来用
const Q22 = Q.concat([80]), Q20 = Q.slice(0, 20);
check('★分位点表长度不是21(22个/20个，但q[4]、q[16]都存在)：不用来计分，回退旧规则——原先只测了长度3(此时q[16]是undefined，碰巧也回退)。证据：62%在新规则下是中性(0)，回退旧规则才是偏空(-1)', [Q22, Q20].every(t => ruleWith(trailing({quantiles:t}), 70)[1] === '开机率70%（&gt;60%）→ 偏空' && ruleWith(trailing({quantiles:t}), 62)[0] === -1 && ruleWith(trailing({quantiles:t}), 62)[1] === '开机率62%（&gt;60%）→ 偏空') && ruleWith(trailing(), 62)[0] === 0);
// 回退的旧规则：严格小于40偏多、严格大于60偏空，40和60本身是中性(边界)
check('★回退旧规则的边界：39.9→偏多、40→中性、60→中性、60.1→偏空(原来只测了35/50/70，阈值40改成45也过)', ruleWith(undefined, 39.9)[0] === 1 && ruleWith(undefined, 40)[0] === 0 && ruleWith(undefined, 44.9)[0] === 0 && ruleWith(undefined, 60)[0] === 0 && ruleWith(undefined, 60.1)[0] === -1 && ruleWith(undefined, 55)[0] === 0);
// 回退时的详情要写明"为什么"——那句解释偏空触发过多的话本身
load(60.95, '2026-09-29', {history:{n:3, minPoints:12, asOf:'2026-09-29', since:'2026-09-27', percentile:null, seasonal:null, trailing:trailing({enough:false, n:3})}});
check('★回退详情里写明"这个阈值在近一年的水平下偏空触发过多"和"常态中位数就是61.6%"(让人知道为什么要回填)', html('crush').includes('偏空触发过多') && html('crush').includes('常态中位数就是61.6%') && html('crush').includes('only=crush_rate'));

// ===================== 5. 回退时卡片详情要说明为什么、怎么办 =====================
load(60.95, '2026-09-29', {history:{n:3, minPoints:12, asOf:'2026-09-29', since:'2026-09-27', percentile:null, seasonal:null, trailing:trailing({enough:false, n:3})}});
check('★回退时详情写明：历史不足、暂用固定阈值、该阈值偏空触发过多(约56%)、运行回填后改用滚动分位', html('crush').includes('历史不足') && html('crush').includes('暂用固定阈值') && html('crush').includes('56%') && html('crush').includes('回填'));
load(60.95, '2026-09-29');
check('有足够历史时详情写明用的是滚动分位(近365天、n、起点)，不出现"暂用固定阈值"', html('crush').includes('近365天') && html('crush').includes('2025-09-29') && !html('crush').includes('暂用固定阈值'));

// ===================== 6. 春节窗口仍然压过一切 =====================
const f1 = load(15.46, '2026-02-24', {festival:{name:'春节', daysTo:7, phase:'假期', holidayDate:'2026-02-17'}}, E.bjToMs(2026,2,25,10,0));
check('★春节窗口内：仍是"扰动期不计分"(suppressed)，不管分位点表说什么', f1.suppressed.startsWith('春节后7天'));

// ===================== 7. 进评分：国内供应松紧里开机率这一项变了 =====================
reset(); window._nowMs = NOW;
makeEl('m_stu').value = '12'; makeEl('m_stock').value = '70'; makeEl('m_crush').value = '60.95';
window._indState.crush = {history:{trailing:trailing()}};
updateOverallAlert();
const newTight = makeEl('alertContent').innerHTML;
reset(); makeEl('m_stu').value = '12'; makeEl('m_stock').value = '70'; makeEl('m_crush').value = '60.95';
window._indState.crush = {};
updateOverallAlert();
const oldTight = makeEl('alertContent').innerHTML;
check('★同样的60.95%：旧规则下国内供应松紧里开机率是偏空(−1)，新规则下是中性(0)——两个页面输出的"国内供应松紧"理由不同', newTight.includes('开机率中性') && oldTight.includes('开机率偏空'));


// ===================== 9. v99：三档——往年同月分位 → 近365天滚动分位 → 固定阈值 =====================
// 同月分位点表：p20=q[4]=55、p80=q[16]=64(比滚动的52.6/66.7窄)，这样每个读数都能分辨"到底用了哪一档"：
//   65：同月≥64偏空，滚动<66.7中性；54：同月≤55偏多，滚动>52.6中性；60：两档都中性
const QS = [30,40,45,50,55,56,57,58,59,60,60.5,61,62,62.5,63,63.5,64,65,66,68,72];
const sameMonth = (o)=>Object.assign({month:11, n:41, years:[2024,2025], since:'2024-11-01', median:60.5, percentile:55, quantiles:QS, enough:true, minN:20}, o||{});
function ruleBoth(sm, tr, v){ reset(); window._indState.crush = {history:{sameMonth:sm, trailing:tr}}; return rule(v); }
let t3 = ruleBoth(sameMonth(), trailing(), 65);
check('★第一档：往年同月够用时优先于滚动分位——65%在同月(≥64)判偏空，若用滚动(<66.7)则是中性', t3[0] === -1 && t3[1].includes('往年同月') && t3[1].includes('11月') && t3[1].includes('2024/2025年') && t3[1].includes('41个读数') && t3[1].includes('≥64%'));
t3 = ruleBoth(sameMonth(), trailing(), 54);
check('★54%在同月(≤55)判偏多，若用滚动(>52.6)则是中性；写明≤55%', t3[0] === 1 && t3[1].includes('往年同月') && t3[1].includes('≤55%') && t3[1].includes('偏紧'));
check('60%：同月中性，文字写常态区间55~64%', ruleBoth(sameMonth(), trailing(), 60)[0] === 0 && ruleBoth(sameMonth(), trailing(), 60)[1].includes('常态区间55~64%'));
check('边界：恰好=同月p80(64)→偏空；恰好=p20(55)→偏多；63.9/55.1→中性', ruleBoth(sameMonth(), trailing(), 64)[0] === -1 && ruleBoth(sameMonth(), trailing(), 55)[0] === 1 && ruleBoth(sameMonth(), trailing(), 63.9)[0] === 0 && ruleBoth(sameMonth(), trailing(), 55.1)[0] === 0);
// 第二档：同月不够 → 滚动
t3 = ruleBoth(sameMonth({enough:false, n:16}), trailing(), 65);
check('★同月参照不够(enough=false，如10月只有16个<20)：退到滚动分位——65%判中性，文字写近365天，不出现"往年同月"', t3[0] === 0 && t3[1].includes('近365天') && !t3[1].includes('往年同月'));
check('同月没有分位点表/长度不是21/退化(q80<=q20)：都退到滚动分位', [null, [1,2,3], QS.concat([80]), new Array(21).fill(60)].every(q => ruleBoth(sameMonth({quantiles:q}), trailing(), 65)[1].includes('近365天')));
check('同月为null/没有sameMonth字段：直接用滚动(v98的行为不变)', ruleBoth(null, trailing(), 65)[1].includes('近365天') && ruleBoth(undefined, trailing(), 65)[1].includes('近365天'));
// 第三档：都不够 → 固定阈值
t3 = ruleBoth(sameMonth({enough:false}), trailing({enough:false, n:50}), 65);
check('★两档都不够：回退固定阈值(>60偏空)，文字与旧规则完全一致', t3[0] === -1 && t3[1] === '开机率65%（&gt;60%）→ 偏空' && ruleBoth(null, null, 35)[1] === '开机率35%（&lt;40%）→ 偏多');
// 手填的值也按同月分位表算
load(60.95, '2026-11-20', {history:{n:350, minPoints:12, asOf:'2026-11-20', since:'2024-12-13', percentile:50, seasonal:null, trailing:trailing(), sameMonth:sameMonth()}});
check('前置：自动读数60.95%在同月中性', window._manualRules.crush(60.95)[0] === 0);
makeEl('m_crush').value = '66'; onManualEdit('crush');
check('★用户手填66%：按同月分位表判偏空(≥64)——规则对传入的值重新算，不沿用自动值', window._manualRules.crush(66)[0] === -1 && window._manualRules.crush(66)[1].includes('往年同月'));
// 卡片详情
load(60.95, '2026-11-20', {history:{n:350, minPoints:12, asOf:'2026-11-20', since:'2024-12-13', percentile:50, seasonal:null, trailing:trailing(), sameMonth:sameMonth()}});
check('★详情(第一档)：写明评分口径=往年同月分位、年份与读数数、去掉春节窗口和关税战、同月不够会自动退滚动', html('crush').includes('评分口径(v99)') && html('crush').includes('往年同月') && html('crush').includes('2024/2025年') && html('crush').includes('关税战') && html('crush').includes('自动退'));
load(60.95, '2026-10-20', {history:{n:350, minPoints:12, asOf:'2026-10-20', since:'2024-12-13', percentile:50, seasonal:null, trailing:trailing(), sameMonth:sameMonth({month:10, n:16, years:[2025], enough:false})}});
check('★详情(第二档)：同月不够时写明"10月往年同月只有16个读数(<20)，暂用近365天滚动分位"', html('crush').includes('10月') && html('crush').includes('16个') && html('crush').includes('近365天') && !html('crush').includes('评分口径(v99)：往年同月'));
// 评分里的效果：同一个读数66.5%，第一档偏空、第二档中性、第三档偏空(>60)——国内供应松紧里的开机率

// ===================== 8. 评分规则版本 =====================
check('★评分规则版本已升到v100(v99：开机率改往年同月分位、豆菜粕价差不再计分；v100：现货基差按当前合约内部分位、供需均衡)', window._scoringVersion === 'v100');

H.printSummary();
