"""持久化层 — 会话快照、回测产物保存、知识卡片持久化。

四层持久化 (HARNESS_DESIGN.md Phase 2):
  Layer 1: 会话快照 (sessions/{session_id}.json)
  Layer 2: 回测产物 (artifacts/{run_id}/)
  Layer 3: 知识卡片 (knowledge/{insight_id}.json + _index.jsonl)
  Layer 4: 工作流模板 (workflows/{name}.yaml)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


from scripts.engine import BacktestResult
from scripts.workflow import FactorResearchWorkflow


class HarnessPersistence:
    """Harness 持久化管理器。"""

    def __init__(self, workspace: Path) -> None:
        """初始化持久化层。

        Args:
            workspace: research/ 目录路径。
        """
        self.workspace = workspace
        self.sessions_dir = workspace / "sessions"
        self.artifacts_dir = workspace / "artifacts"
        self.knowledge_dir = workspace / "knowledge"
        self.workflows_dir = workspace / "workflows"

        for d in [
            self.sessions_dir,
            self.artifacts_dir,
            self.knowledge_dir,
            self.workflows_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    # ── Layer 1: 会话快照 ──

    def save_session(
        self,
        session_id: str,
        workflow: FactorResearchWorkflow,
        messages: list[dict[str, str]],
        metrics: Optional[dict[str, Any]] = None,
    ) -> Path:
        """保存完整会话快照。

        Args:
            session_id: 会话 ID。
            workflow: 工作流状态。
            messages: 对话历史。
            metrics: 度量快照。

        Returns:
            保存的文件路径。
        """
        snapshot: dict[str, Any] = {
            "session_id": session_id,
            "saved_at": datetime.now().isoformat(),
            "workflow": {
                "current_phase": workflow.current_phase.value,
                "report_id": workflow.report_id,
                "selected_factor_name": workflow.selected_factor_name,
                "original_factor_def": workflow.original_factor_def,
                "economic_rationale": workflow.economic_rationale,
                "variants": [
                    {
                        "name": v.name,
                        "description": v.description,
                        "base": v.base,
                        "window": v.window,
                        "agg_func": v.agg_func,
                        "transform": v.transform,
                        "variant_type": v.variant_type,
                    }
                    for v in workflow.variants
                ],
                "analysis_report": workflow.analysis_report,
                "improvement_directions": workflow.improvement_directions,
            },
            "messages": messages,
            "metrics": metrics or {},
        }

        path = self.sessions_dir / f"{session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        return path

    def load_session(self, session_id: str) -> dict[str, Any]:
        """加载会话快照。

        Args:
            session_id: 会话 ID。

        Returns:
            会话快照 dict。

        Raises:
            FileNotFoundError: 会话不存在。
        """
        path = self.sessions_dir / f"{session_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"会话不存在: {session_id}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def list_sessions(self) -> list[dict[str, str]]:
        """列出所有历史会话。

        Returns:
            会话摘要列表。
        """
        sessions: list[dict[str, str]] = []
        for p in sorted(self.sessions_dir.glob("*.json"), reverse=True):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            sessions.append({
                "session_id": data.get("session_id", p.stem),
                "saved_at": data.get("saved_at", ""),
                "phase": data.get("workflow", {}).get("current_phase", ""),
                "factor": data.get("workflow", {}).get("selected_factor_name", ""),
            })
        return sessions

    # ── Layer 2: 回测产物 ──

    def save_backtest_result(
        self,
        run_id: str,
        result: BacktestResult,
    ) -> Path:
        """保存回测结果为 Parquet + JSON 元数据。

        Args:
            run_id: 运行 ID。
            result: 回测结果。

        Returns:
            产物目录路径。
        """
        artifact_dir = self.artifacts_dir / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # 因子值
        result.factor_values.to_parquet(artifact_dir / "factor_values.parquet")
        # 分层收益
        result.quantile.quantile_returns.to_parquet(artifact_dir / "quantile_returns.parquet")
        # 分层累计净值
        result.quantile.quantile_cumulative.to_parquet(artifact_dir / "quantile_cumulative.parquet")
        # IC 序列
        result.ic_series.to_frame("RankIC").to_parquet(artifact_dir / "ic_series.parquet")
        # 多空收益
        result.quantile.top_bottom_spread.to_frame("spread").to_parquet(
            artifact_dir / "top_bottom_spread.parquet"
        )

        # 元数据 JSON
        meta: dict[str, Any] = {
            "run_id": run_id,
            "factor_name": result.factor_name,
            "created_at": datetime.now().isoformat(),
            "ic_mean": result.ic_mean,
            "ic_std": result.ic_std,
            "ic_ir": result.ic_ir,
            "long_short_sharpe": result.long_short_sharpe,
            "long_short_maxdd": result.long_short_maxdd,
            "config": result.config,
        }
        with open(artifact_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return artifact_dir

    # ── Layer 3: 知识卡片 ──

    def save_insight(self, insight: dict[str, Any]) -> Path:
        """保存一条研究洞察。

        Args:
            insight: {id, type, factor_name, finding, sharpe, timestamp, source_session}。

        Returns:
            保存路径。
        """
        insight_id = insight.get("id", f"insight_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        path = self.knowledge_dir / f"{insight_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(insight, f, ensure_ascii=False, indent=2)

        # 追加索引行
        index_path = self.knowledge_dir / "_index.jsonl"
        index_entry = {
            "id": insight_id,
            "type": insight.get("type", ""),
            "factor_name": insight.get("factor_name", ""),
            "timestamp": insight.get("timestamp", datetime.now().isoformat()),
        }
        with open(index_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(index_entry, ensure_ascii=False) + "\n")

        return path

    def query_knowledge(
        self,
        factor_name: Optional[str] = None,
        insight_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """检索知识卡片。

        Args:
            factor_name: 按因子名过滤。
            insight_type: 按类型过滤（success/failure/warning）。

        Returns:
            匹配的知识卡片列表。
        """
        results: list[dict[str, Any]] = []
        for p in self.knowledge_dir.glob("*.json"):
            if p.name.startswith("_"):
                continue
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            if factor_name and data.get("factor_name") != factor_name:
                continue
            if insight_type and data.get("type") != insight_type:
                continue
            results.append(data)
        return sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)
