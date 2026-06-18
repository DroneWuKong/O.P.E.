import asyncio
import os
from types import SimpleNamespace

os.environ['OPE_SKIP_EXTERNAL_INIT'] = 'true'
os.environ['OPE_DISABLE_EVENT_LOGGING'] = 'true'

from fastapi.testclient import TestClient

from app import main
from app.models import MemoryItem, MemoryStatsResponse, QueryEvent, ToolJob, ToolQueueStatsResponse


client = TestClient(main.app)


def test_root_index() -> None:
    response = client.get('/')

    assert response.status_code == 200
    body = response.json()
    assert body['service'] == 'ope-core'
    assert body['endpoints']['ui'] == '/ui/'
    assert body['endpoints']['ask'] == '/ask'


def test_ui_index() -> None:
    response = client.get('/ui/')

    assert response.status_code == 200
    assert 'O.P.E. Chat' in response.text


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
    assert 'gemini-fast' in response.json()['models']
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
    assert routes['quick_lookup']['primary_model'] == 'openai-mini'
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


def test_plan_respects_manual_route_mode() -> None:
    response = client.post(
        '/plan',
        json={'query': 'ordinary message', 'mode': 'technical_search', 'allow_search': True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body['route'] == 'technical_search'
    assert body['needs_search'] is True


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
                selected_model='openai-mini',
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
    assert body['events'][0]['selected_model'] == 'openai-mini'


def test_create_tool_job_requires_approval() -> None:
    response = client.post(
        '/tools/jobs',
        json={'tool_name': 'shell', 'action': 'run', 'payload': {'command': 'date'}},
    )

    assert response.status_code == 403
    assert response.json()['detail']['required_approval'] == 'tool_action_approved'


def test_create_list_and_update_tool_jobs(monkeypatch) -> None:
    job = ToolJob(
        id='job-1',
        project='ope-core',
        tool_name='shell',
        action='run',
        payload={'command': 'date'},
        status='pending_review',
    )

    async def fake_create(req, query_event_id=None, route='tool_action'):
        assert req.approval_tokens == ['tool_action_approved']
        return job

    async def fake_list(project=None, status=None, limit=25):
        assert project == 'ope-core'
        assert status == 'pending_review'
        assert limit == 5
        return [job]

    async def fake_update(job_id, req):
        assert job_id == 'job-1'
        return job.model_copy(update={'status': req.status, 'approved_by': req.approved_by})

    monkeypatch.setattr(main, 'create_tool_job', fake_create)
    monkeypatch.setattr(main, 'list_tool_jobs', fake_list)
    monkeypatch.setattr(main, 'update_tool_job', fake_update)

    create_response = client.post(
        '/tools/jobs',
        json={
            'project': 'ope-core',
            'tool_name': 'shell',
            'action': 'run',
            'payload': {'command': 'date'},
            'approval_tokens': ['tool_action_approved'],
        },
    )
    list_response = client.get('/tools/jobs?project=ope-core&status=pending_review&limit=5')
    update_response = client.patch('/tools/jobs/job-1', json={'status': 'approved', 'approved_by': 'operator'})

    assert create_response.status_code == 200
    assert create_response.json()['id'] == 'job-1'
    assert list_response.status_code == 200
    assert list_response.json()['jobs'][0]['id'] == 'job-1'
    assert update_response.status_code == 200
    assert update_response.json()['status'] == 'approved'


def test_tool_queue_stats(monkeypatch) -> None:
    async def fake_stats(project=None):
        assert project == 'ope-core'
        return ToolQueueStatsResponse(
            project=project,
            total=4,
            by_status={'approved': 2, 'running': 1, 'failed': 1},
            running=1,
            expired_leases=1,
            oldest_approved_at='2026-06-18T04:30:00+00:00',
            newest_updated_at='2026-06-18T04:40:00+00:00',
        )

    monkeypatch.setattr(main, 'tool_queue_stats', fake_stats)

    response = client.get('/tools/queue/stats?project=ope-core')

    assert response.status_code == 200
    assert response.json()['total'] == 4
    assert response.json()['by_status']['approved'] == 2
    assert response.json()['expired_leases'] == 1


def test_claim_and_heartbeat_tool_job(monkeypatch) -> None:
    running_job = ToolJob(
        id='job-1',
        project='ope-core',
        tool_name='shell',
        action='run',
        payload={'command': 'date'},
        status='running',
        worker_id='worker-a',
        lease_expires_at='2026-06-18T04:30:00+00:00',
    )

    async def fake_claim(req):
        assert req.worker_id == 'worker-a'
        assert req.project == 'ope-core'
        assert req.lease_seconds == 60
        return running_job

    async def fake_heartbeat(job_id, req):
        assert job_id == 'job-1'
        assert req.worker_id == 'worker-a'
        return running_job

    monkeypatch.setattr(main, 'claim_next_tool_job', fake_claim)
    monkeypatch.setattr(main, 'heartbeat_tool_job', fake_heartbeat)

    claim_response = client.post(
        '/tools/jobs/claim',
        json={'worker_id': 'worker-a', 'project': 'ope-core', 'lease_seconds': 60},
    )
    heartbeat_response = client.post(
        '/tools/jobs/job-1/heartbeat',
        json={'worker_id': 'worker-a', 'lease_seconds': 60},
    )

    assert claim_response.status_code == 200
    assert claim_response.json()['worker_id'] == 'worker-a'
    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()['status'] == 'running'


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


def test_ask_model_failure_returns_gateway_error(monkeypatch) -> None:
    async def fake_recall(req, plan):
        return []

    async def fake_record(*args, **kwargs):
        assert kwargs['success'] is False
        return 'event-failed'

    async def fake_update(**kwargs):
        assert kwargs['success'] is False
        return None

    async def fake_call(primary, fallbacks, messages):
        raise RuntimeError('All configured model routes failed')

    monkeypatch.setattr(
        main,
        'get_settings',
        lambda: SimpleNamespace(ope_disable_event_logging=False, request_timeout_seconds=120),
    )
    monkeypatch.setattr(main, 'recall_memory', fake_recall)
    monkeypatch.setattr(main, 'record_query_event', fake_record)
    monkeypatch.setattr(main, 'update_model_stats', fake_update)
    monkeypatch.setattr(main, 'call_with_fallbacks', fake_call)

    response = client.post('/ask', json={'query': 'quick lookup please'})

    assert response.status_code == 502
    assert response.json()['detail']['error'] == 'model_route_failed'


def test_ask_model_timeout_returns_gateway_error(monkeypatch) -> None:
    async def fake_recall(req, plan):
        return []

    async def fake_call(primary, fallbacks, messages):
        await asyncio.sleep(1)
        return 'late answer', primary, []

    monkeypatch.setattr(
        main,
        'get_settings',
        lambda: SimpleNamespace(ope_disable_event_logging=True, request_timeout_seconds=0.01),
    )
    monkeypatch.setattr(main, 'recall_memory', fake_recall)
    monkeypatch.setattr(main, 'call_with_fallbacks', fake_call)

    response = client.post('/ask', json={'query': 'quick lookup please'})

    assert response.status_code == 502
    assert response.json()['detail']['message'] == 'model route timed out after 0.01s'


def test_ask_records_query_event_when_enabled(monkeypatch) -> None:
    async def fake_recall(req, plan):
        return [MemoryItem(id='memory-1', summary='Stored OPE memory.')]

    async def fake_write(req, plan, answer):
        return None

    async def fake_call(primary, fallbacks, messages):
        return 'evented answer', primary, ['gemini-fast']

    async def fake_record(*args, **kwargs):
        assert kwargs['selected_model'] == 'openai-mini'
        assert kwargs['fallback_models'] == ['gemini-fast']
        assert kwargs['sources_used'] == ['memory-1']
        assert kwargs['success'] is True
        return 'event-1'

    async def fake_update(**kwargs):
        assert kwargs['model_alias'] == 'openai-mini'
        assert kwargs['success'] is True

    monkeypatch.setattr(
        main,
        'get_settings',
        lambda: SimpleNamespace(ope_disable_event_logging=False, request_timeout_seconds=120),
    )
    monkeypatch.setattr(main, 'recall_memory', fake_recall)
    monkeypatch.setattr(main, 'maybe_write_memory', fake_write)
    monkeypatch.setattr(main, 'call_with_fallbacks', fake_call)
    monkeypatch.setattr(main, 'record_query_event', fake_record)
    monkeypatch.setattr(main, 'update_model_stats', fake_update)

    response = client.post('/ask', json={'query': 'quick lookup please'})

    assert response.status_code == 200
    assert response.json()['metadata']['query_event_id'] == 'event-1'


def test_approved_tool_action_ask_creates_tool_job(monkeypatch) -> None:
    async def fake_recall(req, plan):
        return []

    async def fake_write(req, plan, answer):
        return None

    async def fake_call(primary, fallbacks, messages):
        return 'Run a reviewed tool action.', primary, []

    async def fake_record(*args, **kwargs):
        return 'event-2'

    async def fake_update(**kwargs):
        return None

    async def fake_create(req, query_event_id=None, route='tool_action'):
        assert query_event_id == 'event-2'
        assert route == 'tool_action'
        assert req.tool_name == 'manual_review'
        assert req.payload['query'] == 'please deploy this'
        return ToolJob(id='job-2', project=req.project, tool_name=req.tool_name, action=req.action)

    monkeypatch.setattr(
        main,
        'get_settings',
        lambda: SimpleNamespace(ope_disable_event_logging=False, request_timeout_seconds=120),
    )
    monkeypatch.setattr(main, 'recall_memory', fake_recall)
    monkeypatch.setattr(main, 'maybe_write_memory', fake_write)
    monkeypatch.setattr(main, 'call_with_fallbacks', fake_call)
    monkeypatch.setattr(main, 'record_query_event', fake_record)
    monkeypatch.setattr(main, 'update_model_stats', fake_update)
    monkeypatch.setattr(main, 'create_tool_job', fake_create)

    response = client.post(
        '/ask',
        json={
            'query': 'please deploy this',
            'allow_tools': True,
            'approval_tokens': ['tool_action_approved'],
        },
    )

    assert response.status_code == 200
    assert response.json()['metadata']['tool_job_id'] == 'job-2'
