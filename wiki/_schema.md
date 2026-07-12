# Wiki Schema — 量化研究知识库维护规范

> **读者**：AI 编程助手（LLM Agent）。
> **作用**：定义 wiki 的结构、命名约定、页面模板、ingest 工作流。
> **维护**：你（LLM）和用户共同演进此文件。

---

## 一、三层架构

```
llm_wiki/
├── raw/                  # Layer 0: 不可变源文件 (PDF, DOC, CAJ)
├── index.json            # Layer 0: JSON 确定性检索索引
├── wiki/                 # Layer 1: LLM 提炼的 Markdown 知识库 ← 你维护这里
│   ├── _schema.md        # 本文件 — 维护规范
│   ├── _index.md         # 导航目录 — 每个页面在此注册
│   ├── _log.md           # 操作日志 — 追加模式，记录每次 ingest/query/lint
│   ├── overview.md       # 知识库全景概述
│   ├── sources/          # 源文件摘要 (每篇 raw 文件对应一页)
│   ├── strategies/       # 策略实体 (动量、反转、多因子、行业轮动…)
│   ├── factors/          # 因子实体 (规模、价值、动量、质量、波动…)
│   ├── concepts/         # 概念 (IC 分析、分层回测、过拟合…)
│   ├── indicators/       # 技术指标 (KDJ, ADX, MACD, CCI…)
│   └── synthesis/        # 综合分析 (跨策略对比、市场状态分类…)
└── scripts/              # 工具脚本
```

## 二、页面模板

### 2.1 源文件摘要页 (`sources/{report_id}.md`)

```markdown
---
id: ht_tszs_001
source: 海通证券
date: 2012-08-30
type: source
category: 他山之石系列
status: ingested
ingested_at: 2026-07-11
tags: [海外经验, 量化选股]
---

# {报告标题}

- **来源**: {券商/作者}
- **日期**: {YYYY-MM-DD}
- **原始文件**: `raw/{分类}/{文件名}`
- **关键词**: tag1, tag2, tag3

## 核心内容

{3-5 句话概括报告的核心观点和方法}

## 关键发现

- 发现 1: {一句话}
- 发现 2: {一句话}

## 涉及的策略 / 因子 / 指标

- [[strategies/xxx]] — {关系描述}
- [[factors/xxx]] — {关系描述}
- [[indicators/xxx]] — {关系描述}

## 数据与回测

- **标的**: {股票池/期货品种}
- **周期**: {YYYY-MM 至 YYYY-MM}
- **频率**: {日频/周频/月频/分钟}
- **关键参数**: {如果涉及参数}

## 局限性

- {一句话描述研究局限或适用范围}

## 相关来源

- [[sources/xxx]] — {相关点}
```

### 2.2 策略实体页 (`strategies/{strategy-name}.md`)

```markdown
---
id: strat_001
type: strategy
name: 动量策略
aliases: [Momentum, 动量效应]
status: stub | growing | mature
---

# {策略名称}

## 定义

{一句话定义}

## 理论基础

{行为金融学/市场微观结构/风险溢价 等解释}

## 变体

- **横截面动量**: {描述}
- **时间序列动量**: {描述}
- **残差动量**: {描述}

## A 股实证

| 来源 | 标的 | 周期 | 年化收益 | Sharpe | 最大回撤 |
|------|------|------|----------|--------|----------|
| [[sources/xxx]] | ... | ... | ... | ... | ... |

## 关键参数

- 回溯期: {N 周/月}
- 持有期: {N 周/月}
- 常见问题: {参数敏感 / 过拟合风险 / 等等}

## 相关

- [[factors/momentum-factor]] — 动量因子构建
- [[concepts/reversal-effect]] — 反转效应（反面）
- [[strategies/reversal-strategy]] — 反转策略
```

### 2.3 因子实体页 (`factors/{factor-name}.md`)

```markdown
---
id: factor_001
type: factor
name: 规模因子
aliases: [Size, SMB, 市值因子]
category: 市场因子 | 价值因子 | 成长因子 | 质量因子 | 动量因子 | 波动因子 | 技术因子
status: stub | growing | mature
---

# {因子名称}

## 定义与计算

{公式或文字描述}

## 理论解释

{为什么这个因子有效？风险溢价还是行为偏差？}

## A 股实证汇总

| 来源 | IC 均值 | IC_IR | 分层收益差 | 周期 |
|------|---------|-------|------------|------|
| [[sources/xxx]] | ... | ... | ... | ... |

## 因子表现特征

- **市场状态依赖**: {趋势市有效/震荡市失效/...}
- **行业差异**: {在某些行业更有效}
- **参数稳定性**: {高原型/尖峰型}

## 常见组合

- 常与 [[factors/xxx]] 搭配
- 参见 [[strategies/xxx]]

## 相关

- [[concepts/ic-analysis]]
- [[concepts/factor-decay]]
```

### 2.4 技术指标页 (`indicators/{indicator-name}.md`)

```markdown
---
id: ind_001
type: indicator
name: KDJ
aliases: [随机指标]
category: 动量 | 趋势 | 波动 | 成交量
---

# {指标名称}

## 公式

{K 线 / D 线 / J 线 的计算公式}

## 信号规则

- **买入**: {条件}
- **卖出**: {条件}

## A 股回测表现

| 来源 | 标的 | 年化收益 | 胜率 | 最大回撤 |
|------|------|----------|------|----------|
| [[sources/xxx]] | ... | ... | ... | ... |

## 优化变体

- [[sources/xxx]] 中提出的改进: {描述}

## 相关

- [[indicators/xxx]]
- [[strategies/xxx]]
```

### 2.5 概念页 (`concepts/{concept-name}.md`)

```markdown
---
id: concept_001
type: concept
name: IC 分析
aliases: [Information Coefficient, 信息系数]
---

# {概念名称}

## 定义

{一句话 + 公式 if applicable}

## 为什么重要

{1-2 句话}

## 在量化选股中的应用

{如何使用}

## 常见陷阱

- {陷阱 1}
- {陷阱 2}

## 引用来源

- [[sources/xxx]] — {原文中的用法}
```

### 2.6 综合分析页 (`synthesis/{topic}.md`)

```markdown
---
id: synth_001
type: synthesis
topic: 动量 vs 反转
status: evolving
---

# {主题}

## 核心问题

{一句话描述要回答的问题}

## 证据汇总

### 支持方

| 来源 | 核心证据 |
|------|----------|
| [[sources/xxx]] | ... |

### 反对方

| 来源 | 核心证据 |
|------|----------|
| [[sources/xxx]] | ... |

## 当前判断

{基于现有证据的 tentative conclusion}

## 待解决

- [ ] {需要更多证据的问题}
```

## 三、Ingest 工作流

当你被要求 ingest 一个源文件时，按以下步骤执行：

### Step 1: 读取源文件

```
Read llm_wiki/raw/{category}/{filename}
```

如果文件是 PDF，使用 Read 工具读取。如果是 DOC 或 CAJ 格式无法直接读取，告知用户并跳过。

### Step 2: 提取知识

从源文件中提取：
- 核心观点和方法论
- 具体策略/因子/指标的参数和表现
- 可量化的回测结果（年化收益、Sharpe、最大回撤、胜率、IC 等）
- 与其他研究的一致或矛盾之处

### Step 3: 写入 wiki 页面

- **必须**创建 `sources/{report_id}.md` 源文件摘要页
- **如果**涉及新的策略/因子/指标/概念 → 创建对应的实体页（状态设为 `stub`）
- **如果**涉及已有实体 → 更新对应页面，添加新来源的实证数据
- **如果**发现与已有知识矛盾 → 在实体页中标注，在 `synthesis/` 创建或更新对比分析

### Step 4: 更新索引和日志

- 在 `_index.md` 中注册新页面
- 在 `_log.md` 中追加操作记录
- 如果提取了新的可量化数据，考虑更新 `index.json` 中该报告的 abstract

## 四、Query 工作流

当用户提问时：

1. 先读 `_index.md` 定位相关页面
2. 再读具体页面
3. 如果 wiki 信息不足，回溯到 `raw/` 中的原始文件
4. 好的回答可以写入 `synthesis/` 作为新页面

## 五、Lint 工作流

定期（或用户触发）检查：

- [ ] 有无 source 页面已创建但实体页面缺失的？（stub → growing）
- [ ] 有无不同来源对同一策略的报告矛盾？
- [ ] 有无重要概念被多处引用但缺少独立页面的？
- [ ] 有无孤立页面（无入链）？
- [ ] 实体页面的实证表格是否遗漏了已知来源？
- [ ] 量化数据（收益率、Sharpe 等）在不同页面是否一致？

## 六、命名约定

| 类型 | 文件名 | 示例 |
|------|--------|------|
| 源文件摘要 | `{report_id}.md` | `ht_tszs_001.md` |
| 策略实体 | `{english-slug}.md` | `momentum-strategy.md` |
| 因子实体 | `{english-slug}.md` | `size-factor.md` |
| 技术指标 | `{english-slug}.md` | `kdj-indicator.md` |
| 概念 | `{english-slug}.md` | `ic-analysis.md` |
| 综合分析 | `{topic-slug}.md` | `momentum-vs-reversal.md` |

## 七、页面状态生命周期

```
stub → growing → mature
  │        │         │
  └────────┴─────────┴──→ superseded (被新研究取代)
```

- **stub**: 只有基本定义，缺少 A 股实证数据
- **growing**: 有 1-2 个来源的实证数据，结构完整
- **mature**: 有 3+ 来源的实证数据，跨市场/跨周期验证

## 八、Wikilink 语法

页面间引用使用 Obsidian 兼容的 `[[path/to/page]]` 语法：

```
[[sources/ht_tszs_001]]     → 引用源文件摘要
[[strategies/momentum]]     → 引用策略实体
[[factors/size-factor]]     → 引用因子实体
[[indicators/kdj]]          → 引用技术指标
[[concepts/ic-analysis]]    → 引用概念
```

## 九、与其他层的关系

- **raw/** 和 **index.json** 是只读输入。你读取它们，但从不修改 raw/ 中的文件。
- **wiki/** 是你（LLM）的领域。你创建、更新、维护所有 markdown 文件。
- **CLAUDE.md** 或项目根目录的全局规则可能包含额外约束，优先遵守。
