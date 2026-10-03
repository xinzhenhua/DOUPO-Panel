// ============================================================================
// 月差/期限结构：卡片、分位信号(正负本身不是信号)、进评分/分组/市场结构维度、新鲜度、合约切换
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
const E = window._eventCal;
const AUTO = window._autoIndicators;
makeEl('spreadBadge'); makeEl('spreadContent');
const dayAgo = n=>new Date(Date.now()-n*86400000).toISOString().slice(0,10);
const base = {available:true, contractMonth:9, date:dayAgo(0), datesAligned:true, nearSymbol:'M2609', nearPrice:3000, farSymbol:'M2701', farPrice:3100,
  spread:-100, spreadPct:-3.33, source:'测试'};
const withSeasonal = (pct, n, o)=>Object.assign({}, base, {history:{n:800, minPoints:12, since:'2018-04-02', percentile:pct, min:-8, max:6, median:-2, sparse:null, window:null, cohort:null,
  seasonal:{month:7, n:n===undefined?160:n, percentile:pct, median:-2}}}, o||{});
const html = ()=>makeEl('spreadContent').innerHTML;
const headline = ()=>((html().match(/<span class="at">([^<]*)<\/span>/)||[])[1]||'');      // 只取卡片的结论行(详情里的静态说明同时含偏多/偏空字样)

// ===================== 1. 分位信号 =====================
check('★月差偏高(≥80%分位)：偏多(+1)——近月对远月升水比往年更大=近端偏紧', spreadSignalFrom(withSeasonal(85)) === 1);
check('★月差偏低(≤20%分位)：偏空(-1)——远月升水比往年更深=近端宽松', spreadSignalFrom(withSeasonal(10)) === -1);
check('分位50%：中性', spreadSignalFrom(withSeasonal(50)) === 0);
check('边界：80%偏多、20%偏空、79.9%/20.1%中性', spreadSignalFrom(withSeasonal(80)) === 1 && spreadSignalFrom(withSeasonal(20)) === -1 && spreadSignalFrom(withSeasonal(79.9)) === 0 && spreadSignalFrom(withSeasonal(20.1)) === 0);
check('★同月样本不足20个 → null，即使分位是95%', spreadSignalFrom(withSeasonal(95, 19)) === null && spreadSignalFrom(withSeasonal(95, 20)) === 1);
check('没有history/seasonal字段 → null', spreadSignalFrom(base) === null && spreadSignalFrom({...base, history:{n:5, seasonal:null}}) === null && spreadSignalFrom(null) === null);
check('★方向跟榨利相反：榨利越高越偏空，月差越高越偏多(近端越紧)', spreadSignalFrom(withSeasonal(95)) === 1 && crushSignalFrom({history:{seasonal:{percentile:95, n:160}}}) === -1);

// ===================== 2. ★正负本身不是信号 =====================
// 榨利的同类陷阱：粮食可储存，远月升水(contango)是持有成本造成的正常状态，月差为负≠偏空。
renderTermSpread({...base, spread:-100, spreadPct:-3.33}, new Date().toISOString());
check('★回归：远月升水(月差为负，-3.33%)、没有历史分位时，不判偏空(不是bear样式)', !html().includes('alert-box bear') && html().includes('alert-box neutral') && window._spreadSignal === null);
check('★没有历史分位时说明"暂不计分(月差的正负本身不是信号)"', html().includes('样本积累中') && html().includes('正负本身不是信号') && html().includes('暂不计入综合评分'));
renderTermSpread({...base, spread:120, spreadPct:4.0}, new Date().toISOString());
check('★回归：近强远弱(月差为正，+4.0%)、没有历史分位时，同样不判偏多(不是bull样式)', !html().includes('alert-box bull') && window._spreadSignal === null);
check('结构描述是事实：为正写"近强远弱(backwardation)"，为负写"远强近弱(contango，远月升水)"', html().includes('近强远弱(backwardation)'));
renderTermSpread({...base, spread:-100, spreadPct:-3.33}, new Date().toISOString());
check('为负：写"contango，远月升水"', html().includes('contango，远月升水'));
check('★状态=pending(数据在，历史样本积累中)', window._spreadStatus === 'pending');

// ===================== 3. 有历史 → 判方向 =====================
renderTermSpread(withSeasonal(90), new Date().toISOString());
check('★分位90%：偏多(bull)，写明"近月对远月的升水比往年更大，近端偏紧"，参与综合评分', window._spreadSignal === 1 && html().includes('alert-box bull') && html().includes('近端偏紧') && html().includes('90%分位') && html().includes('参与综合评分') && window._spreadStatus === 'ok');
check('★偏多的结论行说的是"历史同期高位"(不是低位)，方向词是"偏多"(不是偏空)', headline().includes('历史同期高位') && !headline().includes('历史同期低位') && headline().endsWith('近端偏紧，偏多') && !headline().includes('偏空'));
renderTermSpread(withSeasonal(8), new Date().toISOString());
check('★分位8%：偏空(bear)，写明"远月升水比往年更深，近端供应宽松"', window._spreadSignal === -1 && html().includes('alert-box bear') && html().includes('近端供应宽松'));
check('★偏空的结论行说的是"历史同期低位"(不是高位)，方向词是"偏空"(不是偏多)', headline().includes('历史同期低位') && !headline().includes('历史同期高位') && headline().endsWith('近端供应宽松，偏空') && !headline().includes('偏多'));
renderTermSpread(withSeasonal(50), new Date().toISOString());
check('分位50%：常态区间', window._spreadSignal === 0 && html().includes('常态区间'));
check('★卡片写明为什么用百分比(不同年份价格水平不同)', html().includes('占近月价格的百分比') && html().includes('2500 vs 4000'));
check('详情里显示历史分位块', html().includes('历史分位(该合约建议交易窗口)'));
check('三种合约的标签：9→9-1、5→5-9、1→1-5', (renderTermSpread(withSeasonal(50), ''), html().includes('9-1月差')) && (renderTermSpread(withSeasonal(50,160,{contractMonth:5}), ''), html().includes('5-9月差')) && (renderTermSpread(withSeasonal(50,160,{contractMonth:1}), ''), html().includes('1-5月差')));

// ===================== 4. 不可用/新鲜度 =====================
renderTermSpread({available:false, reason:'以下合约价格缺失，无法计算月差: 远月M2701(接口失败)'}, new Date().toISOString());
check('★不可用：显示原因(点名缺的合约)，状态=unavailable，信号null', html().includes('远月M2701') && window._spreadStatus === 'unavailable' && window._spreadSignal === null);
renderTermSpread(null, new Date().toISOString());
check('传null不报错，有兜底文字', html().includes('未知原因'));
renderTermSpread({...withSeasonal(90), date: dayAgo(30)}, new Date().toISOString());
check('★盘面数据30天前：过期，不判方向，写明原因', window._spreadSignal === null && window._spreadStatus === 'stale' && html().includes('已过期') && html().includes('不参与评分'));
renderTermSpread({...withSeasonal(90), date: undefined}, new Date().toISOString());
check('数据日期未知：当作正常，仍判方向', window._spreadSignal === 1);
window._nowMs = E.bjToMs(2026,9,30,10,0);
renderTermSpread({...withSeasonal(90), date:'2026-09-25'}, new Date().toISOString());
check('★盘面数据晚了一期(错过2个交易日)：信号仍在，质量乘数×0.5', window._spreadSignal === 1 && window._spreadQuality.m === 0.5 && window._spreadQuality.why.includes('晚了一期'));
renderTermSpread({...withSeasonal(90), date:'2026-09-29'}, new Date().toISOString());
check('数据日期昨天：乘数1', window._spreadQuality.m === 1);
window._nowMs = null;
renderTermSpread({...base, datesAligned:false, date:dayAgo(1)}, new Date().toISOString());
check('两个合约最新日期不一致：写明"以最旧的为准"', html().includes('以最旧的为准'));

// ===================== 5. 合约切换 =====================
window._syncedData = {generatedAt:new Date().toISOString(), termSpreads:{
  sep:{...base, nearSymbol:'M2609', farSymbol:'M2701', contractMonth:9}, may:{...base, nearSymbol:'M2705', farSymbol:'M2709', contractMonth:5}, jan:{available:false, reason:'测试用不可用'}}};
refreshTermSpreadForContract('sep');
check('★切换到sep：显示M2609/M2701(9-1)', html().includes('M2609') && html().includes('M2701'));
refreshTermSpreadForContract('may');
check('★切换到may：显示M2705/M2709(5-9)，不是残留sep的', html().includes('M2705') && html().includes('M2709') && !html().includes('M2609'));
refreshTermSpreadForContract('jan');
check('★切换到jan(不可用)：显示不可用原因', html().includes('测试用不可用'));
delete window._syncedData;
let ok = true; try{ refreshTermSpreadForContract('sep'); }catch(e){ ok = false; }
check('window._syncedData为空时不报错', ok);
window._syncedData = {generatedAt:'x'};
ok = true; try{ refreshTermSpreadForContract('sep'); }catch(e){ ok = false; }
check('旧版latest.json没有termSpreads字段时不报错(部署后、同步之前)', ok);


// ===================== 5b. ★真正走"点击切换合约"这条路径(不是直接调用刷新函数) =====================
['tab-sep','tab-may','tab-jan','contractContext','group-us-weather','group-sa','crushBadge','crushContent'].forEach(id=>makeEl(id));
window._syncedData = {generatedAt:new Date().toISOString(),
  crushMargins:{sep:{available:false, reason:'x'}, may:{available:false, reason:'x'}, jan:{available:false, reason:'x'}},
  termSpreads:{sep:{...base, nearSymbol:'M2609', farSymbol:'M2701', contractMonth:9}, may:{...base, nearSymbol:'M2705', farSymbol:'M2709', contractMonth:5},
               jan:{...base, nearSymbol:'M2701', farSymbol:'M2705', contractMonth:1}}};
selectContract('may');
check('★点击切换到5月合约：月差卡片自动切到M2705/M2709(5-9)', html().includes('M2705') && html().includes('M2709') && html().includes('5-9月差'));
selectContract('jan');
check('★点击切换到1月合约：月差卡片自动切到M2701/M2705(1-5)，不是残留5月的', html().includes('M2701') && html().includes('M2705') && html().includes('1-5月差') && !html().includes('M2709'));
selectContract('sep');
check('★点击切换回9月合约：M2609/M2701(9-1)', html().includes('M2609') && html().includes('9-1月差'));
// 切换合约会改变评分里的月差信号
window._syncedData.termSpreads.may = {...withSeasonal(90), nearSymbol:'M2705', farSymbol:'M2709', contractMonth:5};
window._syncedData.termSpreads.sep = {...base, nearSymbol:'M2609', farSymbol:'M2701', contractMonth:9};    // 没有历史
selectContract('sep');
check('9月合约(没有历史)：信号null', window._spreadSignal === null);
selectContract('may');
check('★切换到5月合约(有历史分位90%)：月差信号变成偏多——评分跟着合约走', window._spreadSignal === 1);

// ===================== 6. 进综合评分：市场结构维度 =====================
function resetScore(){
  AUTO.forEach(c=>{ makeEl(c.inputId).value=''; makeEl('ind_'+c.key); makeEl('alert_'+c.key); });
  window._indState = {}; makeEl('alertContent');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
  window._selectedContract='sep'; H.setMockedMonth(5);
  const fill = {crush:'50', stock:'70', basis:'0', arrival:'900', import:'900', hogratio:'6', poultry:'1', rmspread:'550'};
  Object.keys(fill).forEach(k=>makeEl('m_'+k).value = fill[k]);
  window._crushSignal = undefined;
}
const cell = ()=> (makeEl('structureContent').innerHTML.match(/sd-cell (sd-\w+)">月差\/期限结构[^<]*/)||[]);      // v97：月差在"市场结构"卡里，不在顶部
resetScore(); window._spreadSignal = undefined; updateOverallAlert();
check('★还没渲染过月差卡片(undefined)：这一票不在投票清单里(市场结构卡里没有)', !/sd-cell[^>]*>月差\/期限结构/.test(makeEl('structureContent').innerHTML));
check('★此时市场结构维度只有基差1项：标"样本少·1项"(维度里样本<2项不参与分歧判断)', window._structureSystem.n === 1 && window._structureSystem.thin === true);
resetScore(); window._spreadSignal = null; window._spreadQuality = null; updateOverallAlert();
check('★渲染过但没有信号(null，历史积累中)：这一票在清单里但没数据——作为"缺席的投票"如实列出', /sd-cell sd-empty">月差\/期限结构/.test(makeEl('structureContent').innerHTML) && window._quality.missing.some(x=>x.includes('月差/期限结构')));
resetScore(); window._spreadSignal = 1; window._spreadQuality = {m:1, why:''}; updateOverallAlert();
check('★月差偏多：市场结构卡里"月差/期限结构"是偏多格(▲)', cell()[1] === 'sd-pos' && /<th>市场结构<\/th>/.test(makeEl('structureContent').innerHTML));
check('★★有月差信号后，市场结构维度有2项(基差+月差)——不再是"样本少·1项"，可以参与"供需分歧"判断', window._structureSystem.n === 2 && window._structureSystem.thin === false);
check('★属于"市场反馈"分组(跟基差同组：都是盘面对近端供需的表态，相关性高)', voteGroup('月差/期限结构(近月-远月)') === 'feedback' && voteGroup('现货基差') === 'feedback');
check('详细理由里写明偏多原因', makeEl('alertContent').innerHTML.includes('近月对远月的升水比往年更大'));
resetScore(); window._spreadSignal = -1; window._spreadQuality = {m:1, why:''}; updateOverallAlert();
check('月差偏空：偏空格(▼)', cell()[1] === 'sd-neg');
resetScore(); window._spreadSignal = 1; window._spreadQuality = {m:0.5, why:'盘面数据晚了一期'}; updateOverallAlert();
check('★月差晚了一期：票权×0.5，质量分里点名', window._quality.lowItems.some(x=>x.label.includes('月差/期限结构') && x.q === 0.5));
// 对市场结构维度的净倾向：基差中性 + 月差偏多 → 市场结构偏多
resetScore(); window._spreadSignal = 1; window._spreadQuality = {m:1, why:''}; updateOverallAlert();
check('★基差中性(0) + 月差偏多(+1)：市场结构维度净倾向=+1÷2=+50%', Math.abs(window._structureSystem.ratio - 0.5) < 1e-9);
// 基差和月差同向偏空 → 市场结构偏空；与供给端偏多形成分歧
resetScore(); makeEl('m_basis').value = '-100'; window._spreadSignal = -1; window._spreadQuality = {m:1, why:''};
window._weatherRisk='high'; window._droughtSignal=1; window._noaaOutlookSignal=1; window._soyCondSignal=1;   // 供给端偏多
window._psdSignal=1; window._fxSignal=1; makeEl('m_stu').value='9'; makeEl('m_arrival').value='700'; makeEl('m_import').value='700';
updateOverallAlert();
check('★基差偏空 + 月差偏空：市场结构系统-100%(2项，不再是单项)', window._structureSystem.ratio === -1 && window._structureSystem.n === 2 && window._structureSystem.thin === false && window._structureSystem.direction === '偏空');
// ★v97设计变化：以前"供给端偏多 vs 市场结构偏空"会触发顶部的"方向分歧"并拉低置信度；现在顶部只含供需，分歧只在供给vs需求之间判断。
//   基本面与市场结构的背离，由市场结构卡里"与基本面的关系"专门呈现(不再扣顶部置信度)——信息没丢，只是换了位置
check('★顶部不再出现"方向分歧"(分歧只在供给vs需求之间；这里需求侧没有信号，供给端偏多)', window._dimensions.supply.dir === 1 && !makeEl('alertContent').innerHTML.includes('方向分歧'));
check('★市场结构卡里出现"背离：基本面偏多、市场结构偏空"', makeEl('structureContent').innerHTML.includes('背离：基本面偏多、市场结构偏空') && makeEl('structureContent').innerHTML.includes('市场结构偏空（净倾向-100%）'));
H.clearMockedMonth(); window._spreadSignal = undefined; window._crushSignal = undefined; window._selectedContract = 'sep';
H.printSummary();
