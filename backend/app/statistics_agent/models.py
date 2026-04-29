"""Compatibility shim for `app.agents.statistics.models`."""

import sys

from app.agents.statistics import models as _models_module

sys.modules[__name__] = _models_module
