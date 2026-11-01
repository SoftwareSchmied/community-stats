# Validation of 0.3.0

Validated on 1 November 2026 with Home Assistant 2026.10.4 and Python 3.14.7 on Linux.

| Check | Result |
| --- | --- |
| Automated suite | 102 tests pass with external sockets disabled |
| Coverage including branches | 91.91% |
| Ruff lint and formatting | Pass |
| Hassfest | No invalid integrations |
| Real Recorder statistics | Hourly min/max/mean for falling installation counts match the input data; no counter-reset sum |
| Release archive installation | Three projects configured from the extracted archive in an isolated Home Assistant |
| Restart recovery | All 12 numeric sensors keep their entity IDs after shutdown and startup |
| Public source requests | Custom integration, core integration, release downloads and repository metrics return numeric values |

The automated tests cover exact version identities, rank changes, missing and returning versions, zero and decreasing counts, option reloads, token removal and migration, pagination, incomplete search results, independent search limits, retry scheduling and shared manual-refresh caching.

Fourteen queue regression cases cover the shared 61-minute rotation, waiting states, independent Analytics intervals, normal authenticated refreshes, manual actions, restored observations, restart ordering, token changes, rate-limit recovery, changed source identities, unloaded projects and concurrent refreshes. Tests advance Home Assistant timers to verify the schedule without waiting in real time.

GitHub metrics distinguish actual subscribers from stars, and issue searches exclude pull requests. Changing release filename filters preserves repository-metric histories. Empty filename patterns permit repository statistics without download sensors.

The release installation test uses a temporary configuration and the published data sources, not an existing Home Assistant installation. It checks backend configuration flows and entity states; it is not a visual dashboard test. The standalone environment's optional media-library warnings do not affect these statistics checks.

Reproduce the checks with the commands in [development.md](development.md). HACS and Hassfest also run in the repository's [Validate workflow](https://github.com/SoftwareSchmied/community-stats/actions/workflows/validate.yml).
