"""Compatibility shim for `app.agents.statistics.tools`."""

import sys

from app.agents.statistics import tools as _tools_module

sys.modules[__name__] = _tools_module
