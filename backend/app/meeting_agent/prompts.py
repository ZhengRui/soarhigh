"""Compatibility shim for `app.agents.meeting.prompts`."""

import sys

from app.agents.meeting import prompts as _prompts_module

sys.modules[__name__] = _prompts_module
