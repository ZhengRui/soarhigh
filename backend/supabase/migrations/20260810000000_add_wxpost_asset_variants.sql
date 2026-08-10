-- Persist deterministic platform renditions as children of immutable Public
-- Revision assets. External OSS objects are deleted by the Backend before the
-- parent rows are removed; the foreign key only owns database cleanup.

CREATE TABLE public.wxpost_asset_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL
        REFERENCES public.wxpost_assets(id) ON DELETE CASCADE,
    profile TEXT NOT NULL
        CONSTRAINT wxpost_asset_variants_profile_valid
        CHECK (profile IN ('wechat-body-v1')),
    status TEXT NOT NULL DEFAULT 'pending'
        CONSTRAINT wxpost_asset_variants_status_valid
        CHECK (status IN ('pending', 'ready', 'failed')),
    object_key TEXT NOT NULL UNIQUE
        CONSTRAINT wxpost_asset_variants_object_key_not_blank
        CHECK (object_key ~ '[^[:space:]]'),
    mime_type TEXT NOT NULL
        CONSTRAINT wxpost_asset_variants_mime_valid
        CHECK (mime_type IN ('image/jpeg', 'image/png')),
    size_bytes BIGINT NOT NULL
        CONSTRAINT wxpost_asset_variants_size_positive
        CHECK (size_bytes > 0),
    content_sha256 TEXT NOT NULL
        CONSTRAINT wxpost_asset_variants_sha256_valid
        CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    etag TEXT,
    ready_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT wxpost_asset_variants_asset_profile_unique
        UNIQUE (asset_id, profile),
    CONSTRAINT wxpost_asset_variants_ready_fields_valid CHECK (
        status <> 'ready'
        OR (
            ready_at IS NOT NULL
            AND COALESCE(etag ~ '[^[:space:]]', FALSE)
        )
    )
);

CREATE INDEX wxpost_asset_variants_asset_id_idx
    ON public.wxpost_asset_variants (asset_id);

ALTER TABLE public.wxpost_asset_variants ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.wxpost_asset_variants
    FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.wxpost_asset_variants TO service_role;
