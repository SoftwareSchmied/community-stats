"""Setup and options through Home Assistant's real flow manager."""

import base64
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant import data_entry_flow
from homeassistant.const import CONF_ACCESS_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.community_stats.const import DOMAIN


async def start(hass, user_input):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def finish(hass, result, **extra):
    assert result["step_id"] == "project"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Example",
            "top_versions": 10,
            "include_prereleases": True,
            "update_interval": 12,
            **extra,
        },
    )
    await hass.async_block_till_done()
    return result


async def test_domain_only_setup(hass, source_clients):
    result = await start(
        hass,
        {
            "integration_domain": "test_project",
            "analytics_source": "custom",
            "discover_repository": False,
        },
    )
    result = await finish(hass, result)
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"]["integration_domain"] == "test_project"
    assert not result["data"]["repository"]


async def test_local_manifest_suggests_repository(hass, source_clients, releases):
    github = AsyncMock()
    github.async_json.side_effect = [
        {"full_name": "owner/repo", "private": False},
        releases,
    ]
    local = Mock(name="integration", is_built_in=False)
    local.name = "Example integration"
    local.manifest = {"issue_tracker": "https://github.com/owner/repo/issues"}
    with (
        patch(
            "custom_components.community_stats.config_flow.async_get_integration",
            return_value=local,
        ),
        patch("custom_components.community_stats.config_flow.get_github", return_value=github),
    ):
        result = await start(
            hass,
            {
                "integration_domain": "test_project",
                "analytics_source": "custom",
                "discover_repository": True,
            },
        )
        assert result["description_placeholders"]["repository"] == "owner/repo"
        result = await finish(hass, result, asset_patterns="*.zip")
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_repository_resolves_manifest_domain(hass, source_clients, releases):
    github = AsyncMock()
    manifest = base64.b64encode(json.dumps({"domain": "test_project", "name": "Test"}).encode())
    github.async_json.side_effect = [
        {"full_name": "owner/repo", "private": False},
        [{"type": "dir", "name": "test_project"}],
        {"content": manifest.decode()},
        releases,
    ]
    with patch("custom_components.community_stats.config_flow.get_github", return_value=github):
        result = await start(hass, {"repository": "https://github.com/owner/repo"})
        assert result["description_placeholders"]["integration"] == "test_project"
        result = await finish(hass, result, asset_patterns="*.zip")
    assert result["data"]["analytics_source"] == "custom"


async def test_card_without_manifest_is_downloads_only(hass, source_clients, releases):
    from custom_components.community_stats.models import SourceError

    github = AsyncMock()
    github.async_json.side_effect = [
        {"full_name": "owner/card", "private": False},
        SourceError("not_found"),
        releases,
    ]
    with patch("custom_components.community_stats.config_flow.get_github", return_value=github):
        result = await start(hass, {"repository": "owner/card"})
        result = await finish(hass, result, asset_patterns="*.js")
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert not result["data"]["integration_domain"]


async def test_ambiguous_repository_offers_domain_choice(hass, source_clients, releases):
    github = AsyncMock()
    github.async_json.side_effect = [
        {"full_name": "owner/repo", "private": False},
        [{"type": "dir", "name": "first"}, {"type": "dir", "name": "second"}],
        releases,
    ]
    with patch("custom_components.community_stats.config_flow.get_github", return_value=github):
        result = await start(hass, {"repository": "owner/repo"})
        assert result["step_id"] == "integration"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"integration_domain": "downloads-only"}
        )
        result = await finish(hass, result, asset_patterns="*.zip")
    assert not result["data"]["integration_domain"]


@pytest.mark.parametrize(
    "data,error",
    [
        ({}, "project_required"),
        ({"integration_domain": "Wrong Domain"}, "invalid_domain"),
        ({"repository": "https://evil.example/owner/repo"}, "invalid_repository"),
        (
            {"integration_domain": "mqtt", "analytics_source": "core", "repository": "owner/repo"},
            "core_repository",
        ),
    ],
)
async def test_bad_project_input(hass, data, error):
    result = await start(hass, data)
    assert error in result["errors"].values()


async def test_duplicate_project_is_rejected(hass, source_clients):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="custom:test_project", data={})
    entry.add_to_hass(hass)
    result = await start(
        hass,
        {
            "integration_domain": "test_project",
            "analytics_source": "custom",
            "discover_repository": False,
        },
    )
    result = await finish(hass, result)
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_keep_secret_without_showing_it(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "integration_domain": "test_project",
            "analytics_source": "custom",
            "repository": "",
            CONF_ACCESS_TOKEN: "secret-value",
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "secret-value" not in str(result)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "top_versions": 5,
            "include_prereleases": False,
            "update_interval": 24,
            "repository": "",
            "asset_patterns": "",
            "clear_token": False,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_ACCESS_TOKEN] == "secret-value"


async def test_options_can_remove_saved_secret(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "integration_domain": "test_project",
            "repository": "",
            CONF_ACCESS_TOKEN: "secret-value",
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "top_versions": 5,
            "include_prereleases": True,
            "update_interval": 12,
            "repository": "",
            "asset_patterns": "",
            "clear_token": True,
        },
    )
    assert entry.options[CONF_ACCESS_TOKEN] == ""
    assert CONF_ACCESS_TOKEN not in entry.data


async def test_changing_repository_updates_duplicate_detection(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="github:owner/old",
        data={
            "integration_domain": "",
            "repository": "owner/old",
            "asset_patterns": "*.zip",
        },
    )
    entry.add_to_hass(hass)
    github = AsyncMock()
    github.async_json.return_value = {"full_name": "owner/new", "private": False}
    with patch("custom_components.community_stats.config_flow.get_github", return_value=github):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "top_versions": 5,
                "include_prereleases": True,
                "update_interval": 12,
                "repository": "owner/new",
                "asset_patterns": "*.zip",
                "clear_token": False,
            },
        )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.unique_id == "github:owner/new"


async def test_auto_source_detects_core(hass, source_clients):
    from homeassistant.util import dt as dt_util

    from custom_components.community_stats.models import Snapshot

    analytics = AsyncMock()
    analytics.async_get.side_effect = [
        Snapshot({}, dt_util.utcnow()),
        Snapshot({"integrations": {"mqtt": 100}}, dt_util.utcnow()),
    ]
    with patch(
        "custom_components.community_stats.config_flow.get_analytics", return_value=analytics
    ):
        result = await start(hass, {"integration_domain": "mqtt", "analytics_source": "auto"})
    assert result["description_placeholders"]["source"] == "core"
    assert result["description_placeholders"]["repository"] == "—"


async def test_downloads_only_after_failed_domain_selection_clears_mapping(hass, source_clients):
    from custom_components.community_stats.models import SourceError

    github = AsyncMock()
    manifest = base64.b64encode(json.dumps({"domain": "first", "name": "First"}).encode())
    github.async_json.side_effect = [
        {"full_name": "owner/repo", "private": False},
        [{"type": "dir", "name": "first"}, {"type": "dir", "name": "second"}],
        {"content": manifest.decode()},
        SourceError("cannot_connect"),
        [],
    ]
    with patch("custom_components.community_stats.config_flow.get_github", return_value=github):
        result = await start(hass, {"repository": "owner/repo"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"integration_domain": "first"}
        )
        assert result["errors"] == {"base": "cannot_connect"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"integration_domain": "downloads-only"}
        )
        result = await finish(hass, result, asset_patterns="*.zip")
    assert result["data"]["integration_domain"] == ""


@pytest.mark.parametrize("assets", [None, 5, "invalid"])
async def test_malformed_release_assets_show_validation_error(hass, assets):
    github = AsyncMock()
    github.async_json.side_effect = [
        {"full_name": "owner/repo", "private": False},
        [{"assets": assets}],
    ]
    with patch("custom_components.community_stats.config_flow.get_github", return_value=github):
        result = await start(
            hass,
            {
                "integration_domain": "test_project",
                "analytics_source": "custom",
                "repository": "owner/repo",
            },
        )
    assert result["errors"] == {"base": "invalid_data"}


async def test_invalid_core_feed_structure_is_a_form_error(hass):
    from homeassistant.util import dt as dt_util

    from custom_components.community_stats.models import Snapshot

    analytics = AsyncMock()
    analytics.async_get.side_effect = [
        Snapshot({}, dt_util.utcnow()),
        Snapshot({"integrations": None}, dt_util.utcnow()),
    ]
    with patch(
        "custom_components.community_stats.config_flow.get_analytics", return_value=analytics
    ):
        result = await start(hass, {"integration_domain": "example", "analytics_source": "auto"})
    assert result["errors"] == {"base": "invalid_data"}
