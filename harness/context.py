"""上下文管理器 — 分层注入 + Token 预算控制。

四层注入体系 (HARNESS_DESIGN.md Phase 3):
  Layer 0 (静态, ~2K tokens): 角色定义、品种知识、市场状态
  Layer 1 (准静态, ~3K tokens): 因子库索引、Wiki 知识检索、可用工具列表
  Layer 2 (动态, ~5-10K tokens): 前一阶段产出（回测摘要、参数扫描 top-N）
  Layer 3 (详细, 按需): 完整回测结果、原始行情切片（仅在 LLM 明确请求时注入）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from harness.workflow import FactorResearchPhase


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
