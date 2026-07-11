"""因子研究工作流状态机 — 驱动三阶段因子研究流程。

Phase SELECT: 用户选定报告 + 因子 → agent 深读论文，提取原始因子定义
Phase GENERATE_BACKTEST: 生成因子变体 → 批量回测 → 汇总结果
Phase ANALYZE: 深度分析 → 投资逻辑 → 改进方向 → 生成报告
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FactorResearchPhase(Enum):
    """因子研究三阶段。"""

    SELECT = "select"  # 选定报告和因子，深读提取定义
    GENERATE_BACKTEST = "generate_backtest"  # 生成变体 + 批量回测
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
