#!/usr/bin/env python3
"""
B-12: Data Validation Script for Model Market Agent Tasks.
Validates all data files for schema compliance, completeness, and consistency.
Run: python scripts/validate_data.py
Exit code 0 = all passed.
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERRORS = []
WARNINGS = []

def err(msg):
    ERRORS.append(msg)
    print(f"  FAIL: {msg}")

def warn(msg):
    WARNINGS.append(msg)
    print(f"  WARN: {msg}")

def ok(msg):
    print(f"  OK: {msg}")

def load_json(path):
    # Accept UTF-8 files with or without a BOM. Some spreadsheet/document
    # export workflows add one even though JSON itself does not require it.
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

# ================================================================
# Collect valid tag keys from tags.json
# ================================================================
VALID_TAGS = set()
TAG_CATEGORIES = {}
tags_path = os.path.join(BASE_DIR, "data", "knowledge", "tags.json")
if not os.path.exists(tags_path):
    err("tags.json not found")
    sys.exit(1)

tags_data = load_json(tags_path)
for category, items in tags_data.items():
    TAG_CATEGORIES[category] = []
    for item in items:
        key = item.get("key")
        if key:
            VALID_TAGS.add(key)
            TAG_CATEGORIES[category].append(key)

print(f"\n[Tag Registry] {len(VALID_TAGS)} valid tags across {len(TAG_CATEGORIES)} categories")

# Collect valid domain values
VALID_DOMAINS = {"credit_risk", "customer_marketing", "operation_management"}
VALID_BUSINESS_STAGES = {"pre_loan", "in_loan", "post_loan", "pre_marketing", "in_marketing",
                         "post_marketing", "daily_operation", "risk_management", "compliance",
                         "resource_planning", "performance_analysis"}
VALID_DEPLOY_STATUS = {"production", "staging", "mock_available", "development"}

# Collect valid model IDs
VALID_MODEL_IDS = set()

# ================================================================
# 1. Validate model JSON files in data/knowledge/
# ================================================================
print("\n" + "=" * 60)
print("CHECK 1: Model metadata JSON files")
print("=" * 60)

knowledge_dir = os.path.join(BASE_DIR, "data", "knowledge")
model_files = [f for f in os.listdir(knowledge_dir) if f.endswith(".json") and f[0:3] in ("RIS", "MKT", "OPS")]

required_fields = ["model_id", "model_name", "domain", "business_scenario", "business_stage",
                   "customer_segment", "model_capability", "input_fields_required", "input_fields_optional",
                   "output_fields", "performance_metrics", "applicable_conditions", "unsuitable_conditions",
                   "compliance_boundary", "deployment_status", "api_available", "historical_cases", "tags", "description"]

domain_prefix_map = {"RIS": "credit_risk", "MKT": "customer_marketing", "OPS": "operation_management"}

model_count = 0
for mf in sorted(model_files):
    model_count += 1
    path = os.path.join(knowledge_dir, mf)
    try:
        data = load_json(path)
    except Exception as e:
        err(f"{mf}: cannot parse JSON - {e}")
        continue

    # Required fields
    for field in required_fields:
        if field not in data:
            err(f"{mf}: missing required field '{field}'")

    # model_id matches filename
    expected_id = mf.replace(".json", "")
    if data.get("model_id") != expected_id:
        err(f"{mf}: model_id '{data.get('model_id')}' does not match filename '{expected_id}'")

    # Validate domain
    prefix = expected_id[:3]
    expected_domain = domain_prefix_map.get(prefix)
    if data.get("domain") != expected_domain:
        err(f"{mf}: domain '{data.get('domain')}' does not match expected '{expected_domain}' for prefix {prefix}")

    # Validate business_stage values
    for stage in data.get("business_stage", []):
        if stage not in VALID_BUSINESS_STAGES:
            err(f"{mf}: invalid business_stage '{stage}'")

    # Validate deployment_status
    dep_status = data.get("deployment_status")
    if dep_status not in VALID_DEPLOY_STATUS:
        err(f"{mf}: invalid deployment_status '{dep_status}'")

    # Validate tags
    for tag in data.get("tags", []):
        if tag not in VALID_TAGS:
            err(f"{mf}: tag '{tag}' not found in tags.json")

    # Validate api_available is boolean
    if not isinstance(data.get("api_available"), bool):
        err(f"{mf}: api_available must be boolean")

    # Validate performance_metrics is non-empty object
    metrics = data.get("performance_metrics", {})
    if not isinstance(metrics, dict) or len(metrics) == 0:
        err(f"{mf}: performance_metrics must be non-empty object")

    # Validate historical_cases
    cases = data.get("historical_cases", [])
    if not isinstance(cases, list) or len(cases) == 0:
        err(f"{mf}: historical_cases must be non-empty array")
    else:
        for c in cases:
            for cf in ["client", "description", "effect"]:
                if cf not in c:
                    err(f"{mf}: historical_cases item missing '{cf}'")

    VALID_MODEL_IDS.add(data.get("model_id"))

print(f"  Total model files: {model_count}")
print(f"  Unique valid model IDs: {len(VALID_MODEL_IDS)}")

# Check for duplicate model IDs
model_ids_list = []
for mf in sorted(model_files):
    data = load_json(os.path.join(knowledge_dir, mf))
    model_ids_list.append(data.get("model_id"))
dup_ids = [mid for mid in model_ids_list if model_ids_list.count(mid) > 1]
if dup_ids:
    for did in set(dup_ids):
        err(f"Duplicate model_id '{did}' found")

# Check model count per domain
risk_count = len([f for f in model_files if f.startswith("RIS")])
mkt_count = len([f for f in model_files if f.startswith("MKT")])
ops_count = len([f for f in model_files if f.startswith("OPS")])
print(f"  RISK: {risk_count}, MKT: {mkt_count}, OPS: {ops_count}")
if risk_count < 25:
    err(f"RISK models < 25 (got {risk_count})")
if mkt_count < 25:
    err(f"MKT models < 25 (got {mkt_count})")
if ops_count < 25:
    err(f"OPS models < 25 (got {ops_count})")
if model_count < 100:
    err(f"Total models < 100 (got {model_count})")

# ================================================================
# 1B. Empty required fields in model files
# ================================================================
print("\n" + "=" * 60)
print("CHECK 1B: Empty required fields in model files")
print("=" * 60)

non_empty_fields = ["model_name", "description", "domain", "business_scenario",
                    "business_stage", "customer_segment", "model_capability",
                    "input_fields_required", "output_fields", "tags"]

for mf in sorted(model_files):
    data = load_json(os.path.join(knowledge_dir, mf))
    for field in non_empty_fields:
        val = data.get(field)
        if val is None or val == "" or val == []:
            err(f"{mf}: required field '{field}' is empty")

# ================================================================
# 2. Validate tags.json is complete
# ================================================================
print("\n" + "=" * 60)
print("CHECK 2: tags.json integrity")
print("=" * 60)

expected_tag_categories = ["domain_tags", "business_stage_tags", "customer_segment_tags",
                           "product_tags", "capability_tags", "output_tags",
                           "data_requirement_tags", "compliance_tags"]
for cat in expected_tag_categories:
    if cat not in tags_data:
        err(f"tags.json missing category '{cat}'")
    elif len(tags_data[cat]) == 0:
        err(f"tags.json category '{cat}' is empty")
    else:
        ok(f"{cat}: {len(tags_data[cat])} tags")

# ================================================================
# 3. Validate data_fields.json
# ================================================================
print("\n" + "=" * 60)
print("CHECK 3: data_fields.json integrity")
print("=" * 60)

if not os.path.exists(tags_path):
    err("data_fields.json not found")
else:
    df = load_json(os.path.join(knowledge_dir, "data_fields.json"))
    fields = df.get("fields", [])
    valid_field_keys = set()
    for f in fields:
        fk = f.get("field_key")
        if fk:
            valid_field_keys.add(fk)
        for ff in ["field_key", "name", "category", "sensitivity"]:
            if ff not in f:
                err(f"data_fields field missing '{ff}': {f.get('field_key', '?')}")

    ok(f"Total fields: {len(fields)}, valid keys: {len(valid_field_keys)}")

    # Check all model input_fields_required and input_fields_optional reference valid keys
    for mf in sorted(model_files):
        path = os.path.join(knowledge_dir, mf)
        data = load_json(path)
        for field in data.get("input_fields_required", []):
            if field not in valid_field_keys:
                err(f"{mf}: input_fields_required '{field}' not in data_fields.json keys")
        for field in data.get("input_fields_optional", []):
            if field not in valid_field_keys:
                err(f"{mf}: input_fields_optional '{field}' not in data_fields.json keys")

# ================================================================
# 4. Validate demand_samples.jsonl
# ================================================================
print("\n" + "=" * 60)
print("CHECK 4: demand_samples.jsonl")
print("=" * 60)

samples_path = os.path.join(BASE_DIR, "data", "samples", "demand_samples.jsonl")
if not os.path.exists(samples_path):
    err("demand_samples.jsonl not found")
else:
    samples = load_jsonl(samples_path)
    if len(samples) < 100:
        err(f"demand_samples < 100 (got {len(samples)})")
    else:
        ok(f"Total demand samples: {len(samples)}")

    for s in samples:
        for field in ["demand_id", "user_query", "intent", "scenario"]:
            if field not in s:
                err(f"demand sample {s.get('demand_id', '?')} missing '{field}'")

# ================================================================
# 5. Validate demand_model_labels.jsonl
# ================================================================
print("\n" + "=" * 60)
print("CHECK 5: demand_model_labels.jsonl")
print("=" * 60)

labels_path = os.path.join(BASE_DIR, "data", "samples", "demand_model_labels.jsonl")
if not os.path.exists(labels_path):
    err("demand_model_labels.jsonl not found")
else:
    labels = load_jsonl(labels_path)
    if len(labels) < 100:
        err(f"demand_model_labels < 100 (got {len(labels)})")
    else:
        ok(f"Total labels: {len(labels)}")

    for lbl in labels:
        for field in ["demand_id", "model_id", "relevance_score", "label_type"]:
            if field not in lbl:
                err(f"label missing '{field}': {lbl.get('demand_id', '?')}->{lbl.get('model_id', '?')}")
        if lbl.get("model_id") not in VALID_MODEL_IDS:
            err(f"label references unknown model_id '{lbl.get('model_id')}'")
        if not isinstance(lbl.get("relevance_score"), (int, float)) or not (0 <= lbl.get("relevance_score", -1) <= 1):
            err(f"label relevance_score out of range [0,1]: {lbl.get('relevance_score')}")
        if lbl.get("label_type") not in ("primary", "alternative"):
            err(f"label invalid label_type '{lbl.get('label_type')}'")

# ================================================================
# 6. Validate composition_cases.jsonl
# ================================================================
print("\n" + "=" * 60)
print("CHECK 6: composition_cases.jsonl")
print("=" * 60)

comp_path = os.path.join(BASE_DIR, "data", "samples", "composition_cases.jsonl")
if not os.path.exists(comp_path):
    err("composition_cases.jsonl not found")
else:
    cases = load_jsonl(comp_path)
    if len(cases) < 30:
        err(f"composition_cases < 30 (got {len(cases)})")
    else:
        ok(f"Total composition cases: {len(cases)}")

    for c in cases:
        for field in ["case_id", "name", "description", "models", "scenario"]:
            if field not in c:
                err(f"composition case {c.get('case_id', '?')} missing '{field}'")
        for model_id in c.get("models", []):
            if model_id not in VALID_MODEL_IDS:
                err(f"composition case {c.get('case_id', '?')} references unknown model '{model_id}'")

# ================================================================
# 7. Validate composition_templates.json
# ================================================================
print("\n" + "=" * 60)
print("CHECK 7: composition_templates.json")
print("=" * 60)

tpl_path = os.path.join(knowledge_dir, "composition_templates.json")
if not os.path.exists(tpl_path):
    err("composition_templates.json not found")
else:
    templates = load_json(tpl_path)
    if len(templates) < 5:
        err(f"composition_templates < 5 (got {len(templates)})")
    else:
        ok(f"Total templates: {len(templates)}")

    for t in templates:
        for field in ["template_id", "name", "description", "applicable_scenarios", "stages"]:
            if field not in t:
                err(f"template {t.get('template_id', '?')} missing '{field}'")
        for stage in t.get("stages", []):
            for sf in ["stage", "name", "required_models", "optional_models"]:
                if sf not in stage:
                    err(f"template {t.get('template_id', '?')} stage missing '{sf}'")

# ================================================================
# 8. Validate eval files
# ================================================================
print("\n" + "=" * 60)
print("CHECK 8: Evaluation data files")
print("=" * 60)

eval_dir = os.path.join(BASE_DIR, "data", "eval")
eval_files = {
    "intent_eval.jsonl": {"fields": ["test_id", "query", "expected_intent", "expected_domain", "difficulty"]},
    "tag_eval.jsonl": {"fields": ["test_id", "query", "expected_tags", "difficulty"]},
    "topk_eval.jsonl": {"fields": ["test_id", "query", "expected_model_ids", "k"]},
    "explanation_eval.jsonl": {"fields": ["demand_id", "raw_text", "scenario", "target_audiences", "note"]},
}

for fname, spec in eval_files.items():
    fpath = os.path.join(eval_dir, fname)
    if not os.path.exists(fpath):
        err(f"{fname} not found")
    else:
        items = load_jsonl(fpath)
        ok(f"{fname}: {len(items)} entries")
        for item in items:
            for field in spec["fields"]:
                if field not in item:
                    err(f"{fname}: {item.get('test_id', '?')} missing '{field}'")

# explanation_survey_mock.json
survey_path = os.path.join(eval_dir, "explanation_survey_mock.json")
if not os.path.exists(survey_path):
    err("explanation_survey_mock.json not found")
else:
    survey = load_json(survey_path)
    for field in ["survey_meta", "questions", "conclusion"]:
        if field not in survey:
            err(f"explanation_survey_mock.json missing '{field}'")
    ok("explanation_survey_mock.json: valid")

# Gold model ID validation for topk_eval.jsonl
topk_path = os.path.join(eval_dir, "topk_eval.jsonl")
if os.path.exists(topk_path):
    topk_items = load_jsonl(topk_path)
    for item in topk_items:
        gold_ids = item.get("expected_model_ids", item.get("gold_model_ids", []))
        if isinstance(gold_ids, str):
            gold_ids = [gold_ids]
        for gid in gold_ids:
            if gid not in VALID_MODEL_IDS:
                err(f"topk_eval: {item.get('test_id', '?')} gold model_id '{gid}' not found in knowledge base")

# Domain validation for intent_eval.jsonl
intent_path = os.path.join(eval_dir, "intent_eval.jsonl")
if os.path.exists(intent_path):
    for item in load_jsonl(intent_path):
        exp_domain = item.get("expected_domain", item.get("expected_intent", ""))
        if exp_domain and exp_domain not in VALID_DOMAINS:
            err(f"intent_eval: {item.get('test_id', '?')} invalid expected_domain '{exp_domain}'")

# ================================================================
# 9. Configuration files
# ================================================================
print("\n" + "=" * 60)
print("CHECK 9: Configuration files")
print("=" * 60)

config_dir = os.path.join(BASE_DIR, "data", "config")
if not os.path.exists(config_dir):
    warn("data/config directory not found, skipping config checks")
else:
    # recommendation_weights.json
    weights_path = os.path.join(config_dir, "recommendation_weights.json")
    if os.path.exists(weights_path):
        errors_before_weights = len(ERRORS)
        weights = load_json(weights_path)
        if not isinstance(weights, dict):
            err("recommendation_weights.json must be a dict")
        else:
            nested_sections = {"rerank", "score_blend", "hybrid_retrieval"}
            for key, val in weights.items():
                if key not in nested_sections and not isinstance(val, (int, float)):
                    err(f"recommendation_weights.json: '{key}' value must be numeric, got {type(val).__name__}")

            rerank = weights.get("rerank")
            if not isinstance(rerank, dict):
                err("recommendation_weights.json: 'rerank' must be a dict")
            else:
                candidate_pool = rerank.get("candidate_pool")
                llm_weight = rerank.get("llm_weight")
                required_count = rerank.get("required_ranked_count")
                repair_attempts = rerank.get("repair_attempts")
                if not isinstance(candidate_pool, int) or candidate_pool <= 0:
                    err("recommendation_weights.json: rerank.candidate_pool must be a positive integer")
                if not isinstance(llm_weight, (int, float)) or not 0 <= llm_weight <= 1:
                    err("recommendation_weights.json: rerank.llm_weight must be between 0 and 1")
                if not isinstance(required_count, int) or not isinstance(candidate_pool, int) or not 5 <= required_count <= candidate_pool:
                    err("recommendation_weights.json: rerank.required_ranked_count must be between 5 and candidate_pool")
                if not isinstance(repair_attempts, int) or repair_attempts < 0:
                    err("recommendation_weights.json: rerank.repair_attempts must be a non-negative integer")
                if not isinstance(rerank.get("cache_enabled"), bool):
                    err("recommendation_weights.json: rerank.cache_enabled must be boolean")

            score_blend = weights.get("score_blend")
            if not isinstance(score_blend, dict):
                err("recommendation_weights.json: 'score_blend' must be a dict")
            else:
                blend_values = [score_blend.get(key) for key in ("base", "graph", "field")]
                if not all(isinstance(value, (int, float)) and 0 <= value <= 1 for value in blend_values):
                    err("recommendation_weights.json: score_blend values must be numeric and between 0 and 1")
                elif abs(sum(blend_values) - 1.0) > 1e-9:
                    err("recommendation_weights.json: score_blend values must sum to 1.0")

            hybrid = weights.get("hybrid_retrieval")
            if not isinstance(hybrid, dict):
                err("recommendation_weights.json: 'hybrid_retrieval' must be a dict")
            else:
                for pair in (("rule_weight", "retrieval_weight"), ("full_text_weight", "title_text_weight")):
                    values = [hybrid.get(key) for key in pair]
                    if not all(isinstance(value, (int, float)) and 0 <= value <= 1 for value in values):
                        err(f"recommendation_weights.json: hybrid {pair[0]}/{pair[1]} must be between 0 and 1")
                    elif abs(sum(values) - 1.0) > 1e-9:
                        err(f"recommendation_weights.json: hybrid {pair[0]}/{pair[1]} must sum to 1.0")
                candidate_pool = hybrid.get("candidate_pool")
                dense_weight = hybrid.get("dense_weight")
                dense_cache_enabled = hybrid.get("dense_cache_enabled")
                dense_cache_dir = hybrid.get("dense_cache_dir")
                if not isinstance(candidate_pool, int) or candidate_pool <= 0:
                    err("recommendation_weights.json: hybrid candidate_pool must be a positive integer")
                if not isinstance(dense_weight, (int, float)) or not 0 <= dense_weight <= 1:
                    err("recommendation_weights.json: hybrid dense_weight must be between 0 and 1")
                if not isinstance(dense_cache_enabled, bool):
                    err("recommendation_weights.json: hybrid dense_cache_enabled must be boolean")
                if not isinstance(dense_cache_dir, str) or not dense_cache_dir.strip():
                    err("recommendation_weights.json: hybrid dense_cache_dir must be a non-empty string")
            if len(ERRORS) == errors_before_weights:
                ok("recommendation_weights.json: valid")
    else:
        warn("recommendation_weights.json not found (optional)")

    # synonyms.json
    synonyms_path = os.path.join(config_dir, "synonyms.json")
    if os.path.exists(synonyms_path):
        synonyms = load_json(synonyms_path)
        if not isinstance(synonyms, dict):
            err("synonyms.json must be a dict")
        else:
            ok("synonyms.json: valid")
    else:
        warn("synonyms.json not found (optional)")

# ================================================================
# 10. Official data validation
# ================================================================
print("\n" + "=" * 60)
print("CHECK 10: Official data files")
print("=" * 60)

official_dir = os.path.join(BASE_DIR, "data", "official")

# 10.1 Line-count checks for question files
official_counts = {
    "questions_train.jsonl": 291,
    "questions_test.jsonl": 62,
    "questions_val.jsonl": 64,
    "questions_all.jsonl": 417,
}
for fname, expected in official_counts.items():
    fpath = os.path.join(official_dir, fname)
    if not os.path.exists(fpath):
        err(f"official/{fname} not found")
    else:
        with open(fpath, "r", encoding="utf-8") as f:
            actual = sum(1 for _ in f)
        if actual != expected:
            err(f"official/{fname}: expected {expected} lines, got {actual}")
        else:
            ok(f"official/{fname}: {actual} lines")

# 10.2 model_catalog_structured.jsonl
catalog_path = os.path.join(official_dir, "model_catalog_structured.jsonl")
if not os.path.exists(catalog_path):
    err("official/model_catalog_structured.jsonl not found")
else:
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog_lines = [json.loads(line) for line in f if line.strip()]
    if len(catalog_lines) != 60:
        err(f"official/model_catalog_structured.jsonl: expected 60 lines, got {len(catalog_lines)}")
    else:
        ok(f"official/model_catalog_structured.jsonl: {len(catalog_lines)} lines")
    for rec in catalog_lines:
        if "model_id" not in rec:
            err("official/model_catalog_structured.jsonl: missing 'model_id'")
        if "canonical_name" not in rec:
            err("official/model_catalog_structured.jsonl: missing 'canonical_name'")
        if rec.get("source") != "official":
            err(f"official/model_catalog_structured.jsonl: {rec.get('model_id', '?')} source != 'official'")

# 10.3 model_name_map.json
map_path = os.path.join(official_dir, "model_name_map.json")
if not os.path.exists(map_path):
    err("official/model_name_map.json not found")
else:
    map_data = load_json(map_path)
    total_unique = map_data.get("total_unique")
    if total_unique != 60:
        err(f"official/model_name_map.json: total_unique expected 60, got {total_unique}")
    else:
        ok(f"official/model_name_map.json: total_unique = {total_unique}")

# 10.4 eval_official files
eval_official_dir = os.path.join(BASE_DIR, "data", "eval_official")
expected_eval_files = [
    "combo_eval_official_manual.jsonl",
    "intent_eval_official.jsonl",
    "tag_eval_official.jsonl",
    "topk_eval_official.jsonl",
]
for ef in expected_eval_files:
    efpath = os.path.join(eval_official_dir, ef)
    if not os.path.exists(efpath):
        err(f"eval_official/{ef} not found")
    else:
        ok(f"eval_official/{ef}: exists")

# ================================================================
# Summary
# ================================================================
print("\n" + "=" * 60)
print("VALIDATION SUMMARY")
print("=" * 60)
print(f"  Errors:   {len(ERRORS)}")
print(f"  Warnings: {len(WARNINGS)}")

if ERRORS:
    print("\n  [FAIL] VALIDATION FAILED - fix errors above and re-run")
    sys.exit(1)
else:
    print("\n  [PASS] ALL CHECKS PASSED!")
    sys.exit(0)
