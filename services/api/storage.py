"""Reject new storage-heavy work before disk exhaustion; never block CUT."""
import os
import shutil


def require_storage(path):
    minimum = int(os.getenv("CLAPPY_MIN_FREE_BYTES", "0"))
    if minimum < 0:
        raise ValueError("Storage reserve cannot be negative")
    if shutil.disk_usage(path).free < minimum:
        raise ValueError("Demo storage reserve reached. Existing recordings and CUT remain available.")
