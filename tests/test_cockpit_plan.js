const fs=require('fs'), path=require('path'); const src=fs.readFileSync(path.join(__dirname,'..','cockpit','ui.js'),'utf8');
const a=src.indexOf('/* PLAN_BEGIN'), b=src.indexOf('/* PLAN_END */'); if(a<0||b<0){console.log('❌ 找不到 TPLAN 标记');process.exit(1)}
const code=src.slice(a,b)+'\nreturn {TPLAN,planEntry,planTier,planPct,planMA,planConfirm,planForeign,planSignals,planBasis,planSize,planManage,planWhy,planFee,planPnl,planOpen,planOpenFor,planHold,planEquity,planStats,planGate,planDataLine,planPartsText,planExpect,planWilson,planRng,TBT,planSrc,planAdvice,planPath,planReview,planSlip,planReasonOf,PLAN_REASONS,monthAmpCalc};';
const P=new Function(code)(); let pass=0,fail=0;
const eq=(n,x,y,tol)=>{ const ok=tol?Math.abs(x-y)<=tol:JSON.stringify(x)===JSON.stringify(y); ok?pass++:(fail++,console.log('❌',n,'期望',y,'实际',x)); if(ok) console.log('✅',n) };
// 阶梯(边界：<500万 才是60%)
eq('阶梯 10万→55%',P.planTier(100000),.55); eq('阶梯 499.99万→55%',P.planTier(4999999),.55); eq('阶梯 500万整→40%',P.planTier(5000000),.4);
eq('阶梯 1500万整→25%',P.planTier(15000000),.25); eq('阶梯 5000万整→15%',P.planTier(50000000),.15); eq('阶梯 1亿→15%',P.planTier(1e8),.15);
// 分位：[1..260] 最后=260 → 100；[260..1] 最后=1 → 1/260
const up=[...Array(260)].map((_,i)=>i+1), dn=up.slice().reverse();
eq('分位 递增末位=100',P.planPct(up),100,1e-9); eq('分位 递减末位=1/260',P.planPct(dn),100/260,1e-9); eq('分位 样本不足→null',P.planPct(up.slice(0,150)),null);
// 均线
eq('MA3',P.planMA([1,2,3,4,5,6],3),5); eq('MA不足→null',P.planMA([1,2],3),null);
// 反弹确认：前10日最低100；今天102.5>100*1.01 且 >5日前
const base=Array(20).fill(105); const c1=base.slice(); c1[c1.length-10]=100; c1[c1.length-5]=101; c1.push(102.5);
eq('反弹确认 满足',P.planConfirm(c1),true);
const c2=base.slice(); c2[c2.length-10]=100; c2.push(100.9); eq('反弹确认 未高出前低1%→否',P.planConfirm(c2),false);
const c3=base.slice(); c3[c3.length-10]=100; c3[c3.length-5]=120; c3.push(102.5); eq('反弹确认 不高于5日前→否',P.planConfirm(c3),false);
// 外资合计
const mem={'高盛期货':{foreign:true,history:{change5:{change:-11887}}},'摩根大通':{foreign:true,history:{change5:{change:8143}}},'瑞银期货':{foreign:true,history:{change5:null}},'中粮期货':{foreign:false,history:{change5:{change:7383}}}};
const f=P.planForeign(mem); eq('外资5日合计=-3744',f.sum,-3744); eq('外资缺失席位',f.missing,['瑞银期货']); eq('最弱席位=各席位变化的最小值',f.min,Math.min(...f.parts.map(q=>q.v))); eq('外资用到的席位',f.used,['高盛期货','摩根大通']);
// 信号：构造 260 根：前200根100，之后60根缓降到 80，最后一根反弹
let cs=Array(200).fill(100); for(let i=0;i<59;i++) cs.push(100-i*0.3); cs.push(cs[cs.length-1]+1.5);
let s=P.planSignals(cs,0); eq('信号 低位+反弹+无去杠杆→可做多',s.longOK,true); eq('信号 去杠杆则禁做多',P.planSignals(cs,-20000).longOK,false);
eq('信号 去杠杆阈值边界 -20000 含',P.planSignals(cs,-20000).delev,true); eq('信号 -19999 不算',P.planSignals(cs,-19999).delev,false);
// 空头：下行趋势 + 去杠杆
let dcs=Array(260).fill(0).map((_,i)=>200-i*0.5); const hiDip=[...Array(250)].map((_,i)=>i+1).concat([250,249,248,247,246,245,244,243,242,241]);   // 高位回落：分位≈96%，收盘在MA20下方
eq('空头(v101.89) 高位+收盘<MA20+去杠杆→可做空',P.planSignals(hiDip,-30000).shortOK,true); eq('空头 无去杠杆→不做空',P.planSignals(hiDip,0).shortOK,false);
eq('空头 一路下跌(分位低，不在高位)+去杠杆→不做空',P.planSignals(dcs,-30000).shortOK,false);
// 仓位计算(手算)：v102.14 起按「入场限价」算——信号收盘 3400 做多 → 限价 3390(回调0.3%)；权益50万 保证金13% 占用60% → floor(300000/(10*3390*0.13))=floor(68.07)=68 手
let z=P.planSize({equity:500000,margin:.13,price:3400,side:1,mode:'real'});
eq('入场限价(多)=3390',z.entryPx,3390); eq('planEntry多：限价/止损/启动价/初始移动止损',JSON.stringify(P.planEntry(3400,1)),JSON.stringify({side:1,close:3400,lim:3390,stop:3254,act:3661,trailAtAct:3515}));
eq('planEntry空：限价3410 止损3546 启动3137',JSON.stringify([P.planEntry(3400,-1).lim,P.planEntry(3400,-1).stop,P.planEntry(3400,-1).act]),JSON.stringify([3410,3546,3137]));
eq('手数(实际保证金13%)=62',z.lots,62); eq('名义金额',z.notional,2101800); eq('占用保证金',z.margin,2101800*.13,1e-6); eq('实际占用',z.usage,2101800*.13/500000,1e-9);
eq('止损价=入场价×0.96=3254.4',z.stopPx,3254.4,1e-9); eq('止损亏损',z.lossStop,2101800*.04,1e-6); eq('止损亏损占权益',z.lossPct,2101800*.04/500000,1e-12);
eq('风险度100%价(多)',z.liqPx,(620*3390-500000)/(620*0.87),1e-9); eq('启动价(最高浮盈8%)=入场价×1.08=3661.2',z.actPx,3661.2,1e-9);
// 回测口径：按10%保证金 → 88 手
let y=P.planSize({equity:500000,margin:.13,price:3400,side:1,mode:'bt'});
eq('手数(回测口径)=81',y.lots,81); eq('回测口径·风险100%价(多)',y.liqPx,(810*3390-500000)/(810*0.87),1e-9);
eq('回测口径·止损处风险度',y.riskAtStop,(2745900*0.13*0.96)/(500000-2745900*.04),1e-9);
let sh=P.planSize({equity:500000,margin:.10,price:3400,side:-1,mode:'real'}); eq('空头入场限价=3410(反弹0.3%)',sh.entryPx,3410); eq('空头手数=80',sh.lots,80); eq('空头止损价=3410×1.04=3546.4',sh.stopPx,3546.4,1e-9);
eq('空头风险100%价',sh.liqPx,(500000+800*3410)/(800*1.10),1e-9);
eq('资金不足一手→0手(5000*0.6/(10*3400*0.13)=0.68)',P.planSize({equity:5000,margin:.13,price:3400,side:1,mode:'real'}).lots,0);
eq('刚好够一手(权益8100:4455/4420=1.01→1手)',P.planSize({equity:8100,margin:.13,price:3400,side:1,mode:'real'}).lots,1);
eq('权益600万→占用40%',P.planSize({equity:6000000,margin:.10,price:3400,side:1,mode:'real'}).u,.4);
// 持仓管理
let m1=P.planManage({side:1,entry:3400,peak:3400,last:3263,ma20:3300,fsum:0}); eq('多单 -4.03% → 止损',m1.action,'止损');
let m2=P.planManage({side:1,entry:3400,peak:3800,last:3640,ma20:3300,fsum:0}); eq('多单 峰值3800回落4.2%且浮盈7.06% → 移动止盈',m2.action,'移动止盈');
let m3=P.planManage({side:1,entry:3400,peak:3800,last:3650,ma20:3300,fsum:0}); eq('多单 峰值3800回落3.95%(<4%) → 持有',m3.action,'持有');
let m3b=P.planManage({side:1,entry:3400,peak:3600,last:3450,ma20:3300,fsum:0}); eq('多单 最高浮盈仅5.9%(<8%未启动)，回落4.2% → 持有(只剩止损)',m3b.action,'持有');
eq('峰值版 最高浮盈 peakR',m2.peakR,(3800/3400-1)*100,1e-9);
eq('多单 峰值恰8%(3672)，回落到3525 → 移动止盈',P.planManage({side:1,entry:3400,peak:3672,last:3525,ma20:3300,fsum:0}).action,'移动止盈');
eq('多单 峰值恰8%(3672)，回落到3526 → 持有',P.planManage({side:1,entry:3400,peak:3672,last:3526,ma20:3300,fsum:0}).action,'持有');
eq('多单 峰值3671(7.97%<8)，回落4.5% → 持有',P.planManage({side:1,entry:3400,peak:3671,last:3500,ma20:3300,fsum:0}).action,'持有');
eq('空单 峰值(最低)3127(8.03%)，反弹到3253(≥3252.08) → 移动止盈',P.planManage({side:-1,entry:3400,peak:3127,last:3253,ma20:3400,fsum:-30000}).action,'移动止盈');
eq('空单 峰值(最低)3127，反弹到3252(<3252.08) → 持有',P.planManage({side:-1,entry:3400,peak:3127,last:3252,ma20:3400,fsum:-30000}).action,'持有');
let m4=P.planManage({side:1,entry:3400,peak:3450,last:3420,ma20:3300,fsum:-20000}); eq('多单 外资去杠杆 → 平多',m4.action,'外资去杠杆·平多');
let m5=P.planManage({side:-1,entry:3400,peak:3300,last:3350,ma20:3340,fsum:-30000}); eq('空单 价格上穿MA20 → 空单离场',m5.action,'空单离场');
let m6=P.planManage({side:-1,entry:3400,peak:3300,last:3350,ma20:3400,fsum:-30000}); eq('空单 仍在MA20下且外资去杠杆 → 持有',m6.action,'持有');
let m7=P.planManage({side:-1,entry:3400,peak:3300,last:3540,ma20:3600,fsum:-30000}); eq('空单 -4.1% → 止损',m7.action,'止损');

// —— 补边界（针对变异存活）——
{ const b=Array(20).fill(1100); b[b.length-10]=1000; b[b.length-5]=1002;       // 前10日最低1000，5日前1002
  eq('反弹确认 1005 < 1000*1.01 → 否',P.planConfirm(b.concat([1005])),false);
  eq('反弹确认 1010.5 > 1010 且 > 5日前 → 是',P.planConfirm(b.concat([1010.5])),true);
  const e=Array(20).fill(1100); e[e.length-10]=1000; e[e.length-5]=1020;
  eq('反弹确认 恰好等于5日前(1020)→否',P.planConfirm(e.concat([1020])),false); }
{ const w=[]; for(let i=0;i<130;i++) w.push(1000+i); for(let i=1;i<=129;i++) w.push(i); w.push(500);   // 130个更高、129个更低、末位500 → 分位恰好50
  const sg=P.planSignals(w,0); eq('分位恰好50 → 仍算低位(≤50)',sg.pct,50,1e-9); eq('分位恰好50 → lowOK',sg.lowOK,true); }
{ const u=[...Array(259)].map((_,i)=>i+1).concat([240]); const sg=P.planSignals(u,-30000);
  eq('上行趋势里回落到MA20下方：v101.89 不再要求MA20<MA60，高位+去杠杆 → 做空',sg.shortOK,true); }
{ const m=P.planManage({side:-1,entry:3400,peak:3300,last:3350,ma20:3400,fsum:0}); eq('空单 外资5日净变化=0 → 离场(≥0)',m.action,'空单离场'); }

// ===== v101.26 账户与持仓 =====
{ const T=(o)=>Object.assign({id:'1',side:1,lots:10,entryD:'2026-01-05',entryPx:3000},o);
  // 手续费：每手来回23元，10手 → 开仓115，平仓115
  eq('手续费 持仓中只记开仓一半',P.planFee(T(),23),115); eq('手续费 已平仓记全部',P.planFee(T({exitD:'2026-02-01',exitPx:3100}),23),230);
  eq('手续费 填实际开仓/平仓金额优先',P.planFee(T({exitD:'x',feeO:50,feeC:60}),23),110); eq('手续费 开仓填了0就是0',P.planFee(T({feeO:0}),23),0);
  eq('盈亏 多单涨100，10手×10吨=10000',P.planPnl(T(),3100),10000); eq('盈亏 空单涨100亏10000',P.planPnl(T({side:-1}),3100),-10000);
  eq('找持仓 取最后一笔未平仓',P.planOpen([T({id:'a',exitD:'x'}),T({id:'b'})]).id,'b'); eq('找持仓 全平→null',P.planOpen([T({exitD:'x'})]),null);
  // 持仓最高/最低（自动）：开仓日 01-05 收盘3000，之后 3100,3300,3200,3050
  const h={d:['2026-01-02','2026-01-05','2026-01-06','2026-01-07','2026-01-08','2026-01-09'],c:[9999,3000,3100,3300,3200,3050]};
  let r=P.planHold(h,T()); eq('持仓 多单最高=开仓日起最大收盘(不含开仓日前的9999)',r.peak,3300); eq('持仓 多单持仓期最低',r.worst,3000); eq('持仓 现价=最新收盘',r.last,3050); eq('持仓 交易日数=4',r.days,4); eq('持仓 未折算',r.scaled,false);
  r=P.planHold(h,T({side:-1})); eq('持仓 空单"最高价"位=持仓期最低收盘(不高于开仓价)',r.peak,3000); eq('持仓 空单对应的最不利价=最高收盘',r.worst,3300);
  r=P.planHold(h,T({entryPx:3100})); eq('持仓 开仓价高于之后所有收盘时，多单最高取开仓价',P.planHold({d:['2026-01-05','2026-01-06'],c:[3100,3000]},T({entryPx:3100})).peak,3100);
  // 开仓价和当天主连差>2% → 折算（非主力合约）
  r=P.planHold(h,T({entryPx:3150})); eq('持仓 开仓价高5%→折算系数1.05',r.k,1.05,1e-9); eq('持仓 折算后最高=3300×1.05',r.peak,3465,1e-6); eq('持仓 折算标记',r.scaled,true);
  r=P.planHold(h,T({entryPx:3050})); eq('持仓 差1.7%不折算',r.scaled,false);
  r=P.planHold(h,T({entryD:'2026-02-01'})); eq('持仓 开仓日晚于全部数据→covered=false，最高=开仓价',[r.covered,r.peak,r.last],[false,3000,3000]);
  r=P.planHold({d:[],c:[]},T()); eq('持仓 无价格数据不报错',r.covered,false);
  // 权益 = 初始 + 出入金 + 已平仓盈亏 + 浮动 − 手续费
  const A={init:500000,fee:23,flows:[{d:'2026-03-01',amt:200000}],trades:[T({id:'1',exitD:'2026-02-01',exitPx:3100}),T({id:'2',entryD:'2026-03-02',entryPx:3000})]};
  const e=P.planEquity(A,3050); eq('权益 已平仓 +10000',e.realized,10000); eq('权益 浮动 +5000',e.floating,5000); eq('权益 手续费 230+115=345',e.fees,345); eq('权益 出入金',e.flows,200000);
  eq('权益 合计',e.equity,500000+200000+10000+5000-345);
  eq('权益 无持仓价时浮动按开仓价=0',P.planEquity(A,null).floating,0);
  eq('权益 空账户=初始',P.planEquity({init:500000,fee:23,flows:[],trades:[]},null).equity,500000);
  const st=P.planStats(A); eq('统计 1笔平仓 胜1',[st.n,st.wins],[1,1]); eq('统计 净盈亏=10000-230',st.net,9770);
  const A2={init:1,fee:0,flows:[],trades:[T({exitD:'x',exitPx:2900})]}; eq('统计 亏损单不算胜',P.planStats(A2).wins,0);
  // 信号原因文案
  eq('原因 低位不满足',/不在低位/.test(P.planWhy({pct:80,lowOK:false,delev:false})),true); eq('原因 去杠杆但趋势不向下',/不做多，也不做空/.test(P.planWhy({pct:30,lowOK:true,delev:true,longOK:false,shortOK:false})),true);
  eq('原因 低位未确认',/没出现反弹确认/.test(P.planWhy({pct:30,lowOK:true,delev:false,longOK:false,shortOK:false})),true); eq('原因 分位不足',/历史价格不足/.test(P.planWhy({pct:null,lowOK:false,delev:false})),true);
  // 联动：自动算出的最高价喂给离场判定
  const hh=P.planHold({d:['2026-01-05','2026-01-06','2026-01-07'],c:[3000,3300,3150]},T()); const mm=P.planManage({side:1,entry:3000,peak:hh.peak,last:hh.last,ma20:null,fsum:0});
  eq('联动 最高浮盈10%后回落4.5% → 移动止盈',mm.action,'移动止盈'); }

// ===== v101.27 数据闸门 =====
{ let g=P.planGate(['高盛期货'],'2026-10-09','2026-10-12'); eq('闸门 数据齐、价格3天前 → 通过',[g.ok,g.reasons.length,g.warn.length],[true,0,0]);
  g=P.planGate([],'2026-10-09','2026-10-12'); eq('闸门 外资一个席位都没有 → 不通过',g.ok,false); eq('闸门 原因点名外资',/外资/.test(g.reasons[0]),true);
  g=P.planGate(['摩根大通'],'2026-10-01','2026-10-12'); eq('闸门 价格11天没更新 → 不通过',g.ok,false);
  g=P.planGate(['摩根大通'],'2026-10-05','2026-10-12'); eq('闸门 价格7天（国庆长假内）→ 仍通过',g.ok,true);
  g=P.planGate(['摩根大通'],'2026-10-07','2026-10-12'); eq('闸门 5天 → 通过但提示',[g.ok,g.warn.length],[true,1]);
  g=P.planGate(['摩根大通'],null,'2026-10-12'); eq('闸门 没有价格数据 → 不通过',g.ok,false);
  g=P.planGate([],'2026-09-01','2026-10-12'); eq('闸门 两个问题都点名',g.reasons.length,2);
  g=P.planGate(['摩根大通'],'2026-10-09','2026-10-12',{missing:['瑞银期货'],fD:'2026-10-09'}); eq('分级 缺一个席位 → 部分(仍可用)',[g.ok,g.level],[true,'part']);
  g=P.planGate(['摩根大通','高盛期货','瑞银期货'],'2026-10-09','2026-10-12',{missing:[],fD:'2026-10-09'}); eq('分级 齐全 → ok',[g.ok,g.level],[true,'ok']);
  g=P.planGate(['摩根大通'],'2026-10-09','2026-10-20',{fD:'2026-10-09'}); eq('分级 外资数据11天没更新 → 不可用',[g.ok,g.level],[false,'bad']);
  g=P.planGate(['摩根大通'],'2026-10-09','2026-10-12',{fD:'2026-10-05'}); eq('分级 外资数据7天 → 提示',[g.ok,g.level,g.warn.length],[true,'part',1]);
  g=P.planGate([],null,'2026-10-12',{}); eq('分级 全缺 → bad',g.level,'bad');
  let l=P.planDataLine(P.planGate(['摩根大通','高盛期货'],'2026-10-09','2026-10-12',{missing:['瑞银期货'],fD:'2026-10-09'}),['摩根大通','高盛期货'],'2026-10-09','2026-10-09'); eq('数据行 部分缺失文案',[l.cls,/瑞银期货缺数据按0算/.test(l.t)],['part',true]);
  g=P.planGate(['摩根大通','高盛期货'],'2026-10-09','2026-10-12',{missing:[],approx:['高盛期货'],fD:'2026-10-09'}); eq('分级 有估算席位 → 部分(仍可用)并点名',[g.ok,g.level,/高盛期货为估算值/.test(g.warn[0])],[true,'part',true]);
  eq('planForeign 带出口径',P.planForeign({a:{foreign:1,history:{change5:{change:5,to:'2026-10-09',basis:'long'}}}}).parts[0].basis,'long');
  eq('planForeign 带出估算席位',P.planForeign({a:{foreign:1,history:{change5:{change:5,to:'2026-10-09',approx:1}}},b:{foreign:1,history:{change5:{change:-2,to:'2026-10-08'}}}}).approx,['a']);
  g=P.planGate(['摩根大通'],'2026-10-09','2026-10-12',{adj:false,fD:'2026-10-09'}); eq('缺换月调整价 → 不可用并点名文件',[g.ok,/main_adj/.test(g.reasons[0])],[false,true]);
  g=P.planGate(['摩根大通'],'2026-10-09','2026-10-12',{adj:true,fD:'2026-10-09'}); eq('有换月调整价 → 通过',g.ok,true);
  eq('数据行带价格口径',/换月调整/.test(P.planDataLine(g,['摩根大通'],'2026-10-09','2026-10-09',true).t),true);
  { const parts=[{k:'高盛期货',v:-15392,basis:'long'},{k:'摩根大通',v:8143}], g2=P.planGate(['高盛期货','摩根大通'],'2026-10-09','2026-10-12',{missing:['瑞银期货'],fD:'2026-10-09'});
    const t=P.planDataLine(g2,['高盛期货','摩根大通'],'2026-10-09','2026-10-09',true,parts).t;
    eq('数据行写出每个席位的金额和合计',[/高盛 −15,392\(多单\)/.test(t),/摩根大通 \+8,143/.test(t),/最弱 高盛 −15,392/.test(t)],[true,true,true]);
    eq('数据行没传parts时退回席位名',/外资 高盛期货\+摩根大通/.test(P.planDataLine(g2,['高盛期货','摩根大通'],'2026-10-09','2026-10-09',true).t),true); }
  l=P.planDataLine(P.planGate([],'2026-10-09','2026-10-12',{}),[],'2026-10-09',null); eq('数据行 不足',[l.cls,/数据不足/.test(l.t)],['bad',true]); }

{ const hedge=P.planForeign({a:{foreign:1,history:{change5:{change:-25000,to:'2026-10-09'}}},b:{foreign:1,history:{change5:{change:10000,to:'2026-10-09'}}}});
  eq('对冲：合计-15000，但单个席位-25000',[hedge.sum,hedge.min,hedge.minK],[-15000,-25000,'a']);
  const cs=Array.from({length:300},(_,i)=>3000+i*0.1);
  eq('单席位≤-2万 → 去杠杆(哪怕合计没到)',[P.planSignals(cs,hedge.sum).delev,P.planSignals(cs,hedge.min).delev],[false,true]);
  eq('没有任何席位数据时 min=0 不触发去杠杆',[P.planForeign({}).min,P.planSignals(cs,P.planForeign({}).min).delev],[0,false]); }

{ const base={side:-1,entry:3400,peak:3300,last:3350,ma20:3400};
  eq('空单：最弱席位-2.5万但三家合计+0.5万 → 空单离场(外资回正，看合计)',P.planManage(Object.assign({fsum:-25000,fall:5000},base)).action,'空单离场');
  eq('空单：某席位回到≥0但合计仍<0 → 持有(看合计不看最弱)',P.planManage(Object.assign({fsum:0,fall:-5000},base)).action,'持有');
  eq('多单：最弱席位≤-2万 → 平多，不看合计',P.planManage({side:1,entry:3400,peak:3450,last:3420,ma20:3300,fsum:-25000,fall:5000}).action,'外资去杠杆·平多'); }
{ const T=o=>Object.assign({side:1,lots:1,entryD:'2026-10-08',entryPx:3400},o);
  const tr=[T({id:'a',contract:'M2701'})];
  eq('持仓按合约：看 M2701 → 有',P.planOpenFor(tr,'M2701','M2701').id,'a'); eq('持仓按合约：看 M2705 → 没有',P.planOpenFor(tr,'M2705','M2701'),null);
  eq('持仓按合约：代码大小写不敏感',P.planOpenFor(tr,'m2701','M2701').id,'a');
  eq('持仓按合约：老记录没写合约 → 算自动合约的（看自动合约有，看别的没有）',[P.planOpenFor([T({id:'b'})],'M2701','M2701').id,P.planOpenFor([T({id:'b'})],'M2705','M2701')],['b',null]);
  eq('持仓按合约：已平仓的不算',P.planOpenFor([T({id:'c',contract:'M2701',exitD:'2026-10-09'})],'M2701','M2701'),null);
  eq('持仓按合约：两笔未平仓（不应出现）取各自合约的那笔',[P.planOpenFor([T({id:'d',contract:'M2701'}),T({id:'e',contract:'M2705'})],'M2705','M2701').id],['e']); }

{ // 持仓预期（蒙特卡洛）
  const rg=P.planRng(7), rets=[]; for(let i=0;i<800;i++){ let z=0; for(let k=0;k<12;k++) z+=rg(); rets.push((z-6)*0.012); }
  const closes=[]; for(let i=0;i<30;i++) closes.push(3400+i*0.5);
  const base={side:1,entry:3400,peak:3400,last:3400,closes,rets};
  const a=P.planExpect(Object.assign({n:800},base)), a2=P.planExpect(Object.assign({n:800},base));
  eq('推演：同样输入同样结果（固定随机种子）',a.win,a2.win);
  eq('推演：未来20个交易日的区间，分位单调',a.fan.length===20&&a.fan.every(f=>f.p10<=f.p25&&f.p25<=f.p50&&f.p50<=f.p75&&f.p75<=f.p90),true);
  eq('推演：各种结局概率加起来=1',Math.abs(a.stopP+a.trailP+a.maP+a.flipP+a.holdP-1)<1e-9,true);
  eq('推演：多单/没传flipHeld时不会有外资翻转离场',a.flipP,0);
  const z=P.planExpect(Object.assign({n:800,edge:0},base)), e=P.planExpect(Object.assign({n:800,edge:0.003},base));
  eq('推演：优势越大胜率越高（无优势<有优势）',z.win<e.win,true);
  eq('推演：无优势时新开仓胜率低于50%（有止损的随机游走）',z.win<.5,true);
  const near=P.planExpect(Object.assign({n:800,edge:0},base,{last:3270})), far=P.planExpect(Object.assign({n:800,edge:0},base));
  eq('推演：离止损越近，触发止损概率越高',near.stopP>far.stopP,true);
  const sh=P.planExpect({side:-1,entry:3400,peak:3400,last:3400,closes,rets,n:800,edge:0});
  eq('推演：空单对称，价格上涨先站上MA20离场',sh.maP>0.3&&sh.fan[19].p90>3400,true);
  const sf=P.planExpect({side:-1,entry:3400,peak:3400,last:3400,closes,rets,n:1500,edge:0,flipHeld:0}), sn=P.planExpect({side:-1,entry:3400,peak:3400,last:3400,closes,rets,n:1500,edge:0});
  eq('空单外资翻转：开启后有相当比例路径因翻转离场、中位持有天数大幅缩短',[sf.flipP>.25,sf.medDays<=sn.medDays,sf.medDays<=6],[true,true,true]);
  eq('空单外资翻转：已持有很多天，今天的翻转概率更高（第6天起20%/天）→ 离场更快',P.planExpect({side:-1,entry:3400,peak:3400,last:3400,closes,rets,n:1500,edge:0,flipHeld:8}).medDays<=sf.medDays,true);
  eq('空单外资翻转：常量齐全',[P.TBT.SEDGE>P.TBT.EDGE,P.TBT.FLIPH.length,P.TBT.FLIPH.every(x=>x>0&&x<1)],[true,6,true]);
  eq('推演：数据太少返回null',P.planExpect({side:1,entry:1,peak:1,last:1,closes:[1],rets:[0.01]}),null);
  const w=P.planWilson(9,14); eq('置信区间：14笔赢9笔，90%区间覆盖64%',w[0]<.643&&w[1]>.643&&w[1]<.95,true);
}

{ // 实盘记录：路径/极值/滑点/复盘
  const h={d:['2026-10-08','2026-10-09','2026-10-12','2026-10-13','2026-10-14'],c:[3300,3400,3360,3300,3380]};
  const sh={side:-1,entryD:'2026-10-09',entryPx:3400,lots:10};
  const pa=P.planPath(h,sh);
  eq('路径：空单从开仓日起 4 个价、持有 3 天',[pa.path.length,pa.days],[4,3]);
  eq('路径：空单最大浮盈=最低价3300→+2.94%，最大浮亏=最高价3400→0%',[+pa.mfe.toFixed(2),+pa.mae.toFixed(2)],[2.94,0]);
  const cl=Object.assign({},sh,{exitD:'2026-10-13',exitPx:3300}), pc=P.planPath(h,cl);
  eq('路径：已平仓只算到平仓日',[pc.path.length,pc.days,pc.path[pc.path.length-1][0]],[3,2,'2026-10-13']);
  eq('路径：开仓日晚于已有数据 → null',P.planPath(h,{side:1,entryD:'2026-11-01',entryPx:3300,lots:1}),null);
  eq('滑点：多单买高了 +0.3%；空单卖低了 +0.3%；买得更好为负',[+P.planSlip(1,3000,3009).toFixed(2),+P.planSlip(-1,3000,2991).toFixed(2),+P.planSlip(1,3000,2991).toFixed(2)],[0.3,0.3,-0.3]);
  eq('滑点：平仓多单卖低了为正（传入 -side）',+P.planSlip(-1,3000,2991).toFixed(2),0.3);
  eq('平仓原因：按系统动作映射',[P.planReasonOf('止损'),P.planReasonOf('移动止盈'),P.planReasonOf('空单离场'),P.planReasonOf('持有')],['stop','trail','foreign','feel']);
  const T=(o)=>Object.assign({id:'x',side:1,lots:10,entryD:'2026-01-05',entryPx:3000,exitD:'2026-01-20',exitPx:3100,src:'sys'},o);
  const R=P.planReview([T({pred:{win:.6,ev:2,rr:2},res:{mfe:5,mae:-1,days:10,slipX:.2},slipO:.1}),T({id:'y',exitPx:2900,src:'own',pred:{win:.5,ev:1,rr:1.5},res:{mfe:1,mae:-4,days:5,slipX:.4},slipO:.3}),T({id:'z',side:-1,exitPx:2950,src:'sys'}),{id:'o',side:1,lots:1,entryD:'2026-02-01',entryPx:3000}],23);
  eq('复盘：只统计已平仓（3笔），分来源/方向',[R.n,R.sys.n,R.own.n,R.long.n,R.short.n],[3,2,1,2,1]);
  eq('复盘：预计vs实际只用有预计的2笔',[R.predN,+R.predWin.toFixed(2),R.actWinOfPred],[2,.55,.5]);
  eq('复盘：平均滑点/极值/捕获率',[+R.slipO.toFixed(2),+R.slipX.toFixed(2),R.mfe,R.mae,+R.capture.toFixed(2)],[.2,.3,3,-2.5,.67]);
  eq('复盘：没有已平仓 → n=0',P.planReview([],23).n,0);
}

{ // 月振幅
  const d=[],c=[]; let px=3000, dt=new Date(Date.UTC(2020,0,1));
  while(dt<=new Date(Date.UTC(2026,9,3))){ const w=dt.getUTCDay(); if(w>0&&w<6){ d.push(dt.toISOString().slice(0,10)); px*=1+Math.sin(d.length*1.3)*0.006; c.push(px); } dt=new Date(dt.getTime()+86400000); }
  const M=P.monthAmpCalc(d,c,'2026-10');
  eq('月振幅：6年多共 81 个完整月，本月没走完（只走了2个交易日）',[M.nDone,M.cur.m,M.cur.n],[81,'2026-10',2]);
  const jan=d.map((x,i)=>[x,c[i]]).filter(a=>a[0].startsWith('2021-03')).map(a=>a[1]), want=(Math.max(...jan)-Math.min(...jan))/jan[jan.length-1]*100;
  eq('月振幅：2021-03 = (最高收盘−最低收盘)/月末收盘',+M.rows.find(r=>r.m==='2021-03').amp.toFixed(6),+want.toFixed(6));
  eq('月振幅：分位单调且在0~100，同月历史（10月）有6个完整年+同样走2天的对比',[M.cur.pctAll>=0&&M.cur.pctAll<=100,M.cur.sameN,M.byMonth[9].n],[true,6,6]);
  eq('月振幅：按月统计 q25<=中位<=q75，min<=q25',M.byMonth.every(b=>b&&b.min<=b.q25&&b.q25<=b.med&&b.med<=b.q75&&b.q75<=b.max),true);
  eq('月振幅：历史太短(<200天)或长度不一致 → null',[P.monthAmpCalc(d.slice(0,100),c.slice(0,100),'2026-10'),P.monthAmpCalc(d,c.slice(1),'2026-10')],[null,null]);
  eq('月振幅：今天所在月之后没有数据时 cur=null（最后一个月算完整月）',P.monthAmpCalc(d,c,'2026-12').cur,null);
}

{ // 开仓来源 + 平仓建议
  const sn=(o)=>Object.assign({gateOk:true,pct:30,confirm:true,delev:false,trendDn:false},o);
  eq('来源：明确写了 own 就是 own',P.planSrc({side:1,src:'own',snap:sn({})}),'own');
  eq('来源：旧记录，做多+低位+反弹+没去杠杆 → 系统信号',P.planSrc({side:1,snap:sn({})}),'sys');
  eq('来源：旧记录，做空但外资没去杠杆 → 自主',P.planSrc({side:-1,snap:sn({delev:false,trendDn:true})}),'own');
  eq('来源：旧记录，做空+去杠杆+趋势向下 → 系统信号',P.planSrc({side:-1,snap:sn({delev:true,trendDn:true})}),'sys');
  eq('来源：数据不足时开的 → 自主',P.planSrc({side:1,snap:sn({gateOk:false})}),'own');
  const A=(o)=>P.planAdvice(Object.assign({src:'sys',side:1,r:3,rr:1.0,ev:0.5,gain:2,loss:2,act:'持有',against:false,entry:3400,entryTxt:'3,400'},o));
  eq('建议：规则已触发离场 → exit，不管怎么开的',[A({act:'止损'}).lv,A({act:'止损',src:'own'}).lv],['exit','exit']);
  eq('建议：系统单、有浮盈、盈亏比<1.5 → 保本止损（不是直接平仓）',[A({}).lv,A({}).L.join('').includes('保本止损')],['protect',true]);
  eq('建议：系统单、盈亏比1.8（≥1.5）→ 持有',A({rr:1.8}).lv,'hold');
  eq('建议：自主单阈值是2:1，1.8 也要保本',A({src:'own',rr:1.8}).lv,'protect');
  eq('建议：自主单、盈亏比2.5 → 可持有（观察）',A({src:'own',rr:2.5}).lv,'watch');
  eq('建议：自主单、方向和系统相反 → 及时平仓',A({src:'own',against:true,rr:3}).lv,'exit');
  eq('建议：自主单、浮亏、盈亏比低 → 减仓/止损',A({src:'own',r:-1,rr:1.2}).lv,'exit');
  eq('建议：系统单、浮亏、盈亏比低 → 仍按规则持有（不自己砍）',A({r:-1,rr:1.0}).lv,'watch');
  eq('建议：系统单盈亏比高 → 持有',A({rr:3}).head.includes('按规则持有'),true);
}

// ---- v101.84 基差（做多第④条）----
{ let cs=Array(200).fill(100); for(let i=0;i<59;i++) cs.push(100-i*0.3); cs.push(cs[cs.length-1]+1.5);
  const a=P.planSignals(cs,0);
  eq('基差：不传 = 原规则，输出字段不变',Object.keys(a).sort(),['below20','confirm','delev','highOK','longOK','lowOK','ma20','ma60','pct','shortOK','trendDn']);
  eq('基差：null = 原规则',P.planSignals(cs,0,null).longOK,true);
  eq('基差 0 → 可做多（边界含 0）',[P.planSignals(cs,0,0).longOK,P.planSignals(cs,0,0).basisOK],[true,true]);
  eq('基差 −0.01% → 不做多，basisBlocked',[P.planSignals(cs,0,-0.0001).longOK,P.planSignals(cs,0,-0.0001).basisBlocked],[false,true]);
  eq('基差 +2% → 可做多',P.planSignals(cs,0,0.02).longOK,true);
  eq('去杠杆时基差不算 basisBlocked（本来就不做多）',P.planSignals(cs,-30000,-0.01).basisBlocked,false);
  eq('planWhy：被基差拦下写原因',P.planWhy(P.planSignals(cs,0,-0.0123)).includes('期货高于现货（基差 -1.23%）'),true);
  eq('planWhy：满足时写上第④条',P.planWhy(P.planSignals(cs,0,0.01)),'低位 + 反弹确认 + 外资没有去杠杆 + 期货不高于现货');
  const dcs=Array(260).fill(0).map((_,i)=>200-i*0.5);
  eq('候选：期货升水+趋势向下+外资没去杠杆 → contangoShort，但 shortOK 不变',[P.planSignals(dcs,0,-0.02).contangoShort,P.planSignals(dcs,0,-0.02).shortOK],[true,false]);
  eq('候选：外资去杠杆时不算候选（已经是正式空单）',[P.planSignals(dcs,-30000,-0.02).contangoShort,P.planSignals(hiDip,-30000,-0.02).shortOK],[false,true]);
  eq('候选：基差≥0 没有候选',P.planSignals(dcs,0,0.01).contangoShort,false);
  const sb={available:true,spot:3358,domPrice:3281,date:'2026-10-16',domSymbol:'m2701'};
  const b=P.planBasis(sb,'2026-10-16'); eq('planBasis：比值=现货÷主力−1',b.v,3358/3281-1,1e-12); eq('planBasis：日期/合约',[b.d,b.dom,b.age],['2026-10-16','m2701',0]);
  eq('planBasis：前一天的也用（age=1）',P.planBasis(Object.assign({},sb,{date:'2026-10-15'}),'2026-10-16').age,1);
  eq('planBasis：差 7 天还用、8 天不用',[P.planBasis(Object.assign({},sb,{date:'2026-10-09'}),'2026-10-16').v!=null,P.planBasis(Object.assign({},sb,{date:'2026-10-08'}),'2026-10-16').v],[true,null]);
  eq('planBasis：没取到 → null 并写原因',[P.planBasis({available:false,reason:'最近4个交易日都没取到'},'2026-10-16').v,P.planBasis({available:false,reason:'x'},'2026-10-16').why.includes('没有基差数据')],[null,true]);
  eq('planBasis：没有对象/缺价格 → null',[P.planBasis(null,'2026-10-16').v,P.planBasis({available:true,spot:0,domPrice:3281,date:'2026-10-16'},'2026-10-16').v,P.planBasis({available:true,spot:3358,domPrice:3281,date:'bad'},'2026-10-16').v],[null,null,null]);
  const sn=o=>Object.assign({pct:30,confirm:true,delev:false,trendDn:false,gateOk:true},o);
  eq('来源：开仓快照里基差<0 → 那天系统不会给多单 → own',P.planSrc({side:1,snap:sn({basis:-0.01})}),'own');
  eq('来源：快照基差≥0 或没有基差 → sys',[P.planSrc({side:1,snap:sn({basis:0.01})}),P.planSrc({side:1,snap:sn({})})],['sys','sys']);
}

// ===== v101.87 候选规则：期货升水做空 / 外资加杠杆做多（默认关，opt 控制）=====
{
  const upc=[...Array(260)].map((_,i)=>i+1);                       // 一路涨：不在低位 → 常规多单不成立；反弹确认成立
  const dnc=Array(260).fill(0).map((_,i)=>200-i*0.5);               // 一路跌：趋势向下
  const o0={contangoShort:false,fxLong:false}, oC={contangoShort:true,fxLong:false}, oF={contangoShort:false,fxLong:true};
  eq('候选A 没开：期货升水+趋势向下只是「出现」，不是信号',(r=>[r.contangoShort,r.cShortGo,r.shortOK,r.via])(P.planSignals(dnc,0,-0.02,o0)),[true,false,false,null]);
  eq('候选A 开了：当做空信号，来源 contango',(r=>[r.cShortGo,r.shortOK,r.via])(P.planSignals(dnc,0,-0.02,oC)),[true,true,'contango']);
  eq('候选A 开了但基差≥0：不出现',(r=>[r.contangoShort,r.shortOK])(P.planSignals(dnc,0,0.01,oC)),[false,false]);
  eq('候选A 开了但趋势没向下：不出现',P.planSignals(upc,0,-0.02,oC).shortOK,false);
  eq('候选A 外资已在去杠杆：常规做空已成立，不算候选单（via 为空）',(r=>[r.contangoShort,r.cShortGo,r.via])(P.planSignals(dnc,-30000,-0.02,oC)),[false,false,null]);
  eq('候选A 没有基差数据：不出现（取不到不猜）',P.planSignals(dnc,0,null,oC).shortOK,false);
  eq('候选B 没开：外资加杠杆只是「出现」(fxCand)，不做多',(r=>[r.fxLever,r.fxCand,r.fxGo,r.longOK])(P.planSignals(upc,0,0.01,Object.assign({fmax:25000},o0))),[true,true,false,false]);
  eq('候选B 开了：当做多信号，来源 fx',(r=>[r.fxGo,r.longOK,r.via])(P.planSignals(upc,0,0.01,Object.assign({fmax:25000},oF))),[true,true,'fx']);
  eq('候选B 门槛边界 +20000 含、19999 不算',[P.planSignals(upc,0,0.01,Object.assign({fmax:20000},oF)).fxGo,P.planSignals(upc,0,0.01,Object.assign({fmax:19999},oF)).fxGo],[true,false]);
  eq('候选B 有席位在去杠杆：不做',(r=>[r.fxLever,r.fxGo,r.longOK])(P.planSignals(upc,-25000,0.01,Object.assign({fmax:30000},oF))),[true,false,false]);
  eq('候选B 期货高于现货：不做',(r=>[r.fxCand,r.fxGo])(P.planSignals(upc,0,-0.01,Object.assign({fmax:30000},oF))),[false,false]);
  eq('候选B 取不到基差：不拦（和本地 fx_lever_long 一致）',P.planSignals(upc,0,null,Object.assign({fmax:30000},oF)).fxGo,true);
  eq('候选B 没有外资数据(fmax=null)：不出现',(r=>[r.fxMax,r.fxLever,r.fxGo])(P.planSignals(upc,0,0.01,Object.assign({fmax:null},oF))),[null,false,false]);
  eq('候选B 常规多单已成立：不算外资加杠杆单（via 为空）',(r=>[r.longOK,r.fxCand,r.fxGo,r.via])(P.planSignals(cs,0,0.01,Object.assign({fmax:30000},oF))),[true,false,false,null]);
  eq('不传 opt：不出现任何候选字段（推送提醒用的调用和 v101.84 一样）',['fxGo','cShortGo','via','fxLever'].map(k=>k in P.planSignals(cs,0,0.01)),[false,false,false,false]);
  eq('两个都开、都没出现：和关着一样',(r=>[r.longOK,r.shortOK])(P.planSignals(cs,0,0.01,{contangoShort:true,fxLong:true,fmax:0})),[true,false]);
  eq('planForeign 最大席位变化',(f=>[f.max,f.maxK])(P.planForeign({'摩根大通':{foreign:true,history:{change5:{change:31000}}},'瑞银期货':{foreign:true,history:{change5:{change:-500}}}})),[31000,'摩根大通']);
  eq('planForeign 没有数据：max=null',P.planForeign({}).max,null);
  eq('planWhy 外资加杠杆(已启用)',P.planWhy(P.planSignals(upc,0,0.01,Object.assign({fmax:31000},oF))).includes('外资加杠杆直接做多（候选规则，你已启用）')&&P.planWhy(P.planSignals(upc,0,0.01,Object.assign({fmax:31000},oF))).includes('+31,000'),true);
  eq('planWhy 期货升水做空(已启用)',P.planWhy(P.planSignals(dnc,0,-0.02,oC)).includes('候选规则，你已启用'),true);
  eq('来源：候选B 启用后开的多单 → sys（快照带 via）',P.planSrc({side:1,snap:{pct:88,confirm:true,delev:false,gateOk:true,via:'fx'}}),'sys');
  eq('来源：候选A 启用后开的空单 → sys',P.planSrc({side:-1,snap:{pct:50,confirm:false,delev:false,trendDn:true,gateOk:true,via:'contango'}}),'sys');
  eq('来源：via=fx 但方向是空 → 仍按自主(own)',P.planSrc({side:-1,snap:{pct:88,confirm:true,delev:false,trendDn:false,gateOk:true,via:'fx'}}),'own');
  eq('来源：没有 via、也不满足常规条件 → own（老记录不受影响）',P.planSrc({side:1,snap:{pct:88,confirm:true,delev:false,gateOk:true}}),'own');
}

// ===== v101.89 做空规则：去杠杆 + 收盘<MA20 + 260日分位≥70 =====
{
  const sg=(c,f)=>P.planSignals(c,f);
  eq('做空：三条齐 → 做空',(r=>[r.delev,r.below20,r.highOK,r.shortOK])(sg(hiDip,-30000)),[true,true,true,true]);
  eq('做空：去掉外资去杠杆 → 不做空',sg(hiDip,-19999).shortOK,false);
  eq('做空：去杠杆边界 −20000 含',sg(hiDip,-20000).shortOK,true);
  const aboveMA=[...Array(259)].map((_,i)=>i+1).concat([300]);   // 高位但收盘在MA20上方
  eq('做空：收盘在MA20上方 → 不做空',(r=>[r.below20,r.highOK,r.shortOK])(sg(aboveMA,-30000)),[false,true,false]);
  const lowBelow=[...Array(240)].map((_,i)=>1000+i).concat([...Array(20)].map((_,i)=>1240-i*40)); // 先涨后大跌到分位很低
  eq('做空：收盘<MA20 但价格分位不到70 → 不做空',(r=>[r.below20,r.highOK,r.shortOK])(sg(lowBelow,-30000)),[true,false,false]);
  { const w=[...Array(181)].map((_,i)=>i+1).concat([...Array(78)].map((_,i)=>1000+i),[500]); const r=sg(w,-30000);   // 181个更低、78个更高、末位500 → 分位恰好70，收盘在MA20下方
    eq('做空：分位恰好70 → 算高位(≥70)',[r.pct,r.highOK,r.below20,r.shortOK],[70,true,true,true]);
    const w2=w.slice(); w2[w2.length-1]=499; w2[0]=600;   // 分位降到 ~69.6
    eq('做空：分位<70 → 不算高位',sg(w2,-30000).highOK,false); }
  eq('做空：分位边界 ≥70（P.TPLAN.SHORT_PCT=70）',P.TPLAN.SHORT_PCT,70);
  eq('planWhy 做空文案含分位',P.planWhy(sg(hiDip,-30000)).includes('分位')&&P.planWhy(sg(hiDip,-30000)).includes('≥ 70%'),true);
  eq('planWhy 去杠杆但分位不够 → 不做空文案',P.planWhy(sg(lowBelow,-30000)).includes('不算高位'),true);
  eq('planSrc 新快照(below20+highOK+delev) 空单 → sys',P.planSrc({side:-1,snap:{pct:90,confirm:false,delev:true,below20:true,highOK:true,gateOk:true}}),'sys');
  eq('planSrc 新快照 分位不够 → own',P.planSrc({side:-1,snap:{pct:50,confirm:false,delev:true,below20:true,highOK:false,gateOk:true}}),'own');
  eq('planSrc 老快照(只有trendDn) 仍按旧规则 → sys',P.planSrc({side:-1,snap:{pct:50,confirm:false,delev:true,trendDn:true,gateOk:true}}),'sys');
}
console.log(`\n结果：${pass}项通过，${fail}项失败`); process.exit(fail?1:0);
