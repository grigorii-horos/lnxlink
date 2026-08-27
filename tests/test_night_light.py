"""Tests for the Night Light module."""
# pylint: disable=missing-class-docstring,missing-function-docstring

from unittest.mock import patch

from lnxlink.modules import night_light


class FakeLnxlink:
    def __init__(self, settings=None):
        self.config = {"settings": {"night_light": settings or {}}}

    def add_settings(self, name, default):
        pass


def test_night_light_exposed_controls():
    lnxlink = FakeLnxlink()
    addon = night_light.Addon(lnxlink)
    controls = addon.exposed_controls()
    assert "Night Light" in controls
    assert controls["Night Light"]["type"] == "switch"


def test_night_light_kde_dbus_running():
    lnxlink = FakeLnxlink()
    addon = night_light.Addon(lnxlink)

    fake_dbus_output = (
        "({'available': <true>, 'currenttemperature': <uint32 4500>, "
        "'daylight': <false>, 'enabled': <true>, 'inhibited': <false>, "
        "'mode': <uint32 1>, 'running': <true>},)"
    )

    with patch("lnxlink.modules.night_light.which", return_value="/usr/bin/gdbus"), \
         patch("lnxlink.modules.night_light.syscommand", return_value=(fake_dbus_output, "", 0)):
        info = addon.get_info()
        assert info["status"] == "ON"
        assert info["attributes"]["enabled"] is True
        assert info["attributes"]["inhibited"] is False
        assert info["attributes"]["current_temperature"] == 4500
        assert info["attributes"]["source"] == "kde_kwin_dbus"


def test_night_light_kde_inhibit_control():
    lnxlink = FakeLnxlink()
    addon = night_light.Addon(lnxlink)

    def fake_syscommand(cmd, **kwargs):
        if "introspect" in cmd:
            return ("node /org/kde/KWin/NightLight {}", "", 0)
        if "inhibit" in cmd:
            return ("(uint32 99,)", "", 0)
        return ("", "", 0)

    with patch("lnxlink.modules.night_light.which", return_value="/usr/bin/gdbus"), \
         patch("lnxlink.modules.night_light.syscommand", side_effect=fake_syscommand):
        addon.start_control(["night_light"], "OFF")
        assert addon.inhibit_cookie == 99
