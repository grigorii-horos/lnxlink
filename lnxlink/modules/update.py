"""Update LNXlink directly remotely"""
import importlib.metadata
import json
import logging
import os
import sys
import time

import requests

from lnxlink.modules.scripts.helpers import find_uv_bin, syscommand

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
            "in_progress": False,
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
            self.message["installed_version"] = self._installed_sha()
            self._latest_version()
            self.last_time = cur_time

        return self.message

    @staticmethod
    def _sha_cache_path():
        return os.path.expanduser("~/.cache/lnxlink-installed-sha")

    def _installed_sha(self):
        """Returns installed commit SHA or fallback version"""
        version = getattr(self.lnxlink, "version", "")
        if "+edit-" in version:
            return version.split("-")[-1]
        if "+git-" in version:
            return version.split("-")[-1]

        # 1. From direct_url.json (PEP 610) when installed via pip/uv/pipx
        try:
            pkg_name = (
                __package__.split(".", maxsplit=1)[0] if __package__ else "lnxlink"
            )
            dist = importlib.metadata.distribution(pkg_name)
            raw = dist.read_text("direct_url.json")
            if raw:
                data = json.loads(raw)
                commit_id = data.get("vcs_info", {}).get("commit_id")
                if commit_id:
                    return commit_id[:7]
                url = data.get("url", "")
                if url.startswith("file://"):
                    local_dir = url[7:]
                    git_hash, _, rc = syscommand(
                        f"git -c safe.directory=* -C {local_dir} rev-parse --short HEAD",
                        ignore_errors=True,
                    )
                    if rc == 0 and git_hash.strip():
                        return git_hash.strip()
        except Exception:
            pass

        # 2. From git repository at lnxlink path
        if hasattr(self.lnxlink, "path") and self.lnxlink.path:
            git_hash, _, rc = syscommand(
                f"git -c safe.directory=* -C {self.lnxlink.path} rev-parse --short HEAD",
                ignore_errors=True,
            )
            if rc == 0 and git_hash.strip():
                return git_hash.strip()

        # 3. From saved cache file
        try:
            with open(self._sha_cache_path(), encoding="utf-8") as f:
                cached = f.read().strip()
                if cached:
                    return cached
        except OSError:
            pass

        return version

    def _save_installed_sha(self, sha):
        if not sha:
            return
        try:
            cache_path = self._sha_cache_path()
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(sha.strip())
        except OSError as err:
            logger.error("Failed to save installed SHA to cache: %s", err)

    def _latest_version(self):
        """Gets the latest commit SHA from the fork"""
        url = "https://api.github.com/repos/grigorii-horos/lnxlink/commits/master"
        try:
            resp = requests.get(url=url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                self.message["latest_version"] = data["sha"][:7]
                self.message["release_summary"] = data["commit"]["message"].splitlines()[0]
                self.message["release_url"] = data["html_url"]
            else:
                logger.warning("GitHub API returned status code %s", resp.status_code)
        except Exception as err:
            logger.error("Error fetching latest version from GitHub: %s", err)

    def start_control(self, topic, data):
        """Control system"""
        self.message["in_progress"] = True
        self.lnxlink.run_module(self.name, self.get_info)
        try:
            if self._run_update():
                self.lnxlink.restart_script()
        finally:
            self.message["in_progress"] = False
            self.lnxlink.run_module(self.name, self.get_info)

    def _run_update(self):
        """Run the appropriate update command based on install method"""
        method = self.lnxlink.install_method
        if "_edit" in method:
            return self._update_edit(method)
        if method == "pipx":
            _, _, returncode = syscommand(
                "pipx install --force git+https://github.com/grigorii-horos/lnxlink.git",
                timeout=120,
            )
        elif method == "uv":
            uv_bin = find_uv_bin() or "uv"
            _, _, returncode = syscommand(
                f"{uv_bin} tool install --force"
                " git+https://github.com/grigorii-horos/lnxlink.git",
                timeout=120,
            )
        elif method == "flatpak":
            _, _, returncode = syscommand(
                "flatpak update -y io.github.bkbilly.lnxlink", timeout=120
            )
        elif method == "aur":
            return self._update_aur()
        elif method in ("pip", "system"):
            _, _, returncode = syscommand(
                f"{sys.executable} -m pip install -U"
                " git+https://github.com/grigorii-horos/lnxlink.git",
                timeout=120,
            )
        else:
            logger.warning("Update not supported for install method: %s", method)
            return False

        if returncode == 0:
            latest = self.message.get("latest_version", "")
            if latest:
                self._save_installed_sha(latest)
                self.message["installed_version"] = latest
        return returncode == 0

    def _update_edit(self, method):
        """Handle update for editable installations"""
        _, _, returncode = syscommand(
            f"git -c safe.directory=* -C {self.lnxlink.path} pull", timeout=15
        )
        if returncode != 0:
            return False
        if "pip" in method:
            _, _, returncode = syscommand(
                f"{sys.executable} -m pip install -e {self.lnxlink.path}",
                timeout=120,
            )
        elif "uv" in method:
            uv_bin = find_uv_bin() or "uv"
            _, _, returncode = syscommand(
                f"{uv_bin} pip install --python {sys.executable} -e {self.lnxlink.path}",
                timeout=120,
            )
        else:
            logger.warning("Update not supported for install method: %s", method)
            return False
        if returncode == 0:
            latest = self.message.get("latest_version", "")
            if latest:
                self._save_installed_sha(latest)
                self.message["installed_version"] = latest
        return returncode == 0

    def _update_aur(self):
        """Handle update for AUR installations"""
        _, _, yay = syscommand("which yay", ignore_errors=True)
        _, _, paru = syscommand("which paru", ignore_errors=True)
        if yay == 0:
            _, _, returncode = syscommand(
                "yay -Syu --noconfirm python-lnxlink", timeout=120
            )
        elif paru == 0:
            _, _, returncode = syscommand(
                "paru -Syu --noconfirm python-lnxlink", timeout=120
            )
        else:
            logger.warning("No AUR helper found (yay or paru)")
            return False
        if returncode == 0:
            latest = self.message.get("latest_version", "")
            if latest:
                self._save_installed_sha(latest)
                self.message["installed_version"] = latest
        return returncode == 0
