const fs=require('fs'), path=require('path'); const src=fs.readFileSync(path.join(__dirname,'..','cockpit','ui.js'),'utf8');
const a=src.indexOf('/* PLAN_BEGIN'), b=src.indexOf('/* PLAN_END */'); if(a<0||b<0){console.log('❌ 找不到 TPLAN 标记');process.exit(1)}
const code=src.slice(a,b)+'\nreturn {TPLAN,planTier,planPct,planMA,planConfirm,planForeign,planSignals,planSize,planManage};';
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
const f=P.planForeign(mem); eq('外资5日合计=-3744',f.sum,-3744); eq('外资缺失席位',f.missing,['瑞银期货']); eq('外资用到的席位',f.used,['高盛期货','摩根大通']);
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
console.log(`\n结果：${pass}项通过，${fail}项失败`); process.exit(fail?1:0);
