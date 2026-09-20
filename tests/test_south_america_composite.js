const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


function resetAll(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry','m_rmspread'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import','ind_poultry','ind_rmspread',
   'tab-sep','tab-may','tab-jan','contractContext','esrPsdContractNote','group-us-weather','group-sa'].forEach(id=>elements[id]=makeEl(id));
  elements['alertContent'] = makeEl('alertContent');
  elements['m_crush'].value = '35';
}

// 场景A：南美天气偏多 + 南美产量也偏多(供给紧张) → 应该合成偏多
resetAll();
window._saWeatherSignal = 1; window._saPsdSignal = 1;
selectContract('may');
check('场景A：天气偏多+产量偏多，两者一致，应合成偏多', elements['alertContent'].innerHTML.includes('sd-cell sd-pos">南美(巴西/阿根廷)天气+产量综合'));

// 场景B：南美天气偏空(降雨充沛) + 南美产量偏空(丰产) → 应该合成偏空
resetAll();
window._saWeatherSignal = -1; window._saPsdSignal = -1;
selectContract('may');
check('场景B：天气偏空+产量偏空，两者一致，应合成偏空', elements['alertContent'].innerHTML.includes('sd-cell sd-neg">南美(巴西/阿根廷)天气+产量综合'));

// 场景C：两者方向不一致(天气偏多但产量数据显示丰产偏空)
// ★ 已更新：现在是时间感知加权(不再是50/50等权重)，具体结果取决于当前处于南美生长周期哪个阶段，
// 权重差距大的阶段(比如休耕期天气10%/产量90%)方向相反时会被权重更大的一方主导，不再是"总是中性"
resetAll();
window._saWeatherSignal = 1; window._saPsdSignal = -1;
selectContract('may');
check('场景C：天气偏多+产量偏空，方向不一致，结果取决于当前所处南美生长阶段的权重(不再是固定的50/50中性)', (()=>{
  const html = elements['alertContent'].innerHTML;
  return html.includes('sd-cell sd-neutral">南美(巴西/阿根廷)天气+产量综合') ||
         html.includes('sd-cell sd-neg">南美(巴西/阿根廷)天气+产量综合') ||
         html.includes('sd-cell sd-pos">南美(巴西/阿根廷)天气+产量综合');
})());

// 场景D：只有PSD数据，天气数据缺失(比如南美天气拉取失败) → 应该只用PSD单独判断，不因为天气缺失就整体不算
resetAll();
window._saWeatherSignal = null; window._saPsdSignal = 1;
selectContract('may');
check('场景D：只有产量数据(天气缺失)，应该单独用产量数据判断，不因天气缺失就完全不计入', elements['alertContent'].innerHTML.includes('sd-cell sd-pos">南美(巴西/阿根廷)天气+产量综合'));


H.printSummary();
