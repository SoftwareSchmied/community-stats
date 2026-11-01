"""Community Stats: reported installations and release asset downloads."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import CommunityStatsCoordinator

type CommunityStatsEntry = ConfigEntry[CommunityStatsCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CommunityStatsEntry) -> bool:
    """Set up one project; additional projects use additional entries."""
    if CONF_ACCESS_TOKEN in entry.options and CONF_ACCESS_TOKEN in entry.data:
        # Clean up credentials that were overridden or removed in older versions.
        hass.config_entries.async_update_entry(
            entry,
            data={key: value for key, value in entry.data.items() if key != CONF_ACCESS_TOKEN},
        )
    coordinator = CommunityStatsCoordinator(hass, entry)
    await coordinator.async_load_tracking()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    entry.async_on_unload(coordinator.cancel_retry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CommunityStatsEntry) -> bool:
    """Unload platform entities and scheduled updates."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed settings without restarting Home Assistant."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove only this project's tracking metadata, never Recorder history."""
    from homeassistant.helpers.storage import Store

    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
