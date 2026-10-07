"""Pydantic schemas: the request/response contract of the REST API."""

from app.schemas.auth import *  # noqa: F403
from app.schemas.common import *  # noqa: F403
from app.schemas.masterdata import *  # noqa: F403

__all__ = []  # populated by the star imports above
