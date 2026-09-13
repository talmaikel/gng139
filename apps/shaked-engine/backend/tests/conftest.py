import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings


async def no_wait(_seconds: float) -> None:
    """Stand-in for asyncio.sleep, so tests assert on pacing without waiting for it."""


@pytest.fixture
async def session():
    """
    A session on a real, migrated Postgres, inside a transaction that is rolled
    back, so nothing is left behind. Skips, rather than fails, when no migrated
    database is reachable, so the unit suite still runs without Postgres.
    """
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM field_evidence LIMIT 0"))
    except Exception as exc:  # no server, no database, or not migrated
        await engine.dispose()
        pytest.skip(f"no migrated database reachable: {type(exc).__name__}")
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
        await s.rollback()
    await engine.dispose()
