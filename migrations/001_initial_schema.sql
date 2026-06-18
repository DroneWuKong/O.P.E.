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
  embedding VECTOR(1536),
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
  failure_reason TEXT,
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

CREATE TABLE IF NOT EXISTS tool_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id TEXT,
  query_event_id UUID REFERENCES query_events(id) ON DELETE SET NULL,
  route TEXT NOT NULL DEFAULT 'tool_action',
  tool_name TEXT NOT NULL,
  action TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'pending_review',
  requested_by TEXT,
  approved_by TEXT,
  worker_id TEXT,
  lease_expires_at TIMESTAMPTZ,
  result JSONB,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_project_type ON memory_items(project_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_memory_tags ON memory_items USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_memory_text ON memory_items
  USING GIN(to_tsvector('english', summary));
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_project_key ON memory_items(project_id, memory_key)
  WHERE memory_key IS NOT NULL;

ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS embedding VECTOR(1536);
ALTER TABLE query_events ADD COLUMN IF NOT EXISTS failure_reason TEXT;

ALTER TABLE tool_jobs ADD COLUMN IF NOT EXISTS query_event_id UUID REFERENCES query_events(id) ON DELETE SET NULL;
ALTER TABLE tool_jobs ADD COLUMN IF NOT EXISTS route TEXT NOT NULL DEFAULT 'tool_action';
ALTER TABLE tool_jobs ADD COLUMN IF NOT EXISTS approved_by TEXT;
ALTER TABLE tool_jobs ADD COLUMN IF NOT EXISTS worker_id TEXT;
ALTER TABLE tool_jobs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
ALTER TABLE tool_jobs ADD COLUMN IF NOT EXISTS result JSONB;
ALTER TABLE tool_jobs ADD COLUMN IF NOT EXISTS error TEXT;
CREATE INDEX IF NOT EXISTS idx_tool_jobs_project_status ON tool_jobs(project_id, status);
CREATE INDEX IF NOT EXISTS idx_tool_jobs_created_at ON tool_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_jobs_claimable ON tool_jobs(status, lease_expires_at, created_at);
