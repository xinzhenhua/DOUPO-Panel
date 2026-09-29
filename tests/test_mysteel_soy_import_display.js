const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
function reset(){ makeEl('m_import').value=''; makeEl('ai_import'); makeEl('ind_import'); }

// 欄位为空：自动填入，并标出是哪个月
reset();
window._syncedData = {generatedAt:new Date().toISOString(), mysteelSoyImport:{available:true, value:1214.14, monthLabel:'2026年8月', date:'2026-09-09'}};
refreshMysteelSoyImport();
check('★欄位是空的时应该自动填入进口量', makeEl('m_import').value == '1214.14');
check('★提示区应该标出是哪个月的数(2026年8月)', makeEl('ai_import').innerHTML.includes('2026年8月'));
check('提示区应该显示数值和万吨单位', makeEl('ai_import').innerHTML.includes('1214.14万吨'));
check('提示区应该显示文章发布日期', makeEl('ai_import').innerHTML.includes('2026-09-09'));

// 已有值：抓取成功直接覆盖
reset(); makeEl('m_import').value = '1000';
refreshMysteelSoyImport();
check('★抓取成功时直接覆盖已有值(1000→1214.14)', makeEl('m_import').value == '1214.14');
check('提示区显示抓取到的值', makeEl('ai_import').innerHTML.includes('1214.14'));

// 失败：显示明确原因+debug，不留"尚未粘贴数据"
reset(); makeEl('ai_import').className = 'ai-suggest unavailable'; makeEl('ai_import').innerHTML = '💡 尚未粘贴数据';
window._syncedData = {generatedAt:new Date().toISOString(), mysteelSoyImport:{available:false, reason:'只找到了较旧的月度数据(测试)', debug:{monthsSeen:['2026年6月']}}};
refreshMysteelSoyImport();
check('★失败时应该替换掉默认的"尚未粘贴数据"', !makeEl('ai_import').innerHTML.includes('尚未粘贴数据'));
check('★失败时应该显示明确原因和诊断信息', makeEl('ai_import').innerHTML.includes('较旧的月度数据') && makeEl('ai_import').innerHTML.includes('诊断信息'));

// 荒谬数值：不填入、不显示采用
reset();
window._syncedData = {generatedAt:new Date().toISOString(), mysteelSoyImport:{available:true, value:12, monthLabel:'2026年8月', date:'2026-09-09'}};
refreshMysteelSoyImport();
check('★荒谬数值(12万吨)不能自动填入', makeEl('m_import').value === '');
check('★荒谬数值不能显示采用按钮，要显示警告', !makeEl('ai_import').innerHTML.includes('采用') && makeEl('ai_import').innerHTML.includes('超出合理范围'));

// 没有monthLabel(老数据)时不能出现undefined/null
reset();
window._syncedData = {generatedAt:new Date().toISOString(), mysteelSoyImport:{available:true, value:1214.14, date:'2026-09-09'}};
refreshMysteelSoyImport();
check('★没有monthLabel时不应该出现undefined/null', !makeEl('ai_import').innerHTML.includes('undefined') && !makeEl('ai_import').innerHTML.includes('null'));

// window._syncedData为空不报错
delete window._syncedData;
try { refreshMysteelSoyImport(); check('★window._syncedData为空时不应该报错', true); } catch(e){ check('★window._syncedData为空时不应该报错', false); }
H.printSummary();
