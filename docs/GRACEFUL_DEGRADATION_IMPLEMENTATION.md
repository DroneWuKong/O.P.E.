# Graceful Degradation Implementation Plan

## Purpose

This document defines the full graceful degradation implementation plan for Prismo/O.P.E. using an onion architecture. The goal is to ensure that Prismo loses capability in controlled layers instead of failing as one brittle system.

O.P.E. already acts as the self-hosted AI/control layer on the Octoputer k3s cluster and is intended to route work across OpenAI, Claude, Gemini, and Mistral through LiteLLM. This plan extends that control-layer role so O.P.E. can also track system health, fallback state, provider degradation, transport availability, queue status, and operator-facing mission impact.

## Core Principle

Outer layers may disappear. Inner layers must remain useful.

```text
Layer 7 — AI / Automation
Layer 6 — Cloud / Fleet Sync
Layer 5 — TAK / Collaboration
Layer 4 — Network / Mesh / Relay / Fiber / LTE
Layer 3 — Positioning / GPS / RTK / VIO / Dead Reckoning
Layer 2 — Maps / Mission / Airspace / Terrain
Layer 1 — Local Records / Logs / Checklists / Data
Layer 0 — Human Operator
```

The system should never silently lose data. It should clearly tell the operator what degraded, what still works, what is queued, and what mode they are operating in.

---

## Current O.P.E. Fit

O.P.E. already has useful foundations for this work:

- FastAPI control surface.
- `/health` and `/models/status` requirements.
- LiteLLM provider fallback boundary.
- Planned Redis-backed provider health and cooldown state.
- Planned Postgres + pgvector state layer.
- Octoputer k3s deployment target.
- Manual-dispatch deploy workflows on `octo-cp`.
- Tool approval policy and queue concepts.

Those pieces should be formalized into a broader degradation framework.

---

## Target Architecture

```text
Prismo Client / Hangar Hub / Field Tool
        |
        v
O.P.E. API Gateway
        |
        +-- Health Bus
        +-- Capability Registry
        +-- Degradation Engine
        +-- Provider Router
        +-- Tool Queue
        +-- Sync Queue
        +-- Transport Broker
        +-- Operator Status API
        |
        v
Postgres + Redis + LiteLLM + Tool Runners
```

### Major Components

| Component | Purpose |
|---|---|
| Health Bus | Normalize health reports from providers, tools, transports, databases, and field services. |
| Capability Registry | Describes what each feature requires, enhances, and falls back to. |
| Degradation Engine | Calculates current operating mode and fallback state. |
| Provider Router | Chooses AI/model provider and tracks fallback attempts. |
| Transport Broker | Chooses available message path: local, tailnet, mesh, LoRa, relay, store-forward, manual export. |
| Sync Queue | Local-first event and artifact sync system. |
| Operator Status API | Human-readable status surface for Prismo clients. |
| Failure Test Harness | Simulates outages and verifies fallback behavior. |

---

## Degradation Modes

```text
NORMAL
DEGRADED
AI_OFFLINE
COMMS_LIMITED
LOCAL_ONLY
NAV_LIMITED
RECORD_ONLY
UNSAFE_STORAGE
ABORT_REQUIRED
```

### Example Mode Object

```json
{
  "mode": "COMMS_LIMITED",
  "severity": "YELLOW",
  "lost_layers": ["cloud", "tak"],
  "available_layers": ["local_records", "maps", "gps", "mesh"],
  "operator_message": "Cloud and TAK unavailable. Local logging and mesh remain active.",
  "recommended_action": "Continue if local operation is acceptable.",
  "queued_items": 14
}
```

---

## Capability Contract Schema

Every Prismo/O.P.E. capability should have a contract.

```yaml
id: rtk_survey_point_collection
name: RTK Survey Point Collection
layer: positioning

requires:
  - local_database
  - position_service

enhances:
  - rtk_corrections
  - cached_maps
  - cloud_sync

fallbacks:
  - standard_gnss_point
  - manual_accuracy_warning
  - record_only_note

minimum_viable_mode:
  - local_database
  - manual_note

operator_messages:
  rtk_lost: "RTK lost. Points will be recorded with reduced accuracy."
  gps_lost: "GPS unavailable. Manual location or record-only mode required."
```

Suggested location:

```text
capabilities/
├── ai.yaml
├── cloud-sync.yaml
├── tak-collaboration.yaml
├── transport.yaml
├── positioning.yaml
├── maps.yaml
├── local-records.yaml
└── tool-execution.yaml
```

---

## Health Event Model

### Status Values

```text
OK
DEGRADED
OFFLINE
STALE
UNKNOWN
UNSAFE
```

### Health Event

```json
{
  "service": "litellm",
  "component": "provider_router",
  "layer": "ai_automation",
  "status": "DEGRADED",
  "reason": "claude_provider_cooldown",
  "last_ok": "2026-06-24T16:22:00Z",
  "fallback_active": "openai",
  "metadata": {
    "failed_provider": "claude",
    "fallback_provider": "openai",
    "cooldown_seconds": 300
  }
}
```

### Database Tables

```sql
CREATE TABLE health_events (
  id BIGSERIAL PRIMARY KEY,
  service TEXT NOT NULL,
  component TEXT,
  layer TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT,
  fallback_active TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE service_health_current (
  service TEXT PRIMARY KEY,
  component TEXT,
  layer TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT,
  fallback_active TEXT,
  metadata JSONB DEFAULT '{}',
  last_ok TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

Redis can hold fast-changing current health and cooldowns; Postgres should hold durable event history.

---

## API Endpoints

Add these endpoints to O.P.E. Core.

```text
GET  /health
GET  /ready
GET  /models/status
GET  /system/status
GET  /system/onion
GET  /system/capabilities
GET  /system/degradation
POST /health/event
POST /health/heartbeat
POST /degradation/simulate
POST /sync/enqueue
GET  /sync/status
GET  /transport/status
GET  /operator/status
```

### `/operator/status` Example Response

```json
{
  "mode": "LOCAL_ONLY",
  "severity": "ORANGE",
  "summary": "Cloud, TAK, and AI are unavailable. Local records, maps, and GPS remain active.",
  "available": ["local_records", "cached_maps", "gps"],
  "limited": ["sync_queue", "position_accuracy"],
  "unavailable": ["cloud_sync", "tak", "ai_assistant"],
  "queued": {
    "sync_items": 22,
    "tool_jobs": 0,
    "messages": 7
  },
  "recommendation": "Continue local collection. Sync will resume when connectivity returns."
}
```

---

## Implementation Phases

## Phase 0 — Repo Groundwork

Deliverables:

- Add this implementation plan.
- Add issue epic.
- Add labels if desired: `architecture`, `degradation`, `health`, `sync`, `transport`, `operator-ui`.
- Confirm existing app structure and current FastAPI modules.

Acceptance criteria:

- Plan exists in `docs/`.
- Work is decomposed into issues.
- No credentials or kubeconfigs added.

---

## Phase 1 — Onion Model and Capability Registry

Deliverables:

```text
app/degradation/layers.py
app/degradation/modes.py
app/degradation/capabilities.py
capabilities/*.yaml
```

Tasks:

1. Define `OnionLayer` enum.
2. Define `DegradationMode` enum.
3. Define capability contract Pydantic model.
4. Load YAML capability files at startup.
5. Add `GET /system/capabilities`.
6. Add unit tests for capability parsing.

Acceptance criteria:

- Invalid capability YAML fails startup or validation.
- `/system/capabilities` returns loaded capabilities.
- Each capability declares `requires`, `enhances`, `fallbacks`, and `minimum_viable_mode`.

---

## Phase 2 — Health Bus

Deliverables:

```text
app/health/models.py
app/health/bus.py
app/health/store.py
app/routes/health.py
migrations/002_health_events.sql
```

Tasks:

1. Add `HealthEvent` model.
2. Add health status enum.
3. Store current health in Redis.
4. Store durable event history in Postgres.
5. Add `POST /health/event`.
6. Add `POST /health/heartbeat`.
7. Extend `/health` and `/ready` without breaking existing probes.

Acceptance criteria:

- Services can publish health events.
- Current status can be retrieved from Redis.
- Event history persists in Postgres.
- Readiness only fails when core dependencies are actually unavailable.

---

## Phase 3 — Degradation Engine

Deliverables:

```text
app/degradation/engine.py
app/degradation/resolver.py
app/routes/system.py
```

Tasks:

1. Read current health.
2. Evaluate capability availability.
3. Calculate active degradation mode.
4. Generate operator-facing summary.
5. Add `GET /system/degradation`.
6. Add `GET /system/onion`.

Acceptance criteria:

- If AI provider health is offline, mode becomes `AI_OFFLINE` but local/tool-safe workflows remain available.
- If cloud/sync health is offline, mode becomes `LOCAL_ONLY` or `COMMS_LIMITED` depending on transport state.
- If database write safety fails, mode becomes `UNSAFE_STORAGE`.
- Output includes available, limited, unavailable, and queued items.

---

## Phase 4 — Provider Fallback Integration

Deliverables:

```text
app/providers/router.py
app/providers/health.py
app/providers/cooldown.py
```

Tasks:

1. Track provider failures.
2. Publish provider health events.
3. Store provider cooldowns in Redis.
4. Include fallback attempts in `/ask` responses.
5. Include provider state in `/models/status`.

Acceptance criteria:

- Failed providers enter cooldown.
- Route attempts are logged.
- Model/provider fallback is visible to the operator/admin.
- LiteLLM remains provider execution layer; O.P.E. remains route decision layer.

---

## Phase 5 — Sync Queue

Deliverables:

```text
app/sync/models.py
app/sync/queue.py
app/routes/sync.py
migrations/003_sync_queue.sql
```

Tasks:

1. Add durable sync queue table.
2. Queue tool outputs, memory writes, logs, and artifact references.
3. Add retry policy.
4. Add conflict status.
5. Add manual export bundle placeholder.

Acceptance criteria:

- Cloud failure never blocks local write.
- Queued item count appears in `/operator/status`.
- Sync records preserve failure reason and retry count.
- Nothing is silently discarded.

---

## Phase 6 — Transport Broker

Deliverables:

```text
app/transport/models.py
app/transport/broker.py
app/transport/adapters/base.py
app/transport/adapters/tailnet.py
app/transport/adapters/store_forward.py
app/routes/transport.py
```

Tasks:

1. Define transport adapter interface.
2. Add tailnet/HTTP adapter.
3. Add store-forward adapter.
4. Add priority classes.
5. Add `GET /transport/status`.
6. Add hook for future mesh/LoRa/TAK adapters.

Priority classes:

```text
CRITICAL_ABORT
HEARTBEAT
POSITION
MISSION_UPDATE
COT_MARKER
LOG_SYNC
MEDIA_UPLOAD
AI_QUERY
```

Acceptance criteria:

- Transport state contributes to degradation mode.
- Low-bandwidth transports can reject heavy payload classes.
- Store-forward works when all live transports fail.

---

## Phase 7 — Operator Status API

Deliverables:

```text
app/operator/status.py
app/routes/operator.py
```

Tasks:

1. Aggregate health, degradation, sync, provider, and transport status.
2. Return a simple human-readable state object.
3. Add recommended action strings.
4. Add stale-state timestamps.

Acceptance criteria:

- Prismo/Hangar clients can show one status panel without knowing internal O.P.E. details.
- Status clearly separates available, limited, unavailable, stale, and unsafe states.
- Operator message does not require reading logs.

---

## Phase 8 — Failure Simulation and Tests

Deliverables:

```text
tests/test_degradation_engine.py
tests/test_health_events.py
tests/test_sync_queue.py
tests/test_transport_broker.py
scripts/simulate_degradation.py
```

Simulations:

```text
kill_ai_provider
kill_litellm
kill_redis
kill_postgres
kill_cloud_sync
kill_tailnet
fill_disk
queue_backlog
provider_timeout
stale_heartbeat
```

Acceptance criteria:

- No simulated failure causes silent success.
- Unsafe storage produces `UNSAFE_STORAGE`.
- Provider failure does not collapse non-AI workflows.
- Cloud failure queues work.
- Operator status changes within expected polling window.

---

## Phase 9 — Octoputer Deployment Integration

Deliverables:

```text
k8s/health-config.yaml
k8s/redis.yaml
k8s/postgres.yaml
.github/workflows/octo-degradation-smoke.yml
```

Tasks:

1. Add degradation smoke test workflow.
2. Run on `octo-cp`.
3. Verify `/health`, `/ready`, `/system/degradation`, `/operator/status`.
4. Test Redis cooldown behavior.
5. Test DB persistence.

Acceptance criteria:

- Manual workflow can validate degradation system on Octoputer.
- No secret values are committed.
- Failed smoke test blocks declaring the degradation system functional.

---

## First Seven GitHub Issues to Create

1. Epic: Implement Prismo/O.P.E. graceful degradation onion framework.
2. Add onion layer model and capability registry.
3. Add health event bus with Redis current state and Postgres history.
4. Add degradation engine and operator status API.
5. Integrate AI provider fallback health/cooldown into degradation state.
6. Add local-first sync queue and queued-work status.
7. Add transport broker skeleton with tailnet and store-forward adapters.
8. Add degradation simulation tests and Octoputer smoke workflow.

---

## MVP Definition

The MVP is complete when O.P.E. can answer:

```text
What state am I in?
What broke?
What still works?
What was queued?
What fallback is active?
What should the operator do?
```

MVP endpoints:

```text
GET /system/degradation
GET /system/onion
GET /operator/status
GET /sync/status
GET /transport/status
POST /health/event
POST /health/heartbeat
```

MVP does not need full TAK, LoRa, RTK, or field-device integrations. It needs the framework that those integrations will plug into.

---

## Non-Negotiable Rules

1. Cloud loss must not block local work.
2. AI loss must not block manual workflows.
3. Provider failure must be visible and logged.
4. Sync failure must queue, not discard.
5. Stale data must be labeled stale.
6. Storage failure must be treated as dangerous.
7. Operator-facing status must be simple.
8. Every fallback must be testable.

---

## Suggested Next Commit After This Plan

Implement Phase 1 only:

```text
app/degradation/layers.py
app/degradation/modes.py
app/degradation/capabilities.py
capabilities/ai.yaml
capabilities/local-records.yaml
capabilities/cloud-sync.yaml
app/routes/system.py
```

Do not start with mesh, TAK, RTK, or LoRa. Start with the onion model and capability registry. Everything else depends on that.
