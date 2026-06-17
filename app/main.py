from fastapi import FastAPI

from app.models import AskRequest, AskResponse
from app.planner import build_plan
from app.memory import recall_memory, maybe_write_memory
from app.litellm_client import call_with_fallbacks
from app.provider_health import provider_health

app = FastAPI(title='OPE Core', version='0.1.0')


@app.get('/health')
def health() -> dict:
    return {'ok': True, 'service': 'ope-core', 'cluster': 'Octoputer'}


@app.get('/models/status')
def models_status() -> dict:
    return provider_health.status()


@app.post('/ask', response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    plan = build_plan(req)
    memories = recall_memory(req, plan)
    memory_text = '\n'.join(f'- {m.summary}' for m in memories) or '- none'

    prompt = (
        'OPE Core route plan:\n'
        + str(plan.model_dump())
        + '\n\nMemory:\n'
        + memory_text
        + '\n\nQuestion:\n'
        + req.query
    )

    answer, model_used, fallbacks_attempted = await call_with_fallbacks(
        plan.primary_model,
        plan.fallback_models,
        [{'role': 'user', 'content': prompt}],
    )

    saved = maybe_write_memory(req, plan, answer)

    return AskResponse(
        answer=answer,
        route_plan=plan,
        model_used=model_used,
        fallbacks_attempted=fallbacks_attempted,
        memory_used=memories,
        metadata={'memory_saved': saved is not None},
    )
