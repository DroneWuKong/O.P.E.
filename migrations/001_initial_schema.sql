CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS memory_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scope TEXT NOT NULL,
  project_id TEXT,
  memory_type TEXT NOT NULL,
  memory_key TEXT,
  value JSONB NOT NULL DEFAULT '{}'::jsonb,
  summary TEXT NOT NULL,
  tags TEXT[] DEFAULT '{}',
  importance REAL DEFAULT 0.5,
  confidence REAL DEFAULT 0.5,
  source TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS query_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id TEXT,
  query TEXT NOT NULL,
  query_type TEXT,
  selected_route TEXT,
  selected_model TEXT,
  fallback_models TEXT[] DEFAULT '{}',
  sources_used TEXT[] DEFAULT '{}',
  success BOOLEAN,
  latency_ms INTEGER,
  estimated_cost NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_stats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_alias TEXT NOT NULL,
  task_type TEXT NOT NULL,
  success_count INTEGER DEFAULT 0,
  failure_count INTEGER DEFAULT 0,
  avg_latency_ms INTEGER,
  avg_cost NUMERIC,
  quality_score REAL DEFAULT 0.5,
  last_failure_reason TEXT,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(model_alias, task_type)
);

CREATE INDEX IF NOT EXISTS idx_memory_project_type ON memory_items(project_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_memory_tags ON memory_items USING GIN(tags);
