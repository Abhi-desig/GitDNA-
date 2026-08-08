"""Deterministic randomness.

Every random choice in the pipeline must come from here, so that a username
always produces byte-identical artwork. random.Random uses Mersenne Twister,
which Python guarantees is reproducible across versions for a given seed.
"""

from __future__ import annotations

import hashlib
import random


def seed_for(name: str) -> int:
    digest = hashlib.sha256(name.lower().encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def rng_for(name: str) -> random.Random:
    return random.Random(seed_for(name))
