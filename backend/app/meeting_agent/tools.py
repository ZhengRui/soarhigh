"""Compatibility shim for `app.agents.meeting.tools`."""

import sys

from app.agents.meeting import tools as _tools_module

sys.modules[__name__] = _tools_module
