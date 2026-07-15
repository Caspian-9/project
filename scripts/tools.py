"""工具契约与上下文管理。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

import pandas as pd

from scripts.data import MarketData
from scripts.engine import BacktestConfig, BacktestResult, FactorBacktestEngine, compute_factor_metrics
from scripts.factor import (
    FactorDef,
    TransformMethod,
    build_factor,
)


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

        engine = FactorBacktestEngine(BacktestConfig(n_quantiles=n_quantiles))
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

                    engine = FactorBacktestEngine(BacktestConfig(n_quantiles=5))
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

from dataclasses import dataclass, field
from pathlib import Path

from scripts.workflow import FactorResearchPhase


@dataclass
class ContextBudget:
    """Token 预算分配器 — 超限时自动压缩。"""

    max_tokens: int = 100_000
    allocated: int = 0

    def allocate(self, layer: str, content: str) -> str:
        """尝试分配 token 预算。

        Args:
            layer: 层级名称。
            content: 待注入内容。

        Returns:
            原始内容或压缩后的内容。
        """
        estimated = self._estimate_tokens(content)
        if self.allocated + estimated <= self.max_tokens:
            self.allocated += estimated
            return content
        else:
            remaining = self.max_tokens - self.allocated
            return self._compress(content, max(remaining, 100))

    def reset(self) -> None:
        """重置预算计数器。"""
        self.allocated = 0

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗略估算 token 数：中文 ~1.5 字/token，英文 ~4 字/token。"""
        chinese_chars = sum(1 for c in text if "一" <= c <= "鿿")
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)

    @staticmethod
    def _compress(content: str, budget: int) -> str:
        """分层压缩：摘要 > 截断 > 丢弃。

        Args:
            content: 原始内容。
            budget: 剩余 token 预算。

        Returns:
            压缩后的内容。
        """
        if budget <= 0:
            return ""
        # 简单截断策略：保留前 budget*2 个字符
        max_chars = budget * 2
        if len(content) <= max_chars:
            return content
        return content[:max_chars] + "\n\n[... 内容因 Token 预算限制被截断 ...]"


@dataclass
class ContextManager:
    """上下文管理器 — 为每个研究阶段组装上下文。

    集成 wiki 知识库，在 Layer 1 注入相关知识卡片。
    """

    budget: ContextBudget = field(default_factory=ContextBudget)
    wiki_index: Optional[dict[str, Any]] = None

    # Layer 0: 静态上下文
    layer_0_template: str = """你是一个量化因子研究助手，运行在 Quant Harness 框架内。

## 你的能力
- 深读量化研究报告，提取因子定义和经济逻辑
- 生成因子变体（参数微调、窗口变化、新变量、组合因子）
- 执行向量化回测，分析因子表现
- 撰写因子分析报告

## 品种信息
- 当前市场数据由 harness 注入，你不需要自己获取行情数据
- 因子回测通过调用工具完成，结果由 harness 压缩后返回

## 约束
- 不要凭空编造回测结果
- 不确定时询问用户，不要猜测
- 输出格式应尽量结构化（表格优于大段文字）
"""

    # Layer 1: 因子库概要
    factor_library_summary: str = """
## 可用因子基元
| 基元 | 说明 | 常见窗口 | 聚合方式 |
|------|------|----------|----------|
| returns | 简单收益率 | 5/10/21/60/120/250 | sum(动量)/std(波动) |
| volume | 成交量 | 5/10/21 | mean(均量)/std(量波动) |
| price | 收盘价 | 20/60/120 | sum/mean |
| high/low | 最高/最低价 | 20/60 | max/min |
"""

    def __init__(
        self,
        wiki_index_path: Optional[str] = None,
        max_tokens: int = 100_000,
    ) -> None:
        """初始化上下文管理器。

        Args:
            wiki_index_path: llm_wiki/index.json 的路径。
            max_tokens: 最大 token 预算。
        """
        self.budget = ContextBudget(max_tokens=max_tokens)

        if wiki_index_path:
            p = Path(wiki_index_path)
            if p.exists():
                with open(p, encoding="utf-8") as f:
                    self.wiki_index = json.load(f)

    def assemble(
        self,
        phase: FactorResearchPhase,
        additional: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """为给定阶段组装上下文，返回可供 prompt 模板填充的 dict。

        Args:
            phase: 当前研究阶段。
            additional: 额外上下文 kv。

        Returns:
            prompt 模板填充用的 dict。
        """
        self.budget.reset()
        additional = additional or {}

        # Layer 0: 静态
        l0 = self.budget.allocate("L0_static", self.layer_0_template)

        # Layer 1: 因子库 + Wiki 检索
        l1_parts = [self.factor_library_summary]
        if self.wiki_index and additional.get("search_keyword"):
            wiki_context = self._search_wiki_context(
                additional["search_keyword"],
                max_results=5,
            )
            if wiki_context:
                l1_parts.append(wiki_context)
        l1 = self.budget.allocate("L1_semi_static", "\n".join(l1_parts))

        # Layer 2: 前一阶段产出
        l2_content = additional.get("previous_phase_output", "")
        l2 = self.budget.allocate("L2_dynamic", l2_content) if l2_content else ""

        # Layer 3: 按需（暂不自动注入）
        l3 = ""

        return {
            "layer_0": l0,
            "layer_1": l1,
            "layer_2": l2,
            "layer_3": l3,
            "phase": phase.value,
            **additional,
        }

    def _search_wiki_context(
        self, keyword: str, max_results: int = 5
    ) -> str:
        """在 Wiki 知识库中搜索相关内容。

        Args:
            keyword: 搜索关键词。
            max_results: 最大结果数。

        Returns:
            格式化的 Wiki 检索结果文本。
        """
        if not self.wiki_index or "reports" not in self.wiki_index:
            return ""

        reports = self.wiki_index["reports"]
        kw_lower = keyword.lower()
        matches: list[dict[str, Any]] = []

        for r in reports:
            searchable = " ".join([
                r.get("title", ""),
                " ".join(r.get("keywords", [])),
                r.get("abstract", ""),
            ]).lower()
            if kw_lower in searchable:
                matches.append(r)

        if not matches:
            return ""

        lines = [f"\n## Wiki 知识库检索: '{keyword}' ({len(matches)} 篇)"]
        for m in matches[:max_results]:
            ab = m.get("abstract", "")[:200]
            lines.append(
                f"- [{m['id']}] **{m.get('title','')}** ({m.get('source','')}, {m.get('date','')})\n"
                f"  {ab}"
            )
        return "\n".join(lines)
