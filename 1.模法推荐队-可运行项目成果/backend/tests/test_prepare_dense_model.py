"""Tests for the offline dense-model artifact preparation helpers."""

import hashlib
import json
from pathlib import Path
import sys

import pytest


BACKEND_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(BACKEND_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_SCRIPTS_DIR))

import prepare_dense_model as preparer  # noqa: E402


def test_manifest_validation_accepts_exact_local_artifact(tmp_path):
    model_dir = tmp_path / "bge-m3"
    model_dir.mkdir()
    artifact = model_dir / "config.json"
    artifact.write_text('{"hidden_size": 1024}\n', encoding="utf-8")
    manifest = tmp_path / "bge-m3.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "config.json",
                        "size": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert preparer._manifest_valid(model_dir, manifest) is True


def test_manifest_validation_rejects_modified_artifact(tmp_path):
    model_dir = tmp_path / "bge-m3"
    model_dir.mkdir()
    artifact = model_dir / "config.json"
    artifact.write_text("original", encoding="utf-8")
    manifest = tmp_path / "bge-m3.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "config.json",
                        "size": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    artifact.write_text("tampered", encoding="utf-8")

    assert preparer._manifest_valid(model_dir, manifest) is False


def test_manifest_validation_rejects_parent_path(tmp_path):
    model_dir = tmp_path / "bge-m3"
    model_dir.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    manifest = tmp_path / "bge-m3.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "../outside.bin",
                        "size": outside.stat().st_size,
                        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert preparer._manifest_valid(model_dir, manifest) is False


def test_prepare_rejects_reusing_a_different_pinned_revision(tmp_path):
    model_dir = tmp_path / "bge-m3"
    model_dir.mkdir()
    artifact = model_dir / "config.json"
    artifact.write_text("model", encoding="utf-8")
    manifest = tmp_path / "bge-m3.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_id": "BAAI/bge-m3",
                "resolved_revision": "b" * 40,
                "embedding_dimension": 1024,
                "files": [
                    {
                        "path": "config.json",
                        "size": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="requested revision"):
        preparer.prepare(
            repo_id="BAAI/bge-m3",
            revision="a" * 40,
            output_dir=model_dir,
            manifest_path=manifest,
            expected_dimension=1024,
            force=False,
        )
