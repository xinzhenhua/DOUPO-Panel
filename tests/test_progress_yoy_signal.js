const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

// ===================== 测试1：computeProgressSignal — 五年均值路径(主路径) =====================
const r1 = computeProgressSignal(
  {currentValue: 58, fiveYearAvg: 62.5, fiveYearAvgChangePts: -4.5, yoyValue: 61, yoyChangePts: -3, wowChangePts: -2},
  {slow: -2, fast: 2}
);
check('★比五年均值低4.5个百分点(超过±5阈值门槛的负向)……等等验证边界：-4.5未超过-5阈值，应该是中性', r1.sig === 0);
check('★basis应该标注是fiveYearAvg(说明用的是主路径，不是环比退化路径)', r1.basis === 'fiveYearAvg');

const r2 = computeProgressSignal(
  {currentValue: 55, fiveYearAvg: 62, fiveYearAvgChangePts: -7, yoyValue: 60, yoyChangePts: -5, wowChangePts: -1},
  {slow: -2, fast: 2}
);
check('★比五年均值低7个百分点(超过-5阈值)，应该判定为偏多', r2.sig === 1 && r2.cls === 'bull');
check('说明文字应该提到具体的五年均值数字和差距', r2.reason.includes('62') && r2.reason.includes('7'));

const r3 = computeProgressSignal(
  {currentValue: 70, fiveYearAvg: 62, fiveYearAvgChangePts: 8, yoyValue: 65, yoyChangePts: 5, wowChangePts: 3},
  {slow: -2, fast: 2}
);
check('★比五年均值高8个百分点(超过+5阈值)，应该判定为偏空', r3.sig === -1 && r3.cls === 'bear');

// ===================== 测试2：computeProgressSignal — 五年均值缺失时退化到环比路径 =====================
const r4 = computeProgressSignal(
  {currentValue: 58, fiveYearAvg: null, fiveYearAvgChangePts: null, yoyValue: null, yoyChangePts: null, wowChangePts: -3},
  {slow: -2, fast: 2}
);
check('★五年均值缺失时应该退化到环比阈值判断(basis=wow)', r4.basis === 'wow');
check('环比-3小于slow阈值-2，应该判定偏多', r4.sig === 1);
check('★退化路径的说明文字应该明确标注"置信度低"，不能假装跟主路径一样可靠', r4.reason.includes('置信度低'));

// ===================== 测试3：computeProgressSignal — 完全没有数据(连环比都没有) =====================
const r5 = computeProgressSignal(
  {currentValue: 58, fiveYearAvg: null, fiveYearAvgChangePts: null, yoyValue: null, yoyChangePts: null, wowChangePts: null},
  {slow: -2, fast: 2}
);
check('★连环比都没有时，sig应该是null(信息不足，不能瞎猜)，不是0(中性)', r5.sig === null);
check('basis应该标注none', r5.basis === 'none');

// ===================== 测试4：renderSoyCond整合——新字段应该正确显示且驱动信号 =====================
makeEl('soyCondBadge'); makeEl('soyCondContent');
const scWithHistory = {
  available: true, weekEnding: '2026-09-20', goodExcellentPct: 55,
  wowChangePts: -3, yoyValue: 61, yoyChangePts: -6, fiveYearAvg: 63, fiveYearAvgChangePts: -8,
  source: '测试',
};
renderSoyCond(scWithHistory, new Date().toISOString());
check('★优良率比五年均值低8个点(超阈值)，应该判定为偏多', window._soyCondSignal === 1);
check('★页面应该显示去年同期数值(61%)', makeEl('soyCondContent').innerHTML.includes('61%'));
check('★页面应该显示五年均值数值(63%)', makeEl('soyCondContent').innerHTML.includes('63%'));

// 没有历史数据时(旧数据结构，只有wowChangePts)，应该正常退化，不报错
const scNoHistory = {available: true, weekEnding: '2026-09-20', goodExcellentPct: 58, wowChangePts: -1, source: '测试'};
renderSoyCond(scNoHistory, new Date().toISOString());
check('★没有五年均值字段时(旧数据结构)不应该报错，应该正常渲染', makeEl('soyCondContent').innerHTML.includes('58%'));

// ===================== 测试5：renderPlanting / renderHarvest 整合 =====================
makeEl('plantingBadge'); makeEl('plantingContent');
const ppWithHistory = {available: true, weekEnding: '2026-05-04', pctPlanted: 45, wowChangePts: 10, yoyValue: 30, yoyChangePts: 15, fiveYearAvg: 32, fiveYearAvgChangePts: 13, source: '测试'};
renderPlanting(ppWithHistory, new Date().toISOString());
check('★播种进度比五年均值快13个点(超阈值)，应该判定为偏空(播种过快)', window._plantingSignal === -1);
check('页面应该显示五年均值(32%)', makeEl('plantingContent').innerHTML.includes('32%'));

makeEl('harvestBadge'); makeEl('harvestContent');
const hpWithHistory = {available: true, weekEnding: '2026-09-20', pctHarvested: 12, wowChangePts: 6, yoyValue: 8, yoyChangePts: 4, fiveYearAvg: 8, fiveYearAvgChangePts: 4, source: '测试'};
renderHarvest(hpWithHistory, new Date().toISOString());
check('收获进度比五年均值差距4个点(未超±5阈值)，应该是中性', window._harvestSignal === 0);
check('页面应该显示去年同期(8%)', makeEl('harvestContent').innerHTML.includes('8%'));

H.printSummary();
