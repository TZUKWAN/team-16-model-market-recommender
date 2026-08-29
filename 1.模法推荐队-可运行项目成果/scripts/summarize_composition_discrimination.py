from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "composition" / "composition_discrimination_final.json"
OUTPUT = ROOT / "reports" / "composition" / "composition_discrimination_summary.json"
sys.path.insert(0, str(ROOT / "backend"))
from app.services.composition_planner import CompositionPlanner  # noqa: E402


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    evaluation = payload["composition_evaluation"]
    details = evaluation["details"]
    scores = [float(row["composition_score"]) for row in details]
    status_counts: dict[str, int] = {}
    templates: dict[str, int] = {}
    signatures = set()
    for row in details:
        status = str(row.get("composition_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        name = str(row.get("composition_name") or "unknown")
        templates[name] = templates.get(name, 0) + 1
        signatures.add(tuple(row.get("node_model_ids") or []))
    planner = CompositionPlanner()
    no_template = planner.plan({"intent": "unknown", "business_scenario": "", "tags": []})
    no_permission = planner.plan({
        "intent": "credit_risk",
        "business_scenario": "农户贷款贷前反欺诈和准入评分",
        "tags": ["credit_risk", "pre_loan", "anti_fraud"],
        "permitted_domains": [],
    })
    result = {
        "total": len(details),
        "average_score": round(statistics.mean(scores), 2),
        "min_score": min(scores),
        "max_score": max(scores),
        "score_stddev": round(statistics.pstdev(scores), 3),
        "unique_score_count": len(set(scores)),
        "template_counts": templates,
        "unique_node_signatures": len(signatures),
        "status_counts": status_counts,
        "blocked_case_count": sum(bool(row.get("blocked_nodes")) for row in details),
        "target_met": statistics.mean(scores) >= 80,
        "controlled_negative_cases": [
            {"case": "no_template", "score": no_template.total_score, "status": no_template.composition_status},
            {"case": "no_permitted_model", "score": no_permission.total_score, "status": no_permission.composition_status},
        ],
        "demo_execution_boundary": "Composition execution remains desensitized demo orchestration, not bank production execution.",
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["target_met"] and result["unique_score_count"] > 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
