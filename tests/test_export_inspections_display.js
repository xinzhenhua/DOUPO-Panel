const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：数据不可用时的降级显示 =====================
makeEl('exportInspBadge'); makeEl('exportInspContent');
renderExportInspections({available: false, reason: '找到大豆记录，但数值字段有多个候选，无法唯一确定'}, new Date().toISOString());
check('★数据不可用时应该显示具体原因', makeEl('exportInspContent').innerHTML.includes('数值字段有多个候选'));

renderExportInspections(null, new Date().toISOString());
check('传null不应该报错，应该有兜底文字', makeEl('exportInspContent').innerHTML.includes('未知原因'));

// ===================== 测试2：数据可用时的显示——纯展示，不判断方向 =====================
makeEl('exportInspBadge'); makeEl('exportInspContent');
const eiData = {
  available: true, quantity: 673000, quantityFieldName: 'metric_tons_current_week',
  commodity: 'Soybeans', rawRecord: {commodity_desc: 'Soybeans', metric_tons_current_week: '673000'},
  source: '测试来源',
};
renderExportInspections(eiData, new Date().toISOString());
check('★应该显示数值(673,000，带千分位)', makeEl('exportInspContent').innerHTML.includes('673,000'));
check('★应该显示商品名称(Soybeans)', makeEl('exportInspContent').innerHTML.includes('Soybeans'));
check('★应该明确标注"仅供参考不计入综合评分"(没有比较基准，不该判断方向)', makeEl('exportInspContent').innerHTML.includes('仅供参考不计入综合评分'));
check('★不应该出现bull/bear这种方向性样式(没有基准硬判断方向不诚实)', 
  !makeEl('exportInspContent').innerHTML.includes('alert-box bull') && !makeEl('exportInspContent').innerHTML.includes('alert-box bear'));
check('详情区应该显示数值字段名，方便核对', makeEl('exportInspContent').innerHTML.includes('metric_tons_current_week'));
check('详情区应该显示原始记录JSON，方便核对单位等细节', makeEl('exportInspContent').innerHTML.includes('commodity_desc'));

// ===================== 测试3：commodity缺失时应该有兜底文字，不是显示undefined =====================
makeEl('exportInspBadge'); makeEl('exportInspContent');
renderExportInspections({...eiData, commodity: null}, new Date().toISOString());
check('★commodity缺失时应该兜底显示"大豆"，不是显示null/undefined', 
  makeEl('exportInspContent').innerHTML.includes('大豆') && !makeEl('exportInspContent').innerHTML.includes('undefined'));

H.printSummary();
