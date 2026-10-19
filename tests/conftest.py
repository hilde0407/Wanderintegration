"""Gemeinsame Testhilfen."""
import re
from unittest.mock import patch

import pytest

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.komoot_tours.const import DOMAIN


def tour(i, sport, name, date, km, up=100, dur=3600, lat=47.0, lng=11.0):
    return {
        "id": i, "name": name, "sport": sport, "date": date, "distance": km * 1000,
        "duration": dur, "elevation_up": up, "elevation_down": up, "start_point": {"lat": lat, "lng": lng},
    }


TOURS = [
    tour(1, "hike", "Gipfel", "2026-05-01T08:00:00.000+02:00", 10, 500),
    tour(2, "touringbicycle", "Radtour", "2026-06-02T09:00:00.000+02:00", 50, 300),
    tour(3, "other", "Hiking", "2026-06-10T09:00:00.000+02:00", 5, 50),
    tour(4, "other", "Zumba", "2026-06-11T09:00:00.000+02:00", 1, 0, lat=None, lng=None),
    tour(5, "hike", "Alt", "2025-03-01T08:00:00.000+01:00", 20, 800),
]


@pytest.fixture(autouse=True)
def _auto(enable_custom_integrations):
    yield


@pytest.fixture
async def berlin(hass):
    await hass.config.async_set_time_zone("Europe/Berlin")


@pytest.fixture(autouse=True)
def fast_tracks():
    with patch("custom_components.komoot_tours.coordinator.TRACK_PAUSE", 0):
        yield


@pytest.fixture
def mock_api(aioclient_mock):
    aioclient_mock.get(re.compile(r".*/v006/account/email/.*"), json={"username": "123", "password": "tok"})
    aioclient_mock.get(
        re.compile(r".*/v007/users/123/tours/.*"),
        json={"page": {"totalPages": 1, "totalElements": len(TOURS)}, "_embedded": {"tours": TOURS}},
    )
    aioclient_mock.get(
        re.compile(r".*/v007/tours/(1|2|5)/coordinates"),
        json={"items": [{"lat": 47 + i * 0.001, "lng": 11, "alt": 0, "t": i} for i in range(50)]},
    )
    aioclient_mock.get(re.compile(r".*/v007/tours/3/coordinates"), status=404)
    aioclient_mock.get(re.compile(r".*/v007/tours/3\?_embedded=coordinates"), status=404)
    aioclient_mock.get(re.compile(r".*/v007/tours/4/coordinates"), json={"items": []})
    aioclient_mock.get(
        re.compile(r".*/v007/tours/4\?_embedded=coordinates"),
        json={"_embedded": {"coordinates": {"items": [{"lat": 1, "lng": 2}, {"lat": 1.5, "lng": 2.5}]}}},
    )
    return aioclient_mock


@pytest.fixture
def entry(hass, berlin):
    e = MockConfigEntry(
        domain=DOMAIN, title="a@b.de", unique_id="123",
        data={CONF_EMAIL: "a@b.de", CONF_PASSWORD: "pw"},
    )
    e.add_to_hass(hass)
    return e


@pytest.fixture
def no_frontend():
    yield  # Frontend, Panel und Views werden echt registriert
