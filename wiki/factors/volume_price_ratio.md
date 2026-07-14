---
id: factor_volume_price_ratio
type: factor
name: volume_price_ratio
category: 成交量
status: growing
ic_ir: -0.098
ic_mean: -0.0145
sharpe: -1.179
grade: B
decision: discard
backtest_date: 2026-07-15
---

# volume_price_ratio

- **类别**: 成交量
- **IC_IR**: -0.098 | **IC均值**: -0.0145
- **多空Sharpe**: -1.179 | **MaxDD**: -81.8%
- **单调性**: Y | **评级**: B | **决策**: discard

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | 18.95% |
| Q1 | 8.50% |
| Q2 | 4.43% |
| Q3 | 3.79% |
| Q4 | 0.44% |

## 评价

- 分层收益单调，因子区分度好
- 多空 Sharpe=-1.18，风险调整收益好
- IC_IR=-0.10，预测能力偏弱
- 最大回撤=-81.8%，回撤控制需改善
- IC 胜率仅 44%，信号方向不稳定

## 相关
- [[concepts/ic-analysis]]
