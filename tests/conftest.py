"""Shared fixtures: an in-memory database and session per test."""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import app.database.models  # noqa: F401 - register models on Base.metadata
from app.database.base import Database


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_all()
    async with database.session() as s:
        yield s
    await database.dispose()
