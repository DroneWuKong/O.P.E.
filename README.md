# O.P.E. Core

**O.P.E.** stands for **Optimized Processing Engine**.

O.P.E. Core is a self-hosted AI control layer designed to run on the **Octoputer** k3s cluster. It provides one internal API for intelligent model routing, persistent memory, search orchestration, provider fallback, and approved tool execution.

The first MVP routes work across:

- OpenAI
- Anthropic Claude
- Google Gemini
- Mistral AI

using LiteLLM as the model gateway, with O.P.E. Core deciding which route/model should be used for each request.

## MVP stack

- FastAPI for the O.P.E. Core API
- LiteLLM for multi-provider model access and fallback
- Postgres + pgvector for persistent memory
- Redis for provider health, cache, sessions, and cooldown state
- k3s manifests for staging on the Octoputer

## Core idea

O.P.E. should not ask, "Which model do I like today?"

It should ask:

1. What kind of task is this?
2. What memory matters?
3. Does this need search or tools?
4. Which model is best for this task?
5. Which provider is healthy right now?
6. What is the cheapest model that can do this correctly?
7. Should another model verify the answer?
8. What should be remembered afterward?

## Initial routes

- `quick_lookup`
- `technical_search`
- `codebase_work`
- `deep_reasoning`
- `private_memory`
- `tool_action`

## First local run

```bash
cp .env.example .env
docker compose -f docker-compose.local.yaml up --build
```

Then test:

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/ready
curl -s http://localhost:8080/models/status
curl -s http://localhost:8080/memory/stats
curl -s 'http://localhost:8080/events/recent?project=ope-core&limit=10'
curl -s http://localhost:8080/routes
curl -s http://localhost:8080/approvals
curl -s 'http://localhost:8080/tools/jobs?status=pending_review&limit=10'
curl -s 'http://localhost:8080/tools/queue/stats?project=ope-core'
curl -s http://localhost:8080/tools/jobs/claim \
  -H 'Content-Type: application/json' \
  -d '{"worker_id":"worker-a","project":"ope-core","lease_seconds":300}'
curl -s http://localhost:8080/plan \
  -H 'Content-Type: application/json' \
  -d '{"query":"please deploy this","allow_tools":true}'
curl -s http://localhost:8080/plan \
  -H 'Content-Type: application/json' \
  -d '{"query":"please deploy this","allow_tools":true,"approval_tokens":["tool_action_approved"]}'
curl -s http://localhost:8080/ask \
  -H 'Content-Type: application/json' \
  -d @examples/ask.json
curl -s http://localhost:8080/memory/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"Octoputer","project":"ope-core"}'
```

When `OPE_REQUIRE_API_KEY=true`, send protected API calls with:

```bash
curl -H "Authorization: Bearer <ope-api-key>" http://localhost:8080/routes
```

## API endpoints

- `GET /health`
- `GET /ready`
- `GET /models/status`
- `GET /memory/stats`
- `GET /events/recent`
- `GET /routes`
- `GET /approvals`
- `GET /tools/jobs`
- `GET /tools/queue/stats`
- `POST /tools/jobs`
- `POST /tools/jobs/claim`
- `POST /tools/jobs/{job_id}/heartbeat`
- `PATCH /tools/jobs/{job_id}`
- `POST /plan`
- `POST /ask`
- `POST /memory/write`
- `POST /memory/search`

Memory is backed by Postgres with pgvector enabled. Provider cooldown/status
state is backed by Redis. `/ready` checks Postgres and Redis, while
`/models/status` returns provider health plus model performance rollups. `/ask`
writes query events and model success/failure rollups to Postgres unless
`OPE_DISABLE_EVENT_LOGGING=true`.

`/routes` exposes the loaded routing policy, and `/plan` previews the route O.P.E.
would choose without calling LiteLLM or writing memory.

`/events/recent` exposes recent query events for audit/debugging, and
`/memory/stats` summarizes persisted memory by project, type, and scope.

Tool routes are gated by `policies/approval-policy.yaml`. A tool action can be
classified without approval, but `/ask` rejects it until the request includes the
matching approval token, currently `tool_action_approved`.

Approved tool-action asks create a `pending_review` tool job. Tool jobs are
auditable queue records only; O.P.E. does not execute commands yet. Future
workers can atomically claim approved jobs with a lease and refresh that lease
with heartbeat calls.

`/tools/queue/stats` summarizes backlog, running jobs, expired leases, and the
oldest waiting jobs for operator dashboards or deployment smoke checks.

The included `app.tool_runner` process is intentionally narrow: it only executes
`noop` jobs, marks all other tools failed, and ships as a zero-replica Kubernetes
deployment until an operator explicitly scales it.

## Smoke tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## CI and images

- **CI** runs smoke tests, policy consistency checks, YAML parsing, and a Docker
  build on pull requests, pushes to `main`, and manual dispatch.
- **Build OPE Core Image** publishes `ghcr.io/dronewukong/ope-core` on pushes to
  `main`, version tags, and manual dispatch.

## Octoputer staging

Use the manual GitHub Actions workflow **Octo — Deploy OPE**. It follows the
Octoputer control-plane runner pattern from `DroneWuKong/Ai-Project`: the job is
pinned to `vars.OCTO_CP_RUNNER || '["self-hosted","octo-cp"]'`, defaults
`KUBECONFIG` to `/etc/rancher/k3s/k3s.yaml`, creates Kubernetes secrets from
GitHub secrets, applies the `ope` namespace resources, runs the database
migration, smoke-tests `/health` plus `/ready` from the O.P.E. container, and
smoke-tests the tailnet-facing NodePorts from the runner.
By default it deploys `ghcr.io/dronewukong/ope-core:latest`; the manual `image`
input can pin a tag or `sha-*` image.

The Octoputer staging services expose stable NodePorts for Hangar Hub and other
tailnet clients:

- O.P.E. Core: `http://<octoputer-node>:30080`
- LiteLLM: `http://<octoputer-node>:30400`

Use an `Authorization: Bearer <ope-api-key>` header for protected O.P.E. routes.

Required GitHub secrets:

- `OPE_POSTGRES_PASSWORD`
- `OPE_API_KEYS`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `MISTRAL_API_KEY`
- `LITELLM_MASTER_KEY` optional

For manual kubectl testing only, copy `k8s/secrets.example.yaml` outside the
repo, replace every placeholder, and apply that private copy.

Replace all placeholder secrets before putting this anywhere serious. The repo is public, because apparently we enjoy danger, so do not commit actual keys.
