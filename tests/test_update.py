"""Tests for the update module."""
# pylint: disable=missing-class-docstring,missing-function-docstring

import json
from unittest.mock import MagicMock, patch

from lnxlink.modules import update


class FakeLnxlink:
    def __init__(self, version="2026.8.0", path="/tmp/fake_lnxlink", install_method="pipx"):
        self.version = version
        self.path = path
        self.install_method = install_method
        self.restart_calls = 0

    def restart_script(self):
        self.restart_calls += 1

    def run_module(self, name, func):
        pass


def test_installed_sha_from_edit_version():
    lnxlink = FakeLnxlink(version="2026.8.0+edit-375aa20")
    addon = update.Addon(lnxlink)
    assert addon._installed_sha() == "375aa20"


def test_installed_sha_from_direct_url_git():
    lnxlink = FakeLnxlink(version="2026.8.0")
    fake_dist = MagicMock()
    fake_dist.read_text.return_value = json.dumps({
        "url": "https://github.com/grigorii-horos/lnxlink.git",
        "vcs_info": {"vcs": "git", "commit_id": "375aa20413ddbc47a4591b1654c05ad7629420de"}
    })

    with patch("importlib.metadata.distribution", return_value=fake_dist):
        addon = update.Addon(lnxlink)
        assert addon._installed_sha() == "375aa20"


def test_installed_sha_from_cache_file(tmp_path):
    lnxlink = FakeLnxlink(version="2026.8.0")
    cache_file = tmp_path / "lnxlink-installed-sha"
    cache_file.write_text("e8b9054")

    with patch("importlib.metadata.distribution", side_effect=Exception("not found")), \
         patch.object(update.Addon, "_sha_cache_path", return_value=str(cache_file)):
        addon = update.Addon(lnxlink)
        assert addon._installed_sha() == "e8b9054"


def test_save_installed_sha_creates_directory(tmp_path):
    lnxlink = FakeLnxlink(version="2026.8.0")
    cache_file = tmp_path / "sub" / "dir" / "lnxlink-installed-sha"

    with patch.object(update.Addon, "_sha_cache_path", return_value=str(cache_file)):
        addon = update.Addon(lnxlink)
        addon._save_installed_sha("375aa20")
        assert cache_file.exists()
        assert cache_file.read_text() == "375aa20"


def test_latest_version_fetches_from_github():
    lnxlink = FakeLnxlink(version="2026.8.0")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "sha": "375aa20413ddbc47a4591b1654c05ad7629420de",
        "commit": {"message": "Merge remote-tracking branch 'upstream/master'\n\nDetails"},
        "html_url": "https://github.com/grigorii-horos/lnxlink/commit/375aa20",
    }

    with patch("requests.get", return_value=fake_response):
        addon = update.Addon(lnxlink)
        addon._latest_version()
        assert addon.message["latest_version"] == "375aa20"
        assert addon.message["release_summary"] == "Merge remote-tracking branch 'upstream/master'"
