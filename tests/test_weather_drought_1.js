const H = require('./test_helpers');
const { makeEl, elements } = H;

eval(H.loadDashboardJs());


// ============ 测试场景 ============
let pass = 0, fail = 0;
function check(desc, actual, expected){
  if(JSON.stringify(actual)===JSON.stringify(expected)){ pass++; console.log('✅', desc); }
  else{ fail++; console.log('❌', desc, '期望:', expected, '实际:', actual); }
}

// 场景1：全部字段都填写偏多方向的值，验证score和每个指示器
elements['m_crush'].value = '35';    // <40 偏多
elements['m_stock'].value = '40';    // <50 偏多
elements['m_basis'].value = '20';    // >0 偏多
elements['m_arrival'].value = '150'; // <180 偏多
elements['m_hogratio'].value = '8';  // >7 偏多
elements['m_sows'].value = '3600';   // <3700 偏多
elements['m_import'].value = '700';  // <800 偏多（新逻辑，之前这个方向是反的）

window._weatherRisk = null;
window._droughtSignal = 0;
window._esrSignal = 0;
window._fxSignal = 0;
window._psdSignal = 0;

updateOverallAlert();

check('7项全偏多字段 → 每个指示器都应该是pos(偏多/红色)',
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import'].map(id=>elements[id].className),
  new Array(7).fill('field-ind pos'));

check('7项全偏多 → alertCard应显示"综合偏多"',
  elements['alertContent'].innerHTML.includes('综合偏多'), true);

// 场景2：中国进口量方向验证（这是本次修复的重点：进口多=偏空，不是之前写反的"进口多=偏多"）
elements['m_import'].value = '1200'; // >1000 现在应该是偏空
updateOverallAlert();
check('进口1200万吨（>1000）→ 应为偏空(neg)，验证方向已修正',
  elements['ind_import'].className, 'field-ind neg');

// 场景3：清空某个字段 → 对应指示器应该清空不显示
elements['m_crush'].value = '';
updateOverallAlert();
check('清空开机率字段 → 指示器应清空（不显示pos/neg残留）',
  elements['ind_crush'].className, 'field-ind');

// 场景4：中性区间值 → 应显示中性(灰色)而不是无色
elements['m_crush'].value = '50'; // 40-60之间，中性
updateOverallAlert();
check('开机率50%（中性区间）→ 应显示neutral(灰色)而非空',
  elements['ind_crush'].className, 'field-ind neutral');

// 场景5：验证之前完全没接入打分的3个字段，现在确实生效了
elements['m_crush'].value=''; elements['m_stock'].value=''; elements['m_basis'].value='';
elements['m_hogratio'].value=''; elements['m_import'].value='';
elements['m_arrival'].value = '150'; // 偏多 +1
elements['m_sows'].value = '3600';   // 偏多 +1
updateOverallAlert();
check('只填到港预报+能繁母猪(之前未接入的2个字段) → alertCard应能识别出信号而非"数据不足"',
  elements['alertContent'].innerHTML.includes('数据不足'), false);

// 场景6：验证FX的alert-box颜色不再永远是neutral
window._fxSignal = 1;
elements['fxContent'] = makeEl('fxContent');
// 直接测试 renderPsd 的 _psdSignal 计算逻辑
elements['psdBadge'] = makeEl('psdBadge');
elements['psdContent'] = makeEl('psdContent');
renderPsd({available:true, marketYear:2026, endingStocks:300, production:52000, domesticConsumption:34000}, new Date().toISOString());
const psdRatio = 300/34000*100;
check('PSD库存消费比计算：300/34000='+psdRatio.toFixed(2)+'% → 应判定为偏多(ratio<15)',
  window._psdSignal, 1);


console.log('');
console.log(`结果：${pass}项通过，${fail}项失败`);
if(fail>0) process.exit(1);
