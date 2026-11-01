"""Compile real Recorder statistics for decreasing installation counts."""

from datetime import timedelta

import pytest
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
    do_adhoc_statistics,
)
from test_integration import entity_id, setup_project

from custom_components.community_stats.models import Snapshot


@pytest.fixture
def mock_recorder_before_hass(recorder_db_url):
    """Prepare the database before the shared Home Assistant fixture starts."""


@pytest.mark.freeze_time("2026-11-01 00:00:00+00:00")
async def test_decreasing_counts_produce_hourly_statistics(
    recorder_mock, hass, source_clients, freezer
):
    analytics, _ = source_clients
    start = dt_util.utcnow()
    entry = await setup_project(hass, repository="")
    sensor = entity_id(hass, entry, "installations")
    await async_wait_recording_done(hass)
    for index in range(12):
        moment = start + timedelta(minutes=5 * index)
        freezer.move_to(moment)
        count = 120 - index
        analytics.async_get.return_value = Snapshot(
            {"test_project": {"total": count, "versions": {"0.8.2": count}}}, moment
        )
        await entry.runtime_data.async_refresh()
        await async_wait_recording_done(hass)
        freezer.move_to(moment + timedelta(minutes=5))
        do_adhoc_statistics(hass, start=moment)
        await async_wait_recording_done(hass)
    rows = await hass.async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        start + timedelta(hours=1),
        {sensor},
        "hour",
        None,
        {"min", "max", "mean", "sum"},
    )
    assert len(rows[sensor]) == 1
    row = rows[sensor][0]
    assert row["min"] == 109
    assert row["max"] == 120
    assert row["mean"] == pytest.approx(114.5)
    assert row.get("sum") is None
