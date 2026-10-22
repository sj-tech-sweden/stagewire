import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_stagewire.db")
os.environ.setdefault("APP_ENV", "test")

import pytest  # noqa: E402
from sqlalchemy import delete  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from app.core import db as db_mod  # noqa: E402
from app.domains.auth.models import APIKey, User, UserRole, UserSession  # noqa: E402
from app.domains.auth.security import (  # noqa: E402
    create_access_token,
    hash_password,
)


@pytest.fixture(scope="session", autouse=True)
async def _setup_db():
    db_mod.engine = create_async_engine(db_mod.settings.database_url, future=True)
    db_mod.SessionLocal = async_sessionmaker(db_mod.engine, expire_on_commit=False)
    async with db_mod.engine.begin() as conn:
        await conn.run_sync(db_mod.Base.metadata.create_all)
    yield
    async with db_mod.engine.begin() as conn:
        await conn.run_sync(db_mod.Base.metadata.drop_all)
    await db_mod.engine.dispose()
    try:
        os.remove("./test_stagewire.db")
    except OSError:
        pass


@pytest.fixture
async def auth_headers():
    async with db_mod.SessionLocal() as db:
        await db.execute(delete(UserSession))
        await db.execute(delete(UserRole))
        await db.execute(delete(APIKey))
        await db.execute(delete(User))
        user = User(
            email="admin@test.local",
            password_hash=hash_password("adminpass"),
            first_name="Admin",
            last_name="User",
            full_name="Admin User",
            role="admin",
            is_active=True,
            is_admin=True,
            auth_source="local",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    token = create_access_token(user.id, user.email, user.role)
    return {"Authorization": f"Bearer {token}"}
