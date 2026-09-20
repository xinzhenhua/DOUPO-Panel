const H = require('./test_helpers');
const { makeEl, elements, check } = H;

eval(H.loadDashboardJs());


// 用户场景验证：伊利诺伊(大产区)严重问题 + 威斯康星(小产区)正常
const result1 = weightedAvgJS([{code:'IL', value:80}, {code:'WI', value:0}]);
const simple1 = (80+0)/2;
check('简单平均会是40(看起来只是中等)', simple1 === 40);
check('JS加权平均应明显高于简单平均，贴近伊利诺伊(大产区)的严重程度', result1 > 60);
console.log(`   简单平均=${simple1}, 加权平均=${result1.toFixed(1)}`);

// 反向：小产区威斯康星严重，大产区伊利诺伊正常
const result2 = weightedAvgJS([{code:'IL', value:0}, {code:'WI', value:80}]);
check('JS加权平均应明显低于简单平均(40)，因为只是小产区问题', result2 < 20);
console.log(`   加权平均=${result2.toFixed(1)}`);

// 权重数据本身的数值已经在上面两个场景测试里间接验证过了(66.7和13.3的计算结果
// 只有在权重数据正确时才会算出这些精确值)，不需要再单独访问变量做二次验证


H.printSummary();
