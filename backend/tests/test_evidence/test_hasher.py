"""Tests for the streaming file hasher."""

from rubberduck.evidence.hasher import hash_file, hash_bytes


def test_hash_file(sample_text_file):
    result = hash_file(sample_text_file)
    assert result.sha256
    assert result.md5
    assert len(result.sha256) == 64  # SHA-256 hex
    assert len(result.md5) == 32  # MD5 hex
    assert result.size_bytes > 0


def test_hash_bytes():
    data = b"Hello, world!"
    result = hash_bytes(data)
    assert result.sha256
    assert result.md5
    assert result.size_bytes == len(data)


def test_hash_deterministic(sample_text_file):
    r1 = hash_file(sample_text_file)
    r2 = hash_file(sample_text_file)
    assert r1.sha256 == r2.sha256
    assert r1.md5 == r2.md5


def test_hash_different_files(tmp_dir):
    f1 = tmp_dir / "a.txt"
    f2 = tmp_dir / "b.txt"
    f1.write_text("file one")
    f2.write_text("file two")

    r1 = hash_file(f1)
    r2 = hash_file(f2)
    assert r1.sha256 != r2.sha256
