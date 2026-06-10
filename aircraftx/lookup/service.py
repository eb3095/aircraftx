"""Background aircraft enrichment with bounded cache and periodic cleanup."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Dict, Literal, Optional, Set

from aircraftx.lookup import hexdb
from aircraftx.lookup.hexdb import LookupOutcome
from aircraftx.lookup.models import AircraftEnrichment, LookupStatus

_CLEANUP_INTERVAL_SEC = 30.0
_STALE_LOOKUP_SEC = 60.0
_MAX_AIRCRAFT_RETRIES = 4
_JOB_KIND = Literal["aircraft", "route"]


def _norm_icao(icao: str) -> str:
    return icao.strip().upper()


def _norm_callsign(callsign: str) -> str:
    return callsign.strip().upper()


@dataclass(frozen=True)
class _Job:
    icao: str
    kind: _JOB_KIND
    callsign: str = ""


class AircraftLookupService:
    """Queue ICAO lookups on a worker thread; never blocks the RF/UI loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: Dict[str, AircraftEnrichment] = {}
        self._queue: queue.Queue[_Job] = queue.Queue()
        self._active_icaos: Set[str] = set()
        self._in_flight: Set[str] = set()
        self._queued: Set[str] = set()
        self._route_tried: Dict[str, str] = {}
        self._pending_route: Dict[str, str] = {}
        self._aircraft_retries: Dict[str, int] = {}
        self._stop = threading.Event()
        self._last_cleanup = time.monotonic()
        self._worker = threading.Thread(
            target=self._run,
            name="aircraftx-lookup",
            daemon=True,
        )
        self._worker.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._queue.put_nowait(_Job(icao="", kind="aircraft"))
        self._worker.join(timeout=2.0)

    def sync_active_icaos(self, icaos: Set[str]) -> None:
        """Mark which ICAOs are still tracked; stale cache entries are purged."""
        with self._lock:
            self._active_icaos = {_norm_icao(i) for i in icaos}

    def enqueue_aircraft(self, icao: str) -> None:
        """First ADS-B sighting — fetch registration/type (no callsign required)."""
        key = _norm_icao(icao)
        if not key:
            return
        with self._lock:
            existing = self._cache.get(key)
            if existing is not None:
                if existing.status in ("queued", "loading"):
                    return
                if existing.status == "ready" and existing.registration:
                    return
                if existing.status == "error":
                    if time.time() - existing.updated_at < _STALE_LOOKUP_SEC:
                        return
            self._cache[key] = AircraftEnrichment(icao=key, status="queued")
        self._try_schedule(_Job(icao=key, kind="aircraft"))

    def maybe_route(self, icao: str, callsign: str) -> None:
        """Fetch route once when a callsign appears or changes (optional enrichment)."""
        key = _norm_icao(icao)
        flight = _norm_callsign(callsign)
        if not key or not flight:
            return
        with self._lock:
            existing = self._cache.get(key)
            if existing is None or existing.status != "ready" or not existing.registration:
                self._pending_route[key] = flight
                return
            if existing.route:
                return
            if self._route_tried.get(key) == flight:
                return
        if self._try_schedule(_Job(icao=key, kind="route", callsign=flight)):
            with self._lock:
                self._route_tried[key] = flight

    def get(self, icao: str) -> Optional[AircraftEnrichment]:
        with self._lock:
            return self._cache.get(_norm_icao(icao))

    def pending_count(self) -> int:
        with self._lock:
            return sum(
                1
                for entry in self._cache.values()
                if entry.status in ("queued", "loading")
            )

    def _schedule(self, job: _Job) -> None:
        if self._try_schedule(job):
            return

    def _try_schedule(self, job: _Job) -> bool:
        if not job.icao:
            return False
        with self._lock:
            if job.icao in self._in_flight or job.icao in self._queued:
                if job.kind == "route":
                    self._pending_route[job.icao] = job.callsign
                return False
            self._queued.add(job.icao)
        self._queue.put_nowait(job)
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                self._maybe_cleanup()
                continue
            if not job.icao:
                continue
            self._process(job)
            self._maybe_cleanup()

    def _maybe_cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < _CLEANUP_INTERVAL_SEC:
            return
        self._last_cleanup = now
        with self._lock:
            active = self._active_icaos
            now_ts = time.time()
            stale = []
            for key, entry in self._cache.items():
                if key in active:
                    continue
                age = now_ts - entry.updated_at
                if entry.status in ("ready", "error"):
                    stale.append(key)
                elif entry.status in ("queued", "loading") and age > 300:
                    stale.append(key)
            for key in stale:
                del self._cache[key]
                self._route_tried.pop(key, None)
                self._pending_route.pop(key, None)

    def _process(self, job: _Job) -> None:
        key = job.icao
        with self._lock:
            self._in_flight.add(key)
            self._queued.discard(key)
            prior = self._cache.get(key)

        try:
            if job.kind == "route":
                if prior is None or not prior.registration:
                    enrichment = prior or AircraftEnrichment(icao=key, status="error")
                else:
                    enrichment = self._fetch_route_only(key, job.callsign, prior)
            else:
                self._set_status(key, "loading")
                enrichment = self._fetch_aircraft(key)
                if enrichment.status == "queued":
                    enrichment.updated_at = time.time()
                    with self._lock:
                        self._cache[key] = enrichment
                        self._in_flight.discard(key)
                    delay = min(self._aircraft_retries.get(key, 1) * 2, 10)
                    time.sleep(delay)
                    self._try_schedule(_Job(icao=key, kind="aircraft"))
                    return
        except Exception as exc:  # noqa: BLE001 — worker must not die
            enrichment = AircraftEnrichment(
                icao=key,
                status="error",
                error=str(exc)[:120],
            )

        enrichment.updated_at = time.time()
        with self._lock:
            self._cache[key] = enrichment
            self._in_flight.discard(key)
            if enrichment.status == "ready" and enrichment.registration:
                self._aircraft_retries.pop(key, None)
            pending_cs = self._pending_route.pop(key, None)

        if pending_cs and enrichment.status == "ready" and not enrichment.route:
            self.maybe_route(key, pending_cs)

    def _set_status(self, icao: str, status: LookupStatus) -> None:
        key = _norm_icao(icao)
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                entry.status = status
                entry.updated_at = time.time()

    def _fetch_aircraft(self, icao: str) -> AircraftEnrichment:
        result = hexdb.lookup_aircraft_by_hex(icao)
        if result.outcome == LookupOutcome.OK and result.aircraft is not None:
            ac = result.aircraft
            return AircraftEnrichment(
                icao=icao,
                status="ready",
                registration=ac.registration,
                manufacturer=ac.manufacturer,
                aircraft_type=ac.aircraft_type,
                icao_type_code=ac.icao_type_code,
                operator=ac.operator,
                owner=ac.owner,
            )

        if result.outcome == LookupOutcome.NOT_FOUND:
            return AircraftEnrichment(
                icao=icao,
                status="error",
                error="Not in lookup database",
            )

        with self._lock:
            attempt = self._aircraft_retries.get(icao, 0) + 1
            self._aircraft_retries[icao] = attempt
        if attempt < _MAX_AIRCRAFT_RETRIES:
            return AircraftEnrichment(
                icao=icao,
                status="queued",
                error="Retrying lookup…",
            )
        return AircraftEnrichment(
            icao=icao,
            status="error",
            error="Lookup unavailable — try again later",
        )

    def _fetch_route_only(
        self, icao: str, callsign: str, prior: AircraftEnrichment
    ) -> AircraftEnrichment:
        route_info = hexdb.lookup_route_by_callsign(callsign)
        return AircraftEnrichment(
            icao=icao,
            status="ready",
            registration=prior.registration,
            manufacturer=prior.manufacturer,
            aircraft_type=prior.aircraft_type,
            icao_type_code=prior.icao_type_code,
            operator=prior.operator,
            owner=prior.owner,
            flight=route_info.flight if route_info else callsign,
            route=route_info.route if route_info else "",
            departure=route_info.departure if route_info else "",
            destination=route_info.destination if route_info else "",
        )
