"""Authentifizierte Datenendpunkte fuer die Oberflaeche (Touren, Routen)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import API_URL, DOMAIN

if TYPE_CHECKING:
    from .coordinator import KomootCoordinator


def _coordinator(hass: HomeAssistant, entry_id: str) -> KomootCoordinator | None:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
        return None
    return entry.runtime_data


class KomootEntriesView(HomeAssistantView):
    url = f"{API_URL}/entries"
    name = "api:komoot_tours:entries"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entries = [
            {"entry_id": e.entry_id, "title": e.title}
            for e in hass.config_entries.async_entries(DOMAIN)
            if hasattr(e, "runtime_data")
        ]
        return self.json({"entries": entries, "language": hass.config.language})


class KomootToursView(HomeAssistantView):
    url = API_URL + "/{entry_id}/tours"
    name = "api:komoot_tours:tours"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        coordinator = _coordinator(request.app["hass"], entry_id)
        if coordinator is None or coordinator.data is None:
            return self.json_message("Unbekannter oder nicht geladener Eintrag", 404)
        data = coordinator.data
        return self.json(
            {
                "updated": data.updated.isoformat(),
                "api_total": data.api_total,
                "tracks_total": len(data.tours),
                "tracks_loaded": coordinator.tracks_loaded,
                "tracks_error": coordinator.track_error,
                "tours": [
                    {**t, "track": bool(coordinator.tracks.get(str(t["id"])))}
                    for t in data.tours
                ],
            }
        )


class KomootTracksView(HomeAssistantView):
    url = API_URL + "/{entry_id}/tracks"
    name = "api:komoot_tours:tracks"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        coordinator = _coordinator(request.app["hass"], entry_id)
        if coordinator is None:
            return self.json_message("Unbekannter oder nicht geladener Eintrag", 404)
        wanted = [i for i in request.query.get("ids", "").split(",") if i][:200]
        return self.json({i: coordinator.tracks[i] for i in wanted if coordinator.tracks.get(i)})
