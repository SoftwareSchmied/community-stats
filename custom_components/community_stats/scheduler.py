"""A persistent, shared rotation for GitHub projects without credentials."""

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ACCESS_TOKEN, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import CONF_REPOSITORY, DOMAIN, GITHUB_ROTATION_SECONDS

if TYPE_CHECKING:
    from .coordinator import CommunityStatsCoordinator


class GitHubRotation:
    """Reserve one project per time slot, including across reloads and restarts."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.store = Store(hass, 1, f"{DOMAIN}.github_rotation")
        self.projects: dict[str, CommunityStatsCoordinator] = {}
        self.last_turn: dict[str, float] = {}
        self.next_slot = 0.0
        self._loaded = False
        self._lock = asyncio.Lock()
        self._cancel: Callable[[], None] | None = None
        self._stopped = False
        self._unloaded: set[str] = set()
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_stop)

    async def async_register(self, coordinator: CommunityStatsCoordinator) -> None:
        """Register only projects with a repository and no configured token."""
        async with self._lock:
            if not self._loaded:
                stored = await self.store.async_load()
                if isinstance(stored, dict):
                    self.next_slot = stored.get("next_slot", 0.0)
                    self.last_turn = stored.get("last_turn", {})
                self._loaded = True
            self.projects[coordinator.entry.entry_id] = coordinator
            self._unloaded.discard(coordinator.entry.entry_id)
            self._schedule()

    @callback
    def unregister(self, coordinator: CommunityStatsCoordinator) -> None:
        """Unloading does not erase a project's place or reset the pause."""
        entry_id = coordinator.entry.entry_id
        if self.projects.get(entry_id) is coordinator:
            self.projects.pop(entry_id)
            self._unloaded.add(entry_id)
        self._schedule()

    def ordered_projects(self) -> list[str]:
        """Projects with no turn yet precede those least recently served."""
        candidates = dict.fromkeys(self.projects)
        # Startup order must not let an already served project jump the queue.
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            settings = {**entry.data, **entry.options}
            if (
                entry.entry_id not in self._unloaded
                and not entry.disabled_by
                and entry.state in (ConfigEntryState.NOT_LOADED, ConfigEntryState.SETUP_IN_PROGRESS)
                and settings.get(CONF_REPOSITORY)
                and not settings.get(CONF_ACCESS_TOKEN)
            ):
                candidates[entry.entry_id] = None
        return sorted(candidates, key=lambda entry_id: self.last_turn.get(entry_id, 0.0))

    def scheduled_at(self, entry_id: str) -> float | None:
        """Estimate a project's next slot, assuming membership stays the same."""
        ordered = self.ordered_projects()
        if entry_id not in ordered:
            return None
        return max(time.time(), self.next_slot) + ordered.index(entry_id) * GITHUB_ROTATION_SECONDS

    async def async_claim(self, coordinator: CommunityStatsCoordinator) -> bool:
        """Persist the reservation before allowing any statistics requests."""
        async with self._lock:
            ordered = self.ordered_projects()
            entry_id = coordinator.entry.entry_id
            now = time.time()
            if self._stopped or now < self.next_slot or not ordered or ordered[0] != entry_id:
                return False
            # Saving first prevents a restart during a fetch from opening another slot.
            turns = {**self.last_turn, entry_id: now}
            next_slot = now + GITHUB_ROTATION_SECONDS
            await self.store.async_save({"last_turn": turns, "next_slot": next_slot})
            self.last_turn = turns
            self.next_slot = next_slot
            self._schedule()
            return True

    @callback
    def _schedule(self) -> None:
        if self._cancel:
            self._cancel()
            self._cancel = None
        if self.projects and not self._stopped:
            pending = self.ordered_projects()[0] not in self.projects
            self._cancel = async_call_later(
                self.hass, max(60 if pending else 1, self.next_slot - time.time()), self._async_tick
            )

    async def _async_tick(self, _now: Any) -> None:
        self._cancel = None
        ordered = self.ordered_projects()
        try:
            if ordered and ordered[0] in self.projects and not self._stopped:
                await self.projects[ordered[0]].async_refresh_github()
        finally:
            self._schedule()

    @callback
    def _async_stop(self, _event: Any) -> None:
        self._stopped = True
        self._schedule()


@callback
def get_rotation(hass: HomeAssistant) -> GitHubRotation:
    """All anonymous projects in this instance share one persisted schedule."""
    data = hass.data.setdefault(DOMAIN, {})
    if "github_rotation" not in data:
        data["github_rotation"] = GitHubRotation(hass)
    return data["github_rotation"]
