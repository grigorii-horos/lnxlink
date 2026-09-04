"""Tests for monitor identification in the brightness helper."""
# pylint: disable=missing-class-docstring,missing-function-docstring

from unittest.mock import mock_open, patch

from lnxlink.modules.scripts.monitor_brightness import (
    DDCIPMonitor,
    MonitorBrightness,
    SysfsMonitor,
)

EDID_HEADER = bytes.fromhex("00 FF FF FF FF FF FF 00")


def test_unique_name_uses_edid_serial():
    monitor = DDCIPMonitor("/dev/i2c-14", "AOC", "U34V5C", "1QDQ6HA000243")
    assert monitor.unique_name == "AOC U34V5C 1QDQ6HA000243"


def test_unique_name_survives_bus_renumbering():
    # Ядро призначає номер i2c-шини при завантаженні, і він змінюється.
    # Через це entity_id у Home Assistant "їде" і автоматизації тихо ламаються.
    before = DDCIPMonitor("/dev/i2c-14", "AOC", "U34V5C", "1QDQ6HA000243")
    after = DDCIPMonitor("/dev/i2c-4", "AOC", "U34V5C", "1QDQ6HA000243")
    assert before.unique_name == after.unique_name


def test_unique_name_falls_back_to_bus_when_serial_missing():
    for serial in (None, "", "Unknown"):
        monitor = DDCIPMonitor("/dev/i2c-4", "GSM", "LG HDR WFHD", serial)
        assert monitor.unique_name == "GSM LG HDR WFHD i2c-4"


def test_sysfs_monitor_keeps_its_path_identifier():
    with patch.object(SysfsMonitor, "_read_value", return_value=255):
        monitor = SysfsMonitor("/sys/class/backlight/intel_backlight")
        assert monitor.unique_name == "Internal intel_backlight intel_backlight"


def test_list_displays_passes_serial_to_the_monitor():
    edid = EDID_HEADER + bytes(248)
    with patch(
        "lnxlink.modules.scripts.monitor_brightness.glob.glob",
        side_effect=lambda pattern: ["/dev/i2c-14"] if "i2c" in pattern else [],
    ), patch(
        "builtins.open", mock_open(read_data=edid)
    ), patch(
        "lnxlink.modules.scripts.monitor_brightness.fcntl.ioctl"
    ), patch.object(
        DDCIPMonitor, "parse_edid", return_value=("AOC", "U34V5C", "1QDQ6HA000243")
    ):
        monitors, _ = MonitorBrightness.list_displays()

    assert [m.unique_name for m in monitors] == ["AOC U34V5C 1QDQ6HA000243"]
