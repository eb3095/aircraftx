"""MSK demod and ACARS frame parsing (ported from acarsdec)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List

import numpy as np

# acarsdec INTRATE — 2 MHz / 160 = 12500 Hz after AM envelope extraction.
ACARS_AUDIO_RATE = 12_500
BAUD_RATE = 1200.0
_TWO_PI = 2.0 * math.pi

SYN = 0x16
SOH = 0x01
STX = 0x02
ETX = 0x83
ETB = 0x97
DLE = 0x7F

_PLL_G = 38e-4
_PLL_C = 0.52


def _num_bits_set(value: int) -> int:
    return bin(value & 0xFF).count("1")


@dataclass
class AcarsMessage:
    mode: str
    tail: str
    label: str
    flight: str
    msgno: str
    text: str
    ack: str
    block_id: str
    level_db: float
    error_count: int


class _AcarsState(Enum):
    WSYN = auto()
    SYN2 = auto()
    SOH1 = auto()
    TXT = auto()
    CRC1 = auto()
    CRC2 = auto()
    END = auto()


@dataclass
class _MsgBlock:
    txt: bytearray = field(default_factory=bytearray)
    crc: bytearray = field(default_factory=bytearray)
    err: int = 0
    lvl_sum: float = 0.0
    bit_count: int = 0


class AcarsDecoder:
    """Demodulate AM envelope audio and extract ACARS network messages."""

    def __init__(self) -> None:
        self._init_msk()
        self._reset_acars()

    def _init_msk(self) -> None:
        self._flen = int(ACARS_AUDIO_RATE / BAUD_RATE) + 1
        self._mflt_over = 12
        self._fleno = self._flen * self._mflt_over + 1
        intrate = float(ACARS_AUDIO_RATE)
        self._h = np.array(
            [
                max(
                    0.0,
                    math.cos(
                        _TWO_PI
                        * 600.0
                        / intrate
                        / self._mflt_over
                        * (i - (self._fleno - 1) / 2)
                    ),
                )
                for i in range(self._fleno)
            ],
            dtype=np.float64,
        )
        self._inb = np.zeros(self._flen, dtype=np.complex64)
        self._idx = 0
        self._msk_phi = 0.0
        self._msk_df = 0.0
        self._msk_clk = 0.0
        self._msk_s = 0
        self._msk_lvl_sum = 0.0
        self._msk_bit_count = 0
        self._outbits = 0
        self._nbits = 8
        self._blk: _MsgBlock | None = None

    def _reset_acars(self) -> None:
        self._state = _AcarsState.WSYN
        self._msk_df = 0.0
        self._nbits = 1
        self._blk = None

    def reset(self) -> None:
        self._init_msk()
        self._reset_acars()

    def feed(self, envelope: np.ndarray) -> List[AcarsMessage]:
        """Consume AM-demodulated real samples at ACARS_AUDIO_RATE."""
        messages: List[AcarsMessage] = []
        if envelope.size == 0:
            return messages

        samples = envelope.astype(np.float64, copy=False)
        baud_step = _TWO_PI * BAUD_RATE / ACARS_AUDIO_RATE

        for sample in samples:
            self._msk_phi += self._msk_df
            if self._msk_phi >= _TWO_PI:
                self._msk_phi -= _TWO_PI

            mixed = sample * complex(math.cos(-self._msk_phi), math.sin(-self._msk_phi))
            self._inb[self._idx] = mixed
            self._idx = (self._idx + 1) % self._flen

            self._msk_clk += baud_step
            if self._msk_clk < 1.5 * math.pi - baud_step / 2:
                continue

            self._msk_clk -= 1.5 * math.pi
            o = self._mflt_over * (self._msk_clk / baud_step + 0.5)
            if o > self._mflt_over:
                o = self._mflt_over

            v = 0.0 + 0.0j
            j = 0
            oo = o
            while j < self._flen:
                v += self._h[int(oo)] * self._inb[(j + self._idx) % self._flen]
                j += 1
                oo += self._mflt_over

            lvl = abs(v)
            if lvl > 1e-12:
                v /= lvl
            self._msk_lvl_sum += (lvl * lvl) / 4.0
            self._msk_bit_count += 1

            if self._msk_s & 1:
                vo = v.imag
                dphi = -v.real if vo >= 0 else v.real
            else:
                vo = v.real
                dphi = v.imag if vo >= 0 else -v.imag

            bit_val = -vo if (self._msk_s & 2) else vo
            self._msk_s += 1
            self._msk_df = _PLL_C * self._msk_df + (1.0 - _PLL_C) * _PLL_G * dphi

            msg = self._put_bit(bit_val)
            if msg is not None:
                messages.append(msg)

        return messages

    def _put_bit(self, value: float) -> AcarsMessage | None:
        self._outbits >>= 1
        if value > 0:
            self._outbits |= 0x80
        self._nbits -= 1
        if self._nbits > 0:
            return None
        return self._decode_byte(self._outbits & 0xFF)

    def _decode_byte(self, byte_val: int) -> AcarsMessage | None:
        r = byte_val

        if self._state == _AcarsState.WSYN:
            if r == SYN:
                self._state = _AcarsState.SYN2
                self._nbits = 8
            elif r == (~SYN) & 0xFF:
                self._msk_s ^= 2
                self._state = _AcarsState.SYN2
                self._nbits = 8
            else:
                self._nbits = 1
            return None

        if self._state == _AcarsState.SYN2:
            if r == SYN:
                self._state = _AcarsState.SOH1
                self._nbits = 8
            elif r == (~SYN) & 0xFF:
                self._msk_s ^= 2
                self._nbits = 8
            else:
                self._reset_acars()
            return None

        if self._state == _AcarsState.SOH1:
            if r == SOH:
                self._blk = _MsgBlock(
                    lvl_sum=self._msk_lvl_sum,
                    bit_count=self._msk_bit_count,
                )
                self._state = _AcarsState.TXT
                self._nbits = 8
            else:
                self._reset_acars()
            return None

        if self._state == _AcarsState.TXT:
            assert self._blk is not None
            self._blk.txt.append(r)
            if (_num_bits_set(r) & 1) == 0:
                self._blk.err += 1
                if self._blk.err > 4:
                    self._reset_acars()
                    return None
            if r in (ETX, ETB):
                self._state = _AcarsState.CRC1
                self._nbits = 8
                return None
            if len(self._blk.txt) > 20 and r == DLE:
                self._blk.txt = self._blk.txt[:-3]
                self._blk.crc = bytearray(self._blk.txt[-2:])
                return self._finish_block()
            if len(self._blk.txt) > 240:
                self._reset_acars()
            else:
                self._nbits = 8
            return None

        if self._state == _AcarsState.CRC1:
            assert self._blk is not None
            self._blk.crc = bytearray([r])
            self._state = _AcarsState.CRC2
            self._nbits = 8
            return None

        if self._state == _AcarsState.CRC2:
            assert self._blk is not None
            self._blk.crc.append(r)
            msg = self._finish_block()
            self._state = _AcarsState.END
            self._nbits = 8
            return msg

        if self._state == _AcarsState.END:
            self._reset_acars()
            self._nbits = 8
        return None

    def _finish_block(self) -> AcarsMessage | None:
        blk = self._blk
        self._blk = None
        if blk is None or len(blk.txt) < 13:
            return None

        level_db = 0.0
        if blk.bit_count > 0 and blk.lvl_sum > 0:
            level_db = 10.0 * math.log10(blk.lvl_sum / blk.bit_count)

        payload = bytes(blk.txt)
        stripped = bytearray()
        for b in payload:
            if (_num_bits_set(b) & 1) == 0:
                return None
            stripped.append(b & 0x7F)

        return parse_acars_block(stripped, level_db=level_db, error_count=blk.err)


def parse_acars_block(
    txt: bytes | bytearray,
    *,
    level_db: float = 0.0,
    error_count: int = 0,
) -> AcarsMessage | None:
    """Parse a parity-stripped ACARS block into display fields."""
    if len(txt) < 13:
        return None

    k = 0
    mode = chr(txt[k])
    k += 1

    addr_chars: list[str] = []
    for _ in range(7):
        ch = txt[k]
        k += 1
        if ch != ord("."):
            addr_chars.append(chr(ch))
    tail = "".join(addr_chars)

    ack_byte = txt[k]
    k += 1
    ack = "!" if ack_byte == 0x15 else chr(ack_byte)

    label0 = chr(txt[k])
    k += 1
    label1 = chr(txt[k])
    if label1 == "\x7f":
        label1 = "d"
    k += 1
    label = label0 + label1

    block_id = chr(txt[k])
    k += 1
    downlink = "0" <= block_id <= "9"

    if k < len(txt):
        k += 1  # bs (text start marker)

    msgno = ""
    flight = ""
    if downlink and k < len(txt) - 1:
        msgno = "".join(chr(txt[k + i]) for i in range(4) if k + i < len(txt) - 1)
        k += 4
        flight = "".join(chr(txt[k + i]) for i in range(6) if k + i < len(txt) - 1)
        k += 6

    body = txt[k : len(txt) - 1]
    text = body.decode("ascii", errors="replace").strip()
    if not text and not tail:
        return None

    return AcarsMessage(
        mode=mode,
        tail=tail,
        label=label,
        flight=flight.strip(),
        msgno=msgno.strip(),
        text=text,
        ack=ack,
        block_id=block_id,
        level_db=level_db,
        error_count=error_count,
    )
