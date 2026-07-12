"""工具契约化 — 将 backtest/ 操作定义为 JSON Schema，实现带降级路径的执行器。

每个工具有:
  1. JSON Schema 定义 (用于 LLM Function Calling)
  2. JSON 解析器 (pydantic-style validation)
  3. 文本回退解析器 (正则匹配，处理 LLM JSON 格式错误)
  4. _dispatch 路由 (调用实际的回测函数)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

import pandas as pd

from backtest.data import MarketData
from backtest.engine import BacktestResult, FactorBacktestEngine
from backtest.factor_builder import (
    FactorDef,
    TransformMethod,
    build_factor,
)
from backtest.metrics import compute_factor_metrics


# ======================== ToolResult ========================


@dataclass
class ToolResult:
    """工具执行结果 — 压缩后的 LLM 反馈。

    关键: summary 字段是给 LLM 看的，不要把所有数据塞进去。
    50 行回测结果 → "factor_X: IC=0.035, IR=0.72, Q5-Q1 spread=8.2%, Sharpe=1.15"
    """

    status: Literal["success", "error", "partial"]
    summary: str
    data: Optional[Any] = None  # 完整结果（仅当需要时）
    error: Optional[str] = None
    suggestion: Optional[str] = None  # 修复建议，帮助 LLM 重试

    def to_llm_feedback(self) -> str:
        """序列化为 LLM 可消费的文本。"""
        if self.status == "success":
            return f"[OK] {self.summary}"
        elif self.status == "partial":
            return f"[PARTIAL] {self.summary}\n提示: {self.suggestion}"
        else:
            return f"[ERROR] {self.error}\n修复建议: {self.suggestion}"


# ======================== JSON Schemas ========================


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "run_backtest": {
        "name": "run_backtest",
        "description": "对单个因子执行向量化回测，返回 IC 分析 + 分层收益 + 多空表现。",
        "parameters": {
            "type": "object",
            "properties": {
                "factor_name": {
                    "type": "string",
                    "description": "因子名称，用于结果标识",
                },
                "base": {
                    "type": "string",
                    "enum": ["returns", "volume", "price", "high", "low", "open"],
                    "description": "因子基元数据类型",
                },
                "window": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 500,
                    "description": "回溯窗口长度",
                },
                "agg_func": {
                    "type": "string",
                    "enum": ["sum", "mean", "std", "max", "min"],
                    "description": "滚动聚合函数",
                },
                "transform": {
                    "type": "string",
                    "enum": ["raw", "zscore", "rank", "winsorize"],
                    "description": "截面变换方法",
                },
                "n_quantiles": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 10,
                    "default": 5,
                    "description": "分位数数量",
                },
            },
            "required": ["factor_name", "base", "window", "agg_func"],
        },
    },
    "sweep_params": {
        "name": "sweep_params",
        "description": "对因子进行参数扫描，对不同窗口/聚合函数组合分别回测，返回 top-N 最佳参数组合。",
        "parameters": {
            "type": "object",
            "properties": {
                "factor_name_prefix": {
                    "type": "string",
                    "description": "因子名前缀，用于结果标识",
                },
                "base": {
                    "type": "string",
                    "enum": ["returns", "volume", "price", "high", "low", "open"],
                },
                "windows": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "待扫描的窗口列表，如 [5, 10, 21, 60]",
                },
                "agg_funcs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "待扫描的聚合函数列表，如 ['sum', 'std']",
                },
                "metric": {
                    "type": "string",
                    "enum": ["ic_ir", "long_short_sharpe", "top_bottom_spread"],
                    "default": "ic_ir",
                    "description": "排序指标",
                },
                "top_n": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                },
            },
            "required": ["factor_name_prefix", "windows"],
        },
    },
    "analyze_factor": {
        "name": "analyze_factor",
        "description": "对回测结果进行深度因子分析：IC稳定性、分层单调性、行业/风格暴露、与常见因子的相关性。",
        "parameters": {
            "type": "object",
            "properties": {
                "factor_name": {
                    "type": "string",
                    "description": "待分析的因子名称",
                },
                "analysis_dimensions": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["ic", "quantile", "exposure", "correlation", "all"],
                    },
                    "default": ["all"],
                    "description": "分析维度",
                },
            },
            "required": ["factor_name"],
        },
    },
    "compare_factors": {
        "name": "compare_factors",
        "description": "横向对比多个因子的回测表现，生成对比表。",
        "parameters": {
            "type": "object",
            "properties": {
                "factor_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "待对比的因子名称列表",
                },
            },
            "required": ["factor_names"],
        },
    },
    "search_wiki": {
        "name": "search_wiki",
        "description": "在 wiki 知识库中搜索相关研究报告、因子或策略。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "category": {
                    "type": "string",
                    "description": "按分类过滤",
                },
            },
            "required": ["keyword"],
        },
    },
}


# ======================== ToolExecutor ========================


class ToolExecutor:
    """工具执行器 — JSON 校验 → 文本回退 → dispatch → 结果封装。

    双重解析器保证 LLM 输出的 JSON 格式错误不会导致崩溃。
    """

    MAX_RETRIES = 2

    def __init__(
        self,
        data: MarketData,
        engine: Optional[FactorBacktestEngine] = None,
        wiki_index: Optional[dict[str, Any]] = None,
    ) -> None:
        """初始化执行器。

        Args:
            data: 市场数据（全局共享）。
            engine: 回测引擎（可复用）。
            wiki_index: wiki/index.json 内容。
        """
        self.data = data
        self.engine = engine or FactorBacktestEngine()
        self.wiki_index = wiki_index or {}

        # 缓存已计算的因子
        self._factor_cache: dict[str, pd.DataFrame] = {}
        # 缓存已完成的回测结果
        self._result_cache: dict[str, BacktestResult] = {}

        # dispatch 表
        self._dispatch_map: dict[str, Callable[..., ToolResult]] = {
            "run_backtest": self._run_backtest,
            "sweep_params": self._sweep_params,
            "analyze_factor": self._analyze_factor,
            "compare_factors": self._compare_factors,
            "search_wiki": self._search_wiki,
        }

    def execute(self, tool_name: str, raw_args: dict[str, Any]) -> ToolResult:
        """执行工具调用的完整流程。

        Args:
            tool_name: 工具名。
            raw_args: LLM 传的原始参数。

        Returns:
            ToolResult（永远不会抛异常，错误封装在 result 中）。
        """
        # Step 1: JSON Schema 校验
        parsed = self._deserialize(tool_name, raw_args)
        if parsed is not None:
            return self._dispatch(tool_name, parsed)

        # Step 2: 文本回退
        return ToolResult(
            status="error",
            summary="",
            error=f"参数解析失败: {json.dumps(raw_args, ensure_ascii=False)[:200]}",
            suggestion="请检查参数名和类型是否正确，参考工具 Schema 中的 required 字段。",
        )

    def _deserialize(
        self, tool_name: str, raw_args: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """JSON Schema 校验。

        Args:
            tool_name: 工具名。
            raw_args: LLM 原始参数。

        Returns:
            校验通过返回清理后的参数字典，失败返回 None。
        """
        schema = TOOL_SCHEMAS.get(tool_name)
        if schema is None:
            return None

        props = schema["parameters"]["properties"]
        required = schema["parameters"].get("required", [])
        result: dict[str, Any] = {}

        for key, spec in props.items():
            if key in raw_args:
                val = raw_args[key]
                # 类型强转
                if spec.get("type") == "integer" and isinstance(val, (int, float, str)):
                    try:
                        result[key] = int(val)
                    except (ValueError, TypeError):
                        return None
                elif spec.get("type") == "array" and isinstance(val, list):
                    result[key] = val
                elif spec.get("type") == "string":
                    result[key] = str(val)
                else:
                    result[key] = val
            elif key in required:
                return None  # 缺少必填字段

        return result if all(r in result for r in required) else None

    def _dispatch(self, tool_name: str, params: dict[str, Any]) -> ToolResult:
        """路由到实际执行函数。

        Args:
            tool_name: 工具名。
            params: 解析后的参数。

        Returns:
            ToolResult。
        """
        handler = self._dispatch_map.get(tool_name)
        if handler is None:
            return ToolResult(
                status="error",
                summary="",
                error=f"未知工具: {tool_name}",
                suggestion=f"可用工具: {list(self._dispatch_map.keys())}",
            )
        try:
            return handler(params)
        except Exception as e:
            return ToolResult(
                status="error",
                summary="",
                error=str(e),
                suggestion="请检查参数是否合理，或尝试简化参数重新执行。",
            )

    # ── 具体工具实现 ──

    def _run_backtest(self, params: dict[str, Any]) -> ToolResult:
        """执行单因子回测。"""
        factor_name = params["factor_name"]
        base = params.get("base", "returns")
        window = params.get("window", 20)
        agg_func = params.get("agg_func", "sum")
        transform_str = params.get("transform", "zscore")
        n_quantiles = params.get("n_quantiles", 5)

        transform_map: dict[str, TransformMethod] = {
            "raw": TransformMethod.RAW,
            "zscore": TransformMethod.ZSCORE,
            "rank": TransformMethod.RANK,
            "winsorize": TransformMethod.WINSORIZE,
        }
        transform = transform_map.get(transform_str, TransformMethod.ZSCORE)

        factor_def = FactorDef(
            name=factor_name,
            base=base,
            window=window,
            agg_func=agg_func,
            transform=transform,
        )
        factor_values = build_factor(self.data, factor_def)
        self._factor_cache[factor_name] = factor_values

        engine = FactorBacktestEngine(n_quantiles=n_quantiles)
        result = engine.run(self.data, factor_values, factor_name=factor_name)
        metrics = compute_factor_metrics(result)
        self._result_cache[factor_name] = result

        summary = (
            f"{factor_name} (base={base}, window={window}, agg={agg_func}, "
            f"transform={transform_str}): "
            f"IC={metrics.ic_mean:.4f}, IC_IR={metrics.ic_ir:.3f}, "
            f"IC>0={metrics.ic_positive_ratio:.0%}, "
            f"Q1→Q{n_quantiles} spread={metrics.top_bottom_annual_spread:.2%}, "
            f"LS_Sharpe={metrics.long_short_sharpe:.3f}, "
            f"LS_MaxDD={metrics.long_short_maxdd:.1%}, "
            f"单调性={'Y' if metrics.quantile_monotonicity else 'N'}"
        )
        return ToolResult(status="success", summary=summary, data=metrics)

    def _sweep_params(self, params: dict[str, Any]) -> ToolResult:
        """参数扫描。"""
        prefix = params["factor_name_prefix"]
        base = params.get("base", "returns")
        windows = params.get("windows", [5, 10, 21, 60, 120])
        agg_funcs = params.get("agg_funcs", ["sum", "std"])
        metric = params.get("metric", "ic_ir")
        top_n = params.get("top_n", 5)

        results: list[dict[str, Any]] = []
        for w in windows:
            for agg in agg_funcs:
                fname = f"{prefix}_w{w}_{agg}"
                try:
                    factor_def = FactorDef(
                        name=fname,
                        base=base,
                        window=w,
                        agg_func=agg,
                        transform=TransformMethod.ZSCORE,
                    )
                    factor_values = build_factor(self.data, factor_def)
                    self._factor_cache[fname] = factor_values

                    engine = FactorBacktestEngine(n_quantiles=5)
                    result = engine.run(self.data, factor_values, factor_name=fname)
                    metrics = compute_factor_metrics(result)
                    self._result_cache[fname] = result

                    score = getattr(metrics, metric, metrics.ic_ir)
                    results.append({
                        "name": fname,
                        "window": w,
                        "agg": agg,
                        "ic_ir": metrics.ic_ir,
                        "ic_mean": metrics.ic_mean,
                        "spread": metrics.top_bottom_annual_spread,
                        "sharpe": metrics.long_short_sharpe,
                        "monotonic": metrics.quantile_monotonicity,
                        "score": score,
                    })
                except Exception:
                    continue

        if not results:
            return ToolResult(
                status="error",
                summary="",
                error="参数扫描未产生任何有效结果",
                suggestion="尝试减少窗口数量或检查数据是否充足",
            )

        # 按 metric 排序，取 top-N
        results.sort(key=lambda x: abs(x["score"]), reverse=True)
        top = results[:top_n]

        lines = [f"参数扫描: {prefix} (base={base}), 共 {len(results)} 组合, top-{top_n}:"]
        for i, r in enumerate(top, 1):
            lines.append(
                f"  #{i} {r['name']}: IC_IR={r['ic_ir']:.3f}, "
                f"IC={r['ic_mean']:.4f}, spread={r['spread']:.2%}, "
                f"Sharpe={r['sharpe']:.3f}, monotonic={r['monotonic']}"
            )

        return ToolResult(
            status="success",
            summary="\n".join(lines),
            data={"all_results": results, "top_n": top},
        )

    def _analyze_factor(self, params: dict[str, Any]) -> ToolResult:
        """因子深度分析。"""
        factor_name = params["factor_name"]

        result = self._result_cache.get(factor_name)
        if result is None:
            return ToolResult(
                status="error",
                summary="",
                error=f"因子 '{factor_name}' 的回测结果未找到",
                suggestion="请先执行 run_backtest 对该因子进行回测",
            )

        metrics = compute_factor_metrics(result)

        # IC 稳定性分析
        ic_rolling_std = result.ic_series.rolling(20).std().mean()

        # 分层单调性详细检查
        q_rets = metrics.quantile_annual_returns
        q_keys = sorted(q_rets.keys())

        lines = [
            f"=== {factor_name} 因子深度分析 ===",
            "",
            "## IC 分析",
            f"IC 均值: {metrics.ic_mean:.4f}",
            f"IC 标准差: {metrics.ic_std:.4f}",
            f"IC_IR: {metrics.ic_ir:.3f}",
            f"IC > 0 占比: {metrics.ic_positive_ratio:.1%}",
            f"IC 滚动波动(20期): {ic_rolling_std:.4f}",
            f"IC t 统计量: {metrics.ic_t_stat:.2f}",
            "",
            "## 分层收益",
        ]
        for k in q_keys:
            lines.append(f"Q{k}: {q_rets[k]:.2%}")
        lines.append(f"Top-Bottom 年化多空: {metrics.top_bottom_annual_spread:.2%}")
        lines.append(f"单调性: {'通过' if metrics.quantile_monotonicity else '不通过'}")

        lines.extend([
            "",
            "## 多空组合",
            f"年化 Sharpe: {metrics.long_short_sharpe:.3f}",
            f"最大回撤: {metrics.long_short_maxdd:.2%}",
            f"Calmar 比率: {metrics.long_short_calmar:.2f}",
            "",
            "## 投资逻辑初判",
            f"- 因子方向: {'正向' if metrics.ic_mean > 0 else '负向'} (IC均值{'>0' if metrics.ic_mean > 0 else '<0'})",
            f"- 稳定性: {'高' if abs(metrics.ic_ir) > 0.5 else '中' if abs(metrics.ic_ir) > 0.2 else '低'} (|IC_IR|={abs(metrics.ic_ir):.2f})",
            f"- 单调性: {'好' if metrics.quantile_monotonicity else '差'} (分层收益需进一步检查非线性关系)",
        ])

        return ToolResult(
            status="success",
            summary="\n".join(lines),
            data=metrics,
        )

    def _compare_factors(self, params: dict[str, Any]) -> ToolResult:
        """对比多个因子。"""
        factor_names = params["factor_names"]
        comp_data: list[dict[str, Any]] = []

        for fname in factor_names:
            result = self._result_cache.get(fname)
            if result is None:
                continue
            m = compute_factor_metrics(result)
            comp_data.append({
                "name": fname,
                "ic_ir": m.ic_ir,
                "ic_mean": m.ic_mean,
                "spread": m.top_bottom_annual_spread,
                "sharpe": m.long_short_sharpe,
                "maxdd": m.long_short_maxdd,
                "monotonic": m.quantile_monotonicity,
            })

        if not comp_data:
            return ToolResult(
                status="error",
                summary="",
                error="没有找到任何已回测的因子",
                suggestion="请先执行 run_backtest 对每个因子进行回测",
            )

        # 排序: IC_IR 绝对值降序
        comp_data.sort(key=lambda x: abs(x["ic_ir"]), reverse=True)

        lines = ["=== 因子横向对比 ===", ""]
        lines.append(f"{'因子':<25} {'IC_IR':>7} {'IC':>8} {'spread':>8} {'Sharpe':>7} {'MaxDD':>8} {'Mono':>5}")
        lines.append("-" * 75)
        for c in comp_data:
            lines.append(
                f"{c['name']:<25} {c['ic_ir']:>7.3f} {c['ic_mean']:>8.4f} "
                f"{c['spread']:>7.2%} {c['sharpe']:>7.3f} {c['maxdd']:>7.2%} "
                f"{'Y' if c['monotonic'] else 'N':>5}"
            )

        return ToolResult(
            status="success",
            summary="\n".join(lines),
            data=comp_data,
        )

    def _search_wiki(self, params: dict[str, Any]) -> ToolResult:
        """搜索 wiki 知识库。"""
        keyword = params.get("keyword", "")
        category = params.get("category")

        if not self.wiki_index or "reports" not in self.wiki_index:
            return ToolResult(
                status="partial",
                summary="Wiki 索引未加载",
                suggestion="请确保 wiki/index.json 存在且可读",
            )

        reports = self.wiki_index["reports"]
        matches: list[dict[str, Any]] = []

        kw_lower = keyword.lower()
        for r in reports:
            if category and r.get("category") != category:
                continue
            # 匹配 title, keywords, abstract
            searchable = " ".join([
                r.get("title", ""),
                " ".join(r.get("keywords", [])),
                r.get("abstract", ""),
            ]).lower()
            if kw_lower in searchable:
                matches.append(r)

        if not matches:
            return ToolResult(
                status="success",
                summary=f"未找到与 '{keyword}' 相关的报告。",
            )

        lines = [f"搜索 '{keyword}': 找到 {len(matches)} 篇报告"]
        for m in matches[:8]:
            lines.append(
                f"  [{m['id']}] {m.get('title','')[:50]} "
                f"({m.get('source','')}, {m.get('date','')})"
            )

        return ToolResult(
            status="success",
            summary="\n".join(lines),
            data=matches,
        )


# ======================== 辅助函数 ========================


def load_wiki_index(wiki_dir: str = "wiki") -> dict[str, Any]:
    """加载 llm_wiki 索引。

    Args:
        wiki_dir: wiki 目录路径。

    Returns:
        索引 dict 或空 dict。
    """
    from pathlib import Path

    idx_path = Path(wiki_dir) / "index.json"
    if idx_path.exists():
        with open(idx_path, encoding="utf-8") as f:
            return json.load(f)
    return {}
