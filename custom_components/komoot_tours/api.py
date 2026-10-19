"""Asynchroner Client fuer die INOFFIZIELLE Komoot-Schnittstelle (kann jederzeit brechen)."""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import API_BASE, MAX_PAGES, PAGE_SIZE


class KomootError(Exception):
    """Basisfehler."""


class KomootAuthError(KomootError):
    """E-Mail oder Passwort falsch."""


class KomootConnectionError(KomootError):
    """Komoot nicht erreichbar oder unerwartete Antwort."""


class KomootNoTrack(KomootError):
    """Zu dieser Tour gibt es keine Koordinaten."""


class KomootClient:
    """Meldet sich per E-Mail/Passwort an und liest aufgezeichnete Touren."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self.user_id: str | None = None
        self._token: str | None = None

    async def _get(self, url: str, user: str, secret: str) -> dict[str, Any]:
        try:
            async with self._session.get(
                url,
                auth=aiohttp.BasicAuth(user, secret),
                headers={"Accept": "application/hal+json,application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (401, 403) and user == self._email:
                    raise KomootAuthError("Anmeldung abgelehnt")
                if resp.status in (401, 403):
                    # Token abgelaufen -> beim naechsten Versuch neu anmelden
                    self._token = None
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except KomootError:
            raise
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise KomootAuthError(f"HTTP {err.status}") from err
            raise KomootConnectionError(f"HTTP {err.status}") from err
        except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError, ValueError) as err:
            raise KomootConnectionError(str(err) or type(err).__name__) from err

    async def async_login(self) -> str:
        """Anmelden; liefert die Komoot-Benutzer-ID."""
        data = await self._get(
            f"{API_BASE}/v006/account/email/{quote(self._email, safe='')}/",
            self._email,
            self._password,
        )
        try:
            self.user_id = str(data["username"])
            self._token = data["password"]
        except KeyError as err:
            raise KomootConnectionError("Unerwartete Anmeldeantwort") from err
        return self.user_id

    async def _authed_get(self, url: str) -> dict[str, Any]:
        if self._token is None or self.user_id is None:
            await self.async_login()
        assert self.user_id is not None and self._token is not None  # noqa: S101
        try:
            return await self._get(url, self.user_id, self._token)
        except KomootAuthError:
            # Token koennte abgelaufen sein: einmal neu anmelden
            await self.async_login()
            return await self._get(url, self.user_id, self._token)

    async def async_get_tours(self) -> tuple[list[dict[str, Any]], int | None]:
        """Alle aufgezeichneten Touren (ohne Duplikate) und die gemeldete Gesamtzahl."""
        tours: list[dict[str, Any]] = []
        seen: set[Any] = set()
        total: int | None = None
        if self.user_id is None:
            await self.async_login()
        for page in range(MAX_PAGES):
            url = (
                f"{API_BASE}/v007/users/{self.user_id}/tours/"
                f"?type=tour_recorded&sort_field=date&sort_direction=desc"
                f"&limit={PAGE_SIZE}&page={page}"
            )
            data = await self._authed_get(url)
            if total is None:
                total = (data.get("page") or {}).get("totalElements")
            for tour in (data.get("_embedded") or {}).get("tours", []):
                if tour.get("id") not in seen:
                    seen.add(tour.get("id"))
                    tours.append(tour)
            if page + 1 >= (data.get("page") or {}).get("totalPages", 1):
                break
        return tours, total

    async def async_get_track(self, tour_id: Any) -> list[list[float]]:
        """Rohe Koordinaten [[lat, lng], ...]. KomootNoTrack, wenn es keine gibt."""
        points: list[list[float]] = []
        for url in (
            f"{API_BASE}/v007/tours/{tour_id}/coordinates",
            f"{API_BASE}/v007/tours/{tour_id}?_embedded=coordinates",
        ):
            try:
                data = await self._authed_get(url)
            except KomootConnectionError as err:
                if str(err) in ("HTTP 404", "HTTP 410"):
                    continue
                raise
            except KomootAuthError:
                continue  # 403 bei fremden/privaten Touren: naechsten Weg versuchen
            items = data.get("items")
            if not isinstance(items, list):
                items = ((data.get("_embedded") or {}).get("coordinates") or {}).get("items") or []
            points = [
                [float(c["lat"]), float(c["lng"])] for c in items if "lat" in c and "lng" in c
            ]
            if points:
                return points
        raise KomootNoTrack(str(tour_id))
