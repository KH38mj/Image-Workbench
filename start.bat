@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON_EXE="
set "PYTHONW_EXE="

call :check_python "%ROOT%.venv312\Scripts\python.exe" "%ROOT%.venv312\Scripts\pythonw.exe"
if defined PYTHON_EXE goto run

call :check_python "%ROOT%.venv\Scripts\python.exe" "%ROOT%.venv\Scripts\pythonw.exe"
if defined PYTHON_EXE goto run

for /f "delims=" %%P in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%P"
    goto find_pythonw
)
goto try_py

:find_pythonw
for /f "delims=" %%P in ('where pythonw 2^>nul') do (
    set "PYTHONW_EXE=%%P"
    goto run
)
goto run

:try_py
for /f "delims=" %%P in ('where py 2^>nul') do (
    start "" "%%P" "%ROOT%gui.py"
    exit /b 0
)

echo [ERROR] Could not find a usable Python runtime.
echo Install Python or repair the project virtual environment, then try again.
pause
exit /b 1

:run
if defined PYTHONW_EXE (
    start "" "%PYTHONW_EXE%" "%ROOT%gui.py"
) else (
    start "" "%PYTHON_EXE%" "%ROOT%gui.py"
)
exit /b 0

:check_python
if exist "%~1" (
    "%~1" -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=%~1"
        if exist "%~2" set "PYTHONW_EXE=%~2"
    )
)
exit /b 0
