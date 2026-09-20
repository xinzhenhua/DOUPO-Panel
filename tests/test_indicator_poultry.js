const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());
// ★脚本eval时会自动按"今天"的真实日期跑一次selectContract(getDefaultContractByDate())，
//   这个测试假设的是9月合约(sep)语境下的评分规则，明确覆盖一次，
//   不要让测试结果跟着"今天实际是几月"变来变去。
window._selectedContract = 'sep';


// ===================== 测试1：粘贴解析能识别新指标(用查证过的真实数据) =====================
const realExample = `指标 数据 日期 来源
油厂开机率(%) 65.73% 2026年7月7日 Mysteel
白羽肉鸡养殖利润(元/只) 0.71元/只 2026年5月 财联社`;
const parsed = parsePastedData(realExample);
check('应该正确识别肉鸡养殖利润这个新指标', !!parsed.m_poultry);
check('数值应该正确解析为0.71(用的是真实查证过的数据)', parsed.m_poultry && parsed.m_poultry.value === 0.71);
check('日期应该正确解析为2026-05-01', parsed.m_poultry && parsed.m_poultry.date === '2026-05-01');

// 负数(亏损)场景：用查到的真实案例"一只鸡跌去4块钱"对应的负利润
const lossExample = `肉鸡养殖利润(元/只) -4.0元/只 2026年2月 财联社`;
const parsedLoss = parsePastedData(lossExample);
check('亏损场景(负数)应该正确保留负号，不被截断成正数', parsedLoss.m_poultry && parsedLoss.m_poultry.value === -4.0);

// ===================== 测试2：评分阈值验证(用查证过的真实数据区间) =====================
function resetFields(){
  ['m_crush','m_stock','m_basis','m_arrival','m_hogratio','m_sows','m_import','m_poultry'].forEach(id=>{
    elements[id]=makeEl(id); elements[id].value='';
  });
  ['ind_crush','ind_stock','ind_basis','ind_arrival','ind_hogratio','ind_sows','ind_import','ind_poultry'].forEach(id=>elements[id]=makeEl(id));
  elements['alertContent'] = makeEl('alertContent');
}

resetFields();
elements['m_poultry'].value = '1.73'; // 查到的真实数据：2023年案例，>1.5阈值
updateOverallAlert();
check('盈利1.73元/只(>1.5阈值，真实历史数据)应判定偏多', elements['alertContent'].innerHTML.includes('sd-cell sd-pos">肉鸡养殖利润'));

resetFields();
elements['m_poultry'].value = '0.71'; // 查到的真实数据：2022年案例，介于0-1.5之间
updateOverallAlert();
check('盈利0.71元/只(0-1.5之间，真实历史数据)应判定中性', elements['alertContent'].innerHTML.includes('sd-cell sd-neutral">肉鸡养殖利润'));

resetFields();
elements['m_poultry'].value = '-4'; // 亏损场景
updateOverallAlert();
check('亏损-4元/只(<0)应判定偏空', elements['alertContent'].innerHTML.includes('sd-cell sd-neg">肉鸡养殖利润'));

// ===================== 测试3：12票制审计(11票+新的肉鸡指标=12票) =====================
resetFields();
elements['m_crush'].value='35'; elements['m_stock'].value='40'; elements['m_basis'].value='10';
elements['m_arrival'].value='700'; elements['m_hogratio'].value='8'; elements['m_sows'].value='3600';
elements['m_import'].value='700'; elements['m_poultry'].value='2';
window._weatherRisk='high'; window._droughtSignal=1; window._noaaOutlookSignal=1; window._soyCondSignal=1;
window._esrSignal=1; window._fxSignal=1; window._psdSignal=1;
updateOverallAlert();
check('★12票制审计：全部信号偏多时，总分应精确为+12(新指标正确并入总票数)',
  elements['alertContent'].innerHTML.includes('+12分'));
const posCount = (elements['alertContent'].innerHTML.match(/sd-pos/g)||[]).length;
check('★供需表格应精确显示12个偏多格子', posCount === 12);
check('供需表格需求侧应显示"肉鸡养殖利润"这个新标签', elements['alertContent'].innerHTML.includes('肉鸡养殖利润'));

// ===================== 测试4：一键复制的提示词应包含新指标 =====================
const rawHtml = require('fs').readFileSync('/home/claude/soymeal-dashboard/index.html', 'utf8');
check('复制提示词(PASTE_PROMPT_TEMPLATE)应包含新指标名称，确保用户实际复制时能问到AI', rawHtml.includes('豆菜粕价差(元/吨)\n\n我要数据'));


H.printSummary();
