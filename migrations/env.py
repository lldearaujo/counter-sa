"""Alembic environment configuration."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Carrega .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Read DATABASE_URL from environment (overrides alembic.ini placeholder)
_raw_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://easycount:easycount@localhost:5432/easycount",
)

# Remove sslmode=disable — asyncpg não aceita esse parâmetro na URL
if "sslmode=disable" in _raw_url or "ssl=false" in _raw_url.lower():
    _raw_url = _raw_url.split("?")[0]
    _CONNECT_ARGS = {"ssl": False}
else:
    _CONNECT_ARGS = {}

DATABASE_URL = _raw_url


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(DATABASE_URL, connect_args=_CONNECT_ARGS)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_async_migrations() -> None:
    asyncio.run(run_migrations_online())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_async_migrations()
