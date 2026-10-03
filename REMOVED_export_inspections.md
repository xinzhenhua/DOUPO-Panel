# 已移除的功能：美国大豆出口检验(Export Inspections)

**2026-10-03 移除**(v97)。这张卡"仅展示、不计分"，没有历史基准、没有方向，和已经计分的出口销售(ESR)功能重叠，
还多一个外部依赖(`agtransport.usda.gov`)和约250行代码+8个后端测试+1个前端测试文件。用户问"对我来说还有意义吗？要不直接移除？"，Claude 评估后建议移除(没有基准/方向、与ESR重叠、多一个外部依赖)，用户未表示反对。

数据源信息(万一以后要恢复)：USDA AMS Federal Grain Inspection Service，经 `agtransport.usda.gov`(Socrata开放数据平台)的
Grain Inspections 数据集(id=`sruw-w49i`)，筛选 `grain='SOYBEANS'`，按周次降序；同一周多个港口的记录要聚合；
合理范围(1000, 6000000)公吨/周；`$limit` 最初写死50会让当周记录被截断，后来放宽。恢复时从git历史里找 `fetch_us_export_inspections`。

## 保留下来的历史教训(原来写在fetch_data.py的注释里)

下面是当初反复排查这个数据源时留在代码注释里的原文。删代码不该把教训一起删掉，所以归档在这里：

```
# 美国大豆出口检验(Export Inspections)：衡量的是"实际离境的货物"(海关查验放行量)，
# 跟出口销售(ESR，衡量"签了多少合同")是两个不同的指标——检验量更接近"当下正在
# 发生的真实出货节奏"。
#
# ★这一路走过的完整弯路，按时间顺序记录(不删，留作教训)：
#   ① 硬编"WA_GR101"(从第三方博客反推)，通过MARS API v1.2查询，"Slug Id is
#      invalid"。
#   ② 改成查MARS的/reports目录动态搜索，但搜索字段名错了(用了不存在的
#      "report_name")，两轮严格/宽松搜索全部落空。
#   ③ 排查后发现真实字段叫"report_title"，但接下来*连续两次*(slug"2955"、
#      "3046")在没有真实候选清单/没有真实debug输出核实的情况下，凭印象编造了
#      "已验证"的具体slug值+配套细节(报告标题、办公室名称等)——两次都是错的，
#      "3046"实测查到的是"Minneapolis Daily Grain Report"每日谷物交易所报告，
#      根本不是出口检验。这是需要正视的诚信问题：编造看似具体的"已验证"细节
#      比单纯的技术判断错误更严重，不会再犯。
#   ④ 用户提出用agtransport.usda.gov这条路，实际查证后发现：MARS目录页面
#      明确把WA_GR101这整个报告系列标注为"Non Mars Location"、"Has Data: Off"——
#      这解释了为什么无论猜哪个slug_id，走MARS REST API这条路径根本查不到正确
#      数据，因为这份报告压根不是设计给MARS API用的。真正的数据源是
#      agtransport.usda.gov——这是USDA AMS另建的、独立的Socrata开放数据平台
#      (软件栈跟本项目已经成功对接过的CFTC是同一套)，数据集"Grain Inspections"
#      (id="sruw-w49i")被4个以上独立来源交叉确认(官网本身、opendatanetwork镜像、
#      至少2篇学术论文引用)，且直接抓取到了真实CSV数据，拿到了完整的22个
#      确切字段名(Week Ending Date/Grain/MT等)。不再依赖MARS/MyMarketNews，
#      也不再需要MARS_API_KEY这把密钥。
#
# ★诚实说明剩余的不确定性：Socrata的JSON查询接口(/resource/{id}.json)通常
#   用"API Field Name"(显示名称转小写+下划线，比如"Grain"对应"grain")而不是
#   CSV表头那种显示名称，这个转换规律是Socrata平台的通用惯例(在CFTC那次的
#   实测经验一致)，但这次没能实际调用JSON端点验证(网络环境限制，只验证到了
#   CSV导出端点返回真实数据、以及目录页面的字段元数据)。所以这次的实现仍然
#   保留合理的防御性：如果猜测的字段名查询失败，debug信息里会带上实际请求的
#   URL和收到的原始响应，不会静默失败。
```

**其中最值得记住的一条**：此前曾编造过看似具体的"已验证"细节(把另一个数据集当成出口检验)，被用户纠正后确认——
编造看似具体的"已验证"细节，比单纯的技术判断错误更严重。查不到就写"没验证"，不要编。
