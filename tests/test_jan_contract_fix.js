const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


function resetAll(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry','m_rmspread'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import','ind_poultry','ind_rmspread',
   'tab-sep','tab-may','tab-jan','contractContext','tradingWindowInfo','esrPsdContractNote',
   'group-us-weather','group-sa','group-may-extra','group-jan-extra'].forEach(id=>elements[id]=makeEl(id));
  elements['alertContent'] = makeEl('alertContent');
  elements['m_crush'].value = '35';
}

// ===================== 测试1：修复验证——1月合约现在应该显示group-sa(之前被误隐藏) =====================
H.setMockedMonth(11); // 11月：美豆收获中后期，美国天气板块隐藏
resetAll();
selectContract('jan');
check('★修复验证：1月合约现在应该显示group-sa(南美数据)，之前这里是被误隐藏的', !elements['group-sa'].classList.contains('hidden-by-contract'));
check('1月合约应该显示新的group-jan-extra(收获进度)', !elements['group-jan-extra'].classList.contains('hidden-by-contract'));
check('1月合约(11月)应该隐藏group-us-weather(美国天气类，收获中后期已不相关)', elements['group-us-weather'].classList.contains('hidden-by-contract'));
H.clearMockedMonth();
// ★新增：1月合约的建议窗口是8-11月，8-9月美豆仍在灌浆收尾/刚开始收获，美国天气板块要显示、评分要计入
[8,9].forEach(m=>{
  H.setMockedMonth(m); resetAll(); selectContract('jan');
  check(`★1月合约(${m}月)应该显示group-us-weather(美国天气板块)`, !elements['group-us-weather'].classList.contains('hidden-by-contract'));
  H.clearMockedMonth();
});
[10,11,12].forEach(m=>{
  H.setMockedMonth(m); resetAll(); selectContract('jan');
  check(`1月合约(${m}月)应该隐藏group-us-weather`, elements['group-us-weather'].classList.contains('hidden-by-contract'));
  H.clearMockedMonth();
});
// 评分：8-9月美国天气类综合信号作为独立一票计入；10月起不计入
window._weatherRisk='high'; window._droughtSignal=1; window._noaaOutlookSignal=1; window._soyCondSignal=1;
H.setMockedMonth(9); resetAll(); selectContract('jan');
check('★1月合约(9月)：美国作物生长状况综合应作为独立一票计入(偏多)', elements['alertContent'].innerHTML.includes('sd-cell sd-pos">美国作物生长状况综合'));
H.clearMockedMonth();
H.setMockedMonth(10); resetAll(); selectContract('jan');
check('1月合约(10月)：不再计入美国作物生长状况综合', !elements['alertContent'].innerHTML.includes('美国作物生长状况综合'));
H.clearMockedMonth();
window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null;
check('1月合约应该隐藏group-may-extra(播种进度/雷亚尔，跟1月无关)', elements['group-may-extra'].classList.contains('hidden-by-contract'));

// ===================== 测试2：renderHarvest渲染 =====================
elements['harvestBadge']=makeEl('harvestBadge'); elements['harvestContent']=makeEl('harvestContent');
renderHarvest({available:true, weekEnding:'2026-10-12', pctHarvested:68, wowChangePts:23}, new Date().toISOString());
check('收获推进较快(23个百分点)应判定偏空', window._harvestSignal === -1);
check('收获进度内容应显示68%', elements['harvestContent'].innerHTML.includes('68%'));

elements['harvestBadge']=makeEl('harvestBadge'); elements['harvestContent']=makeEl('harvestContent');
renderHarvest({available:true, weekEnding:'2026-10-12', pctHarvested:30, wowChangePts:3}, new Date().toISOString());
check('收获推进缓慢(3个百分点)应判定偏多(可能秋雨导致延误)', window._harvestSignal === 1);

// ===================== 测试3：1月合约现在应该计入南美综合信号 =====================
resetAll();
H.setMockedMonth(10); // 南美播种生长期(10-次年1月)，权重55/45
window._saWeatherSignal = 1; window._saPsdSignal = 1;
selectContract('jan');
check('★1月合约：南美综合信号现在应该计入评分(之前完全不计入)', 
  elements['alertContent'].innerHTML.includes('南美(巴西/阿根廷)天气+产量综合'));

// ===================== 测试4：收获进度只在1月合约独立计入，其他合约不计入 =====================
resetAll();
window._harvestSignal = 1;
selectContract('jan');
check('★1月合约：收获进度信号应该独立计入评分', elements['alertContent'].innerHTML.includes('sd-cell sd-pos">美豆收获进度'));

resetAll();
window._harvestSignal = 1;
selectContract('sep');
check('★9月合约：即使收获进度信号存在，也不应该计入评分(跟1月无关)', !elements['alertContent'].innerHTML.includes('美豆收获进度'));

// ===================== 测试5：1月合约(10月)全部指标偏多时票数必须精确 =====================
resetAll();
elements['m_stock'].value='40'; elements['m_basis'].value='10'; elements['m_arrival'].value='700';
elements['m_hogratio'].value='8'; elements['m_sows'].value='3600'; elements['m_import'].value='700';
elements['m_poultry'].value='2'; elements['m_rmspread'].value='350';
window._saWeatherSignal=1; window._saPsdSignal=1; window._esrSignal=1; window._fxSignal=1; window._psdSignal=1;
window._harvestSignal=1;
H.setMockedMonth(10); // 播种生长期，权重55/45，两者都偏多，合成应为偏多
selectContract('jan');
// 10月有效投票：作物(南美)、库存消费比、国内豆粕供应松紧、大豆到港/进口、汇率、收获进度 = 6票供应；出口销售、基差、猪粮比、能繁、肉鸡、豆菜粕价差 = 6票需求。国储拍卖/巴西播种没数据不投票
// 手算：有效11票(供应6：作物/美豆库消比/国内松紧/到港进口/汇率/收获进度；需求5：出口/基差/猪粮比/肉鸡/豆菜粕；能繁、国储拍卖已移出评分)；
// 南美天气+产量都偏多→天气开关打开：作物×2，其余10票×0.5 → 2+5=+7；投票总数12(含没数据的巴西播种进度)
check('★1月合约(10月)：顶部10个供需票全偏多(原11个含基差)，天气开关打开：作物×2+其余9票×0.5=+6.5，共11票(含1个没数据的巴西播种进度)', elements['alertContent'].innerHTML.includes('基本面偏多 +6.5（') && elements['alertContent'].innerHTML.includes('有效10/11'));
H.clearMockedMonth();


H.printSummary();
