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


class ConnectorKindRead(BaseModel):
    id: UUID
    key: str
    label: str

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
    row = ConnectorKind(key=key, label=payload.label.strip())
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
