---
id: factor_volume_trend_3m
type: factor
name: volume_trend_3m
category: 成交量
status: growing
ic_ir: -0.071
ic_mean: -0.0099
sharpe: -1.209
grade: C
decision: discard
backtest_date: 2026-07-15
---

# volume_trend_3m

- **类别**: 成交量
- **IC_IR**: -0.071 | **IC均值**: -0.0099
- **多空Sharpe**: -1.209 | **MaxDD**: -91.3%
- **单调性**: N | **评级**: C | **决策**: discard

## 分位收益 (CSI300 2010-2024)

| 分位 | 年化收益 |
|------|----------|
| Q0 | 28.29% |
| Q1 | 14.30% |
| Q2 | 9.91% |
| Q3 | 10.13% |
| Q4 | 5.49% |

## 评价

- 多空 Sharpe=-1.21，风险调整收益好
- IC_IR=-0.07，预测能力偏弱
- 分层收益不单调，存在非线性关系或分组间差异小
- 最大回撤=-91.3%，回撤控制需改善

## 相关
- [[concepts/ic-analysis]]
