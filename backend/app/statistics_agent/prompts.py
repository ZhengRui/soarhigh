"""Compatibility shim for `app.agents.statistics.prompts`."""

import sys

from app.agents.statistics import prompts as _prompts_module

sys.modules[__name__] = _prompts_module
