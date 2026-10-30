-- Weak signals + module bindings (Task2 §5, §11). Additive.

CREATE TABLE IF NOT EXISTS watchlists (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id TEXT,
  topic TEXT NOT NULL,
  products JSONB NOT NULL DEFAULT '[]'::jsonb,
  technologies JSONB NOT NULL DEFAULT '[]'::jsonb,
  companies JSONB NOT NULL DEFAULT '[]'::jsonb,
  queries JSONB NOT NULL DEFAULT '[]'::jsonb,
  geography JSONB NOT NULL DEFAULT '[]'::jsonb,
  budget_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  schedule_cron TEXT,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS signal_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id TEXT,
  watchlist_id UUID REFERENCES watchlists(id),
  event_type TEXT NOT NULL, -- publication | trial | product_launch | partnership | procurement | requirement_change
  subject TEXT NOT NULL,
  technology TEXT,
  company TEXT,
  geography TEXT,
  event_at DATE,
  published_at DATE,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source_document_id TEXT,
  source_evidence_id TEXT,
  reprint_cluster_id TEXT,
  independent_sources INT NOT NULL DEFAULT 1,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_signal_events_ws ON signal_events(workspace_id);
CREATE INDEX IF NOT EXISTS idx_signal_events_detected ON signal_events(detected_at);
CREATE INDEX IF NOT EXISTS idx_signal_events_cluster ON signal_events(reprint_cluster_id);

CREATE TABLE IF NOT EXISTS signal_hypotheses (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id TEXT,
  watchlist_id UUID REFERENCES watchlists(id),
  statement TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'unverified', -- unverified | supported | rejected | needs_more_data
  evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  event_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  window_start DATE,
  window_end DATE,
  baseline_start DATE,
  baseline_end DATE,
  limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
  alternatives JSONB NOT NULL DEFAULT '[]'::jsonb,
  questions JSONB NOT NULL DEFAULT '[]'::jsonb,
  coverage_limited BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- explicit reuse links between modules (§5: public docs shared via links)
CREATE TABLE IF NOT EXISTS research_bindings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id TEXT,
  project_ref TEXT,
  legal_entity_inn TEXT,
  product_ref TEXT,
  report_version_id UUID REFERENCES report_versions(id),
  analysis_version_id UUID REFERENCES analysis_versions_k(id),
  revision INT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bindings_inn ON research_bindings(legal_entity_inn);
