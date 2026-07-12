"""因子动态分析 — IC 衰变、自相关衰变、信号持续/逆转、换手率。

参考: 国信证券《多因子研究系列（一）》第 10-12 页

动态分析回答的核心问题:
  - 因子的预测能力能持续多久？（IC 衰变）
  - 因子值本身的稳定性如何？（自相关衰变）
  - 买入信号一旦出现，能维持几期？（信号持续）
  - 信号如果逆转，逆转速度多快？（信号逆转）
  - 组合调仓导致的交易成本多大？（换手率）
"""

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
    ic_decay = compute_ic_decay(factor, returns)
    autocorr_decay = compute_autocorr_decay(factor)
    signal_persistence = compute_signal_persistence(factor, n_quantiles)
    signal_reversal = compute_signal_reversal(factor, n_quantiles)
    turnover = compute_turnover_metrics(factor, n_quantiles)

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
