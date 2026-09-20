const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


// 场景1：新的byState结构，明尼苏达展望恶化点位占比高
elements['noaaOutlookBadge'] = makeEl('noaaOutlookBadge');
elements['noaaOutlookContent'] = makeEl('noaaOutlookContent');
renderNoaaOutlook({
  available: true,
  byState: {
    IA: {available:true, worseningCount:0, totalPoints:8, worseningPct:0, dominantOutlook:'No_Drought', dominantOutlookLabel:'预计无旱', targetPeriod:'Jul 2026'},
    IL: {available:true, worseningCount:1, totalPoints:8, worseningPct:12.5, dominantOutlook:'No_Drought', dominantOutlookLabel:'预计无旱', targetPeriod:'Jul 2026'},
    MN: {available:true, worseningCount:5, totalPoints:8, worseningPct:62.5, dominantOutlook:'Persistence', dominantOutlookLabel:'干旱持续', targetPeriod:'Jul 2026'},
  },
  avgWorseningPct: 25.0,
  overallSignal: 1,
}, new Date().toISOString());
check('新结构正常渲染，显示已同步', elements['noaaOutlookBadge'].textContent.includes('已同步'));
check('显示各州的恶化点位占比(明尼苏达62.5%)', elements['noaaOutlookContent'].innerHTML.includes('62.5%'));
check('显示众数展望', elements['noaaOutlookContent'].innerHTML.includes('干旱持续'));
check('偏多场景正确显示', elements['noaaOutlookContent'].innerHTML.includes('偏多信号'));
check('window._noaaOutlookSignal正确设为1', window._noaaOutlookSignal === 1);

// 场景2：中性情况(signal=0)
elements['noaaOutlookBadge'] = makeEl('noaaOutlookBadge');
elements['noaaOutlookContent'] = makeEl('noaaOutlookContent');
renderNoaaOutlook({
  available: true,
  byState: {
    IA: {available:true, worseningCount:1, totalPoints:8, worseningPct:12.5, dominantOutlook:'No_Drought', dominantOutlookLabel:'预计无旱', targetPeriod:'Jul 2026'},
  },
  avgWorseningPct: 12.5,
  overallSignal: 0,
}, new Date().toISOString());
check('中性场景(0)应显示"持续观察"文字', elements['noaaOutlookContent'].innerHTML.includes('持续观察'));
check('中性场景window._noaaOutlookSignal应为0', window._noaaOutlookSignal === 0);


H.printSummary();
