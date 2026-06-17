import os
from types import SimpleNamespace

os.environ['OPE_SKIP_EXTERNAL_INIT'] = 'true'
os.environ['OPE_DISABLE_EVENT_LOGGING'] = 'true'

from fastapi.testclient import TestClient

from app import main
from app.models import MemoryItem, MemoryStatsResponse, QueryEvent


client = TestClient(main.app)


def test_health() -> None:
    response = client.get('/health')

    assert response.status_code == 200
    assert response.json()['service'] == 'ope-core'
    assert response.json()['cluster'] == 'Octoputer'


def test_models_status(monkeypatch) -> None:
    async def fake_status() -> dict:
        return {'openai-main': {'available': True, 'cooldown_remaining_seconds': 0, 'last_failure': None}}

    monkeypatch.setattr(main.provider_health, 'status', fake_status)

    response = client.get('/models/status')

    assert response.status_code == 200
    assert response.json()['provider_health']['openai-main']['available'] is True
    assert response.json()['model_stats'] == []


def test_ready(monkeypatch) -> None:
    async def fake_postgres_status() -> dict:
        return {'ok': True, 'latency_ms': 1}

    async def fake_redis_status() -> dict:
        return {'ok': True, 'latency_ms': 2}

    monkeypatch.setattr(main, 'memory_store_status', fake_postgres_status)
    monkeypatch.setattr(main.provider_health, 'health', fake_redis_status)

    response = client.get('/ready')

    assert response.status_code == 200
    assert response.json()['checks']['postgres']['ok'] is True
    assert response.json()['checks']['redis']['ok'] is True


def test_routes_catalog() -> None:
    response = client.get('/routes')

    assert response.status_code == 200
    routes = {route['route']: route for route in response.json()['routes']}
    assert 'quick_lookup' in routes
    assert routes['quick_lookup']['primary_model'] == 'mistral-fast'
    assert routes['tool_action']['tools_enabled'] is True


def test_approval_policy_catalog() -> None:
    response = client.get('/approvals')

    assert response.status_code == 200
    rules = response.json()['rules']
    assert rules[0]['token'] == 'tool_action_approved'
    assert rules[0]['applies_to_routes'] == ['tool_action']


def test_plan_preview() -> None:
    response = client.post('/plan', json={'query': 'please deploy this', 'allow_tools': False})

    assert response.status_code == 200
    body = response.json()
    assert body['route'] != 'tool_action'
    assert body['needs_tools'] is False

    tool_response = client.post('/plan', json={'query': 'please deploy this', 'allow_tools': True})
    assert tool_response.status_code == 200
    tool_body = tool_response.json()
    assert tool_body['route'] == 'tool_action'
    assert tool_body['approval_required'] is True
    assert tool_body['approval_granted'] is False
    assert tool_body['needs_tools'] is False

    approved_response = client.post(
        '/plan',
        json={
            'query': 'please deploy this',
            'allow_tools': True,
            'approval_tokens': ['tool_action_approved'],
        },
    )
    approved_body = approved_response.json()
    assert approved_body['approval_granted'] is True
    assert approved_body['needs_tools'] is True


def test_ask_blocks_unapproved_tool_action(monkeypatch) -> None:
    async def fail_if_called(*args, **kwargs):
        raise AssertionError('model call should not happen before tool approval')

    monkeypatch.setattr(main, 'call_with_fallbacks', fail_if_called)

    response = client.post('/ask', json={'query': 'please deploy this', 'allow_tools': True})

    assert response.status_code == 403
    assert response.json()['detail']['required_approval'] == 'tool_action_approved'


def test_memory_write_and_search(monkeypatch) -> None:
    item = MemoryItem(
        id='memory-1',
        project='ope-core',
        memory_type='project_fact',
        summary='OPE runs on Octoputer.',
        tags=['ope', 'octoputer'],
        importance=0.9,
        confidence=0.9,
    )

    async def fake_write(req):
        return item.model_copy(update=req.model_dump(exclude_unset=True))

    async def fake_search(req):
        return [item]

    monkeypatch.setattr(main, 'write_memory', fake_write)
    monkeypatch.setattr(main, 'search_memory', fake_search)

    write_response = client.post('/memory/write', json={'summary': item.summary, 'project': 'ope-core'})
    search_response = client.post('/memory/search', json={'query': 'Octoputer', 'project': 'ope-core'})

    assert write_response.status_code == 200
    assert write_response.json()['summary'] == item.summary
    assert search_response.status_code == 200
    assert search_response.json()['memories'][0]['id'] == 'memory-1'


def test_memory_stats(monkeypatch) -> None:
    async def fake_stats():
        return MemoryStatsResponse(
            total=3,
            by_project={'ope-core': 2, 'global': 1},
            by_type={'episode': 2, 'fact': 1},
            by_scope={'project': 3},
        )

    monkeypatch.setattr(main, 'memory_stats', fake_stats)

    response = client.get('/memory/stats')

    assert response.status_code == 200
    assert response.json()['total'] == 3
    assert response.json()['by_project']['ope-core'] == 2


def test_recent_events(monkeypatch) -> None:
    async def fake_events(project=None, success=None, limit=25):
        assert project == 'ope-core'
        assert success is True
        assert limit == 5
        return [
            QueryEvent(
                id='event-1',
                project='ope-core',
                query='What should OPE do?',
                query_type='quick_lookup',
                selected_route='quick_lookup',
                selected_model='mistral-fast',
                success=True,
                latency_ms=42,
                created_at='2026-06-17T12:00:00+00:00',
            )
        ]

    monkeypatch.setattr(main, 'list_query_events', fake_events)

    response = client.get('/events/recent?project=ope-core&success=true&limit=5')

    assert response.status_code == 200
    body = response.json()
    assert body['events'][0]['id'] == 'event-1'
    assert body['events'][0]['selected_model'] == 'mistral-fast'


def test_ask_route(monkeypatch) -> None:
    async def fake_recall(req, plan):
        return [
            MemoryItem(
                project='ope-core',
                memory_type='project_fact',
                summary='OPE routes model requests through LiteLLM.',
            )
        ]

    async def fake_write(req, plan, answer):
        return None

    async def fake_call(primary, fallbacks, messages):
        return 'planned answer', primary, []

    monkeypatch.setattr(main, 'recall_memory', fake_recall)
    monkeypatch.setattr(main, 'maybe_write_memory', fake_write)
    monkeypatch.setattr(main, 'call_with_fallbacks', fake_call)

    response = client.post('/ask', json={'query': 'Explain the OPE FastAPI route plan'})

    assert response.status_code == 200
    body = response.json()
    assert body['answer'] == 'planned answer'
    assert body['route_plan']['project'] == 'ope-core'
    assert body['memory_used'][0]['summary'].startswith('OPE routes')


def test_ask_records_query_event_when_enabled(monkeypatch) -> None:
    async def fake_recall(req, plan):
        return [MemoryItem(id='memory-1', summary='Stored OPE memory.')]

    async def fake_write(req, plan, answer):
        return None

    async def fake_call(primary, fallbacks, messages):
        return 'evented answer', primary, ['gemini-fast']

    async def fake_record(*args, **kwargs):
        assert kwargs['selected_model'] == 'mistral-fast'
        assert kwargs['fallback_models'] == ['gemini-fast']
        assert kwargs['sources_used'] == ['memory-1']
        assert kwargs['success'] is True
        return 'event-1'

    async def fake_update(**kwargs):
        assert kwargs['model_alias'] == 'mistral-fast'
        assert kwargs['success'] is True

    monkeypatch.setattr(main, 'get_settings', lambda: SimpleNamespace(ope_disable_event_logging=False))
    monkeypatch.setattr(main, 'recall_memory', fake_recall)
    monkeypatch.setattr(main, 'maybe_write_memory', fake_write)
    monkeypatch.setattr(main, 'call_with_fallbacks', fake_call)
    monkeypatch.setattr(main, 'record_query_event', fake_record)
    monkeypatch.setattr(main, 'update_model_stats', fake_update)

    response = client.post('/ask', json={'query': 'quick lookup please'})

    assert response.status_code == 200
    assert response.json()['metadata']['query_event_id'] == 'event-1'
