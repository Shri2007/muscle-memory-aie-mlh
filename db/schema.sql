-- Tiger Data (Postgres + TimescaleDB + pgvector). factory/store.py writes; factory/api.py reads.
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS prs (
  id          serial PRIMARY KEY,
  agent       text NOT NULL,
  ticket      text NOT NULL,
  created_at  timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hunks (
  id          serial PRIMARY KEY,
  pr_id       int REFERENCES prs(id),
  file        text NOT NULL,
  kind        text NOT NULL,          -- swallowed_exception | restating_comment | redundant_guard | debug_print
  content     text NOT NULL,
  embedding   vector(768)
);

CREATE TABLE IF NOT EXISTS rules (
  id            text PRIMARY KEY,     -- mm-<kind>-v<version>
  kind          text NOT NULL,
  verdict       text NOT NULL CHECK (verdict IN ('keep','cut')),
  pattern_regex text NOT NULL,
  message       text NOT NULL,
  support       int  NOT NULL,
  version       int  NOT NULL,
  active        bool NOT NULL DEFAULT true,
  created_at    timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS decisions (
  time        timestamptz NOT NULL DEFAULT now(),
  hunk_id     int,
  tier        text NOT NULL CHECK (tier IN ('reflex','jev','gemini')),
  verdict     text NOT NULL CHECK (verdict IN ('keep','cut')),
  rule_id     text,
  latency_ms  real NOT NULL,
  tokens      int  NOT NULL DEFAULT 0,
  cost_usd    real NOT NULL DEFAULT 0,
  correct     bool,                   -- cut: tests still pass. keep: true if cutting broke tests. null = unverifiable
  safe        bool,                   -- did the fix keep public tests green and holdout no worse
  spot_check  bool NOT NULL DEFAULT false,
  reason      text
);
SELECT create_hypertable('decisions', by_range('time'), if_not_exists => true);

CREATE MATERIALIZED VIEW IF NOT EXISTS decisions_10s
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('10 seconds', time) AS bucket,
       tier,
       count(*)              AS n,
       avg(latency_ms)       AS avg_latency_ms,
       sum(tokens)           AS tokens,
       sum(cost_usd)         AS cost_usd,
       avg(correct::int)     AS accuracy
FROM decisions
GROUP BY bucket, tier
WITH NO DATA;

SELECT add_continuous_aggregate_policy('decisions_10s',
  start_offset => INTERVAL '1 hour', end_offset => INTERVAL '10 seconds',
  schedule_interval => INTERVAL '10 seconds', if_not_exists => true);

ALTER TABLE decisions SET (timescaledb.compress, timescaledb.compress_segmentby = 'tier');
SELECT add_compression_policy('decisions', INTERVAL '10 minutes', if_not_exists => true);
