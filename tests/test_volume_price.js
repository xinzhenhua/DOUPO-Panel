// ============================================================================
// 量价关系(价格×持仓量，归市场结构)：真实数据逐日对拍、三道可用性门槛、象限、进评分/分组/维度、健康度、合约切换
// 真实数据：用户仓库里 M2609 的全部242根日K线(2025-09-15~2026-09-14)，期望值由独立的Python参考实现算出
// ============================================================================
const fs = require('fs');
const path = require('path');
const H = require('./test_helpers');
const { makeEl, elements, check } = H;
eval(H.loadDashboardJs());
const E = window._eventCal;
const AUTO = window._autoIndicators;
makeEl('vpBadge'); makeEl('vpContent');
const fx = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'm2609_daily_with_expected.json'), 'utf8'));
const BARS = fx.bars, EXP = fx.expected;
const startMs = vpContractStartMs('M2609');
const html = ()=>makeEl('vpContent').innerHTML;
const near = (a,b,t)=> (a===null && b===null) || (a!==null && b!==null && Math.abs(a-b) <= (t||1e-3));

// ===================== 1. ★真实数据逐日对拍(JS vs 独立Python参考实现) =====================
let mismatch = [], compared = 0, gateOk = 0, sigCount = {'-1':0,'0':0,'1':0};
for(let i=0; i<BARS.length; i++){
  const r = vpAt(BARS, i, startMs), e = EXP[i];
  compared++;
  const gateSame = (r.gate === null) === (e.gate === null || e.gate === undefined);
  let ok = gateSame;
  if(ok && e.gate == null){
    gateOk++; sigCount[String(e.signal)]++;
    ok = r.signal === e.signal && near(r.pc, e.pc) && near(r.oc, e.oc) && near(r.dzp, e.dzp) && near(r.dzo, e.dzo) && r.pdir === e.pdir && r.odir === e.odir && near(r.volRatio, e.volRatio);
  } else if(ok && e.gate && e.gate.startsWith('数据不足')) ok = r.gate.startsWith('数据不足');
  if(!ok) mismatch.push(BARS[i].date);
}
check('★真实数据242根K线逐日对拍：JS实现与独立的Python参考实现完全一致(门槛/信号/5日涨跌/5日持仓变动/死区/象限/量比)', mismatch.length === 0 && compared === 242);
check('对拍覆盖了真实的信号分布：门槛通过113根，其中偏多30、偏空14、中性69(不是全为0的空对拍)', gateOk === 113 && sigCount['1'] === 30 && sigCount['-1'] === 14 && sigCount['0'] === 69);

// ===================== 2. ★真实数据里的教训：移仓/交割期不能按"价涨减仓"读 =====================
const idx = d => BARS.findIndex(b=>b.date===d);
let r = vpAt(BARS, idx('2026-08-18'), startMs);
check('★8月18日：价格5日+3.5%、持仓量5日-28%——若按"价涨减仓=上涨乏力"读是错的(那是移仓/交割)——门槛挡住了，写明原因，不投票', r.pc > 3 && r.oc < -25 && r.gate && r.gate.includes('移仓/交割期') && r.signal === 0);
r = vpAt(BARS, idx('2026-08-28'), startMs);
check('8月28日：持仓量已降到几万手，门槛①(≥50万手)拦住', r.gate.includes('低于500,000手'));
r = vpAt(BARS, idx('2026-07-31'), startMs);
check('★7月31日(持仓量156万手=峰值的58%，距合约月31天)：门槛按顺序检查，②先触发(<60%峰值)，仍是移仓/交割期', r.gate && r.gate.includes('58%') && r.gate.includes('移仓/交割期'));
r = vpAt(BARS, idx('2026-07-17'), startMs);
check('★7月17日(距合约月恰好46天)：最后一个通过门槛的日子——通过', r.gate === null);
r = vpAt(BARS, idx('2026-07-20'), startMs);
check('7月20日(距合约月43天)：门槛③关闭', r.gate && r.gate.includes('43天'));
r = vpAt(BARS, idx('2026-04-10'), startMs);
check('★4月10日：持仓量5日+27.6%(增仓)但价格5日只+0.44%(在死区内)：增仓横盘，不投票(中性)', r.gate === null && r.odir === 1 && r.pdir === 0 && r.signal === 0);
r = vpAt(BARS, idx('2026-03-10'), startMs);
check('3月10日：价格+2.23%、持仓量+14.9%(增仓上涨)：偏多(+1)', r.gate === null && r.pdir === 1 && r.odir === 1 && r.signal === 1);
r = vpAt(BARS, idx('2025-11-20'), startMs);
check('★合约早期(2025年11月，持仓量约12万手)：门槛①拦住(还不是主力合约)', r.gate.includes('低于500,000手'));
r = vpAt(BARS, 10, startMs);
check('前25根K线：数据不足', r.gate.startsWith('数据不足'));

// ===================== 3. 象限：只有"增仓"象限投票 =====================
// 构造合成K线：60根平稳基础+最后5日的价格/持仓变化(持仓量维持在100万手以上通过门槛)
function synth(pc, oc, opts){
  opts = opts || {};
  const bars = []; let price = 3000, oi = 1500000;
  for(let i=0; i<70; i++){
    price *= 1 + (i%2===0 ? 0.002 : -0.002);           // 平稳小幅波动，5日变动的稳健σ很小
    oi *= 1 + (i%3===0 ? 0.004 : -0.002);
    const d = new Date(Date.UTC(2026,3,1) + i*86400000);
    bars.push({date: d.toISOString().slice(0,10), close: price, hold: oi, volume: 500000, open:price, high:price, low:price});
  }
  const n = bars.length;
  const p0 = bars[n-6].close, o0 = bars[n-6].hold;
  for(let k=1; k<=5; k++){ bars[n-6+k].close = p0*(1+pc/100*k/5); bars[n-6+k].hold = o0*(1+oc/100*k/5); if(opts.vol) bars[n-6+k].volume = opts.vol; }
  return bars;
}
const start2701 = vpContractStartMs('M2709');       // 合约月2027年9月，距离很远，门槛③不干扰
const Q = (pc, oc, o)=>{ const b = synth(pc, oc, o); return vpAt(b, b.length-1, start2701); };
check('★增仓上涨(价+3%、持仓+8%)：偏多(+1)', Q(3, 8).signal === 1);
check('★增仓下跌(价-3%、持仓+8%)：偏空(-1)', Q(-3, 8).signal === -1);
check('★减仓上涨(价+3%、持仓-8%)：中性(0)——空头回补/多头兑现，缺乏新资金确认，不投票', Q(3, -8).signal === 0 && Q(3, -8).odir === -1 && Q(3, -8).pdir === 1);
check('★减仓下跌(价-3%、持仓-8%)：中性(0)——多头离场，缺乏新空头', Q(-3, -8).signal === 0 && Q(-3, -8).odir === -1 && Q(-3, -8).pdir === -1);
check('增仓但价格横盘(价+0.05%、持仓+8%)：中性(0)——多空在博弈', Q(0.05, 8).signal === 0 && Q(0.05, 8).pdir === 0 && Q(0.05, 8).odir === 1);
check('价格涨但持仓平稳(价+3%、持仓不变)：中性(0)——没有新资金的确认', Q(3, 0).signal === 0 && Q(3, 0).odir === 0 && Q(3, 0).pdir === 1);
check('★门槛之内才投票：同样是增仓上涨，持仓量低于50万手(把持仓压到30万手)就不投票', (()=>{ const b = synth(3, 8); b.forEach(x=>x.hold = x.hold * 0.2); const r = vpAt(b, b.length-1, start2701); return r.gate && r.gate.includes('低于500,000手') && r.signal === 0; })());
// 成交量标签
check('成交量：放量(5日均量/20日均量≥1.2)、缩量(≤0.8)、平量', volumePriceAnalysis(synth(3,8,{vol:900000}), 'M2709', E.bjToMs(2026,6,10,10,0)).volLabel === '放量' && volumePriceAnalysis(synth(3,8,{vol:200000}), 'M2709', E.bjToMs(2026,6,10,10,0)).volLabel === '缩量' && volumePriceAnalysis(synth(3,8), 'M2709', E.bjToMs(2026,6,10,10,0)).volLabel === '平量');
check('★成交量只作确认展示，不改变信号：放量/缩量下增仓上涨都是+1', Q(3,8,{vol:900000}).signal === 1 && Q(3,8,{vol:200000}).signal === 1);
// 死区跟着合约自己的波动走
const wild = synth(3, 8); wild.forEach((x,i)=>{ if(i<60) x.close = x.close * (1 + (i%2===0?0.04:-0.04)); });   // 把历史波动放大：同样+3%在这个合约里已经不算大动
check('★死区随合约自身波动缩放：把历史波动放大后，同样的价格+3%落入死区，不再算上涨', vpAt(wild, wild.length-1, start2701).pdir === 0);

// ===================== 4. 合约代码解析 =====================
check('合约代码→合约月第一天：M2609=2026-09-01、M2701=2027-01-01', vpContractStartMs('M2609') === Date.UTC(2026,8,1) && vpContractStartMs('M2701') === Date.UTC(2027,0,1));
check('解析不了的代码返回null(此时不启用门槛③，其余门槛照常)', vpContractStartMs('abc') === null && vpContractStartMs(undefined) === null);

// ===================== 5. volumePriceAnalysis：状态 =====================
window._nowMs = E.bjToMs(2026,7,17,10,0);
const bars17 = BARS.filter(b=>b.date <= '2026-07-16');            // 7月16日的最新K线，"现在"是7月17日早上
let a = volumePriceAnalysis(bars17, 'M2609', window._nowMs);
check('★7月16日的数据、现在是7月17日：新鲜，门槛通过 → status=ok，带象限和量比', a.status === 'ok' && a.fresh.state === 'fresh' && typeof a.quadrant === 'string' && a.volRatio > 0);
a = volumePriceAnalysis(BARS, 'M2609', E.bjToMs(2026,9,30,10,0));
check('★真实的整条K线、现在是9月30日：最新K线是9月14日、合约已到期 → status=stale(K线过期)，而不是拿0持仓去算', a.status === 'stale' && a.fresh.state === 'stale');
a = volumePriceAnalysis(BARS.filter(b=>b.date <= '2026-08-18'), 'M2609', E.bjToMs(2026,8,19,10,0));
check('★8月18日数据、新鲜但门槛没过 → status=gated，原因是移仓/交割期', a.status === 'gated' && a.gate.includes('移仓/交割期'));
check('K线不足25根 → status=insufficient，写明根数', volumePriceAnalysis(BARS.slice(0,10), 'M2609').status === 'insufficient' && volumePriceAnalysis(BARS.slice(0,10), 'M2609').reason.includes('10根'));
check('没有持仓量字段 → insufficient，不报错', volumePriceAnalysis(BARS.map(b=>({close:b.close, date:b.date, volume:b.volume})), 'M2609').status === 'insufficient');
check('null/undefined不报错', volumePriceAnalysis(null, 'M2609').status === 'insufficient' && volumePriceAnalysis(undefined, 'M2609').status === 'insufficient');
window._nowMs = null;

// ===================== 6. 卡片渲染 =====================
window._nowMs = E.bjToMs(2026,7,17,10,0);
const daily = (until, symbol)=>({available:true, symbol: symbol || 'M2609', bars: BARS.filter(b=>b.date <= until)});
window._nowMs = E.bjToMs(2026,3,11,10,0);
renderVolumePrice(daily('2026-03-10'), new Date().toISOString());
check('★3月10日(增仓上涨)：偏多(bull)，写明象限和含义，参与综合评分', window._vpSignal === 1 && html().includes('alert-box bull') && html().includes('增仓上涨') && html().includes('新多头资金入场') && html().includes('参与综合评分') && window._vpStatus === 'ok');
check('★展示近5日价格/持仓变动/量比，以及"成交量只作确认展示"', /价格\+2\.2\d?%/.test(html()) && html().includes('持仓量+14.') && html().includes('成交量') && html().includes('成交量只作确认展示'));
check('★卡片写明为什么先过门槛(真实数据：M2609持仓量5月见顶271万手、8月底2.8万手)', html().includes('271万手') && html().includes('移仓、交割'));
check('★写明与技术面同源、不是独立证据，阈值暂定', html().includes('跟技术面同源') && html().includes('暂定值'));
check('详情里显示死区和门槛状态', html().includes('死区') && html().includes('三道都通过'));
window._nowMs = E.bjToMs(2026,8,19,10,0);
renderVolumePrice(daily('2026-08-18'), new Date().toISOString());
check('★8月18日(价涨、持仓量暴跌，门槛没过)：中性色，写明"量价关系暂不可用"和原因(移仓/交割期)，不投票', window._vpSignal === null && window._vpStatus === 'gated' && html().includes('量价关系暂不可用') && html().includes('移仓/交割期') && html().includes('暂不计入综合评分') && !html().includes('alert-box bear') && !html().includes('alert-box bull'));
check('详情里门槛"未通过"', html().includes('未通过'));
check('★门槛没过时，象限标"不可靠"，并明说不能按常规含义读；不再写"上涨缺乏新资金确认"这种会误导的解读', html().includes('不可靠') && html().includes('不能</b>按') && !html().includes('缺乏新资金确认，不判方向') && !html().includes('更多是空头回补'));
window._nowMs = E.bjToMs(2026,9,30,10,0);
renderVolumePrice(daily('2026-09-14'), new Date().toISOString());
check('★合约已到期(最新K线9月14日、现在9月30日)：K线过期，不计分，提示合约可能已到期', window._vpStatus === 'stale' && html().includes('K线数据已过期') && window._vpReason.includes('合约可能已到期') && window._vpSignal === null);
renderVolumePrice({available:false, reason:'M2701日线抓取失败'}, new Date().toISOString());
check('不可用：显示原因，状态=unavailable', window._vpStatus === 'unavailable' && html().includes('M2701日线抓取失败'));
renderVolumePrice(null, new Date().toISOString());
check('传null(旧版latest.json没有这个合约的K线)：不报错，有兜底文字', html().includes('还没有同步'));
renderVolumePrice({available:true, symbol:'M2609', bars: BARS.slice(0,10)}, new Date().toISOString());
check('K线不足：写明"数据不足，暂不计分"', window._vpStatus === 'insufficient' && html().includes('数据不足'));
window._nowMs = null;

// ===================== 7. 合约切换 =====================
['tab-sep','tab-may','tab-jan','contractContext','group-us-weather','group-sa','crushBadge','crushContent','spreadBadge','spreadContent'].forEach(id=>makeEl(id));
window._nowMs = E.bjToMs(2026,3,11,10,0);
window._syncedData = {generatedAt:new Date().toISOString(), crushMargins:{sep:{available:false,reason:'x'},may:{available:false,reason:'x'},jan:{available:false,reason:'x'}},
  termSpreads:{sep:{available:false,reason:'x'},may:{available:false,reason:'x'},jan:{available:false,reason:'x'}},
  dceM09Daily: daily('2026-03-10', 'M2609'), dceM05Daily: {available:false, reason:'M2605日线抓取失败(测试)'}, dceM01Daily: undefined};
selectContract('sep');
check('★点击切换到9月合约：量价卡片显示M2609的结果(增仓上涨)', html().includes('增仓上涨') && window._vpSignal === 1);
selectContract('may');
check('★点击切换到5月合约：显示5月合约的日线不可用原因，不残留9月的信号', html().includes('M2605日线抓取失败') && window._vpSignal === null && window._vpStatus === 'unavailable');
selectContract('jan');
check('★点击切换到1月合约(latest.json里没有这个合约)：兜底文字，信号null', html().includes('还没有同步') && window._vpSignal === null);
selectContract('sep');
check('切回9月合约：信号回来', window._vpSignal === 1);
delete window._syncedData;
let ok = true; try{ refreshVolumePriceForContract('sep'); }catch(e){ ok = false; }
check('window._syncedData为空时不报错', ok);
window._nowMs = null;

// ===================== 8. 进综合评分：市场结构维度 =====================
function resetScore(){
  AUTO.forEach(c=>{ makeEl(c.inputId).value=''; makeEl('ind_'+c.key); makeEl('alert_'+c.key); });
  window._indState = {}; makeEl('alertContent');
  window._weatherRisk='medium'; window._droughtSignal=0; window._noaaOutlookSignal=0; window._soyCondSignal=0; window._esrSignal=0; window._fxSignal=0; window._psdSignal=0;
  window._selectedContract='sep'; H.setMockedMonth(5);
  const fill = {crush:'50', stock:'70', basis:'0', arrival:'900', import:'900', hogratio:'6', poultry:'1', rmspread:'550'};
  Object.keys(fill).forEach(k=>makeEl('m_'+k).value = fill[k]);
  window._crushSignal = undefined; window._spreadSignal = undefined; window._vpSignal = undefined;
}
const cell = ()=> (makeEl('structureContent').innerHTML.match(/sd-cell (sd-\w+)">量价关系[^<]*/)||[]);      // v97：量价在"市场结构"卡里，不在顶部
resetScore(); updateOverallAlert();
check('★还没渲染过量价卡片(undefined)：这一票不在投票清单里', !/sd-cell[^>]*>量价关系/.test(makeEl('structureContent').innerHTML));
resetScore(); window._vpSignal = null; window._vpQuality = null; window._vpStatus = 'gated'; updateOverallAlert();
check('★门槛没过(信号null)：这一票在清单里但没数据——作为"缺席的投票"如实列出', /sd-cell sd-empty">量价关系/.test(makeEl('structureContent').innerHTML) && window._quality.missing.some(x=>x.includes('量价关系')));
resetScore(); window._vpSignal = 1; window._vpQuality = {m:1, why:''}; updateOverallAlert();
check('★增仓上涨：偏多格(▲)，放在"市场结构"列', cell()[1] === 'sd-pos' && /<th>市场结构<\/th>/.test(makeEl('structureContent').innerHTML));
check('★属于"市场反馈"分组(跟基差、月差同组)', voteGroup('量价关系(价格×持仓量)') === 'feedback');
check('详细理由里写明偏多原因', makeEl('alertContent').innerHTML.includes('新多头资金入场'));
resetScore(); window._vpSignal = -1; window._vpQuality = {m:1, why:''}; updateOverallAlert();
check('增仓下跌：偏空格(▼)', cell()[1] === 'sd-neg');
resetScore(); window._vpSignal = 0; window._vpQuality = {m:1, why:''}; updateOverallAlert();
check('中性：中性格(—)', cell()[1] === 'sd-neutral');
resetScore(); window._vpSignal = 1; window._vpQuality = {m:0.5, why:'K线数据晚了一期'}; updateOverallAlert();
check('★K线晚了一期：票权×0.5，质量分里点名', window._quality.lowItems.some(x=>x.label.includes('量价关系') && x.q === 0.5));
// 市场结构维度：基差(0) + 量价(+1)
resetScore(); window._vpSignal = 1; window._vpQuality = {m:1, why:''}; updateOverallAlert();
check('★基差中性(0) + 量价偏多(+1)：市场结构维度2项，净倾向+50%，不再是"样本少"', window._structureSystem.n === 2 && Math.abs(window._structureSystem.ratio - 0.5) < 1e-9 && window._structureSystem.thin === false);
// 三个市场结构信号一起
resetScore(); window._vpSignal = 1; window._vpQuality = {m:1, why:''}; window._spreadSignal = 1; window._spreadQuality = {m:1, why:''}; makeEl('m_basis').value = '100'; updateOverallAlert();
check('★基差偏多+月差偏多+量价偏多：市场结构维度3项全偏多，+100%', window._structureSystem.n === 3 && window._structureSystem.ratio === 1);
H.clearMockedMonth(); window._vpSignal = undefined; window._spreadSignal = undefined; window._crushSignal = undefined;
H.printSummary();
