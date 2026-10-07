"""HR: employees, contracts, attendance, leave and payroll.

Payroll rules are fully configurable through ``SalaryComponent`` records; no
country specific rule is hardcoded in the service layer.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    AttendanceStatus,
    ContractType,
    DocumentStatus,
    EmployeeStatus,
    LeaveStatus,
    PayrollStatus,
    SalaryCalculationType,
    SalaryComponentType,
)
from app.models.base import (
    Base,
    CompanyScoped,
    JSONType,
    Money,
    Percent,
    Rate,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class Position(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "positions"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id"))
    grade: Mapped[str | None] = mapped_column(String(32))
    min_salary: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    max_salary: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    headcount_budget: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_positions_company_code"),)


class Employee(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "employees"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_no: Mapped[str] = mapped_column(String(32), nullable=False)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(250))
    national_id: Mapped[str | None] = mapped_column(String(64))
    passport_number: Mapped[str | None] = mapped_column(String(64))
    gender: Mapped[str | None] = mapped_column(String(16))
    birth_date: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(2))
    marital_status: Mapped[str | None] = mapped_column(String(24))
    photo_url: Mapped[str | None] = mapped_column(String(500))

    email: Mapped[str | None] = mapped_column(String(190))
    personal_email: Mapped[str | None] = mapped_column(String(190))
    phone: Mapped[str | None] = mapped_column(String(40))
    emergency_contact_name: Mapped[str | None] = mapped_column(String(160))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))

    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id"))
    position_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("positions.id"))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))

    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    probation_end_date: Mapped[date | None] = mapped_column(Date)
    confirmation_date: Mapped[date | None] = mapped_column(Date)
    termination_date: Mapped[date | None] = mapped_column(Date)
    termination_reason: Mapped[str | None] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(24), default=EmployeeStatus.ACTIVE.value, nullable=False, index=True)

    employment_type: Mapped[str] = mapped_column(String(24), default=ContractType.PERMANENT.value, nullable=False)
    basic_salary: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    housing_allowance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    transport_allowance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    other_allowances: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))

    bank_name: Mapped[str | None] = mapped_column(String(200))
    bank_account_number: Mapped[str | None] = mapped_column(String(64))
    iban: Mapped[str | None] = mapped_column(String(64))
    tax_registration_number: Mapped[str | None] = mapped_column(String(64))
    social_insurance_number: Mapped[str | None] = mapped_column(String(64))

    payable_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    expense_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONType)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    @property
    def full_name(self) -> str:
        return " ".join(part for part in [self.first_name, self.middle_name, self.last_name] if part)

    contracts: Mapped[list[EmploymentContract]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    salary_components: Mapped[list[EmployeeSalaryComponent]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "employee_no", name="uq_employees_company_no"),
        Index("ix_employees_company_status", "company_id", "status"),
        Index("ix_employees_department", "company_id", "department_id"),
        CheckConstraint("basic_salary >= 0", name="basic_salary_non_negative"),
    )


class EmploymentContract(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "employment_contracts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contract_no: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_type: Mapped[str] = mapped_column(String(24), default=ContractType.PERMANENT.value, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    signed_date: Mapped[date | None] = mapped_column(Date)
    position_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("positions.id"))
    basic_salary: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_package: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    working_hours_per_week: Mapped[Decimal] = mapped_column(Rate, default=Decimal("40"), nullable=False)
    probation_months: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notice_period_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    annual_leave_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("21"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    terms: Mapped[str | None] = mapped_column(Text)

    employee: Mapped[Employee] = relationship(back_populates="contracts")

    __table_args__ = (
        UniqueConstraint("company_id", "contract_no", name="uq_employment_contracts_company_no"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="dates_ordered"),
    )


class WorkShift(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "work_shifts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    grace_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    working_days: Mapped[list | None] = mapped_column(JSONType)  # ["sun","mon",...]
    overtime_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("1.5"), nullable=False)
    weekend_overtime_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("2"), nullable=False)
    is_night_shift: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_work_shifts_company_code"),)


class EmployeeShiftAssignment(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "employee_shift_assignments"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("work_shifts.id", ondelete="CASCADE"), nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_employee_shift_assignments_lookup", "company_id", "employee_id", "effective_from"),)


class AttendanceRecord(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "attendance_records"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("work_shifts.id"))
    check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_in_source: Mapped[str | None] = mapped_column(String(24))
    check_out_source: Mapped[str | None] = mapped_column(String(24))
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=AttendanceStatus.PRESENT.value, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(400))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_records_employee_day"),
        Index("ix_attendance_records_date", "company_id", "attendance_date"),
    )


class Holiday(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "holidays"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))

    __table_args__ = (Index("ix_holidays_date", "company_id", "holiday_date"),)


class LeaveType(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "leave_types"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(120))
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    days_per_year: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_notice_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_consecutive_days: Mapped[int | None] = mapped_column(Integer)
    requires_attachment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    carry_forward: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_carry_forward_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    accrual_frequency: Mapped[str] = mapped_column(String(16), default="monthly", nullable=False)
    gender_restriction: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_leave_types_company_code"),)


class LeaveRequest(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "leave_requests"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_no: Mapped[str] = mapped_column(String(64), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("leave_types.id", ondelete="RESTRICT"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_days: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    is_half_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=LeaveStatus.DRAFT.value, nullable=False, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(400))
    replacement_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id")
    )
    workflow_instance_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    unpaid_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("attachments.id"))

    __table_args__ = (
        UniqueConstraint("company_id", "request_no", name="uq_leave_requests_company_no"),
        CheckConstraint("end_date >= start_date", name="dates_ordered"),
    )


class LeaveBalance(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "leave_balances"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("leave_types.id", ondelete="CASCADE"), nullable=False
    )
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("fiscal_years.id"))
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    entitled_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    accrued_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    used_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    pending_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    carried_forward_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    adjustment_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)

    @property
    def remaining_days(self) -> Decimal:
        return (
            Decimal(self.entitled_days or 0)
            + Decimal(self.carried_forward_days or 0)
            + Decimal(self.adjustment_days or 0)
            - Decimal(self.used_days or 0)
            - Decimal(self.pending_days or 0)
        )

    __table_args__ = (
        UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_leave_balances_scope"),
    )


# --------------------------------------------------------------------------- #
# Payroll
# --------------------------------------------------------------------------- #
class SalaryComponent(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Configurable earning/deduction definition.

    ``calculation_type=formula`` accepts a safe arithmetic expression over
    ``basic``, ``gross``, ``days_worked``, ``overtime_hours`` and other component
    codes, evaluated by the payroll service - so new rules need configuration,
    not code changes.
    """

    __tablename__ = "salary_components"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    component_type: Mapped[str] = mapped_column(
        String(24), default=SalaryComponentType.ALLOWANCE.value, nullable=False
    )
    calculation_type: Mapped[str] = mapped_column(
        String(24), default=SalaryCalculationType.FIXED.value, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    formula: Mapped[str | None] = mapped_column(String(400))
    is_taxable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_insurable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    affects_net: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    sequence_no: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_salary_components_company_code"),)


class EmployeeSalaryComponent(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Employee specific override of a salary component."""

    __tablename__ = "employee_salary_components"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("salary_components.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    employee: Mapped[Employee] = relationship(back_populates="salary_components")

    __table_args__ = (Index("ix_employee_salary_components_employee", "company_id", "employee_id"),)


class PayrollPeriod(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "payroll_periods"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_period_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("fiscal_periods.id"))
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_payroll_periods_company_code"),
        CheckConstraint("period_end >= period_start", name="dates_ordered"),
    )


class PayrollRun(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "payroll_runs"

    @property
    def document_date(self) -> object:
        """Uniform document interface: the business date of this record."""
        return self.run_date

    @property
    def document_no(self) -> str:
        """Uniform document interface: this record's natural number."""
        return self.run_no

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_no: Mapped[str] = mapped_column(String(64), nullable=False)
    payroll_period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payroll_periods.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id"))
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    employee_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_gross: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_deductions: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_tax: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_employer_contributions: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_net: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=PayrollStatus.DRAFT.value, nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    workflow_instance_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    payslips: Mapped[list[Payslip]] = relationship(back_populates="payroll_run", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("company_id", "run_no", name="uq_payroll_runs_company_no"),)


class Payslip(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "payslips"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payroll_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    basic_salary: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    housing_allowance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    transport_allowance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    other_allowances: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    overtime_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    bonus_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    gross_pay: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    social_insurance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    absence_deduction: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    late_deduction: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    loan_deduction: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    other_deductions: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_deductions: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    employer_contributions: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    net_pay: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    worked_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    absent_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    paid_leave_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    unpaid_leave_days: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(24), default="unpaid", nullable=False)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    payroll_run: Mapped[PayrollRun] = relationship(back_populates="payslips")
    lines: Mapped[list[PayslipLine]] = relationship(back_populates="payslip", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("payroll_run_id", "employee_id", name="uq_payslips_run_employee"),
        Index("ix_payslips_employee", "company_id", "employee_id"),
    )


class PayslipLine(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "payslip_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payslip_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payslips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("salary_components.id"))
    component_code: Mapped[str | None] = mapped_column(String(48))
    component_name: Mapped[str] = mapped_column(String(160), nullable=False)
    component_type: Mapped[str] = mapped_column(String(24), nullable=False)
    calculation_basis: Mapped[str | None] = mapped_column(String(250))
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    payslip: Mapped[Payslip] = relationship(back_populates="lines")


class EmployeeLoan(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "employee_loans"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    loan_no: Mapped[str] = mapped_column(String(64), nullable=False)
    loan_date: Mapped[date] = mapped_column(Date, nullable=False)
    principal_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    installment_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    installment_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    remaining_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    start_deduction_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    reason: Mapped[str | None] = mapped_column(String(400))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))

    __table_args__ = (UniqueConstraint("company_id", "loan_no", name="uq_employee_loans_company_no"),)
