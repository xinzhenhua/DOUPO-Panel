const H = require('./test_helpers');
const { check } = H;
eval(H.loadDashboardJs());
// v101.9：供给端和需求端先各自算净倾向，再按固定比例(默认50/50)合成。
// 实现：把两个维度各自的有效票权合计缩放到目标占比，**总票权不变**，所以下游(置信度/稳健性/驱动排序/维度拆分)全部一致。
// 起因：供给端有7~10票、需求端只有5票，票权加权汇总时供给端天然占2/3左右，需求端被稀释。
const V = (label, side, signal, weight)=>({label, side, signal, weight: weight==null?1:weight, baseWeight: weight==null?1:weight});
const sum = (vs, side)=>vs.filter(v=>v.side===side && v.signal!==null).reduce((a,v)=>a+v.weight,0);

// ---- 手算案例：供给4票全偏多(各1)，需求2票全偏空(各1) ----
// 不均衡：总分 = (4-2)/6 = +33%。均衡后：供给净倾向+100%、需求-100%，各占50% → 总分 0%。
let vs = [V('s1','supply',1),V('s2','supply',1),V('s3','supply',1),V('s4','supply',1),V('d1','demand',-1),V('d2','demand',-1)];
check('前提：不均衡时总净倾向=+33%', Math.abs(tallyVotes(vs).ratio-1/3)<1e-9);
let r = balanceSupplyDemand(vs);
check('★均衡后供给:需求票权各占一半(总票权6 → 3:3)', Math.abs(sum(vs,'supply')-3)<1e-9 && Math.abs(sum(vs,'demand')-3)<1e-9);
check('★总票权不变(6)', Math.abs(tallyVotes(vs).weight-6)<1e-9);
check('★均衡后总净倾向=0.5×(+100%)+0.5×(-100%)=0', Math.abs(tallyVotes(vs).ratio)<1e-9);
check('返回缩放系数：供给×0.75、需求×1.5', r.applied===true && Math.abs(r.supplyFactor-0.75)<1e-9 && Math.abs(r.demandFactor-1.5)<1e-9);
check('原始票权保留在 rawWeight 里（审计用）', vs.every(v=>v.rawWeight===1));

// ---- 不变式：均衡后总净倾向 = 0.5×供给净倾向 + 0.5×需求净倾向（任意票权/信号） ----
vs = [V('a','supply',1,2),V('b','supply',-1,1),V('c','supply',0,1),V('d','supply',1,1),V('e','supply',null,3),V('x','demand',1,1),V('y','demand',-1,0.5),V('z','demand',0,1)];
const sR = tallyVotes(vs.filter(v=>v.side==='supply')).ratio, dR = tallyVotes(vs.filter(v=>v.side==='demand')).ratio;
const before = tallyVotes(vs).weight;
balanceSupplyDemand(vs);
check('★不变式：均衡后总净倾向=0.5×供给净倾向+0.5×需求净倾向', Math.abs(tallyVotes(vs).ratio-(0.5*sR+0.5*dR))<1e-9);
check('★不变式：总票权不变', Math.abs(tallyVotes(vs).weight-before)<1e-9);
check('无数据(null)的票不参与缩放、权重原样', vs.find(v=>v.label==='e').weight===3);
check('★维度拆分不变式仍然成立：各维度票权合计=总票权', (()=>{ const d = computeDimensions(vs); return Math.abs(d.supply.weight+d.demand.weight-tallyVotes(vs).weight)<1e-9; })());

// ---- 不均衡也会反过来：需求票多时同样拉平 ----
vs = [V('s1','supply',1),V('s2','supply',1),V('d1','demand',-1),V('d2','demand',-1),V('d3','demand',-1),V('d4','demand',-1)];
balanceSupplyDemand(vs);
check('需求票多时同样各占一半', Math.abs(sum(vs,'supply')-3)<1e-9 && Math.abs(sum(vs,'demand')-3)<1e-9);

// ---- 不做均衡的情形 ----
vs = [V('s1','supply',1),V('s2','supply',1),V('s3','supply',1),V('d1','demand',-1)];
r = balanceSupplyDemand(vs);
check('★某一侧有效票不足2：不均衡（否则1票独占一半话语权），说明原因，权重原样', r.applied===false && /不足|少/.test(r.reason) && vs.every(v=>v.weight===1));
vs = [V('s1','supply',1),V('s2','supply',1)];
r = balanceSupplyDemand(vs);
check('一侧完全没有有效票：不均衡，权重原样', r.applied===false && vs.every(v=>v.weight===1));
vs = [V('s1','supply',1),V('s2','supply',null),V('d1','demand',-1),V('d2','demand',-1)];
r = balanceSupplyDemand(vs);
check('★null票不计入"有效票数"：供给只有1个有效 → 不均衡', r.applied===false);
vs = [V('s1','supply',1),V('s2','supply',1),V('s3','supply',1),V('d1','demand',-1),V('d2','demand',-1)];
r = balanceSupplyDemand(vs, {skip:'天气开关打开：作物信号主导，有意偏向供给端'});
check('★天气开关打开时不均衡（那是有意的偏向），并写明原因', r.applied===false && r.reason.includes('天气开关') && vs.every(v=>v.weight===1));
check('★恰好各2票：照常均衡', (()=>{ const w=[V('s1','supply',1,3),V('s2','supply',-1,1),V('d1','demand',1),V('d2','demand',1)]; return balanceSupplyDemand(w).applied===true; })());
check('市场结构票不被缩放', (()=>{ const w=[V('s1','supply',1),V('s2','supply',1),V('s3','supply',1),V('d1','demand',1),V('d2','demand',1),V('m1','structure',1,1)]; balanceSupplyDemand(w); return w.find(v=>v.side==='structure').weight===1; })());
check('权重为0的有效票：不会除零', (()=>{ const w=[V('s1','supply',1,0),V('s2','supply',1,0),V('d1','demand',1),V('d2','demand',1)]; const rr=balanceSupplyDemand(w); return rr.applied===false && w.every(v=>Number.isFinite(v.weight)); })());
check('比例是常量、可调：默认50/50', window._sdBalance.share.supply===0.5 && window._sdBalance.share.demand===0.5 && window._sdBalance.minN===2);
check('自定义比例60/40：均衡后供给占60%', (()=>{ const w=[V('s1','supply',1),V('s2','supply',1),V('s3','supply',1),V('d1','demand',1),V('d2','demand',1)]; balanceSupplyDemand(w,{share:{supply:0.6,demand:0.4}}); return Math.abs(sum(w,'supply')-3)<1e-9 && Math.abs(sum(w,'demand')-2)<1e-9; })());
H.printSummary();
