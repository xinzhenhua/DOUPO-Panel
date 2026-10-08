// ============================================================================
// 原手动指标 → 自动抓取卡片：覆盖/失败保留/过期排除/异常拦截/手动修正/卡片结构
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
window._selectedContract = 'sep';
const AUTO_INDICATORS = window._autoIndicators, AUTO_BY_KEY = window._autoByKey;

const dayStr = (daysAgo)=> new Date(Date.now() - daysAgo*86400000).toISOString().slice(0,10);
function resetKey(key){
  const cfg = AUTO_BY_KEY[key];
  makeEl(cfg.inputId).value = ''; makeEl('ai_'+key).innerHTML = ''; makeEl('badge_'+key); makeEl('alert_'+key); makeEl('ind_'+key);
  makeEl('alertContent');
  window._indState[key] = {};
}

// ===================== 1. 卡片骨架：10张卡，都有"查看详情/手动修正"，没有"采用"按钮 =====================
const hosts = {'cards-supply': {html:''}, 'cards-demand': {html:''}};
Object.keys(hosts).forEach(id=>{ const el = makeEl(id); el.insertAdjacentHTML = (pos, h)=>{ hosts[id].html += h; }; });
buildIndicatorCards();
const allHtml = hosts['cards-supply'].html + hosts['cards-demand'].html;
check('★一共生成12张指标卡片(含国内豆粕库消比、饲料企业豆粕库存天数)', (allHtml.match(/class="card" id="card_/g)||[]).length === 12);
check('★供应区7张(开机率/库存/库消比/基差/到港/进口/国储)、需求区5张(猪粮比/能繁/肉鸡/饲料库存天数/豆菜粕价差)',
  (hosts['cards-supply'].html.match(/id="card_/g)||[]).length === 7 && (hosts['cards-demand'].html.match(/id="card_/g)||[]).length === 5);
check('★每张卡片都有"查看详情 / 手动修正"折叠区', (allHtml.match(/查看详情 \/ 手动修正/g)||[]).length === 12);
check('★每张卡片都有常驻的结论框容器(alert_xxx)和状态徽标(badge_xxx)', AUTO_INDICATORS.every(c=>allHtml.includes(`id="alert_${c.key}"`) && allHtml.includes(`id="badge_${c.key}"`)));
check('★手动输入框放在折叠区里(m_xxx全部存在)', AUTO_INDICATORS.every(c=>allHtml.includes(`id="${c.inputId}"`)));
check('★页面上不再有"采用"按钮', !allHtml.includes('采用'));
check('★关税指标已彻底移除', !allHtml.includes('m_tariff') && !allHtml.includes('关税'));
check('输入框允许小数(step=any)', allHtml.includes('step="any"'));

// ===================== 2. 抓取成功：直接覆盖，同时清掉旧的手动修正 =====================
resetKey('crush');
makeEl('m_crush').value = '55.5';   // 之前手动改过/保存过
window._syncedData = {mysteelCrushRate:{available:true, value:69.98, date:dayStr(2)}};
refreshMysteelCrushRate();
check('★抓取成功时直接覆盖输入框', makeEl('m_crush').value == '69.98');
check('★徽标显示"自动"和数据日期', makeEl('badge_crush').textContent.includes('自动') && makeEl('badge_crush').textContent.includes(dayStr(2)) && makeEl('badge_crush').className.includes('badge-auto'));
check('★结论框显示偏空说明(69.98>60)', makeEl('alert_crush').innerHTML.includes('alert-box bear') && makeEl('alert_crush').innerHTML.includes('偏空'));
check('详情里显示自动抓取来源', makeEl('ai_crush').innerHTML.includes('自动抓取(Mysteel)') && makeEl('ai_crush').innerHTML.includes('69.98%'));

// ===================== 3. 抓取失败：不清空保存过的手动值；徽标如实说明 =====================
resetKey('stock');
makeEl('m_stock').value = '80';
window._syncedData = {mysteelMealStock:{available:false, reason:'搜索结果为空(测试)'}};
refreshMysteelMealStock();
check('★失败时保留保存过的手动值', makeEl('m_stock').value === '80');
check('★徽标提示"沿用你保存的值(自动抓取失败)"', makeEl('badge_stock').textContent.includes('沿用你保存的值') && makeEl('badge_stock').className.includes('badge-manual'));
check('★详情里显示失败原因', makeEl('ai_stock').innerHTML.includes('搜索结果为空(测试)'));
check('★保存的手动值仍然参与评分(结论框显示80万吨→偏空)', makeEl('alert_stock').innerHTML.includes('库存80万吨'));

resetKey('stock');
window._syncedData = {mysteelMealStock:{available:false, reason:'接口无返回'}};
refreshMysteelMealStock();
check('★失败且没有保存值：徽标显示"抓取失败"，结论框显示暂无数据', makeEl('badge_stock').textContent.includes('抓取失败') && makeEl('alert_stock').innerHTML.includes('暂无数据') && makeEl('alert_stock').innerHTML.includes('接口无返回'));

// ===================== 4. 数据过期：显示但不计分 =====================
resetKey('basis');
window._syncedData = {spotBasis:{available:true, value:-100, spot:3300, domSymbol:'M2701', domPrice:3400, usedFallback:false, date:dayStr(20)}};   // 基差日度，7天算过期
refreshMysteelBasis();
check('★过期数据照样显示数值', makeEl('m_basis').value == '-100');
check('★徽标标出"数据过期"并说明不计分(具体错过几个交易日写在详情里)', makeEl('badge_basis').textContent.includes('数据过期') && makeEl('badge_basis').textContent.includes('不计分') && makeEl('ai_basis').innerHTML.includes('错过') && makeEl('ai_basis').innerHTML.includes('个大商所交易日'));
check('★结论框说明不参与综合评分', makeEl('alert_basis').innerHTML.includes('不参与综合评分'));
check('★过期数据的信号被排除(市场结构卡里现货基差是"无信号"格，不是偏空；v97起基差在市场结构卡)', /sd-cell sd-empty">现货基差/.test(makeEl('structureContent').innerHTML));

resetKey('basis');
window._syncedData = {spotBasis:{available:true, value:-100, spot:3300, domSymbol:'M2701', domPrice:3400, usedFallback:false, date:dayStr(3)}};
refreshMysteelBasis();
check('★新鲜数据参与评分(市场结构卡里现货基差是偏空格)', /sd-cell sd-neg">现货基差/.test(makeEl('structureContent').innerHTML));

// ===================== 5. 数值荒谬：不填入、不清掉手动值 =====================
resetKey('crush');
makeEl('m_crush').value = '50';
window._syncedData = {mysteelCrushRate:{available:true, value:6998, date:dayStr(1)}};
refreshMysteelCrushRate();
check('★荒谬数值不覆盖手动值', makeEl('m_crush').value === '50');
check('★徽标提示数值异常已忽略', makeEl('badge_crush').textContent.includes('数值异常'));

// ===================== 6. 旧版后端数据(能繁母猪没有季度信息)：不采用 =====================
resetKey('sows');
window._syncedData = {sowInventory:{available:true, value:3990, date:'2025年10月'}};
refreshSowInventory();
check('★旧版数据不填入', makeEl('m_sows').value === '');
check('★徽标提示旧版数据已忽略', makeEl('badge_sows').textContent.includes('旧版'));

// ===================== 7. 手动修正：立即生效、徽标提示、存储只存手改值 =====================
const store = {};
global.localStorage = { getItem:(k)=> k==='soymeal_manual_v2' ? JSON.stringify(store) : null,
  setItem:(k,v)=>{ if(k==='soymeal_manual_v2'){ Object.keys(store).forEach(x=>delete store[x]); Object.assign(store, JSON.parse(v)); } }, removeItem(){} };
resetKey('crush');
window._syncedData = {mysteelCrushRate:{available:true, value:69.98, date:dayStr(1)}};
refreshMysteelCrushRate();
makeEl('m_crush').value = '38';
onManualEdit('crush');
check('★手动修正后徽标显示"手动修正"并带上自动值', makeEl('badge_crush').textContent.includes('手动修正') && makeEl('badge_crush').textContent.includes('69.98'));
check('★手动修正立即重新计算(38<40→偏多)', makeEl('alert_crush').innerHTML.includes('alert-box bull'));
check('★只存手动改过的值，自动值不存', store.m_crush === '38' && Object.keys(store).length === 1);
makeEl('m_crush').value = '';
onManualEdit('crush');
check('★清空手动值后恢复"自动"状态，并删除保存的手动值', makeEl('badge_crush').textContent.includes('自动') && store.m_crush === undefined);

// 自动抓取成功时，清掉之前保存的手动值
store.m_stock = '99';
resetKey('stock');
window._syncedData = {mysteelMealStock:{available:true, value:65.32, date:dayStr(3)}};
refreshMysteelMealStock();
check('★自动抓取成功后，之前保存的手动值被清掉(下次打开不会再冒出来)', store.m_stock === undefined && makeEl('m_stock').value == '65.32');

// 页面刷新：旧版'soymeal_manual'(存了全部输入框)被丢弃，不会当成手动修正读回来
let removed = [];
global.localStorage = { getItem:(k)=> k==='soymeal_manual' ? JSON.stringify({m_crush:'12'}) : null, setItem(){}, removeItem:(k)=>removed.push(k) };
resetKey('crush');
loadManual();
check('★旧版存储的输入框值不会被当成手动修正读回来', makeEl('m_crush').value === '' && removed.includes('soymeal_manual'));

// ===================== 8. 其它：同步数据还没回来不报错 =====================
delete window._syncedData;
let ok = true; try { AUTO_INDICATORS.forEach(c=>refreshAutoIndicator(c.key)); } catch(e){ ok = false; }
check('★window._syncedData为空时12个指标刷新都不报错', ok);

H.printSummary();
