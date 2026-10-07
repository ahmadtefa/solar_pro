"""Core administration: companies, module activation, users, roles and sessions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.crud import serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.core.config import settings
from app.core.database import utcnow_naive
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailure
from app.core.permissions import CATALOGUE
from app.models.identity import (
    Role,
    RolePermission,
    User,
    UserBranchAccess,
    UserCompanyAccess,
    UserRole,
    UserSession,
    UserWarehouseAccess,
)
from app.models.platform import Branch, Company, ModuleActivation
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.bootstrap_service import BootstrapService

router = APIRouter()


# --------------------------------------------------------------------------- #
# Companies
# --------------------------------------------------------------------------- #
@router.get("/companies", summary="Companies the caller can access")
def list_companies(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.company.view")
    if current.is_superuser:
        rows = db.execute(select(Company).order_by(Company.name)).scalars().all()
    else:
        company_ids = db.execute(
            select(UserCompanyAccess.company_id).where(UserCompanyAccess.user_id == current.id)
        ).scalars().all()
        rows = db.execute(select(Company).where(Company.id.in_(list(company_ids))).order_by(Company.name)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/companies", status_code=201, summary="Create a company with its default chart of accounts")
def create_company(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.company.create")
    name = payload.get("name") or payload.get("name_en")
    if not name:
        raise ValidationFailure("The company name is required")
    data = {
        "name": name,
        "name_ar": payload.get("name_ar"),
        "code": payload.get("code"),
        "currency_code": payload.get("currency_code") or "USD",
        "country_code": payload.get("country_code"),
        "timezone": payload.get("timezone") or "UTC",
        "fiscal_year_start": payload.get("fiscal_year_start"),
        "parent_company_id": payload.get("parent_company_id"),
        "email": payload.get("email"),
        "phone": payload.get("phone"),
        "address": payload.get("address"),
        "tax_number": payload.get("tax_number"),
        "logo_url": payload.get("logo_url"),
        "modules": payload.get("modules"),
    }
    service = BootstrapService(db)
    provisioned = service.create_company(data)
    company = provisioned["company"]
    company_id = company.id
    if payload.get("admin_email"):
        if not payload.get("admin_password"):
            raise ValidationFailure("admin_password is required when admin_email is provided")
        user = db.execute(select(User).where(User.email == str(payload["admin_email"]).lower())).scalar_one_or_none()
        if user is None:
            service.create_user(
                email=str(payload["admin_email"]).lower(),
                password=payload["admin_password"],
                full_name=payload.get("admin_full_name") or "Company administrator",
                company_id=company_id,
                roles=("company_admin",),
            )
        else:
            service.grant_company_access(user, company_id=company_id, roles=("company_admin",))
        db.flush()
    db.flush()
    AuditService(db, audit_context(current)).log_create(company, entity_type="company", label=company.name)
    provisioned_summary = {
        key: serialise(value) if hasattr(value, "__table__") else value
        for key, value in provisioned.items()
        if key in {"branch", "department", "warehouse", "fiscal_year", "settings"}
    }
    return {**serialise(company), "provisioned": provisioned_summary}


@router.get("/companies/{company_id}", summary="Company profile")
def get_company(company_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.company.view")
    if company_id != current.company_id and not current.is_superuser:
        raise PermissionDeniedError("You do not have access to this company")
    company = db.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found", id=str(company_id))
    activations = db.execute(
        select(ModuleActivation).where(ModuleActivation.company_id == company_id).order_by(ModuleActivation.module_key)
    ).scalars().all()
    return {
        **serialise(company),
        "modules": [serialise(row) for row in activations],
        "users": db.execute(
            select(func.count(User.id)).where(User.company_id == company_id)
        ).scalar_one(),
        "branches": db.execute(
            select(func.count(Branch.id)).where(Branch.company_id == company_id)
        ).scalar_one(),
    }


@router.patch("/companies/{company_id}", summary="Update a company profile")
def update_company(company_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.company.edit")
    if company_id != current.company_id and not current.is_superuser:
        raise PermissionDeniedError("You do not have access to this company")
    company = db.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found", id=str(company_id))
    previous = _snapshot(company)
    editable = (
        "name",
        "name_ar",
        "legal_name",
        "email",
        "phone",
        "address",
        "tax_number",
        "currency_code",
        "country_code",
        "timezone",
        "logo_url",
        "fiscal_year_start",
    )
    for field in editable:
        if field in payload and payload[field] is not None:
            setattr(company, field, payload[field])
    db.flush()
    AuditService(db, audit_context(current)).log_update(
        company, previous, entity_type="company", label=company.name
    )
    return serialise(company)


@router.get("/companies/{company_id}/modules", summary="Activated modules")
def company_modules(company_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.module.view")
    if company_id != current.company_id and not current.is_superuser:
        raise PermissionDeniedError("You do not have access to this company")
    rows = db.execute(
        select(ModuleActivation).where(ModuleActivation.company_id == company_id).order_by(ModuleActivation.module_key)
    ).scalars().all()
    if not rows:
        from app.models.platform import DEFAULT_MODULES

        return {"items": [{"module_key": key, "is_active": True} for key in DEFAULT_MODULES]}
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.put("/companies/{company_id}/modules", summary="Activate or deactivate modules")
def set_company_modules(company_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.module.edit")
    if company_id != current.company_id and not current.is_superuser:
        raise PermissionDeniedError("You do not have access to this company")
    modules = payload.get("modules")
    if not isinstance(modules, dict):
        raise ValidationFailure("Provide a modules object of {key: boolean}")
    updated = []
    for key, enabled in modules.items():
        row = db.execute(
            select(ModuleActivation).where(
                ModuleActivation.company_id == company_id, ModuleActivation.module_key == key
            )
        ).scalar_one_or_none()
        if row is None:
            row = ModuleActivation(company_id=company_id, module_key=key, is_active=bool(enabled))
            db.add(row)
        else:
            row.is_active = bool(enabled)
        updated.append({"module_key": key, "is_active": bool(enabled)})
    db.flush()
    AuditService(db, audit_context(current)).log(
        "module_activation_changed",
        entity_type="company",
        entity_id=company_id,
        label=str(sorted(modules)),
        new_values={key: bool(value) for key, value in modules.items()},
    )
    return {"items": updated, "total": len(updated)}


@router.get("/bootstrap-status", summary="Whether the platform has been initialised")
def bootstrap_status(db: DB) -> dict[str, Any]:
    BootstrapService_status = getattr(BootstrapService, "status", None)
    if callable(BootstrapService_status):
        return BootstrapService_status(BootstrapService(db))
    from sqlalchemy import func as _func

    from app.models.platform import Company as _Company

    companies = db.execute(select(_func.count(_Company.id))).scalar_one()
    return {
        "initialised": bool(companies),
        "companies": int(companies),
        "admin_email_hint": settings.bootstrap_admin_email,
        "demo_data_seeded": bool(companies),
    }


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
@router.get("/users/{user_id}", summary="User profile with roles and access scopes")
def get_user(user_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.view")
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("User not found", id=str(user_id))
    if not current.is_superuser and user.company_id != current.company_id:
        raise NotFoundError("User not found", id=str(user_id))
    auth = AuthService(db)
    roles = db.execute(
        select(Role.code, Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    ).all()
    companies = db.execute(
        select(UserCompanyAccess.company_id).where(UserCompanyAccess.user_id == user_id)
    ).scalars().all()
    branches = db.execute(
        select(UserBranchAccess.branch_id).where(UserBranchAccess.user_id == user_id)
    ).scalars().all()
    warehouses = db.execute(
        select(UserWarehouseAccess.warehouse_id).where(UserWarehouseAccess.user_id == user_id)
    ).scalars().all()
    return {
        **serialise(user),
        "roles": [{"code": row[0], "name": row[1]} for row in roles],
        "permissions": sorted(auth.permissions_for_user(user_id, current.company_id)),
        "companies": [str(item) for item in companies],
        "branches": [str(item) for item in branches],
        "warehouses": [str(item) for item in warehouses],
        "sessions": [serialise(row) for row in _active_sessions(db, user_id)],
    }


@router.post("/users/{user_id}/activate", summary="Activate a user")
def activate_user(user_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.edit")
    return serialise(_set_user_status(db, current, user_id, "active"))


@router.post("/users/{user_id}/deactivate", summary="Deactivate a user")
def deactivate_user(user_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.edit")
    return serialise(_set_user_status(db, current, user_id, "inactive"))


@router.post("/users/{user_id}/suspend", summary="Suspend a user and revoke their sessions")
def suspend_user(user_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.edit")
    user = _set_user_status(db, current, user_id, "suspended")
    AuthService(db).revoke_all_sessions(user_id)
    db.flush()
    return serialise(user)


@router.post("/users/{user_id}/branch-access", summary="Grant branch access")
def grant_branch_access(user_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.edit")
    branch_ids = payload.get("branch_ids") or ([payload["branch_id"]] if payload.get("branch_id") else [])
    if not branch_ids:
        raise ValidationFailure("Provide branch_id or branch_ids")
    auth = AuthService(db)
    for branch_id in branch_ids:
        auth.grant_branch_access(user_id, uuid.UUID(str(branch_id)), can_view=not payload.get("read_only", False))
    db.flush()
    return {"user_id": str(user_id), "branches": [str(item) for item in branch_ids]}


@router.delete("/users/{user_id}/branch-access/{branch_id}", summary="Revoke branch access")
def revoke_branch_access(
    user_id: uuid.UUID, branch_id: uuid.UUID, db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("core.user.edit")
    AuthService(db).revoke_branch_access(user_id, branch_id)
    db.flush()
    return {"user_id": str(user_id), "branch_id": str(branch_id), "revoked": True}


@router.post("/users/{user_id}/warehouse-access", summary="Grant warehouse access")
def grant_warehouse_access(
    user_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("core.user.edit")
    ids = payload.get("warehouse_ids") or ([payload["warehouse_id"]] if payload.get("warehouse_id") else [])
    if not ids:
        raise ValidationFailure("Provide warehouse_id or warehouse_ids")
    auth = AuthService(db)
    for warehouse_id in ids:
        auth.grant_warehouse_access(user_id, uuid.UUID(str(warehouse_id)))
    db.flush()
    return {"user_id": str(user_id), "warehouses": [str(item) for item in ids]}


@router.delete("/users/{user_id}/warehouse-access/{warehouse_id}", summary="Revoke warehouse access")
def revoke_warehouse_access(
    user_id: uuid.UUID, warehouse_id: uuid.UUID, db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("core.user.edit")
    AuthService(db).revoke_warehouse_access(user_id, warehouse_id)
    db.flush()
    return {"user_id": str(user_id), "warehouse_id": str(warehouse_id), "revoked": True}


@router.get("/users/{user_id}/sessions", summary="Active sessions and devices")
def user_sessions(user_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.session.view")
    if user_id != current.id and not current.can("core.user.edit"):
        raise PermissionDeniedError("You cannot inspect other users' sessions")
    rows = _active_sessions(db, user_id)
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/users/{user_id}/sessions/revoke", summary="Revoke a user's sessions")
def revoke_sessions(user_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.session.delete")
    if user_id != current.id and not current.can("core.user.edit"):
        raise PermissionDeniedError("You cannot revoke other users' sessions")
    revoked = AuthService(db).revoke_all_sessions(user_id)
    db.flush()
    return {"user_id": str(user_id), "revoked": revoked if isinstance(revoked, int) else True}


# --------------------------------------------------------------------------- #
# Roles and permissions
# --------------------------------------------------------------------------- #
@router.delete("/roles/{role_id}", summary="Delete a custom role")
def delete_role(role_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.role.delete")
    role = _get_role(db, current, role_id)
    if role.is_system:
        raise PermissionDeniedError("System roles cannot be deleted")
    assigned = db.execute(select(func.count(UserRole.id)).where(UserRole.role_id == role_id)).scalar_one()
    if assigned:
        raise ConflictError("Role is still assigned to users", users=int(assigned))
    db.execute(RolePermission.__table__.delete().where(RolePermission.role_id == role_id))
    db.delete(role)
    db.flush()
    return {"id": str(role_id), "deleted": True}


# --------------------------------------------------------------------------- #
# Sessions, attempts and audit
# --------------------------------------------------------------------------- #
@router.get("/sessions", summary="Sessions across the company")
def list_sessions(
    db: DB, current: CurrentUserDep, active_only: bool = True, limit: int = Query(100, ge=1, le=500)
) -> dict[str, Any]:
    current.require("core.session.view")
    stmt = select(UserSession).where(UserSession.company_id == current.company_id)
    if active_only:
        stmt = stmt.where(UserSession.is_revoked.is_(False), UserSession.expires_at > utcnow_naive())
    rows = db.execute(stmt.order_by(UserSession.created_at.desc()).limit(limit)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.delete("/sessions/{session_id}", summary="Revoke one session")
def revoke_session(session_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.session.delete")
    session = db.get(UserSession, session_id)
    if session is None or session.company_id != current.company_id:
        raise NotFoundError("Session not found", id=str(session_id))
    AuthService(db).revoke_session(session_id, reason="revoked by administrator")
    db.flush()
    return {"id": str(session_id), "revoked": True}


@router.get("/login-attempts", summary="Recent login attempts")
def login_attempts(
    db: DB,
    current: CurrentUserDep,
    email: str | None = None,
    successful: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("core.audit_log.view")
    from app.models.identity import LoginAttempt

    stmt = select(LoginAttempt)
    if email:
        stmt = stmt.where(LoginAttempt.email == email.lower())
    if successful is not None:
        stmt = stmt.where(LoginAttempt.successful.is_(successful))
    rows = db.execute(stmt.order_by(LoginAttempt.created_at.desc()).limit(limit)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.get("/audit-logs/{entity_type}/{entity_id}", summary="Full history of one record")
def audit_history(entity_type: str, entity_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.audit_log.view")
    rows = AuditService(db, audit_context(current)).history_for(entity_type, entity_id)
    return {"items": rows, "total": len(rows)}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _snapshot(entity: Any) -> dict[str, Any]:
    from app.core.pagination import snapshot

    return snapshot(entity)


def _active_sessions(db: DB, user_id: uuid.UUID) -> list[UserSession]:
    return list(
        db.execute(
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.is_revoked.is_(False),
                UserSession.expires_at > utcnow_naive(),
            )
            .order_by(UserSession.last_seen_at.desc())
        ).scalars().all()
    )


def _set_user_status(db: DB, current: CurrentUserDep, user_id: uuid.UUID, status: str) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("User not found", id=str(user_id))
    if not current.is_superuser and user.company_id != current.company_id:
        raise NotFoundError("User not found", id=str(user_id))
    if user.id == current.id and status != "active":
        raise ValidationFailure("You cannot deactivate your own account")
    previous = _snapshot(user)
    user.status = status
    user.is_active = status == "active"
    if status == "active":
        user.failed_login_count = 0
        user.locked_until = None
    db.flush()
    AuditService(db, audit_context(current)).log_update(
        user, previous, entity_type="user", label=user.email, action=f"user_{status}"
    )
    return user


def _get_role(db: DB, current: CurrentUserDep, role_id: uuid.UUID) -> Role:
    role = db.get(Role, role_id)
    if role is None or (role.company_id is not None and role.company_id != current.company_id):
        raise NotFoundError("Role not found", id=str(role_id))
    return role


def _assign_permissions(
    db: DB, current: CurrentUserDep, role_id: uuid.UUID, codes: list[str], *, replace: bool = False
) -> None:
    unknown = sorted(set(codes) - set(CATALOGUE))
    if unknown:
        raise ValidationFailure("Unknown permission codes", codes=unknown[:20])
    if replace:
        db.execute(RolePermission.__table__.delete().where(RolePermission.role_id == role_id))
        db.flush()
    existing = set(
        db.execute(select(RolePermission.permission_code).where(RolePermission.role_id == role_id)).scalars().all()
    )
    for code in sorted(set(codes) - existing):
        db.add(
            RolePermission(
                role_id=role_id,
                permission_code=code,
                module=code.split(".")[0],
                granted_by_id=current.id,
            )
        )


def _count(value: Any) -> int:
    return int(len(value))


def _soon(days: int) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


__all__ = ["router"]
