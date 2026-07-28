-- Tighten WXPost visibility and give abandoned direct uploads an explicit,
-- retryable lifecycle state.

ALTER TABLE public.wxposts
    ALTER COLUMN status SET DEFAULT 'assembling';

-- Preserve privacy if an older caller produced the previously-valid
-- ready/private combination.
UPDATE public.wxposts
SET status = 'assembling'
WHERE status = 'ready'
  AND is_public = FALSE;

ALTER TABLE public.wxposts
    DROP CONSTRAINT wxposts_public_ready_valid,
    ADD CONSTRAINT wxposts_visibility_matches_status CHECK (
        is_public = (status = 'ready')
    );

ALTER TABLE public.wxpost_assets
    ADD COLUMN abandoned_at TIMESTAMPTZ,
    DROP CONSTRAINT wxpost_assets_status_valid,
    ADD CONSTRAINT wxpost_assets_status_valid
        CHECK (status IN ('pending', 'ready', 'failed', 'abandoned')),
    ADD CONSTRAINT wxpost_assets_kind_mime_valid CHECK (
        (
            kind = 'image'
            AND mime_type IN (
                'image/jpeg',
                'image/png',
                'image/webp',
                'image/gif'
            )
        )
        OR (
            kind = 'video'
            AND mime_type IN (
                'video/mp4',
                'video/quicktime',
                'video/webm'
            )
        )
    ),
    ADD CONSTRAINT wxpost_assets_abandoned_timestamp_valid CHECK (
        (status = 'abandoned') = (abandoned_at IS NOT NULL)
    );
