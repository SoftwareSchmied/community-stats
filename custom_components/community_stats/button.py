"""Manual refresh through the same cache and quota controls."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CommunityStatsEntry
from .coordinator import CommunityStatsCoordinator
from .entity import CommunityStatsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CommunityStatsEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([RefreshButton(entry.runtime_data)])


class RefreshButton(CommunityStatsEntity, ButtonEntity):
    """Request a refresh without bypassing provider limits."""

    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CommunityStatsCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_refresh"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
