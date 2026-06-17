from functools import lru_cache
from pathlib import Path

import yaml

from app.models import ApprovalRule, AskRequest, QueryType


@lru_cache
def load_approval_rules() -> list[ApprovalRule]:
    path = Path(__file__).resolve().parent.parent / 'policies' / 'approval-policy.yaml'
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    return [ApprovalRule(**rule) for rule in data.get('rules', [])]


def list_approval_rules() -> list[ApprovalRule]:
    return load_approval_rules()


def approval_for_route(route: QueryType) -> ApprovalRule | None:
    for rule in load_approval_rules():
        if route in rule.applies_to_routes:
            return rule
    return None


def is_approved(req: AskRequest, route: QueryType) -> bool:
    rule = approval_for_route(route)
    if rule is None:
        return True
    return rule.token in set(req.approval_tokens)
