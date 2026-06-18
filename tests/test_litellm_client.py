from app.litellm_client import _clean_header_value


def test_clean_header_value_removes_bom_and_outer_whitespace() -> None:
    assert _clean_header_value('\ufeff router-key \n') == 'router-key'


def test_clean_header_value_treats_empty_as_missing() -> None:
    assert _clean_header_value(' \ufeff ') is None
