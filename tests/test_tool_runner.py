from types import SimpleNamespace

import pytest

from app.models import ToolJob
from app import tool_runner


def test_execute_allowlisted_noop() -> None:
    job = ToolJob(
        id='job-1',
        tool_name='noop',
        action='echo',
        payload={'message': 'ok'},
        status='running',
    )

    result = tool_runner.execute_allowlisted_tool(job)

    assert result['ok'] is True
    assert result['payload']['message'] == 'ok'


def test_execute_rejects_non_allowlisted_tool() -> None:
    job = ToolJob(id='job-1', tool_name='shell', action='run', payload={}, status='running')

    with pytest.raises(ValueError):
        tool_runner.execute_allowlisted_tool(job)


def test_execute_connector_tool(monkeypatch) -> None:
    job = ToolJob(
        id='job-1',
        tool_name='connector:github',
        action='search_repos',
        payload={'query': 'OPE'},
        status='running',
    )

    def fake_execute(connector_job):
        assert connector_job is job
        return {'ok': True, 'connector': 'github', 'action': 'search_repos', 'result': {'items': []}}

    monkeypatch.setattr(tool_runner, 'execute_connector_tool', fake_execute)

    result = tool_runner.execute_allowlisted_tool(job)

    assert result['connector'] == 'github'
    assert result['action'] == 'search_repos'


def test_execute_rejects_unknown_connector_action() -> None:
    job = ToolJob(id='job-1', tool_name='connector:github', action='delete_repo', payload={}, status='running')

    with pytest.raises(ValueError):
        tool_runner.execute_allowlisted_tool(job)


@pytest.mark.asyncio
async def test_run_once_finishes_claimed_job(monkeypatch) -> None:
    job = ToolJob(id='job-1', tool_name='noop', action='echo', payload={}, status='running')

    async def fake_claim(req):
        assert req.worker_id == 'worker-a'
        return job

    async def fake_heartbeat(job_id, req):
        assert job_id == 'job-1'
        return job

    async def fake_finish(job_id, *, worker_id, status, result=None, error=None):
        assert job_id == 'job-1'
        assert worker_id == 'worker-a'
        assert status == 'succeeded'
        assert result['ok'] is True
        assert error is None
        return job

    monkeypatch.setattr(tool_runner, 'get_settings', lambda: SimpleNamespace(
        tool_runner_worker_id='worker-a',
        tool_runner_project=None,
        tool_runner_lease_seconds=300,
    ))
    monkeypatch.setattr(tool_runner, 'claim_next_tool_job', fake_claim)
    monkeypatch.setattr(tool_runner, 'heartbeat_tool_job', fake_heartbeat)
    monkeypatch.setattr(tool_runner, 'finish_claimed_tool_job', fake_finish)

    assert await tool_runner.run_once() is True


@pytest.mark.asyncio
async def test_run_once_finishes_connector_job(monkeypatch) -> None:
    job = ToolJob(
        id='job-connector-1',
        tool_name='connector:github',
        action='search_repos',
        payload={'query': 'OPE'},
        status='running',
    )

    async def fake_claim(req):
        return job

    async def fake_heartbeat(job_id, req):
        return job

    async def fake_finish(job_id, *, worker_id, status, result=None, error=None):
        assert status == 'succeeded'
        assert result['connector'] == 'github'
        assert result['result']['items'] == []
        assert error is None
        return job

    monkeypatch.setattr(tool_runner, 'get_settings', lambda: SimpleNamespace(
        tool_runner_worker_id='worker-a',
        tool_runner_project=None,
        tool_runner_lease_seconds=300,
    ))
    monkeypatch.setattr(tool_runner, 'claim_next_tool_job', fake_claim)
    monkeypatch.setattr(tool_runner, 'heartbeat_tool_job', fake_heartbeat)
    monkeypatch.setattr(tool_runner, 'finish_claimed_tool_job', fake_finish)
    monkeypatch.setattr(tool_runner, 'execute_connector_tool', lambda job: {
        'ok': True,
        'connector': 'github',
        'action': job.action,
        'result': {'items': []},
    })

    assert await tool_runner.run_once() is True


@pytest.mark.asyncio
async def test_run_once_fails_non_allowlisted_job(monkeypatch) -> None:
    job = ToolJob(id='job-1', tool_name='shell', action='run', payload={}, status='running')

    async def fake_claim(req):
        return job

    async def fake_heartbeat(job_id, req):
        return job

    async def fake_finish(job_id, *, worker_id, status, result=None, error=None):
        assert status == 'failed'
        assert result is None
        assert 'not allowlisted' in error
        return job

    monkeypatch.setattr(tool_runner, 'get_settings', lambda: SimpleNamespace(
        tool_runner_worker_id='worker-a',
        tool_runner_project=None,
        tool_runner_lease_seconds=300,
    ))
    monkeypatch.setattr(tool_runner, 'claim_next_tool_job', fake_claim)
    monkeypatch.setattr(tool_runner, 'heartbeat_tool_job', fake_heartbeat)
    monkeypatch.setattr(tool_runner, 'finish_claimed_tool_job', fake_finish)

    assert await tool_runner.run_once() is True
