// ============================================================================
// 国内豆粕库存消费比：卡片显示/判定/过期/回退提示 + 评分里的组内权重(50/30/20)与双倍票权 + ESR中国/未知拆分展示
// ============================================================================
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
window._selectedContract = 'sep';
H.setMockedMonth(7);
const AUTO = window._autoIndicators;
const dayStr = n => new Date(Date.now() - n*86400000).toISOString().slice(0,10);

const KEYS = AUTO.map(c=>c.key);
function reset(){
  KEYS.forEach(k=>{ makeEl('m_'+k).value=''; makeEl('ind_'+k); makeEl('alert_'+k); makeEl('badge_'+k); makeEl('ai_'+k); window._indState[k] = {}; });
  makeEl('alertContent');
  window._weatherRisk=null; window._droughtSignal=null; window._noaaOutlookSignal=null; window._soyCondSignal=null;
  window._esrSignal=null; window._fxSignal=null; window._psdSignal=null;
}
const html = ()=>makeEl('alertContent').innerHTML;
const stuData = (o)=>Object.assign({available:true, value:16.04, month:'2026-09', monthLabel:'2026年9月', isForecast:true, usedFallbackMonth:false,
  method:'stated', methodLabel:'文章明示', recordSource:'body', stockWan:125, consumptionWan:779, productionWan:795,
  next:null, trend:null, weeklyCheck:null, date:dayStr(29), articleAgeDays:29, articleTitle:'Mysteel：全国豆粕供需平衡表（2026年8月）'}, o||{});

// ===================== 1. 卡片：判定+展示 =====================
reset();
window._syncedData = {mysteelMealStu: stuData({next:{month:'2026-10', monthLabel:'2026年10月', value:14.2}, trend:{delta:-1.84, direction:'下降(去库)'},
  weeklyCheck:{stockWan:121, stockDate:'2026-09-26', consumptionWan:779, value:15.53}})};
refreshMysteelMealStu();
check('★库消比输入框被自动覆盖为16.04', makeEl('m_stu').value == '16.04');
check('★结论框：16.04%≥14% → 偏空，写明阈值', makeEl('alert_stu').innerHTML.includes('alert-box bear') && makeEl('alert_stu').innerHTML.includes('≥14%') && makeEl('alert_stu').innerHTML.includes('供应宽松'));
check('★徽标：自动 + 文章发布日期', makeEl('badge_stu').textContent.includes('自动') && makeEl('badge_stu').className.includes('badge-auto'));
const d = makeEl('ai_stu').innerHTML;
check('详情：标明是预测值+月份', d.includes('2026年9月(预测)库消比16.04%'));
check('详情：显示月末库存÷当月消费', d.includes('月末库存125万吨') && d.includes('当月消费779万吨'));
check('详情：显示采用值来源方式(文章明示)和文章标题/发布日期', d.includes('文章明示') && d.includes('全国豆粕供需平衡表（2026年8月）'));
check('★详情：显示下月库消比和趋势(去库)', d.includes('2026年10月') && d.includes('14.2%') && d.includes('下降(去库)') && d.includes('-1.84个百分点'));
check('★详情：显示周度库存交叉核对(15.53%)并说明不是月末值', d.includes('交叉核对') && d.includes('15.53%') && d.includes('不是月末值'));

// 没有下月数据时如实说明，而不是留空
reset(); window._syncedData = {mysteelMealStu: stuData()}; refreshMysteelMealStu();
check('★没有下月数据时如实说明"正文只公开到第2个月"', makeEl('ai_stu').innerHTML.includes('暂无下月数据'));

// 判定阈值边界：≤10偏多，≥14偏空，之间中性
[[9.99,'bull'],[10,'bull'],[10.01,'neutral'],[12.45,'neutral'],[13.99,'neutral'],[14,'bear'],[5.94,'bull']].forEach(([v,cls])=>{
  reset(); window._syncedData = {mysteelMealStu: stuData({value:v})}; refreshMysteelMealStu();
  check(`库消比${v}% → ${cls}`, makeEl('alert_stu').innerHTML.includes('alert-box '+cls));
});

// ===================== 2. 回退方式与警告如实显示 =====================
reset(); window._syncedData = {mysteelMealStu: stuData({method:'weekly', methodLabel:'周度库存÷当月预计消费(可信度较低)', value:16.05, stockWan:null})}; refreshMysteelMealStu();
check('★第三级回退(周度库存推算)：详情里有可信度较低的警告', makeEl('ai_stu').innerHTML.includes('可信度低于文中数字'));
reset(); window._syncedData = {mysteelMealStu: stuData({recordSource:'summary', usedFallbackMonth:true, month:'2026-08', monthLabel:'2026年8月', value:15,
  bodyNotes:['2026-08-31: 正文请求失败(HTTP 403: Forbidden)']})}; refreshMysteelMealStu();
check('★摘要回退+月份回退：如实标注"取自搜索摘要""当月记录还没发布""正文没能取到"', makeEl('ai_stu').innerHTML.includes('取自搜索摘要') && makeEl('ai_stu').innerHTML.includes('当月记录还没发布') && makeEl('ai_stu').innerHTML.includes('403'));

// ===================== 3. 失败/过期/荒谬 =====================
reset(); window._syncedData = {mysteelMealStu: {available:false, reason:'最新一篇平衡表是60天前，可能停更'}}; refreshMysteelMealStu();
check('★抓取失败：显示原因，不填入', makeEl('m_stu').value === '' && makeEl('ai_stu').innerHTML.includes('可能停更') && makeEl('badge_stu').textContent.includes('抓取失败'));
reset(); window._syncedData = {mysteelMealStu: stuData({date:dayStr(60)})}; refreshMysteelMealStu();
check('★文章60天前(>45天)：显示但标过期、不计分', makeEl('badge_stu').textContent.includes('不计分') && makeEl('alert_stu').innerHTML.includes('不参与综合评分'));
reset(); window._syncedData = {mysteelMealStu: stuData({value:159})}; refreshMysteelMealStu();
check('★库消比159%(荒谬)：不填入，提示超出合理范围', makeEl('m_stu').value === '' && makeEl('ai_stu').innerHTML.includes('超出合理范围'));

// ===================== 4. 评分：组内权重 库消比50/开机率30/库存20 =====================
function baseNeutral(){
  reset();
  const v = {crush:50, stock:70, stu:12, basis:0, arrival:900, import:900, hogratio:6, sows:3750, poultry:1, rmspread:550, reserve:0};
  Object.keys(v).forEach(k=>makeEl('m_'+k).value = String(v[k]));
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0;
  window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
}
const tightCell = ()=> (html().match(/sd-cell (sd-\w+)">国内豆粕供应松紧/)||[])[1];
baseNeutral(); makeEl('m_stu').value='9'; updateOverallAlert();
check('★库消比偏多(50)+开机率中性(30)+库存中性(20)：0.5≥0.5 → 合并偏多(库消比单独就能定组方向)', tightCell()==='sd-pos');
baseNeutral(); makeEl('m_stu').value='9'; makeEl('m_crush').value='70'; updateOverallAlert();
check('★库消比偏多(50)+开机率偏空(30)：(50-30)/100=0.2 → 中性(开机率能抵消一部分)', tightCell()==='sd-neutral');
baseNeutral(); makeEl('m_stu').value='9'; makeEl('m_crush').value='70'; makeEl('m_stock').value='120'; updateOverallAlert();
check('★库消比偏多(50)+开机率偏空(30)+库存偏空(20)：(50-30-20)/100=0 → 中性', tightCell()==='sd-neutral');
baseNeutral(); makeEl('m_stu').value='16'; updateOverallAlert();
check('★库消比偏空(50)单独 → 合并偏空', tightCell()==='sd-neg');
baseNeutral(); makeEl('m_stu').value='12'; makeEl('m_stock').value='120'; updateOverallAlert();
check('★库存偏空(20)单独：0.2<0.5 → 中性(库存权重只有20，不会重复放大库消比已经表达的信息)', tightCell()==='sd-neutral');

// 库消比不可用 → 回到60/40
baseNeutral(); makeEl('m_stu').value=''; makeEl('m_stock').value='40'; makeEl('m_crush').value='70'; updateOverallAlert();
check('★库消比没有数据：回到60/40——库存偏多(60)+开机率偏空(40)=0.2 → 中性', tightCell()==='sd-neutral');
baseNeutral(); makeEl('m_stu').value=''; makeEl('m_stock').value='40'; updateOverallAlert();
check('★库消比没有数据：库存偏多(60)单独=0.6 → 偏多(第1步的规则保持不变)', tightCell()==='sd-pos');
// 库消比过期 → 不投票 → 回到60/40
baseNeutral(); makeEl('m_stu').value='16'; window._indState.stu = {stale:true, mode:'auto'}; makeEl('m_stock').value='40'; updateOverallAlert();
check('★库消比数据过期：不参与组合，回到库存60/开机率40(库存偏多→偏多)', tightCell()==='sd-pos');
check('详细理由写明各成员权重', (baseNeutral(), makeEl('m_stu').value='9', updateOverallAlert(), html().includes('库消比偏多(权重50)') && html().includes('开机率中性(权重30)') && html().includes('库存中性(权重20)')));
check('★详细理由写明票权×2', html().includes('票权×2'));
check('供需表格里该格标注×2', /sd-cell sd-\w+">国内豆粕供应松紧 ×2/.test(html()));

// ===================== 5. 评分：双倍票权 =====================
baseNeutral(); makeEl('m_stu').value='16'; updateOverallAlert();   // 国内组偏空(票权2)，其余全中性：-2÷13=-15% → 不下结论
check('★国内供应松紧单独偏空：-2÷13=-15%，不够22% → 信号混合(不会单凭这一组下方向结论)', html().includes('信号混合 -2（净倾向-15%）') && window._fundamentalDirection==='中性');
baseNeutral(); makeEl('m_stu').value='16'; window._psdSignal=-1; updateOverallAlert();
check('★再加一个同向指标(美豆库消比偏空)：-3÷13=-23% → 综合偏空(它算2票，但需要有另一个证据)', html().includes('综合偏空 -3（净倾向-23%）') && window._fundamentalDirection==='偏空');
baseNeutral(); window._psdSignal=-1; window._fxSignal=-1; updateOverallAlert();
check('对照：不是国内组的两个指标偏空只算2票：-2÷13=-15% → 信号混合', html().includes('信号混合 -2（净倾向-15%）'));
baseNeutral(); makeEl('m_stu').value=''; makeEl('m_stock').value=''; makeEl('m_crush').value=''; updateOverallAlert();
check('★国内组没有任何数据时不投票，也不占票权(其余11个投票全中性→有效11/12)', html().includes('有效11/12') && tightCell()==='sd-empty');

// ===================== 6. ESR中国/未知/其他展示 =====================
elements['esrBadge']=makeEl('esrBadge'); elements['esrContent']=makeEl('esrContent');
const esr = {available:true, commodity:'Soybeans(大豆)', weekEnding:'2026-09-24', marketYearUsed:2026, dataAgeDays:5, isStale:false,
  netSalesMT:1200000, prevNetSalesMT:800000, avg4wNetSalesMT:700000, vs4wAvgPct:71.4, wowChangePct:50, shipmentsMT:900000,
  chinaNetSalesMT:450000, unknownNetSalesMT:-100000, otherNetSalesMT:850000, chinaShipmentsMT:0,
  china4wSumMT:900000, unknown4wSumMT:300000, total4wSumMT:3000000, chinaShare4wPct:30, chinaMatched:true, countryNamesSeen:['CHINA','UNKNOWN','JAPAN'],
  source:'USDA-FAS ESR API'};
renderEsr(esr, new Date().toISOString());
const e = makeEl('esrContent').innerHTML;
check('★ESR详情：本周分目的地(中国/未知/其他)', e.includes('本周分目的地') && e.includes('中国 450,000 吨') && e.includes('未知目的地 -100,000 吨') && e.includes('其他 850,000 吨'));
check('★ESR详情：近4周合计+中国占比', e.includes('近4周合计') && e.includes('中国 900,000 吨') && e.includes('占总量30%') && e.includes('未知目的地 300,000 吨'));
check('★ESR详情：说明未知不能直接当中国、以及为什么中国采购量不参与打分', e.includes('目的地变更') && e.includes('不能直接当成中国') && e.includes('只展示、不参与打分'));
check('中国匹配正常时不出现警告', !e.includes('没有在数据里匹配到'));
check('★出口销售信号仍然只看总净销售(+71.4%→偏多)，跟中国拆分无关', window._esrSignal === 1);
renderEsr(Object.assign({}, esr, {chinaMatched:false, countryNamesSeen:['PEOPLES REP OF CN','JAPAN']}), new Date().toISOString());
check('★中国名称没匹配上时明确警告并列出国家名', makeEl('esrContent').innerHTML.includes('没有在数据里匹配到') && makeEl('esrContent').innerHTML.includes('PEOPLES REP OF CN'));
const oldShape = Object.assign({}, esr); ['unknownNetSalesMT','otherNetSalesMT','china4wSumMT','unknown4wSumMT','total4wSumMT','chinaShare4wPct','chinaMatched','countryNamesSeen'].forEach(k=>delete oldShape[k]);
let okShape = true; try { renderEsr(oldShape, new Date().toISOString()); } catch(err){ okShape = false; }
check('没有拆分字段的数据(刚部署、latest.json还是上一版)不报错、不显示undefined', okShape && !makeEl('esrContent').innerHTML.includes('undefined') && !makeEl('esrContent').innerHTML.includes('NaN'));

H.clearMockedMonth();
H.printSummary();
