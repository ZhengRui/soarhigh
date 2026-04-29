-- Phase B migration — unified agent router observability.
-- Stores one router decision per /agent/turn request. Specialist turn
-- persistence remains in meeting_agent_* and statistics_agent_* until the
-- unified session model lands.

CREATE TABLE IF NOT EXISTS agent_router_decisions (
    session_id      TEXT NOT NULL,
    seq             INT  NOT NULL,
    user_id         UUID REFERENCES auth.users(id),
    user_message    TEXT NOT NULL,
    decision        JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_agent_router_decisions_session_created
    ON agent_router_decisions(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_agent_router_decisions_user_created
    ON agent_router_decisions(user_id, created_at);

ALTER TABLE agent_router_decisions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_router_decisions_owner ON agent_router_decisions;
CREATE POLICY agent_router_decisions_owner ON agent_router_decisions
    FOR ALL USING (user_id = auth.uid());
