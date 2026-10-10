// ============================================================================
// v101.19b：彩带(MA20/MA60按"价格位置"着色) + 铁底/铁顶价格线(近260日20%/80%分位价)。期望值手算。
// ============================================================================
const logs = []; const priceLines = [];
global.LightweightCharts = {
  createChart(container){
    return {
      addSeries(t, opts){
        const rec = {opts, data:null}; logs.push(rec);
        return { setData(d){ rec.data = d; }, createPriceLine(o){ priceLines.push(o); } };
      },
      timeScale(){ return { fitContent(){}, subscribeVisibleLogicalRangeChange(){}, setVisibleLogicalRange(){} }; },
      applyOptions(){}, remove(){},
    };
  },
  CandlestickSeries: {}, LineSeries: {}, HistogramSeries: {},
};
global.ResizeObserver = class { observe(){} };
const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
const mk = (n, f)=>Array.from({length:n}, (_, i)=>f(i));
const dt = i=>`2025-${String(1 + Math.floor(i/28)).padStart(2,'0')}-${String(i%28+1).padStart(2,'0')}`;   // 仅用作唯一日期串(升序)

// ---- 1. 分位价位 ----
// closes 1..250：20%分位价=第ceil(0.2×250)=50名=50；80%=第200名=200
let lv = percentileLevels(mk(250, i=>i+1));
check('★铁底=近250日20%分位价50，铁顶=80%分位价200', lv.p20 === 50 && lv.p80 === 200);
lv = percentileLevels(mk(203, i=>i+1));
check('★非整除的情形：203个数里 20%分位价=第ceil(40.6)=41名=41，80%=第ceil(162.4)=163名=163', lv.p20 === 41 && lv.p80 === 163);
check('不足200根不给价位', percentileLevels(mk(150, i=>i+1)) === null);

// ---- 2. 逐根着色 ----
// bars: 260根，收盘 1..260。第i根(0起)收盘=i+1。窗口=前面最多260根含自己。
// 第199根(收盘200)：窗口只有200根(1..200) → 200≤200占100% → high；第250根(收盘251)：窗口=最近260根里1..251 → 100%
// 为测中间带/低位带：构造先高后低——前200根收盘 201..400，后60根收盘 100,101,...159
const bars2 = mk(260, i=>({date:dt(i), close: i<200 ? 201+i : 100+(i-200)}));
let bands = ribbonBands(bars2, null);
check('窗口不足200根的前199根=unknown(灰)', bands.slice(0,199).every(b=>b==='unknown'));
check('第200根(收盘400，窗口1..200全是它最高)=high', bands[199]==='high');
// 最后一根收盘159：窗口260根里≤159的：前200根里没有(都≥201)，后60根100..159共60个 → 60/260=23.1% → mid
check('最后一根收盘159：60/260=23.1% → mid(>20%不算低位)', bands[259]==='mid');
// 15.8%也算低位(≤20%)：最后一根收盘139 → ≤139的有100..139共40个(其中含自己重复一个)+... 手算：尾部60根100..158里换成139，≤139 = 100..139(40个，含原位置的139)+最后一根自己=41 → 41/260=15.8%
const bars3b = bars2.slice(0,259).concat([{date:dt(259), close:139}]);
check('最后一根收盘139：41/260=15.8% → low(阈值20%不能偷偷改成10%)', ribbonBands(bars3b, null)[259]==='low');
// 再降一点：最后一根收盘改99 → ≤99的只有它自己=1/260 → low
const bars3 = bars2.slice(0,259).concat([{date:dt(259), close:99}]);
check('最后一根收盘99：1/260=0.4% → low', ribbonBands(bars3, null)[259]==='low');

// ---- 3. 用后端补齐序列时，bars只有100根也能着色 ----
window._dailySymbol = 'M2701';
const own = mk(100, i=>({date:dt(160+i), close:100+i}));                 // 本合约100根：100..199
const extC = mk(260, i=>i<160 ? 50+i : 100+(i-160));                      // 补齐260根：前160根=50..209(换算)，后100根同本合约
const b4 = ribbonBands(own, {symbol:'M2701', closes:extC});
check('★用补齐序列：本合约只有100根，最后一根也不是unknown', b4[99] !== 'unknown');
check('补齐序列symbol对不上就不用 → 全unknown', ribbonBands(own, {symbol:'M2705', closes:extC}).every(b=>b==='unknown'));

// ---- 4. 画图：ribbon模式 ----
const c = makeEl('klineChartContainer'); c.clientWidth = 700; c.clientHeight = 320;
const bars5 = mk(260, i=>({date:dt(i), open:3000+i, high:3010+i, low:2990+i, close:3000+i}));   // 一路上涨 → 最后一根=最高 → high
logs.length = 0; priceLines.length = 0;
renderCandlestickChart('klineChartContainer', bars5, 'ribbon');
const titles = logs.map(l=>l.opts && l.opts.title).filter(Boolean);
check('★ribbon模式画 彩带MA20 和 彩带MA60，不画MA5等普通均线', titles.includes('彩带MA20') && titles.includes('彩带MA60') && !titles.includes('MA5'));
const r20 = logs.find(l=>l.opts && l.opts.title==='彩带MA20');
const lastPt = r20.data[r20.data.length-1];
check('★最后一点按高位着色(橙色)，且每个点都带颜色', lastPt.color === '#ff9f40' && r20.data.every(p=>p.color));
// MA20 第20根起才有值；前60根窗口<200 → 灰
check('窗口不足200根的点是灰色', r20.data[0].color === '#6b6b6b');
check('★画了铁底/铁顶两条价格线：20%分位价=3000+51=3051，80%=3000+207=3207(1..260里第52、208名→价=3000+i,i=51、207)', priceLines.length === 2 && priceLines.some(p=>p.price === 3051 && /铁底/.test(p.title)) && priceLines.some(p=>p.price === 3207 && /铁顶/.test(p.title)));
logs.length = 0; priceLines.length = 0;
renderCandlestickChart('klineChartContainer', bars5, 'ma');
check('均线模式不画铁底铁顶线', priceLines.length === 0);
H.printSummary();
