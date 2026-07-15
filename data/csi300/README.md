# CSI300 日线数据

## 来源

沪深 300 成分股日线行情，前复权。

## 目录结构

```
data/csi300/
├── README.md           # 本文件
├── contract.json       # 合约信息（手续费、乘数、pricetick）
├── component/          # 成分股列表
│   └── 000300.SSE      # 沪深300指数成分股代码
└── daily/              # 个股日线 (859 个 parquet)
    ├── 000001.SZSE.parquet
    ├── 000002.SZSE.parquet
    └── ...
```

## Parquet 数据结构

每个文件代表一只股票的全部历史日线，文件名即股票代码（如 `000001.SZSE` = 平安银行）。

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

## 示例

```
000001.SZSE (平安银行):
  datetime            open    high    low     close   volume      turnover
  2007-01-04          2.7271  2.8518  2.5411  2.7551  3.72×10⁸   1.02×10⁹
  2007-01-05          2.5930  2.5930  2.4790  2.5523  2.89×10⁸   7.15×10⁸
  ...
  2024-10-30          10.921  10.997  10.642  10.780  1.56×10⁸   1.69×10⁹

  4331 个交易日, 2007-01-04 ~ 2024-10-30
```

## 加载方式

```python
from scripts.data import load_csi300

data = load_csi300()
# → MarketData(prices, volumes, highs, lows, opens)
#   859 stocks × 3465 trading days (2010-07-23 ~ 2024-10-30)
#   注: 自动过滤了前20%时间段(IPO少、数据质量差)
```

## 股票代码格式

- `.SZSE` — 深圳证券交易所（000xxx, 002xxx, 300xxx）
- `.SSE` — 上海证券交易所（600xxx, 601xxx, 603xxx, 688xxx）
