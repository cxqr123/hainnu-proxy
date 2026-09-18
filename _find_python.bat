@echo off
rem Usage: call _find_python.bat
rem Sets PY to a usable python.exe (portable across machines).
rem Order: built-in runtime\ (self-contained) -> project-local .venv -> py/python/python3 on PATH.
set "PY=%~dp0runtime\python.exe"
if exist "%PY%" exit /b 0
set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%PY%" exit /b 0
set "PY="
where py >nul 2>&1 && set "PY=py"
if defined PY exit /b 0
where python >nul 2>&1 && set "PY=python"
if defined PY exit /b 0
where python3 >nul 2>&1 && set "PY=python3"
if defined PY exit /b 0
echo.
echo [ERROR] No python found.
echo   The bundled runtime\ folder seems missing; re-extract the zip intact,
echo   or run the "0.*.bat" dependency installer in the project root
echo   to build a local .venv.
echo.
exit /b 1
