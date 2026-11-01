# Changelog

## 0.3.0

- Rotate GitHub projects without a token through one shared queue, with one project every 61 minutes.
- Keep the configured refresh interval for authenticated GitHub projects and Home Assistant Analytics.
- Preserve queue fairness, the next permitted slot and previous GitHub observations across reloads and restarts.
- Keep manual refreshes and rate-limit retries inside the anonymous schedule.
- Show an explicit waiting status before a project's first GitHub observation and include scheduling details in diagnostics.
- Cover queue timing, simultaneous refreshes, restarts, token changes, failures and cache identity with regression tests.

## 0.2.0

- Add sensors for GitHub stars, forks, actual watchers, total issues and open issues.
- Exclude pull requests from issue counts and respect the separate search quota.
- Support repository statistics without release downloads by leaving asset patterns empty.
- Remove superseded GitHub tokens from the original config data, including cleanup of entries edited in 0.1.0.
- Save option and identity changes together so active projects immediately use a changed repository or token.
- Clear a previously selected integration when switching to downloads only after a failed setup attempt.
- Show a validation error for malformed Analytics and release asset data during setup.
- Add regression tests, real Recorder statistics verification and an isolated release installation/restart check.

## 0.1.0

- Configure multiple projects through the Home Assistant interface.
- Track reported core and custom integration installations.
- Preserve exact custom integration versions and GitHub release tags in separate sensor histories.
- Count selected GitHub release assets with complete pagination and quota handling.
- Retain previously selected versions across rank changes and restarts.
- Provide independent source status, manual refresh, diagnostics and long-term statistics.
- Include English and German interfaces, dashboard examples and HACS packaging.
