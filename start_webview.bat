@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "ROOT=%~dp0"
set "PYTHON_EXE="
set "PYTHONW_EXE="
set "PYTHON_SITE_PACKAGES="
set "PYTHON_ENV_ROOT="

call :check_python "%ROOT%.venv312\Scripts\python.exe" "%ROOT%.venv312\Scripts\pythonw.exe"
if defined PYTHON_EXE goto check_runtime

call :check_venv_base "%ROOT%.venv312"
if defined PYTHON_EXE goto check_runtime

call :check_python "%ROOT%.venv\Scripts\python.exe" "%ROOT%.venv\Scripts\pythonw.exe"
if defined PYTHON_EXE goto check_runtime

call :check_venv_base "%ROOT%.venv"
if defined PYTHON_EXE goto check_runtime

for /f "delims=" %%P in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%P"
    set "PYTHON_SITE_PACKAGES="
    set "PYTHON_ENV_ROOT="
    goto find_pythonw
)
goto try_py

:find_pythonw
for /f "delims=" %%P in ('where pythonw 2^>nul') do (
    set "PYTHONW_EXE=%%P"
    goto check_runtime
)
goto check_runtime

:try_py
for /f "delims=" %%P in ('where py 2^>nul') do (
    "%%P" -c "import webview, PIL, requests, numpy" >nul 2>&1
    if errorlevel 1 goto missing_webview
    start "" "%%P" "%ROOT%webview_app.py"
    exit /b 0
)

echo [ERROR] Could not find a usable Python runtime.
pause
exit /b 1

:check_runtime
if defined PYTHON_SITE_PACKAGES (
    set "VIRTUAL_ENV=%PYTHON_ENV_ROOT%"
    set "PYTHONPATH=%PYTHON_SITE_PACKAGES%"
)

"%PYTHON_EXE%" -c "import webview, PIL, requests, numpy" >nul 2>&1
if errorlevel 1 goto missing_webview

echo [INFO] Using runtime: %PYTHON_EXE%
if defined PYTHON_SITE_PACKAGES (
    echo [INFO] Using site-packages fallback: %PYTHON_SITE_PACKAGES%
)

if defined PYTHONW_EXE (
    start "" "%PYTHONW_EXE%" "%ROOT%webview_app.py"
) else (
    start "" "%PYTHON_EXE%" "%ROOT%webview_app.py"
)
exit /b 0

:missing_webview
echo [ERROR] Could not find a Python runtime with pywebview and the core dependencies.
echo Try one of these:
echo.
echo   python -m pip install pywebview Pillow requests numpy
echo   .venv312\Scripts\pip.exe install pywebview Pillow requests numpy
echo.
pause
exit /b 1

:check_python
if exist "%~1" (
    "%~1" -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=%~1"
        if exist "%~2" set "PYTHONW_EXE=%~2"
        set "PYTHON_SITE_PACKAGES="
        set "PYTHON_ENV_ROOT="
    )
)
exit /b 0

:check_venv_base
set "VENV_DIR=%~1"
if not exist "%VENV_DIR%\pyvenv.cfg" exit /b 0

set "VENV_HOME="
for /f "tokens=1,* delims==" %%A in ('type "%VENV_DIR%\pyvenv.cfg" ^| findstr /b /c:"home ="') do (
    set "VENV_HOME=%%B"
)

if not defined VENV_HOME exit /b 0
set "VENV_HOME=%VENV_HOME:~1%"

if exist "%VENV_HOME%\python.exe" (
    set "PYTHON_EXE=%VENV_HOME%\python.exe"
    if exist "%VENV_HOME%\pythonw.exe" set "PYTHONW_EXE=%VENV_HOME%\pythonw.exe"
    set "PYTHON_SITE_PACKAGES=%VENV_DIR%\Lib\site-packages"
    set "PYTHON_ENV_ROOT=%VENV_DIR%"
)
exit /b 0
