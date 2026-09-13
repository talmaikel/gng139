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

    **The session is joined to an outer transaction as a SAVEPOINT.** Without
    that, any `commit()` under test escapes the rollback and writes to the real
    database: the dossier endpoint commits (correctly -- it is production code),
    and every run of the API tests was leaving a tenant, a user and a task row
    behind while reporting green. `create_savepoint` turns those commits into
    savepoint releases, and the outer rollback still discards everything.
    """
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM field_evidence LIMIT 0"))
    except Exception as exc:  # no server, no database, or not migrated
        await engine.dispose()
        pytest.skip(f"no migrated database reachable: {type(exc).__name__}")

    conn = await engine.connect()
    outer = await conn.begin()
    factory = async_sessionmaker(bind=conn, expire_on_commit=False,
                                 join_transaction_mode="create_savepoint")
    async with factory() as s:
        yield s
    await outer.rollback()
    await conn.close()
    await engine.dispose()
