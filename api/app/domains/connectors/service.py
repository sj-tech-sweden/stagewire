from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.connectors.models import ConnectorKind
from app.domains.rigging import connectors


async def refresh_power_connectors(db: AsyncSession = Depends(get_db)) -> None:
    """Load the user-added power connectors into the power connector catalog.

    Used as a router dependency on everything that validates or evaluates power, so a connector
    added from any connector field is known to the power tree from the next request on. It is one
    small query; the registry is replaced as a whole, so deleted kinds are forgotten too.
    """
    rows = await db.scalars(select(ConnectorKind).where(ConnectorKind.power.is_(True)))
    connectors.register_custom(
        [
            connectors.Connector(
                key=row.key,
                label=row.label,
                phases=row.phases or 1,
                amps=row.amps if row.amps is not None else 16,
                circuits=row.circuits or 1,
            )
            for row in rows
        ]
    )
