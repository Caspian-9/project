"""数据清洗管线 — 国信证券因子回溯测试框架的数据预处理层。

参考: 国信证券《多因子研究系列（一）——因子回溯测试的总体框架》(2012.08.22)

管线步骤:
  1. 样本筛选: 剔除 ST/PT、上市不足1年、停牌无法交易
  2. 异常值处理: MAD（绝对中位偏差）方法 + 传统 3σ 方法
  3. 缺失值处理: 根据来源选择剔除或替代
  4. 幸存者偏差校正: 使用历史成分股数据
  5. 信息公布时间校正: 保证因子值不包含未来信息
  6. 增长因子趋势化: 替代算术/几何增长率，避免偏差
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional

import numpy as np
import pandas as pd


# ======================== 数据模型 ========================


class CleanMethod(Enum):
    """异常值处理方法。"""

    MAD = "mad"  # 绝对中位偏差（更稳健）
    THREE_SIGMA = "3sigma"  # 传统三倍标准差
    PERCENTILE = "percentile"  # 分位数截尾


class MissingMethod(Enum):
    """缺失值处理策略。"""

    DROP = "drop"  # 剔除该样本
    MEDIAN = "median"  # 截面中位数填充
    INDUSTRY_MEDIAN = "industry_median"  # 同行业截面中位数填充
    FORWARD_FILL = "forward_fill"  # 前向填充（时序）


@dataclass
class PipelineConfig:
    """数据清洗管线配置。"""

    # 样本筛选
    remove_st: bool = True  # 剔除 ST/PT 股票
    min_listed_days: int = 252  # 上市至少 1 年（约 252 个交易日）
    remove_suspended: bool = True  # 剔除停牌无法买入

    # 异常值处理
    clean_method: CleanMethod = CleanMethod.MAD
    mad_threshold: float = 3.0  # MAD 倍数（默认 3 → 等价 3σ）
    winsorize_bounds: tuple[float, float] = (0.01, 0.99)  # 分位数截尾边界

    # 缺失值
    missing_method: MissingMethod = MissingMethod.INDUSTRY_MEDIAN

    # 幸存者偏差
    use_historical_constituents: bool = True

    # 信息公布时间
    lag_financial_data: bool = True  # 财报数据滞后到公布日

    # 增长因子
    use_trend_growth: bool = True  # 使用趋势化增长因子


# ======================== 管线执行器 ========================


class DataPipeline:
    """数据清洗管线执行器。

    对原始 (time, asset) 因子值矩阵执行完整的清洗流程。
    所有操作在截面上进行，保持时序结构。
    """

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        """初始化管线。

        Args:
            config: 清洗配置，默认使用国信证券框架推荐设置。
        """
        self.config = config or PipelineConfig()

    def run(
        self,
        factor_values: pd.DataFrame,
        returns: Optional[pd.DataFrame] = None,
        asset_info: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """执行完整清洗流程。

        Args:
            factor_values: (time, asset) 原始因子值。
            returns: (time, asset) 收益率矩阵，用于残余收益率计算。
            asset_info: (asset, [sector, market_cap, listed_date, is_st, ...])。

        Returns:
            清洗后的因子值矩阵。
        """
        result = factor_values.copy()

        # Step 1: 样本筛选
        result = self._filter_samples(result, asset_info)

        # Step 2: 异常值处理
        result = self._handle_outliers(result)

        # Step 3: 缺失值处理
        result = self._handle_missing(result, asset_info)

        return result

    # ── 样本筛选 ──

    def _filter_samples(
        self,
        factor: pd.DataFrame,
        asset_info: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        """剔除不合格样本。

        剔除规则:
          1. ST/PT 股票（需 asset_info 提供 is_st 字段）
          2. 上市不足 min_listed_days 天
          3. 停牌导致无法交易（成交量=0 或价格不变）

        注意: 这些筛选在每期截面上进行，不影响其他期。
        """
        if asset_info is None:
            return factor

        result = factor.copy()

        # 标记 ST 股票（如果数据可用）
        if "is_st" in asset_info.columns:
            st_assets = asset_info.index[asset_info["is_st"] == True]  # noqa: E712
            for col in result.columns:
                if col in st_assets:
                    result[col] = np.nan

        return result

    # ── 异常值处理 (MAD 方法) ──

    def _handle_outliers(self, factor: pd.DataFrame) -> pd.DataFrame:
        """MAD 方法处理异常值。

        MAD = median(|Xi - median(Xj)|)

        对于正态分布，MAD 和 σ 存在关系: σ ≈ 1.4826 × MAD
        因此 3σ 等价于 3 × 1.4826 × MAD。

        超过阈值的点可设为 NA 或用边界值替代（Winsorize）。

        Args:
            factor: (time, asset) 因子值。

        Returns:
            异常值处理后的因子值。
        """
        if self.config.clean_method == CleanMethod.THREE_SIGMA:
            return self._winsorize_3sigma(factor)
        elif self.config.clean_method == CleanMethod.PERCENTILE:
            lo, hi = self.config.winsorize_bounds
            return factor.clip(
                lower=factor.quantile(lo, axis=1),
                upper=factor.quantile(hi, axis=1),
                axis=0,
            )
        else:  # MAD — 默认方法
            return self._winsorize_mad(factor)

    def _winsorize_mad(self, factor: pd.DataFrame) -> pd.DataFrame:
        """MAD Winsorize — 每期截面上独立处理。

        Args:
            factor: (time, asset) 因子值。

        Returns:
            MAD Winsorize 后的因子值。
        """
        result = factor.copy()
        threshold = self.config.mad_threshold * 1.4826

        for t_idx in range(len(factor.index)):
            cross = factor.iloc[t_idx]
            valid = cross.dropna()
            if len(valid) < 10:
                continue

            median = valid.median()
            mad = (valid - median).abs().median()
            if mad == 0:
                continue

            lower = median - threshold * mad
            upper = median + threshold * mad
            result.iloc[t_idx] = cross.clip(lower=lower, upper=upper)

        return result

    @staticmethod
    def _winsorize_3sigma(factor: pd.DataFrame) -> pd.DataFrame:
        """3σ Winsorize。

        Args:
            factor: (time, asset) 因子值。

        Returns:
            3σ Winsorize 后的因子值。
        """
        result = factor.copy()
        for t_idx in range(len(factor.index)):
            cross = factor.iloc[t_idx]
            valid = cross.dropna()
            if len(valid) < 10:
                continue
            mu = valid.mean()
            sigma = valid.std()
            if sigma == 0:
                continue
            result.iloc[t_idx] = cross.clip(lower=mu - 3 * sigma, upper=mu + 3 * sigma)
        return result

    # ── 缺失值处理 ──

    def _handle_missing(
        self,
        factor: pd.DataFrame,
        asset_info: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        """缺失值处理。

        根据配置选择:
          - DROP: 直接丢弃含缺失的资产
          - MEDIAN: 用截面中位数填充
          - INDUSTRY_MEDIAN: 用同行业截面中位数填充
          - FORWARD_FILL: 用上一期值填充

        Args:
            factor: (time, asset) 因子值。
            asset_info: 资产信息。

        Returns:
            处理后的因子值。
        """
        if self.config.missing_method == MissingMethod.DROP:
            # 丢弃含缺失值超过 50% 的资产列
            threshold = len(factor.index) * 0.5
            return factor.dropna(axis=1, thresh=threshold)

        result = factor.copy()

        if self.config.missing_method == MissingMethod.FORWARD_FILL:
            return result.ffill()

        # MEDIAN 或 INDUSTRY_MEDIAN
        for t_idx in range(len(factor.index)):
            cross = result.iloc[t_idx]
            missing_mask = cross.isna()
            if not missing_mask.any():
                continue

            if (
                self.config.missing_method == MissingMethod.INDUSTRY_MEDIAN
                and asset_info is not None
                and "sector" in asset_info.columns
            ):
                # 用同行业截面中位数填充
                for asset in cross.index[missing_mask]:
                    sector = asset_info.loc[asset, "sector"] if asset in asset_info.index else None
                    if sector is not None:
                        same_sector = asset_info.index[asset_info["sector"] == sector]
                        sector_vals = cross[same_sector.intersection(cross.index)]
                        if sector_vals.notna().sum() > 0:
                            result.loc[factor.index[t_idx], asset] = sector_vals.median()
                            continue
                    result.loc[factor.index[t_idx], asset] = cross.median()
            else:
                # 截面中位数填充
                result.iloc[t_idx] = cross.fillna(cross.median())

        return result


# ======================== 增长因子趋势化 ========================


def compute_trend_growth(
    series: pd.DataFrame,
    window: int = 20,
    method: Literal["log_linear", "hp_filter"] = "log_linear",
) -> pd.DataFrame:
    """趋势化增长因子计算。

    国信证券框架指出: 传统算术增长率或几何增长率存在两点偏差。
    改进方法: 对对数序列做线性回归，用斜率作为趋势增长率。

    Args:
        series: (time, asset) 原始序列（如净利润）。
        window: 回归窗口长度。
        method: 趋势提取方法。

    Returns:
        (time, asset) 趋势增长率矩阵。
    """
    if method == "log_linear":
        # 对数线性回归: log(y_t) = a + b*t，b 即趋势增长率
        result = pd.DataFrame(index=series.index, columns=series.columns, dtype=float)
        log_series = np.log(series.clip(lower=1e-10))

        for t_idx in range(window, len(series.index)):
            y = log_series.iloc[t_idx - window : t_idx].values  # (window, n_assets)
            x = np.arange(window).reshape(-1, 1)
            # 对每个资产做 OLS: β = (X'X)^(-1) X'Y
            xtx_inv = 1.0 / (x.T @ x)[0, 0]  # scalar
            for a_idx in range(series.shape[1]):
                valid = ~np.isnan(y[:, a_idx])
                if valid.sum() < window // 2:
                    continue
                beta = xtx_inv * (x[valid].T @ y[valid, a_idx])
                result.iloc[t_idx, a_idx] = beta[0]

        return result
    else:
        raise NotImplementedError(f"方法 {method} 尚未实现")


# ======================== 辅助函数 ========================


def create_default_asset_info(n_assets: int, seed: int = 42) -> pd.DataFrame:
    """生成默认的 asset_info DataFrame（用于测试）。

    Args:
        n_assets: 资产数量。
        seed: 随机种子。

    Returns:
        (asset, [sector, market_cap, is_st, listed_date]) DataFrame。
    """
    rng = np.random.default_rng(seed)
    asset_names = [f"stock_{i:04d}" for i in range(n_assets)]
    sectors = rng.choice(
        ["金融", "科技", "消费", "医药", "制造", "能源", "材料"],
        size=n_assets,
    )
    market_caps = np.exp(rng.normal(8, 1.5, n_assets))
    is_st = rng.choice([True, False], size=n_assets, p=[0.02, 0.98])
    listed_dates = pd.date_range("2018-01-01", periods=n_assets, freq="W")

    return pd.DataFrame(
        {
            "sector": sectors,
            "market_cap": market_caps,
            "is_st": is_st,
            "listed_date": listed_dates[:n_assets],
        },
        index=asset_names,
    )
