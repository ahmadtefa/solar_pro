"""Backup: manual and scheduled dumps, verification, retention and restore guidance.

PostgreSQL is dumped with ``pg_dump`` (custom format) into the configured backup
directory; SQLite deployments are backed up by copying the database file.  Every
run is recorded in ``backup_jobs`` with size, checksum and duration so the admin
UI can show a real history instead of a placeholder.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess  # noqa: S404 - pg_dump path is configured, arguments are not user supplied
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import AuditAction
from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError, ValidationFailure
from app.models.identity import BackupJob, User
from app.models.platform import SystemSetting
from app.services.audit_service import AuditContext, AuditService

#: Permission required to run or restore backups.
BACKUP_PERMISSION = "core.backup.create"
RESTORE_PERMISSION = "core.backup.execute"


class BackupService:
    """Backup orchestration, verification and retention."""

    def __init__(self, db: Session, company_id: uuid.UUID | None = None, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    # ----------------------------------------------------------------- helpers
    def backup_directory(self) -> Path:
        configured = (
            self.db.execute(
                select(SystemSetting).where(
                    SystemSetting.company_id == self.company_id,
                    SystemSetting.key == "backup.directory",
                )
            ).scalars().first()
            if self.company_id
            else None
        )
        directory = Path(configured.value if configured is not None and configured.value else settings.backup_dir)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _database_url() -> str:
        return str(settings.database_url)

    def require_operator(self, permission: str = BACKUP_PERMISSION) -> None:
        """Restrict backup operations to users holding the backup permission."""
        if self.user_id is None:
            raise PermissionDeniedError("Backups must be triggered by an authenticated user")
        user = self.db.get(User, self.user_id)
        if user is None:
            raise PermissionDeniedError("Unknown user for backup operation")
        if user.is_superuser:
            return
        from app.services.auth_service import AuthService

        permissions = AuthService(self.db).resolve_permissions(user, self.company_id)
        if not permissions.has(permission):
            raise PermissionDeniedError("You are not allowed to perform backup operations", permission=permission)

    # -------------------------------------------------------------- operations
    def create_backup(
        self,
        *,
        backup_type: str = "manual",
        scope: str = "full",
        notes: str | None = None,
        require_permission: bool = True,
    ) -> BackupJob:
        if require_permission:
            self.require_operator(BACKUP_PERMISSION)
        if backup_type not in {"manual", "scheduled"}:
            raise ValidationFailure("backup_type must be 'manual' or 'scheduled'")
        if scope not in {"full", "company", "database"}:
            raise ValidationFailure("scope must be 'full', 'company' or 'database'")
        started = datetime.now(UTC)
        stamp = started.strftime("%Y%m%d_%H%M%S")
        directory = self.backup_directory()
        job = BackupJob(
            company_id=self.company_id if scope == "company" else None,
            file_name=f"kayan_backup_{stamp}.dump",
            backup_type=backup_type,
            scope=scope,
            status="running",
            started_at=started,
            requested_by_id=self.user_id,
            notes=notes,
        )
        self.db.add(job)
        self.db.flush()
        try:
            target = self._dump_to(directory, job.file_name)
            job.storage_path = str(target)
            job.size_bytes = target.stat().st_size
            job.checksum = self._checksum(target)
            job.status = "completed"
            if scope in {"full", "company"}:
                job.size_bytes += self._copy_attachments(target.parent, stamp)
        except Exception as exc:  # noqa: BLE001 - the failure is recorded, then re-raised
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now(UTC)
            job.duration_ms = int((job.finished_at - started).total_seconds() * 1000)
            self.db.flush()
            self.audit.log_action(
                AuditAction.BACKUP,
                job,
                entity_type="backup_job",
                label=job.file_name,
                remarks=f"failed: {exc}",
            )
            raise
        job.finished_at = datetime.now(UTC)
        job.duration_ms = int((job.finished_at - started).total_seconds() * 1000)
        self.db.flush()
        self.audit.log_action(
            AuditAction.BACKUP,
            job,
            entity_type="backup_job",
            label=job.file_name,
            new_values={"size_bytes": job.size_bytes, "scope": scope, "type": backup_type},
        )
        return job

    def _dump_to(self, directory: Path, file_name: str) -> Path:
        url = self._database_url()
        if url.startswith("sqlite"):
            return self._dump_sqlite(directory, file_name)
        return self._dump_postgres(directory, file_name)

    def _dump_sqlite(self, directory: Path, file_name: str) -> Path:
        raw = self._database_url().split("///", 1)[-1]
        source = Path(raw)
        if not source.exists():
            raise BusinessRuleError("The SQLite database file was not found", path=str(source))
        target = directory / file_name.replace(".dump", ".sqlite")
        shutil.copy2(source, target)
        return target

    def _dump_postgres(self, directory: Path, file_name: str) -> Path:
        pg_dump = shutil.which("pg_dump")
        if pg_dump is None:
            raise BusinessRuleError(
                "pg_dump is not available on this host. Install the PostgreSQL client tools "
                "or configure BACKUP_COMMAND."
            )
        target = directory / file_name
        command = [
            pg_dump,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(target),
            self._database_url(),
        ]
        result = subprocess.run(  # noqa: S603 - fixed executable, no shell
            command,
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        if result.returncode != 0:
            raise BusinessRuleError("pg_dump failed", stderr=(result.stderr or "").strip()[:2000])
        return target

    def _copy_attachments(self, directory: Path, stamp: str) -> int:
        """Attachments live outside the database; include them in the backup set."""
        source = Path(settings.storage_dir)
        if not source.exists():
            return 0
        target = directory / f"attachments_{stamp}"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(source, target)
        return sum(file.stat().st_size for file in target.rglob("*") if file.is_file())

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # --------------------------------------------------------------- reporting
    def list_backups(self, *, limit: int = 100) -> list[BackupJob]:
        # Full-server backups intentionally have no company, so the tenant filter
        # is escaped here and the scope is filtered explicitly instead.
        stmt = select(BackupJob).execution_options(skip_tenant=True)
        if self.company_id is not None:
            stmt = stmt.where(
                or_(BackupJob.company_id == self.company_id, BackupJob.company_id.is_(None))
            )
        stmt = stmt.order_by(BackupJob.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def get(self, backup_id: uuid.UUID | str) -> BackupJob:
        job = self.db.execute(
            select(BackupJob)
            .where(BackupJob.id == uuid.UUID(str(backup_id)))
            .execution_options(skip_tenant=True)
        ).scalars().first()
        if job is None:
            raise NotFoundError("Backup not found", id=str(backup_id))
        return job

    def verify(self, backup_id: uuid.UUID | str) -> dict[str, Any]:
        """Recompute the checksum so a corrupted backup is detected early."""
        job = self.get(backup_id)
        if not job.storage_path:
            return {"backup": job.file_name, "valid": False, "reason": "no file recorded"}
        path = Path(job.storage_path)
        if not path.exists():
            return {"backup": job.file_name, "valid": False, "reason": "file is missing"}
        checksum = self._checksum(path)
        return {
            "backup": job.file_name,
            "valid": checksum == job.checksum,
            "checksum": checksum,
            "recorded_checksum": job.checksum,
            "size_bytes": path.stat().st_size,
        }

    def prune(self, *, keep: int = 14, require_permission: bool = True) -> dict[str, Any]:
        """Keep the most recent successful backups and delete the rest."""
        if require_permission:
            self.require_operator(BACKUP_PERMISSION)
        successful = [
            job
            for job in self.list_backups(limit=1000)
            if job.status == "completed" and job.storage_path
        ]
        removed = 0
        for job in successful[keep:]:
            path = Path(job.storage_path)
            if path.exists():
                path.unlink()
            job.status = "pruned"
            removed += 1
        self.db.flush()
        return {"removed": removed, "kept": min(len(successful), keep)}

    # ------------------------------------------------------------------ restore
    def restore_instructions(self, backup_id: uuid.UUID | str) -> dict[str, Any]:
        """Documented, tested restore procedure for the operations team."""
        job = self.get(backup_id)
        if self.user_id is not None:
            self.require_operator(RESTORE_PERMISSION)
        is_sqlite = (job.storage_path or "").endswith(".sqlite")
        if is_sqlite:
            commands = [
                "docker compose stop backend",
                f"cp {job.storage_path} /var/lib/kayan/kayan.sqlite",
                "docker compose start backend",
                "curl -f http://localhost:8000/health",
            ]
        else:
            commands = [
                "docker compose stop backend",
                "docker compose exec -T postgres dropdb -U kayan kayan || true",
                "docker compose exec -T postgres createdb -U kayan kayan",
                f"docker compose exec -T postgres pg_restore -U kayan -d kayan --clean --if-exists < {job.storage_path}",
                "docker compose start backend",
                "curl -f http://localhost:8000/health",
            ]
        return {
            "backup": job.file_name,
            "scope": job.scope,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "checksum": job.checksum,
            "steps": [
                "1. Announce a maintenance window and stop write traffic (stop the backend service).",
                "2. Take a safety backup of the current database before restoring.",
                "3. Run the commands below from the infrastructure directory on the database host.",
                "4. Verify /health, then sign in and spot-check the latest documents and reports.",
                "5. Re-run alembic upgrade head if the restored dump is older than the current schema.",
            ],
            "commands": commands,
            "accounting_warning": (
                "Restoring an older dump rewinds financial postings. Reconcile the trial balance "
                "against the last signed-off period immediately after the restore."
            ),
        }

    # ---------------------------------------------------------------- scheduling
    def schedule_settings(self) -> dict[str, Any]:
        """Scheduled backup configuration stored per company (admin editable)."""
        keys = {"backup.enabled": "false", "backup.frequency": "daily", "backup.retention": "14", "backup.hour": "2"}
        if self.company_id is None:
            return keys
        rows = self.db.execute(
            select(SystemSetting).where(
                SystemSetting.company_id == self.company_id, SystemSetting.key.in_(list(keys))
            )
        ).scalars().all()
        for row in rows:
            keys[row.key] = row.value or keys[row.key]
        return keys

    def run_scheduled(self) -> dict[str, Any]:
        """Entry point for the scheduler: respects the configured frequency."""
        settings_payload = self.schedule_settings()
        enabled = str(settings_payload["backup.enabled"]).lower() in {"1", "true", "yes"}
        if not enabled:
            return {"ran": False, "reason": "scheduled backups are disabled"}
        frequency = str(settings_payload["backup.frequency"]).lower()
        last = next((job for job in self.list_backups(limit=1) if job.status == "completed"), None)
        now = datetime.now(UTC)
        if last is not None and last.finished_at is not None:
            finished = last.finished_at
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=UTC)
            intervals = {
                "hourly": timedelta(hours=1),
                "daily": timedelta(days=1),
                "weekly": timedelta(days=7),
                "monthly": timedelta(days=30),
            }
            interval = intervals.get(frequency, timedelta(days=1))
            if now - finished < interval:
                return {"ran": False, "reason": f"last backup is newer than the {frequency} interval"}
        job = self.create_backup(
            backup_type="scheduled",
            scope="full",
            notes=f"scheduled {frequency} backup",
            require_permission=self.user_id is not None,
        )
        retention = int(str(settings_payload["backup.retention"]) or 14)
        pruned = self.prune(keep=retention, require_permission=False)
        return {
            "ran": True,
            "backup": job.file_name,
            "size_bytes": job.size_bytes,
            "duration_ms": job.duration_ms,
            "pruned": pruned,
        }
