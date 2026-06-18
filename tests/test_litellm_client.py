from app.litellm_client import _chat_completion_payload, _clean_header_value


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
