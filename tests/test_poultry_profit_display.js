const H = require('./test_helpers');
const { makeEl, check } = H;
eval(H.loadDashboardJs());
// v101.8：肉鸡养殖利润改用 国家发改委价格监测中心×卓创资讯《猪料、鸡料、蛋料比价》周报的'未来肉鸡养殖预期盈利'，不再用 Mysteel。
// 原 test_mysteel_poultry_profit_display.js 的行为(正值带+号、负号不能丢、覆盖已有值、失败不报错、空数据不报错)在新数据源下仍然成立，改写成新数据形状；新增：鸡料比价/平衡点展示、周标签、三种警告、来源不再是 Mysteel。
function reset(){ makeEl('m_poultry').value = ''; makeEl('ai_poultry'); makeEl('ind_poultry'); }
const dayStr = (n)=>{ const d=new Date(Date.now()-n*86400000); const bj=new Date(d.getTime()+8*3600000); return bj.toISOString().slice(0,10); };      // 距今n天的北京日期：新鲜度规则按'今天'算，夹具里的日期不能写死
const NP = (o)=>Object.assign({available:true, value:1.54, date:dayStr(3), ratio:2.26, balance:2.08, weekLabel:'2026年3月第1周', usedFallback:false, fallbackWeeks:0, dateFallback:false, formulaCheckOk:true, formulaCheckValue:1.54,
  definition:'发改委按成本模型推算的未来肉鸡养殖预期盈利，不是Mysteel的白羽肉鸡养殖利润'}, o||{});

// 栏位为空：正数(盈利)自动填入，带+号，显示鸡料比价和平衡点
reset();
window._syncedData = {generatedAt:new Date().toISOString(), ndrcPoultryProfit:NP()};
refreshMysteelPoultryProfit();
check('★盈利时应该自动填入正值', makeEl('m_poultry').value == '1.54');
check('★提示区应该显示正数带+号', makeEl('ai_poultry').innerHTML.includes('+1.54元/只'));
check('★提示区应该显示鸡料比价和平衡点(2.26、2.08)', makeEl('ai_poultry').innerHTML.includes('鸡料比价2.26') && makeEl('ai_poultry').innerHTML.includes('平衡点2.08'));
check('★提示区应该显示监测日期和周标签', makeEl('ai_poultry').innerHTML.includes(dayStr(3)) && makeEl('ai_poultry').innerHTML.includes('2026年3月第1周'));
check('★来源是发改委×卓创，不再是 Mysteel，并说明不是白羽肉鸡养殖利润', makeEl('ai_poultry').innerHTML.includes('发改委') && makeEl('ai_poultry').innerHTML.includes('不是Mysteel的白羽肉鸡养殖利润'));
check('★没有触发任何回退/笔误/不一致时不应该出现警告', !makeEl('ai_poultry').innerHTML.includes('⚠️'));

// ★核心：负数(亏损)时不能漏掉负号
reset();
window._syncedData = {generatedAt:new Date().toISOString(), ndrcPoultryProfit:NP({value:-4.1, date:dayStr(3), ratio:1.79, balance:2.25, weekLabel:'2026年9月第4周', formulaCheckValue:-4.1})};
refreshMysteelPoultryProfit();
check('★亏损时应该自动填入负值(不是绝对值，源头写的是"预期亏损4.10元/只")', makeEl('m_poultry').value == '-4.1');
check('★提示区应该正确显示负号，不应该多此一举加"+"号', makeEl('ai_poultry').innerHTML.includes('-4.1元/只') && !makeEl('ai_poultry').innerHTML.includes('+-4.1'));
check('★不再有采用按钮', !makeEl('ai_poultry').innerHTML.includes('采用'));

// 抓取成功时直接覆盖已有值
reset(); makeEl('m_poultry').value = '1.5';
window._syncedData = {generatedAt:new Date().toISOString(), ndrcPoultryProfit:NP({value:-3.31, date:dayStr(3), ratio:1.83, balance:2.3, formulaCheckValue:-3.31})};
refreshMysteelPoultryProfit();
check('★抓取成功时应直接覆盖已有值(1.5→-3.31)', makeEl('m_poultry').value == '-3.31');
check('提示区应该显示抓取到的负值', makeEl('ai_poultry').innerHTML.includes('-3.31元/只'));

// 三种警告
reset();
window._syncedData = {generatedAt:new Date().toISOString(), ndrcPoultryProfit:NP({value:1.54, usedFallback:true, fallbackWeeks:1})};
refreshMysteelPoultryProfit();
check('★最新一期没解析出来、用了前一期：诚实提示', makeEl('ai_poultry').innerHTML.includes('最新一期周报没解析出来') && makeEl('ai_poultry').innerHTML.includes('1期前'));
reset();
window._syncedData = {generatedAt:new Date().toISOString(), ndrcPoultryProfit:NP({dateFallback:true})};
refreshMysteelPoultryProfit();
check('★正文日期有笔误、日期取了发布日之前的周三：诚实提示', makeEl('ai_poultry').innerHTML.includes('年份笔误') && makeEl('ai_poultry').innerHTML.includes('最近的周三'));
reset();
window._syncedData = {generatedAt:new Date().toISOString(), ndrcPoultryProfit:NP({value:5.0, formulaCheckOk:false, formulaCheckValue:1.54})};
refreshMysteelPoultryProfit();
check('★公布值(5)与公式验算(1.54)对不上：提示两个数，取公布值', makeEl('ai_poultry').innerHTML.includes('对不上') && makeEl('ai_poultry').innerHTML.includes('1.54') && makeEl('m_poultry').value == '5');

// ★周频数据的新鲜度规则对发改委数据同样生效：监测日期距今218天 → 提示数据已过期、不参与综合评分(之前这条规则只验证过 Mysteel 的数据形状)
reset();
window._syncedData = {generatedAt:new Date().toISOString(), ndrcPoultryProfit:NP({date:'2026-03-04'})};
refreshMysteelPoultryProfit();
check('★过期的发改委周报(距今远超周频的正常间隔)：显示数值，但标"数据已过期…不参与综合评分"', makeEl('m_poultry').value == '1.54' && makeEl('ai_poultry').innerHTML.includes('数据已过期') && makeEl('ai_poultry').innerHTML.includes('不参与综合评分'));

// 失败/空数据不报错
reset();
window._syncedData = {generatedAt:new Date().toISOString(), ndrcPoultryProfit:{available:false, reason:'子栏目列表里没有文章链接(测试)'}};
try { refreshMysteelPoultryProfit(); check('★抓取失败时不应该报错', true); } catch(e){ check('★抓取失败时不应该报错', false); }
check('★失败时应该显示明确原因', makeEl('ai_poultry').innerHTML.includes('没有文章链接'));
delete window._syncedData;
try { refreshMysteelPoultryProfit(); check('★window._syncedData为空时不应该报错', true); } catch(e){ check('★window._syncedData为空时不应该报错', false); }
H.printSummary();
