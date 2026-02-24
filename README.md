# EternalRichPresence

**The official Discord Rich Presence bridge for Apple Music and Spotify, by Ali Younes ([@whoisaldo](https://github.com/whoisaldo)).**

Displays your current track with live cover art and a Listen Along invite, all from a lightweight system tray app.

**Requirements:** Windows 10+, Python 3.8+ (for building), or the prebuilt `.exe`.

## Quick Start (prebuilt)

Download the latest `EternalRichPresence.exe` from the [official repository](https://github.com/whoisaldo/Eternal-Rich-Presence) to ensure you have the latest authorized version.

1. Place `EternalRichPresence.exe` and `Apple_Music_Icon.png` in the same folder.
2. Launch the exe — on first run it creates a `config.py` for you. Open it in Notepad and paste your Discord `CLIENT_ID`.
3. Start playing a song in Apple Music or Spotify, then launch again. It runs silently in the system tray.

## Setup (from source)

Clone from the [official repository](https://github.com/whoisaldo/Eternal-Rich-Presence):

```bash
git clone https://github.com/whoisaldo/Eternal-Rich-Presence.git
```

1. Copy `config.example.py` to `config.py` and set `CLIENT_ID` (Developer Portal > your app > OAuth2).
2. Add an Art Asset with key `apple_music` under Rich Presence > Art Assets (or change `ASSET_KEY`).
3. *(Optional)* For Spotify, set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` from the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
4. Install dependencies:

```
pip install -r requirements.txt
```

5. Run:

```bash
python main.py
```

## Building the portable .exe

Place an `Apple_Music_Icon.png` in the project root, then run:

```powershell
.\build.ps1
```

This installs dependencies, compiles a single-file exe via PyInstaller with embedded version metadata, and cleans up build artifacts. The output is `EternalRichPresence.exe` in the project root.

## System Tray

When running in host mode the app sits in the Windows system tray:

| Menu Item | Action |
|---|---|
| About EternalRichPresence | Shows author and version info |
| *Now Playing* | Current track and artist (read-only) |
| *Source* | Active provider (read-only) |
| Pause / Resume | Toggle presence on/off |
| Reconnect to Discord | Re-establish the RPC connection |
| Debug > | Discord status, open/copy log file |
| Exit | Disconnect and quit |

## Architecture

```
main.py              Entry point, CLI, system tray host
presence.py          Discord RPC wrapper with dynamic cover art (catbox.moe)
manager.py           Tries providers in priority order
logger.py            Rotating file + console log (eternalrp.log)
providers/
  base.py            BaseProvider interface + TrackInfo dataclass
  apple_music.py     iTunes COM + Windows SMTC
  spotify.py         Spotify Web API (spotipy + OAuth2)
utils.py             URI scheme registration, cover art upload
config.py            User configuration (gitignored)
build.ps1            One-click PyInstaller build script
```

- **Provider priority:** Apple Music is checked first; Spotify is the fallback.
- **Cover art:** Extracted from SMTC / Spotify and uploaded to catbox.moe so Discord shows the actual album artwork.
- **Listen Along:** Clicking Join on someone's profile launches `eternalrp://` which tries Spotify playback first, then falls back to an Apple Music web search.
- **Auto-register:** The `eternalrp://` URI scheme is silently registered on every launch so deep links always point at the current executable.
- **Logging:** All events are written to `eternalrp.log` (rotates at 2 MB, 3 backups). Open via the Debug tray menu.

## License

EternalRichPresence is **source-available** under a custom license. You may use it freely for personal, non-commercial purposes. Redistribution of the source code or compiled binary, and creation of derivative works or competing versions for public distribution, are strictly prohibited. See [LICENSE](LICENSE) for full terms.

Copyright (c) 2026 Ali Younes ([@whoisaldo](https://github.com/whoisaldo))

For support, licensing inquiries, or business contact: **Aliyounes@eternalreverse.com**
