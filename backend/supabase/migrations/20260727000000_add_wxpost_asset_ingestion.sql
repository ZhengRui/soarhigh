-- Add the private assembly lifecycle and article-owned media assets used by
-- Hermes before a WXPost becomes publicly visible.

ALTER TABLE public.wxposts
    ADD COLUMN status TEXT NOT NULL DEFAULT 'ready'
        CONSTRAINT wxposts_status_valid
        CHECK (status IN ('assembling', 'ready')),
    ADD COLUMN prepare_idempotency_key_hash TEXT,
    ADD COLUMN prepare_request_hash TEXT,
    ADD COLUMN finalize_request_hash TEXT;

ALTER TABLE public.wxposts
    ALTER COLUMN content DROP NOT NULL,
    ALTER COLUMN is_public SET DEFAULT FALSE;

ALTER TABLE public.wxposts
    ADD CONSTRAINT wxposts_ready_content_valid CHECK (
        status = 'assembling'
        OR COALESCE(content ~ '[^[:space:]]', FALSE)
    ),
    ADD CONSTRAINT wxposts_public_ready_valid CHECK (
        NOT is_public OR status = 'ready'
    ),
    ADD CONSTRAINT wxposts_prepare_hashes_valid CHECK (
        (
            prepare_idempotency_key_hash IS NULL
            AND prepare_request_hash IS NULL
        )
        OR (
            prepare_idempotency_key_hash ~ '^[0-9a-f]{64}$'
            AND prepare_request_hash ~ '^[0-9a-f]{64}$'
        )
    ),
    ADD CONSTRAINT wxposts_finalize_hash_valid CHECK (
        finalize_request_hash IS NULL
        OR finalize_request_hash ~ '^[0-9a-f]{64}$'
    );

DROP INDEX public.wxposts_public_created_at_idx;

CREATE INDEX wxposts_public_created_at_idx
    ON public.wxposts (created_at DESC)
    WHERE status = 'ready' AND is_public = TRUE;

CREATE UNIQUE INDEX wxposts_prepare_idempotency_key_hash_idx
    ON public.wxposts (prepare_idempotency_key_hash)
    WHERE prepare_idempotency_key_hash IS NOT NULL;

DROP POLICY wxposts_public_read ON public.wxposts;

CREATE POLICY wxposts_public_read
    ON public.wxposts
    FOR SELECT
    TO anon, authenticated
    USING (status = 'ready' AND is_public = TRUE);

CREATE TABLE public.wxpost_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wxpost_id UUID NOT NULL
        REFERENCES public.wxposts(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending'
        CONSTRAINT wxpost_assets_status_valid
        CHECK (status IN ('pending', 'ready', 'failed')),
    kind TEXT NOT NULL
        CONSTRAINT wxpost_assets_kind_valid
        CHECK (kind IN ('image', 'video')),
    object_key TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL
        CONSTRAINT wxpost_assets_filename_not_blank
        CHECK (original_filename ~ '[^[:space:]]'),
    mime_type TEXT NOT NULL
        CONSTRAINT wxpost_assets_mime_not_blank
        CHECK (mime_type ~ '[^[:space:]]'),
    size_bytes BIGINT NOT NULL
        CONSTRAINT wxpost_assets_size_positive
        CHECK (size_bytes > 0),
    content_sha256 TEXT NOT NULL
        CONSTRAINT wxpost_assets_sha256_valid
        CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    content_md5 TEXT NOT NULL
        CONSTRAINT wxpost_assets_md5_not_blank
        CHECK (content_md5 ~ '[^[:space:]]'),
    upload_idempotency_key_hash TEXT NOT NULL
        CONSTRAINT wxpost_assets_idempotency_key_hash_valid
        CHECK (upload_idempotency_key_hash ~ '^[0-9a-f]{64}$'),
    upload_request_hash TEXT NOT NULL
        CONSTRAINT wxpost_assets_request_hash_valid
        CHECK (upload_request_hash ~ '^[0-9a-f]{64}$'),
    source_type TEXT NOT NULL DEFAULT 'feishu'
        CONSTRAINT wxpost_assets_source_type_valid
        CHECK (source_type IN ('feishu', 'workspace')),
    source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        CONSTRAINT wxpost_assets_source_metadata_is_object
        CHECK (jsonb_typeof(source_metadata) = 'object'),
    etag TEXT,
    poster_object_key TEXT UNIQUE,
    poster_original_filename TEXT,
    poster_mime_type TEXT,
    poster_size_bytes BIGINT,
    poster_content_sha256 TEXT,
    poster_content_md5 TEXT,
    poster_etag TEXT,
    ready_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT wxpost_assets_object_key_owned CHECK (
        object_key = (
            'public/wxposts/'
            || wxpost_id::TEXT
            || '/assets/'
            || id::TEXT
            || '/original.'
            || CASE mime_type
                WHEN 'image/jpeg' THEN 'jpg'
                WHEN 'image/png' THEN 'png'
                WHEN 'image/webp' THEN 'webp'
                WHEN 'image/gif' THEN 'gif'
                WHEN 'video/mp4' THEN 'mp4'
                WHEN 'video/quicktime' THEN 'mov'
                WHEN 'video/webm' THEN 'webm'
                ELSE ''
            END
        )
    ),
    CONSTRAINT wxpost_assets_poster_fields_valid CHECK (
        (
            poster_object_key IS NULL
            AND poster_original_filename IS NULL
            AND poster_mime_type IS NULL
            AND poster_size_bytes IS NULL
            AND poster_content_sha256 IS NULL
            AND poster_content_md5 IS NULL
            AND poster_etag IS NULL
        )
        OR (
            kind = 'video'
            AND poster_object_key = (
                'public/wxposts/'
                || wxpost_id::TEXT
                || '/assets/'
                || id::TEXT
                || '/poster.jpg'
            )
            AND COALESCE(poster_original_filename ~ '[^[:space:]]', FALSE)
            AND poster_mime_type = 'image/jpeg'
            AND poster_size_bytes > 0
            AND poster_content_sha256 ~ '^[0-9a-f]{64}$'
            AND COALESCE(poster_content_md5 ~ '[^[:space:]]', FALSE)
        )
    ),
    CONSTRAINT wxpost_assets_ready_timestamp_valid CHECK (
        status <> 'ready'
        OR (
            ready_at IS NOT NULL
            AND COALESCE(etag ~ '[^[:space:]]', FALSE)
            AND (
                poster_object_key IS NULL
                OR COALESCE(poster_etag ~ '[^[:space:]]', FALSE)
            )
        )
    ),
    CONSTRAINT wxpost_assets_upload_idempotency_key
        UNIQUE (wxpost_id, upload_idempotency_key_hash)
);

CREATE INDEX wxpost_assets_wxpost_id_idx
    ON public.wxpost_assets (wxpost_id);

CREATE FUNCTION public.enforce_wxpost_asset_parent_assembling()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    parent_status TEXT;
BEGIN
    SELECT status
    INTO parent_status
    FROM public.wxposts
    WHERE id = NEW.wxpost_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'WXPost % does not exist', NEW.wxpost_id
            USING ERRCODE = '23503';
    END IF;

    IF parent_status <> 'assembling' THEN
        RAISE EXCEPTION 'WXPost % is not assembling', NEW.wxpost_id
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER wxpost_assets_parent_assembling
    BEFORE INSERT OR UPDATE OF status
    ON public.wxpost_assets
    FOR EACH ROW
    EXECUTE FUNCTION public.enforce_wxpost_asset_parent_assembling();

CREATE FUNCTION public.block_wxpost_finalize_with_pending_assets()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF (
        OLD.status = 'assembling'
        AND NEW.status = 'ready'
        AND EXISTS (
            SELECT 1
            FROM public.wxpost_assets
            WHERE wxpost_id = NEW.id
              AND status = 'pending'
        )
    ) THEN
        RAISE EXCEPTION 'WXPost % still has pending assets', NEW.id
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER wxposts_no_pending_assets_on_finalize
    BEFORE UPDATE OF status
    ON public.wxposts
    FOR EACH ROW
    EXECUTE FUNCTION public.block_wxpost_finalize_with_pending_assets();

ALTER TABLE public.wxpost_assets ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.wxpost_assets
    FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.wxpost_assets TO service_role;

REVOKE ALL ON FUNCTION public.enforce_wxpost_asset_parent_assembling()
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.block_wxpost_finalize_with_pending_assets()
    FROM PUBLIC;
