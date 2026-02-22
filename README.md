# EternalRichPresence

Discord Rich Presence for Apple Music (and other players via Windows System Media Transport Controls). Host mode updates your status with the current track and a join link; listener mode handles `eternalrp://` URIs.

**Requirements:** Windows, Python 3.8+

1. Copy `config.example.py` to `config.py` and set your Discord application `CLIENT_ID` (Developer Portal → your app → OAuth2). Add an Art Asset with key `apple_music` (or set `ASSET_KEY` in config).
2. `pip install -r requirements.txt`
3. Run: `python main.py` (host). Optional: `python main.py --register-uri` to register the URI scheme (admin); `python main.py --clear` to clear stuck presence.
