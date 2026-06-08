"""Convert HackRF int8 interleaved IQ bytes to complex samples."""

from __future__ import annotations

import numpy as np


class IQConverter:
    @staticmethod
    def from_bytes(data: bytes) -> np.ndarray:
        raw = np.frombuffer(data, dtype=np.int8)
        if len(raw) < 2:
            return np.array([], dtype=np.complex64)
        if len(raw) % 2:
            raw = raw[:-1]
        i = raw[0::2].astype(np.float32)
        q = raw[1::2].astype(np.float32)
        return i + 1j * q
