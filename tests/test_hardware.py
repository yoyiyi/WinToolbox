from __future__ import annotations

import unittest

from wintoolbox.services.hardware import parse_disk_json, parse_hardware_json


class HardwareParseTests(unittest.TestCase):
    def test_parse_hardware_payload(self) -> None:
        info = parse_hardware_json(
            {
                "hostname": "TEST-PC",
                "manufacturer": "ASUS",
                "model": "ROG",
                "os_name": "Windows 11",
                "os_version": "10.0",
                "os_build": "26100",
                "cpu_name": "Test CPU",
                "cpu_cores": 8,
                "cpu_threads": 16,
                "cpu_max_mhz": 4000,
                "cpu_socket": "AM5",
                "board_manufacturer": "ASUS",
                "board_product": "B650",
                "bios_vendor": "AMI",
                "bios_version": "1.2.3",
                "bios_date": "2026-01-01",
                "total_memory": 32 * 1024**3,
                "gpus": [{"name": "Test GPU", "driver": "1.0", "vram": 8 * 1024**3}],
                "modules": [
                    {
                        "slot": "DIMM1",
                        "capacity": 16 * 1024**3,
                        "speed": 6000,
                        "manufacturer": "Vendor",
                        "part": "PART",
                        "smbios": 34,
                    }
                ],
                "network": [
                    {
                        "name": "Ethernet",
                        "mac": "AA:BB:CC:DD:EE:FF",
                        "speed": 1_000_000_000,
                        "enabled": True,
                        "status": 2,
                        "ip": "192.168.1.2",
                    }
                ],
            }
        )
        self.assertEqual(info.hostname, "TEST-PC")
        self.assertEqual(info.cpu_threads, 16)
        self.assertEqual(info.modules[0].memory_type, "DDR5")
        self.assertEqual(info.modules[0].speed_mhz, 6000)
        self.assertEqual(info.gpus[0].vram, 8 * 1024**3)
        self.assertTrue(info.network[0].connected)
        self.assertEqual(info.network[0].ip_addresses, "192.168.1.2")

    def test_parse_monitor_payload(self) -> None:
        info = parse_hardware_json(
            {
                "monitors": [
                    {
                        "name": "Test Monitor",
                        "manufacturer": "DEL",
                        "serial": "ABC123",
                        "year": 2024,
                        "width_cm": 60,
                        "height_cm": 34,
                        "resolution": "3840x2160",
                        "connection": 10,
                        "active": True,
                    }
                ]
            }
        )
        self.assertEqual(len(info.monitors), 1)
        self.assertEqual(info.monitors[0].name, "Test Monitor")
        self.assertEqual(info.monitors[0].manufacturer, "Dell")
        self.assertEqual(info.monitors[0].resolution, "3840x2160")
        self.assertEqual(info.monitors[0].connection, "DisplayPort")
        self.assertAlmostEqual(info.monitors[0].size_inches, 27.2, places=1)
        self.assertTrue(info.monitors[0].active)

    def test_parse_disk_payload(self) -> None:
        report = parse_disk_json(
            {
                "disks": [
                    {
                        "name": "Test SSD",
                        "size": 1000 * 1024**3,
                        "media": "SSD",
                        "bus": "NVMe",
                        "health": "Healthy",
                        "serial": "SN123",
                        "firmware": "FW1",
                        "temperature": 42,
                        "wear": 3,
                        "power_on_hours": 1200,
                        "read_errors": 0,
                        "write_errors": 0,
                        "volumes": "C:",
                    }
                ],
                "volumes": [
                    {
                        "letter": "C:",
                        "label": "System",
                        "filesystem": "NTFS",
                        "total": 1000 * 1024**3,
                        "free": 600 * 1024**3,
                        "health": "Healthy",
                    }
                ],
            }
        )
        self.assertEqual(len(report.disks), 1)
        self.assertEqual(report.disks[0].health, "健康")
        self.assertEqual(report.disks[0].temperature, 42)
        self.assertEqual(report.disks[0].volumes, ["C:"])
        self.assertEqual(report.volumes[0].health, "健康")
        self.assertEqual(report.volumes[0].free, 600 * 1024**3)

    def test_single_item_lists_are_normalized(self) -> None:
        report = parse_disk_json(
            {"disks": {"name": "Disk", "health": "Warning"}, "volumes": None}
        )
        self.assertEqual(len(report.disks), 1)
        self.assertEqual(report.disks[0].health, "警告")
        self.assertEqual(report.volumes, [])


if __name__ == "__main__":
    unittest.main()
