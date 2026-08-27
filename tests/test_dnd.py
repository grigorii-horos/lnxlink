"""Tests for the Do Not Disturb (DND) module."""
# pylint: disable=missing-class-docstring,missing-function-docstring

from unittest.mock import MagicMock, patch

from lnxlink.modules import dnd


class FakeLnxlink:
    def __init__(self, settings=None):
        self.config = {"settings": {"dnd": settings or {}}}

    def add_settings(self, name, default):
        pass


def test_dnd_exposed_controls():
    lnxlink = FakeLnxlink()
    addon = dnd.Addon(lnxlink)
    controls = addon.exposed_controls()
    assert "Do Not Disturb" in controls
    assert controls["Do Not Disturb"]["type"] == "switch"


def test_dnd_get_info_dbus_on():
    lnxlink = FakeLnxlink()
    addon = dnd.Addon(lnxlink)

    with patch("lnxlink.modules.dnd.syscommand", return_value=("(<true>,)", "", 0)), \
         patch("lnxlink.modules.dnd.which", return_value="/usr/bin/gdbus"):
        info = addon.get_info()
        assert info["status"] == "ON"
        assert info["attributes"]["inhibited"] is True
        assert info["attributes"]["backend"] == "freedesktop_dbus"


def test_dnd_get_info_dbus_off():
    lnxlink = FakeLnxlink()
    addon = dnd.Addon(lnxlink)

    with patch("lnxlink.modules.dnd.syscommand", return_value=("(<false>,)", "", 0)), \
         patch("lnxlink.modules.dnd.which", return_value="/usr/bin/gdbus"):
        info = addon.get_info()
        assert info["status"] == "OFF"
        assert info["attributes"]["inhibited"] is False


def test_dnd_start_control_inhibit():
    lnxlink = FakeLnxlink()
    addon = dnd.Addon(lnxlink)

    with patch("lnxlink.modules.dnd.syscommand", return_value=("(uint32 42,)", "", 0)) as mock_cmd, \
         patch("lnxlink.modules.dnd.which", return_value="/usr/bin/gdbus"):
        addon.start_control(["dnd"], "ON")
        assert addon.inhibit_cookie == 42
        assert mock_cmd.called
