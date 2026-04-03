"""Tests for archive extraction."""

import zipfile
from pathlib import Path

from rubberduck.evidence.archive import extract_archive, is_archive


def test_is_archive(tmp_dir):
    zip_file = tmp_dir / "test.zip"
    zip_file.touch()
    assert is_archive(zip_file)

    txt_file = tmp_dir / "test.txt"
    txt_file.touch()
    assert not is_archive(txt_file)

    tar_gz = tmp_dir / "test.tar.gz"
    tar_gz.touch()
    assert is_archive(tar_gz)


def test_extract_zip(tmp_dir):
    # Create a test ZIP
    zip_path = tmp_dir / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("file1.txt", "Hello from file 1")
        zf.writestr("subdir/file2.txt", "Hello from file 2")

    dest = tmp_dir / "extracted"
    files = extract_archive(zip_path, dest)

    assert len(files) == 2
    assert any("file1.txt" in str(f) for f in files)
    assert any("file2.txt" in str(f) for f in files)

    # Verify content
    for f in files:
        assert f.exists()
        assert f.stat().st_size > 0
