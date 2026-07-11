"""向量化回测引擎 — 数据加载、因子构建、回测执行、绩效指标。

backtest/ 是确定性计算模块，不做任何 LLM 相关的事。
Harness 通过 backtest_executor.py 调用本模块。
"""

from backtest.data import (
    Freq,
    MarketData,
    generate_synthetic_data,
    load_market_data,
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

__all__ = [
    # data
    "Freq",
    "MarketData",
    "generate_synthetic_data",
    "load_market_data",
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
]
