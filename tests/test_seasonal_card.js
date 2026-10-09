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
months[9] = mk(10, {n:9, mean:-0.28, median:0.29, upPct:55.56, std:3.8, t:-0.2}, {n:10, mean:-2.1, median:-1.5, upPct:30, std:5, t:-1.8}, {n:9, upMean:2.2, upMedian:3, upP90:6.5, dnMean:-2.2, dnMedian:-2, dnP10:-6.5}, grade('不稳','前5年均值+1.0%，后5年−1.2%，方向相反'), grade('较稳','两半同向，70%的年份下跌'));
const table = {futures:{}, spot:{}};
for(let y=2017;y<=2026;y++){ table.futures[y]={10: y===2026?null:(y%2?1.5:-2.5)}; table.spot[y]={10: y===2026?null:(y%2?2.0:-1.0)}; }
const wk = (a)=>Array.from({length:52}, (_, i)=>a + i*0.1);
const ln = (a, b)=>Array.from({length:52}, (_, i)=>a + i*b);
const S = { months, monthlyTable: table,
  path:{weeks:52, bands:{p10:wk(-3), p25:wk(-1), median:wk(1), p75:wk(3), p90:wk(5)}, years:{'2022':ln(5,0.5), '2024':ln(1,0.1), '2025':ln(-2,0.2)}, current:{year:2026, path:wk(0).map((v,i)=>i<=38?v:null), lastWeek:38, value:3.9, asOf:'2026-09-30', position:{percentile:80, flag:'带内', n:9}}},
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

// ---- A 卡：一句话 + 范围条 + 柱图 ----
const fv = seasonalVerdict(S.months[9].futures, S.months[9].gradeFutures), sv = seasonalVerdict(S.months[9].spot, S.months[9].gradeSpot);
check('★期货：9年里涨5年、跌4年(55.56%×9=5.0)，不稳 → 没有明显方向', fv.ups === 5 && fv.downs === 4 && fv.stable === false && fv.dir === '没有明显方向');
check('★现货：10年里涨3年、跌7年(30%)，较稳 → 比较有规律：偏跌', sv.ups === 3 && sv.downs === 7 && sv.stable === true && sv.dir === '偏跌');
check('★33.33%×3年=0.9999 要四舍五入成1年(不能向下取整成0)', seasonalVerdict({n:3, upPct:33.33, mean:1}, null).ups === 1 && seasonalVerdict({n:3, upPct:33.33, mean:1}, null).downs === 2);
check('没有数据 → null，不崩', seasonalVerdict(null, null) === null && seasonalVerdict({n:3}, null) === null);
check('★一句话结论：期货不稳、现货较稳 → 说现货有规律、期货不一定跟', seasonalHeadline(fv, sv).includes('现货') && seasonalHeadline(fv, sv).includes('偏跌') && seasonalHeadline(fv, sv).includes('期货不一定跟'));
check('★两个都不稳 → 明说"没有可靠的规律，季节性帮不上忙"', seasonalHeadline(fv, Object.assign({}, sv, {stable:false})).includes('没有可靠的规律'));
let html = renderSeasonalCardHtml(S, 10, r, 'futures');
check('卡片写明月份和"只展示，不计分"', html.includes('10月的历史规律') && html.includes('只展示，不计分'));
check('★用大白话写涨跌年数："涨5年、跌4年"和"涨3年、跌7年"，平均−0.3%', html.includes('涨5年、跌4年') && html.includes('涨3年、跌7年') && html.includes('−0.3%'));
check('★不再出现看不懂的术语：p90/p10/分位/换月修正标签/样本N年', !/p90|p10|分位|样本\d+年|不稳<\/span>/.test(html));
check('范围条写出上月末收盘与典型最高/最低价位(3,399/3,234)和最强/最弱(3,515/3,086)', html.includes('3,300') && html.includes('3,399') && html.includes('3,234') && html.includes('3,515') && html.includes('3,086'));
check('★现价3,340在典型范围(3,234~3,399)里的位置：(3340−3234)/165=0.64 → "中间"', html.includes('在典型范围的中间'));
const bar = (last)=>renderSeasonalRangeBar(Object.assign({}, r, {last}), S.months[9]);
check('现价跌破典型最低点 / 涨过典型最高点 / 偏低 / 偏高 各有说法', bar(3200).includes('跌破往年本月的典型最低点') && bar(3450).includes('涨过往年本月的典型最高点') && bar(3250).includes('偏低') && bar(3390).includes('偏高'));
check('★位置分档边界：3300在典型范围的0.4处→"中间"(不是偏低)', bar(3300).includes('在典型范围的中间') && !bar(3300).includes('偏低'));
check('范围条里画出现价标记', renderSeasonalRangeBar(r, S.months[9]).includes('现价 3,340'));
check('★防误解：明说不是买卖信号、不预测今年', html.includes('不是买卖信号') && html.includes('不预测今年'));
const noRange = renderSeasonalCardHtml(S, 10, null, 'futures');
check('没有区间数据时明确说缺上月末收盘，不显示假价位', noRange.includes('缺上月末收盘') && !noRange.includes('3,399'));
check('月份越界不抛错，给出"没有该月数据"', renderSeasonalCardHtml(S, 13, null).includes('没有'));
// 柱图
const mb = renderSeasonalMonthBars(S, 10, 'futures');
check('★柱图：12根柱，期货11个月均值+0.5(红)、10月−0.28(绿)', (mb.match(/fill:var\(--r\)/g)||[]).length === 11 && (mb.match(/fill:var\(--g\)/g)||[]).length === 1);
check('柱图：本月(10月)有金框，12个月标签齐全，柱上写平均值(+0.5、−0.3)', (mb.match(/stroke:var\(--gold\)/g)||[]).length === 1 && mb.includes('>1月<') && mb.includes('>12月<') && mb.includes('+0.5') && mb.includes('−0.3'));
check('★期货口径无"较稳"月份 → 没有★；说明里写明期货已扣换月假涨跌', !/<text[^>]*>★<\/text>/.test(mb) && mb.includes('换月'));
const mbs = renderSeasonalMonthBars(S, 10, 'spot');
check('★现货口径：只有10月较稳 → 恰好1个★；上涨占比显示60%/30%', (mbs.match(/<text[^>]*>★<\/text>/g)||[]).length === 1 && mbs.includes('60%') && mbs.includes('30%'));
check('柱图上有 期货/现货 切换按钮，点了调用 setSeasonalKind', mb.includes("setSeasonalKind('spot')") && mb.includes("setSeasonalKind('futures')"));

// ---- B 图：今年和往年比 ----
const svg = renderSeasonalPathSvg(S);
check('折线图是 SVG：往年灰线3条、往年中间水平(蓝虚线)、今年金线', svg.includes('<svg') && (svg.match(/class="sp-past"/g)||[]).length === 3 && svg.includes('class="sp-med"') && svg.includes('class="sp-cur"'));
check('★图例用大白话：灰线=往年每一年，蓝虚线=往年的中间水平，金线=今年', svg.includes('灰线=往年每一年') && svg.includes('蓝虚线=往年的中间水平') && svg.includes('金线=今年'));
const curPts = (svg.match(/class="sp-cur"[^>]*points="([^"]+)"/)||[])[1].trim().split(/\s+/);
check('★今年曲线只画到最后一周(39个点，第39周之后是null不画)', curPts.length === 39, String(curPts.length));
check('往年灰线右端只标年末最高和最低的两年(22、24)，不标25(避免挤成一团)；坐标轴有月份和0%线', svg.includes('>22<') && svg.includes('>24<') && !svg.includes('>25<') && svg.includes('>1月<') && svg.includes('>12月<') && svg.includes('class="sp-zero"'));
const note = renderSeasonalPathNote(S);
check('★第38周往年值：2022=24.0、2025=5.6、2024=4.8；今年+3.9% → 最高+24.0%(2022年)、最低+4.8%(2024年)、4个年份里排第4、比大多数年份都弱', note.includes('+24.0%（2022年）') && note.includes('+4.8%（2024年）') && note.includes('4 个年份里排第 <b>4</b>') && note.includes('比大多数年份都弱') && note.includes('2026-09-30'));
const S2 = JSON.parse(JSON.stringify(S)); S2.path.current.value = 30;
check('今年30%比往年都高 → 排第1、涨得比大多数年份都多', renderSeasonalPathNote(S2).includes('排第 <b>1</b>') && renderSeasonalPathNote(S2).includes('涨得比大多数年份都多'));
S2.path.current.value = 10;
check('中间 → "和往年差不多"', renderSeasonalPathNote(S2).includes('和往年差不多'));
S2.path.current.position = {percentile:100, flag:'高于历史带', n:9};
check('★明显超出往年范围时提示"主要不是季节规律在推动(资金或突发事件)"，不说成买入/卖出', renderSeasonalPathNote(S2).includes('资金或突发事件') && !renderSeasonalPathNote(S2).includes('买入'));
const S3 = JSON.parse(JSON.stringify(S)); S3.path.years = {};
check('往年样本为空 → 说样本不足，不编排名', renderSeasonalPathNote(S3).includes('样本不足') && !renderSeasonalPathNote(S3).includes('排第'));
check('没有今年数据时图仍能画(只画往年)', !renderSeasonalPathSvg(Object.assign({}, S, {path:Object.assign({}, S.path, {current:null})})).includes('class="sp-cur"'));

// ---- 整体渲染接线 ----
['seasonalBadge','seasonalContent','seasonalPath'].forEach(id=>makeEl(id));
window._nowMs = NOW; window._selectedContract = 'jan'; window._seasonal = S;
window._syncedData = {generatedAt:new Date(NOW).toISOString(), dceM01Daily:{available:true, symbol:'M2701', bars}};
renderSeasonal();
check('renderSeasonal：按当前选中合约(1月)的K线换算区间并写入卡片', makeEl('seasonalContent').innerHTML.includes('M2701') && makeEl('seasonalContent').innerHTML.includes('3,399'));
check('默认显示期货柱图(没有★)', !/<text[^>]*>★<\/text>/.test(makeEl('seasonalContent').innerHTML));
setSeasonalKind('spot');
check('★点"现货"：重新渲染成现货柱图(出现1个★)', (makeEl('seasonalContent').innerHTML.match(/<text[^>]*>★<\/text>/g)||[]).length === 1 && window._seasonalKind === 'spot');
setSeasonalKind('futures');
check('badge 显示数据截止日', makeEl('seasonalBadge').textContent.includes('2026-09-30'));
window._seasonal = null; renderSeasonal();
check('没有 seasonal.json 时给明确提示，不报错', makeEl('seasonalContent').innerHTML.includes('尚未生成'));

// ---- 不参与计分(源码层面) ----
const src = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
check('★季节性不进投票：addVote 里没有任何"季节"票', !/addVote\(\s*['"`][^'"`]*季节/.test(src));
H.printSummary();
