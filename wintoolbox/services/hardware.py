"""硬件信息与磁盘健康查询。

通过 PowerShell CIM 读取详细的 CPU/主板/BIOS/显卡/内存/网卡/物理磁盘信息；
PowerShell/CIM 不可用时降级为注册表和系统 API 的基础信息。
"""

from __future__ import annotations

import ctypes
import json
import socket
import winreg
from datetime import datetime
from typing import Any

from ..models import (
    DiskHealthReport,
    GPUInfo,
    HardwareInfo,
    MemoryModule,
    MonitorInfo,
    NetworkAdapter,
    PhysicalDisk,
    VolumeHealth,
)
from ..utils import get_logger, human_bytes, run_powershell
from .largefiles import list_drives
from .system import SystemService

LOGGER = get_logger("hardware")

MEMORY_TYPE_NAMES = {
    20: "DDR",
    21: "DDR2",
    22: "DDR2 FB-DIMM",
    24: "DDR3",
    26: "DDR4",
    27: "LPDDR",
    28: "LPDDR2",
    29: "LPDDR3",
    30: "LPDDR4",
    34: "DDR5",
    35: "LPDDR5",
    36: "HBM",
    37: "HBM2",
    38: "GDDR5",
    39: "GDDR6",
}

PNP_MANUFACTURERS = {
    "AOC": "AOC",
    "PHL": "Philips",
    "DEL": "Dell",
    "SAM": "Samsung",
    "LEN": "Lenovo",
    "HWP": "HP",
    "BNQ": "BenQ",
    "ACR": "Acer",
    "ASU": "ASUS",
    "MSI": "MSI",
    "GSM": "LG",
    "VSC": "ViewSonic",
    "EIZ": "EIZO",
    "NEC": "NEC",
    "SII": "Seiko",
    "APP": "Apple",
    "IBM": "IBM",
    "HKC": "HKC",
    "SKY": "Skyworth",
    "TCL": "TCL",
    "HAI": "Hisense",
    "XIA": "Xiaomi",
}

CONNECTION_NAMES = {
    -1: "其他",
    0: "VGA",
    1: "DVI",
    2: "HDMI",
    3: "LVDS",
    4: "DVI-D",
    5: "HDMI",
    6: "SDI",
    8: "DisplayPort",
    9: "eDP",
    10: "DisplayPort",
    11: "UDI",
    12: "SDTV",
    13: "Miracast",
    14: "间接有线",
    15: "虚拟显示",
}

NETWORK_STATUS = {
    0: "已断开",
    1: "正在连接",
    2: "已连接",
    3: "正在断开",
    4: "硬件不存在",
    5: "硬件已禁用",
    6: "硬件故障",
    7: "媒体断开",
    8: "正在认证",
    9: "认证成功",
    10: "认证失败",
    11: "地址无效",
    12: "需要凭据",
}

HEALTH_NAMES = {
    "healthy": "健康",
    "warning": "警告",
    "unhealthy": "异常",
    "unknown": "未知",
    "ok": "正常",
    "degraded": "降级",
    "stressed": "压力",
    "predictivefailure": "预测故障",
    "error": "错误",
}

HARDWARE_SCRIPT = r"""
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$board = Get-CimInstance Win32_BaseBoard | Select-Object -First 1
$bios = Get-CimInstance Win32_BIOS | Select-Object -First 1
$cs = Get-CimInstance Win32_ComputerSystem | Select-Object -First 1
$os = Get-CimInstance Win32_OperatingSystem | Select-Object -First 1
$gpus = @(Get-CimInstance Win32_VideoController | Sort-Object Name | ForEach-Object {
    [pscustomobject]@{
        name = $_.Name
        driver = $_.DriverVersion
        vram = $_.AdapterRAM
        processor = $_.VideoProcessor
    }
})
$modules = @(Get-CimInstance Win32_PhysicalMemory | Sort-Object DeviceLocator | ForEach-Object {
    [pscustomobject]@{
        slot = $_.DeviceLocator
        bank = $_.BankLabel
        capacity = $_.Capacity
        speed = $_.Speed
        manufacturer = $_.Manufacturer
        part = $_.PartNumber
        smbios = $_.SMBIOSMemoryType
    }
})
function Decode-Id($values) {
    if ($null -eq $values) { return "" }
    return (-join ($values | Where-Object { $_ -gt 0 } | ForEach-Object { [char]$_ }))
}
$monitorIds = @(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID)
$monitorBasic = @(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorBasicDisplayParams)
$monitorConn = @(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorConnectionParams)
$sourceModes = @(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorListedSupportedSourceModes)
$monitors = @(foreach ($m in $monitorIds) {
    $b = $monitorBasic | Where-Object { $_.InstanceName -eq $m.InstanceName } | Select-Object -First 1
    $c = $monitorConn | Where-Object { $_.InstanceName -eq $m.InstanceName } | Select-Object -First 1
    $sm = $sourceModes | Where-Object { $_.InstanceName -eq $m.InstanceName } | Select-Object -First 1
    $mode = @($sm.MonitorSourceModes) | Sort-Object { [int64]$_.HorizontalActivePixels * [int64]$_.VerticalActivePixels } -Descending | Select-Object -First 1
    [pscustomobject]@{
        name = Decode-Id $m.UserFriendlyName
        manufacturer = Decode-Id $m.ManufacturerName
        serial = Decode-Id $m.SerialNumberID
        year = $m.YearOfManufacture
        width_cm = $b.MaxHorizontalImageSize
        height_cm = $b.MaxVerticalImageSize
        resolution = if ($mode) { "$($mode.HorizontalActivePixels)x$($mode.VerticalActivePixels)" } else { "" }
        connection = $c.VideoOutputTechnology
        active = if ($null -ne $b) { [bool]$b.Active } else { $false }
    }
})
$sounds = @(Get-CimInstance Win32_SoundDevice | ForEach-Object { $_.Name } | Where-Object { $_ } | Select-Object -Unique)
$npus = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'NPU|AI Boost|Neural' } | ForEach-Object { $_.Name } | Select-Object -Unique)
$cfg = @(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled=True")
$nets = @(Get-CimInstance Win32_NetworkAdapter -Filter "PhysicalAdapter=True" | ForEach-Object {
    $n = $_
    $c = $cfg | Where-Object { $_.Index -eq $n.Index } | Select-Object -First 1
    [pscustomobject]@{
        name = $n.Name
        description = $n.Description
        mac = $n.MACAddress
        speed = $n.Speed
        enabled = $n.NetEnabled
        status = $n.NetConnectionStatus
        ip = ($c.IPAddress -join ", ")
    }
})
[pscustomobject]@{
    hostname = $cs.DNSHostName
    manufacturer = $cs.Manufacturer
    model = $cs.Model
    total_memory = $cs.TotalPhysicalMemory
    os_name = $os.Caption
    os_version = $os.Version
    os_build = $os.BuildNumber
    cpu_name = $cpu.Name
    cpu_cores = $cpu.NumberOfCores
    cpu_threads = $cpu.NumberOfLogicalProcessors
    cpu_max_mhz = $cpu.MaxClockSpeed
    cpu_socket = $cpu.SocketDesignation
    board_manufacturer = $board.Manufacturer
    board_product = $board.Product
    board_version = $board.Version
    bios_vendor = $bios.Manufacturer
    bios_version = $bios.SMBIOSBIOSVersion
    bios_date = if ($bios.ReleaseDate) { $bios.ReleaseDate.ToString("yyyy-MM-dd") } else { "" }
    gpus = $gpus
    modules = $modules
    monitors = $monitors
    sounds = $sounds
    npus = $npus
    network = $nets
} | ConvertTo-Json -Depth 6 -Compress
"""

DISK_SCRIPT = r"""
$disks = @()
foreach ($d in @(Get-PhysicalDisk)) {
    $r = $null
    try { $r = $d | Get-StorageReliabilityCounter -ErrorAction Stop } catch { }
    $disk = $null
    try { $disk = $d | Get-Disk -ErrorAction Stop } catch { }
    $letters = @()
    if ($disk) {
        try {
            $letters = @($disk | Get-Partition | Get-Volume | Where-Object { $_.DriveLetter } | ForEach-Object { "$($_.DriveLetter):" })
        } catch { }
    }
    $disks += [pscustomobject]@{
        name = $d.FriendlyName
        size = $d.Size
        media = [string]$d.MediaType
        bus = [string]$d.BusType
        health = [string]$d.HealthStatus
        operational = ($d.OperationalStatus -join ",")
        serial = $d.SerialNumber
        firmware = $d.FirmwareVersion
        device_id = $d.DeviceId
        temperature = $r.Temperature
        wear = $r.Wear
        power_on_hours = $r.PowerOnHours
        read_errors = $r.ReadErrorsTotal
        write_errors = $r.WriteErrorsTotal
        volumes = ($letters -join ", ")
    }
}
$volumes = @(Get-Volume | Where-Object { $_.DriveLetter } | Sort-Object DriveLetter | ForEach-Object {
    [pscustomobject]@{
        letter = "$($_.DriveLetter):"
        label = $_.FileSystemLabel
        filesystem = $_.FileSystem
        total = $_.Size
        free = $_.SizeRemaining
        health = [string]$_.HealthStatus
    }
})
[pscustomobject]@{ disks = $disks; volumes = $volumes } | ConvertTo-Json -Depth 5 -Compress
"""


class _DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.c_ushort),
        ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort),
        ("dmDriverExtra", ctypes.c_ushort),
        ("dmFields", ctypes.c_ulong),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", ctypes.c_ulong),
        ("dmDisplayFixedOutput", ctypes.c_ulong),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", ctypes.c_ulong),
        ("dmPelsWidth", ctypes.c_ulong),
        ("dmPelsHeight", ctypes.c_ulong),
        ("dmDisplayFlags", ctypes.c_ulong),
        ("dmDisplayFrequency", ctypes.c_ulong),
        ("dmICMMethod", ctypes.c_ulong),
        ("dmICMIntent", ctypes.c_ulong),
        ("dmMediaType", ctypes.c_ulong),
        ("dmDitherType", ctypes.c_ulong),
        ("dmReserved1", ctypes.c_ulong),
        ("dmReserved2", ctypes.c_ulong),
        ("dmPanningWidth", ctypes.c_ulong),
        ("dmPanningHeight", ctypes.c_ulong),
    ]


def display_session_info() -> dict[str, Any]:
    """读取显示器/会话信息；无显示器时返回 0，不依赖桌面窗口。"""
    try:
        user32 = ctypes.windll.user32
        count = int(user32.GetSystemMetrics(80))
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
        refresh = 0
        try:
            mode = _DEVMODEW()
            mode.dmSize = ctypes.sizeof(_DEVMODEW)
            user32.EnumDisplaySettingsW.argtypes = [
                ctypes.c_wchar_p,
                ctypes.c_ulong,
                ctypes.POINTER(_DEVMODEW),
            ]
            if user32.EnumDisplaySettingsW(None, 0xFFFFFFFF, ctypes.byref(mode)):
                width = int(mode.dmPelsWidth) or width
                height = int(mode.dmPelsHeight) or height
                refresh = int(mode.dmDisplayFrequency)
        except (AttributeError, OSError):
            pass
        remote = bool(user32.GetSystemMetrics(0x1000))
        return {
            "count": max(0, count),
            "width": max(0, width),
            "height": max(0, height),
            "refresh": max(0, refresh),
            "remote": remote,
        }
    except (AttributeError, OSError):
        return {
            "count": 0,
            "width": 0,
            "height": 0,
            "refresh": 0,
            "remote": False,
        }


def _apply_display_info(info: HardwareInfo) -> None:
    display = display_session_info()
    info.display_count = max(int(display["count"]), len(info.monitors))
    info.screen_width = int(display["width"])
    info.screen_height = int(display["height"])
    info.screen_refresh = int(display["refresh"])
    info.remote_session = bool(display["remote"])


def _json_payload(text: str) -> Any:
    text = (text or "").strip()
    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not starts:
        raise ValueError("PowerShell 未返回 JSON 数据")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    if end <= start:
        raise ValueError("PowerShell 返回的 JSON 不完整")
    return json.loads(text[start : end + 1])


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _health_name(value: Any) -> str:
    text = _text(value)
    return HEALTH_NAMES.get(text.casefold(), text or "未知")


def _registry_gpu_vram() -> dict[str, int]:
    """Win32_VideoController.AdapterRAM 是 32 位，读取注册表补全大显存。"""
    result: dict[str, int] = {}
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}",
        ) as key:
            count = winreg.QueryInfoKey(key)[0]
            for index in range(count):
                try:
                    name = winreg.EnumKey(key, index)
                    if not name.isdigit():
                        continue
                    with winreg.OpenKey(key, name) as sub:
                        try:
                            driver_desc = _text(
                                winreg.QueryValueEx(sub, "DriverDesc")[0]
                            )
                        except OSError:
                            continue
                        if not driver_desc:
                            continue
                        for value_name in (
                            "HardwareInformation.qwMemorySize",
                            "HardwareInformation.MemorySize",
                        ):
                            try:
                                result[driver_desc.casefold()] = max(
                                    0, int(winreg.QueryValueEx(sub, value_name)[0])
                                )
                                break
                            except (OSError, TypeError, ValueError):
                                continue
                except OSError:
                    continue
    except OSError:
        pass
    return result


def _memory_type(value: Any) -> str:
    code = _int(value, -1)
    return MEMORY_TYPE_NAMES.get(code, _text(value) or "未知")


def parse_hardware_json(payload: dict[str, Any]) -> HardwareInfo:
    gpus = []
    for item in _as_list(payload.get("gpus")):
        if not isinstance(item, dict):
            continue
        gpus.append(
            GPUInfo(
                name=_text(item.get("name")),
                driver=_text(item.get("driver")),
                vram=max(0, _int(item.get("vram"))),
                processor=_text(item.get("processor")),
            )
        )
    monitors = []
    for item in _as_list(payload.get("monitors")):
        if not isinstance(item, dict):
            continue
        width_cm = max(0, _int(item.get("width_cm")))
        height_cm = max(0, _int(item.get("height_cm")))
        size_inches = (
            round((width_cm**2 + height_cm**2) ** 0.5 / 2.54, 1)
            if width_cm and height_cm
            else 0.0
        )
        manufacturer_code = _text(item.get("manufacturer"))
        manufacturer = PNP_MANUFACTURERS.get(
            manufacturer_code.upper(), manufacturer_code
        )
        name = _text(item.get("name")) or "未知显示器"
        monitors.append(
            MonitorInfo(
                name=name,
                manufacturer=manufacturer,
                serial=_text(item.get("serial")),
                year=max(0, _int(item.get("year"))),
                width_cm=width_cm,
                height_cm=height_cm,
                size_inches=size_inches,
                resolution=_text(item.get("resolution")),
                connection=CONNECTION_NAMES.get(
                    _int(item.get("connection"), -999), _text(item.get("connection"))
                )
                or "未知",
                active=bool(item.get("active")),
            )
        )
    modules = []
    for item in _as_list(payload.get("modules")):
        if not isinstance(item, dict):
            continue
        modules.append(
            MemoryModule(
                slot=_text(item.get("slot")) or _text(item.get("bank")) or "未知插槽",
                capacity=max(0, _int(item.get("capacity"))),
                speed_mhz=max(0, _int(item.get("speed"))),
                manufacturer=_text(item.get("manufacturer")),
                part_number=_text(item.get("part")),
                memory_type=_memory_type(item.get("smbios")),
            )
        )
    network = []
    for item in _as_list(payload.get("network")):
        if not isinstance(item, dict):
            continue
        speed = _int(item.get("speed"))
        if speed > 10**15:
            speed = 0
        status_code = _int(item.get("status"), -1)
        network.append(
            NetworkAdapter(
                name=_text(item.get("name")),
                description=_text(item.get("description")),
                mac=_text(item.get("mac")),
                speed_bps=max(0, speed),
                connected=bool(item.get("enabled")) and status_code == 2,
                status=NETWORK_STATUS.get(status_code, _text(item.get("status"))) or "未知",
                ip_addresses=_text(item.get("ip")),
            )
        )
    info = HardwareInfo(
        hostname=_text(payload.get("hostname")) or socket.gethostname(),
        manufacturer=_text(payload.get("manufacturer")),
        model=_text(payload.get("model")),
        os_name=_text(payload.get("os_name")),
        os_version=_text(payload.get("os_version")),
        os_build=_text(payload.get("os_build")),
        cpu_name=_text(payload.get("cpu_name")),
        cpu_cores=max(0, _int(payload.get("cpu_cores"))),
        cpu_threads=max(0, _int(payload.get("cpu_threads"))),
        cpu_max_mhz=max(0, _int(payload.get("cpu_max_mhz"))),
        cpu_socket=_text(payload.get("cpu_socket")),
        board_manufacturer=_text(payload.get("board_manufacturer")),
        board_product=_text(payload.get("board_product")),
        board_version=_text(payload.get("board_version")),
        bios_vendor=_text(payload.get("bios_vendor")),
        bios_version=_text(payload.get("bios_version")),
        bios_date=_text(payload.get("bios_date")),
        memory_total=max(0, _int(payload.get("total_memory"))),
        monitors=monitors,
        sound_devices=[_text(value) for value in _as_list(payload.get("sounds")) if _text(value)],
        npu_devices=[_text(value) for value in _as_list(payload.get("npus")) if _text(value)],
        modules=modules,
        gpus=gpus,
        network=network,
    )
    if not info.memory_total:
        info.memory_total = sum(item.capacity for item in modules)
    return info


def parse_disk_json(payload: dict[str, Any]) -> DiskHealthReport:
    disks = []
    for item in _as_list(payload.get("disks")):
        if not isinstance(item, dict):
            continue
        disks.append(
            PhysicalDisk(
                name=_text(item.get("name")) or "未知磁盘",
                size=max(0, _int(item.get("size"))),
                media_type=_text(item.get("media")) or "未知",
                bus_type=_text(item.get("bus")) or "未知",
                health=_health_name(item.get("health")),
                operational=_text(item.get("operational")),
                serial=_text(item.get("serial")),
                firmware=_text(item.get("firmware")),
                device_id=_text(item.get("device_id")),
                temperature=(
                    _int(item.get("temperature")) if item.get("temperature") is not None else None
                ),
                wear=_int(item.get("wear")) if item.get("wear") is not None else None,
                power_on_hours=(
                    _int(item.get("power_on_hours"))
                    if item.get("power_on_hours") is not None
                    else None
                ),
                read_errors=(
                    _int(item.get("read_errors"))
                    if item.get("read_errors") is not None
                    else None
                ),
                write_errors=(
                    _int(item.get("write_errors"))
                    if item.get("write_errors") is not None
                    else None
                ),
                volumes=[
                    part.strip()
                    for part in _text(item.get("volumes")).split(",")
                    if part.strip()
                ],
            )
        )
    volumes = []
    for item in _as_list(payload.get("volumes")):
        if not isinstance(item, dict):
            continue
        volumes.append(
            VolumeHealth(
                letter=_text(item.get("letter")),
                label=_text(item.get("label")),
                filesystem=_text(item.get("filesystem")),
                total=max(0, _int(item.get("total"))),
                free=max(0, _int(item.get("free"))),
                health=_health_name(item.get("health")),
            )
        )
    return DiskHealthReport(disks=disks, volumes=volumes)


class HardwareService:
    def collect(self) -> HardwareInfo:
        code, text = run_powershell(HARDWARE_SCRIPT, timeout=60)
        if code == 0:
            try:
                payload = _json_payload(text)
                if isinstance(payload, dict):
                    info = parse_hardware_json(payload)
                    if not info.cpu_name or not info.memory_total:
                        fallback = self._fallback()
                        self._merge_missing(info, fallback)
                        info.errors.append(
                            "CIM 返回的信息不完整，已用注册表/系统 API 补全。"
                        )
                    self._fill_gpu_vram(info)
                    _apply_display_info(info)
                    return info
            except (ValueError, json.JSONDecodeError):
                LOGGER.exception("解析硬件 JSON 失败: %s", text[-500:])
        fallback = self._fallback()
        fallback.errors.append(
            "CIM/WMI 查询不可用，仅显示注册表/系统 API 基础信息。"
        )
        _apply_display_info(fallback)
        LOGGER.warning("硬件 CIM 查询失败 code=%s: %s", code, text[-500:])
        return fallback

    @staticmethod
    def _fill_gpu_vram(info: HardwareInfo) -> None:
        vram_map = _registry_gpu_vram()
        for gpu in info.gpus:
            known = vram_map.get(gpu.name.casefold(), 0)
            if known > gpu.vram:
                gpu.vram = known

    @staticmethod
    def _merge_missing(info: HardwareInfo, fallback: HardwareInfo) -> None:
        fields = (
            "hostname",
            "manufacturer",
            "model",
            "os_name",
            "os_version",
            "os_build",
            "cpu_name",
            "cpu_socket",
            "board_manufacturer",
            "board_product",
            "board_version",
            "bios_vendor",
            "bios_version",
            "bios_date",
        )
        for field in fields:
            if not getattr(info, field):
                setattr(info, field, getattr(fallback, field))
        for field in ("cpu_cores", "cpu_threads", "cpu_max_mhz", "memory_total"):
            if not getattr(info, field):
                setattr(info, field, getattr(fallback, field))
        if not info.modules:
            info.modules = fallback.modules
        if not info.gpus:
            info.gpus = fallback.gpus
        if not info.network:
            info.network = fallback.network

    def _fallback(self) -> HardwareInfo:
        system = SystemService().collect()
        info = HardwareInfo(
            hostname=system.hostname,
            os_name=system.os_name,
            os_build=system.build,
            cpu_name=system.cpu_name,
            cpu_cores=max(1, system.cpu_cores // 2),
            cpu_threads=system.cpu_cores,
            memory_total=system.memory_total,
        )
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\BIOS",
            ) as key:
                def value(name: str) -> str:
                    try:
                        return str(winreg.QueryValueEx(key, name)[0])
                    except OSError:
                        return ""

                info.bios_vendor = value("BIOSVendor")
                info.bios_version = value("BIOSVersion")
                info.bios_date = value("BIOSReleaseDate")
                info.board_manufacturer = value("BaseBoardManufacturer")
                info.board_product = value("BaseBoardProduct")
                info.manufacturer = value("SystemManufacturer")
                info.model = value("SystemProductName")
        except OSError:
            pass
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}",
            ) as key:
                count = winreg.QueryInfoKey(key)[0]
                for index in range(count):
                    try:
                        name = winreg.EnumKey(key, index)
                        if not name.isdigit():
                            continue
                        with winreg.OpenKey(key, name) as sub:
                            driver = str(
                                winreg.QueryValueEx(sub, "DriverDesc")[0]
                            )
                            if not driver:
                                continue
                            vram = 0
                            for vram_name in (
                                "HardwareInformation.qwMemorySize",
                                "HardwareInformation.MemorySize",
                            ):
                                try:
                                    vram = int(winreg.QueryValueEx(sub, vram_name)[0])
                                    break
                                except (OSError, ValueError, TypeError):
                                    continue
                            info.gpus.append(
                                GPUInfo(
                                    name=driver,
                                    driver=str(
                                        winreg.QueryValueEx(sub, "DriverVersion")[0]
                                    ),
                                    vram=vram,
                                )
                            )
                    except OSError:
                        continue
        except OSError:
            pass
        self._fill_gpu_vram(info)
        return info

    @staticmethod
    def format_report(info: HardwareInfo) -> str:
        display = (
            f"{info.display_count} 台 · {info.screen_width}×{info.screen_height}"
            + (f" @ {info.screen_refresh}Hz" if info.screen_refresh else "")
            if info.display_count
            else "未检测到显示器（headless / 无显示输出）"
        )
        if info.remote_session:
            display += " · 远程会话"
        lines = [
            "WinToolbox 硬件检测报告",
            f"主机: {info.hostname}",
            f"系统: {info.os_name} {info.os_build}",
            f"机型: {info.manufacturer} {info.model}".strip(),
            f"显示器: {display}",
            f"CPU: {info.cpu_name} ({info.cpu_cores}C/{info.cpu_threads}T, {info.cpu_max_mhz} MHz)",
            f"主板: {info.board_manufacturer} {info.board_product} {info.board_version}".strip(),
            f"BIOS: {info.bios_vendor} {info.bios_version} {info.bios_date}".strip(),
            f"内存: {human_bytes(info.memory_total)}",
        ]
        for monitor in info.monitors:
            lines.append(
                f"  显示器: {monitor.name} | {monitor.manufacturer} | "
                f"{monitor.size_inches} 英寸 | {monitor.connection} | "
                f"{monitor.serial} | {monitor.year} | "
                f"{'活动' if monitor.active else '非活动'}"
            )
        for module in info.modules:
            lines.append(
                f"  {module.slot}: {human_bytes(module.capacity)} {module.memory_type} "
                f"{module.speed_mhz} MHz {module.manufacturer} {module.part_number}".strip()
            )
        for gpu in info.gpus:
            lines.append(f"显卡: {gpu.name} {gpu.driver} {human_bytes(gpu.vram)}".strip())
        for adapter in info.network:
            lines.append(
                f"网卡: {adapter.name} {adapter.status} {adapter.mac} {adapter.ip_addresses}".strip()
            )
        return "\n".join(lines)


class DiskHealthService:
    def collect(self) -> DiskHealthReport:
        code, text = run_powershell(DISK_SCRIPT, timeout=75)
        if code == 0:
            try:
                payload = _json_payload(text)
                if isinstance(payload, dict):
                    report = parse_disk_json(payload)
                    report.collected_at = datetime.now()
                    if report.disks:
                        return report
                    report.error = "系统没有返回物理磁盘信息。"
                    return report
            except (ValueError, json.JSONDecodeError):
                LOGGER.exception("解析磁盘健康 JSON 失败: %s", text[-500:])
        report = DiskHealthReport(
            error="无法读取物理磁盘健康信息，已降级为卷列表。",
            collected_at=datetime.now(),
        )
        LOGGER.warning("磁盘健康 CIM 查询失败 code=%s: %s", code, text[-500:])
        try:
            for drive in list_drives():
                report.volumes.append(
                    VolumeHealth(
                        letter=drive.letter,
                        label=drive.label,
                        filesystem=drive.filesystem,
                        total=drive.total,
                        free=drive.free,
                        health="未知",
                    )
                )
        except OSError:
            pass
        return report

    @staticmethod
    def format_report(report: DiskHealthReport) -> str:
        lines = ["WinToolbox 磁盘健康报告"]
        for disk in report.disks:
            lines.append(
                f"{disk.name} | {disk.media_type}/{disk.bus_type} | "
                f"{human_bytes(disk.size)} | {disk.health} | "
                f"SN {disk.serial or '—'} | 固件 {disk.firmware or '—'}"
            )
            lines.append(
                f"  温度 {disk.temperature if disk.temperature is not None else '—'}°C"
                f" | 磨损 {disk.wear if disk.wear is not None else '—'}%"
                f" | 通电 {disk.power_on_hours if disk.power_on_hours is not None else '—'} 小时"
                f" | 卷 {', '.join(disk.volumes) or '—'}"
            )
        for volume in report.volumes:
            lines.append(
                f"{volume.letter} {volume.label} {volume.filesystem} "
                f"{human_bytes(volume.free)} 可用 / {human_bytes(volume.total)} "
                f"{volume.health}"
            )
        return "\n".join(lines)
