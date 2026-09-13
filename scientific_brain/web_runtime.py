from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .memory import ScientificMemory
from .persistence import SnapshotStore, snapshot_store_from_env


def require_cloud_store() -> SnapshotStore:
    store = snapshot_store_from_env()
    if store is None:
        raise RuntimeError(
            "This web operation requires durable storage. Set SCIBRAIN_STORAGE_BACKEND=supabase, "
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
    return store


@contextmanager
def temporary_memory():
    fd, path = tempfile.mkstemp(prefix="scientificbrain-", suffix=".db", dir=os.getenv("TMPDIR", "/tmp"))
    os.close(fd)
    memory = ScientificMemory(path)
    try:
        yield memory
    finally:
        memory.close()
        try:
            Path(path).unlink(missing_ok=True)
            for suffix in ("-wal", "-shm"):
                Path(path + suffix).unlink(missing_ok=True)
        except OSError:
            pass
