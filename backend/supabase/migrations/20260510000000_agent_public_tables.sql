-- Public Agent conversation history and rate limiting.
--
-- These tables are intentionally separate from agent_sessions / agent_turns.
-- Member Agent history remains owned by auth.users.id; Public Agent history is
-- owned by (channel, visitor_key), e.g. (miniapp, wxid) or future
-- (web, server-issued visitor id).

CREATE TABLE IF NOT EXISTS agent_sessions_public (
    session_id   TEXT PRIMARY KEY,
    channel      TEXT NOT NULL CHECK (channel IN ('miniapp', 'web')),
    visitor_key  TEXT NOT NULL,
    tail_seq     INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_turns_public (
    session_id      TEXT NOT NULL REFERENCES agent_sessions_public(session_id) ON DELETE CASCADE,
    seq             INT NOT NULL,
    agent_kind      TEXT NOT NULL DEFAULT 'general',
    user_message    TEXT NOT NULL,
    assistant_text  TEXT,
    tool_trace      JSONB NOT NULL DEFAULT '[]'::jsonb,
    history_cursor  JSONB,
    domain_payload  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_public_visitor_created
    ON agent_sessions_public(channel, visitor_key, created_at);

CREATE INDEX IF NOT EXISTS idx_agent_turns_public_session_created
    ON agent_turns_public(session_id, created_at);

ALTER TABLE agent_sessions_public ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_turns_public    ENABLE ROW LEVEL SECURITY;

-- Public Agent endpoints use the backend service-role client and enforce
-- (channel, visitor_key) ownership in application code. Do not add anonymous
-- client policies here.

CREATE TABLE IF NOT EXISTS agent_rate_limits_public (
    key          TEXT NOT NULL,
    bucket       TEXT NOT NULL CHECK (bucket IN ('minute', 'day')),
    window_start TIMESTAMPTZ NOT NULL,
    count        INT NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (key, bucket, window_start)
);

ALTER TABLE agent_rate_limits_public ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION increment_agent_rate_limit_public(
    p_key TEXT,
    p_bucket TEXT,
    p_window_start TIMESTAMPTZ,
    p_limit INT
)
RETURNS TABLE(allowed BOOLEAN, current_count INT, limit_value INT)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_count INT;
BEGIN
    INSERT INTO agent_rate_limits_public(key, bucket, window_start, count, updated_at)
    VALUES (p_key, p_bucket, p_window_start, 1, NOW())
    ON CONFLICT (key, bucket, window_start)
    DO UPDATE SET
        count = agent_rate_limits_public.count + 1,
        updated_at = NOW()
    RETURNING count INTO v_count;

    RETURN QUERY SELECT (v_count <= p_limit), v_count, p_limit;
END;
$$;
