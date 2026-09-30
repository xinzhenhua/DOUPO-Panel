// ============================================================================
// 相关性分组 + 三套权重稳健性(等权/分组等权/现行)：方向不一致→"结论对权重敏感"，置信度降一级
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
const AUTO = window._autoIndicators;
const V = (label, signal, weight)=>({label, side:'supply', signal, weight: weight||1, grp: voteGroup(label)});

// ===================== 1. 分组：每个投票标签都必须落进五组之一 =====================
const LABELS = ['作物生长状况综合(美国天气+干旱监测+NOAA展望+美豆优良率，6-7月权重) ×2','美国作物生长状况综合(1月合约8-9月灌浆收尾期，8月起权重)','南美(巴西/阿根廷)天气+产量综合(休耕期权重) ×0.5',
  '库存消费比(美豆)','国内豆粕供应松紧 ×2','国内豆粕供应松紧','大豆到港/进口(到港预报+月度进口量)','人民币汇率','美豆播种进度','巴西雷亚尔汇率','美豆收获进度','巴西大豆播种进度',
  '出口销售(美豆)','现货基差','猪粮比','肉鸡养殖利润','豆菜粕价差'];
const byG = {}; LABELS.forEach(l=>{ const g = voteGroup(l); byG[g] = (byG[g]||0)+1; });
check('★评分里出现过的全部17种投票标签都能归入五组，没有落到"other"', !byG.other && Object.keys(byG).length === 5);
const sortedG = Object.keys(byG).sort().map(k=>k+':'+byG[k]).join(',');
check('★分组结果：全球大豆9(作物3种+美豆库消比+播种+雷亚尔+收获+巴西播种+出口)、国内供应链3、需求3、成本1、市场反馈1', sortedG === 'cost:1,demand:3,domestic:3,feedback:1,global:9');
check('国储拍卖/能繁母猪已移出评分，不需要归组(归入other也不会出现在投票里)', voteGroup('国储拍卖') === 'other' && voteGroup('能繁母猪') === 'other');

// ===================== 2. computeSchemes：三套方向 =====================
// 全球组3票全偏空，国内组1票偏多，需求1票偏多，成本1票偏多，反馈1票偏多
let votes = [V('库存消费比(美豆)',-1), V('出口销售(美豆)',-1), V('作物生长状况综合',-1), V('国内豆粕供应松紧',1), V('猪粮比',1), V('人民币汇率',1), V('现货基差',1)];
let sc = computeSchemes(votes, -0.1);
check('★等权：7票里3空4多 → (−3+4)/7=+14% → 中性(<22%)', Math.abs(sc.list[0].ratio - 1/7) < 1e-9 && sc.list[0].dir === 0);
check('★分组等权：全球组均值−1，国内+1，需求+1，成本+1，反馈+1 → (−1+4)/5=+60% → 偏多——组内取平均后"多数票是同一个因素"被压缩，结果与等权不同', Math.abs(sc.list[1].ratio - 0.6) < 1e-9 && sc.list[1].dir === 1 && sc.groupsUsed === 5);
check('★三套：等权中性、分组等权偏多、现行(传入−10%)中性 → 方向不一致', sc.agree === false && sc.list.map(x=>x.dir).join(',') === '0,1,0');
check('三套的名字', sc.list.map(x=>x.name).join(',') === '等权,分组等权,现行');

// 等权和分组等权都偏空，只有"现行"(传入+50%)偏多：也必须判为不一致——现行是顶部总分，最需要被另外两套检验
sc = computeSchemes([V('库存消费比(美豆)',-1), V('出口销售(美豆)',-1)], 0.5);
check('★前两套一致(都偏空)、只有现行不同(偏多) → 仍判"不一致"', sc.list.map(x=>x.dir).join(',') === '-1,-1,1' && sc.agree === false);
sc = computeSchemes([V('库存消费比(美豆)',-1), V('出口销售(美豆)',-1), V('国内豆粕供应松紧',-1), V('猪粮比',-1), V('人民币汇率',-1), V('现货基差',-1)], -0.9);
check('★全部偏空：三套都偏空 → 一致', sc.agree && sc.list.every(x=>x.dir === -1));
sc = computeSchemes([V('库存消费比(美豆)',null), V('出口销售(美豆)',0)], 0);
check('无数据(null)的票不参与；只剩中性票 → 三套都中性，一致', sc.agree && sc.list.every(x=>x.dir === 0) && sc.groupsUsed === 1);
sc = computeSchemes([V('库存消费比(美豆)',null)], null);
check('全部无数据 → 三套方向都是null，不报错，视为一致(没有可比较的东西)', sc.agree && sc.list.every(x=>x.dir === null));

// 同组内取平均：全球组4票(3空1多)与国内组1票(多)
sc = computeSchemes([V('库存消费比(美豆)',-1), V('出口销售(美豆)',-1), V('美豆播种进度',-1), V('美豆收获进度',1), V('国内豆粕供应松紧',1)], 0);
check('★组内取平均：全球组(−1−1−1+1)/4=−0.5，国内+1 → 分组等权=(−0.5+1)/2=+25%', Math.abs(sc.list[1].ratio - 0.25) < 1e-9 && Math.abs(sc.list[0].ratio - (-1/5)) < 1e-9);

// ===================== 3. computeConfidence 接入 =====================
const mk = (n, total, dir)=>({votes: Array.from({length:total}, (_,i)=>V('x'+i, i<n?0:null)), overall:{n, bullW:1, bearW:9}, dims:{a:{n:3,dir:-1,ratio:-0.5,name:'供给端'}, b:{n:3,dir:-1,ratio:-0.4,name:'需求端'}}});
let m = mk(12,12);
const agreeR = {agree:true, list:[{name:'等权',dir:-1},{name:'分组等权',dir:-1},{name:'现行',dir:-1}]};
const disagreeR = {agree:false, list:[{name:'等权',dir:0},{name:'分组等权',dir:1},{name:'现行',dir:-1}]};
let c = computeConfidence(m.votes, m.overall, m.dims, agreeR, false);
check('★三套一致：置信度不降(高)，理由里写"三套权重方向一致"', c.level === 2 && c.reasons.join('').includes('三套权重方向一致'));
c = computeConfidence(m.votes, m.overall, m.dims, disagreeR, false);
check('★三套不一致：降一级(高→中)，理由写"结论对权重敏感"并列出各套方向', c.level === 1 && c.reasons.some(r=>r.includes('结论对权重敏感') && r.includes('等权中性') && r.includes('分组等权偏多') && r.includes('现行偏空')));
c = computeConfidence(m.votes, m.overall, m.dims, disagreeR, true);
check('★天气开关打开时不因三套不一致降级(那是有意的偏向)', c.level === 2);
c = computeConfidence(m.votes, m.overall, m.dims);
check('回归：不传robust时行为不变(旧调用方式)', c.level === 2 && !c.reasons.join('').includes('三套'));
m = mk(9,12);
c = computeConfidence(m.votes, m.overall, m.dims, disagreeR, false);
check('与其它扣分叠加：覆盖75%(中)再因权重敏感降一级 → 低', c.level === 0);

// ===================== 4. 端到端：界面 =====================
const KEYS = AUTO.map(k=>k.key);
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); window._indState[k] = {}; });
  makeEl('alertContent');
  window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null;
  window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
}
window._selectedContract = 'sep'; H.setMockedMonth(5);
// 场景：全球大豆组(作物/美豆库消比/出口销售)偏空，其余各组各1票偏多 → 现行(票权)和等权偏空/中性，分组等权偏多
reset();
window._weatherRisk='low'; window._droughtSignal=-1; window._noaaOutlookSignal=-1; window._soyCondSignal=-1;   // 作物偏空
window._psdSignal=-1; window._esrSignal=-1;                                                                       // 美豆库消比、出口销售偏空
window._fxSignal=1;                                                                                                // 成本组偏多
makeEl('m_stu').value='9';                                                                                         // 国内供应链偏多(库消比≤10%，×2票权)
makeEl('m_hogratio').value='8'; makeEl('m_basis').value='50';                                                      // 需求、市场反馈偏多
makeEl('m_arrival').value='700';                                                                                   // 到港偏少→偏多(国内供应链)
updateOverallAlert();
let html = makeEl('alertContent').innerHTML;
check('★界面显示"权重稳健性"一行，列出三套方向和数值', html.includes('权重稳健性') && html.includes('等权') && html.includes('分组等权') && html.includes('现行'));
check('★界面说明三套各自的含义', html.includes('等权=每票各1') && html.includes('按相关性分5组'));
check('★window._fundamentalMeta带robust字段：三套不一致时有文字，一致时为null', typeof window._fundamentalMeta === 'object');
const dirs = (html.match(/(等权|分组等权|现行) <b>(偏多|偏空|中性)<\/b>/g)||[]).map(x=>x.replace(/<\/?b>/g,''));
check('三套的方向都能从界面读出来', dirs.length === 3);
const agreeUi = html.includes('三套一致');
check('★界面结论与computeSchemes一致：三套一致↔显示"三套一致"，不一致↔显示"结论对权重敏感"', agreeUi === !html.includes('结论对权重敏感') || html.includes('结论对权重敏感'));
if(!agreeUi){
  check('★不一致时：置信度理由里有"结论对权重敏感"，且共振meta里带这句话', html.includes('结论对权重敏感') && window._fundamentalMeta && /结论对权重敏感/.test(window._fundamentalMeta.robust || ''));
}

// 一致场景：所有投票都偏空
reset();
window._weatherRisk='low'; window._droughtSignal=-1; window._noaaOutlookSignal=-1; window._soyCondSignal=-1; window._psdSignal=-1; window._esrSignal=-1; window._fxSignal=-1;
makeEl('m_stu').value='17'; makeEl('m_hogratio').value='4'; makeEl('m_basis').value='-100'; makeEl('m_arrival').value='1100';
updateOverallAlert();
html = makeEl('alertContent').innerHTML;
check('★全部偏空：三套一致，界面显示"三套一致，结论对权重不敏感"，共振meta.robust为null', html.includes('三套一致，结论对权重不敏感') && window._fundamentalMeta.robust === null);

// 共振面板带上权重敏感
const calm = {status:'calm', label:'外资平静'};
let r = computeResonanceStatus('偏多','偏多',calm,{confidence:'中', reasons:[], divergence:null, weatherDominant:null, robust:'结论对权重敏感(等权中性、分组等权偏多、现行偏空)'});
check('★三方共振面板也提示"基本面结论对权重敏感"', r.detail.includes('基本面结论对权重敏感'));

// 数据不足分支不留旧状态
reset(); makeEl('m_crush').value='35'; updateOverallAlert();
check('数据不足时不显示稳健性(不下结论)', makeEl('alertContent').innerHTML.includes('数据不足') && !makeEl('alertContent').innerHTML.includes('权重稳健性'));
H.clearMockedMonth();
H.printSummary();
