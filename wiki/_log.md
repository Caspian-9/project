# Wiki 操作日志

> 追加模式。记录每次 ingest、query、lint 操作。
> 格式: `## [YYYY-MM-DD] {operation} | {brief description}`

---

## [2026-07-11] setup | Wiki 初始化

- 创建 wiki/ 目录结构和 _schema.md
- 初始化 _index.md 导航页
- raw/ 中有 84 篇研究报告待 ingest
- 已生成 index.json (JSON 检索索引)

## [2026-07-11] batch-ingest | 批量生成源文件摘要页

- 从 index.json 批量生成 75 篇 sources/ 页面
- 每页包含 PDF 第一页提取的摘要 + 关键词推测的实体关联
- 更新 _index.md 全量导航目录
- 9 篇 DOC/CAJ 待手动处理后 ingest

## [2026-07-11] generate-entities | 生成实体页面

- 10 个策略实体 (3 growing, 7 stub) — 含定义 + 相关来源链接
- 6 个因子实体 (4 growing, 2 stub) — 含A股实证来源表
- 8 个技术指标 (6 growing, 2 stub) — 含关键绩效数据
- 5 个概念 (4 growing, 1 stub) — 含定义 + 引用来源
- 2 个综合分析 (evolving) — 动量vs反转 + 技术指标横向对比
- 所有实体均从 75 篇源文件摘要中自动提取相关内容

## [2026-07-12] ingest | 南科大量化课程4：多因子Quant Lab（截面多因子课件及脚本）

- 新增源文件摘要: [[sources/sz_mf_001]]
- 该源包含 1 份课件PDF + 8 个Jupyter Notebook + 2 个Python模型实现
- 覆盖4种ML选股模型：Lasso、LightGBM、LSTM、DoubleEnsemble
- 涉及 CSI300 和 CSI1000 两个指数成分股
- 更新 [[strategies/multi-factor-strategy]]: 新增 ML 增强多因子选股的回测对比表
- 更新 [[concepts/overfitting]]: 新增早停、正则化、Optuna超参数优化等防控手段
- 更新 [[concepts/factor-testing]]: 新增现代因子测试工具链（Alphalens + vnpy.alpha）
- 本次 ingest 是 wiki 首个含可执行代码的源文件，标志着知识库从纯研究报告向代码+报告融合演进

## [2026-07-12] backtest-batch | 30因子CSI300批量回测

- 数据: CSI300 859只股票, 3465个交易日 (2010-07-23 ~ 2024-10-30)
- 因子: 动量9 + 波动9 + 成交量6 + 趋势4 + 反转2 = 30个
- Top 5: volume_ratio_3m(IC_IR=-0.275), volume_ratio_1m(-0.268), short_reversal(-0.209), volume_volatility(-0.157), price_ma_ratio_1m(-0.150)
- 全部因子 IC_IR 偏弱（|IC_IR| < 0.3），符合A股市场效率较低的学术共识
- 成交量类因子整体表现优于价格类，volume_ratio_3m 最强（低成交量→未来收益高）
- 全部因子页面已更新至 wiki/factors/（30个growing页面含CSI300实证数据）
