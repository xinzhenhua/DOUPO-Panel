global.LightweightCharts = { createChart(){ return { addSeries(){return{setData(){}};}, timeScale(){return{fitContent(){},subscribeVisibleLogicalRangeChange(){},setVisibleLogicalRange(){}};}, applyOptions(){}, remove(){} }; }, CandlestickSeries:{}, LineSeries:{}, HistogramSeries:{} };
global.ResizeObserver = class { observe(){} };

const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：renderPositionRankTableHtml基本渲染 =====================
const mockPositionData = {
  available: true, symbol: 'M2609', date: '20260919',
  rows: [
    {rank:1, volPartyName:'国泰君安', vol:12000, volChg:500,
     longPartyName:'中信期货', longOpenInterest:45000, longOpenInterestChg:1200,
     shortPartyName:'永安期货', shortOpenInterest:42000, shortOpenInterestChg:-800},
    {rank:2, volPartyName:'中信期货', vol:9500, volChg:-200,
     longPartyName:'国泰君安', longOpenInterest:38000, longOpenInterestChg:-500,
     shortPartyName:'中信期货', shortOpenInterest:36000, shortOpenInterestChg:600},
  ],
  source: '测试',
};
const html = renderPositionRankTableHtml(mockPositionData);
check('★HTML应该包含多头持仓排名标题', html.includes('多头持仓排名'));
check('★HTML应该包含空头持仓排名标题', html.includes('空头持仓排名'));
check('★HTML应该包含会员名称(中信期货/国泰君安/永安期货)', html.includes('中信期货') && html.includes('国泰君安') && html.includes('永安期货'));
check('★HTML应该包含具体持仓数值(45000会用千分位格式化成45,000)', html.includes('45,000'));
check('正增减应该带+号且是pos样式', html.includes('class="pos">+1,200'));
check('负增减应该是neg样式(不应该额外加负号，数字本身带负号)', html.includes('class="neg">-800'));
check('★HTML应该包含"会员"和"非最终客户"的澄清说明，不能让人误以为是机构自己的仓位', html.includes('非最终客户'));

// 空数组不应该报错
const emptyData = {available:true, symbol:'M2609', date:'20260919', rows:[], source:'测试'};
const emptyHtml = renderPositionRankTableHtml(emptyData);
check('空rows数组不应该报错，应该显示"无数据"', emptyHtml.includes('无数据'));

// ===================== 测试2：renderKline整合——不可用时优雅降级 =====================
makeEl('klineBadge'); makeEl('klineContent');
['klineChartContainer','klineVolumeContainer'].forEach(id=>{ const el=makeEl(id); el.clientWidth=700; el.clientHeight=200; });
makeEl('klineCardTitle');

const bars = Array.from({length:60}, (_,i)=>({
  date:`2026-0${(i%9)+1}-0${(i%9)+1}`, open:2900+i, high:2920+i, low:2880+i, close:2910+i, volume:1000, hold:50000,
}));
const dailyData = {available:true, symbol:'M2609', totalBarsReturned:60, bars, source:'测试'};

// 持仓排名不可用的情况
renderKline(dailyData, {available:false, reason:'测试'}, new Date().toISOString(), {available:false, reason:'大商所官网风控，暂时拿不到数据'});
check('★持仓排名不可用时，应该在页面上诚实显示失败原因，而不是显示空表格或崩溃',
  makeEl('klineContent').innerHTML.includes('大商所官网风控'));

// 持仓排名可用的情况
renderKline(dailyData, {available:false, reason:'测试'}, new Date().toISOString(), mockPositionData);
check('★持仓排名可用时，应该显示实际日期', makeEl('klineContent').innerHTML.includes('截至20260919'));
check('持仓排名可用时，应该包含"持仓排名"这个板块标题', makeEl('klineContent').innerHTML.includes('持仓排名'));
check('持仓排名数据应该正确渲染进最终HTML(能看到会员名称)', makeEl('klineContent').innerHTML.includes('中信期货'));

// 完全不传positionRankData(undefined)，不应该报错
renderKline(dailyData, {available:false, reason:'测试'}, new Date().toISOString());
check('完全不传positionRankData参数(undefined)时不应该报错，应该显示"暂无数据"',
  makeEl('klineContent').innerHTML.includes('暂无数据') || makeEl('klineContent').innerHTML.includes('未知原因'));

H.printSummary();
