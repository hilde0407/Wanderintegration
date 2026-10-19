"""Hilfsfunktionen: Normalisieren, Filtern, Aggregieren, Linien vereinfachen."""
from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

from homeassistant.util import dt as dt_util


def normalize_tour(raw: dict[str, Any], tz: tzinfo) -> dict[str, Any] | None:
    """Rohdaten einer Komoot-Tour in das interne, schlanke Format bringen."""
    raw_date = raw.get("date") or raw.get("changed_at")
    if not raw_date or raw.get("id") is None:
        return None
    parsed = dt_util.parse_datetime(raw_date)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    local = parsed.astimezone(tz)
    start = raw.get("start_point") or {}

    def num(key: str) -> float:
        try:
            return float(raw.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    def coord(value: Any) -> float | None:
        try:
            return round(float(value), 5)
        except (TypeError, ValueError):
            return None

    return {
        "id": raw["id"],
        "name": raw.get("name") or "",
        "sport": raw.get("sport") or "unknown",
        "date": local.strftime("%Y-%m-%dT%H:%M"),
        "km": round(num("distance") / 1000, 2),
        "min": round(num("duration") / 60),
        "up": round(num("elevation_up")),
        "down": round(num("elevation_down")),
        "lat": coord(start.get("lat")),
        "lng": coord(start.get("lng")),
    }


def parse_name_filter(spec: str | None) -> dict[str, list[str]]:
    """'other:Amazfit Balance 2|Hiking, hike' -> {'other': [...]} (nur Eintraege mit Namen)."""
    result: dict[str, list[str]] = {}
    for part in (spec or "").split(","):
        sport, _, needle = part.strip().partition(":")
        names = [n.strip().lower() for n in needle.split("|") if n.strip()]
        if sport.strip() and names:
            result[sport.strip()] = names
    return result


def filter_tours(
    tours: list[dict[str, Any]], sports: list[str] | None, name_filter: str | None
) -> list[dict[str, Any]]:
    """Touren nach Sportarten (leer = alle) und optionalem Namensfilter je Sportart."""
    needles = parse_name_filter(name_filter)
    selected = set(sports or [])
    out = []
    for tour in tours:
        sport = tour["sport"]
        if selected and sport not in selected:
            continue
        if sport in needles and not any(n in tour["name"].lower() for n in needles[sport]):
            continue
        out.append(tour)
    return out


def aggregate(tours: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(tours),
        "km": round(sum(t["km"] for t in tours), 1),
        "up": sum(t["up"] for t in tours),
        "min": sum(t["min"] for t in tours),
    }


def compute_stats(tours: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """Kennzahlen fuer Sensoren; 'now' muss in der lokalen Zeitzone vorliegen."""
    year = f"{now.year:04d}"
    last_year = f"{now.year - 1:04d}"
    month = f"{now.year:04d}-{now.month:02d}"
    ordered = sorted(tours, key=lambda t: (t["date"], str(t["id"])), reverse=True)
    return {
        "last": ordered[0] if ordered else None,
        "month": aggregate([t for t in tours if t["date"].startswith(month)]),
        "year": aggregate([t for t in tours if t["date"].startswith(year)]),
        "last_year": aggregate([t for t in tours if t["date"].startswith(last_year)]),
        "total": aggregate(tours),
    }


def statistics(tours: list[dict[str, Any]]) -> dict[str, Any]:
    """Ausfuehrliche Statistik (Service get_statistics): gesamt, je Jahr, Monat, Sportart."""
    by_year: dict[str, list] = {}
    by_month: dict[str, list] = {}
    by_sport: dict[str, list] = {}
    for t in tours:
        by_year.setdefault(t["date"][:4], []).append(t)
        by_month.setdefault(t["date"][:7], []).append(t)
        by_sport.setdefault(t["sport"], []).append(t)
    return {
        "total": aggregate(tours),
        "by_year": {k: aggregate(v) for k, v in sorted(by_year.items())},
        "by_month": {k: aggregate(v) for k, v in sorted(by_month.items())},
        "by_sport": {k: aggregate(v) for k, v in sorted(by_sport.items())},
    }


def simplify(points: list[list[float]], tolerance: float) -> list[list[float]]:
    """Douglas-Peucker (iterativ) fuer [[lat, lng], ...]."""
    n = len(points)
    if n < 3:
        return points
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        ay, ax = points[a]
        by, bx = points[b]
        dx, dy = bx - ax, by - ay
        norm = dx * dx + dy * dy
        best, idx = 0.0, None
        for i in range(a + 1, b):
            py, px = points[i]
            if norm == 0:
                d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:
                u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / norm))
                d = ((px - ax - u * dx) ** 2 + (py - ay - u * dy) ** 2) ** 0.5
            if d > best:
                best, idx = d, i
        if idx is not None and best > tolerance:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(points, keep, strict=True) if k]
