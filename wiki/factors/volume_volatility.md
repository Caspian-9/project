---
id: factor_volume_volatility
type: factor
name: volume_volatility
category: 成交量
status: growing
ic_ir: -0.157
ic_mean: -0.0222
sharpe: -1.262
grade: B
decision: needs_work
backtest_date: 2026-07-15
---

# volume_volatility

- **类别**: 成交量
- **IC_IR**: -0.157 | **IC均值**: -0.0222
- **多空Sharpe**: -1.262 | **MaxDD**: -85.5%
- **单调性**: Y | **评级**: B | **决策**: needs_work

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | 19.26% |
| Q1 | 11.32% |
| Q2 | 6.28% |
| Q3 | 5.76% |
| Q4 | -1.62% |

## 评价

- 分层收益单调，因子区分度好
- 多空 Sharpe=-1.26，风险调整收益好
- IC_IR=-0.16，预测能力偏弱
- 最大回撤=-85.5%，回撤控制需改善
- IC 胜率仅 42%，信号方向不稳定

## 相关
- [[concepts/ic-analysis]]
