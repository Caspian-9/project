---
id: factor_price_vol_3m
type: factor
name: price_vol_3m
category: 波动
status: growing
ic_ir: -0.076
ic_mean: -0.0146
sharpe: -0.249
grade: D
decision: discard
backtest_date: 2026-07-15
---

# price_vol_3m

- **类别**: 波动
- **IC_IR**: -0.076 | **IC均值**: -0.0146
- **多空Sharpe**: -0.249 | **MaxDD**: -69.4%
- **单调性**: N | **评级**: D | **决策**: discard

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | 14.23% |
| Q1 | 12.05% |
| Q2 | 9.88% |
| Q3 | 8.83% |
| Q4 | 9.51% |

## 评价

- IC_IR=-0.08，预测能力偏弱
- 分层收益不单调，存在非线性关系或分组间差异小
- 最大回撤=-69.4%，回撤控制需改善

## 相关
- [[concepts/ic-analysis]]
