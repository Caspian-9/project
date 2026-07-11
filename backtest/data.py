"""市场数据加载与合成数据生成。

支持真实数据加载（CSV/Parquet）和合成数据生成（用于测试）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


class Freq(Enum):
    """数据频率。"""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    MINUTE_5 = "5min"


@dataclass
class MarketData:
    """标准化市场数据结构。

    所有 OHLCV 数据按 (time, asset) 的双重索引组织，
    time 为 pd.Timestamp，asset 为 str。
    """

    prices: pd.DataFrame  # (time, asset) → close price
    volumes: pd.DataFrame  # (time, asset) → volume
    highs: Optional[pd.DataFrame] = None  # (time, asset) → high
    lows: Optional[pd.DataFrame] = None  # (time, asset) → low
    opens: Optional[pd.DataFrame] = None  # (time, asset) → open
    freq: Freq = Freq.DAILY

    # 辅助信息
    asset_info: Optional[pd.DataFrame] = None  # (asset, [sector, market_cap, ...])
    benchmark_prices: Optional[pd.Series] = None  # (time,) → benchmark close

    def __post_init__(self) -> None:
        """校验数据完整性。"""
        if self.prices.empty:
            raise ValueError("prices 不能为空")
        if self.prices.index.name != "time":
            self.prices.index.name = "time"
        if self.volumes is None:
            self.volumes = pd.DataFrame(
                1.0, index=self.prices.index, columns=self.prices.columns
            )

    @property
    def n_assets(self) -> int:
        """资产数量。"""
        return self.prices.shape[1]

    @property
    def n_periods(self) -> int:
        """时间周期数。"""
        return self.prices.shape[0]

    @property
    def assets(self) -> list[str]:
        """资产列表。"""
        return list(self.prices.columns)

    @property
    def returns(self) -> pd.DataFrame:
        """简单收益率矩阵 (time, asset)。"""
        return self.prices.pct_change().iloc[1:]


def generate_synthetic_data(
    n_assets: int = 100,
    n_periods: int = 500,
    freq: Freq = Freq.DAILY,
    seed: int = 42,
) -> MarketData:
    """生成合成市场数据用于测试。

    生成具有截面相关性和时序自相关的模拟价格序列，
    以及行业和市值辅助信息。

    Args:
        n_assets: 资产数量。
        n_periods: 时间周期数。
        freq: 数据频率。
        seed: 随机种子。

    Returns:
        MarketData 实例。
    """
    rng = np.random.default_rng(seed)

    # 生成日期索引
    if freq == Freq.DAILY:
        dates = pd.date_range("2020-01-01", periods=n_periods, freq="B")
    elif freq == Freq.WEEKLY:
        dates = pd.date_range("2020-01-01", periods=n_periods, freq="W")
    else:
        dates = pd.date_range("2020-01-01", periods=n_periods, freq="ME")

    # 资产名
    asset_names = [f"stock_{i:04d}" for i in range(n_assets)]

    # 生成因子暴露矩阵 (n_assets × 3)
    # 三个潜在因子: 规模、价值、动量
    factor_exposures = rng.normal(0, 1, (n_assets, 3))
    # 行业分类 (5 个行业)
    sectors = rng.choice(["金融", "科技", "消费", "医药", "制造"], size=n_assets)
    # 市值 (对数正态)
    market_caps = np.exp(rng.normal(8, 1.5, n_assets))

    # 生成因子收益 (n_periods × 3)
    factor_returns = rng.normal(0.0005, 0.015, (n_periods, 3))

    # 生成特质收益
    idiosyncratic = rng.normal(0, 0.02, (n_periods, n_assets))

    # 收益率 = 因子暴露 × 因子收益 + 特质收益
    returns_matrix = factor_exposures @ factor_returns.T + idiosyncratic.T
    returns_df = pd.DataFrame(returns_matrix.T, index=dates, columns=asset_names)

    # 从收益构建价格
    prices_df = (1 + returns_df).cumprod()
    prices_df.iloc[0] = 1.0

    # 成交量 (对数正态)
    volumes_df = pd.DataFrame(
        np.exp(rng.normal(12, 0.8, (n_periods, n_assets))),
        index=dates,
        columns=asset_names,
    )

    # 辅助信息
    asset_info = pd.DataFrame(
        {
            "sector": sectors,
            "market_cap": market_caps,
        },
        index=asset_names,
    )

    # 基准价格 (等权)
    benchmark = prices_df.mean(axis=1)

    return MarketData(
        prices=prices_df,
        volumes=volumes_df,
        freq=freq,
        asset_info=asset_info,
        benchmark_prices=benchmark,
    )


def load_market_data(
    path: Path,
    freq: Freq = Freq.DAILY,
) -> MarketData:
    """从文件加载市场数据。

    支持 CSV 和 Parquet 格式。
    预期格式: (time, asset) 双重索引或 long format。

    Args:
        path: 数据文件路径。
        freq: 数据频率。

    Returns:
        MarketData 实例。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 文件格式不支持。
    """
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    elif suffix in (".parquet", ".pq"):
        df = pd.read_parquet(path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}，仅支持 .csv 和 .parquet")

    # 尝试推断结构
    if "asset" in df.columns and "time" in df.columns:
        # Long format: pivot
        prices = df.pivot(index="time", columns="asset", values="close")
    else:
        prices = df

    return MarketData(prices=prices, volumes=pd.DataFrame(1.0, index=prices.index, columns=prices.columns), freq=freq)
