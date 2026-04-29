"""Compatibility shim for `app.agents.meeting.history`."""

import sys

from app.agents.meeting import history as _history_module

sys.modules[__name__] = _history_module
