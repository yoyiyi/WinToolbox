"""验机工具目录：检测、启动和通过 winget 安装常用第三方工具。

工具箱不重新分发这些第三方安装包。已安装的工具直接从本机启动；
未安装且 winget 有对应包时提供一键安装，否则打开官方下载页。
"""

from __future__ import annotations

import os
import shutil
import winreg
from dataclasses import dataclass

from ..utils import get_logger, run_command
from .winget import WingetService

LOGGER = get_logger("tools")


@dataclass(slots=True)
class ToolSpec:
    key: str
    name: str
    description: str
    category: str
    url: str
    winget_id: str = ""
    paths: tuple[str, ...] = ()
    exe_names: tuple[str, ...] = ()
    note: str = ""


@dataclass(slots=True)
class ToolStatus:
    spec: ToolSpec
    installed: bool = False
    path: str = ""


@dataclass(slots=True)
class ToolActionResult:
    ok: bool
    message: str = ""
    output: str = ""


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        key="cpuz",
        name="CPU-Z",
        description="CPU、主板、内存规格、通道和时序；核对配置时最常用。",
        category="必用",
        url="https://www.cpuid.com/softwares/cpu-z.html",
        winget_id="CPUID.CPU-Z",
        paths=(
            r"%ProgramFiles%\CPUID\CPU-Z\cpuz.exe",
            r"%ProgramFiles(x86)%\CPUID\CPU-Z\cpuz.exe",
            r"%LOCALAPPDATA%\Programs\CPUID\CPU-Z\cpuz.exe",
        ),
        exe_names=("cpuz.exe",),
    ),
    ToolSpec(
        key="gpuz",
        name="GPU-Z",
        description="显卡核心、显存、位宽和 BIOS；二手显卡验卡常用。",
        category="必用",
        url="https://www.techpowerup.com/gpuz/",
        winget_id="TechPowerUp.GPU-Z",
        paths=(
            r"%ProgramFiles(x86)%\GPU-Z\GPU-Z.exe",
            r"%ProgramFiles%\GPU-Z\GPU-Z.exe",
            r"%ProgramFiles(x86)%\TechPowerUp\GPU-Z\GPU-Z.exe",
            r"%ProgramFiles%\TechPowerUp\GPU-Z\GPU-Z.exe",
        ),
        exe_names=("GPU-Z.exe",),
    ),
    ToolSpec(
        key="aida64",
        name="AIDA64",
        description="完整硬件信息、传感器温度/风扇；也可做 FPU 单烤压力测试。",
        category="必用",
        url="https://www.aida64.com/downloads",
        winget_id="FinalWire.AIDA64.Extreme",
        paths=(
            r"%ProgramFiles%\FinalWire\AIDA64 Extreme\aida64.exe",
            r"%ProgramFiles(x86)%\FinalWire\AIDA64 Extreme\aida64.exe",
            r"%ProgramFiles%\FinalWire\AIDA64 Engineer\aida64.exe",
            r"%ProgramFiles%\FinalWire\AIDA64 Business\aida64.exe",
        ),
        exe_names=("aida64.exe",),
        note="Extreme 为试用版，正式版需要官方授权。",
    ),
    ToolSpec(
        key="crystaldiskinfo",
        name="CrystalDiskInfo",
        description="硬盘 SMART、通电时间、写入量和健康度；新机验机常用。",
        category="必用",
        url="https://crystalmark.info/en/software/crystaldiskinfo/",
        winget_id="CrystalDewWorld.CrystalDiskInfo",
        paths=(
            r"%ProgramFiles%\CrystalDewWorld\CrystalDiskInfo\DiskInfo64.exe",
            r"%ProgramFiles(x86)%\CrystalDewWorld\CrystalDiskInfo\DiskInfo64.exe",
            r"%ProgramFiles%\CrystalDewWorld\CrystalDiskInfo\DiskInfo.exe",
            r"%ProgramFiles(x86)%\CrystalDewWorld\CrystalDiskInfo\DiskInfo.exe",
        ),
        exe_names=("DiskInfo64.exe", "DiskInfo.exe"),
    ),
    ToolSpec(
        key="crystaldiskmark",
        name="CrystalDiskMark",
        description="固态硬盘连续/4K 读写测速，检查性能是否达标。",
        category="必用",
        url="https://crystalmark.info/en/software/crystaldiskmark/",
        winget_id="CrystalDewWorld.CrystalDiskMark",
        paths=(
            r"%ProgramFiles%\CrystalDewWorld\CrystalDiskMark\DiskMark64.exe",
            r"%ProgramFiles(x86)%\CrystalDewWorld\CrystalDiskMark\DiskMark64.exe",
            r"%ProgramFiles%\CrystalDewWorld\CrystalDiskMark\DiskMark.exe",
            r"%ProgramFiles(x86)%\CrystalDewWorld\CrystalDiskMark\DiskMark.exe",
        ),
        exe_names=("DiskMark64.exe", "DiskMark.exe"),
    ),
    ToolSpec(
        key="memtest64",
        name="MemTest64",
        description="内存稳定性测试，排查蓝屏、闪退和内存超频问题。",
        category="必用",
        url="https://www.techpowerup.com/memtest64/",
        paths=(
            r"%ProgramFiles%\TechPowerUp\MemTest64\MemTest64.exe",
            r"%ProgramFiles(x86)%\TechPowerUp\MemTest64\MemTest64.exe",
        ),
        exe_names=("MemTest64.exe",),
        note="测试期间系统可能无响应，请先保存工作。",
    ),
    ToolSpec(
        key="furmark",
        name="FurMark",
        description="显卡满载烤机，观察温度、功耗、降频和稳定性。",
        category="必用",
        url="https://geeks3d.com/furmark/",
        winget_id="Geeks3D.FurMark.2",
        paths=(
            r"%ProgramFiles%\Geeks3D\FurMark\FurMark_GUI.exe",
            r"%ProgramFiles%\Geeks3D\FurMark2\FurMark_GUI.exe",
            r"%ProgramFiles(x86)%\Geeks3D\FurMark\FurMark_GUI.exe",
            r"%ProgramFiles%\Geeks3D\FurMark\FurMark.exe",
        ),
        exe_names=("FurMark_GUI.exe", "FurMark.exe"),
        note="烤机会让显卡长时间满载，注意温度和供电。",
    ),
    ToolSpec(
        key="hwinfo",
        name="HWiNFO64",
        description="更细的传感器、电压、风扇和功耗数据，适合散热/超频排查。",
        category="进阶",
        url="https://www.hwinfo.com/download/",
        winget_id="REALiX.HWiNFO",
        paths=(
            r"%ProgramFiles%\HWiNFO64\HWiNFO64.exe",
            r"%ProgramFiles%\HWiNFO\HWiNFO64.exe",
            r"%ProgramFiles(x86)%\HWiNFO64\HWiNFO64.exe",
        ),
        exe_names=("HWiNFO64.exe", "HWiNFO32.exe"),
    ),
    ToolSpec(
        key="asssd",
        name="AS SSD Benchmark",
        description="SSD 测速并检查 4K 对齐、驱动和跑分。",
        category="进阶",
        url="https://www.alex-is.de/PHP/fusion/downloads.php?cat_id=4",
        paths=(
            r"%ProgramFiles%\AS SSD Benchmark\AS SSD Benchmark.exe",
            r"%ProgramFiles(x86)%\AS SSD Benchmark\AS SSD Benchmark.exe",
        ),
        exe_names=("AS SSD Benchmark.exe",),
    ),
    ToolSpec(
        key="prime95",
        name="Prime95",
        description="CPU 极限压力测试，比普通 FPU 烤机更激进。",
        category="进阶",
        url="https://www.mersenne.org/download/",
        winget_id="mersenne.prime95",
        paths=(
            r"%ProgramFiles%\Prime95\prime95.exe",
            r"%ProgramFiles%\Prime95\p95v*.exe",
            r"%ProgramFiles(x86)%\Prime95\prime95.exe",
        ),
        exe_names=("prime95.exe",),
        note="极限测试可能导致死机或温度过高，请谨慎使用。",
    ),
    ToolSpec(
        key="victoria",
        name="Victoria",
        description="机械硬盘/SSD 坏道扫描与 SMART 查看。",
        category="进阶",
        url="https://hdd.by/victoria/",
        winget_id="Victoria.Victoria",
        paths=(
            r"%ProgramFiles%\Victoria\Victoria.exe",
            r"%ProgramFiles%\Victoria\victoria.exe",
            r"%ProgramFiles(x86)%\Victoria\Victoria.exe",
        ),
        exe_names=("Victoria.exe", "victoria.exe"),
    ),
    ToolSpec(
        key="hdtune",
        name="HD Tune",
        description="机械硬盘健康、错误扫描和基准测试。",
        category="进阶",
        url="https://www.hdtune.com/",
        paths=(
            r"%ProgramFiles%\HD Tune\HDTune.exe",
            r"%ProgramFiles%\HD Tune\HDTunePro.exe",
            r"%ProgramFiles(x86)%\HD Tune\HDTune.exe",
            r"%ProgramFiles(x86)%\HD Tune\HDTunePro.exe",
        ),
        exe_names=("HDTune.exe", "HDTunePro.exe"),
        note="Pro 功能可能需要授权。",
    ),
    ToolSpec(
        key="coretemp",
        name="Core Temp",
        description="轻量 CPU 温度监控，可常驻托盘。",
        category="进阶",
        url="https://www.alcpu.com/CoreTemp/",
        winget_id="ALCPU.CoreTemp",
        paths=(
            r"%ProgramFiles%\Core Temp\Core Temp.exe",
            r"%ProgramFiles(x86)%\Core Temp\Core Temp.exe",
        ),
        exe_names=("Core Temp.exe",),
    ),
    ToolSpec(
        key="ssdz",
        name="SSD-Z",
        description="查看固态硬盘主控、颗粒、固件和详细参数。",
        category="进阶",
        url="https://www.ssd-z.com/",
        paths=(
            r"%ProgramFiles%\SSD-Z\SSD-Z.exe",
            r"%ProgramFiles(x86)%\SSD-Z\SSD-Z.exe",
        ),
        exe_names=("SSD-Z.exe",),
    ),
)


def _existing(path: str) -> str:
    expanded = os.path.expandvars(path)
    if os.path.isfile(expanded):
        return os.path.normpath(expanded)
    return ""


def _app_path(exe_name: str) -> str:
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        key_path = (
            r"Software\Microsoft\Windows\CurrentVersion\App Paths" + "\\" + exe_name
        )
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value = winreg.QueryValueEx(key, "")[0]
                found = _existing(str(value))
                if found:
                    return found
        except OSError:
            continue
    return ""


class ToolService:
    def specs(self) -> tuple[ToolSpec, ...]:
        return TOOL_SPECS

    def detect(self) -> list[ToolStatus]:
        statuses = []
        for spec in TOOL_SPECS:
            path = ""
            for candidate in spec.paths:
                path = _existing(candidate)
                if path:
                    break
            if not path:
                for exe_name in spec.exe_names:
                    path = _app_path(exe_name)
                    if path:
                        break
                    path = shutil.which(exe_name) or ""
                    if path:
                        path = os.path.normpath(path)
                        break
            statuses.append(ToolStatus(spec=spec, installed=bool(path), path=path))
        return statuses

    @staticmethod
    def launch(status: ToolStatus) -> ToolActionResult:
        if not status.installed or not status.path:
            return ToolActionResult(False, "没有找到可执行文件。")
        try:
            os.startfile(status.path)  # type: ignore[attr-defined]
        except OSError as exc:
            return ToolActionResult(False, f"启动失败：{exc}")
        return ToolActionResult(True, f"已启动 {status.spec.name}")

    @staticmethod
    def install(spec: ToolSpec, winget: WingetService) -> ToolActionResult:
        if not spec.winget_id:
            return ToolActionResult(False, "该工具没有配置 winget 安装包，请使用官网下载。")
        info = winget.probe()
        if not info.available or not info.path:
            return ToolActionResult(
                False,
                info.error or "winget 不可用，无法自动安装。",
            )
        command = [
            info.path,
            "install",
            "--id",
            spec.winget_id,
            "-e",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--silent",
        ]
        LOGGER.info("安装验机工具: %s", " ".join(command))
        code, output = run_command(command, timeout=900)
        ok = code == 0 or "Successfully installed" in output or "已成功安装" in output
        if ok:
            return ToolActionResult(True, f"{spec.name} 安装完成。", output)
        return ToolActionResult(
            False,
            f"{spec.name} 安装未完成（退出码 {code}）。",
            output,
        )

    @staticmethod
    def open_official(spec: ToolSpec) -> ToolActionResult:
        try:
            os.startfile(spec.url)  # type: ignore[attr-defined]
        except OSError as exc:
            return ToolActionResult(False, f"无法打开浏览器：{exc}")
        return ToolActionResult(True, f"已打开 {spec.name} 官网/下载页")
