"""Koordinator: holt Touren regelmaessig und laedt Routen nach und nach im Hintergrund."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    KomootAuthError,
    KomootClient,
    KomootConnectionError,
    KomootNoTrack,
)
from .const import (
    CONF_LOAD_TRACKS,
    CONF_NAME_FILTER,
    CONF_SCAN_INTERVAL,
    CONF_SPORTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TRACK_MAX_ERRORS,
    TRACK_PAUSE,
    TRACK_TOLERANCE,
)
from .util import compute_stats, filter_tours, normalize_tour, simplify

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1


@dataclass
class KomootData:
    """Ergebnis eines Abrufs."""

    tours: list[dict[str, Any]]
    api_total: int | None
    updated: datetime
    stats: dict[str, Any] = field(default_factory=dict)


class KomootCoordinator(DataUpdateCoordinator[KomootData]):
    """Verwaltet Touren (Abruf per Intervall) und Routen (Hintergrundaufgabe)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: KomootClient) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}.tracks"
        )
        self.tracks: dict[str, list[list[float]]] = {}
        self._track_task: asyncio.Task | None = None
        self.track_error: str | None = None

    # ---- Hilfen ---------------------------------------------------------
    @property
    def options(self) -> dict[str, Any]:
        return self.config_entry.options

    def filtered_tours(self) -> list[dict[str, Any]]:
        """Touren gemaess der in den Optionen gesetzten Filter (fuer die Sensoren)."""
        if not self.data:
            return []
        return filter_tours(
            self.data.tours, self.options.get(CONF_SPORTS), self.options.get(CONF_NAME_FILTER)
        )

    def _build_stats(self, tours: list[dict[str, Any]]) -> dict[str, Any]:
        return compute_stats(
            filter_tours(
                tours, self.options.get(CONF_SPORTS), self.options.get(CONF_NAME_FILTER)
            ),
            dt_util.now(),
        )

    @property
    def tracks_loaded(self) -> int:
        if not self.data:
            return 0
        ids = {str(t["id"]) for t in self.data.tours}
        return sum(1 for key in self.tracks if key in ids)

    @property
    def tracks_with_line(self) -> int:
        return sum(1 for v in self.tracks.values() if v)

    # ---- Abruf ----------------------------------------------------------
    async def async_load_store(self) -> None:
        stored = await self._store.async_load()
        if stored and isinstance(stored.get("tracks"), dict):
            self.tracks = stored["tracks"]

    async def _async_update_data(self) -> KomootData:
        try:
            raw, total = await self.client.async_get_tours()
        except KomootAuthError as err:
            raise ConfigEntryAuthFailed("Komoot-Anmeldung abgelehnt") from err
        except KomootConnectionError as err:
            raise UpdateFailed(f"Komoot nicht erreichbar: {err}") from err

        tz = dt_util.get_default_time_zone()
        tours = [t for t in (normalize_tour(r, tz) for r in raw) if t]
        tours.sort(key=lambda t: (t["date"], str(t["id"])), reverse=True)
        data = KomootData(
            tours=tours,
            api_total=total,
            updated=dt_util.utcnow(),
            stats=self._build_stats(tours),
        )
        if self.options.get(CONF_LOAD_TRACKS, True):
            self.start_track_loading(tours=tours)
        return data

    def refresh_stats(self) -> None:
        """Kennzahlen neu berechnen, z. B. nach geaenderten Filteroptionen."""
        if self.data:
            self.data.stats = self._build_stats(self.data.tours)
            self.async_update_listeners()

    # ---- Routen ---------------------------------------------------------
    def start_track_loading(
        self, force: bool = False, tours: list[dict[str, Any]] | None = None
    ) -> None:
        """Hintergrundaufgabe starten, die fehlende Routen nachlaedt."""
        if self._track_task and not self._track_task.done():
            return
        if tours is None:
            if not self.data:
                return
            tours = self.data.tours
        self._track_task = self.config_entry.async_create_background_task(
            self.hass, self._async_load_tracks(tours, force), f"{DOMAIN} routen"
        )

    async def _async_load_tracks(self, tours: list[dict[str, Any]], force: bool = False) -> None:
        todo = [
            t["id"]
            for t in tours
            if force or str(t["id"]) not in self.tracks
        ]
        if not todo:
            return
        _LOGGER.debug("Lade %s Routen von Komoot", len(todo))
        errors = 0
        since_save = 0
        for tour_id in todo:
            key = str(tour_id)
            try:
                raw = await self.client.async_get_track(tour_id)
                line = await self.hass.async_add_executor_job(simplify, raw, TRACK_TOLERANCE)
                self.tracks[key] = [[round(a, 5), round(b, 5)] for a, b in line]
                errors = 0
                self.track_error = None
            except KomootNoTrack:
                self.tracks[key] = []  # endgueltig: keine Koordinaten vorhanden
            except KomootAuthError:
                self.track_error = "Anmeldung fuer Routen abgelehnt"
                break
            except KomootConnectionError as err:
                errors += 1
                self.track_error = str(err)
                if errors >= TRACK_MAX_ERRORS:
                    _LOGGER.warning("Routen-Abruf abgebrochen: %s", err)
                    break
            since_save += 1
            if since_save >= 25:
                since_save = 0
                await self._async_save_tracks()
                self.async_update_listeners()
            await asyncio.sleep(TRACK_PAUSE)
        await self._async_save_tracks()
        self.async_update_listeners()

    async def _async_save_tracks(self) -> None:
        if self.data:
            valid = {str(t["id"]) for t in self.data.tours}
            self.tracks = {k: v for k, v in self.tracks.items() if k in valid}
        await self._store.async_save({"tracks": self.tracks})

    async def async_remove_store(self) -> None:
        await self._store.async_remove()
