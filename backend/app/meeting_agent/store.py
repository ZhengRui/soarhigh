"""Compatibility shim for `app.agents.meeting.store`."""

import sys

from app.agents.meeting import store as _store_module

sys.modules[__name__] = _store_module
