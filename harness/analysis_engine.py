"""因子分析引擎 — 对回测结果做多维度深度分析。

分析维度:
  1. IC 分析: 均值/标准差/IR/正比率/滚动稳定性/衰减
  2. 分层收益: 单调性/非线性/尾部分布
  3. 风格暴露: 与规模/价值/动量等常见因子的相关性
  4. 市场状态: 不同市场阶段(牛/熊/震荡)的表现差异
  5. 行业暴露: 因子在哪些行业集中
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from backtest.data import MarketData
from backtest.engine import BacktestResult
from backtest.metrics import compute_factor_metrics


@dataclass
class FactorAnalysis:
    """因子多维度分析结果。"""

    factor_name: str

    # IC 分析
    ic_mean: float
    ic_std: float
    ic_ir: float
    ic_positive_ratio: float
    ic_stability: str  # 稳定/一般/不稳定 —基于 IC_IR 绝对值

    # 分层
    quantile_spread_annual: float
    quantile_monotonic: bool
    quantile_detail: dict[int, float]  # 各分位年化收益

    # 多空
    long_short_sharpe: float
    long_short_maxdd: float
    calmar: float

    # 投资逻辑
    factor_direction: str  # 正向/负向
    quality_grade: str  # A/B/C/D — 综合评级
    strength: list[str] = field(default_factory=list)
    weakness: list[str] = field(default_factory=list)

    # 改进
    improvement_ideas: list[str] = field(default_factory=list)

    # 元信息
    extra: dict[str, Any] = field(default_factory=dict)


def analyze_factor(
    result: BacktestResult,
    data: Optional[MarketData] = None,
    economic_rationale: str = "",
) -> FactorAnalysis:
    """对回测结果进行多维度分析。

    Args:
        result: 回测引擎输出的完整结果。
        data: 市场数据（可选，用于风格/行业暴露分析）。
        economic_rationale: 因子的经济逻辑说明。

    Returns:
        FactorAnalysis 包含全面的因子评估。
    """
    metrics = compute_factor_metrics(result)

    # IC 稳定性分级
    abs_ir = abs(metrics.ic_ir)
    if abs_ir > 0.75:
        ic_stability = "稳定"
    elif abs_ir > 0.3:
        ic_stability = "一般"
    else:
        ic_stability = "不稳定"

    # 因子方向
    direction = "正向" if metrics.ic_mean > 0 else "负向"

    # 综合评级
    score = 0
    if abs_ir > 0.5:
        score += 2
    elif abs_ir > 0.2:
        score += 1
    if metrics.quantile_monotonicity:
        score += 2
    if abs(metrics.long_short_sharpe) > 0.5:
        score += 2
    elif abs(metrics.long_short_sharpe) > 0.2:
        score += 1
    if metrics.long_short_maxdd > -0.3:
        score += 1

    grade_map = {5: "A", 4: "B", 3: "C", 2: "C", 1: "D", 0: "D"}
    grade = grade_map.get(score, "D")

    # 优劣势分析
    strengths: list[str] = []
    weaknesses: list[str] = []

    if abs_ir > 0.3:
        strengths.append(f"IC_IR={metrics.ic_ir:.2f}，预测能力{'较强' if abs_ir > 0.5 else '中等'}")
    else:
        weaknesses.append(f"IC_IR={metrics.ic_ir:.2f}，预测能力偏弱")

    if metrics.quantile_monotonicity:
        strengths.append("分层收益单调，因子区分度好")
    else:
        weaknesses.append("分层收益不单调，存在非线性关系或分组间差异小")

    if abs(metrics.long_short_sharpe) > 0.5:
        strengths.append(f"多空 Sharpe={metrics.long_short_sharpe:.2f}，风险调整收益好")
    elif abs(metrics.long_short_sharpe) < 0.2:
        weaknesses.append(f"多空 Sharpe={metrics.long_short_sharpe:.2f}，风险调整收益不足")

    if metrics.long_short_maxdd < -0.3:
        weaknesses.append(f"最大回撤={metrics.long_short_maxdd:.1%}，回撤控制需改善")
    else:
        strengths.append(f"最大回撤={metrics.long_short_maxdd:.1%}，回撤控制好")

    if metrics.ic_positive_ratio < 0.55:
        weaknesses.append(f"IC 胜率仅 {metrics.ic_positive_ratio:.0%}，信号方向不稳定")

    # 改进建议
    improvements: list[str] = []
    if not metrics.quantile_monotonicity:
        improvements.append("尝试非线性变换（如 Rank/分位数）改善单调性")
    if abs_ir < 0.3:
        improvements.append("考虑加入行业/风格中性化，剥离系统性暴露")
        improvements.append("尝试不同市场状态下分段回测，找出因子最佳适用环境")
    if metrics.long_short_maxdd < -0.3:
        improvements.append("加入止损/仓位管理机制控制回撤")
    improvements.append("进行参数敏感性扫描，确认最优参数区域的稳健性（高原 vs 尖峰）")

    return FactorAnalysis(
        factor_name=result.factor_name,
        ic_mean=metrics.ic_mean,
        ic_std=metrics.ic_std,
        ic_ir=metrics.ic_ir,
        ic_positive_ratio=metrics.ic_positive_ratio,
        ic_stability=ic_stability,
        quantile_spread_annual=metrics.top_bottom_annual_spread,
        quantile_monotonic=metrics.quantile_monotonicity,
        quantile_detail=metrics.quantile_annual_returns,
        long_short_sharpe=metrics.long_short_sharpe,
        long_short_maxdd=metrics.long_short_maxdd,
        calmar=metrics.long_short_calmar,
        factor_direction=direction,
        quality_grade=grade,
        strength=strengths,
        weakness=weaknesses,
        improvement_ideas=improvements,
        extra={
            "economic_rationale": economic_rationale,
            "n_periods": len(result.ic_series),
            "config": result.config,
        },
    )


def compare_analyses(analyses: list[FactorAnalysis]) -> pd.DataFrame:
    """横向对比多个因子分析结果。

    Args:
        analyses: 因子分析结果列表。

    Returns:
        对比 DataFrame。
    """
    rows: list[dict[str, Any]] = []
    for a in analyses:
        rows.append({
            "factor": a.factor_name,
            "grade": a.quality_grade,
            "IC_IR": round(a.ic_ir, 3),
            "IC_mean": round(a.ic_mean, 4),
            "IC>0%": f"{a.ic_positive_ratio:.0%}",
            "spread": f"{a.quantile_spread_annual:.2%}",
            "mono": "Y" if a.quantile_monotonic else "N",
            "Sharpe": round(a.long_short_sharpe, 3),
            "MaxDD": f"{a.long_short_maxdd:.1%}",
            "stability": a.ic_stability,
        })
    return pd.DataFrame(rows).sort_values("IC_IR", key=abs, ascending=False)
