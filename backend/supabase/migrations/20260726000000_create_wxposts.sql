-- Persist WeChat article source documents independently from ordinary posts.
--
-- WXPosts have their own rendering, revision, and future WeChat draft
-- lifecycle. They intentionally do not belong to a SoarHigh member: member
-- authentication controls operations, while publisher identity is owned by
-- the configured WeChat Official Account.

CREATE TABLE public.wxposts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL
        CONSTRAINT wxposts_title_not_blank CHECK (title ~ '[^[:space:]]'),
    slug TEXT NOT NULL
        CONSTRAINT wxposts_slug_not_blank CHECK (slug ~ '[^[:space:]]'),
    content TEXT NOT NULL
        CONSTRAINT wxposts_content_not_blank CHECK (content ~ '[^[:space:]]'),
    is_public BOOLEAN NOT NULL DEFAULT TRUE,
    schema_version INTEGER NOT NULL DEFAULT 1
        CONSTRAINT wxposts_schema_version_v1 CHECK (schema_version = 1),
    article_type TEXT NOT NULL
        CONSTRAINT wxposts_article_type_valid CHECK (
            article_type IN (
                'meeting-recap',
                'member-story',
                'event-preview',
                'meeting-review',
                'action-guide',
                'custom'
            )
        ),
    custom_article_type TEXT,
    source_meeting_id UUID
        REFERENCES public.meetings(id) ON DELETE SET NULL,
    excerpt TEXT,
    byline TEXT,
    media_manifest JSONB NOT NULL DEFAULT '[]'::jsonb
        CONSTRAINT wxposts_media_manifest_is_array CHECK (
            jsonb_typeof(media_manifest) = 'array'
        ),
    cover_media_id TEXT,
    default_presentation JSONB NOT NULL
        CONSTRAINT wxposts_default_presentation_is_object CHECK (
            jsonb_typeof(default_presentation) = 'object'
        ),
    article_revision INTEGER NOT NULL DEFAULT 1
        CONSTRAINT wxposts_article_revision_positive CHECK (
            article_revision >= 1
        ),
    render_version INTEGER NOT NULL DEFAULT 1
        CONSTRAINT wxposts_render_version_v1 CHECK (render_version = 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT wxposts_slug_key UNIQUE (slug),
    CONSTRAINT wxposts_custom_article_type_valid CHECK (
        (
            article_type = 'custom'
            AND COALESCE(
                custom_article_type ~ '[^[:space:]]',
                FALSE
            )
        )
        OR (
            article_type <> 'custom'
            AND custom_article_type IS NULL
        )
    )
);

CREATE INDEX wxposts_public_created_at_idx
    ON public.wxposts (created_at DESC)
    WHERE is_public = TRUE;

CREATE INDEX wxposts_source_meeting_id_idx
    ON public.wxposts (source_meeting_id)
    WHERE source_meeting_id IS NOT NULL;

ALTER TABLE public.wxposts ENABLE ROW LEVEL SECURITY;

CREATE POLICY wxposts_public_read
    ON public.wxposts
    FOR SELECT
    TO anon, authenticated
    USING (is_public = TRUE);

REVOKE ALL ON TABLE public.wxposts FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.wxposts TO anon, authenticated;
GRANT ALL ON TABLE public.wxposts TO service_role;
