"""Komoot Touren: aufgezeichnete Komoot-Touren aller Sportarten in Home Assistant."""
from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import panel_custom
from homeassistant.components.frontend import async_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import IntegrationNotFound, async_get_integration

from .api import KomootAuthError, KomootClient, KomootConnectionError
from .const import DOMAIN, PANEL_URL_PATH, STATIC_URL
from .coordinator import KomootCoordinator
from .http import KomootEntriesView, KomootToursView, KomootTracksView
from .util import filter_tours, statistics

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type KomootConfigEntry = ConfigEntry[KomootCoordinator]

SERVICE_REFRESH = "refresh"
SERVICE_FETCH_TRACKS = "fetch_tracks"
SERVICE_STATISTICS = "get_statistics"

_FRONTEND_DIR = Path(__file__).parent / "frontend"


async def _version(hass: HomeAssistant) -> str:
    """Version aus dem Manifest, ohne die Ereignisschleife zu blockieren."""
    try:
        return str((await async_get_integration(hass, DOMAIN)).version or "0")
    except IntegrationNotFound:
        return "0"


def _coordinators(hass: HomeAssistant, entry_id: str | None) -> list[KomootCoordinator]:
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if hasattr(e, "runtime_data")
    ]
    if entry_id:
        entries = [e for e in entries if e.entry_id == entry_id]
    if not entries:
        raise ServiceValidationError("Keine geladene Komoot-Integration gefunden")
    return [e.runtime_data for e in entries]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Dienste registrieren (einmal je Home Assistant)."""

    async def refresh(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call.data.get("config_entry")):
            await coordinator.async_request_refresh()

    async def fetch_tracks(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call.data.get("config_entry")):
            coordinator.start_track_loading(force=call.data["force"])

    async def get_statistics(call: ServiceCall) -> dict:
        coordinator = _coordinators(hass, call.data.get("config_entry"))[0]
        if not coordinator.data:
            raise ServiceValidationError("Noch keine Daten geladen")
        tours = coordinator.data.tours
        if call.data.get("sport"):
            tours = filter_tours(tours, call.data["sport"], None)
        if call.data.get("year"):
            tours = [t for t in tours if t["date"].startswith(str(call.data["year"]))]
        return statistics(tours)

    entry_field = {vol.Optional("config_entry"): cv.string}
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, refresh, vol.Schema(entry_field))
    hass.services.async_register(
        DOMAIN,
        SERVICE_FETCH_TRACKS,
        fetch_tracks,
        vol.Schema({**entry_field, vol.Optional("force", default=False): cv.boolean}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STATISTICS,
        get_statistics,
        vol.Schema(
            {
                **entry_field,
                vol.Optional("year"): vol.All(vol.Coerce(int), vol.Range(min=1990, max=2100)),
                vol.Optional("sport"): vol.All(cv.ensure_list, [cv.string]),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KomootConfigEntry) -> bool:
    client = KomootClient(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    coordinator = KomootCoordinator(hass, entry, client)
    await coordinator.async_load_store()
    try:
        await client.async_login()
    except KomootAuthError as err:
        raise ConfigEntryAuthFailed from err
    except KomootConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await _async_register_frontend(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: KomootConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: KomootConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        remaining = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id and hasattr(e, "runtime_data")
        ]
        if not remaining and hass.data.get(DOMAIN, {}).pop("panel", False):
            async_remove_panel(hass, PANEL_URL_PATH)
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: KomootConfigEntry) -> None:
    from homeassistant.helpers.storage import Store  # noqa: PLC0415

    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.tracks").async_remove()


@callback
def _register_views(hass: HomeAssistant) -> None:
    hass.http.register_view(KomootEntriesView())
    hass.http.register_view(KomootToursView())
    hass.http.register_view(KomootTracksView())


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Statische Seite, Datenendpunkte und Seitenleisten-Eintrag (einmalig)."""
    state = hass.data.setdefault(DOMAIN, {})
    if not state.get("static"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(_FRONTEND_DIR), cache_headers=False)]
        )
        _register_views(hass)
        state["static"] = True
    if not state.get("panel"):
        version = await _version(hass)
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name="komoot-tours-panel",
            frontend_url_path=PANEL_URL_PATH,
            module_url=f"{STATIC_URL}/panel.js?v={version}",
            sidebar_title="Komoot",
            sidebar_icon="mdi:hiking",
            require_admin=False,
            config={"page": f"{STATIC_URL}/index.html?v={version}"},
        )
        state["panel"] = True
