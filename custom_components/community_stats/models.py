"""Validation and stable identities for source data."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatchcase
from typing import Any
from urllib.parse import urlsplit

from packaging.version import InvalidVersion, Version


class SourceError(Exception):
    """A source is unavailable; never substitute zero for this condition."""

    def __init__(self, code: str, retry_at: float | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.retry_at = retry_at


@dataclass
class Snapshot:
    """One successfully fetched source document."""

    body: Any
    fetched_at: datetime


@dataclass
class Counts:
    """Counts in a complete, validated document."""

    total: int | None = None
    versions: dict[str, int] = field(default_factory=dict)
    prereleases: set[str] = field(default_factory=set)


@dataclass
class SourceState:
    """Availability and last successful fetch for an independent source."""

    counts: Counts = field(default_factory=Counts)
    status: str = "disabled"
    last_success: datetime | None = None
    retry_at: float | None = None
    metrics: dict[str, int] = field(default_factory=dict)


def parse_repository_metrics(document: Any) -> dict[str, int]:
    """GitHub watchers_count aliases stars; subscribers_count counts actual watchers."""
    fields = {"stars": "stargazers_count", "forks": "forks_count", "watchers": "subscribers_count"}
    if not isinstance(document, dict) or any(
        not valid_count(document.get(field)) for field in fields.values()
    ):
        raise SourceError("invalid_data")
    return {key: document[field] for key, field in fields.items()}


def valid_count(value: Any) -> bool:
    """Booleans, negatives and fractional counts are not valid counts."""
    return type(value) is int and value >= 0


def parse_analytics(document: Any, domain: str, source: str) -> Counts:
    """Read exact versions without merging prefixes, suffixes or subversions."""
    if not isinstance(document, dict):
        raise SourceError("invalid_data")
    if source == "core":
        integrations = document.get("integrations")
        if not isinstance(integrations, dict):
            raise SourceError("invalid_data")
        if domain not in integrations:
            raise SourceError("not_found")
        count = integrations[domain]
        if not valid_count(count):
            raise SourceError("invalid_data")
        return Counts(total=count)
    if domain not in document:
        raise SourceError("not_found")
    record = document[domain]
    if not isinstance(record, dict) or not valid_count(record.get("total")):
        raise SourceError("invalid_data")
    # A valid total can still be useful if version data is absent or malformed.
    versions = record.get("versions")
    if not isinstance(versions, dict):
        return Counts(total=record["total"])
    return Counts(
        total=record["total"],
        versions={k: v for k, v in versions.items() if isinstance(k, str) and k and valid_count(v)},
    )


def parse_patterns(text: str) -> list[str]:
    """One case-sensitive filename pattern per line; no implicit wildcards."""
    return sorted({line.strip() for line in text.splitlines() if line.strip()})


def parse_downloads(releases: Any, patterns: list[str]) -> Counts:
    """Count each matching asset once, including when patterns overlap."""
    if not isinstance(releases, list):
        raise SourceError("invalid_data")
    counts = Counts()
    seen_releases: set[int] = set()
    for release in releases:
        if not isinstance(release, dict):
            raise SourceError("invalid_data")
        if release.get("draft"):
            continue
        release_id = release.get("id")
        tag = release.get("tag_name")
        assets = release.get("assets")
        if not isinstance(release_id, int) or not isinstance(tag, str) or not tag:
            raise SourceError("invalid_data")
        if not isinstance(assets, list):
            raise SourceError("invalid_data")
        if release_id in seen_releases:
            continue
        seen_releases.add(release_id)
        matched: dict[int, int] = {}
        for asset in assets:
            if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
                raise SourceError("invalid_data")
            if not any(fnmatchcase(asset["name"], pattern) for pattern in patterns):
                continue
            if not valid_count(asset.get("download_count")) or type(asset.get("id")) is not int:
                raise SourceError("invalid_data")
            matched[asset["id"]] = asset["download_count"]
        if matched:
            # Multiple release records for one tag would make a version total ambiguous.
            if tag in counts.versions:
                raise SourceError("invalid_data")
            counts.versions[tag] = sum(matched.values())
            if release.get("prerelease"):
                counts.prereleases.add(tag)
    if not counts.versions:
        raise SourceError("no_matching_assets")
    counts.total = sum(counts.versions.values())
    return counts


def is_prerelease(version: str) -> bool:
    """Recognize conventional version suffixes without changing their identity."""
    try:
        return Version(version).is_prerelease
    except InvalidVersion:
        return bool(re.search(r"(?:alpha|beta|preview|pre|rc|dev|snapshot)", version, re.I))


def top_versions(counts: Counts, limit: int, include_prereleases: bool) -> list[str]:
    """Rank by count; use the exact version string as deterministic tie breaker."""
    return sorted(
        (
            version
            for version in counts.versions
            if include_prereleases or not (version in counts.prereleases or is_prerelease(version))
        ),
        key=lambda version: (-counts.versions[version], version),
    )[:limit]


def version_key(version: str) -> str:
    """Avoid slug collisions such as 1.0+dev and 1.0-dev."""
    return hashlib.sha256(version.encode()).hexdigest()[:24]


def normalize_repository(value: str) -> str:
    """Accept public GitHub repository URLs or owner/name, never arbitrary hosts."""
    value = value.strip().rstrip("/")
    if "://" in value:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or url.netloc.lower() not in ("github.com", "www.github.com")
            or url.query
            or url.fragment
        ):
            raise ValueError("invalid_repository")
        value = url.path.strip("/")
    value = value.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+", value):
        raise ValueError("invalid_repository")
    if value.split("/")[1] in (".", ".."):
        raise ValueError("invalid_repository")
    return value


def repository_from_manifest(manifest: dict[str, Any]) -> str | None:
    """Documentation and issue links can suggest a repository, not prove ownership."""
    for key in ("issue_tracker", "documentation"):
        value = manifest.get(key, "")
        if not isinstance(value, str):
            continue
        url = urlsplit(value)
        if url.scheme == "https" and url.netloc.lower() == "github.com":
            parts = url.path.strip("/").split("/")
            if len(parts) >= 2:
                try:
                    return normalize_repository("/".join(parts[:2]))
                except ValueError:
                    pass
    return None
