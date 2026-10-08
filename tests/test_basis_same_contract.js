const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
// v101.9：现货基差只看"当前主力合约自己历史"里的分位（用户2026-10-08规定，所有换月断层同此处理）。
// 旧规则"正数偏多、负数偏空"在主力为5月/1月合约时基差天然+300~+450，几乎永远偏多——是合约月份决定了符号，不是供需。
const SC = (o)=>Object.assign({contract:'m2701', n:43, minN:20, percentile:50, median:-50, min:-123, max:52, since:'2026-08-03', why:''}, o||{});
function setHist(sc){ window._indState.basis = {history:{n:745, percentile:60, sameContract:sc}}; }
const R = ()=>window._manualRules.basis(-50);

check('常量：≥80偏多、≤20偏空、最少20个样本', window._basisSignal.hi===80 && window._basisSignal.lo===20 && window._basisSignal.minN===20);
setHist(SC({percentile:80}));  let r = R();
check('★边界：同合约内80%分位 → 偏多(+1)', r[0]===1);
setHist(SC({percentile:79.9})); r = R();
check('★边界：79.9% → 中性(0)', r[0]===0);
setHist(SC({percentile:20}));  r = R();
check('★边界：20% → 偏空(-1)', r[0]===-1);
setHist(SC({percentile:20.1})); r = R();
check('★边界：20.1% → 中性(0)', r[0]===0);
setHist(SC({percentile:95}));  r = R();
check('★关键：基差本身是+400(5月合约的常态)但在自己合约里只是15%分位 → 偏空，不是"正数偏多"', (()=>{ setHist(SC({contract:'m2605', percentile:15})); return window._manualRules.basis(400)[0]===-1; })());
check('★关键：基差是-100(负数)但在自己合约里是90%分位 → 偏多，不是"负数偏空"', (()=>{ setHist(SC({contract:'m2609', percentile:90})); return window._manualRules.basis(-100)[0]===1; })());
check('说明里要写出合约、样本数和分位', (()=>{ setHist(SC({contract:'m2609', n:89, percentile:90})); const t = window._manualRules.basis(-100)[1]; return t.includes('M2609') && t.includes('89') && t.includes('90%'); })());

// 不计分的情形：返回 [null, 原因]
check('★样本不足(19个)：不计分，说明原因，不退回正负号规则', (()=>{ setHist(SC({n:19, percentile:null, why:'m2701作为主力合约的历史只有19个交易日'})); const x = window._manualRules.basis(100); return x[0]===null && x[1].includes('19'); })());
check('★没有同合约摘要(旧版latest.json)：不计分，不退回正负号规则', (()=>{ window._indState.basis = {history:{n:745, percentile:60}}; return window._manualRules.basis(100)[0]===null; })());
check('★完全没有历史：不计分', (()=>{ window._indState.basis = {history:null}; return window._manualRules.basis(100)[0]===null; })());
check('★样本数够但 percentile 为空：不计分', (()=>{ setHist(SC({n:50, percentile:null})); return window._manualRules.basis(100)[0]===null; })());
check('★前端也再核对一次最少样本数：n=19 但后端误给了分位 → 仍不计分', (()=>{ setHist(SC({n:19, percentile:99})); return window._manualRules.basis(100)[0]===null; })());

// 端到端：同步数据带 history.sameContract → 刷新后规则读到它
function reset(){ makeEl('m_basis').value=''; makeEl('ai_basis'); makeEl('ind_basis'); }
reset();
window._syncedData = {generatedAt:new Date().toISOString(), spotBasis:{available:true, value:52, date:'2026-10-08', spot:3418, domSymbol:'m2701', domPrice:3366, siteBasis:52, consistent:true, usedFallback:false, fallbackDays:0,
  history:{n:745, percentile:70, sameContract:SC({percentile:92, n:43})}}};
refreshMysteelBasis();
check('★端到端：刷新后状态里带着同合约摘要', window._indState.basis && window._indState.basis.history && window._indState.basis.history.sameContract.percentile===92);
check('★端到端：92%分位 → 规则给偏多', window._manualRules.basis(52)[0]===1);
check('卡片的详情里写明"只在当前主力合约内部比"', (makeEl('ai_basis').innerHTML||'').includes('当前主力合约'));
H.printSummary();
