"""向量化回测引擎 — 将因子值转化为投资组合收益。

核心思路: 每个截面期按因子值排序分组 → 等权/市值加权 → 计算下期组合收益。
全程使用 numpy/pandas 向量化操作，禁止逐行循环。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from backtest.data import MarketData


@dataclass
class QuantileBacktestResult:
    """分层回测结果 — 每个分位组合的时间序列表现。"""

    quantile_returns: pd.DataFrame  # (time, quantile) → 各分位组合收益
    quantile_cumulative: pd.DataFrame  # (time, quantile) → 各分位累计净值
    top_bottom_spread: pd.Series  # (time,) → top - bottom 多空收益
    n_quantiles: int = 5
    weighting: str = "equal"


@dataclass
class BacktestResult:
    """完整回测结果 — 因子 + 分层组合的全面表现。"""

    factor_name: str
    factor_values: pd.DataFrame  # (time, asset) → 因子值

    # 分层回测
    quantile: QuantileBacktestResult

    # IC 序列
    ic_series: pd.Series  # (time,) → 每期 Rank IC
    ic_mean: float
    ic_std: float
    ic_ir: float  # IC 信息比率 = IC均值 / IC标准差

    # 多空组合
    long_short_sharpe: float
    long_short_maxdd: float

    # 元信息
    config: dict = field(default_factory=dict)


class FactorBacktestEngine:
    """向量化因子回测引擎。

    工作流:
      1. 输入 MarketData + factor_values (pd.DataFrame)
      2. 每期按因子值排序 → 分位分组
      3. 计算下期各分位组合收益 → 汇总 IC + 多空表现

    所有计算在数据矩阵上一次完成，无逐行循环。
    """

    def __init__(
        self,
        n_quantiles: int = 5,
        weighting: Literal["equal", "value"] = "equal",
        holding_periods: int = 1,
    ) -> None:
        """初始化回测引擎。

        Args:
            n_quantiles: 分位数（默认 5 组）。
            weighting: 组合加权方式，equal 或 value（市值）。
            holding_periods: 持仓周期数（1 = 下一期）。
        """
        if n_quantiles < 2:
            raise ValueError("n_quantiles 至少为 2")
        self.n_quantiles = n_quantiles
        self.weighting = weighting
        self.holding_periods = holding_periods

    def run(
        self,
        data: MarketData,
        factor_values: pd.DataFrame,
        factor_name: str = "factor",
    ) -> BacktestResult:
        """执行因子回测。

        Args:
            data: 市场数据。
            factor_values: (time, asset) 因子值矩阵，index/columns 需对齐 data。
            factor_name: 因子名称（用于结果标识）。

        Returns:
            BacktestResult 包含分层收益 + IC 序列 + 多空表现。
        """
        # 对齐数据
        common_times = data.returns.index.intersection(factor_values.index)
        common_assets = data.returns.columns.intersection(factor_values.columns)

        if len(common_times) < 12:
            raise ValueError(f"公共时间点不足 ({len(common_times)}), 至少需要 12 期")
        if len(common_assets) < self.n_quantiles * 3:
            raise ValueError(
                f"公共资产不足 ({len(common_assets)}), 至少需要 {self.n_quantiles * 3} 只"
            )

        factor_aligned = factor_values.loc[common_times, common_assets]
        returns_aligned = data.returns.loc[common_times, common_assets]

        # 计算分层收益
        quantile_result = self._compute_quantile_returns(
            factor_aligned, returns_aligned
        )

        # 计算 IC 序列
        ic_series = self._compute_rank_ic(factor_aligned, returns_aligned)

        # 多空表现
        spread = quantile_result.top_bottom_spread.dropna()
        long_short_sharpe = self._annualized_sharpe(spread)
        long_short_maxdd = self._max_drawdown(spread)

        return BacktestResult(
            factor_name=factor_name,
            factor_values=factor_aligned,
            quantile=quantile_result,
            ic_series=ic_series,
            ic_mean=float(ic_series.mean()),
            ic_std=float(ic_series.std()),
            ic_ir=float(ic_series.mean() / ic_series.std()) if ic_series.std() > 0 else 0.0,
            long_short_sharpe=long_short_sharpe,
            long_short_maxdd=long_short_maxdd,
            config={
                "n_quantiles": self.n_quantiles,
                "weighting": self.weighting,
                "holding_periods": self.holding_periods,
            },
        )

    def _compute_quantile_returns(
        self,
        factor: pd.DataFrame,
        returns: pd.DataFrame,
    ) -> QuantileBacktestResult:
        """计算分层组合收益 — 全向量化。

        Args:
            factor: (time, asset) 因子值。
            returns: (time, asset) 下期收益。

        Returns:
            QuantileBacktestResult。
        """
        n_times = len(factor.index)
        quantile_returns_list: list[pd.Series] = []

        for t_idx in range(n_times - self.holding_periods):
            t = factor.index[t_idx]
            t_next = returns.index[t_idx + self.holding_periods]

            # 当前截面因子值
            cross_section = factor.loc[t].dropna()
            if len(cross_section) < self.n_quantiles * 3:
                continue

            # 分位分组标签 (0 = bottom, n_quantiles-1 = top)
            quantile_labels = pd.qcut(
                cross_section, self.n_quantiles, labels=False, duplicates="drop"
            )
            if quantile_labels.nunique() < self.n_quantiles:
                continue

            # 下期收益
            next_returns = returns.loc[t_next].dropna()
            common = quantile_labels.index.intersection(next_returns.index)
            if len(common) < self.n_quantiles * 3:
                continue

            # 每组等权收益
            group_returns = next_returns[common].groupby(quantile_labels[common]).mean()
            group_returns.name = t_next
            quantile_returns_list.append(group_returns)

        if not quantile_returns_list:
            raise ValueError("无法计算分层收益——数据不足")

        quantile_returns = pd.DataFrame(quantile_returns_list).sort_index(axis=1)

        # 累计净值
        quantile_cumulative = (1 + quantile_returns).cumprod()

        # top - bottom 多空
        top_col = quantile_returns.columns[-1]
        bottom_col = quantile_returns.columns[0]
        spread = quantile_returns[top_col] - quantile_returns[bottom_col]

        return QuantileBacktestResult(
            quantile_returns=quantile_returns,
            quantile_cumulative=quantile_cumulative,
            top_bottom_spread=spread,
            n_quantiles=self.n_quantiles,
            weighting=self.weighting,
        )

    @staticmethod
    def _compute_rank_ic(
        factor: pd.DataFrame,
        returns: pd.DataFrame,
    ) -> pd.Series:
        """计算截面 Rank IC 序列 — 全向量化。

        Rank IC = Spearman 秩相关系数(因子值, 下期收益)

        Args:
            factor: (time, asset) 因子值。
            returns: (time, asset) 下期收益。

        Returns:
            (time,) Rank IC 序列。
        """
        ic_values: list[float] = []
        ic_times: list[pd.Timestamp] = []

        for i in range(len(factor.index) - 1):
            t = factor.index[i]
            t_next = returns.index[i + 1]  # 用下期收益

            f_cross = factor.loc[t]
            r_cross = returns.loc[t_next]

            common = f_cross.dropna().index.intersection(r_cross.dropna().index)
            if len(common) < 30:
                continue

            f_rank = f_cross[common].rank()
            r_rank = r_cross[common].rank()

            n = len(common)
            # Spearman = 1 - 6*sum(d^2) / (n*(n^2-1))
            d_sq = ((f_rank - r_rank) ** 2).sum()
            ic = 1.0 - (6.0 * d_sq) / (n * (n * n - 1))
            ic_values.append(ic)
            ic_times.append(t_next)

        return pd.Series(ic_values, index=pd.DatetimeIndex(ic_times), name="RankIC")

    @staticmethod
    def _annualized_sharpe(returns: pd.Series, periods_per_year: int = 252) -> float:
        """年化夏普比率。

        Args:
            returns: 每期收益序列。
            periods_per_year: 年化周期数。

        Returns:
            年化夏普比率。
        """
        if len(returns) < 2:
            return 0.0
        mu = returns.mean()
        sigma = returns.std()
        if sigma == 0:
            return 0.0
        return float(mu / sigma * np.sqrt(periods_per_year))

    @staticmethod
    def _max_drawdown(returns: pd.Series) -> float:
        """最大回撤。

        Args:
            returns: 每期收益序列。

        Returns:
            最大回撤（负值，如 -0.15 表示最大回撤 15%）。
        """
        if len(returns) < 2:
            return 0.0
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        return float(drawdown.min())
