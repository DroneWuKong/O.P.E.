import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

os.environ['OPE_SKIP_EXTERNAL_INIT'] = 'true'

from app import auth, main
from app.degradation.capabilities import load_capabilities
from app.degradation.layers import OnionLayer


def contract(**changes):
    return {
        'id': 'fixture', 'name': 'Fixture', 'layer': 'local_records',
        'implementation_status': 'planned', 'requires': ['local_database'],
        'enhances': [], 'fallbacks': ['manual_record'],
        'minimum_viable_mode': ['local_database'],
        'operator_messages': {'storage_lost': 'Verify storage.'}, **changes,
    }


def write_contract(directory: Path, data, name='fixture.yaml'):
    (directory / name).write_text(yaml.safe_dump(data), encoding='utf-8')


def test_shipped_registry_contains_valid_declared_capabilities():
    capabilities = {item.id: item for item in load_capabilities()}
    assert set(capabilities) == {'ai_assistant', 'local_records', 'cloud_sync'}
    assert capabilities['ai_assistant'].layer == OnionLayer.AI_AUTOMATION
    assert capabilities['cloud_sync'].implementation_status == 'planned'
    assert 'local_records' in capabilities['cloud_sync'].fallbacks


@pytest.mark.parametrize('data', [
    None, [], contract(layer='unknown'), contract(id='invalid id'),
    contract(minimum_viable_mode=[]), contract(fallbacks=[]),
    contract(requires=['local_database', 'local_database']),
    contract(requires=[123]), contract(operator_messages={'storage_lost': ' '}),
    contract(unrecognized='typo'),
    {key: value for key, value in contract().items() if key != 'requires'},
])
def test_invalid_contract_fails_validation_with_file_context(tmp_path, data):
    write_contract(tmp_path, data)
    with pytest.raises(ValueError, match='Invalid capability contract fixture.yaml'):
        load_capabilities(tmp_path)


def test_empty_malformed_and_duplicate_registry_fails(tmp_path):
    with pytest.raises(ValueError, match='No capability contracts'):
        load_capabilities(tmp_path)
    (tmp_path / 'fixture.yaml').write_text('requires: [broken', encoding='utf-8')
    with pytest.raises(ValueError, match='fixture.yaml'):
        load_capabilities(tmp_path)
    write_contract(tmp_path, contract())
    write_contract(tmp_path, contract(), 'duplicate.yml')
    with pytest.raises(ValueError, match='Duplicate capability ID'):
        load_capabilities(tmp_path)


def test_invalid_registry_blocks_startup_before_external_connections(tmp_path, monkeypatch):
    write_contract(tmp_path, contract(layer='unknown'))
    monkeypatch.setattr(main, 'load_capabilities', lambda: load_capabilities(tmp_path))
    monkeypatch.setattr(main, 'get_settings', lambda: SimpleNamespace(ope_skip_external_init=False))
    async def unexpected_connection():
        pytest.fail('invalid registry must fail before connecting external services')
    monkeypatch.setattr(main, 'connect_external_services', unexpected_connection)
    with pytest.raises(ValueError, match='fixture.yaml'):
        with TestClient(main.app):
            pass


def test_registry_endpoint_uses_startup_snapshot_and_existing_auth(tmp_path, monkeypatch):
    write_contract(tmp_path, contract())
    monkeypatch.setattr(main, 'load_capabilities', lambda: load_capabilities(tmp_path))
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        ope_require_api_key=True, ope_api_keys='fixture-secret'))
    with TestClient(main.app) as client:
        assert client.get('/system/capabilities').status_code == 401
        assert client.get('/system/capabilities', headers={'Authorization': 'Bearer wrong'}).status_code == 403
        # The route returns the validated startup snapshot, not a fresh disk read.
        (tmp_path / 'fixture.yaml').write_text('invalid: [', encoding='utf-8')
        response = client.get('/system/capabilities', headers={'Authorization': 'Bearer fixture-secret'})
        assert response.status_code == 200
        assert response.json()['capabilities'] == [contract()]
        assert 'system_capabilities' in client.get('/').json()['endpoints']
