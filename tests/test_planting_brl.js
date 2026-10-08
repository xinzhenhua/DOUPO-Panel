const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


function resetAll(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry','m_rmspread'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import','ind_poultry','ind_rmspread',
   'tab-sep','tab-may','tab-jan','contractContext','tradingWindowInfo','esrPsdContractNote',
   'group-us-weather','group-sa','group-may-extra'].forEach(id=>elements[id]=makeEl(id));
  elements['alertContent'] = makeEl('alertContent');
  elements['m_crush'].value = '35';
}

// ===================== 测试1：group-may-extra只在5月合约显示 =====================
H.setMockedMonth(7);
resetAll();
selectContract('sep');
check('9月合约：group-may-extra应该被隐藏', elements['group-may-extra'].classList.contains('hidden-by-contract'));
selectContract('may');
check('5月合约：group-may-extra应该显示(不隐藏)', !elements['group-may-extra'].classList.contains('hidden-by-contract'));
selectContract('jan');
check('1月合约：group-may-extra应该被隐藏', elements['group-may-extra'].classList.contains('hidden-by-contract'));

// ===================== 测试2：renderPlanting渲染 =====================
elements['plantingBadge']=makeEl('plantingBadge'); elements['plantingContent']=makeEl('plantingContent');
renderPlanting({available:true, weekEnding:'2026-05-11', pctPlanted:78, wowChangePts:16}, new Date().toISOString());
check('播种进度推进较快(16个百分点)应判定偏空', window._plantingSignal === -1);
check('播种进度内容应显示78%', elements['plantingContent'].innerHTML.includes('78%'));

elements['plantingBadge']=makeEl('plantingBadge'); elements['plantingContent']=makeEl('plantingContent');
renderPlanting({available:true, weekEnding:'2026-05-11', pctPlanted:40, wowChangePts:2}, new Date().toISOString());
check('播种进度推进缓慢(2个百分点)应判定偏多(可能降雨导致延误)', window._plantingSignal === 1);

elements['plantingBadge']=makeEl('plantingBadge'); elements['plantingContent']=makeEl('plantingContent');
renderPlanting({available:false, reason:'测试无数据'}, null);
check('播种进度无数据时应优雅降级，signal为null', window._plantingSignal === null);

// ===================== 测试3：5月合约独立计入播种进度+雷亚尔信号 =====================
resetAll();
window._plantingSignal = 1; window._brlSignal = 1; // 都设为偏多
selectContract('may');
check('★5月合约：播种进度+雷亚尔信号应该独立计入评分(不是合并进crop composite)',
  elements['alertContent'].innerHTML.includes('sd-cell sd-pos">美豆播种进度') &&
  elements['alertContent'].innerHTML.includes('sd-cell sd-pos">巴西雷亚尔汇率'));

resetAll();
window._plantingSignal = 1; window._brlSignal = 1;
selectContract('sep');
check('★9月合约：即使播种进度/雷亚尔信号存在，也不应该计入评分(这2项只跟5月合约相关)',
  !elements['alertContent'].innerHTML.includes('美豆播种进度') &&
  !elements['alertContent'].innerHTML.includes('巴西雷亚尔汇率'));

// ===================== 测试4：5月合约全部指标偏多时票数必须精确 =====================
resetAll();
elements['m_stock'].value='40'; H.setBasis('10'); elements['m_arrival'].value='700';
elements['m_hogratio'].value='8'; elements['m_sows'].value='3600'; elements['m_import'].value='700';
elements['m_poultry'].value='2'; elements['m_rmspread'].value='350';
window._saWeatherSignal=1; window._saPsdSignal=1; window._esrSignal=1; window._fxSignal=1; window._psdSignal=1;
window._plantingSignal=1; window._brlSignal=1;
H.setMockedMonth(7); // 休耕期，天气产量权重10/90，两者都偏多，合成应为偏多
selectContract('may');
// 7月：作物(南美)、库存消费比、国内豆粕供应松紧、大豆到港/进口、汇率、播种进度、雷亚尔 = 7票供应；出口销售、基差、猪粮比、能繁、肉鸡、豆菜粕价差 = 6票需求
// 手算：有效12票(供应7+需求5，能繁移出)；7月南美休耕期作物票"背景"档×0.5，不触发天气开关；其余11票×1 → 0.5+11=+11.5
check('★5月合约：顶部11个供需票全偏多(原12个含基差)：作物背景档0.5+其余10票×1=+10.5', elements['alertContent'].innerHTML.includes('基本面偏多 +10.5（') && elements['alertContent'].innerHTML.includes('有效11/11'));
H.clearMockedMonth();


H.printSummary();
