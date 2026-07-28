-- Record OSS-internal meeting image imports without pretending that Hermes
-- uploaded or hashed the source bytes.

ALTER TABLE public.wxpost_assets
    ALTER COLUMN content_sha256 DROP NOT NULL,
    ALTER COLUMN content_md5 DROP NOT NULL,
    DROP CONSTRAINT wxpost_assets_sha256_valid,
    DROP CONSTRAINT wxpost_assets_md5_not_blank,
    DROP CONSTRAINT wxpost_assets_source_type_valid,
    ADD CONSTRAINT wxpost_assets_source_type_valid
        CHECK (source_type IN ('feishu', 'workspace', 'meeting')),
    ADD CONSTRAINT wxpost_assets_source_hashes_valid CHECK (
        (
            source_type IN ('feishu', 'workspace')
            AND content_sha256 IS NOT NULL
            AND content_sha256 ~ '^[0-9a-f]{64}$'
            AND content_md5 IS NOT NULL
            AND content_md5 ~ '[^[:space:]]'
        )
        OR (
            source_type = 'meeting'
            AND content_sha256 IS NULL
            AND content_md5 IS NULL
        )
    );
