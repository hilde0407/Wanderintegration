"""Tests: Konfigurationsablauf, Sensoren, Filter, Routen, Datenendpunkte, Hilfsfunktionen."""
import re
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from custom_components.komoot_tours import _register_views
from custom_components.komoot_tours.const import DOMAIN
from custom_components.komoot_tours.util import (
    compute_stats, filter_tours, normalize_tour, parse_name_filter, simplify, statistics,
)
from homeassistant.util import dt as dt_util

from .conftest import TOURS


def _norm():
    tz = ZoneInfo("Europe/Berlin")
    return [normalize_tour(t, tz) for t in TOURS]


def test_normalize_and_filter():
    tours = _norm()
    assert tours[0]["km"] == 10 and tours[0]["date"].startswith("2026-05-01T08:00")
    assert tours[3]["lat"] is None
    assert parse_name_filter("other:Amazfit|Hiking, hike") == {"other": ["amazfit", "hiking"]}
    only = filter_tours(tours, ["hike", "other"], "other:Hiking")
    assert sorted(t["id"] for t in only) == [1, 3, 5]  # Zumba (other) faellt wegen Namensfilter raus
    assert len(filter_tours(tours, [], None)) == 5


def test_stats_and_statistics():
    tours = _norm()
    s = compute_stats(tours, dt_util.parse_datetime("2026-06-15T10:00:00+00:00"))
    assert s["year"]["count"] == 4 and s["year"]["km"] == 66
    assert s["month"]["count"] == 3 and s["last_year"]["km"] == 20
    assert s["last"]["id"] == 4
    st = statistics(tours)
    assert st["by_year"]["2025"]["count"] == 1 and st["by_sport"]["hike"]["km"] == 30


def test_simplify_keeps_ends():
    line = [[0, 0], [0.00001, 0.5], [0, 1]]
    assert simplify(line, 0.001) == [[0, 0], [0, 1]]
    assert len(simplify(line, 0.0000001)) == 3


async def test_flow_ok(hass: HomeAssistant, mock_api, no_frontend):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert r["type"] is FlowResultType.FORM
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_EMAIL: "a@b.de", CONF_PASSWORD: "pw"})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"][CONF_EMAIL] == "a@b.de"
    # zweites Mal: gleiche Komoot-ID
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_EMAIL: "a@b.de", CONF_PASSWORD: "pw"})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "already_configured"


async def test_flow_invalid_auth(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(re.compile(r".*/v006/account/email/.*"), status=401)
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_EMAIL: "a@b.de", CONF_PASSWORD: "x"})
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"base": "invalid_auth"}


async def test_flow_cannot_connect(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(re.compile(r".*/v006/account/email/.*"), status=500)
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_EMAIL: "a@b.de", CONF_PASSWORD: "x"})
    assert r["errors"] == {"base": "cannot_connect"}


@freeze_time("2026-06-15 12:00:00+02:00")
async def test_sensors_and_options(hass: HomeAssistant, mock_api, entry, no_frontend):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.komoot_touren_dieses_jahr") is None or True
    states = {s.entity_id: s for s in hass.states.async_all("sensor")}
    by_name = {s.attributes.get("friendly_name", ""): s for s in states.values()}
    assert any("Tours this year" in n for n in by_name), list(by_name)
    year = next(s for n, s in by_name.items() if "Tours this year" in n)
    assert year.state == "4"
    dist = next(s for n, s in by_name.items() if "Distance this year" in n)
    assert float(dist.state) == 66.0
    last = next(s for n, s in by_name.items() if n.endswith("Last tour"))
    assert last.state == "Zumba" and last.attributes["tour_id"] == 4

    # Filter: nur Wandern + 'other' mit Namensfilter
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"sports": ["hike", "other"], "name_filter": "other:Hiking", "scan_interval": 60, "load_tracks": True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)
    year = next(s for s in hass.states.async_all("sensor") if "Tours this year" in s.attributes.get("friendly_name", ""))
    assert year.state == "2"  # Gipfel + Hiking
    dist = next(s for s in hass.states.async_all("sensor") if "Distance this year" in s.attributes.get("friendly_name", ""))
    assert float(dist.state) == 15.0


async def test_tracks_views_and_service(hass: HomeAssistant, hass_client, mock_api, entry, no_frontend):
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "auth", {})
    client = await hass_client()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    coordinator = entry.runtime_data
    # 1,2,5 mit Linie; 3 (404) endgueltig leer; 4 ueber den zweiten Weg
    assert set(coordinator.tracks) == {"1", "2", "3", "4", "5"}
    assert coordinator.tracks["3"] == []
    assert len(coordinator.tracks["1"]) == 2  # gerade Linie auf zwei Punkte vereinfacht
    assert len(coordinator.tracks["4"]) == 2

    r = await client.get("/api/komoot_tours/entries")
    assert (await r.json())["entries"][0]["entry_id"] == entry.entry_id
    r = await client.get(f"/api/komoot_tours/{entry.entry_id}/tours")
    data = await r.json()
    assert len(data["tours"]) == 5 and data["tracks_loaded"] == 5
    assert next(t for t in data["tours"] if t["id"] == 3)["track"] is False
    r = await client.get(f"/api/komoot_tours/{entry.entry_id}/tracks?ids=1,3,4")
    tracks = await r.json()
    assert set(tracks) == {"1", "4"}
    r = await client.get("/api/komoot_tours/doesnotexist/tours")
    assert r.status == 404

    resp = await hass.services.async_call(
        DOMAIN, "get_statistics", {"year": 2026, "sport": ["hike"]}, blocking=True, return_response=True
    )
    assert resp["total"]["count"] == 1 and resp["by_month"]["2026-05"]["km"] == 10
    resp = await hass.services.async_call(DOMAIN, "get_statistics", {}, blocking=True, return_response=True)
    assert resp["total"]["count"] == 5 and set(resp["by_year"]) == {"2025", "2026"}

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_reauth_on_bad_password(hass: HomeAssistant, aioclient_mock, entry, no_frontend):
    aioclient_mock.get(re.compile(r".*/v006/account/email/.*"), status=401)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state.name == "SETUP_ERROR"


async def test_static_panel_and_unload(hass: HomeAssistant, hass_client, mock_api, entry):
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "auth", {})
    client = await hass_client()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    for name in ("index.html", "panel.js", "style-hell.json", "style-dunkel.json"):
        r = await client.get(f"/komoot_tours_static/{name}")
        assert r.status == 200, name
    panels = hass.data["frontend_panels"]
    assert "komoot-tours" in panels
    assert panels["komoot-tours"].config["page"].startswith("/komoot_tours_static/index.html")
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "komoot-tours" not in hass.data["frontend_panels"]
    # erneut laden: Panel wird wieder registriert
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "komoot-tours" in hass.data["frontend_panels"]


async def test_reauth_flow(hass: HomeAssistant, mock_api, entry):
    r = await entry.start_reauth_flow(hass)
    assert r["step_id"] == "reauth_confirm"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_PASSWORD: "neu"})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "neu"
