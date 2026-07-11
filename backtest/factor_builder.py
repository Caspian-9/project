"""因子构建器 — 将因子定义转化为可计算因子值矩阵。

支持:
  1. 基础因子: 从 MarketData 直接计算（如 returns_1m, volume_ratio）
  2. 变换因子: 对已有因子做标准化/去极值/中性化
  3. 组合因子: 多个因子的线性组合或非线性组合

设计原则: 每个因子用一个 FactorDef 描述，build_factor 将其编译为 (time, asset) 矩阵。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import pandas as pd

from backtest.data import MarketData


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
