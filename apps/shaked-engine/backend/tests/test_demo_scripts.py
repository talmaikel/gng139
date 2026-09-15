"""‏E8 · סקריפטי ההדגמה עובדים גם אצל מי שאינו בועז.

טל (#41): במסד נקי אין חברת הדגמה ואין סקריפט שיוצר אותה, ו-`demo_preflight`
נותן ב-Windows שלושה ✗ שגויים. הבדיקות כאן על שני אלה.
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import select

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import demo_preflight  # noqa: E402
import demo_setup  # noqa: E402

from app.models.package import Balance  # noqa: E402
from app.models.tenant import Company, User  # noqa: E402


@pytest.mark.asyncio
async def test_demo_setup_creates_the_company_once_and_never_prints_the_password(session, monkeypatch, capsys):
    @asynccontextmanager
    async def same_session():
        yield session

    monkeypatch.setattr(demo_setup, "AsyncSessionLocal", same_session)
    monkeypatch.setattr(demo_setup, "DEMO_EMAIL", "demo-setup-test@shakdan.test")
    monkeypatch.setattr(demo_setup.demo, "COMPANY_SLUG_PREFIX", "demotest-")
    monkeypatch.setenv("DEMO_PASSWORD", "a-long-demo-password")

    assert await demo_setup.main(apply=False) == 1                     # בלי --apply לא נוצר דבר
    assert (await session.execute(select(User).where(
        User.email == "demo-setup-test@shakdan.test"))).scalars().first() is None

    assert await demo_setup.main(apply=True) == 0
    company = (await session.execute(select(Company).where(
        Company.slug.like("demotest-%")))).scalars().one()
    user = (await session.execute(select(User).where(
        User.email == "demo-setup-test@shakdan.test"))).scalars().one()
    balance = (await session.execute(select(Balance).where(Balance.company_id == company.id))).scalars().one()
    assert user.company_id == company.id and user.role == "owner" and not user.is_superuser
    assert balance.credits_remaining == demo_setup.demo.STARTING_CREDITS
    assert "a-long-demo-password" not in capsys.readouterr().out

    assert await demo_setup.main(apply=True) == 0                      # פעם שנייה: קיים, לא נוגע
    assert len((await session.execute(select(Company).where(
        Company.slug.like("demotest-%")))).scalars().all()) == 1


def test_preflight_without_posix_tools_warns_instead_of_blocking(monkeypatch):
    monkeypatch.setattr(demo_preflight, "POSIX_TOOLS", False)
    demo_preflight.results.clear()
    demo_preflight.check_processes()
    assert [level for level, _, _ in demo_preflight.results] == [demo_preflight.WARN]
