-- Drop agent_router_decisions.
-- The router decision is already persisted on agent_turns.router_decision
-- (JSONB) for every router-touched turn — both router-only paths
-- (clarify / direct_answer / handoff proposal) and specialist dispatches
-- (the decision rides along on the AgentTurnRequest). The separate
-- agent_router_decisions table was a duplicate write path with no
-- consumer; removing it keeps the unified envelope as the only place
-- decisions live.

DROP TABLE IF EXISTS agent_router_decisions;
