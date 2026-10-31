"""Read-only smoke check against the public sources; excluded from offline tests."""

import asyncio
import json

from aiohttp import ClientSession

from custom_components.community_stats.api import AnalyticsClient, GitHubClient
from custom_components.community_stats.models import parse_analytics, parse_downloads, top_versions


async def main() -> None:
    async with ClientSession() as session:
        analytics = AnalyticsClient(session)
        github = GitHubClient(session, "")
        custom, core, releases = await asyncio.gather(
            analytics.async_get("custom"),
            analytics.async_get("core"),
            github.async_releases("Sturmi77/heatpump-hydraulic-card"),
        )
        installations = parse_analytics(custom.body, "bosch_buderus_heating", "custom")
        core_counts = parse_analytics(core.body, "mqtt", "core")
        downloads = parse_downloads(releases.body, ["heatpump-hydraulic-card.js"])
        print(
            json.dumps(
                {
                    "custom": {
                        "domain": "bosch_buderus_heating",
                        "total": installations.total,
                        "top_versions": top_versions(installations, 3, True),
                    },
                    "core": {"domain": "mqtt", "total": core_counts.total},
                    "github": {
                        "repository": "Sturmi77/heatpump-hydraulic-card",
                        "releases": len(releases.body),
                        "downloads": downloads.total,
                        "remaining_requests": github.remaining,
                    },
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
