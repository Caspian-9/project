# Quant Harness 构建手册

> **目标**：在现有向量化回测框架之上，搭建一个包裹 LLM 的量化研究 REPL 闭环容器。
> **读者**：AI 编程助手（具备另一个 LLM 也能照此执行的完整度）。
> **前置**：已有一个可独立运行的回测模块（`backtest/`），含 data → strategy → engine → metrics 四层。

---

## 目录

1. [核心概念](#1-核心概念)
2. [目录结构](#2-目录结构)
3. [Phase 1：工具契约化](#3-phase-1工具契约化)
4. [Phase 2：REPL 循环 + 状态管理](#4-phase-2repl-循环--状态管理)
5. [Phase 3：上下文预算 + 分层注入](#5-phase-3上下文预算--分层注入)
6. [Phase 4：度量 + 知识进化闭环](#6-phase-4度量--知识进化闭环)
7. [调用方式](#7-调用方式)
8. [关键设计决策与理由](#8-关键设计决策与理由)

---

## 1. 核心概念

### 1.1 Harness 是什么

Harness 不是回测引擎。回测引擎是**确定性计算模块**（输入 data + strategy → 输出 BacktestResult）。Harness 是**包裹在 LLM 外面的一层**：

```
┌──────────────────────────────────────────────┐
│              Quant Harness                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Context  │ │  REPL    │ │ Tool Executor│  │
│  │ Manager  │ │  Loop    │ │ (Schema+降级) │  │
│  └──────────┘ └──────────┘ └──────┬───────┘  │
│                                   │           │
│  ┌────────────────────────────────┘           │
│  │    已有的 backtest/ 模块 (不动)             │
│  │  ┌──────┐ ┌───────────┐ ┌─────────┐       │
│  │  │data  │ │ strategies│ │ engine  │       │
│  │  └──────┘ └───────────┘ └─────────┘       │
│  │  ┌──────┐                                │
│  │  │metrics│                               │
│  │  └──────┘                                │
│  └──────────────────────────────────────────┘
│                                   │           │
│  ┌────────────────────────────────┘           │
│  │ SessionState (外部持久化)                   │
│  │ HarnessMetrics (度量采集)                   │
│  └────────────────────────────────────────────┘
└──────────────────────────────────────────────┘
```

### 1.2 三大核心约束（设计前提）

| 约束 | 含义 | Harness 应对策略 |
|---|---|---|
| LLM 非确定性 | 每次输出不同，可能格式错误 | 双重解析器（JSON → 文本回退），重试机制 |
| 有限上下文窗口 | LLM 能"看到"的 token 有上限 | 分层上下文注入，Token 预算分配器 |
| 外部世界无限状态 | 49 万行行情数据，数百次回测结果 | 状态外部持久化，按需摘要注入 |

### 1.3 铁律：状态分离原则

```
LLM = 无状态计算单元 (stateless compute unit)
所有跨轮次状态 → Harness 管控的外部持久化引擎
严禁依赖 LLM 自行维护复杂状态
```

---

## 2. 目录结构

在项目根目录下创建 `harness/` 包，与已有的 `backtest/` 平级：

```
项目根目录/
├── backtest/                    # 已有，不动
│   ├── __init__.py
│   ├── data.py                  # 数据加载
│   ├── strategies.py            # 策略库 + BaseStrategy + STRATEGY_REGISTRY
│   ├── engine.py                # 向量化回测引擎 + BacktestResult
│   └── metrics.py               # 绩效指标
│
├── harness/                     # 新建
│   ├── __init__.py              # 导出 QuantHarness, ResearchWorkflow 等
│   ├── tools.py                 # [Phase 1] 工具 Schema + ToolExecutor
│   ├── workflow.py              # [Phase 2] ResearchWorkflow 状态机
│   ├── loop.py                  # [Phase 2] REPL 循环主逻辑
│   ├── context.py               # [Phase 3] ContextManager + Token 预算
│   ├── persistence.py           # [Phase 2] HarnessPersistence 持久化层
│   ├── metrics_harness.py       # [Phase 4] HarnessMetrics 度量采集
│   └── knowledge.py             # [Phase 4] 知识蒸馏 + 检索
│
├── harness_workspace/           # 运行时生成 (gitignore)
│   ├── sessions/                # 会话快照 JSON
│   ├── artifacts/               # 回测产物 (parquet, png)
│   ├── knowledge/               # 知识库 (_index.jsonl + 卡片)
│   └── workflows/               # 工作流模板 YAML
│
├── backtest_main.py             # 已有，不动
└── HARNESS_DESIGN.md            # 本文档
```

---

## 3. Phase 1：工具契约化

**目标**：把 `backtest/` 模块的每个操作定义为 JSON Schema，实现带降级路径的执行器。

**产出文件**：`harness/tools.py`

### 3.1 工具定义

基于已有的回测能力，定义以下工具：

| 工具名 | 输入 | 输出 | 对应已有代码 |
|---|---|---|---|
| `run_backtest` | strategy, params, start, end | BacktestResult 摘要 | `backtest_main.run_single_backtest()` |
| `sweep_params` | strategy, param_grid, metric, top_n | pd.DataFrame (top-N) | `backtest_main.run_parameter_sweep()` |
| `compare_strategies` | strategies[] | pd.DataFrame (横向对比) | `backtest_main.run_comparison()` |
| `list_strategies` | 无 | 策略名列表 + 描述 | `backtest.strategies.list_strategies()` |
| `get_market_summary` | symbol, start, end | OHLCV 统计摘要 | `backtest.data.load_and_prepare()` |

### 3.2 实现要求

```python
# harness/tools.py

# 1. 每个工具有一个 JSON Schema (用于 LLM Function Calling)
TOOL_SCHEMAS: dict[str, dict] = {
    "run_backtest": {
        "name": "run_backtest",
        "description": "对单一策略执行向量化回测...",
        "parameters": {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "enum": [...]},
                "fast": {"type": "integer", "minimum": 2, "maximum": 500},
                ...
            },
            "required": ["strategy"]
        }
    },
    ...
}

# 2. ToolExecutor 类，核心方法：
class ToolExecutor:
    MAX_RETRIES = 2

    def execute(self, tool_name: str, raw_args: dict) -> ToolResult:
        """执行工具调用的完整流程。"""

    def _deserialize(self, tool_name: str, raw_args: dict) -> Optional[dict]:
        """JSON Schema 校验 → 成功返回解析后的参数，失败返回 None。"""

    def _text_fallback_parse(self, tool_name: str, raw_text: str) -> Optional[dict]:
        """降级路径 1：JSON 解析失败时，用正则/简单文本匹配提取参数。"""

    def _dispatch(self, tool_name: str, params: dict) -> Any:
        """路由到实际的回测函数执行。"""

# 3. ToolResult 类：
@dataclass
class ToolResult:
    status: Literal["success", "error", "partial"]
    summary: str               # 给 LLM 看的压缩摘要 (关键!)
    data: Optional[Any] = None # 完整结果 (仅当需要时)
    error: Optional[str] = None
    suggestion: Optional[str] = None  # 修复建议，帮助 LLM 重试

    def to_llm_feedback(self) -> str:
        """将执行结果序列化为 LLM 可消费的文本。"""
```

### 3.3 关键要求

- **双重解析器是必须的**：LLM 输出的 JSON 可能多一个逗号、少一个引号、字段名拼错。JSON Schema 校验失败时必须有文本回退路径，而不是直接崩溃。
- **ToolResult 的 summary 字段是重点**：不要把所有数据塞给 LLM。50 行回测结果压缩为 "SMA(25,80): 年化收益 12.3%, Sharpe 0.87, 最大回撤 -15.2%, 交易 47 笔"。
- **error 必须带 suggestion**：告诉 LLM 怎么修正，不只是报错。

---

## 4. Phase 2：REPL 循环 + 状态管理

**产出文件**：`harness/workflow.py`, `harness/loop.py`, `harness/persistence.py`

### 4.1 工作流状态机 (`harness/workflow.py`)

```python
class ResearchPhase(Enum):
    """量化研究标准流程的 6 个阶段。"""
    HYPOTHESIS = "hypothesis"           # 假设生成
    SINGLE_BACKTEST = "single_backtest" # 单策略回测验证
    PARAMETER_SWEEP = "parameter_sweep" # 参数敏感性
    ROBUSTNESS = "robustness"           # 稳健性检验
    ATTRIBUTION = "attribution"         # 归因分析
    REPORT = "report"                   # 结论汇总

@dataclass
class ResearchWorkflow:
    phases: list[ResearchPhase]       # 阶段列表 (默认全部 6 个)
    current_phase_idx: int = 0        # 当前阶段索引
    phase_results: dict[str, dict]    # 每个阶段的结构化产出

    @property
    def current_phase(self) -> ResearchPhase: ...
    def advance(self) -> Optional[ResearchPhase]: ...
    def can_skip_to(self, phase: ResearchPhase) -> bool: ...
```

### 4.2 每个阶段的 Prompt 模板 (`harness/workflow.py` 中定义)

每个阶段需要一个**结构化的 prompt 模板**，限定 LLM 在该阶段的行为边界：

```python
PHASE_PROMPTS: dict[ResearchPhase, str] = {
    ResearchPhase.HYPOTHESIS: """
你是一个 CTA 策略研究员。基于以下信息，生成一个可验证的交易假设。
...
输出 JSON:
{{
    "hypothesis": "...",
    "strategy": "选择的策略名称",
    "rationale": "为什么可能有效",
    "initial_params": {{}},
    "success_criteria": {{"min_sharpe": 0.5, "max_drawdown": -0.20}}
}}
""",
    ResearchPhase.SINGLE_BACKTEST: """
## 回测结果
{backtest_summary}
## 你的任务
判断结果是否达到成功标准。输出 JSON:
{{
    "verdict": "pass" | "fail" | "suspicious" | "retry",
    "reasoning": "...",
    "next_action": "..."
}}
""",
    # ... 其余阶段类似
}
```

**模板的关键约束**：
- 每个模板的结尾要求 LLM 输出**指定格式的 JSON**，不接受的格式导致解析失败 → 触发重试。
- 模板中 `{market_context}`, `{backtest_summary}` 等是槽位，由 ContextManager 在运行时填充。

### 4.3 工具可用性矩阵 (`harness/workflow.py`)

不是所有工具在任何阶段都能调用：

```python
TOOL_AVAILABILITY: dict[str, set[ResearchPhase]] = {
    "run_backtest":       {HYPOTHESIS, SINGLE_BACKTEST, PARAMETER_SWEEP, ROBUSTNESS},
    "sweep_params":       {PARAMETER_SWEEP, ROBUSTNESS},
    "walk_forward":       {ROBUSTNESS},
    "compare_strategies": {HYPOTHESIS, ROBUSTNESS},
    "plot_equity":        {SINGLE_BACKTEST, ROBUSTNESS, ATTRIBUTION},
    "attribution_report": {ATTRIBUTION},
    "final_report":       {REPORT},
}
```

LLM 在 HYPOTHESIS 阶段请求 `walk_forward` → Harness 拦截，返回："工具 walk_forward 在当前阶段不可用，请先完成单策略回测。"

### 4.4 REPL 主循环 (`harness/loop.py`)

```python
class QuantHarness:
    def __init__(self, workspace: Path): ...

    def repl(self):
        """交互式 REPL 循环 — 主入口。"""
        while not self._terminal_condition():
            user_input = input(f"[{self.workflow.current_phase.value}] > ")

            # 元命令 (不经过 LLM)
            if user_input in ("quit", "help", "status", "save", "skip"): ...

            # 核心：调用 LLM 推理
            response = self._call_llm(user_input)

            # 处理工具调用
            if response.has_tool_calls:
                feedback = self._handle_tool_calls(response.tool_calls)
                # 反馈注入第二轮 LLM 调用 (反思)
                response = self._call_llm_with_feedback(feedback)

            print(response.text)

            # 检查阶段推进
            self._check_phase_transition(response)

    def _call_llm(self, user_input: str) -> LLMResponse:
        """组装上下文 → 调用 LLM API → 返回响应。"""
        context = self.context_manager.assemble(self.workflow.current_phase)
        prompt = PHASE_PROMPTS[self.workflow.current_phase].format(**context)
        tools = self._get_available_tools()  # 按 TOOL_AVAILABILITY 过滤
        return llm_api.chat(system=prompt, messages=..., tools=tools)

    def _handle_tool_calls(self, tool_calls: list) -> str:
        """校验 → 执行 → 度量 → 反馈封装。"""
        for tc in tool_calls:
            if tc.name not in self._get_available_tool_names():
                results.append(f"[拒绝] 工具 '{tc.name}' 在当前阶段不可用")
                continue
            result = self.tool_executor.execute(tc.name, tc.arguments)
            self.metrics.record_tool_call(tc.name, result)
            results.append(result.to_llm_feedback())
        return "\n".join(results)
```

### 4.5 持久化层 (`harness/persistence.py`)

四层持久化，LLM 本身不保存任何状态：

```python
class HarnessPersistence:
    def __init__(self, workspace: Path):
        self.sessions_dir = workspace / "sessions"
        self.artifacts_dir = workspace / "artifacts"
        self.knowledge_dir = workspace / "knowledge"

    # ── Layer 1: 会话快照 ──
    def save_session(self, session_id: str, workflow: ResearchWorkflow,
                     messages: list[dict], metrics: dict):
        """保存完整会话，支持中断恢复。
        存储: sessions/{session_id}.json
        内容: workflow 状态 + 对话历史 (messages) + 度量快照 + 时间戳
        """

    def load_session(self, session_id: str) -> dict:
        """恢复会话，返回完整快照。"""

    def list_sessions(self) -> list[dict]:
        """列出所有历史会话 (id, phase, saved_at)。"""

    # ── Layer 2: 研究产物 ──
    def save_backtest_result(self, run_id: str, result: BacktestResult):
        """序列化回测结果为 Parquet + JSON 元数据。
        存储: artifacts/{run_id}/daily_return.parquet, equity.parquet, trades.parquet, meta.json
        """

    # ── Layer 3: 知识卡片 ──
    def save_insight(self, insight: dict):
        """保存一条研究洞察。
        存储: knowledge/{insight_id}.json
        同时更新 knowledge/_index.jsonl (可检索索引)
        """

    def query_knowledge(self, strategy: str = None,
                        market_condition: str = None) -> list[dict]:
        """按条件检索历史洞察。"""

    # ── Layer 4: 工作流模板 ──
    def save_workflow_template(self, name: str, template: dict):
        """保存自定义工作流模板。
        存储: workflows/{name}.yaml
        """

    def load_workflow_template(self, name: str) -> dict:
        """加载工作流模板。"""
```

### 4.6 对话历史保存的必要性

对话历史不是"日志"，它是 Harness 的核心数据资产，五个不可替代的作用：

1. **上下文重建** — LLM 每次调用都是无状态的，对话历史是它理解"试试把快线改成 30"指向什么的唯一依据（知道上次是 jm99、SMA、5min K 线、2021-2025）。
2. **会话恢复** — 研究可能跨数小时或跨天，中断后必须能从断点继续，而非从零开始。
3. **知识蒸馏** — 从原始对话中提取结构化洞察（策略 vs 市场状态 vs 绩效），存入知识库，未来的研究自动获得"先验知识"注入。
4. **可审计性** — 量化研究要求决策可追溯。三个月后你能回答"为什么当时选了 EMA(12,26) 而不是 EMA(8,32)？"
5. **度量与优化** — 对话历史是度量的数据源：LLM 调用次数、工具成功率、解析失败率、阶段耗时。没有它，无法优化 Harness 本身。

---

## 5. Phase 3：上下文预算 + 分层注入

**产出文件**：`harness/context.py`

### 5.1 问题

已有的回测数据量：1 分钟 Bar 约 49 万行 → 不可能全部塞入 LLM 上下文窗口。必须分层管理，只注入当前阶段需要且 token 预算允许的信息。

### 5.2 四层注入体系

```
Layer 0 (静态, 始终注入, ~2K tokens):
  ├── System Prompt: 角色定义, 约束, 可用工具
  ├── 品种知识: jm99 合约规格, 交易时间, 成本结构
  └── 当前日期 + 市场状态一句话摘要

Layer 1 (准静态, 按需注入, ~3K tokens):
  ├── 策略库索引: 5 个策略的签名 + 一句话描述
  ├── 上次研究的摘要 (知识库检索)
  └── 当前可用的工具列表 (按 TOOL_AVAILABILITY 过滤)

Layer 2 (动态, 前一阶段产出, ~5-10K tokens):
  ├── 前一阶段的回测结果摘要 (不是原始数据!)
  ├── 参数扫描 top-N 表格 (不是全部组合!)
  └── 相关历史洞察 (按 strategy + market_condition 检索)

Layer 3 (详细, 显式请求, 不限):
  └── 原始行情切片 / 完整交易记录 / 图表
      仅在 LLM 明确请求时注入
```

### 5.3 Token 预算分配器

```python
class ContextBudget:
    def __init__(self, max_tokens: int = 100_000):
        self.max = max_tokens
        self.allocated = 0

    def allocate(self, layer: str, content: str) -> str:
        """尝试分配 token 预算。超限时自动压缩。"""
        estimated = estimate_tokens(content)
        if self.allocated + estimated <= self.max:
            self.allocated += estimated
            return content
        else:
            remaining = self.max - self.allocated
            return self._compress(content, remaining)

    def _compress(self, content: str, budget: int) -> str:
        """分层压缩策略: 摘要 > 截断 > 丢弃。
        具体策略:
          数字表格 → 只保留 top/bottom N 行
          长文本 → 提取关键句
          代码块 → 保留签名，丢弃实现
        """

class ContextManager:
    def __init__(self, budget: ContextBudget, persistence: HarnessPersistence):
        self.budget = budget
        self.persistence = persistence

    def assemble(self, phase: ResearchPhase, additional: dict = None) -> dict:
        """为给定阶段组装上下文，返回可供 prompt 模板填充的 dict。

        流程:
          1. Layer 0: 注入静态上下文
          2. Layer 1: 注入策略目录 + 可用工具 + 知识库检索
          3. Layer 2: 注入前一阶段的结构化结果摘要
          4. Layer 3: 仅当 LLM 显式请求时注入
          5. 每层注入后调用 budget.allocate()，超限自动压缩
        """
```

### 5.4 上下文压缩的具体策略

| 数据类型 | 压缩策略 |
|---|---|
| 回测指标 | 只保留 Sharpe / 年化收益 / 最大回撤 / Calmar / 交易笔数，丢弃中间计算过程 |
| 参数扫描 | 只注入 top-5 和 bottom-5，保留拓扑判断（高原 vs 尖峰） |
| 行情数据 | 不注入原始数据。注入统计摘要：均值、波动率、趋势强度、区间振幅 |
| 交易记录 | 不注入全部 trades。注入摘要：总笔数、胜率、平均盈亏比、最大连亏 |
| 图表 | 不注入 base64。注入图表描述："净值曲线在 2022 年 3-8 月出现 15% 回撤" |

---

## 6. Phase 4：度量 + 知识进化闭环

**产出文件**：`harness/metrics_harness.py`, `harness/knowledge.py`

### 6.1 HarnessMetrics

与策略级指标（Sharpe, Calmar）正交，Harness 度量的是**研究过程本身的质量**：

```python
@dataclass
class HarnessMetrics:
    # LLM 侧
    total_llm_calls: int = 0
    total_tokens: int = 0
    avg_llm_latency_ms: float = 0.0
    parse_success_rate: float = 1.0    # LLM 输出 JSON 解析成功率
    retry_count: int = 0              # 解析失败导致的 LLM 重试次数

    # 工具执行侧
    tool_call_count: int = 0
    tool_success_rate: float = 1.0    # 工具执行成功率
    avg_tool_latency_ms: float = 0.0
    tools_by_name: dict[str, int]     # 每个工具的调用次数

    # 研究侧
    hypotheses_tested: int = 0
    phases_completed: int = 0
    human_interventions: int = 0      # 用户手动纠正 LLM 的次数
    insights_generated: int = 0
    time_to_first_result_s: float = 0.0

    def record_llm_call(self, latency_ms: int, tokens: int, parse_ok: bool): ...
    def record_tool_call(self, tool_name: str, result: ToolResult): ...
    def summary(self) -> dict: ...
```

### 6.2 知识蒸馏

从对话历史中提取结构化知识卡片：

```python
class KnowledgeEngine:
    def distill(self, session: dict) -> list[dict]:
        """从一次完整会话中提炼知识卡片。

        提炼规则:
          - LLM 输出中 verdict="pass" 且 sharpe > 0.5 的 → 成功案例
          - LLM 输出中 verdict="suspicious" 且 sharpe > 3 → 过拟合警告
          - LLM 输出中 verdict="fail" 的 → 失败案例
          - 参数扫描中 topology="plateau" 的 → 稳健参数区域
          - 参数扫描中 topology="peak" 的 → 过拟合嫌疑

        每张卡片:
        {
            "id": "insight_20260711_001",
            "type": "success" | "failure" | "warning" | "observation",
            "strategy": "emacross",
            "market_condition": "趋势",     # 从行情摘要推断
            "params": {"fast": 12, "slow": 26},
            "sharpe": 0.92,
            "title": "EMA(12,26) 在趋势市中表现稳健",
            "body": "参数区域呈高原形态，参数不敏感...",
            "timestamp": "2026-07-11T10:30:00",
            "source_session": "session_20260711_103000"
        }
        """

    def inject_relevant_knowledge(self, strategy: str, market_condition: str,
                                  budget_tokens: int) -> str:
        """检索相关知识卡片，压缩为上下文块注入。

        检索策略:
          1. 精确匹配 strategy + market_condition
          2. 仅匹配 strategy (跨市场条件)
          3. 仅匹配 market_condition (跨策略)
          4. 按 sharpe 排序，取 top-K 直到 token 预算用尽
        """
```

### 6.3 进化闭环

```
对话历史 (原始数据)
    ↓ KnowledgeEngine.distill()
标注样本 (结构化知识卡片)
    ↓ 分析
Prompt 模板优化 / 工具 Schema 改进 / 工作流模板调整 / 策略参数先验
    ↓ 回流
下一次研究的上下文更精准，LLM 决策质量更高
```

---

## 7. 调用方式

Harness 提供三种调用模式：

### 7.1 交互式 REPL（日常研究探索）

```bash
python -m harness repl
```

进入交互式终端，LLM 逐步推进研究流程。支持元命令：
- `help` — 显示帮助
- `status` — 显示当前工作流状态
- `save` — 手动保存会话
- `skip` — 跳过当前阶段
- `quit` — 退出（自动保存）

### 7.2 CLI 一次性任务（自动化/批处理）

```bash
python -m harness run --workflow standard --strategy emacross --fast 12 --slow 26
python -m harness resume session_20260711_103000
python -m harness list
python -m harness knowledge --strategy emacross --market-condition 趋势
```

### 7.3 Python API（嵌入到更大系统）

```python
from harness import QuantHarness

harness = QuantHarness(workspace=Path("./research_output"))

# 快速假设验证
result = harness.quick_test(strategy="emacross", params={"fast": 8, "slow": 32})

# 完整工作流
report = harness.run_workflow(
    workflow="standard",
    hypothesis="焦煤在 5 分钟 K 线上存在短期动量效应",
)

# 恢复中断的研究
harness.resume("session_20260711_103000")
```

---

## 8. 关键设计决策与理由

| 决策 | 理由 | 如果不这样做会怎样 |
|---|---|---|
| LLM 不保存任何状态 | LLM 是无状态计算单元，跨轮次记忆依赖其内部实现会导致行为不可预测 | LLM "记错"上一轮的回测结果，基于错误数据做决策 |
| 每个工具有双重解析器 | LLM 输出的 JSON 经常有格式错误 | 一次 JSON 解析失败就崩溃，研究中断 |
| 工具调用必须走可用性矩阵 | 防止 LLM 在研究早期就跳到高级分析（如 walk-forward 验证一个不存在的策略） | LLM 盲目做复杂分析，浪费 token 和时间 |
| 上下文分层注入 | 49 万行数据不可能全部塞进 context window | LLM 的注意力被无关数据稀释，关键信息被"大海捞针" |
| 对话历史必须持久化 | 研究有连续性，中断必须能恢复；历史是知识蒸馏的数据源 | 每次研究从零开始，不可审计，无法进化 |
| Prompt 模板是带槽位的，不是让 LLM 自己写 | 限定 LLM 的行为边界，确保输出可解析 | LLM 输出格式不一致，解析失败率飙升 |
| 度量是 Harness 级的，不是策略级的 | Harness 本身需要优化，没有度量就无法判断改进了什么 | 不知道是 LLM 的问题还是策略的问题 |

---

## 附录 A：LLM API 调用约定

Harness 不绑定特定 LLM 提供商。所有 LLM 调用通过一个统一接口：

```python
@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall] | None
    tokens_used: int
    latency_ms: int

@dataclass
class ToolCall:
    name: str
    arguments: dict

class LLMProvider(ABC):
    """LLM 提供商抽象 — 适配 Anthropic / OpenAI / 本地模型。"""
    @abstractmethod
    def chat(self, system: str, messages: list[dict],
             tools: list[dict]) -> LLMResponse: ...
```

具体实现时，参考 `.claude/agents/quant-trader.md` 中定义的角色设定。Tool use 模式遵循 Anthropic 官方格式（`tool_use` content block），其他提供商的响应需适配为该格式。

## 附录 B：与已有 backtest/ 模块的关系

```
Harness 不修改 backtest/ 的任何代码。

Harness 调用 backtest/ 的方式：
  harness/tools.py → import backtest_main 中的函数
                   → 或直接调用 backtest/engine.py, backtest/strategies.py

Harness 新增的文件全部在 harness/ 和 harness_workspace/ 下。
已有的 backtest_main.py 仍然可以独立运行，不受影响。
```

## 附录 C：建议的实施顺序

1. **先搭骨架**：`harness/__init__.py`, `harness/tools.py` (ToolResult + ToolExecutor 骨架)，验证能调用已有回测代码。
2. **再加循环**：`harness/workflow.py` (状态机), `harness/loop.py` (REPL), `harness/persistence.py` (保存/恢复)。此时可以完整 run 一个研究流程。
3. **再优化上下文**：`harness/context.py` (分层注入 + Token 预算)。当发现 LLM "忘了"前面的内容或输出质量下降时，这一层能解决 80% 的问题。
4. **最后加度量**：`harness/metrics_harness.py`, `harness/knowledge.py` (知识闭环)。这一步是长期价值，不是 MVP 的阻塞项。
