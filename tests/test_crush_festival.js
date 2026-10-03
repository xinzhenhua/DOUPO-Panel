// ============================================================================
// 油厂开机率：春节停机扰动期(节前7天~节后14天)不计分；国庆不受影响
// 数据是用户2026-10-02采样诊断得到的真实开机率(2024-12~2026-09)
// ============================================================================
const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
const E = window._eventCal;
const AUTO = window._autoIndicators, BYKEY = window._autoByKey;
const KEYS = AUTO.map(c=>c.key);
const html = k=>makeEl('ai_'+k).innerHTML;
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); });
  window._indState = {}; makeEl('alertContent');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
  window._selectedContract='sep';
}
const FEST = (daysTo, holidayDate)=>({name:'春节', daysTo, phase: daysTo<0?'节前备货':'假期', holidayDate});
const crushData = (value, date, festival)=>({available:true, value, date, festival: festival||null, rawContent:'x', source:'Mysteel快讯', sourceUrl:'x'});
function load(value, date, festival, nowMs){
  reset();
  window._nowMs = nowMs;
  window._syncedData = {generatedAt:new Date(nowMs).toISOString(), mysteelCrushRate: crushData(value, date, festival)};
  refreshMysteelCrushRate();
  return window._indState.crush;
}
const badge = ()=>makeEl('badge_crush').textContent;
const cfg = BYKEY.crush;

// ---------- 1. 真实数据：春节期间的低值不计分 ----------
// 2026-02-24：春节(2月17日)后7天，开机率15.46%("较前一日上升7.20%")——放假，不是供应紧
let st = load(15.46, '2026-02-24', FEST(7,'2026-02-17'), E.bjToMs(2026,2,25,10,0));
check('★真实数据2026-02-24(春节后7天)15.46%：进入"扰动期不计分"(suppressed)，不再被"<40偏多"误判', st.suppressed.startsWith('春节后7天') && st.mode==='auto');
check('★详情里写明原因和依据(放假停机、不代表供应松紧、国庆不受影响)', html('crush').includes('春节后7天') && html('crush').includes('放假停机') && html('crush').includes('不代表供应松紧') && html('crush').includes('国庆油厂不停机'));
check('★徽标：🧧春节扰动期·不计分', badge().includes('春节') && badge().includes('扰动期') && badge().includes('不计分'));
updateOverallAlert();
check('★评分里没有开机率这一票：春节扰动期的开机率不参与"国内豆粕供应松紧"(该票在_quality.missing里，因为它只靠开机率+库存，开机率不投就缺席)', window._quality.missing.includes('国内豆粕供应松紧'));
check('★同一个场景下，开机率的卡片提示写明"不参与综合评分"', makeEl('alert_crush').innerHTML.includes('不参与综合评分') || makeEl('alert_crush').textContent.includes('不参与综合评分'));
// 同样的15.46%，如果不在春节窗口(比如后端没给festival)，旧行为：<40 → 偏多
st = load(15.46, '2026-06-24', null, E.bjToMs(2026,6,25,10,0));
updateOverallAlert();
check('对照：同样的15.46%但不在春节窗口：不抑制(suppressed为空)，按原规则', st.suppressed === '' && !html('crush').includes('放假停机'));
check('★对照：不在春节窗口时开机率照常投票(<40偏多)，"国内豆粕供应松紧"不再缺席', !window._quality.missing.includes('国内豆粕供应松紧') && makeEl('alert_crush').innerHTML.includes('偏多'));

// ---------- 2. 窗口内各个位置 ----------
for (const [dt, daysTo, label] of [['2026-02-10',-7,'节前7天(窗口起点)'],['2026-02-17',0,'春节当天'],['2026-03-03',14,'节后14天(窗口终点)']]){
  st = load(43.0, dt, FEST(daysTo,'2026-02-17'), E.bjToMs(2026,2,11,10,0) + (daysTo>0?daysTo*86400000:0));
  check(`窗口内·${label}：不计分`, st.suppressed.startsWith('春节'));
}
st = load(9.80, '2025-01-26', FEST(-3,'2025-01-29'), E.bjToMs(2025,1,27,10,0));
check('★真实数据2025-01-26(春节前3天)9.80%：低于合理范围下限10，被当作异常丢弃(同样不投票)——不是抑制，而是"数值异常已忽略"', st.mode==='none' && st.failReason.includes('不合理') && badge().includes('异常'));

// ---------- 3. 国庆不受影响(这是用数据证明的：国庆油厂不停机) ----------
st = load(60.0, '2025-10-02', null, E.bjToMs(2025,10,3,10,0));
check('★国庆期间：后端不给festival(只认春节)，开机率正常计分', st.suppressed === '' && st.mode==='auto' && !badge().includes('扰动期'));

// ---------- 4. 手动修正后恢复计分 ----------
st = load(15.46, '2026-02-24', FEST(7,'2026-02-17'), E.bjToMs(2026,2,25,10,0));
check('前置：自动读数处于春节扰动期', st.suppressed !== '');
makeEl('m_crush').value = '55'; onManualEdit('crush');
check('★用户手动填了值：视为自己负责，恢复计分(suppressed清空)', window._indState.crush.suppressed === '');

// ---------- 5. 健康度面板 ----------
st = load(15.46, '2026-02-24', FEST(7,'2026-02-17'), E.bjToMs(2026,2,25,10,0));
updateOverallAlert();
const hr = indicatorHealth(cfg);
check('★健康度：开机率那一行是suppressed状态，图标🧧，标签"春节扰动期·不计分"', hr.state === 'suppressed' && hr.icon === '🧧' && hr.label === '春节扰动期·不计分');

// ---------- 6. 评分规则版本 ----------
check('★评分规则版本不低于v97(春节期间的投票变了，方向的含义变了；精确版本号只在test_crush_rule.js里守，免得每次升版都要改这里)', parseInt(String(window._scoringVersion).replace(/\D/g,''), 10) >= 97);

H.printSummary();
