-- Persist the single configured Official Account token cache and one WeChat
-- draft projection per durable WxPost workspace. Editorial content remains in
-- the Saved Draft/Public Revision; these rows contain delivery state only.

CREATE TABLE public.wxpost_wechat_token_cache (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    access_token TEXT NOT NULL CHECK (access_token ~ '[^[:space:]]'),
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.wxpost_wechat_token_cache ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.wxpost_wechat_token_cache FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.wxpost_wechat_token_cache TO service_role;

CREATE TABLE public.wxpost_wechat_drafts (
    source_workspace_id TEXT PRIMARY KEY CHECK (source_workspace_id ~ '[^[:space:]]'),
    wxpost_id UUID,
    wechat_media_id TEXT UNIQUE,
    state TEXT NOT NULL DEFAULT 'idle'
        CHECK (state IN ('idle', 'creating', 'ready', 'uncertain')),
    source_public_revision INTEGER CHECK (source_public_revision IS NULL OR source_public_revision >= 1),
    presentation JSONB CHECK (presentation IS NULL OR jsonb_typeof(presentation) = 'object'),
    projection_sha256 TEXT CHECK (projection_sha256 IS NULL OR projection_sha256 ~ '^[0-9a-f]{64}$'),
    asset_mappings JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(asset_mappings) = 'object'),
    submitted_html_sha256 TEXT CHECK (submitted_html_sha256 IS NULL OR submitted_html_sha256 ~ '^[0-9a-f]{64}$'),
    readback_html_sha256 TEXT CHECK (readback_html_sha256 IS NULL OR readback_html_sha256 ~ '^[0-9a-f]{64}$'),
    readback_changed BOOLEAN,
    operation_id UUID,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.wxpost_wechat_drafts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.wxpost_wechat_drafts FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.wxpost_wechat_drafts TO service_role;

CREATE OR REPLACE FUNCTION public.claim_wxpost_wechat_draft(
    requested_workspace_id TEXT,
    requested_wxpost_id UUID,
    requested_revision INTEGER,
    requested_presentation JSONB,
    requested_projection_sha256 TEXT,
    requested_operation_id UUID
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    current_row public.wxpost_wechat_drafts%ROWTYPE;
BEGIN
    INSERT INTO public.wxpost_wechat_drafts (source_workspace_id)
    VALUES (requested_workspace_id)
    ON CONFLICT (source_workspace_id) DO NOTHING;

    SELECT * INTO current_row
    FROM public.wxpost_wechat_drafts
    WHERE source_workspace_id = requested_workspace_id
    FOR UPDATE;

    IF current_row.state = 'ready'
       AND current_row.projection_sha256 = requested_projection_sha256 THEN
        RETURN jsonb_build_object('acquired', FALSE, 'reason', 'unchanged', 'row', to_jsonb(current_row));
    END IF;
    IF current_row.state = 'creating' THEN
        RETURN jsonb_build_object('acquired', FALSE, 'reason', 'busy', 'row', to_jsonb(current_row));
    END IF;
    IF current_row.state = 'uncertain' THEN
        RETURN jsonb_build_object('acquired', FALSE, 'reason', 'uncertain', 'row', to_jsonb(current_row));
    END IF;

    UPDATE public.wxpost_wechat_drafts SET
        wxpost_id = requested_wxpost_id,
        state = 'creating',
        source_public_revision = requested_revision,
        presentation = requested_presentation,
        projection_sha256 = requested_projection_sha256,
        operation_id = requested_operation_id,
        last_error = NULL,
        updated_at = NOW()
    WHERE source_workspace_id = requested_workspace_id
    RETURNING * INTO current_row;

    RETURN jsonb_build_object('acquired', TRUE, 'reason', 'claimed', 'row', to_jsonb(current_row));
END;
$$;

REVOKE ALL ON FUNCTION public.claim_wxpost_wechat_draft(TEXT, UUID, INTEGER, JSONB, TEXT, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_wxpost_wechat_draft(TEXT, UUID, INTEGER, JSONB, TEXT, UUID) TO service_role;
