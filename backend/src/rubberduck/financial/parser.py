"""Bank statement parser — CSV and PDF transaction extraction.

Detects common bank statement formats by header patterns and extracts
individual transactions with date, amount, description, and balance.
"""

import csv
import io
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Column name patterns for auto-detection (case-insensitive)
_DATE_COLS = {"date", "transaction date", "trans date", "posting date", "value date", "txn date"}
_DESC_COLS = {"description", "details", "particulars", "narration", "transaction description", "memo", "payee"}
_AMOUNT_COLS = {"amount", "transaction amount", "txn amount"}
_DEBIT_COLS = {"debit", "withdrawal", "debit amount", "withdrawals"}
_CREDIT_COLS = {"credit", "deposit", "credit amount", "deposits"}
_BALANCE_COLS = {"balance", "running balance", "closing balance", "available balance"}
_REF_COLS = {"reference", "ref", "reference number", "check number", "cheque no"}


def _match_col(header: str, candidates: set[str]) -> bool:
    return header.strip().lower() in candidates


def _parse_amount(value: str | None) -> float | None:
    if not value or not value.strip():
        return None
    cleaned = re.sub(r"[,$\s]", "", value.strip())
    cleaned = cleaned.replace("(", "-").replace(")", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    text = value.strip()
    formats = [
        "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y",
        "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y",
        "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
        "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S",
        "%d/%m/%y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_csv_statement(file_path: Path) -> dict[str, Any]:
    """Parse a bank statement CSV file.

    Returns dict with keys: transactions (list of dicts), account_info (dict),
    warnings (list of str).
    """
    import chardet

    raw = file_path.read_bytes()
    detected = chardet.detect(raw[:10000])
    encoding = detected.get("encoding", "utf-8") or "utf-8"
    text = raw.decode(encoding, errors="replace")

    # Detect delimiter
    try:
        dialect = csv.Sniffer().sniff(text[:4096])
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if len(rows) < 2:
        return {"transactions": [], "warnings": ["File has fewer than 2 rows"]}

    headers = [h.strip() for h in rows[0]]
    headers_lower = [h.lower() for h in headers]

    # Map columns
    col_map: dict[str, int | None] = {
        "date": None, "description": None, "amount": None,
        "debit": None, "credit": None, "balance": None, "reference": None,
    }
    for i, h in enumerate(headers_lower):
        if h in _DATE_COLS:
            col_map["date"] = i
        elif h in _DESC_COLS:
            col_map["description"] = i
        elif h in _AMOUNT_COLS:
            col_map["amount"] = i
        elif h in _DEBIT_COLS:
            col_map["debit"] = i
        elif h in _CREDIT_COLS:
            col_map["credit"] = i
        elif h in _BALANCE_COLS:
            col_map["balance"] = i
        elif h in _REF_COLS:
            col_map["reference"] = i

    if col_map["date"] is None:
        return {"transactions": [], "warnings": ["Could not identify date column"]}

    transactions: list[dict[str, Any]] = []
    warnings: list[str] = []

    for row_idx, row in enumerate(rows[1:], start=2):
        if not row or all(not cell.strip() for cell in row):
            continue

        try:
            date_str = row[col_map["date"]] if col_map["date"] is not None and col_map["date"] < len(row) else None
            date = _parse_date(date_str)

            desc = row[col_map["description"]] if col_map["description"] is not None and col_map["description"] < len(row) else ""

            # Determine amount
            amount = None
            tx_type = "unknown"
            if col_map["amount"] is not None and col_map["amount"] < len(row):
                amount = _parse_amount(row[col_map["amount"]])
                if amount is not None:
                    tx_type = "credit" if amount > 0 else "debit"
            elif col_map["debit"] is not None or col_map["credit"] is not None:
                debit = _parse_amount(row[col_map["debit"]]) if col_map["debit"] is not None and col_map["debit"] < len(row) else None
                credit = _parse_amount(row[col_map["credit"]]) if col_map["credit"] is not None and col_map["credit"] < len(row) else None
                if debit and debit > 0:
                    amount = -debit
                    tx_type = "debit"
                elif credit and credit > 0:
                    amount = credit
                    tx_type = "credit"

            if amount is None:
                continue

            balance = _parse_amount(row[col_map["balance"]]) if col_map["balance"] is not None and col_map["balance"] < len(row) else None
            ref = row[col_map["reference"]].strip() if col_map["reference"] is not None and col_map["reference"] < len(row) else None

            transactions.append({
                "transaction_date": date,
                "transaction_date_raw": date_str,
                "description": desc.strip(),
                "amount": amount,
                "transaction_type": tx_type,
                "balance_after": balance,
                "reference_number": ref,
                "category": _categorize(desc),
            })

        except (IndexError, ValueError) as e:
            warnings.append(f"Row {row_idx}: parse error: {e}")

    return {
        "transactions": transactions,
        "headers": headers,
        "row_count": len(rows) - 1,
        "parsed_count": len(transactions),
        "warnings": warnings,
    }


def _categorize(description: str) -> str:
    """Auto-categorize a transaction by description keywords."""
    desc = description.lower()
    if any(kw in desc for kw in ("salary", "payroll", "wages", "direct deposit")):
        return "salary"
    if any(kw in desc for kw in ("rent", "mortgage", "lease")):
        return "rent"
    if any(kw in desc for kw in ("transfer", "xfer", "wire", "ach")):
        return "transfer"
    if any(kw in desc for kw in ("atm", "cash", "withdrawal")):
        return "cash"
    if any(kw in desc for kw in ("bitcoin", "btc", "ethereum", "eth", "crypto", "coinbase", "binance")):
        return "crypto"
    if any(kw in desc for kw in ("insurance", "premium")):
        return "insurance"
    if any(kw in desc for kw in ("utility", "electric", "gas", "water", "phone", "internet")):
        return "utilities"
    if any(kw in desc for kw in ("grocery", "supermarket", "food", "restaurant", "dining")):
        return "food"
    if any(kw in desc for kw in ("amazon", "walmart", "target", "purchase", "pos")):
        return "purchase"
    return "unknown"
