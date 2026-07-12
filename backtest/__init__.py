"""向量化回测引擎 — 数据加载、因子构建、回测执行、绩效指标。

backtest/ 是确定性计算模块，不做任何 LLM 相关的事。
Harness 通过 backtest_executor.py 调用本模块。

模块结构:
  data.py            — 市场数据加载 + 合成数据生成
  data_pipeline.py   — 数据清洗管线 (MAD异常值/样本筛选/幸存者偏差)  [新增]
  factor_builder.py  — 因子 DSL: FactorDef → 因子值矩阵
  engine.py          — 向量化回测引擎 + 完整三维度分析入口           [升级]
  metrics.py         — 因子绩效指标汇总 (IC/分层/多空)
  style_neutralizer.py — 四层风格过滤 (标准化/分位/权重/残余)       [新增]
  dynamic_analysis.py  — 动态分析 (IC衰变/自相关/信号持续/换手)     [新增]
  context_analysis.py  — 情境分析 (股票池/行业/风格/市场阶段/日历)  [新增]

参考: 国信证券《多因子研究系列（一）——因子回溯测试的总体框架》(2012.08.22)
"""

from backtest.context_analysis import (
    ContextMetrics,
    classify_market_phase,
    compute_calendar_effect,
    compute_full_context_metrics,
    compute_ic_by_context,
    compute_ic_by_industry,
    compute_ic_by_pool,
    compute_ic_by_style,
)
from backtest.data import (
    Freq,
    MarketData,
    generate_synthetic_data,
    load_market_data,
)
from backtest.data_pipeline import (
    CleanMethod,
    DataPipeline,
    MissingMethod,
    PipelineConfig,
    compute_trend_growth,
    create_default_asset_info,
)
from backtest.dynamic_analysis import (
    DynamicMetrics,
    compute_autocorr_decay,
    compute_full_dynamic_metrics,
    compute_ic_decay,
    compute_signal_persistence,
    compute_signal_reversal,
    compute_turnover_metrics,
)
from backtest.engine import (
    BacktestResult,
    FactorBacktestEngine,
    QuantileBacktestResult,
)
from backtest.factor_builder import (
    CompositeFactor,
    FactorDef,
    FactorTransform,
    build_factor,
    parse_factor_expr,
)
from backtest.metrics import (
    FactorMetrics,
    compute_factor_metrics,
    compute_ic_summary,
    compute_quantile_returns,
)
from backtest.style_neutralizer import (
    NeutralizerConfig,
    QuantileMethod,
    StandardizeMethod,
    StyleNeutralizer,
    WeightMethod,
)

__all__ = [
    # data
    "Freq",
    "MarketData",
    "generate_synthetic_data",
    "load_market_data",
    # data_pipeline
    "CleanMethod",
    "DataPipeline",
    "MissingMethod",
    "PipelineConfig",
    "compute_trend_growth",
    "create_default_asset_info",
    # factor_builder
    "FactorDef",
    "FactorTransform",
    "CompositeFactor",
    "build_factor",
    "parse_factor_expr",
    # engine
    "BacktestResult",
    "FactorBacktestEngine",
    "QuantileBacktestResult",
    # metrics
    "FactorMetrics",
    "compute_factor_metrics",
    "compute_ic_summary",
    "compute_quantile_returns",
    # style_neutralizer
    "NeutralizerConfig",
    "QuantileMethod",
    "StandardizeMethod",
    "StyleNeutralizer",
    "WeightMethod",
    # dynamic_analysis
    "DynamicMetrics",
    "compute_autocorr_decay",
    "compute_full_dynamic_metrics",
    "compute_ic_decay",
    "compute_signal_persistence",
    "compute_signal_reversal",
    "compute_turnover_metrics",
    # context_analysis
    "ContextMetrics",
    "classify_market_phase",
    "compute_calendar_effect",
    "compute_full_context_metrics",
    "compute_ic_by_context",
    "compute_ic_by_industry",
    "compute_ic_by_pool",
    "compute_ic_by_style",
]
