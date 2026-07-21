"""
theme.py

Shared design tokens so every screen looks like it belongs to the same
app instead of each one inventing its own font sizes and colors.
Widget colors (buttons, entries, etc.) come from
assets/theme_professional.json via ctk.set_default_color_theme(); this
module covers the things that theme file *can't* express - font
scale, spacing scale, and semantic status colors for the Pending/
Disposed badges used across Results and My Cases.
"""
from __future__ import annotations

import customtkinter as ctk

# Spacing scale - use these instead of ad hoc padx/pady numbers.
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32

# Corner radius for "card" style frames (search cards, table containers).
CARD_RADIUS = 12

# Semantic colors not covered by the CTk widget theme (light, dark).
COLOR_SUCCESS = ("#1F7A4D", "#3FA873")
COLOR_SUCCESS_BG = ("#E4F5EC", "#173327")
COLOR_WARNING = ("#8A6116", "#D9A441")
COLOR_WARNING_BG = ("#FBF0DA", "#332A14")
COLOR_DANGER = ("#A23B3B", "#D9635F")
COLOR_DANGER_BG = ("#FBE7E7", "#331A1A")
COLOR_MUTED = ("#6B7280", "#8A8F98")
COLOR_ACCENT = ("#2F4B8C", "#3B5BA0")

STATUS_COLORS = {
    "PENDING": (COLOR_WARNING, COLOR_WARNING_BG),
    "DISPOSED": (COLOR_SUCCESS, COLOR_SUCCESS_BG),
}


def font_heading() -> ctk.CTkFont:
    return ctk.CTkFont(size=22, weight="bold")


def font_subheading() -> ctk.CTkFont:
    return ctk.CTkFont(size=15, weight="bold")


def font_body() -> ctk.CTkFont:
    return ctk.CTkFont(size=13)


def font_small() -> ctk.CTkFont:
    return ctk.CTkFont(size=11)


def status_badge(master, status: str) -> ctk.CTkLabel:
    """A small colored pill label for PENDING/DISPOSED/unknown status."""
    status = (status or "").upper()
    text = status.title() if status else "Unknown"
    fg, bg = STATUS_COLORS.get(status, (COLOR_MUTED, ("#ECEEF1", "#242835")))
    return ctk.CTkLabel(
        master, text=text, font=font_small(), text_color=fg, fg_color=bg,
        corner_radius=999, width=72, height=22,
    )
