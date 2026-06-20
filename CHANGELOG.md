# Changelog

All notable changes to EternalRichPresence are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `.gitattributes`, `pyproject.toml` (ruff config), `CHANGELOG.md`, and a small
  unit test for the Listen Along join-secret round trip.
- `AUTO_ACCEPT_JOIN_REQUESTS` and `COVER_ART_UPLOAD` config options for control
  over Listen Along join handling and album-art uploads.
- Shared `app_info.app_root()` helper plus `PLACEHOLDER_CLIENT_ID` and
  `DEFAULT_SPOTIFY_REDIRECT_URI` constants (single source of truth).

### Changed
- Album cover art now prefers expiring image hosts (litterbox 24h, then 0x0 24h)
  before falling back to the permanent catbox.moe, so "now playing" artwork is no
  longer permanently published by default.
- Spotify OAuth token cache moved to `%LOCALAPPDATA%\EternalRichPresence` instead
  of sitting next to the executable.
- `version_info.txt` is regenerated from `app_info.py` at build time so the exe's
  embedded version cannot drift from the app version.
- Consolidated duplicated path resolution, multipart upload, and Spotify bootstrap
  logic; modernized typing.

### Fixed
- A pre-existing `config.py` with a placeholder Client ID now correctly opens the
  setup window instead of silently failing to connect to Discord.
- The setup window writes config values safely — a quote or backslash in any field
  no longer corrupts `config.py`.
- Discord IPC frames are fully reassembled; a partial pipe read no longer drops a
  Listen Along join event.
- Listen Along links no longer collapse to "Unknown" for emoji/CJK track titles.
- Transient Spotify states (no active device / server error) no longer pop a
  "press Play in Spotify" message and then open an Apple Music search anyway.

## [2.0.0] - 2026

- Official EternalRichPresence Discord application preconfigured out of the box.
- Tray-first UX with advanced tools grouped under a Dev submenu.
- Listen Along via `eternalrp://` and `discord-{client_id}://` handlers.
- Apple Music (iTunes COM + Windows SMTC) and Spotify providers with live cover art.
