"""HTTP failures, pagination, shared caches and rate limiting."""

import asyncio
import time

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.community_stats.api import AnalyticsClient, GitHubClient, get_github
from custom_components.community_stats.const import CUSTOM_URL, GITHUB_API
from custom_components.community_stats.models import SourceError


async def test_analytics_cache_is_shared_and_zero_survives(hass, aioclient_mock):
    aioclient_mock.get(CUSTOM_URL, json={"test": {"total": 0, "versions": {}}})
    client = AnalyticsClient(async_get_clientsession(hass))
    first, second = await asyncio.gather(client.async_get("custom"), client.async_get("custom"))
    assert first is second
    assert first.body["test"]["total"] == 0
    assert aioclient_mock.call_count == 1


async def test_analytics_failure_does_not_return_stale_data(hass, aioclient_mock, freezer):
    aioclient_mock.get(CUSTOM_URL, json={"test": {"total": 5}})
    client = AnalyticsClient(async_get_clientsession(hass))
    await client.async_get("custom")
    freezer.tick(301)
    aioclient_mock.clear_requests()
    aioclient_mock.get(CUSTOM_URL, status=503)
    with pytest.raises(SourceError, match="cannot_connect") as error:
        await client.async_get("custom")
    assert error.value.detail == "HTTP 503"
    with pytest.raises(SourceError, match="cannot_connect"):
        await client.async_get("custom")
    assert aioclient_mock.call_count == 1


async def test_release_pagination_and_recent_cache(hass, aioclient_mock, releases):
    first_url = f"{GITHUB_API}/repos/owner/repo/releases?per_page=100&page=1"
    second_url = f"{GITHUB_API}/repos/owner/repo/releases?per_page=100&page=2"
    aioclient_mock.get(first_url, json=[releases[0]], headers={"Link": '<unused>; rel="next"'})
    aioclient_mock.get(second_url, json=[releases[1]])
    client = GitHubClient(async_get_clientsession(hass), "")
    snapshot = await client.async_releases("owner/repo")
    assert snapshot.body == releases
    assert await client.async_releases("owner/repo") is snapshot
    assert aioclient_mock.call_count == 2


async def test_rate_limit_pauses_requests_and_resumes_scan(hass, aioclient_mock, freezer, releases):
    first_url = f"{GITHUB_API}/repos/owner/repo/releases?per_page=100&page=1"
    second_url = f"{GITHUB_API}/repos/owner/repo/releases?per_page=100&page=2"
    aioclient_mock.get(first_url, json=[releases[0]], headers={"Link": '<unused>; rel="next"'})
    aioclient_mock.get(second_url, status=429, headers={"Retry-After": "3600"})
    client = GitHubClient(async_get_clientsession(hass), "")
    with pytest.raises(SourceError, match="rate_limited") as error:
        await client.async_releases("owner/repo")
    assert error.value.retry_at > time.time()
    with pytest.raises(SourceError, match="rate_limited"):
        await client.async_releases("owner/repo")
    assert aioclient_mock.call_count == 2
    freezer.tick(3601)
    aioclient_mock.clear_requests()
    aioclient_mock.get(second_url, json=[releases[1]])
    assert (await client.async_releases("owner/repo")).body == releases
    assert aioclient_mock.call_count == 1


async def test_authenticated_conditional_request_preserves_body(hass, aioclient_mock, releases):
    url = f"{GITHUB_API}/repos/owner/repo/releases?per_page=100&page=1"
    client = GitHubClient(async_get_clientsession(hass), "test-token")
    aioclient_mock.get(url, json=releases, headers={"ETag": '"version-one"'})
    await client.async_json("/repos/owner/repo/releases?per_page=100&page=1")
    aioclient_mock.clear_requests()
    aioclient_mock.get(url, status=304)
    body = await client.async_json("/repos/owner/repo/releases?per_page=100&page=1")
    assert body == releases
    assert len(client._requests) == 1
    assert aioclient_mock.mock_calls[0][3]["If-None-Match"] == '"version-one"'


@pytest.mark.parametrize(
    "status,code",
    [(401, "invalid_auth"), (404, "not_found"), (403, "access_denied"), (301, "repository_moved")],
)
async def test_github_failure_classification(hass, aioclient_mock, status, code):
    aioclient_mock.get(f"{GITHUB_API}/repos/owner/repo", status=status, text="denied")
    with pytest.raises(SourceError, match=code):
        await GitHubClient(async_get_clientsession(hass), "").async_json("/repos/owner/repo")


async def test_clients_share_quota_per_token(hass):
    first = get_github(hass)
    assert get_github(hass) is first
    assert get_github(hass, "test-token") is not first


async def test_failed_manual_refresh_has_a_cooldown(hass, aioclient_mock):
    aioclient_mock.get(f"{GITHUB_API}/repos/owner/repo", status=401)
    client = GitHubClient(async_get_clientsession(hass), "test-token")
    for _ in range(3):
        with pytest.raises(SourceError, match="invalid_auth"):
            await client.async_json("/repos/owner/repo")
    assert aioclient_mock.call_count == 1


async def test_low_remaining_quota_waits_for_reset(hass, aioclient_mock):
    reset = int(time.time()) + 3600
    aioclient_mock.get(
        f"{GITHUB_API}/repos/owner/repo",
        json={"name": "repo"},
        headers={
            "X-RateLimit-Remaining": "1",
            "X-RateLimit-Reset": str(reset),
        },
    )
    client = GitHubClient(async_get_clientsession(hass), "")
    await client.async_json("/repos/owner/repo")
    with pytest.raises(SourceError, match="rate_limited") as error:
        await client.async_json("/repos/owner/another")
    assert error.value.retry_at == reset + 1
    assert aioclient_mock.call_count == 1


async def test_concurrent_projects_share_one_repository_scan(hass, aioclient_mock, releases):
    url = f"{GITHUB_API}/repos/owner/repo/releases?per_page=100&page=1"
    aioclient_mock.get(url, json=releases)
    client = GitHubClient(async_get_clientsession(hass), "")
    results = await asyncio.gather(
        client.async_releases("owner/repo"), client.async_releases("owner/repo")
    )
    assert results[0] is results[1]
    assert aioclient_mock.call_count == 1


async def test_local_unauthenticated_budget_bounds_requests(hass, aioclient_mock):
    client = GitHubClient(async_get_clientsession(hass), "")
    client._requests.extend([time.time()] * 50)
    with pytest.raises(SourceError, match="rate_limited"):
        await client.async_json("/repos/owner/repo")
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize("retry_header", ["Sun, 01 Nov 2026 01:00:00 GMT", "invalid"])
@pytest.mark.freeze_time("2026-11-01 00:00:00+00:00")
async def test_retry_after_date_and_invalid_header(hass, aioclient_mock, retry_header):
    aioclient_mock.get(
        f"{GITHUB_API}/repos/owner/repo", status=429, headers={"Retry-After": retry_header}
    )
    client = GitHubClient(async_get_clientsession(hass), "")
    with pytest.raises(SourceError, match="rate_limited") as error:
        await client.async_json("/repos/owner/repo")
    expected_delay = 60 if retry_header == "invalid" else 3600
    assert error.value.retry_at == time.time() + expected_delay


async def test_non_json_response_is_unavailable_and_has_cooldown(hass, aioclient_mock):
    aioclient_mock.get(f"{GITHUB_API}/repos/owner/repo", text="<html>Unavailable</html>")
    client = GitHubClient(async_get_clientsession(hass), "")
    for _ in range(2):
        with pytest.raises(SourceError, match="cannot_connect") as error:
            await client.async_json("/repos/owner/repo")
    assert error.value.detail
    assert aioclient_mock.call_count == 1


async def test_server_error_reports_http_status(hass, aioclient_mock):
    aioclient_mock.get(f"{GITHUB_API}/repos/owner/repo", status=502)
    client = GitHubClient(async_get_clientsession(hass), "token")
    with pytest.raises(SourceError, match="cannot_connect") as error:
        await client.async_json("/repos/owner/repo")
    assert error.value.detail == "HTTP 502"
