"""Quant Harness — 量化因子研究框架。

按工作流阶段组织的模块化脚本:
  data.py           — 数据加载与清洗管线
  factor.py         — 因子构建与风格中性化
  engine.py         — 向量化回测引擎与绩效指标
  analysis.py       — 动态分析 + 情境分析 + 稳健性验证
  workflow.py       — 四阶段状态机 + 变体生成 + Markdown 报告
  report_html.py    — HTML 报告 + Plotly 可视化图表
  tools.py          — 工具契约 + 上下文管理
  persistence.py    — 会话/产物/知识卡片持久化
  llm_provider.py   — LLM API 抽象 (Anthropic/Mock)
  loop.py           — REPL 主循环
"""

from scripts.data import (
    CleanMethod,
    DataPipeline,
    Freq,
    MarketData,
    MissingMethod,
    PipelineConfig,
    compute_trend_growth,
    create_default_asset_info,
    generate_synthetic_data,
    load_csi300,
    load_market_data,
)
from scripts.engine import (
    BacktestResult,
    FactorBacktestEngine,
    FactorMetrics,
    QuantileBacktestResult,
    compute_factor_metrics,
    compute_ic_summary,
    compute_quantile_returns,
)
from scripts.factor import (
    CompositeFactor,
    FactorDef,
    FactorTransform,
    NeutralizerConfig,
    QuantileMethod,
    StandardizeMethod,
    StyleNeutralizer,
    TransformMethod,
    WeightMethod,
    build_composite_factor,
    build_factor,
    parse_factor_expr,
)
from scripts.analysis import (
    ContextMetrics,
    DynamicMetrics,
    FactorAnalysis,
    MarketPhase,
    RobustnessResult,
    analyze_factor,
    classify_market_phase,
    compare_analyses,
    compute_autocorr_decay,
    compute_calendar_effect,
    compute_full_context_metrics,
    compute_full_dynamic_metrics,
    compute_ic_by_context,
    compute_ic_by_industry,
    compute_ic_by_pool,
    compute_ic_by_style,
    compute_ic_decay,
    compute_signal_persistence,
    compute_signal_reversal,
    compute_turnover_metrics,
    robustness_check,
)
from scripts.workflow import (
    PHASE_PROMPTS,
    FactorResearchPhase,
    FactorResearchWorkflow,
    FactorVariant,
    VariantGenerator,
    generate_factor_report,
    generate_summary_for_llm,
    generate_variant_ideas,
    save_report,
)
from scripts.tools import (
    TOOL_SCHEMAS,
    ContextBudget,
    ContextManager,
    ToolExecutor,
    ToolResult,
    load_wiki_index,
)
from scripts.persistence import HarnessPersistence
from scripts.llm_provider import (
    AnthropicProvider,
    LLMProvider,
    LLMResponse,
    MockLLMProvider,
    ToolCall,
)
from scripts.report_html import generate_html_report, save_html_report
from scripts.loop import QuantHarness

__all__ = [
    # data
    "CleanMethod", "DataPipeline", "Freq", "MarketData", "MissingMethod",
    "PipelineConfig", "compute_trend_growth", "create_default_asset_info",
    "generate_synthetic_data", "load_csi300", "load_market_data",
    # engine
    "BacktestResult", "FactorBacktestEngine", "FactorMetrics",
    "QuantileBacktestResult", "compute_factor_metrics", "compute_ic_summary",
    "compute_quantile_returns",
    # factor
    "CompositeFactor", "FactorDef", "FactorTransform", "NeutralizerConfig",
    "QuantileMethod", "StandardizeMethod", "StyleNeutralizer", "TransformMethod",
    "WeightMethod", "build_composite_factor", "build_factor", "parse_factor_expr",
    # analysis
    "ContextMetrics", "DynamicMetrics", "FactorAnalysis", "MarketPhase",
    "RobustnessResult", "analyze_factor", "classify_market_phase",
    "compare_analyses", "compute_autocorr_decay", "compute_calendar_effect",
    "compute_full_context_metrics", "compute_full_dynamic_metrics",
    "compute_ic_by_context", "compute_ic_by_industry", "compute_ic_by_pool",
    "compute_ic_by_style", "compute_ic_decay", "compute_signal_persistence",
    "compute_signal_reversal", "compute_turnover_metrics", "robustness_check",
    # workflow
    "PHASE_PROMPTS", "FactorResearchPhase", "FactorResearchWorkflow",
    "FactorVariant", "VariantGenerator", "generate_factor_report",
    "generate_summary_for_llm", "generate_variant_ideas", "save_report",
    # tools
    "TOOL_SCHEMAS", "ContextBudget", "ContextManager", "ToolExecutor",
    "ToolResult", "load_wiki_index",
    # persistence
    "HarnessPersistence",
    # llm_provider
    "AnthropicProvider", "LLMProvider", "LLMResponse", "MockLLMProvider", "ToolCall",
    # report_html
    "generate_html_report", "save_html_report",
    # loop
    "QuantHarness",
]
