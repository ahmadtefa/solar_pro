"""Identity, RBAC, sessions, audit trail and notifications."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AuditAction, NotificationChannel, NotificationType
from app.models.base import (
    Base,
    CompanyScoped,
    JSONType,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


# --------------------------------------------------------------------------- #
# Users and access
# --------------------------------------------------------------------------- #
class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A person able to sign in.  Users are global; company access is granted
    explicitly through ``UserCompanyAccess`` so one person can work across
    several companies of the group."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(190), nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    full_name_ar: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    job_title: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(5), default="ar", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Cairo", nullable=False)
    theme: Mapped[str] = mapped_column(String(16), default="system", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(String(64))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    permissions_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    default_company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id"))
    employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))

    company_access: Mapped[list[UserCompanyAccess]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="UserCompanyAccess.user_id"
    )
    user_roles: Mapped[list[UserRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="UserRole.user_id"
    )

    __table_args__ = (Index("ix_users_active", "is_active"),)


class Role(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Roles are defined per company so each tenant controls its own matrix."""

    __tablename__ = "roles"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: all_branches | specific_branches | own_records
    data_scope: Mapped[str] = mapped_column(String(24), default="all_branches", nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    role_permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_roles_company_code"),)


class Permission(Base, UUIDMixin, TimestampMixin):
    """Global permission catalogue: ``<module>.<entity>.<action>``."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    module: Mapped[str] = mapped_column(String(48), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(String(250))
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_permissions_module_entity", "module", "entity"),)


class RolePermission(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: optional fine grained constraint, e.g. {"max_amount": 10000}
    constraints_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    role: Mapped[Role] = relationship(back_populates="role_permissions")
    permission: Mapped[Permission] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_pair"),)


class UserRole(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="user_roles", foreign_keys=[user_id])
    role: Mapped[Role] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_pair"),)


class UserCompanyAccess(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_company_access"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: all_branches | specific_branches | own_records
    data_scope: Mapped[str] = mapped_column(String(24), default="all_branches", nullable=False)
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="company_access", foreign_keys=[user_id])
    company: Mapped[Company] = relationship()  # noqa: F821 - resolved at runtime

    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_user_company_access_pair"),)


class UserBranchAccess(Base, UUIDMixin, TimestampMixin):
    """Data level restriction: which branches a user may operate on."""

    __tablename__ = "user_branch_access"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    can_view: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_transact: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "branch_id", name="uq_user_branch_access_pair"),)


class UserWarehouseAccess(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_warehouse_access"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    can_view: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_transact: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "warehouse_id", name="uq_user_warehouse_access_pair"),)


class UserSession(Base, UUIDMixin, TimestampMixin):
    """Device / session tracking - enables remote logout and token revocation."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    previous_refresh_token_hash: Mapped[str | None] = mapped_column(String(128))
    device_name: Mapped[str | None] = mapped_column(String(160))
    device_type: Mapped[str | None] = mapped_column(String(40))
    platform: Mapped[str | None] = mapped_column(String(40))
    app_version: Mapped[str | None] = mapped_column(String(32))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(120))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_user_sessions_user_active", "user_id", "is_active"),)


class LoginAttempt(Base, UUIDMixin, TimestampMixin):
    """Brute force protection telemetry."""

    __tablename__ = "login_attempts"

    email: Mapped[str | None] = mapped_column(String(190), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(120))

    __table_args__ = (Index("ix_login_attempts_email_created", "email", "created_at"),)


class PasswordResetToken(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip: Mapped[str | None] = mapped_column(String(64))
    delivery_channel: Mapped[str] = mapped_column(String(24), default=NotificationChannel.EMAIL.value, nullable=False)


# --------------------------------------------------------------------------- #
# Audit trail
# --------------------------------------------------------------------------- #
class AuditLog(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Append-only audit trail.  Rows are never updated or deleted by the API."""

    __tablename__ = "audit_logs"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    user_email: Mapped[str | None] = mapped_column(String(190))
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    entity_label: Mapped[str | None] = mapped_column(String(250))
    old_values: Mapped[dict | None] = mapped_column(JSONType)
    new_values: Mapped[dict | None] = mapped_column(JSONType)
    changed_fields: Mapped[list | None] = mapped_column(JSONType)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    request_id: Mapped[str | None] = mapped_column(String(64))
    remarks: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_audit_logs_entity", "company_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_company_created", "company_id", "created_at"),
    )


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
class Notification(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "notifications"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    notification_type: Mapped[str] = mapped_column(String(24), default=NotificationType.INFO.value, nullable=False)
    channel: Mapped[str] = mapped_column(String(24), default=NotificationChannel.IN_APP.value, nullable=False)
    module: Mapped[str | None] = mapped_column(String(48))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    action_url: Mapped[str | None] = mapped_column(String(400))
    payload_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    delivery_error: Mapped[str | None] = mapped_column(String(400))

    __table_args__ = (Index("ix_notifications_user_read", "user_id", "is_read", "created_at"),)


class NotificationPreference(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "notification_preferences"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module: Mapped[str] = mapped_column(String(48), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    quiet_hours_start: Mapped[str | None] = mapped_column(String(5))
    quiet_hours_end: Mapped[str | None] = mapped_column(String(5))

    __table_args__ = (
        UniqueConstraint("user_id", "module", "channel", name="uq_notification_preferences_scope"),
    )


class OutboxMessage(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Outbound message queue for email/SMS/WhatsApp/push providers.

    Providers are pluggable; when no provider is configured the message stays in
    ``queued`` state so nothing is silently lost.
    """

    __tablename__ = "outbox_messages"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    recipient: Mapped[str] = mapped_column(String(250), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(250))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    template_code: Mapped[str | None] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("attempts >= 0", name="attempts_non_negative"),)


class Attachment(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Generic document management: any entity can own attachments."""

    __tablename__ = "attachments"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    file_name: Mapped[str] = mapped_column(String(250), nullable=False)
    original_file_name: Mapped[str | None] = mapped_column(String(250))
    content_type: Mapped[str | None] = mapped_column(String(120))
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    __table_args__ = (
        Index("ix_attachments_entity", "company_id", "entity_type", "entity_id"),
        CheckConstraint("file_size >= 0", name="file_size_non_negative"),
    )


class SavedReport(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """User-visible report definitions for the reporting engine."""

    __tablename__ = "saved_reports"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    module: Mapped[str] = mapped_column(String(48), nullable=False)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    definition_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_saved_reports_company_code"),)


class ImportJob(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Import pipeline: upload -> map -> validate -> preview -> commit."""

    __tablename__ = "import_jobs"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(250))
    storage_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="uploaded", nullable=False)
    column_mapping: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    options_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text)


class ImportJobRow(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "import_job_rows"

    import_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    normalized_data: Mapped[dict | None] = mapped_column(JSONType)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    errors: Mapped[list | None] = mapped_column(JSONType)
    imported_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    import_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)


class BackupJob(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Backup bookkeeping.  ``company_id`` is nullable for full-server backups
    so the column is declared without the NOT NULL constraint."""

    __tablename__ = "backup_jobs"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    file_name: Mapped[str] = mapped_column(String(250), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500))
    backup_type: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    scope: Mapped[str] = mapped_column(String(24), default="full", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)
