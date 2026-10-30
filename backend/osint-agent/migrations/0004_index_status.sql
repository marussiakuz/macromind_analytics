-- Knowledge schema v0004 (Astra §6.3): document index lifecycle + job retry backoff.
-- Additive only.

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS index_status TEXT NOT NULL DEFAULT 'saved';
  -- saved | indexing | ready | error | cancelled

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_documents_index_status ON documents(index_status);
CREATE INDEX IF NOT EXISTS idx_jobs_next_attempt ON jobs(next_attempt_at)
  WHERE status = 'queued' AND next_attempt_at IS NOT NULL;
