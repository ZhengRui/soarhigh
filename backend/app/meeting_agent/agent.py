"""Compatibility shim for `app.agents.meeting.agent`."""

import sys

from app.agents.meeting import agent as _agent_module

sys.modules[__name__] = _agent_module
