# Validation of 0.4.0

Validated on 1 November 2026 with Home Assistant 2026.10.4 and Python 3.14.7 on Linux.

| Check | Result |
| --- | --- |
| Automated suite | 118 tests pass with external sockets disabled |
| Coverage including branches | 92.16% |
| Ruff lint and formatting | Pass |
| Hassfest | No invalid integrations |
| Real Recorder statistics | Hourly min/max/mean for falling installation counts match the input data; no counter-reset sum |
| Release archive installation | Three projects configured from the extracted archive in an isolated Home Assistant |
| Restart recovery | All 12 numeric sensors keep their entity IDs after shutdown and startup |
| Public source requests | Custom integration, core integration, release downloads and repository metrics return numeric values |

The automated tests cover exact version identities, rank changes, missing and returning versions, zero and decreasing counts, option reloads, token removal and migration, pagination, incomplete search results, independent search limits, retry scheduling and shared manual-refresh caching.

Setup checks cover single-file proposals, HACS filename matching, missing or malformed metadata, optional metadata rate limits and user overrides. Number-selector values retain integer types in setup and options. The serialized form definitions use number boxes, expose the selected values and show hours as the interval unit; range and whole-number validation were also checked.

GitHub selection tests cover zero-download releases, publication dates independent of commit dates, version numbers and response order, timestamp ties and time zones, malformed dates, drafts, missing matching assets and prerelease exclusion. Entity tests verify that new releases enter the selection while old entities keep their identities and receive updated counts. Cached counts from earlier versions survive reloads and gain publication metadata at the next permitted anonymous update.

Fourteen queue regression cases cover the shared 61-minute rotation, waiting states, independent Analytics intervals, normal authenticated refreshes, manual actions, restored observations, restart ordering, token changes, rate-limit recovery, changed source identities, unloaded projects and concurrent refreshes. Tests advance Home Assistant timers to verify the schedule without waiting in real time.

GitHub metrics distinguish actual subscribers from stars, and issue searches exclude pull requests. Changing release filename filters preserves repository-metric histories. Empty filename patterns permit repository statistics without download sensors.

The release installation test uses a temporary configuration and the published data sources, not an existing Home Assistant installation. It checks backend configuration flows and entity states; it is not a visual dashboard test. The standalone environment's optional media-library warnings do not affect these statistics checks.

Reproduce the checks with the commands in [development.md](development.md). HACS and Hassfest also run in the repository's [Validate workflow](https://github.com/SoftwareSchmied/community-stats/actions/workflows/validate.yml).
