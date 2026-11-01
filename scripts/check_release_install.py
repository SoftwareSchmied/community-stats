"""Boot a release archive in an isolated Home Assistant and verify restart recovery."""

import argparse
import asyncio
import json
import logging
import tempfile
from pathlib import Path
from zipfile import ZipFile

from homeassistant import bootstrap, loader
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant


async def boot(config_dir: Path) -> HomeAssistant:
    hass = HomeAssistant(str(config_dir))
    loader.async_setup(hass)
    result = await bootstrap.async_from_config_dict(
        {
            "homeassistant": {
                "name": "Community Stats release test",
                "latitude": 0,
                "longitude": 0,
                "elevation": 0,
                "time_zone": "UTC",
                "unit_system": "metric",
                "country": "DE",
            },
        },
        hass,
    )
    if result is None:
        raise RuntimeError("Home Assistant bootstrap failed")
    await hass.async_start()
    return hass


async def check(archive_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="community-stats-release-") as directory:
        config_dir = Path(directory)
        destination = config_dir / "custom_components" / "community_stats"
        with ZipFile(archive_path) as archive:
            for name in archive.namelist():
                if not (destination / name).resolve().is_relative_to(destination.resolve()):
                    raise ValueError("Unsafe archive member")
            archive.extractall(destination)
        hass = await boot(config_dir)
        try:
            # This must load the installed archive, never the source checkout.
            integration = await loader.async_get_integration(hass, "community_stats")
            installed_path = await hass.async_add_executor_job(Path(integration.file_path).resolve)
            assert installed_path == destination
            projects = [
                {
                    "integration_domain": "bosch_buderus_heating",
                    "analytics_source": "custom",
                    "discover_repository": False,
                },
                {
                    "integration_domain": "mqtt",
                    "analytics_source": "core",
                    "discover_repository": False,
                },
                {"repository": "Sturmi77/heatpump-hydraulic-card"},
            ]
            for index, project in enumerate(projects):
                result = await hass.config_entries.flow.async_init(
                    "community_stats", context={"source": "user"}
                )
                result = await hass.config_entries.flow.async_configure(result["flow_id"], project)
                assert result.get("step_id") == "project", result.get("errors")
                settings = {
                    "name": f"Release test {index}",
                    "top_versions": 2,
                    "include_prereleases": True,
                    "update_interval": 12,
                }
                if "repository" in project:
                    settings["asset_patterns"] = "heatpump-hydraulic-card.js"
                result = await hass.config_entries.flow.async_configure(result["flow_id"], settings)
                assert result["type"] == "create_entry", result.get("errors")
            await hass.async_block_till_done()
            assert all(
                entry.state == ConfigEntryState.LOADED
                for entry in hass.config_entries.async_entries("community_stats")
            )
            counts = {
                state.entity_id: state.state
                for state in hass.states.async_all("sensor")
                if state.attributes.get("state_class") == "measurement"
            }
            assert len(counts) == 12, counts
            assert all(value.isdigit() for value in counts.values()), counts
        finally:
            await hass.async_stop()
        hass = await boot(config_dir)
        try:
            await hass.async_block_till_done()
            restored = {
                state.entity_id: state.state
                for state in hass.states.async_all("sensor")
                if state.attributes.get("state_class") == "measurement"
            }
            assert restored.keys() == counts.keys(), (counts, restored)
            assert all(value.isdigit() for value in restored.values()), restored
            print(
                json.dumps(
                    {
                        "archive": archive_path.name,
                        "projects": 3,
                        "numeric_sensors": len(restored),
                        "restart_preserved_entity_ids": True,
                    },
                    indent=2,
                )
            )
        finally:
            await hass.async_stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)
    asyncio.run(check(args.archive.resolve()))
