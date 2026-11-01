"""Shared, bounded HTTP access to Analytics and GitHub."""

import asyncio
import hashlib
import time
from collections import deque
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError, ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import CORE_URL, CUSTOM_URL, DOMAIN, GITHUB_API, MIN_REFRESH_SECONDS
from .models import Snapshot, SourceError, valid_count


@dataclass
class CachedResponse:
    """A response body and its conditional-request metadata."""

    body: Any
    etag: str | None
    next_page: bool


class AnalyticsClient:
    """Download each Analytics document once for projects sharing a refresh window."""

    def __init__(self, session: ClientSession) -> None:
        self.session = session
        self.cache: dict[str, Snapshot] = {}
        self.errors: dict[str, tuple[float, SourceError]] = {}
        self.lock = asyncio.Lock()

    async def async_get(self, source: str) -> Snapshot:
        """Return a recent successful document or fetch a new one."""
        async with self.lock:
            now = time.time()
            if cached := self.cache.get(source):
                if now - cached.fetched_at.timestamp() < MIN_REFRESH_SECONDS:
                    return cached
            if error := self.errors.get(source):
                if now < error[0]:
                    raise error[1]
            try:
                async with asyncio.timeout(30):
                    async with self.session.get(
                        CUSTOM_URL if source == "custom" else CORE_URL
                    ) as response:
                        if response.status != 200:
                            raise SourceError("cannot_connect")
                        body = await response.json()
                        if not isinstance(body, dict):
                            raise SourceError("invalid_data")
            except (ClientError, TimeoutError, ValueError) as err:
                error = SourceError("cannot_connect")
                self.errors[source] = (now + MIN_REFRESH_SECONDS, error)
                raise error from err
            except SourceError as err:
                self.errors[source] = (now + MIN_REFRESH_SECONDS, err)
                raise
            snapshot = Snapshot(body, dt_util.utcnow())
            self.cache[source] = snapshot
            self.errors.pop(source, None)
            return snapshot


class GitHubClient:
    """A shared client per credential, with a shared request lock across clients."""

    def __init__(
        self, session: ClientSession, token: str, lock: asyncio.Lock | None = None
    ) -> None:
        self.session = session
        self._token = token
        self._lock = lock or asyncio.Lock()
        self._responses: dict[str, CachedResponse] = {}
        self._failures: dict[str, tuple[float, SourceError]] = {}
        self._recent: dict[str, Snapshot] = {}
        self._scans: dict[str, dict[str, Any]] = {}
        self._scan_locks: dict[str, asyncio.Lock] = {}
        self._metadata: dict[str, Snapshot] = {}
        self._metadata_locks: dict[str, asyncio.Lock] = {}
        self._requests: deque[float] = deque()
        self.remaining: int | None = None
        self.reset_at: float | None = None
        self.retry_at: float | None = None
        self.search_remaining: int | None = None
        self.search_reset_at: float | None = None
        self.search_retry_at: float | None = None

    async def async_metadata(self, path: str) -> Snapshot:
        """Share repository and search snapshots across all matching project entries."""
        async with self._metadata_locks.setdefault(path, asyncio.Lock()):
            cached = self._metadata.get(path)
            if cached and time.time() - cached.fetched_at.timestamp() < MIN_REFRESH_SECONDS:
                return cached
            response = await self._async_request(path)
            snapshot = Snapshot(response.body, dt_util.utcnow())
            self._metadata[path] = snapshot
            return snapshot

    async def async_repository(self, repository: str) -> Snapshot:
        return await self.async_metadata(f"/repos/{repository}")

    async def async_issues(self, repository: str) -> Snapshot:
        """Search real issues, excluding pull requests, with separate search quota."""
        paths = [
            "/search/issues?"
            + urlencode({"q": f"repo:{repository} is:issue{suffix}", "per_page": 1})
            for suffix in ("", " is:open")
        ]
        snapshots = []
        values = {}
        for key, path in zip(("issues_total", "issues_open"), paths, strict=True):
            snapshot = await self.async_metadata(path)
            snapshots.append(snapshot)
            data = snapshot.body
            if (
                not isinstance(data, dict)
                or not valid_count(data.get("total_count"))
                or data.get("incomplete_results") is not False
            ):
                raise SourceError("invalid_data")
            values[key] = data["total_count"]
        if values["issues_open"] > values["issues_total"]:
            raise SourceError("invalid_data")
        return Snapshot(values, min(snapshot.fetched_at for snapshot in snapshots))

    def _set_retry(self, resource: str, retry_at: float) -> SourceError:
        if resource == "search":
            self.search_retry_at = retry_at
        else:
            self.retry_at = retry_at
        return SourceError("rate_limited", retry_at)

    async def async_json(self, path: str) -> Any:
        """Read setup metadata with the same quota handling as statistics."""
        response = await self._async_request(path)
        return response.body

    async def _async_request(self, path: str) -> CachedResponse:
        """Serialize requests; never follow redirects with a token to another host."""
        if not path.startswith(("/repos/", "/search/issues?")) or ".." in path.split("/"):
            raise SourceError("invalid_repository")
        resource = "search" if path.startswith("/search/") else "core"
        async with self._lock:
            now = time.time()
            if failure := self._failures.get(path):
                if now < failure[0]:
                    raise failure[1]
            if self.retry_at is not None and now < self.retry_at:
                raise SourceError("rate_limited", self.retry_at)
            if resource == "search" and self.search_retry_at and now < self.search_retry_at:
                raise SourceError("rate_limited", self.search_retry_at)
            while self._requests and self._requests[0] <= now - 3600:
                self._requests.popleft()
            limit = 4500 if self._token else 50
            if len(self._requests) >= limit:
                self.retry_at = self._requests[0] + 3601
                raise SourceError("rate_limited", self.retry_at)
            remaining = self.search_remaining if resource == "search" else self.remaining
            reset_at = self.search_reset_at if resource == "search" else self.reset_at
            reserve = 0 if resource == "search" else 2
            if remaining is not None and remaining <= reserve:
                if reset_at and now < reset_at:
                    raise self._set_retry(resource, reset_at + 1)
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Community-Stats/0.3.0",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            cached = self._responses.get(path)
            if cached and cached.etag:
                headers["If-None-Match"] = cached.etag
            self._requests.append(now)
            try:
                async with asyncio.timeout(30):
                    async with self.session.get(
                        f"{GITHUB_API}{path}", headers=headers, allow_redirects=False
                    ) as response:
                        for key, attr in (
                            ("X-RateLimit-Remaining", "remaining"),
                            ("X-RateLimit-Reset", "reset_at"),
                        ):
                            try:
                                prefix = "search_" if resource == "search" else ""
                                setattr(self, prefix + attr, int(response.headers[key]))
                            except KeyError, ValueError:
                                pass
                        if response.status == 304 and cached:
                            if self._token:
                                self._requests.pop()
                            return cached
                        if response.status in (301, 302, 307, 308):
                            # Renamed repositories redirect within api.github.com.
                            # Report this so the user can correct the saved repository.
                            raise SourceError("repository_moved")
                        if response.status == 401:
                            raise SourceError("invalid_auth")
                        if response.status == 404:
                            raise SourceError("not_found")
                        if response.status in (403, 429):
                            body = await response.text()
                            retry = response.headers.get("Retry-After")
                            remaining = (
                                self.search_remaining if resource == "search" else self.remaining
                            )
                            reset_at = (
                                self.search_reset_at if resource == "search" else self.reset_at
                            )
                            if (
                                response.status == 429
                                or remaining == 0
                                or retry
                                or "rate limit" in body.lower()
                            ):
                                retry_at = now + 60
                                if retry:
                                    try:
                                        retry_at = now + max(1, int(retry))
                                    except ValueError:
                                        try:
                                            retry_at = parsedate_to_datetime(retry).timestamp()
                                        except ValueError, TypeError, OverflowError:
                                            pass
                                if remaining == 0 and reset_at:
                                    retry_at = max(retry_at, reset_at + 1)
                                # Secondary limits can apply across API resources.
                                blocked_resource = (
                                    "core" if "secondary" in body.lower() else resource
                                )
                                raise self._set_retry(blocked_resource, max(now + 60, retry_at))
                            raise SourceError("access_denied")
                        if response.status != 200:
                            raise SourceError("cannot_connect")
                        body = await response.json()
                        item = CachedResponse(
                            body,
                            response.headers.get("ETag"),
                            'rel="next"' in response.headers.get("Link", ""),
                        )
                        self._responses[path] = item
                        self._failures.pop(path, None)
                        if resource == "search":
                            self.search_retry_at = None
                        else:
                            self.retry_at = None
                        return item
            except (ClientError, TimeoutError, ValueError) as err:
                failure = SourceError("cannot_connect")
                self._failures[path] = (now + MIN_REFRESH_SECONDS, failure)
                raise failure from err
            except SourceError as err:
                if err.code != "rate_limited":
                    self._failures[path] = (now + MIN_REFRESH_SECONDS, err)
                raise

    async def async_releases(self, repository: str) -> Snapshot:
        """Share one in-progress scan between projects using the same repository."""
        async with self._scan_locks.setdefault(repository.lower(), asyncio.Lock()):
            return await self._async_releases(repository)

    async def _async_releases(self, repository: str) -> Snapshot:
        """Fetch all pages atomically, resuming an interrupted rate-limited scan."""
        now = time.time()
        if recent := self._recent.get(repository):
            if now - recent.fetched_at.timestamp() < MIN_REFRESH_SECONDS:
                return recent
        scan = self._scans.setdefault(repository, {"page": 1, "items": {}, "started": now})
        if now - scan["started"] > 86400:
            scan = {"page": 1, "items": {}, "started": now}
            self._scans[repository] = scan
        try:
            while True:
                page = await self._async_request(
                    f"/repos/{repository}/releases?per_page=100&page={scan['page']}"
                )
                if not isinstance(page.body, list):
                    raise SourceError("invalid_data")
                for release in page.body:
                    if not isinstance(release, dict) or type(release.get("id")) is not int:
                        raise SourceError("invalid_data")
                    scan["items"][release["id"]] = release
                if not page.next_page:
                    break
                scan["page"] += 1
        except SourceError as err:
            if err.code != "rate_limited":
                self._scans.pop(repository, None)
            raise
        snapshot = Snapshot(list(scan["items"].values()), dt_util.utcnow())
        self._recent[repository] = snapshot
        self._scans.pop(repository, None)
        return snapshot


def get_analytics(hass: HomeAssistant) -> AnalyticsClient:
    """Share documents between all entries."""
    shared = hass.data.setdefault(DOMAIN, {})
    if "analytics" not in shared:
        shared["analytics"] = AnalyticsClient(async_get_clientsession(hass))
    return shared["analytics"]


def get_github(hass: HomeAssistant, token: str = "") -> GitHubClient:
    """Share quota and release data without exposing credentials as dictionary keys."""
    shared = hass.data.setdefault(DOMAIN, {})
    clients = shared.setdefault("github", {})
    key = hashlib.sha256(token.encode()).hexdigest()
    if key not in clients:
        clients[key] = GitHubClient(
            async_get_clientsession(hass), token, shared.setdefault("github_lock", asyncio.Lock())
        )
    return clients[key]
