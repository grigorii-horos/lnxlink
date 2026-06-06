"""Toggle and report Night Light status"""
import logging
from shutil import which

from lnxlink.modules.scripts.helpers import syscommand

logger = logging.getLogger("lnxlink")


class Addon:
    """Addon module"""

    def __init__(self, lnxlink):
        """Setup addon"""
        self.name = "Night Light"
        self.lnxlink = lnxlink
        self.lnxlink.add_settings(
            "night_light",
            {
                "read_command": "",
                "on_command": "",
                "off_command": "",
            },
        )
        self.settings = self.lnxlink.config["settings"].get("night_light", {})

    def exposed_controls(self):
        """Exposes to home assistant"""
        return {
            "Night Light": {
                "type": "switch",
                "icon": "mdi:weather-night",
                "value_template": "{{ value_json.status }}",
                "attributes_template": "{{ value_json.attributes | tojson }}",
            }
        }

    def get_info(self):
        """Gather information from the system"""
        enabled, source, raw = self._read_state()
        status = None
        if enabled is True:
            status = "ON"
        elif enabled is False:
            status = "OFF"
        return {
            "status": status,
            "attributes": {
                "enabled": enabled,
                "source": source,
                "raw": raw,
            },
        }

    def start_control(self, topic, data):
        """Control system"""
        enabled = self._parse_bool(data)
        if enabled is None:
            logger.error("Expected ON/OFF, received: %s", data)
            return
        self._set_state(enabled)

    def _read_state(self):
        read_command = str(self.settings.get("read_command", "")).strip()
        if read_command:
            stdout, _, _ = syscommand(read_command, ignore_errors=True)
            return self._parse_bool(stdout), "command", stdout
        if which("gsettings") is None:
            return None, "none", ""
        stdout, _, _ = syscommand(
            "gsettings get org.gnome.settings-daemon.plugins.color night-light-enabled",
            ignore_errors=True,
        )
        return self._parse_bool(stdout), "gsettings", stdout

    def _set_state(self, enabled):
        on_command = str(self.settings.get("on_command", "")).strip()
        off_command = str(self.settings.get("off_command", "")).strip()
        if enabled and on_command:
            syscommand(on_command, ignore_errors=True)
            return
        if not enabled and off_command:
            syscommand(off_command, ignore_errors=True)
            return
        if which("gsettings") is None:
            logger.error("System command 'gsettings' not found")
            return
        value = "true" if enabled else "false"
        syscommand(
            f"gsettings set org.gnome.settings-daemon.plugins.color night-light-enabled {value}",
            ignore_errors=True,
        )

    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on", "enabled"}:
            return True
        if text in {"0", "false", "no", "off", "disabled"}:
            return False
        return None
