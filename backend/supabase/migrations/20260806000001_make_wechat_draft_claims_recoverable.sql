-- Distinguish a stale local operation from an ambiguous remote draft add.
-- A stale operation is safe to reclaim until the create request starts. Once
-- it starts, retry must recover the remote result instead of blindly adding.

ALTER TABLE public.wxpost_wechat_drafts
ADD COLUMN add_started_at TIMESTAMPTZ;

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
    IF current_row.state = 'creating'
       AND current_row.add_started_at IS NOT NULL
       AND current_row.wechat_media_id IS NULL THEN
        UPDATE public.wxpost_wechat_drafts SET
            state = 'uncertain',
            last_error = 'The previous WeChat draft creation result is uncertain.',
            updated_at = NOW()
        WHERE source_workspace_id = requested_workspace_id
        RETURNING * INTO current_row;
        RETURN jsonb_build_object('acquired', FALSE, 'reason', 'uncertain', 'row', to_jsonb(current_row));
    END IF;
    IF current_row.state = 'creating'
       AND current_row.updated_at > NOW() - INTERVAL '15 minutes' THEN
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
        add_started_at = NULL,
        last_error = NULL,
        updated_at = NOW()
    WHERE source_workspace_id = requested_workspace_id
    RETURNING * INTO current_row;

    RETURN jsonb_build_object('acquired', TRUE, 'reason', 'claimed', 'row', to_jsonb(current_row));
END;
$$;
