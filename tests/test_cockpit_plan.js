const fs=require('fs'), path=require('path'); const src=fs.readFileSync(path.join(__dirname,'..','cockpit','ui.js'),'utf8');
const a=src.indexOf('/* PLAN_BEGIN'), b=src.indexOf('/* PLAN_END */'); if(a<0||b<0){console.log('❌ 找不到 TPLAN 标记');process.exit(1)}
const code=src.slice(a,b)+'\nreturn {TPLAN,planTier,planPct,planMA,planConfirm,planForeign,planSignals,planSize,planManage,planWhy,planFee,planPnl,planOpen,planOpenFor,planHold,planEquity,planStats,planGate,planDataLine,planPartsText};';
const P=new Function(code)(); let pass=0,fail=0;
const eq=(n,x,y,tol)=>{ const ok=tol?Math.abs(x-y)<=tol:JSON.stringify(x)===JSON.stringify(y); ok?pass++:(fail++,console.log('❌',n,'期望',y,'实际',x)); if(ok) console.log('✅',n) };
// 阶梯(边界：<500万 才是60%)
eq('阶梯 10万→60%',P.planTier(100000),.6); eq('阶梯 499.99万→60%',P.planTier(4999999),.6); eq('阶梯 500万整→40%',P.planTier(5000000),.4);
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
let dcs=Array(260).fill(0).map((_,i)=>200-i*0.5); eq('空头 下行+去杠杆→可做空',P.planSignals(dcs,-30000).shortOK,true); eq('空头 无去杠杆→不做空',P.planSignals(dcs,0).shortOK,false);
// 仓位计算(手算)：权益50万 价3400 保证金13% 占用60% → floor(300000/(10*3400*0.13))=floor(67.87)=67 手
let z=P.planSize({equity:500000,margin:.13,price:3400,side:1,mode:'real'});
eq('手数(实际保证金13%)=67',z.lots,67); eq('名义金额',z.notional,2278000); eq('占用保证金',z.margin,296140,1e-6); eq('实际占用',z.usage,296140/500000,1e-9);
eq('止损价=3264',z.stopPx,3264,1e-9); eq('止损亏损=91120',z.lossStop,91120,1e-6); eq('止损亏损占权益',z.lossPct,91120/500000,1e-12);
eq('风险度100%价(多)≈3050.4',z.liqPx,(670*3400-500000)/(670*0.87),1e-9); eq('启动价(最高浮盈8%)=3672',z.actPx,3672,1e-9);
// 回测口径：按10%保证金 → 88 手；保证金13%时风险度在止损价附近≈98%
let y=P.planSize({equity:500000,margin:.13,price:3400,side:1,mode:'bt'});
eq('手数(回测口径)=88',y.lots,88); eq('回测口径·风险100%价(多)≈3254.96',y.liqPx,(880*3400-500000)/(880*0.87),1e-9);
eq('回测口径·止损处风险度',y.riskAtStop,(2992000*0.13*0.96)/(500000-119680),1e-9);
let sh=P.planSize({equity:500000,margin:.10,price:3400,side:-1,mode:'real'}); eq('空头手数=88',sh.lots,88); eq('空头止损价=3536',sh.stopPx,3536,1e-9);
eq('空头风险100%价',sh.liqPx,(500000+880*3400)/(880*1.10),1e-9);
eq('资金不足一手→0手(5000*0.6/(10*3400*0.13)=0.68)',P.planSize({equity:5000,margin:.13,price:3400,side:1,mode:'real'}).lots,0);
eq('刚好够一手(权益8000:4800/4420=1.09→1手)',P.planSize({equity:8000,margin:.13,price:3400,side:1,mode:'real'}).lots,1);
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
  eq('上行趋势里回落到MA20下方：MA20>MA60 → 不是下行趋势，不做空',sg.shortOK,false); }
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
console.log(`\n结果：${pass}项通过，${fail}项失败`); process.exit(fail?1:0);
