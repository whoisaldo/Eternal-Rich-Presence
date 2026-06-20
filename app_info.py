"""Central application metadata and small shared helpers.

This module imports nothing from the rest of the project, so every other module
(logger, utils, providers, setup_gui, main) can import it without circular-import
risk. Keep it dependency-light.
"""

import os
import sys

APP_NAME = "EternalRichPresence"
APP_VERSION = "2.0.0"
APP_VERSION_FILE = "2.0.0.0"
APP_VERSION_DISPLAY = "2.0"

APP_AUTHOR = "Ali Younes (@whoisaldo)"
APP_REPO_URL = "https://github.com/whoisaldo/Eternal-Rich-Presence"
APP_SUPPORT_EMAIL = "Aliyounes@eternalreverse.com"

DEFAULT_ASSET_KEY = "apple_music"

# Default Spotify OAuth redirect. Single source of truth for the literal that
# used to be repeated across main.py / setup_gui.py / config templates.
DEFAULT_SPOTIFY_REDIRECT_URI = "http://localhost:8888/callback"

# Canonical placeholder Client ID, used wherever code asks "is this config still
# unconfigured?" — defined once so the literal cannot drift across modules.
PLACEHOLDER_CLIENT_ID = "YOUR_DISCORD_CLIENT_ID"

# Official EternalRichPresence Discord app Client ID (Developer Portal > your app > OAuth2).
# A Discord application Client ID is a PUBLIC identifier (it is transmitted in
# everyone's Rich Presence), so it is safe to commit and ship. Do NOT store a
# Discord *client secret* next to it — this app neither has nor needs one.
# Set this before release so users get Discord preconfigured and never have to look it up.
EMBEDDED_CLIENT_ID = "1475237860218241064"

APP_USER_AGENT = f"{APP_NAME}/{APP_VERSION_DISPLAY}"


def app_root() -> str:
    """Absolute path to the application root.

    When frozen by PyInstaller this is the directory containing the executable;
    otherwise it is the directory containing this file (the repo root, since
    app_info.py lives there). Centralizes the frozen-aware path resolution that
    was previously reimplemented — with a subtle divergence — in five modules.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))
