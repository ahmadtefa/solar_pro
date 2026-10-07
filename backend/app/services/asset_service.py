"""Fixed assets: register, depreciation, transfer, maintenance and disposal."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.coercion import as_uuid
from app.core.enums import AssetStatus, AuditAction, DepreciationMethod
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, ValidationFailure
from app.models.assets import (
    Asset,
    AssetCategory,
    AssetDepreciation,
    AssetDisposal,
    AssetMaintenance,
    AssetTransfer,
)
from app.services.audit_service import AuditContext, AuditService
from app.services.posting_service import EntryLine, money

ZERO = Decimal("0")


def _decimal(value: Any, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    return Decimal(str(value))


class AssetCategoryService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def create(self, payload: dict[str, Any]) -> AssetCategory:
        code = str(payload["code"]).strip().upper()
        existing = self.db.execute(
            select(AssetCategory).where(AssetCategory.company_id == self.company_id, AssetCategory.code == code)
        ).scalars().first()
        if existing is not None:
            raise ConflictError(f"Asset category {code} already exists")
        category = AssetCategory(
            company_id=self.company_id,
            code=code,
            name=payload["name"],
            name_ar=payload.get("name_ar"),
            depreciation_method=payload.get("depreciation_method", DepreciationMethod.STRAIGHT_LINE.value),
            useful_life_years=int(payload.get("useful_life_years") or 5),
            useful_life_months=int(payload.get("useful_life_months") or 0),
            salvage_percent=_decimal(payload.get("salvage_percent")),
            declining_rate=_decimal(payload.get("declining_rate")),
            asset_account_id=as_uuid(payload.get("asset_account_id")),
            depreciation_account_id=as_uuid(payload.get("depreciation_account_id")),
            accumulated_depreciation_account_id=as_uuid(payload.get("accumulated_depreciation_account_id")),
            disposal_account_id=as_uuid(payload.get("disposal_account_id")),
            notes=payload.get("notes"),
        )
        self.db.add(category)
        self.db.flush()
        self.audit.log_create(category, entity_type="asset_category", label=category.code)
        return category

    def list(self) -> list[AssetCategory]:
        return list(
            self.db.execute(
                select(AssetCategory)
                .where(AssetCategory.company_id == self.company_id)
                .order_by(AssetCategory.code)
            ).scalars().all()
        )


class AssetService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def get(self, asset_id: uuid.UUID) -> Asset:
        asset = self.db.execute(
            select(Asset).where(Asset.company_id == self.company_id, Asset.id == asset_id)
        ).scalars().first()
        if asset is None:
            raise NotFoundError("Asset not found")
        return asset

    def _next_asset_no(self) -> str:
        count = self.db.execute(
            select(func.count()).select_from(Asset).where(Asset.company_id == self.company_id)
        ).scalar_one()
        candidate = f"FA-{int(count) + 1:05d}"
        while self.db.execute(
            select(Asset).where(Asset.company_id == self.company_id, Asset.asset_no == candidate)
        ).scalars().first():
            count += 1
            candidate = f"FA-{int(count) + 1:05d}"
        return candidate

    # ------------------------------------------------------------- acquisition
    def acquire(self, payload: dict[str, Any]) -> Asset:
        category = None
        if payload.get("category_id"):
            category = self.db.get(AssetCategory, as_uuid(payload["category_id"]))
            if category is None:
                raise NotFoundError("Asset category not found")
        method = payload.get("depreciation_method") or (
            category.depreciation_method if category else DepreciationMethod.STRAIGHT_LINE.value
        )
        useful_life_years = int(payload.get("useful_life_years") or (category.useful_life_years if category else 5))
        cost = money(payload.get("acquisition_cost"))
        if cost <= 0:
            raise ValidationFailure("The acquisition cost must be greater than zero")
        salvage_percent = _decimal(
            payload.get("salvage_percent") if payload.get("salvage_percent") is not None
            else (category.salvage_percent if category else 0)
        )
        salvage = money(payload.get("salvage_value") or (cost * salvage_percent / Decimal("100")))
        asset = Asset(
            company_id=self.company_id,
            asset_no=payload.get("asset_no") or self._next_asset_no(),
            name=payload["name"],
            name_ar=payload.get("name_ar"),
            description=payload.get("description"),
            category_id=category.id if category else None,
            product_id=as_uuid(payload.get("product_id")),
            serial_number=payload.get("serial_number"),
            barcode=payload.get("barcode"),
            manufacturer=payload.get("manufacturer"),
            model=payload.get("model"),
            year_of_manufacture=payload.get("year_of_manufacture"),
            branch_id=as_uuid(payload.get("branch_id")),
            department_id=as_uuid(payload.get("department_id")),
            location=payload.get("location"),
            cost_center_id=as_uuid(payload.get("cost_center_id")),
            project_id=as_uuid(payload.get("project_id")),
            custodian_id=as_uuid(payload.get("custodian_id")),
            supplier_id=as_uuid(payload.get("supplier_id")),
            purchase_invoice_id=as_uuid(payload.get("purchase_invoice_id")),
            acquisition_date=payload.get("acquisition_date") or date.today(),
            in_service_date=payload.get("in_service_date") or payload.get("acquisition_date") or date.today(),
            acquisition_cost=cost,
            additional_cost=money(payload.get("additional_cost")),
            total_cost=money(cost + money(payload.get("additional_cost"))),
            salvage_value=salvage,
            currency_code=payload.get("currency_code"),
            depreciation_method=method,
            useful_life_years=useful_life_years,
            useful_life_months=int(payload.get("useful_life_months") or 0),
            declining_rate=_decimal(
                payload.get("declining_rate") if payload.get("declining_rate") is not None
                else (category.declining_rate if category else 0)
            ),
            total_units_expected=_decimal(payload.get("total_units_expected")),
            accumulated_depreciation=ZERO,
            # Book value = gross cost; the salvage value only limits depreciation.
            book_value=money(cost + money(payload.get("additional_cost"))),
            depreciation_start_date=payload.get("depreciation_start_date") or payload.get("in_service_date") or date.today(),
            asset_account_id=as_uuid(payload.get("asset_account_id")) or (category.asset_account_id if category else None),
            depreciation_account_id=as_uuid(payload.get("depreciation_account_id"))
            or (category.depreciation_account_id if category else None),
            accumulated_depreciation_account_id=as_uuid(payload.get("accumulated_depreciation_account_id"))
            or (category.accumulated_depreciation_account_id if category else None),
            status=AssetStatus.DRAFT.value,
            warranty_start=payload.get("warranty_start"),
            warranty_end=payload.get("warranty_end"),
            insurance_policy_no=payload.get("insurance_policy_no"),
            insurance_value=money(payload.get("insurance_value")),
            insurance_expiry=payload.get("insurance_expiry"),
            notes=payload.get("notes"),
        )
        self.db.add(asset)
        self.db.flush()
        self.audit.log_create(asset, entity_type="asset", label=asset.asset_no)
        return asset

    def capitalize(self, asset_id: uuid.UUID, *, posting: bool = True) -> Asset:
        """Activate an acquired asset and capitalise it in the ledger."""
        asset = self.get(asset_id)
        if asset.status not in {AssetStatus.DRAFT.value, AssetStatus.UNDER_MAINTENANCE.value}:
            raise BusinessRuleError("Only draft assets can be capitalised")
        asset.status = AssetStatus.ACTIVE.value
        if posting:
            from app.services.posting_service import DocumentPostingContext, PostingService

            posting_service = PostingService(self.db, self.company_id)
            asset_account = (
                posting_service.account_by_id(asset.asset_account_id)
                if asset.asset_account_id
                else posting_service.resolve_account("fixed_asset", document_type="asset", fallback_code="1510")
            )
            supplier_id = asset.supplier_id
            if supplier_id is None and asset.purchase_invoice_id:
                from app.models.purchasing import PurchaseInvoice

                invoice = self.db.get(PurchaseInvoice, asset.purchase_invoice_id)
                supplier_id = invoice.supplier_id if invoice else None
            funding_account_id = (asset.extra_data or {}).get("funding_account_id")
            if funding_account_id:
                # Explicit funding account (cash / bank / clearing) supplied at capture time.
                funding = posting_service.account_by_id(uuid.UUID(str(funding_account_id)))
                party_type = None
                party_id = None
            elif supplier_id:
                funding = posting_service.resolve_account(
                    "ap", document_type="asset", fallback_code="2110"
                )
                party_type = "supplier"
                party_id = supplier_id
            else:
                # Purchased cash-down: settle against the default payment account.
                funding = posting_service.resolve_account(
                    "cash", document_type="asset", fallback_code="1110"
                )
                party_type = None
                party_id = None
            entry = posting_service.build_entry(
                context=DocumentPostingContext(
                    document_type="asset",
                    document_id=asset.id,
                    document_no=asset.asset_no,
                    document_date=asset.acquisition_date,
                    description=f"Capitalisation of {asset.name}",
                    branch_id=asset.branch_id,
                ),
                lines=[
                    EntryLine(
                        account_id=asset_account.id,
                        debit=money(asset.total_cost),
                        description=f"Asset {asset.asset_no}",
                        branch_id=asset.branch_id,
                    ),
                    EntryLine(
                        account_id=funding.id,
                        credit=money(asset.total_cost),
                        description=f"Asset {asset.asset_no} acquisition",
                        party_type=party_type,
                        party_id=party_id,
                    ),
                ],
                entry_type="asset_capitalisation",
                reference=asset.asset_no,
                auto_post=True,
                user_id=self.user_id,
            )
            asset.extra_data = {**(asset.extra_data or {}), "capitalisation_entry_id": str(entry.id)}
        self.db.flush()
        self.audit.log_action(AuditAction.POST, asset, entity_type="asset", label=asset.asset_no)
        return asset

    def add_cost(self, asset_id: uuid.UUID, *, amount: Decimal, description: str | None = None) -> Asset:
        asset = self.get(asset_id)
        asset.additional_cost = money(Decimal(asset.additional_cost or 0) + money(amount))
        asset.total_cost = money(Decimal(asset.total_cost or 0) + money(amount))
        if asset.status != AssetStatus.FULLY_DEPRECIATED.value:
            asset.book_value = money(Decimal(asset.book_value or 0) + money(amount))
        self.db.flush()
        self.audit.log_action(
            AuditAction.UPDATE, asset, entity_type="asset", label=asset.asset_no, remarks=description or "cost added"
        )
        return asset

    # ---------------------------------------------------------------- transfers
    def transfer(self, asset_id: uuid.UUID, payload: dict[str, Any]) -> AssetTransfer:
        asset = self.get(asset_id)
        transfer = AssetTransfer(
            company_id=self.company_id,
            document_no=self._next_sequence(AssetTransfer, "TRF"),
            asset_id=asset.id,
            transfer_date=payload.get("transfer_date") or date.today(),
            from_branch_id=asset.branch_id,
            to_branch_id=as_uuid(payload.get("to_branch_id")),
            from_employee_id=asset.custodian_id,
            to_employee_id=as_uuid(payload.get("to_employee_id")),
            from_location=asset.location,
            to_location=payload.get("to_location"),
            from_cost_center_id=asset.cost_center_id,
            to_cost_center_id=as_uuid(payload.get("to_cost_center_id")),
            reason=payload.get("reason"),
            status="approved" if payload.get("approve") else "draft",
            approved_by_id=self.user_id if payload.get("approve") else None,
            approved_at=datetime.now(UTC) if payload.get("approve") else None,
            received_by_name=payload.get("received_by_name"),
            notes=payload.get("notes"),
        )
        self.db.add(transfer)
        self.db.flush()
        if transfer.status == "approved":
            asset.branch_id = transfer.to_branch_id or asset.branch_id
            asset.location = transfer.to_location or asset.location
            asset.custodian_id = transfer.to_employee_id or asset.custodian_id
            asset.cost_center_id = transfer.to_cost_center_id or asset.cost_center_id
        self.db.flush()
        return transfer

    def _next_sequence(self, model: Any, prefix: str) -> str:
        count = self.db.execute(
            select(func.count()).select_from(model).where(model.company_id == self.company_id)
        ).scalar_one()
        return f"{prefix}-{int(count) + 1:05d}"

    # ------------------------------------------------------------- maintenance
    def record_maintenance(self, asset_id: uuid.UUID, payload: dict[str, Any]) -> AssetMaintenance:
        asset = self.get(asset_id)
        parts = money(payload.get("parts_cost"))
        labour = money(payload.get("labour_cost"))
        other = money(payload.get("other_cost"))
        maintenance = AssetMaintenance(
            company_id=self.company_id,
            document_no=self._next_sequence(AssetMaintenance, "MNT"),
            asset_id=asset.id,
            maintenance_type=payload.get("maintenance_type", "corrective"),
            reported_date=payload.get("reported_date") or date.today(),
            scheduled_date=payload.get("scheduled_date"),
            completed_date=payload.get("completed_date"),
            description=payload["description"],
            performed_by=payload.get("performed_by"),
            technician_id=as_uuid(payload.get("technician_id")),
            supplier_id=as_uuid(payload.get("supplier_id")),
            parts_cost=parts,
            labour_cost=labour,
            other_cost=other,
            total_cost=money(parts + labour + other),
            downtime_hours=_decimal(payload.get("downtime_hours")),
            status=payload.get("status", "completed" if payload.get("completed_date") else "open"),
            expense_account_id=as_uuid(payload.get("expense_account_id")),
            notes=payload.get("notes"),
        )
        self.db.add(maintenance)
        self.db.flush()
        if maintenance.status == "open":
            asset.status = AssetStatus.UNDER_MAINTENANCE.value
        elif asset.status == AssetStatus.UNDER_MAINTENANCE.value and maintenance.status == "completed":
            asset.status = AssetStatus.ACTIVE.value
        self.db.flush()
        return maintenance

    def maintenance_history(self, asset_id: uuid.UUID) -> list[AssetMaintenance]:
        return list(
            self.db.execute(
                select(AssetMaintenance)
                .where(AssetMaintenance.company_id == self.company_id, AssetMaintenance.asset_id == asset_id)
                .order_by(AssetMaintenance.reported_date.desc())
            ).scalars().all()
        )

    # ---------------------------------------------------------------- disposal
    def dispose(self, asset_id: uuid.UUID, payload: dict[str, Any]) -> AssetDisposal:
        asset = self.get(asset_id)
        if asset.status == AssetStatus.DISPOSED.value:
            raise BusinessRuleError("This asset has already been disposed of")
        proceeds = money(payload.get("proceeds_amount"))
        removal_cost = money(payload.get("removal_cost"))
        net_book_value = money(asset.book_value)
        gain_loss = money(proceeds - removal_cost - net_book_value)
        disposal = AssetDisposal(
            company_id=self.company_id,
            document_no=self._next_sequence(AssetDisposal, "DIS"),
            asset_id=asset.id,
            disposal_date=payload.get("disposal_date") or date.today(),
            disposal_type=payload.get("disposal_type", "sale"),
            proceeds_amount=proceeds,
            removal_cost=removal_cost,
            net_book_value=net_book_value,
            gain_loss_amount=gain_loss,
            buyer_name=payload.get("buyer_name"),
            reason=payload.get("reason"),
            status="draft",
            approved_by_id=self.user_id,
            approved_at=datetime.now(UTC),
        )
        self.db.add(disposal)
        self.db.flush()
        self.audit.log_create(disposal, entity_type="asset_disposal", label=disposal.document_no)
        return disposal

    def approve_disposal(self, disposal_id: uuid.UUID) -> AssetDisposal:
        disposal = self.db.execute(
            select(AssetDisposal).where(
                AssetDisposal.company_id == self.company_id, AssetDisposal.id == disposal_id
            )
        ).scalars().first()
        if disposal is None:
            raise NotFoundError("Disposal not found")
        if disposal.status == "posted":
            raise BusinessRuleError("This disposal is already posted")
        asset = self.get(disposal.asset_id)
        from app.services.posting_service import DocumentPostingContext, PostingService

        posting = PostingService(self.db, self.company_id)
        asset_account = (
            posting.account_by_id(asset.asset_account_id)
            if asset.asset_account_id
            else posting.resolve_account("fixed_asset", document_type="asset_disposal", fallback_code="1510")
        )
        accumulated_account = (
            posting.account_by_id(asset.accumulated_depreciation_account_id)
            if asset.accumulated_depreciation_account_id
            else posting.resolve_account(
                "accumulated_depreciation", document_type="asset_disposal", fallback_code="1330"
            )
        )
        gain_account = posting.resolve_account("asset_disposal_gain", document_type="asset_disposal", fallback_code="4230")
        loss_account = posting.resolve_account("asset_disposal_loss", document_type="asset_disposal", fallback_code="5220")
        cash_account = posting.resolve_account("cash", document_type="asset_disposal", fallback_code="1110")

        lines: list[EntryLine] = []
        accumulated = money(asset.accumulated_depreciation)
        if accumulated > 0:
            lines.append(
                EntryLine(
                    account_id=accumulated_account.id,
                    debit=accumulated,
                    description=f"Accumulated depreciation {asset.asset_no}",
                )
            )
        if disposal.proceeds_amount > 0:
            lines.append(
                EntryLine(
                    account_id=cash_account.id,
                    debit=money(disposal.proceeds_amount),
                    description=f"Proceeds {asset.asset_no}",
                )
            )
        if disposal.removal_cost > 0:
            lines.append(
                EntryLine(
                    account_id=loss_account.id,
                    debit=money(disposal.removal_cost),
                    description="Removal cost",
                )
            )
        lines.append(
            EntryLine(
                account_id=asset_account.id,
                credit=money(asset.total_cost),
                description=f"Disposal of {asset.asset_no}",
            )
        )
        gain_loss = money(disposal.gain_loss_amount)
        if gain_loss > 0:
            lines.append(
                EntryLine(account_id=gain_account.id, credit=gain_loss, description="Gain on disposal")
            )
        elif gain_loss < 0:
            lines.append(
                EntryLine(account_id=loss_account.id, debit=abs(gain_loss), description="Loss on disposal")
            )
        entry = posting.build_entry(
            context=DocumentPostingContext(
                document_type="asset_disposal",
                document_id=disposal.id,
                document_no=disposal.document_no,
                document_date=disposal.disposal_date,
                description=f"Disposal of asset {asset.asset_no}",
                branch_id=asset.branch_id,
            ),
            lines=lines,
            entry_type="asset_disposal",
            reference=disposal.document_no,
            auto_post=True,
            user_id=self.user_id,
        )
        disposal.status = "posted"
        disposal.journal_entry_id = entry.id
        asset.status = AssetStatus.DISPOSED.value
        asset.disposal_date = disposal.disposal_date
        asset.disposal_proceeds = money(disposal.proceeds_amount)
        asset.disposal_reason = disposal.reason
        asset.book_value = ZERO
        self.db.flush()
        self.audit.log_action(
            AuditAction.POST, disposal, entity_type="asset_disposal", label=disposal.document_no
        )
        return disposal


class DepreciationService:
    """Period depreciation runs supporting every configured method."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def run(
        self,
        *,
        period_year: int,
        period_month: int,
        branch_id: uuid.UUID | None = None,
        asset_ids: Sequence[uuid.UUID] | None = None,
        post: bool = True,
        units_produced: dict[uuid.UUID, Decimal] | None = None,
    ) -> dict[str, Any]:
        depreciation_date = date(
            period_year, period_month, 28
        )  # use a safe day inside the month when running monthly
        stmt = select(Asset).where(
            Asset.company_id == self.company_id,
            Asset.status == AssetStatus.ACTIVE.value,
        )
        if branch_id:
            stmt = stmt.where(Asset.branch_id == branch_id)
        if asset_ids:
            stmt = stmt.where(Asset.id.in_(list(asset_ids)))
        assets = list(self.db.execute(stmt).scalars().all())

        created: list[AssetDepreciation] = []
        total_amount = ZERO
        for asset in assets:
            if asset.depreciation_method == DepreciationMethod.NONE.value:
                continue
            if asset.depreciation_start_date and asset.depreciation_start_date > depreciation_date:
                continue
            existing = self.db.execute(
                select(AssetDepreciation).where(
                    AssetDepreciation.company_id == self.company_id,
                    AssetDepreciation.asset_id == asset.id,
                    AssetDepreciation.period_year == period_year,
                    AssetDepreciation.period_month == period_month,
                )
            ).scalars().first()
            if existing is not None and existing.status == "posted":
                continue
            amount = self._period_amount(
                asset, period_year=period_year, period_month=period_month,
                units_produced=(units_produced or {}).get(asset.id),
            )
            amount = money(amount)
            if amount <= 0:
                continue
            opening = money(asset.book_value)
            accumulated = money(Decimal(asset.accumulated_depreciation or 0) + amount)
            closing = money(opening - amount)
            record = existing or AssetDepreciation(
                company_id=self.company_id,
                asset_id=asset.id,
                period_year=period_year,
                period_month=period_month,
            )
            record.depreciation_date = depreciation_date
            record.opening_book_value = opening
            record.depreciation_amount = amount
            record.accumulated_depreciation = accumulated
            record.closing_book_value = closing
            record.units_produced = (units_produced or {}).get(asset.id)
            record.method = asset.depreciation_method
            record.status = "draft"
            if existing is None:
                self.db.add(record)
            self.db.flush()

            asset.accumulated_depreciation = accumulated
            asset.book_value = closing
            asset.last_depreciation_date = depreciation_date
            if closing <= ZERO:
                asset.status = AssetStatus.FULLY_DEPRECIATED.value
            created.append(record)
            total_amount += amount

        if not created:
            return {"records": [], "total_amount": str(ZERO), "journal_entry_id": None}

        journal_entry_id = None
        if post:
            journal_entry_id = self._post_run(created, depreciation_date, branch_id)
            for record in created:
                record.status = "posted"
                record.posted_by_id = self.user_id
                record.posted_at = datetime.now(UTC)
        self.db.flush()
        self.audit.record(
            action=AuditAction.POST,
            entity_type="asset_depreciation",
            entity_id=None,
            entity_label=f"{period_year}-{period_month:02d}",
            new_values={"assets": len(created), "total": str(money(total_amount))},
        )
        return {
            "records": [
                {
                    "asset_id": str(record.asset_id),
                    "amount": str(money(record.depreciation_amount)),
                    "closing_book_value": str(money(record.closing_book_value)),
                }
                for record in created
            ],
            "total_amount": str(money(total_amount)),
            "journal_entry_id": str(journal_entry_id) if journal_entry_id else None,
        }

    def _post_run(
        self, records: Sequence[AssetDepreciation], depreciation_date: date, branch_id: uuid.UUID | None
    ) -> uuid.UUID:
        from app.services.posting_service import DocumentPostingContext, PostingService

        posting = PostingService(self.db, self.company_id)
        expense_default = posting.resolve_account(
            "depreciation_expense", document_type="asset_depreciation", fallback_code="6120"
        )
        accumulated_default = posting.resolve_account(
            "accumulated_depreciation", document_type="asset_depreciation", fallback_code="1330"
        )
        lines: list[EntryLine] = []
        for record in records:
            asset = self.db.get(Asset, record.asset_id)
            if asset is None:
                continue
            expense_account_id = asset.depreciation_account_id or expense_default.id
            accumulated_account_id = asset.accumulated_depreciation_account_id or accumulated_default.id
            lines.append(
                EntryLine(
                    account_id=expense_account_id,
                    debit=money(record.depreciation_amount),
                    description=f"Depreciation {asset.asset_no} {record.period_year}-{record.period_month:02d}",
                    cost_center_id=asset.cost_center_id,
                    branch_id=asset.branch_id,
                )
            )
            lines.append(
                EntryLine(
                    account_id=accumulated_account_id,
                    credit=money(record.depreciation_amount),
                    description=f"Accumulated depreciation {asset.asset_no}",
                )
            )
        entry = posting.build_entry(
            context=DocumentPostingContext(
                document_type="asset_depreciation",
                document_id=uuid.uuid4(),
                document_no=f"DEP-{depreciation_date.year}{depreciation_date.month:02d}",
                document_date=depreciation_date,
                description="Monthly depreciation run",
                branch_id=branch_id,
            ),
            lines=lines,
            entry_type="asset_depreciation",
            reference=f"DEP-{depreciation_date.year}{depreciation_date.month:02d}",
            auto_post=True,
            user_id=self.user_id,
        )
        for record in records:
            record.journal_entry_id = entry.id
        return entry.id

    def _period_amount(
        self,
        asset: Asset,
        *,
        period_year: int,
        period_month: int,
        units_produced: Decimal | None = None,
    ) -> Decimal:
        method = asset.depreciation_method
        depreciable = money(Decimal(asset.total_cost or 0) - Decimal(asset.salvage_value or 0))
        already = money(asset.accumulated_depreciation)
        remaining = money(depreciable - already)
        if remaining <= 0:
            return ZERO

        if method == DepreciationMethod.STRAIGHT_LINE.value:
            months = int(asset.useful_life_years or 0) * 12 + int(asset.useful_life_months or 0)
            if months <= 0:
                return ZERO
            return money(min(depreciable / Decimal(months), remaining))

        if method in {DepreciationMethod.DECLINING_BALANCE.value, DepreciationMethod.DOUBLE_DECLINING.value}:
            rate = _decimal(asset.declining_rate)
            if rate <= 0:
                years = int(asset.useful_life_years or 5)
                rate = Decimal("200") if method == DepreciationMethod.DOUBLE_DECLINING.value else Decimal("100")
                rate = rate / Decimal(years)
            monthly_rate = rate / Decimal("100") / Decimal("12")
            return money(min(money(Decimal(asset.book_value) * monthly_rate), remaining))

        if method == DepreciationMethod.UNITS_OF_PRODUCTION.value:
            expected = _decimal(asset.total_units_expected)
            produced = _decimal(units_produced)
            if expected <= 0 or produced <= 0:
                return ZERO
            return money(min(depreciable * produced / expected, remaining))

        return ZERO

    def schedule(self, asset_id: uuid.UUID, periods: int = 12) -> list[dict[str, Any]]:
        """Project the next ``periods`` months of depreciation for an asset."""
        asset = self.db.execute(
            select(Asset).where(Asset.company_id == self.company_id, Asset.id == asset_id)
        ).scalars().first()
        if asset is None:
            raise NotFoundError("Asset not found")
        projected: list[dict[str, Any]] = []
        book_value = money(asset.book_value)
        accumulated = money(asset.accumulated_depreciation)
        original_accumulated = accumulated
        current = asset.last_depreciation_date or asset.depreciation_start_date or date.today()
        original_book_value = asset.book_value
        for index in range(periods):
            month = current.month + index + 1
            year = current.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            asset.book_value = book_value
            asset.accumulated_depreciation = accumulated
            amount = money(
                self._period_amount(asset, period_year=year, period_month=month)
            )
            if amount <= 0:
                break
            accumulated = money(accumulated + amount)
            book_value = money(book_value - amount)
            projected.append(
                {
                    "period": f"{year}-{month:02d}",
                    "opening_book_value": str(money(book_value + amount)),
                    "depreciation_amount": str(amount),
                    "accumulated_depreciation": str(accumulated),
                    "closing_book_value": str(book_value),
                }
            )
        # Never leak the projection back onto the persisted entity.
        asset.book_value = original_book_value
        asset.accumulated_depreciation = original_accumulated
        return projected

    def register(self, *, branch_id: uuid.UUID | None = None, category_id: uuid.UUID | None = None) -> dict[str, Any]:
        stmt = select(Asset).where(Asset.company_id == self.company_id)
        if branch_id:
            stmt = stmt.where(Asset.branch_id == branch_id)
        if category_id:
            stmt = stmt.where(Asset.category_id == category_id)
        assets = list(self.db.execute(stmt.order_by(Asset.asset_no)).scalars().all())
        totals = {
            "cost": money(sum((Decimal(item.total_cost or 0) for item in assets), ZERO)),
            "accumulated_depreciation": money(
                sum((Decimal(item.accumulated_depreciation or 0) for item in assets), ZERO)
            ),
            "book_value": money(sum((Decimal(item.book_value or 0) for item in assets), ZERO)),
        }
        return {
            "assets": [
                {
                    "asset_no": item.asset_no,
                    "name": item.name,
                    "status": item.status,
                    "acquisition_date": item.acquisition_date.isoformat() if item.acquisition_date else None,
                    "total_cost": str(money(item.total_cost)),
                    "accumulated_depreciation": str(money(item.accumulated_depreciation)),
                    "book_value": str(money(item.book_value)),
                    "method": item.depreciation_method,
                }
                for item in assets
            ],
            "totals": {key: str(value) for key, value in totals.items()},
            "count": len(assets),
        }
