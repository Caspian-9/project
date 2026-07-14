---
id: factor_volatility_12m
type: factor
name: volatility_12m
category: 波动
status: growing
ic_ir: -0.098
ic_mean: -0.0206
sharpe: -0.086
grade: D
decision: discard
backtest_date: 2026-07-15
---

# volatility_12m

- **类别**: 波动
- **IC_IR**: -0.098 | **IC均值**: -0.0206
- **多空Sharpe**: -0.086 | **MaxDD**: -57.5%
- **单调性**: N | **评级**: D | **决策**: discard

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | 13.14% |
| Q1 | 12.36% |
| Q2 | 11.61% |
| Q3 | 11.79% |
| Q4 | 11.36% |

## 评价

- IC_IR=-0.10，预测能力偏弱
- 分层收益不单调，存在非线性关系或分组间差异小
- 多空 Sharpe=-0.09，风险调整收益不足

## 相关
- [[concepts/ic-analysis]]
