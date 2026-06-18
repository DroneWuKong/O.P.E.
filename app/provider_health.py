from __future__ import annotations

import asyncio
import time

import redis.asyncio as redis

from app.config import get_settings


class ProviderHealth:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        if self._redis is not None:
            return
        settings = get_settings()
        self._redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.ope_external_connect_timeout_seconds,
            socket_timeout=settings.ope_external_connect_timeout_seconds,
        )
        await asyncio.wait_for(
            self._redis.ping(),
            timeout=settings.ope_external_connect_timeout_seconds,
        )

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    def _client(self) -> redis.Redis:
        if self._redis is None:
            raise RuntimeError('Redis provider health store is not initialized')
        return self._redis

    @staticmethod
    def _cooldown_key(model: str) -> str:
        return f'provider-health:{model}:cooldown_until'

    @staticmethod
    def _failure_key(model: str) -> str:
        return f'provider-health:{model}:last_failure'

    async def is_available(self, model: str) -> bool:
        value = await self._client().get(self._cooldown_key(model))
        if value is None:
            return True
        return time.time() >= float(value)

    async def mark_failure(self, model: str, reason: str, cooldown_seconds: int | None = None) -> None:
        settings = get_settings()
        cooldown = cooldown_seconds or settings.provider_cooldown_seconds
        client = self._client()
        await client.set(self._failure_key(model), reason)
        if reason in {'rate_limit', 'quota', 'timeout', 'overloaded'}:
            await client.set(self._cooldown_key(model), time.time() + cooldown, ex=cooldown)

    async def mark_success(self, model: str) -> None:
        client = self._client()
        await client.delete(self._cooldown_key(model))

    async def health(self) -> dict:
        started = time.perf_counter()
        await self._client().ping()
        return {
            'ok': True,
            'latency_ms': int((time.perf_counter() - started) * 1000),
        }

    async def status(self) -> dict:
        client = self._client()
        now = time.time()
        keys = set()
        async for key in client.scan_iter(match='provider-health:*:*'):
            parts = key.split(':')
            if len(parts) >= 3:
                keys.add(parts[1])

        status: dict[str, dict] = {}
        for model in sorted(keys):
            cooldown_until = await client.get(self._cooldown_key(model))
            last_failure = await client.get(self._failure_key(model))
            until = float(cooldown_until) if cooldown_until else 0.0
            status[model] = {
                'available': now >= until,
                'cooldown_remaining_seconds': max(0, int(until - now)),
                'last_failure': last_failure,
            }
        return status


provider_health = ProviderHealth()
