const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：数据不可用时的降级显示 =====================
makeEl('exportInspBadge'); makeEl('exportInspContent');
renderExportInspections({available: false, reason: '筛选grain=\'SOYBEANS\'后没有查到任何记录'}, new Date().toISOString());
check('★数据不可用时应该显示具体原因', makeEl('exportInspContent').innerHTML.includes('没有查到任何记录'));

renderExportInspections(null, new Date().toISOString());
check('传null不应该报错，应该有兜底文字', makeEl('exportInspContent').innerHTML.includes('未知原因'));

// ===================== 测试2：数据可用时的显示——单位已确认是公吨 =====================
makeEl('exportInspBadge'); makeEl('exportInspContent');
const eiData = {
  available: true, weekEndingDate: '2026-09-21', quantityMetricTons: 673000, recordCountThisWeek: 2,
  source: 'USDA AMS Federal Grain Inspection Service，经agtransport.usda.gov获取',
};
renderExportInspections(eiData, new Date().toISOString());
check('★应该显示数值(673,000，带千分位)', makeEl('exportInspContent').innerHTML.includes('673,000'));
check('★应该明确标注单位是公吨(不再是之前的不确定状态)', makeEl('exportInspContent').innerHTML.includes('公吨'));
check('★应该明确标注"仅供参考不计入综合评分"', makeEl('exportInspContent').innerHTML.includes('仅供参考不计入综合评分'));
check('★不应该出现bull/bear这种方向性样式(没有比较基准，不该判断方向)',
  !makeEl('exportInspContent').innerHTML.includes('alert-box bull') && !makeEl('exportInspContent').innerHTML.includes('alert-box bear'));
check('详情区应该显示当周记录数(2条)', makeEl('exportInspContent').innerHTML.includes('>2<'));
check('详情区应该显示数据周次', makeEl('exportInspContent').innerHTML.includes('2026-09-21'));

H.printSummary();
