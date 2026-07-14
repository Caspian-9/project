---
id: factor_volatility_3m
type: factor
name: volatility_3m
category: 波动
status: growing
ic_ir: -0.097
ic_mean: -0.0218
sharpe: 0.081
grade: D
decision: discard
backtest_date: 2026-07-15
---

# volatility_3m

- **类别**: 波动
- **IC_IR**: -0.097 | **IC均值**: -0.0218
- **多空Sharpe**: 0.081 | **MaxDD**: -56.5%
- **单调性**: N | **评级**: D | **决策**: discard

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | 10.03% |
| Q1 | 10.14% |
| Q2 | 11.90% |
| Q3 | 9.58% |
| Q4 | 11.87% |

## 评价

- IC_IR=-0.10，预测能力偏弱
- 分层收益不单调，存在非线性关系或分组间差异小
- 多空 Sharpe=0.08，风险调整收益不足

## 相关
- [[concepts/ic-analysis]]
