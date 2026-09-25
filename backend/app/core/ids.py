"""Time-ordered UUIDs (RFC 9562 UUIDv7) so primary-key indexes stay compact and insert-friendly."""

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76  # version
    value |= ((rand >> 68) & 0x0FFF) << 64  # rand_a
    value |= 0b10 << 62  # variant
    value |= rand & 0x3FFF_FFFF_FFFF_FFFF  # rand_b
    return uuid.UUID(int=value)
