from __future__ import annotations

from aircraftx.radio.channel_defaults import DEFAULT_RADIO_CHANNELS
from aircraftx.radio.channels import (
    build_channel_sets,
    channel_from_dict,
    dedupe_channels,
    parse_config_channels,
)


def test_channel_from_dict_uses_freq_mhz():
    ch = channel_from_dict(
        {
            "id": "121.500",
            "name": "Guard",
            "freq_mhz": 121.5,
            "description": "Emergency",
        }
    )
    assert ch.freq_hz == 121_500_000
    assert ch.name == "Guard"


def test_parse_config_channels_defaults():
    channels = parse_config_channels(None)
    assert len(channels) == len(DEFAULT_RADIO_CHANNELS)
    assert channels[0].channel_id == "121.500"


def test_dedupe_channels_prefers_first():
    first = parse_config_channels(None)
    merged = dedupe_channels([*first, *first])
    assert len(merged) == len(first)


def test_build_channel_sets_splits_local_and_basic(tmp_path, monkeypatch):
    airports = tmp_path / "airports.csv"
    freqs = tmp_path / "airport-frequencies.csv"
    airports.write_text(
        (
            '"id","ident","type","name","latitude_deg","longitude_deg",'
            '"elevation_ft","continent","iso_country","iso_region",'
            '"municipality","scheduled_service","icao_code","iata_code",'
            '"gps_code","local_code","home_link","wikipedia_link","keywords"\n'
            '1,"KAAA","small_airport","Alpha Field",40.45,-74.13,10,'
            '"NA","US","US-NJ","Alpha","no","KAAA",,"KAAA","AAA",,,\n'
        ),
        encoding="utf-8",
    )
    freqs.write_text(
        (
            '"id","airport_ref","airport_ident","type","description","frequency_mhz"\n'
            '1,1,"KAAA","CTAF","CTAF",122.8\n'
            '2,1,"KAAA","ATIS","ATIS",118.25\n'
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "aircraftx.radio.local_lookup._ensure_dataset",
        lambda name: airports if name == "airports.csv" else freqs,
    )

    local, basic = build_channel_sets(
        lat=40.0,
        lon=-74.0,
        config_channels=DEFAULT_RADIO_CHANNELS[:2],
        local_lookup=True,
        local_radius_km=80,
        local_max_airports=5,
    )
    assert local[0].channel_id.startswith("KAAA:")
    assert any(ch.freq_hz == 122_800_000 for ch in local)
    assert basic[0].channel_id == "121.500"
    assert len(basic) == 2
