import httpx
from app.config import get_settings
from app.provider_health import provider_health


def _clean_header_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.replace('\ufeff', '').strip()
    return cleaned or None


async def call_with_fallbacks(primary: str, fallbacks: list[str], messages: list[dict[str, str]]) -> tuple[str, str, list[str]]:
    settings = get_settings()
    attempted: list[str] = []
    last_error = None

    for model in [primary, *fallbacks]:
        if not await provider_health.is_available(model):
            attempted.append(model)
            continue

        attempted.append(model)
        try:
            headers = {'Content-Type': 'application/json'}
            litellm_api_key = _clean_header_value(settings.litellm_api_key)
            if litellm_api_key:
                headers['Authorization'] = f'Bearer {litellm_api_key}'

            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                resp = await client.post(
                    f'{settings.litellm_base_url}/chat/completions',
                    json=_chat_completion_payload(model, messages),
                    headers=headers,
                )
            resp.raise_for_status()
            data = resp.json()
            await provider_health.mark_success(model)
            return data['choices'][0]['message']['content'], model, attempted[:-1]
        except httpx.HTTPStatusError as exc:
            last_error = exc
            reason = _reason_for_status(exc.response.status_code)
            await provider_health.mark_failure(model, reason)
        except Exception as exc:
            last_error = exc
            await provider_health.mark_failure(model, 'timeout' if isinstance(exc, httpx.TimeoutException) else 'error')

    raise RuntimeError(f'All configured model routes failed: {last_error}')


def _reason_for_status(status_code: int) -> str:
    if status_code == 429:
        return 'rate_limit'
    if status_code == 402:
        return 'quota'
    if status_code in {408, 504}:
        return 'timeout'
    if status_code in {500, 502, 503}:
        return 'overloaded'
    return f'http_{status_code}'


def _chat_completion_payload(model: str, messages: list[dict[str, str]]) -> dict[str, object]:
    payload: dict[str, object] = {
        'model': model,
        'messages': messages,
    }
    if not model.startswith('openai-'):
        payload['temperature'] = 0.2
    return payload
