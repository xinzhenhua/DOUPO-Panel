// ============================================================================
// 两个独立系统：基本面(仅供需票，不含市场结构) vs 市场结构(基差/月差/量价)：背离描述 + 共振面板
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
const AUTO = window._autoIndicators;
elements['resonanceContent'] = makeEl('resonanceContent');
const D = (dir, thin)=>({direction: dir, thin: !!thin});

// ===================== 1. 系统级背离描述(纯函数) =====================
let r = computeSystemsDivergence(D('偏多'), D('偏空'));
check('★基本面偏多 + 市场结构偏空：背离(warn)，写"供需面有支撑，但盘面没有确认"', r.cls === 'warn' && r.title === '背离：基本面偏多、市场结构偏空' && r.detail.includes('供需面有支撑') && r.detail.includes('没有确认'));
r = computeSystemsDivergence(D('偏空'), D('偏多'));
check('★基本面偏空 + 市场结构偏多：背离，写"供需面偏弱，但盘面没有确认下跌"', r.cls === 'warn' && r.title === '背离：基本面偏空、市场结构偏多' && r.detail.includes('供需面偏弱'));
r = computeSystemsDivergence(D('偏多'), D('偏多'));
check('★同向偏多：bull色，且提醒"市场结构与技术面同源，二者一致不算独立证据"', r.cls === 'bull' && r.title === '基本面与市场结构同向：偏多' && r.detail.includes('同源') && r.detail.includes('不算独立证据'));
r = computeSystemsDivergence(D('偏空'), D('偏空'));
check('同向偏空：bear色', r.cls === 'bear' && r.title.includes('偏空'));
r = computeSystemsDivergence(D('中性'), D('偏多'));
check('★基本面中性 + 市场结构偏多：warn，写"主要是盘面在推动，缺少供需面的支撑(锚)"', r.cls === 'warn' && r.detail.includes('缺少供需面的支撑'));
r = computeSystemsDivergence(D('偏多'), D('中性'));
check('基本面偏多 + 市场结构中性：neutral，"盘面还没有确认基本面的方向"', r.cls === 'neutral' && r.detail.includes('还没有确认'));
r = computeSystemsDivergence(D('中性'), D('中性'));
check('都中性', r.cls === 'neutral' && r.title.includes('都中性'));
r = computeSystemsDivergence(D('偏多'), D('偏空', true));
check('★市场结构只有1项(thin)：不做背离判断，写"样本少(仅1项)"——单个指标不足以跟基本面比较', r.cls === 'neutral' && r.title.includes('样本少') && !r.title.includes('背离'));
r = computeSystemsDivergence(D('偏多'), D(null));
check('市场结构没有任何信号：写明原因(样本积累中/量价门槛没过)', r.title.includes('暂无信号') && r.detail.includes('量价可用性门槛'));
r = computeSystemsDivergence(D(null), D('偏多'));
check('基本面数据不足：无法比较', r.title.includes('基本面数据不足'));
check('null入参不报错', computeSystemsDivergence(null, null).title.includes('基本面数据不足') && computeSystemsDivergence(D('偏多'), null).title.includes('暂无信号'));
check('★描述里没有操作建议(不出现"不追""等待""买入""卖出""做多""做空")：只描述状态', ['偏多','偏空','中性'].every(f=>['偏多','偏空','中性',null].every(t=>{ const x = computeSystemsDivergence(D(f), D(t)); return !/不追|等待|买入|卖出|做多|做空|建议/.test(x.title + x.detail); })));

// ===================== 2. updateOverallAlert：两个系统独立计算 =====================
const KEYS = AUTO.map(c=>c.key);
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); });
  window._indState = {}; makeEl('alertContent');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
  window._selectedContract='sep'; H.setMockedMonth(5);
  window._crushSignal = undefined; window._spreadSignal = undefined; window._vpSignal = undefined;
  window._technicalDirection = '偏多'; window._foreignActivity = {status:'calm', label:'外资平静'};
  window._fundamentalDirection = null;
}
// 基本面全偏多：作物4项子信号偏多+美豆库消比+汇率+库消比偏多(9%)+到港/进口偏少+猪粮比+肉鸡利润
function fundBull(){
  window._weatherRisk='high'; window._droughtSignal=1; window._noaaOutlookSignal=1; window._soyCondSignal=1; window._psdSignal=1; window._fxSignal=1;
  makeEl('m_stu').value='9'; makeEl('m_arrival').value='700'; makeEl('m_import').value='700'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='2';
  makeEl('m_crush').value='50'; makeEl('m_stock').value='70'; makeEl('m_rmspread').value='550';
}
const stBear = ()=>{ H.setBasis('-100'); window._spreadSignal=-1; window._spreadQuality={m:1,why:''}; window._vpSignal=-1; window._vpQuality={m:1,why:''}; };
const stBull = ()=>{ H.setBasis('100'); window._spreadSignal=1; window._spreadQuality={m:1,why:''}; window._vpSignal=1; window._vpQuality={m:1,why:''}; };
reset(); fundBull(); stBear(); updateOverallAlert();
check('★基本面(仅供需票)偏多：不含市场结构票，只看供给/需求', window._fundamentalPure.direction === '偏多' && window._fundamentalPure.n >= 5);
check('★市场结构：基差偏空+月差偏空+量价偏空 → 3项全偏空(-100%)', window._structureSystem.direction === '偏空' && window._structureSystem.n === 3 && window._structureSystem.ratio === -1 && window._structureSystem.thin === false);
check('市场结构明细列出三项的名字和方向', window._structureSystem.items.map(x=>x.label+':'+x.signal).join(',') === '现货基差:-1,量价关系:-1,月差/期限结构:-1' || (window._structureSystem.items.length === 3 && window._structureSystem.items.every(x=>x.signal === -1)));
let panel = makeEl('resonanceContent').innerHTML;
check('★共振面板出现"背离：基本面偏多、市场结构偏空"', panel.includes('背离：基本面偏多、市场结构偏空') && panel.includes('alert-box warn'));
check('★共振面板的行里同时列出：基本面(仅供需，不含市场结构)、市场结构(基差/月差/量价)', panel.includes('基本面(仅供需，不含市场结构)：偏多') && panel.includes('市场结构(基差/月差/量价)：偏空'));
check('★面板说明(v97)："顶部基本面预警"与这里的基本面是同一个东西，都只含供给/需求票；市场结构是独立的另一个系统——且不再说"也算了进去"(那是v94~v96顶部含结构票时的说法，现在是假话)', panel.includes('同一个东西') && panel.includes('只含供给/需求票') && panel.includes('独立的另一个系统') && !panel.includes('也算了进去'));
check('技术面/外资仍在(这一版没有把它们并进来)', panel.includes('技术面：偏多') && panel.includes('外资动向：外资平静'));
check('★总方向(window._fundamentalDirection)语义没变：仍是全部投票合起来', typeof window._fundamentalDirection === 'string');

reset(); fundBull(); stBull(); updateOverallAlert();
check('★基本面偏多 + 市场结构偏多：同向', window._structureSystem.direction === '偏多' && makeEl('resonanceContent').innerHTML.includes('基本面与市场结构同向：偏多'));

// 市场结构只有基差1项(月差/量价还没信号)：thin
reset(); fundBull(); H.setBasis('-100'); updateOverallAlert();
check('★市场结构只有基差1项：thin=true，方向按这一项，但面板不做背离判断', window._structureSystem.n === 1 && window._structureSystem.thin === true && window._structureSystem.direction === '偏空');
panel = makeEl('resonanceContent').innerHTML;
check('★面板写"市场结构样本少(仅1项：偏空)"，行里标"(仅1项)"，不出现"背离："结论框(底部说明文字里会说"背离才是需要关注的信息"，那不是结论)', panel.includes('市场结构样本少(仅1项：偏空)') && panel.includes('偏空(仅1项)') && !panel.includes('背离：') && !panel.includes('title">背离'));
// 市场结构没有任何信号
reset(); fundBull(); updateOverallAlert();
check('★市场结构完全没有信号(基差也没填)：direction=null，面板"暂无信号"', window._structureSystem.direction === null && window._structureSystem.n === 0 && makeEl('resonanceContent').innerHTML.includes('市场结构暂无信号'));
// 基本面不含市场结构：即使市场结构极端，也不影响基本面方向
reset(); fundBull(); const dirNoStruct = (updateOverallAlert(), window._fundamentalPure.direction, window._fundamentalPure.ratio);
reset(); fundBull(); stBear(); updateOverallAlert();
check('★基本面(仅供需)的净倾向不受市场结构影响：加上三个偏空的市场结构票，基本面ratio不变', window._fundamentalPure.ratio === dirNoStruct);
// 与总分的差别
check('★v97顶部就是纯基本面：加上三个偏空的市场结构票，顶部仍是+85%(不再被拉低到+50%)；被拉低的是composite(全部投票的综合，只用于每天记录)', (function(){ const m = makeEl('alertContent').innerHTML.match(/净倾向([+-]?\d+)%/); const head = m ? parseInt(m[1]) : null; return head === 85 && Math.round(window._fundamentalPure.ratio*100) === 85 && Math.round(window._composite.ratio*100) === 50; })());

// 基本面数据不足：null
reset(); makeEl('m_crush').value='35'; H.setBasis('-100'); window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null; window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
updateOverallAlert();
check('★基本面数据不足(供需票<5)：基本面方向置null、不沿用上次(_fundamentalPure={direction:null})；★市场结构是独立系统，不跟着置空(这里基差-100，n=1、thin)，且市场结构卡照常显示', window._fundamentalPure !== null && window._fundamentalPure.direction === null && window._fundamentalDirection === null && window._structureSystem !== null && window._structureSystem.n === 1 && window._structureSystem.thin === true && makeEl('structureContent').innerHTML.includes('市场结构样本少'));
// 纯基本面票数不足(总票数够，但供需票<5)：基本面方向null，面板"数据不足"
reset(); H.setBasis('-100'); window._spreadSignal=-1; window._spreadQuality={m:1,why:''}; window._vpSignal=-1; window._vpQuality={m:1,why:''};
makeEl('m_crush').value='35'; makeEl('m_stock').value='40';                      // 供需票只有国内供应松紧+作物(0)+美豆库消比(0)+汇率(0)=4项 <5
window._psdSignal = 0; window._esrSignal = null; updateOverallAlert();
check('★总票数够(≥5)但供需票不足5项：基本面方向=null(数据不足)，不拿市场结构去凑。_fundamentalPure保持{direction:null,n<5}(不置null)——面板靠"对象存在"区分"数据不足"和"加载中"', window._fundamentalPure !== null && window._fundamentalPure.n < 5 && window._fundamentalPure.direction === null && window._fundamentalDirection === null && makeEl('resonanceContent').innerHTML.includes('基本面(仅供需，不含市场结构)：数据不足'));
check('★★回归守卫：数据早已加载完、只是供需票不够时，面板写"数据不足"，绝不能写"加载中..."(置null会误导用户一直等)', !makeEl('resonanceContent').innerHTML.includes('基本面(仅供需，不含市场结构)：加载中') && !makeEl('resonanceContent').innerHTML.includes('基本面：加载中'));
check('★同一场景下市场结构(基差-100、月差-1、量价-1共3项)独立存在且有方向：偏空，3项(不因基本面数据不足而丢失)', window._structureSystem.n === 3 && window._structureSystem.direction === '偏空' && window._structureSystem.thin === false && makeEl('structureContent').innerHTML.includes('市场结构偏空（净倾向-100%）'));


// ===================== 4. ★命名(v97)：顶部叫"基本面预警"(仅供需)，市场结构是独立的另一张卡 =====================
// 演变：v94前叫"综合基本面预警"(名不副实：总分混着基差/月差/量价) → v94改叫"综合预警" → v97彻底拆开：顶部只含供需，叫"基本面预警"，
//   市场结构(基差/月差/量价)独立成下面一张卡。这一节守卫的就是这个命名约定，防止以后又把两者混回去。
const fs = require('fs'), path = require('path');
const SRC = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
// ★v99：原来独立的"基本面预警"卡和"市场结构"卡合并进了决策卡，各自是里面的一个折叠区块(<details class="dc-sec">)。
//   这几条守卫的意图不变——基本面预警不能叫"综合"、市场结构必须是**独立的区块**、两者的性质说明要写清楚——只是指向新结构。
const secOf = (marker)=>{ const i = SRC.indexOf(marker); const a = SRC.lastIndexOf('<details class="dc-sec"', i); return SRC.slice(a, SRC.indexOf('</details>', i) + 10); };
const cardHtml = secOf('id="alertContent"');
check('★决策卡里有可见标题"基本面预警"的区块', /<summary>📊 基本面预警/.test(cardHtml));
check('★标题旁写明它是什么：仅供需(供给端+需求端)，不含基差/月差/量价', cardHtml.includes('仅供需') && cardHtml.includes('供给端+需求端') && cardHtml.includes('不含基差/月差/量价'));
check('★该区块不再叫"综合预警"/"综合基本面预警"(它已经不是综合的)', !/<summary>[^<]*综合/.test(cardHtml) && !cardHtml.includes('综合预警') && !cardHtml.includes('综合基本面预警'));
// ★v97新增、v99改为区块：市场结构是独立的系统
const structHtml = secOf('id="structureContent"');
check('★市场结构是决策卡里**独立的区块**(自己的<details>，不和基本面预警混在一个区块里)，紧跟在基本面预警区块之后(DOM顺序)，在三方关系/事件/健康度区块之前', structHtml !== cardHtml && SRC.indexOf('id="structureContent"') > SRC.indexOf('id="alertContent"') && SRC.indexOf('id="structureContent"') < SRC.indexOf('id="resonanceContent"') && !structHtml.includes('id="alertContent"') && !cardHtml.includes('id="structureContent"'));
check('★市场结构区块标题"市场结构"，写明"来自价格本身，跟技术面同源，不是独立于价格的证据"', /<summary>🧭 市场结构/.test(structHtml) && structHtml.includes('基差/月差/量价') && structHtml.includes('来自价格本身') && structHtml.includes('同源') && structHtml.includes('不是独立于价格的证据'));
reset(); fundBull(); stBear(); updateOverallAlert();
const top = makeEl('alertContent').innerHTML;
check('★底部免责写"这是基本面倾向(仅供需)"，指向市场结构卡，不再写"这是综合倾向"', top.includes('这是基本面倾向(仅供需)') && top.includes('不含基差/月差/量价') && top.includes('市场结构」区块') && !top.includes('下一张') && !top.includes('这是综合倾向'));
check('★顶部不含任何市场结构票：供需表格没有"市场结构"列，也没有"现货基差/月差/量价"格', !top.includes('<th>市场结构</th>') && !/sd-cell[^>]*>(现货基差|月差|量价)/.test(top));
const stHtml = makeEl('structureContent').innerHTML;
check('★市场结构卡里有这三项，且各自的方向(这里三个都偏空)', /sd-cell sd-neg">现货基差/.test(stHtml) && /sd-cell sd-neg">月差\/期限结构/.test(stHtml) && /sd-cell sd-neg">量价关系/.test(stHtml) && stHtml.includes('市场结构偏空（净倾向-100%）'));
check('★市场结构卡的说明：三者来自价格本身、跟基本面一致不算独立证据、只描述状态不给买卖建议', stHtml.includes('来自价格本身') && stHtml.includes('不算独立证据') && stHtml.includes('不给买卖建议'));
check('★市场结构卡写出与基本面的关系：基本面偏多、市场结构偏空 = 背离', stHtml.includes('与基本面的关系：背离：基本面偏多、市场结构偏空'));
panel = makeEl('resonanceContent').innerHTML;
check('★共振面板的说明：顶部"基本面预警"与这里的基本面是同一个东西、都只含供需票；市场结构是独立的另一个系统；不再说"综合预警…也算了进去/不是纯基本面"', panel.includes('顶部"基本面预警"与这里的"基本面"是同一个东西') && panel.includes('独立的另一个系统') && !panel.includes('综合预警') && !panel.includes('所以它不是纯基本面') && !panel.includes('也算了进去'));
// 基本面预警的属性(置信度/分歧/权重敏感)在共振面板里都叫"基本面预警…"——它们描述的是顶部这张只含供需的卡
window._fundamentalMeta = {confidence:'低', reasons:['有效指标只有6/12'], divergence:'供需两侧方向分歧(供给端偏空、需求端偏多)', weatherDominant:'美国作物3项偏多', robust:'结论对权重敏感(等权中性、分组等权偏多、现行偏空)'};
const rr = computeResonanceStatus('偏多','偏多',{status:'calm', label:'外资平静'}, window._fundamentalMeta);
check('★共振详情：基本面预警置信度/内部供需分歧/天气主导/权重敏感，全部带"基本面预警"前缀', rr.detail.includes('基本面预警置信度：低') && rr.detail.includes('基本面预警内部供需两侧方向分歧') && rr.detail.includes('基本面预警正处于天气主导行情') && rr.detail.includes('基本面预警结论对权重敏感'));
check('★共振标题的低置信度提示：基本面预警置信度低，共振的可靠性打折', rr.title.includes('基本面预警置信度低，共振的可靠性打折'));
check('★描述这些属性的地方不再出现"综合预警"(它们描述的是只含供需的基本面预警，不是综合)', !/综合预警/.test(rr.title + rr.detail));
// 防回退：扫描页面源码里的用户可见文案(去掉注释行)——不能再出现会误导的旧名字
const visibleLines = SRC.split('\n').filter(l=>!/^\s*(\/\/|<!--|\*|\/\*)/.test(l) && !/^\s+v94：|^\s+v97：|^\s+改叫|^\s+现在彻底拆开/.test(l));
check('★防回退：页面源码的非注释行里没有"综合预警"/"综合基本面预警"/"这是综合倾向"/"基本面结论置信度"(用户可见文案里不能再把顶部叫综合)', !visibleLines.some(l=>/综合预警|综合基本面预警|这是综合倾向|基本面结论置信度/.test(l)));


// ===================== 5. ★v97：顶部的总分绝对数和置信度只来自供需票，不被市场结构票影响 =====================
// (变异检查发现原测试区分不出"总分用overall.score"和"置信度用全部投票"——原场景里两种输入给出同样的结果。这里专门构造会产生差异的场景)
// 5a. 总分绝对数：fundBull()+stBear()场景里，顶部标题是基本面的+5.5(作物×2+其余7票×0.5=5.5)，全部投票的composite是+4(再扣3个偏空结构票×0.5)
reset(); fundBull(); stBear(); updateOverallAlert();
const t5 = makeEl('alertContent').innerHTML;
check('★顶部标题的总分绝对数是供需票的+5.5(作物×2+其余7票×0.5)，不是含结构票的+4', t5.includes('基本面偏多 +5.5（') && !t5.includes('+4（') && window._composite.score === 4 && window._composite.n === 12);
// 5b. 置信度：3个供需票偏多+2个供需票中性+3个结构票偏空(无天气开关，权重各1)——
//     仅供需：偏多3、偏空0 → 一致性100%；若把结构票也算进去：偏多3、偏空3 → 一致性50%<70%，置信度会降级
reset();
window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=1;
makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='2';          // 猪粮比、肉鸡利润偏多(需求侧)
makeEl('m_stu').value='9';                                                // 国内供应松紧偏多(权重2)
makeEl('m_rmspread').value='550'; makeEl('m_arrival').value='900'; makeEl('m_import').value='900';   // 中性
stBear(); updateOverallAlert();
const meta5 = window._fundamentalMeta;
check('★置信度只看供需票：供需票里没有偏空(一致性100%)，不因3个偏空的结构票而降级——不出现"多空意见一致性只有"', window._fundamentalPure.direction === '偏多' && meta5.reasons.every(r=>!r.includes('一致性只有')) && window._structureSystem.direction === '偏空' && window._structureSystem.n === 3);
check('★同一场景下，全部投票(composite)的一致性确实会低——证明上一条不是因为场景没区分度：composite方向没有被结构票拉成偏多', window._composite.ratio < window._fundamentalPure.ratio);


// 5c. ★偏多/偏空依据只列供需票：fundBull()+stBear()里3个偏空的结构票(现货基差/月差/量价)不能出现在顶部的"偏空依据"里
//     (变异检查发现：把driversHtml的输入改成全部投票，没有任何测试发现)
reset(); fundBull(); stBear(); updateOverallAlert();
const t5c = makeEl('alertContent').innerHTML;
check('★顶部"偏空依据"不出现(供需票里没有偏空)，更不会列出偏空的结构票：现货基差/月差/量价', !t5c.includes('偏空依据') && !/偏空依据[^<]*(现货基差|月差|量价)/.test(t5c));
check('★顶部"偏多依据"里全是供需票，没有结构票', t5c.includes('偏多依据：') && !/偏多依据[^<]*(现货基差|月差|量价)/.test(t5c));
// 5d. ★置信度的数据质量只看供需票：6个供需票质量正常 + 3个结构票全"晚了一期"(×0.5)——
//     仅供需质量100%，顶部置信度理由里不出现"数据质量"；而全部投票的质量分(健康度面板用)=(6+3×0.5)/9=83.33%<85%，说明如果误含结构票置信度会降级
//     (变异检查发现：置信度的quality改用全部投票，没有任何测试发现。注意：结构票最多3个，只有供需票较少(5~6个)时才可能越过85%线)
reset();
window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=1; window._psdSignal=1;
makeEl('m_hogratio').value='8'; makeEl('m_arrival').value='900'; makeEl('m_import').value='900';     // 供需票刚好5个、权重各1：作物(中性)/美豆库消比/汇率/猪粮比/到港进口
stBear(); window._spreadQuality = {m:0.5, why:'晚了一期'}; window._vpQuality = {m:0.5, why:'晚了一期'};
H.setBasis('-100'); window._indState.basis = {late:true, mode:'manual', history:H.basisHist(10)};
updateOverallAlert();
const m5d = window._fundamentalMeta;
check('★前置(手算：6个供需票权重各1×质量1 + 3个结构票×0.5 = (6+1.5)/9 = 83.33%)：全部投票的质量分<85%——如果误把结构票算进置信度，会触发降级(供需票越多越稀释，≥7个就不会越线，所以场景必须压到6个)', Math.abs(window._quality.score - 7.5/9) < 1e-9 && window._quality.score < 0.85 && window._quality.lowItems.length === 3 && window._fundamentalPure.n === 6);
check('★顶部置信度的数据质量只看供需票：理由里没有"数据质量"，质量说明那行也不列结构票', m5d.reasons.every(r=>!r.includes('数据质量')) && !/数据质量：[^<]*(现货基差|月差|量价)/.test(makeEl('alertContent').innerHTML));


// 5e. ★顶部维度说明文字只提供给/需求两个维度，不再出现"市场结构无数据"/"三个维度"
//     (渲染真实页面时发现：拆开后这行字仍写"市场结构无数据……三个维度是同一批投票的拆分"——而市场结构其实有3项数据，是错的、会误导)
reset(); fundBull(); stBear(); updateOverallAlert();
const t5e = makeEl('alertContent').innerHTML;
const sum5e = (t5e.match(/margin-top:2px">([^<]*)<\/div>/) || [])[1] || '';
check('★维度说明只提供给端/需求端，不出现"市场结构"', sum5e.includes('供给端') && sum5e.includes('需求端') && !sum5e.includes('市场结构') && !sum5e.includes('无数据'));
check('★维度说明写"两个维度"，不再写"三个维度"', sum5e.includes('两个维度是同一批投票的拆分') && !sum5e.includes('三个维度'));
check('★整张顶部卡里没有"市场结构无数据"(市场结构有数据时更不能这么写)', !t5e.includes('市场结构无数据') && window._structureSystem.n === 3);
// 基本面数据不足时顶部走另一条分支，也不能出现
reset(); H.setBasis('-100'); updateOverallAlert();
check('★数据不足分支的顶部也没有"市场结构无数据"', !makeEl('alertContent').innerHTML.includes('市场结构无数据'));
// 函数本身：默认(不传onlyKeys)仍包含全部三个维度，保持向后兼容；传了只含指定的
check('函数兼容：dimensionSummary(dims)默认含3个维度，传onlyKeys只含指定的', dimensionSummary(computeDimensions([])).includes('市场结构无数据') && !dimensionSummary(computeDimensions([]), ['supply','demand']).includes('市场结构') && dimensionSummary(computeDimensions([]), ['supply','demand']) === '供给端无数据，需求端无数据');

// ===================== 3. 面板的兼容性(旧调用方式) =====================
window._fundamentalPure = undefined; window._structureSystem = undefined; window._fundamentalDirection = '偏空'; window._technicalDirection = '偏空';
renderResonancePanel();
panel = makeEl('resonanceContent').innerHTML;
check('★没有两个系统的数据时(旧调用/加载中)：退回旧行为，基本面用总方向，不出现"市场结构"背离框', panel.includes('基本面：偏空') && !panel.includes('背离：') && !panel.includes('title">背离') && panel.includes('市场结构(基差/月差/量价)：加载中'));      // 不出现"背离："结论框；底部说明文字里会说"背离才是需要关注的信息"，那不是结论
delete elements['resonanceContent'];
let ok = true; try{ renderResonancePanel(); }catch(e){ ok = false; }
check('没有共振面板元素时不报错', ok);
H.clearMockedMonth();
H.printSummary();
