from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth
from app import main


client = TestClient(main.app)


def test_auth_noops_when_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        ope_require_api_key=False,
        ope_api_keys='',
    ))

    assert auth.require_api_key(None) is None


def test_auth_requires_bearer_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        ope_require_api_key=True,
        ope_api_keys='secret-1',
    ))

    with pytest.raises(HTTPException) as exc:
        auth.require_api_key(None)

    assert exc.value.status_code == 401


def test_auth_rejects_invalid_token(monkeypatch) -> None:
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        ope_require_api_key=True,
        ope_api_keys='secret-1',
    ))

    with pytest.raises(HTTPException) as exc:
        auth.require_api_key('Bearer wrong')

    assert exc.value.status_code == 403


def test_auth_rejects_non_ascii_token_without_crashing(monkeypatch) -> None:
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        ope_require_api_key=True,
        ope_api_keys='secret-1',
    ))

    with pytest.raises(HTTPException) as exc:
        auth.require_api_key('Bearer nope-\u2603')

    assert exc.value.status_code == 403


def test_auth_accepts_valid_token(monkeypatch) -> None:
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        ope_require_api_key=True,
        ope_api_keys='secret-1,secret-2',
    ))

    assert auth.require_api_key('Bearer secret-2') is None


def test_health_remains_open_when_auth_enabled(monkeypatch) -> None:
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        ope_require_api_key=True,
        ope_api_keys='secret-1',
    ))

    response = client.get('/health')

    assert response.status_code == 200


def test_protected_endpoint_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        ope_require_api_key=True,
        ope_api_keys='secret-1',
    ))

    response = client.get('/routes')

    assert response.status_code == 401


def test_protected_endpoint_accepts_valid_token(monkeypatch) -> None:
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        ope_require_api_key=True,
        ope_api_keys='secret-1',
    ))

    response = client.get('/routes', headers={'Authorization': 'Bearer secret-1'})

    assert response.status_code == 200
