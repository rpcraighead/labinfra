-- Agent Swarm Audit Database Schema
-- Auto-applied on first Postgres startup via docker-entrypoint-initdb.d

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Core event log: every task start/complete/fail, anomaly, and verdict
CREATE TABLE IF NOT EXISTS agent_events (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID NOT NULL DEFAULT uuid_generate_v4(),
    event_type      VARCHAR(64) NOT NULL,
    sender          VARCHAR(64) NOT NULL,
    task_id         UUID,
    intent_id       UUID,
    body            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_type ON agent_events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_sender ON agent_events (sender);
CREATE INDEX IF NOT EXISTS idx_events_task ON agent_events (task_id);
CREATE INDEX IF NOT EXISTS idx_events_intent ON agent_events (intent_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON agent_events (created_at DESC);

-- Gatekeeper audit: approval/rejection decisions
CREATE TABLE IF NOT EXISTS gatekeeper_decisions (
    id              BIGSERIAL PRIMARY KEY,
    decision_id     UUID NOT NULL DEFAULT uuid_generate_v4(),
    task_id         UUID NOT NULL,
    intent_id       UUID,
    operation       VARCHAR(128) NOT NULL,
    agent           VARCHAR(64) NOT NULL,
    decision        VARCHAR(16) NOT NULL,  -- 'approved', 'rejected', 'pending', 'timeout'
    decided_by      VARCHAR(128),
    decided_at      TIMESTAMPTZ,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gk_task ON gatekeeper_decisions (task_id);
CREATE INDEX IF NOT EXISTS idx_gk_decision ON gatekeeper_decisions (decision);

-- Judge verdicts
CREATE TABLE IF NOT EXISTS judge_verdicts (
    id              BIGSERIAL PRIMARY KEY,
    verdict_id      UUID NOT NULL DEFAULT uuid_generate_v4(),
    kind            VARCHAR(64) NOT NULL,
    decision        VARCHAR(32) NOT NULL,  -- 'halt', 'warn', 'quarantine', 'log'
    severity        VARCHAR(16) NOT NULL,
    reason          TEXT NOT NULL,
    recommended_action VARCHAR(64),
    llm_reasoning   TEXT,
    intent_id       UUID,
    body            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_verdicts_kind ON judge_verdicts (kind);
CREATE INDEX IF NOT EXISTS idx_verdicts_decision ON judge_verdicts (decision);
CREATE INDEX IF NOT EXISTS idx_verdicts_created ON judge_verdicts (created_at DESC);

-- Audit log table (used by N8N Gatekeeper audit-logger workflow)
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ,
    event_type      VARCHAR(64),
    agent           VARCHAR(64),
    task_id         VARCHAR(128),
    intent_id       VARCHAR(128),
    details         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_log (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log (created_at DESC);
