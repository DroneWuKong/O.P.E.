import httpx
from app.config import get_settings


async def call_with_fallbacks(primary: str, fallbacks: list[str], messages: list[dict[str, str]]) -> tuple[str, str, list[str]]:
    settings = get_settings()
    attempted: list[str] = []
    last_error = None

    for model in [primary, *fallbacks]:
        attempted.append(model)
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                resp = await client.post(
                    f'{settings.litellm_base_url}/chat/completions',
                    json={
                        'model': model,
                        'messages': messages,
                        'temperature': 0.2,
                    },
                    headers={'Content-Type': 'application/json'},
                )
            resp.raise_for_status()
            data = resp.json()
            return data['choices'][0]['message']['content'], model, attempted[:-1]
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f'All configured model routes failed: {last_error}')
