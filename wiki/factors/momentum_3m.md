---
id: factor_momentum_3m
type: factor
name: momentum_3m
category: 动量
status: growing
ic_ir: -0.086
ic_mean: -0.0162
sharpe: 0.113
grade: D
decision: discard
backtest_date: 2026-07-15
---

# momentum_3m

- **类别**: 动量
- **IC_IR**: -0.086 | **IC均值**: -0.0162
- **多空Sharpe**: 0.113 | **MaxDD**: -53.4%
- **单调性**: N | **评级**: D | **决策**: discard

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | 8.98% |
| Q1 | 9.27% |
| Q2 | 11.37% |
| Q3 | 12.85% |
| Q4 | 11.17% |

## 评价

- IC_IR=-0.09，预测能力偏弱
- 分层收益不单调，存在非线性关系或分组间差异小
- 多空 Sharpe=0.11，风险调整收益不足

## 相关
- [[concepts/ic-analysis]]
