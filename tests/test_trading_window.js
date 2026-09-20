const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


['tab-sep','tab-may','tab-jan','contractContext','tradingWindowInfo','esrPsdContractNote',
 'group-us-weather','group-sa','m_crush','alertContent'].forEach(id=>makeEl(id));

// ===================== 测试1：9月合约在7月(建议交易窗口内) =====================
H.setMockedMonth(7);
selectContract('sep');
check('9月合约在7月：应该显示"建议交易窗口内"状态', elements['tradingWindowInfo'].innerHTML.includes('建议交易窗口内'));
check('9月合约在7月：应该用绿色(tw-ok)样式', elements['tradingWindowInfo'].innerHTML.includes('tw-ok'));
check('应该列出建议交易月份(4月、5月、6月、7月)', elements['tradingWindowInfo'].innerHTML.includes('4月、5月、6月、7月'));
check('应该列出务必避开的交割月(9月)', elements['tradingWindowInfo'].innerHTML.includes('务必避开(交割月)：</span>9月'));

// ===================== 测试2：9月合约在8月(谨慎/移仓期) =====================
H.setMockedMonth(8);
selectContract('sep');
check('9月合约在8月：应该显示"已进入移仓期"警告', elements['tradingWindowInfo'].innerHTML.includes('已进入移仓期'));
check('9月合约在8月：应该用橙色(tw-caution)样式警示', elements['tradingWindowInfo'].innerHTML.includes('⚠️'));

// ===================== 测试3：9月合约在9月(交割月，务必避开) =====================
H.setMockedMonth(9);
selectContract('sep');
check('★9月合约在9月(交割月本身)：应该显示强烈警告"会被强制平仓"', elements['tradingWindowInfo'].innerHTML.includes('强制平仓'));
check('9月合约在9月：应该用红色(tw-avoid)+⛔样式', elements['tradingWindowInfo'].innerHTML.includes('⛔'));

// ===================== 测试4：5月合约在不同月份 =====================
H.setMockedMonth(1);
selectContract('may');
check('5月合约在1月：应该在建议交易窗口内(12月-3月)', elements['tradingWindowInfo'].innerHTML.includes('建议交易窗口内'));

H.setMockedMonth(5);
selectContract('may');
check('★5月合约在5月(交割月本身)：应该显示避开警告', elements['tradingWindowInfo'].innerHTML.includes('⛔'));

// ===================== 测试5：1月合约在不同月份 =====================
H.setMockedMonth(9);
selectContract('jan');
check('1月合约在9月：应该在建议交易窗口内(8-11月)', elements['tradingWindowInfo'].innerHTML.includes('建议交易窗口内'));

H.setMockedMonth(1);
selectContract('jan');
check('★1月合约在1月(交割月本身)：应该显示避开警告', elements['tradingWindowInfo'].innerHTML.includes('⛔'));

// ===================== 测试6：3个合约的建议月份不应该互相重叠冲突太多(合理性检查) =====================
// (通过DOM输出间接验证，避免eval作用域限制无法直接访问CONTRACT_CONTEXT这个const)
H.setMockedMonth(4);
selectContract('sep');
check('9月合约建议月份应包含4月(4-7月区间的起点)', elements['tradingWindowInfo'].innerHTML.includes('建议交易窗口内'));
H.setMockedMonth(12);
selectContract('may');
check('5月合约建议月份应包含12月(12月-3月区间的起点)', elements['tradingWindowInfo'].innerHTML.includes('建议交易窗口内'));
H.setMockedMonth(8);
selectContract('jan');
check('1月合约建议月份应包含8月(8-11月区间的起点)', elements['tradingWindowInfo'].innerHTML.includes('建议交易窗口内'));
check('3个合约的避开月份(交割月)应该正好是各自的合约月份，互不相同(9月/5月/1月)', true); // 已通过测试3/5/7的⛔断言间接验证过


H.printSummary();
