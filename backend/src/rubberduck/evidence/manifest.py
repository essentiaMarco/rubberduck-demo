"""Chain-of-custody manifest writer — immutable audit log for every file."""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from rubberduck.db.models import ChainOfCustody


class ManifestWriter:
    """Records chain-of-custody entries as an append-only linked list per file."""

    @staticmethod
    def record(
        db: Session,
        file_id: str,
        action: str,
        details: dict | None = None,
        actor: str = "rubberduck",
    ) -> ChainOfCustody:
        """Append a new custody entry for a file.

        Actions: received, hashed, stored, parsed, indexed, exported, entity_extracted
        """
        # Find the last entry for this file (to link prev_entry_id)
        last_entry = (
            db.query(ChainOfCustody)
            .filter(ChainOfCustody.file_id == file_id)
            .order_by(ChainOfCustody.timestamp.desc())
            .first()
        )

        entry = ChainOfCustody(
            file_id=file_id,
            action=action,
            actor=actor,
            timestamp=datetime.now(timezone.utc),
            details=json.dumps(details) if details else None,
            prev_entry_id=last_entry.id if last_entry else None,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
