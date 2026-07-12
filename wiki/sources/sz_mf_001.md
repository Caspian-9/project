---
id: sz_mf_001
source: 南方科技大学
date: 2026-07-11
type: source
category: 课程课件与代码
status: ingested
ingested_at: 2026-07-11
tags: [多因子模型, 机器学习, Alpha框架, Lasso, LightGBM, LSTM, DoubleEnsemble, CSI300, CSI1000]
---

# 南科大量化课程4：多因子Quant Lab

- **来源**: 南方科技大学量化课程（AI辅助量化研究实验室）
- **日期**: 2026-07-11
- **原始文件**: `raw/截面多因子课件及脚本/南方科大量化课程4_多因子Quant Lab.pdf` + `code/` 目录
- **关键词**: 多因子模型, 机器学习选股, vnpy.alpha, Alpha158因子集, 超参数优化, 策略回测

## 核心内容

这是一个完整的AI辅助量化研究教学材料，含一份25页的课件PDF和8个完整的Jupyter Notebook及2个Python模型实现。课程系统讲授了如何利用 `vnpy.alpha` 框架（AlphaLab → AlphaDataset → AlphaModel → BacktestingEngine）搭建端到端的截面多因子选股研究流程。

核心工作流覆盖6个阶段：
1. **数据准备**: 通过 RQData 下载 CSI300/CSI1000 成分股的日线OHLCV数据
2. **特征计算**: 基于 Alpha158 因子集计算 158 个技术/价量因子，进行截面标准化
3. **模型训练**: 分别使用 Lasso 回归、LightGBM、LSTM 神经网络、Double Ensemble 四种模型训练
4. **信号预测**: 在测试集上预测 Alpha 信号
5. **Alphalens 评估**: IC 分析、分层收益评估信号质量
6. **策略回测**: 使用 EquityDemoStrategy (top_k=30, n_drop=3) 进行真实回测

## 关键发现

### CSI300 (沪深300) 回测结果 (2017-01 ~ 2020-07, 初始资金1亿)

| 模型 | 年化收益 | Sharpe Ratio | 最大回撤 | 收益回撤比 |
|------|---------|-------------|---------|-----------|
| LightGBM | 48.16% | 1.26 | -21.79% | 3.31 |
| LSTM | 62.24% | 1.54 | -22.24% | 4.55 |
| DoubleEnsemble | 61.88% | 1.64 | -21.98% | 4.24 |

- **DoubleEnsemble Sharpe最高** (1.64)，体现了集成学习在收益风险比上的优势
- **LSTM 绝对收益最高** (62.24% 年化)，但对数据预处理更敏感（使用 RobustZScore + Cross-Sectional Rank）
- **LightGBM 回撤控制最好** (-21.79%)，更传统的树模型在极端市场可能更稳健

### CSI1000 (中证1000) 回测结果 (2023-01 ~ 2025-12, 初始资金1亿)

| 模型 | 年化收益 | Sharpe Ratio | 最大回撤 |
|------|---------|-------------|---------|
| Lasso | 17.81% | 0.75 | -35.62% |
| LightGBM | 18.29% | 0.74 | -37.54% |

- 中证1000 小盘股池的 ML 选股效果明显弱于沪深300：Lasso 和 LightGBM 的 Sharpe 均不到 0.8，年化收益不足 20%
- 两个模型在 CSI1000 上表现接近（Lasso 略高 Sharpe，LightGBM 略高收益），均未体现出在 CSI300 上的显著优势
- 最大回撤超 35%，说明小盘 ML 选股策略的风险控制是核心挑战

### 模型架构对比

| 模型 | 类型 | 核心机制 | 可解释性 | 超参数数量 |
|------|------|---------|---------|-----------|
| Lasso | 线性(L1正则) | 自动因子筛选，稀疏解 | 高（系数符号+大小） | 少 |
| LightGBM | 树集成 | GBDT梯度提升，天然处理非线性 | 中（特征重要性） | 中等 |
| LSTM | 深度学习 | 序列特征提取 (2层, 64 hidden, 90k参数) | 低（黑盒） | 多 |
| DoubleEnsemble | 元集成 | 多子模型 + Sample Reweighting + Feature Selection | 低 | 最多 (Optuna优化) |

## 涉及的策略 / 因子 / 指标

- [[strategies/multi-factor-strategy]] — 整个工作流就是多因子选股策略的ML化实现
- [[factors/momentum-factor]] — Alpha158 中包含大量动量/反转类因子（rank, rsv, roc, cord 等）
- [[factors/value-factor]] — 价量因子与价值因子的间接关联
- [[concepts/factor-testing]] — Alphalens IC分析和分层回测是课程的核心评估方法
- [[concepts/overfitting]] — DoubleEnsemble 用 Optuna 做超参数优化，LSTM 使用早停防止过拟合
- [[concepts/sharpe-ratio]] — 所有模型均使用 Sharpe Ratio 作为核心评价指标

## 数据与回测

- **标的**: CSI300 (000300.SSE) 和 CSI1000 (000852.SSE) 成分股
- **周期**: 训练 2008-2014 / 验证 2015-2016 / 测试 2017-2020 (CSI300); 训练 2016-2020 / 验证 2021-2022 / 测试 2023-2025 (CSI1000)
- **频率**: 日频
- **特征集**: Alpha158 (158个技术/价量因子)
- **策略参数**: top_k=30, n_drop=3, hold_thresh=3 (CSI300); top_k=225, n_drop=20, min_days=3 (CSI1000)

## 方法论贡献

1. **标准化 ML 选股流水线**: 提供了从数据下载到回测评估的完整可复现代码
2. **Double Ensemble 算法**: 一种新颖的元集成方法，通过在子模型间迭代进行样本重加权和特征选择来提升集成效果
3. **Optuna 超参数优化集成**: 将贝叶斯超参数搜索嵌入训练流程
4. **多模型对比框架**: 在同一数据/特征/回测条件下对比线性和非线性模型的差异

## 局限性

- 特征集仅限于 Alpha158 技术因子，未包含基本面/财务因子
- 回测周期较短（CSI300 3.5年, CSI1000 3年），未覆盖完整牛熊周期
- LSTM 训练仅使用 rank_norm 预处理，doubleensemble 使用 robust_zscore，不同预处理方式使模型间可比性下降
- 未做行业/市值中性化处理，可能暴露于特定风格风险
- 策略使用等权 top_k 选股，未考虑仓位优化

## 相关来源

- [[sources/gx_mf_004]] — 国信证券多因子回溯测试框架（同属多因子方法论）
- [[sources/gx_mf_005]] — 国信成长类因子测试（因子测试方法）
- [[sources/method_002]] — 多因子选股模型方法论综述
