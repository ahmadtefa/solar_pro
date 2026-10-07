"""Role based dashboards built from live figures (no mock data)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import DocumentStatus, ProjectStatus, TicketStatus
from app.models.accounting import (
    Account,
    CustomerLedgerEntry,
    JournalEntry,
    JournalEntryLine,
    SupplierLedgerEntry,
)
from app.models.crm import Lead, Opportunity
from app.models.hr import AttendanceRecord, Employee, LeaveRequest, PayrollRun
from app.models.inventory import StockBalance, StockLedgerEntry
from app.models.masterdata import Customer, Product, Supplier, Warehouse
from app.models.projects import Project, ProjectTask
from app.models.purchasing import PurchaseInvoice, PurchaseOrder, PurchaseRequest, Rfq
from app.models.sales import DeliveryNote, PosShift, Quotation, SalesInvoice, SalesOrder
from app.models.service import ServiceRequest, Ticket, WorkOrder
from app.models.treasury import BankAccount, CashAccount
from app.services.inventory_service import InventoryService
from app.services.posting_service import PostingService, money


class DashboardService:
    def __init__(self, db: Session, company_id: uuid.UUID) -> None:
        self.db = db
        self.company_id = company_id
        self.posting = PostingService(db, company_id)

    # ----------------------------------------------------------------- shared
    def _sum(self, stmt) -> Decimal:
        return money(self.db.execute(stmt).scalar_one())

    def _count(self, stmt) -> int:
        return int(self.db.execute(stmt).scalar_one() or 0)

    def _sum_sales(
        self,
        model: Any,
        column: Any,
        extra_conditions: Sequence[Any] = (),
        *,
        salesperson_id: uuid.UUID | None = None,
    ) -> Decimal:
        """Sum ``column`` for a sales document, optionally scoped to one salesperson."""
        stmt = select(func.coalesce(func.sum(column), 0)).where(
            model.company_id == self.company_id,
            *extra_conditions,
        )
        if salesperson_id is not None and hasattr(model, "salesperson_id"):
            stmt = stmt.where(model.salesperson_id == salesperson_id)
        return self._sum(stmt)

    def _period(self, days: int = 30) -> tuple[date, date]:
        today = date.today()
        return today - timedelta(days=days), today

    def _account_balance_by_code(self, code: str) -> Decimal:
        account = self.db.execute(
            select(Account).where(Account.company_id == self.company_id, Account.code == code)
        ).scalars().first()
        if account is None:
            return money(0)
        debit, credit = self.posting.account_balance(account.id)
        if account.account_type in {"asset", "expense"}:
            return money(debit - credit)
        return money(credit - debit)

    # ------------------------------------------------------------ management
    def management(self) -> dict[str, Any]:
        date_from, date_to = self._period(30)
        previous_from = date_from - timedelta(days=30)

        sales = self._sum(
            select(func.coalesce(func.sum(SalesInvoice.total_amount), 0)).where(
                SalesInvoice.company_id == self.company_id,
                SalesInvoice.status == DocumentStatus.POSTED.value,
                SalesInvoice.document_date >= date_from,
                SalesInvoice.document_date <= date_to,
            )
        )
        previous_sales = self._sum(
            select(func.coalesce(func.sum(SalesInvoice.total_amount), 0)).where(
                SalesInvoice.company_id == self.company_id,
                SalesInvoice.status == DocumentStatus.POSTED.value,
                SalesInvoice.document_date >= previous_from,
                SalesInvoice.document_date < date_from,
            )
        )
        purchases = self._sum(
            select(func.coalesce(func.sum(PurchaseInvoice.total_amount), 0)).where(
                PurchaseInvoice.company_id == self.company_id,
                PurchaseInvoice.status == DocumentStatus.POSTED.value,
                PurchaseInvoice.document_date >= date_from,
                PurchaseInvoice.document_date <= date_to,
            )
        )
        receivable = self._account_balance_by_code("1210")
        payable = self._account_balance_by_code("2110")
        cash = self._account_balance_by_code("1110") + self._account_balance_by_code("1120")
        inventory_value = self._sum(
            select(func.coalesce(func.sum(StockBalance.total_value), 0)).where(
                StockBalance.company_id == self.company_id
            )
        )
        revenue = self._account_balance_by_code("4110")
        cogs = self._account_balance_by_code("5110")
        expenses = self._sum(
            select(func.coalesce(func.sum(JournalEntryLine.debit - JournalEntryLine.credit), 0))
            .join(Account, Account.id == JournalEntryLine.account_id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                JournalEntryLine.company_id == self.company_id,
                JournalEntry.status == DocumentStatus.POSTED.value,
                Account.account_type == "expense",
            )
        )
        profit = money(revenue - expenses)

        trend = self._sales_trend(months=6)
        top_customers = self._top_customers(limit=5)
        top_products = self._top_products(limit=5)
        low_stock = InventoryService(self.db, self.company_id).low_stock_items(limit=5)

        return {
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "kpis": {
                "sales": str(sales),
                "sales_previous": str(previous_sales),
                "sales_growth_percent": str(
                    ((sales - previous_sales) / previous_sales * 100).quantize(Decimal("0.01"))
                    if previous_sales
                    else Decimal("0")
                ),
                "purchases": str(purchases),
                "gross_profit": str(money(revenue - cogs)),
                "total_expenses": str(expenses),
                "net_profit": str(profit),
                "receivables": str(receivable),
                "payables": str(payable),
                "cash_position": str(money(cash)),
                "inventory_value": str(inventory_value),
            },
            "counts": {
                "customers": self._count(
                    select(func.count()).select_from(Customer).where(
                        Customer.company_id == self.company_id, Customer.deleted_at.is_(None)
                    )
                ),
                "suppliers": self._count(
                    select(func.count()).select_from(Supplier).where(
                        Supplier.company_id == self.company_id, Supplier.deleted_at.is_(None)
                    )
                ),
                "products": self._count(
                    select(func.count()).select_from(Product).where(
                        Product.company_id == self.company_id, Product.deleted_at.is_(None)
                    )
                ),
                "employees": self._count(
                    select(func.count()).select_from(Employee).where(
                        Employee.company_id == self.company_id, Employee.deleted_at.is_(None)
                    )
                ),
                "open_sales_orders": self._count(
                    select(func.count()).select_from(SalesOrder).where(
                        SalesOrder.company_id == self.company_id,
                        SalesOrder.status.in_([DocumentStatus.APPROVED.value, DocumentStatus.PARTIALLY_FULFILLED.value]),
                    )
                ),
                "open_purchase_orders": self._count(
                    select(func.count()).select_from(PurchaseOrder).where(
                        PurchaseOrder.company_id == self.company_id,
                        PurchaseOrder.status.in_([DocumentStatus.APPROVED.value, DocumentStatus.PARTIALLY_FULFILLED.value]),
                    )
                ),
                "active_projects": self._count(
                    select(func.count()).select_from(Project).where(
                        Project.company_id == self.company_id, Project.status == ProjectStatus.ACTIVE.value
                    )
                ),
                "open_tickets": self._count(
                    select(func.count()).select_from(Ticket).where(
                        Ticket.company_id == self.company_id,
                        Ticket.status.notin_([TicketStatus.CLOSED.value, TicketStatus.CANCELLED.value]),
                    )
                ),
            },
            "trends": {"sales": trend},
            "top_customers": top_customers,
            "top_products": top_products,
            "low_stock": low_stock,
        }

    def _sales_trend(self, *, months: int = 6) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(
                func.extract("year", SalesInvoice.document_date),
                func.extract("month", SalesInvoice.document_date),
                func.coalesce(func.sum(SalesInvoice.total_amount), 0),
            )
            .where(
                SalesInvoice.company_id == self.company_id,
                SalesInvoice.status == DocumentStatus.POSTED.value,
            )
            .group_by(
                func.extract("year", SalesInvoice.document_date),
                func.extract("month", SalesInvoice.document_date),
            )
            .order_by(
                func.extract("year", SalesInvoice.document_date).desc(),
                func.extract("month", SalesInvoice.document_date).desc(),
            )
            .limit(months)
        ).all()
        trend = [
            {"year": int(year), "month": int(month), "total": str(money(total))}
            for year, month, total in reversed(rows)
        ]
        return trend

    def _top_customers(self, *, limit: int = 5) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(Customer.name, func.coalesce(func.sum(SalesInvoice.total_amount), 0))
            .join(SalesInvoice, SalesInvoice.customer_id == Customer.id)
            .where(
                SalesInvoice.company_id == self.company_id,
                SalesInvoice.status == DocumentStatus.POSTED.value,
            )
            .group_by(Customer.name)
            .order_by(func.coalesce(func.sum(SalesInvoice.total_amount), 0).desc())
            .limit(limit)
        ).all()
        return [{"name": name, "total": str(money(total))} for name, total in rows]

    def _top_products(self, *, limit: int = 5) -> list[dict[str, Any]]:
        from app.models.sales import SalesInvoiceLine

        rows = self.db.execute(
            select(Product.name, func.coalesce(func.sum(SalesInvoiceLine.line_total), 0))
            .join(SalesInvoiceLine, SalesInvoiceLine.product_id == Product.id)
            .where(SalesInvoiceLine.company_id == self.company_id)
            .group_by(Product.name)
            .order_by(func.coalesce(func.sum(SalesInvoiceLine.line_total), 0).desc())
            .limit(limit)
        ).all()
        return [{"name": name, "total": str(money(total))} for name, total in rows]

    # ---------------------------------------------------------------- sales
    def sales(self, *, salesperson_id: uuid.UUID | None = None) -> dict[str, Any]:
        date_from, date_to = self._period(30)

        target_rows = self.db.execute(
            select(func.coalesce(func.sum(Product.sales_price), 0)).where(Product.company_id == self.company_id)
        ).scalar_one()

        leads_by_status = self.db.execute(
            select(Lead.status, func.count())
            .where(Lead.company_id == self.company_id)
            .group_by(Lead.status)
        ).all()
        pipeline = self.db.execute(
            select(func.coalesce(func.sum(Opportunity.amount), 0), func.count())
            .where(
                Opportunity.company_id == self.company_id,
                Opportunity.is_won.is_(False),
                Opportunity.is_lost.is_(False),
            )
        ).one()
        return {
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "kpis": {
                "sales": str(
                    self._sum(
                        select(func.coalesce(func.sum(SalesInvoice.total_amount), 0)).where(
                            SalesInvoice.company_id == self.company_id,
                            SalesInvoice.status == DocumentStatus.POSTED.value,
                            SalesInvoice.document_date >= date_from,
                            SalesInvoice.document_date <= date_to,
                        )
                    )
                ),
                "quotation_value": str(
                    self._sum_sales(
                        Quotation,
                        Quotation.total_amount,
                        (
                            Quotation.status.in_(
                                [
                                    DocumentStatus.DRAFT.value,
                                    DocumentStatus.SUBMITTED.value,
                                    DocumentStatus.APPROVED.value,
                                ]
                            ),
                        ),
                        salesperson_id=salesperson_id,
                    )
                ),
                "open_orders": str(
                    self._sum_sales(
                        SalesOrder,
                        SalesOrder.total_amount,
                        (
                            SalesOrder.status.in_(
                                [DocumentStatus.APPROVED.value, DocumentStatus.PARTIALLY_FULFILLED.value]
                            ),
                        ),
                        salesperson_id=salesperson_id,
                    )
                ),
                "deliveries_pending": str(
                    self._sum_sales(
                        DeliveryNote,
                        DeliveryNote.total_amount,
                        (DeliveryNote.status == DocumentStatus.APPROVED.value,),
                        salesperson_id=salesperson_id,
                    )
                ),
                "pipeline_value": str(money(pipeline[0])),
                "open_opportunities": int(pipeline[1] or 0),
                "receivables": str(self._account_balance_by_code("1210")),
                "commission_accrued": str(
                    self._sum(
                        select(func.coalesce(func.sum(SalesInvoice.commission_amount), 0)).where(
                            SalesInvoice.company_id == self.company_id,
                            SalesInvoice.status == DocumentStatus.POSTED.value,
                        )
                    )
                ),
            },
            "leads_by_status": [{"status": status, "count": int(count)} for status, count in leads_by_status],
            "recent_invoices": [
                {
                    "document_no": invoice.document_no,
                    "date": invoice.document_date.isoformat(),
                    "total": str(money(invoice.total_amount)),
                    "status": invoice.status,
                }
                for invoice in self.db.execute(
                    select(SalesInvoice)
                    .where(SalesInvoice.company_id == self.company_id)
                    .order_by(SalesInvoice.created_at.desc())
                    .limit(10)
                ).scalars().all()
            ],
            "target_reference": str(money(target_rows)),
        }

    # ------------------------------------------------------------ warehouse
    def warehouse(self, *, warehouse_id: uuid.UUID | None = None) -> dict[str, Any]:
        date_from, date_to = self._period(30)
        base = [
            StockLedgerEntry.company_id == self.company_id,
            StockLedgerEntry.entry_date >= date_from,
            StockLedgerEntry.entry_date <= date_to,
        ]
        if warehouse_id:
            base.append(StockLedgerEntry.warehouse_id == warehouse_id)

        receipts = self._sum(
            select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
                *base, StockLedgerEntry.direction == "in"
            )
        )
        issues = self._sum(
            select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
                *base, StockLedgerEntry.direction == "out"
            )
        )
        transfers = self.db.execute(
            select(func.count()).select_from(StockLedgerEntry).where(
                *base, StockLedgerEntry.movement_type.in_(["transfer_in", "transfer_out"])
            )
        ).scalar_one()
        low_stock_items = InventoryService(self.db, self.company_id).low_stock_items(warehouse_id, limit=10)
        inventory_value = self._sum(
            select(func.coalesce(func.sum(StockBalance.total_value), 0)).where(
                StockBalance.company_id == self.company_id,
                *([StockBalance.warehouse_id == warehouse_id] if warehouse_id else []),
            )
        )
        pending_receipts = self._count(
            select(func.count()).select_from(PurchaseOrder).where(
                PurchaseOrder.company_id == self.company_id,
                PurchaseOrder.status.in_([DocumentStatus.APPROVED.value, DocumentStatus.PARTIALLY_FULFILLED.value]),
            )
        )
        pending_deliveries = self._count(
            select(func.count()).select_from(SalesOrder).where(
                SalesOrder.company_id == self.company_id,
                SalesOrder.status.in_([DocumentStatus.APPROVED.value, DocumentStatus.PARTIALLY_FULFILLED.value]),
            )
        )
        return {
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "kpis": {
                "inventory_value": str(inventory_value),
                "received_value": str(receipts),
                "issued_value": str(issues),
                "transfer_count": int(transfers or 0),
                "pending_receipts": pending_receipts,
                "pending_deliveries": pending_deliveries,
                "low_stock_count": len(low_stock_items),
            },
            "low_stock": low_stock_items,
            "warehouses": [
                {
                    "id": warehouse.id,
                    "name": warehouse.name,
                    "value": str(
                        self._sum(
                            select(func.coalesce(func.sum(StockBalance.total_value), 0)).where(
                                StockBalance.company_id == self.company_id,
                                StockBalance.warehouse_id == warehouse.id,
                            )
                        )
                    ),
                }
                for warehouse in self.db.execute(
                    select(Warehouse).where(
                        Warehouse.company_id == self.company_id, Warehouse.deleted_at.is_(None)
                    )
                ).scalars().all()
            ],
        }

    # ----------------------------------------------------------- accounting
    def accounting(self) -> dict[str, Any]:
        date_from, date_to = self._period(30)
        revenue = self._account_balance_by_code("4110")
        cogs = self._account_balance_by_code("5110")
        expenses = self._sum(
            select(func.coalesce(func.sum(JournalEntryLine.debit - JournalEntryLine.credit), 0))
            .join(Account, Account.id == JournalEntryLine.account_id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                JournalEntryLine.company_id == self.company_id,
                JournalEntry.status == DocumentStatus.POSTED.value,
                Account.account_type == "expense",
            )
        )
        overdue_receivable = self._sum(
            select(func.coalesce(func.sum(CustomerLedgerEntry.balance), 0)).where(
                CustomerLedgerEntry.company_id == self.company_id,
                CustomerLedgerEntry.is_open.is_(True),
                CustomerLedgerEntry.due_date < date.today(),
            )
        )
        overdue_payable = self._sum(
            select(func.coalesce(func.sum(SupplierLedgerEntry.balance), 0)).where(
                SupplierLedgerEntry.company_id == self.company_id,
                SupplierLedgerEntry.is_open.is_(True),
                SupplierLedgerEntry.due_date < date.today(),
            )
        )
        return {
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "kpis": {
                "cash": str(self._account_balance_by_code("1110")),
                "bank": str(self._account_balance_by_code("1120")),
                "receivables": str(self._account_balance_by_code("1210")),
                "payables": str(self._account_balance_by_code("2110")),
                "overdue_receivables": str(overdue_receivable),
                "overdue_payables": str(money(-overdue_payable)),
                "revenue": str(revenue),
                "cogs": str(cogs),
                "expenses": str(expenses),
                "gross_profit": str(money(revenue - cogs)),
                "net_profit": str(money(revenue - expenses)),
                "vat_output": str(self._account_balance_by_code("2210")),
                "vat_input": str(self._account_balance_by_code("1410")),
                "unposted_entries": self._count(
                    select(func.count()).select_from(JournalEntry).where(
                        JournalEntry.company_id == self.company_id,
                        JournalEntry.status == DocumentStatus.DRAFT.value,
                    )
                ),
            },
            "cash_accounts": [
                {
                    "code": account.code,
                    "name": account.name,
                    "balance": str(money(account.current_balance)),
                }
                for account in self.db.execute(
                    select(CashAccount).where(CashAccount.company_id == self.company_id)
                ).scalars().all()
            ],
            "bank_accounts": [
                {
                    "code": account.code,
                    "name": account.name,
                    "bank": account.bank_name,
                    "balance": str(money(account.current_balance)),
                }
                for account in self.db.execute(
                    select(BankAccount).where(BankAccount.company_id == self.company_id)
                ).scalars().all()
            ],
            "monthly_trend": self._sales_trend(months=6),
        }

    # ----------------------------------------------------------- hr & service
    def hr(self) -> dict[str, Any]:
        date_from, date_to = self._period(30)
        headcount = self._count(
            select(func.count()).select_from(Employee).where(
                Employee.company_id == self.company_id, Employee.deleted_at.is_(None)
            )
        )
        payroll_total = self._sum(
            select(func.coalesce(func.sum(PayrollRun.total_net), 0)).where(
                PayrollRun.company_id == self.company_id
            )
        )
        pending_leave = self._count(
            select(func.count()).select_from(LeaveRequest).where(
                LeaveRequest.company_id == self.company_id,
                LeaveRequest.status.in_(["submitted", "draft"]),
            )
        )
        return {
            "kpis": {
                "headcount": headcount,
                "payroll_total": str(payroll_total),
                "pending_leave_requests": pending_leave,
                "attendance_recorded": self._count(
                    select(func.count())
                    .select_from(AttendanceRecord)
                    .where(AttendanceRecord.company_id == self.company_id)
                ),
            },
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        }

    def service(self) -> dict[str, Any]:
        return {
            "kpis": {
                "open_tickets": self._count(
                    select(func.count()).select_from(Ticket).where(
                        Ticket.company_id == self.company_id,
                        Ticket.status.notin_([TicketStatus.CLOSED.value, TicketStatus.CANCELLED.value]),
                    )
                ),
                "open_work_orders": self._count(
                    select(func.count()).select_from(WorkOrder).where(
                        WorkOrder.company_id == self.company_id,
                        WorkOrder.status.notin_([DocumentStatus.CLOSED.value, DocumentStatus.CANCELLED.value]),
                    )
                ),
                "service_requests": self._count(
                    select(func.count()).select_from(ServiceRequest).where(
                        ServiceRequest.company_id == self.company_id
                    )
                ),
                "sla_breached": self._count(
                    select(func.count()).select_from(Ticket).where(
                        Ticket.company_id == self.company_id, Ticket.is_sla_breached.is_(True)
                    )
                ),
            }
        }

    def projects(self) -> dict[str, Any]:
        projects = self.db.execute(
            select(Project).where(Project.company_id == self.company_id, Project.deleted_at.is_(None))
        ).scalars().all()
        total_budget = sum((Decimal(project.budget_amount or 0) for project in projects), Decimal("0"))
        total_actual = sum((project.total_actual_cost for project in projects), Decimal("0"))
        total_invoiced = sum((Decimal(project.invoiced_amount or 0) for project in projects), Decimal("0"))
        open_tasks = self._count(
            select(func.count()).select_from(ProjectTask).where(
                ProjectTask.company_id == self.company_id,
                ProjectTask.status.notin_(["done", "cancelled"]),
            )
        )
        return {
            "kpis": {
                "projects": len(projects),
                "active_projects": sum(1 for project in projects if project.status == ProjectStatus.ACTIVE.value),
                "total_budget": str(money(total_budget)),
                "total_actual_cost": str(money(total_actual)),
                "total_invoiced": str(money(total_invoiced)),
                "unbilled": str(money(total_actual - total_invoiced)),
                "open_tasks": open_tasks,
            },
            "projects": [
                {
                    "project_no": project.project_no,
                    "name": project.name,
                    "status": project.status,
                    "progress": str(project.progress_percent or 0),
                    "budget": str(money(project.budget_amount)),
                    "actual_cost": str(money(project.total_actual_cost)),
                    "profit": str(money(project.profit_amount)),
                }
                for project in projects[:20]
            ],
        }

    def purchasing(self) -> dict[str, Any]:
        date_from, date_to = self._period(30)
        return {
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "kpis": {
                "open_requests": self._count(
                    select(func.count()).select_from(PurchaseRequest).where(
                        PurchaseRequest.company_id == self.company_id,
                        PurchaseRequest.status.in_([DocumentStatus.DRAFT.value, DocumentStatus.SUBMITTED.value]),
                    )
                ),
                "open_rfqs": self._count(
                    select(func.count()).select_from(Rfq).where(
                        Rfq.company_id == self.company_id,
                        Rfq.status.in_([DocumentStatus.DRAFT.value, DocumentStatus.SUBMITTED.value]),
                    )
                ),
                "open_orders": self._count(
                    select(func.count()).select_from(PurchaseOrder).where(
                        PurchaseOrder.company_id == self.company_id,
                        PurchaseOrder.status.in_([DocumentStatus.APPROVED.value, DocumentStatus.PARTIALLY_FULFILLED.value]),
                    )
                ),
                "pending_receipts": self._count(
                    select(func.count()).select_from(PurchaseOrder).where(
                        PurchaseOrder.company_id == self.company_id,
                        PurchaseOrder.is_fully_received.is_(False),
                        PurchaseOrder.status != DocumentStatus.CANCELLED.value,
                    )
                ),
                "purchases_period": str(
                    self._sum(
                        select(func.coalesce(func.sum(PurchaseInvoice.total_amount), 0)).where(
                            PurchaseInvoice.company_id == self.company_id,
                            PurchaseInvoice.status == DocumentStatus.POSTED.value,
                            PurchaseInvoice.document_date >= date_from,
                            PurchaseInvoice.document_date <= date_to,
                        )
                    )
                ),
                "payables": str(self._account_balance_by_code("2110")),
                "top_suppliers": [
                    {"name": name, "total": str(money(total))}
                    for name, total in self.db.execute(
                        select(Supplier.name, func.coalesce(func.sum(PurchaseInvoice.total_amount), 0))
                        .join(PurchaseInvoice, PurchaseInvoice.supplier_id == Supplier.id)
                        .where(PurchaseInvoice.company_id == self.company_id)
                        .group_by(Supplier.name)
                        .order_by(func.coalesce(func.sum(PurchaseInvoice.total_amount), 0).desc())
                        .limit(5)
                    ).all()
                ],
            },
        }

    def pos(self, *, shift_id: uuid.UUID | None = None) -> dict[str, Any]:
        shift = self.db.get(PosShift, shift_id) if shift_id else None
        return {
            "open_shifts": self._count(
                select(func.count()).select_from(PosShift).where(
                    PosShift.company_id == self.company_id, PosShift.status == "open"
                )
            ),
            "today_sales": str(
                self._sum(
                    select(func.coalesce(func.sum(SalesInvoice.total_amount), 0)).where(
                        SalesInvoice.company_id == self.company_id,
                        SalesInvoice.sales_channel == "pos",
                        SalesInvoice.document_date == date.today(),
                    )
                )
            ),
            "shift": (
                {
                    "shift_no": shift.shift_no,
                    "total_sales": str(money(shift.total_sales)),
                    "expected_cash": str(money(shift.expected_cash)),
                    "invoice_count": shift.invoice_count,
                }
                if shift
                else None
            ),
        }

    def for_user(self, permission_codes: list[str], *, scope: str = "management") -> dict[str, Any]:
        """Return the dashboard a user has permission to see."""
        dashboards = {
            "management": ("core.dashboard.view", self.management),
            "sales": ("sales.sales_invoice.view", self.sales),
            "warehouse": ("inventory.stock_balance.view", self.warehouse),
            "accounting": ("accounting.trial_balance.view", self.accounting),
            "purchasing": ("purchasing.purchase_order.view", self.purchasing),
            "projects": ("projects.project.view", self.projects),
            "service": ("service.ticket.view", self.service),
            "hr": ("hr.employee.view", self.hr),
            "pos": ("sales.pos_sale.view", self.pos),
        }
        code, builder = dashboards.get(scope, dashboards["management"])
        if code not in permission_codes and not any(
            pattern.startswith(code.split(".")[0]) for pattern in permission_codes if "*" in pattern
        ):
            # Fall back to the management dashboard only if permitted, else KPI-less payload.
            if scope != "management":
                return {"scope": scope, "allowed": False, "message": "No dashboard available for your permissions"}
        return {"scope": scope, "allowed": True, "data": builder()}
