"""Opening-hours helpers.

SiteSettings.opening_hours holds {"0": {"open": "11:00", "close": "22:00"}, ...}
keyed by weekday (0=Monday), or free text on older deployments.
"""
from datetime import datetime

from django.utils import timezone

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def opening_hours_rows(raw_hours):
    """Normalise the JSON into weekday display rows.

    Returns (rows, text): rows for the structured format, or ([], text)
    when the field holds free text instead.
    """
    if isinstance(raw_hours, dict) and raw_hours:
        rows = []
        for day_index, name in enumerate(DAY_NAMES):
            entry = raw_hours.get(str(day_index))
            if isinstance(entry, dict) and entry.get("open") and entry.get("close"):
                rows.append({"day": name, "open": entry["open"], "close": entry["close"]})
            else:
                rows.append({"day": name, "open": "", "close": ""})
        return rows, ""
    if raw_hours:
        return [], str(raw_hours)
    return [], ""


def _parse_time(value):
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except (TypeError, ValueError):
        return None


def opening_status(raw_hours, now=None):
    """Live open/closed status for today, or None when hours are unknown."""
    if not isinstance(raw_hours, dict) or not raw_hours:
        return None
    now = now or timezone.localtime()
    entry = raw_hours.get(str(now.weekday()))
    open_time = _parse_time(entry.get("open")) if isinstance(entry, dict) else None
    close_time = _parse_time(entry.get("close")) if isinstance(entry, dict) else None
    if not open_time or not close_time:
        return {"is_open": False, "label": "Closed today"}

    current = now.time()
    if close_time <= open_time:
        # Kitchen closes after midnight
        is_open = current >= open_time or current < close_time
    else:
        is_open = open_time <= current < close_time

    if is_open:
        return {"is_open": True, "label": f"Open now · until {entry['close']}"}
    if current < open_time:
        return {"is_open": False, "label": f"Closed · opens {entry['open']}"}
    return {"is_open": False, "label": "Closed for today"}
