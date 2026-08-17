"""Shared constants for bounded WeChat/public image renditions.

The deterministic renditions themselves are generated server-side by OSS
(``wxpost_oss_ops.generate_wechat_variant``) rather than decoded locally with
Pillow — the local Pillow renderer that used to live here
(``render_wechat_body_variant``) was retired once both the live publication
path (Task 3) and the WeChat reconciliation backfill (Task 8) switched to the
OSS ladder. These constants remain the single source of truth for the
target/hard-max byte budgets and the resize/quality ladder both the OSS ops
module and the WeChat draft assembly code (``wxpost_wechat.py``) rely on.
"""

from __future__ import annotations

WECHAT_BODY_PROFILE = "wechat-body-v1"
WECHAT_BODY_TARGET_BYTES = 900 * 1024
WECHAT_BODY_HARD_MAX_BYTES = 1024 * 1024 - 1
WECHAT_COVER_HARD_MAX_BYTES = 10 * 1024 * 1024

_MAX_EDGES = (1920, 1600, 1280, 1024, 800, 640)
_JPEG_QUALITIES = (90, 85, 80, 75, 70, 65)
