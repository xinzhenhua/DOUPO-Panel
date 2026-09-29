const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
function reset(){ makeEl('m_basis').value=''; makeEl('ai_basis'); makeEl('ind_basis'); }

// 欄位为空：自动填入，标出代表城市
reset();
window._syncedData = {generatedAt:new Date().toISOString(), mysteelBasis:{available:true, value:-100, city:'防城港', date:'2026-09-28', latestArticleDate:'2026-09-28', usedFallback:false, fallbackDays:0}};
refreshMysteelBasis();
check('★欄位是空的时应该自动填入基差-100', makeEl('m_basis').value == '-100');
check('★提示区应该标出用的是哪个代表城市(防城港)', makeEl('ai_basis').innerHTML.includes('防城港·沿海代表'));
check('提示区应该显示日期', makeEl('ai_basis').innerHTML.includes('2026-09-28'));
check('★没有触发回退时不应该出现滞后警告', !makeEl('ai_basis').innerHTML.includes('没能解析出确切值'));

// 触发回退：应该显示滞后提示
reset();
window._syncedData = {generatedAt:new Date().toISOString(), mysteelBasis:{available:true, value:-110, city:'东莞', date:'2026-09-20', latestArticleDate:'2026-09-22', usedFallback:true, fallbackDays:2}};
refreshMysteelBasis();
check('★触发回退时应该诚实提示最新一篇解析失败、用的是几天前的数据', makeEl('ai_basis').innerHTML.includes('最新一篇(2026-09-22)没能解析出确切值') && makeEl('ai_basis').innerHTML.includes('2天前的数据'));

// 已有值：抓取成功直接覆盖
reset(); makeEl('m_basis').value = '50';
window._syncedData = {generatedAt:new Date().toISOString(), mysteelBasis:{available:true, value:-100, city:'日照', date:'2026-09-28', usedFallback:false}};
refreshMysteelBasis();
check('★抓取成功时直接覆盖已有值(50→-100)', makeEl('m_basis').value == '-100');

// 失败：显示明确原因+debug
reset(); makeEl('ai_basis').className = 'ai-suggest unavailable'; makeEl('ai_basis').innerHTML = '💡 尚未粘贴数据';
window._syncedData = {generatedAt:new Date().toISOString(), mysteelBasis:{available:false, reason:'最近能解析出基差的一篇也是10天前的，超过7天的新鲜度限制(测试)', debug:{attempted:['2026-09-22','2026-09-21']}}};
refreshMysteelBasis();
check('★失败时应该替换掉默认的"尚未粘贴数据"', !makeEl('ai_basis').innerHTML.includes('尚未粘贴数据'));
check('★失败时应该显示明确原因和诊断信息', makeEl('ai_basis').innerHTML.includes('新鲜度限制') && makeEl('ai_basis').innerHTML.includes('诊断信息'));

// 荒谬数值：不填入、不显示采用
reset();
window._syncedData = {generatedAt:new Date().toISOString(), mysteelBasis:{available:true, value:-800, city:'日照', date:'2026-09-28', usedFallback:false}};
refreshMysteelBasis();
check('★荒谬数值(-800元/吨)不能自动填入', makeEl('m_basis').value === '');
check('★荒谬数值不能显示采用按钮，要显示警告', !makeEl('ai_basis').innerHTML.includes('采用') && makeEl('ai_basis').innerHTML.includes('超出合理范围'));

// 正值(北方内陆场景，非负)不受影响也能填入(基差本身可正可负)
reset();
window._syncedData = {generatedAt:new Date().toISOString(), mysteelBasis:{available:true, value:150, city:'日照', date:'2026-09-28', usedFallback:false}};
refreshMysteelBasis();
check('正值基差也应该能正常自动填入(基差本身可正可负)', makeEl('m_basis').value == '150');

delete window._syncedData;
try { refreshMysteelBasis(); check('★window._syncedData为空时不应该报错', true); } catch(e){ check('★window._syncedData为空时不应该报错', false); }
H.printSummary();
