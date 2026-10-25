"""跨服务共享的数据模型。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(slots=True)
class SystemInfo:
    os_name: str
    build: str
    architecture: str
    cpu_name: str
    cpu_cores: int
    memory_total: int
    memory_used: int
    memory_percent: float
    disk_total: int
    disk_used: int
    disk_percent: float
    uptime_seconds: int
    hostname: str
    username: str
    is_admin: bool
    python_version: str
    cpu_percent: float = 0.0


@dataclass(slots=True)
class AppRecord:
    name: str
    version: str = ""
    publisher: str = ""
    install_date: date | None = None
    size_kb: int = 0
    install_location: str = ""
    uninstall_string: str = ""
    quiet_uninstall_string: str = ""
    hive: str = "HKLM"
    architecture: str = "64"
    key_path: str = ""
    display_icon: str = ""
    url: str = ""
    category: str = "其他"
    advice: str = "常规应用"
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    protected: bool = False
    can_uninstall: bool = False

    @property
    def size_bytes(self) -> int:
        return max(0, self.size_kb) * 1024

    @property
    def identity(self) -> str:
        return f"{self.hive}|{self.architecture}|{self.key_path}|{self.name}"

    @property
    def effective_uninstall_command(self) -> str:
        return self.quiet_uninstall_string or self.uninstall_string

    def to_audit_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "publisher": self.publisher,
            "hive": self.hive,
            "architecture": self.architecture,
            "advice": self.advice,
            "score": self.score,
            "uninstall": self.effective_uninstall_command,
        }


@dataclass(slots=True)
class UpdatePackage:
    name: str
    package_id: str
    current_version: str
    available_version: str
    source: str = "winget"

    @property
    def identity(self) -> str:
        return f"{self.package_id}|{self.source}"


@dataclass(slots=True)
class UpdateScanResult:
    updates: list[UpdatePackage]
    error: str = ""
    warning: str = ""
    raw_output: str = ""
    checked_at: datetime | None = None

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass(slots=True)
class WingetInfo:
    available: bool
    version: str = ""
    path: str = ""
    error: str = ""
    install_hint: str = ""


@dataclass(slots=True)
class UpgradeResult:
    package_id: str
    success: bool
    exit_code: int
    output: str = ""
    error: str = ""


@dataclass(slots=True)
class ProcessInfo:
    pid: int
    name: str
    parent_pid: int = 0
    parent_name: str = ""
    cpu_percent: float = 0.0
    memory_bytes: int = 0
    path: str = ""
    username: str = ""
    window_title: str = ""
    create_time: datetime | None = None
    is_background: bool = True
    is_system: bool = False
    threads: int = 0

    @property
    def kind_label(self) -> str:
        if self.is_system:
            return "系统"
        return "后台" if self.is_background else "前台"


@dataclass(slots=True)
class StartupEntry:
    name: str
    command: str
    scope: str
    source: str
    enabled: bool = True
    registry_root: int = 0
    registry_path: str = ""
    approved_path: str = ""
    view_flag: int = 0
    value_name: str = ""
    folder_path: str = ""


@dataclass(slots=True)
class StartupToggleResult:
    ok: bool
    enabled: bool = True
    message: str = ""


@dataclass(slots=True)
class UninstallResult:
    ok: bool
    exit_code: int | None = None
    message: str = ""
    elevated: bool = False


@dataclass(slots=True)
class DriveInfo:
    letter: str
    root: str
    label: str
    filesystem: str
    drive_type: str
    total: int
    free: int
    is_system: bool = False

    @property
    def free_percent(self) -> float:
        return (self.free / self.total * 100.0) if self.total else 0.0

    @property
    def display_name(self) -> str:
        label = self.label or self.drive_type
        return f"{self.letter}  {label}"


@dataclass(slots=True)
class LargeFile:
    path: str
    size: int
    modified: datetime | None = None
    file_type: str = "文件"
    protected: bool = False

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def directory(self) -> str:
        return os.path.dirname(self.path)


@dataclass(slots=True)
class LargeFileScanResult:
    files: list[LargeFile] = field(default_factory=list)
    root: str = ""
    min_size: int = 0
    scanned_files: int = 0
    scanned_dirs: int = 0
    inaccessible: int = 0
    elapsed: float = 0.0
    cancelled: bool = False
    truncated: bool = False

    @property
    def total_size(self) -> int:
        return sum(item.size for item in self.files)


@dataclass(slots=True)
class RecycleResult:
    recycled: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    message: str = ""


@dataclass(slots=True)
class MemoryBoostResult:
    before_total: int = 0
    before_available: int = 0
    before_percent: float = 0.0
    after_total: int = 0
    after_available: int = 0
    after_percent: float = 0.0
    working_set_released: int = 0
    trimmed: int = 0
    skipped: int = 0
    elapsed: float = 0.0
    include_foreground: bool = False

    @property
    def available_delta(self) -> int:
        return max(0, self.after_available - self.before_available)


@dataclass(slots=True)
class MemoryModule:
    slot: str
    capacity: int
    speed_mhz: int = 0
    manufacturer: str = ""
    part_number: str = ""
    memory_type: str = ""


@dataclass(slots=True)
class GPUInfo:
    name: str
    driver: str = ""
    vram: int = 0
    processor: str = ""


@dataclass(slots=True)
class NetworkAdapter:
    name: str
    description: str = ""
    mac: str = ""
    speed_bps: int = 0
    connected: bool = False
    status: str = ""
    ip_addresses: str = ""


@dataclass(slots=True)
class MonitorInfo:
    name: str
    manufacturer: str = ""
    serial: str = ""
    year: int = 0
    width_cm: int = 0
    height_cm: int = 0
    size_inches: float = 0.0
    connection: str = ""
    active: bool = False


@dataclass(slots=True)
class HardwareInfo:
    hostname: str = ""
    manufacturer: str = ""
    model: str = ""
    os_name: str = ""
    os_version: str = ""
    os_build: str = ""
    cpu_name: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0
    cpu_max_mhz: int = 0
    cpu_socket: str = ""
    board_manufacturer: str = ""
    board_product: str = ""
    board_version: str = ""
    bios_vendor: str = ""
    bios_version: str = ""
    bios_date: str = ""
    memory_total: int = 0
    display_count: int = 0
    screen_width: int = 0
    screen_height: int = 0
    screen_refresh: int = 0
    remote_session: bool = False
    monitors: list[MonitorInfo] = field(default_factory=list)
    sound_devices: list[str] = field(default_factory=list)
    npu_devices: list[str] = field(default_factory=list)
    modules: list[MemoryModule] = field(default_factory=list)
    gpus: list[GPUInfo] = field(default_factory=list)
    network: list[NetworkAdapter] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PhysicalDisk:
    name: str
    size: int = 0
    media_type: str = ""
    bus_type: str = ""
    health: str = "未知"
    operational: str = ""
    serial: str = ""
    firmware: str = ""
    temperature: int | None = None
    wear: int | None = None
    power_on_hours: int | None = None
    read_errors: int | None = None
    write_errors: int | None = None
    device_id: str = ""
    volumes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VolumeHealth:
    letter: str
    label: str = ""
    filesystem: str = ""
    total: int = 0
    free: int = 0
    health: str = "未知"


@dataclass(slots=True)
class DiskHealthReport:
    disks: list[PhysicalDisk] = field(default_factory=list)
    volumes: list[VolumeHealth] = field(default_factory=list)
    error: str = ""
    collected_at: datetime | None = None

