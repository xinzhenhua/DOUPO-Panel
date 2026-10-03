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

会自动跑完全部测试文件(v96时为64个)，汇总显示总共通过了多少项测试。

如果只想跑某一个文件（比如只关心5月合约相关的逻辑）：

```bash
node test_planting_brl.js
```

## 测试文件说明

| 文件 | 测试内容 |
|---|---|
| `test_weather_drought_1/2/3.js` | 天气/干旱监测/PSD渲染，综合评分基础逻辑 |
| `test_auto_indicator_cards.js` | v79新增：10个指标卡片的生成、自动覆盖、失败保留、过期不计分、手动修正与存储 |
| `test_snapshot.js` | v95新增：无头快照脚本(jsdom，没装会跳过；本地运行需NODE_PATH指向含jsdom的node_modules) |
| `test_volume_price.js` | v93新增：量价关系(242根真实K线逐日对拍、三道门槛、象限、死区、进评分/市场结构维度、合约切换、健康度) |
| `test_systems.js` | v93新增：基本面(仅供需)与市场结构两个独立系统、背离描述、共振面板 |
| `test_term_spread.js` | v92新增：月差/期限结构(分位信号、正负本身不是信号、合约切换路径、进评分、市场结构维度2项、健康度) |
| `test_feed_days.js` | v91新增：饲料企业豆粕库存天数(用真实20期：卡片/环比同比/趋势/分位规则/长假备货窗口降权/进评分/健康度) |
| `test_health.js` | v89新增：数据健康度面板(指标状态、实时信号按合约、缺席投票、同步是否还活着、整体等级、渲染) |
| `test_freshness.js` | v88新增：按应更新时点的新鲜度(交易日/周频/月频，扣除休市，含国庆案例)、来源可靠性、质量乘数、置信度扣分、ESR新鲜度 |
| `test_robust.js` | v87新增：相关性分组、三套权重(等权/分组等权/现行)的方向一致性、置信度降级、界面与共振面板 |
| `test_events.js` | v86新增：美东↔北京时间换算(含夏令时)、大商所交易日/夜盘/开市判断、休市状态、事件列表与渲染、三方共振接入基本面置信度 |
| `test_seasonal.js` | v85新增：作物票季节档位(主导/参与/背景)、天气开关(极端偏多才开，背景档不开，偏空不开)、国庆轻度扰动(降权不暂停) |
| `test_festival.js` | v84新增：春节扰动月不判方向/不投票、票权规则(库消比参与才×2)、同类月份分位、样本不连续的展示 |
| `test_history_display.js` | v82新增：历史分位展示(积累中/分位/同月分位)、与绝对阈值的一致性提示、PSD/ESR详情接入 |
| `test_dimensions.js` | v81新增：三维度拆分/分歧/置信度(含变异检查过的门槛)、拆分与总分的不变式、界面条形与提示 |
| `test_meal_stu.js` | v80新增：国内豆粕库消比卡片、组内权重50/30/20、国内组双倍票权、ESR中国/未知拆分展示 |
| `test_scoring_v2.js` | v79新增：净倾向归一化、数据不足、合并投票、出口销售信号 |
| `test_noaa_outlook.js` | NOAA月度干旱展望的解析和渲染 |
| `test_tiered_display.js` | 12州分层显示、供需表格、PSD/CBOT的alert-box |
| `test_weighted_avg.js` | 按种植面积加权平均(区别于简单平均) |
| `test_charts_1.js` / `test_charts_2_integration.js` | SVG图表(条形图/仪表盘/供需表格)的生成逻辑 |
| `test_timing_bugfix.js` | loadWeather/loadFxRate异步完成后正确触发重新计算 |
| `test_scoring_audit.js` | 严格审计：全部信号偏多时，票数必须精确匹配(合并后为9票) |
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


## Python侧测试(在项目根目录运行)
- `python3 test_fetch_data.py`：后端抓取/解析(部分测试依赖agrobr/akshare，缺少时会在那一项报错)
- `python3 test_history.py`：v82新增(v83扩充)，历史序列存取/合并/分位/日常累积/四项回填/校准摘要/周度库存校验点(用临时目录，不会写进仓库的data/history)

- `python3 test_feed_days.py`：v91新增，饲料企业豆粕库存天数后端(用真实20期逐期核对解析器、完整抓取流程、节假日窗口、历史累积与分位)
- `python3 test_term_spread.py`：v92新增，月差后端(合约代码推导/百分比口径/抓取/历史累积/回填窗口与取不到的合约对/校准摘要)

- 真实数据夹具：`tests/data/m2609_daily_with_expected.json`(用户仓库里M2609的242根日K线 + 独立Python参考实现算出的逐日期望值)
- `python3 test_record_systems.py`：v95新增，每天记录两个系统的方向(合并策略/分析/工作流配置)
- `python3 test_url_safety.py`：v95.1新增，来自外部响应的URL必须过Mysteel域名白名单(含库消比/饲料库存天数/回填三条路径的端到端)
- `python3 test_window_and_deps.py`：v95.2新增，榨利/月差每日累积只记窗口内、一次性清理、依赖锁定文件与工作流(回填必须先装akshare)
- `python3 test_feed_days_old_wording.py`：v95.2新增，饲料库存天数2021-22年旧措辞(4篇真实原文)与变动量防护

- v96：`run_all_tests.sh`会在汇总里**点名被跳过的测试文件**(没装jsdom时`test_snapshot.js`会被跳过)，跳过的测试里可能有评分规则版本号这类关键检查；本地运行需要`NODE_PATH=<含jsdom的node_modules> ./run_all_tests.sh`
- `python3 test_series_quality.py`：v96.1新增，序列质量声明(周度库存口径断点2024-01-05、meal_stu 2025-04可疑点)
- `python3 test_sample_job.py`：v96.2新增，采样诊断(措辞聚类/口径字样/报告大小预算/容错)
- `python3 test_mysteel_parsers.py` / `python3 test_backfill_mysteel.py`：v96.3新增，Mysteel解析器与进口量/到港预报回填(用真实采样夹具 tests/data/mysteel_samples_20261002.json)
- `python3 test_crush_festival.py` / `tests/test_crush_festival.js`：v97新增，开机率春节扰动期
- v97：移除`test_export_inspections_display.js`及`test_fetch_data.py`里8个出口检验测试；顶部拆开后`test_systems.js`的命名守卫改写为v97(基本面预警+市场结构卡)
- `tests/test_crush_rule.js` / `test_crush_rate_rule.py`：v98新增，开机率滚动分位规则与回填
- `python3 test_sync_watchdog.py`：v98新增，数据同步看门狗(与页面口径对拍；用`NODE_PATH=<含jsdom的node_modules>`跑才包含对拍)
- `python3 test_calibrate_margin_spread.py`：v98新增，榨利/月差校准诊断
- `tests/test_decision_card.js`、`tests/test_rmspread_caliber.js`：v99新增(决策卡、豆菜粕价差新口径)；`tests/test_crush_rule.js`、`test_crush_rate_rule.py`扩展了往年同月三档
- v99移除：`test_sample_job.py`；`test_history.py`里3个meal_stock回填测试；`test_url_safety.py`改为逐个调用点检查白名单
- `python3 test_market_capital.py`、`tests/test_market_capital_card.js`：v100新增，资金面(龙虎榜+CFTC)主力合约/席位净持仓/状态/市场结构里的资金持仓小节/决策卡最上边的当前市场状态
- v100：`test_fetch_data.py`的外资识别测试增加54个真实会员名；**变异检查跑`test_fetch_data`时成功标志是`🎉 全部`而不是`结果：`，并且必须带一个'不改动'的对照组**
- `python3 test_capital_history.py`：v101新增，龙虎榜/CFTC历史累积(序列、同合约连续N日、缺交易日、CFTC 156周回填与自检)；`tests/test_market_capital_card.js`扩展了历史趋势列
