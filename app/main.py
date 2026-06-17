from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, HTTPException, Query

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
)
from app.approvals import list_approval_rules
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.ope_skip_external_init:
        await init_memory_store()
        await provider_health.connect()
    yield
    if not settings.ope_skip_external_init:
        await provider_health.close()
        await close_memory_store()


app = FastAPI(title='OPE Core', version='0.1.0', lifespan=lifespan)


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


@app.get('/models/status')
async def models_status() -> dict:
    settings = get_settings()
    provider_status = await provider_health.status()
    model_stats = [] if settings.ope_disable_event_logging else await list_model_stats()
    return {
        'provider_health': provider_status,
        'model_stats': model_stats,
    }


@app.get('/routes', response_model=RoutesResponse)
def routes() -> RoutesResponse:
    return RoutesResponse(routes=list_routes())


@app.post('/plan', response_model=RoutePlan)
def plan(req: AskRequest) -> RoutePlan:
    return build_plan(req)


@app.get('/approvals', response_model=ApprovalPolicyResponse)
def approvals() -> ApprovalPolicyResponse:
    return ApprovalPolicyResponse(rules=list_approval_rules())


@app.post('/ask', response_model=AskResponse)
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

    try:
        answer, model_used, fallbacks_attempted = await call_with_fallbacks(
            plan.primary_model,
            plan.fallback_models,
            [{'role': 'user', 'content': prompt}],
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        if not settings.ope_disable_event_logging:
            await record_query_event(
                req,
                plan,
                selected_model=None,
                fallback_models=plan.fallback_models,
                sources_used=[m.id for m in memories if m.id],
                success=False,
                latency_ms=latency_ms,
                failure_reason=str(exc)[:500],
            )
            await update_model_stats(
                model_alias=plan.primary_model,
                task_type=plan.query_type,
                success=False,
                latency_ms=latency_ms,
                failure_reason=str(exc)[:500],
            )
        raise

    saved = await maybe_write_memory(req, plan, answer)
    latency_ms = int((time.perf_counter() - started) * 1000)
    query_event_id = None
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

    return AskResponse(
        answer=answer,
        route_plan=plan,
        model_used=model_used,
        fallbacks_attempted=fallbacks_attempted,
        memory_used=memories,
        metadata={
            'memory_saved': saved is not None,
            'query_event_id': query_event_id,
            'latency_ms': latency_ms,
        },
    )


@app.post('/memory/write', response_model=MemoryItem)
async def memory_write(req: MemoryWriteRequest) -> MemoryItem:
    return await write_memory(req)


@app.post('/memory/search', response_model=MemorySearchResponse)
async def memory_search(req: MemorySearchRequest) -> MemorySearchResponse:
    return MemorySearchResponse(memories=await search_memory(req))


@app.get('/memory/stats', response_model=MemoryStatsResponse)
async def memory_stats_endpoint() -> MemoryStatsResponse:
    return await memory_stats()


@app.get('/events/recent', response_model=QueryEventsResponse)
async def recent_events(
    project: str | None = None,
    success: bool | None = None,
    limit: int = Query(25, ge=1, le=100),
) -> QueryEventsResponse:
    return QueryEventsResponse(
        events=await list_query_events(project=project, success=success, limit=limit)
    )
