"""Repository metric semantics, stable entities and independent search limits."""

import time
from urllib.parse import urlencode

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from test_integration import setup_project

from custom_components.community_stats.api import GitHubClient
from custom_components.community_stats.const import DOMAIN, GITHUB_API
from custom_components.community_stats.models import Snapshot, SourceError, version_key


def metric_entity(hass, entry, key):
    return er.async_get(hass).async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_repository_{version_key(entry.runtime_data.repository.lower())}_{key}",
    )


async def test_five_metrics_use_precise_definitions(hass, source_clients):
    entry = await setup_project(hass)
    expected = {"stars": 26, "forks": 10, "watchers": 3, "issues_total": 50, "issues_open": 35}
    for key, value in expected.items():
        state = hass.states.get(metric_entity(hass, entry, key))
        assert state.state == str(value)
        assert state.attributes["state_class"] == "measurement"


async def test_release_failure_does_not_hide_repository_metrics(hass, source_clients):
    _, github = source_clients
    github.async_releases.side_effect = SourceError("no_matching_assets")
    entry = await setup_project(hass)
    assert hass.states.get(metric_entity(hass, entry, "stars")).state == "26"
    assert hass.states.get(metric_entity(hass, entry, "issues_open")).state == "35"


async def test_repository_metrics_work_without_download_patterns(hass, source_clients):
    _, github = source_clients
    entry = await setup_project(hass, integration_domain="", asset_patterns="")
    assert hass.states.get(metric_entity(hass, entry, "stars")).state == "26"
    github.async_releases.assert_not_awaited()
    assert not entry.runtime_data.enabled("downloads")


async def test_search_failure_only_hides_issue_counts(hass, source_clients):
    _, github = source_clients
    github.async_issues.side_effect = SourceError("rate_limited", time.time() + 60)
    entry = await setup_project(hass)
    assert hass.states.get(metric_entity(hass, entry, "issues_open")).state == "unavailable"
    assert hass.states.get(metric_entity(hass, entry, "stars")).state == "26"
    assert entry.runtime_data.states["downloads"].status == "ok"


async def test_release_filter_changes_keep_repository_metric_history(hass, source_clients):
    entry = await setup_project(hass)
    original = metric_entity(hass, entry, "stars")
    hass.config_entries.async_update_entry(entry, options={"asset_patterns": "*.js"})
    await hass.async_block_till_done()
    assert metric_entity(hass, entry, "stars") == original


async def test_repository_counts_can_decrease_to_zero(hass, source_clients):
    _, github = source_clients
    entry = await setup_project(hass)
    github.async_repository.return_value = Snapshot(
        {
            "stargazers_count": 0,
            "forks_count": 0,
            "subscribers_count": 0,
        },
        dt_util.utcnow(),
    )
    await entry.runtime_data.async_refresh()
    for key in ("stars", "forks", "watchers"):
        assert hass.states.get(metric_entity(hass, entry, key)).state == "0"


async def test_issue_search_filters_and_shared_cache(hass, aioclient_mock):
    for suffix, count in (("", 50), (" is:open", 35)):
        query = urlencode({"q": f"repo:owner/repo is:issue{suffix}", "per_page": 1})
        aioclient_mock.get(
            f"{GITHUB_API}/search/issues?{query}",
            json={
                "total_count": count,
                "incomplete_results": False,
            },
        )
    client = GitHubClient(async_get_clientsession(hass), "")
    assert (await client.async_issues("owner/repo")).body == {"issues_total": 50, "issues_open": 35}
    await client.async_issues("owner/repo")
    assert aioclient_mock.call_count == 2


@pytest.mark.parametrize(
    "count,incomplete", [(50, True), (-1, False), (True, False), (None, False)]
)
async def test_incomplete_or_invalid_issue_counts_are_unavailable(
    hass, aioclient_mock, count, incomplete
):
    query = urlencode({"q": "repo:owner/repo is:issue", "per_page": 1})
    aioclient_mock.get(
        f"{GITHUB_API}/search/issues?{query}",
        json={
            "total_count": count,
            "incomplete_results": incomplete,
        },
    )
    with pytest.raises(SourceError, match="invalid_data"):
        await GitHubClient(async_get_clientsession(hass), "").async_issues("owner/repo")
    assert aioclient_mock.call_count == 1


async def test_search_quota_does_not_block_repository_requests(hass, aioclient_mock):
    client = GitHubClient(async_get_clientsession(hass), "")
    path = "/search/issues?q=repo:owner/repo"
    aioclient_mock.get(
        GITHUB_API + path,
        json={"total_count": 1},
        headers={
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + 60),
            "X-RateLimit-Resource": "search",
        },
    )
    await client.async_json(path)
    with pytest.raises(SourceError, match="rate_limited"):
        await client.async_json(path + "+is:open")
    aioclient_mock.get(
        f"{GITHUB_API}/repos/owner/repo",
        json={"stargazers_count": 10},
        headers={
            "X-RateLimit-Remaining": "48",
            "X-RateLimit-Resource": "core",
        },
    )
    assert (await client.async_repository("owner/repo")).body["stargazers_count"] == 10
    assert client.remaining == 48
    assert client.search_remaining == 0
    assert aioclient_mock.call_count == 2


async def test_secondary_search_limit_pauses_all_github_requests(hass, aioclient_mock):
    client = GitHubClient(async_get_clientsession(hass), "")
    path = "/search/issues?q=repo:owner/repo"
    aioclient_mock.get(
        GITHUB_API + path,
        status=403,
        text="secondary rate limit",
        headers={
            "Retry-After": "120",
        },
    )
    with pytest.raises(SourceError, match="rate_limited"):
        await client.async_json(path)
    with pytest.raises(SourceError, match="rate_limited"):
        await client.async_json("/repos/owner/repo")
    assert aioclient_mock.call_count == 1
