// ============================================================================
// 三维度评分(供给/需求/市场结构) + 置信度 + 分歧提示
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
window._sdBalance.minN = 1e9;   // 本文件验证的是别的行为（阈值/排序/质量），期望值是按未均衡票权手算的；供需均衡的单元+集成测试见 test_sd_balance.js / test_sd_balance_integration.js
window._selectedContract = 'sep';
H.setMockedMonth(5);   // 5月：9月合约的作物票在"参与"档(×1)，票数好算；季节档位另见test_seasonal.js
const AUTO = window._autoIndicators;
const V = (label, side, signal, weight)=>({label, side, signal, weight: weight||1});

// ===================== 1. 纯函数：汇总/维度/分歧/置信度 =====================
let t = tallyVotes([V('a','supply',1,2), V('b','supply',-1,1), V('c','supply',0,1), V('d','supply',null,1)]);
check('★tallyVotes：无数据(null)的票不算个数也不占票权', t.n===3 && t.total===4 && t.weight===4);
check('★tallyVotes：票权加权分数=1×2-1×1+0=1，净倾向=1÷4=0.25', t.score===1 && t.ratio===0.25 && t.dir===1);
check('tallyVotes：多空票权分别统计', t.bullW===2 && t.bearW===1);
check('tallyVotes：全部无数据时净倾向为null，方向为null(不是中性)', (()=>{ const z = tallyVotes([V('a','supply',null)]); return z.ratio===null && z.dir===null && z.n===0; })());
check('方向门槛：0.22算偏多，0.21算中性，-0.22算偏空', dirOfRatio(0.22)===1 && dirOfRatio(0.21)===0 && dirOfRatio(-0.22)===-1 && dirOfRatio(null)===null);

const votesA = [V('作物','supply',-1), V('库消比','supply',-1,2), V('汇率','supply',0),
                V('出口','demand',1), V('猪粮比','demand',1), V('肉鸡','demand',0),
                V('基差','structure',-1)];
let dims = computeDimensions(votesA);
check('★维度拆分：供给端=(-1-2+0)÷4=-75%', dims.supply.ratio===-0.75 && dims.supply.n===3 && dims.supply.weight===4);
check('★维度拆分：需求端=(1+1+0)÷3=+67%', Math.abs(dims.demand.ratio-2/3)<1e-9 && dims.demand.dir===1);
check('★市场结构只有1项 → 标"样本少"(thin)', dims.structure.n===1 && dims.structure.thin===true && dims.supply.thin===false);
const ov = tallyVotes(votesA);
check('★不变式：三个维度的票权合计=总票权，分数合计=总分数(维度只是拆开看，不是另外加的指标)',
  ['supply','demand','structure'].reduce((a,k)=>a+dims[k].weight,0)===ov.weight && ['supply','demand','structure'].reduce((a,k)=>a+dims[k].score,0)===ov.score);
let dv = detectDivergence(dims);
check('★分歧：供给端偏空(-75%)+需求端偏多(+67%)，两个维度样本都够 → 分歧', !!dv && dv.bear.key==='supply' && dv.bull.key==='demand');
check('分歧：只有样本少的市场结构偏空、供给需求同向 → 不算分歧', detectDivergence(computeDimensions([V('a','supply',-1),V('b','supply',-1),V('c','demand',-1),V('d','demand',-1),V('e','structure',1)]))===null);
check('分歧：样本少的维度(1项)与另一维度相反 → 不算分歧(单个指标不足以构成"分歧")', detectDivergence(computeDimensions([V('a','supply',-1),V('b','supply',-1),V('c','structure',1)]))===null);
check('分歧：一侧偏空一侧只是中性 → 不算分歧', detectDivergence(computeDimensions([V('a','supply',-1),V('b','supply',-1),V('c','demand',0),V('d','demand',0)]))===null);

// 置信度：从高(2)往下扣
const mk = (nValid, nTotal, bullW, bearW, dvg)=>{
  const votes = []; for(let i=0;i<nTotal;i++) votes.push(V('x'+i,'supply', i<nValid?0:null));
  return computeConfidence(votes, {n:nValid, bullW, bearW}, dvg
    ? {a:{n:3,dir:-1,ratio:-0.5,name:'供给端'}, b:{n:3,dir:1,ratio:0.5,name:'需求端'}} : {a:{n:3,dir:-1,ratio:-0.5,name:'供给端'}, b:{n:3,dir:-1,ratio:-0.4,name:'需求端'}});
};
let c = mk(12,12, 1, 9, false);
check('★置信度：覆盖100%+一致性90%+无分歧 → 高', c.level===2 && c.label==='高' && c.reasons[0].includes('覆盖100%'));
c = mk(10,12, 1, 9, false);
check('★置信度：覆盖83%仍是高；覆盖75%(<80%)降为中', c.level===2 && mk(9,12,1,9,false).level===1 && mk(9,12,1,9,false).reasons[0].includes('低于80%'));
check('★置信度：覆盖50%(<60%)一次扣两级 → 低', mk(6,12,1,9,false).level===0 && mk(6,12,1,9,false).reasons[0].includes('低于60%'));
c = mk(12,12, 3, 7, false);
check('★置信度：多空一致性=7÷10=70%不扣分；6÷10=60%(<70%)扣一级 → 中', c.level===2 && mk(12,12,4,6,false).level===1 && mk(12,12,4,6,false).reasons[0].includes('一致性只有60%'));
c = mk(12,12, 1, 9, true);
check('★置信度：供需分歧扣一级 → 中，理由写明"方向分歧"', c.level===1 && c.reasons.some(r=>r.includes('方向分歧')) && !!c.divergence);
check('★置信度：多个问题叠加最低到低(不会变负)：覆盖50%+分歧+一致性60%', mk(6,12,4,6,true).level===0);
check('多空票权都是0(全中性)时一致性为null，不会除零', mk(12,12,0,0,false).agreement===null);

// ===================== 2. 界面集成 =====================
const KEYS = AUTO.map(k=>k.key);
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); window._indState[k] = {}; });
  makeEl('alertContent');
  window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null;
  window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
}
function neutral(){
  reset();
  const v = {crush:50, stock:70, stu:12, basis:0, arrival:900, import:900, hogratio:6, sows:3750, poultry:1, rmspread:550, reserve:0};
  Object.keys(v).forEach(k=>makeEl('m_'+k).value = String(v[k])); H.setBasis('0');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0;
  window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
}
function supplyBear(){   // 供给端6个投票(权重1,1,2,1,1,1=7)全偏空
  window._weatherRisk='low'; window._droughtSignal=-1; window._noaaOutlookSignal=-1; window._soyCondSignal=-1;
  window._psdSignal=-1; window._fxSignal=-1;
  makeEl('m_stu').value='16'; makeEl('m_arrival').value='1100'; makeEl('m_import').value='1100'; makeEl('m_reserve').value='54';
}
const html = ()=>makeEl('alertContent').innerHTML;

// 全中性：混合，没有置信度评级，只说明多空接近
neutral(); updateOverallAlert();
check('★全中性：顶部只显示供给/需求2条维度条形(v97起市场结构独立成卡，不在顶部)', (html().match(/class="dim-row"/g)||[]).length===2 && !html().includes('>市场结构<'));
check('★全中性(信号混合)：不评置信度，说明"多空力量接近"', html().includes('多空力量接近') && !html().includes('结论置信度') && window._fundamentalConfidence===null);
check('市场结构只有基差1项：市场结构卡里写"样本少：只有1项有信号"，不下结论', makeEl('structureContent').innerHTML.includes('市场结构样本少：只有1项有信号') && makeEl('structureContent').innerHTML.includes('不下结论'));
check('★顶部供需表格只有供应/需求2列(不含市场结构)；基差在市场结构卡里', !html().includes('<th>市场结构</th>') && !/sd-cell sd-\w+">现货基差/.test(html()) && makeEl('structureContent').innerHTML.includes('<th>市场结构</th>') && /sd-cell sd-\w+">现货基差/.test(makeEl('structureContent').innerHTML));
check('★window._dimensions已暴露(供后续三方共振等使用)，且是拆分后的结果(供给5票：作物/美豆库消比/国内松紧/到港进口/汇率；需求4票：出口/猪粮比/肉鸡/豆菜粕；国储拍卖、能繁母猪已移出评分)', window._dimensions && window._dimensions.supply.n===5 && window._dimensions.demand.n===4 && window._dimensions.structure.n===0 && window._structureSystem.n===1);   // v97：顶部维度只含供需(structure维度n=0)；市场结构单独在_structureSystem里
check('页面上有"不是买卖信号"的提示', html().includes('不是买卖信号'));

// 供给偏空(-100%)、需求偏多(+40%)：方向分歧
neutral(); supplyBear(); makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='2'; updateOverallAlert();
check('★分歧场景：供给端-100%、需求端+50%(猪粮比、肉鸡利润偏多，出口/豆菜粕中性：2÷4)', window._dimensions.supply.ratio===-1 && Math.abs(window._dimensions.demand.ratio-0.5)<1e-9);
check('★分歧场景：基本面仍偏空(供给6票权全空+需求2偏多=-4，÷有效票权10=-40%；原11里1票是中性基差=结构票，v97起不在顶部)', html().includes('基本面偏空 -4（净倾向-40%）') && window._fundamentalDirection==='偏空');
check('★分歧场景：弹出"方向分歧"提示，点名两个维度和各自数值', html().includes('方向分歧') && html().includes('供给端偏空(-100%)') && html().includes('需求端偏多(+50%)') && html().includes('不要只看总分'));
check('★分歧场景：置信度降为中，理由含"方向分歧"', html().includes('结论置信度：中') && window._fundamentalConfidence==='中');
check('★偏空依据里带出主导因素(含双倍票权的国内供应松紧)', html().includes('偏空依据：') && html().includes('国内豆粕供应松紧 ×2'));
check('偏多依据里列出猪粮比/能繁母猪', html().includes('偏多依据：') && html().includes('猪粮比') && html().includes('能繁母猪'));

// 高置信度：供给偏空 + 基差偏空 + 需求中性，覆盖100%，一致性100%
neutral(); supplyBear(); H.setBasis('-100'); updateOverallAlert();
check('★高置信度：多空一致(全部偏空)、无分歧、覆盖100% → 高', html().includes('结论置信度：高') && window._fundamentalConfidence==='高' && !html().includes('方向分歧'));
check('高置信度时置信度框不是警告样式', !/alert-box warn"><span class="at">🔎/.test(html()));

// 低置信度：覆盖率低(只有供给端数据)
reset(); supplyBear(); window._esrSignal=null; updateOverallAlert();
check('★低置信度：只有供给端6个投票有数据(覆盖6/12=50%)→ 低，并且是警告样式', html().includes('结论置信度：低') && /alert-box warn"><span class="at">🔎/.test(html()) && html().includes('低于60%'));
check('需求端无数据时条形显示"无数据"而不是0%', html().includes('无数据') && !/需求端<\/span>.*?\+0%/.test(html().replace(/\n/g,'')));

// 数据不足分支：不留旧的维度/置信度
reset(); makeEl('m_crush').value='35'; updateOverallAlert();
check('★数据不足时维度和置信度置空，不沿用上一次的旧值', html().includes('数据不足') && window._dimensions===null && window._fundamentalConfidence===null);

// 条形方向：偏空向左(neg)，偏多向右(pos)
neutral(); supplyBear(); makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='2'; updateOverallAlert();
const rows = html().match(/<div class="dim-row">.*?<\/div><\/div>|<div class="dim-row">.*?<span class="dim-n">[^<]*<\/span><\/div>/g) || [];
check('★供给端条形向左(绿/neg)，需求端条形向右(红/pos)', /供给端.*?dim-bar neg/.test(rows[0]||'') && /需求端.*?dim-bar pos/.test(rows[1]||''));
check('条形宽度=|净倾向|×50%：供给-100%→50%，需求+50%→25%', (rows[0]||'').includes('width:50.0%') && (rows[1]||'').includes('width:25.0%'));

// 分歧不受"样本少"的维度干扰：基差偏多(单项)不应和供给偏空构成分歧
neutral(); supplyBear(); H.setBasis('100'); updateOverallAlert();
check('★市场结构只有基差1项：即使与供给端相反也不算"方向分歧"', !html().includes('方向分歧'));

H.clearMockedMonth();
H.printSummary();
