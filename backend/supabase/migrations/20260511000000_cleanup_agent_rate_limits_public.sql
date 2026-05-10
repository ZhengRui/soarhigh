-- Clean up expired Public Agent rate-limit buckets.
--
-- The rate-limit table stores minute/day counters only. Buckets older than
-- two days are no longer useful for enforcement or analytics, so keep this
-- cleanup inside Postgres instead of using an external workflow.

CREATE EXTENSION IF NOT EXISTS pg_cron;

CREATE OR REPLACE FUNCTION public.cleanup_agent_rate_limits_public()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_deleted INTEGER;
BEGIN
    DELETE FROM public.agent_rate_limits_public
    WHERE window_start < NOW() - INTERVAL '2 days';

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$$;

REVOKE ALL ON FUNCTION public.cleanup_agent_rate_limits_public()
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.cleanup_agent_rate_limits_public()
    TO service_role;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM cron.job
        WHERE jobname = 'cleanup-agent-rate-limits-public'
    ) THEN
        PERFORM cron.unschedule('cleanup-agent-rate-limits-public');
    END IF;
END;
$$;

SELECT cron.schedule(
    'cleanup-agent-rate-limits-public',
    '30 18 * * *',
    $$SELECT public.cleanup_agent_rate_limits_public();$$
);
