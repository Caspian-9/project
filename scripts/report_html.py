"""HTML 因子分析报告 — 自包含 Plotly 交互式图表。

替代 Markdown 报告，为 Pipeline 提供可视化输出。
图表: KPI 卡片、分层累计收益、IC 时序+分布、IC 衰变、分位收益柱状图、多空曲线。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import plotly.graph_objects as go

from scripts.analysis import (
    DynamicMetrics,
    FactorAnalysis,
    RobustnessResult,
)
from scripts.engine import BacktestResult


# ── 配色 ──
COLORS = {
    "bg": "#0f1117",
    "card_bg": "#1a1d2e",
    "text": "#e4e6eb",
    "text_muted": "#8b8fa3",
    "accent": "#6c8cff",
    "green": "#4ade80",
    "red": "#f87171",
    "yellow": "#facc15",
    "quantile": ["#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6"],
    "border": "#2a2d3e",
}

GRADE_COLORS = {"A": "#4ade80", "B": "#a3e635", "C": "#facc15", "D": "#f87171"}


def generate_html_report(
    result: BacktestResult,
    analysis: FactorAnalysis,
    dynamic: Optional[DynamicMetrics] = None,
    robustness: Optional[RobustnessResult] = None,
    factor_name: str = "",
    economic_rationale: str = "",
    report_source: str = "",
) -> str:
    """生成完整的自包含 HTML 因子分析报告。

    Args:
        result: 回测结果。
        analysis: 因子分析。
        dynamic: 动态分析指标（可选）。
        robustness: 稳健性验证（可选）。
        factor_name: 因子名称。
        economic_rationale: 经济逻辑。
        report_source: 来源报告 ID。

    Returns:
        完整 HTML 字符串。
    """
    name = factor_name or result.factor_name
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── 图表 ──
    chart_cumulative = _cumulative_returns_chart(result)
    chart_ic_ts = _ic_timeseries_chart(result)
    chart_ic_dist = _ic_distribution_chart(result)
    chart_quantile_bar = _quantile_bar_chart(result)
    chart_ls = _long_short_chart(result)

    decay_chart = ""
    if dynamic and dynamic.ic_decay:
        decay_chart = _ic_decay_chart(dynamic)

    # ── KPI 卡片 ──
    grade_color = GRADE_COLORS.get(analysis.quality_grade, "#8b8fa3")
    decision_str = robustness.decision if robustness else "未评估"
    decision_color = (
        "#4ade80" if decision_str == "graduate"
        else "#facc15" if decision_str == "needs_work"
        else "#f87171"
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>因子分析报告: {name}</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background:{COLORS['bg']}; color:{COLORS['text']}; line-height:1.6; }}
.container {{ max-width:1200px; margin:0 auto; padding:24px; }}
.header {{ text-align:center; padding:48px 0 32px; border-bottom:1px solid {COLORS['border']}; margin-bottom:32px; }}
.header h1 {{ font-size:2rem; margin-bottom:8px; }}
.header .meta {{ color:{COLORS['text_muted']}; font-size:0.9rem; }}

.kpi-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:16px; margin-bottom:32px; }}
.kpi-card {{ background:{COLORS['card_bg']}; border:1px solid {COLORS['border']}; border-radius:12px;
            padding:20px; text-align:center; }}
.kpi-card .label {{ font-size:0.8rem; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:1px; }}
.kpi-card .value {{ font-size:1.8rem; font-weight:700; margin:4px 0; }}
.kpi-card .sub {{ font-size:0.8rem; color:{COLORS['text_muted']}; }}

.chart-section {{ background:{COLORS['card_bg']}; border:1px solid {COLORS['border']}; border-radius:12px;
                  padding:24px; margin-bottom:24px; }}
.chart-section h2 {{ font-size:1.2rem; margin-bottom:16px; color:{COLORS['accent']}; }}
.chart-container {{ width:100%; min-height:400px; }}

.analysis-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; margin-bottom:24px; }}
@media (max-width:768px) {{ .analysis-grid {{ grid-template-columns:1fr; }} }}
.strength-list {{ color:{COLORS['green']}; }}
.weakness-list {{ color:{COLORS['red']}; }}
.strength-list li, .weakness-list li {{ margin-bottom:8px; }}

table {{ width:100%; border-collapse:collapse; margin:12px 0; }}
th, td {{ padding:10px 14px; text-align:left; border-bottom:1px solid {COLORS['border']}; }}
th {{ color:{COLORS['text_muted']}; font-weight:600; font-size:0.85rem; }}

.footer {{ text-align:center; padding:32px; color:{COLORS['text_muted']}; font-size:0.8rem;
          border-top:1px solid {COLORS['border']}; margin-top:32px; }}
</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>因子分析报告: {name}</h1>
  <p class="meta">生成: {now} | 来源: {report_source or 'N/A'} | Quant Harness</p>
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="label">评级</div>
    <div class="value" style="color:{grade_color}">{analysis.quality_grade}</div>
    <div class="sub">综合评分</div>
  </div>
  <div class="kpi-card">
    <div class="label">IC_IR</div>
    <div class="value">{analysis.ic_ir:.3f}</div>
    <div class="sub">IC均值={analysis.ic_mean:.4f}, σ={analysis.ic_std:.3f}</div>
  </div>
  <div class="kpi-card">
    <div class="label">多空 Sharpe</div>
    <div class="value">{analysis.long_short_sharpe:.3f}</div>
    <div class="sub">MaxDD={analysis.long_short_maxdd:.1%}</div>
  </div>
  <div class="kpi-card">
    <div class="label">多空年化</div>
    <div class="value">{analysis.quantile_spread_annual:.1%}</div>
    <div class="sub">单调性: {'✓' if analysis.quantile_monotonic else '✗'}</div>
  </div>
  <div class="kpi-card">
    <div class="label">IC 胜率</div>
    <div class="value">{analysis.ic_positive_ratio:.0%}</div>
    <div class="sub">{analysis.ic_stability}</div>
  </div>
  <div class="kpi-card">
    <div class="label">稳健性决策</div>
    <div class="value" style="color:{decision_color}; font-size:1.2rem;">{decision_str}</div>
    <div class="sub">{'分段通过' if robustness and robustness.split_test_passed else '分段未通过'}</div>
  </div>
</div>

<div class="analysis-grid">
  <div class="chart-section">
    <h2>优势</h2>
    <ul class="strength-list">
"""
    for s in analysis.strength:
        html += f"      <li>{s}</li>\n"
    html += """    </ul>
  </div>
  <div class="chart-section">
    <h2>不足</h2>
    <ul class="weakness-list">
"""
    for w in analysis.weakness:
        html += f"      <li>{w}</li>\n"
    html += """    </ul>
  </div>
</div>
"""

    # ── 投资逻辑 ──
    if economic_rationale:
        html += f"""<div class="chart-section">
  <h2>投资逻辑</h2>
  <p>{economic_rationale}</p>
</div>
"""

    # ── 图表 ──
    html += """<div class="chart-section">
  <h2>分层累计收益</h2>
  <div class="chart-container" id="chart-cumulative"></div>
</div>

<div class="analysis-grid">
  <div class="chart-section">
    <h2>IC 时间序列</h2>
    <div class="chart-container" id="chart-ic-ts"></div>
  </div>
  <div class="chart-section">
    <h2>IC 分布</h2>
    <div class="chart-container" id="chart-ic-dist"></div>
  </div>
</div>

<div class="chart-section">
  <h2>分位年化收益</h2>
  <div class="chart-container" id="chart-quantile-bar"></div>
</div>

<div class="chart-section">
  <h2>多空组合净值</h2>
  <div class="chart-container" id="chart-ls"></div>
</div>
"""

    if decay_chart:
        html += """<div class="chart-section">
  <h2>IC 衰变曲线</h2>
  <div class="chart-container" id="chart-ic-decay"></div>
</div>
"""

    # ── 分位收益表 ──
    html += """<div class="chart-section">
  <h2>分位收益明细</h2>
  <table>
    <tr><th>分位</th><th>年化收益</th></tr>
"""
    for q in sorted(analysis.quantile_detail.keys()):
        ret = analysis.quantile_detail[q]
        html += f"    <tr><td>Q{q}</td><td>{ret:.2%}</td></tr>\n"
    html += f"""    <tr style="font-weight:700"><td>Top-Bottom 多空</td><td>{analysis.quantile_spread_annual:.2%}</td></tr>
  </table>
</div>
"""

    # ── 改进方向 ──
    if analysis.improvement_ideas:
        html += """<div class="chart-section">
  <h2>改进方向</h2>
  <ol style="padding-left:20px;">
"""
        for idea in analysis.improvement_ideas:
            html += f"    <li style='margin-bottom:8px;'>{idea}</li>\n"
        html += "  </ol>\n</div>\n"

    # ── 稳健性详情 ──
    if robustness:
        html += f"""<div class="chart-section">
  <h2>稳健性验证</h2>
  <table>
    <tr><th>指标</th><th>值</th></tr>
    <tr><td>前半段 IC_IR</td><td>{robustness.first_half_ic_ir:.3f}</td></tr>
    <tr><td>后半段 IC_IR</td><td>{robustness.second_half_ic_ir:.3f}</td></tr>
    <tr><td>分段测试</td><td>{'✓ 通过' if robustness.split_test_passed else '✗ 未通过'}</td></tr>
    <tr><td>参数稳定性</td><td>{robustness.parameter_stability}</td></tr>
    <tr><td>决策</td><td style="color:{decision_color}; font-weight:700;">{robustness.decision}</td></tr>
    <tr><td>理由</td><td>{robustness.reasoning}</td></tr>
  </table>
</div>
"""

    # ── 页脚 + Plotly JSON ──
    html += f"""<div class="footer">
  Generated by Quant Harness | {now}
</div>

</div>

<script>
var config = {{ responsive: true, displayModeBar: false }};
Plotly.newPlot('chart-cumulative', {chart_cumulative}, {{}}, config);
Plotly.newPlot('chart-ic-ts', {chart_ic_ts}, {{}}, config);
Plotly.newPlot('chart-ic-dist', {chart_ic_dist}, {{}}, config);
Plotly.newPlot('chart-quantile-bar', {chart_quantile_bar}, {{}}, config);
Plotly.newPlot('chart-ls', {chart_ls}, {{}}, config);
"""
    if decay_chart:
        html += f"Plotly.newPlot('chart-ic-decay', {decay_chart}, {{}}, config);\n"

    html += """</script>
</body>
</html>"""
    return html


# ── 图表生成 ──

def _cumulative_returns_chart(result: BacktestResult) -> str:
    """分层累计收益曲线。"""
    fig = go.Figure()
    q_df = result.quantile.quantile_cumulative
    for i, col in enumerate(sorted(q_df.columns)):
        fig.add_trace(go.Scatter(
            x=q_df.index, y=q_df[col],
            mode="lines", name=f"Q{int(col)}",
            line=dict(color=COLORS["quantile"][i], width=1.5),
        ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"]),
        margin=dict(l=40, r=20, t=10, b=40),
        legend=dict(orientation="h", y=1.12),
        xaxis=dict(title="", gridcolor=COLORS["border"]),
        yaxis=dict(title="累计净值", gridcolor=COLORS["border"]),
    )
    return fig.to_json()


def _ic_timeseries_chart(result: BacktestResult) -> str:
    """IC 时间序列图。"""
    ic = result.ic_series.dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ic.index, y=ic.values,
        mode="lines", name="Rank IC",
        line=dict(color=COLORS["accent"], width=1),
        fill="tozeroy", fillcolor="rgba(108,140,255,0.1)",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=COLORS["text_muted"], opacity=0.3)
    fig.add_hline(y=result.ic_mean, line_dash="dot", line_color=COLORS["green"],
                  annotation_text=f"均值={result.ic_mean:.3f}")
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"]),
        margin=dict(l=40, r=20, t=10, b=40),
        xaxis=dict(title="", gridcolor=COLORS["border"]),
        yaxis=dict(title="Rank IC", gridcolor=COLORS["border"]),
    )
    return fig.to_json()


def _ic_distribution_chart(result: BacktestResult) -> str:
    """IC 分布直方图。"""
    ic = result.ic_series.dropna()
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=ic.values, nbinsx=30,
        marker=dict(color=COLORS["accent"], line=dict(color=COLORS["border"], width=1)),
        name="IC 分布",
    ))
    fig.add_vline(x=0, line_dash="dash", line_color=COLORS["red"], opacity=0.5)
    fig.add_vline(x=result.ic_mean, line_dash="dot", line_color=COLORS["green"],
                  annotation_text=f"均值={result.ic_mean:.3f}")
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"]),
        margin=dict(l=40, r=20, t=10, b=40),
        xaxis=dict(title="IC", gridcolor=COLORS["border"]),
        yaxis=dict(title="频次", gridcolor=COLORS["border"]),
    )
    return fig.to_json()


def _quantile_bar_chart(result: BacktestResult) -> str:
    """分位年化收益柱状图。"""
    q_df = result.quantile.quantile_returns
    annual = {int(col): q_df[col].mean() * 252 for col in sorted(q_df.columns)}
    labels = [f"Q{k}" for k in sorted(annual.keys())]
    values = [annual[k] for k in sorted(annual.keys())]
    colors_vals = [COLORS["quantile"][i] for i in range(len(values))]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=values,
        marker=dict(color=colors_vals, line=dict(color=COLORS["border"], width=1)),
        text=[f"{v:.1%}" for v in values],
        textposition="outside",
        textfont=dict(color=COLORS["text"]),
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"]),
        margin=dict(l=40, r=20, t=10, b=40),
        xaxis=dict(title="", gridcolor=COLORS["border"]),
        yaxis=dict(title="年化收益", gridcolor=COLORS["border"]),
        showlegend=False,
    )
    return fig.to_json()


def _long_short_chart(result: BacktestResult) -> str:
    """多空组合净值曲线。"""
    spread = result.quantile.top_bottom_spread.dropna()
    cumulative = (1 + spread).cumprod()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cumulative.index, y=cumulative.values,
        mode="lines", name="多空净值",
        line=dict(color=COLORS["accent"], width=1.5),
        fill="tozeroy", fillcolor="rgba(108,140,255,0.1)",
    ))
    fig.add_hline(y=1.0, line_dash="dash", line_color=COLORS["text_muted"], opacity=0.3)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"]),
        margin=dict(l=40, r=20, t=10, b=40),
        xaxis=dict(title="", gridcolor=COLORS["border"]),
        yaxis=dict(title="多空净值", gridcolor=COLORS["border"]),
    )
    return fig.to_json()


def _ic_decay_chart(dynamic: DynamicMetrics) -> str:
    """IC 衰变曲线。"""
    if not dynamic.ic_decay:
        return ""
    periods = sorted(dynamic.ic_decay.keys())
    values = [dynamic.ic_decay[k] for k in periods]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=periods, y=values,
        mode="lines+markers",
        name="IC 衰变",
        line=dict(color=COLORS["accent"], width=2),
        marker=dict(size=6),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=COLORS["text_muted"], opacity=0.3)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"]),
        margin=dict(l=40, r=20, t=10, b=40),
        xaxis=dict(title="持有期", dtick=1, gridcolor=COLORS["border"]),
        yaxis=dict(title="IC 均值", gridcolor=COLORS["border"]),
    )
    return fig.to_json()


def save_html_report(html: str, output_dir: str = "output/reports") -> Path:
    """保存 HTML 报告到文件。

    Args:
        html: HTML 字符串。
        output_dir: 输出目录。

    Returns:
        保存路径。
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out / f"factor_report_{timestamp}.html"
    path.write_text(html, encoding="utf-8")
    return path
