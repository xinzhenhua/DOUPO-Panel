// ============================================================================
// 决策卡(v99)：把原来分散的 事件日历 / 三方共振 / 基本面预警 / 市场结构 / 数据健康度 合成一张卡。
//   - 顶部是一屏可读的摘要(方向+置信度 / 三方关系 / 主导驱动 / 需留意 / 未来事件 / 数据健康)，只读已有的计算结果，不做新的评分；
//   - 下面是五个折叠区块，内容容器沿用原来的id(alertContent/structureContent/resonanceContent/eventCalendarContent/healthContent)，
//     所以所有渲染函数和读这些id的测试都不用改。
// ============================================================================
const fs = require('fs'), path = require('path');
const H = require('./test_helpers');
const { makeEl, check } = H;
const SRC = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
eval(H.loadDashboardJs());
const E = window._eventCal;
const AUTO = window._autoIndicators;
const KEYS = AUTO.map(c=>c.key);

// ===================== 1. 页面结构：一张卡，五个区块 =====================
const bodyStart = SRC.indexOf('<body'), bodyEnd = SRC.indexOf('<script>');
const BODY = SRC.slice(bodyStart, bodyEnd);
const dc0 = BODY.indexOf('id="decisionCard"');
check('★页面里有一张决策卡(id=decisionCard)', dc0 > 0);
// 决策卡的范围：从它的起点到下一个顶层区块(天气板块)的起点
const dcEnd = BODY.indexOf('id="group-us-weather"');
const DC = BODY.slice(dc0, dcEnd);
for (const id of ['decisionSummary','alertContent','structureContent','resonanceContent','eventCalendarContent','healthContent','healthBadge']){
  check(`★原容器 ${id} 在决策卡里(沿用原id，渲染函数和测试不用改)`, DC.includes(`id="${id}"`));
}
check('★五个区块都是折叠区(<details>)：基本面预警、市场结构、三方关系、近期事件、数据健康度', (DC.match(/<details class="dc-sec"/g) || []).length === 5);
for (const old of ['eventCalendarCard','resonanceCard','alertCard','structureCard','healthCard']){
  check(`★旧的顶层独立卡 ${old} 已经不存在(合并进决策卡了，不是在旁边多出一张)`, !BODY.includes(`id="${old}"`));
}
check('决策卡在合约选择/上下文之后、天气板块之前(DOM顺序)', dc0 > BODY.indexOf('id="contractContext"') && dc0 < BODY.indexOf('id="group-us-weather"'));
check('★顶层只剩一张"决策卡"：从上下文卡到天气板块之间，没有别的 class="card" 顶层卡', (BODY.slice(BODY.indexOf('id="contractContext"') + 20, BODY.indexOf('id="group-us-weather"')).match(/<div class="card"/g) || []).length === 1);
check('摘要容器在五个区块之前(先看结论再看依据)', DC.indexOf('id="decisionSummary"') < DC.indexOf('<details class="dc-sec"'));

// ===================== 辅助 =====================
const html = k=>makeEl('ai_'+k).innerHTML;
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); });
  window._indState = {}; ['alertContent','structureContent','resonanceContent','eventCalendarContent','healthContent','healthBadge','decisionSummary'].forEach(makeEl);
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
  window._selectedContract='sep'; window._syncedData = null; window._technicalDirection = undefined; window._foreignActivity = undefined;
}
const NOW = E.bjToMs(2026,9,30,10,0);
const sum = ()=>makeEl('decisionSummary').innerHTML;
const text = ()=>sum().replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');

// ===================== 2. 主导驱动：生效权重降序取前3 =====================
// 场景(手算)：作物(天气high)权重…用显式票：国内供应松紧(库消比9%→偏多，权重2)、猪粮比偏多(1)、肉鸡利润偏多(1)、美豆库消比信号(1)、汇率信号(1)、豆菜粕价差手填700.1→偏空(1)
reset(); window._nowMs = NOW;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = -1; makeEl('m_rmspread').value='800';
updateOverallAlert();
const drivers = window._topDrivers;
check('★导出了主导驱动列表(最多3个)，每个带标签/信号/生效权重', Array.isArray(drivers) && drivers.length === 3 && drivers.every(d=>d.label && (d.signal === 1 || d.signal === -1) && typeof d.weight === 'number'));
check('★第一名是权重最大的"国内豆粕供应松紧 ×2"(页面自己的标签带×2；权重2)；其余按生效权重降序，同权重保持投票顺序', drivers[0].label === '国内豆粕供应松紧 ×2' && drivers[0].weight === 2 && drivers[1].weight <= drivers[0].weight && drivers[2].weight <= drivers[1].weight);
check('★同权重(1)的票保持投票顺序：库存消费比(美豆)在人民币汇率之前(addVote的先后)，不是按标签/字母顺序', drivers[1].label === '库存消费比(美豆)' && drivers[2].label === '人民币汇率');
check('★驱动里没有信号为null/0的票(中性的不算"驱动")', drivers.every(d=>d.signal !== 0 && d.signal !== null));
check('★驱动只来自供需票，不含市场结构票(基差/月差/量价)', drivers.every(d=>!/基差|月差|量价/.test(d.label)));
check('摘要里"主导驱动"行按这个顺序列出，写明多空箭头(偏多▲/偏空▼)，权重只显示一次(标签自己带的×2，不再额外重复)', /主导驱动/.test(text()) && text().indexOf('国内豆粕供应松紧') < text().indexOf(drivers[1].label) && text().includes('国内豆粕供应松紧 ×2 ▲') && text().includes('人民币汇率 ▼') && !/×2 ▲\s*×2/.test(text()));

// 天气开关打开时，作物票权重×2、其余票×0.5：驱动按生效权重排，所以作物票排到前面。
// ★开关要求：作物综合=偏多 且 该季节档位不是背景档 且 ≥3个可用信号里≥3个偏多。9月底美国作物对9月合约是背景档(开关不会开)，
//   所以这里把时钟固定在7月15日(美国天气对9月合约是主导档)——我上一版没想到这点，场景在9月底构造，开关根本没打开。
H.setMockedMonth(7);
reset(); window._nowMs = E.bjToMs(2026,7,15,10,0); window._selectedContract = 'sep';
window._weatherRisk='high'; window._droughtSignal=1; window._noaaOutlookSignal=1; window._soyCondSignal=1;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3';
updateOverallAlert();
const dw = window._topDrivers;
check('前置：天气开关确实打开了(否则下面的断言没意义)', !!window._weatherDominant);
check('★天气开关打开(作物×2、其余×0.5)：驱动按生效权重——作物票(权重2)排第一，"国内供应松紧"的生效权重是1(2×0.5)，不再排第一', /天气|产量|作物|美国/.test(dw[0].label) && dw[0].weight === 2 && dw.find(d=>/国内豆粕供应松紧/.test(d.label)).weight === 1);
H.clearMockedMonth();

// 驱动不足3个/没有
reset(); window._nowMs = NOW; window._psdSignal = 1; updateOverallAlert();
check('有信号的票不足3个：有几个列几个，不凑数', window._topDrivers === null || window._topDrivers.length === 0 || window._topDrivers.length <= 1);

// ===================== 3. 方向+置信度(第一行) =====================
reset(); window._nowMs = NOW;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = 1; makeEl('m_crush').value='30'; makeEl('m_rmspread').value='300';
updateOverallAlert();
const pure = window._fundamentalPure;
check('★第一行：基本面方向、净倾向%、置信度——与顶部预警同源(_fundamentalPure/_fundamentalConfidence)', text().includes(`基本面${pure.direction}`) && text().includes(`${Math.round(pure.ratio*100)}%`) && text().includes(`置信度：${window._fundamentalConfidence}`));
check('方向用颜色/样式类区分(偏多/偏空/中性)', /dc-(bull|bear|neutral)/.test(sum()));

// 基本面数据不足
reset(); window._nowMs = NOW; makeEl('m_basis').value = '-100'; updateOverallAlert();
check('★基本面数据不足：第一行写"数据不足"，不显示净倾向/置信度，也不崩', text().includes('基本面数据不足') && !/置信度：/.test(text()) && !/净倾向/.test(text()));

// ===================== 4. 需留意(≤3条，来自meta) =====================
reset(); window._nowMs = NOW;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = 1; makeEl('m_crush').value='30';
updateOverallAlert();
window._fundamentalMeta = {confidence:'低', reasons:['x'], divergence:'供需两侧方向分歧(供给端偏空、需求端偏多)', weatherDominant:'美国作物3项偏多', robust:'结论对权重敏感(等权中性、分组等权偏多、现行偏空)'};
renderDecisionSummary();
const t4 = text();
check('★需留意：列出供需分歧、天气主导、权重敏感三条(各带⚠)，最多3条', /需留意/.test(t4) && t4.includes('基本面内部供需两侧方向分歧') && t4.includes('天气主导行情(美国作物3项偏多)') && t4.includes('结论对权重敏感') && (sum().match(/⚠/g) || []).length === 3);
window._fundamentalMeta = {confidence:'高', reasons:['x']};
renderDecisionSummary();
check('★没有任何提示时写"无"(不留空行)', /需留意\s*无/.test(text()));
window._fundamentalMeta = {confidence:'低', divergence:'A', weatherDominant:'B', robust:'C', extra:'D'};
renderDecisionSummary();
check('最多3条：即使meta里有更多也只取前3(分歧→天气→权重敏感)', (sum().match(/⚠/g) || []).length === 3);

// ===================== 5. 三方关系行 =====================
reset(); window._nowMs = NOW;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = 1; makeEl('m_crush').value='30';
window._technicalDirection = '偏空'; window._foreignActivity = {status:'quiet', label:'本次未侦测到已确认外资机构进入前20名榜单'};      // 真实的status只有active/quiet/unavailable(我之前编了个'calm')
updateOverallAlert();
check('★三方行：技术面/基本面/市场结构/外资 四个都写出，来自各自的导出变量', text().includes('技术面 偏空') && text().includes(`基本面 ${window._fundamentalPure.direction}`) && /市场结构 (偏多|偏空|中性|暂无信号|加载中)/.test(text()) && text().includes('外资 平静'));
reset(); window._nowMs = NOW; updateOverallAlert();
check('技术面/外资还没加载时写"加载中"/"—"，不崩', text().includes('技术面 加载中') && /外资 —/.test(text()));

// ===================== 6. 未来事件 =====================
// 固定时钟2026-09-30 10:00(北京)：未来14天内有国庆休市开始(10-01)、恢复(10-08)，以及若干美国报告/每周例行
reset(); window._nowMs = NOW; updateOverallAlert();
const evLine = (text().match(/未来事件(.*?)(数据|$)/) || [])[1] || '';
const expectEv = buildEventList(NOW, NOW + 14*86400000).filter(e=>e.ms >= NOW).slice(0,3);
check('★未来事件每一行都带日期(月-日 时:分)：上一版把日期截没了，只剩"20:30 美国出口销售周报"，看不出是哪天', expectEv.length === 3 && expectEv.every(e => evLine.includes(e.label)) && /10-01 00:00/.test(evLine));
check('★未来事件：取14天内最近的3个，按时间顺序，与事件日历(buildEventList)同源', expectEv.length === 3 && expectEv.every(e => evLine.includes(e.title.replace(/\(.*\)/,'').trim().slice(0,6))) && evLine.indexOf(expectEv[0].title.replace(/\(.*\)/,'').trim().slice(0,6)) < evLine.indexOf(expectEv[2].title.replace(/\(.*\)/,'').trim().slice(0,6)));
// ★"已经过去的事件不列"要在一个真正有已过去事件的时钟下测(上一版固定在09-30 10:00，窗口里根本没有早于现在的事件，
//   那条前置检查被写成了恒为真的断言——掩盖了"这个行为完全没被测到")。时钟设在10-01 12:00(北京)：
//   10-01 00:00的两个事件(美国季度库存、大商所国庆节休市开始)已经过去；未来最近3个是ESR(10-01 20:30)、COT(10-03 03:30)、作物进度(10-06 04:00)。
const NOW2 = E.bjToMs(2026,10,1,12,0);
const win2 = buildEventList(NOW2 - 86400000, NOW2 + 14*86400000);
check('★前置(手算)：这个时钟下窗口里确实有已过去的事件(10-01 00:00的两个)，所以"不列已过去的"这条过滤是有意义的', win2.filter(e=>e.ms < NOW2).length === 2 && win2.filter(e=>e.ms < NOW2).every(e => e.label === '10-01 00:00'));
reset(); window._nowMs = NOW2; updateOverallAlert();
const evLine2 = (text().match(/未来事件(.*?)数据/) || [])[1] || '';
check('★已过去的事件(季度库存、国庆休市开始)不出现在摘要里', !evLine2.includes('季度库存') && !evLine2.includes('休市开始'));
check('★摘要列的是未来最近3个：ESR(10-01)、COT(10-03)、作物进度(10-06)，按时间顺序', evLine2.indexOf('出口销售周报') >= 0 && evLine2.indexOf('出口销售周报') < evLine2.indexOf('CFTC') && evLine2.indexOf('CFTC') < evLine2.indexOf('作物进度') && !evLine2.includes('恢复交易'));

// ===================== 7. 数据健康(与健康度区块同一份计算) =====================
reset(); window._nowMs = NOW; window._syncedData = {generatedAt:new Date(NOW - 3600000).toISOString()};
updateOverallAlert();
const hh = computeDataHealth(NOW);
check('★数据行：同步状态文字与computeDataHealth一致，颜色点与level一致', text().includes(hh.sync.label.slice(0, 8)) && sum().includes(hh.level === 'red' ? '🔴' : hh.level === 'yellow' ? '🟡' : '🟢'));
check('★缺席投票数写出来：与_quality.missing的数量一致', hh.missing.length === 0 || text().includes(`缺席投票${hh.missing.length}项`));
// 同步停了(很久之前生成)：红色
reset(); window._nowMs = NOW; window._syncedData = {generatedAt:new Date(NOW - 12*86400000).toISOString()};
updateOverallAlert();
check('★同步停了(12天前)：数据行是🔴，写明同步可能已停止', sum().includes('🔴') && text().includes('同步可能已停止'));

// ===================== 8. 合并没有改变任何折叠区块里的内容 =====================
reset(); window._nowMs = NOW;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = 1; makeEl('m_crush').value='30';
updateOverallAlert();
check('★折叠区块里仍是原来的渲染：基本面预警区块有"基本面偏多/偏空/信号混合"的结论框和维度条', /基本面偏多|基本面偏空|信号混合/.test(makeEl('alertContent').innerHTML) && makeEl('alertContent').innerHTML.includes('class="dim-row"'));
check('★市场结构区块、三方关系区块、健康度区块都有内容(不是"等待数据"占位)', makeEl('structureContent').innerHTML.length > 50 && makeEl('resonanceContent').innerHTML.length > 50 && makeEl('healthContent').innerHTML.length > 50);

// ===================== 9. 摘要不影响评分 =====================
const before = JSON.stringify([window._fundamentalPure, window._composite, window._structureSystem]);
renderDecisionSummary(); renderDecisionSummary();
check('★摘要只读不写：反复渲染不改变任何评分导出(_fundamentalPure/_composite/_structureSystem)', JSON.stringify([window._fundamentalPure, window._composite, window._structureSystem]) === before);

// ===================== 10. 变异检查补的盲区(期望值手算) =====================
// 10a. 驱动只来自供需票：★原场景里市场结构票没有信号，带不带都一样。让基差有方向(-100→偏空)、月差偏多、量价偏多，且权重(1)与供需票并列
reset(); window._nowMs = NOW;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = 1;
makeEl('m_basis').value = '-100'; window._spreadSignal = 1; window._spreadQuality = {m:1, why:''};
updateOverallAlert();
check('前置：市场结构有信号(基差偏空、月差偏多)，且在全部投票里确实有这些票——所以"驱动不含结构票"这条断言有意义', window._structureSystem.n >= 2 && window._structureSystem.direction !== null);
check('★驱动里没有现货基差/月差/量价：即使它们有方向、权重(1)与供需票并列，也不进驱动', window._topDrivers.length === 3 && window._topDrivers.every(d => !/基差|月差|量价/.test(d.label)) && !text().match(/主导驱动.*(现货基差|月差)/));
window._spreadSignal = undefined; window._spreadQuality = undefined;

// 10b. 驱动按"生效权重"而不是"基础权重"排：天气开关打开时(7月，9月合约)，作物票×2不变，其余×0.5。
//      构造让两种口径排出不同的第1名：国内供应松紧基础权重2→生效1；若按基础权重，它(2)仍排在生效权重为1的"猪粮比"之前并列第一名之后…
//      手算：生效权重 作物=2、国内供应松紧=1、猪粮比=0.5、肉鸡=0.5…；按基础权重 作物=2(作物组基础权重也是2? )——用页面导出的baseWeight直接对拍排序差异
H.setMockedMonth(7);
reset(); window._nowMs = E.bjToMs(2026,7,15,10,0); window._selectedContract = 'sep';
window._weatherRisk='high'; window._droughtSignal=1; window._noaaOutlookSignal=1; window._soyCondSignal=1;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1;
updateOverallAlert();
const dd = window._topDrivers;
check('前置：天气开关打开', !!window._weatherDominant);
check('★生效权重(含天气开关×0.5)：驱动列表里的权重是生效值——"国内豆粕供应松紧 ×2"的权重是1(基础2×0.5)，猪粮比是0.5(基础1×0.5)', dd.find(d=>/国内豆粕供应松紧/.test(d.label)).weight === 1 && dd.every(d => d.weight <= 2) && (dd.find(d=>d.label === '猪粮比') || {weight:0.5}).weight === 0.5);
check('★排序按生效权重降序：每个相邻驱动的权重不增', dd.every((d, i) => i === 0 || dd[i-1].weight >= d.weight));
H.clearMockedMonth();

// 10c. 基本面数据不足时摘要不列"主导驱动"(顶部预警明确说不下结论，这里不能自相矛盾)——原来只断言了第一行
// ★上一版以为m_stu+_psdSignal只有2个有效票，实际默认来源(天气/汇率等)也贡献票，有效票=5恰好够——前置检查拦住了。
//   真正的"数据不足"：只填一个供需票(美豆库消比信号)，其余全空。
reset(); window._nowMs = NOW; window._psdSignal = 1; updateOverallAlert();
check('前置：基本面数据不足(供需有效票<5)，且仍有1个有方向的票(_topDrivers有内容)——所以"数据不足时不列驱动"这条断言有意义', window._fundamentalPure.direction === null && window._fundamentalPure.n < 5 && Array.isArray(window._topDrivers) && window._topDrivers.length >= 1);
check('★基本面数据不足：摘要里没有"主导驱动"这一行，也没有"需留意"里的基本面提示(不自相矛盾)', !text().includes('主导驱动') && text().includes('基本面数据不足'));

// 10d. 颜色约定：红=偏多、绿=偏空(页面其它地方都是这样)；摘要的样式类必须一致
reset(); window._nowMs = NOW;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = 1; makeEl('m_crush').value='30';
updateOverallAlert();
check('★偏多的头部用dc-bull(红系)，且不是dc-bear', window._fundamentalPure.direction === '偏多' && /class="dc-head dc-bull"/.test(sum()) && !/class="dc-head dc-bear"/.test(sum()));
check('★偏多的驱动用dc-bullt(红)，偏空的驱动用dc-beart(绿)：构造1个偏多驱动+1个偏空驱动', (function(){
  reset(); window._nowMs = NOW; makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = -1; updateOverallAlert();
  return /<span class="dc-bullt">国内豆粕供应松紧 ×2 ▲<\/span>/.test(sum()) && /<span class="dc-beart">人民币汇率 ▼<\/span>/.test(sum());
})());
reset(); window._nowMs = NOW;
makeEl('m_stu').value='20'; makeEl('m_hogratio').value='4'; makeEl('m_poultry').value='-3'; window._psdSignal = -1; window._fxSignal = -1; makeEl('m_crush').value='70';
updateOverallAlert();
check('★偏空的头部用dc-bear(绿系)，且不是dc-bull', window._fundamentalPure.direction === '偏空' && /class="dc-head dc-bear"/.test(sum()) && !/class="dc-head dc-bull"/.test(sum()));

// 10e. ★生效权重(基础权重×质量系数)排序 vs 基础权重排序：变异检查发现原场景里两种口径排出的前3相同。
//      手算：国内豆粕供应松紧 基础权重2，让它质量差(晚了一期×0.5 且是估算×0.5 → q=0.25)，生效权重=2×0.25=0.5；
//      猪粮比 基础权重1、质量正常，生效权重=1。按基础权重排：供应松紧(2)>猪粮比(1)；按生效权重排：猪粮比(1)>供应松紧(0.5)。
reset(); window._nowMs = NOW;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = 1;
window._indState.stu = {mode:'manual', late:true, estimated:'估算值'};
updateOverallAlert();
const de = window._topDrivers;
const iTight = de.findIndex(d=>/国内豆粕供应松紧/.test(d.label)), iHog = de.findIndex(d=>d.label === '猪粮比');
check('前置(手算)：供应松紧质量差后生效权重=0.5(基础2×q0.25)，猪粮比生效权重=1', (iTight < 0 || de[iTight].weight === 0.5) && (iHog < 0 || de[iHog].weight === 1));
check('★按生效权重排序：猪粮比(生效1)排在质量差的国内供应松紧(基础2但生效0.5)之前——按基础权重排会反过来', iHog >= 0 && (iTight < 0 || iHog < iTight));
check('★质量差的高基础权重票不再排第一：第一名的生效权重≥1', de[0].weight >= 1 && !/国内豆粕供应松紧/.test(de[0].label));

// 10f. ★驱动不含结构票：让结构票的数量大于供需有方向的票，且权重并列，若误含则会挤进列表。
//      手算：只设2个有方向的供需票(美豆库消比psd=+1、汇率fx=+1)；结构票3个有方向(基差-100偏空、月差偏多、量价偏多)，各权重1。
//      正确实现：_topDrivers只有供需票(最多2个~3个，取决于默认来源)；误含结构票会出现基差/月差/量价。
reset(); window._nowMs = NOW;
window._psdSignal = 1; window._fxSignal = 1;
makeEl('m_basis').value = '-100'; window._spreadSignal = 1; window._spreadQuality = {m:1, why:''}; window._vpSignal = 1;
updateOverallAlert();
const ds = window._topDrivers || [];
check('前置：市场结构有方向的票(基差/月差等)确实存在，且数量≥2', (window._structureSystem || {n:0}).n >= 2);
check('★驱动里没有任何结构票(现货基差/月差/量价)——即使它们有方向、权重与供需票并列、总数不足3个供需驱动', ds.length >= 1 && ds.every(d => !/基差|月差|量价/.test(d.label)));
window._spreadSignal = undefined; window._spreadQuality = undefined; window._vpSignal = undefined;

// ===================== 11. 渲染真实页面时发现的3个问题(期望值手算) =====================
// 11a. 置信度只在有方向(偏多/偏空)时才有；"信号混合"时_fundamentalConfidence为null(原设计：没结论就谈不上置信度)。
//      摘要不能写"置信度：—"(像是没算出来)，应该直接不写。
reset(); window._nowMs = NOW;
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = 1; makeEl('m_crush').value='30';
updateOverallAlert();
check('前置：有方向的场景(偏多)置信度是高/中/低', window._fundamentalPure.direction === '偏多' && ['高','中','低'].includes(window._fundamentalConfidence));
check('★有方向：头部写"置信度：X"', new RegExp(`置信度：${window._fundamentalConfidence}`).test(text()));
reset(); window._nowMs = NOW;
makeEl('m_stu').value='12'; makeEl('m_hogratio').value='6'; makeEl('m_poultry').value='1'; window._psdSignal = 0; window._fxSignal = 0;
updateOverallAlert();
check('前置：信号混合(中性)时置信度是null', window._fundamentalPure.direction === '中性' && window._fundamentalConfidence === null);
check('★信号混合：头部写"信号混合"，**不写**"置信度"(不是"置信度：—")', text().includes('基本面信号混合') && !text().includes('置信度') && !/置信度：\s*—/.test(text()));

// 11b. 数据行：同步状态和指标异常分开写，不能出现"🔴 同步正常"这种自相矛盾
//      手算场景：同步1小时前(正常)，但有1个投票指标不可用(bad=1，整体level=red)
reset(); window._nowMs = NOW; window._syncedData = {generatedAt:new Date(NOW - 3600000).toISOString()};
makeEl('m_stu').value='9'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='3'; window._psdSignal = 1; window._fxSignal = 1;
window._indState.crush = {mode:'none', failReason:'抓取失败'};
updateOverallAlert();
const h1 = computeDataHealth(NOW);
check('前置：同步正常，但整体level=red(有指标不可用)——这正是原先会写出"🔴 同步正常"的情形', h1.sync.state === 'ok' && h1.level === 'red' && h1.bad >= 1);
const dataLine = (text().match(/数据(.*)$/) || [])[1] || '';
check('★同步状态用同步自己的图标(🟢同步正常)，不被指标异常染红', /🟢[^🔴🟡]*同步正常/.test(sum().replace(/<[^>]+>/g,'')) && !/🔴\s*同步正常/.test(sum().replace(/<[^>]+>/g,'')));
check('★指标异常单独一段：写"指标：N项不可用"，且带自己的红点(与同步段的🟢分开)', new RegExp(`🔴 指标[^🟢🟡]*${h1.bad}项不可用`).test(sum().replace(/<[^>]+>/g,'')));
// 一切正常：指标写"正常"
reset(); window._nowMs = NOW; window._syncedData = {generatedAt:new Date(NOW - 3600000).toISOString()};
updateOverallAlert();
const h0 = computeDataHealth(NOW);
// 默认的空场景里很多指标没有数据，不会"全部正常"——所以显式构造一个"指标全部正常"的场景太重；改为直接对拍：bad=0且warn=0时写"指标正常"，否则不写
// (原'指标段与computeDataHealth一致'那条因默认场景里指标不全正常、'指标正常'分支根本没跑到，已被下面11d的受控版本取代)
// 同步停了(12天前)：同步段🔴；指标段独立
reset(); window._nowMs = NOW; window._syncedData = {generatedAt:new Date(NOW - 12*86400000).toISOString()};
updateOverallAlert();
check('★同步停了：同步段是🔴"同步可能已停止"(同步自己的状态，不是指标的)', /🔴\s*同步可能已停止/.test(sum().replace(/<[^>]+>/g,'')));

// 11c. 外资只写短状态，不塞整句(整句仍在三方关系区块里)
for (const [fa, want] of [[{status:'quiet', label:'本次未侦测到已确认外资机构进入前20名榜单'}, '平静'], [{status:'active', isGoldman:true, label:'高盛期货出现在净多头榜(+2,181手)'}, '高盛活跃'],
                          [{status:'active', isGoldman:false, label:'CFTC基金净持仓增仓12,000手'}, '外资活跃'], [{status:'unavailable', label:'x'}, '数据不可用']]){
  reset(); window._nowMs = NOW; window._foreignActivity = fa; updateOverallAlert();
  const line = (text().match(/三方(.*?)主导驱动|三方(.*?)需留意/) || [])[0] || text();
  check(`★外资${fa.status}${fa.isGoldman ? '(高盛)' : ''}：三方行只写"外资 ${want}"，不塞整句(${fa.label.slice(0,8)}…)`, text().includes(`外资 ${want}`) && !text().includes(fa.label));
}
reset(); window._nowMs = NOW; window._foreignActivity = undefined; updateOverallAlert();
check('外资还没加载：写"外资 —"，不崩', text().includes('外资 —'));

// 11d. ★变异检查发现：原来"指标正常"那条因为默认场景里指标不是全正常而根本没跑到；同步段的颜色类也没被断言。
//      用受控的健康度(临时替换computeDataHealth)精确构造各种状态，逐个断言——比搭一个真实的全绿页面可靠。
const realHealth = computeDataHealth;
function withHealth(h, fn){ computeDataHealth = ()=>h; try{ renderDecisionSummary(); return fn(); } finally{ computeDataHealth = realHealth; } }
const S = (state, icon, label)=>({state, icon, label});
const base = {rows:[], counts:{}, level:'green', bad:0, warn:0, missing:[], quality:1};
reset(); window._nowMs = NOW; updateOverallAlert();
let r1 = withHealth(Object.assign({}, base, {sync:S('ok','🟢','同步正常：2026-09-30 09:00(1小时前)')}), ()=>({txt:text(), html:sum()}));
check('★全部正常(同步ok、bad=0、warn=0、无缺席)：写"🟢 同步正常…"和"🟢 指标正常"，且都用绿色类', /🟢 同步正常/.test(r1.txt) && /🟢 指标正常/.test(r1.txt) && /class="dc-good">🟢 同步正常/.test(r1.html) && /class="dc-good">🟢 指标正常/.test(r1.html));
let r2 = withHealth(Object.assign({}, base, {level:'yellow', warn:2, missing:['a','b','c'], sync:S('degraded','🟡','同步晚了：2026-09-28 15:05(2天前)，错过2个交易日')}), ()=>({txt:text(), html:sum()}));
check('★同步晚了(degraded)：同步段🟡且用黄色类dc-warn；指标段🟡写"2项降权/手动、缺席投票3项"，用dc-warn', /class="dc-warn">🟡 同步晚了/.test(r2.html) && /class="dc-warn">🟡 指标：2项降权\/手动、缺席投票3项/.test(r2.html));
let r3 = withHealth(Object.assign({}, base, {level:'red', bad:1, warn:1, missing:['a'], sync:S('stale','🔴','同步可能已停止：2026-09-20 15:05(12天前)，错过8个交易日')}), ()=>({txt:text(), html:sum()}));
check('★同步停了(stale)：同步段🔴且用红色类dc-bad；指标段🔴写"1项不可用、1项降权/手动、缺席投票1项"，用dc-bad', /class="dc-bad">🔴 同步可能已停止/.test(r3.html) && /class="dc-bad">🔴 指标：1项不可用、1项降权\/手动、缺席投票1项/.test(r3.html));
let r4 = withHealth(Object.assign({}, base, {sync:S('nodata','⚪','还没有读到同步数据(data/latest.json)')}), ()=>({txt:text(), html:sum()}));
check('★没有同步数据(nodata)：同步段用⚪和dc-bad(不是绿色)，指标段独立写"指标正常"', /class="dc-bad">⚪ 还没有读到同步数据/.test(r4.html) && /🟢 指标正常/.test(r4.txt));
// 恢复真实函数后摘要照常
reset(); window._nowMs = NOW; updateOverallAlert();
check('恢复真实computeDataHealth后摘要照常渲染(桩没有泄漏到后面)', typeof computeDataHealth === 'function' && computeDataHealth === realHealth && /数据/.test(text()));

H.printSummary();
