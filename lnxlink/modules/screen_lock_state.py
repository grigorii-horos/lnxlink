"""Track and control the session lock state"""
import os
import logging
from shutil import which

from lnxlink.modules.scripts.helpers import syscommand

logger = logging.getLogger("lnxlink")


class Addon:
    """Addon module"""

    def __init__(self, lnxlink):
        """Setup addon"""
        self.name = "Screen Lock State"
        self.lnxlink = lnxlink
        self.lnxlink.add_settings(
            "screen_lock_state",
            {
                "read_command": "",
                "lock_command": "",
                "unlock_command": "",
                "session_id": "",
            },
        )
        self.settings = self.lnxlink.config["settings"].get("screen_lock_state", {})
        self.user = os.environ.get("USER") or os.environ.get("LOGNAME")
        self.session_id = self._get_session_id()

    def exposed_controls(self):
        """Exposes to home assistant"""
        return {
            "Screen Lock": {
                "type": "switch",
                "icon": "mdi:lock",
                "value_template": "{{ value_json.status }}",
                "attributes_template": "{{ value_json.attributes | tojson }}",
            }
        }

    def get_info(self):
        """Gather information from the system"""
        locked, source, raw = self._read_lock_state()
        status = None
        if locked is True:
            status = "ON"
        elif locked is False:
            status = "OFF"
        return {
            "status": status,
            "attributes": {
                "locked": locked,
                "session_id": self.session_id,
                "user": self.user,
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
        if enabled:
            self._lock()
        else:
            self._unlock()

    def _read_lock_state(self):
        read_command = str(self.settings.get("read_command", "")).strip()
        if read_command:
            stdout, _, _ = syscommand(read_command, ignore_errors=True)
            return self._parse_bool(stdout), "command", stdout

        if which("loginctl") is None:
            return None, "none", ""

        if self.session_id:
            stdout, _, _ = syscommand(
                f"loginctl show-session {self.session_id} -p LockedHint",
                ignore_errors=True,
            )
            value = stdout.split("=", maxsplit=1)[-1].strip()
            return self._parse_bool(value), "loginctl", stdout

        stdout, _, _ = syscommand(
            "loginctl list-sessions --no-legend",
            ignore_errors=True,
        )
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and self.user and parts[2] == self.user:
                self.session_id = parts[0]
                detail, _, _ = syscommand(
                    f"loginctl show-session {self.session_id} -p LockedHint",
                    ignore_errors=True,
                )
                value = detail.split("=", maxsplit=1)[-1].strip()
                return self._parse_bool(value), "loginctl", detail
        return None, "loginctl", stdout

    def _lock(self):
        lock_command = str(self.settings.get("lock_command", "")).strip()
        if lock_command:
            syscommand(lock_command, ignore_errors=True)
            return
        if which("loginctl") is None:
            logger.error("System command 'loginctl' not found")
            return
        command = "loginctl lock-session"
        if self.session_id:
            command = f"{command} {self.session_id}"
        syscommand(command, ignore_errors=True)

    def _unlock(self):
        unlock_command = str(self.settings.get("unlock_command", "")).strip()
        if unlock_command:
            syscommand(unlock_command, ignore_errors=True)
            return
        if which("loginctl") is None:
            logger.error("System command 'loginctl' not found")
            return
        command = "loginctl unlock-session"
        if self.session_id:
            command = f"{command} {self.session_id}"
        syscommand(command, ignore_errors=True)

    def _get_session_id(self):
        session_id = str(self.settings.get("session_id", "")).strip()
        if session_id:
            return session_id
        env_session = os.environ.get("XDG_SESSION_ID")
        if env_session:
            return env_session
        return None

    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on", "locked"}:
            return True
        if text in {"0", "false", "no", "off", "unlocked"}:
            return False
        return None
