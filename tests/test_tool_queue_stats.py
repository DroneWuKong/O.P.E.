from datetime import datetime, timezone

import pytest

from app import tools


class FakeAcquire:
    def __init__(self, conn) -> None:
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakePool:
    def __init__(self, conn) -> None:
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeConn:
    def __init__(self) -> None:
        self.project_args: list[str | None] = []

    async def fetch(self, query, project):
        self.project_args.append(project)
        return [
            {'status': 'approved', 'count': 2},
            {'status': 'running', 'count': 1},
        ]

    async def fetchrow(self, query, project):
        self.project_args.append(project)
        return {
            'running': 1,
            'expired_leases': 1,
            'oldest_pending_review_at': None,
            'oldest_approved_at': datetime(2026, 6, 18, 4, 30, tzinfo=timezone.utc),
            'newest_created_at': datetime(2026, 6, 18, 4, 31, tzinfo=timezone.utc),
            'newest_updated_at': datetime(2026, 6, 18, 4, 32, tzinfo=timezone.utc),
        }


@pytest.mark.asyncio
async def test_tool_queue_stats_aggregates_status_and_leases(monkeypatch) -> None:
    conn = FakeConn()
    monkeypatch.setattr(tools, 'get_memory_pool', lambda: FakePool(conn))

    stats = await tools.tool_queue_stats(project='ope-core')

    assert conn.project_args == ['ope-core', 'ope-core']
    assert stats.project == 'ope-core'
    assert stats.total == 3
    assert stats.by_status == {'approved': 2, 'running': 1}
    assert stats.running == 1
    assert stats.expired_leases == 1
    assert stats.oldest_approved_at == '2026-06-18T04:30:00+00:00'
