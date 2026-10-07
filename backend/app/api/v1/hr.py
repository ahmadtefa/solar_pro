"""Human resources: employees, contracts, attendance, leave, payroll and loans."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep
from app.core.errors import NotFoundError, ValidationFailure
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
    Position,
    SalaryComponent,
    WorkShift,
)
from app.services.hr_service import AttendanceService, EmployeeService, LeaveService, PayrollService

router = APIRouter()

# --------------------------------------------------------------------------- #
# Employees and positions
# --------------------------------------------------------------------------- #
@router.get("/employees", summary="Employees with position and branch")
def list_employees(
    db: DB,
    current: CurrentUserDep,
    q: str | None = None,
    department_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    current.require("hr.employee.view")
    stmt = select(Employee).where(Employee.company_id == current.company_id, Employee.deleted_at.is_(None))
    if q:
        stmt = stmt.where(
            Employee.first_name.ilike(f"%{q}%")
            | Employee.last_name.ilike(f"%{q}%")
            | Employee.employee_no.ilike(f"%{q}%")
            | Employee.email.ilike(f"%{q}%")
            | Employee.phone.ilike(f"%{q}%")
        )
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if branch_id:
        stmt = stmt.where(Employee.branch_id == branch_id)
    if status_filter:
        stmt = stmt.where(Employee.status == status_filter)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Employee.employee_no).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "items": [serialise(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.post("/employees", status_code=201, summary="Hire an employee")
def create_employee(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.employee.create")
    employee = EmployeeService(db, current.company_id, user_id=current.id).create(payload)
    return serialise(employee)


@router.get("/employees/{employee_id}", summary="Employee file: contracts, attendance, leave, payroll")
def get_employee(employee_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.employee.view")
    service = EmployeeService(db, current.company_id, user_id=current.id)
    employee = service.get(employee_id)
    payload = serialise(employee)
    payload["contracts"] = [
        serialise(row)
        for row in db.execute(
            select(EmploymentContract).where(
                EmploymentContract.company_id == current.company_id,
                EmploymentContract.employee_id == employee_id,
            )
        ).scalars().all()
    ]
    payload["current_shift"] = service.current_shift(employee_id)
    payload["leave"] = LeaveService(db, current.company_id).balance_summary(employee_id=employee_id)
    payload["payslips"] = [
        serialise(row)
        for row in db.execute(
            select(Payslip)
            .where(Payslip.company_id == current.company_id, Payslip.employee_id == employee_id)
            .order_by(Payslip.created_at.desc())
            .limit(12)
        ).scalars().all()
    ]
    payload["loans"] = [
        serialise(row)
        for row in db.execute(
            select(EmployeeLoan)
            .where(
                EmployeeLoan.company_id == current.company_id, EmployeeLoan.employee_id == employee_id
            )
        ).scalars().all()
    ]
    return payload


@router.patch("/employees/{employee_id}", summary="Update an employee")
def update_employee(employee_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.employee.edit")
    employee = EmployeeService(db, current.company_id, user_id=current.id).update(employee_id, payload)
    return serialise(employee)


@router.post("/employees/{employee_id}/terminate", summary="Terminate employment")
def terminate_employee(employee_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.employee.edit")
    employee = EmployeeService(db, current.company_id, user_id=current.id).terminate(
        employee_id,
        termination_date=date.fromisoformat(payload["termination_date"]) if payload.get("termination_date") else date.today(),
        reason=payload.get("reason") or "resignation",
    )
    return serialise(employee)


@router.post("/employees/{employee_id}/contracts", status_code=201, summary="Add a contract")
def create_contract(
    employee_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("hr.employee_contract.create")
    contract = EmployeeService(db, current.company_id, user_id=current.id).create_contract(employee_id, payload)
    return serialise(contract)


@router.post("/contracts/{contract_id}/renew", summary="Renew a contract")
def renew_contract(contract_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.employee_contract.edit")
    contract = EmployeeService(db, current.company_id, user_id=current.id).renew_contract(
        contract_id,
        end_date=date.fromisoformat(payload["end_date"]),
        new_salary=Decimal(str(payload["new_salary"])) if payload.get("new_salary") else None,
    )
    return serialise(contract)


@router.post("/employees/{employee_id}/shift", summary="Assign a work shift")
def assign_shift(employee_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.shift.edit")
    assignment = EmployeeService(db, current.company_id, user_id=current.id).assign_shift(
        employee_id,
        shift_id=uuid.UUID(str(payload.get("shift_id"))),
        effective_from=date.fromisoformat(payload["effective_from"]) if payload.get("effective_from") else date.today(),
        effective_to=date.fromisoformat(payload["effective_to"]) if payload.get("effective_to") else None,
    )
    return serialise(assignment)


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="positions",
            model=Position,
            module="hr",
            entity="position",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(Position, unique=[("code", "Position code")]),
        ),
        tags=["hr"],
    ),
    prefix="/positions",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="contracts",
            model=EmploymentContract,
            module="hr",
            entity="employee_contract",
            filters={"employee_id": "employee_id", "status": "status"},
            create_handler=guarded_create(EmploymentContract),
        ),
        tags=["hr"],
    ),
    prefix="/employee-contracts",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="shifts",
            model=WorkShift,
            module="hr",
            entity="shift",
            search_fields=["code", "name"],
            label_field="name",
            create_handler=guarded_create(WorkShift, unique=[("code", "Shift code")]),
        ),
        tags=["hr"],
    ),
    prefix="/shifts",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="holidays",
            model=Holiday,
            module="hr",
            entity="holiday",
            search_fields=["name", "name_ar"],
            default_sort="holiday_date",
            filters={"branch_id": "branch_id"},
            create_handler=guarded_create(Holiday),
        ),
        tags=["hr"],
    ),
    prefix="/holidays",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="salary-components",
            model=SalaryComponent,
            module="hr",
            entity="payroll_run",
            search_fields=["code", "name"],
            label_field="name",
            create_handler=guarded_create(SalaryComponent, unique=[("code", "Component code")]),
        ),
        tags=["hr"],
    ),
    prefix="/salary-components",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="loans",
            model=EmployeeLoan,
            module="hr",
            entity="loan",
            search_fields=["loan_no"],
            default_sort="loan_date",
            filters={"employee_id": "employee_id", "status": "status"},
            create_handler=guarded_create(EmployeeLoan),
        ),
        tags=["hr"],
    ),
    prefix="/loans",
)

# --------------------------------------------------------------------------- #
# Attendance
# --------------------------------------------------------------------------- #
@router.get("/attendance", summary="Attendance records")
def list_attendance(
    db: DB,
    current: CurrentUserDep,
    employee_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    current.require("hr.attendance.view")
    stmt = select(AttendanceRecord).where(AttendanceRecord.company_id == current.company_id)
    if employee_id:
        stmt = stmt.where(AttendanceRecord.employee_id == employee_id)
    if date_from:
        stmt = stmt.where(AttendanceRecord.attendance_date >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceRecord.attendance_date <= date_to)
    rows = db.execute(
        stmt.order_by(AttendanceRecord.attendance_date.desc()).limit(limit)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/attendance/record", summary="Record attendance for a day")
def record_attendance(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.attendance.create")
    service = AttendanceService(db, current.company_id, user_id=current.id)
    record = service.record(
        employee_id=uuid.UUID(str(payload.get("employee_id"))),
        attendance_date=date.fromisoformat(payload["attendance_date"]) if payload.get("attendance_date") else date.today(),
        check_in=_time(payload.get("check_in")),
        check_out=_time(payload.get("check_out")),
        status=payload.get("status"),
        notes=payload.get("notes"),
    )
    db.flush()
    return serialise(record)


@router.post("/attendance/check-in", summary="Employee check-in")
def check_in(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.attendance.create")
    service = AttendanceService(db, current.company_id, user_id=current.id)
    record = service.check_in(
        employee_id=uuid.UUID(str(payload.get("employee_id"))) if payload.get("employee_id") else _own_employee(db, current),
        at=_datetime(payload.get("at")),
    )
    db.flush()
    return serialise(record)


@router.post("/attendance/check-out", summary="Employee check-out")
def check_out(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.attendance.create")
    service = AttendanceService(db, current.company_id, user_id=current.id)
    record = service.check_out(
        employee_id=uuid.UUID(str(payload.get("employee_id"))) if payload.get("employee_id") else _own_employee(db, current),
        at=_datetime(payload.get("at")),
    )
    db.flush()
    return serialise(record)


@router.get("/attendance/summary", summary="Attendance summary for an employee and period")
def attendance_summary(
    db: DB,
    current: CurrentUserDep,
    employee_id: uuid.UUID = Query(...),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    current.require("hr.attendance.view")
    today = date.today()
    service = AttendanceService(db, current.company_id, user_id=current.id)
    return service.summarize(
        employee_id=employee_id,
        date_from=date_from or today.replace(day=1),
        date_to=date_to or today,
    )


# --------------------------------------------------------------------------- #
# Leave
# --------------------------------------------------------------------------- #
@router.get("/leave-types", summary="Leave types")
def list_leave_types(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.leave_type.view")
    rows = db.execute(
        select(LeaveType).where(LeaveType.company_id == current.company_id, LeaveType.deleted_at.is_(None))
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.get("/leave-requests", summary="Leave requests")
def list_leave_requests(
    db: DB,
    current: CurrentUserDep,
    employee_id: uuid.UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("hr.leave_request.view")
    stmt = select(LeaveRequest).where(
        LeaveRequest.company_id == current.company_id, LeaveRequest.deleted_at.is_(None)
    )
    if employee_id:
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    if status_filter:
        stmt = stmt.where(LeaveRequest.status == status_filter)
    rows = db.execute(stmt.order_by(LeaveRequest.start_date.desc()).limit(limit)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/leave-requests", status_code=201, summary="Request leave")
def request_leave(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.leave_request.create")
    request = LeaveService(db, current.company_id, user_id=current.id).request(payload)
    return serialise(request)


@router.post("/leave-requests/{request_id}/approve", summary="Approve a leave request")
def approve_leave(request_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.leave_request.approve")
    request = LeaveService(db, current.company_id, user_id=current.id).approve(request_id, approver_id=current.id)
    return serialise(request)


@router.post("/leave-requests/{request_id}/reject", summary="Reject a leave request")
def reject_leave(request_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.leave_request.reject")
    request = LeaveService(db, current.company_id, user_id=current.id).reject(
        request_id, reason=payload.get("reason") or "rejected", rejector_id=current.id
    )
    return serialise(request)


@router.post("/leave-requests/{request_id}/cancel", summary="Cancel a leave request")
def cancel_leave(
    request_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("hr.leave_request.edit")
    request = LeaveService(db, current.company_id, user_id=current.id).cancel(
        request_id, reason=payload.get("reason")
    )
    return serialise(request)


@router.get("/leave/balances", summary="Leave balances")
def leave_balances(
    db: DB,
    current: CurrentUserDep,
    employee_id: uuid.UUID = Query(...),
    year: int | None = None,
) -> dict[str, Any]:
    current.require("hr.leave_balance.view")
    return {"items": LeaveService(db, current.company_id).balance_summary(employee_id=employee_id, year=year)}


@router.post("/leave/accrue", summary="Accrue leave days for an employee")
def accrue_leave(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.leave_balance.edit")
    balance = LeaveService(db, current.company_id, user_id=current.id).accrue(
        employee_id=uuid.UUID(str(payload.get("employee_id"))),
        leave_type_id=uuid.UUID(str(payload.get("leave_type_id"))),
        year=int(payload.get("year") or date.today().year),
        days=Decimal(str(payload.get("days", 0))),
    )
    db.flush()
    return serialise(balance)


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="leave-types",
            model=LeaveType,
            module="hr",
            entity="leave_type",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(LeaveType, unique=[("code", "Leave type code")]),
        ),
        tags=["hr"],
    ),
    prefix="/leave-type-master",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="leave-balances",
            model=LeaveBalance,
            module="hr",
            entity="leave_balance",
            filters={"employee_id": "employee_id", "year": "year"},
            soft_delete=False,
        ),
        tags=["hr"],
    ),
    prefix="/leave-balances",
)

# --------------------------------------------------------------------------- #
# Payroll
# --------------------------------------------------------------------------- #
@router.get("/payroll/periods", summary="Payroll periods")
def list_payroll_periods(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.payroll_period.view")
    rows = db.execute(
        select(PayrollPeriod)
        .where(PayrollPeriod.company_id == current.company_id, PayrollPeriod.deleted_at.is_(None))
        .order_by(PayrollPeriod.period_start.desc())
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/payroll/periods", status_code=201, summary="Create a payroll period")
def create_payroll_period(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.payroll_period.create")
    period = PayrollService(db, current.company_id, user_id=current.id).create_period(payload)
    return serialise(period)


@router.get("/payroll/runs", summary="Payroll runs")
def list_payroll_runs(
    db: DB, current: CurrentUserDep, status_filter: str | None = Query(None, alias="status")
) -> dict[str, Any]:
    current.require("hr.payroll_run.view")
    stmt = select(PayrollRun).where(
        PayrollRun.company_id == current.company_id, PayrollRun.deleted_at.is_(None)
    )
    if status_filter:
        stmt = stmt.where(PayrollRun.status == status_filter)
    rows = db.execute(stmt.order_by(PayrollRun.run_date.desc())).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/payroll/runs", status_code=201, summary="Start a payroll run")
def create_payroll_run(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.payroll_run.create")
    run = PayrollService(db, current.company_id, user_id=current.id).create_run(payload)
    return serialise(run)


@router.post("/payroll/runs/{run_id}/compute", summary="Compute payslips for a run")
def compute_payroll(run_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.payroll_run.edit")
    run = PayrollService(db, current.company_id, user_id=current.id).compute(run_id)
    db.flush()
    return serialise(run)


@router.post("/payroll/runs/{run_id}/approve", summary="Approve a computed payroll run")
def approve_payroll(run_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.payroll_run.approve")
    service = PayrollService(db, current.company_id, user_id=current.id)
    run = service.get_document(run_id)
    run = service.approve(run)
    db.flush()
    return serialise(run)


@router.post("/payroll/runs/{run_id}/post", summary="Post the payroll journal")
def post_payroll(run_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.payroll_run.post")
    service = PayrollService(db, current.company_id, user_id=current.id)
    run = service.get_document(run_id)
    run = service.post(run, allow_draft=False)
    db.flush()
    return serialise(run)


@router.post("/payroll/runs/{run_id}/pay", summary="Pay a posted payroll run")
def pay_payroll(
    run_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("hr.payroll_run.edit")
    payment = PayrollService(db, current.company_id, user_id=current.id).pay(
        run_id,
        cash_account_id=uuid.UUID(str(payload["cash_account_id"])) if payload.get("cash_account_id") else None,
        bank_account_id=uuid.UUID(str(payload["bank_account_id"])) if payload.get("bank_account_id") else None,
        payment_date=date.fromisoformat(payload["payment_date"]) if payload.get("payment_date") else None,
        notes=payload.get("notes"),
    )
    db.flush()
    return serialise(payment)


@router.get("/payroll/runs/{run_id}/payslips", summary="Payslips of a run")
def run_payslips(run_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.payslip.view")
    rows = db.execute(
        select(Payslip).where(Payslip.company_id == current.company_id, Payslip.payroll_run_id == run_id)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.get("/payroll/payslip/{payslip_id}/print", summary="Printable payslip")
def payslip_print(payslip_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("hr.payslip.view")
    from app.models.platform import Company

    payslip = db.get(Payslip, payslip_id)
    if payslip is None or payslip.company_id != current.company_id:
        raise NotFoundError("Payslip not found", id=str(payslip_id))
    company = db.get(Company, current.company_id)
    return {
        "company": serialise(company, ["id", "code", "name", "name_ar", "logo_url"]),
        "payslip": serialise(payslip),
        "employee": serialise(db.get(Employee, payslip.employee_id)),
        "generated_at": datetime.now().isoformat(),
    }


@router.get("/payroll/summary", summary="Payroll cost for a period")
def payroll_summary(
    db: DB, current: CurrentUserDep, date_from: date | None = None, date_to: date | None = None
) -> dict[str, Any]:
    current.require("hr.payroll_run.view")
    today = date.today()
    start = date_from or today.replace(month=1, day=1)
    end = date_to or today
    rows = db.execute(
        select(
            func.count(PayrollRun.id),
            func.coalesce(func.sum(PayrollRun.total_gross), 0),
            func.coalesce(func.sum(PayrollRun.total_deductions), 0),
            func.coalesce(func.sum(PayrollRun.total_net), 0),
            func.coalesce(func.sum(PayrollRun.total_employer_contributions), 0),
        ).where(
            PayrollRun.company_id == current.company_id,
            PayrollRun.run_date >= start,
            PayrollRun.run_date <= end,
            PayrollRun.status.in_(["posted", "approved"]),
        )
    ).one()
    return {
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "runs": int(rows[0]),
        "gross": str(rows[1]),
        "deductions": str(rows[2]),
        "net": str(rows[3]),
        "employer_contributions": str(rows[4]),
    }


# --------------------------------------------------------------------------- #
# Self service
# --------------------------------------------------------------------------- #
@router.get("/me", summary="My HR file (self service)")
def my_hr_file(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    employee_id = current.user.employee_id
    if employee_id is None:
        raise ValidationFailure("Your user account is not linked to an employee record")
    return get_employee(employee_id, db, current)


@router.get("/me/attendance", summary="My attendance history")
def my_attendance(db: DB, current: CurrentUserDep, limit: int = Query(30, ge=1, le=120)) -> dict[str, Any]:
    employee_id = _own_employee(db, current)
    rows = db.execute(
        select(AttendanceRecord)
        .where(
            AttendanceRecord.company_id == current.company_id,
            AttendanceRecord.employee_id == employee_id,
        )
        .order_by(AttendanceRecord.attendance_date.desc())
        .limit(limit)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.get("/me/payslips", summary="My payslips")
def my_payslips(db: DB, current: CurrentUserDep, limit: int = Query(24, ge=1, le=120)) -> dict[str, Any]:
    employee_id = _own_employee(db, current)
    rows = db.execute(
        select(Payslip)
        .where(Payslip.company_id == current.company_id, Payslip.employee_id == employee_id)
        .order_by(Payslip.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="attendance",
            model=AttendanceRecord,
            module="hr",
            entity="attendance",
            default_sort="attendance_date",
            filters={"employee_id": "employee_id", "status": "status"},
            soft_delete=False,
        ),
        tags=["hr"],
    ),
    prefix="/attendance-records",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="employee-salary-components",
            model=EmployeeSalaryComponent,
            module="hr",
            entity="payroll_run",
            filters={"employee_id": "employee_id"},
            soft_delete=False,
        ),
        tags=["hr"],
    ),
    prefix="/employee-salary-components",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="shift-assignments",
            model=EmployeeShiftAssignment,
            module="hr",
            entity="shift",
            default_sort="effective_from",
            filters={"employee_id": "employee_id", "shift_id": "shift_id"},
            soft_delete=False,
        ),
        tags=["hr"],
    ),
    prefix="/shift-assignments",
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _own_employee(db: DB, current: CurrentUserDep) -> uuid.UUID:
    if current.user.employee_id is None:
        raise ValidationFailure("Your user account is not linked to an employee record")
    return current.user.employee_id


def _time(value: Any) -> time | None:
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value
    text = str(value)
    if "T" in text:
        return datetime.fromisoformat(text).time()
    return time.fromisoformat(text)


def _datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


__all__ = ["router"]
