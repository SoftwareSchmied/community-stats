"""Data semantics and permanent version identities."""

import pytest

from custom_components.community_stats.models import (
    Counts,
    SourceError,
    normalize_repository,
    parse_analytics,
    parse_downloads,
    parse_patterns,
    repository_from_manifest,
    top_versions,
    version_key,
)


@pytest.mark.parametrize("value", [-1, 1.5, True, "123", None])
def test_invalid_total_is_not_zero(value):
    with pytest.raises(SourceError, match="invalid_data"):
        parse_analytics({"test": {"total": value}}, "test", "custom")


def test_core_count_and_missing_domain():
    assert parse_analytics({"integrations": {"mqtt": 0}}, "mqtt", "core").total == 0
    with pytest.raises(SourceError, match="not_found"):
        parse_analytics({"integrations": {}}, "mqtt", "core")


def test_exact_versions_and_missing_version_data():
    versions = {"0.8.2": 12, "0.8.3-beta.1": 3, "v0.8.2": 2, "0.8.2+local": 1, "bad": -1}
    counts = parse_analytics({"test": {"total": 18, "versions": versions}}, "test", "custom")
    assert counts.versions == {key: value for key, value in versions.items() if key != "bad"}
    assert parse_analytics({"test": {"total": 18}}, "test", "custom").versions == {}
    with pytest.raises(SourceError, match="not_found"):
        parse_analytics({}, "test", "custom")


def test_rank_by_count_not_version_date_and_keep_prereleases_optional():
    counts = Counts(versions={"9.0.0": 1, "0.8.2": 90, "0.8.3-beta.1": 100, "0.7.0": 90})
    assert top_versions(counts, 2, True) == ["0.8.3-beta.1", "0.7.0"]
    assert top_versions(counts, 2, False) == ["0.7.0", "0.8.2"]


def test_prerelease_flag_applies_to_nonstandard_github_tags():
    counts = Counts(versions={"preview-build": 10, "stable": 2}, prereleases={"preview-build"})
    assert top_versions(counts, 10, False) == ["stable"]


def test_slug_collisions_do_not_merge_versions():
    assert version_key("0.8.2+local") != version_key("0.8.2-local")
    assert version_key("v0.8.2") != version_key("0.8.2")


def test_download_patterns_count_each_asset_once(releases):
    result = parse_downloads(releases + [releases[0]], ["*.zip", "project.*"])
    assert result.total == 215
    assert result.versions == {"v0.8.2": 175, "v0.8.3-beta.1": 40}
    assert parse_downloads(releases, ["*.zip"]).total == 190


def test_missing_download_assets_is_unavailable_but_explicit_zero_is_valid(releases):
    with pytest.raises(SourceError, match="no_matching_assets"):
        parse_downloads(releases, ["missing.js"])
    releases[0]["assets"][0]["download_count"] = 0
    assert parse_downloads(releases[:1], ["*.zip"]).total == 0


def test_invalid_download_count_cannot_make_a_partial_total(releases):
    releases[1]["assets"][0]["download_count"] = -5
    with pytest.raises(SourceError, match="invalid_data"):
        parse_downloads(releases, ["*.zip"])


def test_drafts_are_not_counted(releases):
    releases[0]["draft"] = True
    assert parse_downloads(releases, ["*.zip"]).total == 40


@pytest.mark.parametrize(
    "value",
    [
        "http://github.com/owner/repo",
        "https://example.com/owner/repo",
        "https://github.com@evil.invalid/owner/repo",
        "owner/repo/issues",
        "owner/..",
        "https://github.com/owner/repo?token=secret",
        "https://github.com:443/owner/repo",
    ],
)
def test_repository_cannot_change_host_or_include_secrets(value):
    with pytest.raises(ValueError):
        normalize_repository(value)


def test_repository_normalization_and_manifest_discovery():
    assert normalize_repository("https://github.com/Owner/repo.git/") == "Owner/repo"
    assert (
        repository_from_manifest({"issue_tracker": "https://github.com/Owner/repo/issues"})
        == "Owner/repo"
    )
    assert repository_from_manifest({"documentation": "https://example.com/docs"}) is None
    assert parse_patterns("*.zip\n\n  *.js\n*.zip") == ["*.js", "*.zip"]
