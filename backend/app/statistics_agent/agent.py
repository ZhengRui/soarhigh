"""Compatibility shim for `app.agents.statistics.agent`."""

import sys

from app.agents.statistics import agent as _agent_module

sys.modules[__name__] = _agent_module
