"""Update LNXlink directly remotely"""
import logging
import os
import sys
import time

import requests

from lnxlink.modules.scripts.helpers import syscommand

logger = logging.getLogger("lnxlink")


class Addon:
    """Addon module"""

    def __init__(self, lnxlink):
        """Setup addon"""
        self.name = "LNXlink update"
        self.lnxlink = lnxlink
        self.last_time = 0
        self.update_interval = 86400  # Check for updates every 24 hours
        installed_sha = self._installed_sha()
        self.message = {
            "installed_version": installed_sha,
            "latest_version": installed_sha,
            "release_summary": "",
            "release_url": "https://github.com/grigorii-horos/lnxlink/commits/master",
        }

    def exposed_controls(self):
        """Exposes to home assistant"""
        image_url = (
            "https://raw.githubusercontent.com/bkbilly/lnxlink/6d844af/images/logo.png"
        )
        return {
            "Update": {
                "type": "update",
                "title": "LNXlink",
                "icon": "mdi:update",
                "entity_category": "diagnostic",
                "entity_picture": image_url,
                "install": "install",
            },
        }

    def get_info(self, force_update=False):
        """Gather information from the system"""
        cur_time = time.time()
        if force_update or cur_time - self.last_time > self.update_interval:
            self._latest_version()
            self.last_time = cur_time

        return self.message

    @staticmethod
    def _sha_cache_path():
        return os.path.expanduser("~/.cache/lnxlink-installed-sha")

    def _installed_sha(self):
        """Returns installed SHA: from version string for edit, from cache file for pipx"""
        version = self.lnxlink.version
        if "+edit-" in version:
            return version.split("-")[-1]
        try:
            with open(self._sha_cache_path(), encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return version

    def _save_installed_sha(self, sha):
        try:
            with open(self._sha_cache_path(), "w", encoding="utf-8") as f:
                f.write(sha)
        except OSError as err:
            logger.error(err)

    def _latest_version(self):
        """Gets the latest commit SHA from the fork"""
        url = "https://api.github.com/repos/grigorii-horos/lnxlink/commits/master"
        try:
            resp = requests.get(url=url, timeout=5).json()
            self.message["latest_version"] = resp["sha"][:7]
            self.message["release_summary"] = resp["commit"]["message"].splitlines()[0]
            self.message["release_url"] = resp["html_url"]
        except Exception as err:
            logger.error(err)

    def start_control(self, topic, data):
        """Control system"""
        method = self.lnxlink.install_method
        if method == "edit":
            syscommand(f"git -C {self.lnxlink.path} pull", timeout=15)
            syscommand(
                f"{sys.executable} -m pip install -e {self.lnxlink.path}", timeout=120
            )
        elif method == "pipx":
            syscommand(
                "pipx install --force git+https://github.com/grigorii-horos/lnxlink.git",
                timeout=120,
            )
            latest = self.message.get("latest_version", "")
            if latest:
                self._save_installed_sha(latest)
        elif method == "flatpak":
            syscommand("flatpak update -y io.github.bkbilly.lnxlink", timeout=120)
        elif method == "snap":
            syscommand("snap refresh lnxlink", timeout=120)
        elif method == "aur":
            _, _, yay = syscommand("which yay", ignore_errors=True)
            _, _, paru = syscommand("which paru", ignore_errors=True)
            if yay == 0:
                syscommand("yay -Syu --noconfirm python-lnxlink", timeout=120)
            elif paru == 0:
                syscommand("paru -Syu --noconfirm python-lnxlink", timeout=120)
            else:
                logger.warning("No AUR helper found (yay or paru)")
                return
        elif method in ("pip", "system"):
            syscommand(f"{sys.executable} -m pip install -U lnxlink", timeout=120)
        else:
            logger.warning("Update not supported for install method: %s", method)
            return
        self.lnxlink.restart_script()
