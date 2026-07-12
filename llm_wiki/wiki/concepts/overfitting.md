---
id: concept_over
type: concept
name: 过拟合
status: stub
created: 2026-07-11
---

# 过拟合

## 定义

策略在样本内表现优异但样本外失效。警示信号：参数高原型(vs尖峰型)更稳健、Sharpe>3需警惕。

## 常见防控手段

- **早停 (Early Stopping)**: 验证集性能不再提升时终止训练（LSTM课程案例使用 patience=20 epochs）
- **正则化**: L1 (Lasso) 产生稀疏解自动特征筛选；L2 惩罚大权重
- **交叉验证**: 时间序列 walk-forward 比随机 K-fold 更适合金融数据
- **超参数优化**: Optuna 贝叶斯搜索比网格搜索更高效（DoubleEnsemble课程案例使用5次trial搜索7个超参数）
- **情境分析**: 海通证券提出技术指标实证结果情境分析方法来检测过拟合
- **样本外测试**: 严格的 train/valid/test 时间切分（课程案例：7年训练/2年验证/3.5年测试）

## 引用来源

| 来源 | 标题 | 日期 |
|------|------|------|
| [[sources/ht_tszs_005]] | 他山之石（五） | 2013-03-26 |
| [[sources/sz_mf_001]] | 南科大量化课程4：多因子Quant Lab | 2026-07-11 |

## 相关

- [[sources/gx_mf_004]] — 多因子研究系列(一)：因子回溯测试的总体框架
- [[concepts/factor-testing]] — 因子测试中的稳健性检验
