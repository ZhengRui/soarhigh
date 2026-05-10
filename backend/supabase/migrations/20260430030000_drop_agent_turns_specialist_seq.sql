-- Drop the unused specialist_seq column from agent_turns.
-- Originally reserved for cross-row router→specialist references, but the
-- final architecture writes a single self-contained row per user turn
-- (router_decision JSONB carries the routing context inline). The column
-- has always been NULL in production.

ALTER TABLE agent_turns DROP COLUMN IF EXISTS specialist_seq;
