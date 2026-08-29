#!/usr/bin/env python3
"""Generate all model metadata JSON files with diverse, realistic content."""
import json
import os
import sys

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "knowledge")
os.makedirs(KNOWLEDGE_DIR, exist_ok=True)


def save_model(data):
    path = os.path.join(KNOWLEDGE_DIR, f"{data['model_id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Created: {data['model_id']} - {data['model_name']}")


def load_models_from_jsonl(filepath):
    if not os.path.exists(filepath):
        print(f"  File not found: {filepath}")
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "model_data")

    # Load model data from separate JSONL files
    for domain_file in ["risk_models.jsonl", "mkt_models.jsonl", "ops_models.jsonl"]:
        filepath = os.path.join(models_dir, domain_file)
        models = load_models_from_jsonl(filepath)
        print(f"\nLoading {len(models)} models from {domain_file}...")
        for m in models:
            save_model(m)

    print("\nAll models generated successfully!")
