@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3 "%~dp0app.py"
    exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0app.py"
    exit /b 0
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0app.py"
    exit /b
)

echo.
echo 未找到 Python 3。请先安装 Python 3.10 或更高版本。
echo 安装时请勾选 "Add Python to PATH"。
echo 下载地址: https://www.python.org/downloads/windows/
echo.
pause
exit /b 1
