from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    future=True,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    import app.domains.audio.models  # noqa: F401  (register models on metadata)
    import app.domains.auth.models  # noqa: F401
    import app.domains.reports.models  # noqa: F401
    import app.domains.venues.models  # noqa: F401

    # Only create tables directly for the sqlite test suite. In every other
    # (containerised) environment the schema is owned by Alembic and applied
    # by the API container's entrypoint via `alembic upgrade head`.
    if settings.database_url.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    from app.domains.reports.registry import ensure_default_templates

    async with SessionLocal() as session:
        await ensure_default_templates(session)
