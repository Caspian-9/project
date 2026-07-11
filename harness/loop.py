"""Harness 主循环 — 因子研究 REPL 入口。

QuantHarness 是用户交互的主类，协调 LLM + 工具执行 + 工作流。
支持三种调用模式:
  1. 交互式 REPL: harness.repl()
  2. CLI 一次性任务: harness.run_workflow(...)
  3. Python API: harness.quick_test(...)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from backtest.data import MarketData, generate_synthetic_data
from backtest.engine import FactorBacktestEngine
from harness.analysis_engine import analyze_factor
from harness.context import ContextManager
from harness.factor_engine import VariantGenerator
from harness.llm_provider import LLMProvider, MockLLMProvider
from harness.persistence import HarnessPersistence
from harness.reports import generate_factor_report
from harness.tools import TOOL_SCHEMAS, ToolExecutor, load_wiki_index
from harness.workflow import (
    PHASE_PROMPTS,
    FactorResearchPhase,
    FactorResearchWorkflow,
)


class QuantHarness:
    """量化因子研究 Harness — 包裹 LLM 的 REPL 闭环容器。

    职责:
      - 协调整体研究流程（SELECT → GENERATE_BACKTEST → ANALYZE）
      - 管理 LLM 调用 + 上下文注入
      - 桥接工具执行（LLM tool_use → ToolExecutor → backtest）
      - 持久化会话和回测结果
    """

    def __init__(
        self,
        workspace: Optional[Path] = None,
        data: Optional[MarketData] = None,
        llm: Optional[LLMProvider] = None,
        wiki_dir: str = "llm_wiki",
    ) -> None:
        """初始化 Harness。

        Args:
            workspace: 工作空间目录（默认 harness_workspace/）。
            data: 市场数据（默认生成合成数据用于测试）。
            llm: LLM 提供商（默认 MockLLMProvider 用于测试）。
            wiki_dir: llm_wiki 目录路径。
        """
        self.workspace = workspace or Path("harness_workspace")
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.data = data or generate_synthetic_data()
        self.llm = llm or MockLLMProvider()
        self.engine = FactorBacktestEngine()

        # 加载 Wiki 索引
        self.wiki_index = load_wiki_index(wiki_dir)

        # 工具执行器
        self.tool_executor = ToolExecutor(
            data=self.data,
            engine=self.engine,
            wiki_index=self.wiki_index,
        )

        # 上下文管理器
        self.context_manager = ContextManager(
            wiki_index_path=f"{wiki_dir}/index.json",
        )

        # 持久化
        self.persistence = HarnessPersistence(self.workspace)

        # 变体生成器
        self.variant_generator = VariantGenerator()

        # 当前工作流
        self.workflow = FactorResearchWorkflow()

        # 对话历史
        self.messages: list[dict[str, str]] = []

        # 会话 ID
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # ── 交互式 REPL ──

    def repl(self) -> None:
        """交互式 REPL 循环 — 主入口。

        支持元命令:
          help, status, save, skip, quit
        """
        print("=" * 60)
        print("  Quant Harness — 量化因子研究 REPL")
        print(f"  会话: {self.session_id}")
        print(f"  数据: {self.data.n_assets} 只资产 × {self.data.n_periods} 期")
        print("  输入 'help' 查看命令, 'quit' 退出")
        print("=" * 60)

        while True:
            try:
                phase_tag = self.workflow.current_phase.value
                user_input = input(f"\n[{phase_tag}] > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n退出。")
                break

            if not user_input:
                continue

            # 元命令
            if user_input == "quit":
                self._save_and_exit()
                break
            elif user_input == "help":
                self._print_help()
                continue
            elif user_input == "status":
                self._print_status()
                continue
            elif user_input == "save":
                self._save_session()
                continue
            elif user_input == "skip":
                self._skip_phase()
                continue

            # 进入 LLM 推理
            self._process_input(user_input)

    def _process_input(self, user_input: str, max_tool_rounds: int = 5) -> None:
        """处理用户输入 —— LLM 推理 + 多轮工具调用。

        Anthropic tool-use 循环模式:
          1. 用户输入 → LLM
          2. LLM 返回 tool_use → Harness 执行工具 → 结果注入为 tool_result
          3. LLM 看到 tool_result → 可能再次 tool_use 或给出最终回答
          4. 重复直到 LLM 不再请求工具或达到最大轮次

        Args:
            user_input: 用户输入文本。
            max_tool_rounds: 最大工具调用轮次（防止死循环）。
        """

        # 组装上下文
        context = self.context_manager.assemble(
            self.workflow.current_phase,
            additional={
                "user_input": user_input,
                "previous_phase_output": self._get_phase_output(),
            },
        )

        # 构建 system prompt
        phase_prompt_template = PHASE_PROMPTS.get(
            self.workflow.current_phase, "你是量化因子研究助手。"
        )
        system = phase_prompt_template.format(**context)

        # 获取可用工具
        available_tools = self._get_available_tools()
        tool_schemas = [
            TOOL_SCHEMAS[t] for t in available_tools if t in TOOL_SCHEMAS
        ]

        # 构建 Anthropic 格式的消息列表
        api_messages: list[dict[str, Any]] = list(self.messages)
        api_messages.append({"role": "user", "content": user_input})

        # 多轮工具调用循环
        for _round in range(max_tool_rounds):
            response = self.llm.chat(
                system=system,
                messages=api_messages,
                tools=tool_schemas if tool_schemas else None,
            )

            if response.tool_calls:
                # LLM 请求调用工具 → 执行并注入结果
                tool_results_content: list[dict[str, Any]] = []
                for tc in response.tool_calls:
                    result = self._execute_single_tool(tc)
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": getattr(tc, "id", tc.name),
                        "content": result,
                    })

                # 将 assistant tool_use + user tool_result 追加到消息
                api_messages.append({
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "name": tc.name, "input": tc.arguments}
                        for tc in response.tool_calls
                    ],
                })
                api_messages.append({
                    "role": "user",
                    "content": tool_results_content,
                })

                # 同时更新可读的对话历史
                feedback = "\n".join(
                    self._execute_single_tool(tc) for tc in response.tool_calls
                )
                self.messages.append({"role": "user", "content": user_input})
                self.messages.append({
                    "role": "assistant",
                    "content": f"[工具调用]\n{feedback}",
                })
            else:
                # LLM 给出最终回答 → 结束循环
                self.messages.append({"role": "user", "content": user_input})
                self.messages.append({
                    "role": "assistant",
                    "content": response.text,
                })
                print(f"\n{response.text[:2000]}")
                break
        else:
            # 达到最大轮次仍未结束
            print(f"\n[Harness] 达到最大工具调用轮次 ({max_tool_rounds})，强制结束。")

        # 检查阶段推进
        self._check_phase_transition()

    def _execute_single_tool(self, tool_call: Any) -> str:
        """执行单个工具调用并返回反馈文本。

        Args:
            tool_call: ToolCall dataclass 或兼容对象。

        Returns:
            工具执行结果的格式化文本。
        """
        name = tool_call.name if hasattr(tool_call, "name") else tool_call.get("name", "")
        args = (
            tool_call.arguments
            if hasattr(tool_call, "arguments")
            else tool_call.get("arguments", {})
        )

        if name not in self._get_available_tools():
            return f"[拒绝] 工具 '{name}' 在当前阶段不可用"

        result = self.tool_executor.execute(name, args)
        return result.to_llm_feedback()

    def _handle_tool_calls(self, tool_calls: list[Any]) -> str:
        """处理 LLM 的工具调用请求。

        Args:
            tool_calls: LLM 返回的工具调用列表。

        Returns:
            所有工具执行结果的汇总文本。
        """
        results: list[str] = []
        for tc in tool_calls:
            # 兼容 ToolCall dataclass 和 dict
            name = tc.name if hasattr(tc, "name") else tc.get("name", "")
            args = tc.arguments if hasattr(tc, "arguments") else tc.get("arguments", {})

            if name not in self._get_available_tools():
                results.append(f"[拒绝] 工具 '{name}' 在当前阶段不可用")
                continue

            result = self.tool_executor.execute(name, args)
            results.append(result.to_llm_feedback())

        return "\n".join(results)

    def _check_phase_transition(self) -> None:
        """检查是否满足阶段推进条件。"""
        wf = self.workflow

        if wf.current_phase == FactorResearchPhase.SELECT:
            if wf.original_factor_def and wf.economic_rationale:
                print("\n[Harness] 因子定义和经济逻辑已提取，可进入回测阶段。输入 'skip' 推进。")

        elif wf.current_phase == FactorResearchPhase.GENERATE_BACKTEST:
            if wf.backtest_results:
                print(f"\n[Harness] 已完成 {len(wf.backtest_results)} 个因子的回测。输入 'skip' 进入分析阶段。")

        elif wf.current_phase == FactorResearchPhase.ANALYZE:
            if wf.analysis_report:
                print("\n[Harness] 分析报告已生成。研究完成！")

    # ── Python API ──

    def quick_test(
        self,
        factor_name: str,
        base: str = "returns",
        window: int = 20,
        agg_func: str = "sum",
        transform: str = "zscore",
    ) -> dict[str, Any]:
        """快速单因子回测——不需要 LLM。

        Args:
            factor_name: 因子名。
            base: 基元数据。
            window: 窗口。
            agg_func: 聚合函数。
            transform: 变换方式。

        Returns:
            含 metrics, analysis, report 的 dict。
        """
        result = self.tool_executor.execute(
            "run_backtest",
            {
                "factor_name": factor_name,
                "base": base,
                "window": window,
                "agg_func": agg_func,
                "transform": transform,
            },
        )

        if result.status != "success":
            return {"error": result.error}

        backtest_result = self.tool_executor._result_cache.get(factor_name)
        if backtest_result is None:
            return {"error": "回测结果丢失"}

        analysis = analyze_factor(backtest_result)
        report = generate_factor_report(
            original_factor_name=factor_name,
            original_definition={
                "base": base, "window": window,
                "agg_func": agg_func, "transform": transform,
            },
            economic_rationale="",
            analysis=analysis,
        )

        return {
            "metrics": result.data,
            "analysis": analysis,
            "report": report,
        }

    def run_workflow(
        self,
        report_id: str = "",
        factor_name: str = "",
        economic_rationale: str = "",
        original_def: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """通过 Python API 运行完整研究工作流。

        Args:
            report_id: llm_wiki 报告 ID。
            factor_name: 因子名。
            economic_rationale: 经济逻辑。
            original_def: 原始因子定义。

        Returns:
            完整研究产出 dict。
        """
        wf = self.workflow
        wf.report_id = report_id
        wf.selected_factor_name = factor_name
        wf.economic_rationale = economic_rationale
        wf.original_factor_def = original_def or {
            "base": "returns",
            "window": 20,
            "agg_func": "sum",
            "transform": "zscore",
        }

        # Phase 1: 生成变体
        variants = self.variant_generator.generate(wf.original_factor_def, factor_name)
        wf.variants = variants

        # Phase 2: 批量回测
        factor_defs = self.variant_generator.to_factor_defs(variants)
        # 先回测原始因子
        self.tool_executor.execute("run_backtest", {
            "factor_name": factor_name,
            **wf.original_factor_def,
        })
        # 再回测变体
        for fd in factor_defs[:10]:  # 限制数量
            self.tool_executor.execute("run_backtest", {
                "factor_name": fd.name,
                "base": fd.base,
                "window": fd.window,
                "agg_func": fd.agg_func,
                "transform": fd.transform.name.lower() if hasattr(fd.transform, 'name') else "zscore",
            })

        # Phase 3: 分析
        backtest_result = self.tool_executor._result_cache.get(factor_name)
        if backtest_result:
            analysis = analyze_factor(backtest_result, data=self.data,
                                      economic_rationale=economic_rationale)
            report = generate_factor_report(
                original_factor_name=factor_name,
                original_definition=wf.original_factor_def,
                economic_rationale=economic_rationale,
                analysis=analysis,
                variants=variants,
                report_source=report_id,
            )
            wf.analysis_report = report

        self._save_session()
        return {
            "factor_name": factor_name,
            "variants_count": len(variants),
            "backtest_results_count": len(self.tool_executor._result_cache),
            "report": wf.analysis_report,
        }

    # ── 内部辅助 ──

    def _get_available_tools(self) -> list[str]:
        """获取当前阶段可用的工具列表。"""
        # 所有阶段都可以搜索 wiki 和做回测
        return list(TOOL_SCHEMAS.keys())

    def _get_phase_output(self) -> str:
        """获取前一阶段的结构化产出摘要。"""
        wf = self.workflow
        if wf.current_phase == FactorResearchPhase.GENERATE_BACKTEST:
            return json.dumps({
                "factor_name": wf.selected_factor_name,
                "original_def": wf.original_factor_def,
                "economic_rationale": wf.economic_rationale,
            }, ensure_ascii=False, indent=2)
        elif wf.current_phase == FactorResearchPhase.ANALYZE:
            results_summary = {}
            for name, result in list(wf.backtest_results.items())[:5]:
                results_summary[name] = str(result)[:200]
            return json.dumps({
                "backtest_results_summary": results_summary,
                "variants_count": len(wf.variants),
            }, ensure_ascii=False, indent=2)
        return ""

    def _save_session(self) -> None:
        """保存当前会话。"""
        self.persistence.save_session(
            self.session_id,
            self.workflow,
            self.messages,
        )
        print(f"[Harness] 会话已保存: {self.session_id}")

    def _save_and_exit(self) -> None:
        """保存并退出。"""
        self._save_session()
        print("再见！")

    def _print_help(self) -> None:
        """打印帮助信息。"""
        print("""
元命令:
  help    - 显示此帮助
  status  - 显示当前工作流状态
  save    - 手动保存会话
  skip    - 跳过当前阶段
  quit    - 保存并退出

当前阶段: {}
可用工具: {}
""".format(self.workflow.current_phase.value, ", ".join(self._get_available_tools())))

    def _print_status(self) -> None:
        """打印当前工作流状态。"""
        wf = self.workflow
        print(f"""
=== 工作流状态 ===
阶段:       {wf.current_phase.value}
报告:       {wf.report_id or '未选择'}
因子:       {wf.selected_factor_name or '未选择'}
原始定义:   {wf.original_factor_def or '未定义'}
变体数:     {len(wf.variants)}
回测结果数: {len(wf.backtest_results)}
经济逻辑:   {wf.economic_rationale[:100] if wf.economic_rationale else '未分析'}
""")

    def _skip_phase(self) -> None:
        """跳过当前阶段。"""
        next_phase = self.workflow.advance()
        if next_phase:
            print(f"[Harness] 推进到阶段: {next_phase.value}")
        else:
            print("[Harness] 已是最后阶段")
