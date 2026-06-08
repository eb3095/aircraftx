"""VHF ACARS IQ processing and per-channel message buffers."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Mapping, Sequence

import numpy as np

from aircraftx.acars.channels import AcarsChannel, parse_acars_channels
from aircraftx.acars.decoder import ACARS_AUDIO_RATE, AcarsDecoder, AcarsMessage
from aircraftx.config import ACARS_CHANNEL_PAGE_SIZE, MAX_ACARS_MESSAGES
from aircraftx.dsp.am_demodulator import AMDemodulator
from aircraftx.dsp.iq import IQConverter
from aircraftx.log_writer import LogWriter

_ACARS_DEMOD = AMDemodulator()


@dataclass
class AcarsLine:
    timestamp: str
    message: AcarsMessage


class AcarsMonitor:
    def __init__(
        self,
        channels: Sequence[AcarsChannel] | None = None,
        *,
        config_channels: Sequence[Mapping[str, Any]] | None = None,
        log_writer: LogWriter | None = None,
    ) -> None:
        self._log = log_writer
        if channels is not None:
            self._channels = list(channels)
        else:
            self._channels = parse_acars_channels(
                list(config_channels) if config_channels is not None else None
            )
        self.selected_index = 0
        self.page_index = 0
        self._decoder = AcarsDecoder()
        self._buffers: Dict[str, Deque[AcarsLine]] = {
            ch.channel_id: deque(maxlen=MAX_ACARS_MESSAGES) for ch in self._channels
        }
        self.total_messages = 0
        self.last_level_db = 0.0

    @property
    def channels(self) -> List[AcarsChannel]:
        return self._channels

    @property
    def channel_page_size(self) -> int:
        return ACARS_CHANNEL_PAGE_SIZE

    @property
    def page_count(self) -> int:
        total = len(self._channels)
        if total == 0:
            return 1
        return max(1, (total + self.channel_page_size - 1) // self.channel_page_size)

    def page_channels(self) -> List[AcarsChannel]:
        start = self.page_index * self.channel_page_size
        return self._channels[start : start + self.channel_page_size]

    def page_range_label(self) -> str:
        total = len(self._channels)
        if total == 0:
            return "0"
        start = self.page_index * self.channel_page_size
        end = min(start + self.channel_page_size, total)
        return f"{start + 1}-{end} of {total}"

    def channel_page_up(self) -> None:
        self.page_index = max(0, self.page_index - 1)

    def channel_page_down(self) -> None:
        self.page_index = min(self.page_count - 1, self.page_index + 1)

    def selected_channel(self) -> AcarsChannel:
        if not self._channels:
            return parse_acars_channels(None)[0]
        return self._channels[self.selected_index]

    def select_index(self, index: int) -> AcarsChannel:
        if not self._channels:
            return self.selected_channel()
        self.selected_index = max(0, min(index, len(self._channels) - 1))
        page = self.selected_index // self.channel_page_size
        self.page_index = page
        self._decoder.reset()
        return self.selected_channel()

    def channel_up(self) -> AcarsChannel:
        return self.select_index(self.selected_index - 1)

    def channel_down(self) -> AcarsChannel:
        return self.select_index(self.selected_index + 1)

    def buffer_for(self, channel_id: str | None = None) -> Deque[AcarsLine]:
        cid = channel_id or self.selected_channel().channel_id
        if cid not in self._buffers:
            self._buffers[cid] = deque(maxlen=MAX_ACARS_MESSAGES)
        return self._buffers[cid]

    def process_iq(self, chunk: bytes, now: float | None = None) -> None:
        ts = time.strftime("%H:%M:%S", time.localtime(now or time.time()))
        iq = IQConverter.from_bytes(chunk)
        if iq.size == 0:
            return

        audio = _ACARS_DEMOD.demod(iq, audio_rate=ACARS_AUDIO_RATE)
        if audio.size == 0:
            return

        channel = self.selected_channel()
        messages = self._decoder.feed(audio)
        if messages:
            self.last_level_db = messages[-1].level_db
        for message in messages:
            self.total_messages += 1
            self.buffer_for(channel.channel_id).append(
                AcarsLine(timestamp=ts, message=message)
            )
            if self._log is not None:
                self._log.log_acars(channel.freq_mhz, ts, message)
