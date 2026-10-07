"""Authentication, session management and authorization context.

Security properties
-------------------
* Passwords hashed with bcrypt (see :mod:`app.core.security`).
* Short lived JWT access tokens carrying tenant + session + password fingerprint.
* Opaque refresh tokens stored as SHA-256 digests, rotated on every refresh with
  reuse detection (a replayed old token revokes the whole session family).
* Failed login counting with lockout, per-device session list, remote revoke.
* Permissions resolved server side per company from roles + explicit grants.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import AuditAction, NotificationChannel
from app.core.errors import (
    AccountLockedError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailure,
)
from app.core.permissions import PermissionSet, all_permission_codes
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    generate_temporary_password,
    hash_password,
    hash_token,
    password_reset_expiry,
    refresh_token_expiry,
    validate_password_policy,
    verify_password,
)
from app.models.identity import (
    LoginAttempt,
    PasswordResetToken,
    Permission,
    Role,
    RolePermission,
    User,
    UserBranchAccess,
    UserCompanyAccess,
    UserRole,
    UserSession,
    UserWarehouseAccess,
)
from app.models.masterdata import Warehouse
from app.models.platform import Branch, Company, ModuleActivation
from app.services.audit_service import AuditContext, AuditService
from app.services.notification_service import NotificationService


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------------------------------------------------------- login
    def authenticate(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        company_id: uuid.UUID | None = None,
    ) -> User:
        email = (email or "").strip().lower()
        user = self.db.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        ).scalars().first()
        if user is None:
            self._record_attempt(email=email, success=False, reason="unknown_user", ip_address=ip_address, user_agent=user_agent)
            raise AuthenticationError("Invalid email or password")
        if user.locked_until and user.locked_until > datetime.now(UTC):
            self._record_attempt(
                email=email, user_id=user.id, success=False, reason="locked", ip_address=ip_address, user_agent=user_agent
            )
            raise AccountLockedError(
                "Account temporarily locked after repeated failed attempts",
                locked_until=user.locked_until.isoformat(),
            )
        if not user.is_active or user.deleted_at is not None:
            self._record_attempt(
                email=email, user_id=user.id, success=False, reason="inactive", ip_address=ip_address, user_agent=user_agent
            )
            raise AuthenticationError("This account is disabled")
        if user.is_locked:
            raise AccountLockedError("This account is locked, contact an administrator")

        if not verify_password(password, user.password_hash):
            user.failed_login_attempts = int(user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.login_max_failed_attempts:
                from datetime import timedelta

                user.locked_until = datetime.now(UTC) + timedelta(minutes=settings.login_lockout_minutes)
            self.db.flush()
            self._record_attempt(
                email=email, user_id=user.id, success=False, reason="bad_password", ip_address=ip_address, user_agent=user_agent
            )
            raise AuthenticationError(
                "Invalid email or password",
                attempts_left=max(0, settings.login_max_failed_attempts - user.failed_login_attempts),
            )

        if company_id is not None and not user.is_superuser:
            if not self.has_company_access(user.id, company_id):
                raise PermissionDeniedError("You do not have access to the requested company")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(UTC)
        user.last_login_ip = ip_address
        self.db.flush()
        self._record_attempt(
            email=email, user_id=user.id, success=True, ip_address=ip_address, user_agent=user_agent
        )
        return user

    def _record_attempt(
        self,
        *,
        email: str,
        success: bool,
        user_id: uuid.UUID | None = None,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.db.add(
            LoginAttempt(
                email=email[:190] if email else None,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=(user_agent or "")[:400] or None,
                success=success,
                failure_reason=reason,
            )
        )
        self.db.flush()

    # --------------------------------------------------------------- sessions
    def create_session(
        self,
        user: User,
        *,
        company_id: uuid.UUID | None = None,
        device_name: str | None = None,
        device_type: str | None = None,
        platform: str | None = None,
        app_version: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        company_id = company_id or user.default_company_id or self.default_company_for(user)
        if company_id is None:
            raise BusinessRuleError("No company is available for this user; contact an administrator")
        if not user.is_superuser and not self.has_company_access(user.id, company_id):
            raise PermissionDeniedError("You do not have access to this company")

        refresh_token = generate_opaque_token()
        session = UserSession(
            user_id=user.id,
            company_id=company_id,
            refresh_token_hash=hash_token(refresh_token),
            device_name=device_name,
            device_type=device_type,
            platform=platform,
            app_version=app_version,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:400] or None,
            is_active=True,
            last_seen_at=datetime.now(UTC),
            expires_at=refresh_token_expiry(),
        )
        self.db.add(session)
        self.db.flush()

        permissions = self.resolve_permissions(user, company_id)
        access_token, expires_at = create_access_token(
            user_id=user.id,
            company_id=company_id,
            session_id=session.id,
            password_hash=user.password_hash,
            permissions_version=user.permissions_version,
        )
        self._audit(user, company_id, session.id, AuditAction.LOGIN, ip_address, user_agent)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_at": expires_at,
            "expires_in": int((expires_at - datetime.now(UTC)).total_seconds()),
            "session_id": session.id,
            "company_id": company_id,
            "permissions": permissions.as_sorted_list(),
            "must_change_password": user.must_change_password,
        }

    def refresh(self, refresh_token: str, *, ip_address: str | None = None, user_agent: str | None = None) -> dict[str, Any]:
        digest = hash_token(refresh_token)
        session = self.db.execute(
            select(UserSession).where(UserSession.refresh_token_hash == digest)
        ).scalars().first()

        if session is None:
            # Possible reuse of a rotated token: revoke the whole family.
            previous = self.db.execute(
                select(UserSession).where(UserSession.previous_refresh_token_hash == digest)
            ).scalars().first()
            if previous is not None:
                self._revoke_session(previous, reason="refresh_token_reuse")
                self.revoke_all_sessions(previous.user_id, reason="refresh_token_reuse")
                raise AuthenticationError("Refresh token reuse detected; all sessions were revoked")
            raise AuthenticationError("Invalid refresh token")

        if not session.is_active or session.revoked_at is not None:
            raise AuthenticationError("This session has been revoked")
        if session.expires_at and session.expires_at < datetime.now(UTC):
            raise AuthenticationError("Session expired, please sign in again")

        user = self.db.get(User, session.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("This account is no longer active")

        new_refresh = generate_opaque_token()
        session.previous_refresh_token_hash = session.refresh_token_hash
        session.refresh_token_hash = hash_token(new_refresh)
        session.last_seen_at = datetime.now(UTC)
        session.expires_at = refresh_token_expiry()
        if ip_address:
            session.ip_address = ip_address
        self.db.flush()

        permissions = self.resolve_permissions(user, session.company_id)
        access_token, expires_at = create_access_token(
            user_id=user.id,
            company_id=session.company_id,
            session_id=session.id,
            password_hash=user.password_hash,
            permissions_version=user.permissions_version,
        )
        return {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_at": expires_at,
            "expires_in": int((expires_at - datetime.now(UTC)).total_seconds()),
            "session_id": session.id,
            "company_id": session.company_id,
            "permissions": permissions.as_sorted_list(),
            "must_change_password": user.must_change_password,
        }

    def logout(self, session_id: uuid.UUID, *, user_id: uuid.UUID | None = None, reason: str = "user_logout") -> None:
        session = self.db.get(UserSession, session_id)
        if session is None:
            raise NotFoundError("Session not found")
        if user_id and session.user_id != user_id:
            raise PermissionDeniedError("You can only close your own sessions")
        self._revoke_session(session, reason=reason)
        user = self.db.get(User, session.user_id)
        if user:
            self._audit(user, session.company_id, session.id, AuditAction.LOGOUT, session.ip_address, session.user_agent)

    def revoke_session_by_token(self, refresh_token: str, *, reason: str = "logout") -> None:
        digest = hash_token(refresh_token)
        session = self.db.execute(
            select(UserSession).where(
                (UserSession.refresh_token_hash == digest) | (UserSession.previous_refresh_token_hash == digest)
            )
        ).scalars().first()
        if session is not None:
            self._revoke_session(session, reason=reason)

    def _revoke_session(self, session: UserSession, *, reason: str) -> None:
        session.is_active = False
        session.revoked_at = datetime.now(UTC)
        session.revoked_reason = reason
        session.refresh_token_hash = hash_token(generate_opaque_token())
        self.db.flush()

    def revoke_all_sessions(self, user_id: uuid.UUID, *, reason: str = "logout_all", except_session_id: uuid.UUID | None = None) -> int:
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.is_active.is_(True))
            .values(is_active=False, revoked_at=datetime.now(UTC), revoked_reason=reason)
        )
        if except_session_id:
            stmt = stmt.where(UserSession.id != except_session_id)
        result = self.db.execute(stmt)
        self.db.flush()
        return int(result.rowcount or 0)

    def list_sessions(self, user_id: uuid.UUID, *, include_inactive: bool = False) -> list[UserSession]:
        stmt = select(UserSession).where(UserSession.user_id == user_id)
        if not include_inactive:
            stmt = stmt.where(UserSession.is_active.is_(True))
        return list(self.db.execute(stmt.order_by(UserSession.created_at.desc())).scalars().all())

    def validate_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> UserSession:
        session = self.db.get(UserSession, session_id)
        if session is None or session.user_id != user_id:
            raise AuthenticationError("Session not found")
        if not session.is_active or session.revoked_at is not None:
            raise AuthenticationError("Session revoked")
        return session

    # -------------------------------------------------------------- passwords
    def change_password(
        self, user: User, *, current_password: str, new_password: str, keep_session_id: uuid.UUID | None = None
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("The current password is incorrect")
        if verify_password(new_password, user.password_hash):
            raise ValidationFailure("The new password must be different from the current one")
        user.password_hash = hash_password(new_password)
        user.password_changed_at = datetime.now(UTC)
        user.must_change_password = False
        user.permissions_version = int(user.permissions_version or 0) + 1
        self.db.flush()
        self.revoke_all_sessions(user.id, reason="password_changed", except_session_id=keep_session_id)
        self._audit(user, user.default_company_id, keep_session_id, AuditAction.PERMISSION_CHANGE, None, None, remarks="password changed")

    def request_password_reset(self, email: str, *, ip_address: str | None = None) -> dict[str, Any]:
        email = (email or "").strip().lower()
        user = self.db.execute(select(User).where(User.email == email)).scalars().first()
        # Always answer the same way to avoid account enumeration.
        if user is None or not user.is_active:
            return {"sent": True, "delivery": "email"}
        raw_token = generate_opaque_token(32)
        self.db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=password_reset_expiry(),
                requested_ip=ip_address,
            )
        )
        self.db.flush()
        if user.default_company_id:
            NotificationService(self.db, user.default_company_id).queue_message(
                channel=NotificationChannel.EMAIL.value,
                recipient=user.email,
                subject="Kayan ERP password reset",
                body=(
                    "Use the following token to reset your password. "
                    f"It expires in {settings.password_reset_expire_minutes} minutes."
                ),
                payload={"user_id": str(user.id)},
                template_code="password_reset",
            )
        return {
            "sent": True,
            "delivery": "email",
            # Only exposed outside production to make local testing possible.
            "reset_token": None if settings.is_production else raw_token,
        }

    def reset_password(self, token: str, new_password: str) -> User:
        digest = hash_token(token)
        record = self.db.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == digest)
        ).scalars().first()
        if record is None or record.used_at is not None:
            raise ValidationFailure("This reset token is invalid or already used")
        if record.expires_at < datetime.now(UTC):
            raise ValidationFailure("This reset token has expired")
        user = self.db.get(User, record.user_id)
        if user is None:
            raise NotFoundError("User not found")
        validate_password_policy(new_password)
        user.password_hash = hash_password(new_password)
        user.password_changed_at = datetime.now(UTC)
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.locked_until = None
        user.permissions_version = int(user.permissions_version or 0) + 1
        record.used_at = datetime.now(UTC)
        self.db.flush()
        self.revoke_all_sessions(user.id, reason="password_reset")
        return user

    def admin_reset_password(self, user: User, *, actor_id: uuid.UUID | None = None) -> str:
        temporary = generate_temporary_password()
        user.password_hash = hash_password(temporary)
        user.must_change_password = True
        user.failed_login_attempts = 0
        user.locked_until = None
        user.permissions_version = int(user.permissions_version or 0) + 1
        self.db.flush()
        self.revoke_all_sessions(user.id, reason="admin_reset")
        self.db.info.setdefault("temporary_password", temporary)
        return temporary

    def set_active(self, user: User, *, is_active: bool, actor_id: uuid.UUID | None = None) -> User:
        user.is_active = is_active
        if not is_active:
            self.revoke_all_sessions(user.id, reason="account_deactivated")
        self.db.flush()
        return user

    # ------------------------------------------------------------- permissions
    def resolve_permissions(self, user: User, company_id: uuid.UUID | None) -> PermissionSet:
        if user.is_superuser:
            return PermissionSet(all_permission_codes())
        if company_id is None:
            return PermissionSet([])
        rows = self.db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user.id,
                UserRole.company_id == company_id,
                Role.company_id == company_id,
                Role.is_active.is_(True),
                Role.deleted_at.is_(None),
            )
        ).scalars().all()
        return PermissionSet(rows)

    def has_company_access(self, user_id: uuid.UUID, company_id: uuid.UUID) -> bool:
        access = self.db.execute(
            select(UserCompanyAccess).where(
                UserCompanyAccess.user_id == user_id, UserCompanyAccess.company_id == company_id
            )
        ).scalars().first()
        if access is None:
            return False
        if not access.is_active:
            return False
        if access.expires_at and access.expires_at < datetime.now(UTC):
            return False
        return True

    def default_company_for(self, user: User) -> uuid.UUID | None:
        if user.default_company_id:
            return user.default_company_id
        access = self.db.execute(
            select(UserCompanyAccess)
            .where(UserCompanyAccess.user_id == user.id, UserCompanyAccess.is_active.is_(True))
            .order_by(UserCompanyAccess.is_default.desc(), UserCompanyAccess.created_at.asc())
        ).scalars().first()
        return access.company_id if access else None

    def accessible_companies(self, user: User) -> list[dict[str, Any]]:
        if user.is_superuser:
            companies = self.db.execute(
                select(Company).where(Company.deleted_at.is_(None), Company.is_active.is_(True))
            ).scalars().all()
            return [
                {"id": company.id, "code": company.code, "name": company.name, "is_default": company.id == user.default_company_id}
                for company in companies
            ]
        rows = self.db.execute(
            select(Company, UserCompanyAccess)
            .join(UserCompanyAccess, UserCompanyAccess.company_id == Company.id)
            .where(
                UserCompanyAccess.user_id == user.id,
                UserCompanyAccess.is_active.is_(True),
                Company.is_active.is_(True),
                Company.deleted_at.is_(None),
            )
        ).all()
        return [
            {
                "id": company.id,
                "code": company.code,
                "name": company.name,
                "name_ar": company.name_ar,
                "base_currency_code": company.base_currency_code,
                "is_default": access.is_default or company.id == user.default_company_id,
                "data_scope": access.data_scope,
            }
            for company, access in rows
        ]

    def accessible_branches(self, user: User, company_id: uuid.UUID) -> list[uuid.UUID] | None:
        """``None`` means "all branches of the company"."""
        if user.is_superuser:
            return None
        access = self.db.execute(
            select(UserCompanyAccess).where(
                UserCompanyAccess.user_id == user.id, UserCompanyAccess.company_id == company_id
            )
        ).scalars().first()
        if access is not None and access.data_scope == "all_branches":
            return None
        rows = self.db.execute(
            select(UserBranchAccess.branch_id).where(
                UserBranchAccess.user_id == user.id, UserBranchAccess.company_id == company_id
            )
        ).scalars().all()
        if not rows:
            # Fall back to the company scope when no explicit limitation exists.
            return None if (access is None or access.data_scope == "all_branches") else []
        return list(rows)

    def accessible_warehouses(self, user: User, company_id: uuid.UUID) -> list[uuid.UUID] | None:
        if user.is_superuser:
            return None
        rows = self.db.execute(
            select(UserWarehouseAccess.warehouse_id).where(
                UserWarehouseAccess.user_id == user.id, UserWarehouseAccess.company_id == company_id
            )
        ).scalars().all()
        return list(rows) or None

    def data_scope(self, user: User, company_id: uuid.UUID) -> str:
        if user.is_superuser:
            return "all_branches"
        access = self.db.execute(
            select(UserCompanyAccess).where(
                UserCompanyAccess.user_id == user.id, UserCompanyAccess.company_id == company_id
            )
        ).scalars().first()
        return access.data_scope if access else "own_records"

    def enabled_modules(self, company_id: uuid.UUID) -> list[str]:
        rows = self.db.execute(
            select(ModuleActivation.module_key).where(
                ModuleActivation.company_id == company_id, ModuleActivation.is_enabled.is_(True)
            )
        ).scalars().all()
        return list(rows)

    def user_profile(self, user: User, company_id: uuid.UUID, *, session_id: uuid.UUID | None = None) -> dict[str, Any]:
        permissions = self.resolve_permissions(user, company_id)
        roles = self.db.execute(
            select(Role.code, Role.name, Role.name_ar, Role.level, Role.data_scope)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id, UserRole.company_id == company_id)
        ).all()
        company = self.db.get(Company, company_id)
        branches: list[dict[str, Any]] = []
        allowed = self.accessible_branches(user, company_id)
        branch_stmt = select(Branch).where(Branch.company_id == company_id, Branch.is_active.is_(True))
        if allowed is not None:
            branch_stmt = branch_stmt.where(Branch.id.in_(allowed or [uuid.uuid4()]))
        for branch in self.db.execute(branch_stmt.order_by(Branch.code)).scalars().all():
            branches.append({"id": branch.id, "code": branch.code, "name": branch.name, "is_head_office": branch.is_head_office})
        warehouses = self.db.execute(
            select(Warehouse).where(Warehouse.company_id == company_id, Warehouse.is_active.is_(True))
        ).scalars().all()
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "full_name_ar": user.full_name_ar,
                "job_title": user.job_title,
                "language": user.language,
                "theme": user.theme,
                "avatar_url": user.avatar_url,
                "is_superuser": user.is_superuser,
                "must_change_password": user.must_change_password,
            },
            "company": (
                {
                    "id": company.id,
                    "code": company.code,
                    "name": company.name,
                    "name_ar": company.name_ar,
                    "base_currency_code": company.base_currency_code,
                    "logo_url": company.logo_url,
                }
                if company
                else None
            ),
            "companies": self.accessible_companies(user),
            "roles": [
                {"code": code, "name": name, "name_ar": name_ar, "level": level, "data_scope": scope}
                for code, name, name_ar, level, scope in roles
            ],
            "permissions": permissions.as_sorted_list(),
            "branches": branches,
            "warehouses": [
                {"id": warehouse.id, "code": warehouse.code, "name": warehouse.name} for warehouse in warehouses
            ],
            "modules": self.enabled_modules(company_id),
            "data_scope": self.data_scope(user, company_id),
            "session_id": session_id,
        }

    def switch_company(self, user: User, company_id: uuid.UUID, *, session_id: uuid.UUID | None = None) -> dict[str, Any]:
        if not user.is_superuser and not self.has_company_access(user.id, company_id):
            raise PermissionDeniedError("You do not have access to this company")
        session = None
        if session_id:
            session = self.validate_session(session_id, user.id)
            session.company_id = company_id
            self.db.flush()
        return self.create_session(
            user,
            company_id=company_id,
            device_name=session.device_name if session else None,
            device_type=session.device_type if session else None,
            platform=session.platform if session else None,
            app_version=session.app_version if session else None,
            ip_address=session.ip_address if session else None,
            user_agent=session.user_agent if session else None,
        )

    # ------------------------------------------------------------------ helpers
    def create_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        company_ids: list[uuid.UUID],
        role_ids: list[uuid.UUID] | None = None,
        **extra: Any,
    ) -> User:
        email = email.strip().lower()
        existing = self.db.execute(select(User).where(User.email == email)).scalars().first()
        if existing is not None:
            raise ConflictError("A user with this email already exists")
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            default_company_id=company_ids[0] if company_ids else None,
            **{key: value for key, value in extra.items() if hasattr(User, key)},
        )
        self.db.add(user)
        self.db.flush()
        for index, company_id in enumerate(company_ids):
            self.db.add(
                UserCompanyAccess(
                    user_id=user.id, company_id=company_id, is_default=index == 0, data_scope=extra.get("data_scope", "all_branches")
                )
            )
        for role_id in role_ids or []:
            role = self.db.get(Role, role_id)
            if role is None:
                continue
            self.db.add(UserRole(user_id=user.id, role_id=role.id, company_id=role.company_id))
        self.db.flush()
        return user

    def assign_role(self, user_id: uuid.UUID, role_id: uuid.UUID, *, granted_by_id: uuid.UUID | None = None) -> UserRole:
        role = self.db.get(Role, role_id)
        if role is None:
            raise NotFoundError("Role not found")
        existing = self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        ).scalars().first()
        if existing:
            return existing
        link = UserRole(
            user_id=user_id, role_id=role_id, company_id=role.company_id, granted_by_id=granted_by_id, granted_at=datetime.now(UTC)
        )
        self.db.add(link)
        self._bump_permissions_version(user_id)
        self.db.flush()
        return link

    def revoke_role(self, user_id: uuid.UUID, role_id: uuid.UUID) -> None:
        link = self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        ).scalars().first()
        if link is None:
            raise NotFoundError("The user does not have this role")
        self.db.delete(link)
        self._bump_permissions_version(user_id)
        self.db.flush()

    def _bump_permissions_version(self, user_id: uuid.UUID) -> None:
        user = self.db.get(User, user_id)
        if user:
            user.permissions_version = int(user.permissions_version or 0) + 1

    def _audit(
        self,
        user: User,
        company_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
        action: AuditAction,
        ip_address: str | None,
        user_agent: str | None,
        remarks: str | None = None,
    ) -> None:
        if company_id is None:
            return
        AuditService(
            self.db,
            AuditContext(
                company_id=company_id,
                user_id=user.id,
                user_email=user.email,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
            ),
        ).record(
            action=action,
            entity_type="user_session",
            entity_id=session_id,
            entity_label=user.email,
            remarks=remarks,
        )
