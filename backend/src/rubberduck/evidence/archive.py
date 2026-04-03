"""Recursive archive extractor with depth limits and path traversal protection."""

import logging
import tarfile
import tempfile
import zipfile
from pathlib import Path

from rubberduck.config import settings

logger = logging.getLogger(__name__)

ARCHIVE_EXTENSIONS = {".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".gz"}


def is_archive(file_path: Path) -> bool:
    """Check if a file is a supported archive format."""
    name = file_path.name.lower()
    if name.endswith(".tar.gz") or name.endswith(".tar.bz2"):
        return True
    return file_path.suffix.lower() in ARCHIVE_EXTENSIONS


def _is_safe_path(member_path: str) -> bool:
    """Reject path traversal attempts."""
    from pathlib import PurePosixPath

    p = PurePosixPath(member_path)
    # Reject absolute paths and parent directory references
    if p.is_absolute() or ".." in p.parts:
        return False
    return True


def extract_archive(
    archive_path: Path,
    dest_dir: Path | None = None,
    depth: int = 0,
) -> list[Path]:
    """Extract archive members one at a time. Returns list of extracted file paths.

    Supports ZIP, TAR, TAR.GZ, TAR.BZ2. Recurses into nested archives
    up to MAX_ARCHIVE_DEPTH.
    """
    if depth >= settings.max_archive_depth:
        logger.warning(f"Max archive depth {settings.max_archive_depth} reached for {archive_path}")
        return []

    if dest_dir is None:
        dest_dir = Path(tempfile.mkdtemp(prefix="rubberduck_extract_"))

    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    name_lower = archive_path.name.lower()

    try:
        if name_lower.endswith(".zip"):
            extracted = _extract_zip(archive_path, dest_dir)
        elif name_lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2")):
            extracted = _extract_tar(archive_path, dest_dir)
        elif name_lower.endswith(".gz") and not name_lower.endswith(".tar.gz"):
            extracted = _extract_gzip(archive_path, dest_dir)
        else:
            logger.warning(f"Unsupported archive format: {archive_path}")
            return []
    except Exception as e:
        logger.error(f"Failed to extract {archive_path}: {e}")
        return []

    # Recurse into nested archives
    nested_extracted = []
    for fpath in extracted:
        if is_archive(fpath):
            nested = extract_archive(fpath, fpath.parent / f"{fpath.stem}_contents", depth + 1)
            nested_extracted.extend(nested)

    extracted.extend(nested_extracted)
    return extracted


def _extract_zip(archive_path: Path, dest_dir: Path) -> list[Path]:
    """Extract ZIP members one at a time."""
    extracted = []
    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if not _is_safe_path(info.filename):
                logger.warning(f"Skipping unsafe path in ZIP: {info.filename}")
                continue
            out_path = dest_dir / info.filename
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(out_path, "wb") as dst:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    dst.write(chunk)
            extracted.append(out_path)
    return extracted


def _extract_tar(archive_path: Path, dest_dir: Path) -> list[Path]:
    """Extract TAR/TAR.GZ/TAR.BZ2 members one at a time."""
    extracted = []
    with tarfile.open(archive_path, "r:*") as tf:
        for member in tf:
            if not member.isfile():
                continue
            if not _is_safe_path(member.name):
                logger.warning(f"Skipping unsafe path in TAR: {member.name}")
                continue
            out_path = dest_dir / member.name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with tf.extractfile(member) as src, open(out_path, "wb") as dst:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    dst.write(chunk)
            extracted.append(out_path)
    return extracted


def _extract_gzip(archive_path: Path, dest_dir: Path) -> list[Path]:
    """Extract a standalone .gz file."""
    import gzip

    out_name = archive_path.stem  # remove .gz
    out_path = dest_dir / out_name
    with gzip.open(archive_path, "rb") as src, open(out_path, "wb") as dst:
        while True:
            chunk = src.read(65536)
            if not chunk:
                break
            dst.write(chunk)
    return [out_path]
