from functools import lru_cache
from pathlib import Path
from typing import get_args

import yaml

from app.approvals import approval_for_route, is_approved
from app.models import AskRequest, QueryType, RoutePlan, RouteSpec


TECH_TERMS = {'k3s', 'kubernetes', 'yaml', 'docker', 'api', 'github', 'repo', 'litellm', 'postgres', 'redis'}
CODE_TERMS = {'code', 'bug', 'test', 'audit', 'refactor', 'build', 'compile', 'function', 'class'}
SEARCH_TERMS = {'latest', 'current', 'today', 'recent', 'docs', 'version', 'price', 'release'}
TOOL_TERMS = {'deploy', 'create', 'update', 'delete', 'run', 'apply', 'restart', 'commit', 'open pr'}
QUERY_TYPES = set(get_args(QueryType))


def classify(req: AskRequest) -> QueryType:
    if req.mode in QUERY_TYPES:
        return req.mode

    q = req.query.lower()
    words = set(q.replace('/', ' ').replace('-', ' ').split())

    if req.allow_tools and any(term in q for term in TOOL_TERMS):
        return 'tool_action'
    if words & CODE_TERMS:
        return 'codebase_work'
    if words & SEARCH_TERMS:
        return 'technical_search'
    if words & TECH_TERMS:
        return 'deep_reasoning'
    if 'remember' in q or 'what did we' in q or 'previous' in q:
        return 'private_memory'
    return 'quick_lookup'


@lru_cache
def load_route_policy() -> dict:
    path = Path(__file__).resolve().parent.parent / 'policies' / 'routing-policy.yaml'
    return yaml.safe_load(path.read_text(encoding='utf-8'))['routes']


@lru_cache
def load_model_catalog() -> list[str]:
    path = Path(__file__).resolve().parent.parent / 'policies' / 'litellm-config.yaml'
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    return sorted(model['model_name'] for model in config.get('model_list', []))


def list_model_aliases() -> list[str]:
    return load_model_catalog()


def _route_spec(route: QueryType, spec: dict) -> RouteSpec:
    search_enabled = spec.get('search_enabled', spec.get('web_allowed', False))
    return RouteSpec(
        route=route,
        planner_model=spec['planner_model'],
        primary_model=spec['primary_model'],
        fallback_models=spec.get('fallbacks', []),
        search_enabled=bool(search_enabled),
        tools_enabled=bool(spec.get('tools_enabled', False)),
        require_citations=bool(spec.get('require_citations', False)),
        verify=bool(spec.get('verify', False)),
        sources=spec.get('sources', []),
    )


def list_routes() -> list[RouteSpec]:
    routes = load_route_policy()
    return [_route_spec(route, spec) for route, spec in sorted(routes.items())]


def build_plan(req: AskRequest) -> RoutePlan:
    query_type = classify(req)
    project = req.project or 'ope-core'
    spec = load_route_policy()[query_type]
    search_enabled = spec.get('search_enabled', spec.get('web_allowed', False))
    tools_enabled = spec.get('tools_enabled', False)
    approval_rule = approval_for_route(query_type)
    approval_granted = is_approved(req, query_type)
    needs_tools = bool(tools_enabled and req.allow_tools and approval_granted)
    approval_note = ''
    if approval_rule and req.allow_tools and not approval_granted:
        approval_note = f' Approval required: provide approval token {approval_rule.token}.'

    return RoutePlan(
        query_type=query_type,
        project=project,
        needs_memory=True,
        needs_search=bool(search_enabled and req.allow_search),
        needs_tools=needs_tools,
        route=query_type,
        primary_model=spec['primary_model'],
        fallback_models=spec.get('fallbacks', []),
        verify=spec.get('verify', False),
        citations_required=bool(spec.get('require_citations', False) and req.allow_search),
        write_memory=True,
        approval_required=approval_rule is not None,
        approval_granted=approval_granted,
        required_approval=approval_rule.token if approval_rule else None,
        reason=f'Classified as {query_type} using MVP rule-based planner.{approval_note}',
    )
