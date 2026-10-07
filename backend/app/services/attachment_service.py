"""Secure document management (attachments).

Files are stored outside the web root with a random name, validated by
extension and size, checksummed and access controlled through the owning
company.  Downloads stream through the API (never a public URL), so tenant
isolation also applies to binary content.
"""

from __future__ import annotations

import hashlib
import mimetypes
import shutil
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import BusinessRuleError, NotFoundError, ValidationFailure
from app.models.identity import Attachment

DANGEROUS_EXTENSIONS = {"exe", "bat", "cmd", "sh", "js", "php", "py", "rb", "dll", "so", "msi", "com", "scr"}


class AttachmentService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id

    # ------------------------------------------------------------------ upload
    def upload(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        file_name: str,
        stream: BinaryIO,
        content_type: str | None = None,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
    ) -> Attachment:
        safe_name = Path(file_name or "file").name
        extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
        if not extension or extension in DANGEROUS_EXTENSIONS or extension not in settings.allowed_extensions:
            raise ValidationFailure(
                f"File type '{extension or 'unknown'}' is not allowed",
                allowed=sorted(settings.allowed_extensions),
            )

        target_dir = settings.upload_path / str(self.company_id) / entity_type
        target_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex}.{extension}"
        target_path = target_dir / unique_name

        size = 0
        digest = hashlib.sha256()
        with target_path.open("wb") as destination:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_size_bytes:
                    destination.close()
                    target_path.unlink(missing_ok=True)
                    raise BusinessRuleError(
                        f"File exceeds the maximum upload size of {settings.max_upload_size_mb} MB"
                    )
                digest.update(chunk)
                destination.write(chunk)

        if size == 0:
            target_path.unlink(missing_ok=True)
            raise ValidationFailure("Uploaded file is empty")

        attachment = Attachment(
            company_id=self.company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            file_name=unique_name,
            original_file_name=safe_name,
            content_type=content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
            file_size=size,
            storage_path=str(target_path),
            checksum=digest.hexdigest(),
            title=title or safe_name,
            description=description,
            category=category,
            uploaded_by_id=self.user_id,
        )
        self.db.add(attachment)
        self.db.flush()
        return attachment

    # ------------------------------------------------------------------- reads
    def get(self, attachment_id: uuid.UUID) -> Attachment:
        attachment = self.db.execute(
            select(Attachment).where(
                Attachment.company_id == self.company_id, Attachment.id == attachment_id
            )
        ).scalars().first()
        if attachment is None:
            raise NotFoundError("Attachment not found")
        return attachment

    def list_for_entity(self, entity_type: str, entity_id: uuid.UUID) -> list[Attachment]:
        return list(
            self.db.execute(
                select(Attachment)
                .where(
                    Attachment.company_id == self.company_id,
                    Attachment.entity_type == entity_type,
                    Attachment.entity_id == entity_id,
                )
                .order_by(Attachment.created_at.desc())
            ).scalars().all()
        )

    def file_path(self, attachment: Attachment) -> Path:
        path = Path(attachment.storage_path)
        if not path.exists():
            raise NotFoundError("The attachment file is missing from storage")
        return path

    def register_download(self, attachment: Attachment) -> None:
        attachment.download_count = int(attachment.download_count or 0) + 1
        self.db.flush()

    # ------------------------------------------------------------------ delete
    def delete(self, attachment_id: uuid.UUID, *, hard: bool = True) -> None:
        attachment = self.get(attachment_id)
        path = Path(attachment.storage_path)
        self.db.delete(attachment)
        self.db.flush()
        if hard and path.exists():
            path.unlink(missing_ok=True)

    def entity_counts(self, entity_type: str, entity_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not entity_ids:
            return {}
        rows = self.db.execute(
            select(Attachment.entity_id, func.count())
            .where(
                Attachment.company_id == self.company_id,
                Attachment.entity_type == entity_type,
                Attachment.entity_id.in_(entity_ids),
            )
            .group_by(Attachment.entity_id)
        ).all()
        return {row[0]: int(row[1]) for row in rows}

    def counters_for(self, entity_type: str, entity_id: uuid.UUID) -> dict[str, Any]:
        files = self.list_for_entity(entity_type, entity_id)
        return {"count": len(files), "total_size": sum(int(file.file_size or 0) for file in files)}

    # ---------------------------------------------------------------- helpers
    def copy_to_backup(self, destination: Path) -> int:
        """Copy every stored file for a company (used by the backup service)."""
        source_root = settings.upload_path / str(self.company_id)
        if not source_root.exists():
            return 0
        destination.mkdir(parents=True, exist_ok=True)
        copied = 0
        for path in source_root.rglob("*"):
            if path.is_file():
                relative = path.relative_to(source_root)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                copied += 1
        return copied
