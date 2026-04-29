"""Compatibility shim for `app.agents.meeting.segment_ids`."""

import sys

from app.agents.meeting import segment_ids as _segment_ids_module

sys.modules[__name__] = _segment_ids_module
