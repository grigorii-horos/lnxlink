"""Tests for the Do Not Disturb (DND) module."""
# pylint: disable=missing-class-docstring,missing-function-docstring

from unittest.mock import MagicMock, patch

from lnxlink.modules import dnd


class FakeLnxlink:
    def __init__(self, settings=None):
        self.config = {"settings": {"dnd": settings or {}}}
        self.run_module_calls = []

    def add_settings(self, name, default):
        pass

    def run_module(self, topic, data, force_update=False):
        self.run_module_calls.append((topic, data, force_update))


def test_dnd_exposed_controls():
    with patch("lnxlink.modules.dnd.open_dbus_connection", side_effect=Exception("no dbus")):
        lnxlink = FakeLnxlink()
        addon = dnd.Addon(lnxlink)
        controls = addon.exposed_controls()
        assert "Do Not Disturb" in controls
        assert controls["Do Not Disturb"]["type"] == "switch"


def test_dnd_get_info_dbus_on():
    fake_conn = MagicMock()
    fake_reply = MagicMock()
    fake_reply.body = [(None, True)]
    fake_conn.send_and_get_reply.return_value = fake_reply

    with patch("lnxlink.modules.dnd.open_dbus_connection", return_value=fake_conn):
        lnxlink = FakeLnxlink()
        addon = dnd.Addon(lnxlink)
        info = addon.get_info()
        assert info["status"] == "ON"
        assert info["attributes"]["inhibited"] is True
        assert info["attributes"]["backend"] == "freedesktop_dbus"


def test_dnd_get_info_dbus_off():
    fake_conn = MagicMock()
    fake_reply = MagicMock()
    fake_reply.body = [(None, False)]
    fake_conn.send_and_get_reply.return_value = fake_reply

    with patch("lnxlink.modules.dnd.open_dbus_connection", return_value=fake_conn):
        lnxlink = FakeLnxlink()
        addon = dnd.Addon(lnxlink)
        info = addon.get_info()
        assert info["status"] == "OFF"
        assert info["attributes"]["inhibited"] is False


def test_dnd_start_control_inhibit_and_publish():
    fake_conn = MagicMock()
    fake_reply = MagicMock()
    fake_reply.body = [42]
    fake_conn.send_and_get_reply.return_value = fake_reply

    with patch("lnxlink.modules.dnd.open_dbus_connection", return_value=fake_conn), \
         patch("lnxlink.modules.dnd.which", return_value=None):
        lnxlink = FakeLnxlink()
        addon = dnd.Addon(lnxlink)
        addon.start_control(["dnd"], "ON")
        assert addon.inhibit_cookie == 42
        assert len(lnxlink.run_module_calls) == 1
        assert lnxlink.run_module_calls[0][0] == "Do Not Disturb"


def test_dnd_start_control_uninhibit():
    fake_conn = MagicMock()
    with patch("lnxlink.modules.dnd.open_dbus_connection", return_value=fake_conn), \
         patch("lnxlink.modules.dnd.which", return_value=None):
        lnxlink = FakeLnxlink()
        addon = dnd.Addon(lnxlink)
        addon.inhibit_cookie = 42
        addon.start_control(["dnd"], "OFF")
        assert addon.inhibit_cookie is None
        assert fake_conn.send_message.called
