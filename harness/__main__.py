"""Harness CLI 入口 — python -m harness <subcommand>

子命令:
  repl              交互式 REPL（默认）
  run               一次性研究工作流
  resume <id>       恢复中断的会话
  list              列出所有历史会话
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from harness.loop import QuantHarness
from harness.llm_provider import AnthropicProvider, LLMProvider, MockLLMProvider


def cmd_repl(args: argparse.Namespace) -> None:
    """启动交互式 REPL。"""
    from backtest.data import generate_synthetic_data

    data = generate_synthetic_data()

    llm: LLMProvider
    if args.mock:
        llm = MockLLMProvider()
        print("[警告] 使用 MockLLMProvider，LLM 不会真正调用 API")
    else:
        api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("错误: 未设置 ANTHROPIC_API_KEY 环境变量，也没有传入 --api-key")
            print("请设置环境变量或使用 --api-key 参数，或使用 --mock 进入测试模式")
            sys.exit(1)
        llm = AnthropicProvider(
            api_key=api_key,
            model=args.model or "",
            base_url=args.base_url or "",
        )

    harness = QuantHarness(
        workspace=Path(args.workspace),
        data=data,
        llm=llm,
        wiki_dir=args.wiki_dir,
    )
    harness.repl()


def cmd_run(args: argparse.Namespace) -> None:
    """一次性执行研究工作流。"""
    from backtest.data import generate_synthetic_data

    data = generate_synthetic_data()
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    llm: LLMProvider = (
        AnthropicProvider(api_key=api_key, model=args.model or "", base_url=args.base_url or "")
        if api_key
        else MockLLMProvider()
    )

    harness = QuantHarness(
        workspace=Path(args.workspace),
        data=data,
        llm=llm,
        wiki_dir=args.wiki_dir,
    )

    result = harness.run_workflow(
        report_id=args.report or "",
        factor_name=args.factor or "custom_factor",
        economic_rationale=args.rationale or "",
    )
    print(f"变体数: {result['variants_count']}")
    print(f"回测结果: {result['backtest_results_count']}")
    if result.get("report"):
        print(result["report"][:2000])


def cmd_resume(args: argparse.Namespace) -> None:
    """恢复中断的会话。"""
    harness = QuantHarness(
        workspace=Path(args.workspace),
        wiki_dir=args.wiki_dir,
    )
    session = harness.persistence.load_session(args.session_id)
    print(f"已恢复会话: {args.session_id}")
    print(f"阶段: {session['workflow']['current_phase']}")
    print(f"因子: {session['workflow']['selected_factor_name']}")
    harness.repl()


def cmd_list(args: argparse.Namespace) -> None:
    """列出所有历史会话。"""
    harness = QuantHarness(
        workspace=Path(args.workspace),
        wiki_dir=args.wiki_dir,
    )
    sessions = harness.persistence.list_sessions()
    if not sessions:
        print("无历史会话")
        return
    print(f"{'会话ID':<30} {'时间':<22} {'阶段':<20} {'因子'}")
    print("-" * 90)
    for s in sessions:
        print(f"{s['session_id']:<30} {s['saved_at']:<22} {s['phase']:<20} {s['factor']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quant Harness — 量化因子研究 REPL",
        prog="python -m harness",
    )
    parser.add_argument("--workspace", default="research", help="工作空间目录")
    parser.add_argument("--wiki-dir", default="wiki", help="wiki 目录")
    parser.add_argument("--model", default=None, help="LLM 模型名 (默认: ANTHROPIC_MODEL 环境变量 或 claude-sonnet-5)")
    parser.add_argument("--api-key", default=None, help="Anthropic API key (默认: ANTHROPIC_API_KEY 环境变量)")
    parser.add_argument("--base-url", default=None, help="自定义 API 端点/代理地址 (默认: ANTHROPIC_BASE_URL 环境变量)")
    parser.add_argument("--mock", action="store_true", help="使用 Mock LLM（不调用真实 API）")

    sub = parser.add_subparsers(dest="command", help="子命令")

    p_repl = sub.add_parser("repl", help="启动交互式 REPL")
    p_repl.set_defaults(func=cmd_repl)

    p_run = sub.add_parser("run", help="一次性研究工作流")
    p_run.add_argument("--report", help="llm_wiki 报告 ID")
    p_run.add_argument("--factor", help="因子名称")
    p_run.add_argument("--rationale", help="经济逻辑说明")
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume", help="恢复会话")
    p_resume.add_argument("session_id", help="会话 ID")
    p_resume.set_defaults(func=cmd_resume)

    p_list = sub.add_parser("list", help="列出所有会话")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
