"""Repeatable building random streams for the existing stochastic generators."""

from contextlib import contextmanager
from functools import wraps
import hashlib
import json
import random
import threading

import numpy as np


_RANDOM_STATE_LOCK = threading.RLock()


def building_seed(seed, features, phase):
    """Derive a stable seed from scenario seed, building identity and phase."""
    if seed is None:
        return None
    identity = [int(seed), int(features.get("original_bldg_id", features["id"])),
                features.get("mixed_role", ""), phase]
    digest = hashlib.sha256(json.dumps(identity).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little")


def derive_seed(seed, *labels):
    """Derive a stable child seed from a parent seed and labels; None stays None."""
    if seed is None:
        return None
    digest = hashlib.sha256(json.dumps([int(seed), *labels]).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little")


@contextmanager
def seeded_random_state(seed):
    """Seed legacy Python/NumPy APIs temporarily; serialize seeded thread access."""
    if seed is None:
        yield
        return
    with _RANDOM_STATE_LOCK:
        python_state = random.getstate()
        numpy_state = np.random.get_state()
        random.seed(seed)
        np.random.seed(seed)
        try:
            yield
        finally:
            random.setstate(python_state)
            np.random.set_state(numpy_state)


def seeded_demand_worker(function):
    """Apply the same per-building stream in process and thread workers."""
    @wraps(function)
    def worker(owner, building, *args, **kwargs):
        seed = owner.get("random_seed") if isinstance(owner, dict) else owner.random_seed
        with seeded_random_state(building_seed(seed, building["buildingFeatures"], "profiles")):
            return function(owner, building, *args, **kwargs)
    return worker
