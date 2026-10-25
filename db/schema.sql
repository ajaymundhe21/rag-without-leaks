-- One row per chunk. Permissions live on the row, so the search can filter inside the query.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
  id          bigserial,
  tenant_id   int         NOT NULL,             -- which company
  readers     text[]      NOT NULL,             -- which groups can open this chunk (copied from the folder)
  doc_id      text        NOT NULL,             -- find all chunks of a document when it changes
  page        int         NOT NULL,             -- link the answer to the page
  text        text        NOT NULL,
  embedding   vector(256) NOT NULL,             -- WordLlama, 256 numbers
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,  -- word search
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id)
) PARTITION BY HASH (tenant_id);

-- Split by tenant for speed: one company's search opens one part.
-- fillfactor 70 leaves room in each page, so a permission update can rewrite a row in place.
CREATE TABLE IF NOT EXISTS chunks_p0 PARTITION OF chunks FOR VALUES WITH (MODULUS 4, REMAINDER 0) WITH (fillfactor = 70);
CREATE TABLE IF NOT EXISTS chunks_p1 PARTITION OF chunks FOR VALUES WITH (MODULUS 4, REMAINDER 1) WITH (fillfactor = 70);
CREATE TABLE IF NOT EXISTS chunks_p2 PARTITION OF chunks FOR VALUES WITH (MODULUS 4, REMAINDER 2) WITH (fillfactor = 70);
CREATE TABLE IF NOT EXISTS chunks_p3 PARTITION OF chunks FOR VALUES WITH (MODULUS 4, REMAINDER 3) WITH (fillfactor = 70);

CREATE INDEX IF NOT EXISTS chunks_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv  ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_doc  ON chunks (tenant_id, doc_id);
-- No index on readers, on purpose: the vector search does not use it, and it stops in-place updates,
-- so a permission change on 10,000 of 200,000 chunks took 13.1 s with it and 8.2 s without (benchmarks/m7).

-- Isolation between companies is a rule on the table, not a WHERE the app might forget.
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_only ON chunks;
CREATE POLICY tenant_only ON chunks
  USING      (tenant_id = current_setting('app.tenant', true)::int)
  WITH CHECK (tenant_id = current_setting('app.tenant', true)::int);
-- If app.tenant is not set, the setting is NULL and no row matches: it fails closed.

-- How many chunks each group can open. Small groups skip the vector index (it returns too few rows).
CREATE TABLE IF NOT EXISTS group_sizes (
  tenant_id int  NOT NULL,
  grp       text NOT NULL,
  n         int  NOT NULL,
  PRIMARY KEY (tenant_id, grp)
);

-- Who asked, which company, which chunks went out, and when. The question text is not stored.
CREATE TABLE IF NOT EXISTS audit_log (
  at        timestamptz NOT NULL DEFAULT now(),
  tenant_id int         NOT NULL,
  user_id   text        NOT NULL,
  groups    text[]      NOT NULL,
  chunk_ids bigint[]    NOT NULL
);

-- The app connects as this role. It is not a superuser, so row level security applies to it.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') THEN
    CREATE ROLE app LOGIN PASSWORD 'app';
  END IF;
END $$;
GRANT SELECT, INSERT, UPDATE, DELETE ON chunks, group_sizes TO app;
GRANT INSERT, SELECT ON audit_log TO app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app;
