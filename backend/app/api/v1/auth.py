"""Authentication, sessions, users, roles and the audit trail."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Query, Request, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUserDep, audit_context
from app.core.errors import NotFoundError, ValidationFailure
from app.core.permissions import all_permission_codes, entity_permission_templates
from app.models.identity import (
    AuditLog,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    PermissionSyncRequest,
    RefreshRequest,
    ResetPasswordRequest,
    RoleCreateRequest,
    RoleUpdateRequest,
    UserCreateRequest,
    UserUpdateRequest,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login", summary="Sign in and start a session")
def login(payload: LoginRequest, request: Request, db: DB) -> dict[str, Any]:
    return AuthService(db).login(
        email=payload.email,
        password=payload.password,
        company_id=payload.company_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        device_name=payload.device_name,
    )


@router.post("/auth/refresh", summary="Rotate the refresh token and get a new access token")
def refresh(payload: RefreshRequest, request: Request, db: DB) -> dict[str, Any]:
    return AuthService(db).refresh(
        payload.refresh_token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/auth/logout", summary="Revoke the current session")
def logout(
    db: DB,
    current: CurrentUserDep,
    payload: LogoutRequest = Body(default=LogoutRequest()),
) -> dict[str, Any]:
    auth = AuthService(db)
    if payload.all_devices:
        count = auth.revoke_all_sessions(current.id, reason="logout_all")
        return {"revoked_sessions": count}
    auth.logout(current.session.id, user_id=current.id)
    return {"revoked_sessions": 1}


@router.get("/auth/me", summary="Current profile, company and permission set")
def me(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    auth = AuthService(db)
    profile = auth.user_profile(current.user, current.company_id, session_id=current.session.id)
    profile["permissions"] = sorted(current.permissions.codes) if not current.is_superuser else ["*"]  # "*" = wildcard
    profile["companies"] = auth.accessible_companies(current.user)
    profile["branches"] = [str(branch) for branch in (current.branch_ids or [])]
    profile["warehouses"] = [str(warehouse) for warehouse in (current.warehouse_ids or [])]
    profile["data_scope"] = current.data_scope
    return profile


@router.post("/auth/switch-company", summary="Switch the active company (new tokens)")
def switch_company(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    company_id = uuid.UUID(str(payload.get("company_id")))
    return AuthService(db).switch_company(current.user, company_id, session_id=current.session.id)


@router.post("/auth/change-password", summary="Change the password of the signed-in user")
def change_password(payload: ChangePasswordRequest, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    AuthService(db).change_password(
        current.user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        keep_session_id=current.session.id,
    )
    return {"message": "Password updated. Other sessions were revoked."}


@router.post("/auth/forgot-password", summary="Request a password reset token")
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: DB) -> dict[str, Any]:
    return AuthService(db).request_password_reset(
        payload.email, ip_address=request.client.host if request.client else None
    )


@router.post("/auth/reset-password", summary="Consume a reset token")
def reset_password(payload: ResetPasswordRequest, db: DB) -> dict[str, Any]:
    AuthService(db).reset_password(payload.token, payload.new_password)
    return {"message": "Password has been reset"}


@router.get("/auth/sessions", summary="Devices/sessions of the signed-in user")
def list_sessions(db: DB, current: CurrentUserDep, include_inactive: bool = Query(False)) -> dict[str, Any]:
    sessions = AuthService(db).list_sessions(current.id, include_inactive=include_inactive)
    return {
        "items": [
            {
                "id": str(session.id),
                "device_name": session.device_name,
                "device_type": session.device_type,
                "platform": session.platform,
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
                "is_active": session.is_active,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "last_seen_at": session.last_seen_at.isoformat() if session.last_seen_at else None,
                "expires_at": session.expires_at.isoformat() if session.expires_at else None,
                "current": session.id == current.session.id,
            }
            for session in sessions
        ]
    }


@router.delete("/auth/sessions/{session_id}", summary="Revoke one session/device")
def revoke_session(session_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    AuthService(db).logout(session_id, user_id=current.id, reason="revoked_by_user")
    return {"revoked": str(session_id)}


@router.get("/auth/permissions", summary="Permission catalogue (for the role editor)")
def permission_catalogue(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.permission.view")
    codes = all_permission_codes()
    return {
        "total": len(codes),
        "catalogue": entity_permission_templates(),
        "codes": codes,
    }


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
@router.get("/users", summary="List users of the company")
def list_users(
    db: DB,
    current: CurrentUserDep,
    q: str | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    current.require("core.user.view")
    stmt = select(User).where(User.deleted_at.is_(None))
    if q:
        stmt = stmt.where(User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    users = db.execute(stmt.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {
        "items": [
            {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "full_name_ar": user.full_name_ar,
                "job_title": user.job_title,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                "roles": _user_roles(db, user.id),
            }
            for user in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.post("/users", status_code=status.HTTP_201_CREATED, summary="Create a user with roles and access")
def create_user(payload: UserCreateRequest, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.create")
    auth = AuthService(db)
    company_ids = payload.company_ids or [current.company_id]
    user = auth.create_user(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        company_ids=company_ids,
        role_ids=payload.role_ids,
        full_name_ar=payload.full_name_ar,
        phone=payload.phone,
        job_title=payload.job_title,
        language=payload.language,
        is_active=payload.is_active,
        employee_id=payload.employee_id,
        data_scope=payload.data_scope,
    )
    for branch_id in payload.branch_ids:
        auth.grant_branch_access(user.id, branch_id, company_id=company_ids[0])
    for warehouse_id in payload.warehouse_ids:
        auth.grant_warehouse_access(user.id, warehouse_id, company_id=company_ids[0])
    db.flush()
    AuditService(db, audit_context(current)).log_action(
        "create", user, entity_type="user", label=user.email, new_values={"roles": [str(r) for r in payload.role_ids]}
    )
    return {"id": str(user.id), "email": user.email}


@router.patch("/users/{user_id}", summary="Update a user")
def update_user(user_id: uuid.UUID, payload: UserUpdateRequest, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.edit")
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found", id=str(user_id))
    auth = AuthService(db)
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        if field == "data_scope":
            for access in user.company_access:
                if access.company_id == current.company_id:
                    access.data_scope = value
            continue
        setattr(user, field, value)
    if payload.is_active is not None:
        auth.set_active(user, is_active=payload.is_active, actor_id=current.id)
    db.flush()
    AuditService(db, audit_context(current)).log_action("update", user, entity_type="user", label=user.email)
    return {"id": str(user.id), "updated": True}


@router.post("/users/{user_id}/roles/{role_id}", summary="Grant a role to a user")
def grant_role(user_id: uuid.UUID, role_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.edit")
    auth = AuthService(db)
    link = auth.assign_role(user_id, role_id, granted_by_id=current.id)
    db.flush()
    return {"id": str(link.id), "user_id": str(user_id), "role_id": str(role_id)}


@router.delete("/users/{user_id}/roles/{role_id}", summary="Revoke a role from a user")
def revoke_role(user_id: uuid.UUID, role_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.edit")
    AuthService(db).revoke_role(user_id, role_id)
    db.flush()
    return {"revoked": True}


@router.post("/users/{user_id}/reset-password", summary="Administrative password reset")
def admin_reset(user_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.edit")
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found", id=str(user_id))
    temporary = AuthService(db).admin_reset_password(user, actor_id=current.id)
    return {"temporary_password": temporary, "must_change_password": True}


def _user_roles(db: DB, user_id: uuid.UUID) -> list[str]:
    roles = db.execute(
        select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    ).all()
    return [row[0] for row in roles]


# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #
@router.get("/roles", summary="List roles with their permission counts")
def list_roles(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.role.view")
    roles = db.execute(
        select(Role).where(Role.company_id == current.company_id, Role.deleted_at.is_(None)).order_by(Role.level, Role.name)
    ).scalars().all()
    counts = dict(
        db.execute(
            select(RolePermission.role_id, func.count(RolePermission.id)).group_by(RolePermission.role_id)
        ).all()
    )
    return {
        "items": [
            {
                "id": str(role.id),
                "code": role.code,
                "name": role.name,
                "name_ar": role.name_ar,
                "level": role.level,
                "data_scope": role.data_scope,
                "is_system": role.is_system,
                "is_active": role.is_active,
                "permission_count": int(counts.get(role.id, 0)),
            }
            for role in roles
        ]
    }


@router.post("/roles", status_code=status.HTTP_201_CREATED, summary="Create a role from a template or explicit list")
def create_role(payload: RoleCreateRequest, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.role.create")
    from app.core.permissions import expand_role_template

    permissions = set(payload.permissions)
    if payload.template:
        _, permissions = expand_role_template(payload.template)
    role = Role(
        company_id=current.company_id,
        code=payload.code.strip().upper(),
        name=payload.name,
        name_ar=payload.name_ar,
        description=payload.description,
        data_scope=payload.data_scope,
        level=payload.level,
        is_system=False,
    )
    db.add(role)
    db.flush()
    _sync_role_permissions(db, role, permissions)
    AuditService(db, audit_context(current)).log_create(role, entity_type="role", label=role.code)
    return {"id": str(role.id), "code": role.code, "permissions": len(permissions)}


@router.patch("/roles/{role_id}", summary="Update a role")
def update_role(role_id: uuid.UUID, payload: RoleUpdateRequest, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.role.edit")
    role = db.get(Role, role_id)
    if role is None or role.company_id != current.company_id:
        raise NotFoundError("Role not found", id=str(role_id))
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(role, field, value)
    db.flush()
    AuditService(db, audit_context(current)).log_action("update", role, entity_type="role", label=role.code)
    return {"id": str(role.id), "updated": True}


@router.put("/roles/{role_id}/permissions", summary="Replace the permission matrix of a role")
def sync_role_permissions(
    role_id: uuid.UUID, payload: PermissionSyncRequest, db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("core.role.edit")
    role = db.get(Role, role_id)
    if role is None or role.company_id != current.company_id:
        raise NotFoundError("Role not found", id=str(role_id))
    if role.code == "company_admin":
        raise ValidationFailure("The company administrator role always keeps full access")
    count = _sync_role_permissions(db, role, set(payload.permissions))
    db.flush()
    AuditService(db, audit_context(current)).log_action(
        "permission_change",
        role,
        entity_type="role",
        label=role.code,
        new_values={"permissions": count},
    )
    return {"id": str(role.id), "permissions": count}


def _sync_role_permissions(db: DB, role: Role, codes: set[str]) -> int:
    existing = db.execute(select(RolePermission).where(RolePermission.role_id == role.id)).scalars().all()
    by_code: dict[str, Permission] = {
        permission.code: permission
        for permission in db.execute(select(Permission).where(Permission.code.in_(codes))).scalars().all()
    } if codes else {}
    keep = {permission.id for permission in by_code.values()}
    for link in existing:
        if link.permission_id not in keep:
            db.delete(link)
    current_ids = {link.permission_id for link in existing}
    for permission in by_code.values():
        if permission.id not in current_ids:
            db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.flush()
    return len(by_code)


# --------------------------------------------------------------------------- #
# Audit trail
# --------------------------------------------------------------------------- #
@router.get("/audit-logs", summary="Company audit trail")
def list_audit_logs(
    db: DB,
    current: CurrentUserDep,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    action: str | None = None,
    user_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    current.require("core.audit_log.view")
    stmt = select(AuditLog).where(AuditLog.company_id == current.company_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(row.id),
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id) if row.entity_id else None,
                "entity_label": row.entity_label,
                "user_email": row.user_email,
                "ip_address": row.ip_address,
                "old_values": row.old_values,
                "new_values": row.new_values,
                "remarks": row.remarks,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


__all__ = ["router"]
