"""因子研究工作流：状态机 + 变体生成 + 报告。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FactorResearchPhase(Enum):
    """因子研究四阶段。"""

    SELECT = "select"  # 选定报告和因子，深读提取定义
    GENERATE_BACKTEST = "generate_backtest"  # 生成变体 + 批量回测
    ROBUSTNESS = "robustness"  # 稳健性验证 + 毕业/淘汰决策
    ANALYZE = "analyze"  # 深度分析 + 生成报告


@dataclass
class FactorVariant:
    """因子变体定义 — 从原始因子派生的一个变体。"""

    name: str
    description: str  # 变体逻辑：改了什么、为什么
    base: str  # 基元数据
    window: int
    agg_func: str
    transform: str = "zscore"
    parent_factor: str = ""  # 派生自哪个原始因子
    variant_type: str = ""  # param_tweak | window_change | new_variable | composite


@dataclass
class FactorResearchWorkflow:
    """因子研究工作流状态机。

    管理三阶段流程，记录每个阶段的结构化产出。
    """

    # 当前状态
    current_phase: FactorResearchPhase = FactorResearchPhase.SELECT

    # Phase SELECT 产出
    report_id: str = ""  # 选定的报告 ID (对应 llm_wiki index.json)
    selected_factor_name: str = ""  # 用户感兴趣的因子名
    original_factor_def: Optional[dict[str, Any]] = None  # 原始因子定义
    economic_rationale: str = ""  # 因子的经济逻辑分析

    # Phase GENERATE_BACKTEST 产出
    variants: list[FactorVariant] = field(default_factory=list)
    backtest_results: dict[str, Any] = field(default_factory=dict)  # factor_name → metrics

    # Phase ROBUSTNESS 产出
    robustness_passed: bool = False  # 是否通过稳健性验证
    robustness_detail: dict[str, Any] = field(default_factory=dict)  # 分段/分池/参数稳定性
    graduation_decision: str = ""  # graduate | needs_work | discard

    # Phase ANALYZE 产出
    analysis_report: str = ""  # Markdown 格式的完整分析报告
    improvement_directions: list[str] = field(default_factory=list)

    @property
    def phase_index(self) -> int:
        """当前阶段索引（0-based）。"""
        phases = list(FactorResearchPhase)
        return phases.index(self.current_phase)

    def advance(self) -> Optional[FactorResearchPhase]:
        """推进到下一阶段。

        Returns:
            下一阶段，如果已是最后阶段则返回 None。
        """
        phases = list(FactorResearchPhase)
        idx = phases.index(self.current_phase)
        if idx + 1 < len(phases):
            self.current_phase = phases[idx + 1]
            return self.current_phase
        return None

    def can_skip_to(self, phase: FactorResearchPhase) -> bool:
        """检查是否可以跳转到指定阶段。

        Args:
            phase: 目标阶段。

        Returns:
            是否可以跳转。
        """
        phases = list(FactorResearchPhase)
        return phases.index(phase) <= phases.index(self.current_phase) + 1


# ======================== 阶段 Prompt 模板 ========================


PHASE_PROMPTS: dict[FactorResearchPhase, str] = {
    FactorResearchPhase.SELECT: """
你是一个量化因子研究员。用户从研究报告中选定了一个感兴趣的因子。

## 报告信息
{report_context}

## 用户选定的因子
{selected_factor}

## 你的任务
1. 深读报告原文，理解该因子的经济逻辑（为什么有效？基于什么市场异象或风险溢价？）
2. 提取原始因子的完整定义：计算方式、参数、数据来源
3. 分析原始因子的潜在局限：参数敏感性？市场状态依赖？行业/风格暴露？

输出 JSON:
{{
    "factor_name": "因子的唯一标识名",
    "base": "returns|volume|price|high|low|open",
    "window": 20,
    "agg_func": "sum|mean|std|max|min",
    "transform": "zscore|rank|raw|winsorize",
    "economic_rationale": "为什么这个因子可能有效（2-3句话）",
    "limitations": ["局限1", "局限2"],
    "variant_ideas": [
        {{
            "name": "变体名称",
            "description": "变体逻辑",
            "variant_type": "param_tweak|window_change|new_variable|composite"
        }}
    ]
}}
""",

    FactorResearchPhase.GENERATE_BACKTEST: """
你是一个量化因子研究员。基于原始因子定义和变体思路，你需要生成具体的因子变体并执行回测。

## 原始因子
{original_factor_summary}

## 变体思路
{variant_ideas}

## 可用工具
- run_backtest: 单因子回测
- sweep_params: 参数扫描

## 你的任务
1. 为每个变体思路生成具体的 FactorDef（base, window, agg_func, transform）
2. 调用 run_backtest 逐个回测
3. 调用 sweep_params 对最佳候选做参数敏感性分析
4. 汇总所有回测结果，按 IC_IR 降序排列

输出 JSON:
{{
    "best_variant": "表现最好的因子名称",
    "all_results_summary": "所有变体的回测汇总",
    "parameter_sensitivity": "参数稳定性评估"
}}
""",

    FactorResearchPhase.ROBUSTNESS: """
你是一个量化因子研究员。基于回测结果，你需要对最佳因子进行稳健性验证。

## 最佳因子回测结果
{best_backtest_summary}

## 变体排名
{variants_ranking}

## 你的任务

1. **分段测试**: 将回测区间分为前半段和后半段，分别计算 IC_IR
   - 两段 IC_IR 方向一致且绝对值 > 0.2 → 通过
   - 某段 IC_IR 符号反转 → 因子可能过拟合

2. **参数稳定性**: 检查参数扫描结果中 IC_IR 随参数变化的曲线
   - 高原型（IC_IR 在参数区间内稳定）→ 因子稳健
   - 尖峰型（IC_IR 仅在某个参数值最高，偏离后快速下降）→ 过拟合嫌疑

3. **稳健性决策矩阵**:

   | 条件 | 决策 |
   |------|------|
   | 分段均通过 + 参数高原型 + |IC_IR| > 0.5 | **graduate** — 因子可毕业 |
   | 分段均通过 + 参数高原型 + |IC_IR| > 0.2 | **needs_work** — 加入行业中性化后重试 |
   | 分段不通过 或 参数尖峰型 | **needs_work** — 减少参数、简化因子结构 |
   | |IC_IR| < 0.15 或 分段 IC 符号反转 | **discard** — 因子无稳健预测能力 |

输出 JSON:
{{
    "first_half_ic_ir": 0.0,
    "second_half_ic_ir": 0.0,
    "split_test_passed": true,
    "parameter_stability": "plateau|peak",
    "decision": "graduate|needs_work|discard",
    "reasoning": "决策理由"
}}
""",

    FactorResearchPhase.ANALYZE: """
你是一个量化因子分析师。基于回测结果，你需要撰写完整的因子分析报告。

## 回测结果
{backtest_summary}

## 原始因子经济逻辑
{economic_rationale}

## 你的任务
分析以下维度，撰写 Markdown 报告：

1. **投资逻辑**: 因子为何有效？背后的市场机制或行为偏差？
2. **实证表现**: IC/分层收益/多空表现的统计摘要
3. **有效原因**: 哪些市场环境下因子表现最好？为什么？
4. **失效场景**: 哪些情况下因子可能失效？历史上是否有过长期回撤？
5. **行业/风格暴露**: 因子在哪些行业/风格上暴露集中？是否需要中性化？
6. **与常见因子关系**: 与动量/反转/规模/价值/质量因子的相关性
7. **改进方向**: 如何进一步优化？可以加入什么新变量？调整什么结构？

输出 JSON:
{{
    "report_markdown": "完整的 Markdown 分析报告",
    "improvement_directions": ["改进方向1", "改进方向2", "改进方向3"],
    "verdict": "promising|needs_work|reject",
    "next_steps": "建议的下一步"
}}
""",
}

from dataclasses import dataclass, field

from scripts.factor import FactorDef, TransformMethod


# ======================== 变体生成策略 ========================


@dataclass
class VariantGenerator:
    """因子变体生成器 — 根据原始因子定义自动生成变体列表。"""

    # 参数微调: 窗口缩放倍数
    param_tweak_scales: list[float] = field(
        default_factory=lambda: [0.25, 0.5, 0.75, 1.5, 2.0, 3.0]
    )

    # 多时间尺度: 短期/中期/长期窗口
    multi_scale_windows: dict[str, list[int]] = field(
        default_factory=lambda: {
            "short": [5, 10, 15],
            "medium": [20, 40, 60],
            "long": [120, 250],
        }
    )

    # 变换方式
    transforms: list[str] = field(
        default_factory=lambda: ["zscore", "rank", "winsorize"]
    )

    # 备选基元（用于引入新变量）
    alternative_bases: list[str] = field(
        default_factory=lambda: ["returns", "volume", "high", "low"]
    )

    def generate(
        self,
        original: dict[str, Any],
        factor_name: str = "factor",
        max_variants: int = 20,
    ) -> list[FactorVariant]:
        """从原始因子定义生成变体列表。

        Args:
            original: 原始因子参数字典 (base, window, agg_func, transform)。
            factor_name: 因子名称前缀。
            max_variants: 最大变体数量。

        Returns:
            FactorVariant 列表。
        """
        base = original.get("base", "returns")
        window = original.get("window", 20)
        agg_func = original.get("agg_func", "sum")
        transform = original.get("transform", "zscore")

        variants: list[FactorVariant] = []

        # 1. 参数微调 (param_tweak)
        for scale in self.param_tweak_scales:
            new_window = max(2, int(window * scale))
            if new_window == window:
                continue
            variants.append(
                FactorVariant(
                    name=f"{factor_name}_w{new_window}_{agg_func}",
                    description=f"窗口从{window}调整为{new_window}（×{scale}）",
                    base=base,
                    window=new_window,
                    agg_func=agg_func,
                    transform=transform,
                    parent_factor=factor_name,
                    variant_type="param_tweak",
                )
            )

        # 2. 变换方式变化
        for t in self.transforms:
            if t == transform:
                continue
            variants.append(
                FactorVariant(
                    name=f"{factor_name}_w{window}_{agg_func}_{t}",
                    description=f"变换方式从{transform}改为{t}",
                    base=base,
                    window=window,
                    agg_func=agg_func,
                    transform=t,
                    parent_factor=factor_name,
                    variant_type="param_tweak",
                )
            )

        # 3. 引入新变量 (change base)
        for alt_base in self.alternative_bases:
            if alt_base == base:
                continue
            for w in [window, max(2, window // 2)]:
                variants.append(
                    FactorVariant(
                        name=f"{factor_name}_{alt_base}_w{w}_{agg_func}",
                        description=f"改用{alt_base}数据，窗口{w}",
                        base=alt_base,
                        window=w,
                        agg_func=agg_func,
                        transform=transform,
                        parent_factor=factor_name,
                        variant_type="new_variable",
                    )
                )

        # 4. 多时间尺度
        for scale_name, windows in self.multi_scale_windows.items():
            for w in windows:
                if w == window:
                    continue
                variants.append(
                    FactorVariant(
                        name=f"{factor_name}_{scale_name}_w{w}_{agg_func}",
                        description=f"{scale_name}期尺度，窗口{w}",
                        base=base,
                        window=w,
                        agg_func=agg_func,
                        transform=transform,
                        parent_factor=factor_name,
                        variant_type="window_change",
                    )
                )

        # 去重 + 限制数量
        seen: set[str] = set()
        unique: list[FactorVariant] = []
        for v in variants:
            if v.name not in seen:
                seen.add(v.name)
                unique.append(v)
                if len(unique) >= max_variants:
                    break

        return unique

    def to_factor_defs(self, variants: list[FactorVariant]) -> list[FactorDef]:
        """将 FactorVariant 列表转为 FactorDef 列表。

        Args:
            variants: 变体列表。

        Returns:
            FactorDef 列表。
        """
        transform_map: dict[str, TransformMethod] = {
            "raw": TransformMethod.RAW,
            "zscore": TransformMethod.ZSCORE,
            "rank": TransformMethod.RANK,
            "winsorize": TransformMethod.WINSORIZE,
        }

        defs: list[FactorDef] = []
        for v in variants:
            defs.append(
                FactorDef(
                    name=v.name,
                    base=v.base,
                    window=v.window,
                    agg_func=v.agg_func,
                    transform=transform_map.get(v.transform, TransformMethod.ZSCORE),
                )
            )
        return defs


def generate_variant_ideas(
    original: dict[str, Any],
    economic_rationale: str = "",
    limitations: Optional[list[str]] = None,
) -> list[dict[str, str]]:
    """生成变体思路——供 LLM 参考的结构化建议。

    不直接生成 FactorVariant，而是输出自然语言描述，
    让 LLM 理解后再决定采用哪些变体。

    Args:
        original: 原始因子参数。
        economic_rationale: 因子的经济逻辑。
        limitations: 已知局限。

    Returns:
        变体思路列表，每项含 name, description, variant_type。
    """
    base = original.get("base", "returns")
    window = original.get("window", 20)
    agg = original.get("agg_func", "sum")

    ideas: list[dict[str, str]] = [
        {
            "name": "缩短窗口",
            "description": f"将{window}期窗口缩短至{max(2, window//2)}或{max(2, window//4)}期，捕捉更短期的信号",
            "variant_type": "window_change",
        },
        {
            "name": "延长窗口",
            "description": f"将{window}期窗口延长至{window*2}或{window*3}期，过滤噪音捕捉中长期趋势",
            "variant_type": "window_change",
        },
        {
            "name": "改用 Rank 变换",
            "description": "将截面标准化改为截面排序，降低极端值影响，提高因子稳定性",
            "variant_type": "param_tweak",
        },
        {
            "name": "去极值处理",
            "description": "在标准化之前对因子值进行 Winsorize（截尾1%/99%），减少异常值干扰",
            "variant_type": "param_tweak",
        },
        {
            "name": "引入成交量信息",
            "description": f"在{base}基础上乘以或除以成交量，构造价量复合因子",
            "variant_type": "new_variable",
        },
        {
            "name": "改用波动率",
            "description": f"将聚合函数从 {agg} 改为 std，捕捉{base}的波动特征而非方向",
            "variant_type": "param_tweak",
        },
    ]

    # 根据经济逻辑添加针对性建议
    if "动量" in economic_rationale or "趋势" in economic_rationale:
        ideas.append({
            "name": "分离上行/下行动量",
            "description": "将正收益和负收益分别聚合后相减，捕捉非对称动量效应",
            "variant_type": "new_variable",
        })
    if "反转" in economic_rationale:
        ideas.append({
            "name": "加入波动率过滤器",
            "description": "仅在高波动环境下做反转交易，低波动时不做",
            "variant_type": "new_variable",
        })
    if limitations:
        for lim in limitations:
            if "行业" in lim or "风格" in lim:
                ideas.append({
                    "name": "行业中性化",
                    "description": "对因子值做行业中性化处理，消除行业暴露偏差",
                    "variant_type": "new_variable",
                })
                break

    return ideas

from datetime import datetime
from pathlib import Path

from scripts.analysis import FactorAnalysis, compare_analyses


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


def save_report(report: str, output_dir: str = "output/reports") -> Path:
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
