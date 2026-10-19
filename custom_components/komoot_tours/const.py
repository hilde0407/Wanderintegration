"""Konstanten der Komoot-Touren-Integration."""
from __future__ import annotations

DOMAIN = "komoot_tours"

API_BASE = "https://api.komoot.de"
PAGE_SIZE = 50
MAX_PAGES = 60  # Sicherheitsgrenze: 3000 Touren

CONF_SPORTS = "sports"
CONF_NAME_FILTER = "name_filter"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_LOAD_TRACKS = "load_tracks"

DEFAULT_SCAN_INTERVAL = 60  # Minuten
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 1440

TRACK_TOLERANCE = 0.00012  # Grad, ca. 13 m
TRACK_PAUSE = 0.6  # Sekunden zwischen zwei Routen-Abrufen (schont die Komoot-Schnittstelle)
TRACK_MAX_ERRORS = 5

PANEL_URL_PATH = "komoot-tours"
STATIC_URL = "/komoot_tours_static"
API_URL = "/api/komoot_tours"

# Bekannte Sportarten bei Komoot: Schluessel -> (Deutsch, Englisch)
SPORT_LABELS: dict[str, tuple[str, str]] = {
    "hike": ("Wandern", "Hiking"),
    "mountaineering": ("Bergsteigen", "Mountaineering"),
    "snowshoe": ("Schneeschuhwandern", "Snowshoeing"),
    "jogging": ("Laufen", "Running"),
    "racebike": ("Rennrad", "Road cycling"),
    "e_racebike": ("E-Rennrad", "E-road cycling"),
    "touringbicycle": ("Radtour", "Bike touring"),
    "e_touringbicycle": ("E-Radtour", "E-bike touring"),
    "citybike": ("Stadtrad", "City bike"),
    "mtb": ("Mountainbike", "Mountain biking"),
    "mtb_easy": ("Mountainbike leicht", "Mountain biking easy"),
    "mtb_advanced": ("Mountainbike schwer", "Mountain biking advanced"),
    "e_mtb": ("E-Mountainbike", "E-mountain biking"),
    "e_mtb_easy": ("E-Mountainbike leicht", "E-mountain biking easy"),
    "e_mtb_advanced": ("E-Mountainbike schwer", "E-mountain biking advanced"),
    "downhillbike": ("Downhill", "Downhill biking"),
    "gravelbike": ("Gravelbike", "Gravel biking"),
    "skialpin": ("Skifahren", "Alpine skiing"),
    "skitour": ("Skitour", "Ski touring"),
    "nordic": ("Langlauf", "Cross-country skiing"),
    "climbing": ("Klettern", "Climbing"),
    "inlineskates": ("Inlineskaten", "Inline skating"),
    "kayaking": ("Kajak", "Kayaking"),
    "canoe": ("Kanu", "Canoeing"),
    "sup": ("Stand-up-Paddling", "Stand-up paddling"),
    "sailing": ("Segeln", "Sailing"),
    "unicycle": ("Einrad", "Unicycling"),
    "other": ("Andere Sportarten", "Other sports"),
}
