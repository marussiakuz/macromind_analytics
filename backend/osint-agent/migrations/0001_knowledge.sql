-- Knowledge base schema (Task2 RAG §5). PostgreSQL 16 + pgvector.
-- Version 0001 — create core tables. Idempotent-ish IF NOT EXISTS.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS entities (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  entity_type TEXT NOT NULL, -- org | person | product | market
  name TEXT NOT NULL,
  identifiers JSONB NOT NULL DEFAULT '{}'::jsonb, -- {inn, ogrn, ...} with registry/country
  alt_names JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities USING gin (to_tsvector('russian', name));

CREATE TABLE IF NOT EXISTS entity_relations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  subject_id UUID NOT NULL REFERENCES entities(id),
  relation TEXT NOT NULL, -- customer | supplier | plaintiff | defendant | founder | ...
  object_id UUID REFERENCES entities(id),
  object_label TEXT,
  period_start DATE,
  period_end DATE,
  evidence_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  origin_id TEXT, -- dedupe key for reprints
  source_type TEXT NOT NULL, -- web | openalex | registry | file
  url TEXT,
  title TEXT,
  published_at TIMESTAMPTZ,
  retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  storage_path TEXT, -- /srv/macromind-knowledge/objects/...
  checksum TEXT,
  license TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_documents_origin ON documents(origin_id);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_type);

CREATE TABLE IF NOT EXISTS evidence (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id),
  entity_id UUID REFERENCES entities(id),
  claim_type TEXT NOT NULL DEFAULT 'fact', -- fact | forecast | team_claim | calculation | interpretation
  statement TEXT NOT NULL,
  locator TEXT, -- page/section/field path
  quote TEXT,
  period TEXT,
  geography TEXT,
  unit TEXT,
  verification_status TEXT NOT NULL DEFAULT 'unreviewed',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence(entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_doc ON evidence(document_id);

CREATE TABLE IF NOT EXISTS chunks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES documents(id),
  evidence_id UUID REFERENCES evidence(id),
  text TEXT NOT NULL,
  lang TEXT,
  token_count INT,
  embedding vector(1024), -- Qwen3-Embedding-0.6B dim (verify at Stage C)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE TABLE IF NOT EXISTS research_runs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  kind TEXT NOT NULL, -- collect | index | interpret | report
  status TEXT NOT NULL DEFAULT 'queued',
  owner TEXT,
  input_hash TEXT,
  budget_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cost_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  provider TEXT NOT NULL,
  task TEXT NOT NULL,
  status TEXT NOT NULL,
  prompt_tokens INT DEFAULT 0,
  completion_tokens INT DEFAULT 0,
  cost_rub NUMERIC,
  cost_is_estimated BOOLEAN DEFAULT true,
  run_id UUID REFERENCES research_runs(id),
  note TEXT,
  at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analysis_versions_k (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  study_id TEXT,
  legal_entity_inn TEXT,
  version INT NOT NULL,
  status TEXT NOT NULL,
  summary_json JSONB NOT NULL,
  request_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_avk_inn ON analysis_versions_k(legal_entity_inn);
