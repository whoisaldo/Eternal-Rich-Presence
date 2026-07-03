# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

# Discord application client ID (Developer Portal > your app > OAuth2).
# Official EternalRichPresence releases already bake in the official app ID.
# Only change this when developing locally or using your own Discord application.
CLIENT_ID = "YOUR_DISCORD_CLIENT_ID"

# Rich Presence large image: must match an Art Asset key in Dev Portal > Rich Presence > Art Assets.
# The setup window defaults to "apple_music", but you can change it there or here.
ASSET_KEY = "apple_music"

# Spotify Web API credentials (Developer Dashboard > your app).
# Leave empty to disable Spotify integration.
# Listen Along playback control requires Spotify Premium and an active Spotify device.
SPOTIFY_CLIENT_ID = ""
SPOTIFY_CLIENT_SECRET = ""
# Note: Spotify no longer accepts "localhost" for new apps — use an explicit
# loopback IP (127.0.0.1) here and in your Spotify app's settings.
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"

# Privacy: auto-accept Discord "Listen Along" join requests from anyone who
# clicks Join on your Rich Presence. Set to False to ignore them.
AUTO_ACCEPT_JOIN_REQUESTS = True

# Privacy: upload the current album art to a public image host (litterbox/0x0,
# then catbox) so Discord can display it. Set to False to show the static app
# icon instead and never upload artwork.
COVER_ART_UPLOAD = True
