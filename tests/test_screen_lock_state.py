"""Tests for the Screen Lock State module."""
# pylint: disable=missing-class-docstring,missing-function-docstring

from unittest.mock import MagicMock, patch

from lnxlink.modules import screen_lock_state


class FakeLnxlink:
    def __init__(self, settings=None):
        self.config = {"settings": {"screen_lock_state": settings or {}}}
        self.run_module_calls = []

    def add_settings(self, name, default):
        pass

    def run_module(self, topic, data, force_update=False):
        self.run_module_calls.append((topic, data, force_update))


def test_screen_lock_state_exposed_controls():
    lnxlink = FakeLnxlink()
    addon = screen_lock_state.Addon(lnxlink)
    controls = addon.exposed_controls()
    assert "Screen Lock" in controls
    assert controls["Screen Lock"]["type"] == "switch"


def test_screen_lock_state_get_info_locked():
    lnxlink = FakeLnxlink({"session_id": "2"})
    addon = screen_lock_state.Addon(lnxlink)

    with patch("lnxlink.modules.screen_lock_state.which", return_value="/usr/bin/loginctl"), \
         patch("lnxlink.modules.screen_lock_state.syscommand", return_value=("LockedHint=yes", "", 0)):
        info = addon.get_info()
        assert info["status"] == "ON"
        assert info["attributes"]["locked"] is True
        assert info["attributes"]["session_id"] == "2"


def test_screen_lock_state_get_info_unlocked():
    lnxlink = FakeLnxlink({"session_id": "2"})
    addon = screen_lock_state.Addon(lnxlink)

    with patch("lnxlink.modules.screen_lock_state.which", return_value="/usr/bin/loginctl"), \
         patch("lnxlink.modules.screen_lock_state.syscommand", return_value=("LockedHint=no", "", 0)):
        info = addon.get_info()
        assert info["status"] == "OFF"
        assert info["attributes"]["locked"] is False


def test_screen_lock_state_start_control_lock():
    lnxlink = FakeLnxlink({"session_id": "2"})
    addon = screen_lock_state.Addon(lnxlink)

    with patch("lnxlink.modules.screen_lock_state.which", return_value="/usr/bin/loginctl"), \
         patch("lnxlink.modules.screen_lock_state.syscommand", return_value=("", "", 0)) as mock_cmd:
        addon.start_control(["screen_lock"], "ON")
        assert mock_cmd.called
        assert len(lnxlink.run_module_calls) == 1
