"""Runtime configuration and RF constants for AircraftX."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from aircraftx.acars.channels import AcarsChannel
    from aircraftx.radio.channels import AirbandChannel

import numpy as np

# --- RF front-end ---
FREQ_HZ = 1_090_000_000
SAMPLE_RATE = 2_000_000
CHUNK_SAMPLES = 256 * 1024

# --- Mode S frame timing @ 2 MHz (0.5 µs per sample) ---
SAMPLES_PER_BIT = int(SAMPLE_RATE / 1e6)
PREAMBLE_SAMPLES = np.array(
    [1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0], dtype=np.float64
)
PREAMBLE_LEN = len(PREAMBLE_SAMPLES)
SHORT_MSG_BITS = 56
LONG_MSG_BITS = 112
MIN_FRAME_SAMPLES = int(120e-6 * SAMPLE_RATE)  # long frame (~120 µs)
MIN_SHORT_FRAME_SAMPLES = int(64e-6 * SAMPLE_RATE)  # short reply (~64 µs)

# --- Airband voice monitor ---
AIRBAND_MIN_MHZ = 108.0
AIRBAND_MAX_MHZ = 137.0
AIRBAND_AUDIO_RATE = 16_000
AIRBAND_VOLUME_DEFAULT = 3.0
AIRBAND_VOLUME_MIN = 0.0
AIRBAND_VOLUME_MAX = 12.0
AIRBAND_VOLUME_STEP = 0.25
WAVEFORM_HEIGHT = 7
RADIO_CHANNEL_PAGE_SIZE = 15
ACARS_CHANNEL_PAGE_SIZE = 8

# --- UI / memory limits ---
RECENT_MESSAGES_DISPLAY = 10
MAX_RECENT_MESSAGES_STORE = 500
MAX_RADIO_TRANSCRIPTS = 50
MAX_ACARS_MESSAGES = 50
MAX_ADSB_TRACKS = 10_000
MAX_MODE_S_TRACKS = 10_000

# --- Decode / validation ---
CONFIRM_WINDOW_SEC = 45.0
MAX_ALTITUDE_FT = 55_000
MIN_ALTITUDE_FT = -1_000
MAX_GROUNDSPEED_KT = 900
PREFERRED_DF: Set[int] = {17, 18}
ALL_MODE_S_DF: Set[int] = {4, 5, 11, 16, 17, 18, 20, 21, 24}

DF_LABELS = {
    4: "Mode-S alt",
    5: "Mode-S ID",
    11: "all-call",
    16: "Mode-S",
    17: "ADS-B",
    18: "ADS-B ext",
    20: "Comm-B alt",
    21: "Comm-B ID",
    24: "Comm-D",
}

HACKRF_BINARY_PATHS = (
    "hackrf_transfer",
    "/opt/homebrew/bin/hackrf_transfer",
    "/usr/local/bin/hackrf_transfer",
)

RTL_SDR_BINARY_PATHS = (
    "rtl_sdr",
    "/opt/homebrew/bin/rtl_sdr",
    "/usr/local/bin/rtl_sdr",
)


@dataclass(frozen=True)
class DemodSettings:
    """Sensitivity knobs for the PPM demodulator."""

    corr_threshold_sigma: float = 8.0
    max_peaks_per_buffer: int = 12
    min_preamble_pulse_ratio: float = 2.5
    mag_filter_taps: int = 5

    @classmethod
    def outdoor(cls) -> DemodSettings:
        return cls()

    @classmethod
    def indoor(cls) -> DemodSettings:
        return cls(
            corr_threshold_sigma=5.5,
            max_peaks_per_buffer=20,
            min_preamble_pulse_ratio=2.0,
        )


@dataclass(frozen=True)
class TrackerSettings:
    """Confirmation and stale-aircraft eviction policy."""

    min_confirm_hits: int = 3
    stale_unconfirmed_sec: float = 15.0

    @classmethod
    def outdoor(cls) -> TrackerSettings:
        return cls()

    @classmethod
    def indoor(cls) -> TrackerSettings:
        return cls(min_confirm_hits=2, stale_unconfirmed_sec=30.0)


@dataclass(frozen=True)
class RadioConfig:
    backend: str = "hackrf"
    lna_gain: int = 24
    vga_gain: int = 40
    amp_enable: bool = True
    tuner_gain: float = 40
    ppm_error: int = 0


@dataclass(frozen=True)
class SnifferConfig:
    """Top-level configuration for an AircraftX session."""

    lat_ref: Optional[float] = None
    lon_ref: Optional[float] = None
    adsb_only: bool = True
    demod: DemodSettings = DemodSettings.outdoor()
    tracker: TrackerSettings = TrackerSettings.outdoor()
    radio: RadioConfig = RadioConfig()
    refresh_hz: float = 2.0
    sound_enabled: bool = True
    radio_local_channels: Tuple["AirbandChannel", ...] = ()
    radio_basic_channels: Tuple["AirbandChannel", ...] = ()
    acars_channels: Tuple["AcarsChannel", ...] = ()

    @classmethod
    def from_preset(
        cls,
        *,
        indoor: bool = False,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        adsb_only: bool = True,
        lna: int = 24,
        vga: int = 40,
        amp_enable: bool = True,
        backend: str = "hackrf",
        tuner_gain: float = 40,
        ppm_error: int = 0,
        refresh_hz: float = 2.0,
        sound_enabled: bool = True,
        radio_local_channels: Optional[List["AirbandChannel"]] = None,
        radio_basic_channels: Optional[List["AirbandChannel"]] = None,
        acars_channels: Optional[List["AcarsChannel"]] = None,
    ) -> SnifferConfig:
        if indoor:
            demod = DemodSettings.indoor()
            tracker = TrackerSettings.indoor()
        else:
            demod = DemodSettings.outdoor()
            tracker = TrackerSettings.outdoor()
        return cls(
            lat_ref=lat,
            lon_ref=lon,
            adsb_only=adsb_only,
            demod=demod,
            tracker=tracker,
            radio=RadioConfig(
                backend=backend,
                lna_gain=lna,
                vga_gain=vga,
                amp_enable=amp_enable,
                tuner_gain=tuner_gain,
                ppm_error=ppm_error,
            ),
            refresh_hz=refresh_hz,
            sound_enabled=sound_enabled,
            radio_local_channels=tuple(radio_local_channels or ()),
            radio_basic_channels=tuple(radio_basic_channels or ()),
            acars_channels=tuple(acars_channels or ()),
        )
