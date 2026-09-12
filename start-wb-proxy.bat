@echo off
setlocal
rem ===========================================================
rem  WorkBuddy international proxy - launcher
rem  Usage: double-click, or  start-wb-proxy.bat [port]
rem
rem  This file is intentionally ASCII-only: .bat files are read
rem  using the console code page, and non-ASCII text breaks the
rem  parser on some systems.
rem ===========================================================

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8788"
set "HERE=%~dp0"
set "SCRIPT=%HERE%wb_proxy.py"

if not exist "%SCRIPT%" (
    echo [ERROR] wb_proxy.py not found next to this script.
    echo         expected: %SCRIPT%
    echo.
    pause
    exit /b 1
)

set "PYEXE="

rem ---- 1) bundled runtime (ships with the zip) ----
if exist "%HERE%python\python.exe" (
    "%HERE%python\python.exe" --version >nul 2>nul
    if not errorlevel 1 set "PYEXE=%HERE%python\python.exe"
)
if defined PYEXE goto run

rem ---- 2) python on PATH ----
python --version >nul 2>nul
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto run

rem ---- 3) py launcher ----
py --version >nul 2>nul
if not errorlevel 1 set "PYEXE=py"
if defined PYEXE goto run

rem ---- 4) Codex bundled runtimes ----
call :find_codex
if defined PYEXE goto run

echo [ERROR] No usable Python found.
echo.
echo Options:
echo   1. Use the packaged zip, which already contains python\
echo   2. Install Python 3.9+ from https://www.python.org/downloads/
echo      (tick "Add python.exe to PATH" during setup)
echo   3. Edit this file and set PYEXE to a full path, e.g.
echo        set "PYEXE=C:\Python312\python.exe"
echo.
pause
exit /b 1

:find_codex
if not exist "%USERPROFILE%\.cache\codex-runtimes" goto :eof
for /d %%D in ("%USERPROFILE%\.cache\codex-runtimes\*") do (
    if not defined PYEXE (
        for /f "delims=" %%P in ('dir /b /s "%%~D\python.exe" 2^>nul') do (
            if not defined PYEXE (
                "%%~P" --version >nul 2>nul
                if not errorlevel 1 set "PYEXE=%%~P"
            )
        )
    )
)
goto :eof

:run
echo ===========================================================
echo   WorkBuddy proxy
echo.
echo   API      : http://127.0.0.1:%PORT%/v1
echo   Dashboard: http://127.0.0.1:%PORT%/
echo.
echo   Python   : %PYEXE%
echo.
echo   Keep this window open. Closing it stops the server.
echo   Press Ctrl+C to stop.
echo ===========================================================
echo.

"%PYEXE%" "%SCRIPT%" --port %PORT%

echo.
echo [server exited]
pause

