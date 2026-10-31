"""UI setup, repository discovery and project options."""

import base64
import json
import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.loader import IntegrationNotFound, async_get_integration

from .api import get_analytics, get_github
from .const import (
    CONF_INTEGRATION,
    CONF_INTERVAL,
    CONF_PATTERNS,
    CONF_PRERELEASE,
    CONF_REPOSITORY,
    CONF_SOURCE,
    CONF_TOP,
    DEFAULT_INTERVAL,
    DEFAULT_TOP,
    DOMAIN,
)
from .models import SourceError, normalize_repository, parse_patterns, repository_from_manifest

TOKEN_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)
TEXT_SELECTOR = selector.TextSelector()
PATTERN_SELECTOR = selector.TextSelector(selector.TextSelectorConfig(multiline=True))


def tuning_schema(values: dict[str, Any]) -> dict:
    """Shared per-project settings for setup and options."""
    return {
        vol.Required(CONF_TOP, default=values.get(CONF_TOP, DEFAULT_TOP)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Required(CONF_PRERELEASE, default=values.get(CONF_PRERELEASE, True)): bool,
        vol.Required(CONF_INTERVAL, default=values.get(CONF_INTERVAL, DEFAULT_INTERVAL)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=168)
        ),
    }


class CommunityStatsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Add one project at a time, as often as needed."""

    VERSION = 1

    def __init__(self) -> None:
        self._candidate: dict[str, Any] = {}
        self._directories: list[str] = []
        self._assets: list[str] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
        return OptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Accept a domain, a repository, or an explicit mapping between both."""
        errors = {}
        if user_input is not None:
            self._candidate = dict(user_input)
            self._candidate[CONF_INTEGRATION] = user_input.get(CONF_INTEGRATION, "").strip()
            self._candidate[CONF_REPOSITORY] = user_input.get(CONF_REPOSITORY, "").strip()
            self._candidate[CONF_ACCESS_TOKEN] = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            domain = self._candidate[CONF_INTEGRATION]
            if not domain and not self._candidate[CONF_REPOSITORY]:
                errors["base"] = "project_required"
            elif domain and not re.fullmatch(r"[a-z0-9_]+", domain):
                errors[CONF_INTEGRATION] = "invalid_domain"
            else:
                try:
                    result = await self._async_prepare()
                    if result is not None:
                        return result
                    return await self.async_step_project()
                except ValueError:
                    errors[CONF_REPOSITORY] = "invalid_repository"
                except SourceError as err:
                    errors["base"] = err.code
        defaults = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INTEGRATION, default=defaults.get(CONF_INTEGRATION, "")
                    ): TEXT_SELECTOR,
                    vol.Optional(
                        CONF_REPOSITORY, default=defaults.get(CONF_REPOSITORY, "")
                    ): TEXT_SELECTOR,
                    vol.Required(
                        CONF_SOURCE, default=defaults.get(CONF_SOURCE, "auto")
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["auto", "custom", "core"], translation_key="analytics_source"
                        )
                    ),
                    vol.Required(
                        "discover_repository", default=defaults.get("discover_repository", True)
                    ): bool,
                    vol.Optional(CONF_ACCESS_TOKEN): TOKEN_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def _async_prepare(self) -> FlowResult | None:
        """Resolve available metadata without depending on a GitHub search index."""
        domain = self._candidate[CONF_INTEGRATION]
        repository = self._candidate[CONF_REPOSITORY]
        source = self._candidate.get(CONF_SOURCE, "auto")
        local = None
        if domain:
            try:
                local = await async_get_integration(self.hass, domain)
            except IntegrationNotFound:
                pass
            if source == "auto":
                analytics = get_analytics(self.hass)
                custom = await analytics.async_get("custom")
                if domain in custom.body:
                    source = "custom"
                else:
                    core = await analytics.async_get("core")
                    if domain in core.body.get("integrations", {}) or (local and local.is_built_in):
                        source = "core"
                    else:
                        source = "custom"
            if source == "core":
                if repository:
                    raise SourceError("core_repository")
            elif not repository and local and self._candidate.get("discover_repository", True):
                repository = repository_from_manifest(local.manifest) or ""
            self._candidate[CONF_NAME] = local.name if local else domain
        self._candidate[CONF_SOURCE] = "custom" if source == "auto" else source
        if repository:
            repository = normalize_repository(repository)
            github = get_github(self.hass, self._candidate[CONF_ACCESS_TOKEN])
            info = await github.async_json(f"/repos/{repository}")
            if not isinstance(info, dict) or info.get("private"):
                raise SourceError("public_repository_required")
            repository = normalize_repository(info.get("full_name", repository))
            self._candidate[CONF_REPOSITORY] = repository
            if not domain:
                self._candidate[CONF_NAME] = repository.split("/")[1]
                try:
                    directories = await github.async_json(
                        f"/repos/{repository}/contents/custom_components"
                    )
                    if not isinstance(directories, list):
                        raise SourceError("invalid_data")
                    self._directories = [
                        item["name"]
                        for item in directories
                        if isinstance(item, dict)
                        and item.get("type") == "dir"
                        and re.fullmatch(r"[a-z0-9_]+", item.get("name", ""))
                    ]
                except SourceError as err:
                    if err.code != "not_found":
                        raise
                    self._directories = []
                if len(self._directories) > 1:
                    return await self.async_step_integration()
                if self._directories:
                    await self._async_read_manifest(self._directories[0])
            await self._async_asset_suggestions()
        return None

    async def _async_read_manifest(self, directory: str) -> None:
        repository = self._candidate[CONF_REPOSITORY]
        github = get_github(self.hass, self._candidate[CONF_ACCESS_TOKEN])
        result = await github.async_json(
            f"/repos/{repository}/contents/custom_components/{directory}/manifest.json"
        )
        try:
            manifest = json.loads(base64.b64decode(result["content"]))
            domain = manifest["domain"]
            if not isinstance(domain, str) or not re.fullmatch(r"[a-z0-9_]+", domain):
                raise ValueError
        except (KeyError, TypeError, ValueError) as err:
            raise SourceError("invalid_data") from err
        self._candidate[CONF_INTEGRATION] = domain
        self._candidate[CONF_SOURCE] = "custom"
        self._candidate[CONF_NAME] = str(manifest.get("name", domain))

    async def async_step_integration(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Let the user choose when a repository contains more than one integration."""
        errors = {}
        if user_input is not None:
            try:
                if user_input[CONF_INTEGRATION] != "downloads-only":
                    await self._async_read_manifest(user_input[CONF_INTEGRATION])
                await self._async_asset_suggestions()
                return await self.async_step_project()
            except SourceError as err:
                errors["base"] = err.code
        return self.async_show_form(
            step_id="integration",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INTEGRATION): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[*self._directories, "downloads-only"],
                            translation_key="integration_choice",
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def _async_asset_suggestions(self) -> None:
        github = get_github(self.hass, self._candidate[CONF_ACCESS_TOKEN])
        releases = await github.async_json(
            f"/repos/{self._candidate[CONF_REPOSITORY]}/releases?per_page=100&page=1"
        )
        if not isinstance(releases, list):
            raise SourceError("invalid_data")
        self._assets = []
        for release in releases:
            if not isinstance(release, dict):
                raise SourceError("invalid_data")
            if release.get("draft"):
                continue
            self._assets = [
                asset["name"]
                for asset in release.get("assets", [])
                if isinstance(asset, dict) and isinstance(asset.get("name"), str)
            ]
            if self._assets:
                break
        if len(self._assets) == 1:
            self._candidate[CONF_PATTERNS] = self._assets[0]

    async def async_step_project(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm discovered sources and select the files to count."""
        errors = {}
        if user_input is not None:
            if self._candidate.get(CONF_REPOSITORY) and not parse_patterns(
                user_input.get(CONF_PATTERNS, "")
            ):
                errors[CONF_PATTERNS] = "patterns_required"
            elif not user_input.get(CONF_NAME, "").strip():
                errors[CONF_NAME] = "name_required"
            else:
                self._candidate.update(user_input)
                self._candidate.pop("discover_repository", None)
                domain = self._candidate[CONF_INTEGRATION]
                unique_id = (
                    f"{self._candidate[CONF_SOURCE]}:{domain}"
                    if domain
                    else f"github:{self._candidate[CONF_REPOSITORY].lower()}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=self._candidate[CONF_NAME].strip(), data=self._candidate
                )
        values = {**self._candidate, **(user_input or {})}
        fields = {
            vol.Required(
                CONF_NAME, default=values.get(CONF_NAME, "Community Stats")
            ): TEXT_SELECTOR,
            **tuning_schema(values),
        }
        if self._candidate.get(CONF_REPOSITORY):
            fields[vol.Required(CONF_PATTERNS, default=values.get(CONF_PATTERNS, ""))] = (
                PATTERN_SELECTOR
            )
        return self.async_show_form(
            step_id="project",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={
                "integration": self._candidate.get(CONF_INTEGRATION) or "—",
                "source": self._candidate.get(CONF_SOURCE, "—"),
                "repository": self._candidate.get(CONF_REPOSITORY) or "—",
                "assets": ", ".join(self._assets[:10]) or "—",
            },
        )


class OptionsFlow(config_entries.OptionsFlow):
    """Change tracking, polling, the GitHub repository and its access token."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        settings = {**self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            values = dict(user_input)
            token = values.pop(CONF_ACCESS_TOKEN, "").strip()
            clear_token = values.pop("clear_token", False)
            values[CONF_ACCESS_TOKEN] = (
                "" if clear_token else token or settings.get(CONF_ACCESS_TOKEN, "")
            )
            repository = values.get(CONF_REPOSITORY, "").strip()
            try:
                if not repository and not settings.get(CONF_INTEGRATION):
                    raise SourceError("project_required")
                if repository:
                    if settings.get(CONF_SOURCE) == "core" and settings.get(CONF_INTEGRATION):
                        raise SourceError("core_repository")
                    repository = normalize_repository(repository)
                    if not parse_patterns(values.get(CONF_PATTERNS, "")):
                        raise SourceError("patterns_required")
                    if repository != settings.get(CONF_REPOSITORY) or values[
                        CONF_ACCESS_TOKEN
                    ] != settings.get(CONF_ACCESS_TOKEN, ""):
                        info = await get_github(self.hass, values[CONF_ACCESS_TOKEN]).async_json(
                            f"/repos/{repository}"
                        )
                        if not isinstance(info, dict) or info.get("private"):
                            raise SourceError("public_repository_required")
                        repository = normalize_repository(info.get("full_name", repository))
                values[CONF_REPOSITORY] = repository
                if not settings.get(CONF_INTEGRATION):
                    unique_id = f"github:{repository.lower()}"
                    if any(
                        entry.entry_id != self.config_entry.entry_id
                        and entry.unique_id == unique_id
                        for entry in self.hass.config_entries.async_entries(DOMAIN)
                    ):
                        raise SourceError("already_configured")
                    if self.config_entry.unique_id != unique_id:
                        self.hass.config_entries.async_update_entry(
                            self.config_entry, unique_id=unique_id
                        )
                return self.async_create_entry(data=values)
            except ValueError:
                errors[CONF_REPOSITORY] = "invalid_repository"
            except SourceError as err:
                errors["base"] = err.code
            settings.update(user_input)
        fields = tuning_schema(settings)
        fields.update(
            {
                vol.Optional(
                    CONF_REPOSITORY, default=settings.get(CONF_REPOSITORY, "")
                ): TEXT_SELECTOR,
                vol.Optional(
                    CONF_PATTERNS, default=settings.get(CONF_PATTERNS, "")
                ): PATTERN_SELECTOR,
                vol.Optional(CONF_ACCESS_TOKEN): TOKEN_SELECTOR,
                vol.Optional("clear_token", default=False): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields), errors=errors)
