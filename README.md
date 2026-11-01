# Community Stats

<img src="custom_components/community_stats/brand/icon.png" width="96" alt="Community Stats icon">

Track reported Home Assistant integration installations, GitHub release downloads, stars, forks, watchers and issues as Home Assistant sensors. Follow adoption over time, compare projects, and keep the history of each exact version separate.

[Deutsche Anleitung](docs/de.md) · [Dashboard examples](examples/dashboard.yaml) · [Report an issue](https://github.com/SoftwareSchmied/community-stats/issues)

| Project type | Reported installations | Version distribution | GitHub release downloads |
| --- | --- | --- | --- |
| Custom integration | Yes, when reported to Analytics | Exact reported versions | When release assets exist |
| Core integration | Yes, when reported to Analytics | No per-integration breakdown | No separately attributable downloads |
| Dashboard card or theme | Not available from HA Analytics | Not available from HA Analytics | When release assets exist |

## Install

Requires Home Assistant **2026.10 or newer**. Community Stats uses Home Assistant's own Recorder and statistics; no external database is required.

### HACS / Marketplace

Until the repository is included in the default catalog, add it as a custom repository:

1. Open HACS, or the Marketplace in Home Assistant versions that include it.
2. Open **Custom repositories** and add `https://github.com/SoftwareSchmied/community-stats` with category **Integration**.
3. Download **Community Stats** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Community Stats**.

Alternatively, download `community_stats.zip` from the [latest release](https://github.com/SoftwareSchmied/community-stats/releases/latest), extract its contents into `config/custom_components/community_stats/`, and restart Home Assistant. Do not nest a second `community_stats` directory inside it.

## Add projects

Add an entry for each project you want to monitor. Projects do not have to be installed on your Home Assistant instance.

- Enter an integration domain, for example `bosch_buderus_heating`, or a public GitHub repository such as `Sturmi77/heatpump-hydraulic-card`.
- You can enter both to map an integration to its repository explicitly.
- For an installed custom integration, its manifest's documentation or issue URL can suggest a repository. Review that suggestion: documentation links can refer to a different project, and the Analytics feed itself has no repository mapping.
- In the other direction, Community Stats reads `custom_components/*/manifest.json`. Repositories containing multiple integrations prompt for a selection. A repository without such a directory can still provide download sensors.
- **Automatic** Analytics detection checks custom integration data first, then core data. Choose **Core** or **Custom** explicitly if the same domain appears in both. An explicitly selected source also allows adding a domain before it appears in Analytics.
- To monitor only installation statistics, leave the repository empty and turn off the repository suggestion.

The confirmation step shows the proposed domain, source, repository and filenames from a recent release. Give the project a name and choose which files to count. Leave the filename patterns empty for repository statistics without download sensors. Each entry creates one service device containing its sensors and a refresh button.

## GitHub repository statistics

Each configured public repository also provides five numeric sensors:

| Sensor | Definition |
| --- | --- |
| Stars | Current stargazers |
| Forks | Current repository fork count |
| Watchers | Actual subscribers, using `subscribers_count`; GitHub's `watchers_count` is a legacy alias for stars |
| Total issues | Open plus closed issues, excluding pull requests |
| Open issues | Open issues, excluding pull requests |

These sensors support long-term statistics and can decrease. They work even when the repository has no release assets. Their history is independent of download filename filters. GitHub's repository-level `open_issues_count` includes pull requests, so Community Stats uses two issue searches with `is:issue` to obtain the precise counts. Incomplete search results are unavailable rather than published as partial totals.

Repository and issue-source status sensors keep search failures separate from stars, forks, watchers and release downloads. The search index can lag changes made directly on GitHub.

## Sensors and version history

Each configured source provides a total and, where available, sensors for exact versions. Installation versions and GitHub release tags remain separate: a manifest version `0.8.2` and a release tag `v0.8.2` are not assumed to be equivalent.

The default is to discover the **10 most popular versions per source**, ranked by installation or download count, not publication date. You can choose 1–100. Exact spellings such as `0.8.3-beta.1`, `v0.8.2` and `0.8.2+local` are preserved. Ties use the exact string for deterministic ordering.

Once selected, a version's sensor is retained and continues to update even when it drops out of the top selection. Tracking survives restarts and option changes. Consequently, the number of version sensors can grow beyond the configured top count. Reducing that count does not erase existing sensors. Disable unwanted entities through Home Assistant if you no longer want to record them.

Prereleases are included by default. Excluding them affects **new top-version selections**, not source totals or previously tracked sensors. A missing version becomes **unavailable**, not zero, and recovers under the same identity if it returns. An explicitly reported zero remains zero.

All count sensors use `state_class: measurement`. Installation counts may decrease; release asset deletion or replacement may also reduce download counts. Such decreases are not interpreted as counter resets. Recorder can keep hourly long-term min/max/mean statistics for enabled sensors. Detailed history retention follows your Recorder settings, and the sensors must not be excluded from recording. Statistics graphs show aggregates, not a reconstructed historical source feed.

History starts when you enable recording. Community Stats does not import past version adoption. The tracked versions are only a selection, so their sum need not equal the installation total.

## What downloads mean

GitHub exposes download counters for **files attached to releases**. It does not provide equivalent counters for arbitrary repository files, Git clones, or automatically generated source archives. Whether an installation through HACS increments a counter depends on which file HACS downloads.

Select filenames or case-sensitive shell patterns, one per line:

```text
heatpump-hydraulic-card.js
```

or:

```text
*.zip
```

Patterns apply to all published releases. Each matching asset is counted once even if several patterns match it. Be deliberate when using `*`: separate ZIP and JS assets, checksums, or alternative packages all have separate counters. A single filename is suggested only when a recent release contains a single asset.

The total includes matching assets across **all currently available published releases**, including prereleases. Draft releases are excluded. A release with no matching asset is unavailable, rather than counted as zero. When no release has a matching asset, the total is also unavailable.

Changing the repository or filename patterns starts **new download sensor identities** so histories with different meanings are not mixed. Old entities can remain unavailable in the registry; keep or remove them according to your history needs. Returning to the same repository and normalized patterns restores the original identities.

Downloads count requests, not users or active installations. Repeated downloads and updates are included; uninstalling does not subtract a download. Community Stats never labels these counters as installations.

## Updates and GitHub limits

- **Without a GitHub token:** all anonymous projects in this Home Assistant instance share a round-robin queue. One project's GitHub statistics are fetched every **61 minutes**. With ten projects, each is refreshed about every **10 hours 10 minutes**. The first project can start immediately when no previous pause is active; additional projects wait their turn. This schedule replaces the configured interval for anonymous GitHub statistics.
- **With a GitHub token:** GitHub uses the project's configured interval, default **12 hours**, configurable from 1 to 168 hours. Token-based projects are independent of the anonymous queue. An invalid token reports an authentication error; it does not switch to anonymous access automatically.
- **Home Assistant Analytics** always uses the configured interval, independently of GitHub's queue.
- Use the device's **Refresh** button or Home Assistant's `homeassistant.update_entity` action for a manual update. Recent successful data is shared for **five minutes**; repeated clicks do not bypass this cache, the anonymous queue or GitHub's quota.
- Queue order, the next permitted slot and the latest GitHub observations survive reloads and restarts. Waiting keeps the previous observation and its original last-success timestamp. Before the first observation, the affected sensors are unavailable and source status shows **Waiting for first GitHub update**. A failed request makes that source unavailable until a successful turn; other sources remain independent. A restart never triggers a burst of missed updates.
- Analytics documents, repository metadata, issue searches and GitHub release scans are shared between projects using the same source and credential. One API page can contain up to 100 releases and feeds many sensors.
- A repository with one page of releases normally uses **four GitHub requests per refresh**: one for repository metadata, two for issue counts and one for releases. Without download sensors, it uses three. Setup discovery and additional release pages can require more requests.
- All pages must be fetched before a complete download total is published. A scan interrupted by a rate limit resumes when the limit permits; without a token it also waits for that project's next turn. No partial total is exposed. A scan older than 24 hours starts again.
- GitHub normally permits **60 unauthenticated REST requests per hour per public IP**, or **5,000 authenticated requests per hour per account**. Other applications can share those quotas. Community Stats uses a local ceiling of 50 or 4,500 requests respectively and also honors GitHub's remaining quota, reset time and retry headers.
- A GitHub token is optional. Use a token with only the access needed to read public repositories; no write permissions are required. Configure it per project. Entries using the same token share a client. Changing or removing it is available in **Configure**.
- Issue searches have a separate quota. Community Stats tracks its reset time separately, so a search-only limit does not block other repository data. Large collections may need several quota windows; the integration resumes automatically.
- Conditional requests reuse unchanged data. GitHub exempts authenticated `304 Not Modified` responses from its primary quota; do not assume that every request receives a 304.

Analytics, release downloads, repository metadata and issue-search availability are tracked independently. Source status and last-successful-update sensors explain missing data. The GitHub retry-time sensor indicates the earliest rate-limit retry; an anonymous project's turn may be later. Downloadable diagnostics include the scheduling mode and an estimate of that project's next queue slot. Setup discovery uses separate requests subject to the same API limits; the rotation governs sensor updates. Other Home Assistant instances and applications on the same public IP do not share this queue.

A remaining-request diagnostic sensor is disabled by default; its value is the last observed standard REST quota, not an independently reserved allowance or the search quota.

## Data sources and privacy

- [Custom integration Analytics](https://analytics.home-assistant.io/custom_integrations.json)
- [Core integration Analytics](https://analytics.home-assistant.io/current_data.json)
- [GitHub Releases REST API](https://docs.github.com/en/rest/releases/releases)
- [GitHub rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

Home Assistant Analytics counts installations that voluntarily report the relevant usage data. These are not all users, downloads, devices, or configured accounts. Core integrations have no separate public version breakdown in this feed.

Community Stats reads the public sources and stores sensor history locally through Home Assistant. It does not need an API token for your own Home Assistant. An optional GitHub token is stored in Home Assistant's config entry and redacted from downloadable diagnostics. No credentials belong in repository files, issue reports or dashboard examples. Standard Home Assistant Analytics participation remains controlled by your existing Home Assistant settings.

## Development and releases

See [development and release instructions](docs/development.md). Pull requests and pushes run the tests, Hassfest and HACS validation. Catalog inclusion is a separate review by the HACS/Marketplace maintainers; a working custom repository does not imply that review is complete.

Maintained by [SoftwareSchmied](https://github.com/SoftwareSchmied). Licensed under [MIT](LICENSE).
