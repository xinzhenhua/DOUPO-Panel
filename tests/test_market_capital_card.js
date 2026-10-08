// ============================================================================
// 资金面(龙虎榜+CFTC)进"市场结构"区块 + 当前市场状态写在决策卡最上边(v100)
//   数据是2026-09-30真实龙虎榜(M2701主力合约)和CFTC(2026-09-22)；只展示，不进市场结构的净倾向投票。
// ============================================================================
const fs = require('fs'), path = require('path');
const H = require('./test_helpers');
const { makeEl, check } = H;
const SRC = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
eval(H.loadDashboardJs());
const E = window._eventCal;
const KEYS = window._autoIndicators.map(c=>c.key);
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); });
  window._indState = {}; ['alertContent','structureContent','resonanceContent','eventCalendarContent','healthContent','healthBadge','decisionSummary'].forEach(makeEl);
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
  window._selectedContract='sep'; window._syncedData = null; window._technicalDirection = undefined; window._foreignActivity = undefined;
}
const NOW = E.bjToMs(2026,10,1,10,0);
const MC = {available:true, mainContract:{key:'jan', symbol:'M2701', gross:867214}, date:'2026-09-30',
  members:{ '高盛期货':{net:152092, change:2181, side:'long', rank:1, foreign:true}, '摩根大通':{net:-9739, change:-7014, side:'short', rank:7, foreign:true},
            '瑞银期货':{net:11489, change:829, side:'long', rank:12, foreign:true}, '中粮期货':{net:-482209, change:5234, side:'short', rank:1, foreign:false},
            '国投期货':{net:-226091, change:-2906, side:'short', rank:2, foreign:false} },
  industry:{net:-708300, change:2328, changePct:0.33, members:['中粮期货','国投期货']},
  cftc:{net:191087, netChange:7976, streakWeeks:6, streakDirection:'up', percentile:100, weeksUsed:156, reportDate:'2026-09-22'},
  state:{code:'crowded', level:'red', label:'外资多头拥挤', note:'只能判断持仓拥挤度(高盛净多头水平+CFTC管理基金净多的历史分位)。文档里\'资金市\'还要求的价格突破、无视基本面利空、美豆不涨豆粕涨、高盛连续N日单边增仓，目前都未判断：价格/联动需要美豆数据，\'连续N日\'需要龙虎榜历史(v101起每天累积，但刚开始，要攒够才能判断，见TODO.md)。', thresholdSource:'文档经验值，暂定，未回测'},
  source:'大商所龙虎榜(东方财富，T+1)+CFTC'};
function load(mc, extra){
  reset(); window._nowMs = NOW;
  window._syncedData = Object.assign({generatedAt:new Date(NOW - 3600000).toISOString(), marketCapital: mc}, extra||{});
  updateOverallAlert();
}
const st = ()=>makeEl('structureContent').innerHTML;
const stText = ()=>st().replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');
const sum = ()=>makeEl('decisionSummary').innerHTML;
const sumText = ()=>sum().replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');

// ===================== 1. 资金持仓小节在"市场结构"区块里 =====================
load(MC);
check('★市场结构区块里有"资金持仓(龙虎榜+CFTC)"小节，写明主力合约M2701和数据日期', /资金持仓/.test(stText()) && stText().includes('M2701') && stText().includes('2026-09-30'));
check('★外资三家都列出：高盛期货净多152,092手(+2,181)、摩根大通净空9,739手(日变化-7,014)、瑞银期货净多11,489手(+829)', stText().includes('高盛期货') && stText().includes('152,092') && stText().includes('+2,181') && stText().includes('摩根大通') && stText().includes('9,739') && stText().includes('-7,014') && stText().includes('瑞银期货') && stText().includes('11,489'));
check('★方向用文字写清楚：高盛"净多"、摩根大通"净空"(不只是正负号)', /高盛期货[^净]{0,6}净多/.test(stText()) && /摩根大通[^净]{0,6}净空/.test(stText()));
check('★产业：中粮期货净空482,209(日变化+5,234=净空减少)、国投期货净空226,091(-2,906=净空增加)、合计净空708,300', stText().includes('中粮期货') && stText().includes('482,209') && stText().includes('国投期货') && stText().includes('226,091') && stText().includes('708,300'));
check('★产业合计的日变化写成"净空减少/增加"的人话(净持仓变化+2,328=净空减少2,328手，0.33%)，不让用户自己换算符号', stText().includes('净空减少') && stText().includes('2,328') && stText().includes('0.33%'));
check('★CFTC：管理基金净多191,087、周变化+7,976、连续6周增加、近156周100%分位、报告日期2026-09-22', stText().includes('CFTC') && stText().includes('191,087') && stText().includes('+7,976') && stText().includes('6周') && stText().includes('100%') && stText().includes('156') && stText().includes('2026-09-22'));
check('★明确写出CFTC是CBOT豆粕(美国市场)，不是大商所——两者共振没有验证过', /CBOT|美国/.test(stText()) && /不是大商所|没有验证|未验证/.test(stText()));
check('★说明数据性质：T+1滞后(收盘后发布)、高盛席位是代客集合持仓非高盛自营', stText().includes('T+1') && stText().includes('代客'));

// ===================== 2. 只展示，不进市场结构的净倾向投票 =====================
const sysBefore = JSON.stringify(window._structureSystem), pureBefore = JSON.stringify(window._fundamentalPure), compBefore = JSON.stringify(window._composite);
load(null);
check('★资金面只展示不投票：有没有marketCapital，_structureSystem/_fundamentalPure/_composite完全不变(不改评分、不需要升级评分规则版本)', JSON.stringify(window._structureSystem) === sysBefore && JSON.stringify(window._fundamentalPure) === pureBefore && JSON.stringify(window._composite) === compBefore);
load(MC);
check('★市场结构区块里明确写"资金持仓不参与上面的市场结构净倾向"，并说明原因(不是价格衍生、T+1、阈值没标定)', /不参与[^。]{0,20}净倾向|不计入[^。]{0,20}净倾向/.test(stText()) && stText().includes('不是价格') );

// ===================== 3. 三个提前return的分支里资金持仓都在(价格类结构票没数据时它也不能消失) =====================
load(MC);   // 默认空场景：没有任何价格类结构票的信号 → renderStructureCard走"暂无信号"分支
check('前置：这个场景里市场结构(价格类)暂无信号(走第一个提前return分支)', window._structureSystem && window._structureSystem.n === 0 && /市场结构暂无信号/.test(stText()));
check('★价格类结构票暂无信号时，资金持仓小节仍然显示(它们是独立的数据，不能跟着消失)', /资金持仓/.test(stText()) && stText().includes('152,092'));
reset(); window._nowMs = NOW; H.setBasis('-100'); window._syncedData = {generatedAt:new Date(NOW-3600000).toISOString(), marketCapital: MC}; updateOverallAlert();
check('前置：只有基差1项有信号(thin分支)', window._structureSystem.thin === true && /样本少/.test(stText()));
check('★thin分支：资金持仓仍显示', /资金持仓/.test(stText()) && stText().includes('152,092'));
reset(); window._nowMs = NOW; H.setBasis('-100'); window._spreadSignal = 1; window._spreadQuality = {m:1, why:''}; window._syncedData = {generatedAt:new Date(NOW-3600000).toISOString(), marketCapital: MC}; updateOverallAlert();
check('前置：基差+月差2项(正常分支，有净倾向)', window._structureSystem.n === 2 && window._structureSystem.thin === false && /净倾向/.test(stText()));
check('★正常分支：资金持仓仍显示，且在价格类结构票的表格之后', /资金持仓/.test(stText()) && stText().indexOf('资金持仓') > stText().indexOf('净倾向'));
window._spreadSignal = undefined; window._spreadQuality = undefined;

// ===================== 4. 降级：没有数据时不崩、不留空白、不假装 =====================
for (const [label, mc] of [['marketCapital为null', null], ['marketCapital缺失(旧版latest.json)', undefined], ['available=false', {available:false, mainContract:null, members:{}, industry:null, cftc:null, state:{code:'unknown', level:'gray', label:'外资状态：数据不足', note:'x', thresholdSource:'x'}}], ['后端生成失败', {available:false, error:'KeyError: x'}]]){
  load(mc);
  check(`★降级(${label})：资金持仓小节写"暂无数据"，不崩、不显示空表、不显示假数字`, /资金持仓/.test(stText()) && /暂无|数据不足|不可用/.test(stText()) && !stText().includes('152,092'));
}
// CFTC缺失但龙虎榜在
load(Object.assign({}, MC, {cftc:null, state:{code:'elevated', level:'yellow', label:'外资多头高位(高盛净多头在高位，CFTC未到拥挤)', note:'n', thresholdSource:'t'}}));
check('★CFTC缺失：龙虎榜部分照常，CFTC那一行写"暂无"，不显示undefined/NaN', stText().includes('152,092') && /CFTC[^。]{0,20}暂无/.test(stText()) && !/undefined|NaN|null/.test(st()));
// 某个席位未进榜
load(Object.assign({}, MC, {members:Object.assign({}, MC.members, {'瑞银期货':{net:null, change:null, side:null, rank:null, foreign:true}})}));
check('★席位未进榜(net=null)：写"未进榜"，不写0，不显示undefined/NaN', /瑞银期货[^。]{0,12}未进榜/.test(stText()) && !/undefined|NaN|null/.test(st()));

// ===================== 5. 日变化含义逐行对应(最容易读反的地方) =====================
// 净空头席位的"净持仓变化"为正=净空减少，为负=净空增加；净多头席位为正=净多增加，为负=净多减少。
// 只检查"文字里有这几个词"会被"都有但配错了"骗过——所以逐行断言：每一行(<tr>)里数字和含义词必须是对的那一对。
load(MC);
const trRows = h => (h.match(/<tr>(?:(?!<\/tr>)[\s\S])*<\/tr>/g) || []).filter(x=>/^<tr><td>/.test(x)).map(r=>r.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim());
const rows = trRows(st());
const rowOf = n => rows.find(r=>r.startsWith(n)) || '';
check('★每个席位一行，共5行(高盛、摩根大通、瑞银、中粮、国投)', rows.length === 5 && ['高盛期货','摩根大通','瑞银期货','中粮期货','国投期货'].every(n=>rowOf(n)));
check('★高盛(净多152,092，变化+2,181)：这一行写"净多增加"，不写"净空"', /净多 152,092手/.test(rowOf('高盛期货')) && /\+2,181\(净多增加\)/.test(rowOf('高盛期货')) && !rowOf('高盛期货').includes('净空'));
check('★摩根大通(净空9,739，净持仓变化-7,014)：这一行写"净空增加"(净多头减少7,014=净空增加，不是净空减少)', /净空 9,739手/.test(rowOf('摩根大通')) && /-7,014\(净空增加\)/.test(rowOf('摩根大通')) && !rowOf('摩根大通').includes('净空减少'));
check('★瑞银(净多11,489，+829)：净多增加', /净多 11,489手/.test(rowOf('瑞银期货')) && /\+829\(净多增加\)/.test(rowOf('瑞银期货')));
check('★中粮(净空482,209，净持仓变化+5,234)：这一行写"净空减少"——这是最容易读反的一行：变化是正数，但含义是空头在减少', /净空 482,209手/.test(rowOf('中粮期货')) && /\+5,234\(净空减少\)/.test(rowOf('中粮期货')) && !rowOf('中粮期货').includes('净空增加'));
check('★国投(净空226,091，净持仓变化-2,906)：这一行写"净空增加"——变化是负数，含义是空头在增加', /净空 226,091手/.test(rowOf('国投期货')) && /-2,906\(净空增加\)/.test(rowOf('国投期货')) && !rowOf('国投期货').includes('净空减少'));
// 变化为0：不写含义；变化为null：写—
load(Object.assign({}, MC, {members:Object.assign({}, MC.members, {'中粮期货':{net:-482209, change:0, side:'short', rank:1, foreign:false}, '国投期货':{net:-226091, change:null, side:'short', rank:2, foreign:false}})}));
const rows0 = trRows(st());
check('变化为0：不写"净空减少/增加"(没有变化)；变化缺失(null)：写"—"，不写NaN', !/中粮期货[^国]*净空(减少|增加)/.test(rows0.find(r=>r.startsWith('中粮期货'))) && /日变化 —/.test(rows0.find(r=>r.startsWith('国投期货'))) && !/NaN|undefined/.test(st()));

// ===================== 6. 当前市场状态写在决策卡最上边 =====================
// 状态块里嵌套了3层<div>(标题/状态行/依据)，不能用非贪婪正则取到第一个</div>就停(那只会取到标题)——按嵌套深度配对，取完整的状态块
const firstRow = ()=>{ const h = sum(); const i = h.indexOf('<div class="dc-state'); if(i < 0) return ''; let d = 0; for(let k = i; k < h.length; k++){ if(h.startsWith('<div', k)) d++; else if(h.startsWith('</div>', k)){ d--; if(d === 0) return h.slice(i, k + 6); } } return h.slice(i); };
const firstText = ()=>firstRow().replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
load(MC);
check('★摘要的**第一个**元素是"当前市场状态"(在基本面方向那条之前)', sum().trim().startsWith('<div class="dc-state') && sum().indexOf('dc-state') < sum().indexOf('dc-head'));
check('★状态里同时写出两个**独立系统**的结论，不混成一个数：资金面"外资多头拥挤" + 基本面(信号混合/偏多/偏空)', /资金面[^基]*外资多头拥挤/.test(firstText()) && /基本面/.test(firstText()));
check('★状态行写明依据数字：高盛净多15.2万手(152,092)、CFTC近156周100%分位', firstText().includes('152,092') && firstText().includes('100%') && firstText().includes('156'));
check('★资金面状态的颜色：拥挤(red)=🔴，这里"红=偏多/绿=偏空"的涨跌色约定不适用于状态灯——状态灯用🔴🟡🟢⚪，不用dc-bull/dc-bear', firstRow().includes('🔴') && !/dc-bull|dc-bear/.test(firstRow()));
check('★明确写出"只能判断拥挤度、未判断价格突破/美豆联动/连续N日"(防止把它读成"已确认资金市")', /拥挤度/.test(firstText()) && /未判断/.test(firstText()));
check('★不写交易指令：状态行里没有"参与/观望/休息/建议/应该"', !/参与|观望|休息|建议|应该|不要做|别做/.test(firstText()));
check('★来源标注：阈值来自文档经验值、暂定、未回测', /文档经验值/.test(firstText()) && /未回测/.test(firstText()));
// 各档状态各自的灯
for (const [code, level, lamp, label] of [['elevated','yellow','🟡','外资多头高位(高盛净多头在高位，CFTC未到拥挤)'], ['neutral','green','🟢','外资中性(高盛净多头不在高位，CFTC不拥挤)'], ['retreat','yellow','🟡','外资撤退预警：高盛当日减仓25,000手'], ['unknown','gray','⚪','外资状态：数据不足']]){
  load(Object.assign({}, MC, {state:Object.assign({}, MC.state, {code, level, label})}));
  check(`★状态${code}(${level})：灯${lamp}，文字原样来自后端label`, firstRow().includes(lamp) && firstText().includes(label));
}
// 基本面数据不足时，资金面状态仍然显示(它们是独立的)
reset(); window._nowMs = NOW; window._psdSignal = 1; window._syncedData = {generatedAt:new Date(NOW-3600000).toISOString(), marketCapital: MC}; updateOverallAlert();
check('前置：基本面数据不足', window._fundamentalPure.direction === null);
check('★基本面数据不足时，资金面状态仍然显示在最上边(独立系统，不跟着消失)，基本面那半写"数据不足"', firstText().includes('外资多头拥挤') && /基本面[^资]*数据不足/.test(firstText()));
// 资金面不可用：写"资金面数据不足"，不假装中性
for (const [label, mc] of [['marketCapital缺失', undefined], ['available=false', {available:false, state:{code:'unknown', level:'gray', label:'外资状态：数据不足', note:'n', thresholdSource:'t'}}]]){
  load(mc);
  check(`★资金面不可用(${label})：状态行写"资金面数据不足"，灯是⚪，绝不写中性/🟢；基本面那半照常`, /资金面[^基]*数据不足/.test(firstText()) && firstRow().includes('⚪') && !firstRow().includes('🟢') && !/中性/.test(firstText().split('基本面')[0]) && /基本面/.test(firstText()));
}
// 状态行不影响评分
const p0 = JSON.stringify([window._fundamentalPure, window._composite, window._structureSystem]);
load(MC); const p1 = JSON.stringify([window._fundamentalPure, window._composite, window._structureSystem]);
load(null); const p2 = JSON.stringify([window._fundamentalPure, window._composite, window._structureSystem]);
check('★状态行只读不写：有/无资金面数据时评分导出完全相同', p1 === p2);

// ===================== 7. 变异检查补的两个盲区 =====================
// 7a. 资金持仓在价格类结构票的**表格之后**：原先用"净倾向"做锚点，但"净倾向"出现在最上面的结论框里(在表格之前)，资金持仓放表格前后都排在它后面——锚点选错了。
//     用表格里的内容(现货基差那一格)和资金持仓小节自己的标题做锚点。
reset(); window._nowMs = NOW; H.setBasis('-100'); window._spreadSignal = 1; window._spreadQuality = {m:1, why:''}; window._syncedData = {generatedAt:new Date(NOW-3600000).toISOString(), marketCapital: MC}; updateOverallAlert();
const iBasisCell = st().indexOf('现货基差'), iCapHead = st().indexOf('资金持仓(龙虎榜+CFTC)'), iNote = st().indexOf('三者都来自价格本身');
check('前置：价格类结构票的表格(现货基差那一格)和说明文字都存在', iBasisCell > 0 && iNote > 0 && iCapHead > 0);
check('★资金持仓小节在价格类结构票的表格**和**"三者都来自价格本身"说明**之后**(价格类的先说完，再说资金持仓)', iCapHead > iBasisCell && iCapHead > iNote);
window._spreadSignal = undefined; window._spreadQuality = undefined;
// 7b. 降级文案要出现在**资金持仓小节自己**里：上面"市场结构暂无信号"也含"暂无"，会掩盖小节自己没写的情况。
//     取资金持仓小节(从它的标题到末尾)再断言。
load(undefined);
const capPart = st().slice(st().indexOf('资金持仓(龙虎榜+CFTC)')).replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');
check('★降级文案在资金持仓小节自己里：写"资金持仓暂无数据"(不是借用上面"市场结构暂无信号"里的"暂无")', st().indexOf('资金持仓(龙虎榜+CFTC)') > 0 && capPart.includes('资金持仓暂无数据') && capPart.includes('不影响上面的结论'));

// ===================== 8. 累积的历史展示(v101) =====================
// 席位的history：{n(已累积点数), since(历史起点), run{direction,days,total,since,contract}, change5, change20}。
// 要诚实：刚开始累积时(n=1)写"历史累积中(已1个交易日)"，不编趋势；有了才写"连续N日净多减少/增加、累计X手"。
const withHist = (hist)=>Object.assign({}, MC, {members:Object.assign({}, MC.members, {'高盛期货':Object.assign({}, MC.members['高盛期货'], {history:hist})})});
// 历史趋势单元格：取指定席位那一行里class="dc-hist"的<td>(精确取，不再用整行文本做包含判断——整行里还有'日变化…净空减少'这类词，会混淆)
const histOf = name => { const m = (st().match(/<tr><td>[^<]*<\/td>(?:(?!<\/tr>)[\s\S])*?<\/tr>/g) || []).find(r => r.startsWith('<tr><td>' + name + '</td>')); if(!m) return ''; const c = m.match(/<td class="dc-hist">([\s\S]*?)<\/td>/); return c ? c[1].replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim() : ''; };
const gsRow = ()=>histOf('高盛期货');
const run = (direction, days, total, since)=>({direction, days, total, since, contract:'M2701'});
// 8a. 刚开始累积：n=1
load(withHist({n:1, since:'2026-09-30', run:run(null,0,0,null), change5:null, change20:null}));
check('★刚开始累积(n=1)：写"历史累积中(已1个交易日)"，不编连续N日的趋势', /历史累积中/.test(gsRow()) && /已1个交易日/.test(gsRow()) && !/连续/.test(gsRow()));
// 8b. 有连续上升：高盛净多连续4日增加，累计+4,000
load(withHist({n:5, since:'2026-09-23', run:run('up', 4, 4000, '2026-09-24'), change5:null, change20:null}));
check('★连续上升：写"连续4日净多增加，累计+4,000手"(净多头席位：up=增加)', /连续4日净多增加/.test(gsRow()) && /\+4,000/.test(gsRow()));
// 8c. 连续下降：高盛净多连续3日减少，累计-25,000(文档：连续3-4日净多减少=趋势确认——这里只描述，不下结论)
load(withHist({n:8, since:'2026-09-20', run:run('down', 3, -25000, '2026-09-28'), change5:{change:-30000, from:'2026-09-23', to:'2026-09-30', contract:'M2701', n:5}, change20:null}));
check('★连续下降：写"连续3日净多减少，累计-25,000手"', /连续3日净多减少/.test(gsRow()) && /-25,000/.test(gsRow()));
check('★有近5日变化时一并写出：较5个交易日前-30,000手', /近5个交易日[^+\-]*-30,000/.test(gsRow()));
check('★只描述，不下结论：不写"趋势确认""资金市结束""撤退"这类文档里的结论词', !/趋势确认|资金市结束|撤退确认|见顶/.test(gsRow()));
// 8d. 净空头席位的含义：中粮净空，run.direction=up 表示净持仓上升=净空减少
const zl = (hist)=>Object.assign({}, MC, {members:Object.assign({}, MC.members, {'中粮期货':Object.assign({}, MC.members['中粮期货'], {history:hist})})});
load(zl({n:6, since:'2026-09-21', run:run('up', 2, 9000, '2026-09-29'), change5:null, change20:null}));
const zlRow = ()=>histOf('中粮期货');
check('★净空头席位(中粮)：净持仓上升=净空减少。run.direction=up、累计+9,000 → 这个单元格写"连续2日净空减少，累计+9,000手"，且**不含**"净空增加"', /连续2日净空减少，累计\+9,000手/.test(zlRow()) && !zlRow().includes('净空增加'));
load(zl({n:6, since:'2026-09-21', run:run('down', 2, -9000, '2026-09-29'), change5:null, change20:null}));
check('★净空头席位：净持仓下降=净空增加。run.direction=down、累计-9,000 → 这个单元格写"连续2日净空增加，累计-9,000手"，且**不含**"净空减少"', /连续2日净空增加，累计-9,000手/.test(zlRow()) && !zlRow().includes('净空减少'));
// 8e. 缺history(旧数据/未累积)：不显示趋势列的内容，不崩
load(MC);
check('★没有history字段(旧版或累积失败)：不崩、不显示undefined/NaN，也不编趋势；单元格写"—"', !/undefined|NaN|null/.test(st()) && gsRow() === '—');
// 8f. 摩根大通净空(换向)：净持仓为负，up=净空减少
// 8g. 表头多一列
check('★外资席位表和产业席位表的表头都多了"历史趋势"列', (st().match(/<th>历史趋势<\/th>/g) || []).length === 2);
// 8h. 说明里写清楚龙虎榜历史是从什么时候开始累积的、CFTC已回填
load(MC);
check('★小节说明写明：龙虎榜历史从v101起每天累积(不能回填)，CFTC已回填156周——如实写，不夸大', /龙虎榜历史[^。]{0,20}(每天|逐日)累积/.test(stText()) && /CFTC[^。]{0,25}156周/.test(stText()));

// 8i. 一行里同时有"日变化(今天)"和"历史趋势(连续N日)"：两个含义互相独立，且都不能写反。
//     中粮：今天净持仓变化+5,234(净空减少)，但连续趋势是"连续3日净空增加，累计-12,000"(前几天空头在增加，今天反过来减少了一点)——
//     今天=净空减少、趋势=净空增加，两者同时出现在同一行，各自对应各自的单元格。
load(zl({n:9, since:'2026-09-17', run:run('down', 3, -12000, '2026-09-24'), change5:null, change20:null}));
const zlFull = trRows(st()).find(r=>r.startsWith('中粮期货')) || '';
check('★同一行里今天的日变化(+5,234 净空减少)和历史趋势(连续3日净空增加，累计-12,000)各自正确、互不串：日变化单元格含"净空减少"、趋势单元格含"净空增加"，且反过来不含', /\+5,234\(净空减少\)/.test(zlFull) && /连续3日净空增加，累计-12,000手/.test(zlFull) && !zlRow().includes('净空减少') && /日变化 \+5,234\(净空减少\)/.test(zlFull.replace(zlRow(), '')));

// 8j. 变异检查补的三个盲区
// 近20个交易日变化：原来只给了change5。手算：较20个交易日前+60,000
load(withHist({n:25, since:'2026-08-31', run:run(null,0,0,null), change5:{change:5000, from:'2026-09-23', to:'2026-09-30', contract:'M2701', n:5}, change20:{change:60000, from:'2026-09-02', to:'2026-09-30', contract:'M2701', n:20}}));
check('★近5个和近20个交易日变化都写出：+5,000、+60,000(原来只测了近5个)', /近5个交易日\+5,000手/.test(gsRow()) && /近20个交易日\+60,000手/.test(gsRow()) && /；/.test(gsRow()));
// 畸形输入：days=0但direction非空——后端不会产出，但前端不能因此写"连续0日"
load(withHist({n:3, since:'2026-09-28', run:{direction:'up', days:0, total:0, since:null, contract:'M2701'}, change5:null, change20:null}));
check('★畸形输入(days=0但direction=up)：不写"连续0日"，仍写"历史累积中"(两个条件互相掩盖，单独检验days>0这一条)', !/连续/.test(gsRow()) && /历史累积中/.test(gsRow()));
// 布局：表头4列，数据行的"未进榜"行必须是 席位名1列 + colspan=3(共4列)，否则表格错位
load(Object.assign({}, MC, {members:Object.assign({}, MC.members, {'瑞银期货':{net:null, change:null, side:null, rank:null, foreign:true}})}));
check('★未进榜行的布局：席位名1列+colspan="3"(共4列，与表头对齐)——这是视觉属性，文字断言看不到', /<tr><td>瑞银期货<\/td><td colspan="3"/.test(st()));

// 8k. ★说明里CFTC回填的周数必须是**实际拿到的周数**(weeksUsed)，不能写死156——真实接口如果只返回了104周，写"156周"就是夸大。
//   ★锚点用"📚"(说明段的图标，稳定存在)，并且**先断言锚点存在**：上一版用stText().indexOf('历史：')，但标签换成空格后变成"历史 ："，
//   找不到返回-1，slice(-1)只剩一个空格——否定断言对一个空格做检查，永远通过(假的)。
const noteOf = ()=>{ const t = stText(); const i = t.indexOf('📚'); return i < 0 ? null : t.slice(i); };
for (const [weeks, want] of [[156,'近156周'], [104,'近104周'], [null,'CFTC历史']]) {
  load(Object.assign({}, MC, {cftc:Object.assign({}, MC.cftc, {weeksUsed:weeks})}));
  const note = noteOf();
  check(`前置：说明段(📚)存在(周数=${weeks===null?'未知':weeks})`, note !== null && note.length > 40);
  check(`★CFTC回填周数按实际拿到的(${weeks===null?'未知':weeks})来写：说明里写"${want}"，不写死156`, note.includes(want) && (weeks===156 || !note.includes('156周')));
  if(weeks === null) check('★周数未知时**不出现任何具体周数**(不编"近52周"之类)：说明里CFTC那句不含"近N周"', !/CFTC[^。]{0,12}近\d+周/.test(note));
}
load(Object.assign({}, MC, {cftc:null}));
const note0 = noteOf();
check('前置：CFTC缺失时说明段(📚)仍然存在', note0 !== null && note0.length > 40);
check('★CFTC没有数据时：说明里不声称已回填任何周数(不写"已一次性回填近N周")，而是写明CFTC这次没拿到', !/已一次性回填近\d+周/.test(note0) && /CFTC[^。]{0,20}(没拿到|暂无|未拿到)/.test(note0));

H.printSummary();
