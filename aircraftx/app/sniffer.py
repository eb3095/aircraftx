"""AircraftX live capture and replay orchestrator."""

from __future__ import annotations

import time
from typing import Literal

import numpy as np
from rich.live import Live

from aircraftx.app.shutdown import ShutdownCoordinator
from aircraftx.config import FREQ_HZ, SnifferConfig
from aircraftx.log_writer import LogWriter
from aircraftx.decode.tracker import AircraftTracker
from aircraftx.dsp.demodulator import ModeSDemodulator
from aircraftx.dsp.iq import IQConverter
from aircraftx.radio.receiver import make_receiver
from aircraftx.radio.voice_monitor import VoiceMonitor
from aircraftx.acars.monitor import AcarsMonitor
from aircraftx.lookup.service import AircraftLookupService
from aircraftx.ui.acars_display import AcarsDisplay
from aircraftx.ui.display import ConsoleDisplay
from aircraftx.ui.keyboard import drain_keys, repair_live_screen, restore_terminal, terminal_session
from aircraftx.ui.map_window import MapWindowController, build_map_view
from aircraftx.ui.radio_display import RadioDisplay

DashboardMode = Literal["adsb", "radio", "acars"]


class AircraftXSniffer:
    """Coordinates RF capture, demodulation, decoding, and the terminal UI."""

    def __init__(self, config: SnifferConfig) -> None:
        self.config = config
        self._log_writer = LogWriter()
        self.tracker = AircraftTracker(
            lat_ref=config.lat_ref,
            lon_ref=config.lon_ref,
            settings=config.tracker,
        )
        self.demodulator = ModeSDemodulator(config.demod)
        self._lookup = AircraftLookupService()
        self.display = ConsoleDisplay(config, self._log_writer, self._lookup)
        self.voice_monitor = VoiceMonitor(
            config.radio_local_channels,
            config.radio_basic_channels,
            backend=config.radio.backend,
            log_writer=self._log_writer,
        )
        self.radio_display = RadioDisplay(self.voice_monitor, config.radio)
        self.acars_monitor = AcarsMonitor(
            config.acars_channels,
            backend=config.radio.backend,
            log_writer=self._log_writer,
        )
        self.acars_display = AcarsDisplay(self.acars_monitor, config.radio)
        self._map = MapWindowController(
            ref_lat=config.lat_ref,
            ref_lon=config.lon_ref,
        )
        self.dashboard: DashboardMode = "adsb"
        self.receiver = make_receiver(config.radio, freq_hz=self._tuned_frequency())

    def _tuned_frequency(self) -> int:
        if self.dashboard == "radio":
            return self.voice_monitor.selected_channel().freq_hz
        if self.dashboard == "acars":
            return self.acars_monitor.selected_channel().freq_hz
        return FREQ_HZ

    def _apply_tuning(self) -> None:
        self.receiver.set_frequency(self._tuned_frequency())

    def set_dashboard(self, mode: DashboardMode) -> None:
        if self.dashboard == mode:
            return
        self.dashboard = mode
        self._apply_tuning()

    def set_track_mode(self, adsb_only: bool) -> None:
        """Switch visible rows only; demod and tracking stay on all Mode S."""
        self.display.adsb_only = adsb_only

    def _render(self, now: float):
        if self.dashboard == "radio":
            return self.radio_display.render()
        if self.dashboard == "acars":
            return self.acars_display.render()
        if self.dashboard == "adsb":
            self._sync_lookup_cache(now)
            self._sync_map(now)
        return self.display.render(self.tracker, now, self.config.radio)

    def _sync_map(self, now: float) -> None:
        if not self._map.is_open() or not self.display.adsb_only:
            return
        focus = self.display.map_focus_icao(self.tracker, now)
        if not focus:
            return
        ac = None
        for candidate in self.tracker.aircraft.values():
            if candidate.icao.upper() == focus.upper():
                ac = candidate
                break
        if ac is None:
            return
        enrichment = self._lookup.get(focus)
        view = build_map_view(
            aircraft_icao=ac.icao,
            mode=self.display.map_focus_mode(),
            callsign=ac.callsign or "",
            registration=enrichment.registration if enrichment else "",
            altitude_ft=ac.altitude_ft,
            speed_kts=ac.speed_kts,
            heading_deg=ac.heading_deg,
            latitude=ac.latitude,
            longitude=ac.longitude,
            trail=self.display.trails.trail(ac.icao),
            route=enrichment.route if enrichment else "",
            departure=enrichment.departure if enrichment else "",
            destination=enrichment.destination if enrichment else "",
            airport_coords=self._map.airport_coords,
        )
        self._map.update(view)
        self.display.trails.trim(
            {a.icao.upper() for a in self.tracker.confirmed_aircraft(now)}
        )

    def _process_iq_chunk(self, chunk: bytes, now: float) -> None:
        if self.dashboard == "adsb":
            iq = IQConverter.from_radio_bytes(chunk, self.config.radio.backend)
            if iq.size > 0:
                buffer = np.concatenate([self._iq_overlap, iq])
                messages = self.demodulator.demodulate(buffer)
                self._iq_overlap = self.demodulator.overlap_tail(buffer)
                self._process_messages(messages, now)
        elif self.dashboard == "radio":
            self.voice_monitor.process_iq(chunk, now)
        else:
            self.acars_monitor.process_iq(chunk, now)

    def _sync_lookup_cache(self, now: float) -> None:
        active = {
            ac.icao.upper()
            for ac in self.tracker.confirmed_aircraft(now)
            if ac.df17_count > 0
        }
        self._lookup.sync_active_icaos(active)

    def _handle_keys(self, live: Live, last_render: float) -> tuple[bool, float]:
        """Process keyboard input. Returns (should_continue, last_render)."""
        for key in drain_keys():
            if key == "quit":
                return False, last_render
            if key == "dashboard_radio":
                self.set_dashboard("radio")
            elif key == "dashboard_acars":
                self.set_dashboard("acars")
            elif key == "dashboard_adsb":
                self.set_dashboard("adsb")
            elif self.dashboard == "acars":
                if key == "channel_up":
                    self.acars_monitor.channel_up()
                    self._apply_tuning()
                elif key == "channel_down":
                    self.acars_monitor.channel_down()
                    self._apply_tuning()
                elif key == "first":
                    self.acars_monitor.channel_page_up()
                elif key == "last":
                    self.acars_monitor.channel_page_down()
            elif self.dashboard == "radio":
                if key == "channel_up":
                    self.voice_monitor.channel_up()
                    self._apply_tuning()
                elif key == "channel_down":
                    self.voice_monitor.channel_down()
                    self._apply_tuning()
                elif key == "channel_source_local":
                    self.voice_monitor.set_channel_source("local")
                    self._apply_tuning()
                elif key == "channel_source_basic":
                    self.voice_monitor.set_channel_source("basic")
                    self._apply_tuning()
                elif key == "first":
                    self.voice_monitor.channel_page_up()
                elif key == "last":
                    self.voice_monitor.channel_page_down()
                elif key == "prev":
                    self.voice_monitor.squelch_down()
                elif key == "next":
                    self.voice_monitor.squelch_up()
                elif key == "volume_up":
                    self.voice_monitor.volume_up()
                elif key == "volume_down":
                    self.voice_monitor.volume_down()
            elif key == "mode_all":
                self.set_track_mode(False)
            elif key == "mode_adsb":
                self.set_track_mode(True)
            elif key == "toggle_map" and self.dashboard == "adsb":
                self._map.toggle()
                if self._map.is_open():
                    self._map.pump()
            else:
                self.display.handle_key(key, self.tracker, time.time())
            now = time.time()
            live.update(self._render(now))
            last_render = now
        return True, last_render

    def _refresh_after_map_close(self, live: Live) -> None:
        repair_live_screen(self.display.console)
        live.update(self._render(time.time()))

    def _teardown_live(self) -> None:
        self._map.shutdown()
        self._lookup.shutdown()
        self.voice_monitor.shutdown()
        self.receiver.stop(fast=True)
        self._log_writer.close()

    def run_live(self) -> None:
        self.receiver.start()
        shutdown = ShutdownCoordinator()
        shutdown.on_exit(self._teardown_live)
        shutdown.install()

        overlap = np.array([], dtype=np.complex64)
        last_render = 0.0

        try:
            with terminal_session():
                with Live(
                    self._render(time.time()),
                    console=self.display.console,
                    refresh_per_second=self.config.refresh_hz,
                    screen=True,
                    transient=False,
                ) as live:
                    self._map.set_on_close(
                        lambda: self._refresh_after_map_close(live)
                    )
                    self._iq_overlap = overlap
                    while shutdown.running:
                        now = time.time()
                        shutdown.running, last_render = self._handle_keys(
                            live, last_render
                        )
                        if not shutdown.running:
                            break

                        got_iq = False
                        while True:
                            chunk = self.receiver.read_chunk(timeout=0.0)
                            if not chunk:
                                break
                            got_iq = True
                            self._process_iq_chunk(chunk, now)

                        if not got_iq:
                            chunk = self.receiver.read_chunk(
                                timeout=0.0 if not shutdown.running else 0.05
                            )
                            if chunk:
                                self._process_iq_chunk(chunk, now)
                            elif self.receiver.exited:
                                raise RuntimeError(
                                    f"{self.config.radio.backend} receiver exited. "
                                    "Check radio connection."
                                )

                        if now - last_render >= 1.0 / self.config.refresh_hz:
                            live.update(self._render(now))
                            last_render = now
                            if self._map.is_open():
                                self._map.pump()
        finally:
            shutdown.cleanup()
            restore_terminal()

    def run_file(self, path: str) -> None:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            iq = IQConverter.from_radio_bytes(data, self.config.radio.backend)
            messages = self.demodulator.demodulate(iq)
            now = time.time()
            self._process_messages(messages, now)
            self.display.print_once(self.tracker, now, self.config.radio)
        finally:
            self._log_writer.close()

    def _process_messages(self, messages: list[str], now: float) -> None:
        for hex_msg in messages:
            self.tracker.total_messages += 1
            aircraft = self.tracker.ingest(hex_msg, now=now)
            if aircraft is not None:
                self.display.push_message(aircraft, now)
