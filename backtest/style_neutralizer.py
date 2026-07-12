"""四层风格过滤 — 国信证券因子回溯测试框架的风格中性化体系。

参考: 国信证券《多因子研究系列（一）》(2012.08.22) 第 5-6 页

四层过滤（从不同角度剔除风格影响）:
  Layer 1: 标准化 — 从 IC 角度过滤（普通/市值加权/风格标准化/随机数标准化）
  Layer 2: 分位数 — 从 IC 角度过滤（普通分位/风格内分位）
  Layer 3: 组合权重 — 从收益率角度过滤（等权/市值加权/风格中性权重）
  Layer 4: 残余收益率 — 直接从个股收益中剔除风格板块收益

四层的关系:
  - 标准化、分位数、残余收益率 → 影响 IC（因子预测能力）
  - 权重 → 影响收益率（组合表现）
  - 风格分位 + 市值加权 ≈ 普通分位 + 风格中性权重（当指数权重与市值一致时）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


# ======================== 枚举定义 ========================


class StandardizeMethod(Enum):
    """因子标准化方法。"""

    PLAIN = "plain"  # 普通 z-score
    MARKET_CAP = "market_cap"  # 市值加权 z-score
    RANDOM = "random"  # 随机数标准化（保留分布形状）
    STYLE = "style"  # 风格内标准化（如行业标准化）


class QuantileMethod(Enum):
    """分位数方法。"""

    PLAIN = "plain"  # 全市场统一分位
    STYLE = "style"  # 风格内部分位 → 汇总（保证每组风格均匀）


class WeightMethod(Enum):
    """组合权重方法。"""

    EQUAL = "equal"  # 等权
    MARKET_CAP = "market_cap"  # 市值加权
    STYLE_NEUTRAL = "style_neutral"  # 风格中性权重


@dataclass
class NeutralizerConfig:
    """风格中性化配置。"""

    standardize: StandardizeMethod = StandardizeMethod.PLAIN
    quantile: QuantileMethod = QuantileMethod.PLAIN
    weight: WeightMethod = WeightMethod.EQUAL
    residualize: bool = False  # 是否启用残余收益率

    # 风格维度（用于 STYLE 方法）
    style_column: str = "sector"  # asset_info 中的风格列名


# ======================== 中性化执行器 ========================


class StyleNeutralizer:
    """四层风格过滤执行器。

    对因子值矩阵和收益率矩阵，按配置执行四层过滤。
    """

    def __init__(self, config: Optional[NeutralizerConfig] = None) -> None:
        """初始化中性化器。

        Args:
            config: 中性化配置。
        """
        self.config = config or NeutralizerConfig()

    # ── Layer 1: 标准化 ──

    def standardize(
        self,
        factor: pd.DataFrame,
        asset_info: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """因子标准化 — Layer 1。

        Args:
            factor: (time, asset) 因子值。
            asset_info: (asset, [market_cap, sector, ...]) 资产信息。

        Returns:
            标准化后的因子值。
        """
        method = self.config.standardize

        if method == StandardizeMethod.PLAIN:
            return self._plain_zscore(factor)
        elif method == StandardizeMethod.MARKET_CAP:
            return self._market_cap_zscore(factor, asset_info)
        elif method == StandardizeMethod.STYLE:
            return self._style_zscore(factor, asset_info)
        elif method == StandardizeMethod.RANDOM:
            return self._random_standardize(factor)
        else:
            return factor

    @staticmethod
    def _plain_zscore(factor: pd.DataFrame) -> pd.DataFrame:
        """普通 z-score 标准化。

        z = (x - μ) / σ, 每期截面上独立计算。
        """
        mu = factor.mean(axis=1)
        sigma = factor.std(axis=1).replace(0, 1.0)
        return factor.sub(mu, axis=0).div(sigma, axis=0)

    @staticmethod
    def _market_cap_zscore(
        factor: pd.DataFrame,
        asset_info: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        """市值加权 z-score 标准化。

        均值使用市值加权平均，标准差仍用等权。
        考虑了规模对均值的影响。
        """
        if asset_info is None or "market_cap" not in asset_info.columns:
            return StyleNeutralizer._plain_zscore(factor)

        result = pd.DataFrame(index=factor.index, columns=factor.columns, dtype=float)

        for t_idx in range(len(factor.index)):
            cross = factor.iloc[t_idx].dropna()
            common = cross.index.intersection(asset_info.index)
            cross = cross[common]

            if len(cross) < 10:
                continue

            weights = asset_info.loc[common, "market_cap"]
            weights = weights / weights.sum()
            mu_weighted = (cross * weights).sum()

            sigma = cross.std()
            if sigma == 0:
                sigma = 1.0

            result.iloc[t_idx] = (factor.iloc[t_idx] - mu_weighted) / sigma

        return result

    @staticmethod
    def _style_zscore(
        factor: pd.DataFrame,
        asset_info: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        """风格标准化 — 在每个风格内部做 z-score。

        例如行业标准化: z_i = (x_i - μ_industry) / σ_industry。
        这样每个行业内部的因子值均值为 0，标准差为 1。
        """
        config = NeutralizerConfig()  # 使用默认 style_column
        style_col = config.style_column

        if asset_info is None or style_col not in asset_info.columns:
            return StyleNeutralizer._plain_zscore(factor)

        result = pd.DataFrame(index=factor.index, columns=factor.columns, dtype=float)

        for t_idx in range(len(factor.index)):
            cross = factor.iloc[t_idx].dropna()
            common = cross.index.intersection(asset_info.index)
            cross = cross[common]

            if len(cross) < 10:
                continue

            styles = asset_info.loc[common, style_col]
            for style_name in styles.unique():
                style_assets = styles[styles == style_name].index
                style_vals = cross[style_assets.intersection(cross.index)]
                if len(style_vals) < 3:
                    continue
                mu_s = style_vals.mean()
                sigma_s = style_vals.std()
                if sigma_s == 0:
                    sigma_s = 1.0
                for a in style_vals.index:
                    result.loc[factor.index[t_idx], a] = (
                        factor.iloc[t_idx][a] - mu_s
                    ) / sigma_s

        return result.fillna(0.0)

    @staticmethod
    def _random_standardize(factor: pd.DataFrame) -> pd.DataFrame:
        """随机数标准化。

        根据因子值的截面分布随机生成标准化得分。
        优点: 将因子值转换为服从特定分布的得分，保留分布形状。
        缺点: 丢失了原始因子值的相对大小信息。
        """
        result = pd.DataFrame(index=factor.index, columns=factor.columns, dtype=float)

        for t_idx in range(len(factor.index)):
            cross = factor.iloc[t_idx].dropna()
            if len(cross) < 10:
                continue
            # 按因子值的秩，映射到标准正态分位数
            ranks = cross.rank(pct=True)
            result.iloc[t_idx] = pd.Series(
                np.random.normal(0, 1, len(factor.columns)),
                index=factor.columns,
            )
            # 保留排序关系
            sorted_idx = cross.sort_values().index
            for rank_i, asset in enumerate(sorted_idx):
                result.iloc[t_idx, factor.columns.get_loc(asset)] = (
                    ranks[asset] - 0.5
                ) * 4  # 映射到 ~N(0,2)

        return result.fillna(0.0)

    # ── Layer 2: 分位数 ──

    def compute_quantile_labels(
        self,
        factor: pd.DataFrame,
        n_quantiles: int = 5,
        asset_info: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """计算分位标签 — Layer 2。

        Args:
            factor: (time, asset) 因子值。
            n_quantiles: 分位数。
            asset_info: 资产信息。

        Returns:
            (time, asset) 分位标签 (0 ~ n_quantiles-1)。
        """
        if self.config.quantile == QuantileMethod.PLAIN:
            return self._plain_quantile(factor, n_quantiles)
        elif self.config.quantile == QuantileMethod.STYLE:
            return self._style_quantile(factor, n_quantiles, asset_info)
        else:
            return self._plain_quantile(factor, n_quantiles)

    @staticmethod
    def _plain_quantile(
        factor: pd.DataFrame,
        n_quantiles: int = 5,
    ) -> pd.DataFrame:
        """普通分位数 — 全市场统一划分。"""
        result = pd.DataFrame(index=factor.index, columns=factor.columns, dtype=float)
        for t_idx in range(len(factor.index)):
            cross = factor.iloc[t_idx].dropna()
            if len(cross) < n_quantiles * 3:
                continue
            labels = pd.qcut(cross, n_quantiles, labels=False, duplicates="drop")
            for a in labels.index:
                result.loc[factor.index[t_idx], a] = labels[a]
        return result

    @staticmethod
    def _style_quantile(
        factor: pd.DataFrame,
        n_quantiles: int = 5,
        asset_info: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """风格内分位数 — 每个风格内部分组，保证各组风格均匀。

        例如: 先在每个行业内分 5 组，再把所有行业的 Q1 合并为全市场 Q1。
        这样 Q1~Q5 中每个行业的股票数量大致相等。
        """
        config = NeutralizerConfig()
        style_col = config.style_column

        if asset_info is None or style_col not in asset_info.columns:
            return StyleNeutralizer._plain_quantile(factor, n_quantiles)

        result = pd.DataFrame(index=factor.index, columns=factor.columns, dtype=float)

        for t_idx in range(len(factor.index)):
            cross = factor.iloc[t_idx].dropna()
            common = cross.index.intersection(asset_info.index)
            cross = cross[common]

            if len(cross) < n_quantiles * 3:
                continue

            styles = asset_info.loc[common, style_col]
            for style_name in styles.unique():
                style_assets = styles[styles == style_name].index
                style_vals = cross[style_assets.intersection(cross.index)]
                if len(style_vals) < n_quantiles:
                    continue
                try:
                    labels = pd.qcut(
                        style_vals, n_quantiles, labels=False, duplicates="drop"
                    )
                    for a in labels.index:
                        result.loc[factor.index[t_idx], a] = labels[a]
                except ValueError:
                    continue

        return result

    # ── Layer 3: 组合权重 ──

    def compute_weights(
        self,
        quantile_labels: pd.DataFrame,
        target_quantile: int,
        asset_info: Optional[pd.DataFrame] = None,
        benchmark_weights: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        """计算组合内权重 — Layer 3。

        Args:
            quantile_labels: (time, asset) 分位标签。
            target_quantile: 目标分位（如选 Q4 即 top 组）。
            asset_info: 资产信息。
            benchmark_weights: 基准指数中各资产的权重。

        Returns:
            (time, asset) 组合权重矩阵。
        """
        weights = pd.DataFrame(
            0.0, index=quantile_labels.index, columns=quantile_labels.columns
        )

        for t_idx in range(len(quantile_labels.index)):
            mask = quantile_labels.iloc[t_idx] == target_quantile
            selected = mask[mask].index
            n = len(selected)
            if n == 0:
                continue

            if self.config.weight == WeightMethod.EQUAL:
                weights.loc[quantile_labels.index[t_idx], selected] = 1.0 / n

            elif self.config.weight == WeightMethod.MARKET_CAP:
                if asset_info is not None and "market_cap" in asset_info.columns:
                    caps = asset_info.loc[selected, "market_cap"]
                    total = caps.sum()
                    if total > 0:
                        weights.loc[quantile_labels.index[t_idx], selected] = caps / total
                    else:
                        weights.loc[quantile_labels.index[t_idx], selected] = 1.0 / n
                else:
                    weights.loc[quantile_labels.index[t_idx], selected] = 1.0 / n

            elif self.config.weight == WeightMethod.STYLE_NEUTRAL:
                # 风格中性权重 = 市值权重 × (基准中该风格的权重 / 组合中该风格的权重)
                if (
                    asset_info is not None
                    and "market_cap" in asset_info.columns
                    and "sector" in asset_info.columns
                    and benchmark_weights is not None
                ):
                    weights.loc[quantile_labels.index[t_idx], selected] = (
                        self._style_neutral_weights(
                            selected, asset_info, benchmark_weights
                        )
                    )
                else:
                    weights.loc[quantile_labels.index[t_idx], selected] = 1.0 / n

        return weights

    @staticmethod
    def _style_neutral_weights(
        selected: pd.Index,
        asset_info: pd.DataFrame,
        benchmark_weights: pd.Series,
    ) -> pd.Series:
        """计算风格中性权重。

        确保组合在各风格上的权重与基准一致。
        """
        common = selected.intersection(asset_info.index).intersection(
            benchmark_weights.index
        )
        caps = asset_info.loc[common, "market_cap"]
        sectors = asset_info.loc[common, "sector"]

        result = pd.Series(0.0, index=common)
        for sector in sectors.unique():
            sector_assets = sectors[sectors == sector].index
            sector_caps = caps[sector_assets]
            sector_weight_in_benchmark = benchmark_weights[sector_assets].sum()
            sector_weight_in_portfolio = sector_caps.sum() / caps.sum()

            if sector_weight_in_portfolio > 0:
                adj_factor = (
                    sector_weight_in_benchmark / sector_weight_in_portfolio
                )
                result[sector_assets] = (
                    sector_caps / sector_caps.sum() * adj_factor
                )

        # 重新归一化
        total = result.sum()
        if total > 0:
            result = result / total
        return result

    # ── Layer 4: 残余收益率 ──

    @staticmethod
    def residualize_returns(
        returns: pd.DataFrame,
        asset_info: Optional[pd.DataFrame],
        style_column: str = "sector",
    ) -> pd.DataFrame:
        """残余收益率 — 直接从个股收益中剔除风格板块收益。

        对于每个资产 i: r_residual_i = r_i - r_style(i)
        其中 r_style(i) 是资产 i 所属风格板块的等权平均收益。

        这是最直接的风格中性化方法。

        Args:
            returns: (time, asset) 收益率。
            asset_info: 资产信息。
            style_column: 风格列名。

        Returns:
            残余收益率矩阵。
        """
        if asset_info is None or style_column not in asset_info.columns:
            return returns

        result = returns.copy()

        for t_idx in range(len(returns.index)):
            cross = returns.iloc[t_idx].dropna()
            common = cross.index.intersection(asset_info.index)
            cross = cross[common]
            if len(cross) < 10:
                continue

            styles = asset_info.loc[common, style_column]
            for style_name in styles.unique():
                style_assets = styles[styles == style_name].index
                style_assets_common = style_assets.intersection(cross.index)
                if len(style_assets_common) < 3:
                    continue
                style_mean_return = cross[style_assets_common].mean()
                for a in style_assets_common:
                    result.loc[returns.index[t_idx], a] = (
                        returns.iloc[t_idx][a] - style_mean_return
                    )

        return result
