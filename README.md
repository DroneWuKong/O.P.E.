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
curl -s http://localhost:8080/ask \
  -H 'Content-Type: application/json' \
  -d @examples/ask.json
```

## Octoputer staging

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secrets.example.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/litellm.yaml
kubectl apply -f k8s/ope-core.yaml
```

Replace all placeholder secrets before putting this anywhere serious. The repo is public, because apparently we enjoy danger, so do not commit actual keys.
