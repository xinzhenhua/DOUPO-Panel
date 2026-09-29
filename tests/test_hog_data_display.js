const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());

function reset(id, aiId, indId){
  makeEl(id).value = '';
  makeEl(aiId);
  makeEl(indId);
}

// ===================== 猪粮比：欄位为空自动填入 =====================
reset('m_hogratio', 'ai_hogratio', 'ind_hogratio');
window._syncedData = {generatedAt: new Date().toISOString(), hogRatio: {available: true, value: 8.22, date: '2026-09-22', source: '玄田数据'}};
refreshHogRatio();
check('★猪粮比欄位是空的时应该自动填入', makeEl('m_hogratio').value == '8.22');
check('★提示区应该显示玄田数据字样和数值', makeEl('ai_hogratio').innerHTML.includes('玄田数据') && makeEl('ai_hogratio').innerHTML.includes('8.22'));

// 已有值时：抓取成功直接覆盖
reset('m_hogratio', 'ai_hogratio', 'ind_hogratio');
makeEl('m_hogratio').value = '7.5';
window._syncedData = {generatedAt: new Date().toISOString(), hogRatio: {available: true, value: 8.22, date: '2026-09-22'}};
refreshHogRatio();
check('★猪粮比：抓取成功时直接覆盖已有值(7.5→8.22)', makeEl('m_hogratio').value == '8.22');

// 失败时显示明确原因
reset('m_hogratio', 'ai_hogratio', 'ind_hogratio');
makeEl('ai_hogratio').className = 'ai-suggest unavailable';
makeEl('ai_hogratio').innerHTML = '💡 尚未粘贴数据';
window._syncedData = {generatedAt: new Date().toISOString(), hogRatio: {available: false, reason: 'akshare接口调用失败(测试)'}};
refreshHogRatio();
check('★猪粮比失败时应该替换掉默认文字，显示明确原因', !makeEl('ai_hogratio').innerHTML.includes('尚未粘贴数据') && makeEl('ai_hogratio').innerHTML.includes('akshare接口调用失败(测试)'));

// ===================== 能繁母猪存栏：欄位为空自动填入 =====================
reset('m_sows', 'ai_sows', 'ind_sows');
window._syncedData = {generatedAt: new Date().toISOString(), sowInventory: {available: true, value: 3780, date: '2026-09-24', quarterLabel: '2026年二季度末', source: 'Mysteel文章'}};
refreshSowInventory();
check('★能繁母猪存栏欄位是空的时应该自动填入', makeEl('m_sows').value == '3780');
check('★提示区应该显示万头单位', makeEl('ai_sows').innerHTML.includes('3780万头'));
check('★提示区应该明确标出是哪个季度末(2026年二季度末)', makeEl('ai_sows').innerHTML.includes('2026年二季度末'));
check('★提示区应该标出文章发布日期', makeEl('ai_sows').innerHTML.includes('2026-09-24'));
check('提示区应该标注来源是Mysteel，不再是玄田数据', makeEl('ai_sows').innerHTML.includes('Mysteel') && !makeEl('ai_sows').innerHTML.includes('玄田数据'));

// 已有值时：抓取成功直接覆盖
reset('m_sows', 'ai_sows', 'ind_sows');
makeEl('m_sows').value = '4000';
window._syncedData = {generatedAt: new Date().toISOString(), sowInventory: {available: true, value: 3780, date: '2026-09-24', quarterLabel: '2026年二季度末'}};
refreshSowInventory();
check('★能繁母猪存栏：抓取成功时直接覆盖已有值(4000→3780)', makeEl('m_sows').value == '3780');

// 失败时显示明确原因
reset('m_sows', 'ai_sows', 'ind_sows');
makeEl('ai_sows').className = 'ai-suggest unavailable';
makeEl('ai_sows').innerHTML = '💡 尚未粘贴数据';
window._syncedData = {generatedAt: new Date().toISOString(), sowInventory: {available: false, reason: '接口返回空数据(测试)'}};
refreshSowInventory();
check('★能繁母猪存栏失败时应该替换掉默认文字，显示明确原因', !makeEl('ai_sows').innerHTML.includes('尚未粘贴数据') && makeEl('ai_sows').innerHTML.includes('接口返回空数据(测试)'));

// window._syncedData为空时不报错
delete window._syncedData;
try {
  refreshHogRatio();
  refreshSowInventory();
  check('★window._syncedData为空时两个函式都不应该报错', true);
} catch(e) {
  check('★window._syncedData为空时两个函式都不应该报错', false);
}


// ===================== 猪粮比：展示计算依据(外三元价格÷玉米价格) =====================
reset('m_hogratio', 'ai_hogratio', 'ind_hogratio');
window._syncedData = {generatedAt: new Date().toISOString(), hogRatio: {available: true, value: 4.4, date: '2026-09-27', pigPrice: 10.37, cornPricePerTon: 2358}};
refreshHogRatio();
check('★猪粮比提示区应该展示计算依据：外三元10.37元/公斤', makeEl('ai_hogratio').innerHTML.includes('外三元10.37元/公斤'));
check('★猪粮比提示区应该展示计算依据：玉米2358元/吨', makeEl('ai_hogratio').innerHTML.includes('玉米2358元/吨'));
check('猪粮比数值和日期依然正常显示', makeEl('ai_hogratio').innerHTML.includes('4.4') && makeEl('ai_hogratio').innerHTML.includes('2026-09-27'));

// 没有计算依据字段时(老数据)不应该显示undefined
reset('m_hogratio', 'ai_hogratio', 'ind_hogratio');
window._syncedData = {generatedAt: new Date().toISOString(), hogRatio: {available: true, value: 4.4, date: '2026-09-27'}};
refreshHogRatio();
check('★没有计算依据字段时不应该出现undefined', !makeEl('ai_hogratio').innerHTML.includes('undefined'));


// ===================== ★旧格式数据防护(复现用户截图：旧版akshare后端的3990万头/2025年10月) =====================
reset('m_sows', 'ai_sows', 'ind_sows');
makeEl('ai_sows').className = 'ai-suggest unavailable';
makeEl('ai_sows').innerHTML = '💡 尚未粘贴数据';
window._syncedData = {generatedAt: new Date().toISOString(), sowInventory: {available: true, value: 3990, date: '2025年10月', source: '玄田数据(经akshare的futures_hog_supply接口获取)'}};
refreshSowInventory();
check('★旧格式数据(没有quarterLabel)绝不能自动填入输入框', makeEl('m_sows').value === '');
check('★旧格式数据不能显示成"自动抓取(Mysteel)…采用"(那是误导)', !makeEl('ai_sows').innerHTML.includes('自动抓取(Mysteel)') && !makeEl('ai_sows').innerHTML.includes('采用'));
check('★应该提示这是旧版本后端的数据，并指引去检查Actions/latest.json', makeEl('ai_sows').innerHTML.includes('旧版本后端') && makeEl('ai_sows').innerHTML.includes('没有季度末信息'));

H.printSummary();
