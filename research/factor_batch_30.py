"""批量因子回测: 30个因子 × CSI300 → 更新 wiki factors/ 页面。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.data import load_csi300
from scripts.engine import BacktestResult, compute_factor_metrics
from scripts.factor import FactorDef, TransformMethod, build_factor, FactorBacktestEngine
from scripts.analysis import analyze_factor, robustness_check

data = load_csi300()
engine = FactorBacktestEngine(n_quantiles=5)

# ── 30 个因子定义 ──
FACTORS: list[dict[str, Any]] = [
    # === 动量类 (6) ===
    {"name": "momentum_1m", "base": "returns", "window": 21, "agg_func": "sum", "category": "动量因子"},
    {"name": "momentum_3m", "base": "returns", "window": 63, "agg_func": "sum", "category": "动量因子"},
    {"name": "momentum_6m", "base": "returns", "window": 126, "agg_func": "sum", "category": "动量因子"},
    {"name": "momentum_12m", "base": "returns", "window": 252, "agg_func": "sum", "category": "动量因子"},
    {"name": "short_reversal", "base": "returns", "window": 5, "agg_func": "sum", "category": "反转因子"},
    {"name": "momentum_1w", "base": "returns", "window": 5, "agg_func": "sum", "category": "动量因子"},

    # === 波动类 (6) ===
    {"name": "volatility_1m", "base": "returns", "window": 21, "agg_func": "std", "category": "波动因子"},
    {"name": "volatility_3m", "base": "returns", "window": 63, "agg_func": "std", "category": "波动因子"},
    {"name": "volatility_6m", "base": "returns", "window": 126, "agg_func": "std", "category": "波动因子"},
    {"name": "volatility_12m", "base": "returns", "window": 252, "agg_func": "std", "category": "波动因子"},
    {"name": "price_vol_1m", "base": "price", "window": 21, "agg_func": "std", "category": "波动因子"},
    {"name": "price_vol_3m", "base": "price", "window": 63, "agg_func": "std", "category": "波动因子"},

    # === 价格形态类 (8) ===
    {"name": "gh_momentum_26w", "base": "price", "window": 130, "agg_func": "max", "operation": "ratio", "category": "动量因子"},
    {"name": "price_ma_ratio_1m", "base": "price", "window": 21, "agg_func": "mean", "operation": "ratio", "category": "趋势因子"},
    {"name": "price_ma_ratio_3m", "base": "price", "window": 63, "agg_func": "mean", "operation": "ratio", "category": "趋势因子"},
    {"name": "price_ma_ratio_6m", "base": "price", "window": 126, "agg_func": "mean", "operation": "ratio", "category": "趋势因子"},
    {"name": "price_52w_high", "base": "price", "window": 252, "agg_func": "max", "operation": "ratio", "category": "动量因子"},
    {"name": "price_52w_low", "base": "price", "window": 252, "agg_func": "min", "operation": "ratio", "category": "反转因子"},
    {"name": "high_low_spread", "base": "high", "window": 21, "agg_func": "mean", "category": "波动因子"},
    {"name": "price_trend_6m", "base": "price", "window": 126, "agg_func": "sum", "category": "趋势因子"},

    # === 成交量类 (6) ===
    {"name": "volume_ratio_1m", "base": "volume", "window": 21, "agg_func": "mean", "operation": "ratio", "category": "成交量因子"},
    {"name": "volume_ratio_3m", "base": "volume", "window": 63, "agg_func": "mean", "operation": "ratio", "category": "成交量因子"},
    {"name": "volume_trend_1m", "base": "volume", "window": 21, "agg_func": "sum", "category": "成交量因子"},
    {"name": "volume_trend_3m", "base": "volume", "window": 63, "agg_func": "sum", "category": "成交量因子"},
    {"name": "volume_volatility", "base": "volume", "window": 21, "agg_func": "std", "category": "成交量因子"},
    {"name": "vol_price_combo", "base": "volume", "window": 21, "agg_func": "mean", "category": "成交量因子"},

    # === 综合类 (4) ===
    {"name": "returns_range_1m", "base": "high", "window": 21, "agg_func": "max", "operation": "ratio", "category": "波动因子"},
    {"name": "price_momo_1m", "base": "price", "window": 21, "agg_func": "sum", "category": "动量因子"},
    {"name": "price_momo_3m", "base": "price", "window": 63, "agg_func": "sum", "category": "动量因子"},
    {"name": "returns_accel", "base": "returns", "window": 21, "agg_func": "mean", "category": "动量因子"},
]

print(f"总计: {len(FACTORS)} 个因子")
print(f"{'因子':<25} {'IC_IR':>8} {'IC_mean':>8} {'Sharpe':>8} {'MaxDD':>8} {'mono':>5} {'评级':>4} {'决策':>12}")
print("-" * 90)

results_summary: dict[str, dict] = {}

for i, fspec in enumerate(FACTORS):
    name = fspec["name"]
    try:
        op = fspec.get("operation")
        fd = FactorDef(
            name=name, base=fspec["base"], window=fspec["window"],
            agg_func=fspec["agg_func"], transform=TransformMethod.ZSCORE,
            operation=op,
        )
        factor_values = build_factor(data, fd)
        result = engine.run(data, factor_values, factor_name=name)
        analysis = analyze_factor(result, data, f"{name}: {fspec['category']}")
        robust = robustness_check(name, result.ic_series)
        m = compute_factor_metrics(result)

        print(f"{name:<25} {result.ic_ir:>8.3f} {result.ic_mean:>8.4f} "
              f"{result.long_short_sharpe:>8.3f} {result.long_short_maxdd:>7.1%} "
              f"{'Y' if analysis.quantile_monotonic else 'N':>5} "
              f"{analysis.quality_grade:>4} {robust.decision:>12}")

        results_summary[name] = {
            "ic_ir": result.ic_ir, "ic_mean": result.ic_mean,
            "sharpe": result.long_short_sharpe, "maxdd": result.long_short_maxdd,
            "monotonic": analysis.quantile_monotonic, "grade": analysis.quality_grade,
            "decision": robust.decision, "quantile_detail": analysis.quantile_detail,
            "strength": analysis.strength, "weakness": analysis.weakness,
            "category": fspec["category"],
        }
    except Exception as e:
        print(f"{name:<25} ERROR: {e}")

# Save results
out_path = Path("research/factor_batch_results.json")
out_path.write_text(json.dumps(results_summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n结果已保存: {out_path}")

# Rank by |IC_IR|
ranked = sorted(results_summary.items(), key=lambda x: abs(x[1]["ic_ir"]), reverse=True)
print(f"\n=== Top 10 ===")
for i, (name, r) in enumerate(ranked[:10], 1):
    print(f"  #{i} {name}: IC_IR={r['ic_ir']:.3f}, 评级={r['grade']}, 决策={r['decision']}")
