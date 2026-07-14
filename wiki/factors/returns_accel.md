---
id: factor_returns_accel
type: factor
name: returns_accel
category: 动量
status: growing
ic_ir: -0.123
ic_mean: -0.0237
sharpe: 0.452
grade: D
decision: discard
backtest_date: 2026-07-15
---

# returns_accel

- **类别**: 动量
- **IC_IR**: -0.123 | **IC均值**: -0.0237
- **多空Sharpe**: 0.452 | **MaxDD**: -48.1%
- **单调性**: N | **评级**: D | **决策**: discard

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | 5.85% |
| Q1 | 8.92% |
| Q2 | 13.81% |
| Q3 | 16.14% |
| Q4 | 14.89% |

## 评价

- IC_IR=-0.12，预测能力偏弱
- 分层收益不单调，存在非线性关系或分组间差异小
- 最大回撤=-48.1%，回撤控制需改善

## 相关
- [[concepts/ic-analysis]]
