from __future__ import annotations

import json
from pathlib import Path
import time

import asyncpg

from app.config import get_settings
from app.models import AskRequest, MemoryItem, MemorySearchRequest, MemoryStatsResponse, MemoryWriteRequest, RoutePlan


_pool: asyncpg.Pool | None = None


async def init_memory_store() -> None:
    global _pool
    if _pool is not None:
        return

    settings = get_settings()
    _pool = await asyncpg.create_pool(settings.postgres_dsn, min_size=1, max_size=5)
    if settings.ope_run_migrations_on_startup:
        migration = Path(__file__).resolve().parent.parent / 'migrations' / '001_initial_schema.sql'
        async with _pool.acquire() as conn:
            await conn.execute(migration.read_text(encoding='utf-8'))


async def close_memory_store() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _require_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError('Postgres memory store is not initialized')
    return _pool


def get_memory_pool() -> asyncpg.Pool:
    return _require_pool()


async def memory_store_status() -> dict:
    started = time.perf_counter()
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.fetchval('SELECT 1')
    return {
        'ok': True,
        'latency_ms': int((time.perf_counter() - started) * 1000),
    }


def _row_to_memory(row: asyncpg.Record) -> MemoryItem:
    value = row['value']
    if isinstance(value, str):
        value = json.loads(value)

    return MemoryItem(
        id=str(row['id']),
        scope=row['scope'],
        project=row['project_id'],
        memory_type=row['memory_type'],
        memory_key=row['memory_key'],
        summary=row['summary'],
        value=value or {},
        tags=list(row['tags'] or []),
        importance=float(row['importance'] or 0.5),
        confidence=float(row['confidence'] or 0.5),
        source=row['source'],
    )


async def write_memory(req: MemoryWriteRequest) -> MemoryItem:
    pool = _require_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO memory_items (
              scope, project_id, memory_type, memory_key, value, summary, tags,
              importance, confidence, source
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10)
            ON CONFLICT (project_id, memory_key)
              WHERE memory_key IS NOT NULL
              DO UPDATE SET
                scope = EXCLUDED.scope,
                memory_type = EXCLUDED.memory_type,
                value = EXCLUDED.value,
                summary = EXCLUDED.summary,
                tags = EXCLUDED.tags,
                importance = EXCLUDED.importance,
                confidence = EXCLUDED.confidence,
                source = EXCLUDED.source,
                updated_at = now()
            RETURNING id, scope, project_id, memory_type, memory_key, value, summary,
              tags, importance, confidence, source
            """,
            req.scope,
            req.project,
            req.memory_type,
            req.memory_key,
            json.dumps(req.value),
            req.summary,
            req.tags,
            req.importance,
            req.confidence,
            req.source,
        )
    return _row_to_memory(row)


async def search_memory(req: MemorySearchRequest) -> list[MemoryItem]:
    pool = _require_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH query AS (
              SELECT websearch_to_tsquery('english', $1) AS tsq
            )
            SELECT id, scope, project_id, memory_type, memory_key, value, summary,
              tags, importance, confidence, source
            FROM memory_items, query
            WHERE ($2::text IS NULL OR project_id = $2)
              AND ($3::text IS NULL OR memory_type = $3)
              AND (cardinality($4::text[]) = 0 OR tags && $4)
              AND (
                to_tsvector('english', summary || ' ' || array_to_string(tags, ' ')) @@ query.tsq
                OR summary ILIKE '%' || $1 || '%'
              )
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY
              ts_rank_cd(
                to_tsvector('english', summary || ' ' || array_to_string(tags, ' ')),
                query.tsq
              ) DESC,
              importance DESC,
              confidence DESC,
              updated_at DESC
            LIMIT $5
            """,
            req.query,
            req.project,
            req.memory_type,
            req.tags,
            req.limit,
        )
    return [_row_to_memory(row) for row in rows]


async def memory_stats() -> MemoryStatsResponse:
    pool = _require_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            """
            SELECT count(*)
            FROM memory_items
            WHERE expires_at IS NULL OR expires_at > now()
            """
        )
        by_project_rows = await conn.fetch(
            """
            SELECT coalesce(project_id, 'global') AS key, count(*) AS count
            FROM memory_items
            WHERE expires_at IS NULL OR expires_at > now()
            GROUP BY coalesce(project_id, 'global')
            ORDER BY count DESC, key ASC
            """
        )
        by_type_rows = await conn.fetch(
            """
            SELECT memory_type AS key, count(*) AS count
            FROM memory_items
            WHERE expires_at IS NULL OR expires_at > now()
            GROUP BY memory_type
            ORDER BY count DESC, key ASC
            """
        )
        by_scope_rows = await conn.fetch(
            """
            SELECT scope AS key, count(*) AS count
            FROM memory_items
            WHERE expires_at IS NULL OR expires_at > now()
            GROUP BY scope
            ORDER BY count DESC, key ASC
            """
        )

    return MemoryStatsResponse(
        total=total or 0,
        by_project={row['key']: row['count'] for row in by_project_rows},
        by_type={row['key']: row['count'] for row in by_type_rows},
        by_scope={row['key']: row['count'] for row in by_scope_rows},
    )


async def recall_memory(req: AskRequest, plan: RoutePlan) -> list[MemoryItem]:
    return await search_memory(
        MemorySearchRequest(
            query=req.query,
            project=plan.project,
            limit=5,
        )
    )


async def maybe_write_memory(req: AskRequest, plan: RoutePlan, answer: str) -> MemoryItem | None:
    if not plan.write_memory or len(req.query) < 40:
        return None

    return await write_memory(
        MemoryWriteRequest(
            scope='project',
            project=plan.project,
            memory_type='episode',
            summary=f'User asked about {plan.query_type}: {req.query[:180]}',
            value={'route': plan.route, 'answer_preview': answer[:500]},
            tags=[plan.query_type, plan.route],
            importance=0.55,
            confidence=0.7,
            source='ask',
        )
    )
