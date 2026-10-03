// ============================================================================
// 综合评分 v2：净倾向归一化/数据不足/合并投票/出口销售信号/仪表单位
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
window._selectedContract = 'sep';
H.setMockedMonth(5);   // 固定5月(9月合约窗口，作物票"参与"档×1)，不随真实日期变化

const ALL = ['crush','stock','stu','basis','arrival','hogratio','sows','import','poultry','rmspread','reserve'];
function reset(){
  ALL.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); window._indState[k] = {}; });
  makeEl('alertContent');
  window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null;
  window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
}
const AUTO = window._autoIndicators;
window._indState = window._indState || {};
// 12票全中性的基线(sep合约：作物/库存消费比/供应松紧/到港进口/汇率/国储/出口销售/基差/猪粮比/能繁/肉鸡/豆菜粕价差)
function neutralBaseline(){
  reset();
  const v = {crush:50, stock:70, stu:12, basis:0, arrival:900, import:900, hogratio:6, sows:3750, poultry:1, rmspread:550, reserve:0};
  Object.keys(v).forEach(k=>makeEl('m_'+k).value = String(v[k]));
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0;
  window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
}
const html = ()=>makeEl('alertContent').innerHTML;

// ===================== 1. 净倾向 = 分数÷有效指标数；门槛0.22 =====================
neutralBaseline(); updateOverallAlert();
check('★9个供需投票全中性：应显示"信号混合"，有效9/9(国储拍卖、能繁母猪已移出评分；基差是市场结构票，v97起不在顶部)', html().includes('信号混合') && html().includes('有效9/9'));
check('全中性时基本面方向为中性(供三方共振读取)', window._fundamentalDirection === '中性');

neutralBaseline(); window._psdSignal=1; window._fxSignal=1; updateOverallAlert();
check('★9个供需投票(有效票权10，国内供应松紧占2)中2票偏多(2÷10=20%<22%)：仍是信号混合，不下方向结论', html().includes('信号混合 +2（净倾向+20%）') && window._fundamentalDirection === '中性');

neutralBaseline(); window._psdSignal=1; window._fxSignal=1; window._esrSignal=1; updateOverallAlert();
check('★9个供需投票(有效票权10)中3票偏多(3÷10=30%≥22%)：基本面偏多', html().includes('基本面偏多 +3（净倾向+30%）') && window._fundamentalDirection === '偏多');

neutralBaseline(); window._psdSignal=-1; window._fxSignal=-1; window._esrSignal=-1; updateOverallAlert();
check('★3票偏空 → 基本面偏空，方向"偏空"(-3÷10=-30%)', html().includes('基本面偏空 -3（净倾向-30%）') && window._fundamentalDirection === '偏空');
check('结论框写明多/中/空分布(9个供需票：3空+6中)', html().includes('0多 6中 3空'));

// 有效指标变少时门槛按比例降低：8票中2票偏多=25%
neutralBaseline(); ['poultry','rmspread'].forEach(k=>makeEl('m_'+k).value=''); window._psdSignal=1; window._fxSignal=1; updateOverallAlert();
check('★有效指标少(7个供需投票，有效票权8)：2票偏多(2÷8=25%≥22%)即基本面偏多(门槛是固定的22%，不是按比例降低；原2÷9=22%刚好压线，v97起基差不计入后是25%)', html().includes('基本面偏多 +2（净倾向+25%）') && html().includes('有效7/9'));

// ===================== 2. 数据不足：有效指标<5不下结论 =====================
reset(); makeEl('m_crush').value='35'; makeEl('m_stock').value='40'; makeEl('m_basis').value='10'; makeEl('m_hogratio').value='8';
window._weatherRisk = null; updateOverallAlert();
check('★有效指标<5(这里只有2个供需票：供应松紧/猪粮比；基差是市场结构票，不计入顶部)：不下结论，显示"数据不足"', html().includes('数据不足，暂不下结论') && html().includes('只有2项'));
check('★数据不足时基本面方向置空(不让三方共振沿用旧值)', window._fundamentalDirection === null);
check('数据不足时仍显示供需表格，方便看缺哪些', html().includes('sd-table'));

// 覆盖率低(有效5/12=42%<60%)：能下结论，但提示可信度较低
reset(); makeEl('m_crush').value='35'; makeEl('m_stock').value='40'; makeEl('m_basis').value='10'; makeEl('m_hogratio').value='8'; makeEl('m_poultry').value='2';
window._psdSignal = 1; window._fxSignal = 1;   // v97：基差不再计入顶部，原靠它凑的5票变4票；补人民币汇率(成本类供需票)凑够5项
updateOverallAlert();
check('★有效5项(<60%覆盖)：给出结论但提示"有效指标偏少，结论可信度较低"', html().includes('基本面偏多') && html().includes('有效指标偏少'));

// ===================== 3. 合并投票：库存+开机率=1票，到港+进口=1票 =====================
function votesOf(){ return (html().match(/sd-cell/g)||[]).length; }
reset(); makeEl('m_stock').value='40'; makeEl('m_crush').value='35'; updateOverallAlert();
check('★库存+开机率同时有数据：只占1格(合并成"国内豆粕供应松紧")', /sd-cell sd-pos">国内豆粕供应松紧/.test(html()) && !/sd-cell sd-\w+">(开机率|商业库存)/.test(html()));
reset(); makeEl('m_stock').value='40'; makeEl('m_crush').value='70'; updateOverallAlert();   // 库存偏多(60权重)，开机率偏空(40权重) → 平均+0.2 → 中性
check('★库存偏多+开机率偏空：加权平均0.2 → 合并结果中性(权重60/40，不是各投一票抵消)', /sd-cell sd-neutral">国内豆粕供应松紧/.test(html()));
reset(); makeEl('m_stock').value='120'; makeEl('m_crush').value='70'; updateOverallAlert();
check('★库存偏空+开机率偏空 → 合并偏空', /sd-cell sd-neg">国内豆粕供应松紧/.test(html()));
reset(); makeEl('m_crush').value='35'; updateOverallAlert();
check('★只有开机率有数据时，合并信号用开机率(缺一项不会让整个信号失效)', /sd-cell sd-pos">国内豆粕供应松紧/.test(html()));
reset(); makeEl('m_arrival').value='700'; makeEl('m_import').value='1200'; updateOverallAlert();   // 到港偏多(60)，进口偏空(40) → +0.2 → 中性
check('★到港预报偏多+进口量偏空：加权平均0.2 → 中性', /sd-cell sd-neutral">大豆到港\/进口/.test(html()));
reset(); makeEl('m_arrival').value='700'; makeEl('m_import').value='700'; updateOverallAlert();
check('★到港+进口同时偏多 → 合并偏多，只占1格', /sd-cell sd-pos">大豆到港\/进口/.test(html()) && !/sd-cell sd-\w+">(到港预报|进口量)/.test(html()));
check('详细理由里说明"合并为1票"', html().includes('合并为1票'));

// ===================== 4. 出口销售信号：本周净销售 vs 近4周均值 =====================
const seasonal = (pct,n)=>({history:{n:300, percentile:50, seasonal:{month:9, n:n===undefined?40:n, percentile:pct, median:1}}});
check('★近4周净销售合计在往年同月分位85% → 偏多', esrSignalFrom(seasonal(85)) === 1);
check('★分位80%(边界) → 偏多；79.9% → 中性', esrSignalFrom(seasonal(80)) === 1 && esrSignalFrom(seasonal(79.9)) === 0);
check('★分位15% → 偏空；20%(边界)偏空；20.1% → 中性', esrSignalFrom(seasonal(15)) === -1 && esrSignalFrom(seasonal(20)) === -1 && esrSignalFrom(seasonal(20.1)) === 0);
check('★分位50% → 中性', esrSignalFrom(seasonal(50)) === 0);
check('★同月样本不足20个 → null，不投票', esrSignalFrom(seasonal(95, 19)) === null && esrSignalFrom(seasonal(95, 20)) === 1);
check('★没有history/seasonal字段(刚部署、历史还没累积) → null，不投票——旧的±40%规则已弃用', esrSignalFrom({vs4wAvgPct:60, avg4wNetSalesMT:500000}) === null && esrSignalFrom({history:{n:300, seasonal:null}}) === null && esrSignalFrom({history:{n:5, seasonal:{month:9,n:0,percentile:null}}}) === null);
check('★最新一周是市场年度切换周 → null(净销售含结转，虚高)，即使历史分位很高', esrSignalFrom(Object.assign({latestIsRollover:true}, seasonal(99))) === null);

elements['esrBadge']=makeEl('esrBadge'); elements['esrContent']=makeEl('esrContent');
window._nowMs = Date.UTC(2026, 9, 1, 2, 0);   // ★固定"现在"=2026-10-01：下面的ESR数据日期是固定的weekEnding='2026-09-24'，新鲜度判断读时钟——不固定的话，真实时钟走到12月它就"过期"了
const esrNew = {available:true, commodity:'Soybeans(大豆)', weekEnding:'2026-09-24', marketYearUsed:2026, dataAgeDays:5, isStale:false,
  netSalesMT:1200000, prevNetSalesMT:800000, avg4wNetSalesMT:700000, vs4wAvgPct:71.4, wowChangePct:50, shipmentsMT:900000, chinaNetSalesMT:450000, chinaShipmentsMT:0,
  history:{n:300, minPoints:12, since:'2014-10', percentile:90, min:1, max:9, median:4, basis:'近4周净销售合计', seasonal:{month:9, n:40, percentile:88, median:3}}};
renderEsr(esrNew, new Date().toISOString());
check('★出口销售渲染：历史同月分位88%→偏多，写入window._esrSignal', window._esrSignal === 1 && makeEl('esrContent').innerHTML.includes('分位88%'));
renderEsr(Object.assign({}, esrNew, {history:undefined}), new Date().toISOString());
check('★没有历史样本时：信号null，界面说明"历史同月样本不足，暂不判断方向"', window._esrSignal === null && makeEl('esrContent').innerHTML.includes('历史同月样本不足'));
renderEsr(Object.assign({}, esrNew, {latestIsRollover:true, vs4wAvgPct:null, wowChangePct:null, total4wSumMT:null}), new Date().toISOString());
check('★最新周是市场年度切换周：信号null，界面说明净销售含结转、虚高，且不显示"较近4周均值"', window._esrSignal === null && makeEl('esrContent').innerHTML.includes('市场年度切换周') && !makeEl('esrContent').innerHTML.includes('较近4周均值--'));
renderEsr(esrNew, new Date().toISOString());
check('★出口销售详情：显示中国净销售、装船量、4周均值，并说明净销售≠装船量', makeEl('esrContent').innerHTML.includes('450,000') && makeEl('esrContent').innerHTML.includes('本周装船量') && makeEl('esrContent').innerHTML.includes('近4周均值') && makeEl('esrContent').innerHTML.includes('净销售=当周新签'));
renderEsr({available:true, weekEnding:'2026-09-24', marketYearUsed:2026, latestTotalMT:308051, prevTotalMT:248336, wowChangePct:24.0, chinaLatestMT:0}, new Date().toISOString());
check('★★旧版后端数据(豆粕口径，装船量冒充净销售)：必须忽略，信号null，提示等待重新同步', window._esrSignal === null && makeEl('esrContent').innerHTML.includes('旧版本后端') && makeEl('esrBadge').textContent.includes('旧版'));

// ===================== 5. 仪表单位 =====================
check('仪表可显示百分比单位', renderGaugeSVG(36, -66, 66, '%').includes('+36%'));
check('默认单位仍是"分"(向后兼容)', renderGaugeSVG(5, -14, 14).includes('+5分'));
check('★量程±66：22%的方向门槛正好落在仪表1/3分界线上(指针在偏多区段的起点)', (()=>{
  const g = renderGaugeSVG(22, -66, 66, '%'); return g.includes('+22%');
})());

H.clearMockedMonth();
H.printSummary();
