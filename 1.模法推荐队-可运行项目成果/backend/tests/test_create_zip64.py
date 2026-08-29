"""Tests for the Unicode-safe Zip64 delivery archiver."""

from __future__ import annotations

from pathlib import Path
import sys
import zipfile


SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from create_zip64 import create_archive  # noqa: E402


def test_create_archive_preserves_unicode_paths_and_content(tmp_path: Path) -> None:
    source = tmp_path / "source"
    unicode_file = source / "data" / "raw" / "官方数据集_数据.xlsx"
    unicode_file.parent.mkdir(parents=True)
    unicode_file.write_bytes(b"official-dataset")
    (source / "README.md").write_text("delivery", encoding="utf-8")
    archive_path = tmp_path / "delivery.zip"

    result = create_archive(
        source_dir=source,
        archive_path=archive_path,
        root_name="team-16-competition",
    )

    assert result["status"] == "created"
    assert result["source_file_count"] == 2
    with zipfile.ZipFile(archive_path) as archive:
        unicode_name = "team-16-competition/data/raw/官方数据集_数据.xlsx"
        assert archive.namelist() == [
            "team-16-competition/README.md",
            unicode_name,
        ]
        assert archive.read(unicode_name) == b"official-dataset"
        unicode_entry = archive.getinfo(unicode_name)
        assert unicode_entry.flag_bits & 0x800
        assert archive.testzip() is None
