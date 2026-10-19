"""Sensoren mit Kennzahlen (gefiltert nach den Optionen der Integration)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import KomootCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KomootSensorDescription(SensorEntityDescription):
    value_fn: Callable[[KomootCoordinator], Any]
    attrs_fn: Callable[[KomootCoordinator], dict[str, Any]] | None = None


def _stat(period: str, field: str, scale: float = 1, ndigits: int | None = None):
    def fn(c: KomootCoordinator) -> Any:
        stats = c.data.stats if c.data else None
        if not stats:
            return None
        value = stats[period][field]
        if scale != 1:
            value = value / scale
        return round(value, ndigits) if ndigits is not None else value

    return fn


def _last(field: str):
    def fn(c: KomootCoordinator) -> Any:
        last = c.data.stats.get("last") if c.data and c.data.stats else None
        return last[field] if last else None

    return fn


def _last_date(c: KomootCoordinator) -> datetime | None:
    last = c.data.stats.get("last") if c.data and c.data.stats else None
    if not last:
        return None
    parsed = dt_util.parse_datetime(last["date"])
    return parsed.replace(tzinfo=dt_util.get_default_time_zone()) if parsed else None


def _last_attrs(c: KomootCoordinator) -> dict[str, Any]:
    last = c.data.stats.get("last") if c.data and c.data.stats else None
    if not last:
        return {}
    return {
        "tour_id": last["id"],
        "sport": last["sport"],
        "date": last["date"],
        "distance_km": last["km"],
        "duration_min": last["min"],
        "ascent_m": last["up"],
        "url": f"https://www.komoot.com/tour/{last['id']}",
    }


SENSORS: tuple[KomootSensorDescription, ...] = (
    KomootSensorDescription(
        key="last_tour", translation_key="last_tour", icon="mdi:map-marker-path",
        value_fn=_last("name"), attrs_fn=_last_attrs,
    ),
    KomootSensorDescription(
        key="last_tour_date", translation_key="last_tour_date",
        device_class=SensorDeviceClass.TIMESTAMP, value_fn=_last_date,
    ),
    KomootSensorDescription(
        key="last_tour_distance", translation_key="last_tour_distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE, state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value_fn=_last("km"),
    ),
    KomootSensorDescription(
        key="last_tour_ascent", translation_key="last_tour_ascent",
        native_unit_of_measurement=UnitOfLength.METERS, device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:elevation-rise",
        suggested_display_precision=0, value_fn=_last("up"),
    ),
    KomootSensorDescription(
        key="tours_month", translation_key="tours_month", native_unit_of_measurement="Touren",
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:counter", value_fn=_stat("month", "count"),
    ),
    KomootSensorDescription(
        key="tours_year", translation_key="tours_year", native_unit_of_measurement="Touren",
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:counter", value_fn=_stat("year", "count"),
    ),
    KomootSensorDescription(
        key="tours_total", translation_key="tours_total", native_unit_of_measurement="Touren",
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:counter", value_fn=_stat("total", "count"),
    ),
    *(
        KomootSensorDescription(
            key=f"distance_{period}", translation_key=f"distance_{period}",
            native_unit_of_measurement=UnitOfLength.KILOMETERS,
            device_class=SensorDeviceClass.DISTANCE, state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1, value_fn=_stat(period, "km"),
        )
        for period in ("month", "year", "last_year", "total")
    ),
    KomootSensorDescription(
        key="ascent_year", translation_key="ascent_year",
        native_unit_of_measurement=UnitOfLength.METERS, device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:elevation-rise",
        suggested_display_precision=0, value_fn=_stat("year", "up"),
    ),
    KomootSensorDescription(
        key="duration_year", translation_key="duration_year", native_unit_of_measurement=UnitOfTime.HOURS, device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:timer-outline",
        suggested_display_precision=1, value_fn=_stat("year", "min", scale=60),
    ),
    KomootSensorDescription(
        key="tracks_loaded", translation_key="tracks_loaded", native_unit_of_measurement="Routen",
        entity_category=EntityCategory.DIAGNOSTIC, icon="mdi:vector-polyline",
        value_fn=lambda c: c.tracks_with_line,
        attrs_fn=lambda c: {
            "tours_total": len(c.data.tours) if c.data else 0,
            "checked": c.tracks_loaded,
            "error": c.track_error,
            "komoot_reported_total": c.data.api_total if c.data else None,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator: KomootCoordinator = entry.runtime_data
    async_add_entities(KomootSensor(coordinator, entry, d) for d in SENSORS)


class KomootSensor(CoordinatorEntity[KomootCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: KomootSensorDescription

    def __init__(
        self, coordinator: KomootCoordinator, entry: ConfigEntry, description: KomootSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name="Komoot",
            manufacturer="Komoot",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.komoot.com/",
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator) if fn else None
