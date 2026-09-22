global.LightweightCharts = { createChart(){ return { addSeries(){return{setData(){}};}, timeScale(){return{fitContent(){},subscribeVisibleLogicalRangeChange(){},setVisibleLogicalRange(){}};}, applyOptions(){}, remove(){} }; }, CandlestickSeries:{}, LineSeries:{}, HistogramSeries:{} };
global.ResizeObserver = class { observe(){} };

const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：renderPositionRankTableHtml基本渲染(4类别tables结构) =====================
const mockPositionData = {
  available: true, symbol: 'M2701', date: '2026-09-19',
  tables: {
    netLong: [
      {rank:1, name:'国泰君安', value:45000, change:1200, isForeign:false},
    ],
    netShort: [
      {rank:1, name:'高盛期货', value:42000, change:-800, isForeign:true},
      {rank:2, name:'中信期货', value:36000, change:600, isForeign:false},
    ],
    longUp: [
      {rank:1, name:'中粮期货', value:20000, change:3000, isForeign:false},
    ],
    longDown: [
      {rank:1, name:'永安期货', value:15000, change:-2500, isForeign:false},
    ],
  },
  source: '测试',
};
const html = renderPositionRankTableHtml(mockPositionData);
check('★HTML应该包含4个类别的标题(净多头/净空头/多头增仓/多头减仓)',
  html.includes('净多头龙虎榜') && html.includes('净空头龙虎榜') && html.includes('多头增仓龙虎榜') && html.includes('多头减仓龙虎榜'));
check('★HTML应该包含会员名称(国泰君安/高盛期货/中粮期货/永安期货)',
  html.includes('国泰君安') && html.includes('高盛期货') && html.includes('中粮期货') && html.includes('永安期货'));
check('★HTML应该包含具体持仓数值(45000会用千分位格式化成45,000)', html.includes('45,000'));
check('正增减应该带+号且是pos样式', html.includes('class="pos">+1,200'));
check('负增减应该是neg样式(不应该额外加负号，数字本身带负号)', html.includes('class="neg">-800'));
check('★HTML应该包含"会员"和"非最终客户"的澄清说明，不能让人误以为是机构自己的仓位', html.includes('非最终客户'));

// ===================== 测试2：外资标注高亮 =====================
check('★高盛期货(isForeign:true)应该带🌐标记', html.includes('🌐 高盛期货'));
check('★中信期货(isForeign:false)不应该带🌐标记', !html.includes('🌐 中信期货'));
check('★应该有外资侦测数量的提示文字', html.includes('本次共侦测到') && html.includes('条外资独资期货公司'));

// 一个都没侦测到外资时，应该显示"均未进入前20名"的说明，而不是数字0的提示
const noForeignData = {
  available: true, symbol: 'M2701', date: '2026-09-19',
  tables: { netLong: [{rank:1, name:'国泰君安', value:1000, change:10, isForeign:false}] },
  source: '测试',
};
const noForeignHtml = renderPositionRankTableHtml(noForeignData);
check('★一个外资都没侦测到时，应该说明"均未进入前20名"，而不是显示生硬的0条', noForeignHtml.includes('均未进入前20名'));

// 空/缺失的类别不应该报错
const emptyData = {available:true, symbol:'M2701', date:'2026-09-19', tables:{netLong:[]}, source:'测试'};
const emptyHtml = renderPositionRankTableHtml(emptyData);
check('空tables数组不应该报错，应该显示"无数据"', emptyHtml.includes('无数据'));

// ===================== 测试3：renderKline整合——不可用时优雅降级 =====================
makeEl('klineBadge'); makeEl('klineContent');
['klineChartContainer','klineVolumeContainer'].forEach(id=>{ const el=makeEl(id); el.clientWidth=700; el.clientHeight=200; });
makeEl('klineCardTitle');

const bars = Array.from({length:60}, (_,i)=>({
  date:`2026-0${(i%9)+1}-0${(i%9)+1}`, open:2900+i, high:2920+i, low:2880+i, close:2910+i, volume:1000, hold:50000,
}));
const dailyData = {available:true, symbol:'M2701', totalBarsReturned:60, bars, source:'测试'};

// 持仓排名不可用的情况
renderKline(dailyData, {available:false, reason:'测试'}, new Date().toISOString(), {available:false, reason:'接口暂时拿不到数据'});
check('★持仓排名不可用时，应该在页面上诚实显示失败原因，而不是显示空表格或崩溃',
  makeEl('klineContent').innerHTML.includes('接口暂时拿不到数据'));

// 持仓排名可用的情况
renderKline(dailyData, {available:false, reason:'测试'}, new Date().toISOString(), mockPositionData);
check('★持仓排名可用时，应该显示实际日期', makeEl('klineContent').innerHTML.includes('截至2026-09-19'));
check('持仓排名可用时，应该包含"持仓排名"这个板块标题', makeEl('klineContent').innerHTML.includes('持仓排名'));
check('持仓排名数据应该正确渲染进最终HTML(能看到会员名称+外资标注)',
  makeEl('klineContent').innerHTML.includes('国泰君安') && makeEl('klineContent').innerHTML.includes('🌐 高盛期货'));

// 完全不传positionRankData(undefined)，不应该报错
renderKline(dailyData, {available:false, reason:'测试'}, new Date().toISOString());
check('完全不传positionRankData参数(undefined)时不应该报错，应该显示"暂无数据"',
  makeEl('klineContent').innerHTML.includes('暂无数据') || makeEl('klineContent').innerHTML.includes('未知原因'));

H.printSummary();
