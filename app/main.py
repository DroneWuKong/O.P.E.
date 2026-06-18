from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path
import time

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models import (
    ApprovalPolicyResponse,
    AskRequest,
    AskResponse,
    MemoryItem,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryStatsResponse,
    MemoryWriteRequest,
    QueryEventsResponse,
    RoutePlan,
    RoutesResponse,
    ToolJob,
    ToolJobClaimRequest,
    ToolJobCreateRequest,
    ToolJobHeartbeatRequest,
    ToolJobsResponse,
    ToolQueueStatsResponse,
    ToolJobStatus,
    ToolJobUpdateRequest,
)
from app.approvals import list_approval_rules, tokens_approve_route
from app.auth import require_api_key
from app.planner import build_plan, list_routes
from app.memory import (
    close_memory_store,
    init_memory_store,
    maybe_write_memory,
    memory_stats,
    memory_store_status,
    recall_memory,
    search_memory,
    write_memory,
)
from app.events import list_model_stats, list_query_events, record_query_event, update_model_stats
from app.litellm_client import call_with_fallbacks
from app.provider_health import provider_health
from app.tools import (
    claim_next_tool_job,
    create_tool_job,
    heartbeat_tool_job,
    list_tool_jobs,
    tool_queue_stats,
    update_tool_job,
)


logger = logging.getLogger(__name__)


async def connect_external_services() -> None:
    settings = get_settings()
    deadline = time.monotonic() + settings.ope_startup_retry_seconds
    attempt = 0

    while True:
        attempt += 1
        try:
            await init_memory_store()
            await provider_health.connect()
            return
        except Exception as exc:
            await provider_health.close()
            await close_memory_store()
            if time.monotonic() >= deadline:
                logger.exception('external service startup failed after %s attempts', attempt)
                raise
            logger.warning(
                'external service startup attempt %s failed: %r',
                attempt,
                exc,
            )
            await asyncio.sleep(settings.ope_startup_retry_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.ope_skip_external_init:
        await connect_external_services()
    yield
    if not settings.ope_skip_external_init:
        await provider_health.close()
        await close_memory_store()


app = FastAPI(title='OPE Core', version='0.1.0', lifespan=lifespan)

STATIC_DIR = Path(__file__).resolve().parent / 'static'
if STATIC_DIR.exists():
    app.mount('/ui', StaticFiles(directory=STATIC_DIR, html=True), name='ui')


@app.get('/')
def root() -> dict:
    return {
        'ok': True,
        'service': 'ope-core',
        'cluster': 'Octoputer',
        'message': 'OPE Core is running. Use /health, /ready, /routes, /plan, or /ask.',
        'auth': 'Protected API routes require Authorization: Bearer <ope-api-key>.',
        'endpoints': {
            'ui': '/ui/',
            'health': '/health',
            'ready': '/ready',
            'routes': '/routes',
            'plan': '/plan',
            'ask': '/ask',
            'memory_search': '/memory/search',
            'tool_queue_stats': '/tools/queue/stats',
        },
    }


@app.get('/health')
def health() -> dict:
    return {'ok': True, 'service': 'ope-core', 'cluster': 'Octoputer'}


@app.get('/ready')
async def ready() -> dict:
    checks: dict[str, dict] = {}
    ok = True

    for name, check in {
        'postgres': memory_store_status,
        'redis': provider_health.health,
    }.items():
        try:
            checks[name] = await check()
        except Exception as exc:
            ok = False
            checks[name] = {'ok': False, 'error': str(exc)}

    body = {'ok': ok, 'service': 'ope-core', 'checks': checks}
    if not ok:
        raise HTTPException(status_code=503, detail=body)
    return body


@app.get('/models/status', dependencies=[Depends(require_api_key)])
async def models_status() -> dict:
    settings = get_settings()
    provider_status = await provider_health.status()
    model_stats = [] if settings.ope_disable_event_logging else await list_model_stats()
    return {
        'provider_health': provider_status,
        'model_stats': model_stats,
    }


@app.get('/routes', response_model=RoutesResponse, dependencies=[Depends(require_api_key)])
def routes() -> RoutesResponse:
    return RoutesResponse(routes=list_routes())


@app.post('/plan', response_model=RoutePlan, dependencies=[Depends(require_api_key)])
def plan(req: AskRequest) -> RoutePlan:
    return build_plan(req)


@app.get('/approvals', response_model=ApprovalPolicyResponse, dependencies=[Depends(require_api_key)])
def approvals() -> ApprovalPolicyResponse:
    return ApprovalPolicyResponse(rules=list_approval_rules())


@app.post('/ask', response_model=AskResponse, dependencies=[Depends(require_api_key)])
async def ask(req: AskRequest) -> AskResponse:
    settings = get_settings()
    started = time.perf_counter()
    plan = build_plan(req)
    if plan.approval_required and not plan.approval_granted:
        raise HTTPException(
            status_code=403,
            detail={
                'error': 'approval_required',
                'required_approval': plan.required_approval,
                'route_plan': plan.model_dump(),
            },
        )

    memories = await recall_memory(req, plan)
    memory_text = '\n'.join(f'- {m.summary}' for m in memories) or '- none'

    prompt = (
        'OPE Core route plan:\n'
        + str(plan.model_dump())
        + '\n\nMemory:\n'
        + memory_text
        + '\n\nQuestion:\n'
        + req.query
    )

    route_timeout_seconds = getattr(settings, 'request_timeout_seconds', 120)
    try:
        answer, model_used, fallbacks_attempted = await asyncio.wait_for(
            call_with_fallbacks(
                plan.primary_model,
                plan.fallback_models,
                [{'role': 'user', 'content': prompt}],
            ),
            timeout=route_timeout_seconds,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        failure_message = str(exc) or f'model route timed out after {route_timeout_seconds}s'
        if not settings.ope_disable_event_logging:
            await record_query_event(
                req,
                plan,
                selected_model=None,
                fallback_models=plan.fallback_models,
                sources_used=[m.id for m in memories if m.id],
                success=False,
                latency_ms=latency_ms,
                failure_reason=failure_message[:500],
            )
            await update_model_stats(
                model_alias=plan.primary_model,
                task_type=plan.query_type,
                success=False,
                latency_ms=latency_ms,
                failure_reason=failure_message[:500],
            )
        raise HTTPException(
            status_code=502,
            detail={
                'error': 'model_route_failed',
                'message': failure_message,
                'route_plan': plan.model_dump(),
            },
        ) from exc

    saved = await maybe_write_memory(req, plan, answer)
    latency_ms = int((time.perf_counter() - started) * 1000)
    query_event_id = None
    tool_job_id = None
    if not settings.ope_disable_event_logging:
        query_event_id = await record_query_event(
            req,
            plan,
            selected_model=model_used,
            fallback_models=fallbacks_attempted,
            sources_used=[m.id for m in memories if m.id],
            success=True,
            latency_ms=latency_ms,
        )
        if model_used:
            await update_model_stats(
                model_alias=model_used,
                task_type=plan.query_type,
                success=True,
                latency_ms=latency_ms,
            )

    if plan.route == 'tool_action' and plan.needs_tools:
        tool_job = await create_tool_job(
            ToolJobCreateRequest(
                project=plan.project,
                tool_name='manual_review',
                action='tool_action_plan',
                payload={
                    'query': req.query,
                    'route_plan': plan.model_dump(),
                    'model_used': model_used,
                    'fallbacks_attempted': fallbacks_attempted,
                    'answer_preview': answer[:2000],
                },
                requested_by='ask',
                approval_tokens=req.approval_tokens,
            ),
            query_event_id=query_event_id,
            route=plan.route,
        )
        tool_job_id = tool_job.id

    return AskResponse(
        answer=answer,
        route_plan=plan,
        model_used=model_used,
        fallbacks_attempted=fallbacks_attempted,
        memory_used=memories,
        metadata={
            'memory_saved': saved is not None,
            'query_event_id': query_event_id,
            'tool_job_id': tool_job_id,
            'latency_ms': latency_ms,
        },
    )


@app.post('/memory/write', response_model=MemoryItem, dependencies=[Depends(require_api_key)])
async def memory_write(req: MemoryWriteRequest) -> MemoryItem:
    return await write_memory(req)


@app.post('/memory/search', response_model=MemorySearchResponse, dependencies=[Depends(require_api_key)])
async def memory_search(req: MemorySearchRequest) -> MemorySearchResponse:
    return MemorySearchResponse(memories=await search_memory(req))


@app.get('/memory/stats', response_model=MemoryStatsResponse, dependencies=[Depends(require_api_key)])
async def memory_stats_endpoint() -> MemoryStatsResponse:
    return await memory_stats()


@app.get('/events/recent', response_model=QueryEventsResponse, dependencies=[Depends(require_api_key)])
async def recent_events(
    project: str | None = None,
    success: bool | None = None,
    limit: int = Query(25, ge=1, le=100),
) -> QueryEventsResponse:
    return QueryEventsResponse(
        events=await list_query_events(project=project, success=success, limit=limit)
    )


@app.post('/tools/jobs', response_model=ToolJob, dependencies=[Depends(require_api_key)])
async def create_tool_job_endpoint(req: ToolJobCreateRequest) -> ToolJob:
    if not tokens_approve_route(req.approval_tokens, 'tool_action'):
        raise HTTPException(
            status_code=403,
            detail={
                'error': 'approval_required',
                'required_approval': 'tool_action_approved',
            },
        )
    return await create_tool_job(req)


@app.get('/tools/jobs', response_model=ToolJobsResponse, dependencies=[Depends(require_api_key)])
async def tool_jobs(
    project: str | None = None,
    status: ToolJobStatus | None = None,
    limit: int = Query(25, ge=1, le=100),
) -> ToolJobsResponse:
    return ToolJobsResponse(
        jobs=await list_tool_jobs(project=project, status=status, limit=limit)
    )


@app.get('/tools/queue/stats', response_model=ToolQueueStatsResponse, dependencies=[Depends(require_api_key)])
async def tool_queue_stats_endpoint(project: str | None = None) -> ToolQueueStatsResponse:
    return await tool_queue_stats(project=project)


@app.patch('/tools/jobs/{job_id}', response_model=ToolJob, dependencies=[Depends(require_api_key)])
async def patch_tool_job(job_id: str, req: ToolJobUpdateRequest) -> ToolJob:
    job = await update_tool_job(job_id, req)
    if job is None:
        raise HTTPException(status_code=404, detail={'error': 'tool_job_not_found'})
    return job


@app.post('/tools/jobs/claim', response_model=ToolJob | None, dependencies=[Depends(require_api_key)])
async def claim_tool_job(req: ToolJobClaimRequest) -> ToolJob | None:
    return await claim_next_tool_job(req)


@app.post('/tools/jobs/{job_id}/heartbeat', response_model=ToolJob, dependencies=[Depends(require_api_key)])
async def heartbeat_tool_job_endpoint(job_id: str, req: ToolJobHeartbeatRequest) -> ToolJob:
    job = await heartbeat_tool_job(job_id, req)
    if job is None:
        raise HTTPException(status_code=409, detail={'error': 'tool_job_not_claimed_by_worker'})
    return job
