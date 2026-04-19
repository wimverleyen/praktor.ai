"""
praktor.ai — UI color token system.

All color values used in clinical_app.py should reference this module
so the palette can be updated in one place.
"""

COLORS: dict[str, str] = {
    # Clinical status / scores
    "status_ok":   "#22c55e",  # green-500
    "status_warn": "#f59e0b",  # amber-500
    "status_err":  "#ef4444",  # red-500
    "status_muted":"#94a3b8",  # slate-400

    # ReAct trajectory span types
    "span_llm":    "#7c3aed",  # violet-700
    "span_tool":   "#0284c7",  # sky-600
    "span_cached": "#16a34a",  # green-600
    "span_error":  "#dc2626",  # red-600

    # Stars weight tiers
    "stars_3x": "#22c55e",
    "stars_2x": "#f59e0b",
    "stars_1x": "#94a3b8",

    # Member card urgency accents
    "urgency_high": "#ef4444",   # stars_exposure >= 5
    "urgency_med":  "#f59e0b",   # stars_exposure >= 3
    "urgency_low":  "#22c55e",   # stars_exposure < 3

    # AI training / calibration surfaces (promote panel, calibration badge)
    "promote_text":   "#5b21b6",  # violet-800
    "promote_accent": "#7c3aed",  # violet-700
    "promote_bg":     "#f5f3ff",  # violet-50
    "promote_border": "#ddd6fe",  # violet-200
    "promote_hover":  "#ede9fe",  # violet-100

    # Warning state (for _safe_load banners, AIGov amber — darker than status_warn)
    "warn_text":   "#92400e",  # amber-800
    "warn_bg":     "#fffbeb",  # amber-50
    "warn_border": "#fde68a",  # amber-200
}


def urgency_color(stars_exposure: float) -> str:
    if stars_exposure >= 5:
        return COLORS["urgency_high"]
    if stars_exposure >= 3:
        return COLORS["urgency_med"]
    return COLORS["urgency_low"]


def urgency_label(stars_exposure: float) -> str:
    if stars_exposure >= 5:
        return "HIGH"
    if stars_exposure >= 3:
        return "MEDIUM"
    return "LOW"
