@echo off
setlocal enabledelayedexpansion

title AnnoyYourFriend Launcher
cd /d "%~dp0"

echo =========================================
echo         AnnoyYourFriend Launcher         
echo =========================================

:: 1. Check if Python is installed
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=py"
    goto :PYTHON_FOUND
)

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=python"
    goto :PYTHON_FOUND
)

echo [-] Error: Python is not installed or not added to PATH.
echo     Please install Python from https://www.python.org/
echo     (Make sure to check "Add Python to PATH" during installation)
pause
exit /b 1

:PYTHON_FOUND
echo [+] Python found.

:: 2. Create virtual environment if it does not exist
if not exist ".venv\" (
    echo [*] Creating virtual environment...
    %PY_CMD% -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [-] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: 3. Activate the virtual environment
call .venv\Scripts\activate.bat

:: 4. Install / Update dependencies
echo [*] Checking and installing dependencies (PyQt6, requests)...
python -m pip install --upgrade pip --quiet
python -m pip install PyQt6 requests --quiet

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
    echo [-] Error: No .py file found to execute.
    pause
    exit /b 1
)

echo [+] Starting %TARGET_SCRIPT%...
python "%TARGET_SCRIPT%"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [-] Application closed with an error.
    pause
)
