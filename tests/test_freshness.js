// ============================================================================
// 数据质量：新鲜度(按"应更新的时点"，扣除休市) × 来源可靠性；接入票权与置信度
// 所有用例固定"现在"=2026-09-30(周三) 10:00 北京时间，不依赖运行当天是星期几
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
const E = window._eventCal;
const AUTO = window._autoIndicators, BYKEY = window._autoByKey;
const at = (y,m,d,h,mi)=>E.bjToMs(y,m,d,h||10,mi||0);
const NOW = at(2026,9,30,10,0);           // 周三
window._nowMs = NOW;
const F = (cfg, date, now)=>freshnessOf(cfg, date, now == null ? NOW : now).state;

// ===================== 1. 日频(交易日)：错过了几个交易日 =====================
const TR = {cadence:'trading', maxAgeDays:30};
check('★周三10点，数据09-29(周二)：应有的最新数据就是周二 → 错过0个 → 正常', F(TR,'2026-09-29')==='fresh' && tradingDaysMissed('2026-09-29', NOW)===0);
check('数据09-28(周一)：错过周二1个 → 仍算正常(允许1个交易日的发布延迟)', F(TR,'2026-09-28')==='fresh' && tradingDaysMissed('2026-09-28', NOW)===1);
check('★数据09-25(周五)：错过周一、周二2个 → 晚了一期', F(TR,'2026-09-25')==='late' && tradingDaysMissed('2026-09-25', NOW)===2);
check('数据09-24(周四)：错过3个 → 仍是晚了一期', F(TR,'2026-09-24')==='late' && tradingDaysMissed('2026-09-24', NOW)===3);
check('★数据09-23(周三)：错过4个 → 过期', F(TR,'2026-09-23')==='stale' && tradingDaysMissed('2026-09-23', NOW)===4);
check('★数据日期落在周末：按前一个交易日算(周日09-27 = 周五09-25)', tradingDaysMissed('2026-09-27', NOW) === tradingDaysMissed('2026-09-25', NOW) && F(TR,'2026-09-27')==='late');
check('18点以后当天的数据也算"应已发布"：周三18:30，09-29的数据错过周三1个；09-28的错过周二、周三2个 → 晚了一期', F(TR,'2026-09-29',at(2026,9,30,18,30))==='fresh' && F(TR,'2026-09-28',at(2026,9,30,18,30))==='late');
check('★周一10点，数据上周五：周末不是交易日 → 错过0个 → 正常(按绝对天数算3天，但没有错过任何发布)', F(TR,'2026-09-25',at(2026,9,28,10,0))==='fresh');
check('绝对上限：即使交易日数没到，超过maxAgeDays也一律过期', F({cadence:'trading', maxAgeDays:2},'2026-09-27')==='stale');

// ★国庆休市：没有交易日，就不该被判过期——这正是"按应更新时点"而不是"按天数"的意义
const HOL = (d,h)=>at(2026,10,d,h||10,0);
check('★国庆期间(10-07周三)，数据09-30：距今7天但休市期间没有交易日、没有应有的发布 → 错过0个 → 正常', tradingDaysMissed('2026-09-30', HOL(7))===0 && F(TR,'2026-09-30',HOL(7))==='fresh');
check('★10-08(周四，恢复交易当天早上)：仍正常', F(TR,'2026-09-30',HOL(8))==='fresh');
check('★10-09(周五)：应有10-08的数据，没有 → 错过1个 → 仍正常', tradingDaysMissed('2026-09-30', HOL(9))===1 && F(TR,'2026-09-30',HOL(9))==='fresh');
check('★10-12(周一)：应有10-08、10-09 → 错过2个 → 晚了一期', tradingDaysMissed('2026-09-30', HOL(12))===2 && F(TR,'2026-09-30',HOL(12))==='late');
check('对照：如果按绝对天数，10-07时数据已经7天前——旧规则(基差maxAge=7天)会在这时判过期', Math.floor((HOL(7)-at(2026,9,30,0,0))/86400000) >= 7);

// ===================== 2. 周频/月频：发布周期 + 扣除休市 =====================
const WK = {cadence:'weekly', maxAgeDays:30}, MO = {cadence:'monthly', maxAgeDays:90};
const ago = (n, now)=>{ const t = new Date((now==null?NOW:now) - n*86400000 + 8*3600000); return t.toISOString().slice(0,10); };
check('★周频：距今5天(周五发的周报周三仍是最新)正常；9天正常；10天晚了一期；16天晚了一期；17天过期', F(WK,ago(5))==='fresh' && F(WK,ago(9))==='fresh' && F(WK,ago(10))==='late' && F(WK,ago(16))==='late' && F(WK,ago(17))==='stale');
check('★周频扣除休市：10-12(周一)时09-30的数据距今12天，但其间休市5个工作日 → 有效7天 → 正常(不扣休市就是晚了一期)', F(WK,'2026-09-30',HOL(12))==='fresh' && freshnessOf(WK,'2026-09-30',HOL(12)).detail.includes('休市5个工作日'));
check('月频：38天正常，39天晚了一期，69天晚了一期，70天过期', F(MO,ago(38))==='fresh' && F(MO,ago(39))==='late' && F(MO,ago(69))==='late' && F(MO,ago(70))==='stale');
check('★maxAgeDays是绝对上限：库消比cadence=月频但maxAge=45 → 46天一律过期，39~45天是晚了一期', F(BYKEY.stu, ago(40))==='late' && F(BYKEY.stu, ago(46))==='stale' && BYKEY.stu.maxAgeDays===45);
check('★lagDays(出口销售weekEnding比发布早一周)：距今16天(=lag7+周期9)正常；23天晚了一期；24天过期', F({cadence:'weekly',lagDays:7,maxAgeDays:60},ago(16))==='fresh' && F({cadence:'weekly',lagDays:7,maxAgeDays:60},ago(23))==='late' && F({cadence:'weekly',lagDays:7,maxAgeDays:60},ago(24))==='stale');
check('日期未知/坏格式：当作正常，标注unknown，不因为解析失败就排除', freshnessOf(WK,'',NOW).unknown === true && F(WK,'不是日期')==='fresh');
check('没有cadence的(如季度指标)：只按maxAgeDays判断', F({maxAgeDays:130}, ago(100))==='fresh' && F({maxAgeDays:130}, ago(131))==='stale');
check('★10个指标的cadence配置：基差/猪粮比=交易日；开机率/库存/肉鸡/豆菜粕=周频；库消比/到港/进口=月频', ['basis','hogratio'].every(k=>BYKEY[k].cadence==='trading') && ['crush','stock','poultry','rmspread'].every(k=>BYKEY[k].cadence==='weekly') && ['stu','arrival','import'].every(k=>BYKEY[k].cadence==='monthly'));

// ===================== 3. 来源可靠性：只对有具体理由的打折 =====================
check('库消比由库存÷消费推算 → 估算', sourceEstimateReason('stu',{method:'computed'},{}).includes('推算'));
check('库消比由周度库存÷预计消费推算 → 估算(并说明不是文章明示)', sourceEstimateReason('stu',{method:'weekly'},{}).includes('周度库存'));
check('库消比用了上月记录(当月还没发布) → 估算，写明用的是哪个月', sourceEstimateReason('stu',{usedFallbackMonth:true, monthLabel:'2026年8月', method:'stated'},{}).includes('2026年8月'));
check('★库消比文章明示(哪怕来自摘要) → 不打折：摘要里的数字也是文章写的', sourceEstimateReason('stu',{method:'stated', recordSource:'summary'},{}) === '');
check('基差用了前几天的数据(最新一篇没解析出确切值) → 估算', sourceEstimateReason('basis',{usedFallback:true, fallbackDays:3},{}).includes('3天前'));
check('★沿用浏览器保存的手动值(mode=saved)：来源和日期都无法核实 → 估算', sourceEstimateReason('crush',{}, {mode:'saved'}).includes('无法核实'));
check('★Mysteel文章解析(开机率/库存/基差…)没有证据证明更不可靠 → 不打折', ['crush','stock','arrival','import','poultry','rmspread'].every(k=>sourceEstimateReason(k,{value:1},{mode:'auto'})===''));

// ===================== 4. 质量乘数 =====================
window._indState = {};
check('全部正常：乘数1', qualityOf('crush').m === 1 && qualityOf('crush').why === '');
window._indState.crush = {late:true};
check('★晚了一期：×0.5', qualityOf('crush').m === 0.5 && qualityOf('crush').why.includes('晚了一期'));
window._indState.crush = {estimated:'库消比由库存÷消费推算'};
check('★估算：×0.5', qualityOf('crush').m === 0.5);
window._indState.crush = {late:true, estimated:'推算'};
check('两者叠加：×0.25(粗档位相乘，不再叠更多层)', qualityOf('crush').m === 0.25);
window._indState.crush = {mode:'saved'};
check('★手动保存值(saved)：×0.5', qualityOf('crush').m === 0.5);
window._indState.crush = {mode:'manual'};
check('★用户本次会话里刚手动修正(manual)：视为自己负责，不打折', qualityOf('crush').m === 1);
// 复合信号：按成员组内权重加权
window._indState = {stu:{}, crush:{late:true}, stock:{}};
let cq = compositeQuality([['stu',50],['crush',30],['stock',20]], {stu:1, crush:1, stock:1});
check('★复合信号质量：库消比50正常+开机率30晚了一期+库存20正常 → (50+15+20)/100=0.85', Math.abs(cq.m - 0.85) < 1e-9 && cq.why.includes('油厂开机率'));
cq = compositeQuality([['stu',50],['crush',30],['stock',20]], {stu:null, crush:1, stock:1});
check('没有数据的成员不参与加权：库消比缺失 → (30×0.5+20)/50=0.7', Math.abs(cq.m - 0.7) < 1e-9);
check('全部成员没数据 → 乘数1(不影响)', compositeQuality([['stu',50]], {stu:null}).m === 1);

// ===================== 5. 整体质量分 → 置信度 =====================
const V = (label, signal, base, q, why)=>({label, signal, weight: base*(q==null?1:q), baseWeight: base, q: q==null?1:q, qwhy: why||''});
let qs = qualitySummary([V('a',1,1), V('b',1,1), V('c',-1,2,0.5,'晚了一期'), V('d',null,1,0.5,'x')]);
check('★质量分=Σ(基础票权×乘数)÷Σ基础票权：(1+1+2×0.5)/4=0.75；无数据的票不算；被降权的列出原因', Math.abs(qs.score - 0.75) < 1e-9 && qs.lowItems.length === 1 && qs.lowItems[0].why === '晚了一期');
check('全部正常质量分1，无降权项', qualitySummary([V('a',1,1), V('b',0,1)]).score === 1);
check('没有任何有效投票 → 质量分1(不惩罚)', qualitySummary([V('a',null,1,0.5)]).score === 1);
const mkC = (score)=>{
  const votes = Array.from({length:12}, (_,i)=>({label:'x'+i, signal:0, weight:1}));
  return computeConfidence(votes, {n:12, bullW:1, bearW:9}, {a:{n:3,dir:-1,ratio:-0.5,name:'供给端'}, b:{n:3,dir:-1,ratio:-0.4,name:'需求端'}}, null, false, {score, lowItems:[{label:'x',why:'y',q:0.5},{label:'z',why:'y',q:0.5}]});
};
check('★质量分≥0.85：不扣分，高置信度', mkC(0.9).level === 2 && mkC(0.85).level === 2 && mkC(0.9).reasons.join('').includes('数据质量正常'));
check('★质量分0.84(<0.85)：降一级，理由写明"数据质量一般"和项数', mkC(0.84).level === 1 && mkC(0.84).reasons.some(r=>r.includes('数据质量一般') && r.includes('2项')));
check('★质量分0.64(<0.65)：降两级 → 低，理由写"数据质量偏低"', mkC(0.64).level === 0 && mkC(0.64).reasons.some(r=>r.includes('数据质量偏低')));
check('回归：不传质量时行为不变', computeConfidence(Array.from({length:12},(_,i)=>({label:'x',signal:0,weight:1})), {n:12,bullW:1,bearW:9}, {}, null, false).level === 2);

// ===================== 6. 端到端：数据晚了一期 → 降权 + 徽标 + 置信度理由 =====================
KEYS = AUTO.map(k=>k.key);
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); });
  window._indState = {};
  makeEl('alertContent');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0;
  window._esrSignal=0; window._fxSignal=0; window._psdSignal=0; window._esrQuality=null;
  // 其余指标用中性值补齐，让有效投票凑满10个(基差/猪粮比/肉鸡/豆菜粕/到港/进口)；这些是直接填的，没有经过抓取，质量乘数为1
  ({basis:0, hogratio:6, poultry:1, rmspread:550, arrival:900, import:900}, null);
  const fill = {basis:0, hogratio:6, poultry:1, rmspread:550, arrival:900, import:900};
  Object.keys(fill).forEach(k=>makeEl('m_'+k).value = String(fill[k])); H.setBasis('0');
}
const d0 = (n)=>ago(n);
window._selectedContract='sep'; H.setMockedMonth(5);
// 开机率数据11天前(周频：晚了一期)，其余正常
reset();
window._syncedData = {mysteelCrushRate:{available:true, value:50, date:d0(11)}, mysteelMealStock:{available:true, value:70, date:d0(3)}};
refreshMysteelCrushRate(); refreshMysteelMealStock();
check('★开机率距今11天：徽标"晚了一期·降权"，详情说明错过了一个发布、票权×0.5', makeEl('badge_crush').textContent.includes('晚了一期') && makeEl('badge_crush').textContent.includes('降权') && makeEl('ai_crush').innerHTML.includes('晚了一期') && makeEl('ai_crush').innerHTML.includes('票权×0.5'));
check('★库存距今3天：正常，徽标是"自动"', makeEl('badge_stock').textContent.includes('自动'));
check('晚了一期的开机率仍然参与计分(中性区间50%)：卡片结论框不是"不参与综合评分"', !makeEl('alert_crush').innerHTML.includes('不参与综合评分'));
updateOverallAlert();
check('★整体质量分：国内供应松紧成员=库存(60正常)+开机率(40晚了一期) → 乘数0.8；总质量=(9+0.8)/10=0.98', Math.abs(window._quality.score - 0.98) < 1e-9 && window._quality.lowItems.length === 1 && window._quality.lowItems[0].label.includes('国内豆粕供应松紧'));
check('界面显示"数据质量"一行，点名被降权的投票和原因', makeEl('alertContent').innerHTML.includes('数据质量') && makeEl('alertContent').innerHTML.includes('国内豆粕供应松紧') && makeEl('alertContent').innerHTML.includes('数据晚了一期'));

// 票权真的被降：只有美豆库消比偏多，其余全中性
reset(); window._psdSignal = 1;
window._syncedData = {mysteelCrushRate:{available:true, value:50, date:d0(3)}, mysteelMealStock:{available:true, value:70, date:d0(3)}};
refreshMysteelCrushRate(); refreshMysteelMealStock(); updateOverallAlert();
const wFresh = window._quality.score;
const ratioFresh = window._dimensions.supply.ratio;
reset(); window._psdSignal = 1;
window._syncedData = {mysteelCrushRate:{available:true, value:50, date:d0(11)}, mysteelMealStock:{available:true, value:70, date:d0(11)}};
refreshMysteelCrushRate(); refreshMysteelMealStock(); updateOverallAlert();
check('★开机率和库存都晚了一期：国内供应松紧这一票权重减半 → 供给端净倾向里美豆库消比的占比变大(1/4.5 > 1/5)', window._dimensions.supply.ratio > ratioFresh && Math.abs(window._dimensions.supply.ratio - 1/4.5) < 1e-9 && wFresh === 1);

// 过期：不投票
reset();
window._syncedData = {mysteelCrushRate:{available:true, value:50, date:d0(20)}, mysteelMealStock:{available:true, value:70, date:d0(3)}};
refreshMysteelCrushRate(); refreshMysteelMealStock(); updateOverallAlert();
check('★开机率距今20天(周频>16天)：过期，徽标"数据过期·不计分"，不投票，国内供应松紧退回只看库存', makeEl('badge_crush').textContent.includes('数据过期') && makeEl('alert_crush').innerHTML.includes('不参与综合评分'));

// 估算值：库消比由库存÷消费推算
reset();
window._syncedData = {mysteelMealStu:{available:true, value:12, month:'2026-09', monthLabel:'2026年9月', isForecast:false, method:'computed', methodLabel:'由库存÷消费推算', recordSource:'body', stockWan:90, consumptionWan:750, productionWan:700, next:null, trend:null, weeklyCheck:null, date:d0(3), articleAgeDays:3, articleTitle:'x', festival:{name:null, level:null, disturbed:false}}};
refreshMysteelMealStu(); updateOverallAlert();
check('★库消比是推算值：徽标"估算值·降权"，详情写明来源理由和票权×0.5', makeEl('badge_stu').textContent.includes('估算值') && makeEl('ai_stu').innerHTML.includes('来源可靠性') && makeEl('ai_stu').innerHTML.includes('推算') && makeEl('ai_stu').innerHTML.includes('票权×0.5'));
// 手动保存值
reset();
window._indState.crush = {mode:'saved'}; makeEl('m_crush').value = '50'; window._syncedData = {mysteelCrushRate:{available:false, reason:'测试'}};
refreshMysteelCrushRate(); updateOverallAlert();
check('★抓取失败、沿用保存的手动值：徽标"沿用你保存的值"，质量乘数×0.5', makeEl('badge_crush').textContent.includes('沿用你保存的值') && qualityOf('crush').m === 0.5);
// 手动修正：不打折
onManualEdit('crush');
check('★用户手动改了值(manual)：不再打折', qualityOf('crush').m === 1);

// ===================== 7. 出口销售(USDA weekEnding)新鲜度 =====================
elements['esrBadge']=makeEl('esrBadge'); elements['esrContent']=makeEl('esrContent');
const seasonal = {history:{n:300, percentile:90, seasonal:{month:9, n:40, percentile:90, median:1}}};
const esrBase = (weekEnding)=>Object.assign({available:true, commodity:'Soybeans(大豆)', weekEnding, marketYearUsed:2026, dataAgeDays:5, isStale:false, netSalesMT:1200000, prevNetSalesMT:800000, avg4wNetSalesMT:700000, vs4wAvgPct:71.4, wowChangePct:50, shipmentsMT:900000, chinaNetSalesMT:450000, source:'x'}, seasonal);
renderEsr(esrBase(ago(10)), new Date().toISOString());
check('★ESR weekEnding距今10天(周四发布上周四截止的数据，正常)：信号偏多、质量乘数1', window._esrSignal === 1 && window._esrQuality.m === 1);
renderEsr(esrBase(ago(20)), new Date().toISOString());
check('★ESR距今20天(晚了一期)：信号仍在，质量乘数×0.5', window._esrSignal === 1 && window._esrQuality.m === 0.5 && window._esrQuality.why.includes('晚了一期'));
renderEsr(esrBase(ago(30)), new Date().toISOString());
check('★ESR距今30天(过期)：不判方向、不投票，界面说明', window._esrSignal === null && makeEl('esrContent').innerHTML.includes('已过期') && makeEl('esrContent').innerHTML.includes('不参与评分'));
renderEsr({available:false, reason:'x'}, new Date().toISOString());
check('ESR不可用时质量状态被清空(不沿用上次的)', window._esrQuality === null);
// ESR晚了一期 → 票权减半
reset(); makeEl('m_crush').value='50'; makeEl('m_stock').value='70'; window._esrSignal = 1; window._esrQuality = {m:0.5, why:'出口销售周报晚了一期'}; updateOverallAlert();
check('★ESR晚了一期时出口销售这一票降权：质量分(9+0.5)/10=0.95，点名被降权的是出口销售', Math.abs(window._quality.score - 0.95) < 1e-9 && window._quality.lowItems[0].label.includes('出口销售'));

H.clearMockedMonth();
window._nowMs = null;
H.printSummary();
