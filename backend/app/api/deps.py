"""FastAPI dependencies: database session, authentication, tenant and permissions."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, set_session_tenant
from app.core.errors import (
    AppError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    TenantError,
    ValidationFailure,
)
from app.core.permissions import PermissionSet
from app.core.security import decode_token
from app.models.identity import User, UserSession
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token issued by /auth/login")

#: Status codes raised by service layer errors.
_ERROR_STATUS: dict[type[AppError], int] = {
    ValidationFailure: status.HTTP_422_UNPROCESSABLE_ENTITY,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    TenantError: status.HTTP_403_FORBIDDEN,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
}


def get_db() -> Iterator[Session]:
    """Request scoped session; the tenant filter is applied per request below."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except AppError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DB = Annotated[Session, Depends(get_db)]


class CurrentUser:
    """Authenticated principal with the resolved company and permission set."""

    def __init__(
        self,
        user: User,
        session: UserSession,
        company_id: uuid.UUID | None,
        permissions: PermissionSet,
        *,
        branch_ids: list[uuid.UUID] | None = None,
        warehouse_ids: list[uuid.UUID] | None = None,
        data_scope: str = "all_branches",
    ) -> None:
        self.user = user
        self.session = session
        self.company_id = company_id
        self.permissions = permissions
        self.branch_ids = branch_ids
        self.warehouse_ids = warehouse_ids
        self.data_scope = data_scope

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def is_superuser(self) -> bool:
        return bool(self.user.is_superuser)

    def can(self, code: str) -> bool:
        return self.is_superuser or self.permissions.has(code)

    def can_any(self, *codes: str) -> bool:
        return self.is_superuser or self.permissions.any_of(*codes)

    def require(self, code: str) -> None:
        if not self.can(code):
            raise PermissionDeniedError(f"Missing permission: {code}", permission=code)


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None,
    header_token: str | None,
) -> str:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    if header_token:
        return header_token.removeprefix("Bearer ").strip()
    raise AuthenticationError("Authentication required")


def get_current_user(
    request: Request,
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    authorization: Annotated[str | None, Header(include_in_schema=False)] = None,
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
) -> CurrentUser:
    """Resolve the JWT into the user, the active company and the permission set."""
    token = _extract_token(credentials, authorization)
    payload = decode_token(token, expected_type="access")

    user_id = uuid.UUID(str(payload.get("sub")))
    session_id = uuid.UUID(str(payload.get("sid"))) if payload.get("sid") else None
    auth = AuthService(db)
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("The account is not active")
    if session_id is None:
        raise AuthenticationError("The token has no session")
    session = auth.validate_session(session_id, user.id)

    token_company = uuid.UUID(str(payload["cid"])) if payload.get("cid") else None
    requested_company = uuid.UUID(x_company_id) if x_company_id else None
    company_id = requested_company or token_company or auth.default_company_for(user)
    if company_id is None:
        raise TenantError("No company is available for this user")
    if not user.is_superuser and not auth.has_company_access(user.id, company_id):
        raise TenantError("You do not have access to this company", company_id=str(company_id))
    if token_company is not None and company_id != token_company:
        # Switching company requires the session to be re-issued for that company.
        if not auth.has_company_access(user.id, company_id):
            raise TenantError("You do not have access to this company", company_id=str(company_id))

    request.state.company_id = company_id
    request.state.user_id = user.id
    request.state.session_id = session.id
    set_session_tenant(db, company_id)
    if payload.get("locale"):
        request.state.locale = payload["locale"]
    return CurrentUser(
        user=user,
        session=session,
        company_id=company_id,
        permissions=auth.resolve_permissions(user, company_id),
        branch_ids=auth.accessible_branches(user, company_id),
        warehouse_ids=auth.accessible_warehouses(user, company_id),
        data_scope=auth.data_scope(user, company_id),
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require(permission: str):
    """Dependency factory enforcing a single permission code server side."""

    def dependency(current: CurrentUserDep) -> CurrentUser:
        current.require(permission)
        return current

    return dependency


def require_any(*permissions: str):
    def dependency(current: CurrentUserDep) -> CurrentUser:
        if not current.can_any(*permissions):
            raise PermissionDeniedError(
                "Missing permissions: " + ", ".join(permissions), permissions=list(permissions)
            )
        return current

    return dependency


def company_scope(current: CurrentUser) -> uuid.UUID:
    """Every service call must be scoped with the resolved tenant id."""
    if current.company_id is None:  # pragma: no cover - guarded by get_current_user
        raise TenantError("No active company for this request")
    return current.company_id


def audit_context(current: CurrentUser, request: Request | None = None) -> Any:
    from app.services.audit_service import AuditContext

    return AuditContext(
        company_id=current.company_id,
        user_id=current.id,
        user_email=current.user.email,
        session_id=current.session.id,
        ip_address=request.client.host if request is not None and request.client else None,
        user_agent=request.headers.get("user-agent") if request is not None else None,
        request_id=request.headers.get("x-request-id") if request is not None else None,
    )


def settings_dependency() -> Any:
    """Expose the runtime settings object (used by health and version endpoints)."""
    return settings


def http_error_from(exc: AppError) -> HTTPException:
    code = _ERROR_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=code, detail={"error": exc.__class__.__name__, "message": str(exc)})


__all__ = [
    "CurrentUser",
    "CurrentUserDep",
    "DB",
    "audit_context",
    "company_scope",
    "get_current_user",
    "get_db",
    "require",
    "require_any",
]
