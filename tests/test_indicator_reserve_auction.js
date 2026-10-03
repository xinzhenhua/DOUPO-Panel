// ============================================================================
// 国储拍卖(v87起)：事件提示，不参与综合评分。规则本身(≥40万吨算规模较大)保留，用来给卡片写事实性说明。
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());
window._selectedContract = 'sep';
const RULES = window._manualRules;
const AUTO = window._autoByKey;

function resetFields(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry','m_rmspread','m_reserve'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import','ind_poultry','ind_rmspread','ind_reserve'].forEach(id=>elements[id]=makeEl(id));
  elements['alert_reserve'] = makeEl('alert_reserve');
  elements['alertContent'] = makeEl('alertContent');
  window._indState = {};
}

// ===================== 1. 规则本身没变(卡片上的事实性说明用) =====================
check('★拍卖54.3万吨(超过40万吨门槛)：规则判规模较大', RULES.reserve(54.3)[0] === -1 && RULES.reserve(54.3)[1].includes('规模较大'));
check('★小规模拍卖(5万吨，未超过40万吨门槛)：规则判中性，不是偏多', RULES.reserve(5)[0] === 0);
check('★没有拍卖(0万吨)：中性，文字提到"无新增供给压力"——"没有额外空头催化"不等于"看多"', RULES.reserve(0)[0] === 0 && RULES.reserve(0)[1].includes('无新增供给压力'));
check('★配置里标明这是事件提示、不计分，并带说明', AUTO.reserve.noVote === '事件提示' && AUTO.reserve.noVoteNote.includes('一次性') && AUTO.reserve.noVoteNote.includes('事件日历'));

// ===================== 2. 不参与综合评分 =====================
resetFields();
elements['m_reserve'].value = '54.3'; // 真实查证过的规模
updateOverallAlert();
check('★拍卖54.3万吨：供需表格里没有"国储拍卖"这一格(不再投票)', !/sd-cell[^>]*>国储拍卖/.test(elements['alertContent'].innerHTML));
check('★卡片结论框：中性色 + 事实描述 + "事件提示，不计入综合评分"，不是偏空', elements['alert_reserve'].innerHTML.includes('alert-box neutral') && elements['alert_reserve'].innerHTML.includes('国储拍卖54.3万吨') && elements['alert_reserve'].innerHTML.includes('事件提示') && elements['alert_reserve'].innerHTML.includes('不计入综合评分') && !elements['alert_reserve'].innerHTML.includes('alert-box bear'));
check('输入框旁的标记显示"不计分"', elements['ind_reserve'].textContent.includes('不计分'));
check('详细理由里写明未计入评分', elements['alertContent'].innerHTML.includes('事件提示，未计入评分') || elements['alertContent'].innerHTML.includes('数据不足'));

// 对总分没有任何影响：同一组其它数据下，有没有国储拍卖，结果完全一样
function scoreHtml(reserve){
  resetFields();
  ['crush','stock','basis','arrival','hogratio','import','poultry','rmspread'].forEach(k=>elements['m_'+k].value = ({crush:'35',stock:'40',basis:'10',arrival:'700',hogratio:'8',import:'700',poultry:'2',rmspread:'350'})[k]);
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
  if(reserve!==null) elements['m_reserve'].value = String(reserve);
  window._selectedContract = 'sep';
  H.setMockedMonth(5);
  updateOverallAlert();
  return elements['alertContent'].innerHTML.match(/(基本面偏多|基本面偏空|信号混合)[^<]*/)[0] + '|' + (elements['alertContent'].innerHTML.match(/有效\d+\/\d+项/)||[''])[0];
}
const base = scoreHtml(null), withBig = scoreHtml(80), withZero = scoreHtml(0);
check('★对总分没有任何影响：没填/填80万吨大拍卖/填0，综合结论和有效指标数完全相同', base === withBig && base === withZero);
H.clearMockedMonth();

// ===================== 3. 不填不报错 =====================
resetFields();
let ok = true; try { updateOverallAlert(); } catch(e){ ok = false; }
check('★不填这一项时不应该报错', ok);

// ===================== 4. 进事件日历 =====================
const E = window._eventCal;
elements['eventCalendarContent'] = makeEl('eventCalendarContent');
const nowMs = E.bjToMs(2026,9,30,10,0);
window._syncedData = {mysteelReserveAuction:{available:true, value:54.3, auctionDate:'2026-09-25', soldWan:19.2, soldRate:37.3}};
E.renderEventCalendar(nowMs);
let html = elements['eventCalendarContent'].innerHTML;
check('★最近发生的国储拍卖出现在事件日历：计划量/成交量/成交率，并解释成交率低的含义', html.includes('国储进口大豆拍卖(2026-09-25)') && html.includes('计划54.3万吨') && html.includes('成交19.2万吨') && html.includes('成交率37.3%') && html.includes('接货意愿弱'));
const auctionRow = (html.split('国储进口大豆拍卖(2026-09-25)')[1] || '').split('<div class="ir"')[0];
check('★国储拍卖这一行确实存在(先确认取到了要检查的内容)', auctionRow.includes('计划54.3万吨'));
check('★国储拍卖是国内事件，这一行不标注"大商所此时不在交易时段"(那是给美国报告用的)', !auctionRow.includes('大商所此时') && !auctionRow.includes('开盘体现'));
const usdaRow = (html.split('美国季度库存(Grain Stocks)')[1] || '').split('<div class="ir"')[0];
check('对照：美国季度库存那一行仍然标注大商所开市状态', usdaRow.includes('大商所此时不在交易时段'));
window._syncedData = {mysteelReserveAuction:{available:true, value:54.3, auctionDate:'2026-07-01', soldWan:19.2, soldRate:37.3}};
E.renderEventCalendar(nowMs);
check('超过21天前的拍卖不再出现', !elements['eventCalendarContent'].innerHTML.includes('国储进口大豆拍卖'));
window._syncedData = {mysteelReserveAuction:{available:false}};
E.renderEventCalendar(nowMs);
check('抓取失败时不出现、不报错', !elements['eventCalendarContent'].innerHTML.includes('国储进口大豆拍卖'));

H.printSummary();
