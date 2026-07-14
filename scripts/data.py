"""数据加载与清洗管线。"""

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

from dataclasses import dataclass
from enum import Enum
from typing import Literal



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

def load_csi300(data_dir: str = "data/csi300") -> MarketData:
    """加载沪深300成分股日线数据，构建MarketData。

    Args:
        data_dir: CSI300数据目录路径。

    Returns:
        MarketData实例，含prices/volumes/highs/lows/opens。
    """
    import pandas as pd
    from pathlib import Path

    daily_dir = Path(data_dir) / "daily"
    if not daily_dir.exists():
        raise FileNotFoundError(f"CSI300数据目录不存在: {daily_dir}")

    # 读取所有parquet文件
    frames: dict[str, pd.DataFrame] = {}
    for f in sorted(daily_dir.glob("*.parquet")):
        symbol = f.stem  # e.g. 000001.SZSE
        df = pd.read_parquet(f)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        frames[symbol] = df

    if not frames:
        raise ValueError("未找到任何parquet文件")

    # 对齐时间轴，构建统一矩阵
    # 使用价格列构建 (time, asset) 面板
    all_times = sorted(set().union(*[set(df.index) for df in frames.values()]))
    assets = sorted(frames.keys())

    prices = pd.DataFrame(index=all_times, columns=assets, dtype=float)
    volumes = pd.DataFrame(index=all_times, columns=assets, dtype=float)
    highs = pd.DataFrame(index=all_times, columns=assets, dtype=float)
    lows = pd.DataFrame(index=all_times, columns=assets, dtype=float)
    opens = pd.DataFrame(index=all_times, columns=assets, dtype=float)

    for symbol, df in frames.items():
        prices.loc[df.index, symbol] = df["close"]
        volumes.loc[df.index, symbol] = df["volume"]
        if "high" in df.columns:
            highs.loc[df.index, symbol] = df["high"]
        if "low" in df.columns:
            lows.loc[df.index, symbol] = df["low"]
        if "open" in df.columns:
            opens.loc[df.index, symbol] = df["open"]

    # Forward fill missing values (停牌日)
    prices = prices.ffill()
    volumes = volumes.fillna(0.0)

    # 过滤：保留至少有100只股票有数据的日期
    min_assets = max(50, len(assets) // 6)
    valid_times = prices.notna().sum(axis=1) >= min_assets
    prices = prices.loc[valid_times]
    volumes = volumes.loc[valid_times]
    highs = highs.loc[valid_times]
    lows = lows.loc[valid_times]
    opens = opens.loc[valid_times]

    # 过滤：去除前20%时间段（IPO少，数据质量差）
    start_idx = len(prices) // 5
    prices = prices.iloc[start_idx:]
    volumes = volumes.iloc[start_idx:]
    highs = highs.iloc[start_idx:]
    lows = lows.iloc[start_idx:]
    opens = opens.iloc[start_idx:]

    print(f"CSI300: {len(assets)}只股票, {len(prices)}个交易日, {prices.index[0].date()}~{prices.index[-1].date()}")

    return MarketData(
        prices=prices,
        volumes=volumes,
        highs=highs,
        lows=lows,
        opens=opens,
        freq=Freq.DAILY,
    )

