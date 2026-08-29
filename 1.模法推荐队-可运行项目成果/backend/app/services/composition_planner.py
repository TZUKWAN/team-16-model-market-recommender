"""
composition_planner.py — Multi-model composition orchestration engine.

Matches composition templates, assigns models to nodes,
checks IO compatibility, and scores the composition.
When LLM is available, enriches explanations and template matching.
"""

from __future__ import annotations
import uuid
import logging
from typing import Any

from app.schemas.composition import (
    RecommendCompositionResponse, CompositionNode, CompositionEdge, IOCompatibilityResult,
)
from app.services.data_loader import load_composition_templates
from app.services.recommender import ModelCatalogUnavailableError, ModelRecommendationService
from app.services.llm_client import get_llm_client
from app.repositories.model_asset_repository import get_model_asset_repository

logger = logging.getLogger(__name__)

# ─── Composition scoring weights ────────────────────────────────
W_PROCESS = 0.25
W_SCENARIO_CONSISTENCY = 0.20
W_NODE_FIT = 0.20
W_IO = 0.15
W_DATA = 0.10
W_LANDING = 0.05
W_COMPLIANCE = 0.05


class CompositionPlanner:
    """
    Rule-based composition planner. Matches templates, assigns models,
    checks compatibility, and produces an end-to-end plan.
    """

    def __init__(self):
        self.templates = load_composition_templates()
        self.model_repository = get_model_asset_repository()
        self.models = self.model_repository.list_models()
        self.recommender = ModelRecommendationService()
        self.llm = get_llm_client()

    def plan(
        self,
        parse_result: dict[str, Any],
        top_k: int = 3,
    ) -> RecommendCompositionResponse:
        """Build a composition plan from parsed demand."""
        intent = parse_result.get("intent", "")
        scenario = parse_result.get("business_scenario", "")
        tags = parse_result.get("tags", [])
        outputs = parse_result.get("expected_outputs", [])

        # 1. Match template
        template = self._match_template(parse_result)

        if not template:
            # Fallback: simple single-node "composition"
            return self._build_fallback(parse_result)

        # 2. Assign models to each node
        nodes, assignments = self._assign_models(template, parse_result, top_k)

        # 3. Check IO compatibility between nodes (auto-generate edges from nodes)
        auto_edges = [
            {"source": nodes[i].step_order, "target": nodes[i + 1].step_order}
            for i in range(len(nodes) - 1)
        ]
        edges = self._check_io_compatibility(nodes, auto_edges)

        # 3.5 Backfill DAG dependencies onto nodes from the computed edges, and
        # mark a node's dependency as hard when the feeding edge failed IO.
        node_id_by_step = {n.step_order: n.node_id for n in nodes}
        hard_dep_node_ids: set[str] = set()
        for e in edges:
            src = e.source_node_id
            tgt = e.target_node_id
            for n in nodes:
                if n.node_id == tgt and src not in n.depends_on:
                    n.depends_on.append(src)
            if e.io_status == "fail":
                hard_dep_node_ids.add(tgt)
        for n in nodes:
            n.dependency_type = "hard" if n.node_id in hard_dep_node_ids else "soft"

        # 4. Score the composition
        io_result = self._compute_io_result(edges)
        total_score = self._compute_composition_score(
            template, nodes, edges, io_result, parse_result
        )

        # 5. Generate explanations (LLM-enriched when available)
        explanations = template.get("explanations", {})
        t_name = template.get("name", "组合方案")
        t_desc = template.get("description", "")
        if self.llm.available:
            llm_exps = self._generate_explanations_with_llm(template, nodes, parse_result)
            if llm_exps:
                business_exp = llm_exps.get("business", explanations.get("business", ""))
                technical_exp = llm_exps.get("technical", explanations.get("technical", ""))
                management_exp = llm_exps.get("management", explanations.get("management", ""))
            else:
                business_exp = explanations.get("business", f"{t_name}：{t_desc}。本方案覆盖{len(nodes)}个关键环节。")
                technical_exp = explanations.get("technical", f"{t_name}技术方案：包含{len(nodes)}个模型节点。")
                management_exp = explanations.get("management", f"{t_name}管理视图。")
        else:
            business_exp = explanations.get("business", f"{t_name}：{t_desc}。本方案覆盖{len(nodes)}个关键环节。")
            technical_exp = explanations.get("technical", f"{t_name}技术方案：包含{len(nodes)}个模型节点。")
            management_exp = explanations.get("management", f"{t_name}管理视图。")

        # 6. Missing data
        missing_data = self._collect_missing_data(nodes, parse_result)
        failure_reasons = []
        if io_result.failed:
            failure_reasons.append(f"{io_result.failed} hard IO dependency edge(s) failed")
        if io_result.partial:
            failure_reasons.append(f"{io_result.partial} IO edge(s) require external data")
        if missing_data:
            failure_reasons.append(f"{len(missing_data)} required data field(s) are unavailable")
        if any(not node.model_id for node in nodes):
            failure_reasons.append("one or more capabilities have no permitted model")
        if not nodes:
            failure_reasons.append("no permitted model can satisfy the selected template")
        composition_status = (
            "blocked" if not nodes or any(not node.model_id for node in nodes)
            else "partially_blocked" if io_result.failed
            else "degraded" if io_result.partial or missing_data
            else "ready"
        )

        return RecommendCompositionResponse(
            composition_id=f"COMP_{uuid.uuid4().hex[:8].upper()}",
            composition_name=template.get("name", "组合方案"),
            scenario=parse_result.get("business_scenario", template.get("name", "")),
            total_score=round(total_score, 1),
            composition_status=composition_status,
            failure_reasons=failure_reasons,
            demo_execution_only=True,
            nodes=nodes,
            flow_edges=edges,
            io_compatibility=io_result,
            missing_data=missing_data,
            expected_outputs=list(set(
                outputs + [f for n in nodes for f in n.output_fields]
            )),
            business_explanation=business_exp,
            technical_explanation=technical_exp,
            management_explanation=management_exp,
            usage_guide=self._generate_usage_guide(nodes),
        )

    def _match_template(self, parse_result: dict[str, Any]) -> dict[str, Any] | None:
        """Match the best composition template for the parsed demand."""
        intent = parse_result.get("intent", "")
        scenario = parse_result.get("business_scenario", "")
        tags = parse_result.get("tags", [])
        all_text = f"{intent} {scenario} {' '.join(tags)}".lower()

        domain_intent_map = {
            "credit_risk": ["信贷", "贷款", "风控", "农户", "小微", "个人"],
            "customer_marketing": ["营销", "客户", "获客", "交叉"],
            "operation_management": ["运营", "网点", "合规", "反洗钱", "人力"],
        }
        intent_keywords = domain_intent_map.get(intent, [])

        best_template = None
        best_score = 0

        for t in self.templates:
            score = 0.0

            # Scenario match via applicable_scenarios
            t_scenarios = t.get("applicable_scenarios", [])
            for ts in t_scenarios:
                if ts.lower() in all_text or any(kw in ts.lower() for kw in intent_keywords):
                    score += 3
                    break

            # Stage capability match
            stages = t.get("stages", [])
            all_caps = []
            for st in stages:
                all_caps.extend(st.get("required_models", []))
                all_caps.extend(st.get("optional_models", []))
            cap_text = " ".join(all_caps)
            tag_score = sum(1 for tg in tags if tg.lower() in cap_text.lower())
            score += tag_score * 0.5

            # Keyword overlap with template name
            t_name = t.get("name", "")
            if any(kw in t_name for kw in intent_keywords):
                score += 2

            if score > best_score:
                best_score = score
                best_template = t

        if best_score < 2:
            return None
        return best_template

    def _check_scenario_match_llm(
        self, scenario: str, t_scenarios: list[str], t_name: str
    ) -> bool:
        """Use LLM to check if a business scenario semantically matches a template."""
        system = "You are a banking expert. Output ONLY 'yes' or 'no'."
        user = (
            f"Does this business scenario semantically match the template?\n"
            f"Scenario: {scenario}\n"
            f"Template: {t_name}\n"
            f"Template applicable scenarios: {t_scenarios}\n"
            f"Answer yes if the scenario fits this template's domain, no otherwise."
        )
        result = self.llm.chat(system, user)
        return result and "yes" in result.lower()

    def _assign_models(
        self,
        template: dict[str, Any],
        parse_result: dict[str, Any],
        top_k: int,
    ) -> tuple[list[CompositionNode], dict[int, str]]:
        """Assign best-fit models to each template stage's required capabilities."""
        nodes: list[CompositionNode] = []
        assignments: dict[int, str] = {}
        used_model_ids: set[str] = set()
        model_pool = self._model_pool(parse_result)

        stages = template.get("stages", [])
        step = 0

        for stage in stages:
            stage_name = stage.get("name", stage.get("stage", ""))
            capabilities = stage.get("required_models", [])

            for cap in capabilities:
                step += 1
                candidates = []
                for m in model_pool:
                    permitted_domains = parse_result.get("permitted_domains")
                    if isinstance(permitted_domains, list) and m.get("domain") not in permitted_domains:
                        continue
                    if m["model_id"] in used_model_ids:
                        continue
                    m_caps = [c.lower() for c in m.get("model_capability", [])]
                    m_tags = [t.lower() for t in m.get("tags", [])]
                    if cap.lower() in m_caps or cap.lower() in m_tags:
                        fit_score = self._score_model_node_fit(m, {"capability": cap}, parse_result)
                        candidates.append((m, fit_score))

                candidates.sort(key=lambda x: (-x[1], x[0].get("model_id", "")))

                if candidates:
                    best_model, fit_score = candidates[0]
                    used_model_ids.add(best_model["model_id"])
                    assignments[step] = best_model["model_id"]

                    node = CompositionNode(
                        node_id=f"node_{step}",
                        step_order=step,
                        capability=cap,
                        model_id=best_model.get("model_id", ""),
                        model_name=best_model.get("model_name", ""),
                        source=best_model.get("source", "official"),
                        catalog_version=best_model.get("catalog_version", ""),
                        input_requirements=best_model.get("input_fields_required", []),
                        output_fields=best_model.get("output_fields", []),
                        fit_score=round(fit_score, 1),
                        node_explanation=f"{stage_name}阶段: {cap}",
                    )
                    nodes.append(node)

        return nodes, assignments

    def _model_pool(self, parse_result: dict[str, Any]) -> list[dict[str, Any]]:
        """Select one model catalog for the whole composition without fallback."""
        source = str(
            parse_result.get("model_source")
            or parse_result.get("catalog_source")
            or "official"
        ).lower()
        if source not in {"official", "demo"}:
            raise ValueError(f"Unsupported model catalog source: {source}")
        filtered = [model for model in self.models if model.get("source") == source]
        if not filtered:
            raise ModelCatalogUnavailableError(source)
        return filtered

    def _score_model_node_fit(
        self, model: dict[str, Any], t_node: dict[str, Any],
        parse_result: dict[str, Any]
    ) -> float:
        """Score how well a model fits a template node (0-100)."""
        score = 60.0  # Base score

        # Capability exact match
        required = t_node.get("required_capability", t_node.get("capability", ""))
        caps = [c.lower() for c in model.get("model_capability", [])]
        if required.lower() in caps:
            score += 20

        # A capability can occur in many unrelated domains (for example,
        # segmentation is used by marketing, collections and operations).
        # Keep the selected model aligned with the parsed business intent.
        intent = str(parse_result.get("intent", "") or "")
        model_domain = str(model.get("domain", "") or "")
        if intent and model_domain:
            score += 15 if intent == model_domain else -20

        query_text = " ".join([
            str(parse_result.get("raw_text", "") or ""),
            str(parse_result.get("business_scenario", "") or ""),
            " ".join(map(str, parse_result.get("tags", []) or [])),
            " ".join(map(str, parse_result.get("customer_segment", []) or [])),
            " ".join(map(str, parse_result.get("product_type", []) or [])),
        ])
        model_text = " ".join([
            str(model.get("model_name", "") or ""),
            str(model.get("description", "") or ""),
            " ".join(map(str, model.get("business_scenario", []) or [])),
            " ".join(map(str, model.get("tags", []) or [])),
            str(model.get("applicable_conditions", "") or ""),
        ])
        focus_terms = [
            "首贷", "新客", "县域", "转化", "营销", "风控", "欺诈", "催收",
            "逾期", "流失", "存款", "商户", "小微", "对公", "贷后", "预警", "额度",
        ]
        focus_hits = sum(1 for term in focus_terms if term in query_text and term in model_text)
        score += min(15, focus_hits * 3)

        unsuitable = str(model.get("unsuitable_conditions", "") or "")
        if ("新客" in query_text or "新客户" in query_text) and any(
            marker in unsuitable for marker in ("不适用于新客", "不适用于新客户", "开户不足")
        ):
            score -= 40
        if "首贷" in query_text and "首贷" not in model_text:
            score -= 8

        # Input requirement overlap
        req_inputs = set(i.lower() for i in t_node.get("input_requirements", []))
        model_inputs = set(i.lower() for i in model.get("input_fields_required", []))
        overlap = len(req_inputs & model_inputs)
        if req_inputs and overlap > 0:
            score += min(10, overlap * 3)

        # Performance bonus
        metrics = model.get("performance_metrics", {})
        if "auc" in metrics and metrics["auc"] >= 0.8:
            score += 5
        if "ks" in metrics and metrics["ks"] >= 0.4:
            score += 5

        return max(0, min(100, score))

    def _check_io_compatibility(
        self,
        nodes: list[CompositionNode],
        template_edges: list[dict[str, Any]],
    ) -> list[CompositionEdge]:
        """Check IO compatibility between connected nodes with semantic grouping."""
        edges: list[CompositionEdge] = []
        node_map = {n.step_order: n for n in nodes}

        # Semantic field groups — fields within same group are compatible
        field_groups = {
            "customer": ["customer_profile", "customer_info", "contact_info", "address_info",
                        "demographics", "customer_lifecycle", "customer_value_score"],
            "credit": ["credit_report", "credit_history", "overdue_records", "debt_ratio",
                      "risk_preference", "risk_score", "risk_level"],
            "transaction": ["transaction_flow", "transaction_data", "transaction_category",
                           "income_expense", "repayment_history", "repayment_behavior",
                           "repayment_record"],
            "business": ["business_income", "business_cashflow", "business_data",
                        "business_operation", "supply_chain_data", "tax_info", "employee_info"],
            "loan": ["loan_application", "loan_purpose", "collateral_info", "guarantee_info",
                    "anti_fraud_data"],
            "asset": ["asset_info", "liability_info", "net_worth", "asset_liability"],
            "marketing": [
                "marketing_contact_history", "campaign_response", "marketing_history",
                "ranked_list", "customer_ranking", "product_interest",
                "retention_suggestion", "suggested_product", "next_best_action",
            ],
            "channel": ["channel_preference", "channel_behavior", "app_behavior", "online_activity"],
            "branch": ["branch_visit", "branch_data", "counter_business", "queue_data",
                      "atm_usage", "complaint_history", "staff_workload"],
        }

        def field_group(field_key: str) -> str:
            key = field_key.lower()
            for grp, fields in field_groups.items():
                if key in fields:
                    return grp
            # Fuzzy match
            for grp, fields in field_groups.items():
                for f in fields:
                    if key in f or f in key:
                        return grp
            return key

        for t_edge in template_edges:
            src_step = t_edge["source"]
            tgt_step = t_edge["target"]
            src_node = node_map.get(src_step)
            tgt_node = node_map.get(tgt_step)
            if not src_node or not tgt_node:
                continue

            src_outputs = set(o.lower() for o in src_node.output_fields)
            tgt_inputs = set(i.lower() for i in tgt_node.input_requirements)
            # Semantic groups produced by the upstream node, derived strictly
            # from its declared output fields (no implicit "customer" injection,
            # which previously masked all real IO mismatches).
            src_groups = set(field_group(o) for o in src_node.output_fields)
            # A score/probability/ranking output is semantically consumable as
            # a transactional signal, so it also satisfies those groups — but
            # only when the downstream actually needs them.
            produces_signal = any(
                key.endswith("_score")
                or key.endswith("_probability")
                or key in {"ranked_list", "customer_ranking", "risk_level", "alert_signal"}
                for key in src_outputs
            )
            tgt_groups = set(field_group(i) for i in tgt_node.input_requirements)
            if produces_signal:
                src_groups |= {"transaction", "marketing"}

            # Check group-level compatibility
            group_overlap = src_groups & tgt_groups
            # Identify which downstream input groups are NOT covered by the
            # upstream output. These are the missing dependencies.
            missing_groups = tgt_groups - src_groups
            missing_fields = sorted({
                i for i in tgt_node.input_requirements
                if field_group(i) in missing_groups and field_group(i) != "customer"
            })

            if group_overlap and len(group_overlap) >= len(tgt_groups) * 0.5:
                io_status = "pass"
            elif group_overlap:
                # Some (but not enough) overlap — soft degradation.
                io_status = "partial"
            else:
                # No semantic overlap at all: the upstream output cannot feed
                # this node's inputs. This is a hard failure that should block
                # the downstream node rather than be silently swallowed.
                io_status = "fail"

            suggestion = ""
            if io_status == "fail":
                if missing_fields:
                    suggestion = (
                        f"上游输出无法满足该节点核心输入（缺失：{', '.join(missing_fields[:5])}），"
                        "需补充数据源或调整节点顺序。"
                    )
                else:
                    suggestion = "上游输出与下游核心输入之间没有可映射字段，需补充数据源或调整节点顺序。"
            elif io_status == "partial":
                suggestion = (
                    f"部分输入需从外部数据补充：{', '.join(missing_fields[:5])}" if missing_fields else ""
                )

            edges.append(CompositionEdge(
                source_node_id=src_node.node_id,
                target_node_id=tgt_node.node_id,
                io_status=io_status,
                missing_fields=missing_fields,
                suggestion=suggestion,
            ))

        return edges

    def _compute_io_result(self, edges: list[CompositionEdge]) -> IOCompatibilityResult:
        """Compute overall IO compatibility statistics."""
        total = len(edges)
        if total == 0:
            return IOCompatibilityResult()
        passed = sum(1 for e in edges if e.io_status == "pass")
        partial = sum(1 for e in edges if e.io_status == "partial")
        failed = sum(1 for e in edges if e.io_status == "fail")
        # Partial edges mean the downstream node can run with external data supplementation, so they earn half IO credit. Failures remain zero-credit hard gaps.
        rate = (passed + partial * 0.5) / total if total > 0 else 0
        return IOCompatibilityResult(
            total_edges=total,
            passed=passed,
            partial=partial,
            failed=failed,
            compatibility_rate=round(rate, 2),
        )

    def _compute_composition_score(
        self,
        template: dict[str, Any],
        nodes: list[CompositionNode],
        edges: list[CompositionEdge],
        io_result: IOCompatibilityResult,
        parse_result: dict[str, Any],
    ) -> float:
        """Compute overall composition score using weighted formula."""
        # Process coverage: how many template nodes are filled
        template_node_count = len(template.get("nodes", []))
        if template_node_count == 0:
            # Templates use "stages" format — count required_models across stages
            template_node_count = sum(
                len(st.get("required_models", []))
                for st in template.get("stages", [])
            )
        filled_count = len(nodes)
        process_coverage = min(100, (filled_count / max(template_node_count, 1)) * 100)

        # Scenario consistency — use LLM for semantic matching when available
        scenario = parse_result.get("business_scenario", "")
        t_scenarios = template.get("applicable_scenarios", [])
        t_name = template.get("name", "")
        if scenario and t_scenarios:
            if any(scenario in ts or ts in scenario for ts in t_scenarios):
                scenario_consistency = 90.0
            elif self.llm.available:
                # Use LLM to check semantic match
                llm_check = self._check_scenario_match_llm(scenario, t_scenarios, t_name)
                scenario_consistency = 85.0 if llm_check else 70.0
            else:
                scenario_consistency = 70.0
        elif scenario:
            scenario_consistency = 70.0
        else:
            scenario_consistency = 60.0

        # Node fit average
        node_fit_avg = sum(n.fit_score for n in nodes) / max(len(nodes), 1)

        # IO compatibility
        io_score = io_result.compatibility_rate * 100

        # Data availability
        total_inputs = sum(len(n.input_requirements) for n in nodes)
        missing = io_result.partial * 2 + io_result.failed * 5
        data_avail = max(0, min(100, 100 - (missing / max(total_inputs, 1)) * 20))

        # Landing feasibility
        landing_count = sum(1 for n in nodes if any(
            m.get("historical_cases", []) for m in self.models if m["model_id"] == n.model_id
        ))
        landing_feasibility = min(100, (landing_count / max(len(nodes), 1)) * 100)

        # Compliance feasibility — check if models have compliance notes
        compliance_count = sum(
            1 for n in nodes if any(
                m.get("compliance_boundary", "") for m in self.models if m["model_id"] == n.model_id
            )
        )
        compliance_score = 85.0 if compliance_count >= len(nodes) else 75.0

        total = (
            process_coverage * W_PROCESS +
            scenario_consistency * W_SCENARIO_CONSISTENCY +
            node_fit_avg * W_NODE_FIT +
            io_score * W_IO +
            data_avail * W_DATA +
            landing_feasibility * W_LANDING +
            compliance_score * W_COMPLIANCE
        )
        total -= io_result.failed * 1.5 + io_result.partial * 0.25
        return max(0.0, total)

    def _collect_missing_data(
        self,
        nodes: list[CompositionNode],
        parse_result: dict[str, Any],
    ) -> list[str]:
        """Collect data that is required but not available."""
        data_conds = parse_result.get("data_conditions", [])
        cond_set = set(d.lower() for d in data_conds)

        missing: set[str] = set()
        for node in nodes:
            for req in node.input_requirements:
                if not any(req.lower() in cond or cond in req.lower() for cond in cond_set):
                    missing.add(req)

        return list(missing)[:10]

    def _build_fallback(self, parse_result: dict[str, Any]) -> RecommendCompositionResponse:
        """Build a simple fallback composition when no template matches."""
        return RecommendCompositionResponse(
            composition_id=f"COMP_FALLBACK_{uuid.uuid4().hex[:6].upper()}",
            composition_name="单模型使用方案",
            scenario=parse_result.get("business_scenario", "通用"),
            total_score=60.0,
            composition_status="no_template",
            failure_reasons=["No standard composition template matched the demand."],
            demo_execution_only=True,
            usage_guide=[
                "当前需求暂未匹配到标准组合模板",
                "建议使用推荐的单模型满足核心需求",
                "如有更复杂的流程需求，请补充更多业务细节",
            ],
        )

    def _generate_usage_guide(self, nodes: list[CompositionNode]) -> list[str]:
        """Generate a usage guide from the composition."""
        guide: list[str] = []
        for i, node in enumerate(nodes, 1):
            guide.append(f"第{i}步：{node.node_explanation}（使用{node.model_name}）")
        if guide:
            guide.append("所有节点串联完成，输出最终结果。")
        return guide

    def _generate_explanations_with_llm(
        self, template: dict[str, Any], nodes: list[CompositionNode],
        parse_result: dict[str, Any]
    ) -> dict[str, str] | None:
        """Use LLM to generate rich three-mode explanations."""
        scenario = parse_result.get("business_scenario", "")
        t_name = template.get("name", "")
        node_text = "\n".join(
            f"  {n.step_order}. {n.capability} -> {n.model_name} (fit={n.fit_score})"
            for n in nodes
        )
        system = (
            "You are a bank solution architect. Generate three explanation modes "
            "for a model composition. Output ONLY JSON with business/technical/management keys."
        )
        user = (
            f"Scenario: {scenario}\n"
            f"Composition: {t_name}\n"
            f"Models:{node_text}\n\n"
            'Return: {{"business": "业务人员版本(100字内)", '
            '"technical": "技术人员版本(100字内)", '
            '"management": "管理层版本(100字内)"}}'
        )
        result = self.llm.chat_json(system, user)
        if result and all(k in result for k in ("business", "technical", "management")):
            return {
                "business": str(result["business"]),
                "technical": str(result["technical"]),
                "management": str(result["management"]),
            }
        return None
