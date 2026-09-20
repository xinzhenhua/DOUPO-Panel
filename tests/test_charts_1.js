const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


// ===================== 测试1：条形图 =====================
const barItems = [
  {label:'IL', value:32.5, code:'IL'},
  {label:'IA', value:28.0, code:'IA'},
  {label:'WI', value:3.0, code:'WI'},
];
const barSvg = renderBarChartSVG(barItems, {unit:'%', colorFn:v=>v>20?'#e84141':'#00b37a'});
check('条形图应该生成合法的<svg>标签', barSvg.startsWith('<svg') && barSvg.includes('</svg>'));
check('条形图应该包含3个<rect>(对应3个州)', (barSvg.match(/<rect/g)||[]).length === 3);
check('条形图应该按数值从大到小排序(IL在最前面)', barSvg.indexOf('>IL<') < barSvg.indexOf('>IA<') && barSvg.indexOf('>IA<') < barSvg.indexOf('>WI<'));
check('条形图里伊利诺伊(权重10800)的bar高度应该比威斯康星(权重2150)粗', (()=>{
  const heights = [...barSvg.matchAll(/height="([\d.]+)"/g)].map(m=>parseFloat(m[1]));
  return heights[0] > heights[2]; // IL排第一(index 0)，WI排最后
})());
check('数值大的(IL=32.5)条应该比数值小的(WI=3.0)条更长', (()=>{
  const widths = [...barSvg.matchAll(/width="([\d.]+)"/g)].map(m=>parseFloat(m[1]));
  return widths[0] > widths[2];
})());

// ===================== 测试2：仪表盘 =====================
const gaugeSvgBull = renderGaugeSVG(10, -14, 14);  // 明显偏多
const gaugeSvgBear = renderGaugeSVG(-10, -14, 14); // 明显偏空
const gaugeSvgNeutral = renderGaugeSVG(0, -14, 14); // 中性
check('仪表盘应该生成合法的<svg>标签', gaugeSvgBull.startsWith('<svg') && gaugeSvgBull.includes('</svg>'));
check('仪表盘应该显示分数文字(+10分)', gaugeSvgBull.includes('+10分'));
check('仪表盘应该包含指针(<line>元素)', gaugeSvgBull.includes('<line'));
// 偏多(score=10>0)指针应该指向右侧(needleX应该明显大于150这个圆心x坐标)
check('偏多分数(+10)的指针应指向右侧(数值大于中心点150)', (()=>{
  const m = gaugeSvgBull.match(/x2="([\d.]+)"/);
  return m && parseFloat(m[1]) > 150;
})());
// 偏空(score=-10<0)指针应该指向左侧
check('偏空分数(-10)的指针应指向左侧(数值小于中心点150)', (()=>{
  const m = gaugeSvgBear.match(/x2="([\d.]+)"/);
  return m && parseFloat(m[1]) < 150;
})());
check('中性分数(0)的指针应该接近正中间(150附近)', (()=>{
  const m = gaugeSvgNeutral.match(/x2="([\d.]+)"/);
  return m && Math.abs(parseFloat(m[1]) - 150) < 15;
})());
// 超出范围的分数应该被clamp，不应该崩溃或产生NaN
const gaugeSvgOverflow = renderGaugeSVG(999, -14, 14);
check('超出范围的分数应该被clamp而不是崩溃或产生NaN', !gaugeSvgOverflow.includes('NaN'));

// ===================== 测试3：供需二栏表格(取代已移除的状态点图) =====================
const supplyItems = [{label:'开机率', signal:1}, {label:'库存', signal:1}, {label:'天气', signal:0}];
const demandItems = [{label:'基差', signal:-1}, {label:'猪粮比', signal:1}];
const sdTable = renderSupplyDemandTable(supplyItems, demandItems);
check('供需表格应该生成合法的<table>标签', sdTable.includes('<table') && sdTable.includes('</table>'));
check('供需表格应该有"供应"和"需求"两个表头', sdTable.includes('>供应<') && sdTable.includes('>需求<'));
check('供需表格应该显示全部指标标签', ['开机率','库存','天气','基差','猪粮比'].every(l=>sdTable.includes(l)));
check('偏多(signal=1)的格子应该带sd-pos样式类(红色)', sdTable.includes('sd-pos'));
check('偏空(signal=-1)的格子应该带sd-neg样式类(绿色)', sdTable.includes('sd-neg'));
check('行数应该是表头1行+数据3行(以较长的供应列为准)=4行', (sdTable.match(/<tr>/g)||[]).length === 4);


H.printSummary();
