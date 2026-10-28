// 本金追加计算器（cockpit/logic.js 的 calc*）：手算对拍 + 边界。运行：node test_calc.js
const L = require('../cockpit/logic.js'); let pass = 0, fail = 0;
const eq = (n, x, y, tol) => { const ok = tol ? Math.abs(x - y) <= tol : JSON.stringify(x) === JSON.stringify(y); ok ? pass++ : (fail++, console.log('❌', n, '期望', y, '实际', x)); if (ok) console.log('✅', n); };
const P = { start: 10, add: 1, ladder: 'cur', ddy: 0, ddp: 0 };
// 档位边界
eq('档位 <500万=55%', L.calcTier(499.99, 'cur'), .55); eq('v45 <500万=45%', L.calcTier(100, 'v45'), .45); eq('档位 500万整=40%', L.calcTier(500, 'cur'), .40);
eq('档位 1500万整=25%', L.calcTier(1500, 'cur'), .25); eq('档位 5000万整=15%', L.calcTier(5000, 'cur'), .15); eq('档位 flat 1亿=55%', L.calcTier(1e4, 'flat'), .55);
eq('旧阶梯 100万=60%', L.calcTier(100, 'old'), .60);
eq('折算 55%=1', L.calcFactor(.55), 1, 1e-12); eq('折算 45%=48/52', L.calcFactor(.45), 48 / 52, 1e-12); eq('折算 60%=55/52', L.calcFactor(.60), 55 / 52, 1e-12); eq('折算 15%=15/55', L.calcFactor(.15), .15 / .55, 1e-12);
// 手算：不追加、不降档的第1年 = 本金×(1+r)（12 个月 (1+r)^(1/12) 复利）
const s1 = L.calcSim({ start: 10, add: 0, ladder: 'flat', ddy: 0, ddp: 0 }, .36, 1); eq('1年末=10×1.36', s1.final, 13.6, 1e-9);
const s3 = L.calcSim({ start: 10, add: 0, ladder: 'flat', ddy: 0, ddp: 0 }, .36, 3); eq('3年末=10×1.36³', s3.final, 10 * Math.pow(1.36, 3), 1e-9);
// 追加：第2年起每年年初：年末 = (13.6+1)×1.36
const s2 = L.calcSim({ start: 10, add: 1, ladder: 'flat', ddy: 0, ddp: 0 }, .36, 2); eq('追加：第2年末=(13.6+1)×1.36', s2.final, 14.6 * 1.36, 1e-9); eq('累计投入=11', s2.invested, 11);
eq('第1年没有追加', s2.yearly[0].add, 0); eq('第2年追加=1', s2.yearly[1].add, 1);
// 与先前口径一致：10万+1万/年，36%/24%/48% 到 50 万 = 56/76/46 个月
eq('36%到50万=56月', L.calcMonthsTo(P, .36, 50, 50), 56); eq('24%到50万=76月', L.calcMonthsTo(P, .24, 50, 50), 76); eq('48%到50万=46月', L.calcMonthsTo(P, .48, 50, 50), 46);
eq('起点已达到目标=第0月', L.calcMonthsTo({ start: 600, add: 0, ladder: 'cur', ddy: 0, ddp: 0 }, .3, 500, 5), 0);
eq('到不了=null', L.calcMonthsTo({ start: 1, add: 0, ladder: 'cur', ddy: 0, ddp: 0 }, .01, 1e6, 5), null);
// 阶梯降档：500万以上收益变小（同样的年化，档位 40% → 月收益按 40/55 缩小）
const hi = L.calcSim({ start: 1000, add: 0, ladder: 'cur', ddy: 0, ddp: 0 }, .36, 1); eq('1000万档(40%)一年=×(1+.36×40/55)', hi.final, 1000 * (1 + .36 * 40 / 55), 1e-6);
const v45 = L.calcSim({ start: 100, add: 0, ladder: 'v45', ddy: 0, ddp: 0 }, .36, 1); eq('v45 100万一年=×(1+.36×48/52)', v45.final, 100 * (1 + .36 * 48 / 52), 1e-9);
// 回撤：第2年末亏20%
const dd = L.calcSim({ start: 10, add: 0, ladder: 'flat', ddy: 2, ddp: 20 }, .36, 3); eq('回撤：3年末=10×1.36²×0.8×1.36', dd.final, 10 * 1.36 * 1.36 * .8 * 1.36, 1e-9);
eq('回撤年标记', dd.yearly.map(y => y.dd), [false, true, false]);
// 反推每年追加：代回去刚好到目标
const need = L.calcNeedAdd({ start: 5, add: 0, ladder: 'cur', ddy: 0, ddp: 0 }, .36, 1000, 10);
eq('反推追加代回=目标', L.calcSim({ start: 5, add: need, ladder: 'cur', ddy: 0, ddp: 0 }, .36, 10).final, 1000, 1e-3);
eq('本金已够→追加0', L.calcNeedAdd({ start: 1000, add: 0, ladder: 'cur', ddy: 0, ddp: 0 }, .36, 500, 5), 0);
// 回撤同样计入反推
const need2 = L.calcNeedAdd({ start: 5, add: 0, ladder: 'cur', ddy: 3, ddp: 20 }, .36, 1000, 10); eq('回撤使所需追加变大', need2 > need, true);
// 格式化
eq('fmt 10432→1.04 亿', L.calcFmt(10432), '1.04 亿'); eq('fmt 273.4→273 万', L.calcFmt(273.4), '273 万'); eq('fmt 12.34→12.3 万', L.calcFmt(12.34), '12.3 万'); eq('fmt 1234→1,234 万', L.calcFmt(1234), '1,234 万');
eq('ym 56→4 年 8 个月', L.calcYm(56), '4 年 8 个月'); eq('ym 12→1 年', L.calcYm(12), '1 年'); eq('ym 5→5 个月', L.calcYm(5), '5 个月'); eq('ym null', L.calcYm(null), '—');
console.log(`\n结果：${pass}项通过，${fail}项失败`); process.exit(fail ? 1 : 0);
