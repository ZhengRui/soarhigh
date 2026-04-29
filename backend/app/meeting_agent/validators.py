"""Compatibility shim for `app.agents.meeting.validators`."""

import sys

from app.agents.meeting import validators as _validators_module

sys.modules[__name__] = _validators_module
