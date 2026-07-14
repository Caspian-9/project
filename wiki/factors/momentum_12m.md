---
id: factor_momentum_12m
type: factor
name: momentum_12m
category: 动量
status: growing
ic_ir: -0.020
ic_mean: -0.0034
sharpe: 0.526
grade: B
decision: discard
backtest_date: 2026-07-15
---

# momentum_12m

- **类别**: 动量
- **IC_IR**: -0.020 | **IC均值**: -0.0034
- **多空Sharpe**: 0.526 | **MaxDD**: -52.1%
- **单调性**: Y | **评级**: B | **决策**: discard

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | 6.66% |
| Q1 | 11.49% |
| Q2 | 12.12% |
| Q3 | 14.33% |
| Q4 | 15.77% |

## 评价

- 分层收益单调，因子区分度好
- 多空 Sharpe=0.53，风险调整收益好
- IC_IR=-0.02，预测能力偏弱
- 最大回撤=-52.1%，回撤控制需改善
- IC 胜率仅 50%，信号方向不稳定

## 相关
- [[concepts/ic-analysis]]
