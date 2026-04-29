-- Phase C migration — unified agent conversation envelope.
-- Specialist stores remain in meeting_agent_* and statistics_agent_* for model
-- history and meeting revert. These tables record the top-level /agent/turn
-- stream so one user-facing session can contain router-only, meeting, and
-- statistics turns.

CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id   TEXT PRIMARY KEY,
    user_id      UUID REFERENCES auth.users(id),
    tail_seq     INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_turns (
    session_id       TEXT NOT NULL REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    seq              INT  NOT NULL,
    agent_kind       TEXT NOT NULL,
    route            TEXT NOT NULL,
    user_message     TEXT NOT NULL,
    assistant_text   TEXT,
    tool_trace       JSONB NOT NULL DEFAULT '[]'::jsonb,
    router_decision  JSONB NOT NULL,
    specialist_seq   INT,
    agenda_before    JSONB,
    agenda_after     JSONB,
    domain_payload   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_agent_turns_session_created
    ON agent_turns(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_agent_turns_session_kind_created
    ON agent_turns(session_id, agent_kind, created_at);

ALTER TABLE agent_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_turns    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_sessions_owner ON agent_sessions;
CREATE POLICY agent_sessions_owner ON agent_sessions
    FOR ALL USING (user_id = auth.uid());

DROP POLICY IF EXISTS agent_turns_owner ON agent_turns;
CREATE POLICY agent_turns_owner ON agent_turns
    FOR ALL USING (
        session_id IN (
            SELECT session_id FROM agent_sessions WHERE user_id = auth.uid()
        )
    );
