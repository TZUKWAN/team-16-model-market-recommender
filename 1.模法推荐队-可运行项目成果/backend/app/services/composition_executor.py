"""Demo execution service for model composition plans."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
from typing import Any

from app.schemas.composition import (
    CompositionExecutionEdge,
    CompositionExecutionNode,
    CompositionExecutionResult,
    RecommendCompositionResponse,
)


DESENSITIZED_NOTICE = "组合执行结果为脱敏演示数据，不代表真实客户、真实授信或生产决策。"


class CompositionExecutor:
    """Builds a readable demo execution trace for a composition plan."""

    def execute_demo(
        self,
        composition: RecommendCompositionResponse,
        parse_result: dict[str, Any] | None = None,
    ) -> CompositionExecutionResult:
        """Execute a composition in demo mode and return node and fusion evidence.

        Node status now reflects the plan's IO check rather than being
        uniformly "completed": a node whose hard upstream dependency failed is
        ``blocked``; a node with only soft/partial gaps runs in ``degraded``
        mode; otherwise ``completed``. This makes the execution trace a real
        state machine instead of a flat happy-path demo.
        """
        parse = parse_result or {}
        started = datetime.now(timezone.utc)

        # Index edges by target to look up the feeding edge's IO status, and
        # build a node_id -> source_node_id lineage map for provenance.
        edge_by_target: dict[str, Any] = {}
        for edge in composition.flow_edges:
            # Keep the worst feeding edge if a node has multiple feeders.
            prev = edge_by_target.get(edge.target_node_id)
            if prev is None or self._io_severity(edge.io_status) > self._io_severity(prev.io_status):
                edge_by_target[edge.target_node_id] = edge

        node_by_id = {n.node_id: n for n in composition.nodes}
        # Track which nodes were blocked so their downstream is transitively
        # blocked too (hard failure propagates along the DAG).
        blocked_node_ids: set[str] = set()

        execution_nodes: list[CompositionExecutionNode] = []
        previous_outputs: dict[str, Any] = {}

        for index, node in enumerate(sorted(composition.nodes, key=lambda n: n.step_order), start=1):
            node_started = started + timedelta(milliseconds=index * 120)
            node_finished = node_started + timedelta(milliseconds=180 + index * 35)
            feeding_edge = edge_by_target.get(node.node_id)
            input_snapshot = self._build_input_snapshot(node.input_requirements, parse, previous_outputs)

            # Resolve execution status from the plan's IO verdict.
            status, status_reason = self._resolve_node_status(
                node, feeding_edge, blocked_node_ids, node_by_id
            )

            if status == "blocked":
                # A blocked node produces no output; it cannot feed downstream.
                blocked_node_ids.add(node.node_id)
                output_snapshot: dict[str, Any] = {}
            else:
                output_snapshot = self._build_output_snapshot(
                    capability=node.capability,
                    output_fields=node.output_fields,
                    scenario=composition.scenario,
                    parse_result=parse,
                    step_order=node.step_order,
                )
                previous_outputs.update(output_snapshot)

            # Provenance: map each consumed field to the upstream node that
            # produced it (when available in previous_outputs).
            input_lineage = self._build_input_lineage(
                node.input_requirements, feeding_edge, previous_outputs
            )

            execution_nodes.append(
                CompositionExecutionNode(
                    node_id=node.node_id,
                    step_order=node.step_order,
                    model_id=node.model_id,
                    model_name=node.model_name,
                    capability=node.capability,
                    status=status,
                    status_reason=status_reason,
                    input_snapshot=input_snapshot,
                    output_snapshot=output_snapshot,
                    started_at=node_started.isoformat(),
                    finished_at=node_finished.isoformat(),
                    elapsed_ms=int((node_finished - node_started).total_seconds() * 1000),
                    demo_data=True,
                    desensitized_notice=DESENSITIZED_NOTICE,
                    input_lineage=input_lineage,
                )
            )

        execution_edges = [
            CompositionExecutionEdge(
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                status="completed" if edge.io_status in {"pass", "partial"} else "blocked",
                transferred_fields=self._infer_transferred_fields(edge.source_node_id, execution_nodes),
                note=self._edge_note(edge.io_status),
            )
            for edge in composition.flow_edges
        ]

        fused_result = self._build_fused_result(composition, parse, execution_nodes)
        node_contributions = self._build_node_contributions(execution_nodes)

        return CompositionExecutionResult(
            execution_id=f"EXEC_{uuid.uuid4().hex[:10].upper()}",
            status=self._overall_status(execution_nodes),
            demo_data=True,
            desensitized_notice=DESENSITIZED_NOTICE,
            nodes=execution_nodes,
            edges=execution_edges,
            fused_result=fused_result,
            node_contributions=node_contributions,
        )

    @staticmethod
    def _io_severity(io_status: str) -> int:
        """Rank IO status from benign to severe, for worst-edge selection."""
        return {"pass": 0, "partial": 1, "fail": 2}.get(io_status, 0)

    def _resolve_node_status(
        self,
        node: Any,
        feeding_edge: Any | None,
        blocked_node_ids: set[str],
        node_by_id: dict[str, Any],
    ) -> tuple[str, str]:
        """Determine a node's execution status from its DAG dependencies.

        Returns (status, reason). Precedence:
        1. If any upstream node is blocked, this node is transitively blocked.
        2. If the feeding edge failed (hard dependency), this node is blocked.
        3. If the feeding edge is partial (soft gaps), this node is degraded.
        4. Source nodes (no feeder) or pass edges run as completed.
        """
        # 1. Transitive blocking from an already-blocked upstream dependency.
        for dep_id in getattr(node, "depends_on", []):
            if dep_id in blocked_node_ids:
                return "blocked", f"上游节点 {dep_id} 已中断，本节点无法执行。"

        # 2/3. Resolve from the feeding edge's IO verdict.
        if feeding_edge is not None:
            io_status = feeding_edge.io_status
            if io_status == "fail":
                missing = feeding_edge.missing_fields[:4]
                missing_text = "、".join(missing) if missing else "无可映射的上游输出字段"
                return (
                    "blocked",
                    f"核心输入缺失（{missing_text}），硬依赖未满足，节点中断。",
                )
            if io_status == "partial":
                missing = feeding_edge.missing_fields[:4]
                reason = "部分输入由外部数据补齐，节点降级执行。"
                if missing:
                    reason = f"部分输入缺失（{', '.join(missing)}），降级执行。"
                return "degraded", reason

        return "completed", ""

    def _build_input_lineage(
        self,
        input_requirements: list[str],
        feeding_edge: Any | None,
        previous_outputs: dict[str, Any],
    ) -> dict[str, str]:
        """Map each consumed input field to the upstream node id that produced it.

        Only fields actually present in previous_outputs can be attributed; the
        rest come from external data and are omitted. ``feeding_edge`` carries
        the source node id when available.
        """
        lineage: dict[str, str] = {}
        if feeding_edge is None:
            return lineage
        src_id = feeding_edge.source_node_id
        for field in input_requirements:
            # Match loosely: previous_outputs may key on output field names.
            for key in previous_outputs:
                if field.lower() in key.lower() or key.lower() in field.lower():
                    lineage[field] = src_id
                    break
        return lineage

    def _build_node_contributions(
        self, execution_nodes: list[CompositionExecutionNode]
    ) -> list[dict[str, Any]]:
        """Summarize which node contributed which fields to the fused result."""
        contributions = []
        for node in execution_nodes:
            if node.status in {"blocked"}:
                continue
            generated = node.output_snapshot.get("generated_fields", [])
            if not isinstance(generated, list):
                generated = []
            contributions.append({
                "node_id": node.node_id,
                "model_name": node.model_name,
                "capability": node.capability,
                "status": node.status,
                "contributed_fields": generated[:6],
            })
        return contributions

    def _overall_status(self, execution_nodes: list[CompositionExecutionNode]) -> str:
        """Roll up per-node status into an overall execution status."""
        if not execution_nodes:
            return "no_executable_node"
        statuses = {n.status for n in execution_nodes}
        if statuses <= {"completed"}:
            return "completed"
        if "blocked" in statuses:
            return "partially_blocked"
        if "degraded" in statuses:
            return "degraded"
        return "completed"

    def _build_input_snapshot(
        self,
        input_requirements: list[str],
        parse_result: dict[str, Any],
        previous_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        fields = input_requirements[:6]
        return {
            "available_fields": fields,
            "from_previous_nodes": list(previous_outputs.keys())[:6],
            "scenario": parse_result.get("business_scenario", ""),
            "customer_segment": parse_result.get("customer_segment", []),
            "demo_batch_id": "DEMO_BATCH_20260706",
        }

    def _build_output_snapshot(
        self,
        capability: str,
        output_fields: list[str],
        scenario: str,
        parse_result: dict[str, Any],
        step_order: int,
    ) -> dict[str, Any]:
        domain = self._detect_domain(f"{capability} {scenario} {parse_result.get('intent', '')}")
        output: dict[str, Any] = {
            "node_rank": step_order,
            "capability": capability,
            "generated_fields": output_fields[:8],
            "demo_data": True,
        }

        if domain == "marketing":
            output.update({
                "top_customer_group": "县域新客A组",
                "conversion_probability": round(0.76 - step_order * 0.03, 2),
                "priority": "high",
                "recommended_channel": "客户经理企微触达",
            })
        elif domain == "operation":
            output.update({
                "warning_type": "运营异常预警",
                "warning_probability": round(0.71 + step_order * 0.02, 2),
                "affected_scope": "脱敏机构样例-03",
                "suggested_action": "复核异常交易与柜面流程记录",
            })
        else:
            output.update({
                "risk_score": round(0.68 + step_order * 0.05, 2),
                "risk_level": "medium" if step_order == 1 else "high",
                "decision_hint": "进入人工复核" if step_order == 1 else "收紧额度并补充材料",
                "exposure_amount_band": "10万-30万",
            })

        return output

    def _build_fused_result(
        self,
        composition: RecommendCompositionResponse,
        parse_result: dict[str, Any],
        execution_nodes: list[CompositionExecutionNode],
    ) -> dict[str, Any]:
        text = f"{composition.scenario} {parse_result.get('intent', '')} {' '.join(parse_result.get('tags', []))}"
        domain = self._detect_domain(text)
        completed_nodes = [node for node in execution_nodes if node.status == "completed"]
        degraded_nodes = [node for node in execution_nodes if node.status == "degraded"]
        blocked_nodes = [node for node in execution_nodes if node.status in {"blocked", "failed"}]
        completed_models = [node.model_name for node in completed_nodes]
        degraded_models = [node.model_name for node in degraded_nodes]
        blocked_models = [node.model_name for node in blocked_nodes]
        total_nodes = len(execution_nodes)
        if blocked_nodes or degraded_nodes:
            summary = (
                f"{composition.composition_name}共{total_nodes}个节点："
                f"完成{len(completed_nodes)}个，降级{len(degraded_nodes)}个，"
                f"阻塞{len(blocked_nodes)}个。"
            )
        else:
            summary = f"{composition.composition_name}已完成{len(completed_nodes)}个节点演示执行。"
        base = {
            "summary": summary,
            "completed_models": completed_models,
            "degraded_models": degraded_models,
            "blocked_models": blocked_models,
            "confidence": round(min(0.96, max(0.72, composition.total_score / 100)), 2),
            "demo_data": True,
            "desensitized_notice": DESENSITIZED_NOTICE,
        }

        if domain == "marketing":
            base.update({
                "result_type": "marketing_fusion",
                "target_group": "县域新客高意向名单",
                "expected_lift": "响应改善方向：待真实业务数据验证",
                "next_actions": ["生成客户名单", "按渠道偏好分配触达任务", "跟踪7日响应结果"],
            })
        elif domain == "operation":
            base.update({
                "result_type": "operation_fusion",
                "warning_level": "orange",
                "focus_area": "网点运营异常与合规检查",
                "next_actions": ["推送预警工单", "复核异常样本", "沉淀规则回流模型市场"],
            })
        else:
            base.update({
                "result_type": "risk_fusion",
                "decision": "建议审慎通过并补充人工复核",
                "risk_overview": "欺诈、准入和额度节点存在中等偏高风险信号。",
                "next_actions": ["补充经营流水", "复核多头借贷记录", "按额度区间配置审批策略"],
            })

        return base

    def _infer_transferred_fields(
        self,
        source_node_id: str,
        execution_nodes: list[CompositionExecutionNode],
    ) -> list[str]:
        for node in execution_nodes:
            if node.node_id == source_node_id:
                fields = node.output_snapshot.get("generated_fields", [])
                if isinstance(fields, list) and fields:
                    return [str(field) for field in fields[:5]]
                return [key for key in node.output_snapshot.keys() if key not in {"demo_data"}][:5]
        return []

    def _edge_note(self, io_status: str) -> str:
        if io_status == "pass":
            return "上游输出字段可直接进入下游节点。"
        if io_status == "partial":
            return "部分字段可传递，其余字段由业务主数据或配置补齐。"
        return "字段兼容性不足，需人工补充映射规则。"

    def _detect_domain(self, text: str) -> str:
        lowered = text.lower()
        if any(key in lowered for key in ["营销", "客户", "获客", "转化", "marketing"]):
            return "marketing"
        if any(key in lowered for key in ["运营", "网点", "合规", "反洗钱", "预警", "operation"]):
            return "operation"
        return "risk"
