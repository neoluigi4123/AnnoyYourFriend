@echo off
setlocal enabledelayedexpansion

title AnnoyYourFriend Launcher
cd /d "%~dp0"

echo =========================================
echo         AnnoyYourFriend Launcher         
echo =========================================

set "PY_CMD="

:: -------------------------------------------------------------
:: 1. Check if a working Python is already available
:: -------------------------------------------------------------
py -0 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=py"
    goto :PYTHON_READY
)

python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=python"
    goto :PYTHON_READY
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%D\python.exe" (
        set "PY_CMD=%%D\python.exe"
        goto :PYTHON_READY
    )
)

:: -------------------------------------------------------------
:: 2. Auto-Install Python (if not found)
:: -------------------------------------------------------------
echo [!] Python was not detected on this system.
echo [*] Downloading Python installer automatically...

set "INSTALLER_URL=https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
set "INSTALLER_PATH=%TEMP%\python_installer.exe"

curl --ssl-no-revoke -L -o "%INSTALLER_PATH%" "%INSTALLER_URL%"
if not exist "%INSTALLER_PATH%" (
    echo [-] Failed to download Python. Please check your internet connection.
    pause
    exit /b 1
)

echo [*] Installing Python silently...
start /wait "" "%INSTALLER_PATH%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
del "%INSTALLER_PATH%" >nul 2>&1

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%D\python.exe" (
        set "PY_CMD=%%D\python.exe"
        goto :PYTHON_READY
    )
)

py -0 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=py"
    goto :PYTHON_READY
)

python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=python"
    goto :PYTHON_READY
)

echo [-] Installation completed, but could not find the executable path automatically.
pause
exit /b 1

:: -------------------------------------------------------------
:: 3. Setup Virtual Environment & Dependencies
:: -------------------------------------------------------------
:PYTHON_READY
echo [+] Python detected:
"%PY_CMD%" --version
echo.

if not exist ".venv\" (
    echo [*] Creating virtual environment...
    "%PY_CMD%" -m venv .venv
    if errorlevel 1 (
        echo [-] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

set "VENV_PYTHON=.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo [-] Virtual environment interpreter not found in %VENV_PYTHON%
    pause
    exit /b 1
)

echo [*] Checking and installing dependencies: PyQt6, requests...
"%VENV_PYTHON%" -m pip install --upgrade pip --quiet
"%VENV_PYTHON%" -m pip install PyQt6 requests --quiet

:: -------------------------------------------------------------
:: 4. Launch the App
:: -------------------------------------------------------------
set "TARGET_SCRIPT=main.py"
if not exist "%TARGET_SCRIPT%" (
    for %%F in (*.py) do (
        set "TARGET_SCRIPT=%%F"
        goto :RUN_APP
    )
)

:RUN_APP
if not exist "%TARGET_SCRIPT%" (
    echo [-] Error: No .py file found to execute in this folder.
    pause
    exit /b 1
)

echo [+] Starting %TARGET_SCRIPT%...
"%VENV_PYTHON%" "%TARGET_SCRIPT%"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [-] Application closed with an error.
    pause
)
