# WinToolbox · Windows 工具箱

[![GitHub](https://img.shields.io/badge/GitHub-yoyiyi%2FWinToolbox-181717?logo=github)](https://github.com/yoyiyi/WinToolbox)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D6?logo=windows)

一个用 Python + Tkinter 编写的本地 Windows 桌面工具箱，集中处理应用更新、内存整理、硬件验机、磁盘健康、后台进程、大文件扫描、应用卸载和启动项检查。

- 仓库地址：<https://github.com/yoyiyi/WinToolbox>
- 发布包下载：<https://github.com/yoyiyi/WinToolbox/releases>
- 问题反馈：<https://github.com/yoyiyi/WinToolbox/issues>

## 下载与运行

从 [Releases](https://github.com/yoyiyi/WinToolbox/releases) 下载 `WinToolbox-*-portable.zip`，解压后双击 `WinToolbox.exe`。整个 `WinToolbox` 文件夹可以复制到其他 Windows 电脑运行，不需要安装 Python。

如果从源码运行：

```bat
git clone https://github.com/yoyiyi/WinToolbox.git
cd WinToolbox
python app.py
```

要求 Windows 10/11、Python 3.10+。运行时只使用标准库，不依赖第三方 Python 包；`tkinter` 随 Python 官方安装包提供。

## 功能

左侧导航共 9 项，快捷键 `Ctrl+1` 到 `Ctrl+9`：

| 页面 | 作用 |
| --- | --- |
| 概览 | 更新、应用、后台进程、卸载建议和系统状态 |
| 内存加速 | 圆形内存仪表、整理后台闲置工作集、释放结果 |
| 应用更新 | winget 环境检测、可用更新、批量升级、实时输出 |
| 后台进程 | 进程 CPU/内存/用户/路径，结束非系统进程 |
| 硬件检测 | CPU、主板/BIOS、显卡、显示器 EDID、内存、网卡；磁盘健康 |
| 验机工具 | 屏幕坏点、键盘、鼠标测试；第三方验机软件检测、启动与安装 |
| 大文件扫描 | 按磁盘和阈值扫描大文件，筛选、定位、移入回收站 |
| 应用卸载 | 注册表应用清单、启发式建议、调用原厂卸载程序 |
| 启动项 | Run 键和启动文件夹只读视图 |

### 硬件与显示器

- CPU 型号、核心/线程、最大频率、插槽。
- 主板厂商/型号、BIOS 版本和日期。
- 显卡型号、驱动版本、显存。
- 显示器 EDID：名称、厂商、尺寸、年份、接口、序列号、活动状态。
- 顶部显示显示器数量、当前分辨率和刷新率；无显示器或远程会话时仍可读取其他硬件。
- 磁盘：物理磁盘类型、健康状态、温度/磨损/通电时间（硬件提供时）和卷容量。

### 验机工具

内置、无需安装：

- 屏幕坏点检测：全屏纯色循环，左键/空格切换，Esc 退出。
- 键盘测试：按键高亮、最近按键、已测试数量。
- 鼠标测试：坐标、左右中键、双击、滚轮计数。

第三方工具（不随项目分发）：CPU-Z、GPU-Z、AIDA64、CrystalDiskInfo、CrystalDiskMark、MemTest64、FurMark、HWiNFO64、AS SSD Benchmark、Prime95、Victoria、HD Tune、Core Temp、SSD-Z。

- 已安装时直接启动。
- 未安装且 winget 有包时可一键安装；没有 winget 包或安装失败时打开官网。
- 安装前需要二次确认，可能需要网络和 UAC。
- AIDA64/HD Tune 等可能需要官方授权；FurMark/Prime95 等压力测试有风险。

### 无显示器/远程服务器

GUI 仍需要 Windows 桌面会话。没有可用桌面时，可以使用不创建 Tk 窗口的 headless 报告：

```bat
WinToolbox.exe --headless --output D:\hardware-report.txt
WinToolbox.exe --headless --json --output D:\hardware-report.json
```

不指定 `--output` 时写入：

```text
%LOCALAPPDATA%\WinToolbox\reports\hardware-report.txt
```

报告包含硬件、显示器/会话、物理磁盘和卷信息。

## 构建

```bat
build.bat
```

脚本会使用 PyInstaller 构建便携版，输出到：

```text
out\
  WinToolbox\
    WinToolbox.exe
    _internal\
    README.md
    使用说明.txt
  WinToolbox-1.0.0-portable.zip
```

`out/` 是构建产物，不提交到 Git。需要发布时，把 `out/WinToolbox-1.0.0-portable.zip` 上传到 GitHub Releases。

手动构建：

```bat
python -m pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name WinToolbox ^
  --icon assets\app.ico ^
  --add-data "assets;assets" ^
  --distpath out ^
  --workpath build\work ^
  --specpath build\spec ^
  app.py
```

## 项目结构

```text
app.py                    启动入口（GUI / --headless）
wintoolbox/
  services/               Win32、注册表、winget、硬件与工具服务
  ui/                     Tkinter 界面、页面、控件、主题
  models.py               数据模型
  utils.py                格式化、日志、命令和审计工具
assets/                   应用图标
tests/                    纯逻辑单元测试
scripts/                  图标生成和界面截图脚本（开发用）
build.bat                 PyInstaller 构建
requirements.txt          运行时依赖（标准库，无第三方）
requirements-dev.txt      构建/截图依赖
out/                      构建产物（Git 忽略）
```

## 测试

```bat
python -m unittest discover -s tests -v
```

测试覆盖 winget 解析、卸载建议、大文件扫描、内存加速、硬件/显示器解析、headless 报告、工具目录和命令拆分。

## 数据与隐私

- 所有扫描和判断都在本机完成，不上传应用列表、进程信息或硬件信息。
- 日志和配置保存在 `%LOCALAPPDATA%\WinToolbox`；可用 `WINTOOLBOX_HOME` 覆盖。
- 源码和仓库不包含 token、API key、账号密码、本机日志或配置文件。
- 请勿把 `out/`、`%LOCALAPPDATA%\WinToolbox`、`.runtime/` 或个人配置提交到 Git。
- 第三方验机工具从 winget/官网获取，项目不重新分发其安装包。

## 安全边界

- 内存加速只回收工作集，不结束进程，也不会增加物理内存。
- 结束进程、卸载应用、移入回收站等操作均有确认或保护逻辑。
- 卸载通过 ShellExecuteEx 启动原厂卸载程序；HKLM 应用在标准用户下会请求 UAC。
- 大文件扫描默认跳过系统目录；系统文件不能在工具箱内移入回收站。

## 说明

本项目以 Windows 为主要目标平台，源码中的 Win32、注册表和 PowerShell CIM 能力不能在 macOS/Linux 上运行。

如果这个项目对你有帮助，欢迎在 GitHub 上 Star、提交 Issue 或 Pull Request。
