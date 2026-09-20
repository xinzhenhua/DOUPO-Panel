const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


function resetAll(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry','m_rmspread'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import','ind_poultry','ind_rmspread',
   'tab-sep','tab-may','tab-jan','contractContext','group-us-weather','group-sa'].forEach(id=>elements[id]=makeEl(id));
  elements['alertContent'] = makeEl('alertContent');
  elements['m_crush'].value = '35'; // 保底1个手动信号，避免"数据不足"分支
}

// ===================== 测试1：9月合约用美国天气类信号 =====================
resetAll();
window._weatherRisk = 'high'; window._droughtSignal = 1; window._noaaOutlookSignal = 1; window._soyCondSignal = 1;
window._saWeatherSignal = -1; // 故意设成相反方向，验证9月合约不会误用这个
selectContract('sep');
check('9月合约：应该用美国天气类综合信号(4项子信号全偏多→合成偏多)', elements['alertContent'].innerHTML.includes('sd-cell sd-pos">作物生长状况综合'));
check('9月合约：不应该被南美信号(相反方向)干扰', !elements['alertContent'].innerHTML.includes('南美(巴西/阿根廷)天气状况'));

// ===================== 测试2：5月合约切换成用南美天气信号 =====================
resetAll();
window._weatherRisk = 'low'; window._droughtSignal = -1; window._noaaOutlookSignal = -1; window._soyCondSignal = -1; // 美国信号全偏空
window._saWeatherSignal = 1; // 南美信号偏多
selectContract('may');
check('5月合约：应该用南美天气+产量综合信号(偏多)，不是美国天气信号(偏空)', elements['alertContent'].innerHTML.includes('sd-cell sd-pos">南美(巴西/阿根廷)天气+产量综合'));
check('5月合约：不应该显示美国天气类综合这个标签', !elements['alertContent'].innerHTML.includes('作物生长状况综合'));

// ===================== 测试3：1月合约不计入任何天气类信号 =====================
resetAll();
window._weatherRisk = 'high'; window._droughtSignal = 1; window._noaaOutlookSignal = 1; window._soyCondSignal = 1;
window._saWeatherSignal = 1;
selectContract('jan');
check('1月合约：不应该显示"作物生长状况综合"(美国天气类)', !elements['alertContent'].innerHTML.includes('作物生长状况综合'));
check('1月合约：不应该显示"南美天气状况"', !elements['alertContent'].innerHTML.includes('南美(巴西/阿根廷)天气状况'));

// ===================== 测试4：不同合约下，仪表盘最大票数不同(1月少1票) =====================
resetAll();
window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null; window._saWeatherSignal=null;
window._esrSignal=1; window._fxSignal=1; window._psdSignal=1;
elements['m_stock'].value='40'; elements['m_basis'].value='10'; elements['m_arrival'].value='700';
elements['m_hogratio'].value='8'; elements['m_sows'].value='3600'; elements['m_import'].value='700';
elements['m_poultry'].value='2'; elements['m_rmspread'].value='350';
selectContract('jan'); // 12票都偏多(没有天气类)，1月合约上限应该是12
check('★1月合约：12个信号全偏多，总分应精确为+12(1月合约上限就是12，不是13)', elements['alertContent'].innerHTML.includes('+12分'));

// ===================== 测试5：南美PSD已验证生效，用这次实测确认过的真实数值测试 =====================
// 巴西186,000 vs 查证过的真实值180,000(误差3.3%，WASDE月度修正的正常范围) → 确认修复生效
// 阿根廷50,000完全吻合查证过的真实值 → 根因(商品匹配抓错)修复得到验证
elements['saPsdBadge']=makeEl('saPsdBadge'); elements['saPsdContent']=makeEl('saPsdContent');
renderSaPsd({available:true, byCountry:{
  BR:{available:true, marketYear:2026, production:186000, totalSupply:224488, countryName:'巴西'},
  AR:{available:true, marketYear:2026, production:50000, totalSupply:80321, countryName:'阿根廷'},
}}, new Date().toISOString());
check('★南美PSD数据已验证生效后，应该显示带信号的alert-box(不再是永久性"待验证"提示)', !elements['saPsdContent'].innerHTML.includes('待下次同步验证'));
check('南美PSD应该显示巴西+阿根廷合计产量', elements['saPsdContent'].innerHTML.includes('合计产量'));
check('★南美PSD数据确认可靠后，应该正常给出偏多/偏空判断(不再强制为null)', window._saPsdSignal !== null);
check('南美PSD原始数字仍然要显示出来', elements['saPsdContent'].innerHTML.includes('186,000'));
// 236,000(千吨)合计产量 > 210,000阈值 → 应判定产量丰厚，偏空
check('巴西+阿根廷合计236,000(千吨)，超过210,000阈值，应判定为产量丰厚→偏空', window._saPsdSignal === -1);


H.printSummary();
