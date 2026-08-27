"""Tests for the Uptime and Boot Time module."""
# pylint: disable=missing-class-docstring,missing-function-docstring

from unittest.mock import patch

from lnxlink.modules import uptime_boot_time


class FakeLnxlink:
    def __init__(self):
        self.config = {"settings": {}}


def test_uptime_boot_time_exposed_controls():
    lnxlink = FakeLnxlink()
    addon = uptime_boot_time.Addon(lnxlink)
    controls = addon.exposed_controls()
    assert "Uptime" in controls
    assert "Boot Time" in controls
    assert controls["Uptime"]["type"] == "sensor"
    assert controls["Uptime"]["device_class"] == "duration"
    assert controls["Boot Time"]["device_class"] == "timestamp"


def test_uptime_boot_time_get_info():
    lnxlink = FakeLnxlink()
    addon = uptime_boot_time.Addon(lnxlink)

    with patch("psutil.boot_time", return_value=1700000000.0), \
         patch("time.time", return_value=1700090065.0):
        info = addon.get_info()
        assert info["uptime_seconds"] == 90065
        assert info["uptime_human"] == "1d 1h 1m 5s"
        assert "T" in info["boot_time"]


def test_format_uptime_seconds_only():
    lnxlink = FakeLnxlink()
    addon = uptime_boot_time.Addon(lnxlink)
    assert addon._format_uptime(45) == "45s"
    assert addon._format_uptime(125) == "2m 5s"
    assert addon._format_uptime(3661) == "1h 1m 1s"
