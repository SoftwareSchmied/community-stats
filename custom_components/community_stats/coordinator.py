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
from homeassistant.util import dt as dt_util

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
    STALE_SECONDS,
    TRANSIENT_ERRORS,
)
from .models import (
    Counts,
    SourceError,
    SourceState,
    latest_versions,
    parse_analytics,
    parse_downloads,
    parse_patterns,
    parse_repository_metrics,
    top_versions,
    version_key,
)
from .scheduler import get_rotation

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
        self.rotation = (
            get_rotation(hass)
            if self.repository and not self.settings.get(CONF_ACCESS_TOKEN)
            else None
        )
        self._update_lock = asyncio.Lock()
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
        self.selected_versions: dict[str, list[str]] = {"installations": [], "downloads": []}
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
            self._restore_github(stored.get("github", {}))
        if self.rotation:
            await self.rotation.async_register(self)

    def _github_scope(self, source: str) -> str:
        return (
            self.scopes["downloads"]
            if source == "downloads"
            else version_key(self.repository.lower())
        )

    def _restore_github(self, stored: dict) -> None:
        """Keep the last observation visible while waiting, without changing its age."""
        for source in ("downloads", "repository", "issues"):
            cached = stored.get(source)
            if (
                not self.enabled(source)
                or not isinstance(cached, dict)
                or cached.get("scope") != self._github_scope(source)
            ):
                continue
            state = self.states[source]
            state.counts = Counts(
                total=cached["total"],
                versions=cached["versions"],
                prereleases=set(cached["prereleases"]),
                published_at=cached.get("published_at", {}),
            )
            state.metrics = cached["metrics"]
            state.status = cached["status"]
            state.retry_at = cached["retry_at"]
            if cached["last_success"]:
                state.last_success = dt_util.parse_datetime(cached["last_success"])

    async def _async_save(self) -> None:
        """Persist selected versions and GitHub observations without credentials."""
        github = {}
        for source in ("downloads", "repository", "issues"):
            state = self.states[source]
            github[source] = {
                "scope": self._github_scope(source),
                "total": state.counts.total,
                "versions": state.counts.versions,
                "prereleases": sorted(state.counts.prereleases),
                "published_at": state.counts.published_at,
                "metrics": state.metrics,
                "status": state.status,
                "retry_at": state.retry_at,
                "last_success": state.last_success.isoformat() if state.last_success else None,
            }
        await self.store.async_save({**self.tracked, "github": github})

    def known_versions(self, source: str) -> list[str]:
        """Return the versions belonging to this source and selection of files."""
        return self.tracked.get(self.scopes[source], [])

    def enabled(self, source: str) -> bool:
        """Check whether a project has this source configured."""
        if source == "downloads":
            return bool(self.repository and self.patterns)
        return bool(self.integration_domain if source == "installations" else self.repository)

    def usable(self, source: str) -> bool:
        """Keep complete earlier counts visible through short transient outages."""
        state = self.states[source]
        if state.status == "ok":
            return True
        if state.status not in TRANSIENT_ERRORS or state.last_success is None:
            return False
        limit = max(STALE_SECONDS, 3 * self.update_interval.total_seconds())
        return (dt_util.utcnow() - state.last_success).total_seconds() <= limit

    def _log_status(self, source: str, previous: str, err: SourceError | None = None) -> None:
        """Log transitions only, so a lasting outage does not repeat every update."""
        if err is None:
            if previous not in ("ok", "disabled", "waiting"):
                _LOGGER.info("%s: %s update recovered after %s", self.entry.title, source, previous)
            return
        if err.code == previous:
            return
        kept = (
            "; keeping the last successful values"
            if err.code in TRANSIENT_ERRORS and self.states[source].last_success
            else ""
        )
        _LOGGER.log(
            logging.INFO if err.code == "rate_limited" else logging.WARNING,
            "%s: %s update failed: %s%s%s",
            self.entry.title,
            source,
            err.code,
            f" ({err.detail})" if err.detail else "",
            kept,
        )

    async def _async_update_source(self, source: str) -> None:
        if not self.enabled(source):
            return
        state = self.states[source]
        previous = state.status
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
            self._log_status(source, previous)
        except SourceError as err:
            self._log_status(source, previous, err)
            state.status = err.code
            state.retry_at = err.retry_at

    async def _async_update_data(self) -> dict[str, SourceState]:
        async with self._update_lock:
            return await self._async_update()

    async def async_refresh_github(self) -> None:
        """A rotation turn leaves the separate Analytics polling schedule intact."""
        async with self._update_lock:
            await self._async_update(github_only=True)
            self.async_update_listeners()

    async def _async_update(self, *, github_only: bool = False) -> dict[str, SourceState]:
        update_github = not self.rotation or await self.rotation.async_claim(self)
        sources = [] if github_only else ["installations"]
        if update_github:
            sources.extend(("downloads", "repository", "issues"))
        else:
            for source in ("downloads", "repository", "issues"):
                if self.enabled(source) and self.states[source].status == "disabled":
                    self.states[source].status = "waiting"
        await asyncio.gather(*(self._async_update_source(source) for source in sources))
        changed = False
        for source in ("installations", "downloads"):
            state = self.states[source]
            if state.status != "ok":
                continue
            previous = self.known_versions(source)
            select = latest_versions if source == "downloads" else top_versions
            selected = self.selected_versions[source] = select(
                state.counts,
                self.settings.get(CONF_TOP, DEFAULT_TOP),
                self.settings.get(CONF_PRERELEASE, True),
            )
            combined = sorted(set(previous) | set(selected))
            if combined != previous:
                self.tracked[self.scopes[source]] = combined
                changed = True
        if changed or (update_github and self.repository):
            await self._async_save()
        if self._cancel_retry:
            self._cancel_retry()
            self._cancel_retry = None
        retry_times = [
            state.retry_at
            for source, state in self.states.items()
            if state.retry_at and (not self.rotation or source == "installations")
        ]
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
        if self.rotation:
            self.rotation.unregister(self)
