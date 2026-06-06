"""Report the next calendar event from a local CalDAV-synced folder"""
import os
import time
import logging
from datetime import datetime, timedelta, time as time_obj
from pathlib import Path

from lnxlink.modules.scripts.helpers import import_install_package

logger = logging.getLogger("lnxlink")


class Addon:
    """Addon module"""

    def __init__(self, lnxlink):
        """Setup addon"""
        self.name = "Calendar Next Event"
        self.lnxlink = lnxlink
        self.lnxlink.add_settings(
            "calendar_next_event",
            {
                "path": "",
                "calendar": "",
                "days_ahead": 30,
                "include_all_day": True,
                "recursive": False,
                "refresh_interval": 60,
            },
        )
        self.settings = self.lnxlink.config["settings"].get("calendar_next_event", {})
        self._requirements()
        self._calendar_dir = self._resolve_calendar_dir()
        self.last_refresh = 0
        self.cached_info = None

    def exposed_controls(self):
        """Exposes to home assistant"""
        return {
            "Calendar Next Event": {
                "type": "sensor",
                "icon": "mdi:calendar-clock",
                "device_class": "timestamp",
                "value_template": "{{ value_json.start }}",
                "attributes_template": "{{ value_json.attributes | tojson }}",
            },
        }

    def get_info(self):
        """Gather information from the system"""
        refresh_interval = int(self.settings.get("refresh_interval", 60) or 0)
        if time.time() - self.last_refresh < refresh_interval and self.cached_info:
            return self.cached_info
        self.last_refresh = time.time()
        self.cached_info = self._get_next_event()
        return self.cached_info

    def _requirements(self):
        self.icalendar = import_install_package("icalendar", ">=5.0.0", "icalendar")
        self.recurring = import_install_package(
            "recurring-ical-events",
            ">=2.1.2",
            "recurring_ical_events",
        )
        if self.icalendar is None or self.recurring is None:
            raise SystemError("Calendar Next Event requirements are missing")

    def _resolve_calendar_dir(self):
        path = str(self.settings.get("path", "")).strip()
        if not path:
            raise SystemError(
                "Calendar Next Event is not configured; set settings.calendar_next_event.path"
            )
        path = os.path.expanduser(path)
        calendar = str(self.settings.get("calendar", "")).strip()
        if calendar:
            path = os.path.join(path, calendar)
        calendar_dir = Path(path)
        if not calendar_dir.exists():
            raise SystemError(f"Calendar path not found: {calendar_dir}")
        return calendar_dir

    def _get_next_event(self):
        now = datetime.now().astimezone()
        days_ahead = int(self.settings.get("days_ahead", 30) or 30)
        window_end = now + timedelta(days=days_ahead)
        include_all_day = bool(self.settings.get("include_all_day", True))
        recursive = bool(self.settings.get("recursive", False))
        ics_files = (
            self._calendar_dir.rglob("*.ics")
            if recursive
            else self._calendar_dir.glob("*.ics")
        )

        best_event = None
        for ics_file in ics_files:
            try:
                data = ics_file.read_bytes()
                calendar = self.icalendar.Calendar.from_ical(data)
                events = self.recurring.of(calendar).between(now, window_end)
            except Exception as err:
                logger.error("Calendar parse failed for %s: %s", ics_file, err)
                continue

            for event in events:
                event_data = self._event_to_payload(event, now)
                if event_data is None:
                    continue
                if not include_all_day and event_data["attributes"]["is_all_day"]:
                    continue
                best_event = self._pick_best_event(best_event, event_data, now)

        if best_event is None:
            return {
                "start": None,
                "attributes": {
                    "summary": None,
                    "end": None,
                    "location": None,
                    "description": None,
                    "calendar": self.settings.get("calendar") or None,
                    "is_all_day": None,
                    "status": "none",
                    "time_until": None,
                },
            }
        return best_event

    def _pick_best_event(self, current, candidate, now):
        if current is None:
            return candidate
        cur_attr = current["attributes"]
        cand_attr = candidate["attributes"]
        cur_start = self._parse_iso(current["start"])
        cand_start = self._parse_iso(candidate["start"])
        cur_end = self._parse_iso(cur_attr.get("end")) or cur_start
        cand_end = self._parse_iso(cand_attr.get("end")) or cand_start

        cur_priority = self._event_priority(cur_start, cur_end, now)
        cand_priority = self._event_priority(cand_start, cand_end, now)
        if cand_priority < cur_priority:
            return candidate
        if cand_priority == cur_priority:
            if cand_priority[0] == 0 and cand_end < cur_end:
                return candidate
            if cand_priority[0] == 1 and cand_start < cur_start:
                return candidate
        return current

    def _event_priority(self, start, end, now):
        if start is None:
            return (2, datetime.max)
        if end is None:
            end = start
        if start <= now < end:
            return (0, end)
        return (1, start)

    def _event_to_payload(self, event, now):
        start_raw = event.get("dtstart")
        if start_raw is None:
            return None
        start = self._normalize_dt(start_raw.dt)
        end = self._extract_end(event, start)
        is_all_day = not isinstance(start_raw.dt, datetime)
        status = "ongoing" if end and start <= now < end else "upcoming"
        time_until = max(0, int((start - now).total_seconds()))
        summary = self._safe_text(event.get("summary"))
        location = self._safe_text(event.get("location"))
        description = self._safe_text(event.get("description"))
        return {
            "start": start.isoformat(),
            "attributes": {
                "summary": summary,
                "end": end.isoformat() if end else None,
                "location": location,
                "description": description,
                "calendar": self.settings.get("calendar") or None,
                "is_all_day": is_all_day,
                "status": status,
                "time_until": time_until,
            },
        }

    def _extract_end(self, event, start):
        end_raw = event.get("dtend")
        if end_raw is not None:
            return self._normalize_dt(end_raw.dt)
        duration = event.get("duration")
        if duration is not None:
            duration_value = duration.dt if hasattr(duration, "dt") else duration
            if isinstance(duration_value, timedelta):
                return start + duration_value
        return None

    def _normalize_dt(self, value):
        local_tz = datetime.now().astimezone().tzinfo
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=local_tz)
            return value.astimezone(local_tz)
        if hasattr(value, "year"):
            return datetime.combine(value, time_obj.min).replace(tzinfo=local_tz)
        return None

    def _parse_iso(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _safe_text(self, prop):
        if prop is None:
            return None
        try:
            return str(prop)
        except Exception:
            return None
