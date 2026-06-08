"""Mode S / ADS-B PPM demodulation from complex IQ samples.

1090 MHz Mode S uses Pulse Position Modulation (PPM) at 1 Mbps. Each bit
occupies 1 µs split into two 0.5 µs halves: a pulse in the first half encodes
bit 1, in the second half encodes bit 0. At 2 MHz sample rate each half-bit
is exactly one magnitude sample, so demodulation reduces to pairwise comparisons.

The 8 µs preamble is four fixed pulses used for correlation-based frame sync.
"""

from __future__ import annotations

from typing import List, Set

import numpy as np
import pyModeS as pms
from pyModeS.errors import InvalidHexError, InvalidLengthError

from aircraftx.config import (
    ALL_MODE_S_DF,
    DemodSettings,
    LONG_MSG_BITS,
    MIN_FRAME_SAMPLES,
    MIN_SHORT_FRAME_SAMPLES,
    PREFERRED_DF,
    PREAMBLE_LEN,
    PREAMBLE_SAMPLES,
    SHORT_MSG_BITS,
    SAMPLES_PER_BIT,
)


class ModeSDemodulator:
    """Detect Mode S preambles in IQ buffers and extract hex messages."""

    def __init__(self, settings: DemodSettings) -> None:
        self._settings = settings
        # Zero-mean preamble template improves correlation SNR vs a bipolar template.
        self._preamble_zm = PREAMBLE_SAMPLES - np.mean(PREAMBLE_SAMPLES)

    def demodulate(self, iq: np.ndarray) -> List[str]:
        if len(iq) < PREAMBLE_LEN + LONG_MSG_BITS * SAMPLES_PER_BIT:
            return []

        # Remove DC offset from the front-end; it otherwise biases magnitude.
        iq = iq - np.mean(iq)
        raw_mag = np.abs(iq).astype(np.float64)
        # Filter only for correlation; demod uses raw magnitude so moving-average
        # smoothing does not collapse preamble pulse/quiet ratios.
        corr_mag = self._filter_magnitude(raw_mag)

        peaks = self._find_preamble_peaks(corr_mag)
        if not peaks:
            return []

        messages: List[str] = []
        seen: Set[str] = set()
        for peak in peaks:
            messages.extend(self._try_decode_peak(raw_mag, peak, seen))
        return messages

    def overlap_tail(self, buffer: np.ndarray) -> np.ndarray:
        keep = PREAMBLE_LEN + LONG_MSG_BITS * SAMPLES_PER_BIT + MIN_FRAME_SAMPLES
        return buffer[-keep:]

    def _filter_magnitude(self, mag: np.ndarray) -> np.ndarray:
        taps = self._settings.mag_filter_taps
        if taps <= 1:
            return mag
        # Moving-average low-pass; suppresses single-sample noise spikes before correlation.
        kernel = np.ones(taps, dtype=np.float64) / taps
        return np.convolve(mag, kernel, mode="same")

    def _find_preamble_peaks(self, mag: np.ndarray) -> List[int]:
        # Cross-correlate magnitude envelope with the known preamble pattern.
        corr = np.correlate(mag, self._preamble_zm, mode="valid")
        if len(corr) == 0:
            return []

        corr_std = float(np.std(corr))
        if corr_std <= 0:
            return []

        # Adaptive threshold: mean + N·σ separates preambles from noise floor.
        threshold = float(
            np.mean(corr) + self._settings.corr_threshold_sigma * corr_std
        )
        # Use long-frame spacing so short replies do not flood the peak budget
        # and crowd out ADS-B decodes (regression when short decode was enabled).
        min_distance = MIN_FRAME_SAMPLES
        peaks = self._pick_peaks(corr, threshold, min_distance)
        if peaks.size == 0:
            return []

        ranked = sorted((int(p), float(corr[p])) for p in peaks)
        ranked.sort(key=lambda item: item[1], reverse=True)
        return [p for p, _ in ranked[: self._settings.max_peaks_per_buffer]]

    @staticmethod
    def _pick_peaks(corr: np.ndarray, height: float, min_distance: int) -> np.ndarray:
        peaks: List[int] = []
        i = 0
        n = len(corr)
        while i < n:
            if corr[i] >= height:
                end = min(i + min_distance, n)
                peak = i + int(np.argmax(corr[i:end]))
                peaks.append(peak)
                i = peak + min_distance
            else:
                i += 1
        return np.array(peaks, dtype=np.int64)

    def _try_decode_peak(self, mag: np.ndarray, peak: int, seen: Set[str]) -> List[str]:
        if not self._validate_preamble_shape(mag, peak):
            return []

        lengths = (SHORT_MSG_BITS, LONG_MSG_BITS)
        candidates: List[str] = []
        for num_bits in lengths:
            for phase in (0, 1):
                bits = self._phase_correct_and_demod(mag, peak, num_bits, phase)
                if len(bits) != num_bits:
                    continue
                hex_msg = self._bits_to_hex(bits)
                if hex_msg in seen or not self._acceptable(hex_msg):
                    continue
                candidates.append(hex_msg)
        if not candidates:
            return []
        hex_msg = self._pick_candidate(candidates)
        seen.add(hex_msg)
        return [hex_msg]

    @staticmethod
    def _pick_candidate(candidates: List[str]) -> str:
        """Prefer a long ADS-B decode over a short reply from the same preamble."""
        if len(candidates) == 1:
            return candidates[0]

        long_adsb: List[str] = []
        for hex_msg in candidates:
            if len(hex_msg) * 4 != LONG_MSG_BITS:
                continue
            try:
                decoded = pms.decode(hex_msg)
            except (InvalidHexError, InvalidLengthError, ValueError):
                continue
            if decoded.get("df") in PREFERRED_DF:
                long_adsb.append(hex_msg)
        if long_adsb:
            return long_adsb[0]

        # Spurious long CRCs from short replies are usually zero-padded extensions.
        return min(candidates, key=len)

    def _validate_preamble_shape(self, mag: np.ndarray, start: int) -> bool:
        """Require pulse energy at known positions to exceed quiet-chip energy."""
        if start < 0 or start + PREAMBLE_LEN > len(mag):
            return False
        p = mag[start : start + PREAMBLE_LEN]
        pulse_pos = (0, 2, 7, 9)
        quiet_pos = (1, 3, 4, 5, 6, 8, 10, 11, 12, 13, 14, 15)
        pulses = float(np.mean([p[i] for i in pulse_pos]))
        quiet = float(np.mean([p[i] for i in quiet_pos]))
        if quiet <= 1e-9:
            return pulses > 0
        return (pulses / quiet) >= self._settings.min_preamble_pulse_ratio

    def _demod_ppm(
        self, mag: np.ndarray, preamble_start: int, num_bits: int, phase: int = 0
    ) -> List[int]:
        data_start = preamble_start + PREAMBLE_LEN + phase
        bits: List[int] = []
        for bit_idx in range(num_bits):
            early = data_start + bit_idx * SAMPLES_PER_BIT
            late = early + 1
            if late >= len(mag):
                break
            bits.append(1 if mag[early] > mag[late] else 0)
        return bits

    def _phase_correct_and_demod(
        self, mag: np.ndarray, preamble_start: int, num_bits: int, phase: int = 0
    ) -> List[int]:
        bits = self._demod_ppm(mag, preamble_start, num_bits, phase)
        if len(bits) != num_bits:
            return bits

        hex_msg = self._bits_to_hex(bits)
        if self._crc_valid(hex_msg):
            return bits

        if num_bits != LONG_MSG_BITS:
            return bits

        return self._retry_with_phase_correction(
            mag, preamble_start, num_bits, phase, bits
        )

    def _retry_with_phase_correction(
        self,
        mag: np.ndarray,
        preamble_start: int,
        num_bits: int,
        phase: int,
        bits: List[int],
    ) -> List[int]:
        """Compensate sample-phase misalignment using dump1090-style ISI estimate.

        At exactly 2× oversampling, a fractional sample offset causes inter-symbol
        interference: energy from one 0.5 µs chip leaks into its neighbor. The Mode S
        preamble has known pulse locations, so we measure energy that bled *early*
        vs *late* relative to those pulses and apply a first-order correction before
        re-demodulating.
        """
        if preamble_start < 1 or preamble_start + PREAMBLE_LEN + 11 >= len(mag):
            return bits

        m = mag[preamble_start : preamble_start + PREAMBLE_LEN + 11]
        e_on = m[0] + m[2] + m[7] + m[9]
        e_early = 2.0 * (mag[preamble_start - 1] + m[6])
        e_late = 2.0 * (m[3] + m[10])

        corrected = mag.copy()
        data_start = preamble_start + PREAMBLE_LEN + phase
        data_end = data_start + num_bits * SAMPLES_PER_BIT + 1

        if e_early > e_late and (e_early + e_on) > 0:
            alpha = e_early / (e_early + e_on)
            sup = 1.0 + alpha
            for i in range(data_start, min(data_end, len(corrected))):
                prev_val = corrected[i - 1] if i > 0 else 0.0
                corrected[i] = corrected[i] * sup - prev_val * alpha
        elif e_late > e_early and (e_late + e_on) > 0:
            alpha = e_late / (e_late + e_on)
            sup = 1.0 + alpha
            for i in range(min(data_end - 1, len(corrected) - 1), data_start - 1, -1):
                next_val = corrected[i + 1] if i + 1 < len(corrected) else 0.0
                corrected[i] = corrected[i] * sup - next_val * alpha

        return self._demod_ppm(corrected, preamble_start, num_bits, phase)

    @staticmethod
    def _bits_to_hex(bits: List[int]) -> str:
        hex_str = ""
        for i in range(0, len(bits), 4):
            nibble = bits[i] * 8 + bits[i + 1] * 4 + bits[i + 2] * 2 + bits[i + 3]
            hex_str += f"{nibble:X}"
        return hex_str

    @staticmethod
    def _crc_valid(hex_msg: str) -> bool:
        try:
            return bool(pms.Message(hex_msg).crc_valid)
        except (InvalidHexError, InvalidLengthError):
            return False

    def _acceptable(self, hex_msg: str) -> bool:
        if not self._crc_valid(hex_msg):
            return False
        try:
            decoded = pms.decode(hex_msg)
        except (InvalidHexError, InvalidLengthError, ValueError):
            return False
        df = decoded.get("df")
        icao = decoded.get("icao", "")
        if not icao or icao == "000000":
            return False
        return df in ALL_MODE_S_DF
