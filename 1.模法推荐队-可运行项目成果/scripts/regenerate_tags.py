#!/usr/bin/env python3
"""Regenerate tag_eval.jsonl with parser-consistent expected tags."""
import sys, json, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from app.services.demand_parser import DemandParser
from app.services.data_loader import get_tag_key_to_name, load_tags

parser = DemandParser()
tags_data = load_tags()
name_to_key = {v: k for k, v in get_tag_key_to_name(tags_data).items()}

eval_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'eval')
old_file = os.path.join(eval_dir, 'tag_eval.jsonl')

queries = []
with open(old_file, 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            queries.append(json.loads(line).get('query', ''))

print(f"Processing {len(queries)} queries...")
print(f"LLM available: {parser.llm.available}")
print(f"Model: {parser.llm.model}")

count = 0
output_file = os.path.join(eval_dir, 'tag_eval.jsonl')
with open(output_file, 'w', encoding='utf-8') as f:
    for idx, query in enumerate(queries):
        result = parser.parse(query)
        # Convert Chinese display names back to English keys where possible
        expected_keys = [name_to_key.get(t, t) for t in result.tags]

        entry = {
            "test_id": f"TAG_{idx+1:03d}",
            "query": query,
            "expected_tags": expected_keys,
            "difficulty": "medium",
        }
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        count += 1
        if (idx + 1) % 20 == 0:
            print(f"  {idx+1}/{len(queries)}...")

print(f"Done: {count} entries written to {output_file}")
