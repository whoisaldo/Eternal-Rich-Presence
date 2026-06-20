"""
EternalRichPresence — First-run settings GUI.

Launches a modern tkinter window so non-technical users can configure
their Discord Client ID and optional Spotify credentials without
touching a text editor.
"""

import os
import tkinter as tk
import webbrowser
from tkinter import font as tkfont

from app_info import (
    APP_AUTHOR,
    APP_NAME,
    APP_REPO_URL,
    DEFAULT_ASSET_KEY,
    DEFAULT_SPOTIFY_REDIRECT_URI,
    EMBEDDED_CLIENT_ID,
    PLACEHOLDER_CLIENT_ID,
    app_root,
)
from logger import get_logger

log = get_logger("erp.setup_gui")

_BG = "#1a1a2e"
_BG_FIELD = "#16213e"
_FG = "#e0e0e0"
_FG_DIM = "#8a8a9a"
_ACCENT = "#e94560"
_BTN_BG = "#e94560"
_BTN_FG = "#ffffff"
_BTN_HOVER = "#c73650"
_ENTRY_BORDER = "#0f3460"


def _write_config(client_id: str, asset_key: str,
                  sp_id: str, sp_secret: str, sp_redirect: str) -> str:
    """Write config.py and return the file path.

    Values are written with ``!r`` so a quote/backslash/newline in any field
    becomes a safe Python string literal instead of corrupting config.py.
    """
    cfg_path = os.path.join(app_root(), "config.py")
    lines = [
        f"CLIENT_ID = {client_id.strip()!r}",
        f"ASSET_KEY = {(asset_key.strip() or DEFAULT_ASSET_KEY)!r}",
        "",
        f"SPOTIFY_CLIENT_ID = {sp_id.strip()!r}",
        f"SPOTIFY_CLIENT_SECRET = {sp_secret.strip()!r}",
        f"SPOTIFY_REDIRECT_URI = {(sp_redirect.strip() or DEFAULT_SPOTIFY_REDIRECT_URI)!r}",
        "",
    ]
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log.info("config.py saved at %s", cfg_path)
    return cfg_path


def _load_existing() -> dict:
    """Try to read current config.py values, return defaults for missing keys."""
    defaults = {
        "CLIENT_ID": EMBEDDED_CLIENT_ID or "",
        "ASSET_KEY": DEFAULT_ASSET_KEY,
        "SPOTIFY_CLIENT_ID": "",
        "SPOTIFY_CLIENT_SECRET": "",
        "SPOTIFY_REDIRECT_URI": DEFAULT_SPOTIFY_REDIRECT_URI,
    }
    cfg_path = os.path.join(app_root(), "config.py")
    if not os.path.isfile(cfg_path):
        return defaults
    ns: dict = {}
    try:
        with open(cfg_path, encoding="utf-8") as f:
            exec(compile(f.read(), cfg_path, "exec"), ns)
    except Exception:
        return defaults
    for key in defaults:
        val = ns.get(key, "")
        if val and val != PLACEHOLDER_CLIENT_ID:
            defaults[key] = str(val)
    if not (defaults["CLIENT_ID"] and defaults["CLIENT_ID"] != PLACEHOLDER_CLIENT_ID):
        defaults["CLIENT_ID"] = EMBEDDED_CLIENT_ID or ""
    return defaults


def run_setup_gui() -> bool:
    """Show the settings window. Returns True if the user saved valid config."""
    saved = [False]

    root = tk.Tk()
    root.title(f"{APP_NAME} — Setup")
    root.configure(bg=_BG)
    root.resizable(False, False)

    win_w, win_h = 620, 760
    sx = root.winfo_screenwidth() // 2 - win_w // 2
    sy = root.winfo_screenheight() // 2 - win_h // 2
    root.geometry(f"{win_w}x{win_h}+{sx}+{sy}")

    try:
        icon_path = os.path.join(app_root(), "Apple_Music_Icon.png")
        if os.path.isfile(icon_path):
            _photo = tk.PhotoImage(file=icon_path)
            root.iconphoto(True, _photo)
    except Exception:
        pass

    title_font = tkfont.Font(family="Segoe UI", size=18, weight="bold")
    subtitle_font = tkfont.Font(family="Segoe UI", size=9)
    label_font = tkfont.Font(family="Segoe UI", size=10)
    entry_font = tkfont.Font(family="Consolas", size=10)
    btn_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
    small_font = tkfont.Font(family="Segoe UI", size=8)

    header = tk.Frame(root, bg=_BG)
    header.pack(fill="x", padx=30, pady=(24, 4))

    tk.Label(
        header, text=APP_NAME, font=title_font,
        fg=_ACCENT, bg=_BG, anchor="w",
    ).pack(anchor="w")
    tk.Label(
        header, text=f"by {APP_AUTHOR}", font=subtitle_font,
        fg=_FG_DIM, bg=_BG, anchor="w",
    ).pack(anchor="w")

    sep = tk.Frame(root, bg=_ACCENT, height=2)
    sep.pack(fill="x", padx=30, pady=(12, 16))

    existing = _load_existing()

    fields: dict[str, tk.Entry] = {}
    secret_shown = tk.BooleanVar(value=False)

    def _add_field(parent, label_text: str, key: str, show: str = ""):
        frame = tk.Frame(parent, bg=_BG)
        frame.pack(fill="x", padx=30, pady=(0, 10))
        tk.Label(
            frame, text=label_text, font=label_font,
            fg=_FG, bg=_BG, anchor="w",
        ).pack(anchor="w")
        entry = tk.Entry(
            frame, font=entry_font, bg=_BG_FIELD, fg=_FG,
            insertbackground=_FG, relief="flat",
            highlightthickness=1, highlightcolor=_ACCENT,
            highlightbackground=_ENTRY_BORDER,
            show=show,
        )
        entry.pack(fill="x", ipady=6, pady=(2, 0))
        entry.insert(0, existing.get(key, ""))
        fields[key] = entry

    intro_text = (
        "Discord is already configured for EternalRichPresence. "
        "Optionally add Spotify below for Listen Along."
        if EMBEDDED_CLIENT_ID
        else (
            "Set up your Discord app once, then EternalRichPresence will live in "
            "your system tray and update automatically while you listen."
        )
    )
    intro = tk.Label(
        root,
        text=intro_text,
        font=label_font,
        fg=_FG,
        bg=_BG,
        justify="left",
        wraplength=560,
        anchor="w",
    )
    intro.pack(fill="x", padx=30, pady=(0, 16))

    discord_card = tk.Frame(
        root, bg=_BG_FIELD, highlightthickness=1, highlightbackground=_ENTRY_BORDER
    )
    discord_card.pack(fill="x", padx=30, pady=(0, 14))

    tk.Label(
        discord_card,
        text="Discord",
        font=label_font,
        fg=_ACCENT,
        bg=_BG_FIELD,
        anchor="w",
    ).pack(fill="x", padx=16, pady=(14, 2))
    discord_desc = (
        "Preconfigured for EternalRichPresence. The art asset key should match "
        "your app, usually `apple_music`."
        if EMBEDDED_CLIENT_ID
        else (
            "Required. Paste your Discord application Client ID. The Rich Presence "
            "art asset key below should match an asset in your Discord app, "
            f"usually `{DEFAULT_ASSET_KEY}`."
        )
    )
    tk.Label(
        discord_card,
        text=discord_desc,
        font=small_font,
        fg=_FG_DIM,
        bg=_BG_FIELD,
        justify="left",
        wraplength=530,
        anchor="w",
    ).pack(fill="x", padx=16, pady=(0, 12))

    _add_field(
        discord_card,
        "Discord Client ID (advanced override)" if EMBEDDED_CLIENT_ID else "Discord Client ID *",
        "CLIENT_ID",
    )
    _add_field(discord_card, "Discord Art Asset Key", "ASSET_KEY")

    discord_btns = tk.Frame(discord_card, bg=_BG_FIELD)
    discord_btns.pack(fill="x", padx=16, pady=(0, 14))

    tk.Button(
        discord_btns,
        text="Open Discord Developer Portal",
        font=small_font,
        bg=_BG,
        fg=_FG,
        activebackground=_ENTRY_BORDER,
        activeforeground=_FG,
        relief="flat",
        cursor="hand2",
        command=lambda: webbrowser.open("https://discord.com/developers/applications"),
        padx=10,
        pady=5,
    ).pack(side="left")

    spotify_card = tk.Frame(
        root, bg=_BG_FIELD, highlightthickness=1, highlightbackground=_ENTRY_BORDER
    )
    spotify_card.pack(fill="x", padx=30, pady=(0, 12))

    tk.Label(
        spotify_card,
        text="Spotify (optional)",
        font=label_font,
        fg=_ACCENT,
        bg=_BG_FIELD,
        anchor="w",
    ).pack(fill="x", padx=16, pady=(14, 2))
    tk.Label(
        spotify_card,
        text=(
            "Add Spotify if you want richer detection and Listen Along playback controls. "
            "Remote playback requires a Premium account and an active Spotify device."
        ),
        font=small_font,
        fg=_FG_DIM,
        bg=_BG_FIELD,
        justify="left",
        wraplength=530,
        anchor="w",
    ).pack(fill="x", padx=16, pady=(0, 12))

    _add_field(spotify_card, "Spotify Client ID", "SPOTIFY_CLIENT_ID")
    _add_field(spotify_card, "Spotify Client Secret", "SPOTIFY_CLIENT_SECRET", show="\u2022")
    _add_field(spotify_card, "Spotify Redirect URI", "SPOTIFY_REDIRECT_URI")

    tk.Checkbutton(
        spotify_card,
        text="Show Spotify Client Secret",
        variable=secret_shown,
        command=lambda: fields["SPOTIFY_CLIENT_SECRET"].configure(
            show="" if secret_shown.get() else "\u2022"
        ),
        bg=_BG_FIELD,
        fg=_FG_DIM,
        activebackground=_BG_FIELD,
        activeforeground=_FG,
        selectcolor=_BG_FIELD,
        highlightthickness=0,
        font=small_font,
    ).pack(anchor="w", padx=16, pady=(0, 8))

    spotify_btns = tk.Frame(spotify_card, bg=_BG_FIELD)
    spotify_btns.pack(fill="x", padx=16, pady=(0, 14))

    tk.Button(
        spotify_btns,
        text="Open Spotify Dashboard",
        font=small_font,
        bg=_BG,
        fg=_FG,
        activebackground=_ENTRY_BORDER,
        activeforeground=_FG,
        relief="flat",
        cursor="hand2",
        command=lambda: webbrowser.open("https://developer.spotify.com/dashboard"),
        padx=10,
        pady=5,
    ).pack(side="left")

    tk.Button(
        spotify_btns,
        text="Open Setup Guide",
        font=small_font,
        bg=_BG,
        fg=_FG,
        activebackground=_ENTRY_BORDER,
        activeforeground=_FG,
        relief="flat",
        cursor="hand2",
        command=lambda: webbrowser.open(f"{APP_REPO_URL}#quick-start-prebuilt"),
        padx=10,
        pady=5,
    ).pack(side="left", padx=(10, 0))

    tray_hint = tk.Label(
        root,
        text=(
            "After saving, the app will launch in your system tray. Right-click "
            "the tray icon for controls and troubleshooting."
        ),
        font=small_font,
        fg=_FG_DIM,
        bg=_BG,
        wraplength=560,
        justify="left",
        anchor="w",
    )
    tray_hint.pack(fill="x", padx=30, pady=(0, 8))

    status_var = tk.StringVar(value="")
    status_label = tk.Label(
        root, textvariable=status_var, font=small_font,
        fg=_ACCENT, bg=_BG, anchor="w",
    )
    status_label.pack(fill="x", padx=30, pady=(0, 4))

    def _on_save():
        cid = fields["CLIENT_ID"].get().strip() or EMBEDDED_CLIENT_ID
        if not cid or cid == PLACEHOLDER_CLIENT_ID:
            status_var.set("Discord Client ID is required.")
            return
        asset_key = fields["ASSET_KEY"].get().strip()
        if not asset_key:
            status_var.set("Discord Art Asset Key is required.")
            return

        sp_id = fields["SPOTIFY_CLIENT_ID"].get().strip()
        sp_secret = fields["SPOTIFY_CLIENT_SECRET"].get().strip()
        sp_redirect = fields["SPOTIFY_REDIRECT_URI"].get().strip()
        spotify_values = [sp_id, sp_secret]
        if any(spotify_values) and not all(spotify_values):
            status_var.set("Fill in both Spotify Client ID and Client Secret, or leave both blank.")
            return
        if any(spotify_values) and not sp_redirect.startswith(("http://", "https://")):
            status_var.set("Spotify Redirect URI must start with http:// or https://")
            return
        try:
            _write_config(
                client_id=cid,
                asset_key=asset_key,
                sp_id=sp_id,
                sp_secret=sp_secret,
                sp_redirect=sp_redirect,
            )
            saved[0] = True
            root.destroy()
        except Exception as e:
            status_var.set(f"Save failed: {e}")
            log.error("Setup GUI save failed: %s", e)

    btn_frame = tk.Frame(root, bg=_BG)
    btn_frame.pack(fill="x", padx=30, pady=(8, 0))

    save_btn = tk.Button(
        btn_frame, text="Save & Launch", font=btn_font,
        bg=_BTN_BG, fg=_BTN_FG, activebackground=_BTN_HOVER,
        activeforeground=_BTN_FG, relief="flat", cursor="hand2",
        command=_on_save, padx=16, pady=6,
    )
    save_btn.pack(side="left")

    def _on_help():
        webbrowser.open(APP_REPO_URL)

    help_btn = tk.Button(
        btn_frame, text="Help / Setup Guide", font=label_font,
        bg=_BG_FIELD, fg=_FG_DIM, activebackground=_ENTRY_BORDER,
        activeforeground=_FG, relief="flat", cursor="hand2",
        command=_on_help, padx=12, pady=6,
    )
    help_btn.pack(side="right")

    footer = tk.Label(
        root,
        text="github.com/whoisaldo/Eternal-Rich-Presence",
        font=small_font, fg=_FG_DIM, bg=_BG, cursor="hand2",
    )
    footer.pack(side="bottom", pady=(0, 12))
    footer.bind("<Button-1>", lambda _e: webbrowser.open(APP_REPO_URL))

    root.mainloop()
    return saved[0]
