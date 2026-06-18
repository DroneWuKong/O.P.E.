from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from app.config import get_settings


def configured_api_keys() -> list[str]:
    settings = get_settings()
    return [key.strip() for key in settings.ope_api_keys.split(',') if key.strip()]


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    keys = configured_api_keys()
    if not settings.ope_require_api_key and not keys:
        return

    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail={'error': 'missing_bearer_token'})

    token = authorization.removeprefix('Bearer ').strip()
    if not any(secrets.compare_digest(token, key) for key in keys):
        raise HTTPException(status_code=403, detail={'error': 'invalid_bearer_token'})
