from typing import Any, Literal
from pydantic import BaseModel, Field


QueryType = Literal[
    'quick_lookup',
    'technical_search',
    'codebase_work',
    'deep_reasoning',
    'private_memory',
    'tool_action',
]


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1)
    project: str | None = None
    mode: str = 'auto'
    allow_search: bool = True
    allow_tools: bool = False
    budget: Literal['low', 'medium', 'high'] = 'medium'
    latency: Literal['fast', 'normal', 'patient'] = 'normal'
    debug: bool = False


class RoutePlan(BaseModel):
    query_type: QueryType
    project: str
    needs_memory: bool = True
    needs_search: bool = False
    needs_tools: bool = False
    route: str
    primary_model: str
    fallback_models: list[str] = []
    verify: bool = False
    citations_required: bool = False
    write_memory: bool = True
    reason: str = ''


class MemoryItem(BaseModel):
    scope: str = 'project'
    project: str | None = None
    memory_type: str = 'fact'
    summary: str
    value: dict[str, Any] = {}
    tags: list[str] = []
    importance: float = 0.5
    confidence: float = 0.5


class AskResponse(BaseModel):
    answer: str
    route_plan: RoutePlan
    model_used: str | None = None
    fallbacks_attempted: list[str] = []
    memory_used: list[MemoryItem] = []
    metadata: dict[str, Any] = {}
