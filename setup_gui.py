"""
EternalRichPresence — First-run settings GUI.

Launches a modern tkinter window so non-technical users can configure
their Discord Client ID and optional Spotify credentials without
touching a text editor.
"""

import os
import sys
import tkinter as tk
from tkinter import font as tkfont
import webbrowser

from logger import get_logger

log = get_logger("erp.setup_gui")

_REPO_URL = "https://github.com/whoisaldo/Eternal-Rich-Presence"

_BG = "#1a1a2e"
_BG_FIELD = "#16213e"
_FG = "#e0e0e0"
_FG_DIM = "#8a8a9a"
_ACCENT = "#e94560"
_BTN_BG = "#e94560"
_BTN_FG = "#ffffff"
_BTN_HOVER = "#c73650"
_ENTRY_BORDER = "#0f3460"


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _write_config(client_id: str, asset_key: str,
                  sp_id: str, sp_secret: str, sp_redirect: str) -> str:
    """Write config.py and return the file path."""
    cfg_path = os.path.join(_app_dir(), "config.py")
    lines = [
        f'CLIENT_ID = "{client_id.strip()}"',
        f'ASSET_KEY = "{asset_key.strip() or "apple_music"}"',
        "",
        f'SPOTIFY_CLIENT_ID = "{sp_id.strip()}"',
        f'SPOTIFY_CLIENT_SECRET = "{sp_secret.strip()}"',
        f'SPOTIFY_REDIRECT_URI = "{sp_redirect.strip() or "http://localhost:8888/callback"}"',
        "",
    ]
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log.info("config.py saved at %s", cfg_path)
    return cfg_path


def _load_existing() -> dict:
    """Try to read current config.py values, return defaults for missing keys."""
    defaults = {
        "CLIENT_ID": "",
        "ASSET_KEY": "apple_music",
        "SPOTIFY_CLIENT_ID": "",
        "SPOTIFY_CLIENT_SECRET": "",
        "SPOTIFY_REDIRECT_URI": "http://localhost:8888/callback",
    }
    cfg_path = os.path.join(_app_dir(), "config.py")
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
        if val and val != "YOUR_DISCORD_CLIENT_ID":
            defaults[key] = str(val)
    return defaults


def run_setup_gui() -> bool:
    """Show the settings window. Returns True if the user saved valid config."""
    saved = [False]

    root = tk.Tk()
    root.title("EternalRichPresence — Setup")
    root.configure(bg=_BG)
    root.resizable(False, False)

    win_w, win_h = 520, 560
    sx = root.winfo_screenwidth() // 2 - win_w // 2
    sy = root.winfo_screenheight() // 2 - win_h // 2
    root.geometry(f"{win_w}x{win_h}+{sx}+{sy}")

    try:
        icon_path = os.path.join(_app_dir(), "Apple_Music_Icon.png")
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
        header, text="EternalRichPresence", font=title_font,
        fg=_ACCENT, bg=_BG, anchor="w",
    ).pack(anchor="w")
    tk.Label(
        header, text="by Ali Younes (@whoisaldo)", font=subtitle_font,
        fg=_FG_DIM, bg=_BG, anchor="w",
    ).pack(anchor="w")

    sep = tk.Frame(root, bg=_ACCENT, height=2)
    sep.pack(fill="x", padx=30, pady=(12, 16))

    existing = _load_existing()

    fields: dict[str, tk.Entry] = {}

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

    _add_field(root, "Discord Client ID *", "CLIENT_ID")

    sp_label = tk.Label(
        root, text="Spotify (optional — leave blank to disable)",
        font=label_font, fg=_FG_DIM, bg=_BG, anchor="w",
    )
    sp_label.pack(fill="x", padx=30, pady=(6, 4))

    _add_field(root, "Spotify Client ID", "SPOTIFY_CLIENT_ID")
    _add_field(root, "Spotify Client Secret", "SPOTIFY_CLIENT_SECRET", show="\u2022")
    _add_field(root, "Spotify Redirect URI", "SPOTIFY_REDIRECT_URI")

    status_var = tk.StringVar(value="")
    status_label = tk.Label(
        root, textvariable=status_var, font=small_font,
        fg=_ACCENT, bg=_BG, anchor="w",
    )
    status_label.pack(fill="x", padx=30, pady=(0, 4))

    def _on_save():
        cid = fields["CLIENT_ID"].get().strip()
        if not cid or cid == "YOUR_DISCORD_CLIENT_ID":
            status_var.set("Discord Client ID is required.")
            return
        try:
            _write_config(
                client_id=cid,
                asset_key="apple_music",
                sp_id=fields["SPOTIFY_CLIENT_ID"].get(),
                sp_secret=fields["SPOTIFY_CLIENT_SECRET"].get(),
                sp_redirect=fields["SPOTIFY_REDIRECT_URI"].get(),
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
        webbrowser.open(_REPO_URL)

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
    footer.bind("<Button-1>", lambda _e: webbrowser.open(_REPO_URL))

    root.mainloop()
    return saved[0]
