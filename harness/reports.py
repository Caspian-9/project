"""因子分析报告生成器 — 输出结构化 Markdown 报告。

报告模板覆盖 HARNESS_DESIGN.md Phase 3 的四层注入 + Phase 4 的知识蒸馏需求。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from harness.analysis_engine import FactorAnalysis, compare_analyses
from harness.workflow import FactorVariant


def generate_factor_report(
    original_factor_name: str,
    original_definition: dict[str, Any],
    economic_rationale: str,
    analysis: FactorAnalysis,
    variants: Optional[list[FactorVariant]] = None,
    variant_analyses: Optional[list[FactorAnalysis]] = None,
    report_source: str = "",
) -> str:
    """生成完整的因子分析 Markdown 报告。

    Args:
        original_factor_name: 原始因子名称。
        original_definition: 原始因子定义 (base, window, agg_func, transform)。
        economic_rationale: 经济逻辑分析。
        analysis: 原始因子的 FactorAnalysis 结果。
        variants: 变体列表。
        variant_analyses: 变体的分析结果列表。
        report_source: 报告来源（llm_wiki 报告 ID）。

    Returns:
        Markdown 格式的完整报告。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    base = original_definition.get("base", "returns")
    window = original_definition.get("window", 20)
    agg = original_definition.get("agg_func", "sum")
    transform = original_definition.get("transform", "zscore")

    report = f"""# 因子分析报告: {original_factor_name}

> 生成时间: {now}
> 报告来源: {report_source or '手动指定'}

---

## 一、因子定义

| 参数 | 值 |
|------|-----|
| 因子名 | `{original_factor_name}` |
| 基元数据 | `{base}` |
| 回溯窗口 | {window} |
| 聚合函数 | `{agg}` |
| 截面变换 | `{transform}` |

## 二、投资逻辑

{economic_rationale or '_待补充 — 深读报告原文后填写_'}

## 三、回测表现

### 3.1 IC 分析

| 指标 | 值 | 评价 |
|------|-----|------|
| IC 均值 | {analysis.ic_mean:.4f} | |
| IC 标准差 | {analysis.ic_std:.4f} | |
| IC_IR | {analysis.ic_ir:.3f} | {analysis.ic_stability} |
| IC > 0 占比 | {analysis.ic_positive_ratio:.1%} | |

### 3.2 分层收益

| 分位 | 年化收益 |
|------|----------|
"""
    for q in sorted(analysis.quantile_detail.keys()):
        ret = analysis.quantile_detail[q]
        report += f"| Q{q} | {ret:.2%} |\n"

    report += f"""
| Top-Bottom 多空 | {analysis.quantile_spread_annual:.2%} |
| 单调性 | {'**通过**' if analysis.quantile_monotonic else '**不通过**'} |

### 3.3 多空组合

| 指标 | 值 |
|------|-----|
| 年化 Sharpe | {analysis.long_short_sharpe:.3f} |
| 最大回撤 | {analysis.long_short_maxdd:.2%} |
| Calmar 比率 | {analysis.calmar:.2f} |

## 四、综合评价

**因子方向**: {analysis.factor_direction}
**综合评级**: **{analysis.quality_grade}**

### 优势
"""
    for s in analysis.strength:
        report += f"- {s}\n"

    report += "\n### 不足\n"
    for w in analysis.weakness:
        report += f"- {w}\n"

    report += "\n## 五、因子变体对比\n\n"

    if variant_analyses and len(variant_analyses) > 1:
        comp_df = compare_analyses([analysis] + variant_analyses)
        report += f"""```
{comp_df.to_string(index=False)}
```
"""
    elif variants:
        report += "| 变体 | 描述 | 类型 |\n"
        report += "|------|------|------|\n"
        for v in variants[:10]:
            report += f"| `{v.name}` | {v.description[:50]} | {v.variant_type} |\n"
        report += "\n_变体回测待执行_\n"
    else:
        report += "_无变体_\n"

    report += "\n## 六、改进方向\n\n"
    for i, idea in enumerate(analysis.improvement_ideas, 1):
        report += f"{i}. {idea}\n"

    report += """
---

## 七、可能失效的场景

1. **市场状态切换**: 因子在趋势市中有效，震荡市中可能失效（需分段回测验证）
2. **参数过拟合**: 当前最优参数可能过度适应历史数据
3. **行业/风格暴露**: 若因子集中暴露于某行业或风格，该行业/风格失效时因子失效
4. **流动性风险**: 小市值端的因子效应可能在实际交易中难以实现

## 八、与常见因子的关系

_待补充 — 构建常见因子库后，计算因子间的截面相关性_

## 九、下一步

- [ ] 参数敏感性扫描（确定高原 vs 尖峰）
- [ ] 分市场状态（牛/熊/震荡）子样本回测
- [ ] 行业/风格中性化后的表现对比
- [ ] 与已有因子库的相关性分析
"""
    return report


def save_report(report: str, output_dir: str = "harness_workspace/reports") -> Path:
    """保存报告到文件。

    Args:
        report: Markdown 报告内容。
        output_dir: 输出目录。

    Returns:
        保存的文件路径。
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out / f"factor_report_{timestamp}.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


def generate_summary_for_llm(
    analysis: FactorAnalysis,
    max_tokens_estimate: int = 500,
) -> str:
    """生成给 LLM 看的压缩摘要（Token 预算友好）。

    50 行回测结果 → 3 行关键指标。

    Args:
        analysis: 因子分析结果。
        max_tokens_estimate: 约需多少 token 的摘要。

    Returns:
        压缩后的文本摘要。
    """
    return (
        f"[{analysis.quality_grade}] {analysis.factor_name}: "
        f"IC_IR={analysis.ic_ir:.3f}, "
        f"spread={analysis.quantile_spread_annual:.2%}, "
        f"Sharpe={analysis.long_short_sharpe:.3f}, "
        f"MaxDD={analysis.long_short_maxdd:.1%}, "
        f"mono={'Y' if analysis.quantile_monotonic else 'N'}, "
        f"dir={analysis.factor_direction}, "
        f"grade={analysis.quality_grade}"
    )
