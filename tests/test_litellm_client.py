from app.litellm_client import _chat_completion_payload, _clean_header_value, _usage_metadata


def test_clean_header_value_removes_bom_and_outer_whitespace() -> None:
    assert _clean_header_value('\ufeff router-key \n') == 'router-key'


def test_clean_header_value_treats_empty_as_missing() -> None:
    assert _clean_header_value(' \ufeff ') is None


def test_openai_payload_omits_temperature_for_gpt5_family_aliases() -> None:
    payload = _chat_completion_payload('openai-mini', [{'role': 'user', 'content': 'hi'}])

    assert payload == {
        'model': 'openai-mini',
        'messages': [{'role': 'user', 'content': 'hi'}],
    }


def test_non_openai_payload_keeps_temperature() -> None:
    payload = _chat_completion_payload('claude-main', [{'role': 'user', 'content': 'hi'}])

    assert payload['temperature'] == 0.2


def test_usage_metadata_estimates_cost_from_usage() -> None:
    metadata = _usage_metadata(
        'openai-mini',
        {'usage': {'prompt_tokens': 1000, 'completion_tokens': 500, 'total_tokens': 1500}},
    )

    assert metadata['usage']['input_tokens'] == 1000
    assert metadata['usage']['output_tokens'] == 500
    assert metadata['usage']['total_tokens'] == 1500
    assert metadata['estimated_cost_usd'] == 0.00125
    assert metadata['cost_is_estimate'] is True
