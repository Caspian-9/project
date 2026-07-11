"""因子绩效指标计算 — IC 分析、分层收益统计、组合评估。

与 engine.py 的区别:
  - engine.py: 驱动回测流程，产出原始序列（IC序列、分层收益序列）
  - metrics.py: 对原始序列做统计汇总，产出可读的指标表
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TypedDict

import numpy as np
import pandas as pd

from backtest.engine import BacktestResult


class QuantileSummary(TypedDict):
    """分层收益统计摘要。"""

    quantile_annual_returns: dict[int, float]
    top_bottom_annual_spread: float
    quantile_monotonicity: bool


@dataclass
class FactorMetrics:
    """因子绩效指标汇总 — 多维度的统计摘要。"""

    factor_name: str

    # IC 指标
    ic_mean: float
    ic_std: float
    ic_ir: float
    ic_positive_ratio: float  # IC > 0 的比例
    ic_t_stat: float  # IC 均值的 Newey-West t 值（简化: 均值/标准误）

    # 分层收益
    quantile_annual_returns: dict[int, float]  # {quantile: 年化收益}
    top_bottom_annual_spread: float  # top - bottom 年化多空收益
    quantile_monotonicity: bool  # 收益是否单调递增/递减

    # 多空组合
    long_short_sharpe: float
    long_short_maxdd: float
    long_short_calmar: float  # 年化收益 / |最大回撤|

    # 换手率
    avg_turnover: Optional[float] = None  # 平均截面换手率

    # 额外元信息
    extra: dict = field(default_factory=dict)


def compute_ic_summary(ic_series: pd.Series) -> dict[str, float]:
    """计算 IC 序列的统计摘要。

    Args:
        ic_series: Rank IC 序列。

    Returns:
        含 ic_mean, ic_std, ic_ir, ic_positive_ratio, ic_t_stat 的 dict。
    """
    valid = ic_series.dropna()
    if len(valid) < 10:
        return {
            "ic_mean": 0.0,
            "ic_std": 0.0,
            "ic_ir": 0.0,
            "ic_positive_ratio": 0.0,
            "ic_t_stat": 0.0,
        }

    mean = float(valid.mean())
    std = float(valid.std())
    ir = mean / std if std > 0 else 0.0
    positive_ratio = float((valid > 0).mean())
    # 简化 t 统计量（假设独立）
    t_stat = mean / (std / np.sqrt(len(valid))) if std > 0 else 0.0

    return {
        "ic_mean": mean,
        "ic_std": std,
        "ic_ir": ir,
        "ic_positive_ratio": positive_ratio,
        "ic_t_stat": t_stat,
    }


def compute_quantile_returns(
    quantile_returns: pd.DataFrame,
    periods_per_year: int = 252,
) -> QuantileSummary:
    """计算分层收益的统计摘要。

    Args:
        quantile_returns: (time, quantile) 分层组合每期收益。
        periods_per_year: 年化周期数。

    Returns:
        含 quantile_annual_returns, top_bottom_annual_spread, monotonicity 的 dict。
    """
    if quantile_returns.empty:
        return {
            "quantile_annual_returns": {},
            "top_bottom_annual_spread": 0.0,
            "quantile_monotonicity": False,
        }

    annual_returns: dict[int, float] = {}
    for col in sorted(quantile_returns.columns):
        mu = quantile_returns[col].mean()
        annual_returns[int(col)] = float(mu * periods_per_year)

    # 单调性: 从 Q0 到 Q4 是否单调增加或减少
    rets_list = [annual_returns[k] for k in sorted(annual_returns.keys())]
    increasing = all(rets_list[i] <= rets_list[i + 1] for i in range(len(rets_list) - 1))
    decreasing = all(rets_list[i] >= rets_list[i + 1] for i in range(len(rets_list) - 1))

    top = annual_returns[max(annual_returns.keys())]
    bottom = annual_returns[min(annual_returns.keys())]
    spread = top - bottom

    return {
        "quantile_annual_returns": annual_returns,
        "top_bottom_annual_spread": spread,
        "quantile_monotonicity": increasing or decreasing,
    }


def compute_factor_metrics(
    result: BacktestResult,
    periods_per_year: int = 252,
) -> FactorMetrics:
    """从 BacktestResult 生成完整的 FactorMetrics 汇总。

    Args:
        result: 回测引擎输出的完整结果。
        periods_per_year: 年化周期数。

    Returns:
        FactorMetrics 实例。
    """
    # IC 摘要
    ic_summary = compute_ic_summary(result.ic_series)

    # 分层收益
    q_summary = compute_quantile_returns(
        result.quantile.quantile_returns, periods_per_year
    )

    # Calmar = 年化收益 / |最大回撤|
    spread_annual = float(q_summary["top_bottom_annual_spread"])
    calmar = spread_annual / abs(result.long_short_maxdd) if result.long_short_maxdd < 0 else 0.0

    return FactorMetrics(
        factor_name=result.factor_name,
        ic_mean=float(ic_summary["ic_mean"]),
        ic_std=float(ic_summary["ic_std"]),
        ic_ir=float(ic_summary["ic_ir"]),
        ic_positive_ratio=float(ic_summary["ic_positive_ratio"]),
        ic_t_stat=float(ic_summary["ic_t_stat"]),
        quantile_annual_returns=dict(q_summary["quantile_annual_returns"]),
        top_bottom_annual_spread=float(q_summary["top_bottom_annual_spread"]),
        quantile_monotonicity=bool(q_summary["quantile_monotonicity"]),
        long_short_sharpe=result.long_short_sharpe,
        long_short_maxdd=result.long_short_maxdd,
        long_short_calmar=calmar,
        extra=result.config,
    )
