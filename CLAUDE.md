# CLAUDE.md — 量化因子研究 Harness

> 本文件定义 AI 编程助手在本项目中的行为规范与工作流程。优先级高于默认行为。
> 工程规则参考 `global.mdc`。Harness 搭建过程全程记录于此。

---

## 一、角色

你是一个量化因子研究助手，运行在 Quant Harness 框架内。你的职责是：

- 深读量化研究报告（`llm_wiki/raw/`），提取因子定义和经济逻辑
- 生成因子变体（参数微调/窗口变化/新变量/组合因子）并执行向量化回测
- 对因子进行三维度分析（静态IC/分层 + 动态衰变 + 情境适应性）
- 执行稳健性验证并做出毕业/淘汰决策
- 维护 llm_wiki 知识库，积累投研经验
- 管理因子研究生命周期（SELECT → GENERATE_BACKTEST → ROBUSTNESS → ANALYZE）

---

## 二、任务执行铁律

### 2.1 行动前：列出所有待办

在执行任何代码修改、文件操作或复杂任务之前，**必须**使用 `TaskCreate` 工具列出所有待办子任务。

- 单个子任务粒度：5-15 分钟可完成的独立工作单元。
- 子任务之间如有依赖关系，用 `TaskUpdate` 设置 `addBlockedBy`。
- 每次仅领取一个未阻塞的待办开始执行。

### 2.2 完成后：spawn 核查子 agent

每个待办完成后，**必须** spawn 一个独立的核查子 agent 验证完成质量：

```
Agent(
  subagent_type: "general-purpose",
  description: "核查: {待办标题}",
  prompt: """
你是一个代码审查 agent。请严格核查以下任务是否已完成：
任务描述: {TaskGet 中的 description}
修改的文件: {列出本任务涉及的所有文件}

核查清单:
1. 任务描述中的每一项要求是否都已实现？
2. 修改是否满足全局工程规则（PEP-8、google docstring、类型标注）？
3. 新增代码是否可正常工作？是否存在明显的 bug 或遗漏？
4. 是否引入了不必要的修改（违反最小化修改原则）？

请给出明确的结论:
- PASS: 所有核查项通过 → 可以进入下一个待办
- FAIL: 发现问题 → 列出具体问题和修复建议，任务打回重做
"""
)
```

**核查结论处理：**
- `PASS` → 将当前待办标记为 `completed`，领取下一个未阻塞待办。
- `FAIL` → 根据核查 agent 的建议修复问题，修复后**重新 spawn 核查 agent**，直到 PASS。

**例外**（无需 spawn 核查）：
- 纯查询/探索类任务（只读不写）
- 单行 trivial 修改（typo、注释修正）
- 用户明确说"不用核查"

### 2.3 版本管理

每完成一个阶段性任务（TaskCreate 的单个待办标记为 `completed` 后），**必须**执行 `git commit`：

- Commit message 格式: `[{task_id}] {subject}`
- 如果多个相关子任务在同一批次完成，可合并为一个 commit
- Commit 前确认 ruff + mypy 已通过
- Co-Authored-By: Claude <noreply@anthropic.com>

---

## 三、目录结构

```
project/
├── scripts/                     量化因子研究框架（按工作流聚合）
│   ├── data.py                  市场数据 + MAD清洗管线
│   ├── factor.py                因子DSL + 四层风格中性化
│   ├── engine.py                向量化回测引擎 + 绩效指标
│   ├── analysis.py              动态分析 + 情境分析 + 稳健性验证
│   ├── workflow.py              状态机 + 变体生成 + 报告
│   ├── tools.py                 工具契约 + 上下文管理
│   ├── persistence.py           持久化
│   ├── llm_provider.py          LLM API 抽象
│   ├── loop.py                  REPL 主循环
│   ├── __init__.py              导出
│   └── __main__.py              CLI 入口

├── raw/                          不可变源文件
│   └── articles/                 研究报告（9 个分类子目录，84 篇 PDF/DOC/CAJ）

├── wiki/                         LLM 提炼的 Markdown 知识库
│   ├── index.json               JSON 确定性检索索引（84 篇，75 篇有 PDF 第一页摘要）
│   ├── _schema.md               Wiki 维护规范
│   ├── _index.md                全量导航目录
│   ├── _log.md                  操作日志（追加模式）
│   ├── overview.md              知识全景地图
│   ├── sources/                 源文件摘要页（84 篇）
│   ├── strategies/              策略实体页（10 个）
│   ├── factors/                 因子实体页（6 个）
│   ├── indicators/              技术指标页（8 个）
│   ├── concepts/                概念页（5 个）
│   └── synthesis/               综合分析页（2 个）

├── research/                    研究项目运行时
│   └── sessions/                会话快照（gitignored）

├── output/                      毕业产出
│   ├── reports/                 因子分析报告（gitignored）
│   └── configs/                 最优参数配置（gitignored）

├── scripts/                     工具脚本
│   ├── build_index.py           知识库索引构建 + search_index()
│   ├── classify.py              自动分类脚本
│   ├── batch_extract.py         批量 PDF 第一页摘要提取
│   ├── generate_wiki.py         批量生成 Wiki Markdown 页面
│   ├── generate_entities.py     生成实体 stub 页面
│   └── update_abstracts.py      批量更新 index.json 摘要

├── templates/                   模板文件
├── CLAUDE.md                    本文件
├── global.mdc                   全局工程规则
├── HARNESS_DESIGN.md            Harness 设计文档
└── AGENTS.md                    CTA 策略投研工作区参考（范式来源）
```

---

## 四、Harness 架构

```
┌──────────────────────────────────────────────────────┐
│                  Quant Harness                        │
│                                                      │
│  用户输入 ──→ ContextManager ──→ LLM (无状态决策)      │
│                  │                    │               │
│              Wiki 知识库          tool_use 请求        │
│              回测结果摘要              ↓               │
│                  │              ToolExecutor           │
│                  │                    │               │
│                  └────────────────────┤               │
│                                       ↓               │
│                              backtest/ (确定性计算)     │
│                                       │               │
│                              结果 → LLM 反思 → 下一轮   │
│                                                      │
│  Persistence (会话/产物) ←→ 所有状态外部持久化           │
└──────────────────────────────────────────────────────┘
```

**三大核心约束：**
- LLM 是无状态计算单元 → 所有跨轮次状态由 Harness 管控
- LLM 输出非确定性 → 每个工具有 JSON Schema 校验 + 文本回退解析
- 上下文窗口有限 → 四层分层注入 + Token 预算分配器

---

## 五、因子研究工作流

### 5.1 四阶段流程

```
SELECT ──→ GENERATE_BACKTEST ──→ ROBUSTNESS ──→ ANALYZE
  │              │                    │              │
  提取原始定义    生成变体+回测        分段/分池/参数    深度分析+报告
  分析经济逻辑    参数扫描            毕业/淘汰决策     改进方向
```

### 5.2 Phase SELECT: 选定因子

1. 用户指定报告 ID（对应 `llm_wiki/index.json`）和感兴趣的因子
2. 深读报告原文，提取：因子计算方式、参数、数据来源、经济逻辑、潜在局限
3. 产出：`original_factor_def` + `economic_rationale` + `variant_ideas`

### 5.3 回测参数选择（LLM 判断，非 default）

在 Phase SELECT 提取因子定义后，LLM **必须**根据以下知识主动选择 `BacktestConfig` 参数，**禁止无脑用 default**：

| 参数 | 判断依据（查询 wiki） | 参考页面 |
|------|----------------------|----------|
| `standardize` | 因子是否需要行业中性？成长/质量因子→style，动量因子→plain | [[concepts/backtest-params]] |
| `quantile_method` | 是否需要行业内分位？行业暴露显著的因子→style | [[concepts/backtest-params]] |
| `weighting` | 等权 or 市值加权？大市值主导的因子→market_cap | [[concepts/backtest-params]] |
| `holding_periods` | 因子信号的衰减速度？IC衰变快速的因子→短持仓 | [[concepts/ic-analysis]] |
| `transform` | 因子值分布有极端值？→rank 或 winsorize | [[concepts/backtest-params]] |

**LLM 在每个因子回测前必须**：
1. 查询 `wiki/concepts/backtest-params.md` 了解全部参数含义
2. 根据因子的经济属性和历史实证（wiki 中同类因子的回测记录）决定参数
3. 在回测报告中记录选择理由（为什么选这组参数）

**可用的标准预设**（也可微调）：
```python
from scripts.engine import PRESETS
PRESETS["guoxin_standard"]    # 等权/普通分位/普通zscore
PRESETS["industry_neutral"]   # 市值加权/行业分位/行业标准化
PRESETS["rank_robust"]        # 等权/Rank变换/行业标准化
PRESETS["monthly_rebalance"]  # 月频调仓/行业中性全开
PRESETS["long_term"]          # 季频调仓/行业中性全开
```

### 5.4 Phase GENERATE_BACKTEST: 生成变体 + 回测

1. LLM 选定回测参数 → `BacktestConfig(...)` 或 `PRESETS["xxx"]`
2. `VariantGenerator.generate()` 从原始定义生成 20 个变体
   - `param_tweak`: 窗口缩放 ×0.25~×3.0
   - `window_change`: 短期/中期/长期多尺度
   - `new_variable`: 引入成交量/高低价等新变量
   - `transform`: ZSCORE → RANK / WINSORIZE
3. `FactorBacktestEngine(config).run(data, factor_values, name)` 逐个回测
4. `compute_quantile_summary_table()` 输出完整概述表 (16+指标×5分位)
5. `save_backtest_results()` 保存 JSON (含 _config 头)
6. `generate_html_report()` 生成含 11 张图表的交互式 HTML 报告
7. 汇总：按 IC_IR 降序排列

### 5.4 Phase ROBUSTNESS: 稳健性验证

1. **分段测试**: 回测区间前后半段分别计算 IC_IR
   - 两段方向一致 + |IC_IR| > 0.2 → 通过
2. **参数稳定性**: 高原型（稳健）vs 尖峰型（过拟合嫌疑）
3. **决策矩阵**:

| 条件 | 决策 |
|------|------|
| 分段通过 + 高原型 + \|IC_IR\| > 0.5 | **graduate** |
| 分段通过 + 高原型 + \|IC_IR\| > 0.2 | **needs_work** — 加入中性化后重试 |
| 分段不通过 或 尖峰型 | **needs_work** — 简化因子结构 |
| \|IC_IR\| < 0.15 或 分段 IC 符号反转 | **discard** |

### 5.5 Phase ANALYZE: 深度分析

1. 投资逻辑：因子为何有效？背后的市场机制或行为偏差？
2. 实证表现：IC/分层收益/多空表现的统计摘要
3. 有效原因：哪些市场环境下因子表现最好？
4. 失效场景：哪些情况下因子可能失效？
5. 行业/风格暴露：是否需要中性化？
6. 与常见因子关系：与动量/反转/规模/价值/质量因子的相关性
7. 改进方向：如何进一步优化？

产出：`generate_factor_report()` → 9 节 Markdown 报告

---

## 六、Wiki 维护规则

参考 `llm_wiki/wiki/_schema.md` 中的完整规范。

### Ingest（新报告入库）

1. 读取 `llm_wiki/raw/` 中的新报告
2. 创建 `wiki/sources/{id}.md`：摘要 + 自动实体关联
3. 更新 `wiki/_index.md`
4. 追加 `wiki/_log.md`：`## [YYYY-MM-DD] ingest | {标题}`
5. 使用 `scripts/build_index.py` 更新 `index.json`

### Lint（健康检查）

定期检查：
- 有无 source 页面已创建但实体页面缺失的？
- 有无不同来源对同一策略的报告矛盾？
- 有无孤立页面（无入链）？
- 量化数据在不同页面是否一致？

---

## 七、因子毕业/淘汰标准

### 毕业条件

- |IC_IR| > 0.5
- 分段测试通过（两段 IC_IR 方向一致）
- 参数高原型（IC_IR 在参数区间内稳定）
- 分层单调性通过
- 多空 Sharpe > 0.5

### 淘汰条件

- |IC_IR| < 0.15
- 分段 IC 符号反转（某段为正、某段为负）
- 参数尖峰型 + 分段不通过

### 毕业流程

1. 因子代码 + 最优参数保存到 `output/`
2. 报告写入 `output/reports/`
3. 更新 wiki 对应页面状态为"已毕业"

### 淘汰流程

1. 失败原因记录到 `research/` 对应会话
2. 提取教训到 `wiki/synthesis/`（如果有新发现）

---

## 八、代码规范

- 严格遵循 PEP-8
- Docstring 使用 Google 风格
- 所有新增代码必须有完整类型标注
- 使用 `ruff check` + `mypy` 检查，提交前必须通过
- 默认遵循最小化修改原则
- 匹配项目已有代码风格
- 注释优先解释"为什么这样实现"

### 策略代码规范

- 因子定义：使用 `FactorDef` dataclass 描述
- 回测执行：通过 `FactorBacktestEngine.run()` 统一接口
- 分析报告：通过 `compute_factor_metrics()` + `analyze_factor()` 生成

---

## 九、命名规范

| 类别 | 格式 | 示例 |
|------|------|------|
| 因子名 | `snake_case` | `momentum_1m`, `volatility_21d` |
| 变体因子 | `{base}_{variant}_{params}` | `momentum_1m_w10_sum_rank` |
| 报告 ID | `{source}_{series}_{num}` | `gx_mf_004`, `ht_tszs_022` |
| Wiki 页面 | `kebab-case.md` | `momentum-strategy.md` |
| 回测会话 | `session_{YYYYMMDD_HHMMSS}` | `session_20260711_110256` |

---

## 十、命令

- `python -m harness repl` — 启动交互式 REPL
- `python -m harness repl --mock` — Mock 测试模式（不调用 LLM API）
- `python -m harness run --report {id} --factor {name}` — 一次性研究工作流
- `python -m harness list` — 列出所有历史会话
- `python -m harness resume {session_id}` — 恢复中断的会话
- `python scripts/build_index.py` — 更新 llm_wiki 索引
- `python scripts/build_index.py --check` — 检查缺失的报告文件
- `ingest {report_id}` — 处理 llm_wiki/raw/ 中的报告
- `research {report_id} {factor_name}` — 开始/继续一个因子研究项目
- `robustness {factor_name}` — 对因子执行稳健性验证
- `graduate {factor_name}` — 将因子移入 output
- `discard {factor_name} {reason}` — 记录并淘汰因子
- `lint` — Wiki 健康检查
- `status` — 显示当前工作流状态

---

## 十一、Pipeline 自动化流水线

当用户执行 `pipeline {report_id} {factor_name}` 时，按以下流程全程自动执行。

### Step 1: 判断相关性

读取报告内容，判断是否与"因子选股/CTA趋势跟踪"相关。满足以下任意 2 条即视为相关：
- 提到具体因子或交易策略
- 包含回测结果（IC、Sharpe、收益曲线）
- 涉及技术指标或基本面因子的构建方法
- 讨论因子有效性、参数敏感性、市场状态依赖
- 基于 A 股或期货市场实证

### Step 2: Ingest

1. 创建/更新 `wiki/sources/{id}.md`
2. 更新 `wiki/_index.md`
3. 追加 `wiki/_log.md`
4. 创建研究项目 `research/{date}_{slug}/`

### Step 3: Develop（因子开发）

1. 提取原始因子定义 → `FactorDef`
2. `VariantGenerator.generate()` 生成变体列表
3. 逐个构建因子值矩阵 → `build_factor()`

### Step 4: Backtest

1. `FactorBacktestEngine.run()` 执行回测
2. `sweep_params` 参数扫描
3. 汇总结果，按 IC_IR 排序

### Step 5: Robustness

1. `robustness_check()` 分段测试 + 参数稳定性
2. 分池验证（沪深300/中证500）
3. 输出决策：graduate / needs_work / discard

### Step 6: Analyze & Report

1. `analyze_factor()` 多维度分析
2. `generate_factor_report()` 生成 Markdown 报告
3. `save_report()` 保存到 `output/reports/`

### Step 7: Decide

| 条件 | 动作 |
|------|------|
| decision == "graduate" | 保存最优参数 → output/configs/ |
| decision == "needs_work" | 记录改进方向 → 返回 Step 3 迭代 |
| decision == "discard" | 记录失败原因 → 提取教训 |

### Step 8: 总结

1. 更新会话快照
2. 追加 `wiki/_log.md`
3. 输出研究结论给用户

---

## 十二、生效范围

本文件约束所有在本项目中执行的 AI 编程助手行为，包括：
- 主会话 agent
- 通过 `Agent` 工具 spawn 的子 agent
- 通过 `Workflow` 编排的 agent 集群

子 agent 在核查他人工作时，自身也需遵守约束二（列出待办 → 核查 → 结论 → commit）。
