#!/usr/bin/env python3
"""
run_eval_snapshot.py - 评测运行快照脚本

Runs the full evaluation suite and saves a timestamped snapshot
to reports/runs/ for baseline comparison.

Usage:
    python scripts/run_eval_snapshot.py
    python scripts/run_eval_snapshot.py --no-eval  (skip eval, just copy + analyze)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Run evaluation and create timestamped snapshot')
    parser.add_argument('--no-eval', action='store_true',
                        help='Skip running evaluation, just snapshot existing results')
    parser.add_argument('--snapshot-dir', default=None,
                        help='Snapshot output directory (default: reports/runs/TIMESTAMP)')
    args = parser.parse_args()

    # 1. Resolve project root and create snapshot directory
    base_dir = Path(__file__).resolve().parent.parent
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if args.snapshot_dir:
        snapshot_dir = Path(args.snapshot_dir)
    else:
        snapshot_dir = base_dir / "reports" / "runs" / timestamp

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    print(f"Snapshot directory created: {snapshot_dir}")

    # 2. Run eval if not --no-eval
    if not args.no_eval:
        print("\n>>> Running evaluation suite...")
        run_eval_script = base_dir / "scripts" / "run_eval.py"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(base_dir / "backend")

        result = subprocess.run(
            [sys.executable, str(run_eval_script), "--all"],
            cwd=str(base_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"[WARN] run_eval.py exited with code {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
    else:
        print("\n>>> Skipping evaluation (--no-eval)")

    # 3. Copy results from reports/examples/ to snapshot
    reports_examples = base_dir / "reports" / "examples"
    print("\n>>> Copying results to snapshot...")
    for fname in ["eval_results.json", "topk_failures.json"]:
        src = reports_examples / fname
        if src.exists():
            shutil.copy2(src, snapshot_dir / fname)
            print(f"  Copied: {fname}")
        else:
            print(f"  [WARN] {fname} not found at {src}, skipping")

    # 4. Run analyze_eval_failures.py on snapshotted data
    analyze_script = base_dir / "scripts" / "analyze_eval_failures.py"
    if analyze_script.exists():
        print("\n>>> Running failure analysis...")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(base_dir / "backend")
        result = subprocess.run(
            [sys.executable, str(analyze_script),
             "--eval-results", str(snapshot_dir / "eval_results.json"),
             "--topk-failures", str(snapshot_dir / "topk_failures.json"),
             "--out-dir", str(snapshot_dir)],
            cwd=str(base_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"[WARN] analyze_eval_failures.py exited with code {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
    else:
        print(f"\n  [WARN] analyze_eval_failures.py not found at {analyze_script}, skipping analysis")

    # 5. Print final snapshot path and contents
    print("\n" + "=" * 60)
    print(f"Snapshot saved to: {snapshot_dir}")
    print("=" * 60)
    print("Files:")
    for f in sorted(snapshot_dir.glob("*")):
        size = f.stat().st_size if f.is_file() else 0
        if f.is_file():
            print(f"  {f.name:40s} {size:>8,} bytes")
        else:
            print(f"  {f.name:40s}       <dir>")
    print()


if __name__ == "__main__":
    main()
