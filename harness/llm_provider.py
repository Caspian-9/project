"""LLM 提供商抽象 — 解耦具体 LLM API，支持 Anthropic/OpenAI/本地模型。

遵循 HARNESS_DESIGN.md 附录 A 的接口约定。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolCall:
    """LLM 返回的工具调用。"""

    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """统一的 LLM 响应结构。"""

    text: str
    tool_calls: Optional[list[ToolCall]] = None
    tokens_used: int = 0
    latency_ms: int = 0


class LLMProvider(ABC):
    """LLM 提供商抽象基类。

    子类实现 chat 方法，适配具体的 LLM API。
    """

    @abstractmethod
    def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> LLMResponse:
        """调用 LLM 聊天接口。

        Args:
            system: 系统 prompt。
            messages: 对话历史 [{"role": "user"|"assistant", "content": "..."}]。
            tools: 可用的工具 JSON Schema 列表。

        Returns:
            LLMResponse。
        """
        ...


class MockLLMProvider(LLMProvider):
    """Mock LLM 提供商 — 用于测试，不调用任何外部 API。

    返回固定的模拟响应，方便在不依赖外部 API 的情况下测试 harness 流程。
    """

    def __init__(self, mock_response: str = "") -> None:
        """初始化 Mock 提供商。

        Args:
            mock_response: 模拟返回的文本。
        """
        self.mock_response = mock_response or "这是一个 mock LLM 响应。"
        self.call_count = 0

    def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> LLMResponse:
        """返回模拟响应。

        Args:
            system: 系统 prompt。
            messages: 对话历史。
            tools: 工具列表。

        Returns:
            模拟的 LLMResponse。
        """
        self.call_count += 1
        return LLMResponse(
            text=self.mock_response,
            tool_calls=None,
            tokens_used=100,
            latency_ms=1,
        )
