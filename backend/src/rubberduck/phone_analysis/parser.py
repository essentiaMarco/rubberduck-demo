"""Vodafone India phone bill PDF parser.

Extracts Call Detail Records (CDRs) from Vodafone postpaid bills.
Handles the specific layout: page 1 = bill summary, page 3 = usage summary,
pages 4+ = itemized calls in two-column format.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)

# ── Regex patterns for CDR extraction ──────────────────────

# Call record: DD/MM/YY-HH:MM:SS  #PhoneNumber  Min:Sec  Charge**
_CALL_RE = re.compile(
    r"(\d{2}/\d{2}/\d{2})-(\d{2}:\d{2}:\d{2})\s+"   # date-time
    r"(#?\d[\d\s]*?\d)\s+"                               # phone number (may have # prefix)
    r"(\d+:\d{2})\s+"                                     # duration Min:Sec
    r"(\d+\.?\d*)\*?\*?"                                   # charges (with optional **)
)

# SMS record: DD/MM/YY-HH:MM:SS  #PhoneNumber  Count  Charge
_SMS_RE = re.compile(
    r"(\d{2}/\d{2}/\d{2})-(\d{2}:\d{2}:\d{2})\s+"
    r"(#?\d[\d\s]*?\d)\s+"
    r"(\d+)\s+"                                            # count (1 for single SMS)
    r"(\d+\.?\d*)\*?\*?"
)

# Bill metadata patterns
_BILL_NO_RE = re.compile(r"BillNo:\s*(\d+)")
_BILL_PERIOD_RE = re.compile(r"BillPeriod:\s*(\d{2}\.\d{2}\.\d{2})\s*to\s*(\d{2}\.\d{2}\.\d{2})")
_VODAFONE_NO_RE = re.compile(r"VodafoneNo:\s*(\d+)")
_SUBSCRIBER_RE = re.compile(r"MR\.\s*([A-Z\s]+?)(?:\s+VodafoneNo|\s+Alternate)")
_PLAN_RE = re.compile(r"YourPlan:\s*(.+?)(?:\n|$)")

# Section headers that indicate call type
_SECTION_HEADERS = {
    "local": "outgoing_local",
    "std": "outgoing_std",
    "incoming": "incoming",
    "isd": "outgoing_isd",
    "sms": "sms",
    "smsincoming": "sms_incoming",
    "smslocal": "sms_outgoing",
    "smsstd": "sms_outgoing",
    "outgoingcalls": "outgoing_local",  # default for outgoing section
    "incomingcalls": "incoming",
}


def normalize_phone(raw: str) -> str:
    """Normalize a phone number: strip #, spaces, and leading 91 country code."""
    num = raw.replace("#", "").replace(" ", "").strip()
    # Strip leading 91 if result would be 10 digits (Indian mobile)
    if len(num) == 12 and num.startswith("91"):
        num = num[2:]
    # Strip leading 0 for landlines
    if len(num) == 11 and num.startswith("0"):
        num = num[1:]
    return num


def parse_duration(dur_str: str) -> int:
    """Convert 'Min:Sec' to total seconds."""
    parts = dur_str.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0


def parse_bill_date(date_str: str) -> datetime | None:
    """Parse DD.MM.YY or DD/MM/YY to datetime."""
    for fmt in ("%d.%m.%y", "%d/%m/%y", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_call_datetime(date_str: str, time_str: str) -> datetime | None:
    """Parse call date+time: DD/MM/YY + HH:MM:SS."""
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%d/%m/%y %H:%M:%S")
    except ValueError:
        return None


def parse_vodafone_bill(pdf_path: str | Path) -> dict:
    """Parse a Vodafone India phone bill PDF.

    Returns a dict with:
        - metadata: bill_number, subscriber, period, plan, etc.
        - records: list of CDR dicts (each call/SMS)
        - summary: usage summary from page 3
    """
    pdf_path = Path(pdf_path)
    logger.info("Parsing Vodafone bill: %s", pdf_path.name)

    result = {
        "metadata": {},
        "records": [],
        "summary": {},
        "warnings": [],
    }

    try:
        pdf = pdfplumber.open(str(pdf_path))
    except Exception as e:
        logger.error("Failed to open PDF %s: %s", pdf_path.name, e)
        result["warnings"].append(f"Failed to open PDF: {e}")
        return result

    try:
        # ── Page 1: Bill metadata ──
        if len(pdf.pages) >= 1:
            p1_text = pdf.pages[0].extract_text() or ""
            _extract_metadata(p1_text, result["metadata"])

        # ── Pages 3+: Itemized CDRs ──
        current_type = "outgoing_local"  # default
        for page_idx in range(2, len(pdf.pages)):  # skip pages 1-2 (summary/help)
            page_text = pdf.pages[page_idx].extract_text() or ""
            if not page_text:
                continue

            lines = page_text.split("\n")
            for line in lines:
                # Detect section change
                line_lower = line.lower().replace(" ", "")
                for header_key, call_type in _SECTION_HEADERS.items():
                    if header_key in line_lower and len(line.strip()) < 50:
                        current_type = call_type
                        break

                # Try to extract call records
                is_sms = "sms" in current_type
                records = _extract_records_from_line(line, current_type, is_sms)
                result["records"].extend(records)

        # Inject metadata into each record
        for rec in result["records"]:
            rec["subscriber_number"] = result["metadata"].get("vodafone_number")
            rec["subscriber_name"] = result["metadata"].get("subscriber_name")
            rec["bill_number"] = result["metadata"].get("bill_number")
            rec["bill_period_start"] = result["metadata"].get("period_start")
            rec["bill_period_end"] = result["metadata"].get("period_end")
            rec["bill_plan"] = result["metadata"].get("plan")

            # For outgoing calls, caller = subscriber
            if "outgoing" in rec.get("call_type", ""):
                rec["caller_number"] = result["metadata"].get("vodafone_number")
                rec["called_number"] = rec.pop("phone_number", None)
            elif rec.get("call_type") == "incoming":
                rec["caller_number"] = rec.pop("phone_number", None)
                rec["called_number"] = result["metadata"].get("vodafone_number")
            else:
                # SMS or other
                rec["caller_number"] = result["metadata"].get("vodafone_number")
                rec["called_number"] = rec.pop("phone_number", None)

    finally:
        pdf.close()

    logger.info(
        "Parsed %s: %d records, bill %s, period %s - %s",
        pdf_path.name,
        len(result["records"]),
        result["metadata"].get("bill_number", "?"),
        result["metadata"].get("period_start", "?"),
        result["metadata"].get("period_end", "?"),
    )

    return result


def _extract_metadata(text: str, meta: dict) -> None:
    """Extract bill header metadata from page 1 text."""
    m = _BILL_NO_RE.search(text)
    if m:
        meta["bill_number"] = m.group(1)

    m = _BILL_PERIOD_RE.search(text)
    if m:
        meta["period_start"] = parse_bill_date(m.group(1))
        meta["period_end"] = parse_bill_date(m.group(2))

    m = _VODAFONE_NO_RE.search(text)
    if m:
        meta["vodafone_number"] = m.group(1)

    m = _SUBSCRIBER_RE.search(text)
    if m:
        meta["subscriber_name"] = m.group(1).strip()

    m = _PLAN_RE.search(text)
    if m:
        meta["plan"] = m.group(1).strip()


def _extract_records_from_line(line: str, call_type: str, is_sms: bool) -> list[dict]:
    """Extract CDR records from a single line (may contain 2 records in columns)."""
    records = []

    if is_sms:
        pattern = _SMS_RE
    else:
        pattern = _CALL_RE

    for match in pattern.finditer(line):
        date_str, time_str, phone_raw = match.group(1), match.group(2), match.group(3)

        dt = parse_call_datetime(date_str, time_str)
        phone = normalize_phone(phone_raw)

        if is_sms:
            rec = {
                "call_datetime": dt,
                "call_datetime_raw": f"{date_str}-{time_str}",
                "phone_number": phone,
                "duration_seconds": 0,
                "duration_raw": match.group(4),  # SMS count
                "charges": float(match.group(5)),
                "call_type": call_type,
            }
        else:
            dur_raw = match.group(4)
            rec = {
                "call_datetime": dt,
                "call_datetime_raw": f"{date_str}-{time_str}",
                "phone_number": phone,
                "duration_seconds": parse_duration(dur_raw),
                "duration_raw": dur_raw,
                "charges": float(match.group(5)),
                "call_type": call_type,
            }

        records.append(rec)

    return records
