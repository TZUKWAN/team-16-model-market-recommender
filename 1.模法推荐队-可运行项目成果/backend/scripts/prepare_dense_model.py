"""Prepare a pinned, checksum-manifested SentenceTransformer model artifact."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import shutil
from typing import Any

REPO_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
IGNORED_PATTERNS = [
    "*.onnx",
    "onnx/*",
    "openvino/*",
    "*.msgpack",
    "*.h5",
    "*.ot",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".cache" not in path.relative_to(root).parts
    ]


def _manifest_valid(model_dir: Path, manifest_path: Path) -> bool:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) != 1:
            return False
        for item in payload.get("files", []):
            relative = Path(str(item["path"]))
            if relative.is_absolute() or ".." in relative.parts:
                return False
            path = (model_dir / relative).resolve()
            if not path.is_relative_to(model_dir.resolve()) or not path.is_file():
                return False
            if path.stat().st_size != int(item["size"]) or _sha256(path) != item["sha256"]:
                return False
        return bool(payload.get("files"))
    except Exception:
        return False


def prepare(
    *,
    repo_id: str,
    revision: str,
    output_dir: Path,
    manifest_path: Path,
    expected_dimension: int,
    force: bool,
) -> dict[str, Any]:
    if not REPO_ID_PATTERN.fullmatch(repo_id):
        raise ValueError("model repo id must use the owner/name form")
    output_dir = output_dir.resolve()
    manifest_path = manifest_path.resolve()
    if output_dir.exists() and manifest_path.is_file() and not force:
        if not _manifest_valid(output_dir, manifest_path):
            raise RuntimeError("existing dense model artifact failed manifest verification")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(payload.get("model_id") or "") != repo_id:
            raise RuntimeError("existing dense model artifact belongs to a different model id")
        if re.fullmatch(r"[0-9a-fA-F]{40}", revision) and (
            str(payload.get("resolved_revision") or "").lower() != revision.lower()
        ):
            raise RuntimeError(
                "existing dense model artifact does not match the requested revision; "
                "rerun with --force to replace it"
            )
        return {"status": "reused", **payload}

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.with_name(f".{output_dir.name}.staging")
    if staging.exists() and output_dir.exists():
        if not force:
            raise RuntimeError(f"staging and output directories both exist: {staging}")
        shutil.rmtree(staging)
    if output_dir.exists() and not force:
        raise RuntimeError(f"output directory already exists without a valid manifest: {output_dir}")

    from huggingface_hub import HfApi, snapshot_download
    from sentence_transformers import SentenceTransformer

    resolved_revision = str(HfApi().model_info(repo_id, revision=revision).sha)
    snapshot_download(
        repo_id=repo_id,
        revision=resolved_revision,
        local_dir=staging,
        ignore_patterns=IGNORED_PATTERNS,
    )
    metadata_cache = staging / ".cache"
    if metadata_cache.exists():
        shutil.rmtree(metadata_cache)

    encoder = SentenceTransformer(str(staging), local_files_only=True)
    probe = encoder.encode(["模型市场语义检索制品验收"], normalize_embeddings=True)
    dimension = int(probe.shape[1])
    if dimension != expected_dimension:
        raise RuntimeError(
            f"embedding dimension {dimension} does not match expected {expected_dimension}"
        )

    manifest = {
        "schema_version": 1,
        "model_id": repo_id,
        "resolved_revision": resolved_revision,
        "embedding_dimension": dimension,
        "sentence_transformers_version": version("sentence-transformers"),
        "torch_version": version("torch"),
        "files": _files(staging),
    }
    if output_dir.exists():
        shutil.rmtree(output_dir)
    # Directory replacement is denied by Docker Desktop on some Windows bind
    # mounts. Copying the already verified staging tree is portable; the final
    # manifest is still written last, so an interrupted copy cannot be accepted.
    shutil.copytree(staging, output_dir)
    shutil.rmtree(staging)
    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_manifest.replace(manifest_path)
    return {"status": "prepared", **manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default="BAAI/bge-m3")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-dimension", type=int, default=1024)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = prepare(
        repo_id=args.repo_id,
        revision=args.revision,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        expected_dimension=args.expected_dimension,
        force=args.force,
    )
    summary = {key: value for key, value in result.items() if key != "files"}
    summary["file_count"] = len(result.get("files", []))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
