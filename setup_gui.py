# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

"""
EternalRichPresence — First-run settings GUI.

Launches a modern tkinter window so non-technical users can configure
their Discord Client ID and optional Spotify credentials without
touching a text editor.
"""

import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from typing import Optional

from app_info import (
    APP_AUTHOR,
    APP_NAME,
    APP_REPO_URL,
    DEFAULT_ASSET_KEY,
    EMBEDDED_CLIENT_ID,
    PLACEHOLDER_CLIENT_ID,
    config_path,
)
from logger import get_logger
from utils import read_config_values, render_config, resource_path, write_config_file

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


def _write_config(
    client_id: str,
    asset_key: str,
    sp_id: str,
    sp_secret: str,
    sp_redirect: str,
    auto_accept: Optional[bool] = None,
    cover_upload: Optional[bool] = None,
    cfg_path: Optional[str] = None,
) -> str:
    """Write config.py and return the file path.

    Rendering goes through utils.render_config — repr-escaped values and the
    full canonical key set. The privacy toggles come from the GUI checkboxes;
    when None they are preserved from the existing file (rewriting used to
    silently reset them). The write is atomic, so a failure mid-save can't
    leave a truncated config.py.
    """
    cfg_path = cfg_path or config_path()
    existing = read_config_values(cfg_path)
    if auto_accept is None:
        auto_accept = existing["AUTO_ACCEPT_JOIN_REQUESTS"]
    if cover_upload is None:
        cover_upload = existing["COVER_ART_UPLOAD"]
    content = render_config(
        client_id=client_id,
        asset_key=asset_key,
        spotify_client_id=sp_id,
        spotify_client_secret=sp_secret,
        spotify_redirect_uri=sp_redirect,
        auto_accept_join_requests=auto_accept,
        cover_art_upload=cover_upload,
    )
    write_config_file(content, cfg_path)
    log.info("config.py saved at %s", cfg_path)
    return cfg_path


def _load_existing() -> dict:
    """Current config values for prefilling the form (defaults when absent)."""
    values = read_config_values()
    out = {
        key: str(values[key])
        for key in (
            "CLIENT_ID",
            "ASSET_KEY",
            "SPOTIFY_CLIENT_ID",
            "SPOTIFY_CLIENT_SECRET",
            "SPOTIFY_REDIRECT_URI",
        )
    }
    if not out["CLIENT_ID"] or out["CLIENT_ID"] == PLACEHOLDER_CLIENT_ID:
        out["CLIENT_ID"] = EMBEDDED_CLIENT_ID or ""
    if not out["ASSET_KEY"]:
        out["ASSET_KEY"] = DEFAULT_ASSET_KEY
    return out


def run_setup_gui() -> bool:
    """Show the settings window. Returns True if the user saved valid config."""
    saved = [False]

    root = tk.Tk()
    root.title(f"{APP_NAME} — Setup")
    root.configure(bg=_BG)
    root.resizable(False, True)

    # Fit short/DPI-scaled displays: the form scrolls and the Save bar stays
    # pinned at the bottom, so nothing is ever clipped off-screen.
    win_w = 620
    win_h = min(760, root.winfo_screenheight() - 80)
    sx = root.winfo_screenwidth() // 2 - win_w // 2
    sy = max(0, root.winfo_screenheight() // 2 - win_h // 2)
    root.geometry(f"{win_w}x{win_h}+{sx}+{sy}")

    try:
        # resource_path also finds the icon inside a frozen build's _MEIPASS,
        # where the release exe actually ships it.
        icon_path = resource_path("Apple_Music_Icon.png")
        if icon_path:
            _photo = tk.PhotoImage(file=icon_path)
            root.iconphoto(True, _photo)
    except Exception:
        pass

    # Fixed bottom bar (status + buttons + footer) packed first so it always
    # keeps its space; everything above lives in a scrollable canvas.
    bottom = tk.Frame(root, bg=_BG)
    bottom.pack(side="bottom", fill="x")

    scroll_area = tk.Frame(root, bg=_BG)
    scroll_area.pack(side="top", fill="both", expand=True)
    canvas = tk.Canvas(scroll_area, bg=_BG, highlightthickness=0, bd=0)
    scrollbar = tk.Scrollbar(scroll_area, orient="vertical", command=canvas.yview)
    content = tk.Frame(canvas, bg=_BG)
    content_id = canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(content_id, width=e.width))
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _on_mousewheel(event):
        step = int(-event.delta / 120) or (-1 if event.delta > 0 else 1)
        canvas.yview_scroll(step, "units")

    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    title_font = tkfont.Font(family="Segoe UI", size=18, weight="bold")
    subtitle_font = tkfont.Font(family="Segoe UI", size=9)
    label_font = tkfont.Font(family="Segoe UI", size=10)
    entry_font = tkfont.Font(family="Consolas", size=10)
    btn_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
    small_font = tkfont.Font(family="Segoe UI", size=8)

    header = tk.Frame(content, bg=_BG)
    header.pack(fill="x", padx=30, pady=(24, 4))

    tk.Label(
        header,
        text=APP_NAME,
        font=title_font,
        fg=_ACCENT,
        bg=_BG,
        anchor="w",
    ).pack(anchor="w")
    tk.Label(
        header,
        text=f"by {APP_AUTHOR}",
        font=subtitle_font,
        fg=_FG_DIM,
        bg=_BG,
        anchor="w",
    ).pack(anchor="w")

    sep = tk.Frame(content, bg=_ACCENT, height=2)
    sep.pack(fill="x", padx=30, pady=(12, 16))

    existing = _load_existing()

    fields: dict[str, tk.Entry] = {}
    secret_shown = tk.BooleanVar(value=False)

    def _add_field(parent, label_text: str, key: str, show: str = ""):
        frame = tk.Frame(parent, bg=_BG)
        frame.pack(fill="x", padx=30, pady=(0, 10))
        tk.Label(
            frame,
            text=label_text,
            font=label_font,
            fg=_FG,
            bg=_BG,
            anchor="w",
        ).pack(anchor="w")
        entry = tk.Entry(
            frame,
            font=entry_font,
            bg=_BG_FIELD,
            fg=_FG,
            insertbackground=_FG,
            relief="flat",
            highlightthickness=1,
            highlightcolor=_ACCENT,
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
        content,
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
        content, bg=_BG_FIELD, highlightthickness=1, highlightbackground=_ENTRY_BORDER
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
        content, bg=_BG_FIELD, highlightthickness=1, highlightbackground=_ENTRY_BORDER
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

    privacy_values = read_config_values()
    auto_accept_var = tk.BooleanVar(value=privacy_values["AUTO_ACCEPT_JOIN_REQUESTS"])
    cover_upload_var = tk.BooleanVar(value=privacy_values["COVER_ART_UPLOAD"])

    privacy_card = tk.Frame(
        content, bg=_BG_FIELD, highlightthickness=1, highlightbackground=_ENTRY_BORDER
    )
    privacy_card.pack(fill="x", padx=30, pady=(0, 12))

    tk.Label(
        privacy_card,
        text="Privacy",
        font=label_font,
        fg=_ACCENT,
        bg=_BG_FIELD,
        anchor="w",
    ).pack(fill="x", padx=16, pady=(14, 2))
    tk.Label(
        privacy_card,
        text=(
            "These control what leaves your machine. Album art is uploaded to a "
            "public image host so Discord can display it; join requests come from "
            "anyone who clicks Join on your presence."
        ),
        font=small_font,
        fg=_FG_DIM,
        bg=_BG_FIELD,
        justify="left",
        wraplength=530,
        anchor="w",
    ).pack(fill="x", padx=16, pady=(0, 8))

    def _privacy_check(text: str, variable: tk.BooleanVar) -> None:
        tk.Checkbutton(
            privacy_card,
            text=text,
            variable=variable,
            bg=_BG_FIELD,
            fg=_FG,
            activebackground=_BG_FIELD,
            activeforeground=_FG,
            selectcolor=_BG_FIELD,
            highlightthickness=0,
            font=small_font,
        ).pack(anchor="w", padx=16, pady=(0, 4))

    _privacy_check("Upload album art to a public host (live cover art)", cover_upload_var)
    _privacy_check('Auto-accept Discord "Listen Along" join requests', auto_accept_var)
    tk.Frame(privacy_card, bg=_BG_FIELD, height=8).pack()

    tray_hint = tk.Label(
        content,
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
        bottom,
        textvariable=status_var,
        font=small_font,
        fg=_ACCENT,
        bg=_BG,
        anchor="w",
    )
    status_label.pack(fill="x", padx=30, pady=(0, 4))

    def _on_save():
        cid = fields["CLIENT_ID"].get().strip() or EMBEDDED_CLIENT_ID
        if not cid or cid == PLACEHOLDER_CLIENT_ID:
            status_var.set("Discord Client ID is required.")
            return
        if not cid.isdigit():
            status_var.set(
                "Discord Client ID must be a number — copy it from the Developer Portal."
            )
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
        # Blank is fine — the writer substitutes the default redirect URI.
        if sp_redirect and not sp_redirect.startswith(("http://", "https://")):
            status_var.set("Spotify Redirect URI must start with http:// or https://")
            return
        try:
            _write_config(
                client_id=cid,
                asset_key=asset_key,
                sp_id=sp_id,
                sp_secret=sp_secret,
                sp_redirect=sp_redirect,
                auto_accept=auto_accept_var.get(),
                cover_upload=cover_upload_var.get(),
            )
            saved[0] = True
            root.destroy()
        except Exception as e:
            status_var.set(f"Save failed: {e}")
            log.error("Setup GUI save failed: %s", e)

    btn_frame = tk.Frame(bottom, bg=_BG)
    btn_frame.pack(fill="x", padx=30, pady=(8, 0))

    save_btn = tk.Button(
        btn_frame,
        text="Save & Launch",
        font=btn_font,
        bg=_BTN_BG,
        fg=_BTN_FG,
        activebackground=_BTN_HOVER,
        activeforeground=_BTN_FG,
        relief="flat",
        cursor="hand2",
        command=_on_save,
        padx=16,
        pady=6,
    )
    save_btn.pack(side="left")

    def _on_help():
        webbrowser.open(APP_REPO_URL)

    help_btn = tk.Button(
        btn_frame,
        text="Help / Setup Guide",
        font=label_font,
        bg=_BG_FIELD,
        fg=_FG_DIM,
        activebackground=_ENTRY_BORDER,
        activeforeground=_FG,
        relief="flat",
        cursor="hand2",
        command=_on_help,
        padx=12,
        pady=6,
    )
    help_btn.pack(side="right")

    footer = tk.Label(
        bottom,
        text="github.com/whoisaldo/Eternal-Rich-Presence",
        font=small_font,
        fg=_FG_DIM,
        bg=_BG,
        cursor="hand2",
    )
    footer.pack(side="bottom", pady=(0, 12))
    footer.bind("<Button-1>", lambda _e: webbrowser.open(APP_REPO_URL))

    root.mainloop()
    return saved[0]
