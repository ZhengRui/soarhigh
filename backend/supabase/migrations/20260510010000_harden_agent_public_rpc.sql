-- Harden Public Agent rate-limit RPC permissions.
--
-- The backend calls this function with the service-role Supabase client.
-- Browser, Mini App, anon, and authenticated clients should not be able to
-- invoke it directly.

ALTER FUNCTION public.increment_agent_rate_limit_public(TEXT, TEXT, TIMESTAMPTZ, INT)
    SET search_path = public;

REVOKE ALL ON FUNCTION public.increment_agent_rate_limit_public(TEXT, TEXT, TIMESTAMPTZ, INT)
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.increment_agent_rate_limit_public(TEXT, TEXT, TIMESTAMPTZ, INT)
    TO service_role;
