---
id: factor_high_low_spread
type: factor
name: high_low_spread
category: 波动
status: growing
ic_ir: -0.065
ic_mean: -0.0109
sharpe: -0.667
grade: B
decision: discard
backtest_date: 2026-07-15
---

# high_low_spread

- **类别**: 波动
- **IC_IR**: -0.065 | **IC均值**: -0.0109
- **多空Sharpe**: -0.667 | **MaxDD**: -85.6%
- **单调性**: Y | **评级**: B | **决策**: discard

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | 18.21% |
| Q1 | 13.70% |
| Q2 | 11.37% |
| Q3 | 10.86% |
| Q4 | 7.21% |

## 评价

- 分层收益单调，因子区分度好
- 多空 Sharpe=-0.67，风险调整收益好
- IC_IR=-0.06，预测能力偏弱
- 最大回撤=-85.6%，回撤控制需改善
- IC 胜率仅 48%，信号方向不稳定

## 相关
- [[concepts/ic-analysis]]
