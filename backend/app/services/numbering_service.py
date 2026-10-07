"""Server side document numbering.

Numbers are allocated inside the caller's transaction so a rolled back document
does not consume a number and two concurrent users can never receive the same
document number (the sequence row is locked with ``FOR UPDATE`` on PostgreSQL).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError
from app.models.platform import NumberSequence

#: Default prefixes per document type.  Companies can override them.
DEFAULT_PREFIXES: dict[str, str] = {
    "journal_entry": "JE",
    "quotation": "QT",
    "sales_order": "SO",
    "delivery_note": "DN",
    "sales_invoice": "SI",
    "credit_note": "CN",
    "pos_shift": "PS",
    "purchase_request": "PR",
    "rfq": "RFQ",
    "supplier_quotation": "SQ",
    "purchase_order": "PO",
    "goods_receipt": "GRN",
    "purchase_invoice": "PI",
    "debit_note": "DB",
    "payment": "PAY",
    "receipt": "RCP",
    "treasury_transfer": "TRF",
    "stock_transfer": "ST",
    "stock_adjustment": "ADJ",
    "stock_count": "SC",
    "asset": "FA",
    "asset_transfer": "FAT",
    "asset_disposal": "FAD",
    "asset_maintenance": "FAM",
    "production_order": "MO",
    "expense": "EXP",
    "expense_claim": "CLM",
    "expense_advance": "ADV",
    "lead": "LEAD",
    "opportunity": "OPP",
    "service_request": "SR",
    "ticket": "TKT",
    "work_order": "WO",
    "service_contract": "SC",
    "warranty": "WAR",
    "timesheet": "TS",
    "payroll_run": "PRUN",
    "leave_request": "LR",
    "employee": "EMP",
    "customer": "CUS",
    "supplier": "SUP",
    "product": "PRD",
    "bank_reconciliation": "BR",
    "currency_revaluation": "FXR",
    "employee_loan": "LN",
}


class NumberingService:
    def __init__(self, db: Session, company_id: uuid.UUID) -> None:
        self.db = db
        self.company_id = company_id

    def _get_or_create(self, document_type: str, branch_id: uuid.UUID | None) -> NumberSequence:
        stmt = (
            select(NumberSequence)
            .where(
                NumberSequence.company_id == self.company_id,
                NumberSequence.document_type == document_type,
                NumberSequence.branch_id.is_(None) if branch_id is None else NumberSequence.branch_id == branch_id,
            )
            .with_for_update()
        )
        sequence = self.db.execute(stmt).scalars().first()
        if sequence is None:
            sequence = NumberSequence(
                company_id=self.company_id,
                document_type=document_type,
                branch_id=branch_id,
                prefix=DEFAULT_PREFIXES.get(document_type, document_type[:4].upper()),
                suffix="",
                padding=5,
                next_number=1,
                reset_yearly=False,
                current_year=datetime.now(UTC).year,
            )
            # Unique constraint guards concurrent inserts: retry the read once.
            self.db.add(sequence)
            try:
                self.db.flush()
            except Exception:  # pragma: no cover - concurrent creation race
                self.db.rollback()
                sequence = self.db.execute(stmt).scalars().first()
                if sequence is None:
                    raise BusinessRuleError("Could not allocate a document number, please retry") from None
        return sequence

    def next_number(
        self,
        document_type: str,
        *,
        branch_id: uuid.UUID | None = None,
        prefix: str | None = None,
        padding: int | None = None,
        year: int | None = None,
    ) -> str:
        """Allocate the next formatted document number."""
        sequence = self._get_or_create(document_type, branch_id)
        current_year = year or datetime.now(UTC).year
        if sequence.reset_yearly and sequence.current_year != current_year:
            sequence.current_year = current_year
            sequence.next_number = 1
        number = sequence.next_number
        sequence.next_number = number + 1
        sequence.current_year = current_year
        self.db.flush()

        used_prefix = prefix if prefix is not None else sequence.prefix
        used_padding = padding if padding is not None else sequence.padding
        core = str(number).zfill(max(used_padding, 1))
        parts = [used_prefix, core]
        if sequence.suffix:
            parts.append(sequence.suffix)
        document_no = "-".join(part for part in parts if part)
        return document_no

    def peek_next(self, document_type: str, *, branch_id: uuid.UUID | None = None) -> str:
        sequence = self._get_or_create(document_type, branch_id)
        core = str(sequence.next_number).zfill(max(sequence.padding, 1))
        parts = [sequence.prefix, core, sequence.suffix]
        return "-".join(part for part in parts if part)

    def configure(
        self,
        document_type: str,
        *,
        prefix: str | None = None,
        suffix: str | None = None,
        padding: int | None = None,
        reset_yearly: bool | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> NumberSequence:
        sequence = self._get_or_create(document_type, branch_id)
        if prefix is not None:
            sequence.prefix = prefix
        if suffix is not None:
            sequence.suffix = suffix
        if padding is not None:
            sequence.padding = max(padding, 1)
        if reset_yearly is not None:
            sequence.reset_yearly = reset_yearly
        self.db.flush()
        return sequence


def slugify_code(value: str, *, max_length: int = 32) -> str:
    """Turn a human label into an uppercase code (used by auto-generated codes)."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", (value or "").strip()).strip("-").upper()
    return (cleaned or "AUTO")[:max_length]
