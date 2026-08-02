-- Link one durable public WxPost to its private authoring workspace.
--
-- The workspace Draft remains the editorial authority. These fields record
-- exactly which saved Draft publication bundle produced the currently ready
-- public revision, so freshness is derived rather than duplicated in the
-- filesystem manifest.

ALTER TABLE public.wxposts
    ADD COLUMN source_workspace_id TEXT,
    ADD COLUMN source_draft_version INTEGER,
    ADD COLUMN source_draft_sha256 TEXT;

ALTER TABLE public.wxposts
    ADD CONSTRAINT wxposts_source_workspace_not_blank CHECK (
        source_workspace_id IS NULL
        OR source_workspace_id ~ '[^[:space:]]'
    ),
    ADD CONSTRAINT wxposts_source_draft_version_positive CHECK (
        source_draft_version IS NULL
        OR source_draft_version >= 1
    ),
    ADD CONSTRAINT wxposts_source_draft_sha256_valid CHECK (
        source_draft_sha256 IS NULL
        OR source_draft_sha256 ~ '^[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT wxposts_source_draft_fields_complete CHECK (
        (source_workspace_id IS NULL
         AND source_draft_version IS NULL
         AND source_draft_sha256 IS NULL)
        OR
        (source_workspace_id IS NOT NULL
         AND source_draft_version IS NOT NULL
         AND source_draft_sha256 IS NOT NULL)
    );

CREATE UNIQUE INDEX wxposts_source_workspace_id_idx
    ON public.wxposts (source_workspace_id)
    WHERE source_workspace_id IS NOT NULL;
