-- Official Account access tokens now live only in the fixed-egress VPS
-- gateway's process memory. Draft projection and idempotency state remain in
-- public.wxpost_wechat_drafts and are intentionally untouched.

DROP TABLE IF EXISTS public.wxpost_wechat_token_cache;
