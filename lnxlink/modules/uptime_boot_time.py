"""Report system uptime and last boot time"""
import time
from datetime import datetime

import psutil


class Addon:
    """Addon module"""

    def __init__(self, lnxlink):
        """Setup addon"""
        self.name = "Uptime and Boot Time"
        self.lnxlink = lnxlink

    def get_info(self):
        """Gather information from the system"""
        boot_time = psutil.boot_time()
        uptime_seconds = max(0, int(time.time() - boot_time))
        return {
            "uptime_seconds": uptime_seconds,
            "uptime_human": self._format_uptime(uptime_seconds),
            "boot_time": datetime.fromtimestamp(boot_time).astimezone().isoformat(),
        }

    def exposed_controls(self):
        """Exposes to home assistant"""
        return {
            "Uptime": {
                "type": "sensor",
                "icon": "mdi:timer-outline",
                "unit": "s",
                "device_class": "duration",
                "state_class": "measurement",
                "value_template": "{{ value_json.uptime_seconds }}",
                "attributes_template": (
                    "{{ {'human': value_json.uptime_human, "
                    "'boot_time': value_json.boot_time} | tojson }}"
                ),
            },
            "Boot Time": {
                "type": "sensor",
                "icon": "mdi:clock-start",
                "device_class": "timestamp",
                "value_template": "{{ value_json.boot_time }}",
                "enabled": False,
            },
        }

    def _format_uptime(self, seconds):
        seconds = int(seconds)
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, secs = divmod(remainder, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours or days:
            parts.append(f"{hours}h")
        if minutes or hours or days:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)
