from app.models import AskRequest, MemoryItem, RoutePlan

# MVP in-process memory shim.
# Replace with Postgres + pgvector once migrations and deployment are wired.
_MEMORY: list[MemoryItem] = [
    MemoryItem(
        scope='project',
        project='ope-core',
        memory_type='project_fact',
        summary='O.P.E. Core runs on the Octoputer k3s cluster as a model router, persistent memory layer, intelligent search planner, and tool/action control plane.',
        value={'stack': ['k3s', 'LiteLLM', 'FastAPI', 'Postgres', 'pgvector', 'Redis']},
        tags=['ope', 'octoputer', 'k3s', 'litellm'],
        importance=0.95,
        confidence=0.95,
    )
]


def recall_memory(req: AskRequest, plan: RoutePlan) -> list[MemoryItem]:
    query = req.query.lower()
    project = plan.project
    matches: list[MemoryItem] = []
    for item in _MEMORY:
        if item.project and item.project != project:
            continue
        haystack = ' '.join([item.summary, ' '.join(item.tags)]).lower()
        if any(token in haystack for token in query.split()[:12]):
            matches.append(item)
    return matches[:5]


def maybe_write_memory(req: AskRequest, plan: RoutePlan, answer: str) -> MemoryItem | None:
    if not plan.write_memory:
        return None
    if len(req.query) < 40:
        return None

    item = MemoryItem(
        scope='project',
        project=plan.project,
        memory_type='episode',
        summary=f'User asked about {plan.query_type}: {req.query[:180]}',
        value={'route': plan.route, 'answer_preview': answer[:500]},
        tags=[plan.query_type, plan.route],
        importance=0.55,
        confidence=0.7,
    )
    _MEMORY.append(item)
    return item
