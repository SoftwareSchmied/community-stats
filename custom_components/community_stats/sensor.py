"""Numeric statistics with identities bound to exact versions."""

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import CommunityStatsEntry
from .const import CORE_URL, CUSTOM_URL
from .coordinator import CommunityStatsCoordinator
from .entity import CommunityStatsEntity
from .models import version_key

STATUS_OPTIONS = [
    "ok",
    "disabled",
    "cannot_connect",
    "invalid_data",
    "not_found",
    "rate_limited",
    "invalid_auth",
    "access_denied",
    "no_matching_assets",
    "repository_moved",
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CommunityStatsEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add totals, diagnostic sensors and all tracked versions."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    known: set[tuple[str, str]] = set()
    for source in ("installations", "downloads"):
        if coordinator.enabled(source):
            entities.append(CountSensor(coordinator, source))
            entities.extend(
                DiagnosticSensor(coordinator, source, kind) for kind in ("status", "last_success")
            )
    if coordinator.repository:
        entities.extend(
            DiagnosticSensor(coordinator, "downloads", kind) for kind in ("remaining", "retry_at")
        )
    async_add_entities(entities)

    @callback
    def async_add_versions() -> None:
        new_entities = []
        for source in ("installations", "downloads"):
            for version in coordinator.known_versions(source):
                key = (source, version)
                if key not in known:
                    known.add(key)
                    new_entities.append(CountSensor(coordinator, source, version))
        if new_entities:
            async_add_entities(new_entities)

    async_add_versions()
    entry.async_on_unload(coordinator.async_add_listener(async_add_versions))


class CountSensor(CommunityStatsEntity, SensorEntity):
    """A snapshot count; decreases are valid measurements, never meter resets."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(
        self, coordinator: CommunityStatsCoordinator, source: str, version: str | None = None
    ) -> None:
        super().__init__(coordinator)
        self.source = source
        self.version = version
        self._attr_native_unit_of_measurement = source
        self._attr_translation_key = f"{source}_{'version' if version is not None else 'total'}"
        self._attr_translation_placeholders = {"version": version} if version is not None else {}
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{source}_{coordinator.scopes[source]}_"
            f"{version_key(version) if version is not None else 'total'}"
        )

    @property
    def available(self) -> bool:
        state = self.coordinator.states[self.source]
        return super().available and state.status == "ok" and self.native_value is not None

    @property
    def native_value(self) -> int | None:
        counts = self.coordinator.states[self.source].counts
        return counts.total if self.version is None else counts.versions.get(self.version)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        if self.source == "installations":
            attributes["source"] = (
                CUSTOM_URL if self.coordinator.analytics_source == "custom" else CORE_URL
            )
            attributes["integration_domain"] = self.coordinator.integration_domain
            if self.version is not None:
                attributes["version"] = self.version
        else:
            attributes["source"] = f"https://github.com/{self.coordinator.repository}/releases"
            attributes["asset_patterns"] = self.coordinator.patterns
            if self.version is not None:
                attributes["release_tag"] = self.version
        return attributes


class DiagnosticSensor(CommunityStatsEntity, SensorEntity):
    """Expose source status without putting secrets into diagnostics or logs."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CommunityStatsCoordinator, source: str, kind: str) -> None:
        super().__init__(coordinator)
        self.source = source
        self.kind = kind
        self._attr_translation_key = f"{source}_{kind}"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{source}_{kind}"
        if kind == "status":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = STATUS_OPTIONS
        elif kind in ("last_success", "retry_at"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif kind == "remaining":
            self._attr_native_unit_of_measurement = "requests"
            self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> str | int | datetime | None:
        state = self.coordinator.states[self.source]
        if self.kind == "status":
            return state.status
        if self.kind == "last_success":
            return state.last_success
        if self.kind == "remaining":
            return self.coordinator.github.remaining
        if state.retry_at:
            return dt_util.utc_from_timestamp(state.retry_at)
        return None
