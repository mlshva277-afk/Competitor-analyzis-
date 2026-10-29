@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 launch.py
    goto done
)
where python >nul 2>nul
if not errorlevel 1 (
    python launch.py
    goto done
)
echo Python was not found. Install Python 3.12 or newer from https://www.python.org/downloads/
echo Select "Add Python to PATH" during installation, then open this file again.
:done
pause
