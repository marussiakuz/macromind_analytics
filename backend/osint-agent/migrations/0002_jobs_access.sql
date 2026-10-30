-- Knowledge base schema v0002 (Task2 RAG §5, §10.1).
-- Jobs, snapshots, report versions, retrieval log. Additive only.

CREATE TABLE IF NOT EXISTS source_snapshots (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES documents(id),
  published_at TIMESTAMPTZ,
  retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_at TIMESTAMPTZ,
  content_hash TEXT NOT NULL,
  storage_path TEXT,
  size_bytes BIGINT,
  mime_type TEXT,
  coverage TEXT,
  error TEXT,
  extraction_version TEXT,
  parse_status TEXT NOT NULL DEFAULT 'pending', -- pending | ok | ocr_required | failed | empty
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_snap_doc ON source_snapshots(document_id);

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS snapshot_id UUID REFERENCES source_snapshots(id),
  ADD COLUMN IF NOT EXISTS chunk_index INT,
  ADD COLUMN IF NOT EXISTS heading TEXT,
  ADD COLUMN IF NOT EXISTS page INT,
  ADD COLUMN IF NOT EXISTS start_offset INT,
  ADD COLUMN IF NOT EXISTS end_offset INT,
  ADD COLUMN IF NOT EXISTS content_hash TEXT,
  ADD COLUMN IF NOT EXISTS embedding_model TEXT,
  ADD COLUMN IF NOT EXISTS embedding_revision TEXT,
  ADD COLUMN IF NOT EXISTS preprocessing_version TEXT,
  ADD COLUMN IF NOT EXISTS profile_id TEXT;

-- embedding uniqueness: same text + model + revision + preprocess within a document
CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_embed_key
  ON chunks (document_id, content_hash, embedding_model, embedding_revision, preprocessing_version)
  WHERE content_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  job_type TEXT NOT NULL,
  run_id UUID REFERENCES research_runs(id),
  stage TEXT NOT NULL DEFAULT 'collecting',
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 2,
  lease_owner TEXT,
  lease_expires_at TIMESTAMPTZ,
  fencing_token BIGINT NOT NULL DEFAULT 1,
  deadline_at TIMESTAMPTZ,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  result JSONB,
  error TEXT,
  error_kind TEXT, -- source | job | auth | budget
  retry_key TEXT,
  cancel_requested BOOLEAN NOT NULL DEFAULT false,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_retry_key ON jobs(retry_key) WHERE retry_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status) WHERE status IN ('queued','running','waiting_for_input');
CREATE INDEX IF NOT EXISTS idx_jobs_lease ON jobs(lease_expires_at) WHERE status = 'running';

CREATE TABLE IF NOT EXISTS retrieval_runs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  question TEXT NOT NULL,
  filters JSONB NOT NULL DEFAULT '{}'::jsonb,
  mode TEXT NOT NULL DEFAULT 'hybrid', -- exact | text | vector | hybrid
  index_profile TEXT,
  embedding_model TEXT,
  embedding_revision TEXT,
  candidates JSONB NOT NULL DEFAULT '[]'::jsonb,
  selected JSONB NOT NULL DEFAULT '[]'::jsonb,
  scores JSONB NOT NULL DEFAULT '{}'::jsonb,
  limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
  workspace_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report_versions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  study_id TEXT NOT NULL,
  report_version INT NOT NULL,
  body_json JSONB NOT NULL,
  evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  calculation_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  model_uri TEXT,
  instruction_version TEXT,
  validator_version TEXT,
  content_hash TEXT NOT NULL,
  workspace_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (study_id, report_version)
);

CREATE TABLE IF NOT EXISTS provider_calls (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  provider TEXT NOT NULL,
  operation TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  attempt INT NOT NULL DEFAULT 1,
  status TEXT NOT NULL,
  usage JSONB NOT NULL DEFAULT '{}'::jsonb,
  cost_rub NUMERIC,
  cost_is_estimated BOOLEAN DEFAULT true,
  request_id TEXT,
  run_id UUID REFERENCES research_runs(id),
  note TEXT,
  at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Access control: every user object is scoped
ALTER TABLE documents ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS workspace_id TEXT;
CREATE INDEX IF NOT EXISTS idx_documents_ws ON documents(workspace_id);
CREATE INDEX IF NOT EXISTS idx_evidence_ws ON evidence(workspace_id);
