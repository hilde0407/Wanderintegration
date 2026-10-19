# Komoot Touren für Home Assistant

Liest deine **aufgezeichneten Komoot-Touren aller Sportarten** und stellt sie in Home Assistant bereit:

- **Sensoren** für letzte Tour, Touren und Kilometer (Monat, Jahr, Vorjahr, gesamt), Höhenmeter und Dauer
- **Filter** nach Sportart und Namen (für die Sensoren, in den Optionen einstellbar)
- **Seitenleisten-Eintrag „Komoot“** mit
  - **Karte** (Startpunkte und Routen, Vektorkarte der OpenStreetMap Foundation, farbig nach Sportart),
  - **Statistik** mit Jahres- und Monatsbalken, Jahresverlauf im Vergleich zu früheren Jahren, Auswertung nach Sportart und Bestwerten,
  - **Tourenliste** mit Suche und Sortierung,
  - Filterleiste für **Jahr** und **Sportarten** (mehrere gleichzeitig wählbar)
- Dienste: `komoot_tours.refresh`, `komoot_tours.fetch_tracks`, `komoot_tours.get_statistics`

> **Hinweis:** Die Integration nutzt die **inoffizielle** Komoot-Schnittstelle. Sie kann sich jederzeit ändern oder wegfallen. Das Projekt ist nicht mit Komoot verbunden.

## Installation

### Über HACS (benutzerdefiniertes Repository)
1. HACS → Drei-Punkte-Menü → *Benutzerdefinierte Repositories* → `https://github.com/hilde0407/Wanderintegration` einfügen, Kategorie *Integration*. (HACS kann nur **öffentliche** Repositories einbinden. Ist das Repository privat, muss es dafür öffentlich gestellt werden.)
2. „Komoot Touren“ herunterladen und Home Assistant **neu starten**.

### Manuell
Ordner `custom_components/komoot_tours` nach `/config/custom_components/komoot_tours` kopieren und Home Assistant neu starten.

## Einrichten
*Einstellungen → Geräte & Dienste → Integration hinzufügen → Komoot Touren* und mit E-Mail und Passwort anmelden.
Konten, die nur über Google oder Apple angelegt wurden, brauchen zuerst ein Passwort bei Komoot.

Danach erscheint links in der Seitenleiste der Eintrag **Komoot**.

### Optionen (Zahnrad an der Integration)
| Option | Bedeutung |
|---|---|
| Sportarten | Welche Sportarten die **Sensoren** zählen. Leer = alle. |
| Namensfilter | Optional je Sportart, Format `sportart:Text1\|Text2`, mehrere mit Komma. Beispiel: `other:Amazfit Balance 2\|Hiking` zählt Touren der Sportart *other* nur, wenn der Name einen der Texte enthält. |
| Abrufintervall | Minuten zwischen zwei Abrufen (Standard 60). |
| Routen laden | Lädt die Routen für die Karte im Hintergrund. |

Die Seite „Komoot“ zeigt **immer alle** Touren und hat eigene Filter. Die Optionen betreffen nur die Sensoren.

Beispiel für „nur Wandern“ wie bisher mit dem Skript: Sportarten `hike`, `mountaineering`, `snowshoe`, `other`, Namensfilter `other:Amazfit Balance 2|Hiking`.

## Routen
Komoot liefert jede Route einzeln. Die Integration lädt sie nach jedem Abruf im Hintergrund (neueste zuerst, etwa zwei pro Sekunde) und speichert sie in `.storage`. Bei einigen hundert Touren dauert das erste Laden einige Minuten. Der Fortschritt steht im Sensor „Geladene Routen“ und unten links auf der Karte. Die Linien werden auf etwa 13 Meter vereinfacht.

## Sensoren
Letzte Tour (mit Attributen), Datum, Strecke und Aufstieg der letzten Tour, Touren diesen Monat / dieses Jahr / gesamt, Strecke diesen Monat / dieses Jahr / letztes Jahr / gesamt, Aufstieg und Dauer dieses Jahr, Geladene Routen (Diagnose). Monats- und Jahreswechsel werden beim nächsten Abruf übernommen.

## Dienste
- `komoot_tours.refresh` – sofort abrufen
- `komoot_tours.fetch_tracks` – fehlende Routen nachladen (`force: true` lädt alle neu)
- `komoot_tours.get_statistics` – liefert Summen gesamt, je Jahr, Monat und Sportart, optional für ein Jahr (`year`) und Sportarten (`sport`), unabhängig von den Sensorfiltern

## Oberfläche in einem Dashboard
Die Seite lässt sich auch als Karte *Webseite* einbinden: URL `/komoot_tours_static/index.html`.

## Datenschutz und Sicherheit
- E-Mail und Passwort liegen wie bei jeder Integration in der Konfiguration von Home Assistant (und damit in Sicherungen).
- Touren und Routen werden nur über **authentifizierte** Endpunkte (`/api/komoot_tours/...`) ausgeliefert. Angemeldete Benutzer von Home Assistant können sie sehen, auch Nicht-Administratoren.
- Routen enthalten Wohn- und Aufenthaltsorte. Teile Sicherungen und Screenshots entsprechend vorsichtig.
- Die Karte lädt Bibliotheken von `unpkg.com`, Kartenkacheln von `vector.openstreetmap.org` und Schriften und Symbole von `tiles.versatiles.org` direkt im Browser. Fallback: OpenTopoMap. Die Kartennutzung unterliegt der [Nutzungsrichtlinie der OSMF](https://operations.osmfoundation.org/policies/vector/).

## Von dem Skript mit `command_line` umsteigen
Die Einträge unter `command_line:` für `komoot_tours.py`, den Ordner `/config/komoot/` und `/config/www/komoot/` kannst du nach der Einrichtung entfernen. Dashboard-Karten, die `sensor.komoot_*` des Skripts nutzten, müssen auf die neuen Sensoren umgestellt werden.

## Entwicklung
```
pip install pytest-homeassistant-custom-component home-assistant-frontend
pytest
```
