---
id: concept_backtest_params
type: concept
name: 回测参数
aliases: [BacktestConfig, factor backtest parameters]
status: growing
created: 2026-07-16
---

# 回测参数

## 全部可调参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `n_quantiles` | int (2-10) | 5 | 分位数。5=每组20%，2=top/bottom对半 |
| `weighting` | str | equal | 组合加权: equal/ market_cap/ style_neutral |
| `holding_periods` | int | 1 | 持仓周期(交易日): 1=日频, 5=周频, 20=月频, 60=季频 |
| `standardize` | str | plain | 标准化方法: plain(普通zscore)/ market_cap(市值加权)/ random(随机数)/ style(风格标准化) |
| `quantile_method` | str | plain | 分位数方法: plain(全市场统一)/ style(风格内分位→汇总) |
| `transform` | str | zscore | 截面变换: zscore/ rank/ winsorize/ raw |
| `clean_outliers` | bool | True | 是否 MAD 异常值清洗 |
| `clean_method` | str | mad | 清洗方法: mad/ 3sigma/ percentile |

## 标准预设

```python
from scripts.engine import PRESETS

# 1. guoxin_standard — 国信证券默认 (论文对齐)
PRESETS["guoxin_standard"]
# → 5分位, 等权, 持有1期, zscore, MAD清洗, 无行业中性

# 2. industry_neutral — 行业中性 (剥离行业暴露)
PRESETS["industry_neutral"]
# → 5分位, 市值加权, 持有1期, 行业标准化+行业分位

# 3. rank_robust — Rank稳健 (降极端值影响)
PRESETS["rank_robust"]
# → 5分位, 等权, Rank变换, 行业标准化

# 4. monthly_rebalance — 月度调仓
PRESETS["monthly_rebalance"]
# → 5分位, 市值加权, 持有20期, 行业标准化+行业分位

# 5. long_term — 季度调仓
PRESETS["long_term"]
# → 5分位, 市值加权, 持有60期, 行业中性全开
```

## 参数对结果的影响

| 参数 | 影响什么 | 为什么重要 |
|------|----------|------------|
| `n_quantiles` | 多空 spread, 单调性 | 分组越多极端组越纯粹，但每组股票越少 |
| `weighting` | 组合收益 | 等权→小票噪音大; 市值→大票主导; 风格中性→隔离因子能力 |
| `holding_periods` | Sharpe, MaxDD, 换手 | 持仓越短换手越高(交易成本越大)，但信号衰减也快 |
| `transform` | IC_IR | Rank比ZSCORE更稳健(不受极端值影响) |
| `industry_neutralize` | 行业暴露 | 关闭→因子可能只是行业偏好的代理变量 |
| `industry_quantile` | 分位均衡性 | 开启→保证每组行业分布均匀，避免某一行业主导某分位 |

## 使用示例

```python
from scripts.data import load_csi300
from scripts.factor import FactorDef, TransformMethod, build_factor
from scripts.engine import FactorBacktestEngine, PRESETS

data = load_csi300()
factor_def = FactorDef(name='momentum_1m', base='returns', window=21,
                       agg_func='sum', transform=TransformMethod.ZSCORE)
factor_values = build_factor(data, factor_def)

# 用行业中性预设回测
engine = FactorBacktestEngine(PRESETS["industry_neutral"])
result = engine.run(data, factor_values, 'momentum_1m')
```

## 相关

- [[concepts/ic-analysis]] — IC 分析
- [[concepts/factor-testing]] — 因子测试方法
- [[concepts/sharpe-ratio]] — 夏普比率
