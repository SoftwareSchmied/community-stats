"""Redacted diagnostics for support."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant

from . import CommunityStatsEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CommunityStatsEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "configuration": async_redact_data(coordinator.settings, {CONF_ACCESS_TOKEN}),
        "sources": {
            source: {
                "status": state.status,
                "last_success": state.last_success,
                "retry_at": state.retry_at,
                "tracked_versions": (
                    coordinator.known_versions(source)
                    if source in ("installations", "downloads")
                    else []
                ),
            }
            for source, state in coordinator.states.items()
        },
        "github_remaining_at_last_response": coordinator.github.remaining,
        "github_schedule": {
            "mode": "round_robin" if coordinator.rotation else "configured_interval",
            "next_slot": (
                coordinator.rotation.scheduled_at(entry.entry_id) if coordinator.rotation else None
            ),
        },
    }
