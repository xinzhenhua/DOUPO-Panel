const H = require('./test_helpers');
const { makeEl, elements, check } = H;
global.fetch = async()=>({ok:true, json:async()=>({daily:{precipitation_sum:[1,1,1,1,1,1,1], temperature_2m_max:[28,28,28,28,28,28,28]}})});

eval(H.loadDashboardJs());


// ===================== 测试1：合约切换基础功能 =====================
['tab-sep','tab-may','tab-jan','contractContext','group-us-weather','group-sa'].forEach(id=>makeEl(id));

selectContract('sep');
check('选中9月合约后，9月按钮应为active', elements['tab-sep'].classList.contains('active'));
check('9月合约：美国天气组不应该被隐藏', !elements['group-us-weather'].classList.contains('hidden-by-contract'));
check('★行为已变更(改成隐藏而非变暗)：9月合约：南美组应该被隐藏', elements['group-sa'].classList.contains('hidden-by-contract'));
check('9月合约提示文字应提到"生长关键期"', elements['contractContext'].innerHTML.includes('生长关键期'));

selectContract('may');
check('选中5月合约后，5月按钮应为active，9月不再是', elements['tab-may'].classList.contains('active') && !elements['tab-sep'].classList.contains('active'));
check('★行为已变更：5月合约：美国天气组应该被隐藏(不是当前重点)', elements['group-us-weather'].classList.contains('hidden-by-contract'));
check('★行为已变更：5月合约：南美组应该显示(不是隐藏)', !elements['group-sa'].classList.contains('hidden-by-contract'));
check('5月合约提示应提到"巴西"', elements['contractContext'].innerHTML.includes('巴西'));

selectContract('jan');
check('选中1月合约后，1月按钮应为active', elements['tab-jan'].classList.contains('active'));
check('1月合约提示应提到"最终产量"或"WASDE"', elements['contractContext'].innerHTML.includes('最终产量') || elements['contractContext'].innerHTML.includes('WASDE'));

// ===================== 测试2：南美天气渲染(实际执行异步函数) =====================
(async()=>{
  elements['saWeatherBadge']=makeEl('saWeatherBadge'); elements['saWeatherContent']=makeEl('saWeatherContent');
  await loadSaWeather();
  check('南美天气加载完成后badge应显示"实时自动"', elements['saWeatherBadge'].textContent.includes('实时自动'));
  check('南美天气内容应包含降雨相关文字', elements['saWeatherContent'].innerHTML.includes('降雨'));
  check('南美天气应提到南半球生长季节', elements['saWeatherContent'].innerHTML.includes('南半球'));
  check('南美天气应包含<svg>条形图', elements['saWeatherContent'].innerHTML.includes('<svg'));

  // ===================== 测试3：南美PSD渲染 =====================
  elements['saPsdBadge']=makeEl('saPsdBadge'); elements['saPsdContent']=makeEl('saPsdContent');
  renderSaPsd({available:true, byCountry:{
    BR:{available:true, marketYear:2025, production:170000, totalSupply:180000, countryName:'巴西'},
    AR:{available:false, reason:'国家代码验证失败(测试模拟)'},
  }}, new Date().toISOString());
  check('南美PSD应正确显示巴西产量数据', elements['saPsdContent'].innerHTML.includes('巴西') && elements['saPsdContent'].innerHTML.includes('170,000'));
  check('南美PSD应正确显示阿根廷失败原因(而不是静默隐藏)', elements['saPsdContent'].innerHTML.includes('国家代码验证失败'));

  // 完全无数据的情况
  elements['saPsdBadge']=makeEl('saPsdBadge'); elements['saPsdContent']=makeEl('saPsdContent');
  renderSaPsd({available:false, reason:'测试整体失败'}, null);
  check('南美PSD完全失败时应明确提示，且提及国家代码未验证的风险', elements['saPsdContent'].innerHTML.includes('国家代码') && elements['saPsdContent'].innerHTML.includes('推断'));

  console.log('');
  H.printSummary();
})();
