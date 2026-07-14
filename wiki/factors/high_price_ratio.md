---
id: factor_high_price_ratio
type: factor
name: high_price_ratio
category: 波动
status: growing
ic_ir: -0.045
ic_mean: -0.0089
sharpe: 0.784
grade: C
decision: discard
backtest_date: 2026-07-15
---

# high_price_ratio

- **类别**: 波动
- **IC_IR**: -0.045 | **IC均值**: -0.0089
- **多空Sharpe**: 0.784 | **MaxDD**: -43.3%
- **单调性**: N | **评级**: C | **决策**: discard

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | -2.06% |
| Q1 | -3.42% |
| Q2 | -0.86% |
| Q3 | 3.90% |
| Q4 | 13.79% |

## 评价

- 多空 Sharpe=0.78，风险调整收益好
- IC_IR=-0.05，预测能力偏弱
- 分层收益不单调，存在非线性关系或分组间差异小
- 最大回撤=-43.3%，回撤控制需改善

## 相关
- [[concepts/ic-analysis]]
