@echo off
setlocal enabledelayedexpansion

title AnnoyYourFriend Launcher
cd /d "%~dp0"

echo =========================================
echo         AnnoyYourFriend Launcher         
echo =========================================

set "PY_CMD="

:: Test 1: Python Launcher (py.exe)
py -0 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=py"
    goto :VALIDATE_PYTHON
)

:: Test 2: python.exe (Ensuring it's not the Windows Store stub)
python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=python"
    goto :VALIDATE_PYTHON
)

:: Test 3: Common default install directories if PATH was not set
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%D\python.exe" (
        set "PY_CMD=%%D\python.exe"
        goto :VALIDATE_PYTHON
    )
)

echo.
echo [-] Error: A working Python installation was not found!
echo     Please download and install Python from:
echo     https://www.python.org/downloads/
echo.
echo [*] IMPORTANT: Check the box "Add python.exe to PATH" during installation.
echo.
pause
exit /b 1

:VALIDATE_PYTHON
echo [+] Python detected:
%PY_CMD% --version
echo.

:: 2. Create virtual environment if it does not exist
if not exist ".venv\" (
    echo [*] Creating virtual environment (.venv)...
    %PY_CMD% -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [-] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: 3. Identify and use virtualenv python binary directly
set "VENV_PYTHON=.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo [-] Virtual environment interpreter not found in %VENV_PYTHON%
    pause
    exit /b 1
)

:: 4. Install / Update dependencies
echo [*] Checking and installing dependencies (PyQt6, requests)...
"%VENV_PYTHON%" -m pip install --upgrade pip --quiet
"%VENV_PYTHON%" -m pip install PyQt6 requests --quiet

:: 5. Identify Python script to run
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
