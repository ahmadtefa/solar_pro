"""Import and export: CSV/Excel upload → map → validate → preview → import.

Invalid rows are never discarded silently: every row is persisted with its
errors so the UI can show exactly what was rejected and why.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.coercion import as_bool, as_decimal, as_uuid
from app.core.enums import ImportStatus, ProductType
from app.core.errors import NotFoundError, ValidationFailure
from app.core.jsonutil import json_safe
from app.models.identity import ImportJob, ImportJobRow
from app.models.masterdata import (
    Customer,
    CustomerGroup,
    Product,
    ProductCategory,
    Supplier,
    SupplierGroup,
)
from app.models.platform import UnitOfMeasure
from app.services.audit_service import AuditContext, AuditService

#: Fields resolved by natural key (code / sku / email) instead of a UUID.
LOOKUP_FIELDS: dict[str, dict[str, tuple[Any, str]]] = {
    "customer": {
        "group_code": (CustomerGroup, "code"),
        "salesperson_email": (None, "email"),  # resolved in _resolve_user
    },
    "supplier": {"group_code": (SupplierGroup, "code")},
    "product": {
        "category_code": (ProductCategory, "code"),
        "unit_code": (UnitOfMeasure, "code"),
        "brand_code": (None, "code"),
    },
}

#: Importable entities: model, natural key, required fields and field builders.
ENTITY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "customer": {
        "model": Customer,
        "label": "Customers",
        "required": ("name",),
        "unique": ("code",),
        "fields": (
            "code",
            "name",
            "name_ar",
            "email",
            "phone",
            "mobile",
            "tax_registration_number",
            "country_code",
            "city",
            "address_line1",
            "contact_person",
            "credit_limit",
            "credit_days",
            "group_code",
            "is_active",
        ),
        "aliases": {
            "customer_name": "name",
            "customer_code": "code",
            "vat_number": "tax_registration_number",
            "credit_limit_amount": "credit_limit",
        },
    },
    "supplier": {
        "model": Supplier,
        "label": "Suppliers",
        "required": ("name",),
        "unique": ("code",),
        "fields": (
            "code",
            "name",
            "name_ar",
            "email",
            "phone",
            "mobile",
            "tax_registration_number",
            "country_code",
            "city",
            "address_line1",
            "credit_limit",
            "credit_days",
            "group_code",
            "lead_time_days",
            "is_active",
        ),
        "aliases": {
            "supplier_name": "name",
            "supplier_code": "code",
            "vat_number": "tax_registration_number",
        },
    },
    "product": {
        "model": Product,
        "label": "Products / items",
        "required": ("sku", "name"),
        "unique": ("sku",),
        "fields": (
            "sku",
            "barcode",
            "name",
            "name_ar",
            "description",
            "product_type",
            "category_code",
            "unit_code",
            "purchase_price",
            "sales_price",
            "cost_price",
            "min_stock",
            "max_stock",
            "reorder_level",
            "reorder_quantity",
            "lead_time_days",
            "shelf_life_days",
            "is_sellable",
            "is_purchasable",
            "is_active",
        ),
        "aliases": {
            "item_code": "sku",
            "item_name": "name",
            "unit": "unit_code",
            "category": "category_code",
            "selling_price": "sales_price",
            "buying_price": "purchase_price",
        },
    },
}


class ImportExportService:
    """Tabular import/export for master data and reports."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    # ------------------------------------------------------------ definitions
    def available_entities(self) -> list[dict[str, Any]]:
        return [
            {
                "entity": key,
                "label": definition["label"],
                "required": list(definition["required"]),
                "unique": list(definition["unique"]),
                "fields": list(definition["fields"]),
                "template_columns": list(definition["fields"]),
            }
            for key, definition in ENTITY_DEFINITIONS.items()
        ]

    def template_rows(self, entity_type: str, *, sample: bool = True) -> list[dict[str, Any]]:
        definition = self._definition(entity_type)
        columns = list(definition["fields"])
        if not sample:
            return [dict.fromkeys(columns, "")]
        if entity_type == "customer":
            values = {"code": "CUS-9001", "name": "Sample Customer", "email": "buyer@example.com", "credit_limit": "50000"}
        elif entity_type == "supplier":
            values = {"code": "SUP-9001", "name": "Sample Supplier", "email": "sales@example.com", "credit_days": "30"}
        else:
            values = {
                "sku": "SKU-9001",
                "name": "Sample Item",
                "product_type": "stock",
                "unit_code": "PCS",
                "purchase_price": "100",
                "sales_price": "150",
            }
        return [{column: values.get(column, "") for column in columns}]

    # ------------------------------------------------------------------ reading
    def read_tabular(self, content: bytes, file_name: str) -> list[dict[str, Any]]:
        """Parse CSV/TSV or Excel content into a list of row dictionaries."""
        suffix = Path(file_name).suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            return self._read_excel(content)
        if suffix in {".csv", ".txt", ".tsv"}:
            return self._read_csv(content, delimiter="\t" if suffix == ".tsv" else ",")
        raise ValidationFailure(
            "Unsupported file type. Upload a CSV, TSV or Excel (.xlsx) file.", file_name=file_name
        )

    @staticmethod
    def _read_csv(content: bytes, *, delimiter: str = ",") -> list[dict[str, Any]]:
        for encoding in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:  # pragma: no cover - defensive
            raise ValidationFailure("The file encoding could not be detected")
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows: list[dict[str, Any]] = []
        for row in reader:
            cleaned = {
                (key or "").strip(): (value.strip() if isinstance(value, str) else value)
                for key, value in row.items()
                if key is not None
            }
            if any(value not in (None, "") for value in cleaned.values()):
                rows.append(cleaned)
        return rows

    @staticmethod
    def _read_excel(content: bytes) -> list[dict[str, Any]]:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise ValidationFailure("Excel support requires the openpyxl package") from exc
        workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        sheet = workbook.active
        rows_iter = sheet.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration:
            return []
        columns = [str(value).strip() if value is not None else f"column_{index}" for index, value in enumerate(header)]
        rows: list[dict[str, Any]] = []
        for values in rows_iter:
            row = {
                columns[index]: (value.strip() if isinstance(value, str) else value)
                for index, value in enumerate(values)
                if index < len(columns)
            }
            if any(value not in (None, "") for value in row.values()):
                rows.append(row)
        workbook.close()
        return rows

    # ----------------------------------------------------------------- pipeline
    def create_job(
        self,
        entity_type: str,
        *,
        rows: Sequence[dict[str, Any]],
        file_name: str | None = None,
        storage_path: str | None = None,
        column_mapping: dict[str, str] | None = None,
    ) -> ImportJob:
        self._definition(entity_type)
        if not rows:
            raise ValidationFailure("The uploaded file has no data rows")
        job = ImportJob(
            company_id=self.company_id,
            entity_type=entity_type,
            file_name=file_name,
            storage_path=storage_path,
            status=ImportStatus.UPLOADED.value,
            column_mapping=column_mapping or {},
            total_rows=len(rows),
        )
        self.db.add(job)
        self.db.flush()
        for index, raw in enumerate(rows, start=1):
            self.db.add(
                ImportJobRow(
                    import_job_id=job.id,
                    row_number=index,
                    raw_data=json_safe({str(key): value for key, value in raw.items()}),
                    import_status="pending",
                )
            )
        self.db.flush()
        self.audit.log_action(
            "import",
            job,
            entity_type="import_job",
            label=f"{entity_type}:{file_name or 'upload'}",
            new_values={"rows": len(rows)},
        )
        return job

    def job(self, job_id: uuid.UUID | str) -> ImportJob:
        job = self.db.execute(
            select(ImportJob).where(
                ImportJob.company_id == self.company_id, ImportJob.id == as_uuid(job_id)
            )
        ).scalars().first()
        if job is None:
            raise NotFoundError("Import job not found", id=str(job_id))
        return job

    def list_jobs(self, *, limit: int = 50) -> list[ImportJob]:
        return list(
            self.db.execute(
                select(ImportJob)
                .where(ImportJob.company_id == self.company_id)
                .order_by(ImportJob.created_at.desc())
                .limit(limit)
            ).scalars().all()
        )

    def validate(self, job_id: uuid.UUID | str) -> dict[str, Any]:
        """Normalise every row, record per-row errors and return a summary."""
        job = self.job(job_id)
        rows = self._job_rows(job.id)
        valid = invalid = 0
        seen_unique: dict[str, int] = {}
        definition = self._definition(job.entity_type)
        for row in rows:
            normalized, errors = self._normalize_row(job, definition, row, seen_unique)
            row.normalized_data = json_safe(normalized)
            row.errors = json_safe(errors)
            row.is_valid = not errors
            row.import_status = "valid" if row.is_valid else "invalid"
            if row.is_valid:
                valid += 1
            else:
                invalid += 1
        job.valid_rows = valid
        job.invalid_rows = invalid
        job.status = ImportStatus.VALIDATED.value if valid else ImportStatus.FAILED.value
        job.error_summary = (
            None
            if invalid == 0
            else f"{invalid} of {len(rows)} rows are invalid and will be reported, not imported"
        )
        self.db.flush()
        return self.preview(job.id)

    def preview(self, job_id: uuid.UUID | str, *, limit: int = 100) -> dict[str, Any]:
        job = self.job(job_id)
        rows = self._job_rows(job.id)
        return {
            "job_id": str(job.id),
            "entity_type": job.entity_type,
            "status": job.status,
            "file_name": job.file_name,
            "total_rows": job.total_rows,
            "valid_rows": job.valid_rows,
            "invalid_rows": job.invalid_rows,
            "imported_rows": job.imported_rows,
            "error_summary": job.error_summary,
            "valid": [
                {"row": row.row_number, "data": row.normalized_data}
                for row in rows
                if row.is_valid
            ][:limit],
            "invalid": [
                {"row": row.row_number, "data": row.raw_data, "errors": row.errors}
                for row in rows
                if not row.is_valid
            ][:limit],
        }

    def commit(self, job_id: uuid.UUID | str, *, skip_invalid: bool = True) -> dict[str, Any]:
        """Create the entities for validated rows; invalid rows stay reported."""
        from app.services.import_handlers import IMPORT_HANDLERS

        job = self.job(job_id)
        if job.status == ImportStatus.UPLOADED.value:
            self.validate(job.id)
            job = self.job(job_id)
        rows = self._job_rows(job.id)
        if not skip_invalid and any(not row.is_valid for row in rows):
            raise ValidationFailure("Some rows are invalid. Fix them or import with skip_invalid=True.")
        handler = IMPORT_HANDLERS.get(job.entity_type)
        if handler is None:  # pragma: no cover - guarded by _definition
            raise ValidationFailure(f"No import handler for '{job.entity_type}'")
        imported = skipped = failed = 0
        for row in rows:
            if not row.is_valid:
                skipped += 1
                continue
            try:
                entity = handler(self, row.normalized_data or {})
            except Exception as exc:  # noqa: BLE001 - every failure is reported back
                row.is_valid = False
                row.errors = [{"field": None, "message": str(exc)}]
                row.import_status = "failed"
                failed += 1
                continue
            row.imported_entity_id = getattr(entity, "id", None)
            row.import_status = "imported"
            imported += 1
        job.imported_rows = imported
        job.status = (
            ImportStatus.IMPORTED.value
            if failed == 0 and (imported or skipped == 0)
            else ImportStatus.FAILED.value
            if imported == 0
            else ImportStatus.IMPORTED.value
        )
        problems = [f"row {row.row_number}: {row.errors}" for row in rows if row.errors]
        job.error_summary = "; ".join(problems[:20]) if problems else None
        self.db.flush()
        self.audit.log_action(
            "import",
            job,
            entity_type="import_job",
            label=job.entity_type,
            new_values={"imported": imported, "skipped": skipped, "failed": failed},
        )
        return {
            "job_id": str(job.id),
            "entity_type": job.entity_type,
            "imported": imported,
            "skipped_invalid": skipped,
            "failed": failed,
            "status": job.status,
            "errors": [
                {"row": row.row_number, "errors": row.errors}
                for row in rows
                if row.errors
            ][:100],
        }

    # -------------------------------------------------------------- validation
    def _normalize_row(
        self,
        job: ImportJob,
        definition: dict[str, Any],
        row: ImportJobRow,
        seen_unique: dict[str, int],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        raw = self._apply_mapping(row.raw_data or {}, job.column_mapping or {}, definition)
        normalized: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []
        for field in definition["fields"]:
            if field not in raw:
                continue
            value = raw[field]
            if value in (None, ""):
                continue
            try:
                normalized[field] = self._coerce_field(job.entity_type, field, value)
            except (ValidationFailure, InvalidOperation, ValueError) as exc:
                errors.append({"field": field, "message": str(exc)})
        for field in definition["required"]:
            if normalized.get(field) in (None, ""):
                errors.append({"field": field, "message": f"'{field}' is required"})
        for field in definition["unique"]:
            value = normalized.get(field)
            if value in (None, ""):
                continue
            key = f"{field}:{str(value).lower()}"
            if key in seen_unique:
                errors.append(
                    {
                        "field": field,
                        "message": f"Duplicate of row {seen_unique[key]} in this file",
                    }
                )
            else:
                seen_unique[key] = row.row_number
            existing = self._find_existing(job.entity_type, field, value)
            if existing is not None:
                errors.append(
                    {"field": field, "message": f"{field} '{value}' already exists in this company"}
                )
        return normalized, errors

    def _apply_mapping(
        self, raw: dict[str, Any], mapping: dict[str, str], definition: dict[str, Any]
    ) -> dict[str, Any]:
        aliases: dict[str, str] = {**definition.get("aliases", {}), **mapping}
        out: dict[str, Any] = {}
        for key, value in raw.items():
            target = aliases.get(key, key)
            target = aliases.get(target, target)
            if target in definition["fields"] and target not in out:
                out[target] = value
        return out

    def _coerce_field(self, entity_type: str, field: str, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip() if not isinstance(value, (int, float, Decimal, date, bool)) else value
        if field in {"is_active", "is_sellable", "is_purchasable"}:
            parsed = as_bool(text)
            return True if parsed is None else parsed
        if field in {
            "credit_limit",
            "credit_days",
            "lead_time_days",
            "purchase_price",
            "sales_price",
            "cost_price",
            "min_stock",
            "max_stock",
            "reorder_level",
            "reorder_quantity",
            "shelf_life_days",
        }:
            try:
                return as_decimal(text)
            except (InvalidOperation, ValueError) as exc:
                raise ValidationFailure(f"'{value}' is not a valid number") from exc
        if field in {"product_type"}:
            if str(text).lower() not in {member.value for member in ProductType}:
                raise ValidationFailure(
                    f"'{value}' is not a valid product type ({', '.join(m.value for m in ProductType)})"
                )
            return str(text).lower()
        if field == "group_code":
            model, attribute = LOOKUP_FIELDS[entity_type][field]
            group = self._lookup(model, attribute, text)
            if group is None:
                raise ValidationFailure(f"Group code '{value}' does not exist")
            return group.id
        if field in {"category_code", "unit_code", "brand_code"}:
            model, attribute = LOOKUP_FIELDS["product"][field]
            if model is None:
                return text
            found = self._lookup(model, attribute, text)
            if found is None:
                raise ValidationFailure(f"'{value}' does not exist")
            return found.id
        if field == "country_code":
            return str(text).upper()[:2]
        return text

    def _find_existing(self, entity_type: str, field: str, value: Any) -> Any:
        definition = self._definition(entity_type)
        model = definition["model"]
        column = getattr(model, field, None)
        if column is None:
            return None
        stmt = select(model).where(model.company_id == self.company_id, column == value)
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        return self.db.execute(stmt).scalars().first()

    def _lookup(self, model: Any, attribute: str, value: Any) -> Any:
        if model is None:
            return None
        column = getattr(model, attribute, None)
        if column is None:
            return None
        return self.db.execute(
            select(model).where(model.company_id == self.company_id, column == value)
        ).scalars().first()

    def _definition(self, entity_type: str) -> dict[str, Any]:
        definition = ENTITY_DEFINITIONS.get(entity_type)
        if definition is None:
            raise NotFoundError(
                f"'{entity_type}' cannot be imported",
                supported=sorted(ENTITY_DEFINITIONS),
            )
        return definition

    def _job_rows(self, job_id: uuid.UUID) -> list[ImportJobRow]:
        return list(
            self.db.execute(
                select(ImportJobRow).where(ImportJobRow.import_job_id == job_id).order_by(ImportJobRow.row_number)
            ).scalars().all()
        )

    # ---------------------------------------------------------------- exporting
    def export_rows(
        self,
        entity_type: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        definition = self._definition(entity_type)
        model = definition["model"]
        stmt = select(model).where(model.company_id == self.company_id)
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        filters = filters or {}
        if filters.get("is_active") is not None:
            stmt = stmt.where(model.is_active.is_(bool(filters["is_active"])))
        if filters.get("search"):
            needle = f"%{filters['search']}%"
            column = getattr(model, definition["unique"][0])
            name_column = getattr(model, "name", None)
            stmt = stmt.where(column.ilike(needle) if name_column is None else (column.ilike(needle) | name_column.ilike(needle)))
        stmt = stmt.limit(limit)
        records = self.db.execute(stmt).scalars().all()
        rows: list[dict[str, Any]] = []
        for record in records:
            row: dict[str, Any] = {}
            for field in definition["fields"]:
                value = getattr(record, field, None)
                if field.endswith("_code") and value is None:
                    continue
                row[field] = self._export_value(value)
            rows.append(row)
        return rows

    @staticmethod
    def _export_value(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    def to_csv(self, rows: Sequence[dict[str, Any]], columns: Sequence[str] | None = None) -> str:
        if not rows:
            return ",".join(columns or [])
        columns = list(columns or rows[0].keys())
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: ("" if row.get(column) is None else row.get(column)) for column in columns})
        return buffer.getvalue()

    def to_xlsx_bytes(self, rows: Sequence[dict[str, Any]], columns: Sequence[str] | None = None, *, title: str = "Export") -> bytes:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise ValidationFailure("Excel export requires the openpyxl package") from exc
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = title[:31] or "Export"
        columns = list(columns or (rows[0].keys() if rows else []))
        sheet.append(columns)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append([row.get(column) for column in columns])
        for index, column in enumerate(columns, start=1):
            sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = max(12, len(str(column)) + 4)
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def export_report(self, code: str, params: dict[str, Any] | None = None, *, file_format: str = "csv") -> bytes:
        """Export any registered report as CSV or Excel (no placeholder screens)."""
        from app.services.report_service import ReportService

        result = ReportService(self.db, self.company_id).run(code, params or {})
        if file_format in {"xlsx", "excel"}:
            return result.to_excel()
        if file_format == "csv":
            return result.to_csv()
        raise ValidationFailure("Supported export formats are csv and xlsx", requested=file_format)


__all__ = ["ENTITY_DEFINITIONS", "ImportExportService"]
