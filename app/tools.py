from __future__ import annotations

import json

from app.memory import get_memory_pool
from app.models import (
    ToolJob,
    ToolJobClaimRequest,
    ToolJobCreateRequest,
    ToolJobHeartbeatRequest,
    ToolJobUpdateRequest,
    ToolQueueStatsResponse,
)


def _iso_or_none(value) -> str | None:
    return value.isoformat() if value else None


def _row_to_tool_job(row) -> ToolJob:
    payload = row['payload']
    result = row['result']
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(result, str):
        result = json.loads(result)

    return ToolJob(
        id=str(row['id']),
        project=row['project_id'],
        query_event_id=str(row['query_event_id']) if row['query_event_id'] else None,
        route=row['route'],
        tool_name=row['tool_name'],
        action=row['action'],
        payload=payload or {},
        status=row['status'],
        requested_by=row['requested_by'],
        approved_by=row['approved_by'],
        worker_id=row['worker_id'],
        lease_expires_at=row['lease_expires_at'].isoformat() if row['lease_expires_at'] else None,
        result=result,
        error=row['error'],
        created_at=row['created_at'].isoformat() if row['created_at'] else None,
        updated_at=row['updated_at'].isoformat() if row['updated_at'] else None,
    )


async def create_tool_job(
    req: ToolJobCreateRequest,
    *,
    query_event_id: str | None = None,
    route: str = 'tool_action',
) -> ToolJob:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO tool_jobs (
              project_id, query_event_id, route, tool_name, action, payload,
              status, requested_by
            )
            VALUES ($1, $2::uuid, $3, $4, $5, $6::jsonb, 'pending_review', $7)
            RETURNING id, project_id, query_event_id, route, tool_name, action,
              payload, status, requested_by, approved_by, worker_id, lease_expires_at, result, error,
              created_at, updated_at
            """,
            req.project,
            query_event_id,
            route,
            req.tool_name,
            req.action,
            json.dumps(req.payload),
            req.requested_by,
        )
    return _row_to_tool_job(row)


async def list_tool_jobs(
    *,
    project: str | None = None,
    status: str | None = None,
    limit: int = 25,
) -> list[ToolJob]:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, project_id, query_event_id, route, tool_name, action,
              payload, status, requested_by, approved_by, worker_id, lease_expires_at, result, error,
              created_at, updated_at
            FROM tool_jobs
            WHERE ($1::text IS NULL OR project_id = $1)
              AND ($2::text IS NULL OR status = $2)
            ORDER BY created_at DESC
            LIMIT $3
            """,
            project,
            status,
            limit,
        )
    return [_row_to_tool_job(row) for row in rows]


async def tool_queue_stats(*, project: str | None = None) -> ToolQueueStatsResponse:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        by_status_rows = await conn.fetch(
            """
            SELECT status, count(*) AS count
            FROM tool_jobs
            WHERE ($1::text IS NULL OR project_id = $1)
            GROUP BY status
            ORDER BY status ASC
            """,
            project,
        )
        summary = await conn.fetchrow(
            """
            SELECT
              count(*) FILTER (WHERE status = 'running') AS running,
              count(*) FILTER (
                WHERE status = 'running' AND lease_expires_at < now()
              ) AS expired_leases,
              min(created_at) FILTER (WHERE status = 'pending_review') AS oldest_pending_review_at,
              min(created_at) FILTER (WHERE status = 'approved') AS oldest_approved_at,
              max(created_at) AS newest_created_at,
              max(updated_at) AS newest_updated_at
            FROM tool_jobs
            WHERE ($1::text IS NULL OR project_id = $1)
            """,
            project,
        )

    by_status = {row['status']: row['count'] for row in by_status_rows}
    return ToolQueueStatsResponse(
        project=project,
        total=sum(by_status.values()),
        by_status=by_status,
        running=summary['running'] or 0,
        expired_leases=summary['expired_leases'] or 0,
        oldest_pending_review_at=_iso_or_none(summary['oldest_pending_review_at']),
        oldest_approved_at=_iso_or_none(summary['oldest_approved_at']),
        newest_created_at=_iso_or_none(summary['newest_created_at']),
        newest_updated_at=_iso_or_none(summary['newest_updated_at']),
    )


async def update_tool_job(job_id: str, req: ToolJobUpdateRequest) -> ToolJob | None:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE tool_jobs
            SET
              status = coalesce($2, status),
              approved_by = coalesce($3, approved_by),
              result = CASE
                WHEN $6 THEN NULL
                ELSE coalesce($4::jsonb, result)
              END,
              error = CASE
                WHEN $7 THEN NULL
                ELSE coalesce($5, error)
              END,
              worker_id = CASE
                WHEN $2 IN ('succeeded', 'failed', 'cancelled') THEN NULL
                ELSE worker_id
              END,
              lease_expires_at = CASE
                WHEN $2 IN ('succeeded', 'failed', 'cancelled') THEN NULL
                ELSE lease_expires_at
              END,
              updated_at = now()
            WHERE id = $1::uuid
            RETURNING id, project_id, query_event_id, route, tool_name, action,
              payload, status, requested_by, approved_by, worker_id, lease_expires_at, result, error,
              created_at, updated_at
            """,
            job_id,
            req.status,
            req.approved_by,
            json.dumps(req.result) if req.result is not None else None,
            req.error,
            req.clear_result,
            req.clear_error,
        )

    return _row_to_tool_job(row) if row else None


async def claim_next_tool_job(req: ToolJobClaimRequest) -> ToolJob | None:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH candidate AS (
              SELECT id
              FROM tool_jobs
              WHERE status = 'approved'
                AND ($1::text IS NULL OR project_id = $1)
                AND (lease_expires_at IS NULL OR lease_expires_at < now())
              ORDER BY created_at ASC
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE tool_jobs
            SET
              status = 'running',
              worker_id = $2,
              lease_expires_at = now() + make_interval(secs => $3),
              updated_at = now()
            WHERE id = (SELECT id FROM candidate)
            RETURNING id, project_id, query_event_id, route, tool_name, action,
              payload, status, requested_by, approved_by, worker_id, lease_expires_at, result, error,
              created_at, updated_at
            """,
            req.project,
            req.worker_id,
            req.lease_seconds,
        )
    return _row_to_tool_job(row) if row else None


async def heartbeat_tool_job(job_id: str, req: ToolJobHeartbeatRequest) -> ToolJob | None:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE tool_jobs
            SET
              lease_expires_at = now() + make_interval(secs => $3),
              updated_at = now()
            WHERE id = $1::uuid
              AND status = 'running'
              AND worker_id = $2
            RETURNING id, project_id, query_event_id, route, tool_name, action,
              payload, status, requested_by, approved_by, worker_id, lease_expires_at, result, error,
              created_at, updated_at
            """,
            job_id,
            req.worker_id,
            req.lease_seconds,
        )
    return _row_to_tool_job(row) if row else None


async def finish_claimed_tool_job(
    job_id: str,
    *,
    worker_id: str,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> ToolJob | None:
    pool = get_memory_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE tool_jobs
            SET
              status = $3,
              result = $4::jsonb,
              error = $5,
              worker_id = NULL,
              lease_expires_at = NULL,
              updated_at = now()
            WHERE id = $1::uuid
              AND status = 'running'
              AND worker_id = $2
            RETURNING id, project_id, query_event_id, route, tool_name, action,
              payload, status, requested_by, approved_by, worker_id, lease_expires_at, result, error,
              created_at, updated_at
            """,
            job_id,
            worker_id,
            status,
            json.dumps(result) if result is not None else None,
            error,
        )
    return _row_to_tool_job(row) if row else None
