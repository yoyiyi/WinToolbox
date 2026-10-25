@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)

%PYTHON% -m pip install --upgrade pyinstaller
if errorlevel 1 goto :failed

if exist "out\WinToolbox" rmdir /s /q "out\WinToolbox"
if exist "out\WinToolbox-1.0.1-portable.zip" del /q "out\WinToolbox-1.0.1-portable.zip"

%PYTHON% -m PyInstaller --noconfirm --clean --windowed --onedir ^
    --name WinToolbox ^
    --icon "assets\app.ico" ^
    --add-data "assets;assets" ^
    --distpath out ^
    --workpath build\work ^
    --specpath build\spec ^
    app.py
if errorlevel 1 goto :failed

copy /y "README.md" "out\WinToolbox\README.md" >nul
copy /y "使用说明.txt" "out\WinToolbox\使用说明.txt" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -LiteralPath 'out\WinToolbox' -DestinationPath 'out\WinToolbox-1.0.1-portable.zip' -Force"
if errorlevel 1 goto :failed

powershell -NoProfile -Command ^
  "$h=(Get-FileHash 'out\WinToolbox-1.0.1-portable.zip' -Algorithm SHA256).Hash; Set-Content 'out\SHA256SUMS.txt' $h -Encoding ascii"

echo.
echo 构建完成:
echo   out\WinToolbox\WinToolbox.exe
echo   out\WinToolbox-1.0.1-portable.zip
echo.
echo 发布时把 out\WinToolbox-1.0.1-portable.zip 上传到 GitHub Releases。
pause
exit /b 0

:failed
echo.
echo 构建失败。请确认已安装 Python 3.10+ 且能联网安装 PyInstaller。
pause
exit /b 1
