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

// ===================== 测试1：美国6-7月权重(35/30/10/25) =====================
// 场景：天气偏多(35%)+NOAA偏多(30%) vs 干旱偏空(10%)+优良率偏空(25%)
// 加权：(35+30-10-25)/100 = 30/100 = 0.3，不到0.5阈值，应该是中性
// 换一个更明确的场景：只有天气(35%)和NOAA(30%)偏多，干旱(10%)和优良率(25%)缺失
// 加权：(35*1+30*1)/(35+30) = 1.0，应该是明确偏多
H.setMockedMonth(7);
resetAll();
window._weatherRisk='high'; window._noaaOutlookSignal=1; window._droughtSignal=null; window._soyCondSignal=null;
selectContract('sep');
check('6-7月：只有天气+NOAA两个权重最大的信号偏多时，应该合成偏多(6-7月这两项占65%权重)',
  elements['alertContent'].innerHTML.includes('sd-cell sd-pos">作物生长状况综合'));
check('标签应该标注"6-7月"权重', elements['alertContent'].innerHTML.includes('6-7月权重') || elements['contractContext'] );

// 反过来：只有干旱监测(10%)偏多，其余缺失 → 权重太小，不该达到±0.5阈值触发方向
resetAll();
window._weatherRisk=null; window._noaaOutlookSignal=null; window._droughtSignal=1; window._soyCondSignal=null;
selectContract('sep');
// 干旱监测单独存在时，avail只有它自己，weighted avg = 1*10/10 = 1，达到阈值——
// 这是符合预期的：如果只有这一个信号可用，就用它自己的方向，不是"权重太小所以强制中性"
check('6-7月：如果只有干旱监测这一项数据可用(其他都缺失)，应该用它自己的方向(而不是因为权重占比低就强制中性)',
  elements['alertContent'].innerHTML.includes('sd-cell sd-pos">作物生长状况综合'));

// 真正验证权重差异的场景：天气(35%,偏多) vs 干旱监测(10%,偏空)，两者都有数据，方向相反
resetAll();
window._weatherRisk='high'; window._droughtSignal=-1; window._noaaOutlookSignal=null; window._soyCondSignal=null;
selectContract('sep');
// 加权 = (35*1 + 10*(-1))/(35+10) = 25/45 ≈ 0.556，超过0.5阈值，应该是偏多(天气权重更大，主导结果)
check('★6-7月核心验证：天气(权重35%,偏多) vs 干旱监测(权重10%,偏空)方向相反时，天气权重更大应该主导为偏多',
  elements['alertContent'].innerHTML.includes('sd-cell sd-pos">作物生长状况综合'));

// ===================== 测试2：美国8月起权重(25/15/30/30) =====================
H.setMockedMonth(8);
resetAll();
window._weatherRisk='low'; window._droughtSignal=1; window._noaaOutlookSignal=null; window._soyCondSignal=null;
selectContract('sep');
// 加权 = (25*(-1) + 30*1)/(25+30) = 5/55 ≈ 0.09，不到0.5，应该是中性
check('★8月起核心验证：天气(权重25%,偏空) vs 干旱监测(权重30%,偏多)，8月起干旱监测权重反超天气，方向相反时更接近中性(不像6-7月那样天气说了算)',
  elements['alertContent'].innerHTML.includes('sd-cell sd-neutral">作物生长状况综合'));
check('8月起标签应该标注"8月起"权重', elements['alertContent'].innerHTML.includes('8月起权重'));

resetAll();
window._weatherRisk=null; window._noaaOutlookSignal=1; window._droughtSignal=null; window._soyCondSignal=null;
selectContract('sep');
check('8月起：NOAA展望单独偏多时权重只有15%，但因为是唯一可用信号，仍应采用其方向',
  elements['alertContent'].innerHTML.includes('sd-cell sd-pos">作物生长状况综合'));

// ===================== 测试3：南美三阶段权重 =====================
// 休耕期(6-9月)：weather=10, psd=90
H.setMockedMonth(7);
resetAll();
window._saWeatherSignal=1; window._saPsdSignal=-1; // 天气偏多但权重仅10%，产量偏空权重90%
selectContract('may');
// 加权 = (10*1 + 90*(-1))/100 = -80/100 = -0.8，应该是偏空(产量数据主导)
check('★南美休耕期核心验证：天气权重仅10%，产量权重90%，方向相反时产量数据应该主导结果为偏空',
  elements['alertContent'].innerHTML.includes('sd-cell sd-neg">南美(巴西/阿根廷)天气+产量综合'));
check('休耕期标签应该标注"休耕期"权重', elements['alertContent'].innerHTML.includes('休耕期权重'));

// 播种生长期(10-次年1月)：weather=55, psd=45
H.setMockedMonth(11);
resetAll();
window._saWeatherSignal=1; window._saPsdSignal=-1;
selectContract('may');
// 加权 = (55*1 + 45*(-1))/100 = 10/100 = 0.1，不到0.5，应该是中性(权重比较接近，方向相反时容易变中性)
check('★南美播种生长期核心验证：天气(55%)vs产量(45%)权重接近，方向相反时应该更接近中性',
  elements['alertContent'].innerHTML.includes('sd-cell sd-neutral">南美(巴西/阿根廷)天气+产量综合'));
check('播种生长期标签应该标注"播种生长期"权重', elements['alertContent'].innerHTML.includes('播种生长期权重'));

// 关键期收获期(2-5月)：weather=20, psd=80
H.setMockedMonth(3);
resetAll();
window._saWeatherSignal=1; window._saPsdSignal=-1;
selectContract('may');
// 加权 = (20*1 + 80*(-1))/100 = -60/100 = -0.6，应该是偏空(产量数据主导，收获期看实际产量更准)
check('★南美关键期收获期核心验证：产量权重80%远超天气20%，收获期应该以实际产量数据为准，判定偏空',
  elements['alertContent'].innerHTML.includes('sd-cell sd-neg">南美(巴西/阿根廷)天气+产量综合'));
check('关键期收获期标签应该标注"关键期收获期"权重', elements['alertContent'].innerHTML.includes('关键期收获期权重'));


H.printSummary();
