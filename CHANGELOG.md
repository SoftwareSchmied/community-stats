# Changelog

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
