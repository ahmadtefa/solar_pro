"""Projects: phases, tasks, milestones, resources, timesheets, billing and profitability."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.coercion import as_uuid
from app.core.enums import AuditAction, BillingMethod, DocumentStatus, ProjectStatus, TaskStatus
from app.core.errors import BusinessRuleError, NotFoundError, ValidationFailure
from app.models.hr import Employee
from app.models.masterdata import Customer
from app.models.projects import (
    Milestone,
    Project,
    ProjectBillingSchedule,
    ProjectPhase,
    ProjectResourcePlan,
    ProjectTask,
    Timesheet,
    TimesheetLine,
)
from app.services.audit_service import AuditContext, AuditService
from app.services.document_service import BaseDocumentService
from app.services.numbering_service import NumberingService
from app.services.posting_service import money, quantity

ZERO = Decimal("0")
#: Fallback used to derive an hourly cost when the caller does not supply one.
DEFAULT_MONTH_DAYS = Decimal("30")
DEFAULT_DAY_HOURS = Decimal("8")


def _decimal(value: Any, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    return Decimal(str(value))


class ProjectService:
    """Project master data, planning structures and cost roll-up."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    # ------------------------------------------------------------------ basics
    def get(self, project_id: uuid.UUID | str) -> Project:
        identifier = as_uuid(project_id)
        project = self.db.execute(
            select(Project).where(Project.company_id == self.company_id, Project.id == identifier)
        ).scalars().first()
        if project is None:
            raise NotFoundError("Project not found", id=str(project_id))
        return project

    def list(
        self, *, status: str | None = None, customer_id: uuid.UUID | str | None = None, limit: int = 200
    ) -> list[Project]:
        stmt = select(Project).where(Project.company_id == self.company_id)
        if status:
            stmt = stmt.where(Project.status == status)
        if customer_id:
            stmt = stmt.where(Project.customer_id == as_uuid(customer_id))
        stmt = stmt.order_by(Project.project_no.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def create(self, payload: dict[str, Any]) -> Project:
        customer_id = as_uuid(payload.get("customer_id"))
        if customer_id is not None:
            customer = self.db.execute(
                select(Customer).where(Customer.company_id == self.company_id, Customer.id == customer_id)
            ).scalars().first()
            if customer is None:
                raise NotFoundError("Customer not found", id=str(customer_id))
        branch_id = as_uuid(payload.get("branch_id"))
        project = Project(
            company_id=self.company_id,
            project_no=payload.get("project_no")
            or NumberingService(self.db, self.company_id).next_number("project", branch_id=branch_id),
            name=payload["name"],
            name_ar=payload.get("name_ar"),
            description=payload.get("description"),
            project_type=payload.get("project_type", "general"),
            customer_id=customer_id,
            contract_id=as_uuid(payload.get("contract_id")),
            branch_id=branch_id,
            department_id=as_uuid(payload.get("department_id")),
            division_id=as_uuid(payload.get("division_id")),
            cost_center_id=as_uuid(payload.get("cost_center_id")),
            project_manager_id=as_uuid(payload.get("project_manager_id")) or self.user_id,
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            status=payload.get("status", ProjectStatus.DRAFT.value),
            priority=payload.get("priority", "normal"),
            billing_method=payload.get("billing_method", BillingMethod.FIXED_PRICE.value),
            start_date=payload.get("start_date") or date.today(),
            end_date=payload.get("end_date"),
            progress_percent=_decimal(payload.get("progress_percent")),
            contract_value=money(payload.get("contract_value")),
            currency_code=payload.get("currency_code"),
            budget_amount=money(payload.get("budget_amount")),
            budget_materials=money(payload.get("budget_materials")),
            budget_labor=money(payload.get("budget_labor")),
            budget_expenses=money(payload.get("budget_expenses")),
            budget_subcontractors=money(payload.get("budget_subcontractors")),
            retention_percent=_decimal(payload.get("retention_percent")),
            wip_account_id=as_uuid(payload.get("wip_account_id")),
            revenue_account_id=as_uuid(payload.get("revenue_account_id")),
            cost_account_id=as_uuid(payload.get("cost_account_id")),
            notes=payload.get("notes"),
            tags=payload.get("tags") or [],
        )
        self.db.add(project)
        self.db.flush()
        for index, phase in enumerate(payload.get("phases") or [], start=1):
            self.add_phase(project.id, {"sequence_no": index, **phase})
        for task in payload.get("tasks") or []:
            self.add_task(project.id, task)
        for row in payload.get("resources") or []:
            self.add_resource_plan(project.id, row)
        for index, row in enumerate(payload.get("billing_schedule") or [], start=1):
            self.add_billing_schedule(project.id, {"sequence_no": index, **row})
        self.audit.log_create(project, entity_type="project", label=project.project_no)
        return project

    def update(self, project_id: uuid.UUID | str, payload: dict[str, Any]) -> Project:
        project = self.get(project_id)
        for field in (
            "name",
            "name_ar",
            "description",
            "project_type",
            "priority",
            "billing_method",
            "end_date",
            "notes",
        ):
            if field in payload:
                setattr(project, field, payload[field])
        for field in (
            "branch_id",
            "department_id",
            "division_id",
            "cost_center_id",
            "warehouse_id",
            "project_manager_id",
            "customer_id",
            "contract_id",
            "revenue_account_id",
            "cost_account_id",
            "wip_account_id",
        ):
            if field in payload:
                setattr(project, field, as_uuid(payload[field]))
        for field in (
            "contract_value",
            "budget_amount",
            "budget_materials",
            "budget_labor",
            "budget_expenses",
            "budget_subcontractors",
        ):
            if field in payload:
                setattr(project, field, money(payload[field]))
        if "retention_percent" in payload:
            project.retention_percent = _decimal(payload["retention_percent"])
        if "start_date" in payload and payload["start_date"]:
            project.start_date = payload["start_date"]
        if "progress_percent" in payload:
            project.progress_percent = min(Decimal("100"), max(ZERO, _decimal(payload["progress_percent"])))
        self.audit.log_action(
            AuditAction.UPDATE, project, entity_type="project", label=project.project_no, new_values=payload
        )
        self.db.flush()
        return project

    # ------------------------------------------------------------------ status
    def change_status(self, project_id: uuid.UUID | str, status: str, *, reason: str | None = None) -> Project:
        if status not in {member.value for member in ProjectStatus}:
            raise ValidationFailure(f"Unknown project status '{status}'")
        project = self.get(project_id)
        project.status = status
        if status == ProjectStatus.ACTIVE.value and project.actual_start_date is None:
            project.actual_start_date = date.today()
        if status in {ProjectStatus.COMPLETED.value, ProjectStatus.CANCELLED.value}:
            project.actual_end_date = date.today()
        action = AuditAction.UPDATE
        if status == ProjectStatus.COMPLETED.value:
            action = AuditAction.CLOSE
        elif status == ProjectStatus.CANCELLED.value:
            action = AuditAction.CANCEL
        self.audit.log_action(action, project, entity_type="project", label=project.project_no, remarks=reason)
        self.db.flush()
        return project

    # ------------------------------------------------------------------ phases
    def add_phase(self, project_id: uuid.UUID | str, payload: dict[str, Any]) -> ProjectPhase:
        project = self.get(project_id)
        sequence = int(payload.get("sequence_no") or len(project.phases) + 1)
        phase = ProjectPhase(
            company_id=self.company_id,
            project_id=project.id,
            name=payload["name"],
            sequence_no=sequence,
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            progress_percent=_decimal(payload.get("progress_percent")),
            budget_amount=money(payload.get("budget_amount")),
            status=payload.get("status", TaskStatus.TODO.value),
            is_billable=bool(payload.get("is_billable", False)),
            billing_amount=money(payload.get("billing_amount")),
            notes=payload.get("notes"),
        )
        self.db.add(phase)
        self.db.flush()
        return phase

    def update_phase(self, phase_id: uuid.UUID | str, payload: dict[str, Any]) -> ProjectPhase:
        phase = self.db.execute(
            select(ProjectPhase).where(
                ProjectPhase.company_id == self.company_id, ProjectPhase.id == as_uuid(phase_id)
            )
        ).scalars().first()
        if phase is None:
            raise NotFoundError("Project phase not found")
        if "progress_percent" in payload:
            phase.progress_percent = min(Decimal("100"), max(ZERO, _decimal(payload["progress_percent"])))
        for field in ("name", "status", "start_date", "end_date", "notes"):
            if field in payload:
                setattr(phase, field, payload[field])
        if "budget_amount" in payload:
            phase.budget_amount = money(payload["budget_amount"])
        if "is_billable" in payload:
            phase.is_billable = bool(payload["is_billable"])
        if "billing_amount" in payload:
            phase.billing_amount = money(payload["billing_amount"])
        self.db.flush()
        return phase

    # ------------------------------------------------------------------- tasks
    def add_task(self, project_id: uuid.UUID | str, payload: dict[str, Any]) -> ProjectTask:
        project = self.get(project_id)
        phase_id = as_uuid(payload.get("phase_id"))
        task = ProjectTask(
            company_id=self.company_id,
            project_id=project.id,
            phase_id=phase_id,
            parent_task_id=as_uuid(payload.get("parent_task_id")),
            task_no=payload.get("task_no")
            or NumberingService(self.db, self.company_id).next_number("task", branch_id=project.branch_id),
            name=payload["name"],
            description=payload.get("description"),
            status=payload.get("status", TaskStatus.TODO.value),
            priority=payload.get("priority", "normal"),
            assignee_id=as_uuid(payload.get("assignee_id")),
            employee_id=as_uuid(payload.get("employee_id")),
            start_date=payload.get("start_date"),
            due_date=payload.get("due_date"),
            estimated_hours=_decimal(payload.get("estimated_hours")),
            actual_hours=_decimal(payload.get("actual_hours")),
            progress_percent=_decimal(payload.get("progress_percent")),
            is_billable=bool(payload.get("is_billable", False)),
            dependency_ids=payload.get("dependency_ids") or [],
            notes=payload.get("notes"),
        )
        self.db.add(task)
        self.db.flush()
        return task

    def update_task(self, task_id: uuid.UUID | str, payload: dict[str, Any]) -> ProjectTask:
        task = self.db.execute(
            select(ProjectTask).where(
                ProjectTask.company_id == self.company_id, ProjectTask.id == as_uuid(task_id)
            )
        ).scalars().first()
        if task is None:
            raise NotFoundError("Project task not found")
        for field in ("name", "description", "priority", "start_date", "due_date", "notes"):
            if field in payload:
                setattr(task, field, payload[field])
        for field in ("phase_id", "assignee_id", "employee_id"):
            if field in payload:
                setattr(task, field, as_uuid(payload[field]))
        for field in ("estimated_hours", "actual_hours", "progress_percent"):
            if field in payload:
                setattr(task, field, _decimal(payload[field]))
        if payload.get("status"):
            task.status = payload["status"]
        if task.status == TaskStatus.DONE.value or money(task.progress_percent) >= Decimal("100"):
            if task.status != TaskStatus.DONE.value:
                task.status = TaskStatus.DONE.value
            task.progress_percent = Decimal("100")
            task.completed_at = task.completed_at or datetime.now(UTC)
        self.recalculate_progress(task.project_id)
        self.db.flush()
        return task

    def complete_task(self, task_id: uuid.UUID | str, *, actual_hours: Decimal | None = None) -> ProjectTask:
        payload: dict[str, Any] = {"status": TaskStatus.DONE.value, "progress_percent": "100"}
        if actual_hours is not None:
            payload["actual_hours"] = str(actual_hours)
        return self.update_task(task_id, payload)

    # -------------------------------------------------------------- milestones
    def add_milestone(self, project_id: uuid.UUID | str, payload: dict[str, Any]) -> Milestone:
        project = self.get(project_id)
        milestone = Milestone(
            company_id=self.company_id,
            project_id=project.id,
            phase_id=as_uuid(payload.get("phase_id")),
            name=payload["name"],
            description=payload.get("description"),
            due_date=payload.get("due_date"),
            status=payload.get("status", DocumentStatus.DRAFT.value),
            is_billable=bool(payload.get("is_billable", True)),
            billing_amount=money(payload.get("billing_amount")),
        )
        self.db.add(milestone)
        self.db.flush()
        return milestone

    def complete_milestone(self, milestone_id: uuid.UUID | str) -> Milestone:
        milestone = self.db.execute(
            select(Milestone).where(
                Milestone.company_id == self.company_id, Milestone.id == as_uuid(milestone_id)
            )
        ).scalars().first()
        if milestone is None:
            raise NotFoundError("Milestone not found")
        milestone.status = DocumentStatus.APPROVED.value
        milestone.completed_at = datetime.now(UTC)
        milestone.approved_by_id = self.user_id
        self.db.flush()
        return milestone

    # ---------------------------------------------------------- billing plan
    def add_billing_schedule(self, project_id: uuid.UUID | str, payload: dict[str, Any]) -> ProjectBillingSchedule:
        project = self.get(project_id)
        percentage = _decimal(payload.get("percentage"))
        amount = money(payload.get("amount")) or money(money(project.contract_value) * percentage / Decimal("100"))
        row = ProjectBillingSchedule(
            company_id=self.company_id,
            project_id=project.id,
            sequence_no=int(payload.get("sequence_no") or len(project.billing_schedule) + 1),
            description=payload.get("description") or f"Billing {percentage}%",
            percentage=percentage,
            amount=amount,
            due_date=payload.get("due_date"),
        )
        self.db.add(row)
        self.db.flush()
        return row

    # ------------------------------------------------------------- resources
    def add_resource_plan(self, project_id: uuid.UUID | str, payload: dict[str, Any]) -> ProjectResourcePlan:
        project = self.get(project_id)
        planned_quantity = _decimal(payload.get("planned_quantity"))
        unit_cost = money(payload.get("unit_cost"))
        row = ProjectResourcePlan(
            company_id=self.company_id,
            project_id=project.id,
            phase_id=as_uuid(payload.get("phase_id")),
            resource_type=payload.get("resource_type", "material"),
            product_id=as_uuid(payload.get("product_id")),
            employee_id=as_uuid(payload.get("employee_id")),
            description=payload.get("description"),
            planned_quantity=planned_quantity,
            unit_cost=unit_cost,
            planned_cost=money(payload.get("planned_cost")) or money(planned_quantity * unit_cost),
            planned_hours=_decimal(payload.get("planned_hours")),
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            notes=payload.get("notes"),
        )
        self.db.add(row)
        self.db.flush()
        return row

    # ------------------------------------------------------------- cost roll-up
    def record_cost(
        self,
        project_id: uuid.UUID | str,
        *,
        material: Decimal | str = ZERO,
        labour: Decimal | str = ZERO,
        expense: Decimal | str = ZERO,
        subcontractor: Decimal | str = ZERO,
        resource_id: uuid.UUID | str | None = None,
        phase_id: uuid.UUID | str | None = None,
    ) -> Project:
        """Accumulate actual project cost (called by purchasing/expenses/payroll)."""
        project = self.get(project_id)
        project.actual_materials = money(Decimal(project.actual_materials or 0) + _decimal(material))
        project.actual_labor = money(Decimal(project.actual_labor or 0) + _decimal(labour))
        project.actual_expenses = money(Decimal(project.actual_expenses or 0) + _decimal(expense))
        project.actual_subcontractors = money(Decimal(project.actual_subcontractors or 0) + _decimal(subcontractor))
        resource = None
        if resource_id is not None:
            resource = self.db.execute(
                select(ProjectResourcePlan).where(
                    ProjectResourcePlan.company_id == self.company_id,
                    ProjectResourcePlan.id == as_uuid(resource_id),
                )
            ).scalars().first()
        if resource is not None:
            resource.actual_quantity = quantity(Decimal(resource.actual_quantity or 0) + _decimal(material) / (money(resource.unit_cost) or Decimal("1")))
            resource.actual_cost = money(Decimal(resource.actual_cost or 0) + _decimal(material) + _decimal(labour) + _decimal(expense))
        phase = None
        if phase_id is not None:
            phase = self.db.execute(
                select(ProjectPhase).where(
                    ProjectPhase.company_id == self.company_id, ProjectPhase.id == as_uuid(phase_id)
                )
            ).scalars().first()
        elif resource is not None and resource.phase_id is not None:
            phase = self.db.get(ProjectPhase, resource.phase_id)
        if phase is not None:
            phase.actual_amount = money(
                Decimal(phase.actual_amount or 0) + _decimal(material) + _decimal(labour) + _decimal(expense)
            )
        self.db.flush()
        return project

    def recalculate_progress(self, project_id: uuid.UUID | str) -> Project:
        project = self.get(project_id)
        if project.tasks:
            total = sum((money(task.progress_percent) for task in project.tasks), ZERO)
            project.progress_percent = money(total / Decimal(len(project.tasks)))
        elif project.phases:
            total = sum((money(phase.progress_percent) for phase in project.phases), ZERO)
            project.progress_percent = money(total / Decimal(len(project.phases)))
        for phase in project.phases:
            phase_tasks = [task for task in project.tasks if task.phase_id == phase.id]
            if phase_tasks:
                phase.progress_percent = money(
                    sum((money(task.progress_percent) for task in phase_tasks), ZERO) / Decimal(len(phase_tasks))
                )
        if project.phases and all(money(phase.progress_percent) >= Decimal("100") for phase in project.phases):
            if project.status == ProjectStatus.ACTIVE.value:
                project.status = ProjectStatus.COMPLETED.value
                project.actual_end_date = project.actual_end_date or date.today()
        self.db.flush()
        return project

    # ---------------------------------------------------------- profitability
    def profitability(self, project_id: uuid.UUID | str) -> dict[str, Any]:
        project = self.get(project_id)
        actual_cost = money(
            Decimal(project.actual_materials or 0)
            + Decimal(project.actual_labor or 0)
            + Decimal(project.actual_expenses or 0)
            + Decimal(project.actual_subcontractors or 0)
        )
        budget_cost = money(
            Decimal(project.budget_materials or 0)
            + Decimal(project.budget_labor or 0)
            + Decimal(project.budget_expenses or 0)
            + Decimal(project.budget_subcontractors or 0)
        )
        revenue = money(project.invoiced_amount)
        received = money(project.received_amount)
        profit = money(revenue - actual_cost)
        return {
            "project": project.project_no,
            "name": project.name,
            "status": project.status,
            "progress_percent": str(money(project.progress_percent)),
            "contract_value": str(money(project.contract_value)),
            "invoiced_amount": str(revenue),
            "received_amount": str(received),
            "outstanding_amount": str(money(revenue - received)),
            "retention_amount": str(money(project.retention_amount)),
            "budget_cost": str(budget_cost),
            "actual_cost": str(actual_cost),
            "budget_materials": str(money(project.budget_materials)),
            "actual_materials": str(money(project.actual_materials)),
            "budget_labor": str(money(project.budget_labor)),
            "actual_labor": str(money(project.actual_labor)),
            "budget_expenses": str(money(project.budget_expenses)),
            "actual_expenses": str(money(project.actual_expenses)),
            "budget_subcontractors": str(money(project.budget_subcontractors)),
            "actual_subcontractors": str(money(project.actual_subcontractors)),
            "cost_variance": str(money(budget_cost - actual_cost)),
            "gross_profit": str(profit),
            "margin_percent": str(money(profit / revenue * Decimal("100"))) if revenue else "0",
            "cost_to_contract_percent": str(money(actual_cost / money(project.contract_value) * Decimal("100")))
            if money(project.contract_value)
            else "0",
        }

    def billable_summary(self, project_id: uuid.UUID | str) -> dict[str, Any]:
        project = self.get(project_id)
        due_milestones = (
            self.db.execute(
                select(Milestone).where(
                    Milestone.company_id == self.company_id,
                    Milestone.project_id == project.id,
                    Milestone.is_billable.is_(True),
                    Milestone.is_billed.is_(False),
                )
            ).scalars().all()
        )
        schedule = (
            self.db.execute(
                select(ProjectBillingSchedule).where(
                    ProjectBillingSchedule.company_id == self.company_id,
                    ProjectBillingSchedule.project_id == project.id,
                    ProjectBillingSchedule.is_invoiced.is_(False),
                )
            ).scalars().all()
        )
        uninvoiced_timesheets = (
            self.db.execute(
                select(Timesheet).where(
                    Timesheet.company_id == self.company_id,
                    Timesheet.project_id == project.id,
                    Timesheet.status == DocumentStatus.APPROVED.value,
                    Timesheet.is_invoiced.is_(False),
                )
            ).scalars().all()
        )
        return {
            "project": project.project_no,
            "contract_value": str(money(project.contract_value)),
            "invoiced_amount": str(money(project.invoiced_amount)),
            "unbilled_contract_amount": str(money(money(project.contract_value) - money(project.invoiced_amount))),
            "milestones_due": [
                {"id": str(row.id), "name": row.name, "amount": str(money(row.billing_amount))} for row in due_milestones
            ],
            "schedule_due": [
                {"id": str(row.id), "description": row.description, "amount": str(money(row.amount))} for row in schedule
            ],
            "timesheets_due": [
                {
                    "id": str(row.id),
                    "document_no": row.document_no,
                    "billable_amount": str(money(row.billable_amount)),
                }
                for row in uninvoiced_timesheets
            ],
            "unbilled_timesheet_amount": str(
                money(sum((money(row.billable_amount) for row in uninvoiced_timesheets), ZERO))
            ),
        }


class TimesheetService(BaseDocumentService):
    """Employee timesheets: hours per project/task, cost and billable value."""

    document_type = "timesheet"
    model = Timesheet
    line_model = TimesheetLine
    line_relationship = "lines"
    permission_entity = "timesheet"
    permission_module = "projects"
    requires_lines = True

    def create(self, payload: dict[str, Any]) -> Timesheet:
        employee_id = as_uuid(payload["employee_id"])
        employee = self.db.execute(
            select(Employee).where(Employee.company_id == self.company_id, Employee.id == employee_id)
        ).scalars().first()
        if employee is None:
            raise NotFoundError("Employee not found", id=str(employee_id))
        project_id = as_uuid(payload.get("project_id"))
        if project_id is not None:
            ProjectService(self.db, self.company_id, user_id=self.user_id).get(project_id)
        lines_input = payload.get("lines") or []
        if not lines_input:
            raise ValidationFailure("A timesheet needs at least one line")
        period_start = payload.get("period_start") or date.today()
        period_end = payload.get("period_end") or period_start
        if period_end < period_start:
            raise ValidationFailure("The period end cannot be before the period start")
        default_rate = money(payload.get("hourly_rate")) or self.default_hourly_rate(employee)
        timesheet = Timesheet(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            employee_id=employee.id,
            user_id=employee.user_id,
            project_id=project_id,
            period_start=period_start,
            period_end=period_end,
            hourly_rate=default_rate,
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
            created_by_id=self.user_id,
        )
        self.db.add(timesheet)
        self.db.flush()
        for index, item in enumerate(lines_input, start=1):
            work_date = item.get("work_date") or period_start
            if work_date < period_start or work_date > period_end:
                raise ValidationFailure(
                    f"Line {index}: the work date must fall inside the timesheet period",
                    work_date=str(work_date),
                )
            hours = quantity(item.get("hours"))
            if hours <= 0:
                raise ValidationFailure(f"Line {index}: hours must be greater than zero")
            overtime = quantity(item.get("overtime_hours"))
            rate = money(item.get("hourly_rate")) or default_rate
            cost_rate = money(item.get("cost_rate")) or rate
            is_billable = bool(item.get("is_billable", True))
            row = TimesheetLine(
                company_id=self.company_id,
                timesheet_id=timesheet.id,
                work_date=work_date,
                project_id=as_uuid(item.get("project_id")) or project_id,
                task_id=as_uuid(item.get("task_id")),
                activity=item.get("activity"),
                hours=hours,
                overtime_hours=overtime,
                is_billable=is_billable,
                hourly_rate=rate,
                cost_amount=money(cost_rate * (hours + overtime)),
                billable_amount=money(rate * (hours + overtime)) if is_billable else ZERO,
                cost_center_id=as_uuid(item.get("cost_center_id")),
                notes=item.get("notes"),
            )
            self.db.add(row)
        self.db.flush()
        self._recalculate(timesheet)
        self.audit.log_create(timesheet, entity_type="timesheet", label=timesheet.document_no)
        return timesheet

    @staticmethod
    def default_hourly_rate(employee: Employee) -> Decimal:
        """Derive an hourly cost from the employee's salary when none is supplied."""
        salary = money(
            Decimal(employee.basic_salary or 0)
            + Decimal(getattr(employee, "housing_allowance", 0) or 0)
            + Decimal(getattr(employee, "transport_allowance", 0) or 0)
            + Decimal(getattr(employee, "other_allowances", 0) or 0)
        )
        return money(salary / DEFAULT_MONTH_DAYS / DEFAULT_DAY_HOURS)

    def _recalculate(self, timesheet: Timesheet) -> Timesheet:
        lines = list(timesheet.lines)
        timesheet.total_hours = quantity(sum((money(line.hours) for line in lines), ZERO))
        timesheet.billable_hours = quantity(
            sum((money(line.hours) for line in lines if line.is_billable), ZERO)
        )
        timesheet.overtime_hours = quantity(sum((money(line.overtime_hours) for line in lines), ZERO))
        timesheet.total_cost = money(sum((money(line.cost_amount) for line in lines), ZERO))
        timesheet.billable_amount = money(sum((money(line.billable_amount) for line in lines), ZERO))
        self.db.flush()
        return timesheet

    def update_lines(self, timesheet_id: uuid.UUID, lines_input: Sequence[dict[str, Any]]) -> Timesheet:
        timesheet = self.get_document(timesheet_id)
        self.ensure_editable(timesheet)
        timesheet.lines.clear()
        self.db.flush()
        for index, item in enumerate(lines_input, start=1):
            hours = quantity(item.get("hours"))
            if hours <= 0:
                raise ValidationFailure(f"Line {index}: hours must be greater than zero")
            rate = money(item.get("hourly_rate")) or money(timesheet.hourly_rate)
            row = TimesheetLine(
                company_id=self.company_id,
                timesheet_id=timesheet.id,
                work_date=item.get("work_date") or timesheet.period_start,
                project_id=as_uuid(item.get("project_id")) or timesheet.project_id,
                task_id=as_uuid(item.get("task_id")),
                activity=item.get("activity"),
                hours=hours,
                overtime_hours=quantity(item.get("overtime_hours")),
                is_billable=bool(item.get("is_billable", True)),
                hourly_rate=rate,
                cost_amount=money(rate * (hours + quantity(item.get("overtime_hours")))),
                billable_amount=money(rate * (hours + quantity(item.get("overtime_hours"))))
                if item.get("is_billable", True)
                else ZERO,
                cost_center_id=as_uuid(item.get("cost_center_id")),
                notes=item.get("notes"),
            )
            self.db.add(row)
            timesheet.lines.append(row)
        self.db.flush()
        return self._recalculate(timesheet)

    def approve(self, document: Any) -> Any:
        """Approve the timesheet and roll the labour cost into the project/task."""
        timesheet = super().approve(document)
        project_service = ProjectService(self.db, self.company_id, user_id=self.user_id)
        for line in timesheet.lines:
            if line.task_id:
                task = self.db.get(ProjectTask, line.task_id)
                if task is not None:
                    task.actual_hours = quantity(Decimal(task.actual_hours or 0) + money(line.hours))
            if line.project_id:
                project_service.record_cost(
                    line.project_id,
                    labour=money(line.cost_amount),
                )
        if timesheet.project_id:
            project_service.recalculate_progress(timesheet.project_id)
        self.db.flush()
        return timesheet

    def build_journal_lines(self, document: Timesheet, inventory_result: Any = None) -> list[Any]:
        """Labour cost is expensed by payroll; the timesheet only feeds project costing."""
        return []


class MilestoneService:
    """Milestone lifecycle (approval + billing readiness)."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.projects = ProjectService(db, company_id, user_id=user_id)

    def create(self, project_id: uuid.UUID | str, payload: dict[str, Any]) -> Milestone:
        return self.projects.add_milestone(project_id, payload)

    def complete(self, milestone_id: uuid.UUID | str) -> Milestone:
        return self.projects.complete_milestone(milestone_id)

    def due_for_billing(self, project_id: uuid.UUID | str) -> list[Milestone]:
        project = self.projects.get(project_id)
        return list(
            self.db.execute(
                select(Milestone).where(
                    Milestone.company_id == self.company_id,
                    Milestone.project_id == project.id,
                    Milestone.is_billable.is_(True),
                    Milestone.is_billed.is_(False),
                )
            ).scalars().all()
        )


class ProjectBillingService:
    """Turn project progress (milestones, schedule, timesheets) into sales invoices."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))
        self.projects = ProjectService(db, company_id, user_id=user_id)

    def _invoice_service(self) -> Any:
        from app.services.sales_service import SalesInvoiceService

        return SalesInvoiceService(self.db, self.company_id, user_id=self.user_id)

    def create_invoice(
        self,
        project_id: uuid.UUID | str,
        payload: dict[str, Any],
        *,
        post: bool = False,
        allow_credit_override: bool = False,
    ) -> Any:
        """Create (and optionally post) a project sales invoice from explicit lines."""
        project = self.projects.get(project_id)
        if project.customer_id is None:
            raise BusinessRuleError("The project has no customer to bill")
        lines = payload.get("lines") or []
        if not lines:
            raise ValidationFailure("Billing needs at least one line")
        invoice = self._invoice_service().create(
            {
                "customer_id": str(project.customer_id),
                "project_id": str(project.id),
                "branch_id": str(project.branch_id) if project.branch_id else payload.get("branch_id"),
                "warehouse_id": payload.get("warehouse_id"),
                "currency_code": payload.get("currency_code") or project.currency_code,
                "document_date": payload.get("document_date") or date.today(),
                "payment_term_id": payload.get("payment_term_id"),
                "salesperson_id": payload.get("salesperson_id"),
                "notes": payload.get("notes") or f"Billing for project {project.project_no}",
                "reference": project.project_no,
                "lines": lines,
            },
            allow_credit_override=allow_credit_override,
        )
        invoice_service = self._invoice_service()
        invoice.extra_data = {**(invoice.extra_data or {}), "project_no": project.project_no}
        if post:
            invoice_service.approve(invoice)
            invoice_service.post(invoice)
            self.apply_billing(invoice)
        self.db.flush()
        return invoice

    def apply_billing(self, invoice: Any) -> dict[str, Any]:
        """Reconcile a posted project invoice with the project totals (idempotent)."""
        from app.models.sales import SalesInvoice

        if not isinstance(invoice, SalesInvoice) or invoice.project_id is None:
            raise BusinessRuleError("Only project sales invoices can update a project")
        extra = dict(invoice.extra_data or {})
        if extra.get("billing_applied"):
            return {"applied": False, "reason": "already applied"}
        if invoice.status != DocumentStatus.POSTED.value:
            raise BusinessRuleError("Only posted invoices can be registered against a project")
        project = self.projects.get(invoice.project_id)
        # Posting a project invoice already syncs the project total; recompute here as
        # well so this method is safe to call repeatedly.
        from app.services.sales_service import SalesInvoiceService

        SalesInvoiceService(self.db, self.company_id, user_id=self.user_id).sync_project_invoiced(project.id)
        extra["billing_applied"] = True
        invoice.extra_data = extra
        self.audit.log_action(
            AuditAction.POST,
            project,
            entity_type="project_billing",
            label=invoice.document_no,
            new_values={
                "invoice_total": str(money(invoice.total_amount)),
                "invoiced_amount": str(money(project.invoiced_amount)),
            },
        )
        self.db.flush()
        return {"applied": True, "project": project.project_no, "invoiced_amount": str(money(project.invoiced_amount))}

    def bill_milestone(
        self,
        milestone_id: uuid.UUID | str,
        *,
        product_id: uuid.UUID | str,
        tax_id: uuid.UUID | str | None = None,
        quantity_value: Decimal | str = Decimal("1"),
        post: bool = False,
        allow_credit_override: bool = False,
    ) -> Any:
        milestone = self.db.execute(
            select(Milestone).where(
                Milestone.company_id == self.company_id, Milestone.id == as_uuid(milestone_id)
            )
        ).scalars().first()
        if milestone is None:
            raise NotFoundError("Milestone not found")
        if milestone.is_billed:
            raise BusinessRuleError("This milestone was already billed")
        amount = money(milestone.billing_amount)
        if amount <= 0:
            raise BusinessRuleError("The milestone has no billable amount")
        project = self.projects.get(milestone.project_id)
        invoice = self.create_invoice(
            project.id,
            {
                "lines": [
                    {
                        "product_id": str(product_id),
                        "description": f"Milestone {milestone.name}",
                        "quantity": str(quantity_value),
                        "unit_price": str(money(amount / _decimal(quantity_value, "1"))),
                        "tax_id": str(tax_id) if tax_id else None,
                    }
                ],
                "notes": f"Milestone billing: {milestone.name}",
            },
            post=post,
            allow_credit_override=allow_credit_override,
        )
        milestone.is_billed = True
        milestone.invoice_id = invoice.id
        self.db.flush()
        return invoice

    def bill_progress(
        self,
        project_id: uuid.UUID | str,
        *,
        percentage: Decimal | str,
        product_id: uuid.UUID | str,
        apply_retention: bool = False,
        tax_id: uuid.UUID | str | None = None,
        post: bool = False,
        allow_credit_override: bool = False,
    ) -> Any:
        project = self.projects.get(project_id)
        contract_value = money(project.contract_value)
        if contract_value <= 0:
            raise BusinessRuleError("The project has no contract value to bill against")
        percent = _decimal(percentage)
        if percent <= 0 or percent > 100:
            raise ValidationFailure("The billing percentage must be between 0 and 100")
        gross = money(contract_value * percent / Decimal("100"))
        remaining = money(contract_value - money(project.invoiced_amount) - money(project.retention_amount))
        if gross > remaining + Decimal("0.01"):
            raise BusinessRuleError(
                "The requested progress billing exceeds the unbilled contract value",
                requested=str(gross),
                remaining=str(remaining),
            )
        retention = ZERO
        net_amount = gross
        if apply_retention and money(project.retention_percent) > 0:
            retention = money(gross * money(project.retention_percent) / Decimal("100"))
            net_amount = money(gross - retention)
        invoice = self.create_invoice(
            project.id,
            {
                "lines": [
                    {
                        "product_id": str(product_id),
                        "description": f"Progress billing {money(percent)}%",
                        "quantity": "1",
                        "unit_price": str(net_amount),
                        "tax_id": str(tax_id) if tax_id else None,
                    }
                ],
                "notes": f"Progress billing {money(percent)}% of {project.project_no}",
            },
            post=post,
            allow_credit_override=allow_credit_override,
        )
        if retention > 0:
            project.retention_amount = money(Decimal(project.retention_amount or 0) + retention)
        self.db.flush()
        return invoice

    def bill_timesheets(
        self,
        project_id: uuid.UUID | str,
        *,
        product_id: uuid.UUID | str,
        date_from: date | None = None,
        date_to: date | None = None,
        tax_id: uuid.UUID | str | None = None,
        post: bool = False,
        allow_credit_override: bool = False,
    ) -> Any:
        project = self.projects.get(project_id)
        stmt = select(Timesheet).where(
            Timesheet.company_id == self.company_id,
            Timesheet.project_id == project.id,
            Timesheet.status == DocumentStatus.APPROVED.value,
            Timesheet.is_invoiced.is_(False),
        )
        if date_from is not None:
            stmt = stmt.where(Timesheet.period_end >= date_from)
        if date_to is not None:
            stmt = stmt.where(Timesheet.period_start <= date_to)
        timesheets = list(self.db.execute(stmt).scalars().all())
        billable = [row for row in timesheets if money(row.billable_amount) > 0]
        if not billable:
            raise BusinessRuleError("There are no approved uninvoiced billable timesheets for this project")
        lines = [
            {
                "product_id": str(product_id),
                "description": f"Timesheet {row.document_no} ({money(row.billable_hours)} h)",
                "quantity": "1",
                "unit_price": str(money(row.billable_amount)),
                "tax_id": str(tax_id) if tax_id else None,
            }
            for row in billable
        ]
        invoice = self.create_invoice(
            project.id,
            {"lines": lines, "notes": "Timesheet billing"},
            post=post,
            allow_credit_override=allow_credit_override,
        )
        for row in billable:
            row.is_invoiced = True
            row.invoice_id = invoice.id
        self.db.flush()
        return invoice

