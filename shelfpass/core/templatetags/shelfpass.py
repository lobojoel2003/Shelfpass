"""Template helpers: icons, status pills, rule chips and small formatting filters."""

from __future__ import annotations

import datetime

from django import template
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Simple 24x24 stroke icons drawn for Shelfpass.
_ICONS = {
    "home": '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    "letter": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "inbox": '<path d="M3 13l3-8h12l3 8v6H3z"/><path d="M3 13h5l1 3h6l1-3h5"/>',
    "package": '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4"/><path d="M12 11v10"/>'
    '<path d="M7.5 5l9 4"/>',
    "people": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.8 3.4-6 6.5-6s5.7 2.2 6.5 6"/>'
    '<path d="M16 4.5a3.5 3.5 0 010 7"/><path d="M18.5 14.5c1.6.9 2.6 2.8 3 5.5"/>',
    "book": '<path d="M4 4.5A1.5 1.5 0 015.5 3H20v15H5.5A1.5 1.5 0 004 19.5z"/>'
    '<path d="M4 19.5A1.5 1.5 0 005.5 21H20"/><path d="M8 7h8"/>',
    "shelf": '<path d="M3 21h18"/><path d="M3 12h18"/><rect x="5" y="4" width="3" height="8"/>'
    '<rect x="9" y="5" width="3" height="7"/><path d="M14 5l3-1 2.2 7.8-3 .8z"/>'
    '<rect x="5" y="14" width="4" height="7"/><rect x="10" y="15" width="3" height="6"/>',
    "building": '<path d="M4 21V5l8-3 8 3v16"/><path d="M2 21h20"/><path d="M9 21v-4h6v4"/>'
    '<path d="M8 8h1M12 8h0M15 8h1M8 12h1M15 12h1M12 12h0"/>',
    "alert": '<path d="M12 3l10 18H2z"/><path d="M12 10v5"/><path d="M12 18h0"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "print": '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/>'
    '<path d="M6 14h12v7H6z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/>',
    "check": '<path d="M4 12.5l5 5L20 6.5"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "arrow": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "return": '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 010 10h-3"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9'
    'l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    "logout": '<path d="M15 4h4v16h-4"/><path d="M10 8l-4 4 4 4"/><path d="M6 12h11"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 14v6H4V6h6"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "download": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M4 20h16"/>',
    "upload": '<path d="M12 20V9"/><path d="M7 14l5-5 5 5"/><path d="M4 4h16"/>',
    "truck": '<path d="M2 6h12v10H2z"/><path d="M14 9h4l3 3v4h-7"/><circle cx="6" cy="18" r="2"/>'
    '<circle cx="17" cy="18" r="2"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 7.5h0"/>',
    "ban": '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "repeat": '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 013-3h15"/><path d="M7 22l-4-4 4-4"/>'
    '<path d="M21 13v2a3 3 0 01-3 3H3"/>',
    "sparkle": '<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/>',
}


@register.simple_tag
def icon(name: str, size: int = 18, label: str = "") -> str:
    body = _ICONS.get(name, _ICONS["info"])
    aria = format_html(' role="img" aria-label="{}"', label) if label else ' aria-hidden="true"'
    return mark_safe(  # noqa: S308 - icon bodies are static strings defined above
        f'<svg class="icon" width="{int(size)}" height="{int(size)}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round"{aria}>{body}</svg>'
    )


_STATUS_TONES = {
    "open": "info",
    "packing": "warn",
    "shipped": "brand",
    "delivered": "ok",
    "returned": "block",
    "lost": "block",
    "closed": "muted",
    "packed": "ok",
    "unavailable": "muted",
}


@register.simple_tag
def status_pill(status: str, label: str = "") -> str:
    tone = _STATUS_TONES.get(status, "muted")
    return format_html('<span class="pill pill-{}">{}</span>', tone, label or status.title())


@register.filter
def level_icon(level: str) -> str:
    return {"block": "ban", "warn": "alert", "info": "info"}.get(level, "info")


@register.filter
def days_ago(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime.datetime):
        value = timezone.localtime(value).date()
    days = (timezone.localdate() - value).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 60:
        return f"{days} days ago"
    return f"{days // 30} months ago"


@register.filter
def age_days(value) -> int:
    if not value:
        return 0
    return max(0, (timezone.localdate() - value).days)


@register.filter
def lines(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


@register.filter
def initials(value: str) -> str:
    parts = [p for p in (value or "").replace(",", " ").split() if p[:1].isalpha()]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


@register.filter
def first_name(value: str) -> str:
    """First word of a full name ("Marcus Reyes" -> "Marcus")."""
    parts = (value or "").split()
    return parts[0] if parts else ""


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def pluralize_count(count: int, word: str) -> str:
    singular, _, plural = word.partition(",")
    plural = plural or f"{singular}s"
    return f"{count} {singular if count == 1 else plural}"
