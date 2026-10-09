const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
// v101.12 肉鸡兜底单票：发改委缺失/失败/过期/数值不合理时，同一票位改用 Mysteel 白羽肉鸡养殖利润；正常时完全不动；永远只有一票。
function reset(){ makeEl('m_poultry').value = ''; makeEl('ai_poultry'); makeEl('ind_poultry'); makeEl('badge_poultry'); window._indState = {}; }
const dayStr = (n)=>{ const d=new Date(Date.now()-n*86400000); const bj=new Date(d.getTime()+8*3600000); return bj.toISOString().slice(0,10); };
const NP = (o)=>Object.assign({available:true, value:-4.1, date:dayStr(3), ratio:1.79, balance:2.25, weekLabel:'2026年9月第4周', formulaCheckOk:true, formulaCheckValue:-4.1}, o||{});
const MY = (o)=>Object.assign({available:true, value:-4.18, date:dayStr(2), source:'Mysteel文章(白羽肉鸡养殖利润)'}, o||{});
const run = (ndrc, my)=>{ reset(); window._syncedData = {generatedAt:new Date().toISOString(), ndrcPoultryProfit:ndrc, mysteelPoultryProfit:my}; refreshMysteelPoultryProfit(); return {html:makeEl('ai_poultry').innerHTML, v:makeEl('m_poultry').value, st:window._indState.poultry}; };

// 1) 发改委正常 → 用发改委，Mysteel 完全不出现
let r = run(NP(), MY({value:3.3}));
check('★发改委正常：用发改委的值(-4.1)，不用 Mysteel(3.3)', r.v == '-4.1' && !r.html.includes('兜底') && !r.st.fallbackWhy);
check('发改委正常时不打折(不因为兜底存在而降权)', qualityOf('poultry').m === 1);

// 2) 发改委抓取失败 → Mysteel 顶替
r = run({available:false, reason:'发改委文章列表取不到(测试)'}, MY());
check('★发改委失败：改用 Mysteel(-4.18)', r.v == '-4.18' && r.html.includes('兜底来源') && r.html.includes('Mysteel白羽肉鸡养殖利润（兜底）'));
check('★兜底说明里写明了主来源失败的原因', r.html.includes('发改委文章列表取不到(测试)'));
check('★兜底票权×0.5', qualityOf('poultry').m === 0.5);
check('兜底口径写明与发改委不同、同一票位不叠加', r.html.includes('口径不同') && r.html.includes('不叠加'));

// 3) 发改委过期(stale) → Mysteel 顶替；而 Mysteel 也过期 → 不顶替，保持原来"显示但不计分"
r = run(NP({date:dayStr(60)}), MY());
check('★发改委过期：改用 Mysteel', r.v == '-4.18' && r.st.fallbackWhy.includes('已过期'));
r = run(NP({date:dayStr(60)}), MY({date:dayStr(60)}));
check('★两个都过期：不顶替，保持发改委的过期显示(不计分)', r.v == '-4.1' && r.html.includes('数据已过期') && !r.st.fallbackWhy);

// 4) 发改委"晚了一期"(late)仍用发改委，不兜底
r = run(NP({date:dayStr(12)}), MY());
check('★发改委晚了一期(late)：仍用发改委(降权)，不兜底', r.v == '-4.1' && !r.st.fallbackWhy);

// 5) 数值不合理 → 兜底
r = run(NP({value:99}), MY());
check('★发改委数值不合理(99)：改用 Mysteel', r.v == '-4.18' && r.st.fallbackWhy.includes('数值不合理'));
r = run({available:false, reason:'x'}, MY({value:99}));
check('★兜底来源自己数值不合理(99)：不采用，卡片显示抓取失败', r.v === '' && r.html.includes('抓取失败'));

// 6) 两个都不可用 → 失败文案
r = run({available:false, reason:'发改委失败'}, {available:false, reason:'mysteel失败'});
check('两个都失败：显示发改委的失败原因，不报错', r.html.includes('发改委失败') && r.v === '');
r = run({available:false, reason:'发改委失败'}, undefined);
check('没有 mysteelPoultryProfit 字段(后端没抓)：照旧显示发改委失败', r.html.includes('发改委失败'));

// 7) 计分：兜底值走同一条规则、同一个票位，只出现一次
reset(); window._syncedData = {generatedAt:new Date().toISOString(), ndrcPoultryProfit:{available:false, reason:'x'}, mysteelPoultryProfit:MY({value:2.0})};
refreshMysteelPoultryProfit();
['m_crush','m_stock','m_arrival','m_hogratio','m_import'].forEach(id=>makeEl(id));
makeEl('alertContent'); updateOverallAlert();
const html = makeEl('alertContent').innerHTML;
check('★兜底值 2.0(>1.5)判偏多，肉鸡养殖利润这一票只出现一次', (html.match(/sd-cell sd-pos">肉鸡养殖利润/g)||[]).length === 1);
H.printSummary();
