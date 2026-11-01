"""Home Assistant test fixtures."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.community_stats.models import Snapshot

pytest_plugins = ("pytest_homeassistant_custom_component",)


@pytest.fixture(autouse=True)
def enable_integration(enable_custom_integrations):
    """Load the integration from the repository during every test."""
    yield


@pytest.fixture
def releases():
    return [
        {
            "id": 11,
            "tag_name": "v0.8.2",
            "prerelease": False,
            "draft": False,
            "assets": [
                {"id": 101, "name": "project.zip", "download_count": 150},
                {"id": 102, "name": "project.js", "download_count": 25},
            ],
        },
        {
            "id": 12,
            "tag_name": "v0.8.3-beta.1",
            "prerelease": True,
            "draft": False,
            "assets": [{"id": 103, "name": "project.zip", "download_count": 40}],
        },
    ]


@pytest.fixture
def source_clients(releases):
    analytics = AsyncMock()
    analytics.async_get.return_value = Snapshot(
        {
            "test_project": {
                "total": 120,
                "versions": {"0.8.2": 80, "0.8.3-beta.1": 30, "0.7.0": 10},
            }
        },
        dt_util.utcnow(),
    )
    github = AsyncMock()
    github.async_releases.return_value = Snapshot(releases, dt_util.utcnow())
    github.async_repository.return_value = Snapshot(
        {
            "stargazers_count": 26,
            "forks_count": 10,
            "subscribers_count": 3,
            "watchers_count": 26,
            "open_issues_count": 36,
        },
        dt_util.utcnow(),
    )
    github.async_issues.return_value = Snapshot(
        {"issues_total": 50, "issues_open": 35}, dt_util.utcnow()
    )
    github.remaining = 48
    github.retry_at = None
    with (
        patch(
            "custom_components.community_stats.coordinator.get_analytics", return_value=analytics
        ),
        patch("custom_components.community_stats.coordinator.get_github", return_value=github),
    ):
        yield analytics, github
