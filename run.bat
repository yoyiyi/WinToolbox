@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 app.py
    goto :done
)

where python >nul 2>nul
if %errorlevel%==0 (
    python app.py
    goto :done
)

echo.
echo 未找到 Python 3。请先安装 Python 3.10 或更高版本。
echo 下载地址: https://www.python.org/downloads/windows/
echo.
pause
exit /b 1

:done
if errorlevel 1 (
    echo.
    echo 工具箱退出时返回了错误，请检查上方输出或 logs 目录。
    pause
)
