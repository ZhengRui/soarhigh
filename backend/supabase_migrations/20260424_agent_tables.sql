-- Phase 3 migration — run this in the Supabase SQL editor against your project.
-- Creates the agent_sessions and agent_turns scratch tables plus row-level
-- security. Idempotent via IF NOT EXISTS so you can re-run it safely.

CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id   TEXT PRIMARY KEY,
    user_id      UUID REFERENCES auth.users(id),
    tail_seq     INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_turns (
    session_id      TEXT NOT NULL REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    seq             INT  NOT NULL,
    user_message    TEXT NOT NULL,
    assistant_text  TEXT,
    tool_trace      JSONB,
    agenda_before   JSONB NOT NULL,
    agenda_after    JSONB NOT NULL,
    history_cursor  JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_agent_turns_session_created
    ON agent_turns(session_id, created_at);

ALTER TABLE agent_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_turns    ENABLE ROW LEVEL SECURITY;

-- Drop-and-recreate the policies so the file is re-runnable without errors
-- even if the policies already exist from a previous run.
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
