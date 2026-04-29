"""Compatibility shim for `app.agents.meeting.normalize`."""

import sys

from app.agents.meeting import normalize as _normalize_module

sys.modules[__name__] = _normalize_module
