"""Financial intelligence service — anomaly detection and flow analysis."""

import json
import logging
import statistics
from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from rubberduck.db.models import FinancialTransaction

logger = logging.getLogger(__name__)


def detect_anomalies(db: Session) -> dict[str, Any]:
    """Run anomaly detection across all financial transactions.

    Detects:
    - Structuring: sequences just below reporting thresholds ($10K)
    - Velocity: 3+ transactions same day to different accounts
    - Unusual amounts: > 3 standard deviations from account mean
    - Round numbers: exact $1K, $5K, $10K amounts
    """
    transactions = db.query(FinancialTransaction).order_by(FinancialTransaction.transaction_date).all()
    if not transactions:
        return {"total": 0, "anomalies_found": 0}

    anomalies_found = 0

    # Group by from_account for per-account analysis
    by_account: dict[str, list[FinancialTransaction]] = defaultdict(list)
    for tx in transactions:
        key = tx.from_account or tx.to_account or "unknown"
        by_account[key].append(tx)

    for account, txs in by_account.items():
        amounts = [abs(tx.amount) for tx in txs if tx.amount]
        if not amounts:
            continue

        mean_amt = statistics.mean(amounts)
        stddev_amt = statistics.stdev(amounts) if len(amounts) > 1 else 0

        for tx in txs:
            reasons: list[str] = []
            score = 0.0
            abs_amt = abs(tx.amount) if tx.amount else 0

            # Structuring: amount in $9,000-$9,999 range (just below $10K CTR threshold)
            if 9000 <= abs_amt < 10000:
                reasons.append(f"Amount ${abs_amt:,.2f} is just below $10,000 CTR reporting threshold")
                score += 0.4

            # Round numbers: exact thousands
            if abs_amt >= 1000 and abs_amt == int(abs_amt) and abs_amt % 1000 == 0:
                reasons.append(f"Exact round amount: ${abs_amt:,.0f}")
                score += 0.15

            # Unusual amount: > 3 standard deviations
            if stddev_amt > 0 and abs_amt > mean_amt + 3 * stddev_amt:
                reasons.append(f"Amount ${abs_amt:,.2f} is {(abs_amt - mean_amt) / stddev_amt:.1f} std devs above account mean ${mean_amt:,.2f}")
                score += 0.3

            # Large transaction (> $25K)
            if abs_amt > 25000:
                reasons.append(f"Large transaction: ${abs_amt:,.2f}")
                score += 0.2

            if reasons:
                tx.is_anomaly = True
                tx.anomaly_score = min(score, 1.0)
                tx.anomaly_reasons = json.dumps(reasons)
                anomalies_found += 1

    # Velocity detection: 3+ transactions same day
    by_date: dict[str, list[FinancialTransaction]] = defaultdict(list)
    for tx in transactions:
        if tx.transaction_date:
            day_key = tx.transaction_date.strftime("%Y-%m-%d")
            by_date[day_key].append(tx)

    for day, day_txs in by_date.items():
        if len(day_txs) >= 3:
            unique_targets = len({tx.to_account for tx in day_txs if tx.to_account})
            if unique_targets >= 3:
                for tx in day_txs:
                    existing_reasons = json.loads(tx.anomaly_reasons) if tx.anomaly_reasons else []
                    existing_reasons.append(
                        f"Velocity: {len(day_txs)} transactions to {unique_targets} different accounts on {day}"
                    )
                    tx.is_anomaly = True
                    tx.anomaly_score = min((tx.anomaly_score or 0) + 0.3, 1.0)
                    tx.anomaly_reasons = json.dumps(existing_reasons)
                    if not any("Velocity" in r for r in (json.loads(tx.anomaly_reasons) if tx.anomaly_reasons else [])[:-1]):
                        anomalies_found += 1

    db.commit()
    return {"total": len(transactions), "anomalies_found": anomalies_found}


def get_flow_data(db: Session) -> dict[str, Any]:
    """Build Sankey diagram data: nodes (accounts) and links (flows between them).

    Returns {nodes: [{id, name}], links: [{source, target, value}]}
    """
    transactions = (
        db.query(FinancialTransaction)
        .filter(FinancialTransaction.from_account.isnot(None), FinancialTransaction.to_account.isnot(None))
        .all()
    )

    # Aggregate flows between account pairs
    flows: dict[tuple[str, str], float] = defaultdict(float)
    accounts: set[str] = set()
    for tx in transactions:
        if tx.from_account and tx.to_account:
            flows[(tx.from_account, tx.to_account)] += abs(tx.amount)
            accounts.add(tx.from_account)
            accounts.add(tx.to_account)

    # Also include single-direction flows (deposits/withdrawals)
    single_flows = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.from_account.isnot(None),
            FinancialTransaction.to_account.is_(None),
        )
        .all()
    )
    for tx in single_flows:
        cat = tx.category or "unknown"
        flows[(tx.from_account, f"[{cat}]")] += abs(tx.amount)
        accounts.add(tx.from_account)
        accounts.add(f"[{cat}]")

    account_list = sorted(accounts)
    id_map = {name: i for i, name in enumerate(account_list)}

    nodes = [{"id": i, "name": name} for name, i in id_map.items()]
    links = [
        {"source": id_map[src], "target": id_map[tgt], "value": round(val, 2)}
        for (src, tgt), val in sorted(flows.items(), key=lambda x: -x[1])[:200]
    ]

    return {"nodes": nodes, "links": links}


def get_stats(db: Session) -> dict[str, Any]:
    """Financial transaction statistics."""
    total = db.query(FinancialTransaction).count()
    if total == 0:
        return {
            "total_transactions": 0, "total_inflow": 0, "total_outflow": 0,
            "net": 0, "by_category": {}, "by_type": {},
            "anomaly_count": 0, "date_range": None,
        }

    total_inflow = db.query(func.sum(FinancialTransaction.amount)).filter(
        FinancialTransaction.amount > 0
    ).scalar() or 0
    total_outflow = db.query(func.sum(FinancialTransaction.amount)).filter(
        FinancialTransaction.amount < 0
    ).scalar() or 0

    by_category = dict(
        db.query(FinancialTransaction.category, func.count())
        .group_by(FinancialTransaction.category).all()
    )
    by_type = dict(
        db.query(FinancialTransaction.transaction_type, func.count())
        .group_by(FinancialTransaction.transaction_type).all()
    )
    anomaly_count = db.query(FinancialTransaction).filter(FinancialTransaction.is_anomaly == True).count()

    date_min = db.query(func.min(FinancialTransaction.transaction_date)).scalar()
    date_max = db.query(func.max(FinancialTransaction.transaction_date)).scalar()

    return {
        "total_transactions": total,
        "total_inflow": round(total_inflow, 2),
        "total_outflow": round(abs(total_outflow), 2),
        "net": round(total_inflow + total_outflow, 2),
        "by_category": by_category,
        "by_type": by_type,
        "anomaly_count": anomaly_count,
        "date_range": {
            "start": str(date_min) if date_min else None,
            "end": str(date_max) if date_max else None,
        },
    }
