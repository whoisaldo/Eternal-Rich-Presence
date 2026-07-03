# EternalRichPresence

[![CI](https://github.com/whoisaldo/Eternal-Rich-Presence/actions/workflows/ci.yml/badge.svg)](https://github.com/whoisaldo/Eternal-Rich-Presence/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue)](LICENSE)

**The official Discord Rich Presence bridge for Apple Music and Spotify, by Ali Younes ([@whoisaldo](https://github.com/whoisaldo)).**

EternalRichPresence is a lightweight Windows tray app that shows your current song on Discord with live cover art and a Listen Along link.

**Requirements:** Windows 10+, Discord desktop app, and either the prebuilt `.exe` or Python 3.9+ (developed and tested on 3.13) for source installs.

## Quick Start (prebuilt)

Download the latest `EternalRichPresence.exe` from the [official repository](https://github.com/whoisaldo/Eternal-Rich-Presence).

1. Launch the exe.
2. The app is already configured for Discord.
3. It drops into your system tray automatically.
4. Start playing music in Apple Music or Spotify.
5. Optional: use the `Dev` tray menu later if you want to add Spotify credentials or inspect logs.

You do **not** need to run the app as Administrator for normal use. Listen Along protocol handlers are registered per user.

## Setup Notes

### Discord

- Official releases already use the built-in EternalRichPresence Discord application.
- End users do not need to create a Discord app or look up a Client ID.
- If you are developing locally with your own Discord application, set `CLIENT_ID` in `config.py` instead.

### Spotify (optional)

- Spotify support improves playback detection and enables direct Listen Along playback.
- Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
- Set the redirect URI to `http://127.0.0.1:8888/callback` unless you intentionally use a different one. (Spotify no longer accepts `localhost` for new apps — use the loopback IP.)
- Remote playback requires Spotify Premium and an active Spotify device.

### Privacy

Two settings control what leaves your machine — both editable in the setup window, the tray `Settings` menu, or `config.py`:

- `AUTO_ACCEPT_JOIN_REQUESTS` (default `True`) — when someone clicks **Join** on your Rich Presence, the request is accepted automatically. Set to `False` to ignore join requests.
- `COVER_ART_UPLOAD` (default `True`) — your current album art is uploaded to a public image host so Discord can display it. Set to `False` to show the static app icon instead and never upload artwork.

## Setup (from source)

Clone from the [official repository](https://github.com/whoisaldo/Eternal-Rich-Presence):

```bash
git clone https://github.com/whoisaldo/Eternal-Rich-Presence.git
cd Eternal-Rich-Presence
pip install -r requirements.txt
python main.py
```

On first run the app auto-creates `config.py` using the built-in Discord application and drops straight to the tray. The setup window only opens if the embedded Client ID has been removed (local development) or the config is incomplete. If that window can't open, copy `config.example.py` to `config.py` and fill it in manually.

## Developer Shortcuts

When launched with no arguments, `python main.py` opens in its own dedicated Windows console. For troubleshooting from your current terminal, use flags:

```bash
python main.py --setup
python main.py --open-config
python main.py --open-log
python main.py --print-paths
python main.py --clear
python main.py --register-uri
python main.py --unregister-uri
python main.py --version
python main.py --help
```

These are intended for local debugging and support, while the normal release flow stays tray-first and simple for end users.

## Building the portable .exe

The project includes `Apple_Music_Icon.png` in the repo. Build with:

```powershell
.\build.ps1
```

To create GitHub-release-ready artifacts as well:

```powershell
.\build.ps1 -ReleasePackage
```

This installs runtime dependencies plus PyInstaller, compiles a single-file exe with embedded version metadata, bundles the tray icon, and cleans up build artifacts. The output is `EternalRichPresence.exe` in the project root.

With `-ReleasePackage`, the script also creates:

- `release/EternalRichPresence-v<version>-windows.zip`
- `release/EternalRichPresence-v<version>-windows-checksums.txt`
- `release/EternalRichPresence-v<version>-windows-release-body.md`

Upload the `.exe`, `.zip`, and checksums file to the GitHub release. The generated markdown file is ready to paste into the release description.

## System Tray

When running in host mode the app lives in the Windows system tray.

| Menu Item | Action |
|---|---|
| About EternalRichPresence | Shows author, version, and support info |
| Status / Now Playing / Source | Live read-only status labels |
| Copy Listen Along Link | Copies the current join link |
| Repair Listen Along | Re-registers the custom protocol handlers |
| Pause / Resume | Temporarily disable or resume Rich Presence updates |
| Reconnect to Discord | Re-establish the Discord RPC connection |
| Settings > | Start with Windows, album-art upload, and auto-accept join toggles |
| Help | Opens the project page |
| Dev > | Setup, config, app folder, log tools, and advanced troubleshooting |
| Exit | Disconnect and quit |

## Behavior

- **Provider handling:** Spotify is checked first when configured, then Apple Music. Paused playback is no longer shown as live activity.
- **Cover art:** Your current album art is uploaded to a public image host so Discord can display it. The app prefers temporary hosts that expire after ~24 hours (`litterbox.catbox.moe`, then `0x0.st`) and only falls back to the permanent `catbox.moe` if both fail. Set `COVER_ART_UPLOAD = False` to disable uploads entirely.
- **Listen Along:** Join links open Spotify playback when possible, then fall back to an Apple Music search if direct playback is unavailable. Incoming join requests are auto-accepted by default (`AUTO_ACCEPT_JOIN_REQUESTS`).
- **Logging:** Logs are written to `eternalrp.log`. The app prefers the executable folder and falls back to a per-user writable location if needed.
- **Protocol registration:** `eternalrp://` and `discord-{client_id}://` handlers are refreshed automatically for the current Windows user.

## Troubleshooting

- If the app seems to disappear after launch, check the Windows system tray overflow area.
- If Listen Along does not work, use the tray menu and choose `Repair Listen Along`.
- If Discord stops updating after Discord restarts, choose `Reconnect to Discord`.
- If Spotify joins fail, confirm that Spotify is open, signed in, and has an active device. Premium is required for remote playback.
- If you need support logs, open the tray menu and use `Dev > Open Log File`.

## Architecture

```text
main.py              Entry point, setup flow, listener mode, system tray host
app_info.py          App name/version/author constants, embedded Client ID, shared helpers
presence.py          Discord RPC wrapper with reconnect-aware updates
manager.py           Provider selection and playback state normalization
discord_events.py    Raw Win32 named-pipe Discord IPC listener for ACTIVITY_JOIN
setup_gui.py         First-run tkinter config window (writes config.py)
logger.py            Rotating file + console log with writable fallback paths
providers/
  base.py            BaseProvider interface + TrackInfo dataclass
  apple_music.py     iTunes COM + Apple-only SMTC fallback
  spotify.py         Spotify Web API (spotipy + OAuth2)
utils.py             URI registration, join-secret helpers, cover art upload
config.py            User configuration (gitignored)
build.ps1            Portable PyInstaller build script
```

## License & Trademark

EternalRichPresence is free software, licensed under the [GNU General Public License v3.0](LICENSE). You are free to use, study, share, and modify it. Redistributed forks and derivative works must also be licensed under GPL-3.0 and keep their source open — see [LICENSE](LICENSE) for the full terms.

The **EternalRichPresence** and **Eternal Reverse** names and the project logo/branding are **not** covered by the GPL and remain the property of Ali Younes (@whoisaldo). Forks must use a different name and logo and must not imply endorsement — see [TRADEMARK.md](TRADEMARK.md).

Copyright (C) 2026 Ali Younes ([@whoisaldo](https://github.com/whoisaldo))

For support, licensing inquiries, or business contact: **Aliyounes@eternalreverse.com**
