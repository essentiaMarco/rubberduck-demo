"""Immutable content-addressable file store.

Files are stored at: originals/{source_id}/{sha256[:4]}/{sha256}.{ext}
Write-once: if the path already exists and hash matches, skip write.
Original files are NEVER modified or deleted.
"""

import shutil
from pathlib import Path

from rubberduck.config import settings


def store_original(
    source_path: Path,
    source_id: str,
    sha256: str,
    file_ext: str,
) -> Path:
    """Copy a file into the immutable store. Returns the stored path.

    Content-addressable: identical files share the same path.
    """
    ext = file_ext.lstrip(".") if file_ext else "bin"
    dest_dir = settings.originals_dir / source_id / sha256[:4]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{sha256}.{ext}"

    if dest_path.exists():
        # Content-addressable: same hash = same file = skip
        return dest_path

    # Copy, not move — preserve the source
    shutil.copy2(source_path, dest_path)
    # Make read-only to enforce immutability
    dest_path.chmod(0o444)
    return dest_path


def get_original_path(source_id: str, sha256: str, file_ext: str) -> Path:
    """Resolve the stored path for a known file."""
    ext = file_ext.lstrip(".") if file_ext else "bin"
    return settings.originals_dir / source_id / sha256[:4] / f"{sha256}.{ext}"


def ensure_parsed_dir(file_id: str) -> Path:
    """Create and return the parsed output directory for a file."""
    parsed_dir = settings.parsed_dir / file_id
    parsed_dir.mkdir(parents=True, exist_ok=True)
    return parsed_dir
