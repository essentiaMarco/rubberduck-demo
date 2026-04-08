"""Routes for product context document management."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fastapi.responses import JSONResponse

from rubberduck_analyzer.context.product_context import ingest_document, load_context, delete_context

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

UPLOAD_DIR = Path("data/uploads")


@router.get("/", response_class=HTMLResponse)
async def context_page(request: Request):
    """Show ingested context documents."""
    chunks = load_context()

    # Group chunks by type and source
    docs: dict[str, dict] = {}
    for chunk in chunks:
        key = f"{chunk.get('type', 'unknown')}:{chunk.get('source_file', 'unknown')}"
        if key not in docs:
            docs[key] = {
                "type": chunk.get("type"),
                "source": chunk.get("source_file"),
                "date": chunk.get("date_ingested"),
                "chunks": 0,
            }
        docs[key]["chunks"] += 1

    return templates.TemplateResponse(request, "context.html", {
        "documents": list(docs.values()),
    })


@router.post("/ingest")
async def ingest(
    request: Request,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
):
    """Ingest a new product context document."""
    # Save upload
    upload_dir = UPLOAD_DIR / "context"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / (file.filename or "document.txt")
    content = await file.read()
    dest.write_bytes(content)

    result = ingest_document(file_path=str(dest), doc_type=doc_type)

    return templates.TemplateResponse(request, "_context_ingested.html", {
        "result": result,
    })


@router.delete("/{doc_type}/{source_file}")
async def delete_context_endpoint(doc_type: str, source_file: str):
    """Delete all ingested chunks for a source file."""
    # Sanitize: source_file should not contain path separators
    if "/" in source_file or "\\" in source_file or ".." in source_file:
        return JSONResponse({"error": "invalid source file name"}, status_code=400)
    count = delete_context(source_file, doc_type)
    if count == 0:
        return JSONResponse({"error": "no chunks found"}, status_code=404)
    return JSONResponse({"deleted_chunks": count, "source_file": source_file, "doc_type": doc_type})
