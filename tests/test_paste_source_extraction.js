const H = require('./test_helpers');
const { check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：★核心修复——不在硬编清单里的机构名称也能正确解析 =====================
const r1 = parsePastedData('油厂开机率(%) 69.98% 2026年9月22日 我的钢铁网');
check('★"我的钢铁网"这个不在旧清单里的机构名称，现在应该能正确解析为来源', r1.m_crush && r1.m_crush.source === '我的钢铁网');

const r2 = parsePastedData('猪粮比 8.2 2026年9月20日 卓创资讯');
check('★"卓创资讯"这个不在旧清单里的机构名称，也应该能正确解析', r2.m_hogratio && r2.m_hogratio.source === '卓创资讯');

// ===================== 测试2：既有清单里的机构名称，确认没有退步 =====================
const r3 = parsePastedData('现货基差 -66 2026年9月21日 Mysteel');
check('既有清单里的"Mysteel"应该依然能正确解析，没有退步', r3.m_basis && r3.m_basis.source === 'Mysteel');

// ===================== 测试3：数值后紧跟单位文字+说明括号，两层都要跳过 =====================
const r4 = parsePastedData('油厂开机率(%) 65.73%（全国动态全样本油厂） 2026年7月7日 Mysteel');
check('★数值后紧跟单位符号(%)和说明括号，都应该被跳过，只留下真正的来源', r4.m_crush && r4.m_crush.source === 'Mysteel');

const r5 = parsePastedData('豆粕商业库存(万吨) 68万吨（全国主要油厂） 2026年7月3日 国家粮油信息中心');
check('★数值后紧跟单位文字(万吨)和说明括号，都应该被跳过', r5.m_stock && r5.m_stock.source === '国家粮油信息中心');

// ===================== 测试4：markdown表格格式(用|分隔)下的日期+来源解析 =====================
const tableInput = `
| 指标 | 数据 | 日期 | 来源及备注 |
|---|---|---|---|
| 油厂开机率 | 69.98 | 2026年9月22日 | 我的钢铁网,全国动态全样本油厂开机率 |
| 豆粕商业库存 | 117.32 | 2026年9月22日 | 我的钢铁网,环比增加5.7% |
`;
const parsed = parsePastedData(tableInput);
check('★表格格式下，开机率的数值应该正确解析', parsed.m_crush && parsed.m_crush.value === 69.98);
check('★表格格式下，开机率的日期应该正确解析(不是null)', parsed.m_crush && parsed.m_crush.date === '2026-09-22');
check('★表格格式下，开机率的来源应该正确解析(不是null)，包含机构名和备注', parsed.m_crush && parsed.m_crush.source && parsed.m_crush.source.includes('我的钢铁网'));
check('表格格式下，商业库存也应该正确解析出全部三项', 
  parsed.m_stock && parsed.m_stock.value === 117.32 && parsed.m_stock.date === '2026-09-22' && parsed.m_stock.source);

// ===================== 测试5：完全没有来源信息时，source应该保持null，不是空字符串 =====================
const r6 = parsePastedData('猪粮比 8.2 2026年9月20日');
check('★没有来源信息时，source应该是null，不是空字符串或者错误内容', r6.m_hogratio && r6.m_hogratio.source === null);

// ===================== 测试6：一键复制的提示词应该跟用户指定的最新版本完全一致 =====================
const rawHtml = require('fs').readFileSync('/home/claude/soymeal-dashboard/index.html', 'utf8');
const promptMatch = rawHtml.match(/const PASTE_PROMPT_TEMPLATE = `([\s\S]*?)`;/);
check('★提示词模板应该能提取到', promptMatch !== null);
const promptText = promptMatch ? promptMatch[1] : '';
check('★提示词应该包含"纯数值,不能缺失"这个新要求', promptText.includes('纯数值,不能缺失'));
check('★提示词应该包含"来源及备注(文字描述)"这个新要求', promptText.includes('来源及备注(文字描述)'));
check('★提示词应该包含"必须有数据列(数据列不能包含任何文字)"这个新要求', promptText.includes('必须有数据列(数据列不能包含任何文字)'));
check('★提示词应该包含"没有数据,就往前一个最近日期找数据"这个新要求', promptText.includes('没有数据,就往前一个最近日期找数据'));
check('提示词的标点符号应该是英文逗号(用户提供的确切版本)', !promptText.includes('，') && promptText.includes(','));

H.printSummary();
