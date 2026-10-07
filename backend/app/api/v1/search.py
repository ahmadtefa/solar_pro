"""Global search across every module, filtered by the caller's permissions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUserDep
from app.services.search_service import SearchService

router = APIRouter()


@router.get("", summary="Global search")
def search(
    db: DB,
    current: CurrentUserDep,
    q: str = Query(..., min_length=1, max_length=120),
    entities: str | None = Query(None, description="Comma-separated entity keys"),
    limit_per_entity: int = Query(5, ge=1, le=50),
) -> dict[str, Any]:
    current.require("core.search.view")
    selected = [part.strip() for part in (entities or "").split(",") if part.strip()] or None
    service = SearchService(db, current.company_id, user_id=current.id, permissions=current.permissions)
    return service.search(q, limit_per_entity=limit_per_entity, entities=selected)


@router.get("/entities", summary="Searchable entity catalogue")
def entities(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.search.view")
    service = SearchService(db, current.company_id, user_id=current.id, permissions=current.permissions)
    items = list(service.available_entities())
    return {"items": items, "total": len(items)}


@router.get("/quick/{entity}", summary="Search inside a single entity")
def quick(
    entity: str,
    db: DB,
    current: CurrentUserDep,
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    current.require("core.search.view")
    service = SearchService(db, current.company_id, user_id=current.id, permissions=current.permissions)
    rows = service.quick_search(entity, q, limit=limit)
    return {"items": rows, "total": len(rows), "entity": entity}


@router.get("/recent/{entity}", summary="Recently created records of an entity")
def recent(
    entity: str, db: DB, current: CurrentUserDep, limit: int = Query(10, ge=1, le=50)
) -> dict[str, Any]:
    current.require("core.search.view")
    service = SearchService(db, current.company_id, user_id=current.id, permissions=current.permissions)
    rows = service.recent(entity=entity, limit=limit)
    return {"items": rows, "total": len(rows), "entity": entity}


@router.get("/targets", summary="Search targets with their required permissions")
def targets(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.search.view")
    service = SearchService(db, current.company_id, user_id=current.id, permissions=current.permissions)
    rows = [
        {
            "key": target.key,
            "label": target.label,
            "module": target.module,
            "entity": target.entity,
            "number_field": target.number_field,
            "title_field": target.title_field,
        }
        for target in service.searchable_targets()
    ]
    return {"items": rows, "total": len(rows)}


__all__ = ["router"]
