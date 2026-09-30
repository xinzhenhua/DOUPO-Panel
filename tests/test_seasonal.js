// ============================================================================
// 季节性档位(作物/天气这一票) + 天气开关 + 国庆(轻度扰动，降权不暂停)
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
const AUTO = window._autoIndicators; const TIER = window._TIER;
const KEYS = AUTO.map(c=>c.key);
const dayStr = n => new Date(Date.now() - n*86400000).toISOString().slice(0,10);
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); window._indState[k] = {}; });
  makeEl('alertContent');
  window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null;
  window._saWeatherSignal=null; window._saPsdSignal=null;
  window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
}
function neutralBase(){
  reset();
  const v = {crush:50, stock:70, basis:0, arrival:900, import:900, hogratio:6, sows:3750, poultry:1, rmspread:550, reserve:0};
  Object.keys(v).forEach(k=>makeEl('m_'+k).value = String(v[k]));
  window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
}
const html = ()=>makeEl('alertContent').innerHTML;
const setUs = (w,n,d,c)=>{ window._weatherRisk=w; window._noaaOutlookSignal=n; window._droughtSignal=d; window._soyCondSignal=c; };
const cropCell = ()=> (html().match(/sd-cell (sd-\w+)">(?:美国)?作物生长状况综合[^<]*?( ×[\d.]+)?(?: [▲▼—])?<\/td>/)||[]);

// ===================== 1. cropTier：产业逻辑档位 =====================
const T = (k,c,m)=>cropTier(k,c,m).tier;
check('★美国作物(9月合约)：6/7/8月=主导(结荚灌浆关键期)', [6,7,8].every(m=>T('us','sep',m)==='lead'));
check('★美国作物：4/5月=参与(播种出苗)；9月=背景(收获尾声)；10月~3月=背景', [4,5].every(m=>T('us','sep',m)==='join') && T('us','sep',9)==='bg' && [10,11,12,1,2,3].every(m=>T('us','sep',m)==='bg'));
check('★1月合约的美国作物票：8月=参与(不是主导，还要看收获和南美)，9月=背景', T('us','jan',8)==='join' && T('us','jan',9)==='bg');
check('★南美(5月/1月合约)：12/1/2/3月=主导(灌浆收获关键期)', [12,1,2,3].every(m=>T('sa','may',m)==='lead' && T('sa','jan',m)==='lead'));
check('★南美：10/11/4月=参与(播种/收获尾声)；5~9月=背景(休耕/已收获)', [10,11,4].every(m=>T('sa','jan',m)==='join') && [5,6,7,8,9].every(m=>T('sa','may',m)==='bg'));
check('每档都带理由文字', ['us','sa'].every(k=>[1,4,6,9,12].every(m=>cropTier(k,'sep',m).why.length>6)));
check('档位权重：主导×2、参与×1、背景×0.5', TIER.lead.w===2 && TIER.join.w===1 && TIER.bg.w===0.5 && TIER.lead.name==='主导' && TIER.bg.name==='背景');

// ===================== 2. 作物票在评分里按档位加权 =====================
window._selectedContract = 'sep';
H.setMockedMonth(7);   // 9月合约7月：主导×2
neutralBase(); setUs('high',1,1,0);   // 3/4偏多→composite偏多；天气开关(≥3项偏多且有效≥3)会打开——先看不打开的情形(下面单独测)
setUs('medium',0,0,0); updateOverallAlert();
check('★7月(主导档)：作物票中性时权重仍是×2，表格里带×2', /作物生长状况综合[^<]*×2/.test(html()));
check('详细理由里写明"主导"档、票权×2和理由', html().includes('「主导」档(票权×2)') && html().includes('结荚灌浆关键期'));
H.setMockedMonth(5); neutralBase(); setUs('medium',0,0,0); updateOverallAlert();
check('★5月(参与档)：票权×1，表格里没有×标记', !/作物生长状况综合[^<]*×/.test(html()) && html().includes('「参与」档(票权×1)'));
H.setMockedMonth(10); neutralBase(); setUs('medium',0,0,0); updateOverallAlert();
check('★10月(背景档)：票权×0.5，表格里带×0.5，理由写明信息量低', /作物生长状况综合[^<]*×0\.5/.test(html()) && html().includes('「背景」档(票权×0.5)'));

// 权重对总分的影响：只有作物票偏空，其余中性 —— 主导档比背景档更能拉动净倾向
function ratioWithCropBear(month){
  H.setMockedMonth(month); neutralBase(); setUs('low',-1,-1,-1); updateOverallAlert();
  return window._dimensions.supply.ratio;
}
const rLead = ratioWithCropBear(7), rJoin = ratioWithCropBear(5), rBg = ratioWithCropBear(10);
check('★同样的偏空作物信号：主导档(7月)对供给端净倾向的拉动 > 参与档(5月) > 背景档(10月)', rLead < rJoin && rJoin < rBg && rLead < 0);

// ===================== 3. 天气开关 =====================
H.setMockedMonth(7); neutralBase(); setUs('high',1,1,1); updateOverallAlert();
check('★7月美国作物4项子信号全偏多 → 天气开关打开，window._weatherDominant有内容', window._weatherDominant && window._weatherDominant.kind==='us' && window._weatherDominant.why.includes('4项同时偏多') );
check('★页面顶部有"天气主导行情"提示，说明其余指标票权减半', html().includes('天气主导行情') && html().includes('其余指标票权减半'));
// 票权：作物×2(偏多)；其余投票各×0.5(全部中性，除国内供应松紧等)。综合净倾向：2÷(2+其余有效票×0.5)
const votesTot = html().match(/有效(\d+)\/(\d+)项/);
const nValid = parseInt(votesTot[1]);
const expectRatio = Math.round(2/(2+(nValid-1)*0.5)*100);
check(`★天气开关打开时净倾向=2÷(2+${nValid-1}×0.5)=${expectRatio}%(其余票权确实减半)`, html().includes(`净倾向+${expectRatio}%`));
check('天气开关打开时作物票按"天气主导"档写进理由', html().includes('「天气主导」档') && html().includes('天气开关打开'));

setUs('high',1,1,0); updateOverallAlert();
check('★4项里3项偏多(有效4项)：仍然打开(≥3项偏多)', !!window._weatherDominant);
setUs('high',1,0,0); updateOverallAlert();
check('★4项里2项偏多：composite可能偏多但不够极端 → 不打开', window._weatherDominant === null && !html().includes('天气主导行情'));
setUs('high',1,1,null); updateOverallAlert();
check('★优良率暂无数据(有效3项)：3项全偏多仍算极端 → 打开', !!window._weatherDominant);
setUs('high',1,null,null); updateOverallAlert();
check('★有效子信号只有2项：不够3项 → 不打开(样本太少不敢下"极端"结论)', window._weatherDominant === null);
setUs('low',-1,-1,-1); updateOverallAlert();
check('★天气对称性：极端偏空(天气极好)不打开开关——天气是不对称的，只有干旱才是大事件', window._weatherDominant === null && !html().includes('天气主导行情'));
H.setMockedMonth(10); neutralBase(); setUs('high',1,1,1); updateOverallAlert();
check('★背景档(10月)：即使4项偏多也不打开(休耕期的极端天气没有意义)', window._weatherDominant === null);
H.setMockedMonth(9); neutralBase(); setUs('high',1,1,1); updateOverallAlert();
check('9月(背景档)同样不打开', window._weatherDominant === null);
H.setMockedMonth(5); neutralBase(); setUs('high',1,1,1); updateOverallAlert();
check('5月(参与档)：极端偏多打开，此时作物票强制按主导档(×2)而不是×1', !!window._weatherDominant && /作物生长状况综合[^<]*×2/.test(html()));

// 南美
window._selectedContract = 'may';
H.setMockedMonth(1); neutralBase(); window._saWeatherSignal=1; window._saPsdSignal=1; updateOverallAlert();
check('★5月合约1月：南美天气偏多(干旱风险)且合成偏多 → 打开，理由写南美', window._weatherDominant && window._weatherDominant.kind==='sa' && html().includes('南美'));
H.setMockedMonth(7); neutralBase(); window._saWeatherSignal=1; window._saPsdSignal=1; updateOverallAlert();
check('★7月(南美休耕期背景档)：不打开', window._weatherDominant === null);
H.setMockedMonth(1); neutralBase(); window._saWeatherSignal=0; window._saPsdSignal=1; updateOverallAlert();
check('南美天气中性(只有产量偏多)：不打开——开关看的是天气', window._weatherDominant === null);
// 1月合约8月：美国作物(参与)+南美(背景)两票；美国极端偏多时开关打开
window._selectedContract = 'jan';
H.setMockedMonth(8); neutralBase(); setUs('high',1,1,1); window._saWeatherSignal=0; window._saPsdSignal=0; updateOverallAlert();
check('★1月合约8月：美国作物票(参与档×1)极端偏多 → 开关打开', window._weatherDominant && window._weatherDominant.kind==='us');

// 数据不足的分支不留旧状态
window._selectedContract = 'sep';
H.setMockedMonth(7); reset(); makeEl('m_crush').value='35'; updateOverallAlert();
check('数据不足分支：不出现天气主导提示(不下结论)', html().includes('数据不足') && !html().includes('天气主导行情'));

// 分数格式：非整数保留1位
check('分数格式：整数不带小数，半数保留1位', fmtScore(6)==='6' && fmtScore(6.5)==='6.5' && fmtScore(-3.5)==='-3.5');

// ===================== 4. 国庆(轻度扰动)：仍计分，票权降一档 =====================
window._selectedContract = 'sep';
H.setMockedMonth(5);
const stu = (o)=>Object.assign({available:true, value:18, month:'2026-10', monthLabel:'2026年10月', isForecast:true, usedFallbackMonth:false,
  method:'stated', methodLabel:'文章明示', recordSource:'body', stockWan:120, consumptionWan:670, productionWan:700, next:null, trend:null, weeklyCheck:null,
  date:dayStr(2), articleAgeDays:2, articleTitle:'x',
  festival:{name:'国庆', level:'mild', festivalDate:'2026-10-01', coreDays:14, disturbed:true, phase:'假期停摆', bias:'油厂假期计划停机/降负荷、养殖饲料贸易放缓约一周，月消费被压低，库消比容易被抬高(幅度比春节小)'}}, o||{});
const tightCell = ()=> (html().match(/sd-cell (sd-\w+)">国内豆粕供应松紧( ×2)?/)||[]);
neutralBase(); window._syncedData = {mysteelMealStu: stu()}; refreshMysteelMealStu(); updateOverallAlert();
check('★国庆扰动月：库消比18%≥16%照常判偏空(仍计分)——不像春节那样暂停', makeEl('alert_stu').innerHTML.includes('alert-box bear') && tightCell()[1]==='sd-neg');
check('★国庆扰动月：这一组票权降到1票(表格里没有×2)', !tightCell()[2]);
check('★徽标：国庆扰动月·降权', makeEl('badge_stu').textContent.includes('国庆扰动月') && makeEl('badge_stu').textContent.includes('降权'));
let ai = makeEl('ai_stu').innerHTML;
check('★详情：说明这是轻度扰动、仍计分、票权从2降为1、以及油厂停机的影响', ai.includes('国庆扰动月(轻度)') && ai.includes('仍然计分') && ai.includes('从2票降为1票') && ai.includes('油厂'));
check('国庆扰动月不写"不投票/不判方向"', !ai.includes('不据此判偏多偏空'));
// 对照：非扰动月同样18% → ×2
neutralBase(); window._syncedData = {mysteelMealStu: stu({festival:{name:null, level:null, festivalDate:'2026-02-17', coreDays:0, disturbed:false, phase:null}, month:'2026-08', monthLabel:'2026年8月'})};
refreshMysteelMealStu(); updateOverallAlert();
check('★对照：非扰动月同样18% → 票权×2', tightCell()[1]==='sd-neg' && tightCell()[2]===' ×2' && makeEl('badge_stu').textContent.includes('自动'));
// 春节仍是暂停(回归)：旧数据没有name/level字段也按春节strong处理
neutralBase(); window._syncedData = {mysteelMealStu: stu({festival:{festivalDate:'2026-02-17', coreDays:22, disturbed:true, phase:'假期停摆', bias:'月消费骤降'}})};
refreshMysteelMealStu(); updateOverallAlert();
check('★回归：没有name/level字段(旧数据)按春节strong处理 → 不判方向、不投票', makeEl('badge_stu').textContent.includes('春节扰动期') && makeEl('alert_stu').innerHTML.includes('alert-box neutral') && !tightCell()[2]);
// 下月是国庆扰动月的提示
neutralBase(); window._syncedData = {mysteelMealStu: stu({month:'2026-09', monthLabel:'2026年9月', festival:{name:null, level:null, disturbed:false},
  next:{month:'2026-10', monthLabel:'2026年10月', value:15, festival:{name:'国庆', level:'mild', disturbed:true, phase:'假期停摆'}}})};
refreshMysteelMealStu();
check('★下月是国庆扰动月：提示"届时库消比仍计分但票权降一档"', makeEl('ai_stu').innerHTML.includes('下月(2026年10月)是国庆扰动月') && makeEl('ai_stu').innerHTML.includes('仍计分但票权降一档'));
// 手动修正清除轻度降权
neutralBase(); window._syncedData = {mysteelMealStu: stu()}; refreshMysteelMealStu();
makeEl('m_stu').value='18'; onManualEdit('stu'); updateOverallAlert();
check('用户手动修正后恢复×2(视为自己负责)', window._indState.stu.mild==='' && tightCell()[2]===' ×2');
// 同类月份文案
const t = historyBlock({n:60,minPoints:12,asOf:'2026-10',since:'2021-09',percentile:80,min:1,max:2,median:1.5,seasonal:null,sparse:null,cohort:{label:'国庆扰动月',n:5,percentile:60,median:14}}, {unit:'%'});
check('同类月份文案：国庆月只跟往年国庆月比', t.includes('国庆月只跟往年国庆月比'));

H.clearMockedMonth();
H.printSummary();
