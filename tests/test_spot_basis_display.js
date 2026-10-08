const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
// v101.7：现货基差改用 AKShare(生意社现货价 − 主力合约结算价，后端自己算)，不再用 Mysteel。原 test_mysteel_basis_display.js 的每个行为(自动填入/标明来源/回退警告/失败诊断/荒谬值拦截/正值/无数据不报错)
// 在新数据源下仍然成立，改写成 spotBasis 版本；荒谬值的界限从 ±500 变成 ±1000(SANITY_RANGES.spotBasis)；新增：站点基差不一致的警告、当天没出的回退文案。
function reset(){ makeEl('m_basis').value=''; makeEl('ai_basis'); makeEl('ind_basis'); }
const SB = (o)=>Object.assign({available:true, value:-72, date:'2026-09-28', spot:3300, domSymbol:'m2701', domPrice:3372, siteBasis:-72, consistent:true, usedFallback:false, fallbackDays:0, spotDefinition:'生意社现货价(口径未明确)'}, o||{});

// 栏位为空：自动填入，标出现货价和主力合约
reset();
window._syncedData = {generatedAt:new Date().toISOString(), spotBasis:SB()};
refreshMysteelBasis();
check('★栏位是空的时应该自动填入基差-72', makeEl('m_basis').value == '-72');
check('★提示区应该标出是怎么算的(现货3300 − 主力M2701 3372)，akshare 给的小写 m2701 显示成大写 M2701', makeEl('ai_basis').innerHTML.includes('现货3300') && makeEl('ai_basis').innerHTML.includes('主力M2701') && !makeEl('ai_basis').innerHTML.includes('m2701') && makeEl('ai_basis').innerHTML.includes('3372'));
check('★合约代码和结算价之间要有分隔(之前写成了"主力M27013372"，读起来像一个数)：显示"主力M2701的3372"', makeEl('ai_basis').innerHTML.includes('主力M2701的3372') && !makeEl('ai_basis').innerHTML.includes('M27013372'));
check('提示区应该显示日期', makeEl('ai_basis').innerHTML.includes('2026-09-28'));
check('★提示区应该写明现货价口径(文档没写明，不假装确定)', makeEl('ai_basis').innerHTML.includes('口径未明确'));
check('★来源是生意社，不再是 Mysteel', !makeEl('ai_basis').innerHTML.includes('沿海代表') && !makeEl('ai_basis').innerHTML.includes('Mysteel'));
check('★没有触发回退、站点基差一致时不应该出现警告', !makeEl('ai_basis').innerHTML.includes('还没出') && !makeEl('ai_basis').innerHTML.includes('不一致'));

// 当天数据没出：用了前几天的交易日，要诚实说
reset();
window._syncedData = {generatedAt:new Date().toISOString(), spotBasis:SB({value:-70, date:'2026-09-30', usedFallback:true, fallbackDays:8})};
refreshMysteelBasis();
check('★回退时应该诚实提示当天的数据还没出、用的是8天前的交易日(2026-09-30)', makeEl('ai_basis').innerHTML.includes('还没出') && makeEl('ai_basis').innerHTML.includes('8天前') && makeEl('ai_basis').innerHTML.includes('2026-09-30'));

// 站点自己给的基差与自算不一致：提示，取自算值
reset();
window._syncedData = {generatedAt:new Date().toISOString(), spotBasis:SB({value:-72, siteBasis:-5, consistent:false})};
refreshMysteelBasis();
check('★站点基差(-5)与自算(-72)不一致：提示出两个数，说明取自算值', makeEl('ai_basis').innerHTML.includes('不一致') && makeEl('ai_basis').innerHTML.includes('-5') && makeEl('ai_basis').innerHTML.includes('自算'));
check('★不一致时填入的仍是自算值-72(不是站点的-5)', makeEl('m_basis').value == '-72');

// 已有值：抓取成功直接覆盖
reset(); makeEl('m_basis').value = '50';
window._syncedData = {generatedAt:new Date().toISOString(), spotBasis:SB({value:-100, spot:3272, domPrice:3372})};
refreshMysteelBasis();
check('★抓取成功时直接覆盖已有值(50→-100)', makeEl('m_basis').value == '-100');

// 失败：显示明确原因+debug
reset(); makeEl('ai_basis').className = 'ai-suggest unavailable'; makeEl('ai_basis').innerHTML = '💡 尚未粘贴数据';
window._syncedData = {generatedAt:new Date().toISOString(), spotBasis:{available:false, reason:'最近4个交易日都没取到豆粕现货基差(生意社)(测试)', debug:{attempted:['2026-09-30: 没有返回数据','2026-09-29: 超时']}}};
refreshMysteelBasis();
check('★失败时应该替换掉默认的"尚未粘贴数据"', !makeEl('ai_basis').innerHTML.includes('尚未粘贴数据'));
check('★失败时应该显示明确原因和诊断信息', makeEl('ai_basis').innerHTML.includes('没取到豆粕现货基差') && makeEl('ai_basis').innerHTML.includes('诊断信息'));

// 荒谬数值：不填入、不显示采用(新范围±1000，所以用-1500)
reset();
window._syncedData = {generatedAt:new Date().toISOString(), spotBasis:SB({value:-1500, spot:3000, domPrice:4500})};
refreshMysteelBasis();
check('★荒谬数值(-1500元/吨，超过±1000)不能自动填入', makeEl('m_basis').value === '');
check('★荒谬数值不能显示采用按钮，要显示警告', !makeEl('ai_basis').innerHTML.includes('采用') && makeEl('ai_basis').innerHTML.includes('超出合理范围'));

// 旧范围±500之外、新范围±1000之内的值现在可以通过(全国综合现货对主力合约的基差本来就可能更大)
reset();
window._syncedData = {generatedAt:new Date().toISOString(), spotBasis:SB({value:-800, spot:3000, domPrice:3800})};
refreshMysteelBasis();
check('★-800 在新范围内(旧Mysteel沿海代表范围±500会拦下)：可以填入', makeEl('m_basis').value == '-800');

// 正值(现货高于期货)也能正常填入
reset();
window._syncedData = {generatedAt:new Date().toISOString(), spotBasis:SB({value:150, spot:3522, domPrice:3372})};
refreshMysteelBasis();
check('正值基差(现货高于期货)也应该能正常自动填入', makeEl('m_basis').value == '150');

delete window._syncedData;
try { refreshMysteelBasis(); check('★window._syncedData为空时不应该报错', true); } catch(e){ check('★window._syncedData为空时不应该报错', false); }
H.printSummary();
