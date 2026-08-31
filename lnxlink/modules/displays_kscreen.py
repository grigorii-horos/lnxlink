"""Discover and toggle displays via kscreen-doctor (KDE KScreen)"""
import json
import logging
from shutil import which
from typing import Any, Dict

from lnxlink.modules.scripts.helpers import syscommand

logger = logging.getLogger("lnxlink")

# QT_QPA_PLATFORM=wayland avoids kscreen-doctor aborting when it tries (and
# fails) to fall back to an X11/xcb Qt platform plugin on a Wayland-only session.
_KSCREEN = "QT_QPA_PLATFORM=wayland kscreen-doctor"


class Addon:
    """Addon module for discovering and toggling KDE displays via kscreen-doctor

    Complements `screen_onoff`, which doesn't work on KDE Wayland.
    """

    def __init__(self, lnxlink):
        """Setup addon"""
        self.name = "Displays"
        self.lnxlink = lnxlink

        if which("kscreen-doctor") is None:
            raise RuntimeError("kscreen-doctor not found")

        self.displays: Dict[str, bool] = {}
        self._refresh_displays()

    def _refresh_displays(self) -> None:
        """Parse kscreen-doctor -j and populate display state"""
        stdout, _, rc = syscommand(f"{_KSCREEN} -j", ignore_errors=True)
        if rc != 0 or not stdout:
            return
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as err:
            logger.debug("Failed to parse kscreen-doctor output: %s", err)
            return

        displays = {}
        for output in data.get("outputs", []):
            if not output.get("connected"):
                continue
            display_name = output.get("name")
            if not display_name:
                continue
            displays[display_name] = output.get("enabled", False)
        self.displays = displays

    def _update_display(self, display_name: str, enabled: bool) -> None:
        """Update display state using kscreen-doctor"""
        action = "enable" if enabled else "disable"
        logger.info("Sending %s to %s", action, display_name)
        syscommand(f"{_KSCREEN} output.{display_name}.{action}", ignore_errors=True)
        self.displays[display_name] = enabled

    def exposed_controls(self) -> Dict[str, Dict[str, Any]]:
        """Expose a switch for each connected display"""
        controls = {}
        for display_name in self.displays:
            controls[display_name] = {
                "type": "switch",
                "icon": "mdi:monitor",
                "value_template": (
                    f"{{{{ 'ON' if value_json.get('{display_name}') else 'OFF' }}}}"
                ),
            }
        return controls

    def get_info(self) -> Dict[str, bool]:
        """Gather current on/off status of all displays"""
        self._refresh_displays()
        return self.displays

    def start_control(self, topic, data) -> None:
        """Enable or disable a display"""
        # topics are automatically lowercased from their controls' names, so
        # match case-insensitively (kscreen output names can be mixed-case,
        # e.g. laptop panels are typically "eDP-1")
        requested = topic[1].lower()
        display_name = next(
            (name for name in self.displays if name.lower() == requested), None
        )
        if display_name is None:
            logger.error("Could not find display: %s", topic[1])
            return

        command = data.lower()
        if command not in ("on", "off"):
            logger.error("Expected 'on' or 'off', got: %s", data)
            return

        self._update_display(display_name, command == "on")
