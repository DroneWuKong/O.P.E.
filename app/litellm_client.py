import httpx
from app.config import get_settings
from app.provider_health import provider_health


PRICE_PER_MILLION_TOKENS = {
    'openai-main': {'input': 1.25, 'output': 10.0},
    'openai-mini': {'input': 0.25, 'output': 2.0},
    'openai-coding': {'input': 1.25, 'output': 10.0},
    'claude-main': {'input': 3.0, 'output': 15.0},
    'claude-coding': {'input': 3.0, 'output': 15.0},
    'gemini-main': {'input': 1.25, 'output': 10.0},
    'gemini-fast': {'input': 0.30, 'output': 2.50},
    'mistral-large': {'input': 2.0, 'output': 6.0},
    'mistral-fast': {'input': 0.20, 'output': 0.60},
}


def _clean_header_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.replace('\ufeff', '').strip()
    return cleaned or None


async def call_with_fallbacks(primary: str, fallbacks: list[str], messages: list[dict[str, str]]) -> tuple[str, str, list[str], dict]:
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
            return data['choices'][0]['message']['content'], model, attempted[:-1], _usage_metadata(model, data)
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


def _usage_metadata(model: str, response: dict) -> dict:
    usage = response.get('usage') or {}
    input_tokens = int(usage.get('prompt_tokens') or 0)
    output_tokens = int(usage.get('completion_tokens') or 0)
    total_tokens = int(usage.get('total_tokens') or input_tokens + output_tokens)
    pricing = PRICE_PER_MILLION_TOKENS.get(model)
    estimated_cost_usd = None
    if pricing:
        estimated_cost_usd = (
            (input_tokens / 1_000_000) * pricing['input']
            + (output_tokens / 1_000_000) * pricing['output']
        )

    return {
        'usage': {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
        },
        'estimated_cost_usd': estimated_cost_usd,
        'cost_is_estimate': True,
        'pricing_basis': 'static alias price estimate per 1M tokens',
    }
