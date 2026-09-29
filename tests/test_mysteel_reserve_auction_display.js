const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
function reset(){ makeEl('m_reserve').value=''; makeEl('ai_reserve'); makeEl('ind_reserve'); }
const latest = {available:true, value:51.43, auctionDate:'2026-09-28', ageDays:0, plannedWan:51.43, soldWan:19.17, soldRate:37.27,
  avgPrice:null, priceLow:4310, priceHigh:4390, priceKind:'底价~最高价',
  previous:{auctionDate:'2026-09-22', plannedWan:54.3, soldWan:33.87, soldRate:62.37, avgPrice:null}, date:'2026-09-28'};

// 欄位为空：自动填入的是计划拍卖量
reset();
window._syncedData = {generatedAt:new Date().toISOString(), mysteelReserveAuction:latest};
refreshMysteelReserveAuction();
check('★欄位是空的时应该自动填入计划拍卖量51.43', makeEl('m_reserve').value == '51.43');
check('★提示区应该标明这是"计划拍卖量"和拍卖日期', makeEl('ai_reserve').innerHTML.includes('计划拍卖量') && makeEl('ai_reserve').innerHTML.includes('2026-09-28'));
check('★提示区应该同时显示成交量和成交率(参考信息)', makeEl('ai_reserve').innerHTML.includes('成交19.17万吨') && makeEl('ai_reserve').innerHTML.includes('成交率37.27%'));
check('★提示区应该显示成交价格', makeEl('ai_reserve').innerHTML.includes('底价~最高价4310-4390元/吨'));
check('★提示区应该显示上一次拍卖的成交率，方便看趋势', makeEl('ai_reserve').innerHTML.includes('上一次(2026-09-22)') && makeEl('ai_reserve').innerHTML.includes('成交率62.37%'));
check('★不再有"采用"按钮', !makeEl('ai_reserve').innerHTML.includes('采用'));

// 有成交均价时显示成交均价
reset();
window._syncedData = {generatedAt:new Date().toISOString(), mysteelReserveAuction:Object.assign({}, latest, {avgPrice:4162.73, previous:null})};
refreshMysteelReserveAuction();
check('有成交均价时应该显示成交均价', makeEl('ai_reserve').innerHTML.includes('成交均价4162.73元/吨'));
check('★没有上一次拍卖时不应该出现undefined/null', !makeEl('ai_reserve').innerHTML.includes('undefined') && !makeEl('ai_reserve').innerHTML.includes('null'));

// 已有值：抓取成功直接覆盖
reset(); makeEl('m_reserve').value = '30';
window._syncedData = {generatedAt:new Date().toISOString(), mysteelReserveAuction:latest};
refreshMysteelReserveAuction();
check('★抓取成功时直接覆盖已有值(30→51.43)', makeEl('m_reserve').value == '51.43');
check('提示区显示抓取到的值', makeEl('ai_reserve').innerHTML.includes('51.43'));

// 失败：显示明确原因+debug
reset(); makeEl('ai_reserve').className = 'ai-suggest unavailable'; makeEl('ai_reserve').innerHTML = '💡 尚未粘贴数据';
window._syncedData = {generatedAt:new Date().toISOString(), mysteelReserveAuction:{available:false, reason:'最近一次拍卖是50天前，可能国储已暂停拍卖(测试)', debug:{latestAuctionDate:'2026-08-09'}}};
refreshMysteelReserveAuction();
check('★失败时应该替换掉默认的"尚未粘贴数据"', !makeEl('ai_reserve').innerHTML.includes('尚未粘贴数据'));
check('★失败时应该显示明确原因和诊断信息', makeEl('ai_reserve').innerHTML.includes('可能国储已暂停拍卖') && makeEl('ai_reserve').innerHTML.includes('诊断信息'));

// 荒谬数值：不填入、不显示采用
reset();
window._syncedData = {generatedAt:new Date().toISOString(), mysteelReserveAuction:Object.assign({}, latest, {value:5143})};
refreshMysteelReserveAuction();
check('★荒谬数值(5143万吨)不能自动填入', makeEl('m_reserve').value === '');
check('★荒谬数值不能显示采用按钮，要显示警告', !makeEl('ai_reserve').innerHTML.includes('采用') && makeEl('ai_reserve').innerHTML.includes('超出合理范围'));

// window._syncedData为空不报错
delete window._syncedData;
try { refreshMysteelReserveAuction(); check('★window._syncedData为空时不应该报错', true); } catch(e){ check('★window._syncedData为空时不应该报错', false); }
H.printSummary();
