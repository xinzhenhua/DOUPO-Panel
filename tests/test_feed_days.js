// ============================================================================
// 饲料企业豆粕库存天数：卡片(环比/同比/趋势/去年同期)、分位信号、长假备货窗口降权、进评分/分组/健康度
// 数据是用户2026-09-30贴出的Mysteel真实搜索结果(20期，2026-05-15~09-24)
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
const E = window._eventCal;
const AUTO = window._autoIndicators, BYKEY = window._autoByKey;
const NOW = E.bjToMs(2026,9,30,10,0);          // 周三；最新一期09-24(周四)距今6天，周频正常
window._nowMs = NOW;
const KEYS = AUTO.map(c=>c.key);

// 真实的20期(由新到旧)：[日期, 天数, 环比(null=文章只写了方向), 同比]
const REAL = [['2026-09-24',8.55,0.32,-1.05],['2026-09-18',8.23,0.08,-1.19],['2026-09-11',8.15,-0.22,-1.07],['2026-09-04',8.37,0.27,-0.43],['2026-08-28',8.1,0.52,-0.77],
  ['2026-08-21',7.58,0.10,-0.93],['2026-08-14',7.48,0,-0.87],['2026-08-07',7.48,null,null],['2026-07-31',7.54,null,null],['2026-07-24',7.57,null,null],['2026-07-17',7.63,null,null],
  ['2026-07-10',7.58,0.17,-0.34],['2026-07-03',7.41,0.17,-0.50],['2026-06-26',7.24,null,null],['2026-06-18',7.15,0.09,-0.59],['2026-06-12',7.06,0.12,0.23],
  ['2026-06-05',6.94,-0.08,0.63],['2026-05-29',7.02,0.41,1.03],['2026-05-22',6.61,-0.14,0.88],['2026-05-15',6.75,-0.58,1.61]];
const recentWeeks = REAL.map(([date,value,mom,yoy])=>({date, value, mom, yoy}));
// ★v96起信号用"往年同月"分位(history.seasonal.percentile)，全部历史分位(history.percentile)只展示、不计分。
//   hist({percentile:X}) 表示"往年同月分位=X"(计分用)；overall=全部历史分位(只展示，默认55)；seasonalN=同月样本数(默认23，即2021-2025年的9月)；
//   percentile:null 表示历史不够(没有分位/跨度不足/样本不足)——此时seasonal也为null。
const hist = (o)=>{
  o = o || {};
  const p = o.percentile === undefined ? 96 : o.percentile;
  const base = {n:269, minPoints:12, asOf:'2026-09-24', since:'2021-05-21', percentile: p === null ? null : (o.overall === undefined ? 55 : o.overall), min:4.35, max:12.64, median:8.15, cohort:null, sparse:null, window:null,
    seasonal: p === null ? null : {month:9, n: o.seasonalN === undefined ? 23 : o.seasonalN, percentile: p, median:9.45}};
  const rest = Object.assign({}, o); delete rest.percentile; delete rest.overall; delete rest.seasonalN;
  return Object.assign(base, p === null && o.n === undefined ? {n:8} : {}, rest);
};
const feedData = (o)=>Object.assign({available:true, value:8.55, date:'2026-09-24', momDays:0.32, yoyDays:-1.05, lastYearValue:9.6, holiday:null,
  articleTitle:'Mysteel数据：全国主要地区饲料企业豆粕库存天数调查（20260924）', publishDate:'2026-09-24', extractedFrom:'summary', recentWeeks, history:hist(),
  source:'Mysteel文章', sourceUrl:'x'}, o||{});
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); });
  window._indState = {}; makeEl('alertContent');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
  window._selectedContract='sep';
}
const html = k=>makeEl('ai_'+k).innerHTML;

// ===================== 1. 配置 =====================
const cfg = BYKEY.feed;
check('★配置：需求端、周频、单位天、数据来源Mysteel、合理范围key=feedDays', cfg.group==='demand' && cfg.cadence==='weekly' && cfg.unit==='天' && cfg.dataKey==='mysteelFeedDays' && cfg.sanityKey==='feedDays');
check('★评分分组：归"需求(养殖/替代)"组', voteGroup('饲料企业豆粕库存天数') === 'demand');

// ===================== 2. 卡片展示(9-24真实一期，有历史分位) =====================
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData()};
refreshMysteelFeedDays();
check('★输入框被自动覆盖为8.55', makeEl('m_feed').value == '8.55');
check('★徽标：自动 + 数据日期', makeEl('badge_feed').textContent.includes('自动') && makeEl('badge_feed').textContent.includes('2026-09-24'));
let d = html('feed');
check('★环比：文章明示的+0.32天，说明"饲料厂手里的货变多"', d.includes('环比') && d.includes('+0.32天') && d.includes('手里的货变多'));
check('★同比：-1.05天，去年同期约9.6天，并说明同比天然去掉季节因素', d.includes('同比') && d.includes('-1.05天') && d.includes('去年同期约9.6天') && d.includes('去掉了季节因素'));
check('★近20期区间6.61~8.55(注意：区间取的是给出的20期)、本期是这段时间的最高值', d.includes('近20期') && d.includes('最低6.61天') && d.includes('最高8.55天') && d.includes('本期是这段时间的最高值'));
check('★连续上升周数：最近两期(9-18、9-24)是上升，9-11是下降 → 连续2周上升', d.includes('已连续2周上升'));
check('★数据日期和样本说明(50家饲料企业)', d.includes('数据日期2026-09-24') && d.includes('50家饲料企业'));
check('详情里显示历史分位(自2025-09-26起52期的96%)', d.includes('历史分位') && d.includes('96%'));

// 环比只写了方向(没数字)：用相邻两期的差算
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({value:7.48, date:'2026-08-07', momDays:null, yoyDays:null, lastYearValue:null,
  recentWeeks: recentWeeks.filter(w=>w.date <= '2026-08-07')})};
refreshMysteelFeedDays();
check('★文章只写"环比微降"(没数字)：用相邻两期(7.48-7.58...)算出，并说明是按相邻两期算的', html('feed').includes('按相邻两期算出'));
check('没有同比数字时不显示同比行、不出现undefined/NaN', !html('feed').includes('同比') && !/undefined|NaN/.test(html('feed')));

// ===================== 3. 分位规则 =====================
const R = window._manualRules.feed;
function ruleWith(hh, v){ window._indState.feed = {history: hh}; return R(v === undefined ? 8.55 : v); }
check('★往年同月分位96%(≥80)：偏空，写明"饲料厂手里有货，近期补库需求弱"和"往年9月23个样本"', ruleWith(hist({percentile:96}))[0] === -1 && ruleWith(hist({percentile:96}))[1].includes('补库需求弱') && ruleWith(hist({percentile:96}))[1].includes('往年9月23个样本'));
check('★分位10%(≤20)：偏多，写明"饲料厂需要补库"', ruleWith(hist({percentile:10}))[0] === 1 && ruleWith(hist({percentile:10}))[1].includes('需要补库'));
check('分位50%：中性(常态区间)', ruleWith(hist({percentile:50}))[0] === 0 && ruleWith(hist({percentile:50}))[1].includes('常态区间'));
check('边界：80%偏空、20%偏多、79.9%/20.1%中性', ruleWith(hist({percentile:80}))[0] === -1 && ruleWith(hist({percentile:20}))[0] === 1 && ruleWith(hist({percentile:79.9}))[0] === 0 && ruleWith(hist({percentile:20.1}))[0] === 0);
let r = ruleWith(hist({percentile:null, n:8}));
check('★没有往年同月样本(seasonal=null)：返回[null,说明]——不是中性，是"暂不计分"，并写明"还没有往年同月的样本"', r[0] === null && r[1].includes('还没有往年同月的样本') && r[1].includes('暂不计分'));
r = ruleWith(hist({percentile:null, sparse:'样本只跨134天，不足180天'}));
check('★样本跨度不足：把原因写出来(真实场景：这20期只跨了134天)', r[0] === null && r[1].includes('样本只跨134天，不足180天'));
r = ruleWith(null);
check('没有history字段：[null,"还没有历史序列"]，不报错', r[0] === null && r[1].includes('还没有历史序列'));

// ===================== 3b. ★v96核心：信号用"往年同月"分位，不用"全部历史"分位(用真实数字：2026-09-24 全部历史59.7%、往年同月13.0%) =====================
const REAL_HIST = {n:269, minPoints:12, asOf:'2026-09-24', since:'2021-05-21', percentile:59.7, min:4.35, max:12.64, median:8.15, seasonal:{month:9, n:23, percentile:13.0, median:9.45}, cohort:null, sparse:null, window:null};
r = ruleWith(REAL_HIST);
check('★真实数字：全部历史59.7%(中性)、往年同月13.0%(偏低) → 以往年同月为准：偏多(+1)', r[0] === 1 && r[1].includes('13%分位') && r[1].includes('往年9月23个样本') && r[1].includes('偏多'));
check('★文案里不出现全部历史的59.7%(它不参与计分)', !r[1].includes('59.7'));
r = ruleWith(Object.assign({}, REAL_HIST, {percentile:96, seasonal:{month:9, n:23, percentile:50, median:9.45}}));
check('★反过来：全部历史96%(会被判偏空)、往年同月50% → 以往年同月为准：中性(0)——证明全部历史分位确实不再参与', r[0] === 0 && r[1].includes('常态区间'));
r = ruleWith(Object.assign({}, REAL_HIST, {seasonal:{month:9, n:11, percentile:5, median:9.45}}));
check('★往年同月样本不足12个(11)：不判，写明"往年同月样本只有11个(需要≥12个)"——即使分位是5%', r[0] === null && r[1].includes('往年同月样本只有11个') && r[1].includes('需要≥12个'));
r = ruleWith(Object.assign({}, REAL_HIST, {seasonal:{month:9, n:12, percentile:5, median:9.45}}));
check('边界：同月样本恰好12个：可以判(偏多)', r[0] === 1);
r = ruleWith(Object.assign({}, REAL_HIST, {seasonal:null}));
check('★没有往年同月(seasonal=null)：不退回用全部历史分位(59.7%)，而是暂不计分并说明原因', r[0] === null && r[1].includes('还没有往年同月的样本') && r[1].includes('不退回用全部历史分位'));
// 卡片整体：用真实数字渲染，应当判偏多
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({history: REAL_HIST, holiday:null})};
refreshMysteelFeedDays(); updateOverallAlert();
check('★整张卡片用真实数字渲染：结论偏多(往年同月13%)，详情里同时列出"往年同月13%(用于计分)"和"全部历史59.7%(只展示)"', makeEl('alert_feed').innerHTML.includes('alert-box bull') && html('feed').includes('<b>13%</b>') && html('feed').includes('59.7%') && html('feed').includes('只展示、不计分'));

// ===================== 4. 长假备货窗口(v96：用270周真实数据校准；春节降权、国庆不降权) =====================
const GUOQING = {name:'国庆', daysTo:-7, phase:'节前备货', holidayDate:'2026-10-01'};
const CHUNJIE = {name:'春节', daysTo:-14, phase:'节前备货', holidayDate:'2027-02-06'};
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({holiday:GUOQING})};
refreshMysteelFeedDays();
d = html('feed');
check('★国庆前7天：计分用的是往年同月分位(同类对同类，每年9月都含节前备货)——所以不降权，质量乘数=1', qualityOf('feed').m === 1 && !makeEl('ai_feed').innerHTML.includes('票权×0.5'));
check('★国庆：详情里说明"不降权"和原因(往年同月分位已含节前备货，再降权就重复扣了)，并给出校准数据(节前35~28天+0.9天→节前7~0天+2.3天)', d.includes('不降权') && d.includes('同类对同类') && d.includes('+0.9天') && d.includes('+2.3天'));
check('★国庆：徽标仍是"自动"(没有被降权)', makeEl('badge_feed').textContent.includes('自动') && !makeEl('badge_feed').textContent.includes('长假备货窗口'));
check('详情里同时展示两个分位：往年同月(用于计分)和全部历史(只展示、不计分，并说明季节性很强)', d.includes('往年同月') && d.includes('用于计分') && d.includes('全部历史') && d.includes('只展示、不计分') && d.includes('1月中位10.1天'));
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({holiday:CHUNJIE})};
refreshMysteelFeedDays();
d = html('feed');
check('★春节前14天：降权(春节日期在1月22日~2月17日之间浮动，同月比较会错位)，票权×0.5', qualityOf('feed').m === 0.5 && d.includes('票权×0.5') && d.includes('春节节前备货窗口') && d.includes('浮动'));
check('★春节：写明依据是用270周数据校准的(节前21~14天+1.8天、14~7天+2.9天、7~0天+2.9天、节后7~14天-0.1天)，窗口=节前21天~节后7天', d.includes('用你的270周数据校准') && d.includes('+1.8天') && d.includes('+2.9天') && d.includes('-0.1天') && d.includes('节前21天~节后7天'));
check('质量乘数×0.5，理由里点名春节前14天', qualityOf('feed').why.includes('春节前14天'));
check('★春节：徽标如实反映降权："长假备货窗口·降权"，不是"自动"', makeEl('badge_feed').textContent.includes('长假备货窗口') && makeEl('badge_feed').textContent.includes('降权') && !makeEl('badge_feed').textContent.includes('🟢') && makeEl('badge_feed').className.includes('badge-manual'));
// 往年同月样本不足时，国庆也降权(无法剔除节前备货)
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({holiday:GUOQING, history:hist({percentile:50, seasonalN:8})})};
refreshMysteelFeedDays();
check('★往年同月样本不足(8<12)时，国庆也降权：无法剔除节前备货的影响', qualityOf('feed').m === 0.5 && html('feed').includes('往年同月样本不足，无法剔除节前备货'));
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({holiday:null})};
refreshMysteelFeedDays();
check('对照：不在长假窗口：乘数1，没有备货窗口的说明，徽标是"自动"', qualityOf('feed').m === 1 && !html('feed').includes('备货窗口') && makeEl('badge_feed').textContent.includes('自动'));
window._indState.feed.holidayDiscount = '春节前3天(节前备货窗口)'; onManualEdit('feed');
check('★用户手动修正后不再打折(视为自己负责)', qualityOf('feed').m === 1);

// ===================== 5. 进综合评分 =====================
const fill = {crush:'50', stock:'70', stu:'12', basis:'0', arrival:'900', import:'900', hogratio:'6', poultry:'1', rmspread:'550'};
function scoreScenario(feedObj){
  reset(); H.setMockedMonth(5);
  Object.keys(fill).forEach(k=>{ makeEl('m_'+k).value = fill[k]; window._indState[k] = {mode:'auto', dataDate:'2026-09-27'}; });
  window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedObj};
  refreshMysteelFeedDays(); updateOverallAlert();
  return makeEl('alertContent').innerHTML;
}
const cell = a => (a.match(/sd-cell (sd-\w+)">饲料企业豆粕库存天数/)||[])[1];
let a = scoreScenario(feedData({history:hist({percentile:96})}));
check('★分位96%：供需表格里"饲料企业豆粕库存天数"是偏空格(▼)，属于需求侧', cell(a) === 'sd-neg' && a.includes('饲料企业豆粕库存天数 ▼'));
check('详细理由里有偏空原因', a.includes('饲料厂手里有货，近期补库需求弱'));
a = scoreScenario(feedData({history:hist({percentile:10})}));
check('分位10%：偏多格(▲)', cell(a) === 'sd-pos');
a = scoreScenario(feedData({history:hist({percentile:50})}));
check('分位50%：中性格(—)', cell(a) === 'sd-neutral');
a = scoreScenario(feedData({history:hist({percentile:null, n:20, sparse:'样本只跨134天，不足180天'})}));
check('★历史不够：这一票在清单里但没信号(空格)——作为"缺席的投票"如实列出', cell(a) === 'sd-empty' && window._quality.missing.some(x=>x.includes('饲料企业豆粕库存天数')));
check('★卡片结论框：中性色 + "暂不计入综合评分"(不是偏空/偏多)', makeEl('alert_feed').innerHTML.includes('alert-box neutral') && makeEl('alert_feed').innerHTML.includes('暂不计入综合评分') && makeEl('alert_feed').innerHTML.includes('历史样本积累中'));
check('输入框旁标记显示"暂不计分"', makeEl('ind_feed').textContent.includes('暂不计分'));
// 需求侧净倾向：偏空 < 中性
a = scoreScenario(feedData({history:hist({percentile:50})})); const dNeutral = window._dimensions.demand.ratio;
a = scoreScenario(feedData({history:hist({percentile:96})}));
check('★饲料天数偏空 → 需求端净倾向比中性时更低', window._dimensions.demand.ratio < dNeutral);
// 备货窗口降权：同样偏空，票权减半 → 净倾向的变化更小
a = scoreScenario(feedData({history:hist({percentile:96}), holiday:null})); const rFull = window._dimensions.demand.ratio;
a = scoreScenario(feedData({history:hist({percentile:96}), holiday:CHUNJIE})); const rHalf = window._dimensions.demand.ratio;
check('★同样偏空：春节前14天窗口内票权×0.5 → 需求端偏空程度比窗口外更小', rHalf > rFull && rHalf < dNeutral);
a = scoreScenario(feedData({history:hist({percentile:96}), holiday:GUOQING})); const rNat = window._dimensions.demand.ratio;
check('★同样偏空：国庆前7天不降权 → 需求端偏空程度与窗口外完全相同(往年同月分位已含节前备货)', rNat === rFull);
a = scoreScenario(feedData({history:hist({percentile:96}), holiday:CHUNJIE}));       // 自己造春节降权场景，不依赖前面场景留下的状态
check('★春节降权时，质量分点名被降权的是饲料企业豆粕库存天数(×0.5)；国庆不降权时质量分里没有它', window._quality.lowItems.some(x=>x.label.includes('饲料企业豆粕库存天数') && x.q === 0.5)
  && (scoreScenario(feedData({history:hist({percentile:96}), holiday:GUOQING})), !window._quality.lowItems.some(x=>x.label.includes('饲料企业豆粕库存天数'))));

// 还没评估过(mode未定义)：不进投票清单，不改变旧场景的票数
reset(); H.setMockedMonth(5);
Object.keys(fill).forEach(k=>{ makeEl('m_'+k).value = fill[k]; window._indState[k] = {mode:'auto', dataDate:'2026-09-27'}; });
updateOverallAlert();
check('★没有评估过饲料库存天数(_indState.feed没有mode)：这一票不在投票清单里(供需表格没有)', !/sd-cell[^>]*>饲料企业豆粕库存天数/.test(makeEl('alertContent').innerHTML));

// ===================== 6. 失败/过期 =====================
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays:{available:false, reason:'最新一期是45天前，可能停更；不采用'}};
refreshMysteelFeedDays();
check('★抓取失败：显示原因，不填入，徽标"抓取失败"', makeEl('m_feed').value === '' && html('feed').includes('可能停更') && makeEl('badge_feed').textContent.includes('抓取失败'));
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({date:'2026-08-20'})};     // 41天前：周频>16天过期
refreshMysteelFeedDays();
check('★数据41天前：过期，徽标"数据过期·不计分"', makeEl('badge_feed').textContent.includes('数据过期') && html('feed').includes('不参与综合评分'));
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({date:'2026-09-17'})};        // 13天前：周频晚了一期
refreshMysteelFeedDays();
check('数据13天前(周频9天内正常)：晚了一期，票权×0.5', makeEl('badge_feed').textContent.includes('晚了一期') && qualityOf('feed').m === 0.5);
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({value:88})};
refreshMysteelFeedDays();
check('★数值荒谬(88天，超出1~30天合理范围)：不填入，并警告"不合理"和范围', makeEl('m_feed').value === '' && html('feed').includes('不合理') && html('feed').includes('超出合理范围'));

// ===================== 7. 健康度 =====================
elements['healthContent'] = makeEl('healthContent'); elements['healthBadge'] = makeEl('healthBadge');
reset(); H.setMockedMonth(5);
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({history:hist({percentile:null, n:20, sparse:'样本只跨134天，不足180天'})})};
refreshMysteelFeedDays(); updateOverallAlert();
let hh = computeDataHealth(NOW); let row = hh.rows.find(x=>x.key==='feed');
check('★历史样本积累中：健康度显示⏳(不是⚪无数据)，不算投票指标，写明原因', row.state==='pending' && row.icon==='⏳' && row.votes===false && row.detail.includes('样本只跨134天'));
reset();
window._syncedData = {generatedAt:new Date(NOW).toISOString(), mysteelFeedDays: feedData({history:hist({percentile:96}), holiday:CHUNJIE})};
refreshMysteelFeedDays(); updateOverallAlert();
row = computeDataHealth(NOW).rows.find(x=>x.key==='feed');
check('★春节备货窗口降权：健康度显示🟡降权×0.5，写明原因', row.state==='degraded' && row.label.includes('×0.5') && row.detail.includes('春节前14天'));

// ===================== 8. 同一份真实数据的自洽检查 =====================
let bad = 0;
for(let i=1;i<REAL.length;i++){                          // REAL由新到旧：本期-上期=文章写的环比(有数字的那些)
  const [d0,v0,m0] = REAL[i-1], [d1,v1] = REAL[i];
  if(m0 !== null && Math.abs((v0 - v1) - m0) > 0.015) bad++;
}
check('★真实数据自洽：文章写的环比 = 本期天数 - 上期天数(误差≤0.015)，20期里有数字的环比全部吻合', bad === 0);
check('★真实数据里"环比微降"的几期(没有数字)，按相邻两期算出的差方向也是负的(7-31: -0.03, 7-24: -0.06...)', (7.54-7.57) < 0 && (7.57-7.63) < 0 && (7.48-7.54) < 0);

H.clearMockedMonth(); window._nowMs = null;
H.printSummary();
