# Development and release process

## Local checks

Use Python 3.14 and Linux, or Linux through WSL. The Home Assistant test suite is pinned to Home Assistant 2026.10.4.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
python -m pytest --disable-socket --allow-unix-socket --cov=custom_components.community_stats --cov-fail-under=85
python scripts/build_release.py
```

Tests run with external sockets disabled. They exercise the real Home Assistant config flow, config entries, entity registry, sensors and unload/reload lifecycle. Public source data is replaced with controlled responses for rate limits, exact versions and failure recovery.

The Recorder test additionally compiles actual hourly statistics for decreasing installation counts. To exercise a release archive against public data in a temporary Home Assistant instance, including a full stop and startup, run:

```sh
python scripts/check_release_install.py dist/community_stats.zip
```

This optional check requires network access and can install additional Home Assistant bootstrap dependencies into the development environment. It loads the archive into a fresh temporary configuration and does not connect to an existing Home Assistant installation.

The brand images are original geometric artwork. To regenerate them, install Pillow in a development environment and run `python scripts/build_brand.py`; Pillow is not a runtime dependency.

## Release

1. Update the integration's `manifest.json` version, `CHANGELOG.md`, and `docs/releases/VERSION.md`.
2. Push a neutral, descriptive commit and wait for all **Validate** jobs to succeed on that commit. HACS validation must pass without ignored checks.
3. Run `python scripts/build_release.py`, or download the release archive artifact from the successful workflow.
4. Create the matching tag and a full GitHub release with the `community_stats.zip` asset. The archive contains the files *inside* `custom_components/community_stats/`; HACS handles the destination directory.
5. Verify a clean download and installation through HACS or Marketplace.

Example for the initial release:

```sh
git tag v0.1.0
git push origin v0.1.0
gh release create v0.1.0 dist/community_stats.zip --verify-tag --title "Community Stats 0.1.0" --notes-file docs/releases/0.1.0.md
```

## Default catalog submission

The [HACS inclusion requirements](https://www.hacs.xyz/docs/publish/include/) require a public repository with a description, topics, issues, an OSI-approved license, valid local brand assets, successful HACS/Hassfest actions and a full GitHub release created after those checks.

Once these requirements are met, the repository owner can add `SoftwareSchmied/community-stats` in alphabetical order to the `integration` JSON list in `hacs/default`, using a dedicated branch in their fork. Complete the pull request template with links to the release and successful action runs. Inclusion remains subject to the maintainers' review; custom-repository installation works independently of that queue.
