from __future__ import annotations

from decimal import Decimal

from app.memory import get_memory_pool
from app.models import AskRequest, QueryEvent, RoutePlan


async def record_query_event(
    req: AskRequest,
    plan: RoutePlan,
    *,
    selected_model: str | None,
    fallback_models: list[str],
    sources_used: list[str],
    success: bool,
    latency_ms: int,
    estimated_cost: Decimal | None = None,
    failure_reason: str | None = None,
) -> str:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO query_events (
              project_id, query, query_type, selected_route, selected_model,
              fallback_models, sources_used, success, latency_ms, estimated_cost,
              failure_reason
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id
            """,
            plan.project,
            req.query,
            plan.query_type,
            plan.route,
            selected_model,
            fallback_models,
            sources_used,
            success,
            latency_ms,
            estimated_cost,
            failure_reason,
        )
    return str(row['id'])


async def update_model_stats(
    *,
    model_alias: str,
    task_type: str,
    success: bool,
    latency_ms: int | None = None,
    estimated_cost: Decimal | None = None,
    failure_reason: str | None = None,
) -> None:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO model_stats (
              model_alias, task_type, success_count, failure_count, avg_latency_ms,
              avg_cost, last_failure_reason
            )
            VALUES (
              $1, $2,
              CASE WHEN $3 THEN 1 ELSE 0 END,
              CASE WHEN $3 THEN 0 ELSE 1 END,
              $4,
              $5,
              $6
            )
            ON CONFLICT (model_alias, task_type)
            DO UPDATE SET
              success_count = model_stats.success_count + CASE WHEN $3 THEN 1 ELSE 0 END,
              failure_count = model_stats.failure_count + CASE WHEN $3 THEN 0 ELSE 1 END,
              avg_latency_ms = CASE
                WHEN $4::integer IS NULL THEN model_stats.avg_latency_ms
                WHEN model_stats.avg_latency_ms IS NULL THEN $4
                ELSE (
                  (
                    model_stats.avg_latency_ms
                    * GREATEST(model_stats.success_count + model_stats.failure_count, 1)
                  ) + $4
                ) / GREATEST(model_stats.success_count + model_stats.failure_count + 1, 1)
              END,
              avg_cost = CASE
                WHEN $5::numeric IS NULL THEN model_stats.avg_cost
                WHEN model_stats.avg_cost IS NULL THEN $5
                ELSE (
                  (
                    model_stats.avg_cost
                    * GREATEST(model_stats.success_count + model_stats.failure_count, 1)
                  ) + $5
                ) / GREATEST(model_stats.success_count + model_stats.failure_count + 1, 1)
              END,
              last_failure_reason = CASE WHEN $3 THEN model_stats.last_failure_reason ELSE $6 END,
              updated_at = now()
            """,
            model_alias,
            task_type,
            success,
            latency_ms,
            estimated_cost,
            failure_reason,
        )


async def list_model_stats(limit: int = 50) -> list[dict]:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT model_alias, task_type, success_count, failure_count,
              avg_latency_ms, avg_cost, quality_score, last_failure_reason,
              updated_at
            FROM model_stats
            ORDER BY updated_at DESC
            LIMIT $1
            """,
            limit,
        )

    stats: list[dict] = []
    for row in rows:
        avg_cost = row['avg_cost']
        stats.append(
            {
                'model_alias': row['model_alias'],
                'task_type': row['task_type'],
                'success_count': row['success_count'],
                'failure_count': row['failure_count'],
                'avg_latency_ms': row['avg_latency_ms'],
                'avg_cost': float(avg_cost) if avg_cost is not None else None,
                'quality_score': float(row['quality_score'] or 0.0),
                'last_failure_reason': row['last_failure_reason'],
                'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
            }
        )
    return stats


async def list_query_events(
    *,
    project: str | None = None,
    success: bool | None = None,
    limit: int = 25,
) -> list[QueryEvent]:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, project_id, query, query_type, selected_route, selected_model,
              fallback_models, sources_used, success, latency_ms, estimated_cost,
              failure_reason, created_at
            FROM query_events
            WHERE ($1::text IS NULL OR project_id = $1)
              AND ($2::boolean IS NULL OR success = $2)
            ORDER BY created_at DESC
            LIMIT $3
            """,
            project,
            success,
            limit,
        )

    events: list[QueryEvent] = []
    for row in rows:
        estimated_cost = row['estimated_cost']
        events.append(
            QueryEvent(
                id=str(row['id']),
                project=row['project_id'],
                query=row['query'],
                query_type=row['query_type'],
                selected_route=row['selected_route'],
                selected_model=row['selected_model'],
                fallback_models=list(row['fallback_models'] or []),
                sources_used=list(row['sources_used'] or []),
                success=row['success'],
                latency_ms=row['latency_ms'],
                estimated_cost=float(estimated_cost) if estimated_cost is not None else None,
                failure_reason=row['failure_reason'],
                created_at=row['created_at'].isoformat() if row['created_at'] else None,
            )
        )
    return events
