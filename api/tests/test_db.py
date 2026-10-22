from app.core.db import init_db


async def test_init_db() -> None:
    await init_db()
