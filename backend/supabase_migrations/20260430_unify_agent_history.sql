-- Unify history_cursor onto agent_turns.
-- Specialist sessions/turns tables are retired: meeting and statistics agents
-- now read and write conversation history through agent_turns directly. This
-- closes the cross-specialist continuity gap (a "rui呢" follow-up after a stats
-- turn now reaches the meeting agent with the prior context in scope).

ALTER TABLE agent_turns
    ADD COLUMN IF NOT EXISTS history_cursor JSONB;

DROP TABLE IF EXISTS meeting_agent_turns;
DROP TABLE IF EXISTS meeting_agent_sessions;
DROP TABLE IF EXISTS statistics_agent_turns;
DROP TABLE IF EXISTS statistics_agent_sessions;
