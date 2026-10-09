const H = require('./test_helpers');
const { makeEl, check } = H;
const fs = require('fs'), path = require('path');
eval(H.loadDashboardJs());
// v101.14 季节性：月度卡(A) + 年内路径图(B)。只展示，不计分。期望值全部手算。
const NOW = Date.UTC(2026, 9, 9, 2, 0, 0);          // 北京时间 2026-10-09 10:00
const grade = (label, why)=>({label, why: why||''});
const mk = (month, f, s, ex, gf, gs)=>({month, futures:f, spot:s, excursion:ex, gradeFutures:gf, gradeSpot:gs});
const months = [];
for(let m=1;m<=12;m++) months.push(mk(m, {n:10, mean:0.5, median:0.3, upPct:60, std:4, t:0.4}, {n:10, mean:1.0, median:0.8, upPct:60, std:5, t:0.6}, {n:10, upMean:3, upMedian:3, upP90:6.5, dnMean:-2.5, dnMedian:-2, dnP10:-6.5}, grade('不稳','前后两半方向相反'), grade('一般','两半同向')));
months[9] = mk(10, {n:9, mean:-0.28, median:0.29, upPct:55.56, std:3.8, t:-0.2}, {n:9, mean:-0.17, median:0.17, upPct:55.56, std:5, t:-0.1}, {n:9, upMean:2.2, upMedian:3, upP90:6.5, dnMean:-2.2, dnMedian:-2, dnP10:-6.5}, grade('不稳','前5年均值+1.0%，后5年−1.2%，方向相反'), grade('较稳','两半同向，70%的年份上涨'));
const table = {futures:{}, spot:{}};
for(let y=2017;y<=2026;y++){ table.futures[y]={10: y===2026?null:(y%2?1.5:-2.5)}; table.spot[y]={10: y===2026?null:(y%2?2.0:-1.0)}; }
const wk = (a)=>Array.from({length:52}, (_, i)=>a + i*0.1);
const S = { months, monthlyTable: table,
  path:{weeks:52, bands:{p10:wk(-3), p25:wk(-1), median:wk(1), p75:wk(3), p90:wk(5)}, years:{}, current:{year:2026, path:wk(0).map((v,i)=>i<=38?v:null), lastWeek:38, value:3.9, asOf:'2026-09-30', position:{percentile:80, flag:'带内', n:9}}},
  meta:{lastDate:'2026-09-30', firstDate:'2016-10-10', source:'baseline_csv', caveats:['样本小','换月']} };
const bars = [{date:'2026-09-29', close:3290}, {date:'2026-09-30', close:3300}, {date:'2026-10-08', close:3366}, {date:'2026-10-09 00:00:00', close:3340}];

// ---- 区间换算 ----
let r = seasonalRange(bars, NOW, S.months[9].excursion);
check('★上月末收盘取上个月最后一根K线(9月30日=3300)', r && r.prevClose === 3300 && r.prevDate === '2026-09-30');
check('★典型高点：3300×(1+3%)=3399，p90：3300×1.065=3514.5→3515；典型低点 3300×0.98=3234，p10：3300×0.935=3085.5→3086', r.hiMid === 3399 && r.hi90 === 3515 && r.loMid === 3234 && r.lo10 === 3086);
check('现价=最后一根K线(3340，日期带时间也认)，相对上月末 +1.2%', r.last === 3340 && Math.abs(r.lastPct - 1.2121) < 0.001);
check('本月至今最高/最低(收盘)：3366 → +2.0%，3340 → +1.2%', Math.abs(r.monthHiPct - 2.0) < 0.01 && Math.abs(r.monthLoPct - 1.2121) < 0.001);
check('没有上个月的K线 → 不画区间(返回null)，不拿别的数凑', seasonalRange([{date:'2026-10-08', close:3366}], NOW, S.months[9].excursion) === null);
check('没有K线/没有幅度数据 → null', seasonalRange(null, NOW, S.months[9].excursion) === null && seasonalRange(bars, NOW, null) === null);

// ---- A 卡 ----
let html = renderSeasonalCardHtml(S, 10, r);
check('卡片写明月份和"只展示，不计分"', html.includes('10月') && html.includes('只展示，不计分'));
check('★期货(换月修正)标签=不稳，并写出原因', html.includes('不稳') && html.includes('方向相反'));
check('★现货标签=较稳；均值−0.2%、上涨56%、样本9年', html.includes('较稳') && html.includes('−0.2%') && html.includes('56%') && html.includes('9年'));
check('历史各年小方块：2017~2025共9个(2026当月未完成=不画)，涨红跌绿', (html.match(/class="ssq (pos|neg)"/g)||[]).length >= 9 && html.includes('2017'));
check('区间行写出上月末收盘与换算价位', html.includes('3,300') && html.includes('3,399') && html.includes('3,234'));
check('★防误解：明说季节性弱、今年偏离更可能是资金/事件，不是买卖信号', html.includes('不是买卖信号'));
const noRange = renderSeasonalCardHtml(S, 10, null);
check('没有区间数据时明确说缺上月末收盘，不显示假价位', noRange.includes('缺上月末收盘') && !noRange.includes('3,399'));
const empty = renderSeasonalCardHtml(S, 13, null);
check('月份越界不抛错，给出"没有该月数据"', empty.includes('没有'));

// ---- B 图 ----
const svg = renderSeasonalPathSvg(S);
check('路径图是 SVG，含历史带、中位线、今年曲线', svg.includes('<svg') && svg.includes('class="sp-band90"') && svg.includes('class="sp-band50"') && svg.includes('class="sp-med"') && svg.includes('class="sp-cur"'));
const curPts = (svg.match(/class="sp-cur"[^>]*points="([^"]+)"/)||[])[1].trim().split(/\s+/);
check('★今年曲线只画到最后一周(39个点，第39周之后是null不画)', curPts.length === 39, String(curPts.length));
check('坐标轴标出月份(1月…12月)和0%线', svg.includes('>1月<') && svg.includes('>12月<') && svg.includes('class="sp-zero"'));
check('★文字说明：今年累计+3.9%、历史同周80分位、带内、截至2026-09-30', html.includes('3.9%') || renderSeasonalPathNote(S).includes('3.9%'));
const note = renderSeasonalPathNote(S);
check('路径说明写出分位与位置', note.includes('80') && note.includes('带内') && note.includes('2026-09-30'));
S.path.current.position = {percentile:100, flag:'高于历史带', n:9};
check('★高于历史带时提示"更可能是资金/事件在主导"，不说成买入/卖出', renderSeasonalPathNote(S).includes('资金') && !renderSeasonalPathNote(S).includes('买入'));
S.path.current.position = {percentile:80, flag:'带内', n:9};
check('没有今年数据时图仍能画(只画历史带)', !renderSeasonalPathSvg(Object.assign({}, S, {path:Object.assign({}, S.path, {current:null})})).includes('class="sp-cur"'));

// ---- 整体渲染接线 ----
['seasonalBadge','seasonalContent','seasonalPath'].forEach(id=>makeEl(id));
window._nowMs = NOW; window._selectedContract = 'jan'; window._seasonal = S;
window._syncedData = {generatedAt:new Date(NOW).toISOString(), dceM01Daily:{available:true, symbol:'M2701', bars}};
renderSeasonal();
check('renderSeasonal：按当前选中合约(1月)的K线换算区间并写入卡片', makeEl('seasonalContent').innerHTML.includes('M2701') && makeEl('seasonalContent').innerHTML.includes('3,399'));
check('badge 显示数据截止日', makeEl('seasonalBadge').textContent.includes('2026-09-30'));
window._seasonal = null; renderSeasonal();
check('没有 seasonal.json 时给明确提示，不报错', makeEl('seasonalContent').innerHTML.includes('尚未生成'));

// ---- 不参与计分(源码层面) ----
const src = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
check('★季节性不进投票：addVote 里没有任何"季节"票', !/addVote\(\s*['"`][^'"`]*季节/.test(src));
H.printSummary();
