"""因子分析引擎：动态分析 + 情境分析 + 稳健性验证。"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class DynamicMetrics:
    """因子动态分析指标汇总。"""

    factor_name: str

    # IC 衰变
    ic_decay: dict[int, float] = field(default_factory=dict)  # {holding_period: IC_mean}

    # 因子自相关衰变
    autocorr_decay: dict[int, float] = field(default_factory=dict)  # {lag: avg_corr}

    # 信号持续
    signal_persistence: dict[int, float] = field(default_factory=dict)  # {periods: %still_buy}

    # 信号逆转
    signal_reversal: dict[int, float] = field(default_factory=dict)  # {periods: %reversed}

    # 换手率
    avg_turnover_num: float = 0.0  # 按股票数目变动
    avg_turnover_weight: float = 0.0  # 按权重变动
    avg_turnover_factor: float = 0.0  # 按因子值变动（1-自相关）


# ======================== IC 衰变分析 ========================


def compute_ic_decay(
    factor: pd.DataFrame,
    returns: pd.DataFrame,
    max_periods: int = 12,
) -> dict[int, float]:
    """计算 IC 前瞻衰变曲线。

    对于每个前瞻期 k (1~max_periods):
      IC_k = corr(factor_t, return_{t+k}), 截面秩相关

    衰变越快 → 因子信息被市场消化的速度越快 → 需要更高换手频率。

    Args:
        factor: (time, asset) 因子值。
        returns: (time, asset) 收益率。
        max_periods: 最大前瞻期数。

    Returns:
        {holding_period: IC_mean} dict。
    """
    decay: dict[int, float] = {}
    common_times = factor.index.intersection(returns.index)

    for k in range(1, max_periods + 1):
        ic_values: list[float] = []
        for i in range(len(common_times) - k):
            t = common_times[i]
            t_forward = common_times[i + k]

            f_cross = factor.loc[t].dropna()
            r_cross = returns.loc[t_forward].dropna()
            common = f_cross.index.intersection(r_cross.index)
            if len(common) < 30:
                continue

            f_rank = f_cross[common].rank()
            r_rank = r_cross[common].rank()
            n = len(common)
            d_sq = ((f_rank - r_rank) ** 2).sum()
            ic = 1.0 - (6.0 * d_sq) / (n * (n * n - 1))
            ic_values.append(ic)

        if ic_values:
            decay[k] = float(np.mean(ic_values))
        else:
            decay[k] = 0.0

    return decay


# ======================== 因子自相关衰变 ========================


def compute_autocorr_decay(
    factor: pd.DataFrame,
    max_lag: int = 6,
) -> dict[int, float]:
    """计算因子截面平均自相关衰变。

    对每个滞后 k:
      计算每只股票 factor_t 与 factor_{t-k} 的时序自相关，
      取截面平均。

    自相关越高 → 因子越稳定 → 换手率越低。

    Args:
        factor: (time, asset) 因子值。
        max_lag: 最大滞后期数。

    Returns:
        {lag: avg_autocorr} dict。
    """
    decay: dict[int, float] = {}

    for lag in range(1, max_lag + 1):
        corrs: list[float] = []
        for asset in factor.columns:
            series = factor[asset].dropna()
            if len(series) < lag + 10:
                continue
            corr = series.autocorr(lag=lag)
            if not np.isnan(corr):
                corrs.append(corr)

        decay[lag] = float(np.mean(corrs)) if corrs else 0.0

    return decay


# ======================== 买入信号持续/逆转分析 ========================


def compute_signal_persistence(
    factor: pd.DataFrame,
    n_quantiles: int = 5,
    target_quantile: int = 4,  # top group
    max_periods: int = 12,
) -> dict[int, float]:
    """计算买入信号的持续概率。

    选定 top 组（如 Q4），跟踪这些股票在后续 k 期中
    仍保持在 top 组的比例。

    持续率越高 → 不需要频繁调仓 → 换手成本越低。

    Args:
        factor: (time, asset) 因子值。
        n_quantiles: 分位数。
        target_quantile: 目标分位。
        max_periods: 最大跟踪期数。

    Returns:
        {periods: %still_in_top} dict。
    """
    persistence: dict[int, float] = {}

    for k in range(1, max_periods + 1):
        stay_rates: list[float] = []
        for i in range(len(factor.index) - k):
            t = factor.index[i]
            t_k = factor.index[i + k]

            cross_t = factor.loc[t].dropna()
            cross_tk = factor.loc[t_k].dropna()
            common = cross_t.index.intersection(cross_tk.index)
            if len(common) < n_quantiles * 3:
                continue

            labels_t = pd.qcut(cross_t[common], n_quantiles, labels=False, duplicates="drop")
            labels_tk = pd.qcut(cross_tk[common], n_quantiles, labels=False, duplicates="drop")

            top_now = labels_t[labels_t == target_quantile].index
            top_later = labels_tk[labels_tk == target_quantile].index
            stayed = len(top_now.intersection(top_later))
            if len(top_now) > 0:
                stay_rates.append(stayed / len(top_now))

        persistence[k] = float(np.mean(stay_rates)) if stay_rates else 0.0

    return persistence


def compute_signal_reversal(
    factor: pd.DataFrame,
    n_quantiles: int = 5,
    max_periods: int = 12,
) -> dict[int, float]:
    """计算买入信号的逆转概率。

    选定 top 组（Q4），跟踪这些股票在后续 k 期中
    跌入 bottom 组（Q0）的比例。

    逆转率越高 → top 信号越不稳定 → 需要更好的择时。

    Args:
        factor: (time, asset) 因子值。
        n_quantiles: 分位数。
        max_periods: 最大跟踪期数。

    Returns:
        {periods: %reversed_to_bottom} dict。
    """
    reversal: dict[int, float] = {}

    for k in range(1, max_periods + 1):
        rev_rates: list[float] = []
        for i in range(len(factor.index) - k):
            t = factor.index[i]
            t_k = factor.index[i + k]

            cross_t = factor.loc[t].dropna()
            cross_tk = factor.loc[t_k].dropna()
            common = cross_t.index.intersection(cross_tk.index)
            if len(common) < n_quantiles * 3:
                continue

            labels_t = pd.qcut(cross_t[common], n_quantiles, labels=False, duplicates="drop")
            labels_tk = pd.qcut(cross_tk[common], n_quantiles, labels=False, duplicates="drop")

            top_now = labels_t[labels_t == n_quantiles - 1].index
            bottom_later = labels_tk[labels_tk == 0].index
            reversed_to_bottom = len(top_now.intersection(bottom_later))
            if len(top_now) > 0:
                rev_rates.append(reversed_to_bottom / len(top_now))

        reversal[k] = float(np.mean(rev_rates)) if rev_rates else 0.0

    return reversal


# ======================== 换手率分析 ========================


def compute_turnover_metrics(
    factor: pd.DataFrame,
    n_quantiles: int = 5,
    target_quantile: int = 4,
) -> dict[str, float]:
    """计算三种换手率指标。

    1. 数目换手率: Top 组中股票数目的变动比例
       turnover_num = |Top_t ∩ Top_{t-1}| / |Top_{t-1}|

    2. 权重换手率: Top 组中权重变动的比例
       turnover_wgt = Σ|w_{i,t} - w_{i,t-1}| / 2

    3. 因子换手率: 1 - 因子截面平均自相关(lag=1)
       因子越稳定 → 自相关越高 → 换手率越低

    Args:
        factor: (time, asset) 因子值。
        n_quantiles: 分位数。
        target_quantile: 目标分位。

    Returns:
        {turnover_num, turnover_weight, turnover_factor} dict。
    """
    turnover_nums: list[float] = []
    turnover_wgts: list[float] = []

    for i in range(1, len(factor.index)):
        t_prev = factor.index[i - 1]
        t_curr = factor.index[i]

        cross_prev = factor.loc[t_prev].dropna()
        cross_curr = factor.loc[t_curr].dropna()
        common = cross_prev.index.intersection(cross_curr.index)
        if len(common) < n_quantiles * 3:
            continue

        labels_prev = pd.qcut(cross_prev[common], n_quantiles, labels=False, duplicates="drop")
        labels_curr = pd.qcut(cross_curr[common], n_quantiles, labels=False, duplicates="drop")

        top_prev = set(labels_prev[labels_prev == target_quantile].index)
        top_curr = set(labels_curr[labels_curr == target_quantile].index)

        # 数目换手
        if len(top_prev) > 0:
            left = len(top_prev - top_curr)
            joined = len(top_curr - top_prev)
            # 单边换手 = (left + joined) / (2 * |top_prev|)
            turnover_nums.append((left + joined) / (2 * len(top_prev)))

        # 权重换手（简化版: 等权假设下，数目换手即权重换手）
        # 实际中可用市值权重计算，这里用等权近似
        turnover_wgts.append(turnover_nums[-1] if turnover_nums else 0.0)

    # 因子换手 = 1 - 平均一阶自相关
    autocorr_k1 = compute_autocorr_decay(factor, max_lag=1).get(1, 0.0)
    turnover_factor = 1.0 - max(0.0, autocorr_k1)

    return {
        "turnover_num": float(np.mean(turnover_nums)) if turnover_nums else 0.0,
        "turnover_weight": float(np.mean(turnover_wgts)) if turnover_wgts else 0.0,
        "turnover_factor": turnover_factor,
    }


def compute_full_dynamic_metrics(
    factor_name: str,
    factor: pd.DataFrame,
    returns: pd.DataFrame,
    n_quantiles: int = 5,
) -> DynamicMetrics:
    """计算完整的动态分析指标。

    Args:
        factor_name: 因子名。
        factor: (time, asset) 因子值。
        returns: (time, asset) 收益率。
        n_quantiles: 分位数。

    Returns:
        DynamicMetrics。
    """
    print("  动态分析: IC衰变/自相关/信号持续/换手率...", end=" ", flush=True)
    ic_decay = compute_ic_decay(factor, returns)
    autocorr_decay = compute_autocorr_decay(factor)
    signal_persistence = compute_signal_persistence(factor, n_quantiles)
    signal_reversal = compute_signal_reversal(factor, n_quantiles)
    turnover = compute_turnover_metrics(factor, n_quantiles)
    print("done")

    return DynamicMetrics(
        factor_name=factor_name,
        ic_decay=ic_decay,
        autocorr_decay=autocorr_decay,
        signal_persistence=signal_persistence,
        signal_reversal=signal_reversal,
        avg_turnover_num=turnover["turnover_num"],
        avg_turnover_weight=turnover["turnover_weight"],
        avg_turnover_factor=turnover["turnover_factor"],
    )

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional



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

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from scripts.data import MarketData
from scripts.engine import BacktestResult, compute_factor_metrics


@dataclass
class FactorAnalysis:
    """因子多维度分析结果。"""

    factor_name: str

    # IC 分析
    ic_mean: float
    ic_std: float
    ic_ir: float
    ic_positive_ratio: float
    ic_stability: str  # 稳定/一般/不稳定 —基于 IC_IR 绝对值

    # 分层
    quantile_spread_annual: float
    quantile_monotonic: bool
    quantile_detail: dict[int, float]  # 各分位年化收益

    # 多空
    long_short_sharpe: float
    long_short_maxdd: float
    calmar: float

    # 投资逻辑
    factor_direction: str  # 正向/负向
    quality_grade: str  # A/B/C/D — 综合评级
    strength: list[str] = field(default_factory=list)
    weakness: list[str] = field(default_factory=list)

    # 改进
    improvement_ideas: list[str] = field(default_factory=list)

    # 元信息
    extra: dict[str, Any] = field(default_factory=dict)


def analyze_factor(
    result: BacktestResult,
    data: Optional[MarketData] = None,
    economic_rationale: str = "",
) -> FactorAnalysis:
    """对回测结果进行多维度分析。

    Args:
        result: 回测引擎输出的完整结果。
        data: 市场数据（可选，用于风格/行业暴露分析）。
        economic_rationale: 因子的经济逻辑说明。

    Returns:
        FactorAnalysis 包含全面的因子评估。
    """
    metrics = compute_factor_metrics(result)

    # IC 稳定性分级
    abs_ir = abs(metrics.ic_ir)
    if abs_ir > 0.75:
        ic_stability = "稳定"
    elif abs_ir > 0.3:
        ic_stability = "一般"
    else:
        ic_stability = "不稳定"

    # 因子方向
    direction = "正向" if metrics.ic_mean > 0 else "负向"

    # 综合评级
    score = 0
    if abs_ir > 0.5:
        score += 2
    elif abs_ir > 0.2:
        score += 1
    if metrics.quantile_monotonicity:
        score += 2
    if abs(metrics.long_short_sharpe) > 0.5:
        score += 2
    elif abs(metrics.long_short_sharpe) > 0.2:
        score += 1
    if metrics.long_short_maxdd > -0.3:
        score += 1

    grade_map = {5: "A", 4: "B", 3: "C", 2: "C", 1: "D", 0: "D"}
    grade = grade_map.get(score, "D")

    # 优劣势分析
    strengths: list[str] = []
    weaknesses: list[str] = []

    if abs_ir > 0.3:
        strengths.append(f"IC_IR={metrics.ic_ir:.2f}，预测能力{'较强' if abs_ir > 0.5 else '中等'}")
    else:
        weaknesses.append(f"IC_IR={metrics.ic_ir:.2f}，预测能力偏弱")

    if metrics.quantile_monotonicity:
        strengths.append("分层收益单调，因子区分度好")
    else:
        weaknesses.append("分层收益不单调，存在非线性关系或分组间差异小")

    if abs(metrics.long_short_sharpe) > 0.5:
        strengths.append(f"多空 Sharpe={metrics.long_short_sharpe:.2f}，风险调整收益好")
    elif abs(metrics.long_short_sharpe) < 0.2:
        weaknesses.append(f"多空 Sharpe={metrics.long_short_sharpe:.2f}，风险调整收益不足")

    if metrics.long_short_maxdd < -0.3:
        weaknesses.append(f"最大回撤={metrics.long_short_maxdd:.1%}，回撤控制需改善")
    else:
        strengths.append(f"最大回撤={metrics.long_short_maxdd:.1%}，回撤控制好")

    if metrics.ic_positive_ratio < 0.55:
        weaknesses.append(f"IC 胜率仅 {metrics.ic_positive_ratio:.0%}，信号方向不稳定")

    # 改进建议
    improvements: list[str] = []
    if not metrics.quantile_monotonicity:
        improvements.append("尝试非线性变换（如 Rank/分位数）改善单调性")
    if abs_ir < 0.3:
        improvements.append("考虑加入行业/风格中性化，剥离系统性暴露")
        improvements.append("尝试不同市场状态下分段回测，找出因子最佳适用环境")
    if metrics.long_short_maxdd < -0.3:
        improvements.append("加入止损/仓位管理机制控制回撤")
    improvements.append("进行参数敏感性扫描，确认最优参数区域的稳健性（高原 vs 尖峰）")

    return FactorAnalysis(
        factor_name=result.factor_name,
        ic_mean=metrics.ic_mean,
        ic_std=metrics.ic_std,
        ic_ir=metrics.ic_ir,
        ic_positive_ratio=metrics.ic_positive_ratio,
        ic_stability=ic_stability,
        quantile_spread_annual=metrics.top_bottom_annual_spread,
        quantile_monotonic=metrics.quantile_monotonicity,
        quantile_detail=metrics.quantile_annual_returns,
        long_short_sharpe=metrics.long_short_sharpe,
        long_short_maxdd=metrics.long_short_maxdd,
        calmar=metrics.long_short_calmar,
        factor_direction=direction,
        quality_grade=grade,
        strength=strengths,
        weakness=weaknesses,
        improvement_ideas=improvements,
        extra={
            "economic_rationale": economic_rationale,
            "n_periods": len(result.ic_series),
            "config": result.config,
        },
    )


def compare_analyses(analyses: list[FactorAnalysis]) -> pd.DataFrame:
    """横向对比多个因子分析结果。

    Args:
        analyses: 因子分析结果列表。

    Returns:
        对比 DataFrame。
    """
    rows: list[dict[str, Any]] = []
    for a in analyses:
        rows.append({
            "factor": a.factor_name,
            "grade": a.quality_grade,
            "IC_IR": round(a.ic_ir, 3),
            "IC_mean": round(a.ic_mean, 4),
            "IC>0%": f"{a.ic_positive_ratio:.0%}",
            "spread": f"{a.quantile_spread_annual:.2%}",
            "mono": "Y" if a.quantile_monotonic else "N",
            "Sharpe": round(a.long_short_sharpe, 3),
            "MaxDD": f"{a.long_short_maxdd:.1%}",
            "stability": a.ic_stability,
        })
    return pd.DataFrame(rows).sort_values("IC_IR", key=abs, ascending=False)


# ======================== 稳健性验证 ========================


@dataclass
class RobustnessResult:
    """稳健性验证结果。"""

    factor_name: str

    # 分段测试
    first_half_ic_ir: float
    second_half_ic_ir: float
    split_test_passed: bool

    # 参数稳定性
    parameter_stability: str  # "plateau" | "peak" | "unknown"

    # 分池验证
    pool_ic_irs: dict[str, float]  # {pool_name: IC_IR}

    # 决策
    decision: str  # "graduate" | "needs_work" | "discard"
    reasoning: str


def robustness_check(
    factor_name: str,
    ic_series: pd.Series,
    param_sweep_results: Optional[list[dict[str, Any]]] = None,
    pool_ic_irs: Optional[dict[str, float]] = None,
) -> RobustnessResult:
    """执行因子稳健性验证（参考 AGENTS.md Step 6）。

    Args:
        factor_name: 因子名。
        ic_series: Rank IC 时间序列。
        param_sweep_results: 参数扫描结果列表（含 score/IC_IR 等）。
        pool_ic_irs: 分池 IC_IR dict。

    Returns:
        RobustnessResult 含决策建议。
    """
    # ── 1. 分段测试 ──
    mid = len(ic_series) // 2
    first_half = ic_series.iloc[:mid]
    second_half = ic_series.iloc[mid:]

    fh_ir = float(first_half.mean() / first_half.std()) if first_half.std() > 0 else 0.0
    sh_ir = float(second_half.mean() / second_half.std()) if second_half.std() > 0 else 0.0

    # 两段方向一致 + 绝对值 > 0.2
    split_ok = (
        (fh_ir > 0.2 and sh_ir > 0.2)
        or (fh_ir < -0.2 and sh_ir < -0.2)
    )

    # ── 2. 参数稳定性 ──
    stability = "unknown"
    if param_sweep_results and len(param_sweep_results) >= 4:
        scores = [r.get("ic_ir", r.get("score", 0)) for r in param_sweep_results]
        max_score = max(abs(s) for s in scores)
        mean_score = sum(abs(s) for s in scores) / len(scores)
        # 高原型: 均值接近最大值；尖峰型: 最大值远超均值
        if mean_score > 0 and max_score / mean_score < 1.5:
            stability = "plateau"
        else:
            stability = "peak"

    # ── 3. 决策矩阵 (AGENTS.md Step 7 适配) ──
    abs_ir = abs(fh_ir + sh_ir) / 2  # 平均 |IC_IR|

    decision = "needs_work"
    reasoning_parts: list[str] = []

    if split_ok and stability == "plateau" and abs_ir > 0.5:
        decision = "graduate"
        reasoning_parts.append(f"分段测试通过({fh_ir:.2f}/{sh_ir:.2f})")
        reasoning_parts.append(f"参数高原型, |IC_IR|={abs_ir:.2f}>0.5")
    elif split_ok and stability == "plateau" and abs_ir > 0.2:
        decision = "needs_work"
        reasoning_parts.append(f"分段测试通过但|IC_IR|={abs_ir:.2f}<0.5")
        reasoning_parts.append("建议: 加入行业/风格中性化后重试")
    elif not split_ok or stability == "peak":
        decision = "needs_work"
        reasoning_parts.append(
            f"分段测试{'通过' if split_ok else '不通过'}, 参数{stability}型"
        )
        reasoning_parts.append("建议: 减少参数、简化因子结构")
    if abs_ir < 0.15:
        decision = "discard"
        reasoning_parts.append(f"|IC_IR|={abs_ir:.2f}<0.15, 因子无稳健预测能力")

    return RobustnessResult(
        factor_name=factor_name,
        first_half_ic_ir=fh_ir,
        second_half_ic_ir=sh_ir,
        split_test_passed=split_ok,
        parameter_stability=stability,
        pool_ic_irs=pool_ic_irs or {},
        decision=decision,
        reasoning="; ".join(reasoning_parts),
    )
