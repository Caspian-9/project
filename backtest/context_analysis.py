"""因子情境分析 — 分股票池/行业/风格/市场阶段/日历效应。

参考: 国信证券《多因子研究系列（一）》第 12-17 页

情境分析回答:
  - 因子在哪些股票池中有效？（沪深300 vs 中证500 vs 中证800）
  - 因子在哪些行业中暴露集中？
  - 因子在哪种市场风格下表现好？（大盘/中盘/小盘，价值/成长）
  - 因子在不同市场阶段（牛/熊/震荡）表现差异多大？
  - 因子是否有季节效应？（月初/月末，季报期/非季报期）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class MarketPhase(Enum):
    """市场阶段分类。"""

    BULL = "bull"  # 牛市
    BEAR = "bear"  # 熊市
    SIDEWAYS = "sideways"  # 震荡市


@dataclass
class ContextMetrics:
    """因子情境分析汇总。"""

    factor_name: str

    # 分股票池
    by_pool: dict[str, dict[str, float]] = field(default_factory=dict)

    # 分行业
    by_industry: pd.DataFrame = field(default_factory=pd.DataFrame)

    # 分风格
    by_style: dict[str, float] = field(default_factory=dict)

    # 分市场阶段
    by_phase: dict[str, dict[str, float]] = field(default_factory=dict)

    # 日历效应
    by_calendar: dict[int, float] = field(default_factory=dict)  # {month: IC_mean}


# ======================== 市场阶段划分 ========================


def classify_market_phase(
    benchmark_returns: pd.Series,
    bull_threshold: float = 0.20,  # 从高点回落 20% 视为转熊
    lookback: int = 60,  # 60 期滚动窗口
) -> pd.Series:
    """将每期分类为牛市/熊市/震荡市。

    规则:
      - 当前价格在滚动最高点的 80% 以上 → 牛市
      - 当前价格在滚动最高点的 80% 以下 → 熊市
      - 过渡区域 → 震荡市

    简化版: 用滚动均线方向 + 波动率判断。

    Args:
        benchmark_returns: (time,) 基准指数收益率。
        bull_threshold: 牛熊分界阈值。
        lookback: 滚动窗口。

    Returns:
        (time,) 市场阶段 Series。
    """
    cumulative = (1 + benchmark_returns).cumprod()
    rolling_max = cumulative.rolling(lookback, min_periods=1).max()
    drawdown_ratio = cumulative / rolling_max

    phases = pd.Series(index=benchmark_returns.index, dtype=object)
    phases[drawdown_ratio >= 0.80] = MarketPhase.BULL.value
    phases[(drawdown_ratio >= 0.65) & (drawdown_ratio < 0.80)] = MarketPhase.SIDEWAYS.value
    phases[drawdown_ratio < 0.65] = MarketPhase.BEAR.value

    return phases


# ======================== 分情境 IC 计算 ========================


def compute_ic_by_context(
    factor: pd.DataFrame,
    returns: pd.DataFrame,
    context_labels: pd.Series,
) -> dict[str, dict[str, float]]:
    """在不同情境下分别计算因子 IC 统计。

    Args:
        factor: (time, asset) 因子值。
        returns: (time, asset) 收益率。
        context_labels: (time,) 每期的情境标签。

    Returns:
        {context_label: {ic_mean, ic_std, ic_ir, ic_positive_ratio}}。
    """
    results: dict[str, dict[str, float]] = {}

    for label in context_labels.dropna().unique():
        label_times = context_labels[context_labels == label].index
        common = label_times.intersection(factor.index).intersection(returns.index)

        ic_values: list[float] = []
        for i in range(len(common) - 1):
            t = common[i]
            t_next = common[i + 1] if i + 1 < len(common) else t
            # 确保下一期也在同一情境中
            if context_labels.get(t_next) != label:
                continue

            f_cross = factor.loc[t].dropna()
            r_cross = returns.loc[t_next].dropna()
            common_assets = f_cross.index.intersection(r_cross.index)
            if len(common_assets) < 30:
                continue

            f_rank = f_cross[common_assets].rank()
            r_rank = r_cross[common_assets].rank()
            n = len(common_assets)
            d_sq = ((f_rank - r_rank) ** 2).sum()
            ic = 1.0 - (6.0 * d_sq) / (n * (n * n - 1))
            ic_values.append(ic)

        if ic_values:
            arr = np.array(ic_values)
            results[label] = {
                "ic_mean": float(arr.mean()),
                "ic_std": float(arr.std()),
                "ic_ir": float(arr.mean() / arr.std()) if arr.std() > 0 else 0.0,
                "ic_positive_ratio": float((arr > 0).mean()),
                "n_periods": len(arr),
            }

    return results


# ======================== 分行业 IC ========================


def compute_ic_by_industry(
    factor: pd.DataFrame,
    returns: pd.DataFrame,
    asset_info: pd.DataFrame,
    sector_column: str = "sector",
) -> pd.DataFrame:
    """在每个行业内分别计算因子 IC。

    Args:
        factor: (time, asset) 因子值。
        returns: (time, asset) 收益率。
        asset_info: (asset, [sector, ...]) 资产信息。
        sector_column: 行业列名。

    Returns:
        (sector, [ic_mean, ic_std, ic_ir, n_periods]) DataFrame。
    """
    sectors = asset_info[sector_column].dropna().unique()
    rows: list[dict[str, float | str]] = []

    for sector in sectors:
        sector_assets = asset_info.index[asset_info[sector_column] == sector]
        sector_factor = factor[sector_assets.intersection(factor.columns)]
        sector_returns = returns[sector_assets.intersection(returns.columns)]

        ic_values: list[float] = []
        for i in range(len(sector_factor.index) - 1):
            t = sector_factor.index[i]
            t_next = sector_returns.index[i + 1]

            f_cross = sector_factor.loc[t].dropna()
            r_cross = sector_returns.loc[t_next].dropna()
            common = f_cross.index.intersection(r_cross.index)
            if len(common) < 5:
                continue

            f_rank = f_cross[common].rank()
            r_rank = r_cross[common].rank()
            n = len(common)
            d_sq = ((f_rank - r_rank) ** 2).sum()
            ic = 1.0 - (6.0 * d_sq) / (n * (n * n - 1))
            ic_values.append(ic)

        if ic_values:
            arr = np.array(ic_values)
            rows.append({
                "sector": sector,
                "ic_mean": float(arr.mean()),
                "ic_std": float(arr.std()),
                "ic_ir": float(arr.mean() / arr.std()) if arr.std() > 0 else 0.0,
                "ic_positive_ratio": float((arr > 0).mean()),
                "n_periods": len(arr),
            })

    return pd.DataFrame(rows).sort_values("ic_ir", key=abs, ascending=False)


# ======================== 分股票池 IC ========================


def compute_ic_by_pool(
    factor: pd.DataFrame,
    returns: pd.DataFrame,
    pool_masks: dict[str, pd.Index],
) -> dict[str, dict[str, float]]:
    """在不同股票池中分别计算因子 IC。

    Args:
        factor: (time, asset) 因子值。
        returns: (time, asset) 收益率。
        pool_masks: {"沪深300": asset_index, "中证500": asset_index, ...}。

    Returns:
        {pool_name: {ic_mean, ic_std, ic_ir, ...}}。
    """
    results: dict[str, dict[str, float]] = {}

    for pool_name, pool_assets in pool_masks.items():
        common_assets = pool_assets.intersection(factor.columns).intersection(
            returns.columns
        )
        if len(common_assets) < 20:
            continue

        pool_factor = factor[common_assets]
        pool_returns = returns[common_assets]

        ic_values: list[float] = []
        for i in range(len(pool_factor.index) - 1):
            t = pool_factor.index[i]
            t_next = pool_returns.index[i + 1]

            f_cross = pool_factor.loc[t].dropna()
            r_cross = pool_returns.loc[t_next].dropna()
            common = f_cross.index.intersection(r_cross.index)
            if len(common) < 10:
                continue

            f_rank = f_cross[common].rank()
            r_rank = r_cross[common].rank()
            n = len(common)
            d_sq = ((f_rank - r_rank) ** 2).sum()
            ic = 1.0 - (6.0 * d_sq) / (n * (n * n - 1))
            ic_values.append(ic)

        if ic_values:
            arr = np.array(ic_values)
            results[pool_name] = {
                "ic_mean": float(arr.mean()),
                "ic_std": float(arr.std()),
                "ic_ir": float(arr.mean() / arr.std()) if arr.std() > 0 else 0.0,
                "ic_positive_ratio": float((arr > 0).mean()),
                "n_periods": len(arr),
                "n_assets": len(common_assets),
            }

    return results


# ======================== 分风格 IC ========================


def compute_ic_by_style(
    factor: pd.DataFrame,
    returns: pd.DataFrame,
    asset_info: pd.DataFrame,
    style_column: str = "market_cap",
    n_style_groups: int = 3,
) -> dict[str, float]:
    """在不同风格分组中分别计算因子 IC。

    例如: 按市值将股票分为大/中/小盘三组，每组内计算因子 IC。

    Args:
        factor: (time, asset) 因子值。
        returns: (time, asset) 收益率。
        asset_info: 资产信息。
        style_column: 风格列名（如 market_cap）。
        n_style_groups: 风格分组数。

    Returns:
        {style_group_label: IC_mean}。
    """
    # 一次性按风格列排序分组（取首期截面）
    if style_column not in asset_info.columns:
        return {}

    style_vals = asset_info[style_column].dropna()
    if len(style_vals) < n_style_groups * 3:
        return {}

    style_groups = pd.qcut(style_vals, n_style_groups, labels=["大盘", "中盘", "小盘"])

    results: dict[str, float] = {}
    for group_name in style_groups.dropna().unique():
        group_assets = style_groups[style_groups == group_name].index
        common = group_assets.intersection(factor.columns).intersection(returns.columns)
        if len(common) < 10:
            continue

        group_factor = factor[common]
        group_returns = returns[common]

        ic_values: list[float] = []
        for i in range(len(group_factor.index) - 1):
            t = group_factor.index[i]
            t_next = group_returns.index[i + 1]
            f_cross = group_factor.loc[t].dropna()
            r_cross = group_returns.loc[t_next].dropna()
            cmn = f_cross.index.intersection(r_cross.index)
            if len(cmn) < 5:
                continue
            f_rank = f_cross[cmn].rank()
            r_rank = r_cross[cmn].rank()
            n = len(cmn)
            d_sq = ((f_rank - r_rank) ** 2).sum()
            ic_values.append(1.0 - (6.0 * d_sq) / (n * (n * n - 1)))

        if ic_values:
            results[group_name] = float(np.mean(ic_values))

    return results


# ======================== 日历效应 ========================


def compute_calendar_effect(
    factor: pd.DataFrame,
    returns: pd.DataFrame,
) -> dict[int, float]:
    """计算因子 IC 的日历效应（按月）。

    Args:
        factor: (time, asset) 因子值。
        returns: (time, asset) 收益率。

    Returns:
        {month: IC_mean} dict (1-12)。
    """
    monthly_ics: dict[int, list[float]] = {m: [] for m in range(1, 13)}

    for i in range(len(factor.index) - 1):
        t = factor.index[i]
        t_next = returns.index[i + 1]
        month = t.month if hasattr(t, "month") else t.month

        f_cross = factor.loc[t].dropna()
        r_cross = returns.loc[t_next].dropna()
        common = f_cross.index.intersection(r_cross.index)
        if len(common) < 30:
            continue

        f_rank = f_cross[common].rank()
        r_rank = r_cross[common].rank()
        n = len(common)
        d_sq = ((f_rank - r_rank) ** 2).sum()
        ic = 1.0 - (6.0 * d_sq) / (n * (n * n - 1))
        monthly_ics[month].append(ic)

    return {m: float(np.mean(ics)) if ics else 0.0 for m, ics in monthly_ics.items()}


# ======================== 完整情境分析 ========================


def compute_full_context_metrics(
    factor_name: str,
    factor: pd.DataFrame,
    returns: pd.DataFrame,
    asset_info: Optional[pd.DataFrame] = None,
    benchmark_returns: Optional[pd.Series] = None,
) -> ContextMetrics:
    """计算完整的情境分析指标。

    Args:
        factor_name: 因子名。
        factor: (time, asset) 因子值。
        returns: (time, asset) 收益率。
        asset_info: 资产信息。
        benchmark_returns: 基准收益率。

    Returns:
        ContextMetrics。
    """
    metrics = ContextMetrics(factor_name=factor_name)

    # 分市场阶段
    if benchmark_returns is not None:
        phases = classify_market_phase(benchmark_returns)
        metrics.by_phase = compute_ic_by_context(factor, returns, phases)

    # 分行业
    if asset_info is not None and "sector" in asset_info.columns:
        metrics.by_industry = compute_ic_by_industry(factor, returns, asset_info)

    # 分风格
    if asset_info is not None and "market_cap" in asset_info.columns:
        metrics.by_style = compute_ic_by_style(factor, returns, asset_info)

    # 日历效应
    metrics.by_calendar = compute_calendar_effect(factor, returns)

    return metrics
