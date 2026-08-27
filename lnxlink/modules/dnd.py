"""Toggle and report Do Not Disturb (DND) / notification inhibition status"""
import configparser
import datetime
import logging
import os
from shutil import which
from typing import Any, Dict, Optional, Tuple

from jeepney import DBusAddress, new_method_call
from jeepney.io.blocking import open_dbus_connection

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
        self.inhibit_cookie: Optional[int] = None
        self.conn = None
        self.notif_addr = DBusAddress(
            "/org/freedesktop/Notifications",
            bus_name="org.freedesktop.Notifications",
            interface="org.freedesktop.Notifications",
        )
        self.prop_addr = DBusAddress(
            "/org/freedesktop/Notifications",
            bus_name="org.freedesktop.Notifications",
            interface="org.freedesktop.DBus.Properties",
        )
        self._init_dbus()

    def _init_dbus(self):
        """Initialize session D-Bus connection for persistent notification inhibition"""
        try:
            self.conn = open_dbus_connection(bus="SESSION")
        except Exception as err:
            logger.debug("Failed to connect to session D-Bus in DND module: %s", err)
            self.conn = None

    def exposed_controls(self) -> Dict[str, Dict[str, Any]]:
        """Exposes to Home Assistant"""
        return {
            "Do Not Disturb": {
                "type": "switch",
                "icon": "mdi:minus-circle",
                "value_template": "{{ value_json.status }}",
                "attributes_template": "{{ value_json.attributes | tojson }}",
            }
        }

    def get_info(self) -> Dict[str, Any]:
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
        # Immediately publish new state to MQTT
        self.lnxlink.run_module(self.name, self.get_info())

    def _read_state(self) -> Tuple[Optional[bool], str, Any]:
        """Reads DND state across different desktop environments"""
        # 1. Custom read command
        read_cmd = str(self.settings.get("read_command", "")).strip()
        if read_cmd:
            stdout, _, rc = syscommand(read_cmd, ignore_errors=True)
            if rc == 0:
                return self._parse_bool(stdout), "command", stdout

        # 2. Check if we currently hold an active D-Bus inhibit cookie
        if self.inhibit_cookie is not None:
            return True, "inhibit_cookie", str(self.inhibit_cookie)

        # 3. FreeDesktop D-Bus property 'Inhibited'
        if self.conn is not None:
            try:
                msg = new_method_call(
                    self.prop_addr,
                    "Get",
                    "ss",
                    ("org.freedesktop.Notifications", "Inhibited"),
                )
                reply = self.conn.send_and_get_reply(msg, timeout=2.0)
                if reply.body and len(reply.body) > 0:
                    val = reply.body[0][1]
                    if isinstance(val, bool):
                        return val, "freedesktop_dbus", val
            except Exception as err:
                logger.debug("Error reading Inhibited DBus property: %s", err)

        # Fallback to gdbus CLI
        if which("gdbus") is not None:
            stdout, _, rc = syscommand(
                "gdbus call --session --dest org.freedesktop.Notifications "
                "--object-path /org/freedesktop/Notifications "
                "--method org.freedesktop.DBus.Properties.Get "
                "org.freedesktop.Notifications Inhibited",
                ignore_errors=True,
            )
            if rc == 0 and stdout:
                val = "<true>" in stdout.lower() or "true" in stdout.lower()
                return val, "gdbus", stdout

        # 4. GNOME gsettings (show-banners: false means DND is active)
        if which("gsettings") is not None:
            stdout, _, rc = syscommand(
                "gsettings get org.gnome.desktop.notifications show-banners",
                ignore_errors=True,
            )
            if rc == 0 and stdout:
                show_banners = self._parse_bool(stdout)
                if show_banners is not None:
                    return not show_banners, "gnome_gsettings", stdout

        # 5. KDE plasmanotifyrc check
        plasmanotifyrc_path = os.path.expanduser("~/.config/plasmanotifyrc")
        if os.path.exists(plasmanotifyrc_path):
            try:
                config = configparser.ConfigParser()
                config.read(plasmanotifyrc_path, encoding="utf-8")
                if "DoNotDisturb" in config and "Until" in config["DoNotDisturb"]:
                    until_str = config["DoNotDisturb"]["Until"].strip()
                    if until_str:
                        return True, "kde_plasmanotifyrc", until_str
            except Exception as err:
                logger.debug("Failed to read plasmanotifyrc: %s", err)

        # 6. Swaync
        if which("swaync-client") is not None:
            stdout, _, rc = syscommand("swaync-client -D", ignore_errors=True)
            if rc == 0 and stdout:
                val = self._parse_bool(stdout)
                if val is not None:
                    return val, "swaync", stdout

        # 7. Dunst
        if which("dunstctl") is not None:
            stdout, _, rc = syscommand("dunstctl is-paused", ignore_errors=True)
            if rc == 0 and stdout:
                val = self._parse_bool(stdout)
                if val is not None:
                    return val, "dunst", stdout

        # 8. Mako
        if which("makoctl") is not None:
            stdout, _, rc = syscommand("makoctl mode", ignore_errors=True)
            if rc == 0 and stdout:
                return "dnd" in stdout.lower(), "mako", stdout

        return False, "none", ""

    def _set_state(self, enabled: bool) -> None:
        """Sets DND state"""
        # 1. Custom on/off commands
        on_cmd = str(self.settings.get("on_command", "")).strip()
        off_cmd = str(self.settings.get("off_command", "")).strip()
        if enabled and on_cmd:
            syscommand(on_cmd, ignore_errors=True)
            return
        if not enabled and off_cmd:
            syscommand(off_cmd, ignore_errors=True)
            return

        # 2. KDE Plasma plasmanotifyrc
        if which("kwriteconfig6") is not None:
            until_val = "2037,1,1,0,0,0.0" if enabled else ""
            syscommand(
                f'kwriteconfig6 --file plasmanotifyrc --group DoNotDisturb --key Until "{until_val}"',
                ignore_errors=True,
            )
        elif which("kwriteconfig5") is not None:
            until_val = "2037,1,1,0,0,0.0" if enabled else ""
            syscommand(
                f'kwriteconfig5 --file plasmanotifyrc --group DoNotDisturb --key Until "{until_val}"',
                ignore_errors=True,
            )

        # 3. GNOME gsettings (show-banners false = DND ON)
        if which("gsettings") is not None:
            val = "false" if enabled else "true"
            syscommand(
                f"gsettings set org.gnome.desktop.notifications show-banners {val}",
                ignore_errors=True,
            )

        # 4. Swaync / Dunst / Mako
        if which("swaync-client") is not None:
            flag = "-s" if enabled else "-u"
            syscommand(f"swaync-client -d {flag}", ignore_errors=True)
        if which("dunstctl") is not None:
            val = "true" if enabled else "false"
            syscommand(f"dunstctl set-paused {val}", ignore_errors=True)
        if which("makoctl") is not None:
            cmd = "mode -a dnd" if enabled else "mode -r dnd"
            syscommand(f"makoctl {cmd}", ignore_errors=True)

        # 5. FreeDesktop D-Bus Inhibit / UnInhibit via persistent connection
        if self.conn is None:
            self._init_dbus()

        if self.conn is not None:
            if enabled:
                if self.inhibit_cookie is None:
                    try:
                        msg = new_method_call(
                            self.notif_addr,
                            "Inhibit",
                            "ssa{sv}",
                            ("LNXlink", "Do Not Disturb from Home Assistant", {}),
                        )
                        reply = self.conn.send_and_get_reply(msg, timeout=2.0)
                        if reply.body and len(reply.body) > 0:
                            self.inhibit_cookie = reply.body[0]
                            logger.info(
                                "DND inhibited via D-Bus cookie %s", self.inhibit_cookie
                            )
                    except Exception as err:
                        logger.debug("Failed to inhibit DND via D-Bus: %s", err)
            else:
                if self.inhibit_cookie is not None:
                    try:
                        msg = new_method_call(
                            self.notif_addr,
                            "UnInhibit",
                            "u",
                            (self.inhibit_cookie,),
                        )
                        self.conn.send_message(msg)
                        logger.info(
                            "DND uninhibited via D-Bus cookie %s", self.inhibit_cookie
                        )
                    except Exception as err:
                        logger.debug("Failed to uninhibit DND via D-Bus: %s", err)
                    finally:
                        self.inhibit_cookie = None

    @staticmethod
    def _parse_bool(value) -> Optional[bool]:
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
