const H = require('./test_helpers');
const { makeEl, elements } = H;
H.setClipboardMock((text) => { global._copiedText = text; return Promise.resolve(); });

eval(H.loadDashboardJs());


let pass=0, fail=0;
function check(desc, cond, extra){ if(cond){pass++;console.log('✅',desc);} else {fail++;console.log('❌',desc, extra!==undefined?('  实际值: '+JSON.stringify(extra)):'');} }

// ===================== 用户提供的真实完整示例 =====================
const realExample = `指标 数据 日期 来源
油厂开机率(%) 65.73%（全国动态全样本油厂） 2026年7月7日 Mysteel
豆粕商业库存(万吨) 68万吨（全国主要油厂） 2026年7月3日 国家粮油信息中心
现货基差(元/吨，正=现货贵) -182元/吨（豆粕主力M2609合约基差） 2026年7月9日 文华财经
本月到港预报(万吨) 约1100万吨（7月预估） 2026年7月 Mysteel农产品团队
猪粮比 3.88:1 截至2026年7月3日 中财网
能繁母猪存栏(万头) 4043万头 2026年6月末 国家统计局
上月中国大豆月度进口量(万吨) 约1073.80万吨（6月全样本油厂到港预估） 2026年6月 Mysteel农产品团队`;

const parsed = parsePastedData(realExample);
console.log('解析结果:', JSON.stringify(parsed, null, 2));
console.log('');

check('开机率解析正确(65.73)', parsed.m_crush && parsed.m_crush.value === 65.73, parsed.m_crush);
check('开机率日期正确(2026-07-07)', parsed.m_crush && parsed.m_crush.date === '2026-07-07', parsed.m_crush);
check('开机率来源正确(Mysteel)', parsed.m_crush && parsed.m_crush.source === 'Mysteel', parsed.m_crush);

check('商业库存解析正确(68)', parsed.m_stock && parsed.m_stock.value === 68, parsed.m_stock);
check('商业库存来源正确(国家粮油信息中心)', parsed.m_stock && parsed.m_stock.source === '国家粮油信息中心', parsed.m_stock);

check('现货基差解析正确且保留负号(-182)', parsed.m_basis && parsed.m_basis.value === -182, parsed.m_basis);
check('现货基差日期正确(2026-07-09)', parsed.m_basis && parsed.m_basis.date === '2026-07-09', parsed.m_basis);

check('到港预报解析正确，且没被"约"和括号内的"7月"干扰(1100)', parsed.m_arrival && parsed.m_arrival.value === 1100, parsed.m_arrival);
check('到港预报来源正确识别更具体的"Mysteel农产品团队"而非仅"Mysteel"', parsed.m_arrival && parsed.m_arrival.source === 'Mysteel农产品团队', parsed.m_arrival);

check('猪粮比正确识别"X:1"比值格式(3.88)', parsed.m_hogratio && parsed.m_hogratio.value === 3.88, parsed.m_hogratio);

check('能繁母猪解析正确(4043)', parsed.m_sows && parsed.m_sows.value === 4043, parsed.m_sows);
check('能繁母猪"月末"日期正确转换为该月最后一天(2026-06-30)', parsed.m_sows && parsed.m_sows.date === '2026-06-30', parsed.m_sows);

check('进口量解析正确，保留小数点(1073.8)', parsed.m_import && parsed.m_import.value === 1073.8, parsed.m_import);
check('进口量没有被括号内"6月"干扰日期识别(2026-06-01)', parsed.m_import && parsed.m_import.date === '2026-06-01', parsed.m_import);

check('表头行"指标 数据 日期 来源"被正确跳过，没有产生多余字段', Object.keys(parsed).length === 7, Object.keys(parsed));

// ===================== 测试复制提示词功能 =====================
elements['copyPromptResult'] = makeEl('copyPromptResult');
copyPromptToClipboard();
setTimeout(()=>{
  check('复制提示词功能：确实调用了clipboard.writeText', global._copiedText && global._copiedText.includes('油厂开机率'));
  check('复制的提示词包含全部7个指标名称', global._copiedText &&
    ['油厂开机率','豆粕商业库存','现货基差','本月到港预报','猪粮比','能繁母猪存栏','大豆月度进口量'].every(k=>global._copiedText.includes(k)));
  check('复制成功后应显示提示文字', elements['copyPromptResult'].textContent.includes('已复制'));

  console.log('');
  console.log(`结果：${pass}项通过，${fail}项失败`);
  if(fail>0) process.exit(1);
}, 100);
