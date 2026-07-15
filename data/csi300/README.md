# CSI300 数据集

## 来源

沪深 300 成分股日线行情 + 行业分类 + 市值，服务于 Quant Harness 因子回测框架。

## 目录结构

```
data/csi300/
├── README.md              # 本文件
├── contract.json          # 合约信息（手续费、乘数、pricetick）
├── component/             # 成分股列表
│   └── 000300.SSE         # 沪深300指数成分股代码
├── daily/                 # 个股日线 OHLCV (859 个 parquet)
│   ├── 000001.SZSE.parquet
│   ├── 000002.SZSE.parquet
│   └── ...
├── industry.parquet       # 行业分类（证监会行业，68 类）
└── market_cap.parquet     # 市值（当期 CSI300 指数权重代理）
```

## 1. daily/ — 个股日线

每个 parquet 文件代表一只股票的全部历史日线，文件名即股票代码（`000001.SZSE` = 平安银行）。

| 列 | 类型 | 说明 |
|------|------|------|
| `datetime` | datetime64[us] | 交易日 |
| `open` | float64 | 开盘价（前复权） |
| `high` | float64 | 最高价（前复权） |
| `low` | float64 | 最低价（前复权） |
| `close` | float64 | 收盘价（前复权） |
| `volume` | float64 | 成交量（股） |
| `turnover` | float64 | 成交额（元） |
| `open_interest` | int64 | 持仓量（股票恒为 0） |

示例 — 平安银行 (000001.SZSE):

```
datetime        open    high    low     close   volume      turnover
2007-01-04      2.7271  2.8518  2.5411  2.7551  3.72×10⁸   1.02×10⁹
...
2024-10-30      10.921  10.997  10.642  10.780  1.56×10⁸   1.69×10⁹

4331 个交易日, 2007-01-04 ~ 2024-10-30
```

## 2. industry.parquet — 行业分类

来源: baostock `query_stock_industry()`，证监会行业分类（2026-07-13）。

| 列 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `stock_code` | str | 股票代码（6位数字，不含交易所后缀） | `000001` |
| `industry` | str | 证监会行业名称 | `J66货币金融服务` |

```
覆盖: 857/859 只股票, 68 个行业
Top 5: 电子(82), 医药(48), 券商(42), 电气(36), 地产(35)
```

## 3. market_cap.parquet — 市值数据

来源: akshare CSI300 指数权重（2026-06-30），用指数权重作为市值代理。

| 列 | 类型 | 说明 |
|------|------|------|
| `stock_code` | str | 股票代码（6位数字） |
| `stock_name` | str | 股票名称 |
| `weight_pct` | float64 | CSI300 权重（%） |

```
覆盖: 274/859 只股票（仅当期成分股有数据）
范围: 0.036% ~ 5.008%, 中位数 0.180%
注: 权重 ≈ 流通市值 / CSI300总流通市值，可作市值代理
```

## 股票代码格式

| 交易所 | 后缀 | 代码范围 |
|--------|------|----------|
| 深圳证券交易所 | `.SZSE` | 000xxx, 002xxx, 300xxx |
| 上海证券交易所 | `.SSE` | 600xxx, 601xxx, 603xxx, 688xxx |

> industry.parquet 和 market_cap.parquet 使用 6 位短码（无后缀），`load_csi300()` 自动匹配。

## 加载方式

```python
from scripts.data import load_csi300

data = load_csi300()
# → MarketData
#   .prices      859 × 3465  (2010-07-23 ~ 2024-10-30)
#   .volumes     859 × 3465
#   .highs       859 × 3465
#   .lows        859 × 3465
#   .opens       859 × 3465
#   .asset_info  (sector, market_cap)  ← 自动加载 industry + market_cap
#   .freq        Freq.DAILY

# asset_info 示例:
data.asset_info.head()
#              sector              market_cap
# 000001.SZSE  J66货币金融服务       0.345
# 000002.SZSE  K70房地产业           0.071
```

> 注: 自动过滤了前 20% 时间段（IPO 少、数据质量差），实际可用 3465 个交易日而非 4331 个。

## 用途

此数据集驱动以下 Harness 能力:

| 能力 | 依赖数据 |
|------|----------|
| 因子值计算 (`build_factor`) | daily/ OHLCV |
| 数据清洗 (`DataPipeline`) | daily/ OHLCV |
| 行业标准化 (`StyleNeutralizer._style_zscore`) | industry.parquet |
| 行业分位 (`StyleNeutralizer._style_quantile`) | industry.parquet |
| 残余收益率 (`StyleNeutralizer.residualize_returns`) | industry.parquet |
| 市值加权 (`StyleNeutralizer._market_cap_zscore`) | market_cap.parquet |
| 行业暴露分析 (`compute_ic_by_industry`) | industry.parquet |
| 风格分类 (大盘/中盘/小盘) | market_cap.parquet |
