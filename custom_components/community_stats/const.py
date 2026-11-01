"""Constants for Community Stats."""

from homeassistant.const import Platform

DOMAIN = "community_stats"
PLATFORMS = [Platform.SENSOR, Platform.BUTTON]
CONF_INTEGRATION = "integration_domain"
CONF_REPOSITORY = "repository"
CONF_SOURCE = "analytics_source"
CONF_TOP = "top_versions"
CONF_PRERELEASE = "include_prereleases"
CONF_PATTERNS = "asset_patterns"
CONF_INTERVAL = "update_interval"
DEFAULT_TOP = 10
DEFAULT_INTERVAL = 12
MIN_REFRESH_SECONDS = 300
GITHUB_ROTATION_SECONDS = 61 * 60
CUSTOM_URL = "https://analytics.home-assistant.io/custom_integrations.json"
CORE_URL = "https://analytics.home-assistant.io/current_data.json"
GITHUB_API = "https://api.github.com"
