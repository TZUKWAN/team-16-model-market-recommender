"""Create a Unicode-safe Zip64 delivery archive."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import zipfile


ROOT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def create_archive(
    *,
    source_dir: Path,
    archive_path: Path,
    root_name: str,
    compresslevel: int = 6,
) -> dict[str, object]:
    """Create a deflated Zip64 archive with one explicit root directory."""
    source_dir = source_dir.resolve()
    archive_path = archive_path.resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"source directory does not exist: {source_dir}")
    if not ROOT_NAME_PATTERN.fullmatch(root_name) or root_name in {".", ".."}:
        raise ValueError("root name must be one safe ASCII path component")
    if not 0 <= compresslevel <= 9:
        raise ValueError("compresslevel must be between 0 and 9")
    try:
        archive_path.relative_to(source_dir)
    except ValueError:
        pass
    else:
        raise ValueError("archive path must be outside the source directory")

    files = sorted(
        (path for path in source_dir.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(source_dir).as_posix(),
    )
    symlinks = [path for path in files if path.is_symlink()]
    if symlinks:
        names = ", ".join(path.relative_to(source_dir).as_posix() for path in symlinks)
        raise ValueError(f"symbolic links are not allowed in the delivery archive: {names}")

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = archive_path.with_suffix(archive_path.suffix + ".partial")
    partial_path.unlink(missing_ok=True)
    total_bytes = sum(path.stat().st_size for path in files)

    try:
        with zipfile.ZipFile(
            partial_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=compresslevel,
            allowZip64=True,
            strict_timestamps=False,
        ) as archive:
            for path in files:
                relative = path.relative_to(source_dir).as_posix()
                archive.write(path, arcname=f"{root_name}/{relative}")

        with zipfile.ZipFile(partial_path, mode="r", allowZip64=True) as archive:
            corrupt_entry = archive.testzip()
            if corrupt_entry is not None:
                raise RuntimeError(f"archive CRC verification failed: {corrupt_entry}")
            entry_count = len(archive.infolist())
        os.replace(partial_path, archive_path)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise

    return {
        "status": "created",
        "archive": str(archive_path),
        "entry_count": entry_count,
        "source_file_count": len(files),
        "source_total_bytes": total_bytes,
        "archive_bytes": archive_path.stat().st_size,
        "root_name": root_name,
        "zip64_enabled": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--root-name", required=True)
    parser.add_argument("--compresslevel", type=int, default=6)
    args = parser.parse_args()

    result = create_archive(
        source_dir=args.source_dir,
        archive_path=args.archive,
        root_name=args.root_name,
        compresslevel=args.compresslevel,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
