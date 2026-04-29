"""Compatibility shim for `app.agents.statistics.store`."""

import sys

from app.agents.statistics import store as _store_module

sys.modules[__name__] = _store_module
