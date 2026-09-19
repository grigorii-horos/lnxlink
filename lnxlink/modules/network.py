"""Monitor real-time upload and download speeds per network interface"""
from datetime import datetime

import psutil


class Addon:
    """Addon module"""

    def __init__(self, lnxlink):
        """Setup addon"""
        self.name = "Network"
        self.lnxlink = lnxlink
        self.lnxlink.add_settings(
            "network",
            {
                "include": [],
                "exclude": [],
            },
        )
        self.time_old = datetime.now()
        self.interfaces = self._get_interfaces()
        self.old_counters = self._read_counters(self.interfaces)

    def exposed_controls(self):
        """Exposes to home assistant"""
        discovery_info = {}
        for interface in self.interfaces:
            discovery_info[f"Network Upload {interface}"] = {
                "type": "sensor",
                "icon": "mdi:access-point-network",
                "unit": "Mbit/s",
                "state_class": "measurement",
                "device_class": "data_rate",
                "value_template": f"{{{{ value_json.get('{interface}', {{}}).get('upload') }}}}",
            }
            discovery_info[f"Network Download {interface}"] = {
                "type": "sensor",
                "icon": "mdi:access-point-network",
                "unit": "Mbit/s",
                "state_class": "measurement",
                "device_class": "data_rate",
                "value_template": f"{{{{ value_json.get('{interface}', {{}}).get('download') }}}}",
            }
        return discovery_info

    def get_info(self):
        """Returns Mbps for each network interface"""
        interfaces = self._get_interfaces()
        if set(interfaces) != set(self.interfaces):
            self.interfaces = interfaces
            self.lnxlink.setup_discovery("network")

        time_new = datetime.now()
        time_diff = (time_new - self.time_old).total_seconds()
        self.time_old = time_new

        new_counters = self._read_counters(self.interfaces)
        results = {}
        for interface in self.interfaces:
            new_recv, new_sent = new_counters.get(interface, (0, 0))
            old_recv, old_sent = self.old_counters.get(interface, (new_recv, new_sent))

            if time_diff == 0:
                results[interface] = {"upload": 0, "download": 0}
                continue

            recv_speed = max(
                0, round((new_recv - old_recv) * 8 / time_diff / 1024 / 1024, 2)
            )
            sent_speed = max(
                0, round((new_sent - old_sent) * 8 / time_diff / 1024 / 1024, 2)
            )
            results[interface] = {
                "upload": sent_speed,
                "download": recv_speed,
            }
        self.old_counters = new_counters

        return results

    def _read_counters(self, interfaces):
        """Read bytes_recv/bytes_sent for the given interfaces"""
        counters = psutil.net_io_counters(pernic=True)
        return {
            interface: (counters[interface].bytes_recv, counters[interface].bytes_sent)
            for interface in interfaces
            if interface in counters
        }

    def _get_interfaces(self):
        """Get a list of all network interfaces, applying include/exclude filters"""
        includes = self.lnxlink.config["settings"].get("network", {}).get("include", [])
        excludes = self.lnxlink.config["settings"].get("network", {}).get("exclude", [])

        interfaces = []
        for interface in psutil.net_io_counters(pernic=True):
            if includes:
                if not any(interface.startswith(x) for x in includes):
                    continue
            if excludes:
                if any(interface.startswith(x) for x in excludes):
                    continue
            interfaces.append(interface)
        return interfaces
