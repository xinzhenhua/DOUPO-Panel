const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
window._selectedContract = 'sep';
H.setMockedMonth(5);
// v101.9 供需均衡的页面集成：真实流水线(updateOverallAlert)里，顶部总倾向 = 50%×供给净倾向 + 50%×需求净倾向；维度各自的净倾向不受缩放影响。
const AUTO = window._autoIndicators, KEYS = AUTO.map(k=>k.key);
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); window._indState[k] = {}; });
  makeEl('alertContent');
  window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null;
  window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
}
function neutral(){
  reset();
  const v = {crush:50, stock:70, stu:12, arrival:900, import:900, hogratio:6, sows:3750, poultry:1, rmspread:550, reserve:0};
  Object.keys(v).forEach(k=>makeEl('m_'+k).value = String(v[k])); H.setBasis('0');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0;
  window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
}
function supplyBear(){
  window._weatherRisk='low'; window._droughtSignal=-1; window._noaaOutlookSignal=-1; window._soyCondSignal=-1;
  window._psdSignal=-1; window._fxSignal=-1;
  makeEl('m_stu').value='16'; makeEl('m_arrival').value='1100'; makeEl('m_import').value='1100'; makeEl('m_reserve').value='54';
}
const html = ()=>makeEl('alertContent').innerHTML;
const near = (a,b)=>Math.abs(a-b)<1e-9;

// 场景A：供给端全偏空(-100%)，需求端猪粮比、肉鸡偏多(+50%)。不均衡时 -40%（供给票权7、需求票权3）；均衡后 0.5×(-1)+0.5×0.5 = -25%
neutral(); supplyBear(); makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='2'; updateOverallAlert();
const b = window._sdBalanceResult;
check('★A：均衡已启用，写明供给/需求票数', b && b.applied===true && b.supplyN>=5 && b.demandN>=2, JSON.stringify(b));
check('★A：维度各自的净倾向不受缩放影响：供给-100%、需求+50%', near(window._dimensions.supply.ratio,-1) && near(window._dimensions.demand.ratio,0.5));
check('★A：两个维度的票权合计相等(各占一半)', near(window._dimensions.supply.weight, window._dimensions.demand.weight));
check('★A：顶部总倾向 = 0.5×(-1)+0.5×0.5 = -25%（不是不均衡时的-40%）', near(window._fundamentalPure.ratio, -0.25), String(window._fundamentalPure.ratio));
check('★A：页面写出供需均衡说明（票数、占比、缩放系数）', html().includes('供需均衡') && html().includes('50%/50%') && html().includes('总票权不变'));
check('A：-25%仍≥22%门槛 → 基本面偏空', window._fundamentalDirection==='偏空');

// 场景B：同样的数据，把供给端减弱成只剩 -100% 变成 -20%（均衡不应放大弱信号）：构造供给端只有2票偏空、其余中性
neutral(); window._droughtSignal=-1; window._noaaOutlookSignal=-1; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='2'; updateOverallAlert();
const sR = window._dimensions.supply.ratio, dR = window._dimensions.demand.ratio;
check('★B（通用不变式）：顶部总倾向恒等于 0.5×供给净倾向+0.5×需求净倾向', near(window._fundamentalPure.ratio, 0.5*sR+0.5*dR), `${window._fundamentalPure.ratio} vs ${0.5*sR+0.5*dR}`);

// 场景C：天气开关打开 → 不均衡，说明原因
neutral(); window._weatherRisk='high'; window._droughtSignal=1; window._noaaOutlookSignal=1; window._soyCondSignal=1; updateOverallAlert();
if(window._weatherDominant){
  check('★C：天气开关打开 → 不均衡，页面说明原因', window._sdBalanceResult.applied===false && html().includes('供需均衡未启用') && html().includes('天气开关'));
} else {
  check('C：（本组夹具没触发天气开关，改查：未触发时应均衡）', window._sdBalanceResult.applied===true);
}

// 场景D：数据不足(供需票<5)时不报错、不均衡也不崩
reset(); supplyBear(); window._esrSignal=null; updateOverallAlert();
check('D：数据不足时页面照常给出提示，不抛错', typeof html()==='string' && html().length>0);

// 场景E：均衡对"市场结构"无影响：结构系统的净倾向与均衡无关
neutral(); supplyBear(); H.setBasis('-100'); updateOverallAlert();
check('E：市场结构票权不被缩放，结构系统仍按自己的票计算', window._structureSystem && window._structureSystem.n>=1);
H.printSummary();
