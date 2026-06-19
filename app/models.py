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

ToolJobStatus = Literal[
    'pending_review',
    'approved',
    'running',
    'succeeded',
    'failed',
    'cancelled',
]

ConnectorId = Literal['github', 'google_drive', 'gmail']
ConnectorStatus = Literal['configured', 'needs_auth', 'disabled']


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1)
    project: str | None = None
    mode: str = 'auto'
    allow_search: bool = True
    allow_tools: bool = False
    approval_tokens: list[str] = Field(default_factory=list)
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
    fallback_models: list[str] = Field(default_factory=list)
    verify: bool = False
    citations_required: bool = False
    write_memory: bool = True
    approval_required: bool = False
    approval_granted: bool = False
    required_approval: str | None = None
    reason: str = ''


class RouteSpec(BaseModel):
    route: QueryType
    planner_model: str
    primary_model: str
    fallback_models: list[str] = Field(default_factory=list)
    search_enabled: bool = False
    tools_enabled: bool = False
    require_citations: bool = False
    verify: bool = False
    sources: list[str] = Field(default_factory=list)


class RoutesResponse(BaseModel):
    routes: list[RouteSpec] = Field(default_factory=list)


class ApprovalRule(BaseModel):
    name: str
    description: str
    token: str
    applies_to_routes: list[QueryType] = Field(default_factory=list)
    default_decision: Literal['allow', 'deny'] = 'deny'


class ApprovalPolicyResponse(BaseModel):
    rules: list[ApprovalRule] = Field(default_factory=list)


class ConnectorAction(BaseModel):
    name: str
    description: str
    read_only: bool = True
    requires_approval: bool = True


class ConnectorSpec(BaseModel):
    id: ConnectorId
    name: str
    provider: str
    status: ConnectorStatus
    auth_type: str
    auth_configured: bool = False
    scopes: list[str] = Field(default_factory=list)
    actions: list[ConnectorAction] = Field(default_factory=list)
    notes: str = ''


class ConnectorsResponse(BaseModel):
    connectors: list[ConnectorSpec] = Field(default_factory=list)


class ConnectorJobCreateRequest(BaseModel):
    project: str | None = None
    action: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_by: str | None = None
    approval_tokens: list[str] = Field(default_factory=list)


class MemoryItem(BaseModel):
    id: str | None = None
    scope: str = 'project'
    project: str | None = None
    memory_type: str = 'fact'
    memory_key: str | None = None
    summary: str
    value: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    importance: float = 0.5
    confidence: float = 0.5
    source: str | None = None


class AskResponse(BaseModel):
    answer: str
    route_plan: RoutePlan
    model_used: str | None = None
    fallbacks_attempted: list[str] = Field(default_factory=list)
    memory_used: list[MemoryItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryWriteRequest(BaseModel):
    scope: str = 'project'
    project: str | None = None
    memory_type: str = 'fact'
    memory_key: str | None = None
    summary: str = Field(..., min_length=1)
    value: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(0.5, ge=0, le=1)
    confidence: float = Field(0.5, ge=0, le=1)
    source: str | None = None


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    project: str | None = None
    memory_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(5, ge=1, le=25)


class MemorySearchResponse(BaseModel):
    memories: list[MemoryItem] = Field(default_factory=list)


class MemoryStatsResponse(BaseModel):
    total: int = 0
    by_project: dict[str, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)
    by_scope: dict[str, int] = Field(default_factory=dict)


class QueryEvent(BaseModel):
    id: str
    project: str | None = None
    query: str
    query_type: str | None = None
    selected_route: str | None = None
    selected_model: str | None = None
    fallback_models: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    success: bool | None = None
    latency_ms: int | None = None
    estimated_cost: float | None = None
    failure_reason: str | None = None
    created_at: str | None = None


class QueryEventsResponse(BaseModel):
    events: list[QueryEvent] = Field(default_factory=list)


class ToolJob(BaseModel):
    id: str
    project: str | None = None
    query_event_id: str | None = None
    route: str = 'tool_action'
    tool_name: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: ToolJobStatus = 'pending_review'
    requested_by: str | None = None
    approved_by: str | None = None
    worker_id: str | None = None
    lease_expires_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ToolJobCreateRequest(BaseModel):
    project: str | None = None
    tool_name: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_by: str | None = None
    approval_tokens: list[str] = Field(default_factory=list)


class ToolJobUpdateRequest(BaseModel):
    status: ToolJobStatus | None = None
    approved_by: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class ToolJobsResponse(BaseModel):
    jobs: list[ToolJob] = Field(default_factory=list)


class ToolQueueStatsResponse(BaseModel):
    project: str | None = None
    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    running: int = 0
    expired_leases: int = 0
    oldest_pending_review_at: str | None = None
    oldest_approved_at: str | None = None
    newest_created_at: str | None = None
    newest_updated_at: str | None = None


class ToolJobClaimRequest(BaseModel):
    worker_id: str = Field(..., min_length=1)
    project: str | None = None
    lease_seconds: int = Field(300, ge=30, le=3600)


class ToolJobHeartbeatRequest(BaseModel):
    worker_id: str = Field(..., min_length=1)
    lease_seconds: int = Field(300, ge=30, le=3600)
