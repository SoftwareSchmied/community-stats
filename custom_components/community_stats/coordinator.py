"""Independent source updates and persistent version tracking."""

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import get_analytics, get_github
from .const import (
    CONF_INTEGRATION,
    CONF_INTERVAL,
    CONF_PATTERNS,
    CONF_PRERELEASE,
    CONF_REPOSITORY,
    CONF_SOURCE,
    CONF_TOP,
    DEFAULT_INTERVAL,
    DEFAULT_TOP,
    DOMAIN,
)
from .models import (
    SourceError,
    SourceState,
    parse_analytics,
    parse_downloads,
    parse_patterns,
    parse_repository_metrics,
    top_versions,
    version_key,
)

_LOGGER = logging.getLogger(__name__)


class CommunityStatsCoordinator(DataUpdateCoordinator[dict[str, SourceState]]):
    """Keep failures in one source from hiding the other source's values."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.settings = {**entry.data, **entry.options}
        self.integration_domain = self.settings.get(CONF_INTEGRATION, "")
        self.repository = self.settings.get(CONF_REPOSITORY, "")
        self.analytics_source = self.settings.get(CONF_SOURCE, "custom")
        self.patterns = parse_patterns(self.settings.get(CONF_PATTERNS, ""))
        self.github = get_github(hass, self.settings.get(CONF_ACCESS_TOKEN, ""))
        self.analytics = get_analytics(hass)
        self.states = {
            source: SourceState()
            for source in ("installations", "downloads", "repository", "issues")
        }
        self.scopes = {
            "installations": version_key(f"{self.analytics_source}:{self.integration_domain}"),
            "downloads": version_key(f"{self.repository.lower()}:{self.patterns}"),
        }
        self.tracked: dict[str, list[str]] = {}
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._cancel_retry = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            config_entry=entry,
            update_interval=timedelta(hours=self.settings.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
        )

    async def async_load_tracking(self) -> None:
        """Restore every version ever selected, including temporarily missing versions."""
        stored = await self.store.async_load()
        if isinstance(stored, dict):
            self.tracked = {
                key: [v for v in values if isinstance(v, str)]
                for key, values in stored.items()
                if isinstance(values, list)
            }

    def known_versions(self, source: str) -> list[str]:
        """Return the versions belonging to this source and selection of files."""
        return self.tracked.get(self.scopes[source], [])

    def enabled(self, source: str) -> bool:
        """Check whether a project has this source configured."""
        if source == "downloads":
            return bool(self.repository and self.patterns)
        return bool(self.integration_domain if source == "installations" else self.repository)

    async def _async_update_source(self, source: str) -> None:
        if not self.enabled(source):
            return
        state = self.states[source]
        try:
            if source == "installations":
                snapshot = await self.analytics.async_get(self.analytics_source)
                counts = parse_analytics(
                    snapshot.body, self.integration_domain, self.analytics_source
                )
            elif source == "downloads":
                snapshot = await self.github.async_releases(self.repository)
                counts = parse_downloads(snapshot.body, self.patterns)
            elif source == "repository":
                snapshot = await self.github.async_repository(self.repository)
                state.metrics = parse_repository_metrics(snapshot.body)
            else:
                snapshot = await self.github.async_issues(self.repository)
                state.metrics = snapshot.body
            if source in ("installations", "downloads"):
                state.counts = counts
            state.last_success = snapshot.fetched_at
            state.status = "ok"
            state.retry_at = None
        except SourceError as err:
            state.status = err.code
            state.retry_at = err.retry_at

    async def _async_update_data(self) -> dict[str, SourceState]:
        await asyncio.gather(*(self._async_update_source(source) for source in self.states))
        changed = False
        for source in ("installations", "downloads"):
            state = self.states[source]
            if state.status != "ok":
                continue
            previous = self.known_versions(source)
            selected = top_versions(
                state.counts,
                self.settings.get(CONF_TOP, DEFAULT_TOP),
                self.settings.get(CONF_PRERELEASE, True),
            )
            combined = sorted(set(previous) | set(selected))
            if combined != previous:
                self.tracked[self.scopes[source]] = combined
                changed = True
        if changed:
            await self.store.async_save(self.tracked)
        if self._cancel_retry:
            self._cancel_retry()
            self._cancel_retry = None
        retry_times = [s.retry_at for s in self.states.values() if s.retry_at]
        if retry_times:
            self._cancel_retry = async_call_later(
                self.hass, max(60, min(retry_times) - time.time()), self._async_retry
            )
        return self.states

    async def _async_retry(self, _now: Any) -> None:
        self._cancel_retry = None
        await self.async_request_refresh()

    @callback
    def cancel_retry(self) -> None:
        """Cancel pending callbacks when the entry is unloaded."""
        if self._cancel_retry:
            self._cancel_retry()
            self._cancel_retry = None
