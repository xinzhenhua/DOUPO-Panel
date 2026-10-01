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
const stBear = ()=>{ makeEl('m_basis').value='-100'; window._spreadSignal=-1; window._spreadQuality={m:1,why:''}; window._vpSignal=-1; window._vpQuality={m:1,why:''}; };
const stBull = ()=>{ makeEl('m_basis').value='100'; window._spreadSignal=1; window._spreadQuality={m:1,why:''}; window._vpSignal=1; window._vpQuality={m:1,why:''}; };
reset(); fundBull(); stBear(); updateOverallAlert();
check('★基本面(仅供需票)偏多：不含市场结构票，只看供给/需求', window._fundamentalPure.direction === '偏多' && window._fundamentalPure.n >= 5);
check('★市场结构：基差偏空+月差偏空+量价偏空 → 3项全偏空(-100%)', window._structureSystem.direction === '偏空' && window._structureSystem.n === 3 && window._structureSystem.ratio === -1 && window._structureSystem.thin === false);
check('市场结构明细列出三项的名字和方向', window._structureSystem.items.map(x=>x.label+':'+x.signal).join(',') === '现货基差:-1,量价关系:-1,月差/期限结构:-1' || (window._structureSystem.items.length === 3 && window._structureSystem.items.every(x=>x.signal === -1)));
let panel = makeEl('resonanceContent').innerHTML;
check('★共振面板出现"背离：基本面偏多、市场结构偏空"', panel.includes('背离：基本面偏多、市场结构偏空') && panel.includes('alert-box warn'));
check('★共振面板的行里同时列出：基本面(仅供需，不含市场结构)、市场结构(基差/月差/量价)', panel.includes('基本面(仅供需，不含市场结构)：偏多') && panel.includes('市场结构(基差/月差/量价)：偏空'));
check('面板说明"顶部总分把基差/月差/量价也算进去了，这里的基本面只含供给/需求票"(避免两处数字对不上时困惑)', panel.includes('顶部') && panel.includes('也算了进去') && panel.includes('只含供给/需求票'));
check('技术面/外资仍在(这一版没有把它们并进来)', panel.includes('技术面：偏多') && panel.includes('外资动向：外资平静'));
check('★总方向(window._fundamentalDirection)语义没变：仍是全部投票合起来', typeof window._fundamentalDirection === 'string');

reset(); fundBull(); stBull(); updateOverallAlert();
check('★基本面偏多 + 市场结构偏多：同向', window._structureSystem.direction === '偏多' && makeEl('resonanceContent').innerHTML.includes('基本面与市场结构同向：偏多'));

// 市场结构只有基差1项(月差/量价还没信号)：thin
reset(); fundBull(); makeEl('m_basis').value='-100'; updateOverallAlert();
check('★市场结构只有基差1项：thin=true，方向按这一项，但面板不做背离判断', window._structureSystem.n === 1 && window._structureSystem.thin === true && window._structureSystem.direction === '偏空');
panel = makeEl('resonanceContent').innerHTML;
check('★面板写"市场结构样本少(仅1项：偏空)"，行里标"(仅1项)"，不出现"背离"', panel.includes('市场结构样本少(仅1项：偏空)') && panel.includes('偏空(仅1项)') && !panel.includes('背离'));
// 市场结构没有任何信号
reset(); fundBull(); updateOverallAlert();
check('★市场结构完全没有信号(基差也没填)：direction=null，面板"暂无信号"', window._structureSystem.direction === null && window._structureSystem.n === 0 && makeEl('resonanceContent').innerHTML.includes('市场结构暂无信号'));
// 基本面不含市场结构：即使市场结构极端，也不影响基本面方向
reset(); fundBull(); const dirNoStruct = (updateOverallAlert(), window._fundamentalPure.direction, window._fundamentalPure.ratio);
reset(); fundBull(); stBear(); updateOverallAlert();
check('★基本面(仅供需)的净倾向不受市场结构影响：加上三个偏空的市场结构票，基本面ratio不变', window._fundamentalPure.ratio === dirNoStruct);
// 与总分的差别
check('★顶部总分(含市场结构票)被三个偏空的市场结构票拉低，而纯基本面不受：纯基本面+85% > 总分+50%——这正是要分开看的原因', (function(){ const m = makeEl('alertContent').innerHTML.match(/净倾向([+-]?\d+)%/); const head = m ? parseInt(m[1]) : null; return head !== null && Math.round(window._fundamentalPure.ratio*100) === 85 && head === 50 && head < window._fundamentalPure.ratio*100; })());

// 基本面数据不足：null
reset(); makeEl('m_crush').value='35'; makeEl('m_basis').value='-100'; window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null; window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
updateOverallAlert();
check('★数据不足分支(总票数<5)：两个系统都置空，不沿用上次', window._fundamentalPure === null && window._structureSystem === null);
// 纯基本面票数不足(总票数够，但供需票<5)：基本面方向null，面板"数据不足"
reset(); makeEl('m_basis').value='-100'; window._spreadSignal=-1; window._spreadQuality={m:1,why:''}; window._vpSignal=-1; window._vpQuality={m:1,why:''};
makeEl('m_crush').value='35'; makeEl('m_stock').value='40';                      // 供需票只有国内供应松紧+作物(0)+美豆库消比(0)+汇率(0)=4项 <5
window._psdSignal = 0; window._esrSignal = null; updateOverallAlert();
check('★总票数够(≥5)但供需票不足5项：基本面方向=null(数据不足)，不拿市场结构去凑', window._fundamentalPure.n < 5 && window._fundamentalPure.direction === null && makeEl('resonanceContent').innerHTML.includes('基本面数据不足'));


// ===================== 4. ★命名：顶部叫"综合预警"(不是"综合基本面预警")，共振面板里综合分的属性也叫"综合预警" =====================
const fs = require('fs'), path = require('path');
const SRC = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const cardHtml = SRC.slice(SRC.indexOf('id="alertCard"'), SRC.indexOf('id="alertCard"') + 700);
check('★顶部卡片有可见标题"综合预警"(此前这张卡片根本没有标题)', /card-title">📊 综合预警/.test(cardHtml));
check('★标题旁写明它是什么：供需 + 市场结构(基差/月差/量价)合起来的倾向，不是纯基本面', cardHtml.includes('供需 + 市场结构') && cardHtml.includes('基差/月差/量价') && cardHtml.includes('不是纯基本面'));
check('★标题不再叫"综合基本面预警"', !/card-title">[^<]*综合基本面预警/.test(SRC) && !cardHtml.includes('综合基本面预警'));
reset(); fundBull(); stBear(); updateOverallAlert();
const top = makeEl('alertContent').innerHTML;
check('★底部免责写"这是综合倾向(供需 + 市场结构)，不是买卖信号"，不再写"这是基本面倾向"', top.includes('这是综合倾向(供需 + 市场结构)，不是买卖信号') && !top.includes('这是基本面倾向'));
panel = makeEl('resonanceContent').innerHTML;
check('★共振面板的说明引用的是"综合预警"，并说明"所以它不是纯基本面"', panel.includes('顶部"综合预警"的总分') && panel.includes('所以它不是纯基本面') && !panel.includes('综合基本面预警'));
// 综合预警的属性(置信度/分歧/权重敏感)在共振面板里都叫"综合预警…"，不再叫"基本面…"——它们描述的是全部投票合起来的结论
window._fundamentalMeta = {confidence:'低', reasons:['有效指标只有6/12'], divergence:'供需两侧方向分歧(供给端偏空、需求端偏多)', weatherDominant:'美国作物3项偏多', robust:'结论对权重敏感(等权中性、分组等权偏多、现行偏空)'};
const rr = computeResonanceStatus('偏多','偏多',{status:'calm', label:'外资平静'}, window._fundamentalMeta);
check('★共振详情：综合预警置信度/内部供需分歧/天气主导/权重敏感，全部带"综合预警"前缀', rr.detail.includes('综合预警置信度：低') && rr.detail.includes('综合预警内部供需两侧方向分歧') && rr.detail.includes('综合预警正处于天气主导行情') && rr.detail.includes('综合预警结论对权重敏感'));
check('★共振标题的低置信度提示：综合预警置信度低，共振的可靠性打折', rr.title.includes('综合预警置信度低，共振的可靠性打折'));
check('★描述综合分属性的地方不再出现"基本面结论置信度/基本面内部/基本面正处于/基本面结论对权重敏感"(这些说的是综合分，不是纯基本面)', !/基本面结论置信度|基本面内部|基本面正处于|基本面结论对权重敏感|基本面置信度低/.test(rr.title + rr.detail));
// 防回退：扫描页面源码里的用户可见文案(去掉注释行)，不能再出现"综合基本面预警"和"这是基本面倾向"
const visibleLines = SRC.split('\n').filter(l=>!/^\s*(\/\/|<!--|\*|\/\*)/.test(l) && !/^\s+v94：|^\s+改叫/.test(l));
check('★防回退：页面源码的非注释行里没有"综合基本面预警"/"这是基本面倾向"/"基本面结论置信度"', !visibleLines.some(l=>/综合基本面预警|这是基本面倾向|基本面结论置信度/.test(l)));

// ===================== 3. 面板的兼容性(旧调用方式) =====================
window._fundamentalPure = undefined; window._structureSystem = undefined; window._fundamentalDirection = '偏空'; window._technicalDirection = '偏空';
renderResonancePanel();
panel = makeEl('resonanceContent').innerHTML;
check('★没有两个系统的数据时(旧调用/加载中)：退回旧行为，基本面用总方向，不出现"市场结构"背离框', panel.includes('基本面：偏空') && !panel.includes('背离') && panel.includes('市场结构(基差/月差/量价)：加载中'));
delete elements['resonanceContent'];
let ok = true; try{ renderResonancePanel(); }catch(e){ ok = false; }
check('没有共振面板元素时不报错', ok);
H.clearMockedMonth();
H.printSummary();
