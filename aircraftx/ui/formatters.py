"""String formatting helpers for the terminal UI."""

from __future__ import annotations

from typing import List

from aircraftx.models.aircraft import Aircraft


def fmt_optional(value: object, suffix: str = "", na: str = "—") -> str:
    if value is None or value == "":
        return na
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def message_summary(aircraft: Aircraft) -> str:
    parts: List[str] = []
    if aircraft.callsign:
        parts.append(aircraft.callsign)
    if aircraft.altitude_ft is not None:
        parts.append(f"{aircraft.altitude_ft:,} ft")
    if aircraft.speed_kts is not None:
        hdg = (
            f" @{aircraft.heading_deg:.0f}°" if aircraft.heading_deg is not None else ""
        )
        parts.append(f"{aircraft.speed_kts:.0f} kt{hdg}")
    if aircraft.latitude is not None and aircraft.longitude is not None:
        parts.append(f"{aircraft.latitude:.4f}, {aircraft.longitude:.4f}")
    if aircraft.squawk:
        parts.append(f"sq {aircraft.squawk}")
    return " · ".join(parts) if parts else "—"
