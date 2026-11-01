"""Exercise anonymous scheduling through real entries, entities and HA timers."""

import asyncio
import time
from datetime import timedelta

import pytest
from homeassistant.const import CONF_ACCESS_TOKEN, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from test_integration import entity_id, setup_project
from test_repository_stats import metric_entity

from custom_components.community_stats.const import DOMAIN, GITHUB_ROTATION_SECONDS
from custom_components.community_stats.diagnostics import async_get_config_entry_diagnostics
from custom_components.community_stats.models import SourceError


async def anonymous_project(hass, repository="owner/first", **options):
    return await setup_project(hass, repository=repository, access_token="", **options)


async def advance(hass, freezer, seconds=GITHUB_ROTATION_SECONDS):
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_rotation_updates_one_project_each_slot_and_analytics_independently(
    hass, source_clients, freezer
):
    analytics, github = source_clients
    first = await anonymous_project(hass)
    second = await anonymous_project(hass, "owner/second")
    third = await anonymous_project(hass, "owner/third")
    assert hass.states.get(entity_id(hass, first, "downloads")).state == "190"
    for entry in (second, third):
        assert hass.states.get(entity_id(hass, entry, "downloads")).state == STATE_UNAVAILABLE
        assert entry.runtime_data.states["downloads"].status == "waiting"
        assert hass.states.get(entity_id(hass, entry, "installations")).state == "120"
    github.async_repository.assert_awaited_once_with("owner/first")
    for repository in ("owner/second", "owner/third", "owner/first"):
        await advance(hass, freezer)
        github.async_repository.assert_awaited_with(repository)
        github.async_issues.assert_awaited_with(repository)
        github.async_releases.assert_awaited_with(repository)
    assert github.async_repository.await_count == 4
    # Rotation ticks do not poll Analytics or change its configured interval.
    assert analytics.async_get.await_count == 3
    assert first.runtime_data.update_interval == timedelta(hours=12)


async def test_manual_buttons_and_update_entity_do_not_bypass_slot(hass, source_clients, freezer):
    analytics, github = source_clients
    assert await async_setup_component(hass, "homeassistant", {})
    first = await anonymous_project(hass)
    second = await anonymous_project(hass, "owner/second")
    await advance(hass, freezer, 6 * 60)
    for entry in (first, second):
        button = er.async_get(hass).async_get_entity_id(
            "button", DOMAIN, f"{entry.entry_id}_refresh"
        )
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
        await hass.services.async_call(
            "homeassistant",
            "update_entity",
            {"entity_id": entity_id(hass, entry, "downloads")},
            blocking=True,
        )
    await hass.async_block_till_done()
    github.async_repository.assert_awaited_once_with("owner/first")
    assert analytics.async_get.await_count > 2
    assert hass.states.get(entity_id(hass, first, "downloads")).state == "190"
    assert second.runtime_data.states["repository"].status == "waiting"


async def test_authenticated_projects_refresh_normally_alongside_rotation(
    hass, source_clients, freezer
):
    _, github = source_clients
    anonymous = await anonymous_project(hass)
    token = await setup_project(hass, repository="owner/token")
    assert token.runtime_data.rotation is None
    await advance(hass, freezer, 6 * 60)
    await token.runtime_data.async_refresh()
    github.async_repository.assert_awaited_with("owner/token")
    assert github.async_repository.await_count == 3
    await anonymous.runtime_data.async_refresh()
    assert github.async_repository.await_count == 3
    await advance(hass, freezer, 55 * 60)
    github.async_repository.assert_awaited_with("owner/first")


async def test_reload_preserves_counts_last_success_and_pause(hass, source_clients, freezer):
    _, github = source_clients
    entry = await anonymous_project(hass)
    before = entry.runtime_data
    last_success = before.states["downloads"].last_success
    sensor = entity_id(hass, entry, "downloads", "v0.8.3-beta.1")
    await advance(hass, freezer, 6 * 60)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data is not before
    assert entry.runtime_data.states["downloads"].last_success == last_success
    assert hass.states.get(sensor).state == "40"
    assert hass.states.get(sensor).attributes["in_current_selection"] is True
    assert hass.states.get(sensor).attributes["published_at"] == "2026-10-10T12:00:00+00:00"
    assert hass.states.get(metric_entity(hass, entry, "stars")).state == "26"
    github.async_repository.assert_awaited_once()
    await advance(hass, freezer, 55 * 60)
    assert github.async_repository.await_count == 2


@pytest.mark.parametrize("elapsed", [6 * 60, 2 * GITHUB_ROTATION_SECONDS])
async def test_restart_restores_schedule_and_fairness_even_when_first_project_loads_first(
    hass, source_clients, freezer, elapsed
):
    _, github = source_clients
    first = await anonymous_project(hass)
    second = await anonymous_project(hass, "owner/second")
    previous_slot = first.runtime_data.rotation.next_slot
    for entry in (first, second):
        assert await hass.config_entries.async_unload(entry.entry_id)
    # Create a new scheduler from the same on-disk storage, as on HA restart.
    hass.data[DOMAIN].pop("github_rotation")
    freezer.tick(timedelta(seconds=elapsed))
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    github.async_repository.assert_awaited_once_with("owner/first")
    assert first.runtime_data.rotation.next_slot == previous_slot
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    if elapsed < GITHUB_ROTATION_SECONDS:
        github.async_repository.assert_awaited_once()
        await advance(hass, freezer, GITHUB_ROTATION_SECONDS - elapsed)
    github.async_repository.assert_awaited_with("owner/second")
    assert github.async_repository.await_count == 2
    await advance(hass, freezer)
    github.async_repository.assert_awaited_with("owner/first")


async def test_token_addition_and_removal_change_membership_without_resetting_pause(
    hass, source_clients, freezer
):
    _, github = source_clients
    entry = await anonymous_project(hass)
    rotation = entry.runtime_data.rotation
    hass.config_entries.async_update_entry(entry, options={CONF_ACCESS_TOKEN: "new-test-token"})
    await hass.async_block_till_done()
    assert entry.runtime_data.rotation is None
    assert not rotation.projects
    assert rotation._cancel is None
    assert github.async_repository.await_count == 2
    hass.config_entries.async_update_entry(entry, options={CONF_ACCESS_TOKEN: ""})
    await hass.async_block_till_done()
    assert entry.runtime_data.rotation is rotation
    assert github.async_repository.await_count == 2
    assert hass.states.get(entity_id(hass, entry, "downloads")).state == "190"
    await advance(hass, freezer)
    assert github.async_repository.await_count == 3
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["github_schedule"]["mode"] == "round_robin"
    assert diagnostics["github_schedule"]["next_slot"] > time.time()


async def test_rate_limit_does_not_create_an_extra_retry_outside_rotation(
    hass, source_clients, freezer
):
    _, github = source_clients
    snapshot = github.async_releases.return_value
    github.async_releases.side_effect = [SourceError("rate_limited", time.time() + 60), snapshot]
    entry = await anonymous_project(hass)
    assert hass.states.get(entity_id(hass, entry, "downloads")).state == STATE_UNAVAILABLE
    assert hass.states.get(metric_entity(hass, entry, "stars")).state == "26"
    assert entry.runtime_data._cancel_retry is None
    await advance(hass, freezer, 61)
    github.async_releases.assert_awaited_once()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.states["downloads"].status == "rate_limited"
    await advance(hass, freezer, GITHUB_ROTATION_SECONDS - 61)
    assert hass.states.get(entity_id(hass, entry, "downloads")).state == "190"


@pytest.mark.parametrize("options", [{"asset_patterns": "*.js"}, {"repository": "owner/new"}])
async def test_cached_observations_never_cross_source_scope(hass, source_clients, freezer, options):
    _, github = source_clients
    entry = await anonymous_project(hass)
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, entry, "downloads")).state == STATE_UNAVAILABLE
    expected = STATE_UNAVAILABLE if "repository" in options else "26"
    assert hass.states.get(metric_entity(hass, entry, "stars")).state == expected
    github.async_repository.assert_awaited_once()
    await advance(hass, freezer)
    expected_downloads = "25" if "asset_patterns" in options else "190"
    assert hass.states.get(entity_id(hass, entry, "downloads")).state == expected_downloads


async def test_unloaded_project_is_skipped_and_last_unload_cancels_timer(
    hass, source_clients, freezer
):
    _, github = source_clients
    first = await anonymous_project(hass)
    second = await anonymous_project(hass, "owner/second")
    third = await anonymous_project(hass, "owner/third")
    rotation = first.runtime_data.rotation
    await hass.config_entries.async_unload(second.entry_id)
    await advance(hass, freezer)
    github.async_repository.assert_awaited_with("owner/third")
    for entry in (first, third):
        await hass.config_entries.async_unload(entry.entry_id)
    assert rotation._cancel is None
    await advance(hass, freezer)
    assert github.async_repository.await_count == 2


async def test_late_timer_and_concurrent_refreshes_do_not_catch_up_with_a_burst(
    hass, source_clients, freezer
):
    _, github = source_clients
    first = await anonymous_project(hass)
    second = await anonymous_project(hass, "owner/second")
    third = await anonymous_project(hass, "owner/third")
    freezer.tick(timedelta(hours=8))
    await asyncio.gather(*(entry.runtime_data.async_refresh() for entry in (first, second, third)))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert github.async_repository.await_count == 2
    github.async_repository.assert_awaited_with("owner/second")
    await advance(hass, freezer)
    github.async_repository.assert_awaited_with("owner/third")


async def test_metadata_only_project_participates_without_download_requests(
    hass, source_clients, freezer
):
    _, github = source_clients
    await anonymous_project(hass)
    entry = await anonymous_project(hass, "owner/metadata", asset_patterns="")
    await advance(hass, freezer)
    github.async_repository.assert_awaited_with("owner/metadata")
    github.async_issues.assert_awaited_with("owner/metadata")
    github.async_releases.assert_awaited_once_with("owner/first")
    assert hass.states.get(metric_entity(hass, entry, "watchers")).state == "3"


async def test_analytics_interval_runs_before_github_slot(hass, source_clients, freezer):
    analytics, github = source_clients
    await anonymous_project(hass, update_interval=1)
    await advance(hass, freezer, 3601)
    assert analytics.async_get.await_count == 2
    github.async_repository.assert_awaited_once()
    await advance(hass, freezer, 59)
    assert github.async_repository.await_count == 2
    assert analytics.async_get.await_count == 2


async def test_older_cached_counts_keep_histories_until_publication_dates_are_fetched(
    hass, source_clients, freezer
):
    _, github = source_clients
    entry = await anonymous_project(hass, top_versions=2)
    original = entity_id(hass, entry, "downloads", "v0.8.2")
    snapshot = await entry.runtime_data.store.async_load()
    snapshot["github"]["downloads"].pop("published_at")
    await entry.runtime_data.store.async_save(snapshot)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    github.async_releases.assert_awaited_once()
    assert hass.states.get(original).state == "150"
    assert hass.states.get(original).attributes["published_at"] is None
    assert entry.runtime_data.selected_versions["downloads"] == []
    await advance(hass, freezer)
    assert entry.runtime_data.selected_versions["downloads"] == ["v0.8.3-beta.1", "v0.8.2"]
    assert entity_id(hass, entry, "downloads", "v0.8.2") == original
    assert hass.states.get(original).attributes["published_at"] == "2026-10-01T12:00:00+00:00"
