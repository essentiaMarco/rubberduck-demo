"""API routes for financial intelligence."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session

from rubberduck.db.models import FinancialTransaction, File as FileModel
from rubberduck.db.sqlite import get_db
from rubberduck.financial import service as fin_service
from rubberduck.financial.parser import parse_csv_statement

router = APIRouter(prefix="/api/financial", tags=["financial"])


@router.get("/transactions")
def list_transactions(
    transaction_type: str | None = Query(None),
    category: str | None = Query(None),
    anomaly_only: bool = Query(False),
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
    sort_by: str | None = Query("date"),
    sort_dir: str | None = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List financial transactions with filters."""
    q = db.query(FinancialTransaction)
    if transaction_type:
        q = q.filter(FinancialTransaction.transaction_type == transaction_type)
    if category:
        q = q.filter(FinancialTransaction.category == category)
    if anomaly_only:
        q = q.filter(FinancialTransaction.is_anomaly == True)
    if date_start:
        q = q.filter(FinancialTransaction.transaction_date >= date_start)
    if date_end:
        q = q.filter(FinancialTransaction.transaction_date <= date_end)

    total = q.count()

    sort_map = {"amount": FinancialTransaction.amount, "anomaly_score": FinancialTransaction.anomaly_score}
    order_col = sort_map.get(sort_by, FinancialTransaction.transaction_date)
    if sort_dir == "asc":
        q = q.order_by(order_col.asc().nullslast())
    else:
        q = q.order_by(order_col.desc().nullslast())

    txs = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [_tx_dict(t) for t in txs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Financial summary statistics."""
    return fin_service.get_stats(db)


@router.get("/flow")
def get_flow(db: Session = Depends(get_db)):
    """Sankey diagram data — account-to-account money flow."""
    return fin_service.get_flow_data(db)


@router.get("/anomalies")
def get_anomalies(
    min_score: float = Query(0.1),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List anomalous transactions."""
    q = (
        db.query(FinancialTransaction)
        .filter(FinancialTransaction.is_anomaly == True, FinancialTransaction.anomaly_score >= min_score)
        .order_by(FinancialTransaction.anomaly_score.desc())
    )
    total = q.count()
    txs = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_tx_dict(t) for t in txs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/import")
def import_csv(
    file_path: str = Query(..., description="Path to CSV bank statement"),
    account_name: str = Query("", description="Account label for these transactions"),
    db: Session = Depends(get_db),
):
    """Import transactions from a CSV bank statement file."""
    from rubberduck.config import settings

    resolved = Path(file_path).resolve()
    allowed_bases = (
        [Path(p).resolve() for p in settings.allowed_ingest_paths]
        if settings.allowed_ingest_paths
        else [settings.data_dir.resolve()]
    )
    if not any(resolved == base or resolved.is_relative_to(base) for base in allowed_bases):
        raise HTTPException(status_code=403, detail="File is outside allowed paths")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    result = parse_csv_statement(resolved)

    created = 0
    for tx_data in result.get("transactions", []):
        tx = FinancialTransaction(
            transaction_date=tx_data.get("transaction_date"),
            transaction_date_raw=tx_data.get("transaction_date_raw"),
            from_account=account_name or None,
            amount=tx_data["amount"],
            transaction_type=tx_data.get("transaction_type"),
            category=tx_data.get("category"),
            description=tx_data.get("description"),
            reference_number=tx_data.get("reference_number"),
            balance_after=tx_data.get("balance_after"),
        )
        db.add(tx)
        created += 1

    db.commit()

    return {
        "imported": created,
        "total_rows": result.get("row_count", 0),
        "warnings": result.get("warnings", []),
    }


@router.post("/detect-anomalies")
def run_anomaly_detection(db: Session = Depends(get_db)):
    """Run anomaly detection across all financial transactions."""
    return fin_service.detect_anomalies(db)


def _tx_dict(tx: FinancialTransaction) -> dict:
    return {
        "id": tx.id,
        "transaction_date": str(tx.transaction_date) if tx.transaction_date else None,
        "from_account": tx.from_account,
        "to_account": tx.to_account,
        "amount": tx.amount,
        "currency": tx.currency,
        "transaction_type": tx.transaction_type,
        "category": tx.category,
        "description": tx.description,
        "reference_number": tx.reference_number,
        "balance_after": tx.balance_after,
        "is_anomaly": tx.is_anomaly,
        "anomaly_score": tx.anomaly_score,
        "anomaly_reasons": json.loads(tx.anomaly_reasons) if tx.anomaly_reasons else [],
    }
