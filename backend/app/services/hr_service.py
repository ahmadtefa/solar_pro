"""Human resources and payroll.

Payroll is fully data driven: every earning and deduction is a
``SalaryComponent`` row (fixed amount, percentage of basic, hourly, or an
expression) and statutory rules are configured per company - no country
specific logic lives in the code.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.coercion import as_decimal, as_uuid
from app.core.enums import (
    AttendanceStatus,
    AuditAction,
    ContractType,
    DocumentStatus,
    EmployeeStatus,
    LeaveStatus,
    PaymentDirection,
    PaymentMethod,
    PayrollStatus,
    SalaryCalculationType,
    SalaryComponentType,
)
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, ValidationFailure
from app.models.hr import (
    AttendanceRecord,
    Employee,
    EmployeeLoan,
    EmployeeSalaryComponent,
    EmployeeShiftAssignment,
    EmploymentContract,
    Holiday,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    PayrollPeriod,
    PayrollRun,
    Payslip,
    PayslipLine,
    Position,
    SalaryComponent,
    WorkShift,
)
from app.models.platform import Branch, FiscalYear
from app.services.audit_service import AuditContext, AuditService
from app.services.document_service import BaseDocumentService
from app.services.notification_service import NotificationService
from app.services.posting_service import EntryLine, PostingService, money, quantity

ZERO = Decimal("0")


def _decimal(value: Any, default: str = "0") -> Decimal:
    return as_decimal(value, default)


class EmployeeService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    # ---------------------------------------------------------------- create
    def create(self, payload: dict[str, Any]) -> Employee:
        employee_no = payload.get("employee_no") or self._next_employee_no()
        existing = self.db.execute(
            select(Employee).where(
                Employee.company_id == self.company_id, Employee.employee_no == employee_no
            )
        ).scalars().first()
        if existing is not None:
            raise ConflictError(f"Employee number {employee_no} already exists")
        employee = Employee(
            company_id=self.company_id,
            employee_no=employee_no,
            first_name=payload["first_name"],
            middle_name=payload.get("middle_name"),
            last_name=payload.get("last_name"),
            name_ar=payload.get("name_ar"),
            national_id=payload.get("national_id"),
            passport_number=payload.get("passport_number"),
            gender=payload.get("gender"),
            birth_date=payload.get("birth_date"),
            nationality=payload.get("nationality"),
            marital_status=payload.get("marital_status"),
            email=payload.get("email"),
            phone=payload.get("phone"),
            emergency_contact_name=payload.get("emergency_contact_name"),
            emergency_contact_phone=payload.get("emergency_contact_phone"),
            address=payload.get("address"),
            city=payload.get("city"),
            country_code=payload.get("country_code"),
            branch_id=as_uuid(payload.get("branch_id")),
            department_id=as_uuid(payload.get("department_id")),
            position_id=as_uuid(payload.get("position_id")),
            manager_id=as_uuid(payload.get("manager_id")),
            user_id=as_uuid(payload.get("user_id")),
            cost_center_id=as_uuid(payload.get("cost_center_id")),
            project_id=as_uuid(payload.get("project_id")),
            hire_date=payload.get("hire_date") or date.today(),
            probation_end_date=payload.get("probation_end_date"),
            status=payload.get("status", EmployeeStatus.ACTIVE.value),
            employment_type=payload.get("employment_type", ContractType.PERMANENT.value),
            basic_salary=money(payload.get("basic_salary")),
            housing_allowance=money(payload.get("housing_allowance")),
            transport_allowance=money(payload.get("transport_allowance")),
            other_allowances=money(payload.get("other_allowances")),
            currency_code=payload.get("currency_code"),
            bank_name=payload.get("bank_name"),
            bank_account_number=payload.get("bank_account_number"),
            iban=payload.get("iban"),
            tax_registration_number=payload.get("tax_registration_number"),
            social_insurance_number=payload.get("social_insurance_number"),
            payable_account_id=as_uuid(payload.get("payable_account_id")),
            expense_account_id=as_uuid(payload.get("expense_account_id")),
            notes=payload.get("notes"),
        )
        self.db.add(employee)
        self.db.flush()
        self.audit.log_create(employee, entity_type="employee", label=employee.employee_no)
        if payload.get("shift_id"):
            self.assign_shift(
                employee.id,
                shift_id=as_uuid(payload["shift_id"]),
                effective_from=employee.hire_date,
            )
        return employee

    def _next_employee_no(self) -> str:
        count = self.db.execute(
            select(func.count()).select_from(Employee).where(Employee.company_id == self.company_id)
        ).scalar_one()
        candidate = f"EMP-{int(count) + 1:05d}"
        while self.db.execute(
            select(Employee).where(Employee.company_id == self.company_id, Employee.employee_no == candidate)
        ).scalars().first():
            count += 1
            candidate = f"EMP-{int(count) + 1:05d}"
        return candidate

    def get(self, employee_id: uuid.UUID) -> Employee:
        employee = self.db.execute(
            select(Employee).where(Employee.company_id == self.company_id, Employee.id == employee_id)
        ).scalars().first()
        if employee is None:
            raise NotFoundError("Employee not found")
        return employee

    def update(self, employee_id: uuid.UUID, payload: dict[str, Any]) -> Employee:
        employee = self.get(employee_id)
        editable = {
            "first_name", "middle_name", "last_name", "name_ar", "national_id", "passport_number", "gender",
            "birth_date", "nationality", "marital_status", "email", "personal_email", "phone",
            "emergency_contact_name", "emergency_contact_phone", "address", "city", "country_code", "branch_id",
            "department_id", "position_id", "manager_id", "cost_center_id", "project_id", "hire_date",
            "probation_end_date", "confirmation_date", "status", "employment_type", "basic_salary",
            "housing_allowance", "transport_allowance", "other_allowances", "currency_code", "bank_name",
            "bank_account_number", "iban", "tax_registration_number", "social_insurance_number",
            "payable_account_id", "expense_account_id", "notes",
        }
        for key, value in payload.items():
            if key not in editable:
                continue
            if key.endswith("_id") and value:
                value = as_uuid(value)
            if key in {"basic_salary", "housing_allowance", "transport_allowance", "other_allowances"}:
                value = money(value)
            setattr(employee, key, value)
        self.db.flush()
        self.audit.log_update(employee, entity_type="employee", label=employee.employee_no)
        return employee

    def terminate(self, employee_id: uuid.UUID, *, termination_date: date, reason: str) -> Employee:
        employee = self.get(employee_id)
        employee.status = EmployeeStatus.TERMINATED.value
        employee.termination_date = termination_date
        employee.termination_reason = reason
        for contract in employee.contracts:
            if contract.status == "active":
                contract.status = "terminated"
                contract.end_date = termination_date
        self.db.flush()
        self.audit.log_action(
            AuditAction.UPDATE, employee, entity_type="employee", label=employee.employee_no, remarks="terminated"
        )
        return employee

    # ------------------------------------------------------------- contracts
    def create_contract(self, employee_id: uuid.UUID, payload: dict[str, Any]) -> EmploymentContract:
        employee = self.get(employee_id)
        contract_no = payload.get("contract_no") or f"CT-{employee.employee_no}-{len(employee.contracts) + 1}"
        contract = EmploymentContract(
            company_id=self.company_id,
            employee_id=employee.id,
            contract_no=contract_no,
            contract_type=payload.get("contract_type", ContractType.PERMANENT.value),
            start_date=payload.get("start_date") or employee.hire_date or date.today(),
            end_date=payload.get("end_date"),
            signed_date=payload.get("signed_date"),
            position_id=as_uuid(payload.get("position_id")) or employee.position_id,
            basic_salary=money(payload.get("basic_salary") or employee.basic_salary),
            total_package=money(payload.get("total_package")),
            working_hours_per_week=_decimal(payload.get("working_hours_per_week"), "40"),
            probation_months=int(payload.get("probation_months") or 3),
            notice_period_days=int(payload.get("notice_period_days") or 30),
            annual_leave_days=int(payload.get("annual_leave_days") or 21),
            status=payload.get("status", "active"),
            terms=payload.get("terms"),
        )
        self.db.add(contract)
        self.db.flush()
        return contract

    def renew_contract(self, contract_id: uuid.UUID, *, end_date: date, new_salary: Decimal | None = None) -> EmploymentContract:
        contract = self.db.get(EmploymentContract, contract_id)
        if contract is None or contract.company_id != self.company_id:
            raise NotFoundError("Contract not found")
        contract.end_date = end_date
        if new_salary:
            contract.basic_salary = money(new_salary)
        contract.status = "active"
        self.db.flush()
        return contract

    # ----------------------------------------------------------------- shifts
    def assign_shift(
        self, employee_id: uuid.UUID, *, shift_id: uuid.UUID, effective_from: date, effective_to: date | None = None
    ) -> EmployeeShiftAssignment:
        assignment = EmployeeShiftAssignment(
            company_id=self.company_id,
            employee_id=employee_id,
            shift_id=shift_id,
            effective_from=effective_from,
            effective_to=effective_to,
            is_active=True,
        )
        self.db.add(assignment)
        self.db.flush()
        return assignment

    def current_shift(self, employee_id: uuid.UUID, *, on_date: date | None = None) -> WorkShift | None:
        on_date = on_date or date.today()
        assignment = self.db.execute(
            select(EmployeeShiftAssignment)
            .where(
                EmployeeShiftAssignment.company_id == self.company_id,
                EmployeeShiftAssignment.employee_id == employee_id,
                EmployeeShiftAssignment.is_active.is_(True),
                EmployeeShiftAssignment.effective_from <= on_date,
                (EmployeeShiftAssignment.effective_to.is_(None))
                | (EmployeeShiftAssignment.effective_to >= on_date),
            )
            .order_by(EmployeeShiftAssignment.effective_from.desc())
        ).scalars().first()
        return self.db.get(WorkShift, assignment.shift_id) if assignment else None


class AttendanceService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.employees = EmployeeService(db, company_id, user_id=user_id)

    def record(
        self,
        *,
        employee_id: uuid.UUID,
        attendance_date: date,
        check_in: time | None = None,
        check_out: time | None = None,
        status: str | None = None,
        notes: str | None = None,
    ) -> AttendanceRecord:
        record = self.db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.company_id == self.company_id,
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date == attendance_date,
            )
        ).scalars().first()
        if record is None:
            record = AttendanceRecord(
                company_id=self.company_id,
                employee_id=employee_id,
                attendance_date=attendance_date,
            )
            self.db.add(record)
        shift = self.employees.current_shift(employee_id, on_date=attendance_date)
        # The columns are timestamps: combine the day with the reported time so
        # overnight shifts and exact durations are preserved.
        if check_in is not None:
            record.check_in = (
                check_in if isinstance(check_in, datetime) else datetime.combine(attendance_date, check_in)
            )
            record.check_in_source = "manual"
        if check_out is not None:
            record.check_out = (
                check_out if isinstance(check_out, datetime) else datetime.combine(attendance_date, check_out)
            )
            record.check_out_source = "manual"

        if record.check_in and record.check_out:
            start = record.check_in
            end = record.check_out
            if end < start:  # overnight shift
                end += timedelta(days=1)
            worked = int((end - start).total_seconds() // 60)
            break_minutes = int(getattr(shift, "break_minutes", 0) or 0)
            record.worked_minutes = max(worked - break_minutes, 0)
            record.overtime_minutes = self._overtime_minutes(record, shift)
            record.late_minutes = self._late_minutes(record, shift)
            record.early_leave_minutes = self._early_leave_minutes(record, shift)
        record.status = status or self._infer_status(record, attendance_date)
        record.notes = notes or record.notes
        self.db.flush()
        return record

    def check_in(self, *, employee_id: uuid.UUID, at: datetime | None = None) -> AttendanceRecord:
        at = at or datetime.now(UTC)
        return self.record(employee_id=employee_id, attendance_date=at.date(), check_in=at.replace(microsecond=0))

    def check_out(self, *, employee_id: uuid.UUID, at: datetime | None = None) -> AttendanceRecord:
        at = at or datetime.now(UTC)
        return self.record(employee_id=employee_id, attendance_date=at.date(), check_out=at.replace(microsecond=0))

    def _overtime_minutes(self, record: AttendanceRecord, shift: WorkShift | None) -> int:
        if shift is None or record.worked_minutes is None:
            return 0
        standard = self._shift_minutes(shift)
        return max(int(record.worked_minutes) - standard, 0)

    def _late_minutes(self, record: AttendanceRecord, shift: WorkShift | None) -> int:
        if shift is None or record.check_in is None:
            return 0
        grace = int(shift.grace_minutes or 0)
        scheduled = datetime.combine(record.attendance_date, shift.start_time)
        actual = record.check_in if isinstance(record.check_in, datetime) else datetime.combine(
            record.attendance_date, record.check_in
        )
        if shift.is_night_shift and actual < scheduled:
            actual += timedelta(days=1)
        return max(int((actual - scheduled).total_seconds() // 60) - grace, 0)

    def _early_leave_minutes(self, record: AttendanceRecord, shift: WorkShift | None) -> int:
        if shift is None or record.check_out is None:
            return 0
        scheduled = datetime.combine(record.attendance_date, shift.end_time)
        actual = record.check_out if isinstance(record.check_out, datetime) else datetime.combine(
            record.attendance_date, record.check_out
        )
        if actual < scheduled and shift.is_night_shift:
            actual += timedelta(days=1)
        return max(int((scheduled - actual).total_seconds() // 60), 0)

    @staticmethod
    def _shift_minutes(shift: WorkShift) -> int:
        start = datetime.combine(date(2000, 1, 1), shift.start_time)
        end = datetime.combine(date(2000, 1, 1), shift.end_time)
        if end <= start:
            end += timedelta(days=1)
        return int((end - start).total_seconds() // 60) - int(shift.break_minutes or 0)

    def _infer_status(self, record: AttendanceRecord, attendance_date: date) -> str:
        holiday = self.db.execute(
            select(Holiday).where(
                Holiday.company_id == self.company_id, Holiday.holiday_date == attendance_date
            )
        ).scalars().first()
        if holiday is not None:
            return AttendanceStatus.HOLIDAY.value
        if record.check_in is None and record.check_out is None:
            return AttendanceStatus.ABSENT.value
        if record.late_minutes and record.late_minutes > 0:
            return AttendanceStatus.LATE.value
        if record.early_leave_minutes and record.early_leave_minutes > 0:
            return AttendanceStatus.EARLY_LEAVE.value
        return AttendanceStatus.PRESENT.value

    def summarize(self, *, employee_id: uuid.UUID, date_from: date, date_to: date) -> dict[str, Any]:
        records = self.db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.company_id == self.company_id,
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date >= date_from,
                AttendanceRecord.attendance_date <= date_to,
            )
        ).scalars().all()
        return {
            "present": sum(1 for item in records if item.status == AttendanceStatus.PRESENT.value),
            "absent": sum(1 for item in records if item.status == AttendanceStatus.ABSENT.value),
            "late": sum(1 for item in records if item.status == AttendanceStatus.LATE.value),
            "leave": sum(1 for item in records if item.status == AttendanceStatus.ON_LEAVE.value),
            "overtime_minutes": sum(int(item.overtime_minutes or 0) for item in records),
            "late_minutes": sum(int(item.late_minutes or 0) for item in records),
            "worked_minutes": sum(int(item.worked_minutes or 0) for item in records),
            "worked_days": sum(1 for item in records if (item.worked_minutes or 0) > 0),
        }


class LeaveService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))
        self.notifications = NotificationService(db, company_id)

    # -------------------------------------------------------------- balances
    def ensure_balance(self, *, employee_id: uuid.UUID, leave_type_id: uuid.UUID, year: int) -> LeaveBalance:
        balance = self.db.execute(
            select(LeaveBalance).where(
                LeaveBalance.company_id == self.company_id,
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.year == year,
            )
        ).scalars().first()
        if balance is not None:
            return balance
        leave_type = self.db.get(LeaveType, leave_type_id)
        if leave_type is None:
            raise NotFoundError("Leave type not found")
        fiscal_year = self.db.execute(
            select(FiscalYear).where(FiscalYear.company_id == self.company_id, FiscalYear.code == str(year))
        ).scalars().first()
        balance = LeaveBalance(
            company_id=self.company_id,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            fiscal_year_id=fiscal_year.id if fiscal_year else None,
            year=year,
            entitled_days=quantity(leave_type.days_per_year),
        )
        self.db.add(balance)
        self.db.flush()
        return balance

    def accrue(self, *, employee_id: uuid.UUID, leave_type_id: uuid.UUID, year: int, days: Decimal) -> LeaveBalance:
        balance = self.ensure_balance(employee_id=employee_id, leave_type_id=leave_type_id, year=year)
        balance.accrued_days = quantity(Decimal(balance.accrued_days or 0) + days)
        self.db.flush()
        return balance

    def balance_summary(self, *, employee_id: uuid.UUID, year: int | None = None) -> list[dict[str, Any]]:
        year = year or date.today().year
        rows = self.db.execute(
            select(LeaveBalance, LeaveType)
            .join(LeaveType, LeaveType.id == LeaveBalance.leave_type_id)
            .where(
                LeaveBalance.company_id == self.company_id,
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.year == year,
            )
        ).all()
        summary = []
        for balance, leave_type in rows:
            available = (
                Decimal(balance.entitled_days or 0)
                + Decimal(balance.accrued_days or 0)
                + Decimal(balance.carried_forward_days or 0)
                + Decimal(balance.adjustment_days or 0)
                - Decimal(balance.used_days or 0)
                - Decimal(balance.pending_days or 0)
            )
            summary.append(
                {
                    "leave_type": leave_type.name,
                    "code": leave_type.code,
                    "entitled": str(quantity(balance.entitled_days)),
                    "accrued": str(quantity(balance.accrued_days)),
                    "used": str(quantity(balance.used_days)),
                    "pending": str(quantity(balance.pending_days)),
                    "available": str(quantity(available)),
                }
            )
        return summary

    # -------------------------------------------------------------- requests
    def request(self, payload: dict[str, Any]) -> LeaveRequest:
        employee_id = as_uuid(payload["employee_id"])
        leave_type_id = as_uuid(payload["leave_type_id"])
        start_date = payload["start_date"]
        end_date = payload.get("end_date") or start_date
        if end_date < start_date:
            raise ValidationFailure("The leave end date cannot precede the start date")
        leave_type = self.db.get(LeaveType, leave_type_id)
        if leave_type is None:
            raise NotFoundError("Leave type not found")
        requested_days = _decimal(payload.get("total_days"))
        if requested_days <= 0:
            requested_days = quantity(Decimal((end_date - start_date).days + 1))
        if payload.get("is_half_day"):
            requested_days = quantity(Decimal("0.5"))
        if leave_type.min_notice_days and (start_date - date.today()).days < int(leave_type.min_notice_days):
            raise BusinessRuleError(
                f"{leave_type.name} requires {leave_type.min_notice_days} days notice", requested_days=str(requested_days)
            )
        if leave_type.max_consecutive_days and requested_days > Decimal(leave_type.max_consecutive_days):
            raise BusinessRuleError("The request exceeds the maximum consecutive days for this leave type")

        overlapping = self.db.execute(
            select(LeaveRequest).where(
                LeaveRequest.company_id == self.company_id,
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status.in_([LeaveStatus.SUBMITTED.value, LeaveStatus.APPROVED.value]),
                LeaveRequest.start_date <= end_date,
                LeaveRequest.end_date >= start_date,
            )
        ).scalars().first()
        if overlapping is not None:
            raise ConflictError("The employee already has an approved or pending leave in this period")

        balance = self.ensure_balance(employee_id=employee_id, leave_type_id=leave_type_id, year=start_date.year)
        available = (
            Decimal(balance.entitled_days or 0)
            + Decimal(balance.accrued_days or 0)
            + Decimal(balance.carried_forward_days or 0)
            + Decimal(balance.adjustment_days or 0)
            - Decimal(balance.used_days or 0)
            - Decimal(balance.pending_days or 0)
        )
        unpaid_days = Decimal("0")
        if leave_type.is_paid and requested_days > available:
            if not payload.get("allow_unpaid"):
                raise BusinessRuleError(
                    "Insufficient leave balance",
                    available=str(quantity(available)),
                    requested=str(requested_days),
                )
            unpaid_days = quantity(requested_days - max(available, ZERO))

        request = LeaveRequest(
            company_id=self.company_id,
            request_no=self._next_request_no(),
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            start_date=start_date,
            end_date=end_date,
            total_days=requested_days,
            is_half_day=bool(payload.get("is_half_day", False)),
            reason=payload.get("reason"),
            status=LeaveStatus.SUBMITTED.value if leave_type.requires_approval else LeaveStatus.APPROVED.value,
            submitted_at=datetime.now(UTC),
            replacement_employee_id=as_uuid(payload.get("replacement_employee_id")),
            unpaid_days=unpaid_days,
            attachment_id=as_uuid(payload.get("attachment_id")),
        )
        self.db.add(request)
        self.db.flush()
        if request.status == LeaveStatus.APPROVED.value:
            self._apply_balance(request)
        else:
            balance.pending_days = quantity(Decimal(balance.pending_days or 0) + requested_days)
        self.db.flush()
        self.audit.log_create(request, entity_type="leave_request", label=request.request_no)
        return request

    def _next_request_no(self) -> str:
        count = self.db.execute(
            select(func.count()).select_from(LeaveRequest).where(LeaveRequest.company_id == self.company_id)
        ).scalar_one()
        return f"LV-{int(count) + 1:05d}"

    def _apply_balance(self, request: LeaveRequest) -> None:
        balance = self.ensure_balance(
            employee_id=request.employee_id, leave_type_id=request.leave_type_id, year=request.start_date.year
        )
        paid_days = quantity(Decimal(request.total_days or 0) - Decimal(request.unpaid_days or 0))
        balance.used_days = quantity(Decimal(balance.used_days or 0) + paid_days)
        balance.pending_days = quantity(max(Decimal(balance.pending_days or 0) - paid_days, ZERO))
        self.db.flush()

    def approve(self, request_id: uuid.UUID, *, approver_id: uuid.UUID | None = None) -> LeaveRequest:
        request = self.get(request_id)
        if request.status not in {LeaveStatus.SUBMITTED.value, LeaveStatus.DRAFT.value}:
            raise BusinessRuleError("Only submitted requests can be approved")
        request.status = LeaveStatus.APPROVED.value
        request.approved_by_id = approver_id or self.user_id
        request.approved_at = datetime.now(UTC)
        self._apply_balance(request)
        self.db.flush()
        employee = self.db.get(Employee, request.employee_id)
        if employee is not None and employee.user_id:
            self.notifications.notify_users(
                [employee.user_id],
                title="Leave request approved",
                body=f"Your leave request {request.request_no} was approved.",
                notification_type="approval",
                module="hr",
                entity_type="leave_request",
                entity_id=request.id,
            )
        self.audit.log_action(AuditAction.APPROVE, request, entity_type="leave_request", label=request.request_no)
        return request

    def reject(self, request_id: uuid.UUID, *, reason: str, rejector_id: uuid.UUID | None = None) -> LeaveRequest:
        request = self.get(request_id)
        balance = self.ensure_balance(
            employee_id=request.employee_id, leave_type_id=request.leave_type_id, year=request.start_date.year
        )
        balance.pending_days = quantity(max(Decimal(balance.pending_days or 0) - Decimal(request.total_days or 0), ZERO))
        request.status = LeaveStatus.REJECTED.value
        request.rejected_by_id = rejector_id or self.user_id
        request.rejected_at = datetime.now(UTC)
        request.rejection_reason = reason
        self.db.flush()
        self.audit.log_action(
            AuditAction.REJECT, request, entity_type="leave_request", label=request.request_no, remarks=reason
        )
        return request

    def cancel(self, request_id: uuid.UUID, *, reason: str | None = None) -> LeaveRequest:
        request = self.get(request_id)
        if request.status == LeaveStatus.APPROVED.value:
            balance = self.ensure_balance(
                employee_id=request.employee_id, leave_type_id=request.leave_type_id, year=request.start_date.year
            )
            paid_days = quantity(Decimal(request.total_days or 0) - Decimal(request.unpaid_days or 0))
            balance.used_days = quantity(max(Decimal(balance.used_days or 0) - paid_days, ZERO))
        elif request.status == LeaveStatus.SUBMITTED.value:
            balance = self.ensure_balance(
                employee_id=request.employee_id, leave_type_id=request.leave_type_id, year=request.start_date.year
            )
            balance.pending_days = quantity(
                max(Decimal(balance.pending_days or 0) - Decimal(request.total_days or 0), ZERO)
            )
        request.status = LeaveStatus.CANCELLED.value
        self.db.flush()
        return request

    def get(self, request_id: uuid.UUID) -> LeaveRequest:
        request = self.db.execute(
            select(LeaveRequest).where(
                LeaveRequest.company_id == self.company_id, LeaveRequest.id == request_id
            )
        ).scalars().first()
        if request is None:
            raise NotFoundError("Leave request not found")
        return request


class PayrollService(BaseDocumentService):
    """Configurable payroll: components -> payslips -> journal entry -> payment."""

    document_type = "payroll_run"
    model = PayrollRun
    line_model = PayslipLine
    permission_entity = "payroll_run"
    permission_module = "hr"
    requires_lines = False

    # ---------------------------------------------------------------- periods
    def create_period(self, payload: dict[str, Any]) -> PayrollPeriod:
        start = payload["period_start"]
        end = payload["period_end"]
        code = payload.get("code") or start.strftime("%Y-%m")
        existing = self.db.execute(
            select(PayrollPeriod).where(PayrollPeriod.company_id == self.company_id, PayrollPeriod.code == code)
        ).scalars().first()
        if existing is not None:
            raise ConflictError(f"Payroll period {code} already exists")
        period = PayrollPeriod(
            company_id=self.company_id,
            code=code,
            name=payload.get("name") or start.strftime("%B %Y"),
            period_start=start,
            period_end=end,
            payment_date=payload.get("payment_date") or end,
        )
        self.db.add(period)
        self.db.flush()
        return period

    # ------------------------------------------------------------------- runs
    def create_run(self, payload: dict[str, Any]) -> PayrollRun:
        period_id = as_uuid(payload.get("payroll_period_id"))
        if period_id:
            period = self.db.get(PayrollPeriod, period_id)
        else:
            period = self.create_period(payload)
        if period is None:
            raise NotFoundError("Payroll period not found")
        if period.is_closed:
            raise BusinessRuleError("This payroll period is closed")
        run = PayrollRun(
            company_id=self.company_id,
            run_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            payroll_period_id=period.id,
            branch_id=as_uuid(payload.get("branch_id")),
            department_id=as_uuid(payload.get("department_id")),
            run_date=payload.get("run_date") or date.today(),
            status=PayrollStatus.DRAFT.value,
            notes=payload.get("notes"),
        )
        self.db.add(run)
        self.db.flush()
        return run

    def employees_for_run(self, run: PayrollRun) -> list[Employee]:
        stmt = select(Employee).where(
            Employee.company_id == self.company_id,
            Employee.deleted_at.is_(None),
            Employee.status.in_(
                [EmployeeStatus.ACTIVE.value, EmployeeStatus.PROBATION.value, EmployeeStatus.ON_LEAVE.value]
            ),
        )
        if run.branch_id:
            stmt = stmt.where(Employee.branch_id == run.branch_id)
        if run.department_id:
            stmt = stmt.where(Employee.department_id == run.department_id)
        return list(self.db.execute(stmt.order_by(Employee.employee_no)).scalars().all())

    def compute(self, run_id: uuid.UUID) -> PayrollRun:
        """Generate payslips for every eligible employee."""
        run = self.get_document(run_id)
        if run.status != PayrollStatus.DRAFT.value:
            raise BusinessRuleError("Payslips can only be computed for draft runs")
        period = self.db.get(PayrollPeriod, run.payroll_period_id) if run.payroll_period_id else None
        if period is None:
            raise BusinessRuleError("The payroll run has no period")
        attendance = AttendanceService(self.db, self.company_id, user_id=self.user_id)
        leave_service = LeaveService(self.db, self.company_id, user_id=self.user_id)
        components = list(
            self.db.execute(
                select(SalaryComponent).where(
                    SalaryComponent.company_id == self.company_id, SalaryComponent.is_active.is_(True)
                ).order_by(SalaryComponent.sequence_no)
            ).scalars().all()
        )
        for payslip in list(run.payslips):
            self.db.delete(payslip)
        run.payslips.clear()
        self.db.flush()

        employees = self.employees_for_run(run)
        if not employees:
            raise BusinessRuleError("No active employees match this payroll run")
        totals = {"gross": ZERO, "deductions": ZERO, "tax": ZERO, "insurance": ZERO, "net": ZERO, "employer": ZERO}
        for employee in employees:
            payslip = self._compute_payslip(
                run=run,
                employee=employee,
                period=period,
                components=components,
                attendance=attendance,
                leave_service=leave_service,
            )
            run.payslips.append(payslip)
            totals["gross"] += money(payslip.gross_pay)
            totals["deductions"] += money(payslip.total_deductions)
            totals["tax"] += money(payslip.tax_amount)
            totals["insurance"] += money(payslip.social_insurance)
            totals["net"] += money(payslip.net_pay)
            totals["employer"] += money(payslip.employer_contributions)
        run.employee_count = len(employees)
        run.total_gross = money(totals["gross"])
        run.total_deductions = money(totals["deductions"])
        run.total_tax = money(totals["tax"])
        run.total_employer_contributions = money(totals["employer"])
        run.total_net = money(totals["net"])
        run.status = PayrollStatus.SUBMITTED.value
        self.db.flush()
        self.audit.log_action(AuditAction.UPDATE, run, entity_type="payroll_run", label=run.run_no, remarks="computed")
        return run

    def _compute_payslip(
        self,
        *,
        run: PayrollRun,
        employee: Employee,
        period: PayrollPeriod,
        components: Sequence[SalaryComponent],
        attendance: AttendanceService,
        leave_service: LeaveService,
    ) -> Payslip:
        summary = attendance.summarize(
            employee_id=employee.id, date_from=period.period_start, date_to=period.period_end
        )
        basic = money(employee.basic_salary)
        payslip = Payslip(
            company_id=self.company_id,
            payroll_run_id=run.id,
            employee_id=employee.id,
            basic_salary=basic,
            housing_allowance=money(employee.housing_allowance),
            transport_allowance=money(employee.transport_allowance),
            other_allowances=money(employee.other_allowances),
            currency_code=employee.currency_code,
            worked_days=summary["worked_days"],
            absent_days=summary["absent"],
            overtime_hours=quantity(Decimal(summary["overtime_minutes"]) / Decimal("60")),
            payment_status="pending",
        )
        self.db.add(payslip)
        self.db.flush()

        total_working_days = max(self._working_days(period), 1)
        daily_rate = money(basic / Decimal(total_working_days))

        # Configured components (allowances, deductions, taxes, contributions).
        for component in components:
            amount = self._component_amount(
                component=component,
                employee=employee,
                basic=basic,
                daily_rate=daily_rate,
                summary=summary,
            )
            if amount == 0:
                continue
            type_value = str(component.component_type)
            line = PayslipLine(
                company_id=self.company_id,
                payslip_id=payslip.id,
                component_id=component.id,
                component_code=component.code,
                component_name=component.name,
                component_type=type_value,
                calculation_basis=component.calculation_type,
                amount=money(amount),
            )
            self.db.add(line)
            payslip.lines.append(line)
            self._apply_component(payslip, type_value, amount)

        # Overtime pay from the shift's configured rate.
        shift = EmployeeService(self.db, self.company_id).current_shift(employee.id, on_date=period.period_end)
        overtime_minutes = summary["overtime_minutes"]
        if shift is not None and overtime_minutes:
            hourly_rate = money(basic / Decimal(total_working_days) / Decimal("8"))
            rate = _decimal(shift.overtime_rate, "1.5") or Decimal("1.5")
            overtime_amount = money(hourly_rate * rate * (Decimal(overtime_minutes) / Decimal("60")))
            payslip.overtime_amount = money(Decimal(payslip.overtime_amount or 0) + overtime_amount)
            self._add_line(payslip, "OVERTIME", "Overtime", SalaryComponentType.OVERTIME.value, overtime_amount)

        # Absence / unpaid leave deductions.
        if summary["absent"]:
            absence = money(daily_rate * Decimal(summary["absent"]))
            payslip.absence_deduction = money(Decimal(payslip.absence_deduction or 0) + absence)
            self._add_line(payslip, "ABSENCE", "Absence deduction", SalaryComponentType.DEDUCTION.value, -absence)

        # Outstanding loans are recovered in equal instalments.
        loan_instalment = self._loan_instalment(employee.id)
        if loan_instalment:
            payslip.loan_deduction = money(loan_instalment)
            self._add_line(payslip, "LOAN", "Loan instalment", SalaryComponentType.DEDUCTION.value, -loan_instalment)

        self._finalize_totals(payslip)
        self.db.flush()
        return payslip

    def _working_days(self, period: PayrollPeriod) -> int:
        days = 0
        cursor = period.period_start
        while cursor <= period.period_end:
            if cursor.weekday() < 5:
                days += 1
            cursor += timedelta(days=1)
        return days

    def _component_amount(
        self,
        *,
        component: SalaryComponent,
        employee: Employee,
        basic: Decimal,
        daily_rate: Decimal,
        summary: dict[str, Any],
    ) -> Decimal:
        override = self.db.execute(
            select(EmployeeSalaryComponent).where(
                EmployeeSalaryComponent.company_id == self.company_id,
                EmployeeSalaryComponent.employee_id == employee.id,
                EmployeeSalaryComponent.component_id == component.id,
                EmployeeSalaryComponent.is_active.is_(True),
            )
        ).scalars().first()
        calculation = str(component.calculation_type)
        base_amount = _decimal(override.amount if override and override.amount is not None else component.amount)
        percentage = _decimal(override.percentage if override and override.percentage is not None else component.percentage)

        if calculation == SalaryCalculationType.PERCENTAGE_OF_BASIC.value:
            return money(basic * percentage / Decimal("100"))
        if calculation == SalaryCalculationType.HOURLY.value:
            hours = Decimal(summary["worked_minutes"]) / Decimal("60")
            return money(base_amount * hours)
        if calculation == SalaryCalculationType.FORMULA.value:
            return money(self._evaluate_formula(component.formula, basic=basic, daily_rate=daily_rate, summary=summary))
        return money(base_amount)

    def _evaluate_formula(self, formula: str | None, *, basic: Decimal, daily_rate: Decimal, summary: dict[str, Any]) -> Decimal:
        """Evaluate a safe arithmetic expression with a fixed variable set."""
        if not formula:
            return ZERO
        variables = {
            "basic": basic,
            "daily_rate": daily_rate,
            "worked_days": Decimal(summary["worked_days"]),
            "absent_days": Decimal(summary["absent"]),
            "overtime_minutes": Decimal(summary["overtime_minutes"]),
            "late_minutes": Decimal(summary["late_minutes"]),
        }
        # Only arithmetic plus min()/max() on the declared variables is allowed.
        if not re.fullmatch(r"[0-9\.\+\-\*/\(\) ,a-zA-Z_]+", formula):
            raise ValidationFailure(f"Unsupported payroll formula: {formula}")
        identifiers = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", formula)) - {"min", "max", *variables}
        if identifiers:
            raise ValidationFailure(
                f"Unsupported payroll formula variable(s): {', '.join(sorted(identifiers))}"
            )
        expression = formula
        for name, value in variables.items():
            expression = re.sub(rf"\b{name}\b", str(value), expression)
        try:
            return _decimal(eval(expression, {"__builtins__": {}, "min": min, "max": max}, {}))
        except Exception as exc:  # pragma: no cover - defensive
            raise BusinessRuleError(f"Invalid payroll formula: {formula}") from exc

    def _apply_component(self, payslip: Payslip, component_type: str, amount: Decimal) -> None:
        if component_type == SalaryComponentType.ALLOWANCE.value:
            payslip.other_allowances = money(Decimal(payslip.other_allowances or 0) + amount)
        elif component_type == SalaryComponentType.BONUS.value:
            payslip.bonus_amount = money(Decimal(payslip.bonus_amount or 0) + amount)
        elif component_type == SalaryComponentType.TAX.value:
            payslip.tax_amount = money(Decimal(payslip.tax_amount or 0) + amount)
        elif component_type == SalaryComponentType.INSURANCE.value:
            payslip.social_insurance = money(Decimal(payslip.social_insurance or 0) + amount)
        elif component_type == SalaryComponentType.EMPLOYER_CONTRIBUTION.value:
            payslip.employer_contributions = money(Decimal(payslip.employer_contributions or 0) + amount)
        elif component_type == SalaryComponentType.DEDUCTION.value:
            payslip.other_deductions = money(Decimal(payslip.other_deductions or 0) + amount)

    def _add_line(self, payslip: Payslip, code: str, name: str, component_type: str, amount: Decimal) -> None:
        line = PayslipLine(
            company_id=self.company_id,
            payslip_id=payslip.id,
            component_code=code,
            component_name=name,
            component_type=component_type,
            amount=money(amount),
        )
        self.db.add(line)
        payslip.lines.append(line)

    def _loan_instalment(self, employee_id: uuid.UUID) -> Decimal:
        loan = self.db.execute(
            select(EmployeeLoan).where(
                EmployeeLoan.company_id == self.company_id,
                EmployeeLoan.employee_id == employee_id,
                EmployeeLoan.status == "active",
            )
        ).scalars().first()
        if loan is None:
            return ZERO
        return money(min(_decimal(loan.installment_amount), _decimal(loan.remaining_amount)))

    def _finalize_totals(self, payslip: Payslip) -> None:
        gross = money(
            Decimal(payslip.basic_salary or 0)
            + Decimal(payslip.housing_allowance or 0)
            + Decimal(payslip.transport_allowance or 0)
            + Decimal(payslip.other_allowances or 0)
            + Decimal(payslip.overtime_amount or 0)
            + Decimal(payslip.bonus_amount or 0)
        )
        deductions = money(
            Decimal(payslip.tax_amount or 0)
            + Decimal(payslip.social_insurance or 0)
            + Decimal(payslip.absence_deduction or 0)
            + Decimal(payslip.late_deduction or 0)
            + Decimal(payslip.loan_deduction or 0)
            + Decimal(payslip.other_deductions or 0)
        )
        payslip.gross_pay = gross
        payslip.total_deductions = deductions
        payslip.net_pay = money(gross - deductions)
        self.db.flush()

    # --------------------------------------------------------------- approval
    def approve(self, document: Any) -> Any:  # type: ignore[override]
        run = super().approve(document)
        run.status = PayrollStatus.APPROVED.value
        run.approved_by_id = self.user_id
        run.approved_at = datetime.now(UTC)
        self.db.flush()
        return run

    # ---------------------------------------------------------------- posting
    def validate_posting(self, document: PayrollRun) -> None:
        if not document.payslips:
            raise BusinessRuleError("Compute the payslips before posting the payroll run")
        if document.status not in {PayrollStatus.APPROVED.value, PayrollStatus.SUBMITTED.value}:
            raise BusinessRuleError("Only approved payroll runs can be posted")

    def build_journal_lines(self, document: PayrollRun, inventory_result: Any = None) -> list[EntryLine]:
        lines: list[EntryLine] = []
        expense_account = self.posting.resolve_account(
            "salary_expense", document_type=self.document_type, fallback_code="6110"
        )
        payable_account = self.posting.resolve_account(
            "salary_payable", document_type=self.document_type, fallback_code="2230"
        )
        for payslip in document.payslips:
            employee = self.db.get(Employee, payslip.employee_id)
            employee_expense = employee.expense_account_id if employee else None
            expense_account_id = employee_expense or expense_account.id
            payable_account_id = (employee.payable_account_id if employee else None) or payable_account.id
            if money(payslip.gross_pay) > 0:
                lines.append(
                    EntryLine(
                        account_id=expense_account_id,
                        debit=money(payslip.gross_pay),
                        description=f"Salary {employee.employee_no if employee else ''}",
                        party_type="employee",
                        party_id=payslip.employee_id,
                        cost_center_id=employee.cost_center_id if employee else None,
                        branch_id=document.branch_id,
                    )
                )
            if money(payslip.net_pay) > 0:
                lines.append(
                    EntryLine(
                        account_id=payable_account_id,
                        credit=money(payslip.net_pay),
                        description=f"Net pay {employee.employee_no if employee else ''}",
                        party_type="employee",
                        party_id=payslip.employee_id,
                    )
                )
        if money(document.total_tax) > 0:
            tax_account = self.posting.resolve_account(
                "payroll_tax", document_type=self.document_type, fallback_code="2240"
            )
            lines.append(
                EntryLine(account_id=tax_account.id, credit=money(document.total_tax), description="Payroll tax payable")
            )
        insurance_total = money(
            sum((Decimal(payslip.social_insurance or 0) for payslip in document.payslips), Decimal("0"))
        )
        if insurance_total > 0:
            insurance_account = self.posting.resolve_account(
                "social_insurance", document_type=self.document_type, fallback_code="2250"
            )
            lines.append(
                EntryLine(
                    account_id=insurance_account.id,
                    credit=insurance_total,
                    description="Social insurance payable",
                )
            )
        if money(document.total_employer_contributions) > 0:
            employer_account = self.posting.resolve_account(
                "employer_contribution", document_type=self.document_type, fallback_code="6115"
            )
            lines.append(
                EntryLine(
                    account_id=employer_account.id,
                    debit=money(document.total_employer_contributions),
                    description="Employer contributions",
                )
            )
            lines.append(
                EntryLine(
                    account_id=self.posting.resolve_account(
                        "social_insurance", document_type=self.document_type, fallback_code="2250"
                    ).id,
                    credit=money(document.total_employer_contributions),
                    description="Employer contributions payable",
                )
            )
        return lines

    def after_post(self, document: PayrollRun, inventory_result: Any = None, entry: Any = None) -> None:
        # ``status`` is driven by the shared lifecycle transition after this hook.
        document.posted_by_id = self.user_id
        document.posted_at = datetime.now(UTC)
        self.db.flush()
        self._apply_loans(document)

    def _apply_loans(self, document: PayrollRun) -> None:
        for payslip in document.payslips:
            amount = money(payslip.loan_deduction)
            if amount <= 0:
                continue
            loan = self.db.execute(
                select(EmployeeLoan).where(
                    EmployeeLoan.company_id == self.company_id,
                    EmployeeLoan.employee_id == payslip.employee_id,
                    EmployeeLoan.status == "active",
                )
            ).scalars().first()
            if loan is None:
                continue
            loan.paid_amount = money(Decimal(loan.paid_amount or 0) + amount)
            loan.remaining_amount = money(max(Decimal(loan.principal_amount or 0) - Decimal(loan.paid_amount or 0), ZERO))
            if loan.remaining_amount <= 0:
                loan.status = "settled"
        self.db.flush()

    def pay(self, run_id: uuid.UUID, *, cash_account_id: uuid.UUID | None = None, bank_account_id: uuid.UUID | None = None,
            payment_date: date | None = None, notes: str | None = None) -> Any:
        """Pay the net salaries and create the matching treasury payment."""
        from app.models.treasury import CashAccount, Payment
        from app.services.treasury_service import TreasuryService

        run = self.get_document(run_id)
        if run.status != PayrollStatus.POSTED.value:
            raise BusinessRuleError("Post the payroll run before paying it")
        if run.payment_id:
            raise BusinessRuleError("This payroll run is already paid")
        payable = self.posting.resolve_account(
            "salary_payable", document_type=self.document_type, fallback_code="2230"
        )
        treasury = TreasuryService(self.db, self.company_id, user_id=self.user_id)
        payment = treasury.create(
            {
                "direction": PaymentDirection.OUTBOUND.value,
                "payment_method": (PaymentMethod.BANK_TRANSFER.value if bank_account_id else PaymentMethod.CASH.value),
                "document_date": payment_date or date.today(),
                "amount": money(run.total_net),
                "party_type": "other",
                "party_name": "Payroll",
                "cash_account_id": str(cash_account_id) if cash_account_id else None,
                "bank_account_id": str(bank_account_id) if bank_account_id else None,
                "payment_account_id": str(payable.id),
                "branch_id": str(run.branch_id) if run.branch_id else None,
                "description": f"Salary payment {run.run_no}",
                "notes": notes,
            }
        )
        treasury.post(payment)
        run.payment_id = payment.id
        run.status = PayrollStatus.PAID.value
        for payslip in run.payslips:
            payslip.payment_status = "paid"
            payslip.payment_id = payment.id
        self.db.flush()
        return payment
