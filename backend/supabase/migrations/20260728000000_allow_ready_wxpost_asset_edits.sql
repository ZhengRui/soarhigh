-- A ready WXPost is a mutable public preview, not a locked publication.
-- Pending assets remain outside the rendered article until the application
-- references them from a later validated article revision.

DROP TRIGGER IF EXISTS wxpost_assets_parent_assembling
    ON public.wxpost_assets;

DROP FUNCTION IF EXISTS public.enforce_wxpost_asset_parent_assembling();
