from pathlib import Path
from typing import get_args

import yaml

from app.models import AskRequest, QueryType
from app.planner import build_plan, list_routes


ROOT = Path(__file__).resolve().parent.parent


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding='utf-8'))


def litellm_model_names(config: dict) -> set[str]:
    return {item['model_name'] for item in config['model_list']}


def test_routing_policy_covers_all_query_types() -> None:
    routes = load_yaml('policies/routing-policy.yaml')['routes']

    assert set(routes) == set(get_args(QueryType))


def test_routing_policy_models_exist_in_litellm_config() -> None:
    routes = load_yaml('policies/routing-policy.yaml')['routes']
    litellm_models = litellm_model_names(load_yaml('policies/litellm-config.yaml'))

    referenced_models: set[str] = set()
    for spec in routes.values():
        referenced_models.add(spec['planner_model'])
        referenced_models.add(spec['primary_model'])
        referenced_models.update(spec.get('fallbacks', []))

    assert referenced_models <= litellm_models


def test_k8s_litellm_config_matches_policy_file() -> None:
    k8s_docs = list(yaml.safe_load_all((ROOT / 'k8s/litellm.yaml').read_text(encoding='utf-8')))
    config_map = next(doc for doc in k8s_docs if doc['kind'] == 'ConfigMap')
    k8s_litellm_config = yaml.safe_load(config_map['data']['config.yaml'])
    policy_litellm_config = load_yaml('policies/litellm-config.yaml')

    assert litellm_model_names(k8s_litellm_config) == litellm_model_names(policy_litellm_config)


def test_memory_text_index_uses_immutable_expression() -> None:
    migration = (ROOT / 'migrations/001_initial_schema.sql').read_text(encoding='utf-8')

    assert "to_tsvector('english'::regconfig, summary)" in migration
    assert 'array_to_string(tags' not in migration


def test_build_plan_uses_route_policy() -> None:
    assert build_plan(AskRequest(query='quick lookup please')).primary_model == 'openai-mini'
    assert build_plan(AskRequest(query='debug this code path')).primary_model == 'claude-coding'
    assert build_plan(AskRequest(query='deploy this', allow_tools=True)).route == 'tool_action'


def test_route_catalog_is_policy_backed() -> None:
    routes = {route.route: route for route in list_routes()}
    policy = load_yaml('policies/routing-policy.yaml')['routes']

    assert set(routes) == set(policy)
    for route_name, spec in policy.items():
        assert routes[route_name].primary_model == spec['primary_model']
        assert routes[route_name].fallback_models == spec.get('fallbacks', [])


def test_tool_enabled_routes_require_approval_policy() -> None:
    routes = load_yaml('policies/routing-policy.yaml')['routes']
    approval_rules = load_yaml('policies/approval-policy.yaml')['rules']

    tool_routes = {name for name, spec in routes.items() if spec.get('tools_enabled', False)}
    approved_routes = {
        route
        for rule in approval_rules
        for route in rule.get('applies_to_routes', [])
    }

    assert tool_routes <= approved_routes
    assert approved_routes <= set(routes)
