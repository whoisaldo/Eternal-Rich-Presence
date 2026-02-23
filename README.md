# EternalRichPresence

Discord Rich Presence bridge for Apple Music and Spotify. Displays your current track with live cover art and a Listen Along invite, all from a lightweight system tray app.

**Requirements:** Windows 10+, Python 3.8+ (for building), or the prebuilt `.exe`.

## Quick Start (prebuilt)

1. Place `EternalRichPresence.exe` and `Apple_Music_Icon.png` in the same folder.
2. Create a `config.py` next to the exe (copy from `config.example.py`) and set your Discord `CLIENT_ID`.
3. Start playing a song in Apple Music or Spotify, then launch the exe. It runs silently in the system tray.

## Setup (from source)

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

This installs dependencies, compiles a single-file exe via PyInstaller, and cleans up build artifacts. The output is `EternalRichPresence.exe` in the project root.

## System Tray

When running in host mode the app minimizes to the Windows system tray with these options:

| Menu Item                      | Action                                 |
|-------------------------------|----------------------------------------|
| EternalRichPresence Active    | Status indicator (read-only)           |
| Clear Presence                | Remove the current Discord activity    |
| Exit                          | Disconnect from Discord and quit       |

## Architecture

```
main.py              Entry point, CLI, system tray host
presence.py          Discord RPC wrapper with dynamic cover art (catbox.moe)
manager.py           Tries providers in priority order
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
