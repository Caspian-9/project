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
    id: str = ""  # Anthropic tool_use_id, 用于 tool_result 匹配


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


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API 提供商 — 真正的 LLM 调用。

    使用 anthropic Python SDK，处理 tool_use content block。

    支持配置:
      - 环境变量 ANTHROPIC_API_KEY（如果未显式传入 api_key）
      - 环境变量 ANTHROPIC_BASE_URL（自定义 API 端点/代理）
      - 环境变量 ANTHROPIC_MODEL（默认模型名）
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        max_tokens: int = 4096,
        base_url: str = "",
        timeout: float = 120.0,
    ) -> None:
        """初始化 Anthropic 提供商。

        Args:
            api_key: Anthropic API key。为空时从 ANTHROPIC_API_KEY 环境变量读取。
            model: 模型 ID。为空时从 ANTHROPIC_MODEL 环境变量读取，默认 claude-sonnet-5。
            max_tokens: 最大输出 token。
            base_url: 自定义 API 端点（如代理地址）。为空时从 ANTHROPIC_BASE_URL 读取。
            timeout: 请求超时秒数。
        """
        import anthropic
        import os

        # 解析 API key: 参数 > ANTHROPIC_API_KEY > ANTHROPIC_AUTH_TOKEN
        resolved_key = (
            api_key
            or os.environ.get("ANTHROPIC_API_KEY", "")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        )
        if not resolved_key:
            raise ValueError(
                "未找到 Anthropic API key。请设置环境变量 ANTHROPIC_API_KEY "
                "或传入 api_key 参数。"
            )

        # 解析 model: 参数 > 环境变量 > 默认值
        resolved_model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

        # 解析 base_url: 参数 > 环境变量
        resolved_base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL", "")

        client_kwargs: dict[str, Any] = {
            "api_key": resolved_key,
            "timeout": timeout,
        }
        if resolved_base_url:
            client_kwargs["base_url"] = resolved_base_url

        self.client = anthropic.Anthropic(**client_kwargs)
        self.model = resolved_model
        self.max_tokens = max_tokens
        self.base_url = resolved_base_url

    def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> LLMResponse:
        """调用 Anthropic Messages API。

        将 tools 从 JSON Schema 格式转换为 Anthropic tool 格式，
        解析返回的 tool_use content block。

        Args:
            system: 系统 prompt。
            messages: 对话历史。
            tools: 工具 JSON Schema 列表。

        Returns:
            LLMResponse，含文本和/或 tool_calls。
        """
        import time

        # 转换消息格式
        api_messages: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "user")
            if role not in ("user", "assistant"):
                role = "user"
            content = m.get("content", "")
            # content 可以是 str 或 list[ContentBlock] (tool_use / tool_result)
            api_messages.append({"role": role, "content": content})

        # 转换 tools 格式: JSON Schema → Anthropic tool format
        api_tools: Optional[list[dict[str, Any]]] = None
        if tools:
            api_tools = []
            for t in tools:
                api_tools.append({
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": {
                        "type": "object",
                        "properties": t.get("parameters", {}).get("properties", {}),
                        "required": t.get("parameters", {}).get("required", []),
                    },
                })

        # 调用 API
        start = time.time()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": api_messages,
        }
        if api_tools:
            kwargs["tools"] = api_tools

        response = self.client.messages.create(**kwargs)
        latency_ms = int((time.time() - start) * 1000)

        # 解析响应
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        name=block.name,
                        arguments=dict(block.input) if block.input else {},
                        id=block.id,
                    )
                )
            elif block.type == "thinking":
                # DeepSeek/Claude thinking blocks — skip silently
                pass

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls if tool_calls else None,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            latency_ms=latency_ms,
        )


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
