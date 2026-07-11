"""Quant Harness — 包裹 LLM 的量化因子研究 REPL 闭环容器。

Architecture:
  ┌──────────────────────────────────────────┐
  │              Quant Harness                │
  │  ┌──────────┐ ┌──────────┐ ┌───────────┐ │
  │  │ Context  │ │  REPL    │ │   Tool    │ │
  │  │ Manager  │ │  Loop    │ │ Executor  │ │
  │  └──────────┘ └──────────┘ └─────┬─────┘ │
  │                                  │        │
  │  ┌───────────────────────────────┘        │
  │  │    backtest/ 模块 (确定性计算)          │
  │  │    ┌──────┐ ┌───────────┐ ┌─────────┐  │
  │  │    │data  │ │factor_bld │ │ engine  │  │
  │  │    └──────┘ └───────────┘ └─────────┘  │
  │  │    ┌──────┐                            │
  │  │    │metrics│                           │
  │  │    └──────┘                            │
  │  └────────────────────────────────────────┘
  │                                  │        │
  │  ┌───────────────────────────────┘        │
  │  │  Persistence (外部持久化)               │
  │  │  Wiki Integration (llm_wiki)            │
  │  └────────────────────────────────────────┘
  └──────────────────────────────────────────┘

Workflow:
  1. SELECT: 用户选定报告 + 因子 → 深读 → 提取原始定义 + 经济逻辑
  2. GENERATE_BACKTEST: 生成变体 → 批量向量化回测 → 汇总排名
  3. ANALYZE: 多维度分析 → IC/分层/暴露/归因 → Markdown 报告
"""

from harness.analysis_engine import FactorAnalysis, analyze_factor, compare_analyses
from harness.context import ContextBudget, ContextManager
from harness.factor_engine import VariantGenerator, generate_variant_ideas
from harness.llm_provider import (
    LLMProvider,
    LLMResponse,
    MockLLMProvider,
    ToolCall,
)
from harness.loop import QuantHarness
from harness.persistence import HarnessPersistence
from harness.reports import (
    generate_factor_report,
    generate_summary_for_llm,
    save_report,
)
from harness.tools import TOOL_SCHEMAS, ToolExecutor, ToolResult, load_wiki_index
from harness.workflow import (
    PHASE_PROMPTS,
    FactorResearchPhase,
    FactorResearchWorkflow,
    FactorVariant,
)

__all__ = [
    # 主入口
    "QuantHarness",
    # 工作流
    "FactorResearchPhase",
    "FactorResearchWorkflow",
    "FactorVariant",
    "PHASE_PROMPTS",
    # 因子引擎
    "VariantGenerator",
    "generate_variant_ideas",
    # 分析引擎
    "FactorAnalysis",
    "analyze_factor",
    "compare_analyses",
    # 工具
    "TOOL_SCHEMAS",
    "ToolExecutor",
    "ToolResult",
    "load_wiki_index",
    # 上下文
    "ContextBudget",
    "ContextManager",
    # LLM
    "LLMProvider",
    "LLMResponse",
    "MockLLMProvider",
    "ToolCall",
    # 报告
    "generate_factor_report",
    "generate_summary_for_llm",
    "save_report",
    # 持久化
    "HarnessPersistence",
]
