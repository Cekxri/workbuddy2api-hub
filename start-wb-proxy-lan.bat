@echo off
setlocal
rem ===========================================================
rem  WorkBuddy proxy - LAN mode
rem
rem  Listens on every network interface so phones, laptops and
rem  other PCs on the same network can use it.
rem
rem  An API key is REQUIRED in this mode and is generated
rem  automatically - copy it from the window that opens.
rem
rem  ASCII-only on purpose: .bat files are parsed using the
rem  console code page, so non-ASCII text breaks the parser.
rem ===========================================================

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8788"
set "KEY=%~2"
if "%KEY%"=="" set "KEY=qwer.1234"
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
echo   WorkBuddy proxy - LAN MODE
echo.
echo   Port %PORT% - your API address, dashboard link and API
echo   key are printed below once the server is up.
echo.
echo   If other devices cannot connect, run allow-firewall.bat
echo   once as administrator.
echo.
echo   Keep this window open. Closing it stops the server.
echo ===========================================================
echo.

"%PYEXE%" "%SCRIPT%" --port %PORT% --lan --api-key %KEY%

echo.
echo [server exited]
pause

