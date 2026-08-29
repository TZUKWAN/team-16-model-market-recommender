#!/usr/bin/env python3
"""
B-12: Data Loader Script for Model Market Agent Tasks.
Provides a unified interface to load all data artifacts.
Usage:
    from scripts.load_data import load_all_data, load_models, load_tags, ...
"""
import json
import os
from typing import Dict, List, Any, Union

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_jsonl(path: str) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---- Model metadata ----
def load_models() -> Dict[str, dict]:
    """Load all model metadata JSON files. Returns dict keyed by model_id."""
    models: Dict[str, dict] = {}
    knowledge_dir = os.path.join(BASE_DIR, "data", "knowledge")
    for fname in sorted(os.listdir(knowledge_dir)):
        if fname.endswith(".json") and fname[0:3] in ("RIS", "MKT", "OPS"):
            data = load_json(os.path.join(knowledge_dir, fname))
            models[data["model_id"]] = data
    return models


def get_models_by_domain(domain: str) -> Dict[str, dict]:
    """Get all models in a domain: credit_risk / customer_marketing / operation_management."""
    all_models = load_models()
    return {mid: m for mid, m in all_models.items() if m["domain"] == domain}


# ---- Tags ----
def load_tags() -> dict:
    """Load the tag taxonomy from tags.json."""
    return load_json(os.path.join(BASE_DIR, "data", "knowledge", "tags.json"))


def get_all_tag_keys() -> set:
    """Return all valid tag keys from tag taxonomy."""
    tags = load_tags()
    keys = set()
    for category_items in tags.values():
        for item in category_items:
            if "key" in item:
                keys.add(item["key"])
    return keys


# ---- Data fields ----
def load_data_fields() -> List[dict]:
    """Load the data field dictionary."""
    data = load_json(os.path.join(BASE_DIR, "data", "knowledge", "data_fields.json"))
    return data.get("fields", [])


def get_valid_data_field_keys() -> set:
    """Return all valid data field keys."""
    return {f["field_key"] for f in load_data_fields() if "field_key" in f}


# ---- Demand samples ----
def load_demand_samples() -> List[dict]:
    """Load business demand samples."""
    return load_jsonl(os.path.join(BASE_DIR, "data", "samples", "demand_samples.jsonl"))


# ---- Demand-model labels ----
def load_demand_model_labels() -> List[dict]:
    """Load demand-model annotation labels."""
    return load_jsonl(os.path.join(BASE_DIR, "data", "samples", "demand_model_labels.jsonl"))


# ---- Composition cases ----
def load_composition_cases() -> List[dict]:
    """Load composition scenario cases."""
    return load_jsonl(os.path.join(BASE_DIR, "data", "samples", "composition_cases.jsonl"))


# ---- Composition templates ----
def load_composition_templates() -> List[dict]:
    """Load composition templates."""
    return load_json(os.path.join(BASE_DIR, "data", "knowledge", "composition_templates.json"))


# ---- Eval data ----
def load_intent_eval() -> List[dict]:
    return load_jsonl(os.path.join(BASE_DIR, "data", "eval", "intent_eval.jsonl"))


def load_tag_eval() -> List[dict]:
    return load_jsonl(os.path.join(BASE_DIR, "data", "eval", "tag_eval.jsonl"))


def load_topk_eval() -> List[dict]:
    return load_jsonl(os.path.join(BASE_DIR, "data", "eval", "topk_eval.jsonl"))


def load_explanation_survey() -> dict:
    return load_json(os.path.join(BASE_DIR, "data", "eval", "explanation_survey_mock.json"))


def load_explanation_eval() -> list:
    """Load explanation eval test queries."""
    return load_jsonl(os.path.join(BASE_DIR, "data", "eval", "explanation_eval.jsonl"))


# ---- Bulk load ----
def load_all_data() -> dict:
    """Load all data artifacts into a single dict."""
    return {
        "models": load_models(),
        "tags": load_tags(),
        "data_fields": load_data_fields(),
        "demand_samples": load_demand_samples(),
        "demand_model_labels": load_demand_model_labels(),
        "composition_cases": load_composition_cases(),
        "composition_templates": load_composition_templates(),
        "intent_eval": load_intent_eval(),
        "tag_eval": load_tag_eval(),
        "topk_eval": load_topk_eval(),
        "explanation_survey": load_explanation_survey(),
        "explanation_eval": load_explanation_eval(),
    }


if __name__ == "__main__":
    print("Loading all data...")
    data = load_all_data()
    print(f"  Models:              {len(data['models'])}")
    print(f"  Tag categories:      {len(data['tags'])}")
    print(f"  Data fields:         {len(data['data_fields'])}")
    print(f"  Demand samples:      {len(data['demand_samples'])}")
    print(f"  Demand-model labels: {len(data['demand_model_labels'])}")
    print(f"  Composition cases:   {len(data['composition_cases'])}")
    print(f"  Composition templates:{len(data['composition_templates'])}")
    print(f"  Intent eval:         {len(data['intent_eval'])}")
    print(f"  Tag eval:            {len(data['tag_eval'])}")
    print(f"  TopK eval:           {len(data['topk_eval'])}")
    print(f"  Survey:              {len(data['explanation_survey'])} keys")
    print(f"  Explanation eval:    {len(data['explanation_eval'])} entries")
    print("All data loaded successfully!")
