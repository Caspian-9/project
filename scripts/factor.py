"""因子构建与风格中性化。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import pandas as pd

from scripts.data import MarketData


# ======================== 因子定义 DSL ========================


class TransformMethod(Enum):
    """因子变换方法。"""

    RAW = "raw"  # 不做变换
    ZSCORE = "zscore"  # 截面标准化 (减均值/除标准差)
    RANK = "rank"  # 截面排序 (0~1)
    PERCENTILE = "percentile"  # 截面分位数
    WINSORIZE = "winsorize"  # 去极值 (截尾)
    NEUTRALIZE = "neutralize"  # 风格/行业中性化


@dataclass
class FactorDef:
    """单个因子的完整定义。

    示例:
        # 1个月动量因子
        FactorDef(
            name="momentum_1m",
            base="returns",
            window=21,
            transform=TransformMethod.ZSCORE,
        )

        # 波动率因子
        FactorDef(
            name="volatility_1m",
            base="returns",
            window=21,
            agg_func="std",
            transform=TransformMethod.ZSCORE,
        )
    """

    name: str  # 因子唯一标识
    base: str  # 基元数据: "returns", "volume", "price", "high", "low", "open"
    window: int = 20  # 回溯窗口长度
    agg_func: str = "sum"  # 聚合函数: "sum", "mean", "std", "max", "min"
    transform: TransformMethod = TransformMethod.RAW
    transform_params: dict[str, Any] = field(default_factory=dict)

    # 可选: 直接引用已有因子名（组合因子用）
    depends_on: Optional[str] = None

    # 运算模式: None=纯滚动聚合, "ratio"=当前值/滚动值, "diff"=当前值-滚动值
    # 例: GH动量 = price / rolling_max(price, 130) → operation="ratio", agg_func="max"
    operation: Optional[str] = None  # None | "ratio" | "diff"


@dataclass
class FactorTransform:
    """因子变换 — 标准化/去极值/中性化 的配置。

    用于对已有因子值 (pd.DataFrame) 做后处理。
    """

    method: TransformMethod
    params: dict[str, Any] = field(default_factory=dict)

    def apply(self, factor: pd.DataFrame) -> pd.DataFrame:
        """对因子矩阵应用变换。

        Args:
            factor: (time, asset) 因子值。

        Returns:
            变换后的因子值。
        """
        if self.method == TransformMethod.RAW:
            return factor
        elif self.method == TransformMethod.ZSCORE:
            return factor.sub(factor.mean(axis=1), axis=0).div(
                factor.std(axis=1).replace(0, 1), axis=0
            )
        elif self.method == TransformMethod.RANK:
            return factor.rank(axis=1, pct=True)
        elif self.method == TransformMethod.PERCENTILE:
            return factor.rank(axis=1, pct=True)
        elif self.method == TransformMethod.WINSORIZE:
            lower = self.params.get("lower", 0.01)
            upper = self.params.get("upper", 0.99)
            return factor.clip(
                lower=factor.quantile(lower, axis=1),
                upper=factor.quantile(upper, axis=1),
                axis=0,
            )
        else:
            return factor


@dataclass
class CompositeFactor:
    """组合因子 — 多个因子的加权组合。

    示例:
        CompositeFactor(
            name="combo_momentum_vol",
            components=[
                ("momentum_1m", 0.6),
                ("volatility_1m", -0.4),
            ],
            transform=TransformMethod.ZSCORE,
        )
    """

    name: str
    components: list[tuple[str, float]]  # [(factor_name, weight), ...]
    transform: TransformMethod = TransformMethod.ZSCORE


# ======================== 因子计算引擎 ========================


def _get_current_values(data: MarketData, base: str) -> pd.DataFrame:
    """获取当前值矩阵（非滚动），用于 ratio/diff 运算。

    Args:
        data: 市场数据。
        base: 基元类型。

    Returns:
        (time, asset) 当前值矩阵。
    """
    base_map: dict[str, pd.DataFrame] = {
        "returns": data.returns,
        "price": data.prices,
        "volume": data.volumes,
        "high": data.highs if data.highs is not None else data.prices,
        "low": data.lows if data.lows is not None else data.prices,
        "open": data.opens if data.opens is not None else data.prices,
    }
    result = base_map.get(base)
    if result is None:
        raise ValueError(f"不支持的基元类型: {base}")
    return result


def _compute_base_factor(
    data: MarketData,
    base: str,
    window: int,
    agg_func: str = "sum",
) -> pd.DataFrame:
    """从 MarketData 计算基础因子。

    Args:
        data: 市场数据。
        base: 基元类型。
        window: 回溯窗口。
        agg_func: 聚合方式。

    Returns:
        (time, asset) 因子值矩阵。
    """
    # 选择底层数据
    base_map: dict[str, pd.DataFrame] = {
        "returns": data.returns,
        "price": data.prices,
        "volume": data.volumes,
        "high": data.highs if data.highs is not None else data.prices,
        "low": data.lows if data.lows is not None else data.prices,
        "open": data.opens if data.opens is not None else data.prices,
    }
    series = base_map.get(base)
    if series is None:
        raise ValueError(f"不支持的基元类型: {base}")

    # 滚动聚合
    agg_map: dict[str, Callable[..., pd.DataFrame]] = {
        "sum": lambda x: x.rolling(window).sum(),
        "mean": lambda x: x.rolling(window).mean(),
        "std": lambda x: x.rolling(window).std(),
        "max": lambda x: x.rolling(window).max(),
        "min": lambda x: x.rolling(window).min(),
    }
    agg = agg_map.get(agg_func)
    if agg is None:
        raise ValueError(f"不支持的聚合函数: {agg_func}")

    return agg(series)


def build_factor(
    data: MarketData,
    factor_def: FactorDef,
    existing_factors: Optional[dict[str, pd.DataFrame]] = None,
) -> pd.DataFrame:
    """从 FactorDef 构建因子值矩阵。

    Args:
        data: 市场数据。
        factor_def: 因子定义。
        existing_factors: 已构建的因子字典（用于组合因子的依赖引用）。

    Returns:
        (time, asset) 因子值矩阵。
    """
    # 如果是依赖已有因子
    if factor_def.depends_on and existing_factors:
        factor = existing_factors.get(factor_def.depends_on)
        if factor is None:
            raise ValueError(f"依赖因子 '{factor_def.depends_on}' 未找到")
    else:
        factor = _compute_base_factor(
            data, factor_def.base, factor_def.window, factor_def.agg_func
        )

    # 应用 operation（ratio/diff）：当前值 vs 滚动聚合值
    if factor_def.operation == "ratio":
        current = _get_current_values(data, factor_def.base)
        aligned = current.loc[factor.index][factor.columns]
        factor = aligned / factor.replace(0, float("nan"))
    elif factor_def.operation == "diff":
        current = _get_current_values(data, factor_def.base)
        aligned = current.loc[factor.index][factor.columns]
        factor = aligned - factor

    # 应用变换
    transform = FactorTransform(factor_def.transform, factor_def.transform_params)
    return transform.apply(factor)


def build_composite_factor(
    data: MarketData,
    composite: CompositeFactor,
    component_defs: list[FactorDef],
) -> pd.DataFrame:
    """构建组合因子。

    Args:
        data: 市场数据。
        composite: 组合因子定义。
        component_defs: 各组分因子的 FactorDef 列表。

    Returns:
        (time, asset) 组合因子值矩阵。
    """
    # 先构建所有组件因子
    component_factors: dict[str, pd.DataFrame] = {}
    for factor_def in component_defs:
        component_factors[factor_def.name] = build_factor(data, factor_def)

    # 加权组合
    result: Optional[pd.DataFrame] = None
    for factor_name, weight in composite.components:
        factor = component_factors.get(factor_name)
        if factor is None:
            raise ValueError(f"组件因子 '{factor_name}' 未在 component_defs 中定义")
        weighted = factor * weight
        if result is None:
            result = weighted
        else:
            result = result + weighted

    if result is None:
        raise ValueError("组合因子至少需要一个组件")

    # 最终变换
    transform = FactorTransform(composite.transform)
    return transform.apply(result)


def parse_factor_expr(expr: str) -> FactorDef:
    """从简单表达式解析因子定义。

    支持的表达式格式:
      - "returns_20_sum" → base=returns, window=20, agg=sum
      - "returns_60_std" → base=returns, window=60, agg=std
      - "volume_10_mean" → base=volume, window=10, agg=mean

    Args:
        expr: 因子表达式字符串。

    Returns:
        FactorDef 实例。
    """
    parts = expr.split("_")
    if len(parts) < 3:
        raise ValueError(f"无法解析因子表达式: {expr}，格式: base_window_agg")

    base = parts[0]
    try:
        window = int(parts[1])
    except ValueError:
        raise ValueError(f"窗口必须是整数: {parts[1]}")

    agg = parts[2]

    valid_bases = {"returns", "price", "volume", "high", "low", "open"}
    valid_aggs = {"sum", "mean", "std", "max", "min"}

    if base not in valid_bases:
        raise ValueError(f"不支持的 base: {base}，可选: {valid_bases}")
    if agg not in valid_aggs:
        raise ValueError(f"不支持的 agg: {agg}，可选: {valid_aggs}")

    return FactorDef(name=expr, base=base, window=window, agg_func=agg)

from dataclasses import dataclass
from enum import Enum

import numpy as np


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
