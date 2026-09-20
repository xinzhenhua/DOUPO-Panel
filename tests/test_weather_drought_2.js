const H = require('./test_helpers');
const { makeEl, elements } = H;

eval(H.loadDashboardJs());


let pass=0, fail=0;
function check(desc, cond){
  if(cond){ pass++; console.log('✅', desc); }
  else{ fail++; console.log('❌', desc); }
}

// 测试1：干旱模块，模拟真实报告的场景——三州全部fetch失败，debug里带HTTP错误详情
elements['droughtBadge'] = makeEl('droughtBadge');
elements['droughtContent'] = makeEl('droughtContent');
renderDrought({
  available: false,
  reason: "USDM接口未返回任何州的数据",
  debug: {
    IA: {url:'https://usdmdataservices.unl.edu/api/...aoi=IA...', httpStatus:404, error:'HTTP 404: Not Found', rawSnippet:'<html>Page not found</html>'},
    IL: {url:'https://usdmdataservices.unl.edu/api/...aoi=IL...', httpStatus:404, error:'HTTP 404: Not Found', rawSnippet:'<html>Page not found</html>'},
    MN: {url:'https://usdmdataservices.unl.edu/api/...aoi=MN...', httpStatus:404, error:'HTTP 404: Not Found', rawSnippet:'<html>Page not found</html>'},
  }
}, null);
check('干旱：三州失败时，界面应显示诊断信息区块', elements['droughtContent'].innerHTML.includes('诊断信息'));
check('干旱：诊断信息里应包含实际HTTP状态码404', elements['droughtContent'].innerHTML.includes('404'));
check('干旱：诊断信息里应包含IA/IL/MN三州各自的错误', 
  elements['droughtContent'].innerHTML.includes('IA') && elements['droughtContent'].innerHTML.includes('IL') && elements['droughtContent'].innerHTML.includes('MN'));

// 测试2：PSD模块，模拟真实报告的场景——已同步但字段值undefined
elements['psdBadge'] = makeEl('psdBadge');
elements['psdContent'] = makeEl('psdContent');
renderPsd({
  available: true,
  marketYear: 2026,
  endingStocks: null,
  production: null,
  domesticConsumption: null,
  debug: {
    warning: "已连接上接口并拿到数据，但字段名一个都没匹配上",
    actualAttributeNamesSeen: ["Beginning Stocks", "Imports", "Exports"],  // 假设真实字段名跟预期不同
    sampleRawRow: {attributeName: "Beginning Stocks", value: 123}
  }
}, new Date().toISOString());
check('PSD：字段全undefined时，badge应仍显示"已同步"（因为接口确实连上了）', elements['psdBadge'].textContent.includes('已同步'));
check('PSD：应显示"字段名没匹配上"的明确警告，而不是让人误以为是网页bug', elements['psdContent'].innerHTML.includes('字段名没匹配上'));
check('PSD：应显示实际收到的字段名列表，方便直接看出真实名称', elements['psdContent'].innerHTML.includes('Beginning Stocks'));
check('PSD：数值应显示为"--"占位符而不是"undefined"字样', !elements['psdContent'].innerHTML.includes('undefined'));

// 测试3：正常情况（无debug）不应该出现诊断信息区块，避免正常用户被无关信息打扰
elements['psdContent'] = makeEl('psdContent');
renderPsd({available:true, marketYear:2026, endingStocks:400, production:52000, domesticConsumption:34000}, new Date().toISOString());
check('PSD：数据正常时不应显示诊断信息区块', !elements['psdContent'].innerHTML.includes('诊断信息'));


console.log('');
console.log(`结果：${pass}项通过，${fail}项失败`);
if(fail>0) process.exit(1);
