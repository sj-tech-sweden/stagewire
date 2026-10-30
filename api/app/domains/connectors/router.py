import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.auth.deps import get_current_user
from app.domains.connectors.models import ConnectorKind

router = APIRouter(
    prefix="/connector-kinds", tags=["connectors"], dependencies=[Depends(get_current_user)]
)


class ConnectorKindCreate(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    power: bool = False
    amps: int | None = Field(None, ge=0, le=1000)
    phases: int | None = Field(None, ge=1, le=3)
    circuits: int | None = Field(None, ge=1, le=24)


class ConnectorKindRead(BaseModel):
    id: UUID
    key: str
    label: str
    power: bool = False
    amps: int | None = None
    phases: int | None = None
    circuits: int | None = None

    model_config = {"from_attributes": True}


def key_for(label: str) -> str:
    """The stored value for a label: lowercase letters and digits, other runs become one dash."""
    return re.sub(r"[^a-z0-9]+", "-", label.strip().lower()).strip("-")[:64]


@router.get("", response_model=list[ConnectorKindRead])
async def list_kinds(db: AsyncSession = Depends(get_db)) -> list[ConnectorKind]:
    rows = await db.scalars(select(ConnectorKind).order_by(ConnectorKind.label))
    return list(rows)


@router.post("", response_model=ConnectorKindRead, status_code=status.HTTP_201_CREATED)
async def create_kind(
    payload: ConnectorKindCreate, db: AsyncSession = Depends(get_db)
) -> ConnectorKind:
    """Add a kind. Adding one that exists (same key) returns the existing row, so a field that
    saves what the user typed can call this without checking first."""
    key = key_for(payload.label)
    if not key:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the connector a name")
    existing = await db.scalar(select(ConnectorKind).where(ConnectorKind.key == key))
    if existing is not None:
        return existing
    if payload.power and (payload.amps is None or payload.phases not in (1, 3)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A power connector needs its amps (0 for fixed installation) and 1 or 3 phases",
        )
    from app.domains.rigging import connectors as power_connectors

    if (
        payload.power
        and power_connectors.known(key)
        and not power_connectors.catalog_is_custom(key)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "That is already a built-in power connector")
    row = ConnectorKind(
        key=key,
        label=payload.label.strip(),
        power=payload.power,
        amps=payload.amps if payload.power else None,
        phases=payload.phases if payload.power else None,
        circuits=(payload.circuits or 1) if payload.power else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{kind_id}", status_code=204)
async def delete_kind(kind_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    row = await db.get(ConnectorKind, kind_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector kind not found")
    await db.delete(row)
    await db.commit()
