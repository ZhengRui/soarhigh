from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from typing import Iterator


@contextmanager
def serialize_controller_database_initialization(
    state_directory: Path,
) -> Iterator[None]:
    """Serialize schema setup without creating a separate lock file."""

    descriptor = os.open(state_directory, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
