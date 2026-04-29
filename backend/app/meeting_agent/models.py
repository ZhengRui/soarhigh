"""Compatibility shim for `app.agents.meeting.models`."""

import sys

from app.agents.meeting import models as _models_module

sys.modules[__name__] = _models_module
