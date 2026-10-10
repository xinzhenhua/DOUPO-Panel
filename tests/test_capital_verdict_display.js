// ============================================================================
// 外资趋势结论进首页(v101.18)：顶部"资金面"不再只写"外资多头拥挤"，而是带方向的结论 + 与基本面/价格结构的三信号对照。
//   fixture VERDICT 由 capital_trend.build_verdict 对真实数据生成(高盛M2701：09-30峰值152,092 → 10-09的129,562，连续2日减仓，跨国庆)。
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
const NOW = E.bjToMs(2026,10,10,10,0);
const VERDICT = {"code": "retreat_from_high", "level": "yellow", "short": "外资高位撤退中", "label": "外资高位撤退中：高盛净多从峰值152,092手(09-30)降到129,562手，较峰值回落22,530手(14.8%)，连续2个交易日减仓", "lines": ["高盛净多129,562手；09-30峰值152,092手，回落22,530手(14.8%)；连续2个交易日减仓累计-22,530手；近5个交易日-11,887手。", "注：这段里的部分点是下限估计(高盛只进了买方前20，卖方用第20名持仓顶替，该名次约2万多手)，绝对数值可能有几千到2万手的出入，所以看方向和量级，不要看个位数。", "距文档的12万手警戒线还差9,562手(文档：从16万级降到12万以下，资金市可能接近尾声)。", "这段减仓跨过国庆长假(节前减风险、节后复盘的成分较大)，文档提示长假前后的变动要打折看，且假期后只有很少几个交易日，是否延续要再看几天。", "CFTC管理基金净多处近156周的100%分位，连续7周增加(周度数据，截至2026-09-29，未反映之后的交易日；CBOT美国市场，与国内高盛是否同向没有验证过)。"], "evidence": ["历史检验(龙虎榜文件2020-12~2026-08，9个合约；高盛只有2026年入榜，样本主要是摩根大通)：外资3日净加仓≥1万手后，同合约未来5个交易日平均约+1.2%(约12个独立事件，无条件基准约+0.8%)，方向偏涨但样本小；", "外资3日净减仓≥1万手后，未来5个交易日平均约-0.2%(约17个独立事件)，和基准没有明显差别——减仓预示下跌没有证据，所以这里只描述'在撤退'，不写成看空信号；", "2020年4月及以前的龙虎榜无法取得，阈值是文档经验值，只检验了方向、没有调优。"]};
const MC = {available:true, mainContract:{key:'jan', symbol:'M2701', gross:822654}, date:'2026-10-09',
  members:{ '高盛期货':{net:129562, change:-8421, side:'long', rank:2, foreign:true, history:{n:24, since:'2026-08-31', run:{direction:'down', days:2, total:-22530, since:'2026-10-08', contract:'M2701'}, change5:{change:-11887}, change20:null}},
            '摩根大通':{net:1635, change:9505, side:'long', rank:12, foreign:true}, '瑞银期货':{net:11787, change:-194, side:'long', rank:10, foreign:true},
            '中粮期货':{net:-502772, change:-27174, side:'short', rank:1, foreign:false}, '国投期货':{net:-208344, change:7773, side:'short', rank:2, foreign:false} },
  industry:{net:-711116, change:-19401, changePct:-2.73, members:['中粮期货','国投期货']},
  cftc:{net:207578, netChange:16491, streakWeeks:7, streakDirection:'up', percentile:100, weeksUsed:156, reportDate:'2026-09-29'},
  state:{code:'crowded', level:'red', label:'外资多头拥挤', note:'旧说明', thresholdSource:'文档经验值，暂定，未回测'}, verdict: VERDICT};
function load(mc, tech){
  reset(); window._nowMs = NOW; window._technicalDirection = tech;
  window._syncedData = {generatedAt:new Date(NOW - 3600000).toISOString(), marketCapital: mc};
  updateOverallAlert();
}
const sum = ()=>makeEl('decisionSummary').innerHTML;
const firstRow = ()=>{ const h = sum(); const i = h.indexOf('<div class="dc-state'); if(i < 0) return ''; let d = 0; for(let k = i; k < h.length; k++){ if(h.startsWith('<div', k)) d++; else if(h.startsWith('</div>', k)){ d--; if(d === 0) return h.slice(i, k + 6); } } return h.slice(i); };
const T = h=>h.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
const lineOf = ()=>{ const m = firstRow().match(/<div class="dc-st-line">([\s\S]*?)<\/div>/); return m ? T(m[1]) : ''; };

// ===== 1. 顶部状态行：带方向，不再是一句"外资多头拥挤" =====
load(MC, '偏多');
check('★顶部资金面写"外资高位撤退中"(不是"外资多头拥挤")，灯🟡', /资金面：外资高位撤退中/.test(lineOf()) && !/资金面：外资多头拥挤/.test(lineOf()) && firstRow().includes('🟡'));
check('★状态区写出趋势数字：高盛从峰值152,092(09-30)降到129,562，较峰值回落22,530手(14.8%)，连续2个交易日减仓', ['152,092','129,562','22,530','14.8%','连续2个交易日'].every(s=>T(firstRow()).includes(s)));
check('★距文档12万手警戒线还差9,562手', T(firstRow()).includes('9,562') && T(firstRow()).includes('12万'));
check('★跨国庆长假要打折的提示在', T(firstRow()).includes('国庆'));
check('★含下限估计的提示在(绝对数值可能有出入)', T(firstRow()).includes('下限估计'));
check('★CFTC仍在顶部：近156周100%分位、连续7周增加、周度未反映最新交易日', T(firstRow()).includes('100%') && T(firstRow()).includes('7周') && T(firstRow()).includes('未反映'));
check('★诚实写出历史检验：减仓预示下跌没有证据；阈值是文档经验值', T(firstRow()).includes('没有证据') && T(firstRow()).includes('文档经验值'));
check('★不写交易指令', !/参与|观望|休息|建议|应该|不要做|别做/.test(T(firstRow())));

// ===== 2. 三信号对照(资金→基本面→价格结构) =====
const al = window._capitalAlignment;
check('导出了 _capitalAlignment', typeof al === 'function');
const A = (code, f, t)=>T((al(code, f, t) || {}).title || '') + ' ' + T((al(code, f, t) || {}).detail || '');
check('★撤退+基本面偏空+技术偏空：三项同向偏空', /三项同向/.test(A('retreat_from_high','偏空','偏空')));
check('★撤退+基本面偏空+技术偏多：资金和基本面同向，价格结构未确认(先资金→基本面→价格结构，现在在第二步)', /价格结构[^。]*(未确认|尚未确认)/.test(A('retreat_from_high','偏空','偏多')) && /基本面/.test(A('retreat_from_high','偏空','偏多')));
check('★撤退+基本面偏多：背离，不替用户选边，写"没有验证/没有回测"', /背离/.test(A('retreat','偏多','偏多')) && /没有(验证|回测)|未(验证|回测)/.test(A('retreat','偏多','偏多')));
check('★加仓+基本面偏空：背离——文档的"资金市"特征，基本面信号参考价值下降', /背离/.test(A('build_high','偏空','偏空')) && /资金市/.test(A('build_high','偏空','偏空')));
check('★加仓+基本面偏多：同向', /同向/.test(A('build','偏多','偏多')));
check('★无明显动作(crowded_flat)：以基本面为主', /无明显|没有明显/.test(A('crowded_flat','偏空','偏空')));
check('★趋势不可判(insufficient)/高盛未进榜：不做三项对照，写明', /不可判|无法判断|不做/.test(A('insufficient','偏空','偏空')) && /不可判|无法判断|不做/.test(A('no_member','偏空','偏空')));
check('基本面数据不足(null)：写明基本面缺失，不编方向', /基本面[^。]*(不足|缺)/.test(A('retreat_from_high',null,'偏多')));
// 页面上：基本面偏空(用后端风格直接调 marketStateHtml)
window._technicalDirection = '偏多';
const st = marketStateHtml(true, {direction:'偏空', ratio:-0.77});
check('★顶部同一块里：资金面撤退 | 基本面偏空(净倾向-77%)，并有三信号对照一句', /资金面：外资高位撤退中/.test(T(st)) && /基本面：偏空\(净倾向-77%\)/.test(T(st)) && /价格结构[^。]*(未确认|尚未确认)/.test(T(st)));

// ===== 3. 市场结构区块的资金持仓小节也带趋势 =====
load(MC, '偏多');
const cap = T(makeEl('structureContent').innerHTML);
check('★资金持仓小节里有趋势摘要(高位撤退、较峰值回落22,530手)', cap.includes('高位撤退') && cap.includes('22,530'));
check('★高盛那一行"历史趋势"写连续2日净多减少累计-22,530手', /高盛期货[^|]*连续2日净多减少，累计-22,530手/.test(cap));

// ===== 4. 降级：没有verdict(旧版latest.json) → 原来的拥挤度标签，不崩 =====
const MC_OLD = Object.assign({}, MC); delete MC_OLD.verdict;
load(MC_OLD, '偏多');
check('★旧版latest.json没有verdict：仍显示原来的"外资多头拥挤"，不崩、不出现undefined', /资金面：外资多头拥挤/.test(lineOf()) && !/undefined|NaN/.test(firstRow()));
load(Object.assign({}, MC, {verdict:{code:'insufficient', level:'red', short:'外资多头拥挤(趋势暂不可判：同合约连续历史仅2个交易日，攒够3日才判断)', label:'外资多头拥挤(趋势暂不可判：同合约连续历史仅2个交易日，攒够3日才判断)', lines:[], evidence:[]}}), '偏多');
check('★趋势不可判：灯保持🔴(沿用拥挤度)，并写明"趋势暂不可判"和天数', firstRow().includes('🔴') && /趋势暂不可判/.test(T(firstRow())) && T(firstRow()).includes('2个交易日'));
load(null, '偏多');
check('★资金面不可用：仍写"资金面数据不足"⚪', /资金面：数据不足/.test(lineOf()) && firstRow().includes('⚪'));

// ===== 5. 只读不写评分 =====
load(MC, '偏多'); const p1 = JSON.stringify([window._fundamentalPure, window._composite, window._structureSystem]);
load(null, '偏多'); const p2 = JSON.stringify([window._fundamentalPure, window._composite, window._structureSystem]);
check('★有/无verdict评分导出完全相同', p1 === p2);

H.printSummary();
