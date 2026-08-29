#!/usr/bin/env python3
"""Compatibility wrapper for explanation evaluation.

This keeps the historical entry point working while the unified evaluation
suite lives in scripts/run_eval.py.
"""

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_eval import main


if __name__ == '__main__':
    main()
