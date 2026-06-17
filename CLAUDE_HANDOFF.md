# Claude Handoff: O.P.E. Core on the Octoputer

You are continuing implementation of O.P.E. Core, the Optimized Processing Engine.

## Goal

Build a self-hosted AI control layer that runs on the Octoputer k3s cluster and routes work across OpenAI, Claude, Gemini, and Mistral using LiteLLM.

## Existing context

- Repo: `DroneWuKong/O.P.E.`
- Existing cluster/conventions repo: `DroneWuKong/Ai-Project`
- Existing k3s cluster name: `Octoputer`
- Existing k3s docs to inspect:
  - `infra/octo/RUNNERS.md`
  - `infra/octo/minio/README.md`
  - `.github/workflows/octo-minio-deploy.yml`

## Build priorities

1. Finish the FastAPI MVP.
2. Replace the in-process memory shim with Postgres + pgvector.
3. Add Redis-backed provider health/cooldown state.
4. Add a GitHub Actions workflow named `Octo — Deploy OPE`.
5. Follow the `octo-cp` control-plane runner pattern from `Ai-Project`.
6. Keep O.P.E. in its own `ope` namespace.
7. Do not commit real provider credentials or local kubeconfigs.

## Required endpoints

- `GET /health`
- `GET /models/status`
- `POST /ask`
- `POST /memory/write`
- `POST /memory/search`

## Required services

- `ope-core`
- `litellm`
- `postgres` with pgvector
- `redis`

## Design rules

- O.P.E. chooses the route. LiteLLM only calls providers and handles provider-level fallback.
- Use memory first, search second, tools only after policy approval.
- Track which model was used and which fallbacks were attempted.
- Store useful memory after each request.
- Treat cluster-mutating workflows as manual dispatch jobs pinned to `octo-cp`.

## Next implementation steps

1. Audit current files for syntax/runtime errors.
2. Add missing route modules or keep routes in `app/main.py` for MVP simplicity.
3. Add database wiring using asyncpg or SQLAlchemy.
4. Add migration command documentation.
5. Add Redis-backed provider health.
6. Add an Octoputer deploy workflow.
7. Add smoke test commands.
8. Build and deploy only after placeholders are replaced through GitHub secrets or cluster secrets.
