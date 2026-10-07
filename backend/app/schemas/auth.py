"""Authentication, session and user/role administration schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    company_id: uuid.UUID | None = None
    device_name: str | None = Field(None, max_length=120)
    remember_me: bool = False


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_at: datetime
    session_id: uuid.UUID
    company_id: uuid.UUID | None = None
    must_change_password: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None
    all_devices: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=20)
    new_password: str = Field(..., min_length=8, max_length=128)


class UserSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_name: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    is_active: bool
    created_at: datetime
    last_seen_at: datetime | None = None
    expires_at: datetime | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    username: str | None = None
    full_name: str
    full_name_ar: str | None = None
    phone: str | None = None
    job_title: str | None = None
    language: str | None = None
    is_active: bool
    is_superuser: bool
    default_company_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None
    last_login_at: datetime | None = None
    created_at: datetime


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=160)
    full_name_ar: str | None = Field(None, max_length=160)
    phone: str | None = Field(None, max_length=40)
    job_title: str | None = Field(None, max_length=120)
    company_ids: list[uuid.UUID] = Field(default_factory=list)
    role_ids: list[uuid.UUID] = Field(default_factory=list)
    branch_ids: list[uuid.UUID] = Field(default_factory=list)
    warehouse_ids: list[uuid.UUID] = Field(default_factory=list)
    data_scope: str = Field("all_branches", pattern="^(all_branches|specific_branches|own_records)$")
    language: str = Field("ar", pattern="^(ar|en)$")
    is_active: bool = True
    employee_id: uuid.UUID | None = None


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=160)
    full_name_ar: str | None = None
    phone: str | None = None
    job_title: str | None = None
    language: str | None = Field(None, pattern="^(ar|en)$")
    is_active: bool | None = None
    data_scope: str | None = Field(None, pattern="^(all_branches|specific_branches|own_records)$")


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    name_ar: str | None = None
    description: str | None = None
    data_scope: str
    level: int
    is_system: bool
    is_active: bool


class RoleCreateRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=120)
    name_ar: str | None = None
    description: str | None = None
    data_scope: str = Field("all_branches", pattern="^(all_branches|specific_branches|own_records)$")
    level: int = Field(10, ge=1, le=99)
    template: str | None = Field(
        None, description="Optional ROLE_TEMPLATES key to seed the permission matrix from"
    )
    permissions: list[str] = Field(default_factory=list)


class RoleUpdateRequest(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    description: str | None = None
    data_scope: str | None = Field(None, pattern="^(all_branches|specific_branches|own_records)$")
    level: int | None = Field(None, ge=1, le=99)
    is_active: bool | None = None


class PermissionSyncRequest(BaseModel):
    permissions: list[str] = Field(default_factory=list)


class ProfileOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    full_name_ar: str | None = None
    language: str | None = None
    timezone: str | None = None
    theme: str | None = None
    job_title: str | None = None
    is_superuser: bool
    permissions_version: int


class CompanyAccessOut(BaseModel):
    company_id: uuid.UUID
    company_name: str
    company_code: str
    is_default: bool
    data_scope: str
    roles: list[str] = Field(default_factory=list)
    base_currency_code: str | None = None


class BootstrapStatusOut(BaseModel):
    needs_setup: bool
    companies: int
    users: int


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID | None = None
    entity_label: str | None = None
    user_id: uuid.UUID | None = None
    user_email: str | None = None
    ip_address: str | None = None
    session_id: uuid.UUID | None = None
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None
    remarks: str | None = None
    created_at: datetime


__all__ = [
    "AuditLogOut",
    "BootstrapStatusOut",
    "ChangePasswordRequest",
    "CompanyAccessOut",
    "ForgotPasswordRequest",
    "LoginRequest",
    "LogoutRequest",
    "PermissionSyncRequest",
    "ProfileOut",
    "RefreshRequest",
    "ResetPasswordRequest",
    "RoleCreateRequest",
    "RoleOut",
    "RoleUpdateRequest",
    "TokenPair",
    "UserCreateRequest",
    "UserOut",
    "UserSessionOut",
    "UserUpdateRequest",
]
