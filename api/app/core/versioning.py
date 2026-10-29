from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError


def raise_revision_conflict(current: BaseModel) -> None:
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        detail={"code": "revision_conflict", "current": current.model_dump(mode="json")},
    )


async def run_versioned_write[Versioned](
    db: AsyncSession,
    entity: Versioned,
    expected_revision: int,
    schema: type[BaseModel],
    operation: Callable[[], Awaitable[Versioned]],
    reload: Callable[[], Awaitable[Versioned | None]],
) -> Versioned:
    if entity.revision != expected_revision:
        raise_revision_conflict(schema.model_validate(entity))
    try:
        return await operation()
    except StaleDataError:
        await db.rollback()
        current = await reload()
        if current is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found") from None
        raise_revision_conflict(schema.model_validate(current))


async def run_versioned_delete[Versioned](
    db: AsyncSession,
    entity: Versioned,
    expected_revision: int,
    schema: type[BaseModel],
    operation: Callable[[], Awaitable[None]],
    reload: Callable[[], Awaitable[Versioned | None]],
) -> None:
    async def delete() -> Versioned:
        await operation()
        return entity

    await run_versioned_write(db, entity, expected_revision, schema, delete, reload)
