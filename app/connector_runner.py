from __future__ import annotations

import base64
from typing import Any

import httpx

from app.config import get_settings
from app.models import ToolJob


MAX_TEXT_BYTES = 128_000


def _require_token(value: str | None, label: str) -> str:
    token = (value or '').strip()
    if not token or token.startswith('replace-with'):
        raise ValueError(f'{label} is not configured')
    return token


def _limit(value: Any, default: int = 10, maximum: int = 25) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _client(base_url: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url.rstrip('/'),
        timeout=20,
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'User-Agent': 'ope-core-connector-runner',
        },
    )


def _raise_for_status(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = ''
        try:
            body = response.json()
            detail = body.get('message') or body.get('error', {}).get('message') or ''
        except Exception:
            detail = response.text[:200]
        suffix = f': {detail}' if detail else ''
        raise RuntimeError(f'connector request failed with HTTP {response.status_code}{suffix}') from exc


def _github_client() -> httpx.Client:
    settings = get_settings()
    return _client(settings.github_api_base_url, _require_token(settings.github_token, 'GITHUB_TOKEN'))


def _google_token(*, gmail: bool = False) -> str:
    settings = get_settings()
    if gmail:
        return _require_token(settings.gmail_access_token or settings.google_access_token, 'GMAIL_ACCESS_TOKEN or GOOGLE_ACCESS_TOKEN')
    return _require_token(settings.google_access_token, 'GOOGLE_ACCESS_TOKEN')


def _google_client(*, gmail: bool = False) -> httpx.Client:
    settings = get_settings()
    return _client(settings.google_api_base_url, _google_token(gmail=gmail))


def _github_search_repos(payload: dict[str, Any]) -> dict:
    query = str(payload.get('query') or '').strip()
    if not query:
        raise ValueError('query is required')

    with _github_client() as client:
        response = client.get(
            '/search/repositories',
            params={
                'q': query,
                'per_page': _limit(payload.get('limit')),
                'sort': payload.get('sort') or 'updated',
            },
        )
        _raise_for_status(response)
        data = response.json()

    return {
        'ok': True,
        'items': [
            {
                'full_name': item.get('full_name'),
                'description': item.get('description'),
                'private': item.get('private'),
                'html_url': item.get('html_url'),
                'updated_at': item.get('updated_at'),
            }
            for item in data.get('items', [])
        ],
        'total_count': data.get('total_count', 0),
    }


def _github_read_file(payload: dict[str, Any]) -> dict:
    owner = str(payload.get('owner') or '').strip()
    repo = str(payload.get('repo') or '').strip()
    path = str(payload.get('path') or '').strip().lstrip('/')
    if not owner or not repo or not path:
        raise ValueError('owner, repo, and path are required')

    params = {}
    if payload.get('ref'):
        params['ref'] = payload['ref']

    with _github_client() as client:
        response = client.get(f'/repos/{owner}/{repo}/contents/{path}', params=params)
        _raise_for_status(response)
        data = response.json()

    if isinstance(data, list) or data.get('type') != 'file':
        raise ValueError('path must resolve to a file')
    encoded = (data.get('content') or '').replace('\n', '')
    content = base64.b64decode(encoded).decode('utf-8', errors='replace')
    if len(content.encode('utf-8')) > MAX_TEXT_BYTES:
        content = content.encode('utf-8')[:MAX_TEXT_BYTES].decode('utf-8', errors='replace')

    return {
        'ok': True,
        'name': data.get('name'),
        'path': data.get('path'),
        'sha': data.get('sha'),
        'html_url': data.get('html_url'),
        'truncated': data.get('size', 0) > MAX_TEXT_BYTES,
        'content': content,
    }


def _drive_search_files(payload: dict[str, Any]) -> dict:
    query = str(payload.get('query') or '').strip()
    if not query:
        raise ValueError('query is required')
    escaped_query = query.replace("'", "\\'")
    drive_query = payload.get('drive_query') or f"name contains '{escaped_query}' and trashed = false"

    with _google_client() as client:
        response = client.get(
            '/drive/v3/files',
            params={
                'q': drive_query,
                'pageSize': _limit(payload.get('limit')),
                'fields': 'files(id,name,mimeType,webViewLink,modifiedTime,size)',
            },
        )
        _raise_for_status(response)
        data = response.json()

    return {'ok': True, 'files': data.get('files', [])}


def _drive_read_document(payload: dict[str, Any]) -> dict:
    file_id = str(payload.get('file_id') or '').strip()
    if not file_id:
        raise ValueError('file_id is required')
    export_mime = str(payload.get('mime_type') or 'text/plain')

    with _google_client() as client:
        response = client.get(f'/drive/v3/files/{file_id}/export', params={'mimeType': export_mime})
        _raise_for_status(response)
        content = response.content[:MAX_TEXT_BYTES].decode('utf-8', errors='replace')

    return {
        'ok': True,
        'file_id': file_id,
        'mime_type': export_mime,
        'truncated': len(response.content) > MAX_TEXT_BYTES,
        'content': content,
    }


def _gmail_search_mail(payload: dict[str, Any]) -> dict:
    if not get_settings().gmail_enabled:
        raise ValueError('Gmail connector is disabled')
    query = str(payload.get('query') or '').strip()
    if not query:
        raise ValueError('query is required')

    with _google_client(gmail=True) as client:
        response = client.get(
            '/gmail/v1/users/me/messages',
            params={'q': query, 'maxResults': _limit(payload.get('limit'), default=10, maximum=20)},
        )
        _raise_for_status(response)
        data = response.json()

    return {'ok': True, 'messages': data.get('messages', []), 'result_size_estimate': data.get('resultSizeEstimate', 0)}


def _gmail_read_thread(payload: dict[str, Any]) -> dict:
    if not get_settings().gmail_enabled:
        raise ValueError('Gmail connector is disabled')
    thread_id = str(payload.get('thread_id') or '').strip()
    if not thread_id:
        raise ValueError('thread_id is required')

    with _google_client(gmail=True) as client:
        response = client.get(
            f'/gmail/v1/users/me/threads/{thread_id}',
            params={'format': payload.get('format') or 'metadata'},
        )
        _raise_for_status(response)
        data = response.json()

    return {'ok': True, 'thread': data}


CONNECTOR_ACTIONS = {
    ('github', 'search_repos'): _github_search_repos,
    ('github', 'read_file'): _github_read_file,
    ('google_drive', 'search_files'): _drive_search_files,
    ('google_drive', 'read_document'): _drive_read_document,
    ('gmail', 'search_mail'): _gmail_search_mail,
    ('gmail', 'read_thread'): _gmail_read_thread,
}


def execute_connector_tool(job: ToolJob) -> dict:
    if not job.tool_name.startswith('connector:'):
        raise ValueError(f'tool is not a connector: {job.tool_name}')
    connector_id = job.tool_name.split(':', 1)[1]
    handler = CONNECTOR_ACTIONS.get((connector_id, job.action))
    if handler is None:
        raise ValueError(f'connector action is not allowlisted: {connector_id}/{job.action}')
    result = handler(job.payload)
    return {
        'ok': True,
        'connector': connector_id,
        'action': job.action,
        'result': result,
    }
