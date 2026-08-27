"""Toggle and report Do Not Disturb (DND) / notification inhibition status"""
import logging
import os
from shutil import which

from lnxlink.modules.scripts.helpers import syscommand

logger = logging.getLogger("lnxlink")


class Addon:
    """Addon module for Do Not Disturb (DND) notification inhibition"""

    def __init__(self, lnxlink):
        """Setup addon"""
        self.name = "Do Not Disturb"
        self.lnxlink = lnxlink
        self.lnxlink.add_settings(
            "dnd",
            {
                "read_command": "",
                "on_command": "",
                "off_command": "",
            },
        )
        self.settings = self.lnxlink.config["settings"].get("dnd", {})
        self.inhibit_cookie = None

    def exposed_controls(self):
        """Exposes to Home Assistant"""
        return {
            "Do Not Disturb": {
                "type": "switch",
                "icon": "mdi:minus-circle",
                "value_template": "{{ value_json.status }}",
                "attributes_template": "{{ value_json.attributes | tojson }}",
            }
        }

    def get_info(self):
        """Gather information from the system"""
        inhibited, backend, raw = self._read_state()
        status = None
        if inhibited is True:
            status = "ON"
        elif inhibited is False:
            status = "OFF"

        return {
            "status": status,
            "attributes": {
                "inhibited": inhibited,
                "backend": backend,
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
        """Reads DND state across different desktop environments"""
        read_cmd = str(self.settings.get("read_command", "")).strip()
        if read_cmd:
            stdout, _, rc = syscommand(read_cmd, ignore_errors=True)
            if rc == 0:
                return self._parse_bool(stdout), "command", stdout

        # 1. FreeDesktop / KDE / GNOME D-Bus notification property
        if which("gdbus") is not None:
            stdout, _, rc = syscommand(
                "gdbus call --session --dest org.freedesktop.Notifications "
                "--object-path /org/freedesktop/Notifications "
                "--method org.freedesktop.DBus.Properties.Get "
                "org.freedesktop.Notifications Inhibited",
                ignore_errors=True,
            )
            if rc == 0 and stdout:
                # gdbus returns e.g. (<true>,) or (<false>,)
                val = "<true>" in stdout.lower() or "true" in stdout.lower()
                return val, "freedesktop_dbus", stdout

        # 2. GNOME gsettings (show-banners: false means DND is active)
        if which("gsettings") is not None:
            stdout, _, rc = syscommand(
                "gsettings get org.gnome.desktop.notifications show-banners",
                ignore_errors=True,
            )
            if rc == 0 and stdout:
                show_banners = self._parse_bool(stdout)
                if show_banners is not None:
                    # If show-banners is False, DND is ON
                    return not show_banners, "gnome_gsettings", stdout

        # 3. KDE notificationrc check
        kde_notif = os.path.expanduser("~/.config/notificationrc")
        if os.path.exists(kde_notif):
            stdout, _, rc = syscommand(
                "kreadconfig6 --file notificationrc --group DoNotDisturb --key Running",
                ignore_errors=True,
            )
            if rc != 0:
                stdout, _, rc = syscommand(
                    "kreadconfig5 --file notificationrc --group DoNotDisturb --key Running",
                    ignore_errors=True,
                )
            if rc == 0 and stdout:
                val = self._parse_bool(stdout)
                if val is not None:
                    return val, "kde_config", stdout

        # Fallback to internal inhibit cookie state if active
        if self.inhibit_cookie is not None:
            return True, "cookie_state", str(self.inhibit_cookie)

        return False, "default", ""

    def _set_state(self, enabled):
        """Sets DND state"""
        on_cmd = str(self.settings.get("on_command", "")).strip()
        off_cmd = str(self.settings.get("off_command", "")).strip()
        if enabled and on_cmd:
            syscommand(on_cmd, ignore_errors=True)
            return
        if not enabled and off_cmd:
            syscommand(off_cmd, ignore_errors=True)
            return

        # 1. FreeDesktop D-Bus Inhibit / UnInhibit
        if which("gdbus") is not None:
            if enabled:
                stdout, _, rc = syscommand(
                    "gdbus call --session --dest org.freedesktop.Notifications "
                    "--object-path /org/freedesktop/Notifications "
                    '--method org.freedesktop.Notifications.Inhibit "LNXlink" "Do Not Disturb" "{}"',
                    ignore_errors=True,
                )
                if rc == 0 and "uint32" in stdout:
                    try:
                        self.inhibit_cookie = int(stdout.split("uint32")[1].split(")")[0].strip(", "))
                    except Exception:
                        pass
                    return
            elif self.inhibit_cookie is not None:
                syscommand(
                    f"gdbus call --session --dest org.freedesktop.Notifications "
                    f"--object-path /org/freedesktop/Notifications "
                    f"--method org.freedesktop.Notifications.UnInhibit {self.inhibit_cookie}",
                    ignore_errors=True,
                )
                self.inhibit_cookie = None
                return

        # 2. GNOME gsettings
        if which("gsettings") is not None:
            # DND enabled = show-banners false
            val = "false" if enabled else "true"
            syscommand(
                f"gsettings set org.gnome.desktop.notifications show-banners {val}",
                ignore_errors=True,
            )

    @staticmethod
    def _parse_bool(value):
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "(<true>,)"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "(<false>,)"}:
            return False
        return None
