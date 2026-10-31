"""Exercise real Home Assistant setup, entity registry and source updates."""

import pytest
from homeassistant.const import CONF_ACCESS_TOKEN, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.community_stats.const import DOMAIN
from custom_components.community_stats.diagnostics import async_get_config_entry_diagnostics
from custom_components.community_stats.models import Snapshot, SourceError, version_key


async def setup_project(hass, **overrides):
    data = {
        "integration_domain": "test_project",
        "analytics_source": "custom",
        "repository": "owner/repo",
        "asset_patterns": "*.zip",
        "top_versions": 1,
        "include_prereleases": True,
        "update_interval": 12,
    }
    data.update(overrides)
    entry = MockConfigEntry(domain=DOMAIN, title="Test project", data=data, unique_id="custom:test")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity_id(hass, entry, source, version=None):
    unique = (
        f"{entry.entry_id}_{source}_{entry.runtime_data.scopes[source]}_"
        f"{version_key(version) if version is not None else 'total'}"
    )
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique)


async def test_setup_numeric_measurements_device_and_refresh(hass, source_clients):
    entry = await setup_project(hass)
    sensor_id = entity_id(hass, entry, "installations")
    state = hass.states.get(sensor_id)
    assert state.state == "120"
    assert state.attributes["state_class"] == "measurement"
    assert hass.states.get(entity_id(hass, entry, "downloads")).state == "190"
    registry = er.async_get(hass)
    project_entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len({item.device_id for item in project_entities}) == 1
    button = next(item.entity_id for item in project_entities if item.domain == "button")
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_rank_changes_add_versions_without_reassigning_existing_sensors(hass, source_clients):
    analytics, _ = source_clients
    entry = await setup_project(hass)
    original = entity_id(hass, entry, "installations", "0.8.2")
    analytics.async_get.return_value = Snapshot(
        {"test_project": {"total": 99, "versions": {"0.8.2": 9, "0.8.3-beta.1": 90}}},
        dt_util.utcnow(),
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    new = entity_id(hass, entry, "installations", "0.8.3-beta.1")
    assert new and new != original
    assert hass.states.get(original).state == "9"
    assert hass.states.get(new).state == "90"
    assert hass.states.get(entity_id(hass, entry, "installations")).state == "99"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entity_id(hass, entry, "installations", "0.8.2") == original
    assert hass.states.get(original).state == "9"


async def test_missing_version_is_unavailable_then_recovers_same_identity(hass, source_clients):
    analytics, _ = source_clients
    entry = await setup_project(hass)
    original = entity_id(hass, entry, "installations", "0.8.2")
    analytics.async_get.return_value = Snapshot(
        {"test_project": {"total": 7, "versions": {"0.9.0": 7}}}, dt_util.utcnow()
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(original).state == STATE_UNAVAILABLE
    analytics.async_get.return_value = Snapshot(
        {"test_project": {"total": 7, "versions": {"0.8.2": 0, "0.9.0": 7}}}, dt_util.utcnow()
    )
    await entry.runtime_data.async_refresh()
    assert hass.states.get(original).state == "0"


@pytest.mark.parametrize("failed_source", ["installations", "downloads"])
async def test_source_failures_are_independent(hass, source_clients, failed_source):
    analytics, github = source_clients
    entry = await setup_project(hass)
    if failed_source == "downloads":
        github.async_releases.side_effect = SourceError("invalid_auth")
    else:
        analytics.async_get.side_effect = SourceError("cannot_connect")
    await entry.runtime_data.async_refresh()
    other = "downloads" if failed_source == "installations" else "installations"
    assert hass.states.get(entity_id(hass, entry, failed_source)).state == STATE_UNAVAILABLE
    assert hass.states.get(entity_id(hass, entry, other)).state != STATE_UNAVAILABLE


async def test_no_data_at_first_setup_still_exposes_unavailable_totals(hass, source_clients):
    analytics, github = source_clients
    analytics.async_get.side_effect = SourceError("not_found")
    github.async_releases.side_effect = SourceError("no_matching_assets")
    entry = await setup_project(hass)
    assert hass.states.get(entity_id(hass, entry, "installations")).state == STATE_UNAVAILABLE
    assert hass.states.get(entity_id(hass, entry, "downloads")).state == STATE_UNAVAILABLE


async def test_core_has_only_total_and_no_github_calls(hass, source_clients):
    analytics, github = source_clients
    analytics.async_get.return_value = Snapshot({"integrations": {"mqtt": 500}}, dt_util.utcnow())
    entry = await setup_project(
        hass, integration_domain="mqtt", analytics_source="core", repository=""
    )
    assert hass.states.get(entity_id(hass, entry, "installations")).state == "500"
    assert entry.runtime_data.known_versions("installations") == []
    github.async_releases.assert_not_awaited()


async def test_changing_asset_filter_starts_a_new_download_series(hass, source_clients):
    entry = await setup_project(hass)
    old_total = entity_id(hass, entry, "downloads")
    old_installations = entity_id(hass, entry, "installations")
    hass.config_entries.async_update_entry(entry, options={"asset_patterns": "*.js"})
    await hass.async_block_till_done()
    new_total = entity_id(hass, entry, "downloads")
    assert new_total != old_total
    assert hass.states.get(new_total).state == "25"
    assert entity_id(hass, entry, "installations") == old_installations


async def test_diagnostics_redact_token(hass, source_clients):
    entry = await setup_project(hass, **{CONF_ACCESS_TOKEN: "sensitive-example"})
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert "sensitive-example" not in str(result)
    assert result["configuration"][CONF_ACCESS_TOKEN] == "**REDACTED**"


async def test_rate_limit_retry_is_cancelled_on_unload(hass, source_clients):
    _, github = source_clients
    github.async_releases.side_effect = SourceError(
        "rate_limited", dt_util.utcnow().timestamp() + 3600
    )
    entry = await setup_project(hass)
    coordinator = entry.runtime_data
    assert coordinator._cancel_retry is not None
    await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator._cancel_retry is None
