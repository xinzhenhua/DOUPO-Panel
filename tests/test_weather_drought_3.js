const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


// 复现真实报告的异常场景
elements['droughtBadge'] = makeEl('droughtBadge');
elements['droughtContent'] = makeEl('droughtContent');
renderDrought({
  available: true,
  anomalous: true,
  byState: {
    IA: {available:true, anomalous:true, validDate:'2026-06-30', d0:18776.87, d1:6840.84, d2:1.9, d3:0, d4:0, severeOrWorsePct:1.9},
    IL: {available:true, anomalous:false, validDate:'2026-06-30', d0:10, d1:5, d2:0, d3:0, d4:0, severeOrWorsePct:0},
    MN: {available:true, anomalous:true, validDate:'2026-06-30', d0:60706.52, d1:25537.95, d2:9779.32, d3:0, d4:0, severeOrWorsePct:9779.32},
  },
  avgSevereOrWorsePct: 3260.4,
  debug: {IA:{note:'test'}, IL:{note:'test'}, MN:{note:'test'}}
}, new Date().toISOString());

check('异常场景：badge应显示"数据异常"而不是绿色"已同步"', elements['droughtBadge'].textContent.includes('异常'));
check('异常场景：不应该显示误导性的"干旱面积占比高/低"结论文字', !elements['droughtContent'].innerHTML.includes('干旱面积占比高'));
check('异常场景：应明确提示"数值异常"', elements['droughtContent'].innerHTML.includes('数值异常') || elements['droughtContent'].innerHTML.includes('检测到数值超出'));
check('异常场景：window._droughtSignal应为0（不参与打分，避免异常数据污染综合预警）', window._droughtSignal === 0);
check('异常场景：正常的IL州数据仍应正常显示（不应该因为其他州异常就全部隐藏）', elements['droughtContent'].innerHTML.includes('伊利诺伊'));


H.printSummary();
