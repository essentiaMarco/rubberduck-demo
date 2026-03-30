"""Streaming file hasher — never loads entire file into memory."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from rubberduck.config import settings


@dataclass
class HashResult:
    sha256: str
    md5: str
    size_bytes: int


def hash_file(file_path: Path, chunk_size: int | None = None) -> HashResult:
    """Compute SHA-256 and MD5 of a file using streaming 64KB chunks.

    Never loads the entire file into memory.
    """
    chunk_size = chunk_size or settings.hash_chunk_size
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    size = 0

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
            md5.update(chunk)
            size += len(chunk)

    return HashResult(
        sha256=sha256.hexdigest(),
        md5=md5.hexdigest(),
        size_bytes=size,
    )


def hash_bytes(data: bytes) -> HashResult:
    """Hash in-memory bytes (for small extracted content)."""
    return HashResult(
        sha256=hashlib.sha256(data).hexdigest(),
        md5=hashlib.md5(data).hexdigest(),
        size_bytes=len(data),
    )
