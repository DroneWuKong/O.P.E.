from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.memory import close_memory_store, init_memory_store
from app.models import ToolJob, ToolJobClaimRequest, ToolJobHeartbeatRequest
from app.tools import claim_next_tool_job, finish_claimed_tool_job, heartbeat_tool_job


logger = logging.getLogger('ope.tool_runner')


def execute_allowlisted_tool(job: ToolJob) -> dict:
    if job.tool_name != 'noop':
        raise ValueError(f'tool is not allowlisted: {job.tool_name}')
    return {
        'ok': True,
        'tool_name': job.tool_name,
        'action': job.action,
        'payload': job.payload,
    }


async def run_once() -> bool:
    settings = get_settings()
    job = await claim_next_tool_job(
        ToolJobClaimRequest(
            worker_id=settings.tool_runner_worker_id,
            project=settings.tool_runner_project,
            lease_seconds=settings.tool_runner_lease_seconds,
        )
    )
    if job is None:
        return False

    await heartbeat_tool_job(
        job.id,
        ToolJobHeartbeatRequest(
            worker_id=settings.tool_runner_worker_id,
            lease_seconds=settings.tool_runner_lease_seconds,
        ),
    )

    try:
        result = execute_allowlisted_tool(job)
        finished = await finish_claimed_tool_job(
            job.id,
            worker_id=settings.tool_runner_worker_id,
            status='succeeded',
            result=result,
        )
    except Exception as exc:
        finished = await finish_claimed_tool_job(
            job.id,
            worker_id=settings.tool_runner_worker_id,
            status='failed',
            error=str(exc),
        )

    if finished is None:
        raise RuntimeError(f'claimed tool job disappeared or lease ownership changed: {job.id}')
    return True


async def run_forever() -> None:
    settings = get_settings()
    await init_memory_store()
    try:
        while True:
            handled = await run_once()
            if settings.tool_runner_once:
                return
            if not handled:
                await asyncio.sleep(settings.tool_runner_poll_seconds)
    finally:
        await close_memory_store()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())


if __name__ == '__main__':
    main()
