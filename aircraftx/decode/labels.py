"""Human-readable Downlink Format labels."""

from __future__ import annotations

from aircraftx.config import DF_LABELS, PREFERRED_DF
from aircraftx.models.aircraft import Aircraft


def _format_df(df: int, tc: int | None) -> str:
    label = DF_LABELS.get(df, f"DF{df}")
    if tc is not None:
        return f"{label}/{tc}"
    return label


def df_label(aircraft: Aircraft) -> str:
    """Label from the most recent message (any DF)."""
    if aircraft.last_df is None:
        return "—"
    return _format_df(aircraft.last_df, aircraft.last_tc)


def table_type_label(aircraft: Aircraft, *, adsb_table: bool) -> str:
    """Table label that does not let a later Mode-S reply mask ADS-B."""
    if adsb_table and aircraft.has_adsb():
        if aircraft.last_adsb_df is not None:
            return _format_df(aircraft.last_adsb_df, aircraft.last_adsb_tc)
        return "ADS-B"
    if aircraft.last_df is None:
        return "—"
    return _format_df(aircraft.last_df, aircraft.last_tc)


def table_type_is_adsb(aircraft: Aircraft, *, adsb_table: bool) -> bool:
    if adsb_table:
        return aircraft.has_adsb()
    return aircraft.last_df in PREFERRED_DF if aircraft.last_df is not None else False
