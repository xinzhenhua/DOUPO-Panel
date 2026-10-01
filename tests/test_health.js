// ============================================================================
// 数据健康度面板：指标状态、实时信号、评分里缺席的投票、每小时同步是否还活着
// 固定"现在"=2026-09-30(周三) 10:00 北京时间
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
const E = window._eventCal;
const AUTO = window._autoIndicators;
const at = (y,m,d,h,mi)=>E.bjToMs(y,m,d,h==null?10:h,mi||0);
const NOW = at(2026,9,30,10,0);
window._nowMs = NOW;
const ago = n=>new Date(NOW - n*86400000 + 8*3600000).toISOString().slice(0,10);
const iso = (y,m,d,h,mi)=>new Date(E.bjToMs(y,m,d,h,mi||0)).toISOString();   // 北京时间→UTC ISO
const KEYS = AUTO.map(c=>c.key);
elements['healthContent'] = makeEl('healthContent'); elements['healthBadge'] = makeEl('healthBadge');
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); });
  window._indState = {}; makeEl('alertContent');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0;
  window._esrSignal=0; window._fxSignal=0; window._psdSignal=0; window._esrQuality=null; window._esrPending=null;
  window._crushSignal=0; window._crushQuality={m:1,why:''}; window._crushStatus='ok';
  window._spreadSignal=0; window._spreadQuality={m:1,why:''}; window._spreadStatus='ok';
  window._vpSignal=0; window._vpQuality={m:1,why:''}; window._vpStatus='ok'; window._vpReason='';
  window._saWeatherSignal=null; window._saPsdSignal=null; window._plantingSignal=null; window._brlSignal=null; window._harvestSignal=null; window._brazilPlantingSignal=null;
  window._selectedContract='sep'; window._syncedData = {generatedAt: iso(2026,9,30,9,58)};
}
const row = (h,key)=>h.rows.find(r=>r.key===key);
window._selectedContract='sep'; H.setMockedMonth(5);

// ===================== 1. 同步健康度(每小时同步本身是不是还活着) =====================
const SYNC = (gen, now)=>{ window._syncedData = {generatedAt: gen}; return syncHealth(now==null?NOW:now); };
let s = SYNC(iso(2026,9,30,9,58));
check('★今天09:58同步：正常，写明时间和"2分钟前"(不满1小时用分钟)', s.state==='ok' && s.label.includes('2026-09-30 09:58') && s.label.includes('2分钟前'));
s = SYNC(iso(2026,9,30,6,58));
check('3小时前用"3小时前"', s.label.includes('3小时前'));
s = SYNC(iso(2026,9,29,15,10));
check('昨天(周二)最后一次同步：错过0~1个交易日 → 正常', s.state==='ok');
s = SYNC(iso(2026,9,28,15,10));
check('★周一同步(周三10点时只错过周二1个交易日)：仍算正常(允许1个交易日的延迟)', s.state==='ok' && s.missed===1);
s = SYNC(iso(2026,9,25,15,10));
check('★上周五同步(错过周一、周二2个交易日)：同步晚了，提示检查Actions', s.state==='degraded' && s.label.includes('错过2个交易日') && s.detail.includes('GitHub Actions'));
s = SYNC(iso(2026,9,22,15,10));
check('★9-22同步(错过5个交易日)：同步可能已停止，红色，说明"所有卡片都在变旧却看不出来"', s.state==='stale' && s.label.includes('可能已停止') && s.detail.includes('看不出来'));
// 国庆：休市期间没有同步是正常的
s = SYNC(iso(2026,9,30,17,30), at(2026,10,7,10,0));
check('★国庆期间(10-07)，最后一次同步是9-30 17:30：休市期间没有交易日、没有同步是正常的 → 同步正常(按绝对天数已经7天)', s.state==='ok' && s.missed===0);
s = SYNC(iso(2026,9,30,17,30), at(2026,10,12,10,0));
check('10-12(周一)：应有10-08、10-09的同步，都没有 → 错过2个 → 晚了', s.state==='degraded');
s = SYNC(iso(2026,9,30,9,58), at(2026,9,30,10,0)+60*3600000*24*3);
check('数据是几天前的：写"N小时前/N天前"(超过48小时改用天数)', /\d天前|小时前/.test(s.label));
window._syncedData = null; s = syncHealth(NOW);
check('还没有读到同步数据：⚪，不报错', s.state==='nodata' && s.label.includes('还没有读到'));
window._syncedData = {generatedAt:'乱码'}; s = syncHealth(NOW);
check('同步时间格式坏：⚪并显示原文，不报错', s.state==='nodata' && s.detail==='乱码');

// ===================== 2. 指标状态 =====================
reset();
const fresh = (n)=>({available:true, value:50, date:ago(n)});
window._syncedData = {generatedAt: iso(2026,9,30,9,58),
  mysteelCrushRate: fresh(3),                                   // 正常
  mysteelMealStock: {available:true, value:70, date:ago(11)},   // 周频11天：晚了一期
  mysteelBasis: {available:true, value:-100, city:'日照', date:ago(20)},   // 过期
  mysteelPoultryProfit: {available:false, reason:'搜索结果为空(测试)'}, // 无数据
  mysteelReserveAuction: {available:true, value:54.3, auctionDate:ago(3), soldWan:19.2, soldRate:37.3}}; // 事件提示
['crush','stock','basis','poultry','reserve'].forEach(k=>{ const m={crush:'refreshMysteelCrushRate',stock:'refreshMysteelMealStock',basis:'refreshMysteelBasis',poultry:'refreshMysteelPoultryProfit',reserve:'refreshMysteelReserveAuction'}; globalThis[m[k]] ? globalThis[m[k]]() : eval(m[k]+'()'); });
let h = computeDataHealth(NOW);
check('★开机率距今3天：🟢正常，带数据日期', row(h,'crush').state==='ok' && row(h,'crush').icon==='🟢' && row(h,'crush').detail.includes('数据日期'+ago(3)));
check('★库存距今11天(周频)：🟡降权×0.5，写明晚了一期', row(h,'stock').state==='degraded' && row(h,'stock').label.includes('×0.5') && row(h,'stock').detail.includes('晚了一期'));
check('★基差距今20天：🔴过期·不计分', row(h,'basis').state==='stale' && row(h,'basis').icon==='🔴' && row(h,'basis').label.includes('不计分'));
check('★肉鸡利润抓取失败：⚪无数据，带上失败原因', row(h,'poultry').state==='nodata' && row(h,'poultry').detail.includes('搜索结果为空'));
check('★国储拍卖：📣事件提示·不计分，且不算"有投票的指标"(不会拉红整体)', row(h,'reserve').state==='event' && row(h,'reserve').votes===false && row(h,'reserve').label.includes('事件提示'));
check('没有填过的指标(如猪粮比)：⚪无数据', row(h,'hogratio').state==='nodata' && row(h,'hogratio').detail.includes('还没有抓取'));
check('★整体：有过期/无数据的投票指标 → 红', h.level==='red' && h.bad >= 3);
check('计数：正常1、降权1、过期1、无数据(肉鸡+猪粮比+其余没填的)、事件1', h.counts.ok>=1 && h.counts.degraded>=1 && h.counts.stale===1 && h.counts.event===1 && h.counts.nodata>=2);

// 春节扰动 / 国庆降权 / 手动
reset();
window._syncedData = {generatedAt: iso(2026,9,30,9,58), mysteelMealStu:{available:true, value:20, month:'2026-02', monthLabel:'2026年2月', isForecast:false, method:'stated', methodLabel:'文章明示', recordSource:'body', stockWan:93, consumptionWan:444, productionWan:500, next:null, trend:null, weeklyCheck:null, date:ago(3), articleAgeDays:3, articleTitle:'x', festival:{name:'春节', level:'strong', festivalDate:'2026-02-17', coreDays:22, disturbed:true, phase:'假期停摆', bias:'月消费骤降'}}};
refreshMysteelMealStu(); h = computeDataHealth(NOW);
check('★春节扰动月：🧧春节扰动期·不计分', row(h,'stu').state==='suppressed' && row(h,'stu').icon==='🧧' && row(h,'stu').label.includes('春节'));
window._syncedData.mysteelMealStu = Object.assign({}, window._syncedData.mysteelMealStu, {festival:{name:'国庆', level:'mild', festivalDate:'2026-10-01', coreDays:14, disturbed:true, phase:'假期停摆', bias:'x'}, month:'2026-10', monthLabel:'2026年10月'});
refreshMysteelMealStu(); h = computeDataHealth(NOW);
check('★国庆扰动月：🎆国庆扰动月·降权', row(h,'stu').state==='degraded' && row(h,'stu').icon==='🎆' && row(h,'stu').label.includes('国庆'));
window._syncedData.mysteelMealStu = Object.assign({}, window._syncedData.mysteelMealStu, {festival:{name:null, level:null, disturbed:false}, method:'computed', methodLabel:'由库存÷消费推算'});
refreshMysteelMealStu(); h = computeDataHealth(NOW);
check('★库消比是推算值：🟡降权×0.5，写明推算', row(h,'stu').state==='degraded' && row(h,'stu').detail.includes('推算'));
makeEl('m_stu').value = '13'; onManualEdit('stu'); h = computeDataHealth(NOW);
check('★用户手动修正：✏️手动修正', row(h,'stu').state==='manual' && row(h,'stu').icon==='✏️');
window._indState.crush = {mode:'saved'}; makeEl('m_crush').value='50'; h = computeDataHealth(NOW);
check('沿用浏览器保存的手动值：🟡降权(来源和日期无法核实)', row(h,'crush').state==='degraded' && row(h,'crush').detail.includes('无法核实'));

// ===================== 3. 实时/API信号(按合约) =====================
reset();
h = computeDataHealth(NOW);
const sigNames = c=>{ window._selectedContract=c; return computeDataHealth(NOW).rows.filter(r=>r.kind==='signal').map(r=>r.name).join(','); };
check('★9月合约：美豆库消比/出口销售/汇率 + 美国天气预报/NOAA展望/干旱监测/优良率', sigNames('sep') === '美豆库存消费比(USDA),出口销售(USDA),量价关系(DCE),月差/期限结构(DCE),盘面压榨毛利(DCE),人民币汇率,美国天气预报,NOAA展望,干旱监测,美豆优良率');
check('★5月合约：南美天气/南美产量/播种进度/雷亚尔(不含美国天气)', sigNames('may') === '美豆库存消费比(USDA),出口销售(USDA),量价关系(DCE),月差/期限结构(DCE),盘面压榨毛利(DCE),人民币汇率,南美天气,南美产量(PSD),美豆播种进度,巴西雷亚尔汇率');
H.setMockedMonth(11);
check('★1月合约11月：南美+收获进度+巴西播种(美国天气不含)', sigNames('jan') === '美豆库存消费比(USDA),出口销售(USDA),量价关系(DCE),月差/期限结构(DCE),盘面压榨毛利(DCE),人民币汇率,南美天气,南美产量(PSD),美豆收获进度,巴西大豆播种进度');
H.setMockedMonth(9);
check('★1月合约9月：多出美国四项(灌浆收尾期仍计入)', sigNames('jan').includes('美国天气预报') && sigNames('jan').includes('美豆优良率'));
H.setMockedMonth(5); window._selectedContract='sep';
window._noaaOutlookSignal = null; window._soyCondSignal = null;
h = computeDataHealth(NOW);
check('★没有信号的实时数据(NOAA、优良率)：⚪无数据，整体变红', row(h,'sig:NOAA展望').state==='nodata' && row(h,'sig:美豆优良率').state==='nodata' && h.level==='red');
window._weatherRisk = null; h = computeDataHealth(NOW);
check('天气预报风险为null(还没加载)：⚪无数据', row(h,'sig:美国天气预报').state==='nodata');
window._weatherRisk='low'; h = computeDataHealth(NOW);
check('天气风险low(有信号，偏空)：算有信号，🟢', row(h,'sig:美国天气预报').state==='ok');
window._esrQuality = {m:0.5, why:'出口销售周报晚了一期'}; h = computeDataHealth(NOW);
check('★出口销售晚了一期：🟡降权×0.5，写明原因', row(h,'sig:出口销售(USDA)').state==='degraded' && row(h,'sig:出口销售(USDA)').detail.includes('晚了一期'));


// ===================== 3b. 榨利/出口销售：区分"抓取失败"和"历史样本还在积累" =====================
reset();
window._crushSignal = null; window._crushStatus = 'pending'; window._crushQuality = null;
h = computeDataHealth(NOW);
check('★榨利数据在、历史同期样本还在积累：⏳暂不计分，写明原因，不算投票指标', row(h,'sig:盘面压榨毛利(DCE)').state==='pending' && row(h,'sig:盘面压榨毛利(DCE)').icon==='⏳' && row(h,'sig:盘面压榨毛利(DCE)').detail.includes('历史同期样本') && row(h,'sig:盘面压榨毛利(DCE)').votes===false);
const badSignals = h.rows.filter(r=>r.kind==='signal' && r.votes && (r.state==='stale' || r.state==='nodata'));
check('★积累中不算异常：实时信号里没有异常项(否则回填之前榨利会一直把整体拉红，那是误导)；pending计数为1', h.counts.pending === 1 && badSignals.length === 0 && !badSignals.some(r=>r.key.includes('压榨')));
window._crushSignal = null; window._crushStatus = 'unavailable';
h = computeDataHealth(NOW);
check('★榨利抓取失败(status=unavailable)：⚪无数据，是投票指标，整体变红——跟"积累中"区分开', row(h,'sig:盘面压榨毛利(DCE)').state==='nodata' && row(h,'sig:盘面压榨毛利(DCE)').votes===true && h.level==='red');
window._crushSignal = -1; window._crushStatus = 'ok'; window._crushQuality = {m:0.5, why:'盘面数据晚了一期'};
h = computeDataHealth(NOW);
check('榨利晚了一期：🟡降权×0.5', row(h,'sig:盘面压榨毛利(DCE)').state==='degraded' && row(h,'sig:盘面压榨毛利(DCE)').detail.includes('晚了一期'));
reset(); window._esrSignal = null; window._esrPending = '历史同月样本不足，暂不判方向';
h = computeDataHealth(NOW);
check('★出口销售数据在、但历史同月样本不足：⏳暂不计分(不是⚪无数据)', row(h,'sig:出口销售(USDA)').state==='pending');
window._esrPending = '本周是市场年度切换周，净销售含结转，暂不判方向';
check('出口销售切换周：⏳并写明原因', computeDataHealth(NOW).rows.find(r=>r.key==='sig:出口销售(USDA)').detail.includes('切换周'));
reset(); window._esrSignal = null; window._esrPending = null;
check('出口销售真的没有数据(没加载/失败)：⚪无数据', computeDataHealth(NOW).rows.find(r=>r.key==='sig:出口销售(USDA)').state==='nodata');


// ===================== 3c. 月差/期限结构：同样区分"抓取失败"和"历史样本还在积累" =====================
reset();
window._spreadSignal = null; window._spreadStatus = 'pending'; window._spreadQuality = null;
h = computeDataHealth(NOW);
check('★月差数据在、历史同期样本还在积累：⏳暂不计分，写明"月差的正负本身不是信号"，不算投票指标', row(h,'sig:月差/期限结构(DCE)').state==='pending' && row(h,'sig:月差/期限结构(DCE)').icon==='⏳' && row(h,'sig:月差/期限结构(DCE)').detail.includes('正负本身不是信号') && row(h,'sig:月差/期限结构(DCE)').votes===false);
window._spreadSignal = null; window._spreadStatus = 'unavailable';
h = computeDataHealth(NOW);
check('★月差抓取失败：⚪无数据，是投票指标，整体变红', row(h,'sig:月差/期限结构(DCE)').state==='nodata' && row(h,'sig:月差/期限结构(DCE)').votes===true && h.level==='red');
window._spreadSignal = 1; window._spreadStatus = 'ok'; window._spreadQuality = {m:0.5, why:'盘面数据晚了一期'};
check('月差晚了一期：🟡降权×0.5', computeDataHealth(NOW).rows.find(r=>r.key==='sig:月差/期限结构(DCE)').state==='degraded');


// ===================== 3d. 量价关系：门槛没过=⏳不是异常；K线过期/拿不到=⚪无数据 =====================
reset();
window._vpSignal = null; window._vpStatus = 'gated'; window._vpReason = '持仓量只有近120日峰值的36%(移仓/交割期，持仓量变动是机械的)'; window._vpQuality = null;
h = computeDataHealth(NOW);
check('★量价门槛没过(移仓/交割期)：⏳暂不计分，写明原因，不算投票指标、不拉红整体', row(h,'sig:量价关系(DCE)').state==='pending' && row(h,'sig:量价关系(DCE)').icon==='⏳' && row(h,'sig:量价关系(DCE)').detail.includes('移仓/交割期') && row(h,'sig:量价关系(DCE)').votes===false);
window._vpStatus = 'insufficient'; window._vpReason = 'K线只有10根，不足25根';
check('K线不足：同样⏳', computeDataHealth(NOW).rows.find(r=>r.key==='sig:量价关系(DCE)').state==='pending');
window._vpStatus = 'stale'; window._vpReason = 'K线已过期，合约可能已到期'; window._vpSignal = null;
h = computeDataHealth(NOW);
check('★K线过期(合约可能已到期)：⚪无数据，是投票指标，整体变红——这是真的有问题，跟"门槛没过"区分开', row(h,'sig:量价关系(DCE)').state==='nodata' && row(h,'sig:量价关系(DCE)').votes===true && h.level==='red');
window._vpStatus = 'unavailable'; window._vpReason = '当前合约的日K线不可用';
check('日K线拿不到：⚪无数据', computeDataHealth(NOW).rows.find(r=>r.key==='sig:量价关系(DCE)').state==='nodata');
window._vpSignal = 1; window._vpStatus = 'ok'; window._vpQuality = {m:0.5, why:'K线数据晚了一期'};
check('K线晚了一期：🟡降权×0.5', computeDataHealth(NOW).rows.find(r=>r.key==='sig:量价关系(DCE)').state==='degraded');

// ===================== 4. 整体等级 =====================
reset();
const okAll = {crush:'50',stock:'70',basis:'0',arrival:'900',import:'900',hogratio:'6',poultry:'1',rmspread:'550',stu:'12',feed:'8'};
Object.keys(okAll).forEach(k=>{ makeEl('m_'+k).value = okAll[k]; window._indState[k] = {mode:'auto', dataDate: ago(2), freshDetail:'x'}; });
makeEl('m_sows').value='3750'; makeEl('m_reserve').value='0'; window._indState.sows = {mode:'auto'}; window._indState.reserve = {mode:'auto'};
window._syncedData = {generatedAt: iso(2026,9,30,9,58)};
h = computeDataHealth(NOW);
check('★全部正常 + 同步正常：整体🟢', h.level==='green' && h.bad===0 && h.warn===0 && h.sync.state==='ok');
window._syncedData = {generatedAt: iso(2026,9,25,15,10)};
check('★指标都正常但同步晚了(错过2个交易日)：整体🟡——单看每张卡片发现不了这个问题', computeDataHealth(NOW).level==='yellow');
window._syncedData = {generatedAt: iso(2026,9,22,15,10)};
check('★指标都"正常"(没有被判过期，因为没有刷新)但同步已停止：整体🔴', computeDataHealth(NOW).level==='red');
window._syncedData = {generatedAt: iso(2026,9,30,9,58)};
window._indState.crush = {mode:'auto', late:true, dataDate: ago(11)}; 
check('有一项晚了一期：整体🟡', computeDataHealth(NOW).level==='yellow');
window._indState.crush = {mode:'auto', dataDate: ago(2)}; window._indState.sows = {mode:'auto', stale:true};
check('★背景/事件类指标(能繁母猪)过期时显示为📣背景，不拉红整体', computeDataHealth(NOW).level==='green' && row(computeDataHealth(NOW),'sows').state==='event');
makeEl('m_sows').value=''; makeEl('m_reserve').value='';
let hEmpty = computeDataHealth(NOW);
check('★能繁母猪、国储拍卖完全没有数据：⚪无数据，但不算投票指标，整体仍是🟢(它们不参与评分)', row(hEmpty,'sows').state==='nodata' && row(hEmpty,'sows').votes===false && row(hEmpty,'reserve').votes===false && hEmpty.level==='green' && hEmpty.bad===0);
reset(); Object.keys(okAll).forEach(k=>{ makeEl('m_'+k).value = okAll[k]; window._indState[k] = {mode:'auto', dataDate: ago(2)}; }); makeEl('m_crush').value='';
check('对照：参与评分的开机率没有数据 → 整体🔴', computeDataHealth(NOW).level==='red');

// ===================== 5. 缺席的投票 + 渲染 =====================
reset(); makeEl('m_crush').value='35'; makeEl('m_stock').value='40'; makeEl('m_basis').value='10'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='2';
KEYS.forEach(k=>{ window._indState[k] = {mode:'auto', dataDate: ago(2)}; });
window._syncedData = {generatedAt: iso(2026,9,30,9,58)};
updateOverallAlert();
check('★评分里没有数据的投票被列出：到港/进口、豆菜粕价差没数据 → 缺席', window._quality.missing.some(x=>x.includes('大豆到港/进口')) && window._quality.missing.some(x=>x.includes('豆菜粕价差')) && !window._quality.missing.some(x=>x.includes('猪粮比')));
let html = makeEl('healthContent').innerHTML;
check('★面板渲染：汇总行、同步框、缺席投票、折叠的全部指标', html.includes('正常') && html.includes('每小时同步') && html.includes('没有参与评分的投票') && html.includes('大豆到港/进口') && html.includes('查看全部指标状态'));
check('面板里有数据质量分', html.includes('数据质量分'));
check('徽标反映整体等级', makeEl('healthBadge').textContent.length > 0 && makeEl('healthBadge').className.includes('badge'));
check('全部指标状态里每个指标一行(12个指标+实时信号10个)', (html.match(/class="ir"/g)||[]).length === 12 + 10);
check('★有问题的项在折叠区外就能看到(无数据的猪粮比以外的问题项)', html.includes('还没有抓取到数据'));
// 数据不足分支也会渲染面板
reset(); makeEl('m_crush').value='35';
window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null; window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
updateOverallAlert();
check('★数据不足分支(不下结论)也照样渲染健康度面板——这时候最需要看到"缺了什么"', makeEl('alertContent').innerHTML.includes('数据不足') && makeEl('healthContent').innerHTML.includes('每小时同步'));
// 没有面板元素不报错
delete elements['healthContent']; let ok = true; try{ renderDataHealth(); }catch(e){ ok=false; }
check('页面上没有健康度元素时不报错', ok);
H.clearMockedMonth(); window._nowMs = null;
H.printSummary();
