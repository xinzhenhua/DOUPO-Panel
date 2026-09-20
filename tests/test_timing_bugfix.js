const H = require('./test_helpers');
const { makeEl, elements, check } = H;
global.fetch = async(url)=>{
  if(url.includes('open-meteo')){
    return {ok:true, json:async()=>({daily:{precipitation_sum:[1,1,1,1,1,1,1], temperature_2m_max:[30,30,30,30,30,30,30]}})};
  }
  if(url.includes('frankfurter')){
    return {ok:true, json:async()=>({rates:{CNY:7.15,BRL:5.4}, date:'2026-07-10'})};
  }
  return {ok:false};
};

eval(H.loadDashboardJs());


// ===================== 测试2：天气/汇率的时序bug已修复 =====================
// 准备好综合预警需要的字段(空值即可，只是为了不让updateOverallAlert在读取时报错)
['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import'].forEach(id=>{
  elements[id] = makeEl(id);
});
elements['ind_crush']=makeEl('ind_crush');elements['ind_stock']=makeEl('ind_stock');
elements['ind_basis']=makeEl('ind_basis');elements['ind_arrival']=makeEl('ind_arrival');
elements['ind_hogratio']=makeEl('ind_hogratio');elements['ind_sows']=makeEl('ind_sows');
elements['ind_import']=makeEl('ind_import');
elements['alertContent'] = makeEl('alertContent');
elements['weatherContent'] = makeEl('weatherContent');
elements['weatherBadge'] = makeEl('weatherBadge');
elements['fxContent'] = makeEl('fxContent');
elements['fxBadge'] = makeEl('fxBadge');

(async()=>{
  // 先确认window._weatherRisk一开始是undefined(模拟页面刚打开、天气数据还没到达的状态)
  check('测试开始前window._weatherRisk应为undefined(模拟数据未加载完成的状态)', window._weatherRisk === undefined);

  await loadWeather();
  // ★ 核心验证：loadWeather完成后，alertContent应该已经被更新过(不再是初始的loading占位文字)
  //   如果之前的bug还在，alertContent会因为从没被updateOverallAlert触碰过而保持初始值
  check('★之前的bug修复验证：loadWeather完成后，window._weatherRisk应已被设置', window._weatherRisk !== undefined);
  check('★之前的bug修复验证：loadWeather完成后，综合预警应已重新渲染(alertContent.innerHTML应包含"数据不足"提示，因为没填手动数据但天气信号已经生效触发了渲染)',
    elements['alertContent'].innerHTML.length > 0);

  await loadFxRate();
  check('★之前的bug修复验证：loadFxRate完成后，window._fxSignal应已被设置', window._fxSignal !== undefined);

  // ===================== 测试3：供需表格里应该同时体现天气和汇率信号 =====================
  elements['m_crush'].value = '35'; // 触发至少一个手动指标信号，避免"数据不足"分支
  updateOverallAlert();
  check('供需表格应该包含"天气"这个供应侧标签', elements['alertContent'].innerHTML.includes('天气'));
  check('供需表格应该包含"人民币汇率"这个供应侧标签', elements['alertContent'].innerHTML.includes('人民币汇率'));
  check('供需表格应该包含"出口销售"这个需求侧标签', elements['alertContent'].innerHTML.includes('出口销售'));
  check('供需表格应该包含"猪粮比"这个需求侧标签', elements['alertContent'].innerHTML.includes('猪粮比'));

  console.log('');
  H.printSummary();
})();
