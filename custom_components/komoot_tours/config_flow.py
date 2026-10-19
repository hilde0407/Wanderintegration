"""Einrichtung per Oberflaeche: Anmeldung, erneute Anmeldung, Optionen (Filter)."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import KomootAuthError, KomootClient, KomootConnectionError
from .const import (
    CONF_LOAD_TRACKS,
    CONF_NAME_FILTER,
    CONF_SCAN_INTERVAL,
    CONF_SPORTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SPORT_LABELS,
)

_LOGGER = logging.getLogger(__name__)


async def _validate(hass, email: str, password: str) -> str:
    client = KomootClient(async_get_clientsession(hass), email, password)
    return await client.async_login()


class KomootConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> KomootOptionsFlow:
        return KomootOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            try:
                user_id = await _validate(self.hass, email, user_input[CONF_PASSWORD])
            except KomootAuthError:
                errors["base"] = "invalid_auth"
            except KomootConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unerwarteter Fehler bei der Anmeldung")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=email, data={CONF_EMAIL: email, CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=(user_input or {}).get(CONF_EMAIL, "")): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                user_id = await _validate(self.hass, entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            except KomootAuthError:
                errors["base"] = "invalid_auth"
            except KomootConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
                    )
                }
            ),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )


class KomootOptionsFlow(OptionsFlow):
    """Filter fuer die Sensoren, Abrufintervall und Routen-Download."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        german = self.hass.config.language.startswith("de")
        seen: dict[str, int] = {}
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator and coordinator.data:
            for tour in coordinator.data.tours:
                seen[tour["sport"]] = seen.get(tour["sport"], 0) + 1
        keys = sorted(
            set(SPORT_LABELS) | set(seen) | set(self.config_entry.options.get(CONF_SPORTS, [])),
            key=lambda k: (-seen.get(k, 0), k),
        )

        def label(key: str) -> str:
            name = SPORT_LABELS.get(key, (key, key))[0 if german else 1]
            return f"{name} ({seen[key]})" if key in seen else name

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SPORTS, default=options.get(CONF_SPORTS, [])
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=k, label=label(k)) for k in keys],
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_NAME_FILTER, description={"suggested_value": options.get(CONF_NAME_FILTER, "")}
                ): TextSelector(),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=5,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_LOAD_TRACKS, default=options.get(CONF_LOAD_TRACKS, True)
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
