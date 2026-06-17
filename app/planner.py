from app.models import AskRequest, RoutePlan


TECH_TERMS = {'k3s', 'kubernetes', 'yaml', 'docker', 'api', 'github', 'repo', 'litellm', 'postgres', 'redis'}
CODE_TERMS = {'code', 'bug', 'test', 'audit', 'refactor', 'build', 'compile', 'function', 'class'}
SEARCH_TERMS = {'latest', 'current', 'today', 'recent', 'docs', 'version', 'price', 'release'}
TOOL_TERMS = {'deploy', 'create', 'update', 'delete', 'run', 'apply', 'restart', 'commit', 'open pr'}


def classify(req: AskRequest) -> str:
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


def build_plan(req: AskRequest) -> RoutePlan:
    query_type = classify(req)
    project = req.project or 'ope-core'

    routes = {
        'quick_lookup': {
            'route': 'quick_lookup',
            'primary_model': 'mistral-fast',
            'fallback_models': ['gemini-fast', 'openai-mini'],
            'needs_search': False,
            'verify': False,
        },
        'technical_search': {
            'route': 'technical_search',
            'primary_model': 'openai-main',
            'fallback_models': ['claude-main', 'gemini-main', 'mistral-large'],
            'needs_search': req.allow_search,
            'verify': True,
            'citations_required': req.allow_search,
        },
        'codebase_work': {
            'route': 'codebase_work',
            'primary_model': 'claude-coding',
            'fallback_models': ['openai-coding', 'gemini-main', 'mistral-large'],
            'needs_search': req.allow_search,
            'verify': True,
        },
        'deep_reasoning': {
            'route': 'deep_reasoning',
            'primary_model': 'openai-main',
            'fallback_models': ['claude-main', 'gemini-main'],
            'needs_search': False,
            'verify': True,
        },
        'private_memory': {
            'route': 'private_memory',
            'primary_model': 'openai-main',
            'fallback_models': ['claude-main', 'gemini-main'],
            'needs_search': False,
            'verify': False,
        },
        'tool_action': {
            'route': 'tool_action',
            'primary_model': 'openai-main',
            'fallback_models': ['claude-main'],
            'needs_search': req.allow_search,
            'needs_tools': req.allow_tools,
            'verify': True,
        },
    }

    spec = routes[query_type]
    return RoutePlan(
        query_type=query_type,
        project=project,
        needs_memory=True,
        needs_search=spec.get('needs_search', False),
        needs_tools=spec.get('needs_tools', False),
        route=spec['route'],
        primary_model=spec['primary_model'],
        fallback_models=spec.get('fallback_models', []),
        verify=spec.get('verify', False),
        citations_required=spec.get('citations_required', False),
        write_memory=True,
        reason=f'Classified as {query_type} using MVP rule-based planner.',
    )
