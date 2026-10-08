// ============================================================================
// 事件日历：美东↔北京时间换算(含夏令时)、大商所交易日/夜盘/开市判断、休市状态、事件列表、渲染；三方共振接入基本面置信度
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
const E = window._eventCal;
const bj = (y,m,d,h,mi)=>E.bjToMs(y,m,d,h||0,mi||0);
const L = ms=>E.bjLabel(ms);

// ===================== 1. 时间换算 =====================
check('★美东夏令时(2026-10-09 12:00 EDT=UTC-4) → 北京时间10-10 00:00', L(E.etToMs(2026,10,9,12,0)) === '10-10 00:00');
check('★美东夏令时(2026-09-30 12:00 EDT) → 北京时间10-01 00:00(季度库存报告，此时大商所已进入国庆休市)', L(E.etToMs(2026,9,30,12,0)) === '10-01 00:00');
check('★冬令时(2026-11-10 12:00 EST=UTC-5) → 北京时间11-11 01:00(比夏令时晚1小时)', L(E.etToMs(2026,11,10,12,0)) === '11-11 01:00');
check('冬令时(2026-12-10 12:00 EST) → 12-11 01:00', L(E.etToMs(2026,12,10,12,0)) === '12-11 01:00');
check('ESR每周四8:30 EDT → 北京时间当晚20:30', L(E.etToMs(2026,10,8,8,30)) === '10-08 20:30' && L(E.etToMs(2026,11,12,8,30)) === '11-12 21:30');
check('★夏令时边界：2026年11月1日(第1个周日)起是冬令时，10月31日仍是夏令时', E.isUsDst(2026,10,31) === true && E.isUsDst(2026,11,1) === false && E.isUsDst(2026,11,2) === false);
check('夏令时起点：2026年3月8日(第2个周日)起', E.isUsDst(2026,3,7) === false && E.isUsDst(2026,3,8) === true && E.isUsDst(2026,7,1) === true && E.isUsDst(2026,1,15) === false);

// ===================== 2. 大商所交易日/夜盘/开市 =====================
check('★交易日：国庆休市期间(10/1~10/7)的工作日不是交易日；10/8恢复', !E.dceIsTradingDay(2026,10,1) && !E.dceIsTradingDay(2026,10,5) && !E.dceIsTradingDay(2026,10,7) && E.dceIsTradingDay(2026,10,8) && E.dceIsTradingDay(2026,9,30));
check('周末不是交易日(含10/10周六)', !E.dceIsTradingDay(2026,10,3) && !E.dceIsTradingDay(2026,10,10) && !E.dceIsTradingDay(2026,10,11) && E.dceIsTradingDay(2026,10,12));
check('★夜盘：9/29(周二，次日是交易日)有夜盘', E.dceHasNightSession(2026,9,29) === true);
check('★夜盘：9/30(周三，次日10/1休市)——节假日前最后一个交易日无夜盘', E.dceHasNightSession(2026,9,30) === false);
check('★夜盘：10/7(休市最后一天)无夜盘(不是交易日)；10/8(周四)有夜盘', E.dceHasNightSession(2026,10,7) === false && E.dceHasNightSession(2026,10,8) === true);
check('★夜盘：周五(10/9)有夜盘——属于下周一的交易日，因为下一个工作日周一是交易日', E.dceHasNightSession(2026,10,9) === true);
check('★开市判断：10/8 09:30 开市；10/8 12:00(午休) 不开；10/8 14:00 开；10/8 21:30(夜盘) 开；10/8 23:30 不开', E.dceIsOpenAt(bj(2026,10,8,9,30)) && !E.dceIsOpenAt(bj(2026,10,8,12,0)) && E.dceIsOpenAt(bj(2026,10,8,14,0)) && E.dceIsOpenAt(bj(2026,10,8,21,30)) && !E.dceIsOpenAt(bj(2026,10,8,23,30)));
check('★开市判断：9/30 日盘开、9/30 21:30 不开(无夜盘)、10/1~10/7任何时刻不开', E.dceIsOpenAt(bj(2026,9,30,10,0)) && !E.dceIsOpenAt(bj(2026,9,30,21,30)) && !E.dceIsOpenAt(bj(2026,10,1,10,0)) && !E.dceIsOpenAt(bj(2026,10,5,21,30)));
check('开市判断：周末不开(含周五夜盘之后的周六凌晨)', !E.dceIsOpenAt(bj(2026,10,10,10,0)) && !E.dceIsOpenAt(bj(2026,10,11,21,30)));

// 下一个交易时段
check('★下一个交易时段：休市期间(10/1 00:00)之后 → 10-08 09:00', L(E.dceNextOpenAfter(bj(2026,10,1,0,0))) === '10-08 09:00');
check('★下一个交易时段：10/9 15:30(周五收盘后) → 当晚21:00夜盘', L(E.dceNextOpenAfter(bj(2026,10,9,15,30))) === '10-09 21:00');
check('下一个交易时段：10/10 00:00(周六凌晨，周五夜盘已收) → 下周一10-12 09:00', L(E.dceNextOpenAfter(bj(2026,10,10,0,0))) === '10-12 09:00');
check('下一个交易时段：午休(12:00) → 13:30', L(E.dceNextOpenAfter(bj(2026,10,8,12,0))) === '10-08 13:30');

// ===================== 3. 休市状态 =====================
let st = E.closureStatus(bj(2026,9,30,10,0), 3);
check('★9/30(休市前1天)：state=soon，恢复交易时段=10-08 09:00', st && st.state==='soon' && L(st.reopenMs)==='10-08 09:00');
st = E.closureStatus(bj(2026,10,4,12,0), 3);
check('★10/4：休市中(in)', st && st.state==='in');
st = E.closureStatus(bj(2026,10,7,23,0), 3);
check('10/7深夜：仍是休市中', st && st.state==='in');
st = E.closureStatus(bj(2026,10,8,7,0), 3);
check('★10/8 07:00(已过休市区间但还没开盘)：仍标休市中，直到9:00开盘', st && st.state==='in');
check('10/8 09:30(已开盘)：不再是休市状态', E.closureStatus(bj(2026,10,8,9,30), 3) === null);
check('休市前4天(9/26)且soon=3：不提示；休市后很久也不提示', E.closureStatus(bj(2026,9,26,10,0), 3) === null && E.closureStatus(bj(2026,11,1,10,0), 3) === null);

// ===================== 4. 事件列表 =====================
const from = bj(2026,9,30,8,0), to = from + 14*86400000;
const ev = E.buildEventList(from, to);
const by = t => ev.filter(e=>e.title.includes(t));
const gs = by('季度库存')[0];
check('★季度库存(Grain Stocks)：北京时间10-01 00:00，大商所此时不开市，最早10-08 09:00体现', gs && gs.label==='10-01 00:00' && gs.dceOpen===false && L(gs.dceNext)==='10-08 09:00');
const wasde = by('WASDE 10月')[0];
check('★WASDE 10月：北京时间10-10 00:00(周六凌晨)，大商所不开市，最早10-12 09:00体现', wasde && wasde.label==='10-10 00:00' && wasde.dceOpen===false && L(wasde.dceNext)==='10-12 09:00');
check('WASDE 11月不在未来14天窗口内', by('WASDE 11月').length === 0);
const closureEv = ev.filter(e=>e.kind==='closure'), reopenEv = ev.filter(e=>e.kind==='reopen');
check('★休市开始/恢复交易两个事件：10-01 00:00、10-08 09:00', closureEv.length===1 && closureEv[0].label==='10-01 00:00' && reopenEv.length===1 && reopenEv[0].label==='10-08 09:00');
const esr = by('出口销售周报');
check('每周例行ESR(周四8:30 ET=北京当晚20:30)：10-01、10-08 各一次', esr.map(e=>e.label).join(',') === '10-01 20:30,10-08 20:30');
check('★10-08 20:30的ESR：大商所夜盘前半小时，此时休市间隙(日盘已收、夜盘21:00才开)，最早21:00体现', esr[1].dceOpen===false && L(esr[1].dceNext)==='10-08 21:00');
const crop = by('作物进度');
check('作物进度(周一16:00 ET=北京周二04:00)：10-06 04:00', crop.some(e=>e.label==='10-06 04:00'));
check('事件按时间排序', ev.every((e,i)=>i===0 || ev[i-1].ms<=e.ms));
// 例行事件的截止日期：作物进度到11-30
const late = E.buildEventList(bj(2026,12,1,0,0), bj(2026,12,20,0,0));
const lateCrop = late.filter(e=>e.title.includes('作物进度')).map(e=>e.label);
check('★作物进度只到2026-11-30(美东周一)：最后一期换算成北京时间是12-01 05:00(冬令时)，12-07/12-08之后不再出现；ESR/COT到年底仍在', lateCrop.join(',') === '12-01 05:00' && late.some(e=>e.title.includes('出口销售周报')) && late.some(e=>e.title.includes('COT')));
check('12月WASDE(12-10 12:00 EST → 北京12-11 01:00)', late.some(e=>e.title.includes('WASDE 12月') && e.label==='12-11 01:00'));

// ===================== 5. 渲染 =====================
elements['eventCalendarContent'] = makeEl('eventCalendarContent');
E.renderEventCalendar(bj(2026,9,30,10,0));
let html = makeEl('eventCalendarContent').innerHTML;
check('★9/30：顶部有休市警示，写明休市区间、恢复交易日期和首个交易时段', html.includes('即将休市') && html.includes('2026-10-01~2026-10-07') && html.includes('2026-10-08恢复交易') && html.includes('10-08 09:00'));
check('★警示里点名休市期间的关键美国报告(季度库存)，并提示节后可能跳空', html.includes('季度库存') && html.includes('节后首个交易时段可能跳空'));
check('警示里说明休市期间外盘照常交易，并提示以大商所公告为准', html.includes('外盘(CBOT)照常交易') && html.includes('请以大商所公告为准'));
check('列表里：季度库存(10-01 00:00)、WASDE(10-10 00:00)、休市开始/恢复交易', html.includes('10-01 00:00') && html.includes('10-10 00:00') && html.includes('大商所国庆节休市开始') && html.includes('大商所国庆节后恢复交易'));
check('★每个报告标注"大商所此时不在交易时段，最早…开盘体现"', html.includes('大商所此时不在交易时段') && html.includes('最早10-08 09:00开盘体现'));
check('每周例行放在折叠区里，并提示遇美国联邦假日可能顺延', html.includes('每周例行') && html.includes('遇美国联邦假日可能顺延'));
check('页脚说明核对日期和来源，并声明不判断方向', html.includes('日期核对于2026-09-30') && html.includes('不判断方向'));
check('没有超过覆盖期时不显示"日历已超过覆盖期"', !html.includes('日历已超过覆盖期'));
E.renderEventCalendar(bj(2026,10,4,12,0));
check('★10/4休市中：警示标题变为"休市中"', makeEl('eventCalendarContent').innerHTML.includes('休市中'));
E.renderEventCalendar(bj(2026,10,20,10,0));
html = makeEl('eventCalendarContent').innerHTML;
check('10/20：没有休市警示；列表里是WASDE 11月(11-11 01:00)前的例行事件', !html.includes('大商所国庆节休市中') && !html.includes('即将休市'));
E.renderEventCalendar(bj(2027,1,10,10,0));
check('★超过覆盖期(2027-01)：提示日历需要更新', makeEl('eventCalendarContent').innerHTML.includes('日历已超过覆盖期') && makeEl('eventCalendarContent').innerHTML.includes('没有已核实的休市/USDA关键报告'));
let ok = true; try{ const saved = elements['eventCalendarContent']; delete elements['eventCalendarContent']; window.document && 0; E.renderEventCalendar(); }catch(e){ ok=false; }
check('页面上没有事件日历元素时不报错', ok);

// ===================== 6. 三方共振接入基本面置信度 =====================
const calm = {status:'calm', label:'外资平静'};
let r = computeResonanceStatus('偏多','偏多',calm);
check('回归：不传meta时行为不变', r.title==='技术面与基本面同向：偏多' && r.detail==='两者方向一致(外资平静)，仅供参考，不构成操作建议');
r = computeResonanceStatus('偏多','偏多',calm,{confidence:'高', reasons:['覆盖100%'], divergence:null, weatherDominant:null});
check('★高置信度：显示"基本面预警置信度：高"，标题不打折', r.title==='技术面与基本面同向：偏多' && r.detail.includes('基本面预警置信度：高'));
r = computeResonanceStatus('偏空','偏空',calm,{confidence:'低', reasons:['有效指标只有6/12(50%，低于60%)'], divergence:null, weatherDominant:null});
check('★低置信度：标题写明"共振的可靠性打折"，详情列出原因；方向颜色不变', r.title.includes('基本面预警置信度低，共振的可靠性打折') && r.cls==='bear' && r.detail.includes('有效指标只有6/12'));
r = computeResonanceStatus('偏多','偏多',calm,{confidence:'中', reasons:[], divergence:'供需两侧方向分歧(供给端偏空、需求端偏多)', weatherDominant:null});
check('★基本面预警内部的供需分歧也带进共振详情', r.detail.includes('基本面预警内部供需两侧方向分歧'));
r = computeResonanceStatus('偏多','偏多',calm,{confidence:'高', reasons:[], divergence:null, weatherDominant:'美国作物4项子信号里3项同时偏多'});
check('★天气主导行情：说明基本面预警里其它指标只作参考', r.detail.includes('天气主导行情') && r.detail.includes('基本面预警正处于') && r.detail.includes('其它指标只作参考'));
r = computeResonanceStatus('偏多','偏空',calm,{confidence:'中', reasons:[], divergence:null, weatherDominant:null});
check('方向不一致时也带上基本面预警可靠性说明', r.cls==='neutral' && r.detail.includes('基本面预警置信度：中'));
r = computeResonanceStatus('偏多','偏多',{status:'active', isGoldman:true, label:'高盛大幅增仓'},{confidence:'低', reasons:[]});
check('外资活跃时仍优先提示外资(不被覆盖)', r.title==='外资(高盛)活跃');
// 端到端：updateOverallAlert 写入 window._fundamentalMeta
const AUTO = window._autoIndicators;
AUTO.forEach(c=>{ makeEl(c.inputId).value=''; makeEl('ind_'+c.key); makeEl('alert_'+c.key); window._indState[c.key]={}; });
makeEl('alertContent'); H.setMockedMonth(5);
window._selectedContract='sep'; window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
makeEl('m_crush').value='70'; makeEl('m_stock').value='120'; H.setBasis('-100'); makeEl('m_arrival').value='1100'; makeEl('m_import').value='1100'; makeEl('m_hogratio').value='4'; makeEl('m_sows').value='3900';
updateOverallAlert();
check('★updateOverallAlert写入window._fundamentalMeta：方向明确时带置信度和原因', window._fundamentalMeta && ['高','中','低'].includes(window._fundamentalMeta.confidence) && Array.isArray(window._fundamentalMeta.reasons) && window._fundamentalMeta.reasons.length>0);
AUTO.forEach(c=>{ makeEl(c.inputId).value=''; }); makeEl('m_crush').value='35';
window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null; window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
updateOverallAlert();
check('★数据不足时meta置空(不沿用旧值)', window._fundamentalMeta === null);
H.clearMockedMonth();
H.printSummary();
