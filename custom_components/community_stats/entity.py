"""Common device grouping for a monitored project."""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CommunityStatsCoordinator


class CommunityStatsEntity(CoordinatorEntity[CommunityStatsCoordinator]):
    """All project entities share one service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CommunityStatsCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer="Community Stats",
            model="Project statistics",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=(
                f"https://github.com/{coordinator.repository}"
                if coordinator.repository
                else "https://analytics.home-assistant.io/"
            ),
        )
