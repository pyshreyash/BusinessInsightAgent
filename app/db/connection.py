from __future__ import annotations

import asyncpg
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from app.db.schema import TABLE_SCHEMAS


logger = logging.getLogger("biz-insights-copilot.db")


class PostgresConnectionManager:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
        self._pool = None

    @asynccontextmanager
    async def _acquire(self) -> Any:
        if self._pool is None:
            raise RuntimeError("PostgresConnectionManager.connect() must be called first.")
        async with self._pool.acquire() as conn:
            yield conn

    async def init_schema(self) -> None:
        create_statements: List[str] = [
            """
            CREATE TABLE IF NOT EXISTS fact_sales (
              date date NOT NULL,
              product_id integer NOT NULL,
              quantity numeric NOT NULL,
              price numeric NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS dim_product (
              product_id integer PRIMARY KEY,
              category text NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS dim_time (
              date date PRIMARY KEY,
              week integer NOT NULL,
              month integer NOT NULL
            )
            """,
        ]
        async with self._acquire() as conn:
            for stmt in create_statements:
                await conn.execute(stmt)

    async def seed_if_empty(self, seed_rows: Dict[str, List[Dict[str, Any]]]) -> None:
        async with self._acquire() as conn:
            # Seed dim_product first.
            existing = await conn.fetchval("SELECT COUNT(*) FROM dim_product")
            if existing and int(existing) > 0:
                return

            await conn.executemany(
                "INSERT INTO dim_product (product_id, category) VALUES ($1, $2) ON CONFLICT (product_id) DO UPDATE SET category = EXCLUDED.category",
                [(r["product_id"], r["category"]) for r in seed_rows["dim_product"]],
            )
            await conn.executemany(
                "INSERT INTO dim_time (date, week, month) VALUES ($1, $2, $3) ON CONFLICT (date) DO UPDATE SET week = EXCLUDED.week, month = EXCLUDED.month",
                [(r["date"], r["week"], r["month"]) for r in seed_rows["dim_time"]],
            )
            await conn.executemany(
                "INSERT INTO fact_sales (date, product_id, quantity, price) VALUES ($1, $2, $3, $4)",
                [(r["date"], r["product_id"], r["quantity"], r["price"]) for r in seed_rows["fact_sales"]],
            )

    async def execute_select(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute only SELECT queries.
        """
        async with self._acquire() as conn:
            try:
                records = await conn.fetch(sql)
            except Exception as e:
                logger.exception("Query execution failed.")
                raise e
        # asyncpg Record -> dict
        return [dict(r) for r in records]

