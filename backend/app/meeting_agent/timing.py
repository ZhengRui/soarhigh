"""Compatibility shim for `app.agents.meeting.timing`."""

import sys

from app.agents.meeting import timing as _timing_module

sys.modules[__name__] = _timing_module
