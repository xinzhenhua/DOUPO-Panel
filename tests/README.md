# 前端测试套件

这里是豆粕仪表盘(`../index.html`)的前端JS逻辑测试，用纯Node.js写的，不需要`npm install`任何东西。

## 怎么跑

```bash
cd tests
./run_all_tests.sh
```

如果提示"Permission denied"（有些系统解压zip后会丢失可执行权限），改用：

```bash
bash run_all_tests.sh
```

会自动跑完全部21个测试文件，汇总显示总共通过了多少项测试。

如果只想跑某一个文件（比如只关心5月合约相关的逻辑）：

```bash
node test_planting_brl.js
```

## 测试文件说明

| 文件 | 测试内容 |
|---|---|
| `test_weather_drought_1/2/3.js` | 天气/干旱监测/PSD渲染，综合评分基础逻辑 |
| `test_paste_parse.js` | "复制提示词→粘贴解析"这套机制，8个手动指标的识别 |
| `test_noaa_outlook.js` | NOAA月度干旱展望的解析和渲染 |
| `test_tiered_display.js` | 12州分层显示、供需表格、PSD/CBOT的alert-box |
| `test_weighted_avg.js` | 按种植面积加权平均(区别于简单平均) |
| `test_charts_1.js` / `test_charts_2_integration.js` | SVG图表(条形图/仪表盘/供需表格)的生成逻辑 |
| `test_timing_bugfix.js` | loadWeather/loadFxRate异步完成后正确触发重新计算 |
| `test_scoring_audit.js` | 严格审计：14/N个信号全部设为偏多时，总分必须精确匹配，不多不少 |
| `test_indicator_poultry.js` | 白羽肉鸡养殖利润指标 |
| `test_indicator_rmspread.js` | 豆菜粕价差指标 |
| `test_contract_switching.js` / `test_contract_scoring.js` | 9/5/1月合约切换、板块显示隐藏、综合评分随合约变化 |
| `test_esr_psd_visibility.js` | 出口销售/PSD在3个合约下都应保持可见 |
| `test_south_america_composite.js` | 南美天气+产量信号合成逻辑 |
| `test_time_aware_weights.js` | 时间感知加权（6-7月/8月起两档；南美三阶段） |
| `test_trading_window.js` | 3个合约的建议/谨慎/避开交易月份判断 |
| `test_planting_brl.js` | 美豆播种进度+巴西雷亚尔汇率(5月合约专属) |
| `test_jan_contract_fix.js` | 美豆收获进度+南美数据开放给1月合约(1月合约专属) |

## 技术说明

- `test_helpers.js` 是所有测试文件共用的浏览器环境模拟（`document`/`window`/`localStorage`/
  `fetch`/`navigator`），以及断言工具`check()`。每个测试文件开头都是：
  ```js
  const H = require('./test_helpers');
  const { makeEl, elements, check } = H;
  eval(H.loadDashboardJs());  // 从 ../index.html 里提取<script>内容并执行
  ```
- **⚠️重要坑点**：Node.js v21+内置了只读的`navigator`全局对象，直接`global.navigator = {...}`
  赋值会被静默忽略（不报错，但也不生效）。`test_helpers.js`里用`Object.defineProperty`
  正确处理了这个问题，如果需要自定义`navigator.clipboard`行为，用`H.setClipboardMock(fn)`。
- 部分测试需要模拟"当前月份"（验证时间感知加权/交易窗口逻辑），用`H.setMockedMonth(7)`
  设置，`H.clearMockedMonth()`还原。
- 每次修改`../index.html`后，直接重新运行`./run_all_tests.sh`即可验证有没有破坏现有功能——
  测试会自动读取最新的`index.html`内容，不需要额外的构建/编译步骤。
