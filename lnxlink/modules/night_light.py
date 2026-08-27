"""Toggle and report Night Light status across desktop environments"""
import logging
import os
from shutil import which

from lnxlink.modules.scripts.helpers import syscommand

logger = logging.getLogger("lnxlink")


class Addon:
    """Addon module for Night Light / Blue Light Filter"""

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
        self.inhibit_cookie = None

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
        enabled, source, extra_attrs = self._read_state()
        status = None
        if enabled is True:
            status = "ON"
        elif enabled is False:
            status = "OFF"

        attrs = {
            "enabled": enabled,
            "source": source,
        }
        if extra_attrs:
            attrs.update(extra_attrs)

        return {
            "status": status,
            "attributes": attrs,
        }

    def start_control(self, topic, data):
        """Control system"""
        enabled = self._parse_bool(data)
        if enabled is None:
            logger.error("Expected ON/OFF, received: %s", data)
            return
        self._set_state(enabled)

    def _read_state(self):
        # 1. Custom read command
        read_command = str(self.settings.get("read_command", "")).strip()
        if read_command:
            stdout, _, _ = syscommand(read_command, ignore_errors=True)
            return self._parse_bool(stdout), "command", {"raw": stdout}

        # 2. KDE Plasma KWin NightLight D-Bus
        if which("gdbus") is not None:
            stdout, _, rc = syscommand(
                "gdbus call --session --dest org.kde.KWin.NightLight "
                "--object-path /org/kde/KWin/NightLight "
                "--method org.freedesktop.DBus.Properties.GetAll org.kde.KWin.NightLight",
                ignore_errors=True,
            )
            if rc == 0 and stdout:
                running = "'running': <true>" in stdout.lower()
                enabled = "'enabled': <true>" in stdout.lower()
                inhibited = "'inhibited': <true>" in stdout.lower()
                daylight = "'daylight': <true>" in stdout.lower()
                is_active = (running or enabled) and not inhibited

                attrs = {
                    "running": running,
                    "enabled": enabled,
                    "inhibited": inhibited,
                    "daylight": daylight,
                }
                # Parse currentTemperature
                if "currenttemperature" in stdout.lower():
                    try:
                        temp_part = stdout.lower().split("currenttemperature': <uint32")[1]
                        temp_val = int(temp_part.split(">")[0].strip())
                        attrs["current_temperature"] = temp_val
                    except Exception:
                        pass

                return is_active, "kde_kwin_dbus", attrs

        # 3. GNOME gsettings
        if which("gsettings") is not None:
            stdout, _, rc = syscommand(
                "gsettings get org.gnome.settings-daemon.plugins.color night-light-enabled",
                ignore_errors=True,
            )
            if rc == 0 and stdout:
                val = self._parse_bool(stdout)
                if val is not None:
                    return val, "gnome_gsettings", {"raw": stdout}

        # 4. Fallback check for gammastep or redshift process
        stdout, _, rc = syscommand("pgrep -x gammastep || pgrep -x redshift", ignore_errors=True)
        if rc == 0 and stdout.strip():
            return True, "process", {"pid": stdout.strip()}

        return None, "none", {}

    def _set_state(self, enabled):
        on_command = str(self.settings.get("on_command", "")).strip()
        off_command = str(self.settings.get("off_command", "")).strip()
        if enabled and on_command:
            syscommand(on_command, ignore_errors=True)
            return
        if not enabled and off_command:
            syscommand(off_command, ignore_errors=True)
            return

        # 1. KDE KWin NightLight via D-Bus Inhibit / Uninhibit
        if which("gdbus") is not None:
            # Check if KWin NightLight is present
            _, _, rc = syscommand(
                "gdbus introspect --session --dest org.kde.KWin.NightLight "
                "--object-path /org/kde/KWin/NightLight",
                ignore_errors=True,
            )
            if rc == 0:
                if not enabled:
                    # Inhibit nightlight
                    stdout, _, irc = syscommand(
                        "gdbus call --session --dest org.kde.KWin.NightLight "
                        "--object-path /org/kde/KWin/NightLight "
                        "--method org.kde.KWin.NightLight.inhibit",
                        ignore_errors=True,
                    )
                    if irc == 0 and "uint32" in stdout:
                        try:
                            self.inhibit_cookie = int(
                                stdout.split("uint32")[1].split(")")[0].strip(", ")
                            )
                        except Exception:
                            pass
                    return
                elif self.inhibit_cookie is not None:
                    # Uninhibit nightlight
                    syscommand(
                        f"gdbus call --session --dest org.kde.KWin.NightLight "
                        f"--object-path /org/kde/KWin/NightLight "
                        f"--method org.kde.KWin.NightLight.uninhibit {self.inhibit_cookie}",
                        ignore_errors=True,
                    )
                    self.inhibit_cookie = None
                    return

        # 2. GNOME gsettings
        if which("gsettings") is not None:
            value = "true" if enabled else "false"
            syscommand(
                f"gsettings set org.gnome.settings-daemon.plugins.color night-light-enabled {value}",
                ignore_errors=True,
            )

    @staticmethod
    def _parse_bool(value):
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
