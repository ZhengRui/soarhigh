-- Phase 2 migration — statistics agent persistence.
-- Mirrors meeting_agent_sessions / meeting_agent_turns but without the
-- agenda_before / agenda_after columns (stats is read-only). Phase 3
-- will collapse all per-agent tables into a unified `agent_turns`
-- envelope; for Phase 2 they stay physically separate so the statistics
-- agent ships without touching the meeting agent's persistence layer.

CREATE TABLE IF NOT EXISTS statistics_agent_sessions (
    session_id   TEXT PRIMARY KEY,
    user_id      UUID REFERENCES auth.users(id),
    tail_seq     INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS statistics_agent_turns (
    session_id      TEXT NOT NULL REFERENCES statistics_agent_sessions(session_id) ON DELETE CASCADE,
    seq             INT  NOT NULL,
    user_message    TEXT NOT NULL,
    assistant_text  TEXT,
    tool_trace      JSONB,
    history_cursor  JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_statistics_agent_turns_session_created
    ON statistics_agent_turns(session_id, created_at);

ALTER TABLE statistics_agent_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE statistics_agent_turns    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS statistics_agent_sessions_owner ON statistics_agent_sessions;
CREATE POLICY statistics_agent_sessions_owner ON statistics_agent_sessions
    FOR ALL USING (user_id = auth.uid());

DROP POLICY IF EXISTS statistics_agent_turns_owner ON statistics_agent_turns;
CREATE POLICY statistics_agent_turns_owner ON statistics_agent_turns
    FOR ALL USING (
        session_id IN (
            SELECT session_id FROM statistics_agent_sessions WHERE user_id = auth.uid()
        )
    );
