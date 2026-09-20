const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


['tab-sep','tab-may','tab-jan','contractContext','esrPsdContractNote','group-us-weather','group-sa',
 'm_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry','m_rmspread',
 'ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import','ind_poultry','ind_rmspread',
 'alertContent'].forEach(id=>makeEl(id));

// ★ 核心验证：ESR/PSD不属于contract-group(group-us-weather/group-sa)，
//   所以selectContract()的隐藏逻辑不会碰到它们，3个合约下都应该保持可见
const html = require('fs').readFileSync('/home/claude/soymeal-dashboard/index.html', 'utf8');
const esrPos = html.indexOf('id="esrContent"');
const psdPos = html.indexOf('id="psdContent"');
const groupUsOpen = html.indexOf('id="group-us-weather"');
const groupUsClose = html.indexOf('/group-us-weather');
const groupSaOpen = html.indexOf('id="group-sa"');
const groupSaClose = html.indexOf('/group-sa');
check('ESR卡片应该在group-us-weather容器外面(不会被9月/5月切换隐藏)', esrPos > groupUsClose);
check('ESR卡片应该在group-sa容器外面', esrPos > groupSaClose || esrPos < groupSaOpen);
check('PSD卡片应该在两个contract-group容器外面', psdPos > groupUsClose && (psdPos > groupSaClose || psdPos < groupSaOpen));

// ===================== 验证3个合约下contractNote正确更新，且ESR/PSD从不被隐藏 =====================
['sep','may','jan'].forEach(month=>{
  selectContract(month);
  check(`${month}合约：esrPsdContractNote应该有内容(不是空的)`, elements['esrPsdContractNote'].innerHTML.length > 10);
});

selectContract('sep');
check('9月合约的ESR/PSD说明应提到"预估"或"趋势"(强调不确定性)', elements['esrPsdContractNote'].innerHTML.includes('预估') || elements['esrPsdContractNote'].innerHTML.includes('趋势'));

selectContract('may');
check('5月合约的ESR/PSD说明应提到"南美"', elements['esrPsdContractNote'].innerHTML.includes('南美'));

selectContract('jan');
check('1月合约的ESR/PSD说明应提到"真实"或"确定性"(强调数字更可靠)', elements['esrPsdContractNote'].innerHTML.includes('真实') || elements['esrPsdContractNote'].innerHTML.includes('确定性'));


H.printSummary();
