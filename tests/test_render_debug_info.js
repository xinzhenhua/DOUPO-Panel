const H = require('./test_helpers');
const { check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：场景A(PSD/ESR那种)既有行为不变 =====================
const a = renderDebugInfo({warning: '字段不匹配', actualFieldsSeen: ['x','y'], sampleRawRow: {foo:1}});
check('场景A应该显示实际字段名', a.includes('实际收到的字段名') && a.includes('"x"') && a.includes('"y"'));
check('场景A应该显示原始数据样例', a.includes('原始数据样例') && a.includes('foo'));

// ===================== 测试2：场景B(网络请求失败那种)既有行为不变 =====================
const b = renderDebugInfo({url: 'http://x.com', httpStatus: 404, error: 'not found'});
check('场景B应该显示HTTP状态码', b.includes('404'));
check('场景B应该显示错误信息', b.includes('not found'));

const bMulti = renderDebugInfo({IA: {httpStatus: 200}, IL: {error: '超时'}});
check('场景B按州分组的形式(多个key)也应该正常工作', bMulti.includes('200') && bMulti.includes('超时'));

// ===================== 测试3：★核心修复——场景C兜底，自定义debug形状不再显示空壳 =====================
const c1 = renderDebugInfo({
  stage: "连只含'grain'这个词的报告都一个没找到",
  totalReportsInCatalog: 1051,
  sampleReportEntries: [{name: 'test1'}, {name: 'test2'}],
});
check('★场景C应该能看到stage文字内容', c1.includes('grain'));
check('★场景C应该能看到totalReportsInCatalog数值', c1.includes('1051'));
check('★场景C应该能看到sampleReportEntries数组内容(不是空壳)', c1.includes('test1') && c1.includes('test2'));
check('★场景C标题下面不应该是空的——之前的bug是有标题但内容完全空白', c1.length > 200);

// 出口检验实际会遇到的另一种debug形状：候选清单场景
const c2 = renderDebugInfo({
  stage: "目录里匹配到多个候选报告，无法自动确定唯一slug",
  candidates: [{slug_id: '100', report_name: 'Report A'}, {slug_id: '200', report_name: 'Report B'}],
});
check('★候选清单这种debug形状也应该能看到完整内容', c2.includes('Report A') && c2.includes('Report B') && c2.includes('100'));

// ===================== 测试4：空debug应该返回空字符串，不报错 =====================
check('debug为null时应该返回空字符串', renderDebugInfo(null) === '');
check('debug为undefined时应该返回空字符串', renderDebugInfo(undefined) === '');

H.printSummary();
