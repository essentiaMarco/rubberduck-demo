"""Product context ingestion and retrieval for RubberDuck documents."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

CONTEXT_DIR = Path("data/context")
CHUNK_SIZE = 2000  # characters per chunk


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks at paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_size = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if current_size + len(para) > chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_size = len(para)
        else:
            current_chunk.append(para)
            current_size += len(para)

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def _read_file(path: str | Path) -> str:
    """Read a file as text. For PDFs, extracts text if possible."""
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() == ".pdf":
        # Try pdfminer.six if available
        try:
            from pdfminer.high_level import extract_text
            return extract_text(str(path))
        except ImportError:
            pass
        # Fallback: try subprocess with pdftotext (path resolved above)
        import subprocess
        result = subprocess.run(
            ["pdftotext", "--", str(path), "-"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
        raise RuntimeError(
            f"Cannot read PDF {path}. Install pdfminer.six or pdftotext."
        )
    return path.read_text(encoding="utf-8")


def ingest_document(
    file_path: str | Path,
    doc_type: str,
    output_dir: str | Path | None = None,
) -> dict:
    """Ingest a product context document, chunk it, and store in data/context/.

    Args:
        file_path: Path to the document file (text, markdown, or PDF).
        doc_type: One of whitepaper, competitive, kpi, roadmap, changelog.
        output_dir: Override output directory (default: data/context/).

    Returns:
        Dict with ingestion metadata.
    """
    file_path = Path(file_path)
    out_dir = Path(output_dir) if output_dir else CONTEXT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading {file_path}...", file=sys.stderr)
    text = _read_file(file_path)

    print("Chunking document...", file=sys.stderr)
    chunks = _chunk_text(text)

    # Create a stable ID from the file
    file_hash = hashlib.md5(file_path.name.encode() + doc_type.encode()).hexdigest()[:8]

    # Store each chunk with metadata
    chunk_files: list[str] = []
    for i, chunk in enumerate(chunks):
        chunk_data = {
            "type": doc_type,
            "source_file": file_path.name,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "date_ingested": str(date.today()),
            "text": chunk,
        }
        chunk_path = out_dir / f"{doc_type}_{file_hash}_{i:03d}.json"
        chunk_path.write_text(json.dumps(chunk_data, indent=2), encoding="utf-8")
        chunk_files.append(str(chunk_path))

    result = {
        "doc_type": doc_type,
        "source_file": str(file_path),
        "chunk_count": len(chunks),
        "chunk_files": chunk_files,
        "total_characters": len(text),
    }

    print(f"Ingested {len(chunks)} chunks from {file_path.name}", file=sys.stderr)
    return result


def load_context(
    doc_type: str | None = None,
    context_dir: str | Path | None = None,
) -> list[dict]:
    """Load ingested context chunks, optionally filtered by type.

    Returns a list of chunk dicts with 'type', 'text', and metadata.
    """
    ctx_dir = Path(context_dir) if context_dir else CONTEXT_DIR
    if not ctx_dir.exists():
        return []

    chunks: list[dict] = []
    for f in sorted(ctx_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if doc_type is None or data.get("type") == doc_type:
                chunks.append(data)
        except (json.JSONDecodeError, KeyError):
            continue

    return chunks


def search_context(query: str, doc_type: str | None = None) -> list[dict]:
    """Simple keyword search across ingested context chunks."""
    query_lower = query.lower()
    results: list[dict] = []
    for chunk in load_context(doc_type):
        text = chunk.get("text", "")
        if query_lower in text.lower():
            results.append(chunk)
    return results
