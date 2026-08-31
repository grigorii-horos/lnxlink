"""Monitor user inactivity duration on Wayland (ext-idle-notify-v1)"""
import logging
import threading
import time
from importlib import import_module

from lnxlink.modules.scripts.helpers import import_install_package

logger = logging.getLogger("lnxlink")

# Granularity of the idle/resumed edge, in milliseconds. The protocol only
# reports edges (idled/resumed), not a continuously queryable idle time, so
# this is added back on top of the elapsed time since the edge fired.
IDLE_TIMEOUT_MS = 1000


class Addon:  # pylint: disable=too-many-instance-attributes
    """Addon module for Wayland idle time, via the ext-idle-notify-v1 protocol

    The stock `idle` module relies on `dbus_idle`, which only finds a working
    backend on GNOME (`org.gnome.Mutter.IdleMonitor`) or X11 (XScreenSaver
    extension). KWin/Plasma on Wayland exposes neither, so idle time is
    unavailable there. This module talks directly to the compositor over the
    standard `ext-idle-notify-v1` Wayland protocol instead, which KWin (and
    other Wayland compositors that implement it) does support.
    """

    def __init__(self, lnxlink):
        """Setup addon"""
        self.name = "Idle (Wayland)"
        self.lnxlink = lnxlink
        self._lock = threading.Lock()
        self._idle_since = None  # time.monotonic() the idle edge fired, or None

        if import_install_package("pywayland") is None:
            raise RuntimeError("Python package 'pywayland' can't be installed")

        self._display_cls = import_module("pywayland.client").Display
        self._wl_seat_cls = import_module("pywayland.protocol.wayland").WlSeat
        self._notifier_cls = import_module(
            "pywayland.protocol.ext_idle_notify_v1"
        ).ExtIdleNotifierV1

        self._display = self._display_cls()
        self._display.connect()
        seat, notifier = self._bind_globals()
        if notifier is None:
            self._display.disconnect()
            raise RuntimeError(
                "Compositor does not support ext-idle-notify-v1 (Wayland required)"
            )

        notification = notifier.get_idle_notification(IDLE_TIMEOUT_MS, seat)
        notification.dispatcher["idled"] = self._on_idled
        notification.dispatcher["resumed"] = self._on_resumed
        self._display.roundtrip()

        threading.Thread(target=self._watch_events, daemon=True).start()

    def _bind_globals(self):
        """Bind the wl_seat and ext_idle_notifier_v1 globals from the registry"""
        bound = {"seat": None, "notifier": None}

        def on_global(registry, name, interface, version):
            if interface == "wl_seat":
                bound["seat"] = registry.bind(name, self._wl_seat_cls, min(version, 7))
            elif interface == "ext_idle_notifier_v1":
                bound["notifier"] = registry.bind(
                    name, self._notifier_cls, min(version, 1)
                )

        registry = self._display.get_registry()
        registry.dispatcher["global"] = on_global
        self._display.dispatch(block=True)
        self._display.roundtrip()
        return bound["seat"], bound["notifier"]

    def _on_idled(self, _notification):
        with self._lock:
            self._idle_since = time.monotonic()

    def _on_resumed(self, _notification):
        with self._lock:
            self._idle_since = None

    def _watch_events(self):
        """Background Wayland event loop, dispatches idled/resumed callbacks"""
        while True:
            try:
                self._display.dispatch(block=True)
            except Exception as err:
                logger.error("Wayland idle-notify event loop stopped: %s", err)
                return

    def get_info(self):
        """Gather information from the system"""
        with self._lock:
            idle_since = self._idle_since
        if idle_since is None:
            return 0
        idle_sec = (time.monotonic() - idle_since) + (IDLE_TIMEOUT_MS / 1000)
        return round(idle_sec, 0)

    def exposed_controls(self):
        """Exposes to home assistant"""
        return {
            "Idle (Wayland)": {
                "type": "sensor",
                "icon": "mdi:timer-sand",
                "unit": "s",
                "state_class": "total_increasing",
                "device_class": "duration",
            },
        }
