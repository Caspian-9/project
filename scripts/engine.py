"""向量化回测引擎与绩效指标。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd

from scripts.data import MarketData


# ── 回测参数配置 ──


@dataclass
class BacktestConfig:
    """因子回测全参数配置 — 一个 dataclass 封装所有可调参数。

    每个因子回测时只需传入一个 BacktestConfig 实例。
    """

    # === 分组参数 ===
    n_quantiles: int = 5  # 分位数 (2~10)
    weighting: Literal["equal", "market_cap", "style_neutral"] = "equal"
    holding_periods: int = 1  # 持仓周期 (1=下一期, 5=下周, 20=下月)

    # === 因子预处理 ===
    transform: str = "zscore"  # zscore | rank | winsorize | raw
    clean_outliers: bool = True  # MAD 异常值清洗
    clean_method: str = "mad"  # mad | 3sigma | percentile
    industry_neutralize: bool = False  # 行业标准化
    industry_quantile: bool = False  # 行业内分位 (vs 全市场分位)

    # === 分析参数 ===
    periods_per_year: int = 252

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_quantiles": self.n_quantiles,
            "weighting": self.weighting,
            "holding_periods": self.holding_periods,
            "transform": self.transform,
            "clean_outliers": self.clean_outliers,
            "clean_method": self.clean_method,
            "industry_neutralize": self.industry_neutralize,
            "industry_quantile": self.industry_quantile,
            "periods_per_year": self.periods_per_year,
        }


# ── 标准预设 ──

PRESETS: dict[str, BacktestConfig] = {
    "default": BacktestConfig(
        # 国信证券默认: 5分位, 等权, 持有1期, zscore
    ),
    "guoxin_standard": BacktestConfig(
        n_quantiles=5, weighting="equal", holding_periods=1,
        transform="zscore", clean_outliers=True, clean_method="mad",
        industry_neutralize=False, industry_quantile=False,
    ),
    "industry_neutral": BacktestConfig(
        n_quantiles=5, weighting="market_cap", holding_periods=1,
        transform="zscore", clean_outliers=True, clean_method="mad",
        industry_neutralize=True, industry_quantile=True,
    ),
    "rank_robust": BacktestConfig(
        n_quantiles=5, weighting="equal", holding_periods=1,
        transform="rank", clean_outliers=True, clean_method="mad",
        industry_neutralize=True, industry_quantile=False,
    ),
    "monthly_rebalance": BacktestConfig(
        n_quantiles=5, weighting="market_cap", holding_periods=20,
        transform="zscore", clean_outliers=True, clean_method="mad",
        industry_neutralize=True, industry_quantile=True,
    ),
    "long_term": BacktestConfig(
        n_quantiles=5, weighting="market_cap", holding_periods=60,
        transform="zscore", clean_outliers=True, clean_method="mad",
        industry_neutralize=True, industry_quantile=True,
    ),
}


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

    def __init__(self, config: Optional[BacktestConfig] = None) -> None:
        """初始化回测引擎。

        Args:
            config: 回测参数配置。默认使用 PRESETS['default']。
        """
        self.config = config or PRESETS["default"]
        self.n_quantiles = self.config.n_quantiles
        self.weighting = self.config.weighting
        self.holding_periods = self.config.holding_periods
        if self.n_quantiles < 2:
            raise ValueError("n_quantiles 至少为 2")

    @staticmethod
    def compute_full_report(
        factor_name: str,
        factor_values: pd.DataFrame,
        returns: pd.DataFrame,
        asset_info: Optional[pd.DataFrame] = None,
        benchmark_returns: Optional[pd.Series] = None,
        n_quantiles: int = 5,
    ) -> dict[str, Any]:
        """计算完整的因子分析报告（静态 + 动态 + 情境）。

        这是国信证券框架的完整实现入口。
        一次性返回全部三维度的分析结果。

        Args:
            factor_name: 因子名。
            factor_values: (time, asset) 因子值。
            returns: (time, asset) 收益率。
            asset_info: 资产信息（行业、市值、风格）。
            benchmark_returns: 基准收益序列。
            n_quantiles: 分位数。

        Returns:
            {static, dynamic, context} 三维度完整分析 dict。
        """
        from scripts.analysis import compute_full_dynamic_metrics
        from scripts.analysis import (
            compute_full_context_metrics,
            compute_ic_by_pool,
        )

        # 从收益率反推价格用于 MarketData
        prices = (1 + returns.fillna(0.0)).cumprod()
        volumes = pd.DataFrame(
            1.0, index=returns.index, columns=returns.columns
        )

        # 静态分析
        engine = FactorBacktestEngine(BacktestConfig(n_quantiles=n_quantiles))
        result = engine.run(
            MarketData(prices=prices, volumes=volumes),
            factor_values,
            factor_name=factor_name,
        )

        # 动态分析
        dynamic = compute_full_dynamic_metrics(
            factor_name, factor_values, returns, n_quantiles
        )

        # 情境分析
        context = compute_full_context_metrics(
            factor_name, factor_values, returns, asset_info, benchmark_returns
        )

        # 股票池分析（默认三大指数）
        pool_masks: dict[str, pd.Index] = {}
        if asset_info is not None:
            if "pool" in asset_info.columns:
                for pool_name in asset_info["pool"].dropna().unique():
                    pool_masks[pool_name] = asset_info.index[
                        asset_info["pool"] == pool_name
                    ]
        if pool_masks:
            context.by_pool = compute_ic_by_pool(factor_values, returns, pool_masks)

        return {
            "static": result,
            "dynamic": dynamic,
            "context": context,
        }

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
        asset_info = data.asset_info
        quantile_result = self._compute_quantile_returns(
            factor_aligned, returns_aligned, asset_info
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
            config=self.config.to_dict(),
        )

    def _compute_quantile_returns(
        self,
        factor: pd.DataFrame,
        returns: pd.DataFrame,
        asset_info: Optional[pd.DataFrame] = None,
    ) -> QuantileBacktestResult:
        """计算分层组合收益。

        支持:
          - 普通分位 / 行业内分位 (config.industry_quantile)
          - 等权 / 市值加权 / 风格中性 (config.weighting)

        Args:
            factor: (time, asset) 因子值。
            returns: (time, asset) 下期收益。
            asset_info: (asset, [sector, market_cap]) 辅助信息。

        Returns:
            QuantileBacktestResult。
        """
        n_times = len(factor.index)
        quantile_returns_list: list[pd.Series] = []

        use_industry_q = (
            self.config.industry_quantile
            and asset_info is not None
            and "sector" in asset_info.columns
        )
        use_mcap_w = (
            self.config.weighting in ("market_cap", "style_neutral")
            and asset_info is not None
            and "market_cap" in asset_info.columns
        )

        for t_idx in range(n_times - self.holding_periods):
            t = factor.index[t_idx]
            t_next = returns.index[t_idx + self.holding_periods]

            cross_section = factor.loc[t].dropna()
            if len(cross_section) < self.n_quantiles * 3:
                continue

            # 分位分组
            if use_industry_q:
                # 行业内分位 → 保证每组行业均匀
                quantile_labels = self._industry_quantile_labels(
                    cross_section, asset_info
                )
            else:
                quantile_labels = pd.qcut(
                    cross_section, self.n_quantiles, labels=False, duplicates="drop"
                )

            if quantile_labels is None or quantile_labels.nunique() < self.n_quantiles:
                continue

            # 下期收益
            next_returns = returns.loc[t_next].dropna()
            common = quantile_labels.index.intersection(next_returns.index)
            if len(common) < self.n_quantiles * 3:
                continue

            # 计算每组加权收益
            if use_mcap_w and asset_info is not None:
                mcap = asset_info.loc[common, "market_cap"].fillna(1.0)
                mcap = mcap / mcap.sum()  # normalize weights
                # weighted average per group
                weighted_ret = next_returns[common] * mcap
                group_returns = weighted_ret.groupby(quantile_labels[common]).sum() / mcap.groupby(quantile_labels[common]).sum()
            else:
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

    def _industry_quantile_labels(
        self,
        cross_section: pd.Series,
        asset_info: Optional[pd.DataFrame],
    ) -> Optional[pd.Series]:
        """行业内分位数 — 每个行业内部独立分位后汇总。

        保证每个分位组内各行业的股票数量均匀分布。

        Args:
            cross_section: 截面因子值。
            asset_info: 资产信息 (含 sector)。

        Returns:
            分位标签 (0 ~ n_quantiles-1) 或 None。
        """
        if asset_info is None or "sector" not in asset_info.columns:
            return None
        result = pd.Series(index=cross_section.index, dtype=float)
        sectors = asset_info.loc[cross_section.index, "sector"].dropna()

        for sector in sectors.unique():
            s_assets = sectors[sectors == sector].index
            s_vals = cross_section[s_assets].dropna()
            if len(s_vals) < self.n_quantiles * 2:
                continue
            try:
                labels = pd.qcut(
                    s_vals, self.n_quantiles, labels=False, duplicates="drop"
                )
                result.loc[labels.index] = labels.values
            except ValueError:
                continue

        if result.notna().sum() < self.n_quantiles * 3:
            return None
        return result

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

from dataclasses import dataclass, field
from typing import TypedDict




def save_backtest_results(
    results: dict[str, dict[str, Any]],
    config: BacktestConfig,
    output_path: str = "research/backtest_results.json",
    factor_source: str = "",
    notes: str = "",
) -> Path:
    """保存回测结果 JSON，开头包含回测参数配置。

    Args:
        results: {factor_name: {ic_ir, ic_mean, sharpe, ...}} 因子结果字典。
        config: 回测参数配置。
        output_path: 输出文件路径。
        factor_source: 因子来源说明 (如报告ID)。
        notes: 备注。

    Returns:
        保存的文件路径。
    """
    import json
    from datetime import datetime
    from pathlib import Path

    output: dict[str, Any] = {
        "_config": config.to_dict(),
        "_meta": {
            "generated_at": datetime.now().isoformat(),
            "n_factors": len(results),
            "factor_source": factor_source,
            "notes": notes,
        },
        "factors": results,
    }
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


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
